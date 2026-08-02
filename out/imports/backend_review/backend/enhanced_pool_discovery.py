"""
Enhanced Pool Discovery using 1inch API
Discovers 1000+ pools across Polygon DEXs
"""

import asyncio
import logging
from typing import List, Dict, Set
from oneinch_discovery import get_oneinch_discovery

logger = logging.getLogger(__name__)

# Top tokens on Polygon for pool discovery
TOP_POLYGON_TOKENS = [
    "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
    "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
    "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC.e
    "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
    "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
    "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
    "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",  # LINK
    "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",  # AAVE
    "0x172370d5Cd63279eFa6d502DAB29171933a610AF",  # CRV
    "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",  # SUSHI
    "0x580A84C73811E1839F75d86d75d88cCa0c241fF4",  # QI
    "0x831753DD7087CaC61aB5644b308642cc1c33Dc13",  # QUICK
    "0xB0B195aEFA3650A6908f15CdaC7D92F8a5791B0B",  # BOB
    "0x385Eeac5cB85A38A9a07A70c73e0a3271CfB54A7",  # GHST
    "0xC3C7d422809852031b44ab29EEC9F1EfF2A58756",  # LDO
]


class EnhancedPoolDiscovery:
    """
    Discover pools by querying 1inch for all token pair combinations
    """
    
    def __init__(self):
        self.oneinch = get_oneinch_discovery()
        self.discovered_pairs = set()
        self.discovered_pools = {}
    
    async def discover_pools_from_token_pairs(
        self, 
        max_pairs: int = 500,
        amount_per_query: str = "1000000000000000000"  # 1 token
    ) -> Dict[str, Dict]:
        """
        Discover pools by querying swap routes for token pairs.
        
        Strategy:
        1. Query 1inch swap API for top token pairs
        2. Extract pool addresses from routing data
        3. Build comprehensive pool list
        
        Args:
            max_pairs: Maximum number of token pairs to query
            amount_per_query: Test swap amount (1 token in wei)
            
        Returns:
            Dictionary of discovered pools with metadata
        """
        logger.info(f"🔍 Starting enhanced pool discovery via 1inch...")
        logger.info(f"   Querying {len(TOP_POLYGON_TOKENS)} tokens × {len(TOP_POLYGON_TOKENS)-1} pairs")
        
        pools = {}
        pair_count = 0
        discovered_protocols = set()
        
        # Query all combinations of top tokens
        for i, token_a in enumerate(TOP_POLYGON_TOKENS):
            for j, token_b in enumerate(TOP_POLYGON_TOKENS):
                if token_a == token_b:
                    continue
                
                pair_key = tuple(sorted([token_a, token_b]))
                if pair_key in self.discovered_pairs:
                    continue  # Skip already queried pairs
                
                self.discovered_pairs.add(pair_key)
                
                try:
                    # Get swap quote from 1inch
                    quote = await self.oneinch.get_swap_quote(
                        src_token=token_a,
                        dst_token=token_b,
                        amount=amount_per_query
                    )
                    
                    if quote and 'protocols' in quote:
                        # Extract protocol/pool information from routing data
                        protocols = quote.get('protocols', [])
                        
                        for route in protocols:
                            for step in route:
                                for pool_info in step:
                                    protocol_name = pool_info.get('name', 'Unknown')
                                    discovered_protocols.add(protocol_name)
                                    
                                    # Create pool entry
                                    pool_key = f"{token_a}_{token_b}_{protocol_name}"
                                    
                                    if pool_key not in pools:
                                        pools[pool_key] = {
                                            'token0_address': token_a,
                                            'token1_address': token_b,
                                            'dex_name': protocol_name,
                                            'source': '1inch_routing',
                                            'part': pool_info.get('part', 100)
                                        }
                    
                    pair_count += 1
                    
                    if pair_count % 20 == 0:
                        logger.info(f"   Progress: {pair_count} pairs queried, {len(pools)} pools found")
                    
                    if pair_count >= max_pairs:
                        break
                    
                    # Rate limiting: 1 RPS for free tier
                    await asyncio.sleep(1.1)
                
                except Exception as e:
                    logger.debug(f"Failed to query {token_a[:8]}/{token_b[:8]}: {e}")
                    continue
            
            if pair_count >= max_pairs:
                break
        
        logger.info(f"\n✅ Discovery complete:")
        logger.info(f"   Pairs queried: {pair_count}")
        logger.info(f"   Pools discovered: {len(pools)}")
        logger.info(f"   DEXs found: {len(discovered_protocols)}")
        logger.info(f"   DEX list: {', '.join(sorted(discovered_protocols)[:10])}")
        
        self.discovered_pools = pools
        return pools
    
    async def discover_all_liquidity_sources(self) -> Dict[str, List]:
        """
        Get metadata about all DEXs integrated with 1inch on Polygon.
        
        Returns:
            Dictionary of DEX protocols with their metadata
        """
        logger.info("🔍 Discovering liquidity sources from 1inch...")
        
        sources = await self.oneinch.discover_liquidity_sources()
        
        if sources:
            logger.info(f"✅ Found {len(sources)} liquidity sources:")
            for protocol_id, protocol_data in list(sources.items())[:15]:
                logger.info(f"   • {protocol_data.get('title', protocol_id)}")
        
        return sources


async def run_enhanced_discovery(max_pairs: int = 200) -> Dict:
    """
    Run enhanced pool discovery and return results.
    
    Args:
        max_pairs: Maximum token pairs to query (default 200)
                  200 pairs @ 1 RPS = ~3-4 minutes
                  500 pairs @ 1 RPS = ~8-10 minutes
    """
    discovery = EnhancedPoolDiscovery()
    
    # Step 1: Discover liquidity sources (DEX metadata)
    await discovery.discover_all_liquidity_sources()
    
    # Step 2: Discover pools via token pair queries
    pools = await discovery.discover_pools_from_token_pairs(max_pairs=max_pairs)
    
    return pools


# Synchronous wrapper for backward compatibility
def discover_pools_sync(max_pairs: int = 200) -> Dict:
    """
    Synchronous wrapper for enhanced pool discovery.
    
    Use this from non-async code.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run_enhanced_discovery(max_pairs))


if __name__ == "__main__":
    """
    Test script: Run pool discovery
    """
    import sys
    
    # Parse command line args
    max_pairs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    
    print("=" * 80)
    print("ENHANCED POOL DISCOVERY TEST")
    print("=" * 80)
    print(f"\nQuerying {max_pairs} token pairs...")
    print("This will take ~1 minute per 50 pairs (due to 1 RPS rate limit)\n")
    
    pools = discover_pools_sync(max_pairs=max_pairs)
    
    print("\n" + "=" * 80)
    print("DISCOVERY COMPLETE")
    print("=" * 80)
    print(f"\nTotal pools discovered: {len(pools)}")
    
    if pools:
        print("\nSample pools:")
        for i, (pool_id, pool_data) in enumerate(list(pools.items())[:10], 1):
            print(f"\n{i}. {pool_data['dex_name']}")
            print(f"   Token0: {pool_data['token0_address'][:10]}...")
            print(f"   Token1: {pool_data['token1_address'][:10]}...")
