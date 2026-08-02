"""
APEX_OMEGA Price Discovery Engine
Comprehensive Ask/Bid Price Listing Across ALL Pools
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class PriceQuote:
    """Single price quote from a pool"""
    pool_address: str
    dex_name: str
    dex_id: int
    protocol: int
    token_pair: str  # "WMATIC/USDC"
    base_token: str  # Token address
    quote_token: str  # Token address
    base_symbol: str
    quote_symbol: str
    
    # Ask/Bid prices
    ask_price: float  # Buy price (how much quote_token per base_token when BUYING base)
    bid_price: float  # Sell price (how much quote_token per base_token when SELLING base)
    
    # Pool depth
    base_reserve: float  # Normalized reserve of base token
    quote_reserve: float  # Normalized reserve of quote token
    tvl_usd: float
    
    # Fees
    fee_bps: int  # Fee in basis points (30 = 0.30%)
    
    # Pool metadata
    weight0: float = 0.5
    weight1: float = 0.5
    sqrt_price_x96: int = 0
    tick: int = 0
    liquidity: float = 0


class PriceDiscoveryEngine:
    """
    Builds comprehensive ask/bid price matrix across ALL pools
    Enables proper arbitrage discovery by comparing prices across DEXes
    """
    
    def __init__(self):
        self.price_matrix: Dict[str, List[PriceQuote]] = defaultdict(list)
        logger.info("🔍 Price Discovery Engine initialized")
    
    def build_price_matrix(self, pools: Dict[str, any]) -> Dict[str, List[PriceQuote]]:
        """
        Build complete ask/bid price matrix for all pools
        
        Args:
            pools: Dictionary of PoolPrice objects from arbitrage_engine
            
        Returns:
            price_matrix: Dict mapping token_pair -> List[PriceQuote]
            
        Example output:
            {
                "WMATIC/USDC": [
                    PriceQuote(pool="QuickSwap V2", ask=0.5010, bid=0.4990, ...),
                    PriceQuote(pool="UniSwap V3", ask=0.5008, bid=0.4992, ...),
                    PriceQuote(pool="SushiSwap", ask=0.5012, bid=0.4988, ...),
                ],
                "WETH/USDC": [...]
            }
        """
        self.price_matrix.clear()
        
        for pool_key, pool in pools.items():
            try:
                # Create normalized token pair key (alphabetically sorted)
                tokens = sorted([
                    (pool.token0.lower(), pool.token0_symbol),
                    (pool.token1.lower(), pool.token1_symbol)
                ])
                token_pair = f"{tokens[0][1]}/{tokens[1][1]}"
                
                # Calculate ask/bid prices
                # ASK (buy price) = price you pay to BUY base token (includes fee)
                # BID (sell price) = price you receive when SELLING base token (after fee)
                
                # For token0/token1 pair:
                # - Buying token0: pay token1 (ask)
                # - Selling token0: receive token1 (bid)
                
                if pool.reserve0 == 0 or pool.reserve1 == 0:
                    continue
                
                # Spot price (mid-price without fees)
                # How much token1 per token0
                spot_price = pool.reserve1 / pool.reserve0
                
                # Fee adjustment
                fee_multiplier = (10000 + pool.fee // 100) / 10000  # e.g., 30 bps -> 1.003
                fee_divisor = (10000 - pool.fee // 100) / 10000      # e.g., 30 bps -> 0.997
                
                # ASK: When buying token0, you pay more (spot + fee)
                ask_price = spot_price * fee_multiplier
                
                # BID: When selling token0, you receive less (spot - fee)
                bid_price = spot_price * fee_divisor
                
                # Create quote for token0/token1 direction
                quote = PriceQuote(
                    pool_address=pool.pool_address,
                    dex_name=pool.dex_name,
                    dex_id=pool.dex_id,
                    protocol=pool.protocol,
                    token_pair=token_pair,
                    base_token=pool.token0,
                    quote_token=pool.token1,
                    base_symbol=pool.token0_symbol,
                    quote_symbol=pool.token1_symbol,
                    ask_price=ask_price,
                    bid_price=bid_price,
                    base_reserve=pool.reserve0,
                    quote_reserve=pool.reserve1,
                    tvl_usd=pool.reserve_usd,
                    fee_bps=pool.fee // 100,
                    weight0=pool.weight0,
                    weight1=pool.weight1,
                    sqrt_price_x96=pool.sqrt_price_x96,
                    tick=pool.tick,
                    liquidity=pool.liquidity,
                )
                
                self.price_matrix[token_pair].append(quote)
                
            except Exception as e:
                logger.warning(f"Failed to process pool {pool_key}: {e}")
                continue
        
        # Log summary
        total_quotes = sum(len(quotes) for quotes in self.price_matrix.values())
        logger.info(f"📊 Price Matrix Built: {len(self.price_matrix)} pairs, {total_quotes} quotes")
        
        return self.price_matrix
    
    def find_arbitrage_opportunities(
        self,
        min_spread_bps: int = 10,  # Minimum 0.10% spread to consider
        min_tvl_usd: float = 10000  # Minimum $10k TVL per pool
    ) -> List[Tuple[PriceQuote, PriceQuote, float]]:
        """
        Find arbitrage opportunities by comparing ask/bid across pools
        
        Logic:
            For each token pair:
                - Find pool with LOWEST ask (cheapest place to buy)
                - Find pool with HIGHEST bid (best place to sell)
                - If (highest_bid - lowest_ask) > min_spread: OPPORTUNITY!
        
        Returns:
            List of (buy_quote, sell_quote, spread_bps) tuples
        """
        opportunities = []
        
        for token_pair, quotes in self.price_matrix.items():
            if len(quotes) < 2:
                continue
            
            # Filter by minimum TVL
            valid_quotes = [q for q in quotes if q.tvl_usd >= min_tvl_usd]
            if len(valid_quotes) < 2:
                continue
            
            # Find best buy and sell opportunities across ALL pools
            # Best buy = lowest ask price (cheapest place to BUY)
            best_buy = min(valid_quotes, key=lambda q: q.ask_price)
            
            # Best sell = highest bid price (best place to SELL)
            best_sell = max(valid_quotes, key=lambda q: q.bid_price)
            
            # Calculate cross-pool spread (CRITICAL: This is buy-cheap-sell-expensive spread)
            # Spread = (highest_bid_across_all_pools - lowest_ask_across_all_pools) / lowest_ask
            spread_bps = ((best_sell.bid_price - best_buy.ask_price) / best_buy.ask_price) * 10000
            
            if spread_bps >= min_spread_bps:
                opportunities.append((best_buy, best_sell, spread_bps))
                logger.info(
                    f"💰 Opportunity: {token_pair} | "
                    f"Buy @ {best_buy.dex_name} ({best_buy.ask_price:.6f}) | "
                    f"Sell @ {best_sell.dex_name} ({best_sell.bid_price:.6f}) | "
                    f"Spread: {spread_bps:.2f} bps"
                )
        
        # Sort by spread (highest first)
        opportunities.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"🎯 Found {len(opportunities)} arbitrage opportunities (>{min_spread_bps} bps)")
        
        return opportunities
    
    def get_price_summary(self, token_pair: str = None) -> Dict:
        """
        Get price summary for a specific token pair or all pairs
        
        Returns:
            {
                "WMATIC/USDC": {
                    "pools": 5,
                    "best_ask": 0.5008,
                    "best_bid": 0.4992,
                    "spread_bps": 16,
                    "cheapest_buy_pool": "UniSwap V3",
                    "best_sell_pool": "QuickSwap V2",
                    "avg_price": 0.5000,
                    "all_quotes": [...]
                }
            }
        """
        if token_pair:
            pairs_to_process = {token_pair: self.price_matrix.get(token_pair, [])}
        else:
            pairs_to_process = self.price_matrix
        
        summary = {}
        
        for pair, quotes in pairs_to_process.items():
            if not quotes:
                continue
            
            best_buy = min(quotes, key=lambda q: q.ask_price)
            best_sell = max(quotes, key=lambda q: q.bid_price)
            avg_price = sum(q.ask_price for q in quotes) / len(quotes)
            spread_bps = ((best_sell.bid_price - best_buy.ask_price) / best_buy.ask_price) * 10000
            
            summary[pair] = {
                "pools": len(quotes),
                "best_ask": best_buy.ask_price,
                "best_bid": best_sell.bid_price,
                "spread_bps": spread_bps,
                "cheapest_buy_pool": best_buy.dex_name,
                "best_sell_pool": best_sell.dex_name,
                "avg_price": avg_price,
                "total_tvl_usd": sum(q.tvl_usd for q in quotes),
                "all_quotes": [
                    {
                        "pool": q.dex_name,
                        "ask": q.ask_price,
                        "bid": q.bid_price,
                        "tvl_usd": q.tvl_usd,
                        "fee_bps": q.fee_bps
                    }
                    for q in quotes
                ]
            }
        
        return summary


# Global instance
_price_discovery: Optional[PriceDiscoveryEngine] = None


def get_price_discovery_engine() -> PriceDiscoveryEngine:
    """Get or create price discovery engine"""
    global _price_discovery
    if _price_discovery is None:
        _price_discovery = PriceDiscoveryEngine()
    return _price_discovery
