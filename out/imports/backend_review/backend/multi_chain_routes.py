"""
Multi-Chain API Routes
All endpoints are scoped per chain — no cross-chain mixing.

WebSocket channels (via ws_endpoint):
  ws://host/ws/mc_spreads          → live spread broadcast, all chains
  ws://host/ws/mc_chain_{chain_id} → live spread broadcast, one chain
"""

import logging
import asyncio
import time
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, WebSocket
import httpx

from chain_config import CHAINS, get_all_chain_ids, get_chain
from multi_chain_engine import get_multi_chain_engine, periodic_multi_chain_scan
from multi_chain_discovery import get_multi_chain_discovery
from multi_chain_rpc import get_multi_chain_rpc
from ws_hub import ws_endpoint

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chains", tags=["multi-chain"])

# ── Native price + gas price live feeds ───────────────────────

# CoinGecko free API IDs per chain_id
_GECKO_IDS: dict = {
    1: "ethereum",      56: "binancecoin",  137: "matic-network",
    42161: "ethereum",  10: "ethereum",      8453: "ethereum",
    43114: "avalanche-2", 250: "fantom",     324: "ethereum",
    59144: "ethereum",
}
_PRICE_DEFAULTS: dict = {
    1: 3500.0, 56: 600.0, 137: 0.70, 42161: 3500.0,
    10: 3500.0, 8453: 3500.0, 43114: 30.0, 250: 0.50,
    324: 3500.0, 59144: 3500.0,
}
_price_cache: dict = {"prices": dict(_PRICE_DEFAULTS), "ts": 0.0}


async def _refresh_native_prices() -> dict:
    ids = ",".join(sorted(set(_GECKO_IDS.values())))
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
            raw = r.json()
        result = {}
        for cid, gecko_id in _GECKO_IDS.items():
            result[cid] = float(raw.get(gecko_id, {}).get("usd", _PRICE_DEFAULTS.get(cid, 1)))
        return result
    except Exception as e:
        logger.warning(f"[NativePrices] CoinGecko fetch failed: {e}; using cache/defaults")
        return _price_cache["prices"] if _price_cache["ts"] > 0 else dict(_PRICE_DEFAULTS)


@router.get("/native-prices")
async def native_prices():
    """Live native token USD prices from CoinGecko (cached 5 min, fallback to defaults)."""
    global _price_cache
    now = time.time()
    if now - _price_cache["ts"] > 300:
        prices = await _refresh_native_prices()
        _price_cache = {"prices": prices, "ts": now}
    return {
        "prices": _price_cache["prices"],
        "source": "coingecko" if _price_cache["ts"] > 0 else "defaults",
        "cached_at": int(_price_cache["ts"] * 1000),
        "age_seconds": int(now - _price_cache["ts"]),
    }


@router.get("/gas-prices")
async def gas_prices():
    """Live gas price in gwei from each chain's best RPC endpoint."""
    rpc = get_multi_chain_rpc()

    async def _fetch_one(cid: int):
        try:
            w3 = rpc.get_web3(cid)
            if not w3 or not w3.is_connected():
                return cid, None
            gp = await asyncio.to_thread(lambda: w3.eth.gas_price)
            return cid, round(gp / 1e9, 2)
        except Exception:
            return cid, None

    results = await asyncio.gather(*[_fetch_one(cid) for cid in get_all_chain_ids()])
    return {
        "gas_prices_gwei": {str(cid): gp for cid, gp in results},
        "timestamp": int(time.time() * 1000),
    }


# ── WebSocket endpoints ───────────────────────────────────────

@router.websocket("/ws/mc_spreads")
async def ws_mc_spreads(websocket: WebSocket):
    """
    Real-time multi-chain spread stream.
    Pushes { type, spreads, executable, timestamp, note } every ~3s.
    Each spread includes a complete execution_payload with flash loan + swap calldata.
    """
    await ws_endpoint(websocket, "mc_spreads")


@router.websocket("/ws/mc_chain/{chain_id}")
async def ws_mc_chain(websocket: WebSocket, chain_id: int):
    """
    Real-time spread stream for a single chain.
    Channel: mc_chain_{chain_id}  (e.g. mc_chain_137 for Polygon)
    """
    if chain_id not in CHAINS:
        await websocket.close(code=4404)
        return
    await ws_endpoint(websocket, f"mc_chain_{chain_id}")


