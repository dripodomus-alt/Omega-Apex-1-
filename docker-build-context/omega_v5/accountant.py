"""
omega_v5/accountant.py — High-Performance, Non-Blocking Audit Logger

Fire-and-Forget pattern for HFT:
- Main loop calls record_simulation() → immediate XADD to Redis Stream (L1, ~1ms, no block)
- Background worker (run in separate process/thread) drains stream → batch INSERT to Cloud SQL (L2)

This guarantees the arbitrage engine (Bellman, capital injector, execution) never waits for DB.

Ties directly to Capital Injector math + on-chain truth for ML Alpha retraining.
"""

from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

try:
    import orjson as json_lib
except ImportError:
    import json as json_lib

from .config import REDIS_URL, DATABASE_URL


class OmegaAccountant:
    """
    Low-latency, low-memory accountant.
    - Never blocks caller.
    - Uses Redis Stream with maxlen for bounded memory.
    - Batches to SQL to reduce IOPS and cost.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        sql_url: Optional[str] = None,
        stream_key: str = "omega:audit:simulations",
        batch_size: int = 50,
        flush_interval: float = 5.0,
    ):
        self.redis_url = redis_url or REDIS_URL
        self.sql_url = sql_url or DATABASE_URL
        self.stream_key = stream_key
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        self.redis: Optional[aioredis.Redis] = None
        self.sql_engine = None
        self.logger = logging.getLogger("omega.accountant")
        self._worker_task: Optional[asyncio.Task] = None

        self._init_engines()

    def _init_engines(self) -> None:
        try:
            self.redis = aioredis.from_url(
                self.redis_url,
                socket_connect_timeout=0.5,
                socket_timeout=1.0,
                decode_responses=False,  # we handle bytes for payload
            )
        except Exception as e:
            self.logger.warning(f"Redis init failed (will be no-op): {e}")
            self.redis = None

        try:
            # asyncpg driver recommended for Cloud SQL
            self.sql_engine = create_async_engine(
                self.sql_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False,
            )
        except Exception as e:
            self.logger.warning(f"SQL engine init failed (will be no-op): {e}")
            self.sql_engine = None

    async def _ensure_redis(self) -> bool:
        if self.redis is None:
            return False
        try:
            await self.redis.ping()
            return True
        except Exception:
            return False

    def _prepare_data(self, data: Any) -> Any:
        """Recursive, non-mutating, low-memory JSON-safe conversion."""
        if isinstance(data, Decimal):
            return str(data)
        if isinstance(data, dict):
            return {k: self._prepare_data(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [self._prepare_data(item) for item in data]
        if isinstance(data, (int, float, str, bool, type(None))):
            return data
        # Fallback for other objects
        try:
            return str(data)
        except Exception:
            return None

    async def record_simulation(self, sim_data: Dict[str, Any]) -> None:
        """
        FIRE-AND-FORGET entry point.
        Pushes to Redis Stream immediately. Never awaits SQL.
        Safe to call from hot path with asyncio.create_task(...) or fire-and-forget.
        """
        if not sim_data:
            return

        try:
            serializable = self._prepare_data(sim_data)

            if not await self._ensure_redis():
                self.logger.debug("Redis unavailable, dropping audit record")
                return

            payload = json_lib.dumps(serializable) if hasattr(json_lib, "dumps") else json.dumps(serializable)

            await self.redis.xadd(
                self.stream_key,
                {"payload": payload},
                maxlen=10000,   # bounded memory in Redis
                approximate=True,
            )
        except Exception as e:
            # Never crash the main loop
            self.logger.error(f"Accountant record_simulation failed (non-fatal): {e}")

    async def run_audit_worker(self) -> None:
        """
        BACKGROUND WORKER — run in separate asyncio task / process / pm2.
        Consumes Redis Stream and flushes batches to Cloud SQL.
        """
        self.logger.info("OmegaAccountant audit worker starting...")

        if self.sql_engine is None:
            self.logger.error("No SQL engine — worker exiting")
            return

        last_id = "0-0"
        batch: List[Dict[str, Any]] = []
        last_flush = time.time()

        while True:
            try:
                if not await self._ensure_redis():
                    await asyncio.sleep(2)
                    continue

                # Proper stream consumption (not always from 0-0)
                entries = await self.redis.xread(
                    {self.stream_key: last_id},
                    count=self.batch_size,
                    block=1000,
                )

                if entries:
                    for _, msg_list in entries:
                        for msg_id, content in msg_list:
                            try:
                                raw = content.get(b"payload") or content.get("payload")
                                if raw:
                                    record = json_lib.loads(raw) if hasattr(json_lib, "loads") else json.loads(raw)
                                    batch.append(record)
                                last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                            except Exception as parse_err:
                                self.logger.warning(f"Parse error on stream msg: {parse_err}")
                                last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id

                now = time.time()
                should_flush = (
                    len(batch) >= self.batch_size or
                    (now - last_flush > self.flush_interval and batch)
                )

                if should_flush:
                    await self._flush_to_sql(batch)
                    batch.clear()
                    last_flush = now

                await asyncio.sleep(0.05)  # tiny yield, low CPU

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Audit worker error (will retry): {e}")
                await asyncio.sleep(3)

    async def _flush_to_sql(self, batch: List[Dict[str, Any]]) -> None:
        if not batch or self.sql_engine is None:
            return

        def _generate_route_hash(path: List[str]) -> str:
            """Generates a deterministic hash for a given route path."""
            path_str = ",".join(sorted(path))
            return hashlib.sha256(path_str.encode('utf-8')).hexdigest()

        try:
            async with self.sql_engine.begin() as conn:
                # 1. Prepare route registry data and UPSERT
                route_params = []
                for rec in batch:
                    # The 'path' is the list of pool addresses/IDs
                    path = rec.get("path") or rec.get("metadata", {}).get("path")
                    if isinstance(path, list) and path:
                        route_hash = _generate_route_hash(path)
                        rec['route_hash'] = route_hash  # Add hash to record for simulation insert
                        route_params.append({
                            "route_hash": route_hash,
                            "path_json": json_lib.dumps(path)
                        })

                if route_params:
                    # Use ON CONFLICT to perform a safe, low-latency UPSERT (INSERT or DO NOTHING)
                    route_stmt = text("""
                        INSERT INTO route_registry (route_hash, path_json)
                        VALUES (:route_hash, :path_json::jsonb)
                        ON CONFLICT (route_hash) DO NOTHING
                    """)
                    await conn.execute(route_stmt, route_params)

                # 2. Prepare simulation audit data and INSERT
                sim_params = []
                for rec in batch:
                    if 'route_hash' in rec:
                        sim_params.append({
                            "route_hash": rec['route_hash'],
                            # The rest of the data goes into the metadata column
                            "metadata_jsonb": json_lib.dumps(rec)
                        })

                if sim_params:
                    sim_stmt = text("""
                        INSERT INTO simulation_audit (route_hash, metadata_jsonb)
                        VALUES (:route_hash, :metadata_jsonb::jsonb)
                    """)
                    await conn.execute(sim_stmt, sim_params)


            self.logger.info(f"Accountant flushed {len(batch)} simulation records to Cloud SQL using structured schema.")
        except Exception as e:
            self.logger.error(f"SQL flush failed (records dropped this batch): {e}")

    async def close(self) -> None:
        if self.redis:
            await self.redis.close()
        if self.sql_engine:
            await self.sql_engine.dispose()


# Singleton helper for easy import
_accountant: Optional[OmegaAccountant] = None


def get_accountant() -> OmegaAccountant:
    global _accountant
    if _accountant is None:
        _accountant = OmegaAccountant()
    return _accountant


# Convenience fire-and-forget helper
def record_simulation_fire_and_forget(sim_data: Dict[str, Any]) -> None:
    """Call from sync or async hot path. Never blocks."""
    try:
        acc = get_accountant()
        # Schedule without awaiting
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(acc.record_simulation(sim_data))
        else:
            loop.run_until_complete(acc.record_simulation(sim_data))
    except Exception:
        # Absolute last-resort silence
        pass
