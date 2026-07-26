# ==============================================================================
# rpc_layer.py -- Dynamic, Resilient, and Performance-Aware RPC Configuration
#
# This module automatically selects the best RPC endpoints for different roles
# based on a benchmark report. It provides a single source of truth for RPC
# URLs and Web3 instances throughout the application.
#
# NEW: Integrated RPC Plan Quota Management for Developer/Standard plans.
# Tracks request units, enforces RPS (e.g. 25), and provides throttling.
# ==============================================================================

import json
import os
import sys
import time
import asyncio
from collections import deque
from pathlib import Path
from typing import Optional, Any, Dict, List, Callable
from web3 import Web3
from web3.providers.rpc import HTTPProvider

from .config import (
    CHAIN_ID,
    DODO_RPC_PROVIDER_URL,
    DODO_RPC_SOURCES,
    DODO_RPC_EXTRA_HTTP_URLS,
    REDIS_RPC_CACHE_TTL_SECONDS,
    REDIS_URL,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
    # Quota config
    RPC_PLAN_NAME,
    RPC_REQUEST_UNITS_LIMIT,
    RPC_RPS_LIMIT,
    RPC_QUOTA_ENFORCEMENT,
    RPC_QUOTA_WARN_THRESHOLD,
    RPC_UNIT_COSTS,
)

# --- Dynamic RPC Configuration ---

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RPC_BENCHMARK_FILE = PROJECT_ROOT / "out" / "rpc_benchmark.json"

DEFAULT_DISCOVERY_URL = "https://polygon.publicnode.com"
DEFAULT_BROADCAST_URL = "https://polygon.drpc.org"
DEFAULT_WSS_URLS = ["wss://polygon.drpc.org"]

DISCOVERY_RPC_URL = os.getenv("DISCOVERY_RPC_URL", DEFAULT_DISCOVERY_URL)
BROADCAST_RPC_URL = os.getenv("BROADCAST_RPC_URL", DEFAULT_BROADCAST_URL)
_listener_urls_str = os.getenv("LISTENER_WSS_URLS")
LISTENER_WSS_URLS = _listener_urls_str.split(',') if _listener_urls_str else DEFAULT_WSS_URLS

BROADCAST_ENDPOINTS = [{"url": BROADCAST_RPC_URL, "mev_capability": "None"}]

if RPC_BENCHMARK_FILE.exists():
    try:
        with open(RPC_BENCHMARK_FILE, 'r', encoding='utf-8') as f:
            endpoints = json.load(f)
        reliable_endpoints = [e for e in endpoints if e.get("SuccessRate") == 100]
        mev_endpoints = [e for e in reliable_endpoints if e.get("Type") == "HTTP" and e.get("MevCapability") != "None"]
        writable_endpoints = [e for e in reliable_endpoints if e.get("Type") == "HTTP" and e.get("Writable")]
        broadcast_candidates = mev_endpoints + [w for w in writable_endpoints if w not in mev_endpoints]
        if broadcast_candidates:
            BROADCAST_ENDPOINTS = [
                {"url": e["Url"], "mev_capability": e.get("MevCapability", "None")}
                for e in broadcast_candidates[:5]
            ]
            BROADCAST_RPC_URL = broadcast_candidates[0]["Url"]
        http_endpoints = [e for e in reliable_endpoints if e.get("Type") == "HTTP"]
        if http_endpoints:
            DISCOVERY_RPC_URL = http_endpoints[0]["Url"]
        wss_endpoints = [e for e in reliable_endpoints if e.get("Type") == "WSS"]
        if wss_endpoints:
            LISTENER_WSS_URLS = [e["Url"] for e in wss_endpoints[:3]]
        print("--- Dynamically Configured RPCs from Benchmark ---")
    except Exception as e:
        print(f"Warning: Could not parse RPC benchmark file. Using defaults/env vars. Error: {e}")
        print("--- Using Default/Environment RPCs ---")
else:
    print("--- Using Default/Environment RPCs (no benchmark file found) ---")


