# ==============================================================================
# rpc_layer.py  —  WSS/HTTP RPC connection, deep pool registry, live state loader
# Extracted from Cell 6 of notebooks/omega_v5.ipynb (updated to use publicnode WSS)
# ==============================================================================

import os
import sys
import time
from collections import Counter
from itertools import combinations
from decimal import Decimal
from typing import Optional

import requests
from web3 import Web3

from .config import (
    WSS_URL, HTTP_URL, HTTP_URL_2, CHAINSTACK_URL, CHAIN_ID, ASSET_MATRIX,
    DODO_RPC_EXTRA_HTTP_URLS, DODO_RPC_PROVIDER_URL, DODO_RPC_PROXY_URL, DODO_RPC_SOURCES,
    REDIS_RPC_CACHE_TTL_SECONDS, ENABLE_FACTORY_POOL_DISCOVERY,
    ENABLE_APPRENTICE_METADATA_PROMOTIONS, APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE,
    DISCOVERY_MAX_TOKEN_PAIRS, BROADCAST_RPC_URL, RPC_REQUEST_TIMEOUT_SECONDS,
    POOL_LOAD_SLEEP_SECONDS, DISCOVERY_MAX_PROMOTED_POOLS,
    POLYGON_TOKEN_LIST_BASES, ENABLE_INDEXER_STATE_READS,
    ENABLE_DYNAMIC_POOL_REGISTRY, DYNAMIC_POOLS_JSON_PATH, DYNAMIC_POOL_REGISTRY_MAX_POOLS,
    ENABLE_CURVE_POOL_REGISTRY, CURVE_POOL_REGISTRY_API_BASE_URL,
    CURVE_POOL_REGISTRY_FAMILIES, CURVE_POOL_REGISTRY_MAX_POOLS,
    CURVE_POOL_REGISTRY_MIN_USD_TVL,
)
from .contract_deployments import deployment_address
from .pool_quality import CLMM_AUDIT_KEY, V2_AUDIT_KEY, filter_rankable_pools
from .redis_cache import get_json, key as redis_key, set_json

# ── State ─────────────────────────────────────────────────────────────────────
w3:       Optional[Web3] = None
BLOCK:    int            = 0
RPC_LIVE: bool           = False
FACTORY_DISCOVERY_STATS: dict = {}
LAST_POOL_QUALITY_STATS: dict = {}
POLYGON_TOKEN_LIST_DISCOVERY_STATS: dict = {}
POLYGON_TOKEN_LIST_DISCOVERY_SYMBOLS: list[str] = []
SUBGRAPH_POOL_INTEL_STATS: dict = {}
DYNAMIC_POOL_REGISTRY_STATS: dict = {}
CURVE_POOL_REGISTRY_STATS: dict = {}
APPRENTICE_METADATA_PROMOTION_STATS: dict = {}

UNISWAP_V3_FACTORY_POLYGON = deployment_address("UNISWAP_V3_FACTORY")
QUICKSWAP_V2_FACTORY_POLYGON = deployment_address("QUICKSWAP_V2_FACTORY")
QUICKSWAP_ALGEBRA_FACTORY_POLYGON = deployment_address("QUICKSWAP_ALGEBRA_FACTORY")
BALANCER_VAULT_POLYGON = deployment_address("BALANCER_VAULT")
MULTICALL3_ADDRESS = deployment_address("MULTICALL3_ADDRESS")


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
    if not ENABLE_APPRENTICE_METADATA_PROMOTIONS:
        APPRENTICE_METADATA_PROMOTION_STATS = {"enabled": False}
        return APPRENTICE_METADATA_PROMOTION_STATS
    try:
        from .apprentice_metadata_registry import review_apprentice_metadata_promotions as _review

        APPRENTICE_METADATA_PROMOTION_STATS = _review(
            apply=apply,
            max_promotions=APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE,
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


def connect(
    http_urls: Optional[list[str]] = None,
    wss_url: Optional[str] = None,
    prefer_wss: bool = True,
) -> bool:
    """
    Establishes the best available RPC connection.

    Priority
    --------
    1. WSS  wss://polygon-bor-rpc.publicnode.com  (real-time, low latency)
    2. HTTP https://polygon-bor-rpc.publicnode.com
    3. HTTP https://rpc.ankr.com/polygon
    4. HTTP https://polygon-rpc.com

    Sets module-level ``w3``, ``BLOCK``, and ``RPC_LIVE``.
    Returns True when a live connection is established.
    """
    global w3, BLOCK, RPC_LIVE

    target_wss = wss_url if wss_url is not None else WSS_URL
    if wss_url is None:
        try:
            from .transport_lanes import select_endpoint

            lane_wss = select_endpoint("wss_block_heads", probe_if_stale=False)
            target_wss = lane_wss or target_wss
        except Exception:
            pass

    # 1. WSS first unless a caller explicitly requests HTTP-only validation.
    if prefer_wss and target_wss:
        try:
            ws_provider = getattr(Web3, "WebsocketProvider", None) or getattr(
                Web3, "LegacyWebSocketProvider", None
            )
            if ws_provider is None:
                raise RuntimeError("installed web3 package has no websocket provider")
            try:
                provider = ws_provider(target_wss, websocket_timeout=15)
            except TypeError:
                provider = ws_provider(target_wss)
            _ws = Web3(provider)
            _inject_poa_middleware(_ws)
            BLOCK    = _ws.eth.block_number
            w3       = _ws
            RPC_LIVE = True
            print(f"✅ WSS connected  →  {_host_label(target_wss)}  block #{BLOCK:,}")
            return True
        except Exception as exc:
            print(f"  ⚠️  WSS [{_host_label(target_wss)}] unavailable: {exc}")

    # 2–4. HTTP fallback chain
    if http_urls is not None:
        fallback_urls = http_urls
    else:
        try:
            from .transport_lanes import endpoint_candidates_for_lane, select_endpoint

            lane_read = select_endpoint("v2_reserves_multicall")
            lane_discovery_candidates = endpoint_candidates_for_lane("quickswap_v2_factory_discovery")
        except Exception:
            lane_read = ""
            lane_discovery_candidates = []
        fallback_urls = [
            lane_read,
            HTTP_URL,
            HTTP_URL_2,
            DODO_RPC_PROXY_URL,
            *lane_discovery_candidates,
            *dodo_provider_endpoints(CHAIN_ID),
            BROADCAST_RPC_URL,
            "https://rpc.ankr.com/polygon",
            "https://polygon-rpc.com",
        ]
    for url in dict.fromkeys(filter(None, fallback_urls)):
        if not url:
            continue
        try:
            _cand = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": RPC_REQUEST_TIMEOUT_SECONDS}))
            _inject_poa_middleware(_cand)
            BLOCK    = _cand.eth.block_number
            w3       = _cand
            RPC_LIVE = True
            lbl      = _host_label(url)
            print(f"✅ HTTP connected  →  {lbl}  block #{BLOCK:,}")
            return True
        except Exception as exc:
            lbl = _host_label(url)
            print(f"  ⚠️  HTTP [{lbl}] unavailable: {exc}")

    print("⚠️  All RPC endpoints unreachable. Live pool loading is unavailable.")
    return False


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
    "WBTC":   "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
    "WETH":   "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    "LINK":   "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
    "AAVE":   "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
    "CRV":    "0x172370d5Cd63279eFa6d502DAB29171933a610AF",
    "UNI":    "0xb33EaAd8d922B1083446DC23f610c2567fB5180f",
    "BAL":    "0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3",
    "SUSHI":  "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",
    "QUICK":  "0xB5C064F955D8e7F38fE0460C556a72987494eE17",
    "MKR":    "0x6f7C932e7684666C9fd1d44527765433e01fF61d",
    "COMP":   "0x8505b9d2254a7ae468c0e9dd10ccea3a837aef5c",
    "SNX":    "0x50B728D8D964fd00C2d0AAD81718b71311feF68a",
    "LDO":    "0xc3c7d422809852031b44ab29eec9f1eff2a58756",
    "1INCH":  "0x111111111117dC0aa78b770fA6A738034120C302",
    "GHST":   "0x385Eeac5cb85A38A9a07A70c73e0a3271cfb54A7",
    "GNS":    "0xE5417Af5648c8D19cA30609789a288ceA55312f9",
    "TEL":    "0xdf7837de1f2fa4631d716cf2502f8b230f1dcc32",
    "QI":     "0x580a84c73811e1839f75d86d75d88cca0c241ff4",
    "DFYN":   "0xC168e40227e4ebD8C1cae80f7a55a4f0e6D66C97",
    "DODO":   "0xe4bf2864ebeC7B7fDf6Eeca9BaCAe7cDfDAffe78",
    "ORBS":   "0x614389Eaae0D7558AfdD54A3a433f595A0D45fA7",
    "TRADE":  "0x82362Ec182Db3Cf7829014Bc61E9BE8a2E82868a",
    "NAKA":   "0xd335261a329411707019866085a53856754020a6",
    "VOXEL":  "0xd335261a329411707019866085a53856754020a6",
    "SAND":   "0xbbba073c31bf03b8acf7c28ef0738decf3695683",
    "MANA":   "0xa1c57f48f0deb89f569dfbe6e2b7f46d33606fd4",
    "GRT":    "0x5fe2B58c013d7601147DcdD68C143A77499f5531",
    "RNDR":   "0x61299774020dA444Af134c82fa83E3810b309991",
    "ANKR":   "0x101A023270368c0D50BFfb62780F4aFd4ea79C35",
    "FIS":    "0x7A7B94F18EF6AD056CDa648588181CDA84800f94",
    "FRAX":   "0x45c32fA6DF82ead1e2EF74d17b76547EDdFaFF89",
    "MAI":    "0xa3Fa98414E23E11171f652A9221193399676369f",
    "miMATIC": "0xa3Fa98414E23E11171f652A9221193399676369f",
    "TUSD":   "0x2e1AD108fF1D8C782fcBbB89AAd783aC49586756",
    "agEUR":  "0xE0B52e49357FD4DAf2C15e02058Dce6b20E4F9B7",
    "jEUR":   "0x4e3decbb3645551b8a19f0ea1678079fcb33fb4c",
    "EURe":   "0x18ec7A158E54d133A524A605996256fF597B0002",
    "EURO3":  "0x990e665d95e263d9198305c74238531557989379",
    "EURS":   "0xE1111111111136d80F33A9f8484196C5C0000000",
    "pUSD":   "0x0d15e45a050519318b3687313364426514f77c3e",
    "stMATIC": "0x3A58a54C066FdC4b273006d6724062701f062433",
    "MaticX": "0xfa68FB26207f140329b97d3dCAea1b9A4E9ad76d",
    "wstETH": "0x03b54a6e9a984069379fae1a4fc4dbae93b3bccd",
    "amUSDC": "0x1a136a9e2cd2c13926654e0940c6298ac531284b",
    "amUSDT": "0x60D55F02A771d515e077c9C2403a1ef324885CeC",
    "amDAI":  "0x27F8D03b3a637257009776d65406C61c3B169300",
    "amWETH": "0x28424507fef75107f80ED07c7569192e44b66501",
    "amWBTC": "0x5c2edBa2651048236842944a1BA0E926A8ef8146",
    "bb-a-USD": "0x48e6b98ef6329f8f0a30ebb817403a721f144203",
    "BIFI":   "0xFbdd194376de19a88118e84E279b977f165d01b8",
    "KLIMA":  "0x4e78011ce80ee02d2c3e649fb657e45898257815",
    "SX":     "0x840195888db4d6a99ed9f73fcd3b225bb3cb1a79",
    "ANGLE":  "0x17C491975b2046830f6D480790F3B4B2838706D2",
    "FXS":    "0x1a3acf6D19267E2d3e7f898f42803e90C9219062",
    "BANANA": "0x5d47bAbA0d6986F5bA39470122E9707255028b9C",
    "ICE":    "0xc6C8527E1643c162A5f448b1d966453A26002fB3",
    "ELON":   "0xe0339c80ffde91f3e20494df88d4206d86024cdf",
    "FISH":   "0x3a977E5Cc1214055d4044d6273e669741639d671",
    "FIRE":   "0x9183188E8715106596131c94d0F98E90267C7D08",
    "ELK":    "0xeeE8a71642c31e97f0E7f68534Be24d51A07b67F",
    "WEXPOLY": "0x4C4BF31dB3B5810C3589B10beC447dd1f2717010",
    "TETU":   "0x2557160ec0f33f6042B84406f522190125ee0efD",
    "RETRO":  "0xbFA71C79C83fCC30fF23b1603769965Fd12ce078",
    "MESH":   "0x82362Ec182Db3Cf7829014Bc61E9BE8a2E82868a",
    "COMBO":  "0xba2e30487029a68664e06306a175394134a0ffbf",
}

