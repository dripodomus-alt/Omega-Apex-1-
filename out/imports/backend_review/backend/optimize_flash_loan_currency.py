"""
Flash Loan Route Optimization
Compare borrowing USDC vs WETH for LINK arbitrage
"""

print("="*80)
print("FLASH LOAN ROUTE OPTIMIZATION: USDC vs WETH")
print("="*80)
print()

# Given prices
link_price_weth_pool = 8.79  # LINK/WETH: $8.79 per LINK (cheaper)
link_price_usdc_pool = 8.86  # LINK/USDC: $8.86 per LINK (higher)
spread_pct = ((link_price_usdc_pool - link_price_weth_pool) / link_price_weth_pool) * 100

loan_amount_usd = 10000
dex_fee = 0.003  # 0.3%
flash_loan_fee = 0.0009  # 0.09%
slippage_per_swap = 0.005  # 0.5%

print(f"Opportunity:")
print(f"  LINK/WETH pool: ${link_price_weth_pool:.2f} (cheaper)")
print(f"  LINK/USDC pool: ${link_price_usdc_pool:.2f} (higher)")
print(f"  Spread: {spread_pct:.2f}%")
print()

print("="*80)
print("ROUTE A: BORROW USDC")
print("="*80)
print()

# Route A: Start USDC
print("Path: USDC → WETH → LINK → USDC")
print()

# Borrow
routeA_borrow = loan_amount_usd
routeA_flash_fee = routeA_borrow * flash_loan_fee
routeA_must_repay = routeA_borrow + routeA_flash_fee

print(f"1. Borrow: ${routeA_borrow:,.2f} USDC")
print(f"   Flash fee: ${routeA_flash_fee:.2f}")
print(f"   Must repay: ${routeA_must_repay:,.2f}")
print()

# Swap 1: USDC → WETH
routeA_swap1_fee = routeA_borrow * dex_fee
routeA_swap1_slip = routeA_borrow * slippage_per_swap
routeA_weth = routeA_borrow - routeA_swap1_fee - routeA_swap1_slip

print(f"2. USDC → WETH")
print(f"   DEX fee: ${routeA_swap1_fee:.2f}")
print(f"   Slippage: ${routeA_swap1_slip:.2f}")
print(f"   Get: ${routeA_weth:,.2f} WETH")
print()

# Swap 2: WETH → LINK
routeA_swap2_fee = routeA_weth * dex_fee
routeA_swap2_slip = routeA_weth * slippage_per_swap
routeA_weth_after = routeA_weth - routeA_swap2_fee - routeA_swap2_slip
routeA_link = routeA_weth_after / link_price_weth_pool

print(f"3. WETH → LINK (at ${link_price_weth_pool:.2f})")
print(f"   DEX fee: ${routeA_swap2_fee:.2f}")
print(f"   Slippage: ${routeA_swap2_slip:.2f}")
print(f"   Get: {routeA_link:,.4f} LINK")
print()

# Swap 3: LINK → USDC
routeA_usdc_gross = routeA_link * link_price_usdc_pool
routeA_swap3_fee = routeA_usdc_gross * dex_fee
routeA_swap3_slip = routeA_usdc_gross * slippage_per_swap
routeA_usdc_final = routeA_usdc_gross - routeA_swap3_fee - routeA_swap3_slip

print(f"4. LINK → USDC (at ${link_price_usdc_pool:.2f})")
print(f"   Gross: ${routeA_usdc_gross:,.2f}")
print(f"   DEX fee: ${routeA_swap3_fee:.2f}")
print(f"   Slippage: ${routeA_swap3_slip:.2f}")
print(f"   Get: ${routeA_usdc_final:,.2f} USDC")
print()

# Result
routeA_profit = routeA_usdc_final - routeA_must_repay
routeA_total_fees = routeA_swap1_fee + routeA_swap2_fee + routeA_swap3_fee + routeA_flash_fee
routeA_total_slip = routeA_swap1_slip + routeA_swap2_slip + routeA_swap3_slip

