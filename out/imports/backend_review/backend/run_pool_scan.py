"""
Run Dynamic Pool Scanner
Discovers ALL pools across Polygon DEXes for 32-token universe
"""
import os
import logging
from pathlib import Path
from web3 import Web3
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')
logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

from dynamic_pool_scanner import DynamicPoolScanner
from token_universe import POLYGON_TOKEN_UNIVERSE


def main():
    logger.info("\n" + "🔱" * 30)
    logger.info("APEX_OMEGA: Dynamic Pool Discovery")
    logger.info("🔱" * 30 + "\n")
    
    # Connect to Web3
    rpc_url = os.getenv('ALCHEMY_HTTP_1') or os.getenv('PRIVATE_RPC_URL')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        logger.error("❌ Web3 not connected")
        return
    
    logger.info(f"✅ Connected to Polygon RPC")
    logger.info(f"✅ Block number: {w3.eth.block_number:,}")
    
    # Token universe info
    logger.info(f"\n📊 Token Universe: {len(POLYGON_TOKEN_UNIVERSE)} tokens")
    
    token_types = {}
    for symbol, info in POLYGON_TOKEN_UNIVERSE.items():
        token_type = info["type"]
        token_types[token_type] = token_types.get(token_type, 0) + 1
    
    logger.info(f"\nToken Distribution:")
    for token_type, count in sorted(token_types.items(), key=lambda x: -x[1]):
        logger.info(f"  {token_type}: {count}")
    
    # Initialize scanner
    min_tvl = float(os.getenv('MIN_POOL_TVL_USD', 10000))
    scanner = DynamicPoolScanner(w3, min_tvl_usd=min_tvl)
    
    # Scan all DEXes
    logger.info(f"\n⏳ Starting pool discovery scan...")
    logger.info(f"   This may take 5-10 minutes...\n")
    
    try:
        pools = scanner.scan_all_dexes()
        
        if not pools:
            logger.error("❌ No pools discovered!")
            return
        
        # Save to JSON
        output_path = Path(__file__).parent / 'data' / 'pools_dynamic.json'
        scanner.save_to_json(pools, str(output_path))
        
        # Statistics
        logger.info("\n" + "=" * 70)
        logger.info("📊 Discovery Statistics")
        logger.info("=" * 70)
        
        dex_counts = {}
        protocol_counts = {}
        
        for pool in pools:
            dex = pool["dex_name"]
            protocol = pool["protocol"]
            dex_counts[dex] = dex_counts.get(dex, 0) + 1
            protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
        
        logger.info(f"\nTotal Pools: {len(pools)}")
        logger.info(f"\nBy DEX:")
        for dex, count in sorted(dex_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {dex}: {count} pools")
        
        logger.info(f"\nBy Protocol:")
        for protocol, count in protocol_counts.items():
            protocol_name = "UniswapV2" if protocol == 2 else "UniswapV3"
            logger.info(f"  {protocol_name}: {count} pools")
        
        # Sample pools
        logger.info(f"\nSample Pools:")
        for pool in pools[:5]:
            logger.info(f"  {pool['token0_symbol']}/{pool['token1_symbol']} on {pool['dex_name']} ({pool['fee_bps']} bps)")
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ Dynamic Pool Discovery Complete!")
        logger.info(f"✅ Output: {output_path}")
        logger.info("=" * 70)
        
        # Recommend next steps
        logger.info("\n📋 Next Steps:")
        logger.info("  1. Review pools_dynamic.json")
        logger.info("  2. Replace pools.json with pools_dynamic.json")
        logger.info("  3. Restart backend to load new pools")
        logger.info("  4. System will auto-fetch Web3 reserves for all pools")
        
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Scan interrupted by user")
        logger.info("Partial results may be incomplete")
    except Exception as e:
        logger.error(f"\n❌ Scan failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