# ── Redis helpers ─────────────────────────────────────────────────────────────
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_ENABLED or not REDIS_URL:
        return None
    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        return _redis_client
    except Exception:
        return None

def redis_key(*parts: Any) -> str:
    prefix = REDIS_KEY_PREFIX or "omega_v5"
    safe = [str(p).replace(":", "_") for p in parts]
    return f"{prefix}:rpc:{':'.join(safe)}"

def get_json(key: str) -> Any:
    client = _get_redis()
    if not client:
        return None
    try:
        data = client.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None

def set_json(key: str, value: Any, ttl: int = 60) -> None:
    client = _get_redis()
    if not client:
        return
    try:
        client.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


# ── RPC Quota & Rate Limit Manager (NEW: Plan Feature) ────────────────────────
class RPCQuotaManager:
    """
    Manages RPC plan quotas:
    - RPS throttling (e.g. 25 requests per second for Developer plan)
    - Request unit tracking (cumulative usage vs limit)
    - Per-method unit cost estimation
    - Warning at threshold (default 80%)
    - Fire-and-forget recording for hot paths
    """
    def __init__(self, rps_limit: int = RPC_RPS_LIMIT, units_limit: int = RPC_REQUEST_UNITS_LIMIT):
        self.rps_limit = max(1, rps_limit)
        self.units_limit = units_limit
        self.request_times: deque = deque()
        self.total_units: int = 0
        self.total_requests: int = 0
        self._lock = asyncio.Lock() if asyncio.get_event_loop_policy().get_event_loop().is_running() else None
        self.plan_name = RPC_PLAN_NAME
        print(f"[RPCQuota] Initialized for plan='{self.plan_name}' RPS={self.rps_limit} units_limit={self.units_limit}")

    def _get_unit_cost(self, method: str) -> int:
        return RPC_UNIT_COSTS.get(method.lower(), RPC_UNIT_COSTS.get("default", 1))

    def can_make_request(self, method: str = "default", estimated_units: int = None) -> bool:
        if not RPC_QUOTA_ENFORCEMENT:
            return True

        now = time.time()
        # Clean old timestamps (1s window for RPS)
        while self.request_times and now - self.request_times[0] > 1.0:
            self.request_times.popleft()

        if len(self.request_times) >= self.rps_limit:
            return False

        units = estimated_units or self._get_unit_cost(method)
        if self.total_units + units > self.units_limit:
            return False

        return True

    def record_request(self, method: str = "default", units: int = None) -> None:
        """Record a request. Non-blocking where possible."""
        now = time.time()
        self.request_times.append(now)
        units = units or self._get_unit_cost(method)
        self.total_units += units
        self.total_requests += 1

        usage_pct = self.total_units / self.units_limit if self.units_limit > 0 else 0
        if usage_pct >= RPC_QUOTA_WARN_THRESHOLD:
            print(f"[RPCQuota][WARN] High usage: {self.total_units}/{self.units_limit} ({usage_pct:.1%}) plan={self.plan_name}")

    def get_stats(self) -> Dict[str, Any]:
        usage_pct = (self.total_units / self.units_limit * 100) if self.units_limit > 0 else 0
        return {
            "plan": self.plan_name,
            "rps_limit": self.rps_limit,
            "current_rps_window": len(self.request_times),
            "total_requests": self.total_requests,
            "total_units": self.total_units,
            "units_limit": self.units_limit,
            "usage_percent": round(usage_pct, 2),
            "enforcement": RPC_QUOTA_ENFORCEMENT,
        }

    async def async_wait_if_needed(self, method: str = "default"):
        """Async friendly throttle."""
        while not self.can_make_request(method):
            await asyncio.sleep(0.05)  # small backoff
        self.record_request(method)

    def sync_wait_if_needed(self, method: str = "default"):
        """Sync throttle (for non-async paths)."""
        while not self.can_make_request(method):
            time.sleep(0.05)
        self.record_request(method)


# Global quota manager instance
quota_manager: RPCQuotaManager = RPCQuotaManager()


