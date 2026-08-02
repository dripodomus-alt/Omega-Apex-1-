"""
Debug the actual spreads calculation with real pool data
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
import logging
logging.basicConfig(level=logging.DEBUG)

from arbitrage_engine import get_arbitrage_engine

print("Loading engine...")
engine = get_arbitrage_engine()

print(f"Pools loaded: {len(engine.pools)}")

# Get two pools for the same pair to test
pools_list = list(engine.pools.values())

# Find USDC/MAI pools
usdc_mai_pools = []
for pool in pools_list:
    pair = frozenset([pool.token0.lower(), pool.token1.lower()])
    usdc = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
    mai = "0xa3fa99a148fa48d14ed51d610c367c61876997f1"
    
    if frozenset([usdc, mai]) == pair:
        usdc_mai_pools.append(pool)

print(f"\nFound {len(usdc_mai_pools)} USDC/MAI pools")

if len(usdc_mai_pools) >= 2:
    pool1 = usdc_mai_pools[0]
    pool2 = usdc_mai_pools[1]
    
    print(f"\nPool 1: {pool1.dex_name}")
    print(f"  Address: {pool1.pool_address}")
    print(f"  Token0: {pool1.token0_symbol} ({pool1.token0_decimals} decimals)")
    print(f"  Token1: {pool1.token1_symbol} ({pool1.token1_decimals} decimals)")
    print(f"  Reserve0: {pool1.reserve0 / (10**pool1.token0_decimals):.2f} {pool1.token0_symbol}")
    print(f"  Reserve1: {pool1.reserve1 / (10**pool1.token1_decimals):.2f} {pool1.token1_symbol}")
    
    print(f"\nPool 2: {pool2.dex_name}")
    print(f"  Address: {pool2.pool_address}")
    print(f"  Token0: {pool2.token0_symbol} ({pool2.token0_decimals} decimals)")
    print(f"  Token1: {pool2.token1_symbol} ({pool2.token1_decimals} decimals)")
    print(f"  Reserve0: {pool2.reserve0 / (10**pool2.token0_decimals):.2f} {pool2.token0_symbol}")
    print(f"  Reserve1: {pool2.reserve1 / (10**pool2.token1_decimals):.2f} {pool2.token1_symbol}")
    
    print("\nAnalyzing spread...")
    spread = engine.analyze_spread(pool1, pool2, loan_amount_usd=10000)
    
    if spread:
        print(f"\n✅ Spread found:")
        print(f"  Pair: {spread.token_pair}")
        print(f"  Net Profit: ${spread.flash_loan.net_profit_usd:,.2f}")
        print(f"  ROI: {spread.flash_loan.roi_percent:.2f}%")
        
        if spread.flash_loan.net_profit_usd > 1000:
            print(f"\n❌ BUG DETECTED: Profit is absurdly high!")
            print(f"\nLeg 1:")
            print(f"  In: ${spread.flash_loan.leg1.amount_in_usd:.2f}")
            print(f"  Out: ${spread.flash_loan.leg1.amount_out_usd:.2f}")
            print(f"  Token In Decimals: {spread.flash_loan.leg1.token_in_decimals}")
            print(f"  Token Out Decimals: {spread.flash_loan.leg1.token_out_decimals}")
            
            print(f"\nLeg 2:")
            print(f"  In: ${spread.flash_loan.leg2.amount_in_usd:.2f}")
            print(f"  Out: ${spread.flash_loan.leg2.amount_out_usd:.2f}")
            print(f"  Token In Decimals: {spread.flash_loan.leg2.token_in_decimals}")
            print(f"  Token Out Decimals: {spread.flash_loan.leg2.token_out_decimals}")
        else:
            print(f"\n✅ Math looks correct!")
    else:
        print("\n⚠️  No spread found between these pools")
