#!/usr/bin/env python3
"""
Test price discovery directly to debug why opportunities aren't being found
"""

import sys
sys.path.insert(0, '/app/backend')

from arbitrage_engine import get_arbitrage_engine
from price_discovery_engine import get_price_discovery_engine

# Initialize engines
print("Initializing engines...")
engine = get_arbitrage_engine()
discovery = get_price_discovery_engine()

# Build price matrix
print(f"Building price matrix from {len(engine.pools)} pools...")
price_matrix = discovery.build_price_matrix(engine.pools)

print(f"\nPrice Matrix Built:")
print(f"  Total pairs: {len(price_matrix)}")

# Check WMATIC/SAND specifically
if 'WMATIC/SAND' in price_matrix:
    quotes = price_matrix['WMATIC/SAND']
    print(f"\nWMATIC/SAND quotes: {len(quotes)}")
    
    for q in quotes:
        print(f"  {q.dex_name}: ask=${q.ask_price:.8f}, bid=${q.bid_price:.8f}, tvl=${q.tvl_usd:,.0f}")
    
    # Find best
    valid = [q for q in quotes if q.tvl_usd >= 0]  # No TVL filter
    if valid:
        best_buy = min(valid, key=lambda q: q.ask_price)
        best_sell = max(valid, key=lambda q: q.bid_price)
        
        spread_bps = ((best_sell.bid_price - best_buy.ask_price) / best_buy.ask_price) * 10000
        
        print(f"\n  BEST BUY: {best_buy.dex_name} @ ${best_buy.ask_price:.8f}")
        print(f"  BEST SELL: {best_sell.dex_name} @ ${best_sell.bid_price:.8f}")
        print(f"  CROSS-POOL SPREAD: {spread_bps:.2f} bps ({spread_bps/100:.2f}%)")

# Run the function
print("\n" + "="*70)
print("Running find_arbitrage_opportunities...")
opportunities = discovery.find_arbitrage_opportunities(
    min_spread_bps=50,
    min_tvl_usd=0
)

print(f"Opportunities found: {len(opportunities)}")
for buy_quote, sell_quote, spread_bps in opportunities[:5]:
    print(f"  {buy_quote.token_pair}: {spread_bps:.2f} bps")
    print(f"    Buy @ {buy_quote.dex_name}: ${buy_quote.ask_price:.8f}")
    print(f"    Sell @ {sell_quote.dex_name}: ${sell_quote.bid_price:.8f}")
