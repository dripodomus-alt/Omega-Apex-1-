"""
Optimized arbitrage scanner using token-DEX graph approach

FIXED:
- Added minimum TVL filter ($50k)
- Added minimum reserve filter (reject dust)
- Tightened spread filter to 15% max
- Filter out pools with fake/zero TVL

Instead of comparing all pool pairs, we:
1. Group pools by token pair
2. Filter out dust/low-liquidity pools
3. Find min/max prices per token
4. Only analyze the BEST opportunity per token

This is O(n) instead of O(n²)
"""

from collections import defaultdict
from typing import List, Dict, Optional
import logging
import os

logger = logging.getLogger(__name__)

# Filtering thresholds (P0 FIX)
MIN_POOL_TVL_USD = float(os.getenv('MIN_POOL_TVL_USD', '50000'))  # $50k minimum
MIN_RESERVE_VALUE = 0.01  # Minimum 0.01 of any token (filters dust like 0.00000001)
MAX_SPREAD_PCT = 15.0  # Maximum 15% spread (anything higher is suspicious)


def group_pools_by_token_pair(pools: List) -> Dict[str, List]:
    """
    Group all pools by their token pair.
    
    FIXED: Now filters out dust liquidity pools before grouping
    
    Returns:
        {
            'WMATIC/USDC': [pool1, pool2, pool3, ...],
            'WETH/USDC': [pool4, pool5, ...],
            ...
        }
    """
    grouped = defaultdict(list)
    filtered_count = 0
    
    for pool in pools:
        # FIX 1: Filter out pools with zero/fake TVL
        if pool.reserve_usd == 0:
            filtered_count += 1
            continue
        
        # FIX 2: Filter out dust liquidity (extremely low reserves)
        if pool.reserve0 < MIN_RESERVE_VALUE or pool.reserve1 < MIN_RESERVE_VALUE:
            filtered_count += 1
            continue
        
        # FIX 3: Filter out pools below minimum TVL threshold
        if pool.reserve_usd < MIN_POOL_TVL_USD:
            filtered_count += 1
            continue
        
        # Create normalized pair key (alphabetically sorted)
        token0 = pool.token0_symbol
        token1 = pool.token1_symbol
        
        if not token0 or not token1:
            continue
        
        # Normalize: always put tokens in alphabetical order
        pair = tuple(sorted([token0, token1]))
        pair_key = f"{pair[0]}/{pair[1]}"
        
        grouped[pair_key].append(pool)
    
    if filtered_count > 0:
        logger.info(f"   Filtered out {filtered_count} dust/low-TVL pools")
    
    return dict(grouped)


def find_best_prices_per_token(grouped_pools: Dict[str, List]) -> List[Dict]:
    """
    For each token pair, find the pools with:
    - LOWEST price (best buy)
    - HIGHEST price (best sell)
    
    FIXED: Tightened spread filter to reject unrealistic opportunities
    
    Returns list of best opportunities, sorted by spread.
    """
    opportunities = []
    
    for token_pair, pool_list in grouped_pools.items():
        if len(pool_list) < 2:
            continue  # Need at least 2 DEXs
        
        # Calculate prices for all pools in this group
        pool_prices = []
        for pool in pool_list:
            if pool.reserve0 <= 0:
                continue
            
            price = pool.reserve1 / pool.reserve0
            pool_prices.append({
                'pool': pool,
                'price': price
            })
        
        if len(pool_prices) < 2:
            continue
        
        # Find extremes
        best_buy_entry = min(pool_prices, key=lambda x: x['price'])
        best_sell_entry = max(pool_prices, key=lambda x: x['price'])
        
        buy_pool = best_buy_entry['pool']
        sell_pool = best_sell_entry['pool']
        buy_price = best_buy_entry['price']
        sell_price = best_sell_entry['price']
        
        # Calculate spread
        unit_spread = sell_price - buy_price
        if unit_spread <= 0:
            continue
        
        spread_pct = (unit_spread / buy_price) * 100
        
        # FIX 4: Tightened spread filter from 100% to 15%
        # Anything above 15% is likely stale/fake data
        if spread_pct > MAX_SPREAD_PCT:
            logger.debug(
                f"Skipping {token_pair}: {spread_pct:.1f}% spread exceeds {MAX_SPREAD_PCT}% max "
                f"(Buy TVL: ${buy_pool.reserve_usd:,.0f}, Sell TVL: ${sell_pool.reserve_usd:,.0f})"
            )
            continue
        
        opportunities.append({
            'token_pair': token_pair,
            'buy_pool': buy_pool,
            'sell_pool': sell_pool,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'unit_spread': unit_spread,
            'spread_pct': spread_pct,
            'num_dexs': len(pool_list)
        })
    
    # Sort by spread percentage (best first)
    return sorted(opportunities, key=lambda x: x['spread_pct'], reverse=True)


def scan_with_token_graph(engine, loan_amount_usd: float = 10000) -> List:
    """
    Optimized scan using token-DEX graph approach.
    
    FIXED: Now filters dust pools and unrealistic spreads
    O(n) complexity instead of O(n²)
    """
    logger.info("🔍 Starting GRAPH-BASED arbitrage scan with DUST FILTERS")
    
    pools = list(engine.pools.values())
    logger.info(f"   Total pools loaded: {len(pools)}")
    logger.info(f"   Applying filters: TVL >= ${MIN_POOL_TVL_USD:,.0f}, Reserves >= {MIN_RESERVE_VALUE}, Spread <= {MAX_SPREAD_PCT}%")
    
    # STEP 1: Group by token pair (with filtering)
    grouped = group_pools_by_token_pair(pools)
    logger.info(f"   Unique token pairs after filtering: {len(grouped)}")
    
    # STEP 2: Find best buy/sell for each token
    best_opportunities = find_best_prices_per_token(grouped)
    logger.info(f"   Potential opportunities: {len(best_opportunities)}")
    
    if len(best_opportunities) == 0:
        logger.warning("⚠️ No opportunities found after applying filters. All pools may be dust/fake TVL.")
        return []
    
    # Log top opportunities for debugging
    logger.info("\n   Top 5 opportunities after filtering:")
    for i, opp in enumerate(best_opportunities[:5], 1):
        logger.info(
            f"   [{i}] {opp['token_pair']}: {opp['spread_pct']:.2f}% "
            f"(Buy: {opp['buy_pool'].dex_name} ${opp['buy_pool'].reserve_usd:,.0f}, "
            f"Sell: {opp['sell_pool'].dex_name} ${opp['sell_pool'].reserve_usd:,.0f})"
        )
    
    # STEP 3: Analyze top opportunities with full swap math
    analyzed_spreads = []
    
    for i, opp in enumerate(best_opportunities[:50], 1):  # Analyze top 50
        logger.info(f"   [{i}/{len(best_opportunities)}] Analyzing {opp['token_pair']}: {opp['spread_pct']:.2f}% spread")
        
        spread = engine.analyze_spread(
            opp['buy_pool'],
            opp['sell_pool'],
            loan_amount_usd=loan_amount_usd
        )
        
        if spread and spread.flash_loan.net_profit_usd > 0:
            analyzed_spreads.append(spread)
    
    # Sort by net profit
    analyzed_spreads.sort(key=lambda x: x.flash_loan.net_profit_usd, reverse=True)
    
    logger.info(f"✅ Found {len(analyzed_spreads)} profitable opportunities")
    
    return analyzed_spreads
