#!/usr/bin/env python3
# ==============================================================================
# walk_pipeline.py -- A simplified script to walk the Omega V5 pipeline.
#
# This script runs the core discovery, ranking, and truth-gating process,
# prints a step-by-step summary, and saves a detailed JSON report to the
# `out/` directory. It is intended as a high-level diagnostic and validation tool.
# ==============================================================================

import argparse
import os
from decimal import Decimal
import time
import json

# Add project root to path to allow direct script execution
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from omega_v5 import (
    rpc_layer,
    ArbitrageGraphEngine,
    get_config_value,
    final_truth_rank, truth_summary,
    base_fee_gwei as _base_fee_gwei,
    score_cross_pool_spreads,
    score_opportunities,
    score_pegged_stable_spreads,
    print_live_opportunities,
    compute_all_pool_rates, detect_cross_pool_two_leg_spreads,
    DEEP_POOL_REGISTRY,
    detect_pegged_stable_spreads,
)


def walk_system_pipeline(principal_usd: Decimal, max_to_test: int) -> dict:
    """Runs a single pass of the discovery and validation pipeline."""

    report = {
        "timestamp": int(time.time()),
        "params": {"principal_usd": str(principal_usd), "max_to_test": max_to_test},
        "context": {
            "python_version": sys.version,
            "script_path": __file__,
        },
        "steps": {},
        "results": {},
        "error": None,
    }
    start_time = time.monotonic()

    try:
        print("--- [Step 1: Connect and Load State] ---")
        step_start = time.monotonic()
        rpc_url = get_config_value("PRIMARY_READ_RPC_URL")
        if not rpc_layer.connect(http_urls=[rpc_url], prefer_wss=False):
            raise ConnectionError("Could not connect to RPC.")

        print(f"✅ Connected to RPC. Current block: {rpc_layer.BLOCK}")
        live_pools = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
        print(f"✅ Loaded {len(live_pools)} live pools from the registry.")
        rpc_layer.refresh_token_prices(force=True)
        print("✅ Refreshed token prices from oracle.")
        report["steps"]["load_state"] = {
            "duration_seconds": time.monotonic() - step_start,
            "block_number": rpc_layer.BLOCK,
            "pools_loaded": len(live_pools),
        }

        print("\n--- [Discovery Summary] ---")
        base_assets_str = get_config_value("FLASH_BASE_ASSETS", "USDC,USDC.e,WPOL,WETH")
        base_assets = set(base_assets_str.split(','))

        all_pool_tokens = set()
        for pool in live_pools:
            all_pool_tokens.update(pool['tokens'])

        mid_tokens = all_pool_tokens - base_assets

        print(f"  - Pools discovered: {len(live_pools)}")
        print(f"  - Base assets configured: {len(base_assets)} ({', '.join(sorted(list(base_assets)))})")
        print(f"  - Mid-tier assets found: {len(mid_tokens)}")

        print("\n--- Asset Prices (USD) ---")
        # Sort prices by token symbol for consistent output
        sorted_prices = sorted(rpc_layer.TOKEN_PRICES.items())
        for token, price in sorted_prices:
            if price > 0:
                print(f"  - {token:<10}: ${price:,.4f}")
        report["steps"]["discovery_summary"] = {
            "pools": len(live_pools), "base_assets": len(base_assets), "mid_tier_assets": len(mid_tokens),
            "prices": {k: str(v) for k, v in rpc_layer.TOKEN_PRICES.items()}
        }

        print("\n--- [Step 2: Theoretical Opportunity Discovery] ---")
        step_start = time.monotonic()
        rates = compute_all_pool_rates(live_pools)
        print(f"✅ Computed {sum(len(v) for v in rates.values())} directional quotes across {len(rates)} pairs.")

        two_leg_spreads = detect_cross_pool_two_leg_spreads(rates)
        stable_spreads = detect_pegged_stable_spreads(two_leg_spreads)
        engine = ArbitrageGraphEngine(rates)
        cycles = engine.bellman_ford_all_sources()
        print(f"✅ Discovered {len(two_leg_spreads)} 2-hop spreads (including {len(stable_spreads)} stable pairs).")
        print(f"✅ Discovered {len(cycles)} 3+ hop cycles via graph search.")
        report["steps"]["discovery"] = {
            "duration_seconds": time.monotonic() - step_start,
            "two_hop_spreads": len(two_leg_spreads),
            "stable_spreads": len(stable_spreads),
            "multi_hop_cycles": len(cycles),
        }

        print("\n--- [Step 3: Economic Ranking] ---")
        step_start = time.monotonic()
        ranked_opps = sorted(
            score_pegged_stable_spreads(stable_spreads, live_pools, principal_usd)
            + score_cross_pool_spreads(two_leg_spreads, live_pools, principal_usd)
            + score_opportunities(cycles, live_pools, rates, principal_usd),
            key=lambda item: item.profitability.net_profit_usd,
            reverse=True,
        )
        print(f"✅ Scored and ranked {len(ranked_opps)} theoretical opportunities.")
        print("Top 50 theoretical opportunities (before on-chain verification):")
        print_live_opportunities(ranked_opps, max_count=50)
        report["steps"]["ranking"] = {
            "duration_seconds": time.monotonic() - step_start,
            "total_ranked": len(ranked_opps),
            "top_50_theoretical": [
                opp.as_dict() for opp in ranked_opps[:50]
            ],
        }

        print(f"\n--- [Step 4: Execution Truth Gate (Top {max_to_test} Candidates)] ---")
        step_start = time.monotonic()
        base_fee, source = _base_fee_gwei()
        print(f"✅ Fetched current gas price: {base_fee:.2f} Gwei (source: {source})")

        executable_opps, truth_results = final_truth_rank(
            ranked_opps,
            live_pools,
            base_fee_gwei=base_fee,
            max_candidates=max_to_test,
        )
        summary = truth_summary(truth_results)
        print(f"✅ Ran {summary['inspected']} candidates through the truth gate ({summary['exact_calls']} total eth_calls).")
        print(f"🔴 Rejections: {summary['rejection_classes']}")
        report["steps"]["truth_gate"] = {
            "duration_seconds": time.monotonic() - step_start,
            "base_fee_gwei": f"{base_fee:.2f}",
            "summary": summary,
        }

        print("\n--- [Step 5: Final Results] ---")
        if executable_opps:
            print(f"✅ SUCCESS: Found {len(executable_opps)} profitable and executable opportunities!")
            print_live_opportunities(executable_opps, max_count=10)
            report["results"] = {
                "found_executable": True,
                "count": len(executable_opps),
                "opportunities": [opp.as_dict() for opp in executable_opps],
            }
        else:
            print("🔴 No executable opportunities found in this cycle after on-chain verification.")
            print("   This is normal; profitable routes are rare and fleeting.")
            report["results"] = {
                "found_executable": False,
                "count": 0,
                "opportunities": [],
            }

    except Exception as e:
        error_message = f"{type(e).__name__}: {e}"
        print(f"\n🔴 PIPELINE FAILED: {error_message}")
        report["error"] = error_message

    finally:
        total_duration = time.monotonic() - start_time
        report["total_duration_seconds"] = total_duration
        print(f"\n--- Pipeline walk complete in {total_duration:.2f} seconds. ---")
        return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk the Omega V5 pipeline and print results.")
    parser.add_argument("--principal", type=float, default=50000, help="Flash loan principal in USD to simulate with.")
    parser.add_argument("--test-top", type=int, default=25, help="Number of top theoretical opportunities to run through the truth gate.")
    args = parser.parse_args()

    print(f"--- Starting Omega V5 Pipeline Walkthrough ---")
    print(f"Simulating with ${args.principal:,.2f} principal. Testing top {args.test_top} routes on-chain.\n")
    
    report_data = walk_system_pipeline(Decimal(str(args.principal)), args.test_top)

    # Save the report
    report_path = os.path.join("out", "pipeline_walk_latest.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)

    print(f"✅ Detailed report saved to: {report_path}")