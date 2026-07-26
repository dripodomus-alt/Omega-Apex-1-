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
    final_truth_rank, truth_summary,
    base_fee_gwei as _base_fee_gwei,
    print_live_opportunities,
    DEEP_POOL_REGISTRY,
    FlashSource,
    get_config_value,
    MIN_FLASH_PRINCIPAL_USD, MAX_FLASH_PRINCIPAL_USD, FLASH_ROUTE_TVL_FRACTIONS, MAX_ROUTE_IMPACT,
)


def walk_system_pipeline(principal_usd: Decimal, max_to_test: int, profile: str) -> dict:
    """Runs a single pass of the discovery and validation pipeline."""

    report = {
        "timestamp": int(time.time()),
        "params": {"principal_usd": str(principal_usd), "max_to_test": max_to_test},
        "context": {
            "python_version": sys.version,
            "script_name": "walk_pipeline.py",
            "script_path": __file__,
        },
        "steps": {},
        "results": {},
        "error": None,
    }
    start_time = time.monotonic()

    try:
        print("--- [Step 1: Connect and Load State] ---")
        step_1_start = time.monotonic()
        rpc_url = get_config_value("PRIMARY_READ_RPC_URL")
        if not rpc_layer.connect(http_urls=[rpc_url], prefer_wss=False):
            raise ConnectionError("Could not connect to RPC.")

        print(f"✅ Connected to RPC. Current block: {rpc_layer.BLOCK}")
        live_pools = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
        print(f"✅ Loaded {len(live_pools)} live pools from the registry.") # This can be a bottleneck if registry is huge
        rpc_layer.refresh_token_prices(force=True)
        print("✅ Refreshed token prices from oracle.")
        report["steps"]["load_state"] = {
            "duration_seconds": time.monotonic() - step_start,
            "block_number": rpc_layer.BLOCK,
            "pools_loaded": len(live_pools),
        }

        print("\n--- [Discovery Summary] ---")
        prices = rpc_layer.TOKEN_PRICES
        print(f"  - Pools discovered: {len(live_pools)}")
        print(f"  - Prices loaded for {len(prices)} tokens.")

        print("\n--- Asset Prices (USD) ---")
        # Sort prices by token symbol for consistent output
        sorted_prices = sorted(prices.items())
        for token, price in sorted_prices:
            if price > 0:
                print(f"  - {token:<10}: ${price:,.4f}")
        report["steps"]["discovery_summary"] = {
            "pools": len(live_pools),
            "prices": {k: str(v) for k, v in prices.items()}
        }

        print("\n--- [Step 2: Unified Discovery & Ranking via Rust Engine] ---")
        step_2_start = time.monotonic()

        # Define discovery profiles
        profiles = {
            "fast": {
                "stager_max_token_paths": 500,
                "stager_max_pre_ranked": 100,
                "stager_max_quote_options_per_pair": 2,            "canary": {
                "stager_max_token_paths": 100,
                "stager_max_pre_ranked": 20,
                "stager_max_quote_options_per_pair": 1,
            },
            "canary": {
                "stager_max_token_paths": 100,
                "stager_max_pre_ranked": 20,
                "stager_max_quote_options_per_pair": 1,
            },
            "deep": {
                "stager_max_token_paths": 0, # Unbounded
                "stager_max_pre_ranked": 0, # Unbounded
                "stager_max_quote_options_per_pair": 0, # Unbounded
            },
        }
        discovery_params = profiles.get(profile, profiles["fast"])
        print(f"✅ Using discovery profile: '{profile}'")

        arb_engine = ArbitrageGraphEngine(live_pools, prices)
        sizing_params = {
            "min_principal_usd": str(MIN_FLASH_PRINCIPAL_USD),
            "max_principal_usd": str(MAX_FLASH_PRINCIPAL_USD),
            "tvl_fractions": [str(f) for f in FLASH_ROUTE_TVL_FRACTIONS],
            "max_impact_bps": int(MAX_ROUTE_IMPACT * 10000),
        }
        ranked_opps, discovery_report = arb_engine.find_and_rank_opportunities(
            sizing_params=sizing_params,
            flash_source=FlashSource.BALANCER,
            **discovery_params,
        )
        print(f"✅ Rust engine returned {len(ranked_opps)} ranked opportunities.")
        print(f"✅ Discovery report: {discovery_report}")

        report["steps"]["discovery"] = {
            "duration_seconds": time.monotonic() - step_2_start,
            "ranked_count": len(ranked_opps),
            "discovery_report": discovery_report,
        }

        print("\n--- [Step 3: Economic Ranking] ---")
        # This step is now part of the unified Rust engine call. We just display the results.
        print(f"✅ Displaying {len(ranked_opps)} opportunities scored by the Rust engine.")
        print("Top 50 theoretical opportunities (before on-chain verification):")
        print_live_opportunities(ranked_opps, max_count=20) # Reduced for brevity
        report["steps"]["ranking"] = {
            "duration_seconds": time.monotonic() - step_start,
            "total_ranked": len(ranked_opps),
            "top_50_theoretical": [
                opp.as_dict() for opp in ranked_opps[:50]
            ],
        }

        print(f"\n--- [Step 4: Execution Truth Gate (Top {max_to_test} Candidates)] ---")
        step_4_start = time.monotonic()
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
            "duration_seconds": time.monotonic() - step_4_start,
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

        # Performance Analysis
        perf_analysis = {}
        for step_name, step_data in report["steps"].items():
            duration = step_data.get("duration_seconds", 0)
            if total_duration > 0:
                perf_analysis[step_name] = {
                    "duration_seconds": duration,
                    "percentage_of_total": (duration / total_duration) * 100
                }
        
        if perf_analysis:
            bottleneck = max(perf_analysis, key=lambda k: perf_analysis[k]["duration_seconds"])
            report["performance_analysis"] = {
                "total_cycle_time_seconds": total_duration,
                "bottleneck_stage": bottleneck,
                "stage_breakdown": perf_analysis
            }
        print(f"\n--- Pipeline walk complete in {total_duration:.2f} seconds. ---")
        return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk the Omega V5 pipeline and print results.")
    parser.add_argument("--principal", type=float, default=50000, help="Flash loan principal in USD to simulate with.")
    parser.add_argument("--profile", choices=["fast", "canary", "deep"], default="fast", help="Discovery profile for speed vs. coverage.")
    parser.add_argument("--test-top", type=int, default=25, help="Number of top theoretical opportunities to run through the truth gate.")
    args = parser.parse_args()

    print(f"--- Starting Omega V5 Pipeline Walkthrough ---")
    print(f"Simulating with ${args.principal:,.2f} principal. Profile: '{args.profile}'. Testing top {args.test_top} routes on-chain.\n")
    
    report_data = walk_system_pipeline(Decimal(str(args.principal)), args.test_top, args.profile)

    # Save the report
    report_path = os.path.join("out", "pipeline_walk_latest.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)

    print(f"✅ Detailed report saved to: {report_path}")