print(f"5. Repay flash loan: ${routeA_must_repay:,.2f}")
print(f"   Have: ${routeA_usdc_final:,.2f}")
print(f"   Profit: ${routeA_profit:+,.2f}")
print()

print(f"Route A Costs:")
print(f"  Total fees: ${routeA_total_fees:.2f}")
print(f"  Total slippage: ${routeA_total_slip:.2f}")
print(f"  Total costs: ${routeA_total_fees + routeA_total_slip:.2f}")
print()

# ============================================================================
print("="*80)
print("ROUTE B: BORROW WETH (YOUR OPTIMIZATION!)")
print("="*80)
print()

print("Path: WETH → LINK → USDC → WETH")
print()

# Borrow WETH
routeB_borrow = loan_amount_usd  # $10k worth of WETH
routeB_flash_fee = routeB_borrow * flash_loan_fee
routeB_must_repay = routeB_borrow + routeB_flash_fee

print(f"1. Borrow: ${routeB_borrow:,.2f} worth of WETH")
print(f"   Flash fee: ${routeB_flash_fee:.2f} (0.09%)")
print(f"   Must repay: ${routeB_must_repay:,.2f} WETH value")
print()

# Swap 1: WETH → LINK (SKIP USDC→WETH!)
routeB_swap1_fee = routeB_borrow * dex_fee
routeB_swap1_slip = routeB_borrow * slippage_per_swap
routeB_weth_after = routeB_borrow - routeB_swap1_fee - routeB_swap1_slip
routeB_link = routeB_weth_after / link_price_weth_pool

print(f"2. WETH → LINK (at ${link_price_weth_pool:.2f})")
print(f"   DEX fee: ${routeB_swap1_fee:.2f}")
print(f"   Slippage: ${routeB_swap1_slip:.2f}")
print(f"   Get: {routeB_link:,.4f} LINK")
print()

# Swap 2: LINK → USDC
routeB_usdc_gross = routeB_link * link_price_usdc_pool
routeB_swap2_fee = routeB_usdc_gross * dex_fee
routeB_swap2_slip = routeB_usdc_gross * slippage_per_swap
routeB_usdc = routeB_usdc_gross - routeB_swap2_fee - routeB_swap2_slip

print(f"3. LINK → USDC (at ${link_price_usdc_pool:.2f})")
print(f"   Gross: ${routeB_usdc_gross:,.2f}")
print(f"   DEX fee: ${routeB_swap2_fee:.2f}")
print(f"   Slippage: ${routeB_swap2_slip:.2f}")
print(f"   Get: ${routeB_usdc:,.2f} USDC")
print()

# Swap 3: USDC → WETH (to repay loan)
routeB_swap3_fee = routeB_usdc * dex_fee
routeB_swap3_slip = routeB_usdc * slippage_per_swap
routeB_weth_final = routeB_usdc - routeB_swap3_fee - routeB_swap3_slip

print(f"4. USDC → WETH (to repay loan)")
print(f"   DEX fee: ${routeB_swap3_fee:.2f}")
print(f"   Slippage: ${routeB_swap3_slip:.2f}")
print(f"   Get: ${routeB_weth_final:,.2f} WETH")
print()

# Result
routeB_profit = routeB_weth_final - routeB_must_repay
routeB_total_fees = routeB_swap1_fee + routeB_swap2_fee + routeB_swap3_fee + routeB_flash_fee
routeB_total_slip = routeB_swap1_slip + routeB_swap2_slip + routeB_swap3_slip

print(f"5. Repay flash loan: ${routeB_must_repay:,.2f} WETH")
print(f"   Have: ${routeB_weth_final:,.2f} WETH")
print(f"   Profit: ${routeB_profit:+,.2f}")
print()

