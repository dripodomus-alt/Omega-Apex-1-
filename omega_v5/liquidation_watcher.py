#!/usr/bin/env python3
# ==============================================================================
# liquidation_watcher.py -- autonomous Aave liquidation watcher/executor lane.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import os
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from eth_account import Account

from . import rpc_layer
from . import redis_cache
from .aave_liquidations import ApexLiquidationCandidatePacket, ExitQuote
from .liquidation_capital import CapitalSourceCheck
from .config import PRIVATE_KEY
from .execution import _broadcast_w3, _receipt_dict, execution_armed, execution_guard_status, wallet_address
from .execution_trace import compute_trace_hash, record_execution_trace
from .liquidation_execution import build_liquidation_payload_envelope, build_liquidation_tx, simulate_liquidation
from .pnl_tracker import record_pnl_event
from .rpc_layer import DEEP_POOL_REGISTRY, connect, load_all_live_pools
from .runtime_control import runtime_mode, set_runtime_mode
from .transport_lanes import record_broadcast_payload, record_executable_route, record_pending_receipt


DEFAULT_INTERVAL_SECONDS = int(os.getenv("OMEGA_LIQUIDATION_WATCH_INTERVAL_SECONDS", "300") or "300")
DEFAULT_MAX_PACKETS = int(os.getenv("OMEGA_LIQUIDATION_MAX_PER_CYCLE", "2") or "2")
DEFAULT_RPC_URL = os.getenv("OMEGA_LIQUIDATION_RPC_URL") or os.getenv("POLYGON_RPC_URL") or os.getenv("RPC_URL") or ""


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _reconstruct_pools(pools_str: str) -> dict:
    """Deserializes a JSON string of pools, converting numeric strings to Decimals."""
    pools = json.loads(pools_str)
    for pool in pools.values():
        for key in [
            "sqrtPriceX96", "liquidity", "fee", "fee_bps", "A", "swap_fee",
            "decimal_adjustment", "tvl_usd", "total_executable_liquidity_usd"
        ]:
            if key in pool and pool[key] is not None:
                pool[key] = Decimal(str(pool[key]))
        if "reserves" in pool and pool["reserves"]:
            pool["reserves"] = [Decimal(str(r)) for r in pool["reserves"]]
        if "weights" in pool and pool["weights"]:
            pool["weights"] = [Decimal(str(w)) for w in pool["weights"]]
    return pools


def _reconstruct_packets(packets_str: str) -> list[ApexLiquidationCandidatePacket]:
    """Deserializes a JSON string of liquidation packets."""
    packets_data = json.loads(packets_str)
    packets = []
    for data in packets_data:
        try:
            # Convert numeric strings back to Decimal
            for key in ["health_factor", "debt_to_cover", "seized_collateral_estimate", "gross_profit_usd", "expected_net_profit_usd"]:
                if key in data and data[key] is not None:
                    data[key] = Decimal(str(data[key]))

            # Reconstruct nested objects if they exist
            if "exit_quote" in data and data["exit_quote"]:
                eq_data = data["exit_quote"]
                for key in ["collateral_amount", "debt_out"]:
                     if key in eq_data and eq_data[key] is not None:
                        eq_data[key] = Decimal(str(eq_data[key]))
                data["exit_quote"] = ExitQuote(**eq_data)

            if "capital_sources" in data and data["capital_sources"]:
                data["capital_sources"] = [CapitalSourceCheck(**cs_data) for cs_data in data["capital_sources"]]

            if "selected_capital_source" in data and data["selected_capital_source"]:
                data["selected_capital_source"] = CapitalSourceCheck(**data["selected_capital_source"])

            packets.append(ApexLiquidationCandidatePacket(**data))
        except (TypeError, KeyError, InvalidOperation) as e:
            print(f"  [CONSUMER] Skipping malformed liquidation packet: {e}")
            continue
    return packets


def _payload_hash(tx: dict[str, Any]) -> str:
    return compute_trace_hash({
        "chainId": tx.get("chainId"),
        "to": tx.get("to"),
        "value": tx.get("value", 0),
        "data": tx.get("data"),
        "gas": tx.get("gas"),
        "maxFeePerGas": tx.get("maxFeePerGas"),
        "maxPriorityFeePerGas": tx.get("maxPriorityFeePerGas"),
        "type": tx.get("type"),
    })


def _route_from_packet(packet: ApexLiquidationCandidatePacket) -> list[str]:
    route = packet.exit_quote.route if packet.exit_quote else []
    if route:
        return list(route)
    return [packet.collateral_symbol, packet.debt_symbol]


