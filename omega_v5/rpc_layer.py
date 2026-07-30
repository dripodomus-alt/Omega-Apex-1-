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
from decimal import Decimal
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
        self.plan_name = RPC_PLAN_NAME
        print(f"[RPCQuota] Initialized for plan='{self.plan_name}' RPS={self.rps_limit} units_limit={self.units_limit}")

    def _get_unit_cost(self, method: str) -> int:
        return RPC_UNIT_COSTS.get(str(method or "default").lower(), RPC_UNIT_COSTS.get("default", 1))

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



# ── Runtime token and pool registries ─────────────────────────────────────────
TOKEN_ADDRESSES: Dict[str, str] = {
    "WPOL": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    "USDC.e": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
    "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
    "LINK": "0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39",
    "AAVE": "0xd6df932a45c0f255f85145f286ea0b292b21c90b",
    "CRV": "0x172370d5cd63279efa6d502dab29171933a610af",
    "BAL": "0x9a71012b13ca4d3d0cdc72a177df3ef03b0e76a3",
    "UNI": "0xb33eaad8d922b1083446dc23f610c2567fb5180f",
    "SUSHI": "0x0b3f868e0be5597d5db7feb59e1cadbb0fdda50a",
    "QUICK": "0xb5c064f955d8e7f38fe0460c556a72987494ee17",
}

TOKEN_DECIMALS: Dict[str, int] = {
    "WPOL": 18,
    "WMATIC": 18,
    "USDC": 6,
    "USDC.e": 6,
    "USDT": 6,
    "DAI": 18,
    "WETH": 18,
    "WBTC": 8,
    "LINK": 18,
    "AAVE": 18,
    "CRV": 18,
    "BAL": 18,
    "UNI": 18,
    "SUSHI": 18,
    "QUICK": 18,
    "A": 18,
    "B": 18,
}

ADDRESS_TO_SYMBOL: Dict[str, str] = {
    address.lower(): symbol for symbol, address in TOKEN_ADDRESSES.items() if address
}


def _protocol_name(raw: Any) -> str:
    if isinstance(raw, int):
        return {1: "UniswapV3", 2: "UniswapV2", 3: "Balancer", 4: "QuickSwapV3"}.get(raw, str(raw))
    value = str(raw or "")
    lowered = value.lower()
    if "quick" in lowered and "v2" in lowered:
        return "UniswapV2"
    if "quick" in lowered and "v3" in lowered:
        return "QuickSwapV3"
    if "uniswap" in lowered and "v3" in lowered:
        return "UniswapV3"
    if "balancer" in lowered:
        return "Balancer"
    return value or "UniswapV2"


def canonical_liquidity_key(pool_id: str, pool: dict | None = None) -> str:
    pool = pool or {}
    explicit = pool.get("liquidity_key") or pool.get("address") or pool.get("pool_address") or pool.get("pair_address")
    if explicit:
        return str(explicit).lower()
    tokens = ":".join(str(token) for token in pool.get("tokens", []) if token)
    return f"{pool.get('protocol', 'unknown')}:{tokens}:{pool_id}"


def _dynamic_pool_registry() -> Dict[str, dict]:
    path = PROJECT_ROOT / "omega_v5" / "data" / "pools_dynamic.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: could not load dynamic pools: {exc}", file=sys.stderr)
        return {}
    registry: Dict[str, dict] = {}
    for idx, item in enumerate(payload.get("pools", [])):
        address = item.get("pair_address") or item.get("address") or item.get("pool_address")
        token0 = item.get("token0_symbol") or item.get("token0")
        token1 = item.get("token1_symbol") or item.get("token1")
        if not address or not token0 or not token1:
            continue
        token0 = "WPOL" if token0 == "WMATIC" else str(token0)
        token1 = "WPOL" if token1 == "WMATIC" else str(token1)
        pool_id = item.get("pool_id") or f"{_protocol_name(item.get('protocol') or item.get('dex_name'))}_{token0}_{token1}_{idx}"
        meta = {
            "protocol": _protocol_name(item.get("protocol") or item.get("dex_name")),
            "token0": token0,
            "token1": token1,
            "tokens": [token0, token1],
            "address": address,
            "pool_address": address,
            "fee_bps": int(item.get("fee_bps") or 30),
            "token0_decimals": int(item.get("token0_decimals") or TOKEN_DECIMALS.get(token0, 18)),
            "token1_decimals": int(item.get("token1_decimals") or TOKEN_DECIMALS.get(token1, 18)),
            "route_class": "NATIVE_POOL_ROUTE",
            "liquidity_key": str(address).lower(),
        }
        registry[str(pool_id)] = meta
        if item.get("token0_address"):
            TOKEN_ADDRESSES.setdefault(token0, str(item["token0_address"]))
            TOKEN_DECIMALS.setdefault(token0, meta["token0_decimals"])
        if item.get("token1_address"):
            TOKEN_ADDRESSES.setdefault(token1, str(item["token1_address"]))
            TOKEN_DECIMALS.setdefault(token1, meta["token1_decimals"])
    ADDRESS_TO_SYMBOL.update({address.lower(): symbol for symbol, address in TOKEN_ADDRESSES.items() if address})
    return registry


