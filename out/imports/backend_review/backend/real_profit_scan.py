#!/usr/bin/env python3
"""
REAL PROFIT SCAN - Check for actual executable arbitrage opportunities
"""

import logging
import time

logging.basicConfig(level=logging.INFO, format='%(message)s')

from arbitrage_engine import get_arbitrage_engine

print('=' * 80)
print('REAL PROFIT SCAN - LIVE MARKET')
print('=' * 80)

engine = get_arbitrage_engine()

# Wait for pools to load
print('\n⏳ Loading market data...')
timeout = 120
start = time.time()
while engine.pools_loading and (time.time() - start) < timeout:
    time.sleep(3)
    if int(time.time() - start) % 15 == 0:
        print(f'   Still loading... ({int(time.time() - start)}s elapsed)')

if engine.pools_loading:
    print('❌ Timeout - pools still loading')
    exit(1)

pools_with_tvl = sum(1 for p in engine.pools.values() if p.reserve_usd > 10000)
print(f'✅ Loaded {len(engine.pools)} pools ({pools_with_tvl} with TVL > $10k)')

# Scan for REAL profitable spreads
print(f'\n🔍 Scanning for PROFITABLE spreads...')
print(f'   Min profit: ${engine.min_profit_usd}')
print(f'   Loan size: $10,000')
print(f'   Max comparisons: 2,000')

start_scan = time.time()
spreads = engine.scan_for_spreads(loan_amount_usd=10000, max_comparisons=2000)
scan_time = time.time() - start_scan

print(f'\n📊 SCAN RESULTS ({scan_time:.1f}s):')
print(f'   Total spreads found: {len(spreads)}')

executable = [s for s in spreads if s.flash_loan.is_executable]
print(f'   Executable spreads: {len(executable)}')

if len(spreads) > 0:
    print(f'\n💰 TOP 10 OPPORTUNITIES:')
    for i, spread in enumerate(spreads[:10], 1):
        profit = spread.flash_loan.net_profit_usd
        roi = spread.flash_loan.roi_percent
        gas = spread.flash_loan.gas_cost_usd
        fees = spread.flash_loan.total_fees_usd
        slippage = spread.flash_loan.total_slippage_usd
        
        # Calculate if ACTUALLY profitable after gas
        real_profit = profit - gas
        executable_marker = '✅ EXEC' if spread.flash_loan.is_executable else '❌ SKIP'
        
        print(f'\n   {i}. {spread.token_pair}:')
        print(f'      Gross Profit: ${profit:,.2f}')
        print(f'      Gas Cost: ${gas:.4f}')
        print(f'      Real Profit: ${real_profit:,.2f}')
        print(f'      ROI: {roi:.2f}%')
        print(f'      Fees: ${fees:.2f} | Slippage: ${slippage:.2f}')
        print(f'      Status: {executable_marker}')
else:
    print(f'\n❌ NO SPREADS FOUND')
    print(f'\n🔍 DIAGNOSIS:')
    print(f'   - Market is efficient (no arbitrage opportunities)')
    print(f'   - OR: Spreads exist but are < ${engine.min_profit_usd}')
    print(f'   - OR: Gas costs eating all profit')
    
    # Try lowering min profit to see if there are ANY spreads
    print(f'\n📉 Checking for smaller spreads (min $1 profit)...')
    engine.min_profit_usd = 1.0
    small_spreads = engine.scan_for_spreads(loan_amount_usd=5000, max_comparisons=500)
    
    if len(small_spreads) > 0:
        print(f'   Found {len(small_spreads)} spreads with profit > $1')
        best = small_spreads[0]
        print(f'   Best: {best.token_pair} = ${best.flash_loan.net_profit_usd:.2f}')
        print(f'\n💡 INSIGHT: Spreads exist but are too small for ${engine.min_profit_usd} threshold')
    else:
        print(f'   ❌ No spreads found even at $1 minimum')
        print(f'\n💡 INSIGHT: Market is VERY efficient - no arbitrage opportunities exist')

print(f'\n' + '=' * 80)
print('ACTIONABLE NEXT STEPS:')
print('=' * 80)

if len(executable) > 0:
    print(f'\n✅ READY TO EXECUTE {len(executable)} TRADES')
    print(f'   1. Review the opportunities above')
    print(f'   2. Start the live executor: python3 live_executor.py')
    print(f'   3. Monitor Telegram for execution alerts')
elif len(spreads) > 0:
    print(f'\n⚠️  {len(spreads)} spreads found but NOT executable (profit < ${engine.min_profit_usd})')
    print(f'   1. Lower MIN_NET_PROFIT_USD in .env (currently ${engine.min_profit_usd})')
    print(f'   2. OR: Wait for market volatility to create larger spreads')
else:
    print(f'\n❌ NO ARBITRAGE OPPORTUNITIES IN CURRENT MARKET')
    print(f'   1. Keep scanning (market conditions change every block)')
    print(f'   2. Reduce gas costs (optimize contract, bundle transactions)')
    print(f'   3. Increase loan sizes to find bigger spreads')
    print(f'   4. Monitor during high volatility periods')
