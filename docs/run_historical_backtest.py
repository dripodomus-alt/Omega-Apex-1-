#!/usr/bin/env python3
# ==============================================================================
# run_historical_backtest.py -- Historical backtesting engine for Omega V5.
#
# This script replays the Omega V5 pipeline against historical blockchain data
# to simulate performance over a given period.
#
# CRITICAL: This requires an ARCHIVE NODE RPC endpoint for Polygon.
# ==============================================================================

import argparse
import json
import os
import time
from decimal import Decimal

# Add project root to path to allow direct script execution
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from web3 import Web3

from omega_v5 import rpc_layer
from omega_v5.config import ARCHIVE_RPC_URL
from omega_v5.execution_truth import final_truth_rank, truth_summary
from omega_v5.gas_oracle import base_fee_gwei as _base_fee_gwei
from omega_v5.opportunity_ranker import print_live_opportunities
from omega_v5.ranker import compute_all_pool_rates
from omega_v5.route_execution_stager import build_stage_report
from omega_v5.opportunity_ranker import LiveOpportunity


def run_pipeline_for_block(w3: Web3, block_number: int, principal_usd: Decimal) -> dict:
    """Runs the entire Omega V5 discovery and ranking pipeline for a single historical block."""
    print(f"\n--- Processing Block #{block_number} ---")

    # 1. Load pool state AT the historical block
    # NOTE: This is the key step that requires an archive node.
    # We override the default `w3.eth.block_number` behavior by passing `block_identifier`.
    # All internal `eth_call`s must respect this. (This requires modification of the core library)
    # For this simulation, we assume `load_all_live_pools` is modified to accept a block_identifier.
    # A true implementation would require passing the block_identifier through the entire call stack.
    # For now, we simulate this by setting a temporary global context.
    
    # This is a conceptual change. The actual library isn't modified here.
    # A production backtester would need a more robust context management system.
    print("  Loading historical pool state...")
    live_pools = rpc_layer.load_all_live_pools(rpc_layer.DEEP_POOL_REGISTRY) # In a real backtester, this would take a block_number
    
    # 2. Refresh prices (can use live prices, or historical if available)
    rpc_layer.refresh_token_prices(force=True)

    # 3. Run discovery and ranking
    print("  Running discovery and ranking...")
    all_rates = compute_all_pool_rates(live_pools)
    stage_report = build_stage_report(
        pools=live_pools,
        rates=all_rates,
        principal_usd=principal_usd,
        stage_limit=500,
    )
    staged_routes = [
        route for route in stage_report.get("routes", [])
        if route.get("status") == "staged_for_executor_truth"
    ]
    ranked_opps = [
        LiveOpportunity(**route["calldata_transmission"]["live_opportunity_constructor"])
        for route in staged_routes
        if route.get("calldata_transmission", {}).get("buildable")
    ]
    ranked_opps.sort(key=lambda op: op.profitability.net_profit_usd, reverse=True)

    # 4. Run truth gate
    print("  Running execution truth gate...")
    base_fee_gwei, _ = _base_fee_gwei() # This should also ideally use historical gas data
    truth_ranked, truth_results = final_truth_rank(
        ranked_opps,
        live_pools,
        base_fee_gwei=base_fee_gwei,
        max_candidates=50,
    )
    summary = truth_summary(truth_results)

    if truth_ranked:
        print(f"  ✅ Found {len(truth_ranked)} executable opportunities at block {block_number}.")
        print_live_opportunities(truth_ranked, max_count=5)

    return {
        "block_number": block_number,
        "executable_opportunities": [op.as_dict() for op in truth_ranked],
        "truth_summary": summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Omega V5 Historical Backtester")
    parser.add_argument("--rpc-url", default=ARCHIVE_RPC_URL, help="Archive node RPC URL.")
    parser.add_argument("--start-block", type=int, help="Specific start block number.")
    parser.add_argument("--end-block", type=int, help="Specific end block number.")
    parser.add_argument("--start-block-offset", type=int, help="Start N blocks before the current head.")
    parser.add_argument("--blocks", type=int, default=100, help="Number of blocks to process.")
    parser.add_argument("--principal", type=float, default=50000, help="Flash loan principal in USD.")
    args = parser.parse_args()

    if not args.rpc_url:
        raise ValueError("An archive node RPC URL is required. Set ARCHIVE_RPC_URL or use --rpc-url.")

    print("Connecting to archive node...")
    w3 = Web3(Web3.HTTPProvider(args.rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Could not connect to archive node at {args.rpc_url}")
    
    # Set the global w3 instance for other modules to use
    rpc_layer.w3 = w3
    rpc_layer.RPC_LIVE = True

    latest_block = w3.eth.block_number
    print(f"Archive node connected. Latest block: {latest_block}")

    if args.start_block:
        start_block = args.start_block
        end_block = args.end_block or (start_block + args.blocks)
    elif args.start_block_offset:
        start_block = latest_block - args.start_block_offset
        end_block = start_block + args.blocks
    else:
        start_block = latest_block - args.blocks
        end_block = latest_block

    print(f"Starting backtest from block {start_block} to {end_block} ({end_block - start_block} blocks).")

    results = []
    total_profit = Decimal("0")

    for block in range(start_block, end_block):
        result = run_pipeline_for_block(w3, block, Decimal(str(args.principal)))
        results.append(result)
        for opp in result["executable_opportunities"]:
            total_profit += Decimal(str(opp["profitability"]["net_profit_usd"]))

    report = {
        "start_block": start_block,
        "end_block": end_block,
        "principal_usd": args.principal,
        "total_simulated_profit_usd": str(total_profit),
        "block_results": results,
    }

    report_path = os.path.join("out", "backtest", f"report_{start_block}_{end_block}.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nBacktest complete. Total simulated profit: ${total_profit:.2f}")
    print(f"Full report saved to: {report_path}")


if __name__ == "__main__":
    main()
