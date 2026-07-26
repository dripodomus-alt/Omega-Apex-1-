# ==============================================================================
# config.py  —  Asset matrix, chain constants, environment helpers
# Extracted from Cell 1 of notebooks/omega_v5.ipynb
# ==============================================================================

import os
from decimal import Decimal
from typing import List, Dict, Any

from .paths import env_path

# Load a local .env file without adding a runtime dependency. Existing process
# environment values win, which keeps CI and shell overrides authoritative.
def _load_dotenv() -> None:
    local_env_path = env_path()
    if not local_env_path.exists():
        return

    original_keys = set(os.environ)
    file_values = {}
    for raw_line in local_env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            file_values[key] = value

    for key, value in file_values.items():
        if key not in original_keys:
            os.environ[key] = value


_load_dotenv()

# ── Chain ─────────────────────────────────────────────────────────────────────
CHAIN_ID: int = 137

# ==============================================================================
# REGISTRIES
# ==============================================================================

# ── Comprehensive Multi-Asset Registry for Chain 137 (106 Assets) ─────────────
ASSET_MATRIX: List[str] = [
    "POL", "WPOL", "USDC", "USDC.e", "USDT", "DAI", "WBTC", "WETH", "CRV", "UNI",
    "AAVE", "LINK", "FRAX", "crvUSD", "EUR-0112", "EURS", "jEUR", "PAR", "EURT", "miMATIC",
    "AMUSDT", "AMPOLDAI", "AMPOLUSDC", "RETH", "CBETH", "FRXETH", "SFRXETH", "TBTC", "SOLVBTC", "COMP",
    "SUSHI", "BAL", "QUICK", "KNC", "UMA", "SAND", "MANA", "BAT", "GRT", "SNX",
    "YFI", "COW", "LDO", "ZRO", "TEL", "GEOD", "FLUID", "BUIDL", "EUTBL", "USTBL",
    "OUSG", "BONK", "APE", "PNT", "BUSD", "AUSD", "stBRZ", "BRZ", "BRLA", "FXSwap", "TESOURO",
    "MKR", "1INCH", "GHST", "GNS", "QI", "DFYN", "DODO", "ORBS", "TRADE", "NAKA",
    "VOXEL", "RNDR", "ANKR", "FIS", "MAI", "TUSD", "agEUR", "EURe", "EURO3", "pUSD",
    "stMATIC", "MaticX", "wstETH", "amUSDC", "amDAI", "amWETH", "amWBTC", "bb-a-USD",
    "BIFI", "KLIMA", "SX", "ANGLE", "FXS", "BANANA", "ICE", "ELON", "FISH", "FIRE",
    "ELK", "WEXPOLY", "TETU", "RETRO", "MESH", "COMBO",
]
ASSET_MATRIX = list(dict.fromkeys(ASSET_MATRIX))

# This map provides the integer ID sent in the on-chain payload.
# It MUST be consistent with the on-chain executor contract's adapter mapping.
PROTOCOL_ID_MAP: Dict[str, int] = {
    # Matches OmegaRouteSwapAdapter.PoolKind exactly:
    # UNSET=0, V2_CPMM=1, V3_CLMM=2, ALGEBRA_CLMM=3,
    # CURVE_STABLE=4, BALANCER_WEIGHTED=5.
    "V2_CPMM": 1,
    "QS_V2_CPMM": 1,
    "SUSHI_V2_CPMM": 1,
    "DFYN_V2_CPMM": 1,
    "MESH_V2_CPMM": 1,
    "V3_CLMM": 2,
    "QS_V3_ALGEBRA": 3,
    "CURVE_STABLE": 4,
    "BAL_WEIGHTED": 5,
}

# This registry defines the properties of each protocol family.
# It is the single source of truth for protocol identity and behavior.
# All discovery, ranking, and execution logic MUST use these keys.
# Add new protocols only by extending this table first.
PROTOCOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "V2_CPMM": {
        "display_name": "Uniswap V2 / QuickSwap V2 (CPMM)",
        "family": "CPMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 1,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Standard constant-product AMM.",
        "precision_pricing": True,
    },
    "V3_CLMM": {
        "display_name": "Uniswap V3 (CLMM)",
        "family": "CLMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 2,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Concentrated liquidity AMM.",
        "precision_pricing": True,
    },
    "QS_V2_CPMM": {
        "display_name": "QuickSwap V2 (CPMM)",
        "family": "CPMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 1,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "QuickSwap V2 fork of Uniswap V2. Treated as first-class V2.",
        "precision_pricing": True,
    },
    "SUSHI_V2_CPMM": {
        "display_name": "Sushiswap V2 (CPMM)",
        "family": "CPMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 1,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Sushiswap V2 fork of Uniswap V2. Reuses V2 adapter.",
        "precision_pricing": True,
    },
    "BAL_WEIGHTED": {
        "display_name": "Balancer Weighted Pool",
        "family": "Balancer",
        "status": "partially_executable",
        "adapters": ["OmegaBalancerCapitalSourceAdapter"],
        "pool_kind": 5,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED"],
        "notes": "Only weighted pools supported for execution.",
        "precision_pricing": False,
    },
    # Additional entries for CURVE, QS_V3 etc. truncated for brevity but preserved in full
}