TOKEN_DISCOVERY_STATUS: dict = {
    "TRADE": "ATTACHMENT_VERIFY_BEFORE_EXECUTION",
    "NAKA": "ATTACHMENT_VERIFY_BEFORE_EXECUTION",
    "VOXEL": "ATTACHMENT_VERIFY_BEFORE_EXECUTION",
    "MESH": "ATTACHMENT_VERIFY_BEFORE_EXECUTION",
    "EURS": "ATTACHMENT_VERIFY_BEFORE_EXECUTION",
}

ADDRESS_TO_SYMBOL: dict = {
    address.lower(): symbol
    for symbol, address in TOKEN_ADDRESSES.items()
    if symbol != "WMATIC"
}

TOKEN_DECIMALS: dict = {
    "WPOL": 18,
    "WMATIC": 18,
    "POL": 18,
    "USDC": 6,
    "USDC.e": 6,
    "USDT": 6,
    "DAI": 18,
    "WBTC": 8,
    "WETH": 18,
    "LINK": 18,
    "AAVE": 18,
    "CRV": 18,
    "UNI": 18,
    "BAL": 18,
    "SUSHI": 18,
    "QUICK": 18,
    "MKR": 18,
    "COMP": 18,
    "SNX": 18,
    "LDO": 18,
    "1INCH": 18,
    "GHST": 18,
    "GNS": 18,
    "TEL": 2,
    "QI": 18,
    "DFYN": 18,
    "DODO": 18,
    "ORBS": 18,
    "TRADE": 18,
    "NAKA": 18,
    "VOXEL": 18,
    "SAND": 18,
    "MANA": 18,
    "GRT": 18,
    "RNDR": 18,
    "ANKR": 18,
    "FIS": 18,
    "FRAX": 18,
    "MAI": 18,
    "miMATIC": 18,
    "TUSD": 18,
    "agEUR": 18,
    "jEUR": 18,
    "EURe": 18,
    "EURO3": 18,
    "EURS": 18,
    "pUSD": 18,
    "stMATIC": 18,
    "MaticX": 18,
    "wstETH": 18,
    "amUSDC": 6,
    "amUSDT": 6,
    "amDAI": 18,
    "amWETH": 18,
    "amWBTC": 8,
    "bb-a-USD": 18,
    "BIFI": 18,
    "KLIMA": 9,
    "SX": 18,
    "ANGLE": 18,
    "FXS": 18,
    "BANANA": 18,
    "ICE": 18,
    "ELON": 18,
    "FISH": 18,
    "FIRE": 18,
    "ELK": 18,
    "WEXPOLY": 18,
    "TETU": 18,
    "RETRO": 18,
    "MESH": 18,
    "COMBO": 18,
}


def canonical_asset_id(symbol: str) -> str:
    """Address-based asset identity; symbols are metadata only."""
    addr = TOKEN_ADDRESSES.get(symbol, "")
    return f"{CHAIN_ID}:{addr.lower()}" if addr else f"{CHAIN_ID}:unknown:{symbol}"


def canonical_liquidity_key(registry_id: str, pool_meta: dict) -> str:
    """
    Canonical native-liquidity identity used for distinct-venue checks.

    The key follows the spec's chain + execution family + execution contract +
    pool identifier + specialization model with available local metadata.
    """
    proto = pool_meta.get("protocol", "unknown")
    address = str(pool_meta.get("address", "")).lower()
    if proto == "UniswapV2":
        factory = str(pool_meta.get("factory_address", QUICKSWAP_V2_FACTORY_POLYGON)).lower()
        return f"{CHAIN_ID}:V2_CPMM:{factory}:{address}"
    if proto in {"UniswapV3", "QuickSwapV3", "Algebra"}:
        default_factory = QUICKSWAP_ALGEBRA_FACTORY_POLYGON if proto in {"QuickSwapV3", "Algebra"} else UNISWAP_V3_FACTORY_POLYGON
        factory = str(pool_meta.get("factory_address", default_factory)).lower()
        fee_tier = pool_meta.get("fee_bps", "")
        family = "ALGEBRA_CLMM" if proto in {"QuickSwapV3", "Algebra"} else "V3_CLMM"
        return f"{CHAIN_ID}:{family}:{factory}:{address}:{fee_tier}"
    if proto == "Balancer":
        vault = str(pool_meta.get("vault_address", BALANCER_VAULT_POLYGON)).lower()
        balancer_pool_id = str(pool_meta.get("pool_id", address)).lower()
        specialization = pool_meta.get("specialization", "weighted")
        return f"{CHAIN_ID}:BALANCER:{vault}:{balancer_pool_id}:{specialization}"
    if proto == "Curve":
        registry = str(pool_meta.get("registry_address", "unknown_registry")).lower()
        variant = pool_meta.get("variant", "stableswap")
        return f"{CHAIN_ID}:CURVE:{registry}:{address}:{variant}"
    route_class = pool_meta.get("route_class", "NATIVE_POOL_ROUTE")
    return f"{CHAIN_ID}:{route_class}:{proto}:{address}:{registry_id}"


def _normalize_units(value: int, symbol: str) -> Decimal:
    decimals = TOKEN_DECIMALS.get(symbol, 18)
    return Decimal(value) / (Decimal(10) ** decimals)


def _v3_decimal_adjustment(token0: str, token1: str) -> Decimal:
    dec0 = TOKEN_DECIMALS.get(token0, 18)
    dec1 = TOKEN_DECIMALS.get(token1, 18)
    return Decimal(10) ** Decimal(dec0 - dec1)


def _resolve_pair_token_details(contract, pool_meta: dict) -> tuple[list[str], list[str]]:
    """Returns on-chain token0/token1 symbols and raw lowercase addresses."""
    try:
        token0_addr = contract.functions.token0().call().lower()
        token1_addr = contract.functions.token1().call().lower()
        token0 = ADDRESS_TO_SYMBOL.get(token0_addr)
        token1 = ADDRESS_TO_SYMBOL.get(token1_addr)
        if token0 and token1:
            return [token0, token1], [token0_addr, token1_addr]
        return [
            token0 or pool_meta["token0"],
            token1 or pool_meta["token1"],
        ], [token0_addr, token1_addr]
    except Exception:
        return [pool_meta["token0"], pool_meta["token1"]], []


def _resolve_pair_tokens(contract, pool_meta: dict) -> list:
    """Returns on-chain token0/token1 symbols for V2/V3 pools."""
    return _resolve_pair_token_details(contract, pool_meta)[0]


def _fetch_erc20_decimals(token_addrs: list[str]) -> list[int | None]:
    if len(token_addrs) != 2 or not all(token_addrs):
        return [None, None]

    contracts = [
        w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_ABI_ERC20)
        for addr in token_addrs
    ]
    try:
        results = multicall3_aggregate([
            (token_addrs[0], False, _encode_fn(contracts[0], "decimals")),
            (token_addrs[1], False, _encode_fn(contracts[1], "decimals")),
        ])
        return [
            int(w3.codec.decode(["uint8"], results[0][1])[0]),
            int(w3.codec.decode(["uint8"], results[1][1])[0]),
        ]
    except Exception:
        values: list[int | None] = []
        for contract in contracts:
            try:
                values.append(int(contract.functions.decimals().call()))
            except Exception:
                values.append(None)
        return values


def _clmm_price_from_sqrt(sqrt_price_x96: Decimal, decimal_adjustment: Decimal) -> Decimal:
    # For maximum precision, use a Decimal representation of the Q96 constant.
    price_scale = sqrt_price_x96 / Decimal(2**96)
    return price_scale * price_scale * decimal_adjustment


