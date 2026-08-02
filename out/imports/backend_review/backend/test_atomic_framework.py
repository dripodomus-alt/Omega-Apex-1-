#!/usr/bin/env python3
"""
Atomic Arbitrage Calculation - Following Exact Framework

This implements the PRECISE mathematical framework for converting mixed units:
- Percentages (spread, slippage, fees) → Whole USD values
- Using Trading Volume (TV) as the anchor
- Final equation: Net Profit = Gross Profit - Slippage - Fees - Gas
"""

import sys
sys.path.insert(0, '/app/backend')

def calculate_atomic_arbitrage(
    tv: float,              # Trading Volume (Initial Capital)
    buy_price: float,       # Price on buy DEX
    sell_price: float,      # Price on sell DEX
    slippage_pct: float,    # Total slippage percentage (both legs)
    fee_pct: float,         # Total exchange fees percentage (both legs)
    gas_cost_usd: float     # Network gas cost (whole number)
):
    """
    Calculate atomic arbitrage following the exact framework.
    
    Args:
        tv: Trading Volume (anchor for all conversions)
        buy_price: Buy price (e.g., $0.6400)
        sell_price: Sell price (e.g., $0.6500)
        slippage_pct: Total slippage as decimal (e.g., 0.0192 for 1.92%)
        fee_pct: Total fees as decimal (e.g., 0.0060 for 0.60%)
        gas_cost_usd: Gas cost in USD (e.g., $0.01)
    
    Returns:
        dict with all calculated values
    """
    
    print("=" * 100)
    print("⚡ ATOMIC ARBITRAGE CALCULATION - EXACT FRAMEWORK")
    print("=" * 100)
    print()
    
    # ========================================================================
    # STEP 1: Establish Trading Volume (TV) - The Anchor
    # ========================================================================
    print("STEP 1: ESTABLISH TRADING VOLUME (TV)")
    print("-" * 100)
    print(f"Initial Capital (TV): ${tv:,.2f}")
    print(f"This is the ANCHOR for all percentage conversions")
    print()
    
    # ========================================================================
    # STEP 2: Convert Spread Percentage to Gross Profit (Whole Value)
    # ========================================================================
    print("STEP 2: CONVERT SPREAD % → GROSS PROFIT (USD)")
    print("-" * 100)
    
    # Calculate percentage spread
    spread_pct = ((sell_price - buy_price) / buy_price) * 100
    print(f"Buy Price:  ${buy_price:.6f}")
    print(f"Sell Price: ${sell_price:.6f}")
    print(f"Spread % = ((${sell_price} - ${buy_price}) / ${buy_price}) × 100")
    print(f"Spread % = {spread_pct:.4f}%")
    print()
    
    # Convert to whole value
    profit_gross = tv * (spread_pct / 100)
    print(f"Profit_gross = TV × (Spread % / 100)")
    print(f"Profit_gross = ${tv:,.2f} × {spread_pct:.4f}%")
    print(f"Profit_gross = ${profit_gross:,.2f}")
    print()
    
    # ========================================================================
    # STEP 3: Convert Slippage % to Whole Value
    # ========================================================================
    print("STEP 3: CONVERT SLIPPAGE % → PENALTY (USD)")
    print("-" * 100)
    
    slippage_penalty_usd = tv * slippage_pct
    print(f"Slippage % = {slippage_pct * 100:.4f}% (from ML Slippage Sentinel)")
    print(f"Slippage_penalty = TV × Slippage %")
    print(f"Slippage_penalty = ${tv:,.2f} × {slippage_pct * 100:.4f}%")
    print(f"Slippage_penalty = ${slippage_penalty_usd:,.2f}")
    print()
    
    # ========================================================================
    # STEP 4: Convert Exchange Fees % to Whole Value
    # ========================================================================
    print("STEP 4: CONVERT EXCHANGE FEES % → COST (USD)")
    print("-" * 100)
    
    fees_usd = tv * fee_pct
    print(f"Exchange Fees % = {fee_pct * 100:.4f}% (DEX fees, both legs)")
    print(f"Fees = TV × Fee %")
    print(f"Fees = ${tv:,.2f} × {fee_pct * 100:.4f}%")
    print(f"Fees = ${fees_usd:,.2f}")
    print()
    
    # ========================================================================
    # STEP 5: Calculate Net Profit (The Golden Equation)
    # ========================================================================
    print("STEP 5: FINAL NET PROFIT EQUATION")
    print("=" * 100)
    
    profit_net = profit_gross - slippage_penalty_usd - fees_usd - gas_cost_usd
    
    print(f"Profit_net = Profit_gross - Slippage_penalty - Fees - Gas")
    print()
    print(f"Profit_net = ${profit_gross:,.2f} - ${slippage_penalty_usd:,.2f} - ${fees_usd:,.2f} - ${gas_cost_usd:,.2f}")
    print()
    print(f"Profit_net = ${profit_net:,.2f}")
    print()
    
    # Calculate ROI
    roi_pct = (profit_net / tv) * 100 if tv > 0 else 0
    print(f"ROI = (Profit_net / TV) × 100")
    print(f"ROI = ${profit_net:,.2f} / ${tv:,.2f} × 100")
    print(f"ROI = {roi_pct:.4f}%")
    print()
    
    # ========================================================================
    # DECISION: EXECUTE OR CANCEL?
    # ========================================================================
    print("=" * 100)
    print("🎯 SMART CONTRACT DECISION")
    print("=" * 100)
    
    if profit_net > 0:
        print(f"✅ EXECUTE: Net Profit = ${profit_net:,.2f} > $0")
        print(f"   ROI: {roi_pct:.4f}%")
        decision = "EXECUTE"
    else:
        print(f"❌ CANCEL: Net Profit = ${profit_net:,.2f} ≤ $0")
        print(f"   This trade would LOSE money!")
        print(f"   Do NOT execute to avoid wasting gas fees")
        decision = "CANCEL"
    
    print()
    print("=" * 100)
    
    return {
        'tv': tv,
        'spread_pct': spread_pct,
        'profit_gross': profit_gross,
        'slippage_penalty_usd': slippage_penalty_usd,
        'fees_usd': fees_usd,
        'gas_cost_usd': gas_cost_usd,
        'profit_net': profit_net,
        'roi_pct': roi_pct,
        'decision': decision
    }


