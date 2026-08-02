"""
Real Web3 Pool Data Fetcher
Fetches actual reserves, liquidity, and weights from blockchain
NO MOCK DATA - all data is fetched via Web3
"""
import os
import logging
import math
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv

# CRITICAL: Load .env at module import
load_dotenv(override=True)

from pool_abis import (
    UNISWAP_V2_PAIR_ABI,
    UNISWAP_V3_POOL_ABI,
    BALANCER_VAULT_ABI,
    BALANCER_POOL_ABI,
    BALANCER_VAULT_ADDRESS,
    ERC20_ABI
)

logger = logging.getLogger(__name__)

# Verify RPC loaded
_rpc = os.getenv('POLYGON_RPC_URL')
logger.info(f"🔗 RPC URL loaded: {_rpc[:60] if _rpc else 'NOT SET'}...")


@dataclass
class PoolReserveData:
    """Real pool reserve data from blockchain"""
    reserve0: float
    reserve1: float
    reserve0_raw: int  # Raw units
    reserve1_raw: int  # Raw units
    token0_decimals: int
    token1_decimals: int
    sqrt_price_x96: int = 0  # V3 only
    tick: int = 0  # V3 only
    liquidity: int = 0  # V3 only
    weight0: float = 0.5  # Balancer only
    weight1: float = 0.5  # Balancer only
    fee: int = 0
    data_source: str = "web3"


