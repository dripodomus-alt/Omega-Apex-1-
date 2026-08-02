"""
PROFIT PER STRIKE BREAKDOWN
What happens in ONE dual-phase execution
"""

print("="*80)
print("💰 DUAL-PHASE PROFIT BREAKDOWN (Scenario 3)")
print("="*80)
print()

# ============================================================================
# INITIAL MARKET STATE (Before anything happens)
# ============================================================================
print("📊 INITIAL MARKET STATE:")
print("-" * 80)
print("  Buy Pool:  $1.00 per token (Liquidity: $3,000,000)")
print("  Sell Pool: $1.20 per token (Liquidity: $3,000,000)")
print("  Raw Spread: 20% ($0.20 per token)")
print()
print("  💡 This is a MASSIVE arbitrage opportunity!")
print()

# ============================================================================
# TRANSACTION 1: C1 AGGRESSOR FIRES
# ============================================================================
print("="*80)
print("⚡ TRANSACTION 1: C1 AGGRESSOR")
print("="*80)
print()

c1_loan = 150_000
c1_profit = 22_699

print(f"Time: 10:00:00.001")
print()
print(f"Step 1: Request Balancer Flash Loan")
print(f"  Amount: ${c1_loan:,}")
print(f"  Fee: $0 (Balancer is FREE!)")
print()
print(f"Step 2: Execute Swap 1 (BUY)")
print(f"  Buy at cheap pool: $1.00")
print(f"  Amount: ${c1_loan:,}")
print(f"  Price impact: +4.5% (pushes price up)")
print(f"  New price: $1.045")
print()
print(f"Step 3: Execute Swap 2 (SELL)")
print(f"  Sell at expensive pool: $1.20")
print(f"  Price impact: -4.8% (pushes price down)")
print(f"  New price: $1.142")
print()
print(f"Step 4: Repay Flash Loan")
print(f"  Borrowed: ${c1_loan:,}")
print(f"  Repay: ${c1_loan:,} (0% fee)")
print(f"  Profit: ${c1_profit:,} 💰")
print()
print(f"⏱️  Time elapsed: 3.2 seconds (1 blockchain tx)")
print()

# ============================================================================
# MARKET STATE AFTER C1 (3 seconds later)
# ============================================================================
print("="*80)
print("📊 MARKET STATE AFTER C1 (10:00:03)")
print("="*80)
print()
print("  Buy Pool:  $1.045 (was $1.00) ↑ +4.5%")
print("  Sell Pool: $1.142 (was $1.20) ↓ -4.8%")
print("  New Spread: 9.3% (was 20%)")
print()
print("  💡 C1's trade moved the market!")
print("     Spread compressed from 20% → 9.3%")
print("     But 9.3% is STILL profitable!")
print()

# ============================================================================
# C2 SURGEON OBSERVES
# ============================================================================
print("="*80)
print("🧠 C2 SURGEON OBSERVES (10:00:03.100)")
print("="*80)
print()
print("  C2 Analysis:")
print("    • Original spread: 20%")
print("    • Current spread: 9.3%")
print("    • C1's impact: 9.3% compression")
print()
print("  C2 Decision Matrix:")
print("    MIRROR:     Score: $11,250 ✅")
print("    REVERSE:    Score: $2,100")
print("    DO NOTHING: Score: -$0.01")
print()
print("  🏆 WINNER: MIRROR")
print("     Reasoning: Spread still exists! Echo C1's path.")
print()

# ============================================================================
# TRANSACTION 2: C2 SURGEON FIRES
# ============================================================================
print("="*80)
print("⚡ TRANSACTION 2: C2 SURGEON (MIRROR)")
print("="*80)
print()

c2_capital = 150_000
c2_profit = 15_563

print(f"Time: 10:00:04.000")
print()
print(f"Step 1: Execute Swap 1 (BUY)")
print(f"  Buy at $1.045 (the NEW price)")
print(f"  Amount: ${c2_capital:,}")
print(f"  Price impact: +3.2%")
print(f"  New price: $1.078")
print()
print(f"Step 2: Execute Swap 2 (SELL)")
print(f"  Sell at $1.142 (the NEW price)")
print(f"  Price impact: -3.4%")
print(f"  New price: $1.103")
print()
print(f"Step 3: Net Calculation")
print(f"  Gross: ${c2_capital * 0.093:,.0f} (9.3% spread)")
print(f"  Costs: ${c2_capital * 0.093 - c2_profit:,.0f} (fees + slippage)")
print(f"  Profit: ${c2_profit:,} 💰")
print()
print(f"⏱️  Time elapsed: 3.1 seconds (1 blockchain tx)")
print()

