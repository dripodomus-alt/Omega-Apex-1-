#!/usr/bin/env python3
# ==============================================================================
# transport_lanes.py -- Redis-backed RPC transport control plane.
#
# DODOEX/web3-rpc-provider is treated as endpoint discovery metadata only. Every
# candidate URL is health-probed, scored, cached, and assigned to a request lane.
# Exact-call truth and live broadcast are intentionally separate lanes.
# ==============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests
from web3 import Web3

from . import redis_cache
from .config import (
    BROADCAST_RPC_URL,
    BROADCAST_RPC_FALLBACK_URLS,
    BROADCAST_WSS_URL,
    BROADCAST_WSS_FALLBACK_URLS,
    CHAIN_ID,
    DODO_RPC_PROVIDER_URL,
    DODO_RPC_EXTRA_HTTP_URLS,
    DODO_RPC_PROXY_URL,
    DODO_RPC_SOURCES,
    EXACT_CALL_RPC_URL,
    FORK_SIM_RPC_URL,
    PRIMARY_READ_RPC_URL,
    PRIMARY_WSS_URL,
    RPC_BROADCAST_MAX_RPS,
    RPC_ENDPOINT_TTL_SECONDS,
    RPC_EXACT_CALL_MAX_RPS,
    RPC_FAILED_TTL_SECONDS,
    RPC_HEALTH_TTL_SECONDS,
    RPC_MAX_RPS_PER_LANE,
    RPC_ROTATION_HTTP_URLS,
    RPC_ROTATION_WSS_URLS,
    RPC_REQUEST_TIMEOUT_SECONDS,
    TELEMETRY_RPC_URL,
    TRANSPORT_LANES_ENABLED,
    WSS_URL,
    HTTP_URL,
    HTTP_URL_2,
)


STREAM_RPC_HEALTH = "omega:rpc:health"
HASH_RPC_HEALTH_SCORES = "omega:rpc:health:scores"
STREAM_RPC_ENDPOINTS = "omega:rpc:endpoints"
STREAM_BLOCKHEADS = "omega:signals:blockheads"
STREAM_POOL_UPDATES = "omega:signals:pool_updates"
STREAM_TRUTH_CANDIDATES = "omega:queue:truth_candidates"
STREAM_EXECUTABLE_ROUTES = "omega:queue:executable_routes"
STREAM_BROADCAST = "omega:queue:broadcast"
STREAM_PENDING_RECEIPTS = "omega:receipts:pending"
STREAM_PNL_LIVE = "omega:pnl:live"
STREAM_PNL_DRY_RUN = "omega:pnl:dry_run"


LANE_WSS_BLOCK_HEADS = 0
LANE_WSS_PENDING_TX = 1
LANE_WSS_POOL_EVENT_LOGS = 2
LANE_WSS_HEARTBEAT_FINALITY = 3
LANE_V2_RESERVES = 4
LANE_V3_SLOT0_LIQUIDITY = 5
LANE_ALGEBRA_SLOT0_LIQUIDITY = 6
LANE_BALANCER_VAULT_READS = 7
LANE_CURVE_READS = 8
LANE_AAVE_READS = 9
LANE_CHAINLINK_ORACLE_READS = 10
LANE_GAS_FEE_READS = 11
LANE_QUICKSWAP_V2_DISCOVERY = 12
LANE_UNISWAP_V3_DISCOVERY = 13
LANE_ALGEBRA_DISCOVERY = 14
LANE_CURVE_REGISTRY_DISCOVERY = 15
LANE_BALANCER_POOL_DISCOVERY = 16
LANE_TOKEN_METADATA_DECIMALS = 17
LANE_THEORETICAL_RANKING = 18
LANE_CLMM_FINAL_QUOTER_SIZING = 19
LANE_EXACT_C1_ETH_CALL = 20
LANE_EXACT_LIQUIDATION_ETH_CALL = 21
LANE_FORK_SIMULATION = 22
LANE_ROUTE_KIND_ADAPTER_AUDIT = 23
LANE_LIVE_BROADCAST_PRIMARY = 24
LANE_PUBLIC_BROADCAST_FALLBACK = 25
LANE_NONCE_MANAGER = 26
LANE_RECEIPT_WATCHER = 27
LANE_C1_TRACE_PNL = 28
LANE_C2_TRACE_PNL = 29
LANE_LIQUIDATION_TRACE_PNL = 30
LANE_RUNTIME_CONTROL_CIRCUIT_BREAKER = 31


