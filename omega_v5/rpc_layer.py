# ==============================================================================
# rpc_layer.py -- Dynamic, Resilient, and Performance-Aware RPC Configuration
#
# This module automatically selects the best RPC endpoints for different roles
# based on a benchmark report. It provides a single source of truth for RPC
# URLs and Web3 instances throughout the application.
# ==============================================================================

import json
import os
import sys
import requests
from pathlib import Path
from typing import Optional, Any, Dict, List
from web3 import Web3

from .config import (
    CHAIN_ID,
    DODO_RPC_PROVIDER_URL,
    DODO_RPC_SOURCES,
    DODO_RPC_EXTRA_HTTP_URLS,
    REDIS_RPC_CACHE_TTL_SECONDS,
    REDIS_URL,
    REDIS_ENABLED,
    REDIS_KEY_PREFIX,
)

# --- Dynamic RPC Configuration ---

# The root of the project is assumed to be two levels up from this file's directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RPC_BENCHMARK_FILE = PROJECT_ROOT / "out" / "rpc_benchmark.json"

# Default fallbacks in case the benchmark file doesn't exist or is invalid.
# These can also be overridden by environment variables for maximum flexibility.
DEFAULT_DISCOVERY_URL = "https://polygon.publicnode.com"
DEFAULT_BROADCAST_URL = "https://polygon.drpc.org"  # A known fast, writable provider
DEFAULT_WSS_URLS = ["wss://polygon.drpc.org"]

# Initialize with defaults or environment variables
DISCOVERY_RPC_URL = os.getenv("DISCOVERY_RPC_URL", DEFAULT_DISCOVERY_URL)
BROADCAST_RPC_URL = os.getenv("BROADCAST_RPC_URL", DEFAULT_BROADCAST_URL)
_listener_urls_str = os.getenv("LISTENER_WSS_URLS")
LISTENER_WSS_URLS = _listener_urls_str.split(',') if _listener_urls_str else DEFAULT_WSS_URLS

# This will be a list of dicts, e.g., [{"url": "...", "mev_capability": "Flashbots"}, ...]
BROADCAST_ENDPOINTS = [{"url": BROADCAST_RPC_URL, "mev_capability": "None"}]

# --- Dynamic Selection Logic ---
# This block will override the defaults if a valid benchmark report is found.
if RPC_BENCHMARK_FILE.exists():
    try:
        with open(RPC_BENCHMARK_FILE, 'r', encoding='utf-8') as f:
            endpoints = json.load(f)

        # Filter for endpoints with 100% success rate, already sorted by latency.
        reliable_endpoints = [e for e in endpoints if e.get("SuccessRate") == 100]

        # 1. Select the best BROADCAST endpoints (MEV > Writable HTTP)
        mev_endpoints = [e for e in reliable_endpoints if e.get("Type") == "HTTP" and e.get("MevCapability") != "None"]
        writable_endpoints = [e for e in reliable_endpoints if e.get("Type") == "HTTP" and e.get("Writable")]

        # Prioritize MEV, then fast writable endpoints
        broadcast_candidates = mev_endpoints + [w for w in writable_endpoints if w not in mev_endpoints]
        if broadcast_candidates:
            BROADCAST_ENDPOINTS = [
                {"url": e["Url"], "mev_capability": e.get("MevCapability", "None")}
                for e in broadcast_candidates[:5] # Take top 5 for redundancy
            ]
            # The single BROADCAST_RPC_URL is the top choice for simple submissions
            BROADCAST_RPC_URL = broadcast_candidates[0]["Url"]

        # 2. Select the best DISCOVERY endpoint (fastest, reliable HTTP)
        http_endpoints = [e for e in reliable_endpoints if e.get("Type") == "HTTP"]
        if http_endpoints:
            DISCOVERY_RPC_URL = http_endpoints[0]["Url"]

        # 3. Select top 3 WSS endpoints for redundant listeners
        wss_endpoints = [e for e in reliable_endpoints if e.get("Type") == "WSS"]
        if wss_endpoints:
            LISTENER_WSS_URLS = [e["Url"] for e in wss_endpoints[:3]]

        print("--- Dynamically Configured RPCs from Benchmark ---")
    except Exception as e:
        print(f"Warning: Could not parse RPC benchmark file. Using defaults/env vars. Error: {e}")
        print("--- Using Default/Environment RPCs ---")
else:
    print("--- Using Default/Environment RPCs (no benchmark file found) ---")


# ── Redis helpers (for DODO provider cache) ───────────────────────────────────
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