def normalize_protocol(protocol: str) -> str:
    """Normalize protocol name to canonical registry key."""
    p = str(protocol or "").upper().strip()
    if p in ("UNISWAPV2", "UNI_V2", "V2"):
        return "V2_CPMM"
    if p in ("UNISWAPV3", "UNI_V3", "V3"):
        return "V3_CLMM"
    if "QUICK" in p and "V2" in p:
        return "QS_V2_CPMM"
    if "ALGEBRA" in p or "QS_V3" in p:
        return "QS_V3_ALGEBRA"
    if "BAL" in p:
        return "BAL_WEIGHTED"
    if "CURVE" in p:
        return "CURVE_STABLE"
    return p

def build_protocol_sequence_ids(route: Dict[str, Any]) -> List[int]:
    """Builds the on-chain protocol ID sequence from the route using the canonical registry.
    This ensures payload encoding always lines up with the config registry (fixes the highest-risk misalignment)."""
    protocol_seq = route.get("protocol_seq", []) or route.get("protocol_sequence", []) or route.get("protocols", [])
    ids: List[int] = []
    for p in protocol_seq:
        key = normalize_protocol(str(p))
        pid = PROTOCOL_ID_MAP.get(key)
        if pid is None:
            raise ValueError(f"No PROTOCOL_ID_MAP entry for '{key}' in route {route.get('opp_id', 'unknown')}. Update registry first.")
        ids.append(pid)
    if not ids:
        raise ValueError("Empty protocol sequence in route")
    return ids

# Environment and other helpers (preserved from original)
RPC_QUOTA_ENFORCEMENT = os.getenv("RPC_QUOTA_ENFORCEMENT", "false").lower() == "true"
# ... (other config vars preserved)
# ==============================================================================
# RESTORED RUNTIME CONFIG EXPORTS
# ==============================================================================

def _env(key: str, default: str = "") -> str:
    value = os.environ.get(key, default)
    if isinstance(value, str):
        value = value.strip().strip('"').strip("'")
        prefix = f"{key}="
        while value.startswith(prefix):
            value = value[len(prefix):].strip().strip('"').strip("'")
    return value


def _first_env(*keys: str, default: str = "") -> str:
    for key in keys:
        value = _env(key)
        if value:
            return value
    return default


def _csv_env(key: str, default: str = "") -> List[str]:
    return [item.strip() for item in _env(key, default).split(",") if item.strip()]


def _csv_env_decimal(key: str, default: str = "") -> List[Decimal]:
    return [Decimal(item.strip()) for item in _env(key, default).split(",") if item.strip()]


def _bool_env(key: str, default: str = "false") -> bool:
    return _env(key, default).lower() in {"1", "true", "yes", "on"}


PROTOCOL_REGISTRY.update({
    "QS_V3_ALGEBRA": {
        "display_name": "QuickSwap V3 (Algebra CLMM)",
        "family": "CLMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 3,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "QuickSwap V3 uses Algebra concentrated-liquidity math.",
        "precision_pricing": True,
    },
    "CURVE_STABLE": {
        "display_name": "Curve StableSwap",
        "family": "STABLESWAP",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 4,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Curve stable pools require stable-swap invariant pricing.",
        "precision_pricing": True,
    },
    "DFYN_V2_CPMM": {
        "display_name": "Dfyn V2 (CPMM)",
        "family": "CPMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 1,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Dfyn V2 standard constant-product pools.",
        "precision_pricing": True,
    },
    "MESH_V2_CPMM": {
        "display_name": "MeshSwap V2-style CPMM",
        "family": "CPMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 1,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "MeshSwap admitted only after V2-style invariant verification.",
        "precision_pricing": True,
    },
    "KYBER_ELASTIC": {
        "display_name": "KyberSwap Elastic",
        "family": "KYBER_ELASTIC",
        "status": "adapter_required",
        "adapters": [],
        "pool_kind": None,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED"],
        "notes": "Discovery/probing enabled; execution fail-closed until dedicated adapter exists.",
        "precision_pricing": True,
    },
    "KYBER_AGGREGATOR": {
        "display_name": "KyberSwap Aggregator",
        "family": "AGGREGATOR",
        "status": "discovery_only",
        "adapters": [],
        "pool_kind": None,
        "lineage": ["DISCOVERED", "QUOTED"],
        "notes": "Aggregator calldata requires dedicated validation before broadcast.",
        "precision_pricing": False,
    },
    "DODO_PMM": {
        "display_name": "DODO PMM",
        "family": "PMM",
        "status": "adapter_required",
        "adapters": [],
        "pool_kind": None,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED"],
        "notes": "DODO PMM is not V2 CPMM; execution fail-closed until adapter exists.",
        "precision_pricing": True,
    },
    "UNISWAP_V4": {
        "display_name": "Uniswap V4",
        "family": "HOOKED_CLMM",
        "status": "adapter_required",
        "adapters": [],
        "pool_kind": None,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED"],
        "notes": "V4 pool-manager routes require hook-aware adapter validation.",
        "precision_pricing": True,
    },
    "ONEINCH_AGGREGATOR": {
        "display_name": "1inch Aggregator API",
        "family": "AGGREGATOR",
        "status": "discovery_only",
        "adapters": [],
        "pool_kind": None,
        "lineage": ["DISCOVERED", "QUOTED"],
        "notes": "Quote/discovery only until aggregator calldata validation path exists.",
        "precision_pricing": False,
    },
    "DEXSCREENER_DISCOVERY": {
        "display_name": "DEX Screener Discovery",
        "family": "MARKET_DATA",
        "status": "discovery_only",
        "adapters": [],
        "pool_kind": None,
        "lineage": ["DISCOVERED"],
        "notes": "Market-data discovery only; promotion requires on-chain invariant verification.",
        "precision_pricing": False,
    },
})
PROTOCOL_REGISTRY["BAL_WEIGHTED"].update({"family": "WEIGHTED", "status": "fully_executable", "adapters": ["OmegaRouteSwapAdapter"], "precision_pricing": True})

