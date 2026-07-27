#!/usr/bin/env python3
"""
Benchmark script for the Rust price-driven scanner vs pure Python fallback.

Run after `maturin develop`:
    python scripts/benchmark_rust_scanner.py
"""

import time
import json
import random
from decimal import Decimal

try:
    from scanner_core import GateConfig, scan_opportunities
    from omega_v5.rust_scanner import RustScanner
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

def generate_synthetic_pools(num_pairs=50, pools_per_pair=3):
    """Generate synthetic pool data for benchmarking."""
    pools = {}
    tokens = [f"T{i}" for i in range(20)]
    counter = 0
    for i in range(len(tokens)):
        for j in range(i+1, len(tokens)):
            if len(pools) >= num_pairs:
                break
            ta, tb = tokens[i], tokens[j]
            for k in range(pools_per_pair):
                price = Decimal(random.uniform(0.5, 2.0))
                tvl = Decimal(random.uniform(60000, 500000))
                addr = f"0x{hex(counter)[2:].zfill(40)}"
                pools[f"pool_{counter}"] = {
                    "protocol": random.choice(["UniswapV2", "UniswapV3", "Algebra"]),
                    "address": addr,
                    "tokens": [ta, tb],
                    "total_executable_liquidity_usd": str(tvl),
                    "executable_price": str(price)
                }
                counter += 1
            if len(pools) >= num_pairs:
                break
    # Add one guaranteed profitable pair
    pools["guaranteed_buy"] = {
        "protocol": "UniswapV2",
        "address": "0x" + "a"*40,
        "tokens": ["USDC", "WETH"],
        "total_executable_liquidity_usd": "150000",
        "executable_price": "3000"
    }
    pools["guaranteed_sell"] = {
        "protocol": "UniswapV2",
        "address": "0x" + "b"*40,
        "tokens": ["WETH", "USDC"],
        "total_executable_liquidity_usd": "150000",
        "executable_price": "3015"
    }
    return pools

def benchmark_rust(pools, config, iterations=5):
    if not RUST_AVAILABLE:
        return None
    scanner = RustScanner(min_tvl_usd=config.min_tvl_usd, chain_id=config.chain_id)
    start = time.perf_counter()
    for _ in range(iterations):
        results = scanner.scan(pools)
    elapsed = (time.perf_counter() - start) / iterations
    return elapsed, len(results) if 'results' in locals() else 0

def benchmark_python_fallback(pools, config, iterations=5):
    scanner = RustScanner(min_tvl_usd=config.min_tvl_usd)
    # Force fallback
    scanner.is_available = lambda: False
    start = time.perf_counter()
    for _ in range(iterations):
        results = scanner.scan(pools)
    elapsed = (time.perf_counter() - start) / iterations
    return elapsed, len(results) if 'results' in locals() else 0

def main():
    print("=== Rust Scanner Benchmark ===")
    pools = generate_synthetic_pools(num_pairs=100, pools_per_pair=4)
    print(f"Generated {len(pools)} synthetic pools")

    config = GateConfig(min_tvl_usd="50000", chain_id=137) if RUST_AVAILABLE else None

    if RUST_AVAILABLE:
        rust_time, rust_count = benchmark_rust(pools, config)
        print(f"Rust scanner: {rust_time*1000:.2f} ms per run, found {rust_count} candidates")
    else:
        print("Rust scanner not available (skipping)")

    py_time, py_count = benchmark_python_fallback(pools, config)
    print(f"Python fallback: {py_time*1000:.2f} ms per run, found {py_count} candidates")

    if RUST_AVAILABLE:
        speedup = py_time / rust_time if rust_time > 0 else 0
        print(f"Speedup (Rust vs Py): {speedup:.1f}x")

    print("Benchmark complete. Rust must be the source of truth for price selection.")

if __name__ == "__main__":
    main()