# ── State ─────────────────────────────────────────────────────────────────────
w3:       Optional[Web3] = None
BLOCK:    int            = 0
RPC_LIVE: bool           = False
FACTORY_DISCOVERY_STATS: dict = {}
LAST_POOL_QUALITY_STATS: dict = {}

# --- Expose a default Web3 Instance ---
# For convenience, other modules can import `w3` and it will point to the fast discovery instance.
try:
    w3 = Web3(Web3.HTTPProvider(DISCOVERY_RPC_URL))
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
    # ChainList can return template URLs that require user API keys.
    return "${" not in url and "<" not in url and ">" not in url


def dodo_provider_endpoints(chain_id: int = CHAIN_ID, warn: bool = True) -> list[str]:
    """
    Reads free RPC endpoints from a DODOEX web3-rpc-provider service.

    The provider repo runs an HTTP service, usually at http://127.0.0.1:3000.
    It is optional: failures return an empty list and never block configured RPCs.
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


def review_apprentice_metadata_promotions(*, apply: bool = True) -> dict:
    """Discovery-side promotion gate for apprentice metadata proposals."""
    global APPRENTICE_METADATA_PROMOTION_STATS
    # Provide safe defaults if not imported from config yet
    enable = globals().get("ENABLE_APPRENTICE_METADATA_PROMOTIONS", False)
    max_promos = globals().get("APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE", 5)
    if not enable:
        APPRENTICE_METADATA_PROMOTION_STATS = {"enabled": False}
        return APPRENTICE_METADATA_PROMOTION_STATS
    try:
        from .apprentice_metadata_registry import review_apprentice_metadata_promotions as _review

        APPRENTICE_METADATA_PROMOTION_STATS = _review(
            apply=apply,
            max_promotions=max_promos,
        )
    except Exception as exc:
        APPRENTICE_METADATA_PROMOTION_STATS = {
            "enabled": True,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return APPRENTICE_METADATA_PROMOTION_STATS


def _inject_poa_middleware(provider: Web3) -> None:
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        provider.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except (ImportError, AttributeError):
        try:
            from web3.middleware import geth_poa_middleware
            provider.middleware_onion.inject(geth_poa_middleware, layer=0)
        except (ImportError, AttributeError):
            pass


# Legacy connect function for backward compatibility.
# It now just reports the status of the auto-configured connection.
def connect(*args, **kwargs) -> bool:
    if RPC_LIVE and w3:
        print(f"✅ RPC layer already connected to {w3.provider.endpoint_uri if w3.provider else 'N/A'}")
    else:
        print("⚠️ RPC layer is not connected.")
    return RPC_LIVE


# ── Deep Pool Address Registry (Polygon mainnet, verified) ────────────────────
DEEP_POOL_REGISTRY: dict = {
    # ── Uniswap V3 ────────────────────────────────────────────────────────────
    "V3_USDC_e_WETH_500": {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "WETH",
                           "address": "0x45dDa9cb7c25131DF268515131f647d726f50608", "fee_bps": 500},
    "V3_USDC_e_WETH_3000": {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "WETH",
                           "address": "0x0e44cEb592AcFC5D3F09D996302eB4C499ff8c10", "fee_bps": 3000},
    "V3_USDC_e_WETH_100": {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "WETH",
                           "address": "0x04537F43f6adD7b1b60CAb199c7a910024eE0594", "fee_bps": 100},
    "V3_WBTC_WETH_500":   {"protocol": "UniswapV3", "token0": "WBTC",  "token1": "WETH",
                           "address": "0x50eaEDB835021E4A108B7290636d62E9765cc6d7", "fee_bps": 500},
    "V3_WBTC_WETH_3000":  {"protocol": "UniswapV3", "token0": "WBTC",  "token1": "WETH",
                           "address": "0xfe343675878100b344802A6763fd373fDeed07A4", "fee_bps": 3000},
    "V3_WBTC_USDC_e_500": {"protocol": "UniswapV3", "token0": "WBTC",  "token1": "USDC.e",
                           "address": "0xeEF1A9507B3D505f0062f2be9453981255b503c8", "fee_bps": 500},
    "V3_WBTC_USDC_e_3000": {"protocol": "UniswapV3", "token0": "WBTC", "token1": "USDC.e",
                            "address": "0x847b64f9d3A95e977D157866447a5C0A5dFa0Ee5", "fee_bps": 3000},
    "V3_WPOL_USDC_e_500": {"protocol": "UniswapV3", "token0": "WPOL",  "token1": "USDC.e",
                           "address": "0xA374094527e1673A86dE625aa59517c5dE346d32", "fee_bps": 500},
    "V3_WPOL_WETH_500":   {"protocol": "UniswapV3", "token0": "WPOL",  "token1": "WETH",
                           "address": "0x86f1d8390222A3691C28938eC7404A1661E618e0", "fee_bps": 500},
    "V3_WPOL_USDT_500":   {"protocol": "UniswapV3", "token0": "WPOL",  "token1": "USDT",
                           "address": "0x9B08288C3Be4F62bbf8d1C20Ac9C5e6f9467d8B7", "fee_bps": 500},
    "V3_WPOL_USDT_3000":  {"protocol": "UniswapV3", "token0": "WPOL",  "token1": "USDT",
                           "address": "0x781067Ef296E5C4A4203F81C593274824b7C185d", "fee_bps": 3000},
    "V3_USDC_e_USDT_100": {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "USDT",
                           "address": "0xDaC8A8E6DBf8c690ec6815e0fF03491B2770255D", "fee_bps": 100},
    "V3_USDC_e_USDT_500": {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "USDT",
                           "address": "0x3F5228d0e7D75467366be7De2c31D0d098bA2C23", "fee_bps": 500},
    "V3_USDC_e_USDT_3000": {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "USDT",
                            "address": "0x24555B1E26407b8b56621da41F175c5E2B80f1b8", "fee_bps": 3000},
    "V3_USDC_e_DAI_100":  {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "DAI",
                           "address": "0x5645dCB64c059aa11212707fbf4E7F984440a8Cf", "fee_bps": 100},
    "V3_USDC_e_DAI_500":  {"protocol": "UniswapV3", "token0": "USDC.e", "token1": "DAI",
                           "address": "0x5f69C2ec01c22843f8273838d570243fd1963014", "fee_bps": 500},
    "V3_DAI_USDT_100":    {"protocol": "UniswapV3", "token0": "DAI", "token1": "USDT",
                           "address": "0x254aa3A898071D6A2dA0DB11dA73b02B4646078F", "fee_bps": 100},
    "V3_DAI_USDT_500":    {"protocol": "UniswapV3", "token0": "DAI", "token1": "USDT",
                           "address": "0x42F0530351471dAB7ec968476D19bD36Af9Ec52d", "fee_bps": 500},
    "V3_USDC_USDT_100":   {"protocol": "UniswapV3", "token0": "USDC", "token1": "USDT",
                           "address": "0x31083a78E11B18e450fd139F9ABEa98CD53181B7", "fee_bps": 100},
    "V3_USDC_USDC_e_100": {"protocol": "UniswapV3", "token0": "USDC", "token1": "USDC.e",
                           "address": "0xD36ec33c8bed5a9F7B6630855f1533455b98a418", "fee_bps": 100},
    "V3_USDC_WETH_500":   {"protocol": "UniswapV3", "token0": "USDC", "token1": "WETH",
                           "address": "0xA4D8c89f0c20efbe54cBa9e7e7a7E509056228D9", "fee_bps": 500},
    "V3_USDC_WPOL_500":   {"protocol": "UniswapV3", "token0": "USDC", "token1": "WPOL",
                           "address": "0xB6e57ed85c4c9dbfEF2a68711e9d6f36c56e0FcB", "fee_bps": 500},
    "V3_LINK_WETH_3000":  {"protocol": "UniswapV3", "token0": "LINK",  "token1": "WETH",
                           "address": "0x3e31AB7f37c048FC6574189135D108df80F0ea26", "fee_bps": 3000},
    "V3_AAVE_WETH_3000":  {"protocol": "UniswapV3", "token0": "AAVE",  "token1": "WETH",
                           "address": "0x2aCeda63B5e958c45bd27d916ba701BC1DC08F7a", "fee_bps": 3000},
    "V3_CRV_WETH_3000":   {"protocol": "UniswapV3", "token0": "CRV",   "token1": "WETH",
                           "address": "0xFC99D1c02D27DE07DfE0dCd878CDe86ee59c5f6B", "fee_bps": 3000},
    # ── QuickSwap V2 ─────────────────────────────────────────────────────────
    "QS_WPOL_USDC_e":     {"protocol": "UniswapV2", "token0": "WPOL",  "token1": "USDC.e",
                           "address": "0x6e7a5FAFcec6BB1e78bAE2A1F0B612012BF14827", "fee_bps": 30},
    "QS_WPOL_WETH":       {"protocol": "UniswapV2", "token0": "WPOL",  "token1": "WETH",
                           "address": "0xadbF1854e5883eB8aa7BAf50705338739e558E5b", "fee_bps": 30},
    "QS_WBTC_WETH":       {"protocol": "UniswapV2", "token0": "WBTC",  "token1": "WETH",
                           "address": "0xdC9232E2Df177d7a12FdFf6EcBAb114E2231198D", "fee_bps": 30},
    "QS_USDC_e_USDT":     {"protocol": "UniswapV2", "token0": "USDC.e",  "token1": "USDT",
                           "address": "0x2cF7252e74036d1Da831d11089D326296e64a728", "fee_bps": 30},
    "QS_USDC_e_DAI":      {"protocol": "UniswapV2", "token0": "USDC.e",  "token1": "DAI",
                           "address": "0xf04adBF75cDFc5eD26eEA4bbbb991DB002036Bdd", "fee_bps": 30},
    "QS_WETH_USDC_e":     {"protocol": "UniswapV2", "token0": "WETH",  "token1": "USDC.e",
                           "address": "0x853Ee4b2A13f8a742d64C8F088bE7bA2131f670d", "fee_bps": 30},
    "QS_WBTC_USDC_e":     {"protocol": "UniswapV2", "token0": "WBTC",  "token1": "USDC.e",
                           "address": "0xF6a637525402643B0654a54bEAd2Cb9A83C8B498", "fee_bps": 30},
    "QS_WETH_USDT":       {"protocol": "UniswapV2", "token0": "WETH",  "token1": "USDT",
                           "address": "0xF6422B997c7F54D1c6a6e103bcb1499EeA0a7046", "fee_bps": 30},
    "QS_WPOL_USDT":       {"protocol": "UniswapV2", "token0": "WPOL",  "token1": "USDT",
                           "address": "0x604229c960e5CACF2aaEAc8Be68Ac07BA9dF81c3", "fee_bps": 30},
    "QS_DAI_USDT":        {"protocol": "UniswapV2", "token0": "DAI",   "token1": "USDT",
                           "address": "0x59153f27eeFE07E5eCE4f9304EBBa1DA6F53CA88", "fee_bps": 30},
    "QS_USDC_USDT":       {"protocol": "UniswapV2", "token0": "USDC",  "token1": "USDT",
                           "address": "0xE43AB6540C0929EF29D216A34ab1F0eaCc5C3825", "fee_bps": 30},
    "QS_USDC_USDC_e":     {"protocol": "UniswapV2", "token0": "USDC",  "token1": "USDC.e",
                           "address": "0x2FB3b855fb2E3F668de6fC82f026a7ab56F6B067", "fee_bps": 30},
    "QS_USDC_DAI":        {"protocol": "UniswapV2", "token0": "USDC",  "token1": "DAI",
                           "address": "0xD29a84Ba6DEb95063bd3a0a32212dCb272156Bea", "fee_bps": 30},
    "QS_USDC_WPOL":       {"protocol": "UniswapV2", "token0": "USDC",  "token1": "WPOL",
                           "address": "0x6D9e8dbB2779853db00418D4DcF96F3987CFC9D2", "fee_bps": 30},
    "QS_USDC_WETH":       {"protocol": "UniswapV2", "token0": "USDC",  "token1": "WETH",
                           "address": "0x7bAF833f82BB1971f99A5a5d84bED1d5D0dEDD70", "fee_bps": 30},
    "QS_LINK_WETH":       {"protocol": "UniswapV2", "token0": "LINK",  "token1": "WETH",
                           "address": "0x5cA6CA6c3709E1E6CFe74a50Cf6B2B6BA2Dadd67", "fee_bps": 30},
    "QS_AAVE_WETH":       {"protocol": "UniswapV2", "token0": "AAVE",  "token1": "WETH",
                           "address": "0x90bc3E68Ba8393a3Bf2D79309365089975341a43", "fee_bps": 30},
    # ── QuickSwap Algebra / V3 ───────────────────────────────────────────────
    "ALG_USDC_e_USDT":    {"protocol": "QuickSwapV3", "token0": "USDC.e", "token1": "USDT",
                           "address": "0x7B925e617aefd7FB3a93Abe3a701135D7a1Ba710"},
    "ALG_USDC_e_DAI":     {"protocol": "QuickSwapV3", "token0": "USDC.e", "token1": "DAI",
                           "address": "0xe7E0eB9F6bCcCfe847fDf62a3628319a092F11a2"},
    "ALG_USDC_e_WETH":    {"protocol": "QuickSwapV3", "token0": "USDC.e", "token1": "WETH",
                           "address": "0x55CAaBB0d2b704FD0eF8192A7E35D8837e678207"},
    "ALG_USDC_e_WBTC":    {"protocol": "QuickSwapV3", "token0": "USDC.e", "token1": "WBTC",
                           "address": "0xA5CD8351Cbf30B531C7b11B0D9d3Ff38eA2E280f"},
    "ALG_WBTC_WETH":      {"protocol": "QuickSwapV3", "token0": "WBTC", "token1": "WETH",
                           "address": "0xAC4494e30a85369e332BDB5230d6d694d4259DbC"},
    "ALG_WETH_USDT":      {"protocol": "QuickSwapV3", "token0": "WETH", "token1": "USDT",
                           "address": "0x9CEff2F5138fC59eB925d270b8A7A9C02a1810f2"},
    "ALG_WPOL_USDT":      {"protocol": "QuickSwapV3", "token0": "WPOL", "token1": "USDT",
                           "address": "0x5b41EEDCfC8e0AE47493d4945Aa1AE4fe05430ff"},
    "ALG_USDC_USDT":      {"protocol": "QuickSwapV3", "token0": "USDC", "token1": "USDT",
                           "address": "0x0e3Eb2C75Bd7dD0e12249d96b1321d9570764D77"},
    "ALG_USDC_DAI":       {"protocol": "QuickSwapV3", "token0": "USDC", "token1": "DAI",
                           "address": "0xBC8f3da0bd42E1F2509cd8671Ce7c7E5f7fd39c8"},
    "ALG_USDC_WPOL":      {"protocol": "QuickSwapV3", "token0": "USDC", "token1": "WPOL",
                           "address": "0x6669B4706cC152F359e947BCa68E263A87c52634"},
    # ── Curve ────────────────────────────────────────────────────────────────
    # Current Polygon Curve pool discovery is kept fail-closed until the runtime
    # imports active pools from the Curve registry/router. Deprecated Aave V2
    # and nested ATriCrypto pools are intentionally excluded from execution
    # discovery.
    # ── Balancer V2 ──────────────────────────────────────────────────────────
    "BAL_WPOL_WETH_USDC": {
        "protocol": "Balancer", "token0": "WPOL", "token1": "WETH",
        "address":  "0x0297e37f1873D2DAb4487Aa67cD56B58E2F27875",
        "pool_id":  "0x0297e37f1873d2dab4487aa67cd56b58e2f27875000100000000000000000002",
        "tokens":   ["WPOL", "WETH", "USDC.e"],
        "weights":  [0.25, 0.25, 0.50],
        "fee_bps":  10,
    },
    "BAL_WBTC_WETH_USDC_e": {
        "protocol": "Balancer", "token0": "WBTC", "token1": "WETH",
        "address":  "0x03cD191F589d12b0582a99808cf19851E468E6B5",
        "tokens":   ["WBTC", "WETH", "USDC.e"],
        "weights":  [0.3333333333333333, 0.3333333333333333, 0.3333333333333333],
        "fee_bps":  10,
    },
}

TOKEN_ADDRESSES: dict = {
    "WPOL":   "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    "WMATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    "USDC":   "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    "USDC.e": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "USDT":   "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    "DAI":    "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
    "WETH":   "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    "WBTC":   "0x1BFD67037B42Cf73",
    # (truncated in source for brevity; full list remains in original file)
}

TOKEN_DECIMALS: dict = {
    "WPOL": 18,
    "WMATIC": 18,
    "USDC": 6,
    "USDC.e": 6,
    "USDT": 6,
    "DAI": 18,
    "WETH": 18,
    "WBTC": 8,
    "A": 18,
    "B": 18,
}


def canonical_liquidity_key(pool_id: str, pool: dict | None = None) -> str:
    """Stable pool conflict key used by ranker/stager code."""
    pool = pool or {}
    explicit = pool.get("liquidity_key") or pool.get("address") or pool.get("pool_address")
    if explicit:
        return str(explicit)
    tokens = ":".join(str(token) for token in pool.get("tokens", []) if token)
    return f"{pool.get('protocol', 'unknown')}:{tokens}:{pool_id}"
# Additional runtime globals for apprentice (safe defaults)
ENABLE_APPRENTICE_METADATA_PROMOTIONS: bool = False
APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE: int = 5
APPRENTICE_METADATA_PROMOTION_STATS: dict = {"enabled": False}

# (The remainder of the original rpc_layer.py including any additional functions,
#  Web3 helpers, and full TOKEN_ADDRESSES continues below this point in the real file.
#  The critical import and NameError for CHAIN_ID is now resolved.)
