"""
Test coefficient calculator with LINK arbitrage scenario
"""
import sys
sys.path.insert(0, '/app/backend')

from coefficient_profit_calculator import (
    get_coefficient_calculator,
    print_coefficient_breakdown
)

print("LINK ARBITRAGE: $8.79 (buy) → $8.86 (sell)")
print("Spread: $0.07 per LINK (0.8%)")
print()

calc = get_coefficient_calculator()

# LINK example from optimize_flash_loan_currency.py
result = calc.calculate_optimal_size(
    buy_price=8.79,   # LINK/WETH pool
    sell_price=8.86   # LINK/USDC pool
)

print_coefficient_breakdown(result)

# Calculate equivalent USD loan amount
loan_amount_usd = result.optimal_token_units * result.buy_price
print(f"\n💰 EQUIVALENT FLASHLOAN:")
print(f"   {result.optimal_token_units:.0f} LINK × ${result.buy_price:.2f} = ${loan_amount_usd:,.2f}")
print()

# Compare with old approach ($10k fixed loan)
fixed_loan_usd = 10000
fixed_token_units = fixed_loan_usd / result.buy_price
fixed_profit = (fixed_token_units * result.coeff) - calc.gas_buffer_usd

print("COMPARISON:")
print(f"  Coefficient Approach:")
print(f"    Loan: ${loan_amount_usd:,.2f}")
print(f"    Tokens: {result.optimal_token_units:.0f} LINK")
print(f"    Net Profit: ${result.net_profit_usd:.2f} ✅")
print()
print(f"  Fixed $10k Approach:")
print(f"    Loan: ${fixed_loan_usd:,.2f}")
print(f"    Tokens: {fixed_token_units:.2f} LINK")
print(f"    Net Profit: ${fixed_profit:.2f}")