def _record_rejected(packet: ApexLiquidationCandidatePacket, detail: str) -> None:
    packet_data = packet.as_packet()
    record_execution_trace(
        stage="LIQUIDATION",
        status="SIMULATION_REJECTED",
        mode=runtime_mode(),
        opp_id=f"liq-{packet.borrower[:10]}-{packet.block_number}",
        route=_route_from_packet(packet),
        payload_hash=compute_trace_hash(packet_data),
        metadata={"detail": detail, "packet": packet_data},
    )
    record_pnl_event(
        mode=runtime_mode(),
        stage="LIQUIDATION",
        status="SIMULATION_REJECTED",
        opp_id=f"liq-{packet.borrower[:10]}-{packet.block_number}",
        route=_route_from_packet(packet),
        expected_net_usd=packet.expected_net_profit_usd,
        realized_net_usd="0",
        metadata={"detail": detail},
    )


def _process_packet(packet: ApexLiquidationCandidatePacket, pools: dict[str, dict], *, no_submit: bool) -> dict[str, Any]:
    opp_id = f"liq-{packet.borrower[:10]}-{packet.block_number}-{packet.debt_symbol}-{packet.collateral_symbol}"
    route = _route_from_packet(packet)
    wallet = wallet_address()
    try:
        tx = build_liquidation_tx(packet, pools, nonce=0)
        envelope = build_liquidation_payload_envelope(packet, tx)
        payload_hash = _payload_hash(tx)
    except Exception as exc:
        detail = f"payload_build_failed: {type(exc).__name__}: {exc}"
        _record_rejected(packet, detail)
        return {"ok": False, "status": "PAYLOAD_BUILD_FAILED", "detail": detail, "opp_id": opp_id}

    sim_ok, sim_detail = simulate_liquidation(tx, from_addr=wallet or None)
    if not sim_ok:
        detail = f"liquidation_exact_call_failed: {sim_detail}"
        record_execution_trace(
            stage="LIQUIDATION",
            status="SIMULATION_REJECTED",
            mode=runtime_mode(),
            opp_id=opp_id,
            route=route,
            envelope=envelope.as_dict(),
            payload_hash=payload_hash,
            metadata={"detail": detail, "packet": packet.as_packet()},
        )
        record_pnl_event(
            mode=runtime_mode(),
            stage="LIQUIDATION",
            status="SIMULATION_REJECTED",
            opp_id=opp_id,
            route=route,
            expected_net_usd=packet.expected_net_profit_usd,
            realized_net_usd="0",
            metadata={"detail": detail, "payload_hash": payload_hash},
        )
        return {"ok": False, "status": "SIMULATION_REJECTED", "detail": detail, "opp_id": opp_id}

    record_executable_route({
        "opp_id": opp_id,
        "payload_hash": payload_hash,
        "stage": "LIQUIDATION",
        "route": route,
        "expected_net_usd": str(packet.expected_net_profit_usd),
        "tx_to": tx.get("to", ""),
        "tx_gas_limit": tx.get("gas", ""),
        "borrower": packet.borrower,
    })

    if no_submit or runtime_mode() != "live" or not execution_armed():
        record_execution_trace(
            stage="LIQUIDATION",
            status="DRY_RUN_STAGED",
            mode=runtime_mode(),
            opp_id=opp_id,
            route=route,
            envelope=envelope.as_dict(),
            payload_hash=payload_hash,
            metadata={"exact_call": sim_detail, "guards": execution_guard_status(probe=False)},
        )
        record_pnl_event(
            mode=runtime_mode(),
            stage="LIQUIDATION",
            status="DRY_RUN_STAGED",
            opp_id=opp_id,
            route=route,
            expected_net_usd=packet.expected_net_profit_usd,
            realized_net_usd="0",
            metadata={"payload_hash": payload_hash, "exact_call_passed": True},
        )
        return {"ok": True, "status": "DRY_RUN_STAGED", "opp_id": opp_id, "payload_hash": payload_hash}

    tx_w3 = _broadcast_w3()
    if tx_w3 is None:
        return {"ok": False, "status": "NO_BROADCAST_RPC", "detail": "writable broadcast RPC unavailable", "opp_id": opp_id}
    if not PRIVATE_KEY:
        return {"ok": False, "status": "NO_PRIVATE_KEY", "detail": "EXECUTOR_PRIVATE_KEY unset", "opp_id": opp_id}

    nonce = tx_w3.eth.get_transaction_count(wallet)
    tx = build_liquidation_tx(packet, pools, nonce=nonce)
    sim_ok, sim_detail = simulate_liquidation(tx, from_addr=wallet or None)
    if not sim_ok:
        detail = f"liquidation_exact_call_failed_after_nonce: {sim_detail}"
        _record_rejected(packet, detail)
        return {"ok": False, "status": "SIMULATION_REJECTED", "detail": detail, "opp_id": opp_id}

    acct = Account.from_key(PRIVATE_KEY)
    signed = acct.sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    record_broadcast_payload({
        "opp_id": opp_id,
        "payload_hash": payload_hash,
        "stage": "LIQUIDATION",
        "status": "SUBMITTING",
        "to": tx.get("to", ""),
        "nonce": nonce,
        "gas": tx.get("gas", ""),
    })
    tx_hash = tx_w3.eth.send_raw_transaction(raw_tx).hex()
    record_pending_receipt({
        "opp_id": opp_id,
        "payload_hash": payload_hash,
        "tx_hash": tx_hash,
        "stage": "LIQUIDATION",
    })
    receipt = tx_w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
    status = "CONFIRMED" if int(receipt.status) == 1 else "REVERTED"
    realized = packet.expected_net_profit_usd if status == "CONFIRMED" else Decimal("0")
    record_execution_trace(
        stage="LIQUIDATION",
        status=status,
        mode="live",
        opp_id=opp_id,
        route=route,
        c1_tx_hash=tx_hash,
        receipt=_receipt_dict(receipt),
        envelope=envelope.as_dict(),
        payload_hash=payload_hash,
        metadata={"packet": packet.as_packet()},
    )
    record_pnl_event(
        mode="live",
        stage="LIQUIDATION",
        status=status,
        opp_id=opp_id,
        route=route,
        expected_net_usd=packet.expected_net_profit_usd,
        realized_net_usd=realized,
        tx_hash=tx_hash,
        block=int(receipt.blockNumber),
        metadata={"payload_hash": payload_hash},
    )
    return {"ok": status == "CONFIRMED", "status": status, "opp_id": opp_id, "tx_hash": tx_hash, "payload_hash": payload_hash}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apex-Omega liquidation watcher")
    parser.add_argument("--once", action="store_true", help="Run one scan/process cycle and exit.")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--max-packets", type=int, default=DEFAULT_MAX_PACKETS)
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL)
    parser.add_argument("--no-submit", action="store_true", help="Never sign/broadcast, even when live guards are armed.")
    args = parser.parse_args()

    print(
        "liquidation_watcher=START "
        f"mode={runtime_mode()} interval={args.interval}s max_packets={args.max_packets} no_submit={args.no_submit}",
        flush=True,
    )

    if not connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        raise RuntimeError("liquidation watcher RPC connection failed")

    stream_id = "0"
    cycles_processed = 0
    consecutive_failures = 0

    print("🎧 [LIQUIDATION CONSUMER] Listening for liquidation candidates...")

    while True:
        try:
            results = redis_cache.xread(
                {"omega:liquidations:candidates": stream_id},
                count=1,
                block=args.interval * 1000
            )
            if not results:
                continue

            cycles_processed += 1
            print(f"\n--- Processing Liquidation Cycle {cycles_processed} ---")

            stream_name, entries = results[0]
            entry_id, data = entries[0]
            stream_id = entry_id

            packets = _reconstruct_packets(data.get("packets", "[]"))
            pools = _reconstruct_pools(data.get("pools", "{}"))

            print(f"   [CONSUMER] Received {len(packets)} liquidation candidates for processing.")

            processed_results = []
            for packet in packets[:max(0, args.max_packets)]:
                processed_results.append(_process_packet(packet, pools, no_submit=args.no_submit))

            result = {
                "mode": runtime_mode(),
                "packets_received": len(packets),
                "processed": len(processed_results),
                "results": processed_results,
            }
            consecutive_failures = 0
            print("liquidation_watcher_cycle=" + json.dumps(_json_safe(result), sort_keys=True), flush=True)
        except Exception as exc:
            consecutive_failures += 1
            print(f"liquidation_watcher=ERROR failures={consecutive_failures} detail={type(exc).__name__}: {exc}", flush=True)
            if runtime_mode() == "live" and consecutive_failures >= 3:
                set_runtime_mode("dry_run", actor="liquidation_watcher_circuit_breaker")
                print("liquidation_watcher_circuit_breaker=DRY_RUN", flush=True)
        if args.once:
            break


if __name__ == "__main__":
    main()
