"""
PROFITABLE DUAL-PHASE EXECUTION
Shows C1 → C2 with realistic profitable scenarios
"""

import sys
sys.path.insert(0, '/app/backend')

from dual_phase_execution import (
    MarketState,
    execute_dual_phase_arbitrage
)

print("="*80)
print("💰 PROFITABLE DUAL-PHASE SCENARIOS")
print("="*80)
print()

# ========================================================================
# SCENARIO 1: Small trade, Large spread, Deep liquidity
# ========================================================================
print("🎯 SCENARIO 1: Ideal Conditions (Small C1, Large Spread)")
print()

scenario1 = MarketState(
    buy_pool_price=1.00,
    sell_pool_price=1.15,      # 15% spread (large!)
    buy_pool_liquidity=5_000_000,   # Very deep
    sell_pool_liquidity=5_000_000,
    timestamp="10:00:00"
)

result1 = execute_dual_phase_arbitrage(
    scenario1,
    c1_max_loan_usd=100_000,   # Smaller trade = less impact
    c2_capital_usd=100_000
)

print()
print()
print("─" * 80)
print()

# ========================================================================
# SCENARIO 2: C1 creates REBALANCING opportunity for C2
# ========================================================================
print("🎯 SCENARIO 2: C1 Creates Rebalancing Opportunity")
print()

scenario2 = MarketState(
    buy_pool_price=1.00,
    sell_pool_price=1.12,      # 12% spread
    buy_pool_liquidity=1_000_000,  # Medium liquidity
    sell_pool_liquidity=1_000_000,
    timestamp="11:00:00"
)

result2 = execute_dual_phase_arbitrage(
    scenario2,
    c1_max_loan_usd=80_000,    # 8% utilization
    c2_capital_usd=60_000
)

print()
print()
print("─" * 80)
print()

# ========================================================================
# SCENARIO 3: Extreme spread, C2 MIRRORS
# ========================================================================
print("🎯 SCENARIO 3: Extreme Spread (20%) - C2 Mirrors")
print()

scenario3 = MarketState(
    buy_pool_price=1.00,
    sell_pool_price=1.20,      # 20% spread!
    buy_pool_liquidity=3_000_000,
    sell_pool_liquidity=3_000_000,
    timestamp="12:00:00"
)

result3 = execute_dual_phase_arbitrage(
    scenario3,
    c1_max_loan_usd=150_000,
    c2_capital_usd=150_000
)

print()
print()

# ========================================================================
# FINAL SUMMARY
# ========================================================================
print("="*80)
print("📊 PROFITABILITY SUMMARY")
print("="*80)
print()

scenarios = [
    ("Scenario 1 (Small/Large/Deep)", result1),
    ("Scenario 2 (Medium/Medium/Medium)", result2),
    ("Scenario 3 (Medium/Extreme/Deep)", result3)
]

for name, result in scenarios:
    c1_profit = result['c1_result'].net_profit_usd
    c2_profit = result['c2_decision'].expected_net_usd if result['c2_decision'].strategy != "DO_NOTHING" else 0
    total = result['total_profit_usd']
    
    status = "✅ PROFIT" if total > 0 else "❌ LOSS"
    
    print(f"{name:40}")
    print(f"   C1: ${c1_profit:>10,.2f} | C2 ({result['c2_decision'].strategy:12}): ${c2_profit:>10,.2f} | Total: ${total:>10,.2f} {status}")
    print()

print("="*80)
print("🎯 KEY INSIGHTS:")
print("="*80)
print()
print("✅ For C2 to find opportunity:")
print("   1. C1 must be PROFITABLE first (positive spread > costs)")
print("   2. C1's impact should be MODERATE (3-8% price move)")
print("   3. Spread must be LARGE ENOUGH for C2 to harvest remainder")
print()
print("📊 MIRROR wins when:")
print("   • C1's impact is SMALL (<5%)")
print("   • Original spread is LARGE (>10%)")
print("   • Spread STILL EXISTS after C1")
print()
print("🔄 REVERSE wins when:")
print("   • C1's impact is MODERATE (5-10%)")
print("   • Pools are MEDIUM liquidity")
print("   • Mean reversion is expected")
print()
print("👻 DO NOTHING wins when:")
print("   • C1 CLOSES the spread entirely")
print("   • Both MIRROR and REVERSE are unprofitable")
print()
print("="*80)
