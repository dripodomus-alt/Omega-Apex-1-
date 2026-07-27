#!/usr/bin/env python3
"""
Colab / notebook friendly runner for the Apex-Omega Rust price-driven scanner.

Usage in Colab:
    !pip install maturin
    !maturin develop
    %run scripts/run_apex_omega_colab_scanner.py

Or directly:
    python scripts/run_apex_omega_colab_scanner.py
"""

import json
from decimal import Decimal

try:
    from scanner_core import GateConfig, scan_opportunities
    from omega_v5.rust_scanner import RustScanner, find_best_legs_with_rust
    RUST_AVAILABLE = True
except ImportError as e:
    print("Rust extension not available:", e)
    RUST_AVAILABLE = False

def run_scanner_demo():
    print("=== Apex Omega Rust Scanner Demo (Colab ready) ===")
    print(f"Rust available: {RUST_AVAILABLE}")

    # Example pool data (simulating live discovery output)
    example_pools = {
        "disc_usdc_weth_v2": {
            "protocol": "UniswapV2",
            "address": "0x1111111111111111111111111111111111111111",
            "tokens": ["USDC", "WETH"],
            "total_executable_liquidity_usd": "250000",
            "executable_price": "2995.5"
        },
        "disc_weth_usdc_v3": {
            "protocol": "UniswapV3",
            "address": "0x2222222222222222222222222222222222222222",
            "tokens": ["WETH", "USDC"],
            "total_executable_liquidity_usd": "180000",
            "executable_price": "3005.2"
        },
        "disc_usdc_weth_algebra": {
            "protocol": "Algebra",
            "address": "0x3333333333333333333333333333333333333333",
            "tokens": ["USDC", "WETH"],
            "total_executable_liquidity_usd": "95000",
            "executable_price": "2998.0"
        }
    }

    if RUST_AVAILABLE:
        scanner = RustScanner(min_tvl_usd="50000", chain_id=137)
        results = scanner.scan(example_pools)
        print(f"\nRust scanner found {len(results)} price-driven opportunities:")
        for r in results:
            print(f"  {r.token_in} -> {r.token_mid}: buy@{r.buy_leg.executable_price} ({r.buy_leg.protocol}) sell@{r.sell_leg.executable_price} ({r.sell_leg.protocol}) spread={r.net_spread}")
    else:
        print("\nFalling back to pure Python implementation (same logic):")
        results = find_best_legs_with_rust(example_pools, min_tvl="50000")
        for r in results:
            print(f"  {r.token_in} -> {r.token_mid}: buy@{r.buy_leg.executable_price} sell@{r.sell_leg.executable_price} spread={r.net_spread}")

    print("\nKey invariants enforced:")
    print("- Min buy price selected (best for arbitrage entry)")
    print("- Max sell price selected (best for arbitrage exit)")
    print("- TVL gate >= 50k USD")
    print("- Chain 137 only")
    print("- Different pools for buy/sell")
    print("- Protocols (V3/Algebra) treated separately via metadata only")

    print("\nTo rebuild after Rust changes: maturin develop")
    print("To test: pytest tests/rust/test_scanner_core.py")

if __name__ == "__main__":
    run_scanner_demo()
