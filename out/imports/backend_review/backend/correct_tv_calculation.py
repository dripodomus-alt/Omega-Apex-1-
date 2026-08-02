#!/usr/bin/env python3
"""
CRITICAL CORRECTION: Each Leg Has Its Own TV (Trading Volume)

TV is NOT constant across both legs!
- TV1 (Leg 1) = Flash loan amount
- TV2 (Leg 2) = Output from Leg 1 (DIFFERENT!)
"""

print("=" * 100)
print("🚨 CRITICAL INSIGHT: TV CHANGES BETWEEN LEGS")
print("=" * 100)
print()

# Initial setup
flash_loan = 10000
buy_price = 0.6400
sell_price = 0.6500

print("SCENARIO:")
print(f"  Flash Loan: ${flash_loan:,}")
print(f"  Buy Price:  ${buy_price}")
print(f"  Sell Price: ${sell_price}")
print()

print("=" * 100)
print("❌ WRONG ASSUMPTION: Using Same TV for Both Legs")
print("=" * 100)
print()

print("INCORRECT CALCULATION:")
print(f"  TV = ${flash_loan:,} (constant for everything)")
print()
print(f"  Leg 1 Fee:      0.30% × ${flash_loan:,} = ${flash_loan * 0.003:,.2f}")
print(f"  Leg 1 Slippage: 0.96% × ${flash_loan:,} = ${flash_loan * 0.0096:,.2f}")
print(f"  Leg 2 Fee:      0.30% × ${flash_loan:,} = ${flash_loan * 0.003:,.2f}")
print(f"  Leg 2 Slippage: 0.96% × ${flash_loan:,} = ${flash_loan * 0.0096:,.2f}")
print()
print("  Total Costs: $60 + $96 + $60 + $96 = $312")
print()
print("⚠️  THIS IS WRONG! Leg 2 doesn't operate on $10,000!")
print()

print("=" * 100)
print("✅ CORRECT: Each Leg Has Its Own TV")
print("=" * 100)
print()

print("STEP-BY-STEP CALCULATION:")
print()

# LEG 1
tv1 = flash_loan
print(f"━━━ LEG 1: BUY ━━━")
print(f"TV1 (Input to Leg 1) = ${tv1:,.2f}")
print()

# Calculate Leg 1 costs
leg1_fee = tv1 * 0.0030
leg1_slippage = tv1 * 0.0096
leg1_gross_output = tv1 / buy_price * buy_price  # Simplified
leg1_net_output = tv1 - leg1_fee - leg1_slippage

print(f"  Fee (0.30% of TV1):      0.30% × ${tv1:,.2f} = ${leg1_fee:,.2f}")
print(f"  Slippage (0.96% of TV1): 0.96% × ${tv1:,.2f} = ${leg1_slippage:,.2f}")
print(f"  Net Output:              ${tv1:,.2f} - ${leg1_fee:,.2f} - ${leg1_slippage:,.2f} = ${leg1_net_output:,.2f}")
print()

# LEG 2
tv2 = leg1_net_output  # ← THIS IS DIFFERENT FROM TV1!
print(f"━━━ LEG 2: SELL ━━━")
print(f"TV2 (Input to Leg 2) = ${tv2:,.2f}  ← DIFFERENT from TV1!")
print()

# Calculate Leg 2 costs based on TV2 (not TV1!)
leg2_gross = tv2 / buy_price * sell_price  # Convert through tokens
leg2_fee = leg2_gross * 0.0030
leg2_slippage = leg2_gross * 0.0096
leg2_net_output = leg2_gross - leg2_fee - leg2_slippage

print(f"  Gross output (sell):     ${leg2_gross:,.2f}")
print(f"  Fee (0.30% of output):   0.30% × ${leg2_gross:,.2f} = ${leg2_fee:,.2f}")
print(f"  Slippage (0.96% of out): 0.96% × ${leg2_gross:,.2f} = ${leg2_slippage:,.2f}")
print(f"  Net Output:              ${leg2_gross:,.2f} - ${leg2_fee:,.2f} - ${leg2_slippage:,.2f} = ${leg2_net_output:,.2f}")
print()

# FINAL
flash_fee = flash_loan * 0.0009
net_profit = leg2_net_output - flash_loan - flash_fee

print("━━━ FINAL ACCOUNTING ━━━")
print(f"  Returned:       ${leg2_net_output:,.2f}")
print(f"  Repay loan:     ${flash_loan:,.2f}")
print(f"  Flash fee:      ${flash_fee:,.2f}")
print(f"  ─────────────────────────────")
print(f"  NET PROFIT:     ${net_profit:,.2f}")
print()

print("=" * 100)
print("📊 COMPARISON: Wrong vs Correct")
print("=" * 100)
print()

# Wrong way (constant TV)
wrong_leg2_fee = flash_loan * 0.003
wrong_leg2_slippage = flash_loan * 0.0096
wrong_total_costs = leg1_fee + leg1_slippage + wrong_leg2_fee + wrong_leg2_slippage

# Correct way (changing TV)
correct_total_costs = leg1_fee + leg1_slippage + leg2_fee + leg2_slippage

print(f"WRONG (constant TV = ${flash_loan:,}):")
print(f"  Leg 1: ${leg1_fee:,.2f} + ${leg1_slippage:,.2f} = ${leg1_fee + leg1_slippage:,.2f}")
print(f"  Leg 2: ${wrong_leg2_fee:,.2f} + ${wrong_leg2_slippage:,.2f} = ${wrong_leg2_fee + wrong_leg2_slippage:,.2f}")
print(f"  Total: ${wrong_total_costs:,.2f}")
print()

print(f"CORRECT (TV1 = ${tv1:,.2f}, TV2 = ${tv2:,.2f}):")
print(f"  Leg 1: ${leg1_fee:,.2f} + ${leg1_slippage:,.2f} = ${leg1_fee + leg1_slippage:,.2f}")
print(f"  Leg 2: ${leg2_fee:,.2f} + ${leg2_slippage:,.2f} = ${leg2_fee + leg2_slippage:,.2f}")
print(f"  Total: ${correct_total_costs:,.2f}")
print()

difference = abs(wrong_total_costs - correct_total_costs)
print(f"Difference: ${difference:,.2f}")
print()

print("=" * 100)
print("🎯 KEY INSIGHT")
print("=" * 100)
print()
print("TV (Trading Volume) is NOT constant!")
print()
print("  TV1 (Leg 1 input) = Flash loan amount")
print("  TV2 (Leg 2 input) = Leg 1 output (after fees/slippage)")
print()
print("  TV2 < TV1 because Leg 1 costs reduce the amount!")
print()
print("Each leg's costs are calculated based on THAT leg's actual volume:")
print(f"  ✅ Leg 1: 0.30% of ${tv1:,.2f} = ${leg1_fee:,.2f}")
print(f"  ✅ Leg 2: 0.30% of ${leg2_gross:,.2f} = ${leg2_fee:,.2f} ← Different base!")
print()
print("=" * 100)
