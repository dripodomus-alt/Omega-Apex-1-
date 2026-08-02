#!/usr/bin/env python3
from arbitrage_engine import get_arbitrage_engine
import time

engine = get_arbitrage_engine()
print('Waiting for pools...')
time.sleep(6)

pools = list(engine.pools.values())
print(f'Total pools: {len(pools)}\n')

# Check TVL calculations
print("Sample Pool TVL Data:")
print("=" * 80)
for pool in pools[:10]:
    print(f'{pool.token0_symbol}/{pool.token1_symbol} on {pool.dex_name}')
    print(f'  Reserve0: {pool.reserve0:.6f}')
    print(f'  Reserve1: {pool.reserve1:.6f}')
    print(f'  TVL (from metadata): ${pool.reserve_usd:,.2f}')
    estimated = pool.reserve1 * 2
    print(f'  Estimated from reserves: ${estimated:,.2f}')
    print()
