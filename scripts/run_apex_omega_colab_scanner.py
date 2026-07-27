#!/usr/bin/env python3
# ==============================================================================
# run_apex_omega_colab_scanner.py — Colab / notebook runner for locked scanner
# ==============================================================================
"""
Standalone Colab-style runner for the Apex-Omega Chain 137 scanner.

This mirrors the "Python/Colab production-ready" status in the locked canon.

It uses the Rust scanner when available, otherwise the pure-Python reference
implementation that exactly follows:

best_buy = min(..., key=lambda r: r.buy_price_executable_usd_per_base)
best_sell = max(..., key=lambda r: r.sell_price_executable_usd_per_base)

Gates are enforced identically.
"""

from decimal import Decimal
from typing import List, Dict, Any

from omega_v5.rust_scanner import RustScanner, Candidate, build_candidate_from_row

def load_synthetic_or_live_rows() -> List[Dict[str, Any]]:
    """In real Colab this would come from live pool matrix or cache."""
    return [
        {
            "chain_id": 137,
            "pool_id": "DISC_V3_USDC_WETH_500",
            "protocol": "UniswapV3",
            "buy_price_executable_usd_per_base": "0.9998",
            "sell_price_executable_usd_per_base": "1.0023",
            "pool_tvl_usd": "125000",
            "has_live_quote": True,
            "destination": "WETH",
            "pool_address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            "metadata": {"dna": "live_quote_137_42", "source": "eth_call"},
        },
        {
            "chain_id": 137,
            "pool_id": "DISC_ALG_USDC_USDT_100",
            "protocol": "Algebra",
            "buy_price_executable_usd_per_base": "0.9995",
            "sell_price_executable_usd_per_base": "1.0019",
            "pool_tvl_usd": "98000",
            "has_live_quote": True,
            "destination": "USDT",
            "pool_address": "0x1234567890abcdef1234567890abcdef12345678",
            "metadata": {"dna": "algebra_live_137", "source": "global_state"},
        },
        {
            "chain_id": 137,
            "pool_id": "DISC_QS_WPOL_USDC",
            "protocol": "QuickSwapV2",
            "buy_price_executable_usd_per_base": "1.0012",
            "sell_price_executable_usd_per_base": "1.0001",
            "pool_tvl_usd": "45000",   # below gate
            "has_live_quote": True,
            "destination": "USDC",
            "pool_address": "0xdeadbeef",
            "metadata": {},
        },
    ]

def run_scanner_cycle(rows: List[Dict[str, Any]]):
    scanner = RustScanner()
    candidates = [build_candidate_from_row(r) for r in rows]

    print("=== Apex-Omega Chain 137 Scanner (Locked Canon) ===")
    print(f"Input candidates: {len(candidates)}")

    best_buy, best_sell = scanner.find_best_legs(candidates)

    if best_buy and best_sell:
        print("\n✅ VALID EXECUTABLE PAIR FOUND (price-driven only)")
        print(f"  Best BUY  (lowest executable price): {best_buy.pool_id} @ {best_buy.buy_price_executable_usd_per_base}")
        print(f"  Best SELL (highest executable price): {best_sell.pool_id} @ {best_sell.sell_price_executable_usd_per_base}")
        print(f"  Spread: {best_sell.sell_price_executable_usd_per_base - best_buy.buy_price_executable_usd_per_base}")
        print(f"  Destinations distinct: {best_buy.destination != best_sell.destination}")
        print(f"  Pools distinct: {best_buy.pool_address != best_sell.pool_address}")
        print(f"  DNA preserved: {best_buy.metadata}")
    else:
        print("\n❌ No pair passed all gates (TVL >= 50000, 2+ dests, buy < sell, distinct pools)")

    # Show gate rejections
    for c in candidates:
        ok, reason = scanner.validate(c)
        if not ok:
            print(f"  Rejected {c.pool_id}: {reason}")

if __name__ == "__main__":
    rows = load_synthetic_or_live_rows()
    run_scanner_cycle(rows)
    print("\nColab runner finished. Ready for notebook integration.")
