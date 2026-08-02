"""
Flash Loan Triangular Arbitrage - LINK Example
All steps atomic in single transaction
"""

print("="*80)
print("FLASH LOAN ATOMIC ARBITRAGE: LINK 0.8% SPREAD")
print("="*80)
print()

# Flash loan parameters
flash_loan_amount = 10000  # USDC
flash_loan_fee_pct = 0.0009  # 0.09% Balancer
flash_loan_fee = flash_loan_amount * flash_loan_fee_pct
repay_amount = flash_loan_amount + flash_loan_fee

print("FLASH LOAN:")
print(f"  Borrow: ${flash_loan_amount:,.2f} USDC")
print(f"  Fee: {flash_loan_fee_pct*100:.2f}% = ${flash_loan_fee:.2f}")
print(f"  Must repay: ${repay_amount:,.2f} by end of transaction")
print()

print("="*80)
print("ATOMIC TRANSACTION (All in 1 block)")
print("="*80)
print()

# Step 1: USDC → WETH
step1_fee = flash_loan_amount * 0.003
step1_weth = flash_loan_amount - step1_fee

print("STEP 1: Swap USDC → WETH")
print(f"  Trade: ${flash_loan_amount:,.2f} USDC")
print(f"  DEX fee (0.3%): ${step1_fee:.2f}")
print(f"  Receive: ${step1_weth:,.2f} WETH")
print()

# Step 2: WETH → LINK (at cheaper price)
link_price_weth_pool = 8.79
step2_fee = step1_weth * 0.003
step2_weth_after_fee = step1_weth - step2_fee
link_received = step2_weth_after_fee / link_price_weth_pool

print("STEP 2: Buy LINK in WETH pool (cheaper)")
print(f"  Trade: ${step1_weth:,.2f} WETH")
print(f"  DEX fee (0.3%): ${step2_fee:.2f}")
print(f"  After fee: ${step2_weth_after_fee:,.2f}")
print(f"  Price: ${link_price_weth_pool:.2f} per LINK")
print(f"  Receive: {link_received:,.4f} LINK")
print()

# Step 3: LINK → USDC (at higher price)
link_price_usdc_pool = 8.86
step3_gross_usdc = link_received * link_price_usdc_pool
step3_fee = step3_gross_usdc * 0.003
usdc_received = step3_gross_usdc - step3_fee

print("STEP 3: Sell LINK in USDC pool (higher)")
print(f"  Trade: {link_received:,.4f} LINK")
print(f"  Price: ${link_price_usdc_pool:.2f} per LINK")
print(f"  Gross: ${step3_gross_usdc:,.2f} USDC")
print(f"  DEX fee (0.3%): ${step3_fee:.2f}")
print(f"  Receive: ${usdc_received:,.2f} USDC")
print()

# Step 4: Repay flash loan
print("="*80)
print("REPAYMENT CHECK")
print("="*80)
print()

print(f"You have: ${usdc_received:,.2f} USDC")
print(f"Must repay: ${repay_amount:,.2f} USDC")
print()

if usdc_received >= repay_amount:
    profit = usdc_received - repay_amount
    roi = (profit / flash_loan_amount) * 100
    print(f"✅ CAN REPAY!")
    print(f"   Profit after loan: ${profit:,.2f}")
    print(f"   ROI: {roi:.3f}%")
    print(f"   Transaction SUCCEEDS")
else:
    shortfall = repay_amount - usdc_received
    print(f"❌ CANNOT REPAY!")
    print(f"   Shortfall: ${shortfall:,.2f}")
    print(f"   Transaction REVERTS")
    print(f"   Loss: Only gas (~$0.50)")

print()

# Full breakdown
print("="*80)
print("FULL COST BREAKDOWN")
print("="*80)
print()

total_dex_fees = step1_fee + step2_fee + step3_fee
gross_profit = usdc_received - flash_loan_amount
net_profit = usdc_received - repay_amount

print(f"Flash loan borrowed: ${flash_loan_amount:,.2f}")
print(f"Spread captured: {link_price_usdc_pool - link_price_weth_pool:.2f} × {link_received:.2f} = ${(link_price_usdc_pool - link_price_weth_pool) * link_received:.2f}")
print()
print(f"Costs:")
print(f"  DEX fees (3 swaps): ${total_dex_fees:.2f}")
print(f"  Flash loan fee: ${flash_loan_fee:.2f}")
print(f"  Total costs: ${total_dex_fees + flash_loan_fee:.2f}")
print()
print(f"Gross profit (before loan fee): ${gross_profit:+,.2f}")
print(f"Net profit (after all costs): ${net_profit:+,.2f}")
print()

# Now with realistic slippage
print("="*80)
print("WITH REALISTIC SLIPPAGE (0.5% per swap)")
print("="*80)
print()

slippage_per_swap = 0.005
total_slippage = flash_loan_amount * slippage_per_swap * 3

print(f"Slippage impact: {slippage_per_swap*100:.1f}% × 3 swaps = ${total_slippage:.2f}")
print()

net_with_slippage = net_profit - total_slippage

print(f"Net profit (no slippage): ${net_profit:+,.2f}")
print(f"Slippage cost: ${total_slippage:.2f}")
print(f"Net profit (with slippage): ${net_with_slippage:+,.2f}")
print()

if net_with_slippage > 0:
    print(f"✅ PROFITABLE: ${net_with_slippage:,.2f}")
    print(f"   Transaction would SUCCEED")
else:
    print(f"❌ UNPROFITABLE: ${net_with_slippage:,.2f}")
    print(f"   Transaction would REVERT")
    print(f"   Actual loss: ~$0.50 gas only")

print()

# Calculate minimum spread needed
print("="*80)
print("MINIMUM SPREAD NEEDED FOR PROFIT")
print("="*80)
print()

total_costs_usd = total_dex_fees + flash_loan_fee + total_slippage
total_costs_pct = (total_costs_usd / flash_loan_amount) * 100

print(f"Total costs: ${total_costs_usd:.2f} ({total_costs_pct:.2f}%)")
print(f"Current spread: 0.80%")
print()

if total_costs_pct < 0.80:
    print(f"✅ Spread covers costs")
else:
    needed_spread = total_costs_pct
    print(f"❌ Need {needed_spread:.2f}% spread minimum")
    print(f"   Current spread (0.80%) is SHORT by {needed_spread - 0.80:.2f}%")

print()

# Flash loan advantages
print("="*80)
print("FLASH LOAN ADVANTAGES")
print("="*80)
print()
print("1. ✅ ZERO CAPITAL - Borrow everything")
print("2. ✅ RISK-FREE - Transaction reverts if unprofitable")
print("3. ✅ ATOMIC - All swaps in 1 block (no frontrunning)")
print("4. ✅ SCALABLE - Can borrow $1M+ with no collateral")
print("5. ✅ GAS ONLY - Loss limited to ~$0.50 gas if unprofitable")
print()
print("DISADVANTAGES:")
print("1. ❌ Must be profitable AFTER all fees")
print("2. ❌ Flash loan adds 0.09% extra cost")
print("3. ❌ All steps must succeed atomically")
print("4. ❌ Competition from other bots")
