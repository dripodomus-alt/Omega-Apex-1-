"""
1inch API v6.1 Integration for Polygon Pool Discovery
Fixed: Proper Bearer token auth and v6.1 endpoints
"""

import os
import logging
import httpx
from typing import Dict, List, Optional
import asyncio
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# 1inch API v6.1 (Polygon chain ID: 137)
ONEINCH_BASE_URL = "https://api.1inch.com"
ONEINCH_API_VERSION = "v6.1"
POLYGON_CHAIN_ID = 137

class OneInchPoolDiscovery:
    """
    Discover liquidity pools on Polygon via 1inch API v6.1
    
    Fixed:
    - Upgraded from v5.2 to v6.1 endpoints
    - Proper Bearer token authentication
    - Correct endpoint paths
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ONEINCH_API_KEY')
        if not self.api_key:
            logger.warning("1inch API key not configured. Rate limits will be restrictive.")
        
        self.base_url = ONEINCH_BASE_URL
        self.timeout = httpx.Timeout(30.0)
        self.discovered_pools = {}
    
    def _get_headers(self) -> Dict[str, str]:
        """Generate request headers with Bearer token authentication."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    async def discover_liquidity_sources(self) -> Dict[str, List[Dict]]:
        """
        Get all liquidity sources tracked by 1inch on Polygon.
        
        FIXED: Now uses v6.1 endpoint with proper auth
        """
        logger.info("🔍 Discovering liquidity sources via 1inch API v6.1...")
        
        try:
            # FIXED: Updated to v6.1 endpoint path
            endpoint = f"{self.base_url}/swap/{ONEINCH_API_VERSION}/{POLYGON_CHAIN_ID}/liquidity-sources"
            headers = self._get_headers()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint, headers=headers)
                
                # Handle authentication errors
                if response.status_code == 401:
                    logger.error("1inch API authentication failed. Check your API key.")
                    return {}
                elif response.status_code == 429:
                    logger.warning("1inch rate limit exceeded. Consider upgrading your tier.")
                    return {}
                
                response.raise_for_status()
                data = response.json()
                
                if "protocols" in data:
                    protocols = data.get('protocols', [])
                    logger.info(f"✅ 1inch tracks {len(protocols)} protocols on Polygon")
                    
                    # Group by protocol
                    protocol_pools = {}
                    for protocol in protocols:
                        protocol_id = protocol.get('id', 'unknown')
                        protocol_pools[protocol_id] = protocol
                    
                    self.discovered_pools = protocol_pools
                    return protocol_pools
                else:
                    logger.warning(f"Unexpected response format: {data}")
                    return {}
        
        except httpx.HTTPError as e:
            logger.error(f"1inch API HTTP error: {e}")
            return {}
        except Exception as e:
            logger.error(f"Failed to fetch 1inch liquidity sources: {e}")
            return {}
    
    async def get_swap_quote(self, src_token: str, dst_token: str, amount: str) -> Optional[Dict]:
        """
        Get swap quote for a token pair.
        
        FIXED: Now uses v6.1 quote endpoint with proper auth
        """
        try:
            endpoint = f"{self.base_url}/swap/{ONEINCH_API_VERSION}/{POLYGON_CHAIN_ID}/quote"
            headers = self._get_headers()
            
            params = {
                'src': src_token,
                'dst': dst_token,
                'amount': amount,
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint, headers=headers, params=params)
                
                if response.status_code == 401:
                    logger.error("1inch API authentication failed")
                    return None
                elif response.status_code == 429:
                    logger.warning("1inch rate limit exceeded")
                    return None
                
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            logger.debug(f"Failed to get 1inch quote: {e}")
            return None
    
    def get_top_tokens(self, limit: int = 50) -> List[str]:
        """Get top tokens by volume on Polygon."""
        # Known top Polygon tokens
        top_tokens = [
            "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
            "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
            "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC.e
            "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
            "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # DAI
            "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
            "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",  # LINK
            "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",  # AAVE
        ]
        return top_tokens[:limit]


# Global instance
_oneinch_discovery = None

def get_oneinch_discovery(api_key: str = None) -> OneInchPoolDiscovery:
    """Get or create 1inch discovery singleton."""
    global _oneinch_discovery
    if _oneinch_discovery is None:
        _oneinch_discovery = OneInchPoolDiscovery(api_key)
    return _oneinch_discovery
