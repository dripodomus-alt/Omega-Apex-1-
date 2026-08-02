"""
DefiLlama API Integration for Pool TVL & Metadata
Fixed: Correct endpoint paths and Polygon filtering
"""

import logging
import httpx
from typing import Dict, List, Optional
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# DefiLlama FREE tier API (no auth required)
DEFILLAMA_BASE_URL = "https://api.llama.fi"

class DefiLlamaPoolDiscovery:
    """
    Fetch pool metadata, TVL, and volume data from DefiLlama.
    
    Fixed:
    - Correct endpoint paths for free tier
    - Proper Polygon chain filtering
    - Comprehensive error handling
    """
    
    def __init__(self):
        self.base_url = DEFILLAMA_BASE_URL
        self.timeout = httpx.Timeout(30.0)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _make_request(self, endpoint: str) -> Dict:
        """Make HTTP request with retry logic."""
        try:
            url = f"{self.base_url}{endpoint}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                
                if response.status_code == 404:
                    logger.error(f"DefiLlama endpoint not found: {endpoint}")
                    raise ValueError(f"Endpoint not found: {endpoint}")
                elif response.status_code == 429:
                    logger.warning("DefiLlama rate limit exceeded")
                    raise ValueError("Rate limit exceeded")
                elif response.status_code >= 500:
                    logger.error(f"DefiLlama server error: {response.status_code}")
                    raise ValueError(f"Server error: {response.status_code}")
                
                response.raise_for_status()
                return response.json()
        
        except httpx.TimeoutException:
            logger.error(f"Request timeout to {endpoint}")
            raise ValueError("Request timeout")
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {str(e)}")
            raise
    
    async def get_pools(self) -> List[Dict]:
        """
        Get all pools from DefiLlama.
        
        FIXED: Correct endpoint path for free tier
        """
        logger.info("🦙 Fetching pools from DefiLlama...")
        
        try:
            # FIXED: Free tier uses /pools (not /api/pools)
            data = await self._make_request("/pools")
            
            # DefiLlama returns {"data": [pools]} format
            if isinstance(data, dict) and "data" in data:
                pools = data["data"]
            elif isinstance(data, list):
                pools = data
            else:
                logger.warning(f"Unexpected pools response format: {type(data)}")
                return []
            
            logger.info(f"✅ DefiLlama returned {len(pools)} total pools")
            return pools
        
        except Exception as e:
            logger.error(f"Failed to fetch DefiLlama pools: {e}")
            return []
    
    async def get_polygon_pools(self, min_tvl: float = 10000) -> List[Dict]:
        """
        Get Polygon pools with TVL filtering.
        
        FIXED: Proper Polygon chain filtering and TVL thresholds
        """
        try:
            all_pools = await self.get_pools()
            
            # Filter for Polygon pools with meaningful TVL
            polygon_pools = [
                pool for pool in all_pools
                if pool.get('chain', '').lower() == 'polygon'
                and pool.get('tvlUsd', 0) >= min_tvl
            ]
            
            logger.info(
                f"✅ DefiLlama: {len(polygon_pools)} Polygon pools "
                f"with TVL >= ${min_tvl:,.0f}"
            )
            return polygon_pools
        
        except Exception as e:
            logger.error(f"Failed to get Polygon pools: {e}")
            return []
    
    async def get_dex_overview(self, chain: str = "polygon") -> Dict:
        """
        Get DEX overview for Polygon.
        
        Endpoint: /overview/dexs/{chain}
        """
        try:
            endpoint = f"/overview/dexs/{chain}"
            data = await self._make_request(endpoint)
            logger.info(f"Retrieved DEX overview for {chain}")
            return data
        except Exception as e:
            logger.error(f"Failed to get DEX overview: {e}")
            return {}
    
    async def get_protocol_tvl(self, protocol_name: str) -> float:
        """
        Get total TVL for a specific protocol.
        """
        try:
            endpoint = f"/tvl/{protocol_name}"
            tvl = await self._make_request(endpoint)
            return float(tvl) if tvl else 0.0
        except Exception as e:
            logger.debug(f"Failed to get TVL for {protocol_name}: {e}")
            return 0.0


# Global instance
_defillama_discovery = None

def get_defillama_discovery() -> DefiLlamaPoolDiscovery:
    """Get or create DefiLlama discovery singleton."""
    global _defillama_discovery
    if _defillama_discovery is None:
        _defillama_discovery = DefiLlamaPoolDiscovery()
    return _defillama_discovery