# ============================================================================
# FINAL MARKET STATE
# ============================================================================
print("="*80)
print("📊 FINAL MARKET STATE (10:00:07)")
print("="*80)
print()
print("  Buy Pool:  $1.078 (was $1.00) ↑ +7.8%")
print("  Sell Pool: $1.103 (was $1.20) ↓ -8.1%")
print("  Final Spread: 2.3% (was 20%)")
print()
print("  💡 After C1 + C2, the spread is nearly closed")
print("     No more arbitrage left in this pair")
print()

# ============================================================================
# TOTAL PROFIT BREAKDOWN
# ============================================================================
print("="*80)
print("💰 TOTAL PROFIT PER STRIKE")
print("="*80)
print()

total_capital = c1_loan + c2_capital
total_profit = c1_profit + c2_profit
roi = (total_profit / total_capital) * 100

print(f"  TRANSACTION 1 (C1):  ${c1_profit:>10,} profit")
print(f"  TRANSACTION 2 (C2):  ${c2_profit:>10,} profit")
print(f"  ──────────────────────────────────")
print(f"  TOTAL PER STRIKE:    ${total_profit:>10,} 💰")
print()
print(f"  Capital Used:  ${total_capital:,}")
print(f"  ROI:           {roi:.2f}%")
print(f"  Time:          ~7 seconds (2 transactions)")
print()

# ============================================================================
# COMPARISON: SINGLE TRADE VS DUAL PHASE
# ============================================================================
print("="*80)
print("📊 COMPARISON: SINGLE TRADE vs DUAL-PHASE")
print("="*80)
print()

single_trade_profit = 22_699  # Just C1 alone
dual_phase_profit = 38_262

improvement = ((dual_phase_profit - single_trade_profit) / single_trade_profit) * 100

print("  Option 1: SINGLE TRADE (C1 only)")
print(f"    Profit: ${single_trade_profit:,}")
print()
print("  Option 2: DUAL-PHASE (C1 + C2)")
print(f"    Profit: ${dual_phase_profit:,}")
print()
print(f"  🚀 Improvement: +${dual_phase_profit - single_trade_profit:,} ({improvement:.1f}% more)")
print()

# ============================================================================
# FREQUENCY & REALITY CHECK
# ============================================================================
print("="*80)
print("⚠️  REALITY CHECK")
print("="*80)
print()
print("❓ How often does this happen?")
print()
print("  20% spreads are RARE:")
print("    • Occur during:")
print("      - Major news events")
print("      - Token launches")
print("      - Flash crashes")
print("      - Low liquidity periods")
print()
print("  More realistic spreads:")
print("    • 0.5% - 2%:  Common (hundreds per day)")
print("    • 2% - 5%:    Occasional (dozens per day)")
print("    • 5% - 10%:   Rare (few per day)")
print("    • 10%+:       Very rare (few per week)")
print()
print("  Typical profits:")
print("    • Small spread (1%):   $500 - $2,000 per strike")
print("    • Medium spread (3%):  $2,000 - $8,000 per strike")
print("    • Large spread (10%):  $15,000 - $50,000 per strike")
print()

# ============================================================================
# EXECUTION SPEED
# ============================================================================
print("="*80)
print("⚡ EXECUTION SPEED")
print("="*80)
print()
print("  How fast must you execute?")
print()
print("  Timeline:")
print("    00:00.000 - Opportunity detected")
print("    00:00.100 - C1 transaction submitted")
print("    00:03.200 - C1 transaction confirmed ✅")
print("    00:03.300 - C2 observes new state")
print("    00:03.400 - C2 transaction submitted")
print("    00:06.500 - C2 transaction confirmed ✅")
print()
print("  Total execution: ~6.5 seconds")
print()
print("  ⚠️  Competition:")
print("    • Other MEV bots scanning same pools")
print("    • First to execute wins")
print("    • Need <100ms detection → submission")
print()

# ============================================================================
# SUMMARY
# ============================================================================
print("="*80)
print("📝 SUMMARY")
print("="*80)
print()
print("✅ YES - $38,262 is profit PER STRIKE")
print()
print("  'Strike' = 1 complete execution of C1 + C2")
print("  'Strike' = 2 blockchain transactions")
print("  'Strike' = ~7 seconds total")
print()
print("  This specific example:")
print("    • Initial spread: 20% (extreme!)")
print("    • Capital: $300k total ($150k C1 + $150k C2)")
print("    • Profit: $38,262")
print("    • ROI: 12.75%")
print()
print("  Real-world expectations:")
print("    • Most spreads: 0.5% - 3%")
print("    • Typical profit: $500 - $5,000 per strike")
print("    • Frequency: Dozens of opportunities per day")
print("    • Competition: HIGH (many MEV bots)")
print()
print("="*80)
print("The silence strikes once, profits, and vanishes. 🎯")
print("="*80)
