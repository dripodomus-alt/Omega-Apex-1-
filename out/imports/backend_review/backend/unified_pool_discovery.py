"""
Unified Pool Discovery Engine
Combines 1inch + DefiLlama + Local Database + Curve + Balancer
for comprehensive per-chain pool coverage.

Now chain-aware: each chain runs isolated discovery.
No cross-chain pool merging.
"""

import logging
import asyncio
import time
from typing import Dict, List, Set, Optional
from oneinch_discovery import get_oneinch_discovery
from defillama_discovery import get_defillama_discovery

logger = logging.getLogger(__name__)


class UnifiedPoolDiscovery:
    """
    INSTITUTIONAL-GRADE pool discovery combining multiple sources.

    Sources:
    1. 1inch API       → 100+ DEXs, real-time routing
    2. DefiLlama       → TVL, volume, APY metadata
    3. Local database  → Cached pools for fast startup
    4. Curve Finance   → Stable + crypto pools (per chain)
    5. Balancer V2     → Weighted + stable pools (per chain)

    Each source is scoped to a single chain.
    Output: comprehensive pool list with EXACT reserves via Multicall3
    """

    def __init__(self, oneinch_api_key: str = None):
        self.oneinch  = get_oneinch_discovery(oneinch_api_key)
        self.defillama = get_defillama_discovery()
        self.all_pools: Dict[str, Dict] = {}
        self.pool_metadata: Dict[str, Dict] = {}

    def discover_all_pools(self, use_cache: bool = True) -> Dict[str, Dict]:
        """
        Discover ALL liquidity pools on Polygon (legacy single-chain path).
        The multi-chain path goes through multi_chain_discovery.py.

        Returns:
            { "0xpool_address": { pool_data } }
        """
        start_time = time.time()
        logger.info("🌐 Starting unified pool discovery (Polygon — 1inch + Curve + Balancer + Database)…")

        discovered: Dict[str, Dict] = {}

        # ── Source 1: 1inch protocol list ────────────────────────────────────
        logger.info("📊 Source 1/3: 1inch API…")
        # Async path — skipped here; arbitrage_engine loads from DB
        logger.info("  ⏭️  Skipping 1inch discovery (using database pools + Curve/Balancer)")

        # ── Source 2: Curve + Balancer on Polygon ────────────────────────────
        logger.info("📊 Source 2/3: Curve + Balancer (Polygon)…")
        try:
            from chain_config import get_chain
            from multi_chain_rpc import get_multi_chain_rpc
            from curve_balancer_discovery import get_curve_balancer_discovery

            polygon_cfg = get_chain(137)
            mc_rpc = get_multi_chain_rpc()
            w3 = mc_rpc.get_web3(137)

            if w3:
                cb = get_curve_balancer_discovery(w3, polygon_cfg)
                cb_pools = cb.discover_all()
                for pool in cb_pools:
                    addr = pool["pair_address"].lower()
                    discovered[addr] = pool
                logger.info(f"  ✅ Curve+Balancer: {len(cb_pools)} pools")
            else:
                logger.warning("  ⚠️  No Polygon web3 connection for Curve/Balancer discovery")
        except Exception as e:
            logger.warning(f"  ⚠️  Curve/Balancer discovery error: {e}")

        # ── Source 3: Local database (merged in by arbitrage_engine.py) ──────
        logger.info("📊 Source 3/3: Local database (loaded by arbitrage engine)")

        elapsed = time.time() - start_time
        logger.info(f"✅ Discovery complete: {len(discovered)} unique pools in {elapsed:.1f}s")

        self.all_pools = discovered
        return discovered

    def get_pool_metadata(self, pool_address: str) -> Dict:
        if pool_address in self.pool_metadata:
            return self.pool_metadata[pool_address]
        metadata = self.defillama.enrich_pool_data(pool_address)
        self.pool_metadata[pool_address] = metadata
        return metadata

    def get_top_pools_by_tvl(self, limit: int = 100) -> List[Dict]:
        pools_list = list(self.all_pools.values())
        pools_list.sort(key=lambda x: x.get("tvl_usd", 0), reverse=True)
        return pools_list[:limit]


# Global instance
_unified_discovery: Optional[UnifiedPoolDiscovery] = None


def get_unified_discovery(oneinch_api_key: str = None) -> UnifiedPoolDiscovery:
    """Get or create unified discovery singleton."""
    global _unified_discovery
    if _unified_discovery is None:
        _unified_discovery = UnifiedPoolDiscovery(oneinch_api_key)
    return _unified_discovery
