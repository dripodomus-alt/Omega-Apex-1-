"""
What Does "TV as the Anchor" Mean?

TV = Trading Volume = Your Initial Capital = Flash Loan Amount

"Anchor" means: The FIXED BASE NUMBER that all percentage calculations use.
"""

print("=" * 100)
print("🎯 UNDERSTANDING 'TV AS THE ANCHOR'")
print("=" * 100)
print()

print("TV = Trading Volume = Your Flash Loan Amount")
print()
print("In our system:")
print("  TV = $10,000  ← This is the flash loan you're borrowing")
print()

print("=" * 100)
print("WHY DO WE NEED AN ANCHOR?")
print("=" * 100)
print()

print("Problem: A percentage BY ITSELF means NOTHING!")
print()
print("Example:")
print("  'I have a 2% spread' ← Meaningless without context!")
print()
print("  2% of what?")
print("    - 2% of $100 = $2")
print("    - 2% of $10,000 = $200")
print("    - 2% of $1,000,000 = $20,000")
print()
print("The ANCHOR (TV) tells you: 2% of WHAT BASE NUMBER?")
print()

print("=" * 100)
print("EXAMPLE: Converting Percentages Using TV as Anchor")
print("=" * 100)
print()

# Example with TV = $10,000
tv = 10000
spread_pct = 1.56
slippage_pct = 1.92
fee_pct = 0.60

print(f"TV (Anchor) = ${tv:,}")
print()

print("Now we can convert percentages to actual dollar amounts:")
print()

gross_profit = tv * (spread_pct / 100)
print(f"1. Spread: {spread_pct}%")
print(f"   {spread_pct}% of what? → {spread_pct}% of TV (${tv:,})")
print(f"   ${tv:,} × {spread_pct}% = ${gross_profit:,.2f}")
print()

slippage_usd = tv * (slippage_pct / 100)
print(f"2. Slippage: {slippage_pct}%")
print(f"   {slippage_pct}% of what? → {slippage_pct}% of TV (${tv:,})")
print(f"   ${tv:,} × {slippage_pct}% = ${slippage_usd:,.2f}")
print()

fee_usd = tv * (fee_pct / 100)
print(f"3. Fees: {fee_pct}%")
print(f"   {fee_pct}% of what? → {fee_pct}% of TV (${tv:,})")
print(f"   ${tv:,} × {fee_pct}% = ${fee_usd:,.2f}")
print()

print("=" * 100)
print("WITHOUT AN ANCHOR (WRONG!)")
print("=" * 100)
print()

print("If you don't use TV as the anchor:")
print()
print("  Spread:   1.56%  ← 1.56% of WHAT?")
print("  Slippage: 1.92%  ← 1.92% of WHAT?")
print("  Fees:     0.60%  ← 0.60% of WHAT?")
print()
print("  You can't calculate profit because you don't know the BASE!")
print()

print("=" * 100)
print("WITH TV AS ANCHOR (CORRECT!)")
print("=" * 100)
print()

print(f"TV = ${tv:,} ← This is your anchor (base number)")
print()
print(f"  Spread:   1.56% of ${tv:,} = ${gross_profit:,.2f}")
print(f"  Slippage: 1.92% of ${tv:,} = ${slippage_usd:,.2f}")
print(f"  Fees:     0.60% of ${tv:,} = ${fee_usd:,.2f}")
print()
print("  Now you can calculate profit in actual dollars!")
print(f"  Net = ${gross_profit:,.2f} - ${slippage_usd:,.2f} - ${fee_usd:,.2f} = ${gross_profit - slippage_usd - fee_usd:,.2f}")
print()

print("=" * 100)
print("REAL-WORLD ANALOGY")
print("=" * 100)
print()

print("Imagine you're at a store:")
print()
print("  Salesperson: 'This item is 20% off!'")
print("  You: '20% off what price?'")
print()
print("  Without the BASE PRICE (anchor), 20% is meaningless!")
print()
print("  If base price = $100 → 20% off = $20 discount")
print("  If base price = $1000 → 20% off = $200 discount")
print()
print("  The BASE PRICE is the ANCHOR for the percentage.")
print()

print("=" * 100)
print("IN ARBITRAGE TRADING")
print("=" * 100)
print()

print("TV (Trading Volume) = Your flash loan amount = The ANCHOR")
print()
print("  You borrow: $10,000 (this is your TV)")
print("  Spread: 1.56% of $10,000 = $156 gross profit")
print("  Slippage: 1.92% of $10,000 = $192 cost")
print("  Fees: 0.60% of $10,000 = $60 cost")
print()
print("  Net Profit = $156 - $192 - $60 = $-96 (LOSS!)")
print()

print("=" * 100)
print("KEY TAKEAWAY")
print("=" * 100)
print()
print("  'Anchor' = The fixed reference point for all calculations")
print("  'TV' = Trading Volume = Flash loan amount")
print()
print("  Without TV as the anchor:")
print("    ❌ Percentages are meaningless")
print("    ❌ Can't convert to dollars")
print("    ❌ Can't calculate profit")
print()
print("  With TV as the anchor:")
print("    ✅ All percentages reference the same base")
print("    ✅ Can convert everything to dollars")
print("    ✅ Can accurately calculate profit")
print()
print("=" * 100)
