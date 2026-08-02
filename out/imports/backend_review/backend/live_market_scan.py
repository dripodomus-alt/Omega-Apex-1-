"""
LIVE MARKET SCAN: How many executable spreads exist RIGHT NOW?

Applies:
1. Coefficient pre-filter (coeff > 0)
2. C1 profitability check
3. C2 dual-phase decision logic
4. Realistic constraints (slippage, fees, gas)
"""

import sys
import time
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from coefficient_arbitrage_engine import get_coefficient_engine
from dual_phase_execution import (
    MarketState,
    simulate_c1_market_impact,
    c2_surgeon_decision
)
import logging

logging.basicConfig(level=logging.WARNING)  # Reduce noise

print("="*80)
print("📡 LIVE MARKET SCAN - EXECUTABLE SPREADS")
print("="*80)
print()

# ============================================================================
# STEP 1: Load Coefficient Engine with Real Pool Data
# ============================================================================
print("⏳ Loading pool data from Polygon mainnet...")
print()

engine = get_coefficient_engine()

# Wait for pools to load
start_time = time.time()
while engine.pools_loading and (time.time() - start_time) < 30:
    time.sleep(1)

if engine.pools_loading:
    print("❌ Timeout waiting for pools to load")
    sys.exit(1)

print(f"✅ Loaded {len(engine.pools):,} pools")
print()

# ============================================================================
# STEP 2: Scan with Coefficient Pre-Filter
# ============================================================================
print("="*80)
print("🔍 PHASE 1: COEFFICIENT PRE-FILTER")
print("="*80)
print()
print("Scanning all pairs for positive coefficient...")
print()

opportunities = engine.scan_for_coefficient_opportunities(max_comparisons=5000)

print(f"✅ Found {len(opportunities)} opportunities with coeff > 0")
print()

if len(opportunities) == 0:
    print("❌ No opportunities found with current market conditions")
    print()
    print("Possible reasons:")
    print("  • All spreads < fees (coeff <= 0)")
    print("  • Pool data has decimal normalization issues")
    print("  • Market is highly efficient (no arbitrage)")
    sys.exit(0)

# ============================================================================
# STEP 3: Filter by Realistic Constraints
# ============================================================================
print("="*80)
print("⚙️  PHASE 2: REALISTIC CONSTRAINT FILTERING")
print("="*80)
print()

realistic_opps = []

# Constraints
MIN_COEFFICIENT = 0.0001  # $0.0001 per token minimum (was 0.001)
MAX_COEFFICIENT = 1.0    # $1.00 per token maximum (filter outliers)
MIN_LIQUIDITY = 10_000   # $10k minimum per pool (was 50k)
MAX_POOL_UTILIZATION = 0.20  # Max 20% of pool TVL (was 15%)

print("Applying filters:")
print(f"  • Coefficient: ${MIN_COEFFICIENT:.4f} - ${MAX_COEFFICIENT:.2f}")
print(f"  • Min liquidity: ${MIN_LIQUIDITY:,} per pool")
print(f"  • Max utilization: {MAX_POOL_UTILIZATION*100:.0f}% of pool")
print()

for opp in opportunities:
    coeff = opp.coeff_result.coeff
    
    # Filter outliers (broken decimal data)
    if coeff < MIN_COEFFICIENT or coeff > MAX_COEFFICIENT:
        continue
    
    # Check liquidity
    min_liq = min(opp.buy_pool.reserve_usd, opp.sell_pool.reserve_usd)
    if min_liq < MIN_LIQUIDITY:
        continue
    
    # Check utilization
    utilization = opp.optimal_loan_usd / min_liq
    if utilization > MAX_POOL_UTILIZATION:
        continue
    
    realistic_opps.append(opp)

print(f"✅ {len(realistic_opps)} opportunities passed filters")
print()

# ============================================================================
# STEP 4: Simulate C1 Execution for Top Opportunities
# ============================================================================
print("="*80)
print("🔥 PHASE 3: C1 PROFITABILITY CHECK")
print("="*80)
print()

c1_profitable = []
c1_unprofitable = []