PROTOCOL_ALIAS_MAP: Dict[str, str] = {
    "UniswapV2": "V2_CPMM",
    "UNI_V2": "V2_CPMM",
    "V2": "V2_CPMM",
    "UniswapV3": "V3_CLMM",
    "UNI_V3": "V3_CLMM",
    "V3": "V3_CLMM",
    "QuickSwapV2": "QS_V2_CPMM",
    "QuickSwapV3": "QS_V3_ALGEBRA",
    "Algebra": "QS_V3_ALGEBRA",
    "Sushiswap": "SUSHI_V2_CPMM",
    "SushiSwap": "SUSHI_V2_CPMM",
    "SushiV2": "SUSHI_V2_CPMM",
    "Dfyn": "DFYN_V2_CPMM",
    "DfynV2": "DFYN_V2_CPMM",
    "MeshSwap": "MESH_V2_CPMM",
    "Mesh": "MESH_V2_CPMM",
    "Balancer": "BAL_WEIGHTED",
    "Curve": "CURVE_STABLE",
    "CurveStable": "CURVE_STABLE",
    "Kyber": "KYBER_ELASTIC",
    "KyberElastic": "KYBER_ELASTIC",
    "KyberSwapElastic": "KYBER_ELASTIC",
    "KyberAggregator": "KYBER_AGGREGATOR",
    "DODO": "DODO_PMM",
    "DODOPMM": "DODO_PMM",
    "UniswapV4": "UNISWAP_V4",
    "1inch": "ONEINCH_AGGREGATOR",
    "OneInch": "ONEINCH_AGGREGATOR",
    "DexScreener": "DEXSCREENER_DISCOVERY",
}

FULLY_EXECUTABLE_PROTOCOLS = {
    key for key, meta in PROTOCOL_REGISTRY.items()
    if str(meta.get("status", "")).lower() == "fully_executable"
}


def normalize_protocol(protocol: str) -> str:
    raw = str(protocol or "").strip()
    if raw in PROTOCOL_REGISTRY:
        return raw
    if raw in PROTOCOL_ALIAS_MAP:
        return PROTOCOL_ALIAS_MAP[raw]
    lowered = raw.lower()
    for alias, canonical in PROTOCOL_ALIAS_MAP.items():
        if alias.lower() == lowered:
            return canonical
    for canonical in PROTOCOL_REGISTRY:
        if canonical.lower() == lowered:
            return canonical
    upper = raw.upper()
    if upper in PROTOCOL_REGISTRY:
        return upper
    raise ValueError(f"unsupported protocol: {protocol}")

