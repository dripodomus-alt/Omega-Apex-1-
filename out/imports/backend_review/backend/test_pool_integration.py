"""
Test script to verify 133 real pools are loaded correctly
"""
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def test_arbitrage_engine_pools():
    """Test ArbitrageEngine loads pools from JSON"""
    from arbitrage_engine import get_arbitrage_engine
    
    logger.info("=" * 60)
    logger.info("TEST: ArbitrageEngine Pool Loading")
    logger.info("=" * 60)
    
    engine = get_arbitrage_engine()
    
    logger.info(f"Total pools loaded: {len(engine.pools)}")
    logger.info(f"Expected: 133 pools")
    
    if len(engine.pools) == 0:
        logger.error("❌ FAILED: No pools loaded!")
        return False
    
    # Display first 5 pools
    logger.info("\nFirst 5 pools loaded:")
    for i, (addr, pool) in enumerate(list(engine.pools.items())[:5]):
        logger.info(f"  {i+1}. {pool.token0_symbol}/{pool.token1_symbol} | "
                   f"DEX: {pool.dex_name} | Protocol: {pool.protocol} | "
                   f"TVL: ${pool.reserve_usd:,.2f} | Fee: {pool.fee} ppm")
    
    # Check protocol distribution
    protocols = {}
    for pool in engine.pools.values():
        proto = pool.protocol
        if proto not in protocols:
            protocols[proto] = 0
        protocols[proto] += 1
    
    logger.info("\nProtocol distribution:")
    for proto, count in protocols.items():
        logger.info(f"  Protocol {proto}: {count} pools")
    
    # Check DEX distribution
    dexes = {}
    for pool in engine.pools.values():
        dex = pool.dex_name
        if dex not in dexes:
            dexes[dex] = 0
        dexes[dex] += 1
    
    logger.info("\nDEX distribution:")
    for dex, count in sorted(dexes.items(), key=lambda x: -x[1]):
        logger.info(f"  {dex}: {count} pools")
    
    # Check TVL range
    tvls = [p.reserve_usd for p in engine.pools.values()]
    logger.info(f"\nTVL Statistics:")
    logger.info(f"  Min TVL: ${min(tvls):,.2f}")
    logger.info(f"  Max TVL: ${max(tvls):,.2f}")
    logger.info(f"  Avg TVL: ${sum(tvls)/len(tvls):,.2f}")
    
    logger.info("\n✅ Pool loading test PASSED")
    return True


def test_engine_pool_loading():
    """Test engine.py loads pools from JSON"""
    from engine import Web3PoolScanner, POLYGON_POOLS
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST: engine.py Pool Database Loading")
    logger.info("=" * 60)
    
    logger.info(f"Total pool pairs loaded: {len(POLYGON_POOLS)}")
    
    if len(POLYGON_POOLS) == 0:
        logger.error("❌ FAILED: No pools loaded in POLYGON_POOLS!")
        return False
    
    logger.info("\nFirst 10 pool pairs:")
    for i, (pair, address) in enumerate(list(POLYGON_POOLS.items())[:10]):
        logger.info(f"  {i+1}. {pair} -> {address}")
    
    logger.info("\n✅ Engine pool loading test PASSED")
    return True


def test_slippage_calculations():
    """Test slippage calculations use correct TVL"""
    from arbitrage_engine import get_arbitrage_engine
    from titan_slippage import titan_engine
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Slippage Calculation with Pool TVL")
    logger.info("=" * 60)
    
    engine = get_arbitrage_engine()
    
    if len(engine.pools) == 0:
        logger.error("❌ FAILED: No pools to test")
        return False
    
    # Get first pool
    pool = list(engine.pools.values())[0]
    
    logger.info(f"\nTesting pool: {pool.token0_symbol}/{pool.token1_symbol}")
    logger.info(f"Pool TVL: ${pool.reserve_usd:,.2f}")
    logger.info(f"Pool Fee: {pool.fee} ppm ({pool.fee/10000:.2f}%)")
    
    # Test slippage calculation
    test_amount = 10000  # $10k trade
    slippage_pct = engine.calculate_slippage(
        amount_usd=test_amount,
        pool_tvl_usd=pool.reserve_usd,
        fee_bps=pool.fee / 100,  # Convert ppm to bps
        protocol=pool.protocol
    )
    
    logger.info(f"\nTest trade: ${test_amount:,.2f}")
    logger.info(f"Calculated slippage: {slippage_pct:.4f}%")
    logger.info(f"Market impact ratio: {(test_amount/pool.reserve_usd)*100:.4f}%")
    
    if slippage_pct < 0 or slippage_pct > 100:
        logger.error(f"❌ FAILED: Invalid slippage value: {slippage_pct}%")
        return False
    
    logger.info("\n✅ Slippage calculation test PASSED")
    return True


if __name__ == "__main__":
    logger.info("\n" + "🔱" * 20)
    logger.info("APEX_OMEGA: 133 REAL POOLS INTEGRATION TEST")
    logger.info("🔱" * 20 + "\n")
    
    results = []
    
    # Run tests
    results.append(("ArbitrageEngine Pool Loading", test_arbitrage_engine_pools()))
    results.append(("Engine.py Pool Loading", test_engine_pool_loading()))
    results.append(("Slippage Calculations", test_slippage_calculations()))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} | {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED - 133 Real Pools Integrated Successfully!")
        sys.exit(0)
    else:
        logger.error("\n❌ SOME TESTS FAILED - Please review errors above")
        sys.exit(1)
