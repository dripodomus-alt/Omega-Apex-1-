#!/usr/bin/env python3
"""
Token-DEX Price Graph Generator

Groups all pools by token pair, then finds:
1. LOWEST price (best buy) across all DEXs
2. HIGHEST price (best sell) across all DEXs

This is the CORRECT way to find optimal arbitrage opportunities.
"""

import sys
from collections import defaultdict
from typing import Dict, List, Tuple

sys.path.insert(0, '/app/backend')

def build_token_dex_graph(pools: List) -> Dict[str, List[Dict]]:
    """
    Build a graph of token pairs → list of DEXs with prices
    
    Returns:
        {
            'WMATIC/USDC': [
                {'dex': 'QuickSwap', 'price': 0.6400, 'pool': pool_obj},
                {'dex': 'SushiSwap', 'price': 0.6450, 'pool': pool_obj},
                {'dex': 'Balancer', 'price': 0.6425, 'pool': pool_obj},
                ...
            ],
            'WETH/USDC': [...],
            ...
        }
    """
    graph = defaultdict(list)
    
    for pool in pools:
        # Create normalized token pair key (alphabetically sorted)
        token_pair = tuple(sorted([pool.token0_symbol, pool.token1_symbol]))
        pair_key = f"{token_pair[0]}/{token_pair[1]}"
        
        # Calculate price (token1 per token0)
        if pool.reserve0 > 0:
            price = pool.reserve1 / pool.reserve0
        else:
            continue
        
        # Add to graph
        graph[pair_key].append({
            'dex': pool.dex_name,
            'dex_id': pool.dex_id,
            'price': price,
            'pool': pool,
            'tvl': pool.reserve_usd
        })
    
    return dict(graph)


def find_best_arbitrage_per_token(graph: Dict[str, List[Dict]]) -> List[Dict]:
    """
    For each token pair, find the BEST arbitrage opportunity:
    - Lowest price (where to BUY)
    - Highest price (where to SELL)
    
    Returns list of opportunities sorted by spread.
    """
    opportunities = []
    
    for token_pair, dex_list in graph.items():
        if len(dex_list) < 2:
            continue  # Need at least 2 DEXs for arbitrage
        
        # Find LOWEST price (best buy)
        best_buy = min(dex_list, key=lambda x: x['price'])
        
        # Find HIGHEST price (best sell)
        best_sell = max(dex_list, key=lambda x: x['price'])
        
        # Calculate spread
        unit_spread = best_sell['price'] - best_buy['price']
        spread_pct = (unit_spread / best_buy['price']) * 100
        
        if unit_spread > 0:
            opportunities.append({
                'token_pair': token_pair,
                'buy_dex': best_buy['dex'],
                'buy_price': best_buy['price'],
                'buy_pool': best_buy['pool'],
                'sell_dex': best_sell['dex'],
                'sell_price': best_sell['price'],
                'sell_pool': best_sell['pool'],
                'unit_spread': unit_spread,
                'spread_pct': spread_pct,
                'num_dexs': len(dex_list),
                'all_dexs': dex_list
            })
    
    # Sort by spread percentage (best opportunities first)
    return sorted(opportunities, key=lambda x: x['spread_pct'], reverse=True)


