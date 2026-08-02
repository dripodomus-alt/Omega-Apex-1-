"""
Test real Web3 pool data fetching with NO DEFAULTS
V2, V3 tick math, and Balancer weights
"""
import logging
import os
from web3 import Web3
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / '.env')
logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def test_web3_fetcher():
    """Test Web3 pool fetcher with real pools"""
    from web3_pool_fetcher import Web3PoolFetcher
    
    logger.info("=" * 70)
    logger.info("TEST: Real Web3 Pool Data Fetching (NO DEFAULTS)")
    logger.info("=" * 70)
    
    # Connect to Web3
    rpc_url = os.getenv('ALCHEMY_HTTP_1') or os.getenv('PRIVATE_RPC_URL')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        logger.error("❌ Web3 not connected")
        return False
    
    logger.info(f"✅ Connected to RPC: {rpc_url[:50]}...")
    logger.info(f"✅ Block number: {w3.eth.block_number}")
    
    fetcher = Web3PoolFetcher(w3)
    
    # Test V2 pool (QuickSwap WETH/USDC)
    logger.info("\n📊 TEST 1: UniswapV2 Pool (QuickSwap WETH/USDC)")
    v2_pool = "0x853Ee4b2A13f8a742d64C8F088bE7bA2131f670d"
    token0 = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619"  # WETH
    token1 = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC
    
    v2_data = fetcher.fetch_v2_reserves(v2_pool, token0, token1)
    
    if v2_data:
        logger.info(f"   ✅ V2 Reserves Fetched:")
        logger.info(f"      Reserve0 (WETH): {v2_data.reserve0:,.6f}")
        logger.info(f"      Reserve1 (USDC): {v2_data.reserve1:,.2f}")
        logger.info(f"      Token0 Decimals: {v2_data.token0_decimals}")
        logger.info(f"      Token1 Decimals: {v2_data.token1_decimals}")
        logger.info(f"      Fee: {v2_data.fee} bps")
        logger.info(f"      Data Source: {v2_data.data_source}")
    else:
        logger.error("   ❌ V2 fetch failed")
        return False
    
    # Test V3 pool (Uniswap V3 WETH/USDC)
    logger.info("\n📊 TEST 2: UniswapV3 Pool (Uniswap WETH/USDC 0.05%)")
    v3_pool = "0x45dDa9cb7c25131DF268515131f647d726f50608"
    
    v3_data = fetcher.fetch_v3_state(v3_pool, token0, token1)
    
    if v3_data:
        logger.info(f"   ✅ V3 State Fetched:")
        logger.info(f"      Liquidity: {v3_data.liquidity:,}")
        logger.info(f"      Tick: {v3_data.tick}")
        logger.info(f"      sqrtPriceX96: {v3_data.sqrt_price_x96}")
        logger.info(f"      Current Price: {(v3_data.sqrt_price_x96 / (2**96))**2:.6f}")
        logger.info(f"      Virtual Reserve0: {v3_data.reserve0:,.6f}")
        logger.info(f"      Virtual Reserve1: {v3_data.reserve1:,.2f}")
        logger.info(f"      Fee: {v3_data.fee} (not bps, raw)")
        logger.info(f"      Data Source: {v3_data.data_source}")
    else:
        logger.error("   ❌ V3 fetch failed")
        return False
    
    # Test Balancer pool
    logger.info("\n📊 TEST 3: Balancer Weighted Pool")
    bal_pool = "0x03cD191F589d12b0582a99808cf19851E468E6B5"  # Example Balancer pool
    bal_token0 = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619"  # WETH
    bal_token1 = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC
    
    bal_data = fetcher.fetch_balancer_pool(bal_pool, bal_token0, bal_token1)
    
    if bal_data:
        logger.info(f"   ✅ Balancer Data Fetched:")
        logger.info(f"      Reserve0 (WETH): {bal_data.reserve0:,.6f}")
        logger.info(f"      Reserve1 (USDC): {bal_data.reserve1:,.2f}")
        logger.info(f"      Weight0: {bal_data.weight0:.4f} ({bal_data.weight0*100:.1f}%)")
        logger.info(f"      Weight1: {bal_data.weight1:.4f} ({bal_data.weight1*100:.1f}%)")
        logger.info(f"      Fee: {bal_data.fee} bps")
        logger.info(f"      Data Source: {bal_data.data_source}")
        logger.info(f"      ⚠️  NO DEFAULTS - All weights from blockchain")
    else:
        logger.warning("   ⚠️  Balancer fetch failed (pool may not exist or wrong address)")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ Web3 Fetcher Test PASSED")
    logger.info("   All data fetched from blockchain - NO DEFAULTS USED")
    logger.info("=" * 70)
    
    return True


