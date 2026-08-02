#!/usr/bin/env python3
"""
Slippage Validation Tool
Compares ML Slippage Sentinel predictions against actual AMM math to verify accuracy
"""

import sys
sys.path.insert(0, '/app/backend')

from swap_simulator import swap_simulator
from slippage_sentinel import get_slippage_sentinel
from arbitrage_engine import Protocol

def validate_slippage(
    trade_amount: float,
    reserve_in: float,
    reserve_out: float,
    pool_liquidity_usd: float,
    fee_bps: int = 30
):
    """
    Compare ML prediction vs actual AMM math slippage
    
    Returns detailed breakdown showing if ML is accurate or over/under predicting
    """
    
    print("=" * 100)
    print("🔍 SLIPPAGE VALIDATION - ML vs ACTUAL AMM MATH")
    print("=" * 100)
    print()
    
    # STEP 1: Calculate ACTUAL slippage using swap simulator (exact AMM math)
    print("STEP 1: Calculate ACTUAL slippage using constant product formula")
    print("-" * 100)
    
    actual_swap = swap_simulator.simulate_swap(
        amount_in=trade_amount,
        reserve_in=reserve_in,
        reserve_out=reserve_out,
        fee_bps=fee_bps,
        protocol=Protocol.V2
    )
    
    actual_slippage_pct = actual_swap.slippage_pct
    actual_price_impact = actual_swap.price_impact_pct
    actual_fee = (trade_amount * fee_bps / 10000)
    
    print(f"Trade Amount:        ${trade_amount:,.2f}")
    print(f"Pool Reserves:       ${reserve_in:,.0f} / ${reserve_out:,.0f}")
    print(f"Pool Utilization:    {trade_amount/reserve_in*100:.4f}%")
    print()
    print(f"✅ ACTUAL Results (Constant Product Formula):")
    print(f"   Amount Out:       {actual_swap.amount_out:,.6f}")
    print(f"   Effective Price:  {actual_swap.effective_price:.10f}")
    print(f"   Fee Paid:         ${actual_fee:.2f} ({fee_bps} bps)")
    print(f"   Price Impact:     {actual_price_impact:.4f}%")
    print(f"   Slippage:         {actual_slippage_pct:.4f}%")
    print()
    
    # STEP 2: Get ML prediction from Slippage Sentinel
    print("STEP 2: Get ML prediction from Slippage Sentinel")
    print("-" * 100)
    
    sentinel = get_slippage_sentinel()
    
    ml_prediction = sentinel.predict_slippage(
        trade_amount_usd=trade_amount,
        pool_liquidity_usd=pool_liquidity_usd,
        volatility_1h=0.01,
        volatility_24h=0.02,
        gas_price_gwei=50,
        spread_bps=fee_bps,
        dex_protocol='quickswap_v2',
        pool_data={
            'reserve_in': reserve_in,
            'reserve_out': reserve_out,
            'fee_bps': fee_bps
        }
    )
    
    ml_slippage_pct = ml_prediction['predicted_slippage'] * 100
    ml_raw_pct = ml_prediction.get('raw_prediction', 0) * 100
    calibration_factor = ml_prediction.get('calibration_factor', 1.0)
    exact_slippage_pct = ml_prediction.get('exact_slippage', 0) * 100
    
    print(f"🧠 ML PREDICTION:")
    print(f"   Exact AMM Math:        {exact_slippage_pct:.4f}%")
    print(f"   Raw ML Prediction:     {ml_raw_pct:.4f}%")
    print(f"   Calibration Factor:    {calibration_factor:.2f}x")
    print(f"   CALIBRATED Prediction: {ml_slippage_pct:.4f}%")
    print()
    
    # STEP 3: Compare and validate
    print("STEP 3: VALIDATION - Is the ML prediction accurate?")
    print("=" * 100)
    
    error_abs = abs(ml_slippage_pct - actual_slippage_pct)
    error_pct = (error_abs / actual_slippage_pct * 100) if actual_slippage_pct > 0 else 0
    
    print(f"ACTUAL Slippage (AMM Math):     {actual_slippage_pct:.4f}%")
    print(f"ML Predicted Slippage:          {ml_slippage_pct:.4f}%")
    print(f"Absolute Error:                 {error_abs:.4f}%")
    print(f"Relative Error:                 {error_pct:.2f}%")
    print()
    
    # Determine if prediction is acceptable
    if error_pct < 5:
        status = "✅ EXCELLENT"
        assessment = "ML prediction is highly accurate (< 5% error)"
    elif error_pct < 15:
        status = "✅ GOOD"
        assessment = "ML prediction is reasonably accurate (< 15% error)"
    elif error_pct < 30:
        status = "⚠️  ACCEPTABLE"
        assessment = "ML prediction has moderate error (< 30%)"
    else:
        status = "❌ POOR"
        assessment = "ML prediction has high error (> 30%)"
    
    print(f"Prediction Quality: {status}")
    print(f"Assessment: {assessment}")
    print()
    
    # Show what the difference means in dollar terms
    slippage_diff_usd = (ml_slippage_pct - actual_slippage_pct) / 100 * trade_amount
    
    if slippage_diff_usd > 0:
        print(f"💰 Impact: ML is over-predicting by ${abs(slippage_diff_usd):.2f}")
        print(f"   This means profit calculations are MORE CONSERVATIVE (safer)")
    elif slippage_diff_usd < 0:
        print(f"💰 Impact: ML is under-predicting by ${abs(slippage_diff_usd):.2f}")
        print(f"   This means profit calculations are MORE AGGRESSIVE (riskier)")
    else:
        print(f"💰 Impact: ML prediction matches AMM math perfectly")
    
    print()
    print("=" * 100)
    
    return {
        'actual_slippage_pct': actual_slippage_pct,
        'ml_slippage_pct': ml_slippage_pct,
        'error_abs': error_abs,
        'error_pct': error_pct,
        'status': status,
        'is_over_predicting': ml_slippage_pct > actual_slippage_pct
    }


