"""
Direct On-Chain Pool Discovery
Queries DEX factory contracts to discover ALL pools on Polygon

This is MORE comprehensive than API-based discovery because we get
EVERY pool directly from the blockchain, not just what aggregators track.
"""

import os
import logging
from web3 import Web3
from typing import List, Dict
import json
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger(__name__)

# Polygon DEX Factory Contracts
POLYGON_DEX_FACTORIES = {
    'QuickSwap V2': {
        'factory': '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32',
        'type': 'uniswap_v2',
        'init_code_hash': '0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f'
    },
    'SushiSwap': {
        'factory': '0xc35DADB65012eC5796536bD9864eD8773aBc74C4',
        'type': 'uniswap_v2',
        'init_code_hash': '0xe18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303'
    },
    'Uniswap V3': {
        'factory': '0x1F98431c8aD98523631AE4a59f267346ea31F984',
        'type': 'uniswap_v3'
    },
    'QuickSwap V3 (Algebra)': {
        'factory': '0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28',
        'type': 'algebra'
    },
}

# UniswapV2 Factory ABI (minimal - just what we need)
UNISWAP_V2_FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "allPairsLength",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "", "type": "uint256"}],
        "name": "allPairs",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    }
]

# UniswapV2 Pair ABI (minimal)
UNISWAP_V2_PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    }
]


class OnChainPoolDiscovery:
    """
    Discover pools directly from DEX factory contracts on Polygon
    """
    
    def __init__(self):
        rpc_url = os.getenv('POLYGON_RPC_URL') or os.getenv('POLYGON_HTTP') or 'https://polygon-rpc.com'
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Polygon RPC: {rpc_url}")
        
        logger.info(f"✅ Connected to Polygon: {rpc_url[:50]}...")
    
    def discover_uniswap_v2_pools(
        self, 
        factory_address: str, 
        dex_name: str,
        max_pools: int = 5000
    ) -> List[Dict]:
        """
        Discover all pools from a Uniswap V2-style factory contract.
        
        Args:
            factory_address: Factory contract address
            dex_name: Name of the DEX (for metadata)
            max_pools: Maximum pools to fetch
            
        Returns:
            List of pool dictionaries with addresses and metadata
        """
        logger.info(f"🔍 Discovering {dex_name} pools...")
        
        try:
            factory = self.w3.eth.contract(
                address=Web3.to_checksum_address(factory_address),
                abi=UNISWAP_V2_FACTORY_ABI
            )
            
            # Get total number of pairs
            total_pairs = factory.functions.allPairsLength().call()
            logger.info(f"   Total pairs in factory: {total_pairs}")
            
            # Limit to max_pools
            pairs_to_fetch = min(total_pairs, max_pools)
            
            pools = []
            batch_size = 100
            
            for i in range(0, pairs_to_fetch, batch_size):
                end_idx = min(i + batch_size, pairs_to_fetch)
                logger.info(f"   Fetching pools {i}-{end_idx}...")
                
                for idx in range(i, end_idx):
                    try:
                        pair_address = factory.functions.allPairs(idx).call()
                        
                        # Get pair contract
                        pair = self.w3.eth.contract(
                            address=pair_address,
                            abi=UNISWAP_V2_PAIR_ABI
                        )
                        
                        # Get tokens
                        token0 = pair.functions.token0().call()
                        token1 = pair.functions.token1().call()
                        
                        pools.append({
                            'pair_address': pair_address,
                            'token0_address': token0,
                            'token1_address': token1,
                            'dex_name': dex_name,
                            'protocol': 2,  # V2
                            'source': 'on_chain_factory'
                        })
                    
                    except Exception as e:
                        logger.debug(f"Failed to fetch pair {idx}: {e}")
                        continue
            
            logger.info(f"✅ {dex_name}: Discovered {len(pools)} pools")
            return pools
        
        except Exception as e:
            logger.error(f"Failed to discover {dex_name} pools: {e}")
            return []
    
    def discover_all_dex_pools(self, max_pools_per_dex: int = 2000) -> Dict[str, List[Dict]]:
        """
        Discover pools from all major DEXs on Polygon.
        
        Args:
            max_pools_per_dex: Maximum pools to fetch per DEX
            
        Returns:
            Dictionary mapping DEX name to list of pools
        """
        all_pools = {}
        
        for dex_name, config in POLYGON_DEX_FACTORIES.items():
            if config['type'] == 'uniswap_v2':
                pools = self.discover_uniswap_v2_pools(
                    factory_address=config['factory'],
                    dex_name=dex_name,
                    max_pools=max_pools_per_dex
                )
                all_pools[dex_name] = pools
            else:
                logger.info(f"⏭️  Skipping {dex_name} (type: {config['type']}) - not yet implemented")
        
        return all_pools
    
    def flatten_pools(self, pools_by_dex: Dict[str, List[Dict]]) -> List[Dict]:
        """Flatten pools dictionary into a single list."""
        flat_list = []
        for dex_name, pools in pools_by_dex.items():
            flat_list.extend(pools)
        return flat_list


def discover_polygon_pools(max_pools_per_dex: int = 2000) -> List[Dict]:
    """
    Main entry point: Discover all pools on Polygon.
    
    Args:
        max_pools_per_dex: Maximum pools per DEX (default 2000)
    
    Returns:
        List of all discovered pools
    """
    discovery = OnChainPoolDiscovery()
    pools_by_dex = discovery.discover_all_dex_pools(max_pools_per_dex=max_pools_per_dex)
    
    all_pools = discovery.flatten_pools(pools_by_dex)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"🎯 TOTAL POOLS DISCOVERED: {len(all_pools)}")
    logger.info(f"{'='*80}\n")
    
    for dex_name, pools in pools_by_dex.items():
        logger.info(f"   {dex_name}: {len(pools)} pools")
    
    return all_pools


if __name__ == "__main__":
    """
    Test script: Discover pools from Polygon DEXs
    """
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    max_pools = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    
    print("\n" + "=" * 80)
    print("ON-CHAIN POOL DISCOVERY")
    print("=" * 80)
    print(f"\nFetching up to {max_pools} pools per DEX...")
    print("This queries factory contracts directly - NO API rate limits!\n")
    
    pools = discover_polygon_pools(max_pools_per_dex=max_pools)
    
    print("\n" + "=" * 80)
    print("SAMPLE POOLS")
    print("=" * 80)
    
    for i, pool in enumerate(pools[:10], 1):
        print(f"\n{i}. {pool['dex_name']}")
        print(f"   Address: {pool['pair_address'][:20]}...")
        print(f"   Token0: {pool['token0_address'][:20]}...")
        print(f"   Token1: {pool['token1_address'][:20]}...")