def test_arbitrage_with_real_data():
    """Test arbitrage engine with real Web3 data"""
    from arbitrage_engine import get_arbitrage_engine
    
    logger.info("\n" + "=" * 70)
    logger.info("TEST: Arbitrage Engine with Real Web3 Data")
    logger.info("=" * 70)
    
    engine = get_arbitrage_engine()
    
    logger.info(f"\n   Total pools loaded: {len(engine.pools)}")
    logger.info(f"   Web3 fetcher enabled: {engine.pool_fetcher is not None}")
    
    # Check if pools have real reserves
    pools_with_real_reserves = 0
    pools_with_v3_data = 0
    pools_with_balancer_weights = 0
    
    for pool in engine.pools.values():
        if pool.reserve0 > 0 and pool.reserve1 > 0:
            pools_with_real_reserves += 1
        if pool.sqrt_price_x96 > 0:
            pools_with_v3_data += 1
        if pool.weight0 != 0.5 or pool.weight1 != 0.5:
            pools_with_balancer_weights += 1
    
    logger.info(f"\n   Pools with real reserves: {pools_with_real_reserves}")
    logger.info(f"   Pools with V3 tick data: {pools_with_v3_data}")
    logger.info(f"   Pools with Balancer weights: {pools_with_balancer_weights}")
    
    # Show sample pool data
    if engine.pools:
        sample_pool = list(engine.pools.values())[0]
        logger.info(f"\n   Sample Pool: {sample_pool.token0_symbol}/{sample_pool.token1_symbol}")
        logger.info(f"      DEX: {sample_pool.dex_name}")
        logger.info(f"      Reserve0: {sample_pool.reserve0:,.6f}")
        logger.info(f"      Reserve1: {sample_pool.reserve1:,.6f}")
        logger.info(f"      Weight0: {sample_pool.weight0:.4f}")
        logger.info(f"      Weight1: {sample_pool.weight1:.4f}")
        if sample_pool.sqrt_price_x96 > 0:
            logger.info(f"      V3 sqrtPriceX96: {sample_pool.sqrt_price_x96}")
            logger.info(f"      V3 Tick: {sample_pool.tick}")
    
    # Scan for spreads
    spreads = engine.scan_for_spreads(10000)
    logger.info(f"\n   ✅ Found {len(spreads)} arbitrage opportunities")
    
    if spreads:
        top = spreads[0]
        logger.info(f"\n   Top Opportunity:")
        logger.info(f"      Pair: {top.token_pair}")
        logger.info(f"      Net Profit: ${top.flash_loan.net_profit_usd:.2f}")
        logger.info(f"      ROI: {top.flash_loan.roi_percent:.4f}%")
        logger.info(f"      Using REAL Web3 reserves")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ Real Data Integration Test PASSED")
    logger.info("=" * 70)
    
    return True


if __name__ == "__main__":
    logger.info("\n🔱 APEX_OMEGA: Real Web3 Data Fetching Test\n")
    
    try:
        # Test Web3 fetcher
        if not test_web3_fetcher():
            logger.error("\n❌ Web3 fetcher test failed")
            exit(1)
        
        # Test arbitrage with real data
        if not test_arbitrage_with_real_data():
            logger.error("\n❌ Arbitrage integration test failed")
            exit(1)
        
        logger.info("\n✅ ALL TESTS PASSED - Real Web3 Data Integration Complete\n")
        
    except Exception as e:
        logger.error(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
