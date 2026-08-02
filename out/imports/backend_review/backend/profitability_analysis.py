"""
PROFITABILITY BREAKEVEN ANALYSIS
What slippage prediction makes trades profitable?
"""

print("="*80)
print("PROFITABILITY BREAKEVEN ANALYSIS")
print("="*80)
print()

# Real scan data
spread_bps = 164  # 1.64% spread from scan
loan_amount_usd = 10000

print("GIVEN (from your scan):")
print(f"  Spread: {spread_bps} bps (1.64%)")
print(f"  Loan amount: ${loan_amount_usd:,}")
print()

# Fixed costs
dex_fee_bps = 30 * 2  # 0.30% × 2 legs
gas_bps = (0.50 / loan_amount_usd) * 10000  # $0.50 gas
flash_fee_bps = 9  # 0.09% Balancer flash loan

fixed_costs_bps = dex_fee_bps + gas_bps + flash_fee_bps

print("FIXED COSTS:")
print(f"  DEX fees (2 legs): {dex_fee_bps} bps")
print(f"  Gas cost: {gas_bps:.2f} bps")
print(f"  Flash loan fee: {flash_fee_bps} bps")
print(f"  Total fixed: {fixed_costs_bps:.2f} bps")
print()

# Calculate max allowable slippage
max_slippage_bps = spread_bps - fixed_costs_bps

print("BREAKEVEN CALCULATION:")
print(f"  Spread: {spread_bps} bps")
print(f"  - Fixed costs: {fixed_costs_bps:.2f} bps")
print(f"  = Max slippage: {max_slippage_bps:.2f} bps")
print()

# Current prediction
current_slippage_bps = 232  # From your scan (2.32% buy slippage)

print("CURRENT STATE:")
print(f"  Current slippage prediction: {current_slippage_bps} bps")
print(f"  Max allowable: {max_slippage_bps:.2f} bps")
print(f"  Over by: {current_slippage_bps - max_slippage_bps:.2f} bps")
print()

# Required adjustment
reduction_factor = max_slippage_bps / current_slippage_bps
reduction_pct = (1 - reduction_factor) * 100

print("REQUIRED ADJUSTMENT:")
print(f"  Need to reduce slippage by: {reduction_pct:.1f}%")
print(f"  New coefficient: {reduction_factor:.3f} (multiply current by this)")
print()

print("="*80)
print("COEFFICIENT CHANGES NEEDED")
print("="*80)
print()

# Current calibration table
calibration_current = {
    "< 0.5%": 0.50,
    "< 1.0%": 0.55,
    "< 2.0%": 0.66,
    "< 5.0%": 0.75,
    "< 10.0%": 0.85,
    "< 25.0%": 0.91,
    ">= 25.0%": 0.95
}

# Calculate new calibration (multiply by reduction_factor)
calibration_new = {k: v * reduction_factor for k, v in calibration_current.items()}

print("CALIBRATION TABLE ADJUSTMENTS:")
print()
print(f"{'Utilization':<15} {'Current':<10} {'New':<10} {'Change'}")
print("-"*50)
for util_range in calibration_current.keys():
    old_val = calibration_current[util_range]
    new_val = calibration_new[util_range]
    change = new_val - old_val
    print(f"{util_range:<15} {old_val:<10.3f} {new_val:<10.3f} {change:+.3f}")

print()
print("="*80)
print("ALTERNATIVE: ML ADJUSTMENT CLAMP")
print("="*80)
print()

# Current: ml_adjustment clamped to [-0.5, +1.0]
# This means slippage can increase by up to 100%

current_clamp_max = 1.0
new_clamp_max = current_clamp_max * reduction_factor - current_clamp_max

print("Current ML adjustment range: -50% to +100%")
print(f"Recommended new range: -50% to {new_clamp_max*100:+.1f}%")
print()

# Calculate what exact_slippage should be
exact_slippage_bps = 195.5  # From earlier calculation
ml_adjustment = 0.40  # Example from earlier
calibration = 0.55  # For 1% utilization

raw_slippage_bps = exact_slippage_bps * (1 + ml_adjustment)
current_final_bps = raw_slippage_bps * calibration

print("EXAMPLE CALCULATION:")
print(f"  exact_slippage: {exact_slippage_bps:.1f} bps")
print(f"  ml_adjustment: +{ml_adjustment*100:.0f}%")
print(f"  raw: {raw_slippage_bps:.1f} bps")
print(f"  calibration (current): {calibration:.3f}")
print(f"  final (current): {current_final_bps:.1f} bps")
print()

new_calibration = calibration * reduction_factor
new_final_bps = raw_slippage_bps * new_calibration

print(f"  calibration (new): {new_calibration:.3f}")
print(f"  final (new): {new_final_bps:.1f} bps ✅")
print()

print("="*80)
print("SUMMARY")
print("="*80)
print()
print(f"To make {spread_bps} bps spread profitable:")
print()
print(f"1. REDUCE all calibration factors by {reduction_pct:.1f}%")
print(f"   Multiply each by {reduction_factor:.3f}")
print()
print(f"2. OR reduce ML adjustment clamp from +100% to {new_clamp_max*100:+.1f}%")
print()
print(f"3. OR reduce exact_slippage calculation by {reduction_pct:.1f}%")
print()
print("RECOMMENDATION:")
print("  Adjust calibration table (easiest, most direct)")
print(f"  Example: 0.55 → {0.55 * reduction_factor:.3f} for 1% utilization")
print()

# Verify
print("="*80)
print("VERIFICATION")
print("="*80)
print()

verified_slippage = new_final_bps
net_profit_bps = spread_bps - verified_slippage - fixed_costs_bps

print(f"Spread: {spread_bps} bps")
print(f"- Slippage (adjusted): {verified_slippage:.1f} bps")
print(f"- Fixed costs: {fixed_costs_bps:.1f} bps")
print(f"= Net profit: {net_profit_bps:.1f} bps")
print()

if net_profit_bps > 0:
    profit_usd = (net_profit_bps / 10000) * loan_amount_usd
    print(f"✅ PROFITABLE: ${profit_usd:.2f} on ${loan_amount_usd:,} loan")
else:
    print(f"❌ Still unprofitable by {abs(net_profit_bps):.1f} bps")
