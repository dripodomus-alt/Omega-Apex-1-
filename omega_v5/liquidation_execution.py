#!/usr/bin/env python3
# ==============================================================================
# liquidation_execution.py -- liquidation calldata and eth_call simulation.
# ==============================================================================

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from web3 import Web3

from . import rpc_layer
from .aave_liquidations import ApexLiquidationCandidatePacket
from .config import CHAIN_ID, LIQUIDATION_EXECUTOR_ADDRESS, LIQUIDATION_MIN_NET_PROFIT_USD
from .oracle_layer import token_price_usd
from .accounting import usd_to_token_raw_floor
from .paths import output_path
from .payload_envelope import PayloadEnvelope, build_payload_envelope
from .revert_decoder import format_revert
from .rpc_layer import TOKEN_ADDRESSES, TOKEN_DECIMALS


EXECUTOR_ARTIFACT = output_path("OmegaLiquidationExecutor.sol", "OmegaLiquidationExecutor.json")
EXECUTE_LIQUIDATION_SELECTOR = Web3.keccak(
    text=(
        "executeLiquidation((address,address,address,uint256,address[],address[],"
        "uint256,uint256,uint256,bytes32,bytes32))"
    )
)[:4].hex()


def _load_executor_abi() -> list:
    if not EXECUTOR_ARTIFACT.exists():
        raise RuntimeError(f"artifact missing: {EXECUTOR_ARTIFACT}. Run `forge build` first.")
    return json.loads(EXECUTOR_ARTIFACT.read_text(encoding="utf-8"))["abi"]


def _packet_dict(packet: ApexLiquidationCandidatePacket | dict[str, Any]) -> dict[str, Any]:
    return packet.as_packet() if hasattr(packet, "as_packet") else dict(packet)


def _selected_source_id(packet: ApexLiquidationCandidatePacket | dict[str, Any]) -> int | None:
    if isinstance(packet, ApexLiquidationCandidatePacket):
        return packet.selected_capital_source.source_id if packet.selected_capital_source else None
    source = packet.get("selectedCapitalSource")
    if not source:
        return None
    return int(source.get("source_id", source.get("sourceId", -1)))


def _pool_addresses_for_exit(packet_data: dict[str, Any], pools: dict[str, dict]) -> list[str]:
    quote = packet_data.get("exitQuote") or {}
    route = quote.get("route") or []
    if len(route) <= 1:
        return []
    pool_id = quote.get("poolId") or ""
    pool = pools.get(pool_id)
    address = (pool or {}).get("address", "")
    if not Web3.is_address(address):
        raise RuntimeError(f"missing executable exit pool address for poolId={pool_id}")
    return [Web3.to_checksum_address(address)]


def _token_path_for_exit(packet_data: dict[str, Any]) -> list[str]:
    quote = packet_data.get("exitQuote") or {}
    route = quote.get("route") or []
    if len(route) <= 1:
        return []
    addresses: list[str] = []
    for symbol in route:
        address = TOKEN_ADDRESSES.get(symbol, "")
        if not Web3.is_address(address):
            raise RuntimeError(f"missing token address for liquidation exit symbol={symbol}")
        addresses.append(Web3.to_checksum_address(address))
    return addresses


def _min_profit_raw(debt_symbol: str) -> int:
    price = token_price_usd(debt_symbol)
    decimals = TOKEN_DECIMALS.get(debt_symbol, 18)
    return usd_to_token_raw_floor(LIQUIDATION_MIN_NET_PROFIT_USD, price, decimals)


def _state_hash(packet_data: dict[str, Any]) -> bytes:
    payload = "|".join([
        str(packet_data.get("borrower", "")),
        str(packet_data.get("blockNumber", "")),
        str(packet_data.get("healthFactor", "")),
        str(packet_data.get("debtSymbol", "")),
        str(packet_data.get("collateralSymbol", "")),
        str(packet_data.get("debtToCoverRaw", "")),
    ])
    return Web3.keccak(text=payload)


def _nonce_hash(packet_data: dict[str, Any]) -> bytes:
    payload = "|".join([
        "omega_v5_liquidation",
        str(packet_data.get("borrower", "")),
        str(packet_data.get("blockNumber", "")),
        str(packet_data.get("debtSymbol", "")),
        str(packet_data.get("collateralSymbol", "")),
        str(packet_data.get("debtToCoverRaw", "")),
    ])
    return Web3.keccak(text=payload)