class QuotaAwareHTTPProvider(HTTPProvider):
    """HTTPProvider that respects the plan quota before making requests."""
    def make_request(self, method: str, params: Any) -> Any:
        # Estimate and check quota
        if not quota_manager.can_make_request(method):
            stats = quota_manager.get_stats()
            raise Exception(f"RPC quota exceeded or rate limited. Stats: {stats}")

        # Record before the call (optimistic)
        quota_manager.record_request(method)

        # Delegate to parent
        return super().make_request(method, params)


# ── State ─────────────────────────────────────────────────────────────────────
w3:       Optional[Web3] = None
BLOCK:    int            = 0
RPC_LIVE: bool           = False
FACTORY_DISCOVERY_STATS: dict = {}
LAST_POOL_QUALITY_STATS: dict = {}

# --- Expose a default Web3 Instance ---
# Use quota-aware provider for enforcement
try:
    provider = QuotaAwareHTTPProvider(DISCOVERY_RPC_URL)
    w3 = Web3(provider)
    RPC_LIVE = w3.is_connected()
    if RPC_LIVE:
        BLOCK = w3.eth.block_number
except Exception as e:
    print(f"Warning: Could not connect to discovery RPC {DISCOVERY_RPC_URL}. Error: {e}")
    w3 = None
    RPC_LIVE = False


def _host_label(url: str) -> str:
    return url.split("/")[2] if "//" in url else url


def _is_usable_rpc_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    lowered = url.lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    return "${" not in url and "<" not in url and ">" not in url


def dodo_provider_endpoints(chain_id: int = CHAIN_ID, warn: bool = True) -> list[str]:
    """
    Reads free RPC endpoints from a DODOEX web3-rpc-provider service.
    """
    extra_urls = [url for url in DODO_RPC_EXTRA_HTTP_URLS if _is_usable_rpc_url(url)]
    if not DODO_RPC_PROVIDER_URL:
        return list(dict.fromkeys(extra_urls))

    base = DODO_RPC_PROVIDER_URL.rstrip("/")
    sources = [s.strip() for s in DODO_RPC_SOURCES.split(",") if s.strip()]
    if not sources:
        sources = ["ChainList"]

    cache_key = redis_key("dodo_provider_endpoints", chain_id, ",".join(sources), base)
    cached = get_json(cache_key)
    if isinstance(cached, list):
        return [url for url in cached if _is_usable_rpc_url(url)]
    if isinstance(cached, dict) and cached.get("unavailable"):
        return []

    try:
        resp = requests.get(
            f"{base}/{chain_id}/endpoints",
            params=[("sources[]", source) for source in sources],
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        if warn:
            print(f"  ⚠️  DODO RPC provider unavailable [{_host_label(base)}]: {exc}", file=sys.stderr)
        set_json(cache_key, {"unavailable": True}, ttl=15)
        return list(dict.fromkeys(extra_urls))

    urls = []
    for item in payload if isinstance(payload, list) else []:
        if item.get("chainId") == chain_id and _is_usable_rpc_url(item.get("url", "")):
            urls.append(item["url"])
    unique_urls = list(dict.fromkeys([*urls, *extra_urls]))
    set_json(cache_key, unique_urls, ttl=REDIS_RPC_CACHE_TTL_SECONDS)
    return unique_urls


def get_web3_for_role(role: str = "discovery") -> Web3:
    """Return a Web3 instance for the given role, quota-aware."""
    if role == "broadcast":
        url = BROADCAST_RPC_URL
    else:
        url = DISCOVERY_RPC_URL
    provider = QuotaAwareHTTPProvider(url)
    return Web3(provider)


def get_quota_stats() -> Dict[str, Any]:
    """Public API for quota stats (used by pnl_analyzer, preflight, verify scripts)."""
    return quota_manager.get_stats()


def reset_quota_stats() -> None:
    """Reset for testing or new cycle."""
    global quota_manager
    quota_manager = RPCQuotaManager()


# Backwards compat
def get_w3() -> Optional[Web3]:
    return w3


print("[rpc_layer] Quota-aware RPC layer loaded. Enforcement=", RPC_QUOTA_ENFORCEMENT)
