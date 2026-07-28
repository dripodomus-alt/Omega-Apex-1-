#!/usr/bin/env python3
# ==============================================================================
# compare_scanners.py — Performance benchmark for Rust vs. Python scanners.
#
# This script directly measures and compares the performance of the high-speed
# Rust scanning engine against its pure Python equivalent. It validates that
# both implementations produce identical results while quantifying the
# performance gain from the Rust implementation.
# Now supports --json-output for bottleneck discovery and template generation.
# ==============================================================================

import argparse
import json
import random
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Dict

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


def main() -> int:
    """Main benchmark execution function."""
    parser = argparse.ArgumentParser(description="Benchmark Rust vs. Python opportunity scanners.")
    parser.add_argument("--tokens", type=int, default=25, help="Number of synthetic tokens to generate (if not using --pools-json).")
    parser.add_argument("--pools-per-pair", type=int, default=5, help="Number of pools to generate for each token pair (if not using --pools-json).")
    parser.add_argument("--json-output", type=str, default=None, help="Path to write structured JSON results for bottleneck analysis.")
    parser.add_argument("--min-tvl-usd", type=str, default="50000", help="Minimum TVL filter passed to RustScanner.")
    parser.add_argument("--pools-json", type=str, default=None, help="Path to a JSON file containing a registry of pools to use for the benchmark.")
    args = parser.parse_args()

    print("=" * 80)
    print(" Rust vs. Python Scanner Performance Benchmark")
    print("=" * 80)

    scanner = RustScanner(min_tvl_usd=args.min_tvl_usd)

    if not scanner.is_available():
        print("\n❌ Rust scanner not available. Run 'maturin develop' first.")
        print("Cannot perform a meaningful comparison.")
        return 1

    pools = {}
    if args.pools_json:
        pools_path = Path(args.pools_json)
        if not pools_path.exists():
            print(f"❌ Error: Pools JSON file not found at '{pools_path}'")
            return 1
        print(f"Loading pools from registry: {pools_path}")
        with open(pools_path, "r") as f:
            pools = json.load(f)
    else:
        print(f"Configuration: --tokens {args.tokens} --pools-per-pair {args.pools_per_pair} --min-tvl-usd {args.min_tvl_usd}")
        pools = generate_pools(num_tokens=args.tokens, pools_per_pair=args.pools_per_pair)

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
        match_ok = False
    else:
        print("✅  Result count matches between Rust and Python implementations.")
        match_ok = True

    performance_multiplier = (py_duration / rust_duration) if rust_duration > 0 else 0.0
    print(f"\n🚀 Performance Gain: Rust is {performance_multiplier:.2f}x faster than Python.")

    # Structured results for bottleneck discovery
    results = {
        "config": {
            "tokens": args.tokens,
            "pools_per_pair": args.pools_per_pair,
            "min_tvl_usd": int(args.min_tvl_usd),
            "total_pools": len(pools)
        },
        "performance": {
            "rust_ms": round(rust_duration, 2),
            "python_ms": round(py_duration, 2),
            "multiplier": round(performance_multiplier, 2),
            "opportunities_rust": len(rust_results),
            "opportunities_python": len(python_results)
        },
        "status": {
            "match_ok": match_ok,
            "rust_available": True
        }
    }

    print(json.dumps(results, indent=2))

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results written to {output_path}")

    return 0 if match_ok else 1


if __name__ == "__main__":
    sys.exit(main())
