"""
LINK Triangular Arbitrage Analysis
0.8% spread between LINK/WETH and LINK/USDC pools
"""

print("="*80)
print("LINK TRIANGULAR ARBITRAGE: 0.8% SPREAD ANALYSIS")
print("="*80)
print()

# Given data
link_price_weth_pool = 8.79  # LINK price in WETH pool (in USD equivalent)
link_price_usdc_pool = 8.86  # LINK price in USDC pool
spread_pct = ((link_price_usdc_pool - link_price_weth_pool) / link_price_weth_pool) * 100

print("GIVEN:")
print(f"  LINK/WETH pool: ${link_price_weth_pool:.2f} per LINK")
print(f"  LINK/USDC pool: ${link_price_usdc_pool:.2f} per LINK")
print(f"  Apparent spread: {spread_pct:.2f}%")
print()

# Starting capital
capital_usdc = 10000
dex_fee = 0.003  # 0.3% per swap

print("="*80)
print("ARBITRAGE ROUTE: USDC → WETH → LINK → USDC")
print("="*80)
print()

# Step 1: USDC → WETH
print("STEP 1: Swap USDC → WETH")
step1_fee = capital_usdc * dex_fee
step1_weth_usd_value = capital_usdc - step1_fee
print(f"  Start: ${capital_usdc:,.2f} USDC")
print(f"  Fee (0.3%): ${step1_fee:,.2f}")
print(f"  Receive: ${step1_weth_usd_value:,.2f} worth of WETH")
print()

# Step 2: WETH → LINK (buy at cheaper pool)
print("STEP 2: Buy LINK in WETH pool at $8.79")
step2_fee = step1_weth_usd_value * dex_fee
step2_after_fee = step1_weth_usd_value - step2_fee
link_received = step2_after_fee / link_price_weth_pool
print(f"  Trade: ${step1_weth_usd_value:,.2f} WETH")
print(f"  Fee (0.3%): ${step2_fee:,.2f}")
print(f"  After fee: ${step2_after_fee:,.2f}")
print(f"  Receive: {link_received:,.2f} LINK")
print()

# Step 3: LINK → USDC (sell at higher pool)
print("STEP 3: Sell LINK in USDC pool at $8.86")
step3_gross = link_received * link_price_usdc_pool
step3_fee = step3_gross * dex_fee
step3_usdc_received = step3_gross - step3_fee
print(f"  Sell: {link_received:,.2f} LINK")
print(f"  Gross: ${step3_gross:,.2f} USDC")
print(f"  Fee (0.3%): ${step3_fee:,.2f}")
print(f"  Receive: ${step3_usdc_received:,.2f} USDC")
print()

# Final result
gross_profit = step3_usdc_received - capital_usdc
total_fees = step1_fee + step2_fee + step3_fee

print("="*80)
print("RESULT (without slippage)")
print("="*80)
print(f"  Started with: ${capital_usdc:,.2f}")
print(f"  Ended with: ${step3_usdc_received:,.2f}")
print(f"  Gross profit: ${gross_profit:+,.2f}")
print(f"  Total fees paid: ${total_fees:,.2f}")
print()

if gross_profit > 0:
    roi = (gross_profit / capital_usdc) * 100
    print(f"✅ PROFITABLE: {roi:.3f}% ROI (before slippage)")
else:
    loss_pct = (gross_profit / capital_usdc) * 100
    print(f"❌ LOSS: {loss_pct:.3f}% (before slippage)")

print()

# Now add realistic slippage
print("="*80)
print("WITH REALISTIC SLIPPAGE")
print("="*80)
print()

# Assume 0.5% slippage per swap (conservative for $10k trades)
slippage_per_swap = 0.005
total_slippage_impact = capital_usdc * slippage_per_swap * 3  # 3 swaps

print(f"  Slippage per swap: {slippage_per_swap*100:.1f}%")
print(f"  Total slippage (3 swaps): ${total_slippage_impact:,.2f}")
print()

net_profit = gross_profit - total_slippage_impact
print(f"  Gross profit: ${gross_profit:+,.2f}")
print(f"  - Slippage: ${total_slippage_impact:,.2f}")
print(f"  = Net profit: ${net_profit:+,.2f}")
print()

if net_profit > 0:
    roi = (net_profit / capital_usdc) * 100
    print(f"✅ PROFITABLE: {roi:.3f}% ROI")
else:
    loss_pct = (net_profit / capital_usdc) * 100
    print(f"❌ LOSS: {loss_pct:.3f}%")

print()

# Break-even analysis
print("="*80)
print("BREAK-EVEN ANALYSIS")
print("="*80)
print()

total_costs_pct = (total_fees + total_slippage_impact) / capital_usdc * 100
min_spread_needed = total_costs_pct

print(f"  Total costs: {total_costs_pct:.2f}%")
print(f"  Current spread: {spread_pct:.2f}%")
print(f"  Minimum spread needed: {min_spread_needed:.2f}%")
print()

if spread_pct > min_spread_needed:
    print(f"✅ Spread covers costs by {spread_pct - min_spread_needed:.2f}%")
else:
    print(f"❌ Spread SHORT by {min_spread_needed - spread_pct:.2f}%")

print()

# Summary
print("="*80)
print("KEY INSIGHTS")
print("="*80)
print()
print("1. This is TRIANGULAR ARBITRAGE (3 swaps), not simple DEX-to-DEX")
print("2. You need to convert: USDC → WETH → LINK → USDC")
print("3. Each swap costs 0.3% fee = 0.9% total fees")
print("4. Each swap has slippage ≈ 0.5% = 1.5% total slippage")
print("5. Total costs ≈ 2.4% vs 0.8% spread")
print()
print("CONCLUSION:")
print("  The 0.8% spread is REAL")
print("  But 3 swaps cost ~2.4% in fees + slippage")
print("  Net result: ~1.6% LOSS ❌")
print()
print("To profit from this, you'd need:")
print(f"  - Spread ≥ {min_spread_needed:.1f}%")
print("  - OR route optimization (direct LINK/WETH ↔ LINK/USDC pools)")
print("  - OR much deeper liquidity (lower slippage)")
