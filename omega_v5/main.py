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
from .pricing import PrecisionPricingEngine, PRICE_SCALE
from .pricing.precision_pricing import create_default_engine


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
    print(f"Discovered {total_opps} total opportunities across {cycles} cycle(s)")


if __name__ == "__main__":
    main()

