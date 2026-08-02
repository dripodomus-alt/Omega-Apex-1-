"""
Smart Pool Discovery - Prioritized Scanning
Instead of ALL combinations, focus on high-value pairs
"""
import os
import logging
from pathlib import Path
from web3 import Web3
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv(Path(__file__).parent / '.env')
logging.basicConfig(level=logging.INFO, format='%(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

from dynamic_pool_scanner import DynamicPoolScanner, UNISWAP_V2_FACTORY_ABI, UNISWAP_V3_FACTORY_ABI
from token_universe import POLYGON_TOKEN_UNIVERSE, get_token_info


def generate_smart_pairs():
    """Generate high-priority token pairs instead of all combinations"""
    
    # Core tokens for most trading
    core_tokens = [
        "WMATIC", "WETH", "WBTC", "USDC", "USDT", "DAI"
    ]
    
    # DeFi tokens
    defi_tokens = [
        "AAVE", "CRV", "SUSHI", "BAL", "QUICK", "LINK", "UNI"
    ]
    
    # Stablecoins
    stablecoins = [
        "USDC", "USDT", "DAI", "FRAX", "MAI", "USDD"
    ]
    
    # Gaming & others
    other_tokens = [
        "SAND", "MANA", "GHST", "GRT", "SNX", "stMATIC", "MaticX"
    ]
    
    pairs = []
    
    # 1. Core token pairs (highest priority)
    from itertools import combinations
    core_pairs = list(combinations(core_tokens, 2))
    pairs.extend([(t0, t1) for t0, t1 in core_pairs])
    
    # 2. Core tokens with DeFi tokens
    for core in core_tokens:
        for defi in defi_tokens:
            if core != defi:
                pairs.append((core, defi))
    
    # 3. Stablecoin pairs
    stable_pairs = list(combinations(stablecoins, 2))
    pairs.extend([(t0, t1) for t0, t1 in stable_pairs])
    
    # 4. Core tokens with other tokens
    for core in core_tokens:
        for other in other_tokens:
            if core != other:
                pairs.append((core, other))
    
    # Remove duplicates
    unique_pairs = list(set(pairs))
    
    logger.info(f"Generated {len(unique_pairs)} smart token pairs (vs {len(list(combinations(POLYGON_TOKEN_UNIVERSE.keys(), 2)))} total combinations)")
    
    return unique_pairs


def scan_smart_pairs(w3: Web3) -> List[Dict]:
    """Scan only high-priority pairs"""
    
    smart_pairs = generate_smart_pairs()
    
    # DEX factories
    factories = {
        "QuickSwap V2": {
            "address": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
            "abi": UNISWAP_V2_FACTORY_ABI,
            "protocol": 2,
            "fee": 30
        },
        "QuickSwap V3": {
            "address": "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28",
            "abi": UNISWAP_V3_FACTORY_ABI,
            "protocol": 3,
            "fees": [1, 5, 30, 100]  # 0.01%, 0.05%, 0.3%, 1%
        },
        "Uniswap V3": {
            "address": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            "abi": UNISWAP_V3_FACTORY_ABI,
            "protocol": 3,
            "fees": [1, 5, 30, 100]
        },
        "SushiSwap": {
            "address": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
            "abi": UNISWAP_V2_FACTORY_ABI,
            "protocol": 2,
            "fee": 30
        }
    }
    
    all_pools = []
    
    for dex_name, dex_info in factories.items():
        logger.info(f"\n📊 Scanning {dex_name}...")
        
        factory = w3.eth.contract(
            address=Web3.to_checksum_address(dex_info["address"]),
            abi=dex_info["abi"]
        )
        
        found = 0
        
        for symbol0, symbol1 in smart_pairs:
            # Get token addresses
            token0_data = POLYGON_TOKEN_UNIVERSE.get(symbol0)
            token1_data = POLYGON_TOKEN_UNIVERSE.get(symbol1)
            
            if not token0_data or not token1_data:
                continue
            
            addr0 = Web3.to_checksum_address(token0_data["address"])
            addr1 = Web3.to_checksum_address(token1_data["address"])
            
            try:
                if dex_info["protocol"] == 2:  # V2
                    pair_addr = factory.functions.getPair(addr0, addr1).call()
                    
                    if pair_addr != "0x0000000000000000000000000000000000000000":
                        all_pools.append({
                            "pair_address": pair_addr,
                            "dex_name": dex_name,
                            "protocol": 2,
                            "token0_address": addr0,
                            "token1_address": addr1,
                            "token0_symbol": symbol0,
                            "token1_symbol": symbol1,
                            "token0_decimals": token0_data["decimals"],
                            "token1_decimals": token1_data["decimals"],
                            "fee_bps": dex_info["fee"]
                        })
                        found += 1
                
                elif dex_info["protocol"] == 3:  # V3
                    for fee_bps in dex_info["fees"]:
                        fee_raw = fee_bps * 100  # Convert bps to raw (100 = 0.01%)
                        
                        pool_addr = factory.functions.getPool(addr0, addr1, fee_raw).call()
                        
                        if pool_addr != "0x0000000000000000000000000000000000000000":
                            all_pools.append({
                                "pair_address": pool_addr,
                                "dex_name": dex_name,
                                "protocol": 3,
                                "token0_address": addr0,
                                "token1_address": addr1,
                                "token0_symbol": symbol0,
                                "token1_symbol": symbol1,
                                "token0_decimals": token0_data["decimals"],
                                "token1_decimals": token1_data["decimals"],
                                "fee_bps": fee_bps
                            })
                            found += 1
                
            except Exception as e:
                logger.debug(f"Error checking {symbol0}/{symbol1}: {e}")
                continue
        
        logger.info(f"✅ {dex_name}: Found {found} pools")
    
    # Remove duplicates
    unique_pools = {}
    for pool in all_pools:
        addr = pool["pair_address"].lower()
        if addr not in unique_pools:
            unique_pools[addr] = pool
    
    return list(unique_pools.values())


def main():
    logger.info("\n" + "🔱" * 30)
    logger.info("APEX_OMEGA: Smart Pool Discovery (32-Token Universe)")
    logger.info("🔱" * 30 + "\n")
    
    # Connect
    rpc_url = os.getenv('ALCHEMY_HTTP_1') or os.getenv('PRIVATE_RPC_URL')
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        logger.error("❌ Web3 not connected")
        return
    
    logger.info(f"✅ Connected to Polygon")
    logger.info(f"✅ Block: {w3.eth.block_number:,}\n")
    
    # Scan
    logger.info("⏳ Scanning high-priority token pairs...\n")
    
    pools = scan_smart_pairs(w3)
    
    logger.info(f"\n" + "=" * 70)
    logger.info(f"✅ Discovery Complete: {len(pools)} pools found")
    logger.info("=" * 70)
    
    # Save
    import json
    from datetime import datetime
    
    output_path = Path(__file__).parent / 'data' / 'pools_dynamic.json'
    
    data = {
        "updated_at": int(datetime.now().timestamp()),
        "count": len(pools),
        "token_universe_size": len(POLYGON_TOKEN_UNIVERSE),
        "scan_type": "smart_pairs",
        "pools": pools
    }
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"\n✅ Saved to: {output_path}")
    
    # Stats
    dex_counts = {}
    pair_counts = {}
    
    for pool in pools:
        dex = pool["dex_name"]
        pair = f"{pool['token0_symbol']}/{pool['token1_symbol']}"
        dex_counts[dex] = dex_counts.get(dex, 0) + 1
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    
    logger.info(f"\n📊 By DEX:")
    for dex, count in sorted(dex_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {dex}: {count} pools")
    
    logger.info(f"\n📊 Top 10 Pairs:")
    for pair, count in sorted(pair_counts.items(), key=lambda x: -x[1])[:10]:
        logger.info(f"  {pair}: {count} pools")
    
    logger.info("\n✅ Run complete!")


if __name__ == "__main__":
    main()