def _audit_clmm_orientation_decimals(
    *,
    pool_id: str,
    pool_meta: dict,
    proto: str,
    toks: list[str],
    token_addrs: list[str],
    onchain_decimals: list[int | None],
    sqrt_price_x96: Decimal,
    liquidity: Decimal,
    decimal_adjustment: Decimal,
) -> dict:
    registered_toks = [pool_meta.get("token0"), pool_meta.get("token1")]
    expected_addrs = [TOKEN_ADDRESSES.get(toks[0], ""), TOKEN_ADDRESSES.get(toks[1], "")]
    expected_decimals = [TOKEN_DECIMALS.get(toks[0]), TOKEN_DECIMALS.get(toks[1])]
    expected_adjustment = _v3_decimal_adjustment(toks[0], toks[1]) if len(toks) == 2 else Decimal("0")
    price_token1_per_token0 = Decimal("0")
    reject_reasons: list[str] = []

    if len(toks) != 2 or len(set(toks)) != 2:
        reject_reasons.append("invalid_onchain_token_pair")
    if len(token_addrs) != 2 or not all(token_addrs):
        reject_reasons.append("missing_onchain_token_addresses")
    if len(token_addrs) == 2 and len(expected_addrs) == 2:
        for idx, (actual, expected) in enumerate(zip(token_addrs, expected_addrs)):
            if not actual or not expected or actual.lower() != expected.lower():
                reject_reasons.append(f"token{idx}_address_symbol_mismatch")
    if sorted(registered_toks) != sorted(toks):
        reject_reasons.append("registered_pair_does_not_match_onchain_pair")
    if len(onchain_decimals) != 2 or any(value is None for value in onchain_decimals):
        reject_reasons.append("missing_onchain_decimals")
    else:
        for idx, (actual, expected) in enumerate(zip(onchain_decimals, expected_decimals)):
            if expected is None or int(actual) != int(expected):
                reject_reasons.append(f"token{idx}_decimals_mismatch")
    if sqrt_price_x96 <= 0:
        reject_reasons.append("non_positive_sqrt_price")
    if liquidity <= 0:
        reject_reasons.append("non_positive_liquidity")
    if decimal_adjustment != expected_adjustment:
        reject_reasons.append("decimal_adjustment_mismatch")
    try:
        price_token1_per_token0 = _clmm_price_from_sqrt(sqrt_price_x96, decimal_adjustment)
        if price_token1_per_token0 <= 0:
            reject_reasons.append("non_positive_normalized_price")
    except Exception:
        reject_reasons.append("normalized_price_decode_failed")

    return {
        "status": "fail" if reject_reasons else "pass",
        "gate": "v3_algebra_orientation_decimals",
        "pool_id": pool_id,
        "protocol": proto,
        "registered_tokens": registered_toks,
        "onchain_tokens": list(toks),
        "onchain_addresses": [Web3.to_checksum_address(addr) for addr in token_addrs] if len(token_addrs) == 2 and all(token_addrs) else [],
        "registered_order_matches_onchain": registered_toks == toks,
        "registered_pair_matches_onchain": sorted(registered_toks) == sorted(toks),
        "expected_decimals": expected_decimals,
        "onchain_decimals": onchain_decimals,
        "decimal_adjustment": str(decimal_adjustment),
        "expected_decimal_adjustment": str(expected_adjustment),
        "sqrtPriceX96": str(sqrt_price_x96),
        "liquidity": str(liquidity),
        "price_token1_per_token0": str(price_token1_per_token0),
        "price_token0_per_token1": str((Decimal("1") / price_token1_per_token0) if price_token1_per_token0 > 0 else Decimal("0")),
        "reject_reasons": reject_reasons,
    }


def _audit_v2_pair_canonical(
    *,
    pool_id: str,
    pool_meta: dict,
    toks: list[str],
    token_addrs: list[str],
    onchain_decimals: list[int | None],
    reserves_raw: list[int],
) -> dict:
    registered_toks = [pool_meta.get("token0"), pool_meta.get("token1")]
    expected_addrs = [TOKEN_ADDRESSES.get(toks[0], ""), TOKEN_ADDRESSES.get(toks[1], "")] if len(toks) == 2 else []
    expected_decimals = [TOKEN_DECIMALS.get(toks[0]), TOKEN_DECIMALS.get(toks[1])] if len(toks) == 2 else []
    reject_reasons: list[str] = []

    if len(toks) != 2 or len(set(toks)) != 2:
        reject_reasons.append("invalid_onchain_token_pair")
    if len(token_addrs) != 2 or not all(token_addrs):
        reject_reasons.append("missing_onchain_token_addresses")
    if len(token_addrs) == 2:
        for idx, actual in enumerate(token_addrs):
            if actual and actual.lower() not in ADDRESS_TO_SYMBOL:
                reject_reasons.append(f"token{idx}_unknown_onchain_address")
    if len(token_addrs) == 2 and len(expected_addrs) == 2:
        for idx, (actual, expected) in enumerate(zip(token_addrs, expected_addrs)):
            if not actual or not expected or actual.lower() != expected.lower():
                reject_reasons.append(f"token{idx}_address_symbol_mismatch")
    if sorted(registered_toks) != sorted(toks):
        reject_reasons.append("registered_pair_does_not_match_onchain_pair")
    if len(onchain_decimals) != 2 or any(value is None for value in onchain_decimals):
        reject_reasons.append("missing_onchain_decimals")
    else:
        for idx, (actual, expected) in enumerate(zip(onchain_decimals, expected_decimals)):
            if expected is None or int(actual) != int(expected):
                reject_reasons.append(f"token{idx}_decimals_mismatch")
    if len(reserves_raw) != 2 or any(Decimal(str(value)) <= 0 for value in reserves_raw):
        reject_reasons.append("non_positive_reserve")

    return {
        "status": "fail" if reject_reasons else "pass",
        "gate": "v2_pair_canonical",
        "pool_id": pool_id,
        "protocol": "UniswapV2",
        "registered_tokens": registered_toks,
        "onchain_tokens": list(toks),
        "onchain_addresses": [Web3.to_checksum_address(addr) for addr in token_addrs] if len(token_addrs) == 2 and all(token_addrs) else [],
        "registered_order_matches_onchain": registered_toks == toks,
        "registered_pair_matches_onchain": sorted(registered_toks) == sorted(toks),
        "expected_addresses": [Web3.to_checksum_address(addr) for addr in expected_addrs if addr],
        "expected_decimals": expected_decimals,
        "onchain_decimals": onchain_decimals,
        "reserves_raw": [str(value) for value in reserves_raw],
        "reject_reasons": reject_reasons,
    }


def _registered_balancer_tokens(pool_meta: dict) -> list[str]:
    return [
        token
        for token in list(pool_meta.get("tokens") or [pool_meta.get("token0"), pool_meta.get("token1")])
        if token
    ]


def _audit_balancer_remap(pool_id: str, pool_meta: dict, token_addrs: list, toks: list[str]) -> dict | None:
    registered = _registered_balancer_tokens(pool_meta)
    if registered == toks:
        return None

    remap = {
        "pool_id": pool_id,
        "balancer_pool_id": pool_meta.get("pool_id"),
        "registered_tokens": registered,
        "registered_addresses": [TOKEN_ADDRESSES.get(symbol, "") for symbol in registered],
        "onchain_tokens": list(toks),
        "onchain_addresses": [Web3.to_checksum_address(addr) for addr in token_addrs],
        "reason": "Vault.getPoolTokens token list differs from registered metadata",
    }
    pool_meta.setdefault("_meta", {})["balancer_remap"] = remap
    pool_meta["tokens"] = list(toks)
    if len(toks) >= 2:
        pool_meta["token0"] = toks[0]
        pool_meta["token1"] = toks[1]
    return remap

# ── ABI Fragments ─────────────────────────────────────────────────────────────
_ABI_V2_PAIR = [
    {"name": "token0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "token1", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "getReserves", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [
         {"name": "reserve0",            "type": "uint112"},
         {"name": "reserve1",            "type": "uint112"},
         {"name": "blockTimestampLast",  "type": "uint32"},
     ]},
]
_ABI_V3_POOL = [
    {"name": "token0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "token1", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "slot0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [
         {"name": "sqrtPriceX96",              "type": "uint160"},
         {"name": "tick",                       "type": "int24"},
         {"name": "observationIndex",           "type": "uint16"},
         {"name": "observationCardinality",     "type": "uint16"},
         {"name": "observationCardinalityNext", "type": "uint16"},
         {"name": "feeProtocol",               "type": "uint8"},
         {"name": "unlocked",                   "type": "bool"},
     ]},
    {"name": "liquidity", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint128"}]},
    {"name": "tickSpacing", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "int24"}]},
]
_ABI_ERC20 = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
]
_ABI_V2_FACTORY = [
    {"name": "getPair", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}],
     "outputs": [{"name": "pair", "type": "address"}]},
]
_ABI_V3_FACTORY = [
    {"name": "getPool", "type": "function", "stateMutability": "view",
     "inputs": [
         {"name": "tokenA", "type": "address"},
         {"name": "tokenB", "type": "address"},
         {"name": "fee", "type": "uint24"},
     ],
     "outputs": [{"name": "pool", "type": "address"}]},
]
_ABI_ALGEBRA_FACTORY = [
    {"name": "poolByPair", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}],
     "outputs": [{"name": "pool", "type": "address"}]},
]
_ABI_ALGEBRA_POOL = [
    {"name": "token0", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "token1", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "address"}]},
    {"name": "globalState", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [
         {"name": "price", "type": "uint160"},
         {"name": "tick", "type": "int24"},
         {"name": "lastFee", "type": "uint16"},
         {"name": "timepointIndex", "type": "uint16"},
         {"name": "communityFeeToken0", "type": "uint8"},
         {"name": "communityFeeToken1", "type": "uint8"},
         {"name": "unlocked", "type": "bool"},
     ]},
    {"name": "liquidity", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint128"}]},
    {"name": "tickSpacing", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "int24"}]},
]
_ABI_CURVE_POOL = [
    {"name": "coins", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "i", "type": "uint256"}],
     "outputs": [{"name": "", "type": "address"}]},
    {"name": "balances", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "i", "type": "uint256"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "fee", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},
]
_ABI_BALANCER_VAULT = [
    {"name": "getPoolTokens", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "poolId", "type": "bytes32"}],
     "outputs": [
         {"name": "tokens", "type": "address[]"},
         {"name": "balances", "type": "uint256[]"},
         {"name": "lastChangeBlock", "type": "uint256"},
     ]},
]
_ABI_BALANCER_WEIGHTED_POOL = [
    {"name": "getPoolId", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "bytes32"}]},
    {"name": "getNormalizedWeights", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256[]"}]},
    {"name": "getSwapFeePercentage", "type": "function", "stateMutability": "view",
     "inputs": [], "outputs": [{"name": "", "type": "uint256"}]},
]

