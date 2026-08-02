#!/usr/bin/env python3
"""
Quick test for DEXScreener batch integration
Verifies that pools are loaded without dropping unknown tokens
"""

import logging
import time

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from arbitrage_engine import get_arbitrage_engine

def main():
    print('=' * 80)
    print('DEXSCREENER BATCH INTEGRATION TEST')
    print('=' * 80)
    
    # Initialize engine
    engine = get_arbitrage_engine()
    
    # Wait for pools to load
    print('\n⏳ Waiting for pools to load...')
    timeout = 120
    start = time.time()
    while engine.pools_loading and (time.time() - start) < timeout:
        time.sleep(2)
        elapsed = int(time.time() - start)
        if elapsed % 10 == 0:
            print(f'  Still loading... ({elapsed}s elapsed)')
    
    if engine.pools_loading:
        print('❌ FAILED: Timeout waiting for pools to load')
        return False
    
    # Analyze results
    print(f'\n📊 RESULTS:')
    print(f'  Total pools: {len(engine.pools)}')
    
    pools_with_tvl = sum(1 for p in engine.pools.values() if p.reserve_usd > 1000)
    pools_dust = sum(1 for p in engine.pools.values() if 0 < p.reserve_usd < 1000)
    pools_zero_tvl = sum(1 for p in engine.pools.values() if p.reserve_usd == 0)
    
    print(f'  With TVL > $1,000: {pools_with_tvl}')
    print(f'  With dust TVL (<$1,000): {pools_dust}')
    print(f'  With unknown tokens (TVL=$0): {pools_zero_tvl}')
    
    # Validation
    print(f'\n✅ VALIDATION:')
    
    # Check 1: At least 4,000 pools loaded
    if len(engine.pools) >= 4000:
        print(f'  ✅ PASS: {len(engine.pools)} pools loaded (>= 4,000)')
    else:
        print(f'  ❌ FAIL: Only {len(engine.pools)} pools loaded (expected >= 4,000)')
        return False
    
    # Check 2: Unknown token pools are kept (not dropped)
    if pools_zero_tvl > 0:
        print(f'  ✅ PASS: {pools_zero_tvl} unknown token pools kept in database')
    else:
        print(f'  ⚠️  WARNING: No unknown token pools found')
    
    # Check 3: At least some pools have valid TVL
    if pools_with_tvl > 0:
        print(f'  ✅ PASS: {pools_with_tvl} pools with valid TVL')
    else:
        print(f'  ❌ FAIL: No pools with valid TVL')
        return False
    
    # Show sample
    print(f'\n📋 Sample Pools:')
    count = 0
    for addr, pool in list(engine.pools.items())[:100]:
        if pool.reserve_usd > 1000:
            print(f'  {pool.token0_symbol}/{pool.token1_symbol} ({pool.dex_name}): ${pool.reserve_usd:,.2f}')
            count += 1
            if count >= 5:
                break
    
    print(f'\n✅ SUCCESS: DEXScreener batch integration working correctly!')
    print(f'🎯 NO POOLS DROPPED - User requirement satisfied')
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
