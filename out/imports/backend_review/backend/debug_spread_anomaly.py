#!/usr/bin/env python3
"""
Debug script to find the origin of massive spread anomalies
"""

from arbitrage_engine import get_arbitrage_engine
import time

engine = get_arbitrage_engine()
print('Waiting for pools to load...')
time.sleep(6)

pools = list(engine.pools.values())
print(f'Total pools: {len(pools)}\n')

# Find WBTC/QUICK pools mentioned in user's table
print("=" * 100)
print("SEARCHING FOR WBTC/QUICK POOLS")
print("=" * 100)
print()

wbtc_quick_pools = []
for pool in pools:
    tokens = {pool.token0_symbol, pool.token1_symbol}
    if 'WBTC' in tokens and 'QUICK' in tokens:
        wbtc_quick_pools.append(pool)
        print(f'Pool: {pool.dex_name}')
        print(f'  Address: {pool.pool_address[:20]}...')
        print(f'  Token0: {pool.token0_symbol} (decimals={pool.token0_decimals})')
        print(f'  Token1: {pool.token1_symbol} (decimals={pool.token1_decimals})')
        print(f'  Reserve0: {pool.reserve0:.10f}')
        print(f'  Reserve1: {pool.reserve1:.10f}')
        print(f'  Price (res1/res0): {pool.reserve1/pool.reserve0 if pool.reserve0 > 0 else 0:.10f}')
        print(f'  TVL: ${pool.reserve_usd:,.2f}')
        print()

print(f'Found {len(wbtc_quick_pools)} WBTC/QUICK pools')
print()

# Check if there are pools with extremely low liquidity
print("=" * 100)
print("CHECKING FOR LOW LIQUIDITY POOLS")
print("=" * 100)
print()

low_liq_count = 0
for pool in pools:
    if pool.reserve_usd < 100:  # Less than $100 TVL
        low_liq_count += 1
        if low_liq_count <= 10:  # Show first 10
            print(f'{pool.token0_symbol}/{pool.token1_symbol} on {pool.dex_name}')
            print(f'  TVL: ${pool.reserve_usd:,.2f}')
            print(f'  Reserve0: {pool.reserve0:.10f}')
            print(f'  Reserve1: {pool.reserve1:.10f}')
            print()

print(f'Total pools with TVL < $100: {low_liq_count}')
print()

# Show distribution of TVL
print("=" * 100)
print("TVL DISTRIBUTION")
print("=" * 100)
print()

tvl_buckets = {
    'Under $100': 0,
    '$100-$1K': 0,
    '$1K-$10K': 0,
    '$10K-$100K': 0,
    '$100K-$1M': 0,
    'Over $1M': 0
}

for pool in pools:
    tvl = pool.reserve_usd
    if tvl < 100:
        tvl_buckets['Under $100'] += 1
    elif tvl < 1000:
        tvl_buckets['$100-$1K'] += 1
    elif tvl < 10000:
        tvl_buckets['$1K-$10K'] += 1
    elif tvl < 100000:
        tvl_buckets['$10K-$100K'] += 1
    elif tvl < 1000000:
        tvl_buckets['$100K-$1M'] += 1
    else:
        tvl_buckets['Over $1M'] += 1

for bucket, count in tvl_buckets.items():
    pct = (count / len(pools) * 100) if pools else 0
    print(f'{bucket}: {count} pools ({pct:.1f}%)')