_ABI_MULTICALL3 = [
    {
        "name": "aggregate3",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [{
            "name": "calls",
            "type": "tuple[]",
            "components": [
                {"name": "target", "type": "address"},
                {"name": "allowFailure", "type": "bool"},
                {"name": "callData", "type": "bytes"},
            ],
        }],
        "outputs": [{
            "name": "returnData",
            "type": "tuple[]",
            "components": [
                {"name": "success", "type": "bool"},
                {"name": "returnData", "type": "bytes"},
            ],
        }],
    }
]


def multicall3_aggregate(calls: list[tuple[str, bool, bytes]]) -> list[tuple[bool, bytes]]:
    if not RPC_LIVE or w3 is None or not MULTICALL3_ADDRESS:
        raise RuntimeError("Multicall3 unavailable")
    contract = w3.eth.contract(address=Web3.to_checksum_address(MULTICALL3_ADDRESS), abi=_ABI_MULTICALL3)
    normalized = [
        (Web3.to_checksum_address(target), bool(allow_failure), call_data)
        for target, allow_failure, call_data in calls
    ]
    return contract.functions.aggregate3(normalized).call(block_identifier="latest")


def _encode_fn(contract, fn_name: str, args: list | None = None) -> bytes:
    args = args or []
    if hasattr(contract, "encodeABI"):
        data = contract.encodeABI(fn_name=fn_name, args=args)
    else:
        data = contract.encode_abi(fn_name, args=args)
    return bytes.fromhex(data[2:])


def _has_code(address: str) -> bool:
    if w3 is None or not address or int(address, 16) == 0:
        return False
    try:
        return w3.eth.get_code(Web3.to_checksum_address(address)).hex() not in ("", "0x")
    except Exception:
        return False


NATIVE_USDC_SYMBOL = "USDC"
BRIDGED_USDC_SYMBOL = "USDC.e"
BRIDGED_STABLE_VARIANTS = {NATIVE_USDC_SYMBOL, BRIDGED_USDC_SYMBOL}

ALGEBRA_DISCOVERY_PAIR_HINTS = {
    tuple(sorted(pair))
    for pair in [
        ("USDC", "DAI"),
        ("WBTC", "WETH"),
        ("USDC.e", "WETH"),
        ("USDC.e", "USDT"),
        ("USDC.e", "DAI"),
        ("USDC.e", "WBTC"),
        ("USDT", "WETH"),
        ("USDT", "WPOL"),
        ("USDT", "DAI"),
        ("USDC", "USDT"),
        ("USDC", "DAI"),
        ("USDC", "WPOL"),
        ("LINK", "WETH"),
        ("AAVE", "WETH"),
        ("WPOL", "WETH"),
        ("WPOL", "USDC"),
    ]
}


V2_DISCOVERY_PAIR_HINTS_ORDERED = [
        ("USDC.e", "USDT"),
        ("USDC.e", "DAI"),
        ("USDC.e", "WPOL"),
        ("USDC.e", "WETH"),
        ("USDC.e", "WBTC"),
        ("USDT", "WETH"),
        ("USDT", "WPOL"),
        ("USDT", "DAI"),
        ("USDC", "USDC.e"),
        ("USDC", "USDT"),
        ("USDC", "DAI"),
        ("USDC", "WPOL"),
        ("USDC", "WETH"),
        ("WPOL", "WETH"),
        ("WBTC", "WETH"),
        ("LINK", "WETH"),
        ("AAVE", "WETH"),
        ("CRV", "WETH"),
        ("BAL", "WETH"),
        ("UNI", "WETH"),
        ("SUSHI", "WETH"),
        ("QUICK", "WPOL"),
]

DISCOVERY_PAIR_HINTS_ORDERED = [
        ("USDC", "USDC.e"),
        ("USDC.e", "USDT"),
        ("USDC.e", "DAI"),
        ("USDC.e", "WETH"),
        ("USDC.e", "WBTC"),
        ("USDC", "USDT"),
        ("USDC", "DAI"),
        ("USDC", "WPOL"),
        ("USDC", "WETH"),
        ("USDT", "WETH"),
        ("USDT", "WPOL"),
        ("USDT", "DAI"),
        ("WPOL", "WETH"),
        ("WBTC", "WETH"),
        ("LINK", "WETH"),
        ("AAVE", "WETH"),
        ("CRV", "WETH"),
        ("BAL", "WETH"),
        ("UNI", "WETH"),
]

DISCOVERY_PAIR_HINTS = {tuple(sorted(pair)) for pair in DISCOVERY_PAIR_HINTS_ORDERED}
V2_DISCOVERY_PAIR_HINTS = {tuple(sorted(pair)) for pair in V2_DISCOVERY_PAIR_HINTS_ORDERED}


def _prioritized_discovery_pairs(
    symbols: list[str],
    *,
    hint_order: list[tuple[str, str]] | None = None,
    deprioritize_native_usdc: bool = False,
    priority_symbols: list[str] | None = None,
) -> list[tuple[str, str]]:
    ordered_symbols = list(dict.fromkeys(symbols))
    broad_pairs = list(combinations(ordered_symbols, 2))
    hint_order = hint_order or DISCOVERY_PAIR_HINTS_ORDERED
    hinted: list[tuple[str, str]] = []
    for token_a, token_b in hint_order:
        if token_a in ordered_symbols and token_b in ordered_symbols:
            pair = (token_a, token_b)
            reverse = (token_b, token_a)
            if pair in broad_pairs:
                hinted.append(pair)
            elif reverse in broad_pairs:
                hinted.append(reverse)
    hinted = list(dict.fromkeys(hinted))
    hinted_set = {tuple(sorted(pair)) for pair in hinted}
    priority: list[tuple[str, str]] = []
    priority_set: set[tuple[str, str]] = set()
    if priority_symbols:
        base_symbols = [
            base for base in POLYGON_TOKEN_LIST_BASES
            if base in ordered_symbols
        ]
        for candidate in priority_symbols:
            if candidate not in ordered_symbols:
                continue
            for base in base_symbols:
                if base == candidate:
                    continue
                pair = (base, candidate)
                reverse = (candidate, base)
                selected = pair if pair in broad_pairs else reverse if reverse in broad_pairs else None
                if not selected:
                    continue
                key = tuple(sorted(selected))
                if key in hinted_set or key in priority_set:
                    continue
                priority.append(selected)
                priority_set.add(key)
    rest = [
        pair for pair in broad_pairs
        if tuple(sorted(pair)) not in hinted_set and tuple(sorted(pair)) not in priority_set
    ]
    if deprioritize_native_usdc:
        native_rest = [
            pair for pair in rest
            if NATIVE_USDC_SYMBOL in pair and BRIDGED_USDC_SYMBOL not in pair
        ]
        rest = [
            pair for pair in rest
            if not (NATIVE_USDC_SYMBOL in pair and BRIDGED_USDC_SYMBOL not in pair)
        ] + native_rest
    ordered_pairs = hinted + priority + rest
    window_size = int(os.environ.get("DISCOVERY_PAIR_WINDOW_SIZE", "0") or "0")
    if window_size > 0 and len(ordered_pairs) > window_size:
        offset = int(os.environ.get("DISCOVERY_PAIR_WINDOW_OFFSET", "0") or "0")
        start = offset % len(ordered_pairs)
        rotated = ordered_pairs[start:] + ordered_pairs[:start]
        return rotated[:window_size]
    if int(DISCOVERY_MAX_TOKEN_PAIRS or 0) <= 0:
        return ordered_pairs
    return ordered_pairs[:DISCOVERY_MAX_TOKEN_PAIRS]


