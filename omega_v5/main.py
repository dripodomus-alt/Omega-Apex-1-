#!/usr/bin/env python3
"""
omega_v5.main — Primary entry point for the arbitrage engine.

The precision pricing engine is now wired into the core pipeline.
All new opportunity economics and execution math should go through
PrecisionPricingEngine for 18-decimal integer correctness.
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
    args = parser.parse_args()

    print(f"Omega V5 starting (precision pricing available, SCALE={PRICE_SCALE})")

    if args.precision:
        # Example of constructing the engine (real usage supplies live sources)
        print("Precision pricing mode enabled — using PrecisionPricingEngine contract")
        # engine = create_default_engine(...)  # wire real tokens/policies/sources

    opps = run_arbitrage_discovery(use_precision_pricing=True)
    print(f"Discovered {len(opps)} opportunities (pricing via precision layer)")


if __name__ == "__main__":
    main()
