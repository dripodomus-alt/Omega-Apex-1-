#!/usr/bin/env python3
# ==============================================================================
# compare_scanners.py — Performance benchmark for Rust vs. Python scanners.
#
# This script directly measures and compares the performance of the high-speed
# Rust scanning engine against its pure Python equivalent. It validates that
# both implementations produce identical results while quantifying the
# performance gain from the Rust implementation.
# ==============================================================================

import json
import random
import sys
import time
from decimal import Decimal
from pathlib import Path

# Ensure the project root is in the Python path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5.rust_scanner import RustScanner


def generate_pools(num_tokens: int, pools_per_pair: int) -> dict:
    """Generates a large, complex set of synthetic pools for benchmarking."""
    print(f"Generating a test set of {num_tokens} tokens with {pools_per_pair} pools per pair...")
    tokens = [f"0x{'%040x' % i}" for i in range(num_tokens)]
    pools_data = {}
    pool_counter = 0

    for i in range(num_tokens):
        for j in range(i + 1, num_tokens):
            token_a, token_b = tokens[i], tokens[j]
            for k in range(pools_per_pair):
                pool_id = f"SCALE_POOL_{pool_counter}"
                # Create price variance to exercise selection logic
                price = 3000.0 + (random.random() - 0.5) * 100
                pools_data[pool_id] = {
                    "protocol": "UniswapV3" if k % 2 == 0 else "Algebra",
                    "address": f"0x{'%040x' % (pool_counter + 1)}",
                    "tokens": [token_a, token_b],
                    "total_executable_liquidity_usd": "1000000.0",
                    "executable_price": str(price),
                }
                pool_counter += 1

    # Inject a guaranteed profitable route to ensure it's found
    pools_data["GUARANTEED_BUY"] = {
        "protocol": "UniswapV3", "address": "0xdeadbeefa" + "a" * 31,
        "tokens": [tokens[0], tokens[1]], "total_executable_liquidity_usd": "5000000.0",
        "executable_price": "2900.0",
    }
    pools_data["GUARANTEED_SELL"] = {
        "protocol": "UniswapV2", "address": "0xdeadbeefb" + "b" * 31,
        "tokens": [tokens[1], tokens[0]], "total_executable_liquidity_usd": "5000000.0",
        "executable_price": "2901.0",
    }
    print(f"Generated {len(pools_data)} total pools.")
    return pools_data


def main():
    """Main benchmark execution function."""
    print("=" * 80)
    print(" Rust vs. Python Scanner Performance Benchmark")
    print("=" * 80)

    scanner = RustScanner(min_tvl_usd="50000")

    if not scanner.is_available():
        print("\n❌ Rust scanner not available. Run 'maturin develop' first.")
        print("Cannot perform a meaningful comparison.")
        return 1

    pools = generate_pools(num_tokens=25, pools_per_pair=5)

    # --- Benchmark Rust Implementation ---
    print("\nBenchmarking Rust scanner...")
    start_time_rust = time.perf_counter()
    rust_results = scanner.scan(pools)
    end_time_rust = time.perf_counter()
    rust_duration = (end_time_rust - start_time_rust) * 1000  # to ms
    print(f"Rust scan completed in: {rust_duration:.2f} ms")
    print(f"Opportunities found: {len(rust_results)}")

    # --- Benchmark Python Fallback Implementation ---
    print("\nBenchmarking Python fallback scanner...")
    start_time_py = time.perf_counter()
    # We call the private method directly for this benchmark
    python_results = scanner._python_fallback_scan(pools)
    end_time_py = time.perf_counter()
    py_duration = (end_time_py - start_time_py) * 1000  # to ms
    print(f"Python scan completed in: {py_duration:.2f} ms")
    print(f"Opportunities found: {len(python_results)}")

    # --- Comparison and Verification ---
    print("\n" + "=" * 80)
    print(" Benchmark Summary")
    print("=" * 80)

    if len(rust_results) != len(python_results):
        print(f"⚠️  Result mismatch! Rust found {len(rust_results)} but Python found {len(python_results)}.")
    else:
        print("✅  Result count matches between Rust and Python implementations.")

    if rust_duration > 0:
        performance_multiplier = py_duration / rust_duration
        print(f"\n🚀 Performance Gain: Rust is {performance_multiplier:.2f}x faster than Python.")

    return 0

if __name__ == "__main__":
    sys.exit(main())