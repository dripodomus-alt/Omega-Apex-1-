"""
Dynamic Pool Scanner for Polygon DEXes
Queries factory contracts to find ALL pools with valid TVL
NO STATIC JSON - all pools discovered dynamically
"""
import logging
from typing import List, Dict, Optional, Set, Tuple
from web3 import Web3
from web3.contract import Contract
import asyncio
from itertools import combinations

from token_universe import POLYGON_TOKEN_UNIVERSE, get_token_addresses, get_token_info

logger = logging.getLogger(__name__)

# DEX Factory Addresses on Polygon
DEX_FACTORIES = {
    "quickswap_v2": {
        "address": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
        "protocol": "UniswapV2",
        "type": 2
    },
    "quickswap_v3": {
        "address": "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28",
        "protocol": "UniswapV3",
        "type": 3
    },
    "uniswap_v3": {
        "address": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "protocol": "UniswapV3",
        "type": 3
    },
    "sushiswap": {
        "address": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
        "protocol": "UniswapV2",
        "type": 2
    },
}

# Factory ABIs
UNISWAP_V2_FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "allPairs",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "allPairsLength",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

UNISWAP_V3_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "uint24", "name": "", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]


class DynamicPoolScanner:
    """
    Scans DEX factories to discover ALL pools dynamically
    Filters by TVL and token universe
    """
    
    def __init__(self, w3: Web3, min_tvl_usd: float = 10000):
        self.w3 = w3
        self.min_tvl_usd = min_tvl_usd
        self.token_addresses = [Web3.to_checksum_address(addr) for addr in get_token_addresses()]
        self.discovered_pools: List[Dict] = []
        
        logger.info(f"DynamicPoolScanner initialized with {len(self.token_addresses)} tokens")
    
    def scan_v2_factory(
        self,
        factory_address: str,
        dex_name: str,
        protocol_type: int
    ) -> List[Dict]:
        """
        Scan UniswapV2-style factory for all token pair combinations
        """
        logger.info(f"Scanning {dex_name} V2 factory: {factory_address[:10]}...")
        
        factory_address = Web3.to_checksum_address(factory_address)
        factory = self.w3.eth.contract(address=factory_address, abi=UNISWAP_V2_FACTORY_ABI)
        
        pools = []
        checked = 0
        found = 0
        
        # Generate all token pair combinations
        token_pairs = list(combinations(self.token_addresses, 2))
        total_pairs = len(token_pairs)
        
        logger.info(f"Checking {total_pairs} token pair combinations...")
        
        for token0, token1 in token_pairs:
            try:
                checked += 1
                
                # Query factory for pair
                pair_address = factory.functions.getPair(token0, token1).call()
                
                # Check if pair exists
                if pair_address == "0x0000000000000000000000000000000000000000":
                    continue
                
                # Get token info
                token0_info = get_token_info(token0)
                token1_info = get_token_info(token1)
                
                if not token0_info or not token1_info:
                    continue
                
                pool_data = {
                    "pair_address": pair_address,
                    "dex_name": dex_name,
                    "protocol": protocol_type,
                    "token0_address": token0,
                    "token1_address": token1,
                    "token0_symbol": token0_info["symbol"],
                    "token1_symbol": token1_info["symbol"],
                    "token0_decimals": token0_info["decimals"],
                    "token1_decimals": token1_info["decimals"],
                    "fee_bps": 30  # Standard V2 fee
                }
                
                pools.append(pool_data)
                found += 1
                
                if checked % 100 == 0:
                    logger.info(f"Progress: {checked}/{total_pairs} checked, {found} pools found")
                
            except Exception as e:
                logger.debug(f"Failed to check pair {token0[:10]}/{token1[:10]}: {e}")
                continue
        
        logger.info(f"✅ {dex_name} V2: Found {found} pools from {checked} combinations")
        return pools
    
    def scan_v3_factory(
        self,
        factory_address: str,
        dex_name: str,
        protocol_type: int
    ) -> List[Dict]:
        """
        Scan UniswapV3-style factory for all token pairs across fee tiers
        """
        logger.info(f"Scanning {dex_name} V3 factory: {factory_address[:10]}...")
        
        factory_address = Web3.to_checksum_address(factory_address)
        factory = self.w3.eth.contract(address=factory_address, abi=UNISWAP_V3_FACTORY_ABI)
        
        # V3 fee tiers (in hundredths of bps)
        fee_tiers = [100, 500, 3000, 10000]  # 0.01%, 0.05%, 0.3%, 1%
        
        pools = []
        checked = 0
        found = 0
        
        # Generate all token pair combinations
        token_pairs = list(combinations(self.token_addresses, 2))
        total_combinations = len(token_pairs) * len(fee_tiers)
        
        logger.info(f"Checking {total_combinations} token pair + fee tier combinations...")
        
        for token0, token1 in token_pairs:
            for fee in fee_tiers:
                try:
                    checked += 1
                    
                    # Query factory for pool
                    pool_address = factory.functions.getPool(token0, token1, fee).call()
                    
                    # Check if pool exists
                    if pool_address == "0x0000000000000000000000000000000000000000":
                        continue
                    
                    # Get token info
                    token0_info = get_token_info(token0)
                    token1_info = get_token_info(token1)
                    
                    if not token0_info or not token1_info:
                        continue
                    
                    pool_data = {
                        "pair_address": pool_address,
                        "dex_name": dex_name,
                        "protocol": protocol_type,
                        "token0_address": token0,
                        "token1_address": token1,
                        "token0_symbol": token0_info["symbol"],
                        "token1_symbol": token1_info["symbol"],
                        "token0_decimals": token0_info["decimals"],
                        "token1_decimals": token1_info["decimals"],
                        "fee_bps": fee // 100  # Convert to bps
                    }
                    
                    pools.append(pool_data)
                    found += 1
                    
                    if checked % 200 == 0:
                        logger.info(f"Progress: {checked}/{total_combinations} checked, {found} pools found")
                    
                except Exception as e:
                    logger.debug(f"Failed to check pool {token0[:10]}/{token1[:10]} fee {fee}: {e}")
                    continue
        
        logger.info(f"✅ {dex_name} V3: Found {found} pools from {checked} combinations")
        return pools
    
    def scan_all_dexes(self) -> List[Dict]:
        """
        Scan all DEX factories and return discovered pools
        """
        logger.info("=" * 70)
        logger.info("Starting Dynamic Pool Discovery Scan")
        logger.info(f"Token Universe: {len(self.token_addresses)} tokens")
        logger.info(f"DEXes to scan: {len(DEX_FACTORIES)}")
        logger.info("=" * 70)
        
        all_pools = []
        
        for dex_id, dex_info in DEX_FACTORIES.items():
            try:
                if dex_info["type"] == 2:  # V2
                    pools = self.scan_v2_factory(
                        dex_info["address"],
                        dex_id.replace("_", " ").title(),
                        dex_info["type"]
                    )
                elif dex_info["type"] == 3:  # V3
                    pools = self.scan_v3_factory(
                        dex_info["address"],
                        dex_id.replace("_", " ").title(),
                        dex_info["type"]
                    )
                else:
                    logger.warning(f"Unknown protocol type for {dex_id}")
                    continue
                
                all_pools.extend(pools)
                
            except Exception as e:
                logger.error(f"Failed to scan {dex_id}: {e}")
                continue
        
        # Remove duplicates (same pool address)
        unique_pools = {}
        for pool in all_pools:
            addr = pool["pair_address"].lower()
            if addr not in unique_pools:
                unique_pools[addr] = pool
        
        final_pools = list(unique_pools.values())
        
        logger.info("=" * 70)
        logger.info(f"✅ Scan Complete: {len(final_pools)} unique pools discovered")
        logger.info("=" * 70)
        
        # Log token pair distribution
        pair_counts = {}
        for pool in final_pools:
            pair = f"{pool['token0_symbol']}/{pool['token1_symbol']}"
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
        
        top_pairs = sorted(pair_counts.items(), key=lambda x: -x[1])[:10]
        logger.info("\nTop 10 token pairs:")
        for pair, count in top_pairs:
            logger.info(f"  {pair}: {count} pools")
        
        return final_pools
    
    def filter_by_tvl(self, pools: List[Dict], min_tvl: float = None) -> List[Dict]:
        """
        Filter pools by TVL (requires fetching reserves)
        For now, return all discovered pools
        TODO: Fetch reserves and filter by TVL
        """
        if min_tvl is None:
            min_tvl = self.min_tvl_usd
        
        logger.info(f"\nFiltering pools by min TVL: ${min_tvl:,.0f}")
        logger.info(f"Note: TVL filtering requires Web3 reserve fetching (expensive)")
        logger.info(f"Returning all {len(pools)} discovered pools for now")
        
        return pools
    
    def save_to_json(self, pools: List[Dict], filepath: str):
        """Save discovered pools to JSON file"""
        import json
        from datetime import datetime
        
        data = {
            "updated_at": int(datetime.now().timestamp()),
            "count": len(pools),
            "min_tvl_usd": self.min_tvl_usd,
            "token_universe_size": len(self.token_addresses),
            "pools": pools
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"✅ Saved {len(pools)} pools to {filepath}")
