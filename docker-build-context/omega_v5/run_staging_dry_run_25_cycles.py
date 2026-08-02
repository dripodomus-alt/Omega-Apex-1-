#!/usr/bin/env python3
"""
run_staging_dry_run_25_cycles.py

This script runs a 25-cycle dry run of the full Omega V5 pipeline, from
discovery through staging. It is designed to validate the end-to-end
profitability and staging logic without executing any transactions.

In each cycle, it will:
1. Load live pool and price data.
2. Discover all potential arbitrage routes (2, 3, and 4-hop).
3. Score and rank all routes based on estimated net profitability.
4. Stage the top 10 most profitable routes, preparing them for the
   final execution truth gate.
"""

import argparse
import os
import sys
from decimal import Decimal

# Add project root to path to allow direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from omega_v5 import rpc_layer
from omega_v5.ranker import compute_all_pool_rates
from omega_v5.route_execution_stager import build_stage_report


def run_single_cycle(principal_usd: Decimal, stage_top_n: int) -> dict:
    """
    Runs one full cycle of the discovery and staging pipeline.
    """
    print(f"\n--- Processing Cycle (Principal: ${principal_usd:,.2f}, Staging Top: {stage_top_n}) ---")

    # 1. Load live state from RPC and oracles
    live_pools = rpc_layer.load_all_live_pools(rpc_layer.DEEP_POOL_REGISTRY)
    rpc_layer.refresh_token_prices(force=True)
    print(f"  Loaded {len(live_pools)} live pools at block {rpc_layer.BLOCK}.")

    # 2. Compute all directional rates
    rates = compute_all_pool_rates(live_pools)
    print(f"  Computed {sum(len(v) for v in rates.values())} directional quotes across {len(rates)} pairs.")

    # 3. Build the stage report, which runs discovery and ranking
    report = build_stage_report(
        pools=live_pools,
        rates=rates,
        principal_usd=principal_usd,
        stage_limit=stage_top_n,
        hops=(2, 3, 4),
        max_pre_ranked=200,
    )

    staged_count = report.get("stage", {}).get("staged_for_executor_truth", 0)
    print(f"  ✅ Staged {staged_count} routes for executor truth gate.")

    return {"staged_count": staged_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a 25-cycle staging dry run.")
    parser.add_argument("--principal", type=float, default=50000, help="Flash loan principal in USD.")
    parser.add_argument("--stage-top", type=int, default=10, help="Number of top routes to stage per cycle.")
    args = parser.parse_args()

    print("======================================================")
    print("  Omega V5: 25-Cycle Staging Dry Run")
    print("======================================================")

    if not rpc_layer.connect():
        print("[FATAL] Could not connect to RPC. Aborting.")
        return 1

    for i in range(1, 26):
        print(f"\nRunning cycle {i}/25...")
        run_single_cycle(Decimal(str(args.principal)), args.stage_top)

    print("\n✅ 25-cycle dry run complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())