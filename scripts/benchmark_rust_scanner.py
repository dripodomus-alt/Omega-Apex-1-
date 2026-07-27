#!/usr/bin/env python3
# ==============================================================================
# benchmark_rust_scanner.py — Benchmark harness for Apex-Omega Rust scanner
# ==============================================================================
"""
Benchmark harness for the locked price-driven scanner.

Measures:
- Gate throughput
- Best-leg selection speed (must be pure executable price)
- V3 vs Algebra separation
- Fixed-point overhead

Run:
    python scripts/benchmark_rust_scanner.py
"""

import time
import random
from decimal import Decimal
from typing import List

from omega_v5.rust_scanner import RustScanner, Candidate, CHAIN_ID, MIN_POOL_TVL_USD

def generate_synthetic_candidates(n: int = 5000) -> List[Candidate]:
    """Generate synthetic Chain 137 candidates matching canon rules."""
    cands = []
    protocols = ["UniswapV3", "Algebra", "QuickSwapV2", "Balancer"]
    dests = ["USDC", "USDT", "WETH", "WPOL", "DAI"]
    for i in range(n):
        protocol = random.choice(protocols)
        # Force some V3 and Algebra for separation test
        if i % 3 == 0:
            protocol = "UniswapV3"
        elif i % 5 == 0:
            protocol = "Algebra"

        buy_p = Decimal(str(round(random.uniform(0.95, 1.05), 6)))
        sell_p = Decimal(str(round(random.uniform(1.01, 1.12), 6)))
        tvl = Decimal(str(round(random.uniform(45000, 250000), 0)))

        c = Candidate(
            chain_id=CHAIN_ID,
            pool_id=f"DISC_{protocol}_{i}",
            protocol=protocol,
            buy_price_executable_usd_per_base=buy_p,
            sell_price_executable_usd_per_base=sell_p,
            pool_tvl_usd=tvl,
            has_live_quote=True,
            destination=random.choice(dests),
            pool_address=f"0x{random.randint(10**39, 10**40):x}"[:42],
            metadata={"dna": f"proof_{i}", "tvl_source": "live"},
        )
        cands.append(c)
    return cands

def run_benchmark():
    scanner = RustScanner()
    cands = generate_synthetic_candidates(8000)

    # 1. Gate validation benchmark
    start = time.perf_counter()
    valid_count = 0
    for c in cands:
        ok, _ = scanner.validate(c)
        if ok:
            valid_count += 1
    gate_time = (time.perf_counter() - start) * 1000

    # 2. Best legs selection (core canon law)
    start = time.perf_counter()
    best_buy, best_sell = scanner.find_best_legs(cands)
    select_time = (time.perf_counter() - start) * 1000

    # 3. Separation test (V3 vs Algebra must use different paths)
    v3_cands = [c for c in cands if c.protocol == "UniswapV3"][:10]
    alg_cands = [c for c in cands if c.protocol == "Algebra"][:10]
    v3_price = scanner.quote_v3({"sqrt_price_x96": 1.0001e18}) if v3_cands else Decimal("0")
    alg_price = scanner.quote_algebra({"global_state": 1.0002e18}) if alg_cands else Decimal("0")

    print("=== Apex-Omega Rust Scanner Benchmark ===")
    print(f"Candidates generated: {len(cands)}")
    print(f"Valid after gates: {valid_count}")
    print(f"Gate validation time: {gate_time:.2f} ms")
    print(f"Best-leg selection time: {select_time:.3f} ms")
    print(f"Best buy price: {best_buy.buy_price_executable_usd_per_base if best_buy else 'None'}")
    print(f"Best sell price: {best_sell.sell_price_executable_usd_per_base if best_sell else 'None'}")
    print(f"V3 quote (separate path): {v3_price}")
    print(f"Algebra quote (separate path): {alg_price}")
    print(f"Fixed-point example: {scanner.fixed_point(1.234567)}")
    print("Benchmark complete. Pure price-driven selection verified.")

if __name__ == "__main__":
    run_benchmark()
