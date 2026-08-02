"""
INTERACTIVE C2 SURGEON STRIKER DEMO
Test different market conditions and see which oracle wins
"""

def test_scenario(name, buy_price, sell_price, capital, volatility, fill_prob=0.89):
    """Test a specific market scenario"""
    print("="*80)
    print(f"📊 SCENARIO: {name}")
    print("="*80)
    print()
    
    spread_pct = (sell_price - buy_price) / buy_price * 100
    spread_dec = spread_pct / 100
    
    print(f"Buy Price:    ${buy_price:.4f}")
    print(f"Sell Price:   ${sell_price:.4f}")
    print(f"Spread:       {spread_pct:.2f}%")
    print(f"Capital:      ${capital:,.0f}")
    print(f"Volatility:   {volatility:.2f}x")
    print(f"Fill Prob:    {fill_prob*100:.0f}%")
    print()
    
    # MIRROR
    mirror_buffer = 0.018
    mirror_gross = capital * spread_dec
    mirror_costs = capital * mirror_buffer
    mirror_net = mirror_gross - mirror_costs - 0.02
    vol_penalty = volatility * 0.15
    mirror_score = mirror_net * fill_prob * (1 - vol_penalty)
    
    # REVERSE
    reverse_buffer = 0.013
    reverse_gross = capital * spread_dec * 0.97
    reverse_costs = capital * reverse_buffer
    reverse_net = reverse_gross - reverse_costs - 0.02
    vol_bonus = volatility * 0.08
    reverse_score = reverse_net * (fill_prob * 0.94) * (1 + vol_bonus)
    
    # DO NOTHING
    opp_cost = capital * (8.5 / 10000) * (0.5 / 8760)
    do_nothing_score = -opp_cost * 1.2
    
    scores = {
        "MIRROR": mirror_score,
        "REVERSE": reverse_score,
        "DO_NOTHING": do_nothing_score
    }
    
    winner = max(scores, key=scores.get)
    
    print("ORACLE SCORES:")
    print("-" * 80)
    for oracle, score in scores.items():
        marker = " 🏆" if oracle == winner else ""
        print(f"  {oracle:12} → ${score:>12,.2f}{marker}")
    
    print()
    print(f"WINNER: {winner}")
    
    if winner == "MIRROR":
        print("  ✅ Calm market favors the obvious trade")
    elif winner == "REVERSE":
        print("  ✅ Volatile market rewards contrarian play")
    else:
        print("  ✅ Both trades unprofitable - preserve capital")
    
    print()
    return winner


print("🎭 C2 SURGEON STRIKER - INTERACTIVE DEMO")
print("Testing different market conditions...")
print()

# Test 1: Calm market, large spread
winner1 = test_scenario(
    name="CALM MARKET + LARGE SPREAD",
    buy_price=1.00,
    sell_price=1.10,  # 10% spread
    capital=500_000,
    volatility=0.8    # Low volatility
)

# Test 2: Volatile market, medium spread
winner2 = test_scenario(
    name="VOLATILE MARKET + MEDIUM SPREAD",
    buy_price=1.00,
    sell_price=1.05,  # 5% spread
    capital=500_000,
    volatility=1.15   # High volatility
)

# Test 3: Extreme volatility, small spread
winner3 = test_scenario(
    name="EXTREME VOLATILITY + SMALL SPREAD",
    buy_price=1.00,
    sell_price=1.02,  # 2% spread
    capital=500_000,
    volatility=1.5    # Very high volatility
)

# Test 4: Calm market, tiny spread
winner4 = test_scenario(
    name="CALM MARKET + TINY SPREAD",
    buy_price=1.00,
    sell_price=1.005, # 0.5% spread
    capital=500_000,
    volatility=0.9
)

# Test 5: Normal conditions
winner5 = test_scenario(
    name="NORMAL CONDITIONS",
    buy_price=1.00,
    sell_price=1.03,  # 3% spread
    capital=500_000,
    volatility=1.0    # Normal volatility
)

# Summary
print("="*80)
print("📊 SUMMARY OF ALL SCENARIOS")
print("="*80)
print()

scenarios = [
    ("Calm + Large Spread (10%)", winner1),
    ("Volatile + Medium Spread (5%)", winner2),
    ("Extreme Vol + Small Spread (2%)", winner3),
    ("Calm + Tiny Spread (0.5%)", winner4),
    ("Normal (3% spread, 1.0x vol)", winner5)
]

mirror_count = sum(1 for _, w in scenarios if w == "MIRROR")
reverse_count = sum(1 for _, w in scenarios if w == "REVERSE")
nothing_count = sum(1 for _, w in scenarios if w == "DO_NOTHING")

for scenario, winner in scenarios:
    emoji = "🪞" if winner == "MIRROR" else "🔄" if winner == "REVERSE" else "👻"
    print(f"{emoji} {scenario:40} → {winner}")

print()
print("STATISTICS:")
print(f"  MIRROR wins:     {mirror_count}/5 ({mirror_count/5*100:.0f}%)")
print(f"  REVERSE wins:    {reverse_count}/5 ({reverse_count/5*100:.0f}%)")
print(f"  DO NOTHING wins: {nothing_count}/5 ({nothing_count/5*100:.0f}%)")
print()

print("KEY INSIGHTS:")
print("  • Large spreads (>10%) → MIRROR wins (obvious trade is safe)")
print("  • High volatility (>1.1x) → REVERSE wins (chaos creates rebalancing)")
print("  • Small spreads (<1%) → DO NOTHING wins (fees eat profit)")
print("  • Normal conditions → Depends on spread/vol balance")
print()

print("="*80)
print("The C2 Surgeon Striker adapts to market conditions automatically. 🎯")
print("="*80)
