"""
Trace the exact decimal bug in analyze_spread
"""
import json

data = json.load(open('data/pools.json'))
pools = data['pools']

# Find two USDC/MAI pools
usdc_mai_pools = []
for p in pools:
    t0 = p.get('token0_symbol', '')
    t1 = p.get('token1_symbol', '')
    if ('USDC' in t0 or 'USDC' in t1) and ('MAI' in t0 or 'MAI' in t1 or 'a3Fa99' in t0 or 'a3Fa99' in t1):
        usdc_mai_pools.append(p)

if len(usdc_mai_pools) >= 2:
    pool1 = usdc_mai_pools[0]
    pool2 = usdc_mai_pools[1]
    
    print("Pool 1:")
    print(f"  Token0: {pool1['token0_symbol']} ({pool1['token0_decimals']} decimals)")
    print(f"  Token1: {pool1['token1_symbol']} ({pool1['token1_decimals']} decimals)")
    print()
    print("Pool 2:")
    print(f"  Token0: {pool2['token0_symbol']} ({pool2['token0_decimals']} decimals)")
    print(f"  Token1: {pool2['token1_symbol']} ({pool2['token1_decimals']} decimals)")
    print()
    
    # Simulate the bug
    # Assume leg2 outputs 1000 * 10^18 (1000 MAI in raw units)
    final_amount_token0_raw = 1000 * (10 ** 18)
    
    print("Leg 2 output: 1000 MAI")
    print(f"  Raw value: {final_amount_token0_raw}")
    print()
    
    # WRONG: Using buy_pool (pool1) decimals
    wrong_normalized = final_amount_token0_raw / (10 ** pool1['token0_decimals'])
    print(f"WRONG normalization (using pool1.token0_decimals={pool1['token0_decimals']}):")
    print(f"  {final_amount_token0_raw} / 10^{pool1['token0_decimals']} = {wrong_normalized:,.2f}")
    print()
    
    # CORRECT: Should use sell_pool (pool2) decimals for token0
    # But wait - if both pools have same token order, this should be the same!
    correct_normalized = final_amount_token0_raw / (10 ** pool2['token0_decimals'])
    print(f"CORRECT normalization (using pool2.token0_decimals={pool2['token0_decimals']}):")
    print(f"  {final_amount_token0_raw} / 10^{pool2['token0_decimals']} = {correct_normalized:,.2f}")
    print()
    
    # AH! The issue is that final_amount_token0 is actually in token1 units if we swapped token1→token0!
    # We need to check which token we're actually receiving
    print("WAIT - the real issue:")
    print("  Leg 2 swaps token1 → token0")
    print("  So final_amount_token0 is in token0 units")
    print(f"  But token0 for sell_pool might be different than buy_pool!")
    print()
    print("  If buy_pool.token0 = USDC (6 decimals)")
    print("  And sell_pool.token0 = USDC (6 decimals)")
    print("  Then we should use 6 decimals")
    print()
    print("  But if the output is actually MAI (18 decimals)")
    print("  And we divide by 6, we get 10^12 times too much!")