def hydrate_polygon_token_list_candidates(force_refresh: bool = False) -> list[str]:
    """
    Add vetted Polygon token-list candidates to the runtime symbol maps.

    This is discovery metadata only. These symbols can be used to probe factory
    pools, but execution eligibility is still decided later by pool state,
    quoter/exact-call validation, adapter coverage, and profit gates.
    """
    global POLYGON_TOKEN_LIST_DISCOVERY_STATS, POLYGON_TOKEN_LIST_DISCOVERY_SYMBOLS
    try:
        from .polygon_token_list import fetch_polygon_pos_candidates

        candidates, stats = fetch_polygon_pos_candidates(
            known_addresses=TOKEN_ADDRESSES.values(),
            known_symbols=TOKEN_ADDRESSES.keys(),
            force_refresh=force_refresh,
        )
        added: list[str] = []
        for candidate in candidates:
            symbol = candidate.symbol.strip()
            address_l = candidate.address.lower()
            if not symbol or symbol in TOKEN_ADDRESSES or address_l in ADDRESS_TO_SYMBOL:
                continue
            TOKEN_ADDRESSES[symbol] = candidate.address
            TOKEN_DECIMALS[symbol] = candidate.decimals
            TOKEN_DISCOVERY_STATUS[symbol] = candidate.discovery_status
            ADDRESS_TO_SYMBOL[address_l] = symbol
            added.append(symbol)
        POLYGON_TOKEN_LIST_DISCOVERY_SYMBOLS = added
        POLYGON_TOKEN_LIST_DISCOVERY_STATS = {
            **stats,
            "runtime_added": len(added),
            "base_pair_bias": POLYGON_TOKEN_LIST_BASES,
        }
        return added
    except Exception as exc:
        POLYGON_TOKEN_LIST_DISCOVERY_SYMBOLS = []
        POLYGON_TOKEN_LIST_DISCOVERY_STATS = {
            "enabled": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        return []


def discover_factory_pool_registry(base_registry: dict | None = None) -> dict:
    """
    Discover additional live V2/V3 pools from protocol factories.

    This is live-only and bytecode-validated. It never creates synthetic pools.
    """
    global FACTORY_DISCOVERY_STATS, SUBGRAPH_POOL_INTEL_STATS, DYNAMIC_POOL_REGISTRY_STATS, CURVE_POOL_REGISTRY_STATS
    registry = dict(base_registry or DEEP_POOL_REGISTRY)
    if not ENABLE_FACTORY_POOL_DISCOVERY or not RPC_LIVE or w3 is None:
        FACTORY_DISCOVERY_STATS = {
            "enabled": bool(ENABLE_FACTORY_POOL_DISCOVERY),
            "live_candidates": 0,
            "promoted": 0,
            "live_by_protocol": {},
            "promoted_by_protocol": {},
            "active_limit": DISCOVERY_MAX_PROMOTED_POOLS,
            "pair_scan_limit": DISCOVERY_MAX_TOKEN_PAIRS,
            "v2_anchor": BRIDGED_USDC_SYMBOL,
            "bridge_variants": sorted(BRIDGED_STABLE_VARIANTS),
            "polygon_token_list": POLYGON_TOKEN_LIST_DISCOVERY_STATS,
            "subgraph_pool_intel": SUBGRAPH_POOL_INTEL_STATS,
            "dynamic_pool_registry": DYNAMIC_POOL_REGISTRY_STATS,
            "curve_pool_registry": CURVE_POOL_REGISTRY_STATS,
            "apprentice_metadata_promotions": APPRENTICE_METADATA_PROMOTION_STATS,
        }
        return registry

    apprentice_promotions = review_apprentice_metadata_promotions(apply=True)

    known_addresses = {
        str(meta.get("address", "")).lower()
        for meta in registry.values()
        if meta.get("address")
    }
    if ENABLE_DYNAMIC_POOL_REGISTRY:
        try:
            from .external_pool_registry import load_dynamic_pool_registry

            imported = load_dynamic_pool_registry(
                DYNAMIC_POOLS_JSON_PATH,
                address_to_symbol=ADDRESS_TO_SYMBOL,
                token_addresses=TOKEN_ADDRESSES,
                known_pool_addresses=known_addresses,
                max_pools=DYNAMIC_POOL_REGISTRY_MAX_POOLS,
            )
            registry.update(imported.registry)
            DYNAMIC_POOL_REGISTRY_STATS = imported.stats
        except Exception as exc:
            DYNAMIC_POOL_REGISTRY_STATS = {
                "enabled": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
    else:
        DYNAMIC_POOL_REGISTRY_STATS = {"enabled": False}

    known_addresses = {
        str(meta.get("address", "")).lower()
        for meta in registry.values()
        if meta.get("address")
    }
    if ENABLE_CURVE_POOL_REGISTRY:
        try:
            from .curve_pool_registry import load_curve_pool_registry

            imported_curve = load_curve_pool_registry(
                api_base_url=CURVE_POOL_REGISTRY_API_BASE_URL,
                families=CURVE_POOL_REGISTRY_FAMILIES,
                address_to_symbol=ADDRESS_TO_SYMBOL,
                token_addresses=TOKEN_ADDRESSES,
                token_decimals=TOKEN_DECIMALS,
                token_discovery_status=TOKEN_DISCOVERY_STATUS,
                known_pool_addresses=known_addresses,
                max_pools=CURVE_POOL_REGISTRY_MAX_POOLS,
                min_usd_tvl=CURVE_POOL_REGISTRY_MIN_USD_TVL,
            )
            registry.update(imported_curve.registry)
            CURVE_POOL_REGISTRY_STATS = imported_curve.stats
        except Exception as exc:
            CURVE_POOL_REGISTRY_STATS = {
                "enabled": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
    else:
        CURVE_POOL_REGISTRY_STATS = {"enabled": False}

    token_list_symbols = hydrate_polygon_token_list_candidates()
    configured_symbols = [
        symbol for symbol in ASSET_MATRIX
        if symbol in TOKEN_ADDRESSES and symbol != "WMATIC"
        and not str(TOKEN_DISCOVERY_STATUS.get(symbol, "")).startswith("ATTACHMENT_VERIFY")
    ]
    symbols = list(dict.fromkeys(configured_symbols + token_list_symbols))
    pairs = _prioritized_discovery_pairs(
        symbols,
        priority_symbols=token_list_symbols,
    )
    v2_pairs = _prioritized_discovery_pairs(
        symbols,
        hint_order=V2_DISCOVERY_PAIR_HINTS_ORDERED,
        deprioritize_native_usdc=True,
        priority_symbols=token_list_symbols,
    )
    live_candidates = 0
    promoted = 0
    live_by_protocol = Counter()
    promoted_by_protocol = Counter()
    unbounded_promotions = int(DISCOVERY_MAX_PROMOTED_POOLS or 0) <= 0
    algebra_reserve = 0 if unbounded_promotions else min(len(ALGEBRA_DISCOVERY_PAIR_HINTS), DISCOVERY_MAX_PROMOTED_POOLS)

    def _can_promote(address: str, protocol: str) -> bool:
        if address.lower() in known_addresses:
            return False
        if unbounded_promotions:
            return True
        effective_limit = DISCOVERY_MAX_PROMOTED_POOLS
        if protocol != "QuickSwapV3":
            effective_limit = max(0, DISCOVERY_MAX_PROMOTED_POOLS - algebra_reserve)
        return promoted < effective_limit

    try:
        v2_factory = w3.eth.contract(
            address=Web3.to_checksum_address(QUICKSWAP_V2_FACTORY_POLYGON),
            abi=_ABI_V2_FACTORY,
        )
        v2_calls = [
            (
                QUICKSWAP_V2_FACTORY_POLYGON,
                True,
                _encode_fn(v2_factory, "getPair", [
                    Web3.to_checksum_address(TOKEN_ADDRESSES[token_a]),
                    Web3.to_checksum_address(TOKEN_ADDRESSES[token_b]),
                ]),
            )
            for token_a, token_b in v2_pairs
        ]
        v2_results = multicall3_aggregate(v2_calls)
        for (token_a, token_b), result in zip(v2_pairs, v2_results):
            if not result[0] or not result[1]:
                continue
            pair_addr = w3.codec.decode(["address"], result[1])[0]
            if not _has_code(pair_addr):
                continue
            live_candidates += 1
            live_by_protocol["UniswapV2"] += 1
            if not _can_promote(pair_addr, "UniswapV2"):
                continue
            pool_id = f"DISC_QS_{token_a}_{token_b}".replace(".", "_")
            registry[pool_id] = {
                "protocol": "UniswapV2",
                "token0": token_a,
                "token1": token_b,
                "address": pair_addr,
                "fee_bps": 30,
                "factory_address": QUICKSWAP_V2_FACTORY_POLYGON,
            }
            known_addresses.add(pair_addr.lower())
            promoted += 1
            promoted_by_protocol["UniswapV2"] += 1
    except Exception as exc:
        print(f"  ⚠️  QuickSwap factory discovery unavailable: {exc}")

    try:
        v3_factory = w3.eth.contract(
            address=Web3.to_checksum_address(UNISWAP_V3_FACTORY_POLYGON),
            abi=_ABI_V3_FACTORY,
        )
        v3_tasks = [
            (token_a, token_b, fee)
            for token_a, token_b in pairs
            for fee in (100, 500, 3000, 10000)
        ]
        v3_calls = [
            (
                UNISWAP_V3_FACTORY_POLYGON,
                True,
                _encode_fn(v3_factory, "getPool", [
                        Web3.to_checksum_address(TOKEN_ADDRESSES[token_a]),
                        Web3.to_checksum_address(TOKEN_ADDRESSES[token_b]),
                        fee,
                ]),
            )
            for token_a, token_b, fee in v3_tasks
        ]
        v3_results = multicall3_aggregate(v3_calls)
        for (token_a, token_b, fee), result in zip(v3_tasks, v3_results):
            if not result[0] or not result[1]:
                continue
            pool_addr = w3.codec.decode(["address"], result[1])[0]
            if not _has_code(pool_addr):
                continue
            live_candidates += 1
            live_by_protocol["UniswapV3"] += 1
            if not _can_promote(pool_addr, "UniswapV3"):
                continue
            pool_id = f"DISC_V3_{token_a}_{token_b}_{fee}".replace(".", "_")
            registry[pool_id] = {
                "protocol": "UniswapV3",
                "token0": token_a,
                "token1": token_b,
                "address": pool_addr,
                "fee_bps": fee,
                "factory_address": UNISWAP_V3_FACTORY_POLYGON,
            }
            known_addresses.add(pool_addr.lower())
            promoted += 1
            promoted_by_protocol["UniswapV3"] += 1
    except Exception as exc:
        print(f"  ⚠️  Uniswap V3 factory discovery unavailable: {exc}")

    try:
        algebra_factory = w3.eth.contract(
            address=Web3.to_checksum_address(QUICKSWAP_ALGEBRA_FACTORY_POLYGON),
            abi=_ABI_ALGEBRA_FACTORY,
        )
        algebra_pairs = [
            pair for pair in pairs
            if tuple(sorted(pair)) in ALGEBRA_DISCOVERY_PAIR_HINTS
        ]
        for token_a, token_b in algebra_pairs:
            try:
                pool_addr = algebra_factory.functions.poolByPair(
                    Web3.to_checksum_address(TOKEN_ADDRESSES[token_a]),
                    Web3.to_checksum_address(TOKEN_ADDRESSES[token_b]),
                ).call()
            except Exception:
                continue
            if not _has_code(pool_addr):
                continue
            live_candidates += 1
            live_by_protocol["QuickSwapV3"] += 1
            if not _can_promote(pool_addr, "QuickSwapV3"):
                continue
            pool_id = f"DISC_ALGEBRA_{token_a}_{token_b}".replace(".", "_")
            registry[pool_id] = {
                "protocol": "QuickSwapV3",
                "token0": token_a,
                "token1": token_b,
                "address": pool_addr,
                "fee_bps": Decimal("7.4"),
                "factory_address": QUICKSWAP_ALGEBRA_FACTORY_POLYGON,
            }
            known_addresses.add(pool_addr.lower())
            promoted += 1
            promoted_by_protocol["QuickSwapV3"] += 1
    except Exception as exc:
        print(f"  ⚠️  QuickSwap Algebra discovery unavailable: {exc}")

    try:
        from .subgraph_intel import discover_subgraph_v3_candidates

        subgraph_candidates, SUBGRAPH_POOL_INTEL_STATS = discover_subgraph_v3_candidates()
        subgraph_promoted = 0
        for candidate in sorted(
            subgraph_candidates,
            key=lambda item: (item.liquidity_usd, item.volume_usd),
            reverse=True,
        ):
            if not _has_code(candidate.address):
                continue
            token0 = ADDRESS_TO_SYMBOL.get(candidate.token0_address) or candidate.token0_symbol
            token1 = ADDRESS_TO_SYMBOL.get(candidate.token1_address) or candidate.token1_symbol
            token0 = "WPOL" if token0 in {"MATIC", "WMATIC", "POL"} else token0
            token1 = "WPOL" if token1 in {"MATIC", "WMATIC", "POL"} else token1
            if token0 not in TOKEN_ADDRESSES or token1 not in TOKEN_ADDRESSES:
                continue
            live_candidates += 1
            live_by_protocol[candidate.protocol] += 1
            if not _can_promote(candidate.address, candidate.protocol):
                continue
            pool_id = (
                f"DISC_SUBGRAPH_{candidate.source}_{token0}_{token1}_{candidate.fee_tier}"
                .replace(".", "_")
                .replace("-", "_")
            )
            if candidate.address.lower() in known_addresses:
                continue
            registry[pool_id] = {
                "protocol": candidate.protocol,
                "token0": token0,
                "token1": token1,
                "address": candidate.address,
                "fee_bps": candidate.fee_tier or (Decimal("7.4") if candidate.protocol == "QuickSwapV3" else 3000),
                "factory_address": (
                    QUICKSWAP_ALGEBRA_FACTORY_POLYGON
                    if candidate.protocol == "QuickSwapV3"
                    else UNISWAP_V3_FACTORY_POLYGON
                ),
                "_meta": {
                    "discovery_source": candidate.source,
                    "subgraph_liquidity_usd": str(candidate.liquidity_usd),
                    "subgraph_volume_usd": str(candidate.volume_usd),
                    "subgraph_execution_policy": "rpc_state_verification_required",
                },
            }
            known_addresses.add(candidate.address.lower())
            promoted += 1
            subgraph_promoted += 1
            promoted_by_protocol[candidate.protocol] += 1
        SUBGRAPH_POOL_INTEL_STATS = {
            **SUBGRAPH_POOL_INTEL_STATS,
            "promoted": subgraph_promoted,
        }
    except Exception as exc:
        SUBGRAPH_POOL_INTEL_STATS = {
            "enabled": True,
            "error": f"{type(exc).__name__}: {exc}",
        }

    FACTORY_DISCOVERY_STATS = {
        "enabled": True,
        "live_candidates": live_candidates,
        "promoted": promoted,
        "live_by_protocol": dict(live_by_protocol),
        "promoted_by_protocol": dict(promoted_by_protocol),
        "active_limit": DISCOVERY_MAX_PROMOTED_POOLS,
        "pair_scan_limit": DISCOVERY_MAX_TOKEN_PAIRS,
        "pair_scan_counts": {
            "v3_uniswap_algebra_pairs_this_cycle": len(pairs),
            "v2_pairs_this_cycle": len(v2_pairs),
        },
        "pair_scan_window": {
            "size": int(os.environ.get("DISCOVERY_PAIR_WINDOW_SIZE", "0") or "0"),
            "offset": int(os.environ.get("DISCOVERY_PAIR_WINDOW_OFFSET", "0") or "0"),
        },
        "unbounded_pair_scan": int(DISCOVERY_MAX_TOKEN_PAIRS or 0) <= 0,
        "unbounded_promotions": unbounded_promotions,
        "v2_anchor": BRIDGED_USDC_SYMBOL,
        "bridge_variants": sorted(BRIDGED_STABLE_VARIANTS),
        "polygon_token_list": POLYGON_TOKEN_LIST_DISCOVERY_STATS,
        "subgraph_pool_intel": SUBGRAPH_POOL_INTEL_STATS,
        "dynamic_pool_registry": DYNAMIC_POOL_REGISTRY_STATS,
        "curve_pool_registry": CURVE_POOL_REGISTRY_STATS,
        "apprentice_metadata_promotions": apprentice_promotions,
    }
    if live_candidates:
        suffix = "" if promoted == live_candidates else f" ({live_candidates} live found)"
        print(f"🔎 Factory discovery promoted {promoted} live pool(s){suffix}.")
    if POLYGON_TOKEN_LIST_DISCOVERY_STATS.get("runtime_added"):
        print(
            "   🧬 Polygon token-list discovery staged "
            f"{POLYGON_TOKEN_LIST_DISCOVERY_STATS['runtime_added']} candidate token(s) "
            f"against bases {','.join(POLYGON_TOKEN_LIST_BASES)}."
        )
    if DYNAMIC_POOL_REGISTRY_STATS.get("promoted"):
        print(
            "   🗂️  Dynamic pool registry staged "
            f"{DYNAMIC_POOL_REGISTRY_STATS['promoted']} metadata pool(s) "
            "for live RPC verification."
        )
    if CURVE_POOL_REGISTRY_STATS.get("promoted"):
        print(
            "   🌀 Curve official registry staged "
            f"{CURVE_POOL_REGISTRY_STATS['promoted']} pool(s) "
            f"across {CURVE_POOL_REGISTRY_STATS.get('by_family', {})}."
        )
    if SUBGRAPH_POOL_INTEL_STATS.get("promoted"):
        print(f"   🛰️  Subgraph pool intel promoted {SUBGRAPH_POOL_INTEL_STATS['promoted']} RPC-verified hint(s).")
    return registry


def hydrate_one_shot_pool_metadata(registry: dict) -> None:
    """Cache tick spacing and Balancer pool IDs into pool metadata before state load."""
    if not RPC_LIVE or w3 is None:
        return
    tick_targets = [
        (pool_id, meta)
        for pool_id, meta in registry.items()
        if meta.get("protocol") in {"UniswapV3", "QuickSwapV3", "Algebra"}
        and meta.get("address")
    ]
    tick_ok = 0
    if tick_targets:
        calls = []
        contracts = []
        for _, meta in tick_targets:
            abi = _ABI_ALGEBRA_POOL if meta.get("protocol") in {"QuickSwapV3", "Algebra"} else _ABI_V3_POOL
            contract = w3.eth.contract(address=Web3.to_checksum_address(meta["address"]), abi=abi)
            contracts.append(contract)
            calls.append((meta["address"], True, _encode_fn(contract, "tickSpacing")))
        try:
            results = multicall3_aggregate(calls)
            for (_, meta), result in zip(tick_targets, results):
                if not result[0] or not result[1]:
                    continue
                tick_spacing = w3.codec.decode(["int24"], result[1])[0]
                if tick_spacing and tick_spacing > 0:
                    meta.setdefault("_meta", {})["tick_spacing"] = int(tick_spacing)
                    tick_ok += 1
        except Exception:
            for _, meta in tick_targets:
                try:
                    abi = _ABI_ALGEBRA_POOL if meta.get("protocol") in {"QuickSwapV3", "Algebra"} else _ABI_V3_POOL
                    contract = w3.eth.contract(address=Web3.to_checksum_address(meta["address"]), abi=abi)
                    tick_spacing = contract.functions.tickSpacing().call()
                    if tick_spacing and tick_spacing > 0:
                        meta.setdefault("_meta", {})["tick_spacing"] = int(tick_spacing)
                        tick_ok += 1
                except Exception:
                    continue
        print(f"   🧭 tickSpacing cached: {tick_ok}/{len(tick_targets)}")

    balancer_targets = [
        (pool_id, meta)
        for pool_id, meta in registry.items()
        if meta.get("protocol") == "Balancer" and meta.get("address")
    ]
    bal_ok = 0
    if balancer_targets:
        calls = []
        for _, meta in balancer_targets:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(meta["address"]),
                abi=_ABI_BALANCER_WEIGHTED_POOL,
            )
            calls.append((meta["address"], True, _encode_fn(contract, "getPoolId")))
        try:
            results = multicall3_aggregate(calls)
            for (_, meta), result in zip(balancer_targets, results):
                if not result[0] or not result[1]:
                    continue
                pool_id = "0x" + w3.codec.decode(["bytes32"], result[1])[0].hex()
                if pool_id and int(pool_id, 16) != 0:
                    meta["pool_id"] = pool_id
                    meta.setdefault("_meta", {})["balancer_pool_id"] = pool_id
                    bal_ok += 1
        except Exception:
            for _, meta in balancer_targets:
                try:
                    contract = w3.eth.contract(
                        address=Web3.to_checksum_address(meta["address"]),
                        abi=_ABI_BALANCER_WEIGHTED_POOL,
                    )
                    pool_id = "0x" + contract.functions.getPoolId().call().hex()
                    if pool_id and int(pool_id, 16) != 0:
                        meta["pool_id"] = pool_id
                        meta.setdefault("_meta", {})["balancer_pool_id"] = pool_id
                        bal_ok += 1
                except Exception:
                    continue
        print(f"   🧩 Balancer poolIds cached: {bal_ok}/{len(balancer_targets)}")


# ── Live State Loader ─────────────────────────────────────────────────────────

def _indexed_pool_state(pool_id: str, pool_meta: dict, liquidity_key: str) -> Optional[dict]:
    if not ENABLE_INDEXER_STATE_READS:
        return None
    try:
        from .indexer_state import get_indexed_pool_state

        state = get_indexed_pool_state(pool_meta.get("address", ""), current_block=BLOCK)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None

    proto = state.get("protocol")
    if proto not in {"UniswapV2", "UniswapV3", "QuickSwapV3", "Algebra", "Curve", "Balancer"}:
        return None
    tokens = state.get("tokens")
    if not isinstance(tokens, list) or len(tokens) < 2:
        return None

    if "reserves" in state:
        try:
            state["reserves"] = [Decimal(str(value)) for value in state["reserves"]]
        except Exception:
            return None
    for numeric_key in ("sqrtPriceX96", "liquidity", "fee", "fee_bps", "A", "decimal_adjustment"):
        if numeric_key in state and state[numeric_key] is not None:
            try:
                state[numeric_key] = Decimal(str(state[numeric_key]))
            except Exception:
                return None
    state.setdefault("address", pool_meta.get("address"))
    state.setdefault("pool_id", pool_id)
    state.setdefault("registry_id", pool_id)
    state.setdefault("liquidity_key", liquidity_key)
    state.setdefault("route_class", "NATIVE_POOL_ROUTE")
    meta = dict(pool_meta.get("_meta", {}))
    meta.update(state.get("_meta", {}))
    state["_meta"] = meta
    return state


def load_live_pool_state(pool_id: str, pool_meta: dict) -> Optional[dict]:
    """
    Fetches live state for a single pool via eth_call.

    Returns a pool-state dict compatible with DeFiEngineMath, or None on failure.
    """
    if not RPC_LIVE or w3 is None:
        return None

    addr  = pool_meta["address"]
    proto = pool_meta["protocol"]
    liquidity_key = canonical_liquidity_key(pool_id, pool_meta)
    indexed_state = _indexed_pool_state(pool_id, pool_meta, liquidity_key)
    if indexed_state:
        return indexed_state

    try:
        if proto == "UniswapV2":
            c        = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_ABI_V2_PAIR)
            token0_addr = ""
            token1_addr = ""
            try:
                results = multicall3_aggregate([
                    (addr, False, _encode_fn(c, "token0")),
                    (addr, False, _encode_fn(c, "token1")),
                    (addr, False, _encode_fn(c, "getReserves")),
                ])
                token0_addr = w3.codec.decode(["address"], results[0][1])[0].lower()
                token1_addr = w3.codec.decode(["address"], results[1][1])[0].lower()
                r0, r1, _ = w3.codec.decode(["uint112", "uint112", "uint32"], results[2][1])
                toks = [
                    ADDRESS_TO_SYMBOL.get(token0_addr, pool_meta["token0"]),
                    ADDRESS_TO_SYMBOL.get(token1_addr, pool_meta["token1"]),
                ]
            except Exception:
                toks, addrs = _resolve_pair_token_details(c, pool_meta)
                if len(addrs) == 2:
                    token0_addr, token1_addr = addrs
                r0, r1, _ = c.functions.getReserves().call()
            token_addrs = [token0_addr, token1_addr] if token0_addr and token1_addr else []
            onchain_decimals = _fetch_erc20_decimals(token_addrs)
            v2_audit = _audit_v2_pair_canonical(
                pool_id=pool_id,
                pool_meta=pool_meta,
                toks=toks,
                token_addrs=token_addrs,
                onchain_decimals=onchain_decimals,
                reserves_raw=[r0, r1],
            )
            registered_toks = [pool_meta.get("token0"), pool_meta.get("token1")]
            usdc_variant = (
                "bridged_usdc"
                if BRIDGED_USDC_SYMBOL in toks
                else "native_usdc" if NATIVE_USDC_SYMBOL in toks else ""
            )
            meta = dict(pool_meta.get("_meta", {}))
            meta.update({
                "registered_tokens": registered_toks,
                "onchain_tokens": toks,
                "onchain_addresses": v2_audit.get("onchain_addresses", []),
                "onchain_decimals": onchain_decimals,
                "composition_mismatch": sorted(registered_toks) != sorted(toks),
                "usdc_variant": usdc_variant,
                "v2_anchor_policy": f"prefer_{BRIDGED_USDC_SYMBOL}",
                V2_AUDIT_KEY: v2_audit,
            })
            return {
                "protocol": "UniswapV2",
                "tokens":   toks,
                "reserves": [
                    _normalize_units(r0, toks[0]),
                    _normalize_units(r1, toks[1]),
                ],
                "fee":      Decimal(pool_meta["fee_bps"]) / Decimal("10000"),
                "address":  addr,
                "pool_id": pool_id,
                "registry_id": pool_id,
                "liquidity_key": liquidity_key,
                "route_class": "NATIVE_POOL_ROUTE",
                "_meta": meta,
            }

        elif proto in {"UniswapV3", "QuickSwapV3", "Algebra"}:
            is_algebra = proto in {"QuickSwapV3", "Algebra"}
            c = w3.eth.contract(
                address=Web3.to_checksum_address(addr),
                abi=_ABI_ALGEBRA_POOL if is_algebra else _ABI_V3_POOL,
            )
            token0_addr = ""
            token1_addr = ""
            try:
                results = multicall3_aggregate([
                    (addr, False, _encode_fn(c, "token0")),
                    (addr, False, _encode_fn(c, "token1")),
                    (addr, False, _encode_fn(c, "globalState" if is_algebra else "slot0")),
                    (addr, False, _encode_fn(c, "liquidity")),
                ])
                token0_addr = w3.codec.decode(["address"], results[0][1])[0].lower()
                token1_addr = w3.codec.decode(["address"], results[1][1])[0].lower()
                if is_algebra:
                    slot0 = w3.codec.decode(
                        ["uint160", "int24", "uint16", "uint16", "uint8", "uint8", "bool"],
                        results[2][1],
                    )
                else:
                    slot0 = w3.codec.decode(
                        ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
                        results[2][1],
                    )
                liq = w3.codec.decode(["uint128"], results[3][1])[0]
                toks = [
                    ADDRESS_TO_SYMBOL.get(token0_addr, pool_meta["token0"]),
                    ADDRESS_TO_SYMBOL.get(token1_addr, pool_meta["token1"]),
                ]
            except Exception:
                toks, addrs = _resolve_pair_token_details(c, pool_meta)
                if len(addrs) == 2:
                    token0_addr, token1_addr = addrs
                slot0 = c.functions.globalState().call() if is_algebra else c.functions.slot0().call()
                liq   = c.functions.liquidity().call()
            if is_algebra and len(slot0) > 2 and Decimal(str(slot0[2])) > 0:
                fee_tier = None
                fee_bps = Decimal(str(slot0[2])) / Decimal("100")
            else:
                # Uniswap V3 factory fees are fee tiers in hundredths of a bip:
                # 100=1 bps, 500=5 bps, 3000=30 bps, 10000=100 bps.
                # Keep fee_tier for quoter/factory semantics and expose
                # normalized fee_bps for invariant math.
                fee_tier = int(Decimal(str(pool_meta["fee_bps"])))
                fee_bps = Decimal(fee_tier) / Decimal("100")
            sqrt_price_x96 = Decimal(slot0[0])
            liquidity = Decimal(liq)
            token_addrs = [token0_addr, token1_addr] if token0_addr and token1_addr else []
            onchain_decimals = _fetch_erc20_decimals(token_addrs)
            decimal_adjustment = _v3_decimal_adjustment(toks[0], toks[1])
            audit = _audit_clmm_orientation_decimals(
                pool_id=pool_id,
                pool_meta=pool_meta,
                proto="QuickSwapV3" if is_algebra else "UniswapV3",
                toks=toks,
                token_addrs=token_addrs,
                onchain_decimals=onchain_decimals,
                sqrt_price_x96=sqrt_price_x96,
                liquidity=liquidity,
                decimal_adjustment=decimal_adjustment,
            )
            meta = dict(pool_meta.get("_meta", {}))
            meta.update({
                "registered_tokens": [pool_meta.get("token0"), pool_meta.get("token1")],
                "onchain_tokens": toks,
                "onchain_addresses": audit.get("onchain_addresses", []),
                "onchain_decimals": onchain_decimals,
                "composition_mismatch": sorted([pool_meta.get("token0"), pool_meta.get("token1")]) != sorted(toks),
                "orientation_remapped_to_onchain_order": [pool_meta.get("token0"), pool_meta.get("token1")] != toks,
                CLMM_AUDIT_KEY: audit,
            })
            return {
                "protocol":     "QuickSwapV3" if is_algebra else "UniswapV3",
                "tokens":       toks,
                "sqrtPriceX96": sqrt_price_x96,
                "liquidity":    liquidity,
                "fee_bps":      fee_bps,
                "fee_tier":     fee_tier,
                "tick_spacing": pool_meta.get("_meta", {}).get("tick_spacing"),
                "decimal_adjustment": decimal_adjustment,
                "address":  addr,
                "pool_id": pool_id,
                "registry_id": pool_id,
                "liquidity_key": liquidity_key,
                "route_class": "NATIVE_POOL_ROUTE",
                "_meta": meta,
            }

        elif proto == "Curve":
            curve = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_ABI_CURVE_POOL)
            configured_toks = pool_meta.get("tokens", [pool_meta["token0"], pool_meta["token1"]])
            toks: list[str] = []
            reserves = []
            token_addresses: list[str] = []
            for idx, configured_tok in enumerate(configured_toks):
                tok = configured_tok
                tok_addr = TOKEN_ADDRESSES.get(configured_tok)
                try:
                    onchain_addr = curve.functions.coins(idx).call().lower()
                    tok = ADDRESS_TO_SYMBOL.get(onchain_addr, configured_tok)
                    tok_addr = onchain_addr
                except Exception:
                    pass
                try:
                    raw_balance = curve.functions.balances(idx).call()
                except Exception:
                    if tok_addr:
                        erc = w3.eth.contract(address=Web3.to_checksum_address(tok_addr), abi=_ABI_ERC20)
                        raw_balance = erc.functions.balanceOf(Web3.to_checksum_address(addr)).call()
                    else:
                        return None
                toks.append(tok)
                token_addresses.append(Web3.to_checksum_address(tok_addr) if tok_addr else "")
                reserves.append(_normalize_units(raw_balance, tok))
            meta = dict(pool_meta.get("_meta", {}))
            if pool_meta.get("tvl_usd") is not None:
                meta.setdefault("tvl_source", "curve_official_api")
                meta.setdefault("tvl_state", "api_seeded_live_balances_loaded")
            return {
                "protocol": "Curve",
                "tokens":   toks,
                "token_addresses": token_addresses,
                "reserves": reserves,
                "A":        Decimal(str(pool_meta.get("A", 100))),
                "fee_bps":  pool_meta.get("fee_bps", 4),
                "tvl_usd":  Decimal(str(pool_meta.get("tvl_usd", 0) or 0)),
                "address":  addr,
                "pool_id": pool_id,
                "registry_id": pool_id,
                "liquidity_key": liquidity_key,
                "route_class": "NATIVE_POOL_ROUTE",
                "_meta": meta,
            }

        elif proto == "Balancer":
            pool_id_hex = pool_meta.get("pool_id")
            if not pool_id_hex:
                return None
            vault = w3.eth.contract(
                address=Web3.to_checksum_address(BALANCER_VAULT_POLYGON),
                abi=_ABI_BALANCER_VAULT,
            )
            bal_pool = w3.eth.contract(
                address=Web3.to_checksum_address(addr),
                abi=_ABI_BALANCER_WEIGHTED_POOL,
            )
            swap_fee_source = "metadata"
            weights_source = "metadata"
            try:
                results = multicall3_aggregate([
                    (BALANCER_VAULT_POLYGON, False, _encode_fn(vault, "getPoolTokens", [bytes.fromhex(pool_id_hex[2:])])),
                    (addr, True, _encode_fn(bal_pool, "getNormalizedWeights")),
                    (addr, True, _encode_fn(bal_pool, "getSwapFeePercentage")),
                ])
                token_addrs, balances, _ = w3.codec.decode(["address[]", "uint256[]", "uint256"], results[0][1])
                if results[1][0]:
                    weights = [
                        Decimal(raw_weight) / Decimal("1e18")
                        for raw_weight in w3.codec.decode(["uint256[]"], results[1][1])[0]
                    ]
                    weights_source = "onchain_getNormalizedWeights"
                else:
                    weights = []
                if results[2][0]:
                    swap_fee = Decimal(w3.codec.decode(["uint256"], results[2][1])[0]) / Decimal("1e18")
                    swap_fee_source = "onchain_getSwapFeePercentage"
                else:
                    swap_fee = Decimal(pool_meta["fee_bps"]) / Decimal("10000")
            except Exception:
                token_addrs, balances, _ = vault.functions.getPoolTokens(bytes.fromhex(pool_id_hex[2:])).call()
                try:
                    weights = [
                        Decimal(raw_weight) / Decimal("1e18")
                        for raw_weight in bal_pool.functions.getNormalizedWeights().call()
                    ]
                    weights_source = "onchain_getNormalizedWeights"
                except Exception:
                    weights = []
                try:
                    swap_fee = Decimal(bal_pool.functions.getSwapFeePercentage().call()) / Decimal("1e18")
                    swap_fee_source = "onchain_getSwapFeePercentage"
                except Exception:
                    swap_fee = Decimal(pool_meta["fee_bps"]) / Decimal("10000")
            toks = []
            reserves = []
            for token_addr, balance in zip(token_addrs, balances):
                tok = ADDRESS_TO_SYMBOL.get(token_addr.lower())
                if not tok:
                    continue
                toks.append(tok)
                reserves.append(_normalize_units(balance, tok))
            if not toks or len(toks) != len(reserves):
                return None
            remap = _audit_balancer_remap(pool_id, pool_meta, token_addrs, toks)
            if not weights:
                w_raw = pool_meta.get("weights", [1.0 / len(toks)] * len(toks))
                weights = [Decimal(str(wt)) for wt in w_raw]
                weights_source = "metadata_fallback"
            if len(weights) != len(toks):
                return None
            meta = dict(pool_meta.get("_meta", {}))
            meta.update({
                "balancer_pool_id": pool_meta.get("pool_id"),
                "weights_source": weights_source,
                "swap_fee_source": swap_fee_source,
            })
            if remap:
                meta["balancer_remap"] = remap
            return {
                "protocol": "Balancer",
                "tokens":   toks,
                "reserves": reserves,
                "weights":  weights,
                "swap_fee": swap_fee,
                "address":  addr,
                "pool_id": pool_id,
                "registry_id": pool_id,
                "balancer_pool_id": pool_meta.get("pool_id"),
                "liquidity_key": liquidity_key,
                "route_class": "NATIVE_POOL_ROUTE",
                "_meta": meta,
            }

    except Exception as exc:
        print(f"    ⚠️  [{pool_id}] RPC call failed: {exc}")

    return None