print(f"Testing top {min(len(realistic_opps), 20)} opportunities with C1 simulation...")
print()

for i, opp in enumerate(realistic_opps[:20], 1):
    # Create market state
    state = MarketState(
        buy_pool_price=opp.coeff_result.buy_price,
        sell_pool_price=opp.coeff_result.sell_price,
        buy_pool_liquidity=opp.buy_pool.reserve_usd,
        sell_pool_liquidity=opp.sell_pool.reserve_usd,
        timestamp=f"scan_{i}"
    )
    
    # Simulate C1
    loan_amount = min(opp.optimal_loan_usd, state.buy_pool_liquidity * 0.10)
    c1_result = simulate_c1_market_impact(state, loan_amount)
    
    if c1_result.net_profit_usd > 5.0:  # Min $5 profit
        c1_profitable.append({
            'opp': opp,
            'c1_result': c1_result,
            'state': state
        })
    else:
        c1_unprofitable.append(opp)

print(f"✅ C1 Profitable: {len(c1_profitable)}")
print(f"❌ C1 Unprofitable: {len(c1_unprofitable)}")
print()

# ============================================================================
# STEP 5: Test C2 Decision for Profitable C1 Trades
# ============================================================================
print("="*80)
print("🧠 PHASE 4: C2 DUAL-PHASE DECISION")
print("="*80)
print()

dual_phase_executable = []
c1_only_executable = []

print(f"Testing C2 decision logic for {len(c1_profitable)} C1-profitable trades...")
print()

for item in c1_profitable:
    opp = item['opp']
    c1_result = item['c1_result']
    state = item['state']
    
    # C2 decides
    c2_capital = c1_result.loan_amount_usd * 0.5  # C2 uses 50% of C1's size
    c2_decision = c2_surgeon_decision(state, c1_result, c2_capital)
    
    if c2_decision.strategy != "DO_NOTHING" and c2_decision.expected_net_usd > 0:
        dual_phase_executable.append({
            'opp': opp,
            'c1_result': c1_result,
            'c2_decision': c2_decision,
            'total_profit': c1_result.net_profit_usd + c2_decision.expected_net_usd
        })
    else:
        c1_only_executable.append({
            'opp': opp,
            'c1_result': c1_result,
            'total_profit': c1_result.net_profit_usd
        })

print(f"✅ Dual-Phase Executable: {len(dual_phase_executable)} (C1 + C2 both profit)")
print(f"⚠️  C1-Only Executable: {len(c1_only_executable)} (C2 says DO NOTHING)")
print()

# ============================================================================
# FINAL RESULTS
# ============================================================================
print("="*80)
print("📊 FINAL RESULTS")
print("="*80)
print()

total_executable = len(dual_phase_executable) + len(c1_only_executable)

print(f"Total Pools Scanned:           {len(engine.pools):,}")
print(f"Coefficient Positive:          {len(opportunities):,}")
print(f"Passed Realistic Filters:      {len(realistic_opps):,}")
print(f"C1 Profitable:                 {len(c1_profitable):,}")
print(f"  ├─ Dual-Phase Executable:    {len(dual_phase_executable):,} 🎯")
print(f"  └─ C1-Only Executable:       {len(c1_only_executable):,}")
print(f"────────────────────────────────────────")
print(f"TOTAL EXECUTABLE NOW:          {total_executable:,} ✅")
print()

# ============================================================================
# TOP 5 OPPORTUNITIES
# ============================================================================
if len(dual_phase_executable) > 0:
    print("="*80)
    print("🏆 TOP 5 DUAL-PHASE OPPORTUNITIES")
    print("="*80)
    print()
    
    # Sort by total profit
    sorted_opps = sorted(dual_phase_executable, key=lambda x: x['total_profit'], reverse=True)
    
    for i, item in enumerate(sorted_opps[:5], 1):
        opp = item['opp']
        c1_result = item['c1_result']
        c2_decision = item['c2_decision']
        total = item['total_profit']
        
        print(f"{i}. {opp.token_pair}")
        print(f"   Buy:  {opp.buy_pool.dex_name} @ ${opp.coeff_result.buy_price:.6f}")
        print(f"   Sell: {opp.sell_pool.dex_name} @ ${opp.coeff_result.sell_price:.6f}")
        print(f"   Coefficient: ${opp.coeff_result.coeff:.6f}")
        print(f"   C1 Profit: ${c1_result.net_profit_usd:,.2f}")
        print(f"   C2 ({c2_decision.strategy}): ${c2_decision.expected_net_usd:,.2f}")
        print(f"   TOTAL: ${total:,.2f} 💰")
        print()