class Web3PoolFetcher:
    """
    Fetches real pool data from blockchain
    Supports UniswapV2, UniswapV3, and Balancer
    """
    
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.balancer_vault = self.w3.eth.contract(
            address=Web3.to_checksum_address(BALANCER_VAULT_ADDRESS),
            abi=BALANCER_VAULT_ABI
        )
    
    def fetch_v2_reserves(
        self,
        pool_address: str,
        token0_address: str,
        token1_address: str
    ) -> Optional[PoolReserveData]:
        """
        Fetch real reserves from UniswapV2-compatible pool
        Calls getReserves() on-chain
        """
        try:
            pool_address = Web3.to_checksum_address(pool_address)
            pool = self.w3.eth.contract(address=pool_address, abi=UNISWAP_V2_PAIR_ABI)
            
            # Fetch reserves
            reserves = pool.functions.getReserves().call()
            reserve0_raw = reserves[0]
            reserve1_raw = reserves[1]
            
            # Fetch token decimals
            token0_decimals = self._get_token_decimals(token0_address)
            token1_decimals = self._get_token_decimals(token1_address)
            
            # Convert to human-readable units
            reserve0 = reserve0_raw / (10 ** token0_decimals)
            reserve1 = reserve1_raw / (10 ** token1_decimals)
            
            logger.debug(f"V2 Pool {pool_address[:10]}: R0={reserve0:.2f}, R1={reserve1:.2f}")
            
            return PoolReserveData(
                reserve0=reserve0,
                reserve1=reserve1,
                reserve0_raw=reserve0_raw,
                reserve1_raw=reserve1_raw,
                token0_decimals=token0_decimals,
                token1_decimals=token1_decimals,
                fee=3000,  # V2 standard is 0.3%
                data_source="web3_v2"
            )
            
        except Exception as e:
            logger.warning(f"Failed to fetch V2 reserves for {pool_address[:10]}: {e}")
            return None
    
    def fetch_v3_state(
        self,
        pool_address: str,
        token0_address: str,
        token1_address: str
    ) -> Optional[PoolReserveData]:
        """
        Fetch real state from UniswapV3 pool
        Calls slot0() and liquidity() on-chain
        """
        try:
            pool_address = Web3.to_checksum_address(pool_address)
            pool = self.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
            
            # Fetch slot0 (price and tick)
            slot0 = pool.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            tick = slot0[1]
            
            # Fetch liquidity
            liquidity = pool.functions.liquidity().call()
            
            # Fetch fee
            fee = pool.functions.fee().call()
            
            # Fetch token decimals
            token0_decimals = self._get_token_decimals(token0_address)
            token1_decimals = self._get_token_decimals(token1_address)
            
            # Calculate virtual reserves from liquidity and price
            # For V3, we approximate reserves from liquidity and current price
            if sqrt_price_x96 > 0:
                # Price = (sqrtPriceX96 / 2^96)^2
                price = (sqrt_price_x96 / (2 ** 96)) ** 2
                
                # Approximate reserves from liquidity
                # L = sqrt(x * y), where x and y are virtual reserves
                # For concentrated liquidity, we use liquidity as proxy
                sqrt_liquidity = math.sqrt(liquidity) if liquidity > 0 else 0
                
                # Virtual reserve calculations
                reserve1_raw = int(sqrt_liquidity * sqrt_price_x96 / (2 ** 96))
                reserve0_raw = int(sqrt_liquidity * (2 ** 96) / sqrt_price_x96) if sqrt_price_x96 > 0 else 0
                
                reserve0 = reserve0_raw / (10 ** token0_decimals)
                reserve1 = reserve1_raw / (10 ** token1_decimals)
            else:
                reserve0, reserve1 = 0, 0
                reserve0_raw, reserve1_raw = 0, 0
            
            logger.debug(f"V3 Pool {pool_address[:10]}: L={liquidity}, tick={tick}, sqrtPrice={sqrt_price_x96}")
            
            return PoolReserveData(
                reserve0=reserve0,
                reserve1=reserve1,
                reserve0_raw=reserve0_raw,
                reserve1_raw=reserve1_raw,
                token0_decimals=token0_decimals,
                token1_decimals=token1_decimals,
                sqrt_price_x96=sqrt_price_x96,
                tick=tick,
                liquidity=liquidity,
                fee=fee,
                data_source="web3_v3"
            )
            
        except Exception as e:
            logger.warning(f"Failed to fetch V3 state for {pool_address[:10]}: {e}")
            return None
    
    def fetch_balancer_pool(
        self,
        pool_address: str,
        token0_address: str,
        token1_address: str
    ) -> Optional[PoolReserveData]:
        """
        Fetch real balances and weights from Balancer pool
        Calls getPoolTokens() and getNormalizedWeights() on-chain
        """
        try:
            pool_address = Web3.to_checksum_address(pool_address)
            pool = self.w3.eth.contract(address=pool_address, abi=BALANCER_POOL_ABI)
            
            # Get pool ID
            pool_id = pool.functions.getPoolId().call()
            
            # Get tokens and balances from vault
            pool_tokens_data = self.balancer_vault.functions.getPoolTokens(pool_id).call()
            tokens = pool_tokens_data[0]
            balances = pool_tokens_data[1]
            
            # Get normalized weights
            try:
                weights = pool.functions.getNormalizedWeights().call()
            except:
                # Some Balancer pools don't have weights (stable pools)
                weights = [10**18, 10**18]  # Equal weights as fallback
            
            # Get fee
            try:
                fee_percentage = pool.functions.getSwapFeePercentage().call()
                fee_bps = int(fee_percentage / 10**14)  # Convert from 18 decimals to bps
            except:
                fee_bps = 30  # Default 0.3%
            
            # Find token0 and token1 in the pool
            token0_checksum = Web3.to_checksum_address(token0_address)
            token1_checksum = Web3.to_checksum_address(token1_address)
            
            token0_index = None
            token1_index = None
            
            for i, token in enumerate(tokens):
                if token == token0_checksum:
                    token0_index = i
                if token == token1_checksum:
                    token1_index = i
            
            if token0_index is None or token1_index is None:
                logger.warning(f"Tokens not found in Balancer pool {pool_address[:10]}")
                return None
            
            # Get balances and weights for our tokens
            reserve0_raw = balances[token0_index]
            reserve1_raw = balances[token1_index]
            weight0_raw = weights[token0_index] if token0_index < len(weights) else 10**18
            weight1_raw = weights[token1_index] if token1_index < len(weights) else 10**18
            
            # Fetch token decimals
            token0_decimals = self._get_token_decimals(token0_address)
            token1_decimals = self._get_token_decimals(token1_address)
            
            # Convert to human-readable
            reserve0 = reserve0_raw / (10 ** token0_decimals)
            reserve1 = reserve1_raw / (10 ** token1_decimals)
            weight0 = weight0_raw / 10**18  # Weights are in 18 decimals
            weight1 = weight1_raw / 10**18
            
            logger.debug(f"Balancer Pool {pool_address[:10]}: R0={reserve0:.2f}, R1={reserve1:.2f}, W0={weight0:.3f}, W1={weight1:.3f}")
            
            return PoolReserveData(
                reserve0=reserve0,
                reserve1=reserve1,
                reserve0_raw=reserve0_raw,
                reserve1_raw=reserve1_raw,
                token0_decimals=token0_decimals,
                token1_decimals=token1_decimals,
                weight0=weight0,
                weight1=weight1,
                fee=fee_bps,
                data_source="web3_balancer"
            )
            
        except Exception as e:
            logger.warning(f"Failed to fetch Balancer pool {pool_address[:10]}: {e}")
            return None
    
    def _get_token_decimals(self, token_address: str) -> int:
        """Fetch token decimals from contract"""
        try:
            token_address = Web3.to_checksum_address(token_address)
            token = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            decimals = token.functions.decimals().call()
            return decimals
        except:
            # Default to 18 if fetch fails
            return 18
    
    def fetch_pool_data(
        self,
        pool_address: str,
        token0_address: str,
        token1_address: str,
        protocol: int
    ) -> Optional[PoolReserveData]:
        """
        Fetch pool data based on protocol type
        Returns real blockchain data or None if fetch fails
        """
        if protocol == 2:  # V2
            return self.fetch_v2_reserves(pool_address, token0_address, token1_address)
        elif protocol == 3:  # V3 or Algebra
            return self.fetch_v3_state(pool_address, token0_address, token1_address)
        elif protocol == 5:  # Balancer
            return self.fetch_balancer_pool(pool_address, token0_address, token1_address)
        elif protocol == 4:  # Stableswap (treat as V2 for now)
            return self.fetch_v2_reserves(pool_address, token0_address, token1_address)
        else:
            logger.warning(f"Unknown protocol {protocol}, trying V2")
            return self.fetch_v2_reserves(pool_address, token0_address, token1_address)