def load_all_live_pools(registry: dict = None) -> dict:
    """
    Iterates the full registry, loads live states, and returns the combined
    pool dict. Refuses to synthesize pool state when RPC is unavailable.
    """
    if registry is None:
        registry = DEEP_POOL_REGISTRY
    global LAST_POOL_QUALITY_STATS
    LAST_POOL_QUALITY_STATS = {}
    if RPC_LIVE:
        registry = discover_factory_pool_registry(registry)
        hydrate_one_shot_pool_metadata(registry)

    live_pools: dict = {}
    failed           = 0
    balancer_remaps  = 0

    if RPC_LIVE:
        print(f"🌐 Loading live state for {len(registry)} registered pools...")
        for pool_id, meta in registry.items():
            state = load_live_pool_state(pool_id, meta)
            if state:
                live_pools[pool_id] = state
                if state.get("_meta", {}).get("balancer_remap"):
                    balancer_remaps += 1
            else:
                failed += 1
            if POOL_LOAD_SLEEP_SECONDS > 0:
                time.sleep(float(POOL_LOAD_SLEEP_SECONDS))
        print(f"   ✅ {len(live_pools)} pools loaded live  |  ⚠️  {failed} failed")
        if balancer_remaps:
            print(f"   🔁 Balancer metadata remaps applied: {balancer_remaps}")
        live_pools, quality_summary = filter_rankable_pools(live_pools)
        LAST_POOL_QUALITY_STATS = quality_summary
        clmm_summary = quality_summary.get("v3_algebra_orientation_decimals", {})
        v2_summary = quality_summary.get("v2_pair_canonical", {})
        print(
            "   🧭 V3/Algebra orientation+decimals audit: "
            f"passed={clmm_summary.get('clmm_passed', 0)}/{clmm_summary.get('clmm_total', 0)} "
            f"failed={clmm_summary.get('clmm_failed', 0)}"
        )
        if clmm_summary.get("reject_reasons"):
            print(f"      reject_reasons={clmm_summary['reject_reasons']}")
        print(
            "   🧭 V2 pair canonical audit: "
            f"passed={v2_summary.get('v2_passed', 0)}/{v2_summary.get('v2_total', 0)} "
            f"failed={v2_summary.get('v2_failed', 0)} "
            f"filtered_out={quality_summary.get('filtered_out', 0)}"
        )
        if v2_summary.get("reject_reasons"):
            print(f"      reject_reasons={v2_summary['reject_reasons']}")
        _hydrate_v3_tvl_state(live_pools)
        _apply_executable_liquidity_schema(live_pools)
    else:
        raise RuntimeError("RPC offline; live production mode refuses synthetic pool state")

    return live_pools


