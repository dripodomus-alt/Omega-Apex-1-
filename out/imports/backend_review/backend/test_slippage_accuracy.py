#!/usr/bin/env python3
"""
Slippage Sentinel Validation Test
Compares Slippage Sentinel ML predictions against actual swap simulator results
"""

import sys
sys.path.insert(0, '/app/backend')

print("=" * 100)
print("🧠 SLIPPAGE SENTINEL ACCURACY VALIDATION")
print("=" * 100)
print()

from slippage_sentinel import get_slippage_sentinel
from swap_simulator import swap_simulator
from arbitrage_engine import ArbitrageEngine, PoolPrice, Protocol

sentinel = get_slippage_sentinel()
engine = ArbitrageEngine()

# Test scenarios with different pool sizes and trade amounts
test_scenarios = [
    {
        'name': 'Small trade in large pool (low impact)',
        'trade_amount_usd': 5000,
        'pool_liquidity_usd': 2_000_000,
        'reserve0': 1_000_000,  # $1M of token0
        'reserve1': 1_000_000,  # $1M of token1
        'expected_range': (0.1, 0.5),  # Expected 0.1-0.5% slippage
    },
    {
        'name': 'Medium trade in medium pool',
        'trade_amount_usd': 10000,
        'pool_liquidity_usd': 1_000_000,
        'reserve0': 500_000,
        'reserve1': 500_000,
        'expected_range': (0.5, 1.5),  # Expected 0.5-1.5% slippage
    },
    {
        'name': 'Large trade in small pool (high impact)',
        'trade_amount_usd': 50000,
        'pool_liquidity_usd': 200_000,
        'reserve0': 100_000,
        'reserve1': 100_000,
        'expected_range': (5.0, 15.0),  # Expected 5-15% slippage
    },
    {
        'name': 'Tiny trade (negligible impact)',
        'trade_amount_usd': 1000,
        'pool_liquidity_usd': 5_000_000,
        'reserve0': 2_500_000,
        'reserve1': 2_500_000,
        'expected_range': (0.01, 0.1),  # Expected <0.1% slippage
    },
]

print("Testing Slippage Sentinel predictions vs actual swap math:\n")

results = []

for scenario in test_scenarios:
    print("-" * 100)
    print(f"📊 SCENARIO: {scenario['name']}")
    print(f"   Trade: ${scenario['trade_amount_usd']:,} in ${scenario['pool_liquidity_usd']:,} pool")
    print(f"   Utilization: {scenario['trade_amount_usd']/scenario['pool_liquidity_usd']*100:.2f}%")
    print()
    
    # Get Slippage Sentinel prediction
    sentinel_pred = sentinel.predict_slippage(
        trade_amount_usd=scenario['trade_amount_usd'],
        pool_liquidity_usd=scenario['pool_liquidity_usd'],
        volatility_1h=0.01,
        volatility_24h=0.02,
        gas_price_gwei=50,
        spread_bps=30,
        dex_protocol='quickswap_v2',
        pool_data={
            'reserve_in': scenario['reserve0'],
            'reserve_out': scenario['reserve1'],
            'fee_bps': 30
        }
    )
    
    # Calculate actual swap slippage using swap simulator
    # Assume we're swapping token0 for token1
    token0_amount = scenario['trade_amount_usd']  # In USD-normalized units
    
    swap_result = swap_simulator.simulate_swap(
        amount_in=token0_amount,
        reserve_in=scenario['reserve0'],
        reserve_out=scenario['reserve1'],
        fee_bps=30,  # 0.30% fee
        protocol=Protocol.V2
    )
    
    # Swap simulator's slippage
    actual_slippage_pct = swap_result.slippage_pct
    
    # Sentinel's prediction
    predicted_slippage_pct = sentinel_pred['predicted_slippage'] * 100
    
    # Calculate error
    error = abs(predicted_slippage_pct - actual_slippage_pct)
    error_pct = (error / actual_slippage_pct * 100) if actual_slippage_pct > 0 else 0
    
    # Check if prediction is in expected range
    in_expected_range = scenario['expected_range'][0] <= actual_slippage_pct <= scenario['expected_range'][1]
    
    print(f"   🎯 ACTUAL Slippage (Swap Simulator):   {actual_slippage_pct:.4f}%")
    print(f"   🧠 PREDICTED Slippage (ML Sentinel):   {predicted_slippage_pct:.4f}%")
    print(f"   📏 Prediction Error:                   {error:.4f}% ({error_pct:.1f}% relative)")
    print(f"   ✅ Within Expected Range:              {'YES' if in_expected_range else 'NO'} ({scenario['expected_range'][0]:.1f}%-{scenario['expected_range'][1]:.1f}%)")
    print(f"   📊 Confidence Score:                   {sentinel_pred['confidence_score']*100:.1f}%")
    print()
    
    results.append({
        'scenario': scenario['name'],
        'actual': actual_slippage_pct,
        'predicted': predicted_slippage_pct,
        'error': error,
        'error_pct': error_pct,
        'in_range': in_expected_range
    })

