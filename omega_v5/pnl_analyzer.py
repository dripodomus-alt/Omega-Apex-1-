#!/usr/bin/env python3
# ==============================================================================
# pnl_analyzer.py -- Post-trade profit and loss calculator.
#
# This module analyzes confirmed transaction receipts to calculate the real,
# net profit in USD by accounting for gas costs and the value of all assets
# swept to the executor wallet.
# ==============================================================================

import argparse
import json
import sys
from decimal import Decimal

from web3 import Web3
from web3.types import TxReceipt

# --- Assumed Project Infrastructure ---
# The following imports assume the existence of modules within the omega_v5
# package that provide core functionalities like RPC connection, configuration,
# token information (decimals, symbol), and on-chain pricing.
try:
    from . import config
    from . import rpc_layer
    # Hypothetical module to get token info (symbol, decimals) by address
    from .token_db import Token, get_token_by_address
    # Hypothetical module to get the USD price of a token at a specific block
    from .pricing import get_price_usd
except ImportError as e:
    print(f"Failed to import project modules: {e}. Ensure this script is run as part of the omega_v5 package.", file=sys.stderr)
    sys.exit(1)

# Standard ERC20 Transfer event signature: Transfer(address,address,uint256)
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _get_native_profit_from_trace(w3: Web3, tx_hash: str, executor_address: str) -> Decimal:
    """
    Uses debug_traceTransaction with a callTracer to find native asset profit.
    This is more robust for profit delivered as MATIC/ETH instead of an ERC20.
    """
    native_profit = Decimal("0")
    try:
        trace = w3.provider.make_request(
            "debug_traceTransaction", [tx_hash, {"tracer": "callTracer"}]
        )
    except Exception as e:
        print(f"Warning: debug_traceTransaction failed: {e}. Native profit will be ignored.", file=sys.stderr)
        return native_profit

    def find_value_transfers(call: dict):
        nonlocal native_profit
        if call.get("to", "").lower() == executor_address.lower() and int(call.get("value", "0x0"), 16) > 0:
            native_profit += Decimal(int(call.get("value", "0x0"), 16))

        for sub_call in call.get("calls", []):
            find_value_transfers(sub_call)

    find_value_transfers(trace)
    return native_profit