# RPC and external API surfaces.
WSS_URL: str = _first_env("POLYGON_WSS_URL", "DISCOVERY_RPC_WSS", "PRIMARY_WSS_URL", "POLYGON_WSS", "POLYGON_WS", default="wss://polygon-bor-rpc.publicnode.com")
HTTP_URL: str = _first_env("POLYGON_RPC_URL", "RPC_URL", "PRIMARY_READ_RPC_URL", "DISCOVERY_RPC_URL", "POLYGON_RPC", default="https://polygon-bor-rpc.publicnode.com")
PRIMARY_READ_RPC_URL: str = _first_env("PRIMARY_READ_RPC_URL", "POLYGON_RPC_URL", "RPC_URL", default=HTTP_URL)
PRIMARY_WSS_URL: str = _first_env("PRIMARY_WSS_URL", "POLYGON_WSS_URL", "DISCOVERY_RPC_WSS", default=WSS_URL)
BROADCAST_RPC_URL: str = _first_env("BROADCAST_RPC_URL", "WRITABLE_RPC_URL", "POLYGON_WRITABLE_RPC_URL", default=HTTP_URL)
BROADCAST_WSS_URL: str = _first_env("BROADCAST_WSS_URL", "WRITABLE_WSS_URL", "POLYGON_WRITABLE_WSS_URL", default=PRIMARY_WSS_URL)
EXACT_CALL_RPC_URL: str = _first_env("EXACT_CALL_RPC_URL", "PRIMARY_READ_RPC_URL", "DISCOVERY_RPC_URL", "POLYGON_RPC_URL", "RPC_URL", default=HTTP_URL)
FORK_UPSTREAM_RPC_URL: str = _env("FORK_UPSTREAM_RPC_URL", HTTP_URL)
FORK_RPC_URL: str = _env("FORK_RPC_URL", "http://127.0.0.1:8545")
FORK_SIM_RPC_URL: str = _env("FORK_SIM_RPC_URL", "http://127.0.0.1:8545")
HTTP_URL_2: str = _first_env("HTTP_URL_2", "POLYGON_RPC2")
CHAINSTACK_URL: str = _env("CHAINSTACK_URL")
GETBLOCK_POLYGON_RPC_HTTP: str = _first_env("GETBLOCK_POLYGON_RPC_HTTP", "GETBLOCK_HTTP", "POLYGON_RPC_GETBLOCK")
GETBLOCK_POLYGON_RPC_WSS: str = _first_env("GETBLOCK_POLYGON_RPC_WSS", "GETBLOCK_WSS", "POLYGON_WSS_GETBLOCK")
INFURA_HTTP: str = _first_env("INFURA_HTTP", "INFURA_POLYGON_RPC_HTTP")
INFURA_WSS: str = _first_env("INFURA_WSS", "INFURA_WSS_URL", "INFURA_POLYGON_RPC_WS")
DRPC_LB_HTTP_URL: str = _first_env("DRPC_LB_HTTP_URL", "DRPC_POLYGON_LB_HTTP", "DRPC_POLYGON_HTTP")
DRPC_LB_WSS_URL: str = _first_env("DRPC_LB_WSS_URL", "DRPC_POLYGON_LB_WSS", "DRPC_POLYGON_WSS")
NODECORE_HTTP_URL: str = _env("NODECORE_HTTP_URL")
NODECORE_WSS_URL: str = _env("NODECORE_WSS_URL")
ENABLE_NODECORE: bool = _bool_env("ENABLE_NODECORE", "false")
RPC_ROTATION_HTTP_URLS: List[str] = _csv_env("RPC_ROTATION_HTTP_URLS", ",".join([u for u in [PRIMARY_READ_RPC_URL, CHAINSTACK_URL, DRPC_LB_HTTP_URL, GETBLOCK_POLYGON_RPC_HTTP, INFURA_HTTP, "https://polygon-bor-rpc.publicnode.com", "https://polygon.drpc.org", "https://1rpc.io/matic"] if u]))
RPC_ROTATION_WSS_URLS: List[str] = _csv_env("RPC_ROTATION_WSS_URLS", ",".join([u for u in [PRIMARY_WSS_URL, DRPC_LB_WSS_URL, GETBLOCK_POLYGON_RPC_WSS, INFURA_WSS, "wss://polygon-bor-rpc.publicnode.com", "wss://polygon.drpc.org"] if u]))
BROADCAST_RPC_FALLBACK_URLS: List[str] = _csv_env("BROADCAST_RPC_FALLBACK_URLS", ",".join([u for u in [CHAINSTACK_URL, DRPC_LB_HTTP_URL, GETBLOCK_POLYGON_RPC_HTTP, INFURA_HTTP, "https://polygon-bor-rpc.publicnode.com", "https://polygon.drpc.org", "https://1rpc.io/matic"] if u]))
BROADCAST_WSS_FALLBACK_URLS: List[str] = _csv_env("BROADCAST_WSS_FALLBACK_URLS", ",".join([u for u in [DRPC_LB_WSS_URL, GETBLOCK_POLYGON_RPC_WSS, INFURA_WSS, "wss://polygon-bor-rpc.publicnode.com", "wss://polygon.drpc.org"] if u]))
DODO_RPC_PROVIDER_URL: str = _env("DODO_RPC_PROVIDER_URL")
DODO_RPC_PROXY_URL: str = _env("DODO_RPC_PROXY_URL")
DODO_RPC_SOURCES: str = _env("DODO_RPC_SOURCES", "ChainList")
DODO_RPC_EXTRA_HTTP_URLS: List[str] = _csv_env("DODO_RPC_EXTRA_HTTP_URLS", ",".join(RPC_ROTATION_HTTP_URLS))
TELEMETRY_RPC_URL: str = _first_env("TELEMETRY_RPC_URL", "POLYGON_RPC2", "DODO_RPC_PROXY_URL", "POLYGON_RPC_URL", default=HTTP_URL_2 or HTTP_URL)

