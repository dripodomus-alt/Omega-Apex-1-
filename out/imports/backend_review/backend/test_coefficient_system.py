#!/usr/bin/env python3
"""
Test Coefficient System End-to-End
Dry run with real pool data (no transactions)
"""

import sys
import logging
import time

sys.path.insert(0, '/app/backend')

from coefficient_arbitrage_engine import (
    get_coefficient_engine,
    CoefficientOpportunity
)
from coefficient_profit_calculator import print_coefficient_breakdown

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)

logger = logging.getLogger(__name__)

print("="*80)
print("APEX_OMEGA COEFFICIENT SYSTEM TEST")
print("Mode: DRY RUN (No Transactions)")
print("="*80)
print()

# Initialize engine
logger.info("Initializing Coefficient Arbitrage Engine...")
engine = get_coefficient_engine()

# Wait for pools to load
while engine.pools_loading:
    logger.info("Waiting for pools to load...")
    time.sleep(2)

logger.info(f"Pools loaded: {len(engine.pools)}")
print()

# Run coefficient scan
logger.info("Running coefficient scan (max 1000 comparisons)...")
opportunities = engine.scan_for_coefficient_opportunities(max_comparisons=1000)

print()
print("="*80)
print(f"COEFFICIENT SCAN RESULTS: {len(opportunities)} OPPORTUNITIES")
print("="*80)
print()

if len(opportunities) == 0:
    print("❌ No profitable opportunities found with current parameters")
    print()
    print("This is expected if:")
    print("  - Spreads are too small (< 1%)")
    print("  - Pools have low liquidity")
    print("  - DEX fees (0.6%) + flash fees (0.09%) exceed spreads")
    print()
    print("Try:")
    print("  - Lowering MIN_NET_PROFIT_USD in .env")
    print("  - Increasing pool discovery (more DEXs)")
    print("  - Waiting for market volatility")
else:
    print(f"Found {len(opportunities)} profitable opportunities!")
    print()
    
    # Show top 5
    print("TOP 5 OPPORTUNITIES:")
    print("-" * 80)
    
    for i, opp in enumerate(opportunities[:5], 1):
        print(f"\n{i}. {opp.token_pair}")
        print(f"   Buy:  {opp.buy_pool.dex_name} @ ${opp.coeff_result.buy_price:.6f}")
        print(f"   Sell: {opp.sell_pool.dex_name} @ ${opp.coeff_result.sell_price:.6f}")
        print(f"   Spread: ${opp.coeff_result.raw_spread_per_token:.6f} per token ({(opp.coeff_result.raw_spread_per_token/opp.coeff_result.buy_price)*100:.3f}%)")
        print(f"   Coefficient: ${opp.coeff_result.coeff:.6f} per token")
        print(f"   Optimal Size: {opp.optimal_token_units:.2f} tokens (${opp.optimal_loan_usd:,.2f})")
        print(f"   Net Profit: ${opp.net_profit_usd:.2f}")
        print(f"   ROI: {opp.roi_percent:.4f}%")
        print(f"   Score: {opp.opportunity_score:.2f}")
    
    # Detailed breakdown of best opportunity
    if len(opportunities) > 0:
        print()
        print("="*80)
        print("DETAILED BREAKDOWN: BEST OPPORTUNITY")
        print("="*80)
        print()
        best = opportunities[0]
        print_coefficient_breakdown(best.coeff_result)
        
        print()
        print("POOL DETAILS:")
        print(f"  Buy Pool:")
        print(f"    DEX: {best.buy_pool.dex_name}")
        print(f"    Address: {best.buy_pool.pool_address}")
        print(f"    TVL: ${best.buy_pool.reserve_usd:,.2f}")
        print(f"    Reserve0: {best.buy_pool.reserve0:,.4f} {best.buy_pool.token0_symbol}")
        print(f"    Reserve1: {best.buy_pool.reserve1:,.4f} {best.buy_pool.token1_symbol}")
        print()
        print(f"  Sell Pool:")
        print(f"    DEX: {best.sell_pool.dex_name}")
        print(f"    Address: {best.sell_pool.pool_address}")
        print(f"    TVL: ${best.sell_pool.reserve_usd:,.2f}")
        print(f"    Reserve0: {best.sell_pool.reserve0:,.4f} {best.sell_pool.token0_symbol}")
        print(f"    Reserve1: {best.sell_pool.reserve1:,.4f} {best.sell_pool.token1_symbol}")

print()
print("="*80)
print("✅ DRY RUN COMPLETE")
print("="*80)
print()
print("Next steps:")
print("  1. Review opportunities above")
print("  2. Run Anvil fork simulation (test_anvil_simulation.py)")
print("  3. Execute live if profitable")
print()
