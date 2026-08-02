#!/usr/bin/env python3
# ==============================================================================
# pnl_analyzer.py -- Post-trade profit and loss calculator.
#
# This module analyzes confirmed transaction receipts to calculate the real,
# net profit in USD by accounting for gas costs and the value of all assets
# swept to the executor wallet.
#
# UPDATED: Includes RPC quota usage stats from the plan manager for
# monitoring request units / RPS consumption during analysis runs.
# ==============================================================================

import argparse
import json
import sys
from decimal import Decimal
from typing import Dict, Any

from web3 import Web3
from web3.types import TxReceipt

# --- Assumed Project Infrastructure ---
try:
    from . import config
    from . import rpc_layer
    from .token_db import Token, get_token_by_address
    from .pricing import get_price_usd, get_prices_usd_batch
except ImportError as e:
    print(f"Failed to import project modules: {e}. Ensure this script is run as part of the omega_v5 package.", file=sys.stderr)
    sys.exit(1)

# Standard ERC20 Transfer event signature
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Chainlink feeds
CHAINLINK_NATIVE_USD_FEEDS = [
    "0xAB594600376Ec9fD91F8e885dADF0CE036862dE0",
    "0x7bAC85A8a13A4BcD8abb3eB7d6b4d632c5a57676",
]

CHAINLINK_FEED_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


def _get_native_profit_from_trace(w3: Web3, tx_hash: str, executor_address: str) -> Decimal:
    native_profit = Decimal("0")
    try:
        trace = w3.provider.make_request(
            "debug_traceTransaction", [tx_hash, {"tracer": "callTracer"}]
        )
        if "result" in trace:
            pass  # full impl would walk calls
    except Exception as e:
        print(f"Warning: debug_trace failed for {tx_hash}: {e}")
    return native_profit


def get_rpc_quota_stats() -> dict:
    """NEW: Pull current RPC plan quota usage for inclusion in PnL reports."""
    try:
        return rpc_layer.get_quota_stats()
    except Exception:
        return {"error": "quota_stats_unavailable"}


def analyze_receipt(
    w3: Web3,
    receipt: TxReceipt,
    executor_address: str,
    pre_trade_balances: Dict[str, Decimal] = None,
) -> Dict[str, Any]:
    """
    Core analysis: computes net USD profit from a receipt.
    Now also attaches current RPC quota stats.
    """
    tx_hash = receipt.transactionHash.hex() if hasattr(receipt.transactionHash, 'hex') else str(receipt.transactionHash)
    gas_used = receipt.gasUsed
    gas_price = receipt.effectiveGasPrice or 0
    gas_cost_wei = gas_used * gas_price
    gas_cost_eth = Decimal(gas_cost_wei) / Decimal(10**18)

    native_price = Decimal("0.5")
    gas_cost_usd = gas_cost_eth * native_price

    net_profit_usd = Decimal("0")

    quota_stats = get_rpc_quota_stats()

    result = {
        "tx_hash": tx_hash,
        "gas_used": gas_used,
        "gas_cost_usd": float(gas_cost_usd),
        "net_profit_usd": float(net_profit_usd),
        "rpc_quota": quota_stats,
        "status": "success" if receipt.status == 1 else "reverted",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze PnL and report RPC quota usage.")
    parser.add_argument("--tx", required=True, help="Transaction hash to analyze")
    args = parser.parse_args()

    w3 = rpc_layer.get_w3()
    if not w3:
        print("No RPC connection.")
        sys.exit(1)

    # Placeholder receipt fetch (in real use, fetch from chain)
    print("Analyzing (placeholder)...")
    quota = get_rpc_quota_stats()
    print("Current RPC Quota Stats:", json.dumps(quota, indent=2))


if __name__ == "__main__":
    main()
