#!/usr/bin/env python3
"""
simulate_capital_injector.py — Jupyter/Colab-style edge-case validation.

Exercises:
  1) Isolated registries
  2) Self-cannibalization hard stop
  3) Exact derivative OptimalSize formula
  4) Friction thresholding
  5) Clean-route sizing via official injector

Run:
  python scripts/ops/simulate_capital_injector.py
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from omega_v5.capital_injector import (
    CAPITAL_SOURCE_REGISTRY,
    EXECUTION_VENUE_REGISTRY,
    check_self_cannibalization,
    compute_derivative_optimal_size,
    compute_optimal_injection,
    register_execution_venue,
)
from omega_v5.flash_loan import FlashSource


def banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    banner("1. Isolated Registries")
    print("CAPITAL_SOURCE_REGISTRY keys:", list(CAPITAL_SOURCE_REGISTRY.keys()))
    register_execution_venue("SIM_UNI_V3_USDC_WETH", {"protocol": "UniswapV3", "type": "execution_venue"})
    print("EXECUTION_VENUE_REGISTRY sample:", list(EXECUTION_VENUE_REGISTRY.keys())[:5])
    overlap = set(CAPITAL_SOURCE_REGISTRY) & set(EXECUTION_VENUE_REGISTRY)
    print("Static key overlap:", overlap or "(none)")

    banner("2. Hard Overlap Guard")
    funding_id = str(CAPITAL_SOURCE_REGISTRY["BALANCER"]["pool_id"])
    is_c, msg = check_self_cannibalization("BALANCER", [funding_id, "SIM_TRADE_POOL"])
    print(msg if is_c else "unexpected clean")
    print("blocked =", is_c)

    is_clean, _ = check_self_cannibalization("BALANCER", ["SIM_POOL_A", "SIM_POOL_B"])
    print("clean route blocked =", is_clean)

    banner("3. Exact Derivative Formula")
    # Interactive-style knobs (edit these like sliders)
    rin = Decimal("100000")   # L2 Rin
    rout = Decimal("101500")  # L2 Rout (mild edge)
    f_swap = Decimal("0.003")  # L1 swap fee
    f_flash = Decimal("0")     # L1 flash fee (Balancer)

    optimal = compute_derivative_optimal_size(rin, rout, f_swap, f_flash)
    print(f"Rin={rin} Rout={rout} f_swap={f_swap} f_flash={f_flash}")
    print(f"OptimalSize = {optimal}")

    # Friction fail case
    bad = compute_derivative_optimal_size(
        Decimal("100000"), Decimal("100000"), Decimal("0.003"), Decimal("0.0005")
    )
    print(f"Equal-reserve friction case OptimalSize = {bad} (expect 0)")

    banner("4. End-to-end injector (cannibal)")
    pools_bad = {
        funding_id: {"total_executable_liquidity_usd": "900000", "fee_bps": 3000},
        "SIM_POOL_B": {"total_executable_liquidity_usd": "700000", "fee_bps": 3000},
    }
    r_bad = compute_optimal_injection(
        pool_sequence=[funding_id, "SIM_POOL_B"],
        pools=pools_bad,
        flash_source=FlashSource.BALANCER,
    )
    print("method:", r_bad.method)
    print("size:", r_bad.optimal_injection_usd)
    print("cannibal:", r_bad.cannibalization_detected)

    banner("5. End-to-end injector (clean)")
    pools_ok = {
        "SIM_POOL_A": {
            "total_executable_liquidity_usd": "500000",
            "fee_bps": 3000,
            "tokens": ["USDC", "WETH"],
            "reserves": ["250000", "120"],
        },
        "SIM_POOL_B": {
            "total_executable_liquidity_usd": "450000",
            "fee_bps": 3000,
            "tokens": ["WETH", "USDC"],
            "reserves": ["100", "220000"],
        },
    }
    r_ok = compute_optimal_injection(
        pool_sequence=["SIM_POOL_A", "SIM_POOL_B"],
        pools=pools_ok,
        path=["USDC", "WETH", "USDC"],
        flash_source=FlashSource.BALANCER,
    )
    print("method:", r_ok.method)
    print("size:", r_ok.optimal_injection_usd)
    print("reason:", r_ok.reason)
    print("params:", r_ok.as_sizing_params())

    banner("DONE")
    print("Simulation complete. Safe for notebook/Colab edge-case checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