# ── helpers ──────────────────────────────────────────────────

def _validate_chain(chain_id: int):
    if chain_id not in CHAINS:
        raise HTTPException(
            status_code=404,
            detail=f"Chain {chain_id} not supported. Available: {get_all_chain_ids()}"
        )


# ── chain registry ───────────────────────────────────────────

@router.get("")
async def list_chains():
    """List all 10 supported chains with metadata."""
    return {
        "chains": [
            {
                "chain_id":      cid,
                "name":          cfg["name"],
                "display":       cfg["display"],
                "native_symbol": cfg["native_symbol"],
                "dex_count":     len(cfg.get("dex_factories", {})),
                "token_count":   len(cfg.get("tokens", {})),
                "curve_enabled": cfg.get("curve", {}).get("enabled", False),
                "balancer_enabled": cfg.get("balancer", {}).get("enabled", False),
                "block_time_s":  cfg.get("block_time_s", 12),
            }
            for cid, cfg in CHAINS.items()
        ],
        "total": len(CHAINS),
        "note": "Each chain runs isolated single-chain discovery + execution. No cross-chain arb.",
    }


@router.get("/{chain_id}/info")
async def chain_info(chain_id: int):
    """Full configuration for a specific chain."""
    _validate_chain(chain_id)
    cfg = get_chain(chain_id)
    return {
        "chain_id":        chain_id,
        "display":         cfg["display"],
        "native_symbol":   cfg["native_symbol"],
        "wrapped_native":  cfg["wrapped_native"],
        "block_time_s":    cfg.get("block_time_s"),
        "tokens":          cfg["tokens"],
        "dex_factories":   cfg.get("dex_factories", {}),
        "curve":           cfg.get("curve", {}),
        "balancer":        cfg.get("balancer", {}),
        "priority_pairs":  cfg.get("priority_pairs", []),
    }


# ── RPC health ───────────────────────────────────────────────

@router.get("/rpc/health")
async def all_rpc_health():
    """Health summary for every chain's RPC endpoints."""
    mon = get_multi_chain_rpc()
    return {
        "chains": mon.all_summaries(),
        "note": "Each chain uses its own isolated RPC pool.",
    }


@router.get("/{chain_id}/rpc/health")
async def chain_rpc_health(chain_id: int):
    """RPC health for a single chain."""
    _validate_chain(chain_id)
    mon = get_multi_chain_rpc()
    return mon.chain_summary(chain_id)


@router.post("/{chain_id}/rpc/scan")
async def scan_chain_rpc(chain_id: int):
    """Force RPC endpoint scan for a specific chain."""
    _validate_chain(chain_id)
    mon = get_multi_chain_rpc()
    results = mon.scan_chain(chain_id)
    return {"chain_id": chain_id, "results": results, "count": len(results)}


@router.post("/rpc/scan-all")
async def scan_all_rpc():
    """Force RPC scan across all 10 chains."""
    mon = get_multi_chain_rpc()
    results = mon.scan_all()
    return {
        "scanned": {str(cid): len(r) for cid, r in results.items()},
        "summaries": mon.all_summaries(),
    }


# ── pool discovery ───────────────────────────────────────────

@router.get("/{chain_id}/pools")
async def get_chain_pools(
    chain_id: int,
    protocol: Optional[str] = Query(None, description="Filter: uniswap_v2 | uniswap_v3 | curve_stable | balancer_v2"),
    dex: Optional[str]      = Query(None, description="Filter by dex_name substring"),
    limit: int              = Query(200, ge=1, le=2000),
):
    """Return discovered pools for a chain, optionally filtered."""
    _validate_chain(chain_id)
    disc = get_multi_chain_discovery()
    pools = disc.get_cached(chain_id)

    if protocol:
        pools = [p for p in pools if protocol.lower() in str(p.get("protocol", "")).lower()]
    if dex:
        pools = [p for p in pools if dex.lower() in str(p.get("dex_name", "")).lower()]

    return {
        "chain_id":   chain_id,
        "chain_name": CHAINS[chain_id]["display"],
        "total":      len(pools),
        "pools":      pools[:limit],
        "protocol_breakdown": _protocol_breakdown(pools),
    }


