#!/usr/bin/env python3
"""
USD-Based Profit Calculation Demonstration
Shows why we MUST use USD amounts, not percentages
"""

print("=" * 100)
print("💰 WHY WE CAN'T SUBTRACT PERCENTAGES DIRECTLY")
print("=" * 100)
print()

# Example scenario
loan_usd = 10000
buy_price = 0.6400
sell_price = 0.6500

print("SCENARIO:")
print(f"  Flash Loan: ${loan_usd:,}")
print(f"  Buy Price:  ${buy_price}")
print(f"  Sell Price: ${sell_price}")
print()

# Calculate raw spread percentage
raw_spread_pct = ((sell_price - buy_price) / buy_price) * 100
print(f"Raw Price Spread: {raw_spread_pct:.4f}%")
print()

print("=" * 100)
print("❌ WRONG WAY (Subtracting Percentages)")
print("=" * 100)
print()

# Wrong calculation
dex_fee_pct = 0.60  # 30 bps × 2
slippage_pct = 1.92  # ML prediction
flash_fee_pct = 0.09  # Aave

wrong_net_pct = raw_spread_pct - dex_fee_pct - slippage_pct - flash_fee_pct
wrong_profit_usd = loan_usd * wrong_net_pct / 100

print(f"Raw Spread:    {raw_spread_pct:.4f}%")
print(f"DEX Fees:     -{dex_fee_pct:.4f}%")
print(f"Slippage:     -{slippage_pct:.4f}%")
print(f"Flash Fee:    -{flash_fee_pct:.4f}%")
print(f"─────────────────────────")
print(f"Net (WRONG):   {wrong_net_pct:.4f}%")
print(f"Profit (WRONG): ${wrong_profit_usd:.2f}")
print()
print("⚠️  THIS IS WRONG because each % has a different base!")
print()

print("=" * 100)
print("✅ CORRECT WAY (USD Flow Calculation)")
print("=" * 100)
print()

# Correct calculation - step by step in USD
print("STEP-BY-STEP USD FLOW:")
print()

# Start
amount_usd = loan_usd
print(f"1️⃣  Start with flash loan:     ${amount_usd:,.2f}")
print()

# Leg 1: Buy tokens
tokens_bought = amount_usd / buy_price
leg1_fee_usd = amount_usd * 0.0030  # 30 bps
leg1_slippage_usd = amount_usd * 0.0096  # 0.96% (example)
amount_after_leg1_usd = (amount_usd - leg1_fee_usd - leg1_slippage_usd) / buy_price * buy_price  # Convert through tokens

print(f"2️⃣  LEG 1 - BUY {tokens_bought:,.2f} tokens @ ${buy_price}")
print(f"    Input:                     ${amount_usd:,.2f}")
print(f"    Fee (30 bps):             -${leg1_fee_usd:.2f}")
print(f"    Slippage (0.96%):         -${leg1_slippage_usd:.2f}")
print(f"    Net tokens:                {(amount_usd - leg1_fee_usd - leg1_slippage_usd) / buy_price:,.2f}")
print(f"    Value:                     ${amount_usd - leg1_fee_usd - leg1_slippage_usd:,.2f}")
print()

# Leg 2: Sell tokens
amount_before_leg2 = amount_usd - leg1_fee_usd - leg1_slippage_usd
tokens_to_sell = amount_before_leg2 / buy_price
leg2_gross_usd = tokens_to_sell * sell_price
leg2_fee_usd = leg2_gross_usd * 0.0030  # 30 bps on output
leg2_slippage_usd = leg2_gross_usd * 0.0096  # 0.96%
amount_after_leg2_usd = leg2_gross_usd - leg2_fee_usd - leg2_slippage_usd

print(f"3️⃣  LEG 2 - SELL {tokens_to_sell:,.2f} tokens @ ${sell_price}")
print(f"    Gross output:              ${leg2_gross_usd:,.2f}")
print(f"    Fee (30 bps):             -${leg2_fee_usd:.2f}")
print(f"    Slippage (0.96%):         -${leg2_slippage_usd:.2f}")
print(f"    Net output:                ${amount_after_leg2_usd:,.2f}")
print()

# Final calculation
flash_fee_usd = loan_usd * 0.0009  # 0.09% Aave fee
amount_to_repay = loan_usd + flash_fee_usd
net_profit_usd = amount_after_leg2_usd - amount_to_repay

print(f"4️⃣  FINAL ACCOUNTING:")
print(f"    Returned:                  ${amount_after_leg2_usd:,.2f}")
print(f"    Repay loan:               -${loan_usd:,.2f}")
print(f"    Flash fee (0.09%):        -${flash_fee_usd:.2f}")
print(f"    ─────────────────────────────")
print(f"    NET PROFIT:                ${net_profit_usd:.2f}")
print(f"    ROI:                       {(net_profit_usd / loan_usd * 100):.4f}%")
print()

print("=" * 100)
print("📊 COMPARISON")
print("=" * 100)
print()
print(f"Wrong method (% subtraction):  ${wrong_profit_usd:.2f}")
print(f"Correct method (USD flow):     ${net_profit_usd:.2f}")
print(f"Difference:                    ${abs(wrong_profit_usd - net_profit_usd):.2f}")
print()
print("The USD flow method is ACCURATE because:")
print("  ✅ Each step uses the actual USD amount at that stage")
print("  ✅ Fees are calculated on their correct bases")
print("  ✅ Leg2 fees/slippage use Leg1 output, not original loan")
print("  ✅ No mixing of percentages with different denominators")
print()
print("=" * 100)
