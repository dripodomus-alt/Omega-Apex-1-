#!/usr/bin/env python3
"""
BPS Conversion Test Suite
Verify all basis points calculations use correct DeFi standard (10,000 divisor)
"""

def test_trading_fee_conversion():
    """Test 30 bps = 0.30%"""
    fee_bps = 30
    fee_decimal = fee_bps / 10000
    fee_percent = fee_decimal * 100
    
    assert fee_decimal == 0.003, f"Expected 0.003, got {fee_decimal}"
    assert fee_percent == 0.30, f"Expected 0.30%, got {fee_percent}%"
    print(f"✅ Trading Fee: {fee_bps} bps = {fee_decimal} = {fee_percent}%")


def test_aave_flash_loan_fee():
    """Test Aave 9 bps = 0.09%"""
    fee_bps = 9
    loan_amount_usd = 10000
    
    fee_usd = loan_amount_usd * (fee_bps / 10000)
    
    assert fee_usd == 9.0, f"Expected $9.00, got ${fee_usd}"
    print(f"✅ Aave Flash Loan: {fee_bps} bps on ${loan_amount_usd:,} = ${fee_usd:.2f}")


def test_balancer_flash_loan_fee():
    """Test Balancer 0 bps = 0%"""
    fee_bps = 0
    loan_amount_usd = 10000
    
    fee_usd = loan_amount_usd * (fee_bps / 10000)
    
    assert fee_usd == 0.0, f"Expected $0.00, got ${fee_usd}"
    print(f"✅ Balancer Flash Loan: {fee_bps} bps on ${loan_amount_usd:,} = ${fee_usd:.2f} (FREE)")


def test_ask_bid_spread():
    """Test ask/bid price calculation with 30 bps fee"""
    spot_price = 0.50  # WMATIC/USDC
    fee_bps = 30
    
    # Ask (buy price) - pay MORE
    fee_multiplier = (10000 + fee_bps) / 10000
    ask_price = spot_price * fee_multiplier
    
    # Bid (sell price) - receive LESS
    fee_divisor = (10000 - fee_bps) / 10000
    bid_price = spot_price * fee_divisor
    
    assert fee_multiplier == 1.003, f"Expected 1.003, got {fee_multiplier}"
    assert fee_divisor == 0.997, f"Expected 0.997, got {fee_divisor}"
    assert ask_price == 0.5015, f"Expected 0.5015, got {ask_price}"
    assert bid_price == 0.4985, f"Expected 0.4985, got {bid_price}"
    
    spread = ask_price - bid_price
    spread_bps = (spread / spot_price) * 10000
    
    assert abs(spread - 0.003) < 0.0001, f"Expected 0.003 spread, got {spread}"
    assert abs(spread_bps - 60) < 0.1, f"Expected 60 bps spread, got {spread_bps}"
    
    print(f"✅ Ask/Bid Spread:")
    print(f"   Spot: ${spot_price:.4f} | Fee: {fee_bps} bps")
    print(f"   Ask: ${ask_price:.4f} (buy price, +{(ask_price/spot_price - 1)*100:.2f}%)")
    print(f"   Bid: ${bid_price:.4f} (sell price, {(bid_price/spot_price - 1)*100:.2f}%)")
    print(f"   Spread: ${spread:.4f} ({spread_bps:.1f} bps = {spread_bps/100:.2f}%)")


def test_minimum_profit_threshold():
    """Test 15 bps minimum profit = 0.15%"""
    min_profit_bps = 15
    min_profit_percent = min_profit_bps / 100
    
    # On $10,000 trade
    trade_size_usd = 10000
    min_profit_usd = trade_size_usd * (min_profit_bps / 10000)
    
    assert min_profit_percent == 0.15, f"Expected 0.15%, got {min_profit_percent}%"
    assert min_profit_usd == 15.0, f"Expected $15.00, got ${min_profit_usd}"
    
    print(f"✅ Minimum Profit: {min_profit_bps} bps = {min_profit_percent}% = ${min_profit_usd:.2f} on ${trade_size_usd:,}")