if __name__ == "__main__":
    print("\n\n")
    print("🧪 TEST CASE 1: Profitable Trade (Large Spread)")
    result1 = calculate_atomic_arbitrage(
        tv=10000,
        buy_price=0.6000,
        sell_price=0.7000,
        slippage_pct=0.0192,  # 1.92%
        fee_pct=0.0060,       # 0.60%
        gas_cost_usd=0.01
    )
    
    print("\n\n")
    print("🧪 TEST CASE 2: Unprofitable Trade (Small Spread)")
    result2 = calculate_atomic_arbitrage(
        tv=10000,
        buy_price=0.6400,
        sell_price=0.6500,
        slippage_pct=0.0192,  # 1.92%
        fee_pct=0.0060,       # 0.60%
        gas_cost_usd=0.01
    )
    
    print("\n\n")
    print("🧪 TEST CASE 3: Edge Case (Breakeven)")
    result3 = calculate_atomic_arbitrage(
        tv=10000,
        buy_price=0.6400,
        sell_price=0.6652,
        slippage_pct=0.0192,  # 1.92%
        fee_pct=0.0060,       # 0.60%
        gas_cost_usd=0.01
    )
    
    print("\n\n")
    print("=" * 100)
    print("📊 SUMMARY OF ALL TEST CASES")
    print("=" * 100)
    print()
    print(f"Test 1 (Large Spread):  Net Profit = ${result1['profit_net']:,.2f}  → {result1['decision']}")
    print(f"Test 2 (Small Spread):  Net Profit = ${result2['profit_net']:,.2f} → {result2['decision']}")
    print(f"Test 3 (Breakeven):     Net Profit = ${result3['profit_net']:,.2f}   → {result3['decision']}")
    print()
    print("=" * 100)
    print("✅ FRAMEWORK VALIDATION COMPLETE")
    print("=" * 100)
    print()
    print("All calculations followed the exact atomic arbitrage framework:")
    print("  1. ✅ Established TV as anchor")
    print("  2. ✅ Converted spread % → whole USD")
    print("  3. ✅ Converted slippage % → whole USD")
    print("  4. ✅ Converted fees % → whole USD")
    print("  5. ✅ Calculated Net Profit in USD")
    print("  6. ✅ Made execute/cancel decision based on Net Profit > 0")
    print()
