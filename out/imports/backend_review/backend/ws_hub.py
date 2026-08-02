"""
WebSocket Hub — Real-time push for spread updates and pipeline status.

Replaces frontend 5s polling with server-push deltas. Connections are tracked
per-channel; broadcast is fire-and-forget so a slow client cannot stall the
scan loop.

Channels:
  - "spreads"   — pushes {type:"spreads", spreads:[...], timestamp}
  - "network"   — pushes {type:"network", blockNumber, baseFeeGwei, ...}
  - "pipeline"  — pushes {type:"pipeline_state", loading, ready, progress}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, Set, Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketHub:
    """Per-channel connection manager."""

    def __init__(self) -> None:
        self._channels: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(ws)
        logger.info(f"WS connected: channel={channel} total={len(self._channels[channel])}")

    async def disconnect(self, ws: WebSocket, channel: str) -> None:
        async with self._lock:
            if channel in self._channels:
                self._channels[channel].discard(ws)
        logger.info(f"WS disconnected: channel={channel}")

    async def broadcast(self, channel: str, payload: Dict[str, Any]) -> int:
        """Fire-and-forget broadcast; drops dead sockets. Returns recipient count."""
        if channel not in self._channels or not self._channels[channel]:
            return 0
        msg = json.dumps(payload, default=str)
        dead: list = []
        sent = 0
        # Snapshot under lock to avoid mutation during iteration
        async with self._lock:
            sockets = list(self._channels[channel])
        for ws in sockets:
            try:
                await ws.send_text(msg)
                sent += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._channels[channel].discard(ws)
        return sent

    def channel_size(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))


# Module-level singleton
hub = WebSocketHub()


async def spread_push_loop(get_engine_fn, interval_sec: float = 3.0) -> None:
    """
    Background pusher: every `interval_sec` triggers a fresh scan-or-cached
    fetch and broadcasts to the "spreads" + "network" channels.

    Stops broadcasting to a channel when no clients are connected (to avoid
    wasted scans), but still polls cheap network state every interval.
    """
    logger.info(f"📡 WS spread_push_loop started (interval={interval_sec}s)")
    while True:
        try:
            engine = get_engine_fn()
            # Skip during cold-start
            if getattr(engine, "pools_loading", False) or len(engine.pools) == 0:
                if hub.channel_size("pipeline") > 0:
                    await hub.broadcast("pipeline", {
                        "type": "pipeline_state",
                        "loading": True,
                        "ready": False,
                        "progress": {
                            "pools_loaded": len(engine.pools),
                            "pools_target": 4500,
                        },
                        "timestamp": int(time.time() * 1000),
                    })
                await asyncio.sleep(interval_sec)
                continue

            # Spreads channel — only scan if anyone is listening
            if hub.channel_size("spreads") > 0:
                # Use cached if recent (< 30s), else fresh scan
                if engine.last_update > 0 and (time.time() * 1000 - engine.last_update) < 30000:
                    spreads_data = engine.get_spreads()
                else:
                    engine.scan_for_spreads(loan_amount_usd=10000, max_comparisons=100)
                    spreads_data = engine.get_spreads()
                await hub.broadcast("spreads", {
                    "type": "spreads",
                    "timestamp": spreads_data.get("timestamp", 0),
                    "spreads": spreads_data.get("spreads", []),
                })

            # Network channel — cheap, push if anyone listens
            if hub.channel_size("network") > 0:
                snap = engine.get_cached_gas_snapshot()
                if snap is not None:
                    await hub.broadcast("network", {
                        "type": "network",
                        "blockNumber": snap.block_number,
                        "baseFeeGwei": snap.base_fee_gwei,
                        "tipP50Gwei": snap.tip_p50_gwei,
                        "tipP90Gwei": snap.tip_p90_gwei,
                        "gasPrice": snap.base_fee_gwei + snap.tip_p50_gwei,
                        "timestamp": int(time.time() * 1000),
                    })

            # Pipeline channel — push current ready state
            if hub.channel_size("pipeline") > 0:
                await hub.broadcast("pipeline", {
                    "type": "pipeline_state",
                    "loading": False,
                    "ready": True,
                    "progress": {
                        "pools_loaded": len(engine.pools),
                        "pools_target": len(engine.pools),
                    },
                    "timestamp": int(time.time() * 1000),
                })
        except Exception as e:
            logger.error(f"spread_push_loop error: {e}", exc_info=True)
        await asyncio.sleep(interval_sec)


async def mc_spread_push_loop(get_mc_engine_fn, interval_sec: float = 3.0) -> None:
    """
    Multi-chain spread push loop.
    Pushes cached engine results to the "mc_spreads" channel every interval_sec.
    The heavy scan runs separately in periodic_multi_chain_scan; this loop
    only serialises already-computed data, so it is extremely cheap.
    """
    logger.info(f"📡 mc_spread_push_loop started (interval={interval_sec}s)")
    while True:
        try:
            if hub.channel_size("mc_spreads") > 0:
                engine = get_mc_engine_fn()
                all_spreads = engine.all_spreads()
                executable  = [s for s in all_spreads if (s.get("execution_payload") or {}).get("executable", False)]
                await hub.broadcast("mc_spreads", {
                    "type":          "mc_spreads",
                    "total_spreads": len(all_spreads),
                    "executable":    len(executable),
                    "spreads":       sorted(all_spreads, key=lambda x: -x.get("spread_bps", 0))[:50],
                    "timestamp":     int(time.time() * 1000),
                    "note":          "Single-chain cross-DEX only. No cross-chain arbitrage.",
                })
        except Exception as e:
            logger.error(f"mc_spread_push_loop error: {e}")
        await asyncio.sleep(interval_sec)


async def ws_endpoint(websocket: WebSocket, channel: str) -> None:
    """
    Generic per-channel WS handler — connect, hold, drop on disconnect.

    Supported channels:
      spreads       — legacy Polygon single-chain spreads
      network       — Polygon block / gas state
      pipeline      — Polygon pool loading progress
      mc_spreads    — multi-chain cross-DEX spreads (all 10 chains)
      mc_chain_{id} — per-chain spread stream  (e.g. mc_chain_137)
    """
    # Dynamic channel validation: allow mc_chain_<int> patterns
    STATIC_CHANNELS = {"spreads", "network", "pipeline", "mc_spreads"}
    is_mc_chain = channel.startswith("mc_chain_") and channel[9:].isdigit()
    if channel not in STATIC_CHANNELS and not is_mc_chain:
        await websocket.close(code=4400)
        return

    await hub.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS recv loop ended: {e}")
    finally:
        await hub.disconnect(websocket, channel)
