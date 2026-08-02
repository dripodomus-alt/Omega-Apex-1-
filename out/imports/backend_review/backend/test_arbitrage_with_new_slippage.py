"""
Test LINK arbitrage with new slippage (ML ÷ 3)
"""
import sys
sys.path.insert(0, '/app/backend')

from slippage_sentinel import get_slippage_sentinel

print("="*80)
print("LINK ARBITRAGE WITH NEW SLIPPAGE (ML ÷ 3)")
print("="*80)
print()

# LINK arbitrage example
loan_amount_usd = 10000
pool1_tvl = 2_000_000  # LINK/WETH pool
pool2_tvl = 1_800_000  # LINK/USDC pool

sentinel = get_slippage_sentinel()

# Leg 1: Buy LINK with WETH ($10k swap)
leg1_pred = sentinel.predict_slippage(
    trade_amount_usd=loan_amount_usd,
    pool_liquidity_usd=pool1_tvl,
    dex_protocol='quickswap_v2'
)

# Leg 2: Sell LINK for USDC (~$9,920 after leg1)
leg2_amount = loan_amount_usd * (1 - leg1_pred['predicted_slippage'] - 0.003)  # Rough estimate after fees/slip
leg2_pred = sentinel.predict_slippage(
    trade_amount_usd=leg2_amount,
    pool_liquidity_usd=pool2_tvl,
    dex_protocol='quickswap_v2'
)

print("SLIPPAGE CALCULATIONS:")
print("-" * 80)
print(f"Leg 1: ${loan_amount_usd:,.0f} USDC → WETH → LINK")
print(f"  Pool TVL: ${pool1_tvl:,.0f}")
print(f"  Utilization: {leg1_pred['utilization_ratio']*100:.3f}%")
print(f"  Raw ML: {leg1_pred['raw_prediction']*100:.4f}%")
print(f"  Calibrated (÷3): {leg1_pred['predicted_slippage']*100:.4f}%")
print(f"  Cost: ${loan_amount_usd * leg1_pred['predicted_slippage']:.2f}")
print()

print(f"Leg 2: ${leg2_amount:,.0f} LINK → USDC")
print(f"  Pool TVL: ${pool2_tvl:,.0f}")
print(f"  Utilization: {leg2_pred['utilization_ratio']*100:.3f}%")
print(f"  Raw ML: {leg2_pred['raw_prediction']*100:.4f}%")
print(f"  Calibrated (÷3): {leg2_pred['predicted_slippage']*100:.4f}%")
print(f"  Cost: ${leg2_amount * leg2_pred['predicted_slippage']:.2f}")
print()

# Total costs
total_slippage = (loan_amount_usd * leg1_pred['predicted_slippage'] + 
                  leg2_amount * leg2_pred['predicted_slippage'])
dex_fees = (loan_amount_usd + leg2_amount) * 0.003  # 0.3% per swap
flash_fee = loan_amount_usd * 0.0009  # 0.09% Balancer
total_costs = total_slippage + dex_fees + flash_fee

print("COST BREAKDOWN:")
print("-" * 80)
print(f"Slippage (ML ÷ 3): ${total_slippage:.2f}")
print(f"DEX Fees (0.6%):   ${dex_fees:.2f}")
print(f"Flash Fee (0.09%): ${flash_fee:.2f}")
print(f"Total Costs:       ${total_costs:.2f}")
print()

# Profit calculation (0.8% spread example)
spread_pct = 0.008
gross_profit = loan_amount_usd * spread_pct
net_profit = gross_profit - total_costs

print("PROFITABILITY:")
print("-" * 80)
print(f"Spread: {spread_pct*100:.2f}%")
print(f"Gross Profit: ${gross_profit:.2f}")
print(f"Net Profit:   ${net_profit:.2f}")
print()

if net_profit > 0:
    print(f"✅ PROFITABLE! ROI: {(net_profit/loan_amount_usd)*100:.4f}%")
else:
    print(f"❌ UNPROFITABLE (loss: ${abs(net_profit):.2f})")
    print()
    print("Required spread for breakeven:")
    breakeven_spread = total_costs / loan_amount_usd
    print(f"  {breakeven_spread*100:.4f}%")

print()
print("="*80)
print("COMPARISON WITH OLD SLIPPAGE:")
print("="*80)
# Old calibrated slippage was ~0.84% per leg
old_leg1_slip = 0.0084
old_leg2_slip = 0.0082
old_total_slippage = loan_amount_usd * old_leg1_slip + leg2_amount * old_leg2_slip
old_total_costs = old_total_slippage + dex_fees + flash_fee
old_net_profit = gross_profit - old_total_costs

print(f"Old Slippage Cost: ${old_total_slippage:.2f}")
print(f"New Slippage Cost: ${total_slippage:.2f}")
print(f"Savings: ${old_total_slippage - total_slippage:.2f}")
print()
print(f"Old Net Profit: ${old_net_profit:.2f}")
print(f"New Net Profit: ${net_profit:.2f}")
print(f"Improvement: ${net_profit - old_net_profit:.2f}")

