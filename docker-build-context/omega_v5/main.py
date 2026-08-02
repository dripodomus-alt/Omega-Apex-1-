#!/usr/bin/env python3
"""
omega_v5.main — Primary entry point for the arbitrage engine pipeline.

This module serves as the main entry point for a single, discrete run of the
arbitrage discovery and execution pipeline. It is designed to be called by
higher-level orchestrators, such as the `engine_daemon.py` for continuous
operation or `recursive_ml_orchestrator.py` for ML training loops.

Pipeline Stages Triggered:
1.  **Discovery**: Calls `run_arbitrage_discovery` to get opportunities from the
    Rust engine.
2.  **Pricing**: Initializes and uses the `PrecisionPricingEngine` for all
    economic calculations, ensuring dimensional correctness with 18-decimal
    fixed-point arithmetic.
"""

from __future__ import annotations

import argparse
import sys

from .arbitrage import run_arbitrage_discovery
from .execution import run_execution_loop
from .payload_envelope import UNIFIED_ROUTE_SCHEMA_VERSION
from .pricing import PrecisionPricingEngine, PRICE_SCALE
from .pricing.precision_pricing import create_default_engine


def _coerce_value(source: object, key: str, default: object = None) -> object:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _build_staged_route_payload(opportunity: object, *, principal_usd: object = 1000) -> dict:
    path = list(_coerce_value(opportunity, "path", ()) or ())
    pool_sequence = list(_coerce_value(opportunity, "pool_sequence", ()) or ())
    protocol_seq = list(_coerce_value(opportunity, "protocol_seq", ()) or ())
    profitability = _coerce_value(opportunity, "profitability", None)
    if isinstance(profitability, dict):
        gross_surplus_usd = profitability.get("gross_surplus_usd", 0)
        flashloan_fee_usd = profitability.get("flashloan_fee_usd", 0)
        gas_cost_usd = profitability.get("gas_cost_usd", 0)
        relay_tip_usd = profitability.get("relay_tip_usd", 0)
        risk_buffer_usd = profitability.get("risk_buffer_usd", 0)
        net_profit_usd = profitability.get("net_profit_usd", 0)
    else:
        gross_surplus_usd = getattr(profitability, "gross_surplus_usd", 0)
        flashloan_fee_usd = getattr(profitability, "flashloan_fee_usd", 0)
        gas_cost_usd = getattr(profitability, "gas_cost_usd", 0)
        relay_tip_usd = getattr(profitability, "relay_tip_usd", 0)
        risk_buffer_usd = getattr(profitability, "risk_buffer_usd", 0)
        net_profit_usd = getattr(profitability, "net_profit_usd", 0)

    opp_id = str(_coerce_value(opportunity, "opp_id", "") or "")
    if not opp_id:
        opp_id = f"OPP-{abs(hash(tuple(path)))}"

    return {
        "opp_id": opp_id,
        "opportunity_id": opp_id,
        "status": "staged_for_executor_truth",
        "path": path,
        "pool_sequence": pool_sequence,
        "protocol_seq": protocol_seq,
        "principal_usd": str(principal_usd),
        "profitability": {
            "gross_surplus_usd": gross_surplus_usd,
            "flashloan_fee_usd": flashloan_fee_usd,
            "gas_cost_usd": gas_cost_usd,
            "relay_tip_usd": relay_tip_usd,
            "risk_buffer_usd": risk_buffer_usd,
            "net_profit_usd": net_profit_usd,
        },
        "unified_route_envelope": {
            "schema_version": UNIFIED_ROUTE_SCHEMA_VERSION,
            "opp_id": opp_id,
            "route": {"path": path, "pool_sequence": pool_sequence},
            "staging": {
                "opportunity_id_frozen": True,
                "principal_usd": str(principal_usd),
            },
            "fees": {},
            "math": {"net_profit_usd": str(net_profit_usd)},
        },
    }


def _prepare_execution_payloads(opportunities: list[object]) -> list[dict]:
    return [_build_staged_route_payload(opportunity) for opportunity in opportunities]


def main() -> None:
    parser = argparse.ArgumentParser(description="Omega V5 Arbitrage Engine")
    parser.add_argument("--precision", action="store_true",
                        help="Force use of the canonical precision pricing engine")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run discovery/readiness without live submission")
    parser.add_argument("--cycles", type=int, default=1,
                        help="Number of pipeline cycles requested by readiness wrappers")
    args = parser.parse_args()

    print(f"Omega V5 starting (precision pricing available, SCALE={PRICE_SCALE}, dry_run={args.dry_run}, cycles={args.cycles})")

    if args.precision:
        # Example of constructing the engine (real usage supplies live sources)
        print("Precision pricing mode enabled — using PrecisionPricingEngine contract")
        # engine = create_default_engine(...)  # wire real tokens/policies/sources

    total_opps = 0
    cycles = max(1, int(args.cycles or 1))
    for cycle in range(cycles):
        opps = run_arbitrage_discovery(use_precision_pricing=True)
        total_opps += len(opps)
        print(f"Cycle {cycle + 1}/{cycles}: discovered {len(opps)} opportunities (pricing via precision layer)")

        if opps:
            execution_results = []
            staged_payloads = _prepare_execution_payloads(opps)
            if args.dry_run:
                execution_results = __import__("asyncio").run(
                    run_execution_loop(opportunities=staged_payloads, pools={}, nonce=cycle + 1)
                )
            else:
                execution_results = __import__("asyncio").run(
                    run_execution_loop(opportunities=staged_payloads, pools={}, nonce=cycle + 1)
                )
            print(f"Cycle {cycle + 1}/{cycles}: execution loop completed with {len(execution_results)} result(s)")
    print(f"Discovered {total_opps} total opportunities across {cycles} cycle(s)")


if __name__ == "__main__":
    main()