elif len(c1_only_executable) > 0:
    print("="*80)
    print("🏆 TOP 5 C1-ONLY OPPORTUNITIES")
    print("="*80)
    print()
    
    sorted_opps = sorted(c1_only_executable, key=lambda x: x['total_profit'], reverse=True)
    
    for i, item in enumerate(sorted_opps[:5], 1):
        opp = item['opp']
        c1_result = item['c1_result']
        
        print(f"{i}. {opp.token_pair}")
        print(f"   Coefficient: ${opp.coeff_result.coeff:.6f}")
        print(f"   C1 Profit: ${c1_result.net_profit_usd:,.2f}")
        print(f"   C2 Decision: DO NOTHING (spread closes)")
        print()

else:
    print("❌ No executable opportunities at this moment")
    print()
    print("Market is currently efficient. Wait for:")
    print("  • Volatility events")
    print("  • Token launches")
    print("  • Liquidity imbalances")
    print()

# ============================================================================
# ANALYSIS
# ============================================================================
print("="*80)
print("📈 MARKET ANALYSIS")
print("="*80)
print()

if total_executable > 0:
    avg_profit = sum(x['total_profit'] for x in dual_phase_executable + c1_only_executable) / total_executable
    
    print(f"Average Profit per Opportunity: ${avg_profit:,.2f}")
    print()
    
    if len(dual_phase_executable) > 0:
        dual_phase_avg = sum(x['total_profit'] for x in dual_phase_executable) / len(dual_phase_executable)
        c1_avg = sum(x['c1_result'].net_profit_usd for x in dual_phase_executable) / len(dual_phase_executable)
        c2_avg = sum(x['c2_decision'].expected_net_usd for x in dual_phase_executable) / len(dual_phase_executable)
        
        print("Dual-Phase Breakdown:")
        print(f"  Avg C1 Profit: ${c1_avg:,.2f}")
        print(f"  Avg C2 Profit: ${c2_avg:,.2f}")
        print(f"  Avg Total:     ${dual_phase_avg:,.2f}")
        print(f"  C2 Adds:       {(c2_avg/c1_avg)*100:.1f}% more profit")
        print()
    
    # Frequency estimate
    opportunities_per_hour = total_executable * 6  # Assuming market refreshes every 10 min
    daily_opportunities = opportunities_per_hour * 24
    
    print("Estimated Frequency:")
    print(f"  Current snapshot: {total_executable} executable")
    print(f"  Per hour (est):   {opportunities_per_hour:.0f}")
    print(f"  Per day (est):    {daily_opportunities:.0f}")
    print()
    
    # Revenue potential
    daily_revenue_low = daily_opportunities * avg_profit * 0.3  # 30% execution rate
    daily_revenue_high = daily_opportunities * avg_profit * 0.7  # 70% execution rate
    
    print("Revenue Potential (if you execute):")
    print(f"  Conservative (30% success): ${daily_revenue_low:,.0f} / day")
    print(f"  Aggressive (70% success):   ${daily_revenue_high:,.0f} / day")
    print()

else:
    print("No executable opportunities currently.")
    print()
    print("This could mean:")
    print("  • Market is very efficient right now")
    print("  • Pool data has issues (decimal normalization)")
    print("  • Filters are too strict")
    print()
    print("Try:")
    print("  • Lowering MIN_NET_PROFIT_USD in .env")
    print("  • Scanning during high volatility periods")
    print("  • Expanding pool discovery to more DEXs")

print()
print("="*80)
print("Scan complete. The silence has observed the market. 🎯")
print("="*80)
