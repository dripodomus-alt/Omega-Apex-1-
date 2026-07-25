#!/usr/bin/env python3
# ==============================================================================
# pipeline_validation.py -- Main entry point for a full discovery-to-truth cycle.
#
# This script orchestrates the new, high-performance pipeline:
# 1. Loads live market data (pools, prices).
# 2. Makes a single, unified call to the Rust engine for discovery, sizing, and ranking.
# 3. Takes the top-ranked opportunities and runs them through the final `eth_call` truth gate.
# 4. Constructs executable transaction payloads for opportunities that pass all gates.
# 5. Writes a final report for consumption by benchmark scripts.
# ==============================================================================

import argparse
import json
import os
import sys
import time
from decimal import Decimal

from . import rpc_layer
from .arbitrage import ArbitrageGraphEngine
from .config import (
    CHAIN_ID,
    HTTP_URL,
    FORK_SIM_RPC_URL,
    MAX_FLASH_PRINCIPAL_USD,
    MAX_ROUTE_IMPACT,
    FLASH_ROUTE_TVL_FRACTIONS,
    PREFERRED_FLASH_SOURCE,
)
from .execution import build_tx_payload
from .execution_truth import final_truth_rank, truth_summary
from .flash_loan import FlashSource
from .gas_oracle import eip1559_fee_params
from .oracle_layer import refresh_token_prices
from .paths import output_path

LATEST_REPORT = output_path("pipeline_validation_latest.json")


def run_pipeline(*, use_fork: bool = False, no_eth_call: bool = False, max_opps: int = 50) -> dict:
    """Runs the full discovery-to-truth pipeline."""
    started = time.time()
    os.environ.setdefault("OMEGA_RUNTIME_MODE", "dry_run")
    os.environ.setdefault("EXECUTION_MODE", "dry_run" if no_eth_call else "shadow")
    os.environ.setdefault("LIVE_TRADING", "0")

    rpc_url = FORK_SIM_RPC_URL if use_fork else HTTP_URL
    if not rpc_layer.connect(http_urls=[rpc_url], wss_url="", prefer_wss=False):
        raise RuntimeError(f"RPC connection failed to {rpc_url}")

    # --- Phase 1: Data Loading ---
    print("1. Loading live pool states and prices...")
    pools = rpc_layer.load_all_live_pools()
    prices = refresh_token_prices(force=True)
    print(f"   -> Loaded {len(pools)} pools and {len(prices)} prices.")

    # --- Phase 2: Rust-Powered Discovery, Sizing, and Ranking ---
    print("2. Running unified discovery & ranking pipeline (Rust engine)...")
    arb_engine = ArbitrageGraphEngine(pools, prices)
    sizing_params = {
        "min_principal_usd": "5000", # Use a reasonable minimum for discovery
        "max_principal_usd": str(MAX_FLASH_PRINCIPAL_USD),
        "tvl_fractions": [str(f) for f in FLASH_ROUTE_TVL_FRACTIONS],
        "max_impact_bps": int(MAX_ROUTE_IMPACT * 10000),
    }
    flash_source = FlashSource[PREFERRED_FLASH_SOURCE]

    ranked_opps, discovery_report = arb_engine.find_and_rank_opportunities(
        sizing_params=sizing_params,
        flash_source=flash_source,
        stager_max_token_paths=0,  # Unbounded for max discovery
        stager_max_pre_ranked=1000,
        max_quote_options_per_pair=0,
    )
    print(f"   -> Rust engine returned {len(ranked_opps)} ranked opportunities.")
    if not ranked_opps:
        print("   -> No profitable routes found by the core engine.")

    # --- Phase 3: Final On-Chain Truth Gate ---
    if no_eth_call:
        print("3. Skipping final `eth_call` truth gate as requested.")
        executable_opps = ranked_opps[:max_opps]
        truth_results = []
    else:
        print(f"3. Proving execution truth for top {max_opps} candidates...")
        try:
            base_fee, _, _ = eip1559_fee_params()
        except Exception:
            base_fee = Decimal("50") # Fallback
        
        executable_opps, truth_results = final_truth_rank(
            opportunities=ranked_opps,
            pools=pools,
            base_fee_gwei=base_fee,
            max_candidates=max_opps,
        )
        print(f"   -> Found {len(executable_opps)} fully executable opportunities.")

    # --- Phase 4: Build Transaction Payloads ---
    print("4. Generating performance metrics and building payloads...")
    final_payloads = []
    performance_metrics = {
        "python_quote_calls": len(truth_results),
        "total_candidates": len(ranked_opps),
    }
    print(f"   -> Performance: {performance_metrics['total_candidates']} total candidates, {performance_metrics['python_quote_calls']} truth-gated.")

    for opp in executable_opps:
        try:
            # Nonce is a placeholder; the benchmark script will manage it.
            tx_payload = build_tx_payload(opp, pools, nonce=0, base_fee_gwei=base_fee) # type: ignore
            final_payloads.append({
                "estimated_profit_usd": float(opp.profitability.net_profit_usd),
                "path": list(opp.path),
                "pool_sequence": list(opp.pool_sequence),
                "principal_usd": float(opp.profitability.flashloan.principal_usd),
                "transaction": tx_payload,
            })
        except Exception as e:
            print(f"   -> Failed to build payload for opp {opp.path}: {e}")
            continue
    
    # --- Phase 5: Generate Final Report ---
    print("5. Generating final report...")
    report = {
        "ok": True,
        "chain_id": CHAIN_ID,
        "block": rpc_layer.BLOCK,
        "timestamp": int(time.time()),
        "elapsed_seconds": round(time.time() - started, 2),
        "discovery_report": discovery_report,
        "performance_metrics": performance_metrics,
        "executor_truth": truth_summary(truth_results),
        "payload_execution_eligible": bool(final_payloads),
        "opportunities": final_payloads,
    }

    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"   -> Report written to {LATEST_REPORT}")
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Run the full Omega V5 discovery-to-truth pipeline.")
    parser.add_argument("--use-fork", action="store_true", help="Use the Anvil fork RPC for all operations.")
    parser.add_argument("--no-eth-call", action="store_true", help="Skip the final eth_call truth-gating step.")
    parser.add_argument("--max-opps", type=int, default=50, help="Maximum opportunities to pass to the truth gate.")
    args = parser.parse_args()

    try:
        run_pipeline(use_fork=args.use_fork, no_eth_call=args.no_eth_call, max_opps=args.max_opps)
    except Exception as e:
        print(f"\n[FATAL] Pipeline failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # Write a failure report
        report = {
            "ok": False,
            "error": str(e),
            "timestamp": int(time.time()),
        }
        LATEST_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        sys.exit(1)


if __name__ == "__main__":
    main()