def test_slippage_tolerance():
    """Test 100 bps slippage = 1%"""
    expected_output = 1000  # USDC
    slippage_bps = 100
    
    min_acceptable = expected_output * (10000 - slippage_bps) / 10000
    
    assert min_acceptable == 990.0, f"Expected 990, got {min_acceptable}"
    
    slippage_percent = slippage_bps / 100
    assert slippage_percent == 1.0, f"Expected 1%, got {slippage_percent}%"
    
    print(f"✅ Slippage Tolerance: {slippage_bps} bps = {slippage_percent}%")
    print(f"   Expected: {expected_output} USDC | Min Acceptable: {min_acceptable} USDC")


def test_complete_arbitrage_scenario():
    """Test complete arbitrage P&L with all fees"""
    loan_amount_usd = 10000
    pool_a_fee_bps = 30
    pool_b_fee_bps = 30
    aave_fee_bps = 9
    gas_cost_usd = 0.02
    
    # Simulate perfect spread (no slippage for simplicity)
    raw_spread_bps = 100  # 1% raw spread
    gross_profit_usd = loan_amount_usd * (raw_spread_bps / 10000)
    
    # Calculate all costs
    pool_a_fee_usd = loan_amount_usd * (pool_a_fee_bps / 10000)
    pool_b_fee_usd = loan_amount_usd * (pool_b_fee_bps / 10000)
    flash_fee_usd = loan_amount_usd * (aave_fee_bps / 10000)
    
    total_costs = pool_a_fee_usd + pool_b_fee_usd + flash_fee_usd + gas_cost_usd
    net_profit_usd = gross_profit_usd - total_costs
    roi_percent = (net_profit_usd / loan_amount_usd) * 100
    
    print(f"✅ Complete Arbitrage Scenario:")
    print(f"   Loan: ${loan_amount_usd:,}")
    print(f"   Raw Spread: {raw_spread_bps} bps = {raw_spread_bps/100}%")
    print(f"   Gross Profit: ${gross_profit_usd:.2f}")
    print(f"   ")
    print(f"   Costs Breakdown:")
    print(f"   - Pool A Fee ({pool_a_fee_bps} bps): ${pool_a_fee_usd:.2f}")
    print(f"   - Pool B Fee ({pool_b_fee_bps} bps): ${pool_b_fee_usd:.2f}")
    print(f"   - Flash Loan Fee ({aave_fee_bps} bps): ${flash_fee_usd:.2f}")
    print(f"   - Gas Cost: ${gas_cost_usd:.2f}")
    print(f"   - Total Costs: ${total_costs:.2f}")
    print(f"   ")
    print(f"   Net Profit: ${net_profit_usd:.2f} ({roi_percent:.3f}% ROI)")
    
    assert abs(gross_profit_usd - 100.0) < 0.01, f"Expected $100 gross, got ${gross_profit_usd}"
    assert abs(pool_a_fee_usd - 30.0) < 0.01, f"Expected $30 Pool A fee, got ${pool_a_fee_usd}"
    assert abs(pool_b_fee_usd - 30.0) < 0.01, f"Expected $30 Pool B fee, got ${pool_b_fee_usd}"
    assert abs(flash_fee_usd - 9.0) < 0.01, f"Expected $9 flash fee, got ${flash_fee_usd}"
    assert abs(net_profit_usd - 30.98) < 0.01, f"Expected $30.98 net, got ${net_profit_usd}"


if __name__ == "__main__":
    print("=" * 70)
    print("BASIS POINTS (BPS) CONVERSION TEST SUITE")
    print("DeFi Standard: 1 bps = 0.01% (divisor = 10,000)")
    print("=" * 70)
    print()
    
    test_trading_fee_conversion()
    print()
    
    test_aave_flash_loan_fee()
    print()
    
    test_balancer_flash_loan_fee()
    print()
    
    test_ask_bid_spread()
    print()
    
    test_minimum_profit_threshold()
    print()
    
    test_slippage_tolerance()
    print()
    
    test_complete_arbitrage_scenario()
    print()
    
    print("=" * 70)
    print("✅ ALL TESTS PASSED - BPS CONVERSIONS VERIFIED")
    print("=" * 70)
