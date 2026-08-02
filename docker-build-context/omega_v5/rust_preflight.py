#!/usr/bin/env python3
# ==============================================================================
# rust_preflight.py -- mandatory Rust hybrid engine readiness check.
# ==============================================================================

from __future__ import annotations

from .rust_engine import assert_rust_engine_ready, rust_bellman_ford_cycles


def main() -> int:
    binary = assert_rust_engine_ready()
    rates = {
        ("A", "B"): [{"pool_id": "test-ab", "protocol": "test", "rate": 2.0}],
        ("B", "A"): [{"pool_id": "test-ba", "protocol": "test", "rate": 0.6}],
    }
    cycles = rust_bellman_ford_cycles(rates)
    if not cycles:
        print(f"rust_engine_preflight=FAIL binary={binary} reason=no_cycle_detected")
        return 1
    best = cycles[0]
    print(
        f"rust_engine_preflight=OK binary={binary} "
        f"cycles={len(cycles)} best_profit_pct={best.get('profit_pct')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