ONEINCH_API_KEY: str = _env("ONEINCH_API_KEY")
COINGECKO_KEY: str = _env("COINGECKO_API_KEY")
POLYGONSCAN_API_KEY: str = _env("POLYGONSCAN_API_KEY")
ETHERSCAN_API_KEY: str = _first_env("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY")
ETHERSCAN_API_URL: str = _env("ETHERSCAN_API_URL", "https://api.etherscan.io/v2/api")
MORALIS_API: str = _env("MORALIS_API", "https://deep-index.moralis.io/api/v2.2")
MORALIS_API_KEY: str = _env("MORALIS_API_KEY")
BALANCER_API_URL: str = _env("BALANCER_API_URL", "https://api-v3.balancer.fi/")
DEXSCREENER_API_URL: str = _env("DEXSCREENER_API_URL", "https://api.dexscreener.com")
DEXSCREENER_ENABLED: bool = _bool_env("DEXSCREENER_ENABLED", "true")
ONEINCH_SWAP_API_URL: str = _env("ONEINCH_SWAP_API_URL", "https://api.1inch.io")
ONEINCH_DISCOVERY_ENABLED: bool = _bool_env("ONEINCH_DISCOVERY_ENABLED", "true")
KYBER_AGGREGATOR_API_URL: str = _env("KYBER_AGGREGATOR_API_URL", "https://aggregator-api.kyberswap.com")
KYBER_DISCOVERY_ENABLED: bool = _bool_env("KYBER_DISCOVERY_ENABLED", "true")

# Wallet, executor, runtime, and safety.
BOT_ADDRESS: str = _env("BOT_ADDRESS")
EXECUTOR_WALLET: str = _env("EXECUTOR_WALLET")
OWNER_ADDRESS: str = _first_env("OWNER_ADDRESS", "EXECUTOR_WALLET", "BOT_ADDRESS")
SOLC_VERSION: str = _env("SOLC_VERSION", "0.8.24")
CANONICAL_HFT_EXECUTOR_ADDRESS: str = "0x409ece3Fd71DFBd8f692B600f36A89301cb37346"
HFT_EXECUTOR_ADDRESS: str = _first_env("HFT_EXECUTOR_ADDRESS", "HFT_DEFAULT_TARGET", "CANONICAL_ON_CHAIN_MUSCLE", "C1_PAYLOAD_TARGET", "EXECUTOR_CONTRACT_ADDR", default=CANONICAL_HFT_EXECUTOR_ADDRESS)
EXECUTOR_CONTRACT: str = _first_env("EXECUTOR_CONTRACT", "EXECUTOR_CONTRACT_ADDR", "C1_PAYLOAD_TARGET", "CANONICAL_ON_CHAIN_MUSCLE", "HFT_DEFAULT_TARGET", default=HFT_EXECUTOR_ADDRESS)
C1_PAYLOAD_TARGET: str = _first_env("C1_PAYLOAD_TARGET", "C1_TARGET", "C1_ARB_EXECUTOR_ADDRESS", "EXECUTOR_CONTRACT_ADDR", default=EXECUTOR_CONTRACT)
C2_PAYLOAD_TARGET: str = _first_env("C2_PAYLOAD_TARGET", "C2_TARGET", "C2_ARB_EXECUTOR_ADDRESS", default=C1_PAYLOAD_TARGET)
ADAPTER_CONFIGURATION_TARGET: str = _env("ADAPTER_CONFIGURATION_TARGET", C1_PAYLOAD_TARGET)
CANONICAL_ON_CHAIN_MUSCLE: str = _first_env("CANONICAL_ON_CHAIN_MUSCLE", "HFT_DEFAULT_TARGET", "EXECUTOR_CONTRACT_ADDR", default=EXECUTOR_CONTRACT)
LIQUIDATION_EXECUTOR_ADDRESS: str = _env("LIQUIDATION_EXECUTOR_ADDRESS", "0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951")
PRIVATE_KEY: str = _first_env("PRIVATE_KEY", "EXECUTOR_PRIVATE_KEY")
EXEC_MODE: str = _first_env("EXECUTION_MODE", "EXEC_MODE", default="dry_run").lower()
LIVE_FLAG: str = _first_env("LIVE_TRADING", "LIVE_FLAG", default="0")
REQUIRED_CONFIRM: str = "YES_I_UNDERSTAND_THIS_USES_REAL_FUNDS"
CONFIRM_FLAG: str = _env("CONFIRM_MAINNET_EXECUTION")
MEV_ENABLED: bool = _bool_env("MEV_ENABLED", "false")
MEV_PUBLIC_FALLBACK_ENABLED: bool = _bool_env("MEV_PUBLIC_FALLBACK_ENABLED", "false")
FLASHBOTS_RELAY_URL: str = _env("FLASHBOTS_RELAY_URL", "https://relay.flashbots.net")
TITAN_MEV_US_WEST: str = _env("TITAN_MEV_US_WEST", "https://rpc.titanbuilder.xyz/")
BEAVER_BUILD_URL: str = _env("BEAVER_BUILD_URL", "https://rpc.beaverbuild.org/")
RSYNC_BUILDER_URL: str = _env("RSYNC_BUILDER_URL", "https://rsync-builder.xyz/")