@dataclass(frozen=True)
class Lane:
    lane_id: int
    name: str
    kind: str
    stream: str
    max_rps: int
    endpoint_role: str


LANES: dict[int, Lane] = {
    0: Lane(0, "wss_block_heads", "wss", STREAM_BLOCKHEADS, RPC_MAX_RPS_PER_LANE, "wss"),
    1: Lane(1, "wss_pending_tx", "wss", STREAM_BLOCKHEADS, RPC_MAX_RPS_PER_LANE, "wss"),
    2: Lane(2, "wss_pool_event_logs", "wss", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "wss"),
    3: Lane(3, "wss_heartbeat_finality", "wss", STREAM_RPC_HEALTH, RPC_MAX_RPS_PER_LANE, "wss"),
    4: Lane(4, "v2_reserves_multicall", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    5: Lane(5, "v3_slot0_liquidity_multicall", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    6: Lane(6, "algebra_slot0_liquidity_multicall", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    7: Lane(7, "balancer_vault_reads", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    8: Lane(8, "curve_reads", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    9: Lane(9, "aave_reads", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    10: Lane(10, "chainlink_oracle_reads", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    11: Lane(11, "gas_basefee_priority_reads", "read", STREAM_RPC_HEALTH, RPC_MAX_RPS_PER_LANE, "read"),
    12: Lane(12, "quickswap_v2_factory_discovery", "discovery", STREAM_RPC_ENDPOINTS, RPC_MAX_RPS_PER_LANE, "discovery"),
    13: Lane(13, "uniswap_v3_factory_discovery", "discovery", STREAM_RPC_ENDPOINTS, RPC_MAX_RPS_PER_LANE, "discovery"),
    14: Lane(14, "algebra_factory_discovery", "discovery", STREAM_RPC_ENDPOINTS, RPC_MAX_RPS_PER_LANE, "discovery"),
    15: Lane(15, "curve_registry_discovery", "discovery", STREAM_RPC_ENDPOINTS, RPC_MAX_RPS_PER_LANE, "discovery"),
    16: Lane(16, "balancer_pool_discovery", "discovery", STREAM_RPC_ENDPOINTS, RPC_MAX_RPS_PER_LANE, "discovery"),
    17: Lane(17, "token_metadata_decimals_validation", "read", STREAM_POOL_UPDATES, RPC_MAX_RPS_PER_LANE, "read"),
    18: Lane(18, "theoretical_ranking", "compute", STREAM_TRUTH_CANDIDATES, RPC_MAX_RPS_PER_LANE, "read"),
    19: Lane(19, "clmm_final_quoter_sizing", "read", STREAM_TRUTH_CANDIDATES, RPC_EXACT_CALL_MAX_RPS, "exact"),
    20: Lane(20, "exact_c1_eth_call", "exact_call", STREAM_TRUTH_CANDIDATES, RPC_EXACT_CALL_MAX_RPS, "exact"),
    21: Lane(21, "exact_liquidation_eth_call", "exact_call", STREAM_TRUTH_CANDIDATES, RPC_EXACT_CALL_MAX_RPS, "exact"),
    22: Lane(22, "fork_simulation", "fork", STREAM_TRUTH_CANDIDATES, RPC_EXACT_CALL_MAX_RPS, "fork"),
    23: Lane(23, "route_kind_adapter_audit", "read", STREAM_TRUTH_CANDIDATES, RPC_EXACT_CALL_MAX_RPS, "exact"),
    24: Lane(24, "live_broadcast_private_primary", "broadcast", STREAM_BROADCAST, RPC_BROADCAST_MAX_RPS, "broadcast"),
    25: Lane(25, "public_broadcast_fallback", "broadcast", STREAM_BROADCAST, 1, "broadcast_fallback"),
    26: Lane(26, "nonce_manager", "broadcast", STREAM_BROADCAST, RPC_BROADCAST_MAX_RPS, "broadcast"),
    27: Lane(27, "receipt_watcher", "read", STREAM_PENDING_RECEIPTS, RPC_MAX_RPS_PER_LANE, "read"),
    28: Lane(28, "c1_trace_pnl", "stream", STREAM_PNL_LIVE, RPC_MAX_RPS_PER_LANE, "none"),
    29: Lane(29, "c2_trace_pnl", "stream", STREAM_PNL_LIVE, RPC_MAX_RPS_PER_LANE, "none"),
    30: Lane(30, "liquidation_trace_pnl", "stream", STREAM_PNL_LIVE, RPC_MAX_RPS_PER_LANE, "none"),
    31: Lane(31, "runtime_control_circuit_breaker", "control", STREAM_RPC_HEALTH, RPC_MAX_RPS_PER_LANE, "read"),
}
LANE_BY_NAME = {lane.name: lane for lane in LANES.values()}


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _is_http(url: str) -> bool:
    lowered = str(url).lower()
    return lowered.startswith(("http://", "https://")) and "${" not in url and "<" not in url and ">" not in url


def _is_wss(url: str) -> bool:
    lowered = str(url).lower()
    return lowered.startswith(("ws://", "wss://")) and "${" not in url and "<" not in url and ">" not in url


def _host(url: str) -> str:
    return url.split("/")[2] if "//" in url else url


def _mask_url(url: str) -> str:
    if not url:
        return ""
    if "//" not in url:
        return url
    scheme, rest = url.split("//", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}//{host}/..."


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _lane(lane: int | str | Lane) -> Lane:
    if isinstance(lane, Lane):
        return lane
    if isinstance(lane, int):
        if lane not in LANES:
            raise KeyError(f"unknown lane id {lane}")
        return LANES[lane]
    if lane not in LANE_BY_NAME:
        raise KeyError(f"unknown lane {lane}")
    return LANE_BY_NAME[lane]


def dodo_endpoint_metadata() -> list[str]:
    """
    Pulls endpoint metadata from DODOEX/web3-rpc-provider and caches it.
    These URLs are not trusted for execution until health-scored per lane.
    """
    extra_urls = [url for url in DODO_RPC_EXTRA_HTTP_URLS if _is_http(url)]
    if not DODO_RPC_PROVIDER_URL:
        return _dedupe(extra_urls)
    base = DODO_RPC_PROVIDER_URL.rstrip("/")
    sources = [source.strip() for source in DODO_RPC_SOURCES.split(",") if source.strip()] or ["ChainList"]
    cache_key = redis_cache.key("transport", "dodo_endpoints", CHAIN_ID, base, ",".join(sources))
    cached = redis_cache.get_json(cache_key)
    if isinstance(cached, list):
        return [url for url in cached if _is_http(url)]

    try:
        response = requests.get(
            f"{base}/{CHAIN_ID}/endpoints",
            params=[("sources[]", source) for source in sources],
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        redis_cache.set_json(cache_key, {"unavailable": type(exc).__name__}, ttl=RPC_FAILED_TTL_SECONDS)
        return _dedupe(extra_urls)

    urls: list[str] = []
    for item in payload if isinstance(payload, list) else []:
        if str(item.get("chainId")) == str(CHAIN_ID) and _is_http(str(item.get("url", ""))):
            urls.append(str(item["url"]))
    urls = _dedupe([*urls, *extra_urls])
    redis_cache.set_json(cache_key, urls, ttl=RPC_ENDPOINT_TTL_SECONDS)
    redis_cache.xadd(STREAM_RPC_ENDPOINTS, {"source": "dodo", "count": len(urls), "urls": [_mask_url(url) for url in urls]})
    return urls


def endpoint_candidates_for_lane(lane: int | str | Lane) -> list[str]:
    selected = _lane(lane)
    role = selected.endpoint_role

    if role == "wss":
        return [
            url
            for url in _dedupe([PRIMARY_WSS_URL, WSS_URL, *RPC_ROTATION_WSS_URLS, BROADCAST_WSS_URL, *BROADCAST_WSS_FALLBACK_URLS])
            if _is_wss(url)
        ]
    if role == "broadcast":
        return [url for url in _dedupe([BROADCAST_RPC_URL, *BROADCAST_RPC_FALLBACK_URLS]) if _is_http(url)]
    if role == "broadcast_fallback":
        return [
            url
            for url in _dedupe([BROADCAST_RPC_URL, *BROADCAST_RPC_FALLBACK_URLS, TELEMETRY_RPC_URL, DODO_RPC_PROXY_URL, *RPC_ROTATION_HTTP_URLS, HTTP_URL_2, HTTP_URL])
            if _is_http(url)
        ]
    if role == "exact":
        return [url for url in _dedupe([EXACT_CALL_RPC_URL, PRIMARY_READ_RPC_URL, *RPC_ROTATION_HTTP_URLS]) if _is_http(url)]
    if role == "fork":
        return [url for url in _dedupe([FORK_SIM_RPC_URL, PRIMARY_READ_RPC_URL, *RPC_ROTATION_HTTP_URLS]) if _is_http(url)]
    if role == "discovery":
        return [
            url
            for url in _dedupe([PRIMARY_READ_RPC_URL, TELEMETRY_RPC_URL, DODO_RPC_PROXY_URL, *RPC_ROTATION_HTTP_URLS, *dodo_endpoint_metadata(), HTTP_URL_2, HTTP_URL])
            if _is_http(url)
        ]
    if role == "read":
        return [
            url
            for url in _dedupe([PRIMARY_READ_RPC_URL, EXACT_CALL_RPC_URL, TELEMETRY_RPC_URL, *RPC_ROTATION_HTTP_URLS, HTTP_URL_2, HTTP_URL])
            if _is_http(url)
        ]
    return []


def _inject_poa(provider: Web3) -> None:
    try:
        from web3.middleware import ExtraDataToPOAMiddleware

        provider.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except Exception:
        try:
            from web3.middleware import geth_poa_middleware

            provider.middleware_onion.inject(geth_poa_middleware, layer=0)
        except Exception:
            return


def probe_http_endpoint(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    record: dict[str, Any] = {
        "url_hash": _url_hash(url),
        "host": _host(url),
        "url_masked": _mask_url(url),
        "ok": False,
        "chain_id": None,
        "block": None,
        "latency_ms": None,
        "score": 0,
        "error": "",
        "ts": time.time(),
    }
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": RPC_REQUEST_TIMEOUT_SECONDS}))
        _inject_poa(w3)
        chain_id = w3.eth.chain_id
        block = w3.eth.block_number
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        record.update({
            "ok": chain_id == CHAIN_ID,
            "chain_id": chain_id,
            "block": block,
            "latency_ms": latency_ms,
            "score": max(1, int(100 - min(latency_ms / 20, 60))) if chain_id == CHAIN_ID else 0,
        })
        if chain_id != CHAIN_ID:
            record["error"] = f"wrong_chain_id_{chain_id}"
    except Exception as exc:
        record.update({
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": f"{type(exc).__name__}: {exc}",
        })
    redis_cache.hset_json(HASH_RPC_HEALTH_SCORES, record["url_hash"], record, ttl=RPC_HEALTH_TTL_SECONDS * 4)
    redis_cache.xadd(STREAM_RPC_HEALTH, record, maxlen=2000)
    return record


def _probe_send_raw_transaction_method(url: str) -> dict[str, Any]:
    """
    Proves JSON-RPC write-method reachability without submitting a valid tx.
    A reachable write method should reject "0x" as malformed/invalid raw tx. A
    method-not-found, auth, rate-limit, or transport failure is not usable.
    """
    started = time.perf_counter()
    try:
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction", "params": ["0x"]},
            timeout=RPC_REQUEST_TIMEOUT_SECONDS,
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if response.status_code >= 400:
            return {
                "ok": False,
                "latency_ms": latency_ms,
                "detail": f"http_{response.status_code}",
            }
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return {"ok": False, "latency_ms": latency_ms, "detail": "unexpected_success_for_invalid_raw_tx"}
        code = str(error.get("code", ""))
        message = str(error.get("message", "")).lower()
        method_missing = code == "-32601" or "method not found" in message or "not supported" in message
        expected_invalid = any(
            marker in message
            for marker in ["invalid", "raw", "rlp", "hex", "transaction", "signed"]
        )
        return {
            "ok": expected_invalid and not method_missing,
            "latency_ms": latency_ms,
            "detail": str(error.get("message", ""))[:180],
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "detail": f"{type(exc).__name__}: {exc}",
        }


def probe_broadcast_endpoint(url: str) -> dict[str, Any]:
    record = probe_http_endpoint(url)
    method_probe = _probe_send_raw_transaction_method(url) if record.get("ok") else {"ok": False, "detail": record.get("error", "")}
    record.update(
        {
            "send_raw_transaction_method": bool(method_probe.get("ok")),
            "send_raw_transaction_probe_ms": method_probe.get("latency_ms"),
            "send_raw_transaction_detail": method_probe.get("detail", ""),
        }
    )
    if not record["send_raw_transaction_method"]:
        record["ok"] = False
        record["score"] = 0
        record["error"] = record.get("error") or f"eth_sendRawTransaction unavailable: {method_probe.get('detail', '')}"
    redis_cache.hset_json(HASH_RPC_HEALTH_SCORES, record["url_hash"], record, ttl=RPC_HEALTH_TTL_SECONDS * 4)
    redis_cache.xadd(STREAM_RPC_HEALTH, record, maxlen=2000)
    return record


def probe_wss_endpoint(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    record: dict[str, Any] = {
        "url_hash": _url_hash(url),
        "host": _host(url),
        "url_masked": _mask_url(url),
        "ok": False,
        "chain_id": None,
        "block": None,
        "latency_ms": None,
        "score": 0,
        "error": "",
        "ts": time.time(),
    }
    try:
        from websockets.sync.client import connect

        with connect(url, open_timeout=RPC_REQUEST_TIMEOUT_SECONDS, close_timeout=RPC_REQUEST_TIMEOUT_SECONDS) as ws:
            ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}))
            chain_payload = json.loads(ws.recv(timeout=RPC_REQUEST_TIMEOUT_SECONDS))
            ws.send(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []}))
            block_payload = json.loads(ws.recv(timeout=RPC_REQUEST_TIMEOUT_SECONDS))
        chain_id = int(chain_payload.get("result"), 16) if chain_payload.get("result") else None
        block = int(block_payload.get("result"), 16) if block_payload.get("result") else None
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        record.update({
            "ok": chain_id == CHAIN_ID and bool(block),
            "chain_id": chain_id,
            "block": block,
            "latency_ms": latency_ms,
            "score": max(1, int(100 - min(latency_ms / 20, 60))) if chain_id == CHAIN_ID and block else 0,
        })
        if chain_id != CHAIN_ID:
            record["error"] = f"wrong_chain_id_{chain_id}"
        elif not block:
            record["error"] = "empty_block_number"
    except Exception as exc:
        record.update({
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": f"{type(exc).__name__}: {exc}",
        })
    redis_cache.hset_json(HASH_RPC_HEALTH_SCORES, record["url_hash"], record, ttl=RPC_HEALTH_TTL_SECONDS * 4)
    redis_cache.xadd(STREAM_RPC_HEALTH, record, maxlen=2000)
    return record


def probe_lane(lane: int | str | Lane) -> list[dict[str, Any]]:
    selected = _lane(lane)
    if selected.kind == "wss":
        return [probe_wss_endpoint(url) for url in endpoint_candidates_for_lane(selected)]
    if selected.endpoint_role in {"broadcast", "broadcast_fallback"}:
        return [probe_broadcast_endpoint(url) for url in endpoint_candidates_for_lane(selected)]
    return [probe_http_endpoint(url) for url in endpoint_candidates_for_lane(selected)]


def _cached_health(url: str) -> dict[str, Any] | None:
    rows = redis_cache.hgetall_json(HASH_RPC_HEALTH_SCORES)
    row = rows.get(_url_hash(url))
    if not isinstance(row, dict):
        return None
    if time.time() - float(row.get("ts", 0)) > RPC_HEALTH_TTL_SECONDS:
        return None
    return row


def select_endpoint(lane: int | str | Lane, *, probe_if_stale: bool = True) -> str:
    if not TRANSPORT_LANES_ENABLED:
        candidates = endpoint_candidates_for_lane(lane)
        return candidates[0] if candidates else ""

    selected = _lane(lane)
    candidates = endpoint_candidates_for_lane(selected)
    if not candidates:
        return ""
    rows: list[dict[str, Any]] = []
    for url in candidates:
        row = _cached_health(url)
        if (
            row is not None
            and selected.endpoint_role in {"broadcast", "broadcast_fallback"}
            and "send_raw_transaction_method" not in row
            and probe_if_stale
        ):
            row = None
        if row is None and probe_if_stale:
            if selected.kind == "wss":
                row = probe_wss_endpoint(url)
            elif selected.endpoint_role in {"broadcast", "broadcast_fallback"}:
                row = probe_broadcast_endpoint(url)
            else:
                row = probe_http_endpoint(url)
        if row:
            rows.append({**row, "url": url})

    usable = [row for row in rows if row.get("ok") and int(row.get("score", 0)) > 0]
    if selected.endpoint_role in {"broadcast", "broadcast_fallback"}:
        usable = [row for row in usable if row.get("send_raw_transaction_method")]
    if not usable:
        return ""
    if selected.endpoint_role == "broadcast":
        candidate_order = {url: index for index, url in enumerate(candidates)}
        chosen_row = sorted(usable, key=lambda row: candidate_order.get(row["url"], 999999))[0]
        redis_cache.xadd(
            STREAM_RPC_ENDPOINTS,
            {
                "lane": selected.name,
                "lane_id": selected.lane_id,
                "role": selected.endpoint_role,
                "url_hash": chosen_row["url_hash"],
                "host": chosen_row["host"],
                "score": chosen_row["score"],
                "block": chosen_row.get("block"),
                "latency_ms": chosen_row.get("latency_ms"),
                "selection_policy": "configured_broadcast_priority",
            },
            maxlen=2000,
        )
        return str(chosen_row["url"])
    if selected.endpoint_role == "exact":
        candidate_order = {url: index for index, url in enumerate(candidates)}
        chosen_row = sorted(usable, key=lambda row: candidate_order.get(row["url"], 999999))[0]
        redis_cache.xadd(
            STREAM_RPC_ENDPOINTS,
            {
                "lane": selected.name,
                "lane_id": selected.lane_id,
                "role": selected.endpoint_role,
                "url_hash": chosen_row["url_hash"],
                "host": chosen_row["host"],
                "score": chosen_row["score"],
                "block": chosen_row.get("block"),
                "latency_ms": chosen_row.get("latency_ms"),
                "selection_policy": "configured_exact_call_priority",
            },
            maxlen=2000,
        )
        return str(chosen_row["url"])
    freshest_block = max(int(row.get("block") or 0) for row in usable)

    def _effective_score(row: dict[str, Any]) -> tuple[int, float]:
        block_lag = max(0, freshest_block - int(row.get("block") or 0))
        freshness_penalty = min(40, block_lag * 8)
        score = max(0, int(row.get("score", 0)) - freshness_penalty)
        return score, -float(row.get("latency_ms") or 999999)

    chosen_row = sorted(usable, key=_effective_score, reverse=True)[0]
    block_lag = max(0, freshest_block - int(chosen_row.get("block") or 0))
    redis_cache.xadd(
        STREAM_RPC_ENDPOINTS,
        {
            "lane": selected.name,
            "lane_id": selected.lane_id,
            "role": selected.endpoint_role,
            "url_hash": chosen_row["url_hash"],
            "host": chosen_row["host"],
            "score": chosen_row["score"],
            "block": chosen_row.get("block"),
            "block_lag": block_lag,
            "latency_ms": chosen_row.get("latency_ms"),
        },
    )
    return str(chosen_row["url"])


def rate_limit_allow(lane: int | str | Lane) -> bool:
    selected = _lane(lane)
    bucket = int(time.time())
    cache_key = redis_cache.key("transport", "rate", selected.lane_id, bucket)
    count = redis_cache.incr_with_ttl(cache_key, 2)
    return True if count is None else count <= max(1, int(selected.max_rps))


def web3_for_lane(lane: int | str | Lane) -> Web3 | None:
    selected = _lane(lane)
    if selected.kind == "wss":
        return None
    if not rate_limit_allow(selected):
        redis_cache.xadd(STREAM_RPC_HEALTH, {"lane": selected.name, "status": "rate_limited", "max_rps": selected.max_rps})
        return None
    url = select_endpoint(selected)
    if not url:
        return None
    provider = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": RPC_REQUEST_TIMEOUT_SECONDS}))
    _inject_poa(provider)
    return provider


def record_truth_candidate(payload: dict[str, Any]) -> str:
    return redis_cache.xadd(STREAM_TRUTH_CANDIDATES, payload)


def record_executable_route(payload: dict[str, Any]) -> str:
    payload = {**payload, "exact_call_passed": True}
    return redis_cache.xadd(STREAM_EXECUTABLE_ROUTES, payload)


def record_broadcast_payload(payload: dict[str, Any]) -> str:
    return redis_cache.xadd(STREAM_BROADCAST, payload)


def record_pending_receipt(payload: dict[str, Any]) -> str:
    return redis_cache.xadd(STREAM_PENDING_RECEIPTS, payload)


def transport_status(*, probe_if_stale: bool = False) -> dict[str, Any]:
    redis_ok, redis_detail = redis_cache.status()
    selected: dict[str, Any] = {}
    for lane_id in [
        LANE_WSS_BLOCK_HEADS,
        LANE_V2_RESERVES,
        LANE_CLMM_FINAL_QUOTER_SIZING,
        LANE_EXACT_C1_ETH_CALL,
        LANE_LIVE_BROADCAST_PRIMARY,
        LANE_RECEIPT_WATCHER,
    ]:
        lane = LANES[lane_id]
        url = select_endpoint(lane, probe_if_stale=probe_if_stale)
        selected[lane.name] = _mask_url(url) if url else ""
    return {
        "enabled": TRANSPORT_LANES_ENABLED,
        "chain_id": CHAIN_ID,
        "lane_count": len(LANES),
        "redis_ok": redis_ok,
        "redis_detail": redis_detail,
        "streams": [
            STREAM_RPC_HEALTH,
            STREAM_RPC_ENDPOINTS,
            STREAM_BLOCKHEADS,
            STREAM_POOL_UPDATES,
            STREAM_TRUTH_CANDIDATES,
            STREAM_EXECUTABLE_ROUTES,
            STREAM_BROADCAST,
            STREAM_PENDING_RECEIPTS,
            STREAM_PNL_LIVE,
            STREAM_PNL_DRY_RUN,
        ],
        "selected_endpoints": selected,
        "dodo_endpoint_metadata_count": len(dodo_endpoint_metadata()),
        "rotation_http_candidate_count": len([url for url in _dedupe(RPC_ROTATION_HTTP_URLS) if _is_http(url)]),
        "rotation_wss_candidate_count": len([url for url in _dedupe(RPC_ROTATION_WSS_URLS) if _is_wss(url)]),
    }


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Omega V5 RPC transport lane status/probe")
    parser.add_argument("--status", action="store_true", help="print lane and Redis status")
    parser.add_argument("--probe", action="store_true", help="probe selected lane endpoints")
    parser.add_argument("--probe-status", action="store_true", help="refresh endpoint probes while building --status output")
    parser.add_argument("--lane", default="exact_c1_eth_call", help="lane name or id for --probe")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    output: Any
    if args.probe:
        lane_arg: int | str = int(args.lane) if str(args.lane).isdigit() else args.lane
        output = {"lane": args.lane, "results": probe_lane(lane_arg)}
    else:
        output = transport_status(probe_if_stale=args.probe_status)

    if args.json:
        print(json.dumps(output, indent=2, default=str))
    else:
        if isinstance(output, dict):
            for key, value in output.items():
                print(f"{key}={value}")
        else:
            print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