DEEP_POOL_REGISTRY: Dict[str, dict] = _dynamic_pool_registry()


_V2_PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"},
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    },
]


def _decimal_units(raw_amount: int, decimals: int) -> Decimal:
    return Decimal(int(raw_amount)) / (Decimal(10) ** int(decimals))


def _hydrate_v2_reserves(pool_id: str, meta: dict) -> None:
    if meta.get("reserves"):
        return
    if str(meta.get("protocol") or "") != "UniswapV2":
        return
    address = meta.get("address") or meta.get("pool_address") or meta.get("pair_address")
    if not address or w3 is None or not Web3.is_address(str(address)):
        return
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(str(address)), abi=_V2_PAIR_ABI)
        token0_addr = str(contract.functions.token0().call()).lower()
        token1_addr = str(contract.functions.token1().call()).lower()
        token0_symbol = ADDRESS_TO_SYMBOL.get(token0_addr)
        token1_symbol = ADDRESS_TO_SYMBOL.get(token1_addr)
        if not token0_symbol or not token1_symbol:
            return
        reserve0, reserve1, _ = contract.functions.getReserves().call(block_identifier="latest")
        dec0 = int(TOKEN_DECIMALS.get(token0_symbol, 18))
        dec1 = int(TOKEN_DECIMALS.get(token1_symbol, 18))
        reserves = [_decimal_units(reserve0, dec0), _decimal_units(reserve1, dec1)]
        if reserves[0] <= 0 or reserves[1] <= 0:
            return
        meta["token0"] = token0_symbol
        meta["token1"] = token1_symbol
        meta["token0_address"] = Web3.to_checksum_address(token0_addr)
        meta["token1_address"] = Web3.to_checksum_address(token1_addr)
        meta["token0_decimals"] = dec0
        meta["token1_decimals"] = dec1
        meta["tokens"] = [token0_symbol, token1_symbol]
        meta["reserves"] = reserves
        fee_bps = Decimal(str(meta.get("fee_bps", 30) or 30))
        meta.setdefault("fee", fee_bps / Decimal("10000"))
        meta.setdefault("reserve_block", BLOCK)
        meta["reserve_source"] = "live_getReserves_token0_token1_aligned"
    except Exception:
        return


def load_live_pool_state(pool_id: str, meta: dict | None = None) -> dict | None:
    meta = dict(meta or DEEP_POOL_REGISTRY.get(pool_id, {}))
    if not meta:
        return None
    meta.setdefault("pool_id", pool_id)
    meta.setdefault("liquidity_key", canonical_liquidity_key(pool_id, meta))
    _hydrate_v2_reserves(pool_id, meta)
    return meta


def load_all_live_pools(registry: Dict[str, dict] | None = None) -> Dict[str, dict]:
    source = registry or DEEP_POOL_REGISTRY
    return {
        pool_id: state
        for pool_id, meta in source.items()
        for state in [load_live_pool_state(pool_id, meta)]
        if state
    }


def discover_factory_pool_registry(base_registry: Dict[str, dict] | None = None) -> Dict[str, dict]:
    merged = dict(base_registry or {})
    merged.update(DEEP_POOL_REGISTRY)
    return merged

print("[rpc_layer] Quota-aware RPC layer loaded. Enforcement=", RPC_QUOTA_ENFORCEMENT)




def _audit_v2_pair_canonical(
    *,
    pool_id: str,
    pool_meta: dict,
    toks: list[str],
    token_addrs: list[str],
    onchain_decimals: list[int] | None = None,
    reserves_raw: list[int] | None = None,
) -> dict:
    reject_reasons: list[str] = []
    canonical = [TOKEN_ADDRESSES.get(str(tok), "").lower() for tok in toks]
    for idx, (tok, observed, expected) in enumerate(zip(toks, token_addrs, canonical)):
        observed_l = str(observed or "").lower()
        if not observed_l or observed_l == "0x0000000000000000000000000000000000000000":
            reject_reasons.append(f"token{idx}_unknown_onchain_address")
            continue
        if expected and observed_l != expected:
            reject_reasons.append(f"token{idx}_unknown_onchain_address")
            reject_reasons.append(f"token{idx}_address_symbol_mismatch")
    if onchain_decimals and any(int(d) < 0 for d in onchain_decimals):
        reject_reasons.append("invalid_onchain_decimals")
    if reserves_raw and any(int(r) <= 0 for r in reserves_raw):
        reject_reasons.append("empty_reserves")
    return {
        "status": "fail" if reject_reasons else "pass",
        "pool_id": pool_id,
        "tokens": toks,
        "token_addrs": token_addrs,
        "canonical_addrs": canonical,
        "reject_reasons": reject_reasons,
    }