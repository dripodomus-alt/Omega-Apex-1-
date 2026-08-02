"""
MINIMAL decimal bug test with hardcoded pools
Bypass the slow engine loading
"""

# Test the exact bug scenario
pool1_token0_decimals = 6  # USDC
pool1_token1_decimals = 18  # MAI

pool2_token0_decimals = 6  # USDC  
pool2_token1_decimals = 18  # MAI

# Simulate swap output (raw units)
final_amount_token0 = 1000 * (10 ** 6)  # 1000 USDC (raw: 1,000,000,000)

print("Decimal Normalization Test")
print("=" * 60)
print(f"final_amount_token0 (raw): {final_amount_token0}")
print(f"Pool1 token0_decimals: {pool1_token0_decimals}")
print(f"Pool2 token0_decimals: {pool2_token0_decimals}")
print()

# WRONG: Using buy_pool decimals
wrong_normalized = final_amount_token0 / (10 ** pool1_token0_decimals)
print(f"❌ WRONG (using pool1.token0_decimals={pool1_token0_decimals}):")
print(f"   {final_amount_token0} / 10^{pool1_token0_decimals} = {wrong_normalized:,.2f}")
print()

# CORRECT: Using sell_pool decimals (should be same in this case)
correct_normalized = final_amount_token0 / (10 ** pool2_token0_decimals)
print(f"✅ CORRECT (using pool2.token0_decimals={pool2_token0_decimals}):")
print(f"   {final_amount_token0} / 10^{pool2_token0_decimals} = {correct_normalized:,.2f}")
print()

# Now test with DIFFERENT token ordering (this is the real bug)
print("=" * 60)
print("Test with REVERSED token order:")
print("=" * 60)

# Pool1: USDC (6) / MAI (18)
# Pool2: MAI (18) / USDC (6)  ← REVERSED ORDER

pool1_token0_decimals = 6  # USDC
pool1_token1_decimals = 18  # MAI

pool2_token0_decimals = 18  # MAI  ← Now token0 is MAI!
pool2_token1_decimals = 6  # USDC  ← Now token1 is USDC!

# Swap result: 1000 USDC
# But it's in pool2's token1 position (USDC)
final_amount_token1 = 1000 * (10 ** 6)  # 1000 USDC (raw)

print(f"\nfinal_amount (raw): {final_amount_token1}")
print(f"Pool1 token0_decimals: {pool1_token0_decimals} (USDC)")
print(f"Pool2 token0_decimals: {pool2_token0_decimals} (MAI)")
print(f"Pool2 token1_decimals: {pool2_token1_decimals} (USDC)")
print()

# WRONG: Using pool1.token0_decimals
wrong_normalized = final_amount_token1 / (10 ** pool1_token0_decimals)
print(f"❌ WRONG (using pool1.token0_decimals={pool1_token0_decimals}):")
print(f"   {final_amount_token1} / 10^{pool1_token0_decimals} = {wrong_normalized:,.2f} USDC")
print()

# WRONG ALSO: Using pool2.token0_decimals  
wrong2_normalized = final_amount_token1 / (10 ** pool2_token0_decimals)
print(f"❌ STILL WRONG (using pool2.token0_decimals={pool2_token0_decimals}):")
print(f"   {final_amount_token1} / 10^{pool2_token0_decimals} = {wrong2_normalized:,.10f} USDC")
print(f"   = {wrong2_normalized * 1e12:,.2f} with 10^12 multiplier error!")
print()

# CORRECT: Using pool2.token1_decimals (because it's in token1 position)
correct_normalized = final_amount_token1 / (10 ** pool2_token1_decimals)
print(f"✅ CORRECT (using pool2.token1_decimals={pool2_token1_decimals}):")
print(f"   {final_amount_token1} / 10^{pool2_token1_decimals} = {correct_normalized:,.2f} USDC")
print()

print("=" * 60)
print("CONCLUSION:")
print("The bug happens when pools have DIFFERENT token ordering!")
print("We need to track which token is which, not just pool reference.")
print("=" * 60)