def _hydrate_v3_tvl_state(live_pools: dict) -> None:
    v3_pool_items = [
        (pool_id, pool)
        for pool_id, pool in live_pools.items()
        if pool.get("protocol") in {"UniswapV3", "QuickSwapV3", "Algebra"}
        and pool.get("address")
    ]
    if not v3_pool_items:
        return
    try:
        from .oracle_layer import dexscreener_pool_tvls
        tvl_rows = dexscreener_pool_tvls([pool["address"] for _, pool in v3_pool_items])
    except Exception:
        tvl_rows = {}

    hydrated = 0
    for pool_id, pool in v3_pool_items:
        row = tvl_rows.get(str(pool["address"]).lower())
        meta = dict(pool.get("_meta", {}))
        if row and row.get("tvl_usd", Decimal("0")) > 0:
            pool["tvl_usd"] = row["tvl_usd"]
            pool["volume_24h_usd"] = row.get("volume_24h_usd", Decimal("0"))
            meta["tvl_source"] = "dexscreener_pairs"
            meta["tvl_state"] = "hydrated"
            hydrated += 1
        else:
            pool.setdefault("tvl_usd", Decimal("0"))
            pool.setdefault("volume_24h_usd", Decimal("0"))
            meta["tvl_source"] = "dexscreener_pairs"
            meta["tvl_state"] = "unavailable"
        pool["_meta"] = meta
    print(f"   📊 V3 TVL state hydrated: {hydrated}/{len(v3_pool_items)}")


