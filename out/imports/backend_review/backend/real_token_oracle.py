"""
REAL TOKEN PRICE ORACLE - NO MORE PLACEHOLDER BULLSHIT
Fetches actual prices for ALL tokens from DEXScreener API
"""

import requests
import os
import logging
from typing import Dict
import time

logger = logging.getLogger(__name__)


class RealTokenPriceOracle:
    """
    Fetches REAL token prices from DEXScreener API
    No more hardcoded placeholder crap
    """
    
    def __init__(self):
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 60  # Cache for 60 seconds
        self.base_url = "https://api.dexscreener.com/latest/dex"
    
    def get_token_price_usd(self, token_address: str, chain: str = "polygon") -> float:
        """
        Get REAL price for ANY token from DEXScreener
        
        Args:
            token_address: Token contract address
            chain: Blockchain (polygon, ethereum, etc)
        
        Returns:
            float: USD price or 0 if not found
        """
        if not token_address or token_address == "0x0000000000000000000000000000000000000000":
            return 0.0
        
        token_address = token_address.lower()
        
        # Check cache
        cache_key = f"{chain}:{token_address}"
        if cache_key in self.cache:
            if time.time() - self.cache_time[cache_key] < self.cache_ttl:
                return self.cache[cache_key]
        
        try:
            # DEXScreener API endpoint
            url = f"{self.base_url}/tokens/{token_address}"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                # DEXScreener returns pairs for this token
                if 'pairs' in data and len(data['pairs']) > 0:
                    # Get the pair with highest liquidity
                    pairs = data['pairs']
                    
                    # Filter for Polygon chain
                    polygon_pairs = [p for p in pairs if p.get('chainId') == chain]
                    
                    if polygon_pairs:
                        # Sort by liquidity (USD)
                        sorted_pairs = sorted(
                            polygon_pairs,
                            key=lambda x: float(x.get('liquidity', {}).get('usd', 0)),
                            reverse=True
                        )
                        
                        best_pair = sorted_pairs[0]
                        price_usd = float(best_pair.get('priceUsd', 0))
                        
                        # Cache it
                        self.cache[cache_key] = price_usd
                        self.cache_time[cache_key] = time.time()
                        
                        logger.debug(f"Price for {token_address[:10]}: ${price_usd:.6f}")
                        return price_usd
                
                # Token not found on DEXScreener
                logger.debug(f"No price data for {token_address[:10]}")
                
                # Cache 0 to avoid repeated API calls
                self.cache[cache_key] = 0.0
                self.cache_time[cache_key] = time.time()
                return 0.0
            
            else:
                logger.warning(f"DEXScreener API error: {response.status_code}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error fetching price for {token_address[:10]}: {e}")
            return 0.0
    
    def get_multiple_prices(self, token_addresses: list, chain: str = "polygon") -> Dict[str, float]:
        """
        Batch fetch prices for multiple tokens
        
        Returns:
            dict: {token_address: price_usd}
        """
        prices = {}
        
        # DEXScreener supports up to 30 addresses at once
        batch_size = 30
        total_batches = (len(token_addresses) + batch_size - 1) // batch_size
        
        logger.info(f"📡 Fetching prices for {len(token_addresses)} tokens in {total_batches} batches...")
        
        for batch_num, i in enumerate(range(0, len(token_addresses), batch_size), 1):
            batch = token_addresses[i:i+batch_size]
            
            # Build query string
            addresses_str = ','.join([addr.lower() for addr in batch if addr])
            
            try:
                url = f"{self.base_url}/tokens/{addresses_str}"
                response = requests.get(url, timeout=15)  # Increased timeout
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'pairs' in data and data['pairs'] is not None:
                        # Group pairs by token
                        for pair in data['pairs']:
                            if pair.get('chainId') != chain:
                                continue
                            
                            # Check which token in the pair we're looking for
                            base_token = pair.get('baseToken', {}).get('address', '').lower()
                            quote_token = pair.get('quoteToken', {}).get('address', '').lower()
                            
                            if base_token in [addr.lower() for addr in batch]:
                                price = float(pair.get('priceUsd', 0))
                                if base_token not in prices or price > 0:
                                    prices[base_token] = price
                            
                            if quote_token in [addr.lower() for addr in batch]:
                                # Calculate quote token price
                                price_native = float(pair.get('priceNative', 0))
                                if price_native > 0 and base_token in prices:
                                    prices[quote_token] = prices[base_token] / price_native
                    else:
                        logger.debug(f"No pairs found for batch {batch_num}/{total_batches}")
                elif response.status_code == 429:
                    # Rate limited - wait longer
                    logger.warning(f"Rate limited on batch {batch_num}/{total_batches}, waiting 2s...")
                    time.sleep(2)
                    continue
                else:
                    logger.debug(f"API returned {response.status_code} for batch {batch_num}/{total_batches}")
                
                # Rate limit: 0.5s between requests (max 2 req/s)
                if batch_num % 10 == 0:
                    logger.info(f"  Progress: {batch_num}/{total_batches} batches ({len(prices)} prices found)")
                time.sleep(0.5)
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on batch {batch_num}/{total_batches}, skipping...")
                continue
            except Exception as e:
                logger.warning(f"Batch {batch_num}/{total_batches} error: {str(e)[:100]}")
                continue
        
        return prices


# Global instance
_price_oracle = None

def get_real_price_oracle() -> RealTokenPriceOracle:
    """Get or create real price oracle"""
    global _price_oracle
    if _price_oracle is None:
        _price_oracle = RealTokenPriceOracle()
    return _price_oracle


if __name__ == "__main__":
    # Test the oracle
    oracle = get_real_price_oracle()
    
    # Test with known tokens on Polygon
    test_tokens = {
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "LINK": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
    }
    
    print("Testing Real Price Oracle:")
    print("="*80)
    
    for symbol, address in test_tokens.items():
        price = oracle.get_token_price_usd(address)
        print(f"{symbol:8} ({address[:10]}...): ${price:>12,.2f}")
    
    print()
    print("✅ Real prices fetched from DEXScreener API")