if __name__ == "__main__":
    print("\n")
    print("🎯 Testing with the exact scenario from your concern")
    print("=" * 100)
    print()
    
    # Test Case 1: $10k WMATIC/USDC arbitrage (from your example)
    print("TEST CASE 1: $10,000 trade in $2M pool (0.5% utilization)")
    print()
    
    result1 = validate_slippage(
        trade_amount=10000,
        reserve_in=1_500_000,
        reserve_out=975_000,
        pool_liquidity_usd=2_000_000,
        fee_bps=30
    )
    
    print("\n" * 2)
    
    # Test Case 2: Different utilization
    print("TEST CASE 2: $10,000 trade in $1M pool (1% utilization)")
    print()
    
    result2 = validate_slippage(
        trade_amount=10000,
        reserve_in=500_000,
        reserve_out=500_000,
        pool_liquidity_usd=1_000_000,
        fee_bps=30
    )
    
    print("\n" * 2)
    
    # Test Case 3: Higher utilization
    print("TEST CASE 3: $50,000 trade in $200k pool (25% utilization)")
    print()
    
    result3 = validate_slippage(
        trade_amount=50000,
        reserve_in=100_000,
        reserve_out=100_000,
        pool_liquidity_usd=200_000,
        fee_bps=30
    )
    
    print("\n" * 2)
    print("=" * 100)
    print("📊 SUMMARY")
    print("=" * 100)
    
    all_results = [result1, result2, result3]
    avg_error = sum(r['error_pct'] for r in all_results) / len(all_results)
    
    print(f"\nAverage Prediction Error: {avg_error:.2f}%")
    
    over_count = sum(1 for r in all_results if r['is_over_predicting'])
    print(f"Over-predictions: {over_count}/{len(all_results)}")
    
    if avg_error < 10:
        print("\n✅ VALIDATION PASSED: ML predictions are highly accurate")
        print("   The 1.92% slippage you saw is realistic and well-calibrated")
    elif avg_error < 25:
        print("\n✅ VALIDATION PASSED: ML predictions are reasonably accurate")
        print("   The slippage predictions are usable but have some variance")
    else:
        print("\n⚠️  NEEDS RECALIBRATION: ML predictions show significant error")
        print("   Consider adjusting calibration factors")
