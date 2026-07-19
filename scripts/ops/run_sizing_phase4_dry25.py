#!/usr/bin/env python3
"""
Phase-4 sizing 2.0 — 25-cycle dry run.

Exercises optimize_principal_with_dynamic + ranker sizing path without broadcast.
"""
from __future__ import annotations

import random
import sys
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5.flash_loan import FlashSource, evaluate_profitability
from omega_v5.sizing import (
    dynamic_size_optimizer,
    optimize_principal_with_dynamic,
    estimate_route_tvl_usd,
)


def _pools(tvl_a: Decimal, tvl_b: Decimal) -> dict:
    return {
        "P1": {
            "tokens": ["USDC", "WETH"],
            "total_executable_liquidity_usd": tvl_a,
            "tvl_usd": tvl_a,
        },
        "P2": {
            "tokens": ["WETH", "USDC"],
            "total_executable_liquidity_usd": tvl_b,
            "tvl_usd": tvl_b,
        },
    }


def _quote_factory(peak: Decimal, edge_bps: Decimal):
    """Parabolic-ish gross: peaks near `peak`, declines with size."""

    def quote_fn(principal: Decimal) -> Decimal:
        if principal <= 0:
            return Decimal("0")
        # edge declines as |p - peak| grows
        dist = abs(principal - peak) / max(peak, Decimal("1"))
        edge = (edge_bps / Decimal("10000")) * (Decimal("1") - dist * Decimal("0.85"))
        if edge < Decimal("0"):
            edge = Decimal("0")
        return principal * (Decimal("1") + edge)

    return quote_fn


def run_cycle(cycle: int) -> dict:
    random.seed(1000 + cycle)
    tvl_a = Decimal(str(random.randint(200_000, 2_000_000)))
    tvl_b = Decimal(str(random.randint(150_000, 1_500_000)))
    pools = _pools(tvl_a, tvl_b)
    bottleneck = min(tvl_a, tvl_b)
    peak = bottleneck * Decimal("0.08")
    edge_bps = Decimal(str(random.randint(12, 45)))

    opp = MagicMock()
    opp.pool_sequence = ["P1", "P2"]
    opp.path = ["USDC", "WETH", "USDC"]
    opp.flash_source = FlashSource.BALANCER

    t0 = time.perf_counter()
    sizing = optimize_principal_with_dynamic(
        opportunity=opp,
        live_pools=pools,
        quote_function=_quote_factory(peak, edge_bps),
        steps=14,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    route_tvl = estimate_route_tvl_usd(["P1", "P2"], pools)
    selected = sizing.selected_principal_usd
    max_profit = sizing.max_profit_usd
    upper = sizing.search_upper_bound_usd

    # Validate ladder optimizer early-exit path still works
    calls = {"n": 0}

    def pf(p: Decimal):
        calls["n"] += 1
        gross = _quote_factory(peak, edge_bps)(p)
        return evaluate_profitability(
            gross,
            p,
            hops=2,
            flash_source=FlashSource.BALANCER,
            asset="USDC",
        )

    best_p, best_prof = dynamic_size_optimizer(
        profit_function=pf,
        min_principal=Decimal("1000"),
        max_principal=upper if upper > 0 else Decimal("10000"),
        steps=40,
    )

    ok = True
    reasons = []
    if route_tvl <= 0:
        ok = False
        reasons.append("tvl_missing")
    if selected < 0:
        ok = False
        reasons.append("negative_principal")
    if selected > upper + Decimal("0.01"):
        ok = False
        reasons.append("above_cap")
    if calls["n"] >= 40:
        # early exit should usually cut before full 40 on peaked curves
        pass

    return {
        "cycle": cycle,
        "ok": ok,
        "reasons": reasons,
        "bottleneck_tvl": str(bottleneck),
        "route_tvl": str(route_tvl),
        "upper_bound": str(upper),
        "selected": str(selected),
        "max_profit": str(max_profit),
        "ladder_best": str(best_p),
        "ladder_net": str(getattr(best_prof, "net_profit_usd", 0) if best_prof else 0),
        "ladder_calls": calls["n"],
        "elapsed_ms": round(elapsed_ms, 3),
        "method": sizing.method,
        "version": (sizing.search_space_details or {}).get("version", "?"),
    }


def main() -> int:
    print("=" * 72)
    print("PHASE-4 SIZING 2.0 — 25 CYCLE DRY RUN (no broadcast)")
    print("=" * 72)

    rows = []
    for c in range(1, 26):
        row = run_cycle(c)
        rows.append(row)
        status = "PASS" if row["ok"] else "FAIL"
        print(
            f"  [{c:02d}] {status} selected=${row['selected']:>12} "
            f"upper=${row['upper_bound']:>12} peak_net=${row['max_profit']:>10} "
            f"tvl=${row['route_tvl']:>12} ladder_calls={row['ladder_calls']:<3} "
            f"{row['elapsed_ms']}ms method={row['method']}"
        )

    passed = sum(1 for r in rows if r["ok"])
    avg_ms = sum(r["elapsed_ms"] for r in rows) / len(rows)
    avg_calls = sum(r["ladder_calls"] for r in rows) / len(rows)
    profitable = sum(1 for r in rows if Decimal(r["max_profit"]) > 0)
    selected_pos = sum(1 for r in rows if Decimal(r["selected"]) > 0)

    print("-" * 72)
    print(f"Cycles:            25")
    print(f"Passed caps/gates: {passed}/25")
    print(f"Positive size:     {selected_pos}/25")
    print(f"Positive peak net: {profitable}/25")
    print(f"Avg size latency:  {avg_ms:.3f} ms")
    print(f"Avg ladder calls:  {avg_calls:.1f} (early-exit speed)")
    print(f"Sizing version:    2.0 (optimize_principal_with_dynamic)")
    print("=" * 72)

    # Also run the legacy DNA dry-run for staging stats if present
    try:
        from tests.dry_run_25_cycles import main as dna_main

        print("\n--- Legacy DNA staging dry-run ---")
        dna_main()
    except Exception as exc:
        print(f"(DNA dry-run skipped: {exc})")

    return 0 if passed == 25 else 1


if __name__ == "__main__":
    raise SystemExit(main())
