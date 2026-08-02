"""
Debug swap math to find where the trillion-dollar bug is coming from
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from swap_simulator import swap_simulator

# Test with a simple WMATIC/USDC swap
# Assume:
# - reserve0 = 100 WMATIC (raw: 100 * 10^18)
# - reserve1 = 50 USDC (raw: 50 * 10^6)
# - Price: 1 WMATIC = 0.5 USDC
# - Loan: 10 WMATIC (raw: 10 * 10^18)
# - Expected out: ~4.5 USDC (accounting for fees)

reserve0_raw = 100 * (10 ** 18)  # 100 WMATIC
reserve1_raw = 50 * (10 ** 6)    # 50 USDC
amount_in_raw = 10 * (10 ** 18)  # 10 WMATIC

print("Test Swap: WMATIC → USDC")
print("=" * 60)
print(f"Reserve0 (WMATIC): {reserve0_raw / (10**18):.2f} WMATIC ({reserve0_raw} raw)")
print(f"Reserve1 (USDC): {reserve1_raw / (10**6):.2f} USDC ({reserve1_raw} raw)")
print(f"Amount In: {amount_in_raw / (10**18):.2f} WMATIC ({amount_in_raw} raw)")
print()

# Simulate swap
result = swap_simulator.simulate_swap(
    amount_in=amount_in_raw,
    reserve_in=reserve0_raw,
    reserve_out=reserve1_raw,
    fee_bps=30,  # 0.3% fee
    protocol=2  # V2
)

print("Swap Result:")
print(f"  Amount Out (raw): {result.amount_out}")
print(f"  Amount Out (normalized): {result.amount_out / (10**6):.6f} USDC")
print(f"  Fee Paid (raw): {result.fee_paid}")
print(f"  Fee Paid (normalized): {result.fee_paid / (10**18):.6f} WMATIC")
print()

# Calculate price
token0_decimals = 18
token1_decimals = 6

reserve0_normalized = reserve0_raw / (10 ** token0_decimals)
reserve1_normalized = reserve1_raw / (10 ** token1_decimals)

# Price of WMATIC in USDC
wmatic_price_usd = reserve1_normalized / reserve0_normalized
print(f"WMATIC Price: ${wmatic_price_usd:.4f} USD")
print()

# Convert to USD
amount_in_normalized = amount_in_raw / (10 ** token0_decimals)
amount_out_normalized = result.amount_out / (10 ** token1_decimals)

amount_in_usd = amount_in_normalized * wmatic_price_usd
amount_out_usd = amount_out_normalized  # USDC is already USD

print("USD Values:")
print(f"  Amount In: ${amount_in_usd:.2f} USD")
print(f"  Amount Out: ${amount_out_usd:.2f} USD")
print(f"  Profit: ${amount_out_usd - amount_in_usd:.2f} USD")
print()

# Expected: ~$5 input → ~$4.5 output (after 0.3% fee + slippage)
if amount_out_usd > 1000:
    print("❌ BUG DETECTED: Output is absurdly high!")
else:
    print("✅ Math looks correct")