print(f"Route B Costs:")
print(f"  Total fees: ${routeB_total_fees:.2f}")
print(f"  Total slippage: ${routeB_total_slip:.2f}")
print(f"  Total costs: ${routeB_total_fees + routeB_total_slip:.2f}")
print()

# ============================================================================
print("="*80)
print("COMPARISON")
print("="*80)
print()

print(f"{'Metric':<30} {'Route A (USDC)':<20} {'Route B (WETH)':<20} {'Winner'}")
print("-"*80)

swaps_a = 3
swaps_b = 3
print(f"{'Number of swaps':<30} {swaps_a:<20} {swaps_b:<20} {'TIE'}")

print(f"{'Total fees':<30} ${routeA_total_fees:<19.2f} ${routeB_total_fees:<19.2f} ", end="")
if routeB_total_fees < routeA_total_fees:
    savings = routeA_total_fees - routeB_total_fees
    print(f"Route B (saves ${savings:.2f})")
else:
    print("TIE")

print(f"{'Total slippage':<30} ${routeA_total_slip:<19.2f} ${routeB_total_slip:<19.2f} ", end="")
if routeB_total_slip < routeA_total_slip:
    savings = routeA_total_slip - routeB_total_slip
    print(f"Route B (saves ${savings:.2f})")
else:
    print("TIE")

total_costs_a = routeA_total_fees + routeA_total_slip
total_costs_b = routeB_total_fees + routeB_total_slip
print(f"{'Total costs':<30} ${total_costs_a:<19.2f} ${total_costs_b:<19.2f} ", end="")
if routeB_profit > routeA_profit:
    savings = total_costs_a - total_costs_b
    print(f"Route B (saves ${savings:.2f})")
else:
    print("TIE")

print(f"{'Net profit':<30} ${routeA_profit:<19.2f} ${routeB_profit:<19.2f} ", end="")
if routeB_profit > routeA_profit:
    improvement = routeB_profit - routeA_profit
    print(f"✅ Route B (+${improvement:.2f})")
else:
    print("TIE")

print()

# ============================================================================
print("="*80)
print("RECOMMENDATION: DYNAMIC ROUTE SELECTION")
print("="*80)
print()

print("Your system should:")
print()
print("1. ✅ Detect which pools exist (LINK/WETH and LINK/USDC)")
print("2. ✅ Calculate both routes:")
print("   - Route A: Borrow quote currency of HIGHER price pool (USDC)")
print("   - Route B: Borrow quote currency of LOWER price pool (WETH)")
print()
print("3. ✅ Compare total costs for each route")
print()
print("4. ✅ Choose route with LOWER total costs")
print()
print("5. ✅ Execute flash loan in optimal currency")
print()

if abs(routeB_profit - routeA_profit) < 1:
    print("In this case: ROUTES ARE IDENTICAL (both have 3 swaps)")
    print("  → System can choose either")
else:
    print(f"In this case: Route B is BETTER by ${abs(routeB_profit - routeA_profit):.2f}")
    print(f"  → System should borrow WETH")

print()
print("="*80)
print("IMPLEMENTATION")
print("="*80)
print()
print("""
def find_optimal_route(pool_a, pool_b):
    # Calculate both directions
    route_a = calculate_profit(
        borrow_currency=pool_b.quote,  # Borrow from higher price pool
        buy_pool=pool_a,
        sell_pool=pool_b
    )
    
    route_b = calculate_profit(
        borrow_currency=pool_a.quote,  # Borrow from lower price pool
        buy_pool=pool_a,
        sell_pool=pool_b
    )
    
    # Choose better route
    if route_b.net_profit > route_a.net_profit:
        return route_b  # Borrow WETH
    else:
        return route_a  # Borrow USDC

optimal = find_optimal_route(link_weth_pool, link_usdc_pool)
execute_flash_loan(optimal.borrow_currency, optimal.loan_amount)
""")
