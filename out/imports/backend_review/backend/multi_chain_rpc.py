"""
Multi-Chain RPC Health Monitor
Per-chain RPC selection + health checking with automatic failover.
Each chain is fully independent — no cross-chain mixing.
"""

import os
import time
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone
from web3 import Web3
from web3.providers import HTTPProvider

from chain_config import CHAINS, get_all_chain_ids, get_rpc_url

logger = logging.getLogger(__name__)


class ChainRPCMonitor:
    """Health monitor for a single chain's RPC endpoints."""

    def __init__(self, chain_id: int):
        cfg = CHAINS[chain_id]
        self.chain_id   = chain_id
        self.chain_name = cfg["display"]

        # Build candidate URL list: env vars first, then public fallbacks
        urls: Dict[str, str] = {}
        for var in cfg.get("rpc_env_vars", []):
            url = os.getenv(var, "").strip()
            if url:
                urls[var] = url
        for i, pub in enumerate(cfg.get("public_rpcs", [])):
            urls[f"public_{i}"] = pub

        self.endpoints: Dict[str, str] = urls
        self.health_data: Dict[str, Dict] = {}
        self.current_best: Optional[str] = None
        self.last_scan: Optional[datetime] = None

    def test_endpoint(self, name: str, url: str) -> Optional[Dict]:
        t0 = time.time()
        try:
            w3 = Web3(HTTPProvider(url, request_kwargs={"timeout": 5}))
            if not w3.is_connected():
                return {"name": name, "url": url, "status": "down", "error": "not connected",
                        "last_check": datetime.now(timezone.utc)}

            latency_ms = (time.time() - t0) * 1000

            # Verify chain
            chain_id = w3.eth.chain_id
            if chain_id != self.chain_id:
                logger.warning(
                    f"[RPC/{self.chain_name}] {name}: wrong chain {chain_id} (want {self.chain_id})"
                )
                return None

            block = w3.eth.block_number
            return {
                "name":        name,
                "url":         url,
                "status":      "healthy",
                "latency_ms":  latency_ms,
                "block":       block,
                "chain_id":    chain_id,
                "last_check":  datetime.now(timezone.utc),
            }
        except Exception as e:
            return {"name": name, "url": url, "status": "down", "error": str(e)[:100],
                    "last_check": datetime.now(timezone.utc)}

    def scan(self) -> List[Dict]:
        results = []
        for name, url in self.endpoints.items():
            r = self.test_endpoint(name, url)
            if r:
                results.append(r)
                self.health_data[name] = r

        healthy = [r for r in results if r.get("status") == "healthy"]
        if not healthy:
            logger.error(f"[RPC/{self.chain_name}] ❌ ALL endpoints down!")
            self.last_scan = datetime.now(timezone.utc)
            return []

        max_block = max(n["block"] for n in healthy)
        healthy.sort(key=lambda x: (-x["block"], x["latency_ms"]))
        self.current_best = healthy[0]["name"]
        self.last_scan = datetime.now(timezone.utc)

        logger.info(
            f"[RPC/{self.chain_name}] best={self.current_best} "
            f"({healthy[0]['latency_ms']:.0f}ms, block={healthy[0]['block']}) "
            f"| {len(healthy)}/{len(self.endpoints)} healthy"
        )
        return healthy

    def get_best_url(self) -> Optional[str]:
        if not self.current_best:
            self.scan()
        if not self.current_best:
            return None
        return self.health_data.get(self.current_best, {}).get("url")

    def get_web3(self) -> Optional[Web3]:
        url = self.get_best_url()
        if not url:
            return None
        return Web3(HTTPProvider(url, request_kwargs={"timeout": 15}))

    def summary(self) -> Dict:
        return {
            "chain_id":      self.chain_id,
            "chain_name":    self.chain_name,
            "current_best":  self.current_best,
            "last_scan":     self.last_scan.isoformat() if self.last_scan else None,
            "endpoints":     self.health_data,
            "healthy_count": sum(1 for d in self.health_data.values() if d.get("status") == "healthy"),
            "total":         len(self.endpoints),
        }


class MultiChainRPCMonitor:
    """Aggregates per-chain RPC monitors for all 10 chains."""

    def __init__(self, chain_ids: Optional[List[int]] = None):
        self.chain_ids = chain_ids or get_all_chain_ids()
        self.monitors: Dict[int, ChainRPCMonitor] = {
            cid: ChainRPCMonitor(cid) for cid in self.chain_ids
        }

    def scan_chain(self, chain_id: int) -> List[Dict]:
        return self.monitors[chain_id].scan()

    def scan_all(self) -> Dict[int, List[Dict]]:
        results = {}
        for cid, mon in self.monitors.items():
            try:
                results[cid] = mon.scan()
            except Exception as e:
                logger.error(f"[MultiChainRPC] chain {cid} scan error: {e}")
                results[cid] = []
        return results

    def get_web3(self, chain_id: int) -> Optional[Web3]:
        return self.monitors[chain_id].get_web3()

    def get_best_url(self, chain_id: int) -> Optional[str]:
        return self.monitors[chain_id].get_best_url()

    def all_summaries(self) -> Dict[int, Dict]:
        return {cid: mon.summary() for cid, mon in self.monitors.items()}

    def chain_summary(self, chain_id: int) -> Dict:
        return self.monitors[chain_id].summary()


# ── Singleton ────────────────────────────────────────────────

_monitor: Optional[MultiChainRPCMonitor] = None


def get_multi_chain_rpc() -> MultiChainRPCMonitor:
    global _monitor
    if _monitor is None:
        _monitor = MultiChainRPCMonitor()
    return _monitor


async def periodic_multi_chain_rpc_scan(interval_minutes: int = 10):
    """Background task: scan all chain RPCs every N minutes."""
    mon = get_multi_chain_rpc()
    while True:
        try:
            logger.info("[MultiChainRPC] periodic scan starting…")
            mon.scan_all()
        except Exception as e:
            logger.error(f"[MultiChainRPC] periodic scan error: {e}")
        await asyncio.sleep(interval_minutes * 60)