@router.post("/{chain_id}/pools/discover")
async def discover_chain_pools(chain_id: int, background_tasks: BackgroundTasks):
    """
    Trigger full pool discovery for one chain (V2 + V3 + Curve + Balancer).
    Runs synchronously — may take 30-120 seconds for large chains.
    """
    _validate_chain(chain_id)
    disc = get_multi_chain_discovery()

    def _run():
        try:
            pools = disc.discover_chain(chain_id, force=True)
            logger.info(f"[API] chain {chain_id} discovery complete: {len(pools)} pools")
        except Exception as e:
            logger.error(f"[API] chain {chain_id} discovery failed: {e}")

    background_tasks.add_task(_run)
    return {
        "chain_id":    chain_id,
        "status":      "discovery_started",
        "message":     "Discovery running in background. Poll /pools to see results.",
    }


@router.post("/pools/discover-all")
async def discover_all_chains_pools(background_tasks: BackgroundTasks):
    """Trigger pool discovery across all 10 chains in background."""
    disc = get_multi_chain_discovery()

    def _run():
        results = disc.discover_all_chains(force=True)
        for cid, pools in results.items():
            logger.info(f"[API] chain {cid} → {len(pools)} pools")

    background_tasks.add_task(_run)
    return {
        "status":  "discovery_started",
        "chains":  get_all_chain_ids(),
        "message": "All-chain discovery running in background.",
    }


@router.get("/pools/summary")
async def pools_summary():
    """Pool count per chain from cache."""
    disc = get_multi_chain_discovery()
    summary = disc.summary()
    return {
        "chains": [
            {
                "chain_id":   cid,
                "chain_name": CHAINS[cid]["display"],
                "pool_count": count,
            }
            for cid, count in summary.items()
        ],
        "total_pools": sum(summary.values()),
    }


# ── price matrix ─────────────────────────────────────────────

@router.get("/{chain_id}/prices")
async def chain_prices(
    chain_id: int,
    max_pools: int = Query(300, ge=10, le=1000),
):
    """Fetch live on-chain prices for all pools on a chain."""
    _validate_chain(chain_id)
    engine = get_multi_chain_engine().get_engine(chain_id)
    prices = engine.fetch_all_prices(max_pools=max_pools)
    return {
        "chain_id":   chain_id,
        "chain_name": CHAINS[chain_id]["display"],
        "count":      len(prices),
        "pools": [
            {
                "pool_address":   p.pool_address,
                "dex_name":       p.dex_name,
                "protocol":       p.protocol,
                "token0_symbol":  p.token0_symbol,
                "token1_symbol":  p.token1_symbol,
                "price_t0_in_t1": p.price_t0_in_t1,
                "price_t1_in_t0": p.price_t1_in_t0,
                "reserve0":       p.reserve0,
                "reserve1":       p.reserve1,
                "fee_bps":        p.fee_bps,
                "liquidity_usd":  p.liquidity_usd,
            }
            for p in prices
        ],
    }


# ── spread / arbitrage opportunities ─────────────────────────

@router.get("/{chain_id}/spreads")
async def chain_spreads(
    chain_id: int,
    min_spread_bps: float = Query(20.0, ge=0),
    min_liquidity:  float = Query(10000.0, ge=0),
    max_pools:      int   = Query(300, ge=10, le=1000),
    top_n:          int   = Query(50, ge=1, le=500),
):
    """
    Cross-DEX spread opportunities on a single chain.
    Strictly no cross-chain opportunities returned.
    """
    _validate_chain(chain_id)
    engine = get_multi_chain_engine().get_engine(chain_id)
    prices, spreads = engine.scan(
        max_pools=max_pools,
        min_spread_bps=min_spread_bps,
        min_liquidity_usd=min_liquidity,
    )
    top = spreads[:top_n]
    return {
        "chain_id":    chain_id,
        "chain_name":  CHAINS[chain_id]["display"],
        "pools_priced": len(prices),
        "opportunities_found": len(spreads),
        "opportunities": [s.to_dict() for s in top],
        "note": "Cross-DEX only within this chain. No cross-chain arbitrage.",
    }


