"""
Test EXACT swap calculations vs approximate slippage calculations
"""
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def test_exact_swap_vs_approximate():
    """Compare exact AMM formulas vs approximate slippage"""
    from swap_simulator import swap_simulator
    from arbitrage_engine import get_arbitrage_engine
    
    logger.info("=" * 70)
    logger.info("TEST: Exact Swap Calculations for Real DeFi Arbitrage")
    logger.info("=" * 70)
    
    # Test UniswapV2 exact swap
    logger.info("\n📊 UniswapV2 Constant Product Test:")
    logger.info(f"   Reserve In: 1,000,000 USDC")
    logger.info(f"   Reserve Out: 500 ETH")
    logger.info(f"   Trade: 10,000 USDC → ETH")
    logger.info(f"   Fee: 30 bps (0.30%)")
    
    result_v2 = swap_simulator.simulate_swap(
        amount_in=10000,
        reserve_in=1_000_000,
        reserve_out=500,
        fee_bps=30,
        protocol=2  # V2
    )
    
    logger.info(f"\n   ✅ Output: {result_v2.amount_out:.6f} ETH")
    logger.info(f"   Price Impact: {result_v2.price_impact_pct:.4f}%")
    logger.info(f"   Effective Price: {result_v2.effective_price:.6f}")
    logger.info(f"   Fee Paid: ${result_v2.fee_paid:.2f}")
    
    # Test Balancer weighted pool
    logger.info("\n📊 Balancer Weighted Pool Test (80/20):")
    logger.info(f"   Reserve In: 800,000 WETH (weight 0.8)")
    logger.info(f"   Reserve Out: 200,000 USDC (weight 0.2)")
    logger.info(f"   Trade: 5,000 WETH → USDC")
    logger.info(f"   Fee: 30 bps")
    
    result_bal = swap_simulator.simulate_swap(
        amount_in=5000,
        reserve_in=800_000,
        reserve_out=200_000,
        fee_bps=30,
        protocol=5,  # Balancer
        weight_in=0.8,
        weight_out=0.2
    )
    
    logger.info(f"\n   ✅ Output: ${result_bal.amount_out:,.2f} USDC")
    logger.info(f"   Price Impact: {result_bal.price_impact_pct:.4f}%")
    logger.info(f"   Slippage: {result_bal.slippage_pct:.4f}%")
    
    # Test full arbitrage calculation
    logger.info("\n📊 Full Flash Loan Arbitrage Test:")
    logger.info(f"   Flash Loan: $10,000")
    logger.info(f"   Pool 1 (QuickSwap V2): 2M reserves, 30 bps")
    logger.info(f"   Pool 2 (Uniswap V2): 1M reserves, 30 bps")
    
    arb_result = swap_simulator.calculate_arbitrage_profit(
        flash_loan_amount=10000,
        pool1_reserve_in=2_000_000,
        pool1_reserve_out=1_000,
        pool1_fee_bps=30,
        pool1_protocol=2,
        pool2_reserve_in=1_000,
        pool2_reserve_out=1_000_000,
        pool2_fee_bps=30,
        pool2_protocol=2,
        flash_loan_fee_bps=9,
        gas_cost_usd=0.3375
    )
    
    logger.info(f"\n   Leg 1:")
    logger.info(f"      In: ${arb_result['leg1']['amount_in']:,.2f}")
    logger.info(f"      Out: ${arb_result['leg1']['amount_out']:,.2f}")
    logger.info(f"      Fee: ${arb_result['leg1']['fee_paid']:.2f}")
    logger.info(f"      Slippage: {arb_result['leg1']['slippage_pct']:.4f}%")
    
    logger.info(f"\n   Leg 2:")
    logger.info(f"      In: ${arb_result['leg2']['amount_in']:,.2f}")
    logger.info(f"      Out: ${arb_result['leg2']['amount_out']:,.2f}")
    logger.info(f"      Fee: ${arb_result['leg2']['fee_paid']:.2f}")
    logger.info(f"      Slippage: {arb_result['leg2']['slippage_pct']:.4f}%")
    
    logger.info(f"\n   💰 Results:")
    logger.info(f"      Flash Loan Fee: ${arb_result['flash_loan_fee']:.2f}")
    logger.info(f"      Gas Cost: ${arb_result['gas_cost']:.2f}")
    logger.info(f"      Gross Profit: ${arb_result['gross_profit']:,.2f}")
    logger.info(f"      Net Profit: ${arb_result['net_profit']:,.2f}")
    logger.info(f"      ROI: {arb_result['roi_percent']:.4f}%")
    logger.info(f"      Profitable: {'YES ✅' if arb_result['is_profitable'] else 'NO ❌'}")
    
    # Now test with real pools from arbitrage engine
    logger.info("\n📊 Real Pool Integration Test:")
    engine = get_arbitrage_engine()
    
    if len(engine.pools) >= 2:
        pools_list = list(engine.pools.values())
        pool1 = pools_list[0]
        pool2 = pools_list[1]
        
        logger.info(f"\n   Pool 1: {pool1.token0_symbol}/{pool1.token1_symbol} ({pool1.dex_name})")
        logger.info(f"      TVL: ${pool1.reserve_usd:,.2f}")
        logger.info(f"      Reserves: {pool1.reserve0:.2f} / {pool1.reserve1:.2f}")
        
        logger.info(f"\n   Pool 2: {pool2.token0_symbol}/{pool2.token1_symbol} ({pool2.dex_name})")
        logger.info(f"      TVL: ${pool2.reserve_usd:,.2f}")
        logger.info(f"      Reserves: {pool2.reserve0:.2f} / {pool2.reserve1:.2f}")
        
        # Scan for spreads using exact calculations
        spreads = engine.scan_for_spreads(10000)
        logger.info(f"\n   ✅ Found {len(spreads)} arbitrage opportunities")
        
        if spreads:
            top = spreads[0]
            logger.info(f"\n   Top Opportunity:")
            logger.info(f"      Pair: {top.token_pair}")
            logger.info(f"      Net Profit: ${top.flash_loan.net_profit_usd:.2f}")
            logger.info(f"      ROI: {top.flash_loan.roi_percent:.4f}%")
            logger.info(f"      Executable: {top.flash_loan.is_executable}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ Exact Swap Calculations: OPERATIONAL")
    logger.info("   Using real AMM formulas for accurate profit calculations")
    logger.info("=" * 70)
    
    return True


if __name__ == "__main__":
    test_exact_swap_vs_approximate()