def build_liquidation_tx(
    packet: ApexLiquidationCandidatePacket | dict[str, Any],
    pools: dict[str, dict],
    *,
    nonce: int = 0,
    base_fee_gwei: Decimal = Decimal("50"),
    deadline_blocks: int = 5,
) -> dict[str, Any]:
    packet_data = _packet_dict(packet)
    if packet_data.get("authority") != "SCANNER_ONLY":
        raise RuntimeError("liquidation packet authority must be SCANNER_ONLY")
    if packet_data.get("nextStage") != "LIQUIDATION":
        raise RuntimeError(f"liquidation packet is not execution-ready: {packet_data.get('rejectReasons')}")
    if _selected_source_id(packet) != 0:
        raise RuntimeError("current liquidation adapter is Aave flash-only; selected capital source must be AAVE_V3")
    if not LIQUIDATION_EXECUTOR_ADDRESS or not Web3.is_address(LIQUIDATION_EXECUTOR_ADDRESS):
        raise RuntimeError("LIQUIDATION_EXECUTOR_ADDRESS is required to build liquidation calldata")
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC is not connected; call rpc_layer.connect() first")

    debt_symbol = packet_data["debtSymbol"]
    collateral_symbol = packet_data["collateralSymbol"]
    debt_asset = TOKEN_ADDRESSES.get(debt_symbol, "")
    collateral_asset = TOKEN_ADDRESSES.get(collateral_symbol, "")
    if not Web3.is_address(debt_asset) or not Web3.is_address(collateral_asset):
        raise RuntimeError("liquidation packet references unknown token address")

    current_block = int(rpc_layer.w3.eth.block_number)
    try:
        from .gas_oracle import eip1559_fee_params

        max_fee, priority_fee, gas_fee_source = eip1559_fee_params()
    except Exception:
        max_fee = int((base_fee_gwei + Decimal("30")) * Decimal("1e9"))
        priority_fee = int(Decimal("30") * Decimal("1e9"))
        gas_fee_source = "legacy_base_plus_30_gwei"
    params = (
        Web3.to_checksum_address(packet_data["borrower"]),
        Web3.to_checksum_address(collateral_asset),
        Web3.to_checksum_address(debt_asset),
        int(packet_data["debtToCoverRaw"]),
        _pool_addresses_for_exit(packet_data, pools),
        _token_path_for_exit(packet_data),
        _min_profit_raw(debt_symbol),
        max_fee,
        current_block + int(deadline_blocks),
        _nonce_hash(packet_data),
        _state_hash(packet_data),
    )

    contract = rpc_layer.w3.eth.contract(
        address=Web3.to_checksum_address(LIQUIDATION_EXECUTOR_ADDRESS),
        abi=_load_executor_abi(),
    )
    try:
        data = contract.encodeABI(fn_name="executeLiquidation", args=[params])
    except AttributeError:
        data = contract.encode_abi("executeLiquidation", args=[params])
    expected_selector = (
        EXECUTE_LIQUIDATION_SELECTOR
        if EXECUTE_LIQUIDATION_SELECTOR.startswith("0x")
        else "0x" + EXECUTE_LIQUIDATION_SELECTOR
    )
    if not str(data).startswith(expected_selector):
        raise RuntimeError("liquidation calldata selector mismatch")
    return {
        "chainId": CHAIN_ID,
        "nonce": nonce,
        "to": Web3.to_checksum_address(LIQUIDATION_EXECUTOR_ADDRESS),
        "value": 0,
        "data": data,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee,
        "gas": 900_000,
        "gasFeeSource": gas_fee_source,
        "type": 2,
    }


def build_liquidation_payload_envelope(
    packet: ApexLiquidationCandidatePacket | dict[str, Any],
    tx: dict[str, Any],
) -> PayloadEnvelope:
    packet_data = _packet_dict(packet)
    return build_payload_envelope(
        kind="LIQUIDATION",
        target=tx["to"],
        calldata=tx["data"],
        unique_salt=str(packet_data.get("blockNumber", "")),
        metadata={
            "borrower": packet_data.get("borrower", ""),
            "debt_symbol": packet_data.get("debtSymbol", ""),
            "collateral_symbol": packet_data.get("collateralSymbol", ""),
            "debt_to_cover_raw": packet_data.get("debtToCoverRaw", ""),
            "expected_net_profit_usd": packet_data.get("expectedNetProfitUsd", ""),
        },
    )


def simulate_liquidation(tx: dict[str, Any], from_addr: str | None = None) -> tuple[bool, str]:
    payload_hash = Web3.keccak(
        text=json.dumps(
            {
                "chainId": tx.get("chainId"),
                "to": tx.get("to"),
                "value": tx.get("value", 0),
                "data": tx.get("data"),
                "gas": tx.get("gas"),
                "maxFeePerGas": tx.get("maxFeePerGas"),
                "maxPriorityFeePerGas": tx.get("maxPriorityFeePerGas"),
                "type": tx.get("type"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    ).hex()
    call_tx = {"to": tx["to"], "data": tx["data"], "value": tx.get("value", 0)}
    if from_addr:
        call_tx["from"] = from_addr
    exact_w3 = web3_for_lane(LANE_EXACT_LIQUIDATION_ETH_CALL)
    providers = []
    for provider in (exact_w3, rpc_layer.w3):
        if provider is not None and all(provider is not existing for existing in providers):
            providers.append(provider)
    if not providers:
        record_truth_candidate({
            "payload_hash": payload_hash,
            "stage": "LIQUIDATION",
            "status": "NO_EXACT_CALL_RPC",
            "to": tx.get("to", ""),
        })
        return False, "liquidation exact-call RPC unavailable"
    for attempt, provider in enumerate(providers, 1):
        try:
            result = provider.eth.call(call_tx, block_identifier="latest")
            record_truth_candidate({
                "payload_hash": payload_hash,
                "stage": "LIQUIDATION",
                "status": "EXACT_CALL_PASS",
                "to": tx.get("to", ""),
                "from": from_addr or "",
                "result": result.hex(),
                "attempt": attempt,
            })
            return True, result.hex()
        except Exception as exc:
            detail = f"{type(exc).__name__}: {format_revert(exc)}"
            if attempt < len(providers) and any(
                marker in detail.lower()
                for marker in ("429", "rate limit", "timeout", "tls", "ssl", "connection")
            ):
                continue
            record_truth_candidate({
                "payload_hash": payload_hash,
                "stage": "LIQUIDATION",
                "status": "EXACT_CALL_FAIL",
                "to": tx.get("to", ""),
                "from": from_addr or "",
                "detail": detail,
                "attempt": attempt,
            })
            return False, detail