def _decimal_or_zero(value) -> Decimal:
    try:
        dec = Decimal(str(value))
        return dec if dec > 0 else Decimal("0")
    except Exception:
        return Decimal("0")


def _reserve_depths_usd(pool: dict) -> dict[str, Decimal]:
    from .oracle_layer import PriceUnavailable, token_price_usd

    tokens = pool.get("tokens", [])
    reserves = pool.get("reserves", [])
    if not tokens or not reserves or len(tokens) != len(reserves):
        return {}

    depths: dict[str, Decimal] = {}
    for token, reserve in zip(tokens, reserves):
        try:
            value = Decimal(str(reserve)) * token_price_usd(str(token))
            if value > 0:
                depths[str(token)] = value
        except (PriceUnavailable, ArithmeticError):
            continue
    return depths


def _clmm_active_virtual_depths_usd(pool: dict) -> dict[str, Decimal]:
    from .oracle_layer import PriceUnavailable, token_price_usd

    tokens = [str(token) for token in pool.get("tokens", [])]
    if len(tokens) != 2:
        return {}
    liquidity = _decimal_or_zero(pool.get("liquidity"))
    sqrt_price_x96 = _decimal_or_zero(pool.get("sqrtPriceX96"))
    if liquidity <= 0 or sqrt_price_x96 <= 0:
        return {}

    q96 = Decimal(2) ** Decimal(96)
    sqrt_price = sqrt_price_x96 / q96
    if sqrt_price <= 0:
        return {}

    raw0 = liquidity / sqrt_price
    raw1 = liquidity * sqrt_price
    amount0 = raw0 / (Decimal(10) ** TOKEN_DECIMALS.get(tokens[0], 18))
    amount1 = raw1 / (Decimal(10) ** TOKEN_DECIMALS.get(tokens[1], 18))

    depths: dict[str, Decimal] = {}
    for token, amount in ((tokens[0], amount0), (tokens[1], amount1)):
        try:
            value = amount * token_price_usd(token)
            if value > 0:
                depths[token] = value
        except (PriceUnavailable, ArithmeticError):
            continue
    return depths


def _apply_executable_liquidity_schema(live_pools: dict) -> None:
    """Hydrate the executable liquidity schema for every loaded pool."""
    try:
        from .oracle_layer import refresh_token_prices
        refresh_token_prices(force=False)
        from .liquidity_registry import _local_tvl_usd, _token_side_depth
    except Exception:
        pass

    hydrated = 0
    unavailable = 0
    for pool in live_pools.values():
        meta = dict(pool.get("_meta", {}))
        total = _local_tvl_usd(pool)
        pool["total_executable_liquidity_usd"] = total
        pool["executable_token_depth_usd"] = {
            k: _decimal_or_zero(v) for k, v in _token_side_depth(pool).items()
        }
        meta["base_pool_registry_schema"] = "omega_v5.base_pool_registry.v1"
        meta["total_executable_liquidity_source"] = meta.get("tvl_source", "reserve_x_oracle")
        pool["_meta"] = meta

        if total > 0:
            hydrated += 1
        else:
            unavailable += 1

    print(
        "   🧮 Total executable liquidity hydrated: "
        f"{hydrated}/{len(live_pools)} pools  |  unavailable={unavailable}"
    )