# Summary statistics
print("=" * 100)
print("📈 STATISTICAL SUMMARY")
print("=" * 100)
print()

avg_error = sum(r['error'] for r in results) / len(results)
avg_error_pct = sum(r['error_pct'] for r in results) / len(results)
in_range_count = sum(1 for r in results if r['in_range'])

print(f"Average Prediction Error: {avg_error:.4f}% ({avg_error_pct:.1f}% relative)")
print(f"Scenarios in Expected Range: {in_range_count}/{len(results)}")
print()

# Assess if predictions are extreme
extreme_predictions = [r for r in results if r['predicted'] > 10.0]
overpredicting = [r for r in results if r['predicted'] > r['actual'] * 2]

print("🔍 ANALYSIS:")
if len(extreme_predictions) > len(results) / 2:
    print("   ⚠️  WARNING: Slippage Sentinel is predicting EXTREME values (>10%) for majority of scenarios")
    print("      Recommendation: Model needs recalibration - retrain on real execution data")
elif len(overpredicting) > len(results) / 2:
    print("   ⚠️  WARNING: Slippage Sentinel is OVER-PREDICTING (2x+ actual) for majority")
    print("      Recommendation: Reduce volatility multipliers or retrain model")
elif avg_error_pct > 50:
    print("   ⚠️  WARNING: Average prediction error >50% - model accuracy is LOW")
    print("      Recommendation: Retrain on larger dataset with actual execution data")
else:
    print("   ✅ Slippage Sentinel predictions are REASONABLE")
    print("      Model can be used for live trading with periodic recalibration")

print()
print("=" * 100)
print("✅ SLIPPAGE SENTINEL VALIDATION COMPLETE")
print("=" * 100)

# Now test with REAL opportunity from live pools
print("\n" + "=" * 100)
print("🔴 LIVE DATA TEST - Using Real Polygon Mainnet Pools")
print("=" * 100)
print()

# Get actual pools
print("Loading real pools from live data...")
import time
max_wait = 15
waited = 0
while engine.pools_loading and waited < max_wait:
    time.sleep(1)
    waited += 1

if len(engine.pools) > 0:
    print(f"✅ Loaded {len(engine.pools)} real pools\n")
    
    # Find WMATIC/USDC pools (most liquid pair on Polygon)
    wmatic_usdc_pools = []
    for pool in engine.pools.values():
        if (pool.token0_symbol == "WMATIC" and pool.token1_symbol == "USDC") or \
           (pool.token0_symbol == "USDC" and pool.token1_symbol == "WMATIC"):
            if pool.reserve_usd > 100000 and pool.fee > 0:  # >$100k TVL and has fee data
                wmatic_usdc_pools.append(pool)
    
    if len(wmatic_usdc_pools) >= 2:
        pool1, pool2 = wmatic_usdc_pools[0], wmatic_usdc_pools[1]
        
        print(f"Testing with real pools:")
        print(f"  Pool 1: {pool1.dex_name} - TVL: ${pool1.reserve_usd:,.0f} - Fee: {pool1.fee // 100} bps")
        print(f"  Pool 2: {pool2.dex_name} - TVL: ${pool2.reserve_usd:,.0f} - Fee: {pool2.fee // 100} bps")
        print()
        
        # Analyze with $10k loan
        spread = engine.analyze_spread(pool1, pool2, loan_amount_usd=10000)
        
        if spread:
            print("✅ Live opportunity analyzed - check logs above for PROFIT BREAKDOWN")
        else:
            print("❌ No profitable opportunity found (expected with high threshold)")
    else:
        print(f"⚠️  Only found {len(wmatic_usdc_pools)} WMATIC/USDC pools with sufficient data")
else:
    print("⚠️  No pools loaded - skipping live data test")