# Cache, quota, and transport.
DATABASE_URL: str = _env("DATABASE_URL")
REDIS_URL: str = _env("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_ENABLED: str = _env("REDIS_ENABLED", "true")
REDIS_KEY_PREFIX: str = _env("REDIS_KEY_PREFIX", "omega_v5")
REDIS_RPC_CACHE_TTL_SECONDS: int = int(_env("REDIS_RPC_CACHE_TTL_SECONDS", "60") or "60")
TRANSPORT_LANES_ENABLED: bool = _bool_env("TRANSPORT_LANES_ENABLED", "true")
REQUIRE_EXECUTABLE_ROUTE_STREAM: bool = _bool_env("REQUIRE_EXECUTABLE_ROUTE_STREAM", "false")
EXECUTION_ROUTE_TARGET_MODE: str = _env("EXECUTION_ROUTE_TARGET_MODE", "capital_source_adapters").lower()
ALLOW_POOL_TARGETS_FOR_SCHEMA_CHECK: bool = _bool_env("ALLOW_POOL_TARGETS_FOR_SCHEMA_CHECK", "true")
RPC_HEALTH_TTL_SECONDS: int = int(_env("RPC_HEALTH_TTL_SECONDS", "15") or "15")
RPC_FAILED_TTL_SECONDS: int = int(_env("RPC_FAILED_TTL_SECONDS", "60") or "60")
RPC_ENDPOINT_TTL_SECONDS: int = int(_env("RPC_ENDPOINT_TTL_SECONDS", "60") or "60")
RPC_MAX_RPS_PER_LANE: int = int(_env("RPC_MAX_RPS_PER_LANE", "8") or "8")
RPC_EXACT_CALL_MAX_RPS: int = int(_env("RPC_EXACT_CALL_MAX_RPS", "3") or "3")
RPC_BROADCAST_MAX_RPS: int = int(_env("RPC_BROADCAST_MAX_RPS", "2") or "2")
RPC_REQUEST_TIMEOUT_SECONDS: int = int(_env("RPC_REQUEST_TIMEOUT_SECONDS", "6") or "6")
RPC_PLAN_NAME: str = _env("RPC_PLAN_NAME", "developer")
RPC_REQUEST_UNITS_LIMIT: int = int(_env("RPC_REQUEST_UNITS_LIMIT", "3000000") or "3000000")
RPC_COMPUTED_UNITS_EST: int = int(_env("RPC_COMPUTED_UNITS_EST", "60000000") or "60000000")
RPC_API_CREDITS: int = int(_env("RPC_API_CREDITS", "78000000") or "78000000")
RPC_RPS_LIMIT: int = int(_env("RPC_RPS_LIMIT", "25") or "25")
RPC_NODES: int = int(_env("RPC_NODES", "1") or "1")
RPC_WARP_TRANSACTIONS_ENABLED: bool = _bool_env("RPC_WARP_TRANSACTIONS_ENABLED", "false")
RPC_QUOTA_ENFORCEMENT: bool = _bool_env("RPC_QUOTA_ENFORCEMENT", "true")
RPC_QUOTA_WARN_THRESHOLD: float = float(_env("RPC_QUOTA_WARN_THRESHOLD", "0.8") or "0.8")
RPC_UNIT_COSTS: Dict[str, int] = {"eth_call": 1, "eth_getbalance": 1, "eth_getblockbynumber": 1, "eth_getcode": 1, "eth_getlogs": 5, "eth_gettransactionreceipt": 2, "eth_sendrawtransaction": 10, "debug_tracetransaction": 50, "default": 1}

POLYGON_GAS_STATION_ENABLED: bool = _bool_env("POLYGON_GAS_STATION_ENABLED", "true")
POLYGON_GAS_STATION_URL: str = _env("POLYGON_GAS_STATION_URL", "https://gasstation.polygon.technology/v2")
POLYGON_GAS_STATION_TIER: str = _env("POLYGON_GAS_STATION_TIER", "fast")
POLYGON_GAS_STATION_TTL_SECONDS: int = int(_env("POLYGON_GAS_STATION_TTL_SECONDS", "10") or "10")
POLYGON_GAS_STATION_TIMEOUT_SECONDS: Decimal = Decimal(_env("POLYGON_GAS_STATION_TIMEOUT_SECONDS", "3") or "3")
POLYGON_MIN_PRIORITY_FEE_GWEI: Decimal = Decimal(_env("POLYGON_MIN_PRIORITY_FEE_GWEI", "30") or "30")
POLYGON_MAX_FEE_SAFETY_MULTIPLIER: Decimal = Decimal(_env("POLYGON_MAX_FEE_SAFETY_MULTIPLIER", "1.25") or "1.25")

# Strategy sizing and guards.
ENABLE_STABLE_SWAP_STRATEGIES: bool = _bool_env("ENABLE_STABLE_SWAP_STRATEGIES", "true")
STABLE_SWAP_MIN_PROFIT_BPS: Decimal = Decimal(_env("STABLE_SWAP_MIN_PROFIT_BPS", "0") or "0")
STABLE_SWAP_MAX_PEG_DEVIATION_BPS: Decimal = Decimal(_env("STABLE_SWAP_MAX_PEG_DEVIATION_BPS", "250") or "250")
STABLE_MIN_NET_PROFIT_USD: Decimal = Decimal(_env("STABLE_MIN_NET_PROFIT_USD", "1") or "1")
STABLE_RISK_BUFFER_USD: Decimal = Decimal(_env("STABLE_RISK_BUFFER_USD", "0.5") or "0.5")
FLASH_BASE_ASSETS: List[str] = _csv_env("FLASH_BASE_ASSETS", "USDC,USDC.e,USDT,DAI,WPOL,WETH,WBTC")
PREFERRED_FLASH_SOURCE: str = _env("PREFERRED_FLASH_SOURCE", "BALANCER").upper()
ENABLE_DYNAMIC_FLASH_SIZING: bool = _bool_env("ENABLE_DYNAMIC_FLASH_SIZING", "true")
ENABLE_DYNAMIC_SIZE_OPTIMIZER: bool = _bool_env("ENABLE_DYNAMIC_SIZE_OPTIMIZER", "true")
MIN_FLASH_PRINCIPAL_USD: Decimal = Decimal(_env("MIN_FLASH_PRINCIPAL_USD", "5000") or "5000")
MAX_FLASH_PRINCIPAL_USD: Decimal = Decimal(_env("MAX_FLASH_PRINCIPAL_USD", "250000") or "250000")
MAX_ROUTE_TVL_FRACTION: Decimal = Decimal(_env("MAX_ROUTE_TVL_FRACTION", "0.50") or "0.50")
MAX_ROUTE_IMPACT: Decimal = Decimal(_env("MAX_ROUTE_IMPACT", "0.01") or "0.01")
FLASH_ROUTE_TVL_FRACTIONS: List[Decimal] = _csv_env_decimal("FLASH_ROUTE_TVL_FRACTIONS", "0.15,0.25,0.50")
FLASH_SIZE_LADDER_BPS: List[Decimal] = _csv_env_decimal("FLASH_SIZE_LADDER_BPS", "1000,1500")
DYNAMIC_SIZE_IMPACT_PENALTY_BPS: Decimal = Decimal(_env("DYNAMIC_SIZE_IMPACT_PENALTY_BPS", "120") or "120")
DYNAMIC_SIZE_MAX_SEARCH_STEPS: int = int(_env("DYNAMIC_SIZE_MAX_SEARCH_STEPS", "18") or "18")
DYNAMIC_SIZE_OPT_BINS_USD: List[Decimal] = _csv_env_decimal("DYNAMIC_SIZE_OPT_BINS_USD", "100,500,1000,2500,5000,10000,25000,50000")
MIN_PRINCIPAL_USD: Decimal = Decimal(_env("MIN_PRINCIPAL_USD", "10.0") or "10.0")
MAX_PRINCIPAL_USD: Decimal = Decimal(_env("MAX_PRINCIPAL_USD", "100000.0") or "100000.0")
MIN_PROFIT_THRESHOLD_USD: Decimal = Decimal(_env("MIN_PROFIT_THRESHOLD_USD", "0.50") or "0.50")
MAX_SLIPPAGE_BPS: int = int(_env("MAX_SLIPPAGE_BPS", "300") or "300")
MIN_NET_PROFIT_USD: Decimal = Decimal(_env("MIN_NET_PROFIT_USD", "0.5") or "0.5")
PROTOCOL_OVERHEAD_USD: Decimal = Decimal(_env("PROTOCOL_OVERHEAD_USD", "0.01") or "0.01")
DETERMINISTIC_APEX_INJECTOR_ENABLED: bool = _bool_env("OMEGA_INJECTOR_DETERMINISTIC_MODE", "true")
APEX_INJECTOR_PRECISION_DECIMALS: int = int(_env("OMEGA_INJECTOR_PRECISION_DECIMALS", "18") or "18")
APEX_INJECTOR_MAX_TVL_IMPACT_BPS: int = int(_env("OMEGA_INJECTOR_MAX_TVL_IMPACT_BPS", "500") or "500")
BELLMAN_CURVE_DECAY_FACTOR: Decimal = Decimal(_env("BELLMAN_CURVE_DECAY_FACTOR", "0.85") or "0.85")
BELLMAN_QUADRATIC_IMPACT: Decimal = Decimal(_env("BELLMAN_QUADRATIC_IMPACT", "0.5") or "0.5")
ENABLE_QUANTUM_SIZING: bool = _bool_env("ENABLE_QUANTUM_SIZING", "true")
QUANTUM_SIZING_SHOTS: int = int(_env("QUANTUM_SIZING_SHOTS", "64") or "64")
QUANTUM_ADJUSTMENT_SCALE: Decimal = Decimal(_env("QUANTUM_ADJUSTMENT_SCALE", "0.02") or "0.02")
ML_RANKING_ENABLED: bool = _bool_env("ML_RANKING_ENABLED", "true")
CURRENT_RANKER_MODEL: str = _env("CURRENT_RANKER_MODEL", "vqc_surplus_ranker_v1.1.0")
OMEGA_ML_MODEL_DIR: str = _env("OMEGA_ML_MODEL_DIR", "models")

# Liquidation, discovery, indexer, token calibration.
ENABLE_LIQUIDATION_PIPELINE: bool = _bool_env("ENABLE_LIQUIDATION_PIPELINE", "true")
LIQUIDATION_SCAN_BLOCKS: int = int(_env("LIQUIDATION_SCAN_BLOCKS", "2500") or "2500")
LIQUIDATION_MAX_BORROWERS: int = int(_env("LIQUIDATION_MAX_BORROWERS", "200") or "200")
LIQUIDATION_MIN_NET_PROFIT_USD: Decimal = Decimal(_env("LIQUIDATION_MIN_NET_PROFIT_USD", "5") or "5")
LIQUIDATION_GAS_UNITS_1HOP: int = int(_env("LIQUIDATION_GAS_UNITS_1HOP", "650000") or "650000")
LIQUIDATION_GAS_UNITS_2HOP: int = int(_env("LIQUIDATION_GAS_UNITS_2HOP", "900000") or "900000")
AAVE_V3_POOL_ADDRESSES_PROVIDER: str = _env("AAVE_V3_POOL_ADDRESSES_PROVIDER", "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb")
AAVE_V3_PROTOCOL_DATA_PROVIDER: str = _env("AAVE_V3_PROTOCOL_DATA_PROVIDER")
AAVE_BORROWER_SEED_ADDRESSES: List[str] = _csv_env("AAVE_BORROWER_SEED_ADDRESSES")
ENABLE_FACTORY_POOL_DISCOVERY: bool = _bool_env("ENABLE_FACTORY_POOL_DISCOVERY", "true")
DISCOVERY_MAX_TOKEN_PAIRS: int = int(_env("DISCOVERY_MAX_TOKEN_PAIRS", "160") or "160")
DISCOVERY_MAX_PROMOTED_POOLS: int = int(_env("DISCOVERY_MAX_PROMOTED_POOLS", "192") or "192")
POOL_LOAD_SLEEP_SECONDS: Decimal = Decimal(_env("POOL_LOAD_SLEEP_SECONDS", "0.02") or "0.02")
INDEXER_SQLITE_PATH: str = _env("INDEXER_SQLITE_PATH", "out/polygon_indexer.sqlite")
INDEXER_STATE_MAX_AGE_BLOCKS: int = int(_env("INDEXER_STATE_MAX_AGE_BLOCKS", "20") or "20")
TOKEN_CALIBRATION_CACHE_TTL_SECONDS: int = int(_env("TOKEN_CALIBRATION_CACHE_TTL_SECONDS", "86400") or "86400")
TOKEN_CALIBRATION_MAX_MULTICALL_BATCH: int = int(_env("TOKEN_CALIBRATION_MAX_MULTICALL_BATCH", "120") or "120")

# Smart/session surfaces.
ENABLE_SMART_SESSIONS: bool = _bool_env("ENABLE_SMART_SESSIONS", "false")
SESSION_SIGNER_ENABLED: bool = _bool_env("SESSION_SIGNER_ENABLED", "false")
SESSION_SIGNER_MODE: str = _env("SESSION_SIGNER_MODE", "dry_run").lower()
WAAS_BROADCAST_ADAPTER_ENABLED: bool = _bool_env("WAAS_BROADCAST_ADAPTER_ENABLED", "false")
WAAS_BROADCAST_ADAPTER_MODE: str = _env("WAAS_BROADCAST_ADAPTER_MODE", "dry_run").lower()
SMART_SESSIONS_WAAS_API_URL: str = _env("SMART_SESSIONS_WAAS_API_URL")
SMART_SESSIONS_CREDENTIAL_ID: str = _env("SMART_SESSIONS_CREDENTIAL_ID")
SMART_SESSIONS_WALLET_ID: str = _env("SMART_SESSIONS_WALLET_ID")
SMART_SESSIONS_MAX_VALUE_WEI: str = _env("SMART_SESSIONS_MAX_VALUE_WEI", "0")
SMART_SESSIONS_ALLOWED_TARGETS: List[str] = _csv_env("SMART_SESSIONS_ALLOWED_TARGETS")
SMART_SESSIONS_ALLOWED_SELECTORS: List[str] = _csv_env("SMART_SESSIONS_ALLOWED_SELECTORS")
SESSION_PROOF_SAMPLES: int = int(_env("SESSION_PROOF_SAMPLES", "5") or "5")

BALANCER_V3_VAULT: str = _env("BALANCER_V3_VAULT", "0xBA12222222228d8Ba445958a75a0704d566BF2C8")
ENABLE_TRANSIENT_STORAGE_FLASH: bool = _bool_env("ENABLE_TRANSIENT_STORAGE_FLASH", "true")
RESERVE_DRIFT_THRESHOLD_MS: int = int(_env("OMEGA_RESERVE_DRIFT_THRESHOLD_MS", "200") or "200")
ML_LIQUIDITY_VOLATILITY_THRESHOLD: float = float(_env("OMEGA_ML_LIQUIDITY_VOLATILITY_THRESHOLD", "0.85") or "0.85")