def analyze_transaction_pnl(w3: Web3, tx_hash: str) -> dict:
    """
    Analyzes a single transaction to calculate its gross and net profit in USD.

    Args:
        w3: The Web3 instance.
        tx_hash: The transaction hash to analyze.

    Returns:
        A dictionary containing:
        - gross_profit_usd: The total value of assets swept to the executor.
        - net_profit_usd: The gross profit minus gas costs.
        - gas_cost_usd: The calculated gas cost in USD.
    """
    try:
        receipt: TxReceipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception as e:
        print(f"Error fetching receipt for {tx_hash}: {e}", file=sys.stderr)
        return Decimal("0")

    block_number = receipt["blockNumber"]

    # 1. Calculate Gas Cost in USD
    gas_used = Decimal(receipt["gasUsed"])
    effective_gas_price = Decimal(receipt["effectiveGasPrice"])
    gas_cost_native = gas_used * effective_gas_price

    # Use WPOL as the strict native token for gas pricing.
    native_token_address = getattr(config, "WPOL_ADDRESS", None)
    if not native_token_address:
        print("Warning: Native token address (WPOL_ADDRESS) not found in config. Gas cost cannot be calculated in USD.", file=sys.stderr)
        gas_cost_usd = Decimal("0")
    else:
        native_price_usd = get_price_usd(native_token_address, block_identifier=block_number)
        if native_price_usd is None:
            print(f"Warning: Could not determine price for native token. Gas cost will be ignored.", file=sys.stderr)
            gas_cost_usd = Decimal("0")
        else:
            # Assume native token (e.g., MATIC) has 18 decimals
            gas_cost_usd = (gas_cost_native / Decimal(10**18)) * Decimal(native_price_usd)

    # If the transaction failed, the PnL is simply the negative gas cost.
    if receipt["status"] != 1:
        print(f"Transaction {tx_hash} failed (reverted). PnL is negative gas cost.", file=sys.stderr)
        return {
            "gross_profit_usd": Decimal("0"),
            "net_profit_usd": -gas_cost_usd,
            "gas_cost_usd": gas_cost_usd,
        }

    # 2. Calculate Gross Profit in USD by summing incoming transfers to the executor wallet
    # 2. Calculate Gross Profit in USD
    gross_profit_usd = Decimal("0")
    executor_wallet_address = Web3.to_checksum_address(config.EXECUTOR_WALLET)

    # 2a. Add native asset profit from trace
    native_profit_wei = _get_native_profit_from_trace(w3, tx_hash, executor_wallet_address)
    if native_profit_wei > 0:
        native_price_usd = get_price_usd(native_token_address, block_identifier=block_number) if native_token_address else Decimal("0")
        if native_price_usd and native_price_usd > 0:
            native_profit_usd = (native_profit_wei / Decimal(10**18)) * Decimal(native_price_usd)
            gross_profit_usd += native_profit_usd
            print(f"  -> Detected internal transfer of {native_profit_wei / Decimal(10**18):.6f} native token (${native_profit_usd:.2f}) to executor wallet.", file=sys.stderr)
        else:
            print(f"Warning: Could not price native profit of {native_profit_wei} wei.", file=sys.stderr)

    # 2b. Add ERC20 profit from event logs
    for log in receipt["logs"]:
        # Check if it's an ERC20 Transfer event with the correct number of topics
        if log["topics"][0].hex() == TRANSFER_EVENT_TOPIC and len(log["topics"]) == 3:
            # The 'to' address is the 3rd topic, padded to 32 bytes.
            # We extract the last 20 bytes for the address.
            to_address = Web3.to_checksum_address(log["topics"][2][-20:].hex())

            if to_address == executor_wallet_address:
                token_address = Web3.to_checksum_address(log["address"])
                token: Token = get_token_by_address(token_address)

                if not token:
                    print(f"Warning: Unknown token transferred: {token_address}", file=sys.stderr)
                    continue

                # Decode the amount from the data field
                amount_raw = int.from_bytes(log["data"], 'big')
                amount_adjusted = Decimal(amount_raw) / Decimal(10**token.decimals)

                # Get token price in USD
                token_price_usd = get_price_usd(token_address, block_identifier=block_number)
                if token_price_usd is None:
                    print(f"Warning: Could not get price for {token.symbol}. Ignoring this transfer.", file=sys.stderr)
                    continue

                transfer_value_usd = amount_adjusted * Decimal(token_price_usd)
                gross_profit_usd += transfer_value_usd
                print(f"  -> Detected incoming transfer of {amount_adjusted:.6f} {token.symbol} (${transfer_value_usd:.2f}) to executor wallet.", file=sys.stderr)

    net_profit_usd = gross_profit_usd - gas_cost_usd

    print(f"Analysis for {tx_hash}:", file=sys.stderr)
    print(f"  Gross Profit: ${gross_profit_usd:.4f} USD", file=sys.stderr)
    print(f"  Gas Cost:     ${gas_cost_usd:.4f} USD", file=sys.stderr)
    print(f"  Net Profit:   ${net_profit_usd:.4f} USD", file=sys.stderr)

    return {
        "gross_profit_usd": gross_profit_usd,
        "net_profit_usd": net_profit_usd,
        "gas_cost_usd": gas_cost_usd,
    }


def main():
    """
    Main entry point for the PnL analyzer script.
    """
    parser = argparse.ArgumentParser(description="Calculate Net Profit/Loss (PnL) for a list of transactions.")
    # Changed to handle one hash at a time to simplify JSON output and script integration.
    parser.add_argument(
        "--tx-hash",
        required=True,
        help="A single transaction hash to analyze."
    )
    parser.add_argument(
        "--rpc-url",
        help="Optional RPC URL to use. Overrides the one from the config/environment."
    )
    args = parser.parse_args()

    if not getattr(config, "EXECUTOR_WALLET", None):
        print("Fatal: EXECUTOR_WALLET is not defined in the environment/config.", file=sys.stderr)
        sys.exit(1)

    w3 = None
    if args.rpc_url:
        try:
            w3 = Web3(Web3.HTTPProvider(args.rpc_url))
            if not w3.is_connected():
                raise ConnectionError(f"Could not connect to provided RPC: {args.rpc_url}")
        except Exception as e:
            print(f"Fatal: Could not connect to provided RPC endpoint. {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Initialize RPC connection from the project's rpc_layer
        try:
            rpc_layer.init()
            if not rpc_layer.RPC_LIVE or rpc_layer.w3 is None:
                raise ConnectionError("RPC layer could not be initialized or is not live.")
            w3 = rpc_layer.w3
        except Exception as e:
            print(f"Fatal: Could not connect to default RPC endpoint. {e}", file=sys.stderr)
            sys.exit(1)

    pnl_data = analyze_transaction_pnl(w3, args.tx_hash)

    # Output the final result as JSON to stdout, converting Decimals to floats
    result = {k: float(v) for k, v in pnl_data.items()}
    print(json.dumps(result))


if __name__ == "__main__":
    main()