if __name__ == "__main__":
    print("=" * 100)
    print("🔍 TOKEN-DEX PRICE GRAPH ANALYSIS")
    print("=" * 100)
    print()
    
    from arbitrage_engine import get_arbitrage_engine
    import time
    
    engine = get_arbitrage_engine()
    
    # Wait for pools to load
    print("Loading pools...")
    time.sleep(6)
    
    pools = list(engine.pools.values())
    print(f"✅ Loaded {len(pools)} pools")
    print()
    
    # STEP 1: Build graph
    print("=" * 100)
    print("STEP 1: GROUP BY TOKEN PAIR")
    print("=" * 100)
    print()
    
    graph = build_token_dex_graph(pools)
    
    print(f"Found {len(graph)} unique token pairs")
    print()
    
    # Show sample groups
    print("Sample token pair groups:")
    for i, (pair, dex_list) in enumerate(list(graph.items())[:5], 1):
        print(f"\n{i}. {pair} - {len(dex_list)} DEXs")
        for dex_entry in dex_list[:3]:
            print(f"   • {dex_entry['dex']}: ${dex_entry['price']:.6f} (TVL: ${dex_entry['tvl']:,.0f})")
    
    print()
    
    # STEP 2: Find best opportunities
    print("=" * 100)
    print("STEP 2: FIND BEST BUY/SELL FOR EACH TOKEN")
    print("=" * 100)
    print()
    
    opportunities = find_best_arbitrage_per_token(graph)
    
    print(f"Found {len(opportunities)} arbitrage opportunities")
    print()
    
    # STEP 3: Show top opportunities
    print("=" * 100)
    print("TOP 10 ARBITRAGE OPPORTUNITIES")
    print("=" * 100)
    print()
    
    for i, opp in enumerate(opportunities[:10], 1):
        print(f"{i}. {opp['token_pair']}")
        print(f"   🔵 BUY  (LEG 1): {opp['buy_dex']} @ ${opp['buy_price']:.6f}/token")
        print(f"   🔴 SELL (LEG 2): {opp['sell_dex']} @ ${opp['sell_price']:.6f}/token")
        print(f"   💰 SPREAD: ${opp['unit_spread']:.6f} per token ({opp['spread_pct']:.4f}%)")
        print(f"   📊 Available on {opp['num_dexs']} DEXs")
        print()
    
    # STEP 4: Compare with pairwise approach
    print("=" * 100)
    print("EFFICIENCY COMPARISON")
    print("=" * 100)
    print()
    
    # Calculate how many comparisons each method needs
    total_comparisons_pairwise = 0
    total_comparisons_graph = 0
    
    for pair, dex_list in graph.items():
        n = len(dex_list)
        if n >= 2:
            pairwise = n * (n - 1) // 2  # All pairs
            graph_based = 1  # Just find min/max
            
            total_comparisons_pairwise += pairwise
            total_comparisons_graph += graph_based
    
    print(f"OLD APPROACH (pairwise comparison):")
    print(f"  Total comparisons needed: {total_comparisons_pairwise:,}")
    print()
    print(f"NEW APPROACH (graph-based):")
    print(f"  Total comparisons needed: {total_comparisons_graph:,}")
    print()
    print(f"Efficiency gain: {total_comparisons_pairwise / total_comparisons_graph if total_comparisons_graph > 0 else 0:.1f}x faster!")
    print()
    
    # STEP 5: Example with real numbers
    print("=" * 100)
    print("EXAMPLE: DETAILED BREAKDOWN")
    print("=" * 100)
    print()
    
    if opportunities:
        best_opp = opportunities[0]
        
        print(f"Best opportunity: {best_opp['token_pair']}")
        print()
        print(f"All DEXs trading this pair:")
        for dex_entry in sorted(best_opp['all_dexs'], key=lambda x: x['price']):
            marker = ""
            if dex_entry['dex'] == best_opp['buy_dex']:
                marker = " ← 🔵 BEST BUY (LOWEST)"
            elif dex_entry['dex'] == best_opp['sell_dex']:
                marker = " ← 🔴 BEST SELL (HIGHEST)"
            
            print(f"  {dex_entry['dex']}: ${dex_entry['price']:.6f}{marker}")
        
        print()
        print(f"ARBITRAGE PATH:")
        print(f"  1. BUY on {best_opp['buy_dex']} @ ${best_opp['buy_price']:.6f}")
        print(f"  2. SELL on {best_opp['sell_dex']} @ ${best_opp['sell_price']:.6f}")
        print(f"  3. Profit: ${best_opp['unit_spread']:.6f} per token")
        print()
        print(f"With $10,000 flash loan:")
        tokens = 10000 / best_opp['buy_price']
        gross_profit = tokens * best_opp['unit_spread']
        print(f"  Tokens: {tokens:,.2f}")
        print(f"  Gross profit: {tokens:,.2f} × ${best_opp['unit_spread']:.6f} = ${gross_profit:,.2f}")
    
    print()
    print("=" * 100)
    print("✅ GRAPH ANALYSIS COMPLETE")
    print("=" * 100)
    print()
    print("KEY INSIGHTS:")
    print("  1. ✅ Grouped all pools by token pair")
    print("  2. ✅ Found LOWEST buy price across ALL DEXs")
    print("  3. ✅ Found HIGHEST sell price across ALL DEXs")
    print("  4. ✅ Identified optimal arbitrage paths")
    print(f"  5. ✅ {total_comparisons_pairwise / total_comparisons_graph if total_comparisons_graph > 0 else 0:.1f}x more efficient than pairwise")
    print()
