#!/usr/bin/env python3
# ==============================================================================
# executor.py -- The Autonomous Execution Engine for Omega V5
#
# UPDATED: Integrates the full production pipeline for discovery, staging,
# and concurrent simulation to achieve high-frequency execution cycles.
# This is the canonical entrypoint for 24/7, autonomous, live-money operation.
# It orchestrates the entire arbitrage pipeline in a continuous loop:
# 1. Fetches live market data (gas prices, token prices).
# 2. Discovers and ranks a wide surface of opportunities.
# 3. Re-ranks opportunities intelligently using the ML Alpha model.
# 4. Verifies the top candidates with the concurrent `eth_call` truth gate.
# 5. Prepares and broadcasts transactions for verified, profitable opportunities.
# 6. Logs all data for the next ML training cycle.
# ==============================================================================

import time
import argparse
import asyncio
from decimal import Decimal

from . import rpc_layer, execution
from .rpc_layer import DEEP_POOL_REGISTRY
from .ranker import compute_all_pool_rates
from .route_execution_stager import build_stage_report
from .pricing.gas_oracle import get_live_gas_price_gwei, get_live_native_price_usd
from .execution_truth import batch_simulate_with_truth


def run_cycle(principal_usd: Decimal, max_slippage_bps: Decimal, live_gas_gwei: float, live_native_usd: float):
    """
    Executes a single, complete cycle of the autonomous engine.
    """
    print("\n" + "="*40)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting new execution cycle...")
    print("="*40)

    # 2. Discover and Rank Opportunities
    print("[2/5] Discovering and ranking opportunities...")
    pools = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
    rates = compute_all_pool_rates(pools)
    # The stager discovers, ranks by gross profit, and then re-ranks with ML Alpha.
    # We increase max_pre_ranked to 500 to match the desired "top 50" processing goal.
    report = build_stage_report(
        pools=pools,
        rates=rates,
        principal_usd=principal_usd,
        stage_limit=50, # Stage the top 50 for the truth gate
        hops=(2, 3, 4),
        max_pre_ranked=500,
    )
    staged_routes = [
        route for route in report.get("routes", [])
        if route.get("status") == "staged_for_executor_truth"
    ]
    print(f"      -> Discovered and staged {len(staged_routes)} candidates.")

    # 3. Pre-flight Simulation (Truth Gate)
    print("[3/5] Running concurrent pre-flight simulation (Truth Gate)...")
    simulation_results = batch_simulate_with_truth(staged_routes, pools)
    executable_opportunities = [opp for opp, passed in simulation_results if passed]
    print(f"      -> {len(executable_opportunities)} / {len(staged_routes)} opportunities passed truth gate.")

    # 4. & 5. Broadcast Transactions & Log
    print(f"[4/5] Preparing to broadcast {len(executable_opportunities)} verified opportunities...")
    # The run_execution_loop handles the final `simulate_and_maybe_broadcast` step
    # which includes the final guards and MEV-aware submission.
    # We assume a nonce is fetched once per cycle.
    nonce = 0 # In a real run: w3.eth.get_transaction_count(wallet_address)
    execution_results = asyncio.run(execution.run_execution_loop(executable_opportunities, pools, nonce))
    print(f"[5/5] Execution loop complete. {len(execution_results)} results.")

    print("="*40)
    print("Cycle complete.")
    print("="*40)


def main():
    parser = argparse.ArgumentParser(description="Omega V5 Autonomous Executor")
    parser.add_argument("--principal", default="50000", help="Principal USD for sizing.")
    parser.add_argument("--slippage", default="15", help="Max slippage in BPS.")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous loop.")
    args = parser.parse_args()

    principal = Decimal(args.principal)
    slippage = Decimal(args.slippage)

    while True:
        # 1. Fetch Live Market Data (now done in the main loop)
        print("\n[1/6] Fetching live market data...")
        live_gas_gwei = get_live_gas_price_gwei()
        live_native_usd = get_live_native_price_usd()
        if not live_gas_gwei or not live_native_usd:
            print("[ERROR] Failed to fetch live market data. Skipping cycle.")
            time.sleep(15)
            continue
        run_cycle(principal, slippage, live_gas_gwei, live_native_usd) # This is now a synchronous call
        if not args.loop:
            break
        print("\nWaiting 12 seconds before next cycle...")
        time.sleep(12)

if __name__ == "__main__":
    main()
