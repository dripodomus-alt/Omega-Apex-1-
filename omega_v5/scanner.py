# ==============================================================================
# scanner.py  —  Real-time dual-frequency pool-state ingestion loop
# Extracted from Cell 3 of notebooks/omega_v5.ipynb
#
# DynamicAQSMatrixScanner runs two concurrent async tasks:
#   live_state_refresher  — ingests current on-chain pool state over RPC
#   macro_black_scan_loop — evaluates the full cache every macro_interval seconds
#
# The refresher is intentionally read-only. Broadcast and signing are handled
# only by the guarded execution module.
# ==============================================================================

import asyncio
import time
from decimal import Decimal
from typing import Dict, List, Any

from .config import ASSET_MATRIX
from .amm_adapters import quote_pool
from .rpc_layer import DEEP_POOL_REGISTRY, load_live_pool_state


class DynamicAQSMatrixScanner:
    """
    Dual-frequency matrix scanner.

    Attributes
    ----------
    macro_interval : float
        Seconds between deep evaluation sweeps (default: 15 s).
    memory_cache : dict
        Rolling window of pool state updates keyed by pool_id.
    pools : dict
        Current live pool state registry.
    metrics : dict
        Running counters for ticks evaluated and signals caught.
    """

    def __init__(self, assets: List[str] = None, macro_interval: float = 15.0):
        self.assets         = assets or ASSET_MATRIX
        self.macro_interval = macro_interval
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.pools:         Dict[str, Dict[str, Any]] = {}
        self.metrics        = {"ticks_evaluated": 0, "signals_caught": 0}

    def load_live_pools(self, live_pools: Dict[str, Any]):
        """Load externally fetched Chain 137 pool states."""
        self.pools = live_pools

    # ── Async tasks ───────────────────────────────────────────────────────────

    async def live_state_refresher(self):
        """
        Refreshes registered Chain 137 pool states from RPC.

        This is intentionally read-only and live-only. It does not synthesize
        events or mutate reserves with random data.
        """
        print("📡 [LIVE-REFRESH] Mounted Chain 137 live state refresh pipeline...")
        while True:
            current_time = time.time()
            for pool_id in list(self.pools.keys()):
                meta = DEEP_POOL_REGISTRY.get(pool_id)
                if not meta:
                    continue
                fresh = load_live_pool_state(pool_id, meta)
                if not fresh:
                    continue
                self.pools[pool_id] = fresh
                self.memory_cache[pool_id] = {
                    "type": "LIVE_STATE_REFRESH", "pool": fresh, "timestamp": current_time,
                }
                await asyncio.sleep(0.05)
            await asyncio.sleep(max(1.0, self.macro_interval / 2))

    async def macro_black_scan_loop(self, max_ticks: int = 3):
        """
        Evaluates and quotes every cached pool update on `macro_interval` cadence.

        Parameters
        ----------
        max_ticks : int
            Number of macro iterations to run before returning (0 = infinite).
        """
        print(f"🦅 [MACRO-SCANNER] Deep Matrix Black Scan Loop Online. Interval: {self.macro_interval}s.")
        await asyncio.sleep(1.0)

        while max_ticks == 0 or self.metrics["ticks_evaluated"] < max_ticks:
            start_time = time.time()
            self.metrics["ticks_evaluated"] += 1
            tick_n = self.metrics["ticks_evaluated"]

            print(f"\n⏱️  [BLACK SCAN TICK #{tick_n}] Evaluating Core Trailing Window...")

            cached_events = list(self.memory_cache.items())
            if not cached_events:
                print("  ↳ [INFO] No state entries in this interval cycle.")
            else:
                print(f"  ↳ [PROCESSING] {len(cached_events)} cross-protocol pipeline mutations...")
                for pool_id, update in cached_events:
                    pool = update["pool"]
                    age  = start_time - update["timestamp"]

                    if age <= self.macro_interval:
                        self._quote_pool(pool_id, pool, age)
                        self.metrics["signals_caught"] += 1

                    if age > self.macro_interval:
                        self.memory_cache.pop(pool_id, None)

            elapsed       = time.time() - start_time
            sleep_duration = max(0.1, self.macro_interval - elapsed)
            await asyncio.sleep(sleep_duration)

        print("\n🏁 [EVALUATION COMPLETE] Macro intervals traced and analysed.")

    def _quote_pool(self, pool_id: str, pool: dict, age: float):
        """Computes and prints a single pool quote."""
        quotes = quote_pool(pool, Decimal("1000"))
        if not quotes:
            return
        best = max(quotes, key=lambda q: q.amount_out)
        print(
            f"    🌟 [{pool['protocol']:<12}] {pool_id:<40} "
            f"{best.token_in}->{best.token_out} Out: {best.amount_out:.4f} | Age: {age:.2f}s"
        )

    # ── Runner ────────────────────────────────────────────────────────────────

    async def run(self, max_ticks: int = 3):
        """Launch micro-listener and macro-scan loop concurrently."""
        if not self.pools:
            raise RuntimeError("live scanner requires preloaded Chain 137 pools")
        listener_task = asyncio.create_task(self.live_state_refresher())
        await self.macro_black_scan_loop(max_ticks=max_ticks)
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