@router.get("/spreads/all")
async def all_chains_spreads(
    min_spread_bps: float = Query(20.0, ge=0),
    top_n:          int   = Query(100, ge=1, le=1000),
):
    """
    All cross-DEX spread opportunities across every chain.
    Results are grouped and tagged by chain_id — NOT cross-chain pairs.
    """
    engine = get_multi_chain_engine()
    all_spreads = engine.all_spreads()
    filtered = [s for s in all_spreads if s.get("spread_bps", 0) >= min_spread_bps]
    filtered = filtered[:top_n]

    by_chain = {}
    for s in filtered:
        cid = s["chain_id"]
        by_chain.setdefault(cid, []).append(s)

    return {
        "total_opportunities": len(filtered),
        "spreads": filtered,          # flat list — consumed by GlobalDataContext
        "by_chain": {
            str(cid): {
                "chain_name": CHAINS[cid]["display"],
                "count":      len(opps),
                "top_spread_bps": max(o["spread_bps"] for o in opps) if opps else 0,
                "opportunities": opps,
            }
            for cid, opps in by_chain.items()
        },
        "note": "All entries are cross-DEX within their own chain. No cross-chain entries.",
    }


@router.post("/scan-all")
async def scan_all_chains(
    min_spread_bps: float = Query(20.0, ge=0),
    max_pools:      int   = Query(200, ge=10, le=1000),
    background_tasks: BackgroundTasks = None,
):
    """Trigger a full scan of all 10 chains in background."""
    engine = get_multi_chain_engine()

    async def _run():
        await engine.scan_all_chains_async(
            max_pools=max_pools,
            min_spread_bps=min_spread_bps,
        )

    if background_tasks:
        background_tasks.add_task(asyncio.ensure_future, _run())
    else:
        asyncio.ensure_future(_run())

    return {
        "status":  "scan_started",
        "chains":  get_all_chain_ids(),
        "message": "All-chain scan running. Poll /spreads/all to see results.",
    }


# ── engine status ─────────────────────────────────────────────

@router.get("/status")
async def engine_status():
    """Status of the multi-chain engine across all chains."""
    engine = get_multi_chain_engine()
    disc   = get_multi_chain_discovery()
    return {
        "engines":     engine.status(),
        "pool_cache":  disc.summary(),
        "chain_count": len(CHAINS),
    }


@router.get("/{chain_id}/status")
async def chain_engine_status(chain_id: int):
    """Status of a single chain engine."""
    _validate_chain(chain_id)
    engine = get_multi_chain_engine().get_engine(chain_id)
    disc   = get_multi_chain_discovery()
    return {
        **engine.get_status(),
        "cached_pools": len(disc.get_cached(chain_id)),
    }


# ── Curve + Balancer specific ─────────────────────────────────

@router.get("/{chain_id}/pools/curve")
async def chain_curve_pools(chain_id: int, limit: int = Query(200, ge=1, le=2000)):
    """Curve pools discovered on this chain."""
    _validate_chain(chain_id)
    disc  = get_multi_chain_discovery()
    pools = [
        p for p in disc.get_cached(chain_id)
        if "curve" in str(p.get("protocol", "")).lower()
        or "curve" in str(p.get("dex_name", "")).lower()
    ]
    return {
        "chain_id":   chain_id,
        "chain_name": CHAINS[chain_id]["display"],
        "count":      len(pools),
        "pools":      pools[:limit],
        "curve_enabled": CHAINS[chain_id].get("curve", {}).get("enabled", False),
    }


@router.get("/{chain_id}/pools/balancer")
async def chain_balancer_pools(chain_id: int, limit: int = Query(200, ge=1, le=2000)):
    """Balancer pools discovered on this chain."""
    _validate_chain(chain_id)
    disc  = get_multi_chain_discovery()
    pools = [
        p for p in disc.get_cached(chain_id)
        if "balancer" in str(p.get("protocol", "")).lower()
        or "balancer" in str(p.get("dex_name", "")).lower()
    ]
    return {
        "chain_id":   chain_id,
        "chain_name": CHAINS[chain_id]["display"],
        "count":      len(pools),
        "pools":      pools[:limit],
        "balancer_enabled": CHAINS[chain_id].get("balancer", {}).get("enabled", False),
    }


# ── internal helpers ──────────────────────────────────────────

def _protocol_breakdown(pools: list) -> dict:
    counts: dict = {}
    for p in pools:
        proto = str(p.get("protocol", "unknown"))
        counts[proto] = counts.get(proto, 0) + 1
    return counts
