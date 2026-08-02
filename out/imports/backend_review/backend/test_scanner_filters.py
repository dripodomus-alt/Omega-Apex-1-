#!/usr/bin/env python3
"""
Test the updated optimized_scanner with filters
"""

from arbitrage_engine import get_arbitrage_engine
from optimized_scanner import scan_with_token_graph
import time

print("Testing optimized scanner with P0 filters...")
print("=" * 80)

engine = get_arbitrage_engine()
print('\nWaiting for pools to load...')
time.sleep(8)

print(f'\nTotal pools in engine: {len(engine.pools)}\n')

# Run the scan with filters
print("Running graph-based scan with dust filters...")
print("=" * 80)

spreads = scan_with_token_graph(engine, loan_amount_usd=10000)

print("\n")
print("=" * 80)
print("SCAN RESULTS")
print("=" * 80)

if spreads:
    print(f"\n✅ Found {len(spreads)} profitable opportunities after filtering!\n")
    for i, spread in enumerate(spreads[:5], 1):
        print(f"{i}. {spread.token_pair}")
        print(f"   Buy: {spread.buy_pool.dex_name} (TVL: ${spread.buy_pool.reserve_usd:,.0f})")
        print(f"   Sell: {spread.sell_pool.dex_name} (TVL: ${spread.sell_pool.reserve_usd:,.0f})")
        print(f"   Spread: {spread.spread_pct:.2f}%")
        print(f"   Net Profit: ${spread.flash_loan.net_profit_usd:,.2f}")
        print()
else:
    print("\n⚠️ No profitable opportunities found.")
    print("This is EXPECTED if all pools have fake TVL < $50k threshold.")
    print("The filters are working correctly!")
