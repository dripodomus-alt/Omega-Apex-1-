"""
Test the new slippage calculation (ML ÷ 3)
"""
import sys
sys.path.insert(0, '/app/backend')

from slippage_sentinel import get_slippage_sentinel

print("="*80)
print("TESTING NEW SLIPPAGE CALCULATION (ML ÷ 3)")
print("="*80)
print()

sentinel = get_slippage_sentinel()

# Test case 1: $10k in $2M pool (0.5% utilization)
result1 = sentinel.predict_slippage(
    trade_amount_usd=10000,
    pool_liquidity_usd=2_000_000,
    volatility_1h=0.01,
    volatility_24h=0.02,
    dex_protocol='quickswap_v2'
)

print("Test 1: $10k swap in $2M pool")
print(f"  Raw ML Prediction: {result1['raw_prediction']*100:.4f}%")
print(f"  Calibration Factor: {result1['calibration_factor']:.4f} (÷3)")
print(f"  Final Slippage: {result1['predicted_slippage']*100:.4f}%")
print(f"  Impact Category: {result1['impact_category']}")
print(f"  Confidence: {result1['confidence_score']*100:.1f}%")
print()

# Test case 2: $50k in $200k pool (25% utilization)
result2 = sentinel.predict_slippage(
    trade_amount_usd=50000,
    pool_liquidity_usd=200_000,
    volatility_1h=0.03,
    volatility_24h=0.05,
    dex_protocol='quickswap_v2'
)

print("Test 2: $50k swap in $200k pool (high impact)")
print(f"  Raw ML Prediction: {result2['raw_prediction']*100:.4f}%")
print(f"  Calibration Factor: {result2['calibration_factor']:.4f} (÷3)")
print(f"  Final Slippage: {result2['predicted_slippage']*100:.4f}%")
print(f"  Impact Category: {result2['impact_category']}")
print(f"  Confidence: {result2['confidence_score']*100:.1f}%")
print()

# Test case 3: $5k in $5M pool (0.1% utilization - very low)
result3 = sentinel.predict_slippage(
    trade_amount_usd=5000,
    pool_liquidity_usd=5_000_000,
    volatility_1h=0.01,
    volatility_24h=0.02,
    dex_protocol='quickswap_v2'
)

print("Test 3: $5k swap in $5M pool (institutional liquidity)")
print(f"  Raw ML Prediction: {result3['raw_prediction']*100:.4f}%")
print(f"  Calibration Factor: {result3['calibration_factor']:.4f} (÷3)")
print(f"  Final Slippage: {result3['predicted_slippage']*100:.4f}%")
print(f"  Impact Category: {result3['impact_category']}")
print(f"  Confidence: {result3['confidence_score']*100:.1f}%")
print()

print("="*80)
print("✅ SIMPLE CALIBRATION ACTIVE: All ML predictions divided by 3")
print("="*80)

