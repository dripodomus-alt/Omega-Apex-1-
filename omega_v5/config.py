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
    "V3_CLMM": 1,        # Uniswap V3
    "QS_V2_CPMM": 2,     # QuickSwap V2
    "BAL_WEIGHTED": 3,   # Balancer
    "QS_V3_ALGEBRA": 4,  # QuickSwap V3 / Algebra
    "SUSHI_V2_CPMM": 2,  # Sushiswap V2 (reuses the same V2 adapter ID)
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
        "pool_kind": 0,
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
        "pool_kind": 1, # Reuses the V2 CPMM pool kind
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Sushiswap V2 fork of Uniswap V2. Reuses the V2 adapter.",
        "precision_pricing": True,
    },
    "QS_V3_ALGEBRA": {
        "display_name": "QuickSwap V3 (Algebra CLMM)",
        "family": "CLMM",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 0,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "QuickSwap V3 uses the Algebra protocol, which is V3-compatible.",
        "precision_pricing": True,
    },
    "BAL_WEIGHTED": {
        "display_name": "Balancer Weighted Pool",
        "family": "WEIGHTED",
        "status": "fully_executable",
        "adapters": ["OmegaRouteSwapAdapter"],
        "pool_kind": 2,
        "lineage": ["DISCOVERED", "RANKED", "SIMULATED", "PREPARED", "EXECUTED", "ACCOUNTED"],
        "notes": "Balancer weighted pools, including multi-asset.",
        "precision_pricing": True,
    },
}

# This map provides a bridge from common (and sometimes inconsistent) names
# found in external data sources to our canonical internal protocol keys.
PROTOCOL_ALIAS_MAP: Dict[str, str] = {
    "UniswapV3": "V3_CLMM",
    "QuickSwapV2": "QS_V2_CPMM",
    "QuickSwapV3": "QS_V3_ALGEBRA",
    "Sushiswap": "SUSHI_V2_CPMM",
    "Algebra": "QS_V3_ALGEBRA",
    "Balancer": "BAL_WEIGHTED",
}


# ==============================================================================
# ENVIRONMENT HELPERS
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


# ==============================================================================
# RPC & API ENDPOINTS
# ==============================================================================

# ── Primary RPCs ──────────────────────────────────────────────────────────────
WSS_URL: str = _first_env(
    "POLYGON_WSS_URL",
    "DISCOVERY_RPC_WSS",
    "PRIMARY_WSS_URL",
    "POLYGON_WSS",
    "POLYGON_WS",
    default="wss://polygon-bor-rpc.publicnode.com",
)
HTTP_URL: str = _first_env(
    "POLYGON_RPC_URL",
    "RPC_URL",
    "PRIMARY_READ_RPC_URL",
    "DISCOVERY_RPC_URL",
    "POLYGON_RPC",
    default="https://polygon-bor-rpc.publicnode.com",
)

BROADCAST_RPC_URL: str = _first_env(
    "BROADCAST_RPC_URL",
    "WRITABLE_RPC_URL",
    "POLYGON_WRITABLE_RPC_URL",
)
BROADCAST_WSS_URL: str = _first_env(
    "BROADCAST_WSS_URL",
    "WRITABLE_WSS_URL",
    "POLYGON_WRITABLE_WSS_URL",
)

EXACT_CALL_RPC_URL: str = _first_env(
    "EXACT_CALL_RPC_URL",
    "PRIMARY_READ_RPC_URL",
    "DISCOVERY_RPC_URL",
    "POLYGON_RPC_URL",
    "RPC_URL",
    default=HTTP_URL,
)

# ── Forking & Simulation RPCs ─────────────────────────────────────────────────
FORK_UPSTREAM_RPC_URL: str = _env("FORK_UPSTREAM_RPC_URL", HTTP_URL)
FORK_RPC_URL: str = _env("FORK_RPC_URL", "http://127.0.0.1:8545")
FORK_SIM_RPC_URL: str = _env("FORK_SIM_RPC_URL", "http://127.0.0.1:8545")

# ── Vendor-Specific & Fallback RPCs ───────────────────────────────────────────
GETBLOCK_POLYGON_RPC_HTTP: str = _first_env("GETBLOCK_POLYGON_RPC_HTTP", "GETBLOCK_HTTP", "POLYGON_RPC_GETBLOCK")
GETBLOCK_POLYGON_RPC_WSS: str = _first_env("GETBLOCK_POLYGON_RPC_WSS", "GETBLOCK_WSS", "POLYGON_WSS_GETBLOCK")
INFURA_HTTP: str = _first_env("INFURA_HTTP", "INFURA_POLYGON_RPC_HTTP")
INFURA_WSS: str = _first_env("INFURA_WSS", "INFURA_WSS_URL", "INFURA_POLYGON_RPC_WS")
DRPC_LB_HTTP_URL: str = _first_env("DRPC_LB_HTTP_URL", "DRPC_POLYGON_LB_HTTP", "DRPC_POLYGON_HTTP")
DRPC_LB_WSS_URL: str = _first_env("DRPC_LB_WSS_URL", "DRPC_POLYGON_LB_WSS", "DRPC_POLYGON_WSS")
ENABLE_NODECORE: bool = _env("ENABLE_NODECORE", "false").lower() in {"1", "true", "yes", "on"}
NODECORE_HTTP_URL: str = _env("NODECORE_HTTP_URL") # For RPC rotation
NODECORE_WSS_URL: str = _env("NODECORE_WSS_URL")   # For RPC rotation
HTTP_URL_2: str = _env("POLYGON_RPC2") # Generic secondary RPC
CHAINSTACK_URL: str  = _env("CHAINSTACK_URL", "https://polygon-mainnet.chainstackapis.com")

# ── API Keys & External Services ──────────────────────────────────────────────
ONEINCH_API_KEY: str = _env("ONEINCH_API_KEY")
COINGECKO_KEY: str   = _env("COINGECKO_API_KEY")
POLYGONSCAN_API_KEY: str = _env("POLYGONSCAN_API_KEY")
ETHERSCAN_API_KEY: str = _first_env("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY")
ETHERSCAN_API_URL: str = _env("ETHERSCAN_API_URL", "https://api.etherscan.io/v2/api")
MORALIS_API: str = _env("MORALIS_API", "https://deep-index.moralis.io/api/v2.2")
MORALIS_API_KEY: str = _env("MORALIS_API_KEY")
BALANCER_API_URL: str = _env("BALANCER_API_URL", "https://api-v3.balancer.fi/")

# ── Local API Server ──────────────────────────────────────────────────────────
API_HOST: str = _env("API_HOST", "127.0.0.1")
API_PORT: int = int(_env("API_PORT", "8080") or "8080")
API_PROXY_TARGET: str = _env("API_PROXY_TARGET", f"http://localhost:{API_PORT}")
API_TOKEN: str = _env("API_TOKEN")
API_CORS_ORIGINS: List[str] = _csv_env(
    "API_CORS_ORIGINS",
    ",".join(
        [
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "https://ai.studio",
        ]
    ),
)
API_FRONTEND_TOKEN_REQUIRED: bool = _bool_env("API_FRONTEND_TOKEN_REQUIRED", "false")

# ── RPC Rotation & Fallbacks ──────────────────────────────────────────────────
BROADCAST_RPC_FALLBACK_URLS: List[str] = _csv_env(
    "BROADCAST_RPC_FALLBACK_URLS",
    ",".join(
        [
            GETBLOCK_POLYGON_RPC_HTTP,
            INFURA_HTTP,
            "https://polygon.drpc.org",
            "https://polygon-bor-rpc.publicnode.com",
            "https://polygon.publicnode.com",
            "https://1rpc.io/matic",
        ]
    ),
)
BROADCAST_WSS_FALLBACK_URLS: List[str] = _csv_env(
    "BROADCAST_WSS_FALLBACK_URLS",
    ",".join([GETBLOCK_POLYGON_RPC_WSS, INFURA_WSS, "wss://polygon.drpc.org", "wss://polygon-bor-rpc.publicnode.com"]),
)
RPC_ROTATION_HTTP_URLS: List[str] = _csv_env(
    "RPC_ROTATION_HTTP_URLS",
    ",".join(
        [
            NODECORE_HTTP_URL,
            DRPC_LB_HTTP_URL,
            "https://polygon.drpc.org",
            "https://tenderly.rpc.polygon.community",
            "https://polygon-bor-rpc.publicnode.com",
            "https://polygon.publicnode.com",
            "https://polygon-mainnet.gateway.tatum.io",
            "https://polygon-public.nodies.app",
            "https://1rpc.io/matic",
            "https://rpc-mainnet.matic.quiknode.pro",
            "https://polygon.api.onfinality.io/public",
            GETBLOCK_POLYGON_RPC_HTTP,
            INFURA_HTTP,
        ]
    ),
)
RPC_ROTATION_WSS_URLS: List[str] = _csv_env(
    "RPC_ROTATION_WSS_URLS",
    ",".join([NODECORE_WSS_URL, DRPC_LB_WSS_URL, "wss://polygon.drpc.org", "wss://polygon-bor-rpc.publicnode.com", GETBLOCK_POLYGON_RPC_WSS, INFURA_WSS]),
)

# ── MEV Relays / Builders ─────────────────────────────────────────────────────
FLASHBOTS_RELAY_URL: str = _env("FLASHBOTS_RELAY_URL", "https://relay.flashbots.net")
TITAN_MEV_US_WEST: str = _env("TITAN_MEV_US_WEST", "https://rpc.titanbuilder.xyz/")
BEAVER_BUILD_URL: str = _env("BEAVER_BUILD_URL", "https://rpc.beaverbuild.org/")
RSYNC_BUILDER_URL: str = _env("RSYNC_BUILDER_URL", "https://rsync-builder.xyz/")

# ── DODO RPC Proxy (if used) ──────────────────────────────────────────────────
DODO_RPC_PROVIDER_URL: str = _env("DODO_RPC_PROVIDER_URL")
DODO_RPC_PROXY_URL: str = _env("DODO_RPC_PROXY_URL")
DODO_RPC_SOURCES: str = _env("DODO_RPC_SOURCES", "ChainList")
DODO_RPC_EXTRA_HTTP_URLS: List[str] = _csv_env("DODO_RPC_EXTRA_HTTP_URLS", ",".join(RPC_ROTATION_HTTP_URLS))

# ── Telemetry RPC ─────────────────────────────────────────────────────────────
TELEMETRY_RPC_URL: str = _first_env(
    "TELEMETRY_RPC_URL",
    "POLYGON_RPC2",
    "DODO_RPC_PROXY_URL",
    "POLYGON_RPC_URL",
    default=HTTP_URL_2 or HTTP_URL,
)

# ==============================================================================
# WALLET & EXECUTION
# ==============================================================================
BOT_ADDRESS: str = _env("BOT_ADDRESS")
EXECUTOR_WALLET: str = _env("EXECUTOR_WALLET")
OWNER_ADDRESS: str = _first_env("OWNER_ADDRESS", "EXECUTOR_WALLET", "BOT_ADDRESS")
SOLC_VERSION: str = _env("SOLC_VERSION", "0.8.24")

# ==============================================================================
# CACHING
# ==============================================================================
REDIS_URL: str = _env("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_ENABLED: str = _env("REDIS_ENABLED", "true")
REDIS_KEY_PREFIX: str = _env("REDIS_KEY_PREFIX", "omega_v5")
REDIS_RPC_CACHE_TTL_SECONDS: int = int(_env("REDIS_RPC_CACHE_TTL_SECONDS", "60") or "60")
TRANSPORT_LANES_ENABLED: bool = (
    _env("TRANSPORT_LANES_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
)
REQUIRE_EXECUTABLE_ROUTE_STREAM: bool = (
    _env("REQUIRE_EXECUTABLE_ROUTE_STREAM", "false").lower() in {"1", "true", "yes", "on"}
)
EXECUTION_ROUTE_TARGET_MODE: str = _env("EXECUTION_ROUTE_TARGET_MODE", "capital_source_adapters").lower()
ALLOW_POOL_TARGETS_FOR_SCHEMA_CHECK: bool = (
    _env("ALLOW_POOL_TARGETS_FOR_SCHEMA_CHECK", "true").lower() in {"1", "true", "yes", "on"}
)

# ==============================================================================
# RPC TRANSPORT & HEALTH
# ==============================================================================
RPC_HEALTH_TTL_SECONDS: int = int(_env("RPC_HEALTH_TTL_SECONDS", "15") or "15")
RPC_FAILED_TTL_SECONDS: int = int(_env("RPC_FAILED_TTL_SECONDS", "60") or "60")
RPC_ENDPOINT_TTL_SECONDS: int = int(_env("RPC_ENDPOINT_TTL_SECONDS", "60") or "60")
RPC_MAX_RPS_PER_LANE: int = int(_env("RPC_MAX_RPS_PER_LANE", "8") or "8")
RPC_EXACT_CALL_MAX_RPS: int = int(_env("RPC_EXACT_CALL_MAX_RPS", "3") or "3")
RPC_BROADCAST_MAX_RPS: int = int(_env("RPC_BROADCAST_MAX_RPS", "2") or "2")
RPC_REQUEST_TIMEOUT_SECONDS: int = int(_env("RPC_REQUEST_TIMEOUT_SECONDS", "6") or "6")

# ==============================================================================
# SMART SESSIONS (Waas)
# ==============================================================================
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

# ==============================================================================
# STRATEGY PARAMETERS
# ==============================================================================

# ── Stable Swap Strategy ──────────────────────────────────────────────────────
ENABLE_STABLE_SWAP_STRATEGIES: bool = (
    _env("ENABLE_STABLE_SWAP_STRATEGIES", "true").lower() in {"1", "true", "yes", "on"}
)
STABLE_SWAP_MIN_PROFIT_BPS: Decimal = Decimal(_env("STABLE_SWAP_MIN_PROFIT_BPS", "0") or "0")
STABLE_SWAP_MAX_PEG_DEVIATION_BPS: Decimal = Decimal(
    _env("STABLE_SWAP_MAX_PEG_DEVIATION_BPS", "250") or "250"
)
STABLE_MIN_NET_PROFIT_USD: Decimal = Decimal(_env("STABLE_MIN_NET_PROFIT_USD", "1") or "1")
STABLE_RISK_BUFFER_USD: Decimal = Decimal(_env("STABLE_RISK_BUFFER_USD", "0.5") or "0.5")

# ── Liquidation Strategy ──────────────────────────────────────────────────────
ENABLE_LIQUIDATION_PIPELINE: bool = (
    _env("ENABLE_LIQUIDATION_PIPELINE", "true").lower() in {"1", "true", "yes", "on"}
)
LIQUIDATION_SCAN_BLOCKS: int = int(_env("LIQUIDATION_SCAN_BLOCKS", "2500") or "2500")
LIQUIDATION_MAX_BORROWERS: int = int(_env("LIQUIDATION_MAX_BORROWERS", "200") or "200")
LIQUIDATION_MIN_NET_PROFIT_USD: Decimal = Decimal(_env("LIQUIDATION_MIN_NET_PROFIT_USD", "5") or "5")
LIQUIDATION_GAS_UNITS_1HOP: int = int(_env("LIQUIDATION_GAS_UNITS_1HOP", "650000"))
LIQUIDATION_GAS_UNITS_2HOP: int = int(_env("LIQUIDATION_GAS_UNITS_2HOP", "900000"))
AAVE_V3_POOL_ADDRESSES_PROVIDER: str = _env(
    "AAVE_V3_POOL_ADDRESSES_PROVIDER",
    "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
)
AAVE_V3_PROTOCOL_DATA_PROVIDER: str = _env("AAVE_V3_PROTOCOL_DATA_PROVIDER")
AAVE_BORROWER_SEED_ADDRESSES: List[str] = _csv_env("AAVE_BORROWER_SEED_ADDRESSES")

# ==============================================================================
# SIZING, GUARDRAILS & PROFITABILITY
# ==============================================================================

# ── Flash Loan Sizing ─────────────────────────────────────────────────────────
FLASH_BASE_ASSETS: List[str] = [
    item.strip()
    for item in _env("FLASH_BASE_ASSETS", "USDC,USDC.e,USDT,DAI,WPOL,WETH,WBTC").split(",")
    if item.strip()
]
PREFERRED_FLASH_SOURCE: str = _env("PREFERRED_FLASH_SOURCE", "BALANCER").upper()
ENABLE_DYNAMIC_FLASH_SIZING: bool = (
    _env("ENABLE_DYNAMIC_FLASH_SIZING", "true").lower() in {"1", "true", "yes", "on"}
)
ENABLE_DYNAMIC_SIZE_OPTIMIZER: bool = (
    _env("ENABLE_DYNAMIC_SIZE_OPTIMIZER", "true").lower() in {"1", "true", "yes", "on"}
)
MIN_FLASH_PRINCIPAL_USD: Decimal = Decimal(_env("MIN_FLASH_PRINCIPAL_USD", "5000"))
MAX_FLASH_PRINCIPAL_USD: Decimal = Decimal(_env("MAX_FLASH_PRINCIPAL_USD", "250000"))
MAX_ROUTE_TVL_FRACTION: Decimal = Decimal(_env("MAX_ROUTE_TVL_FRACTION", "0.50"))
MAX_ROUTE_IMPACT: Decimal = Decimal(_env("MAX_ROUTE_IMPACT", "0.01"))
FLASH_ROUTE_TVL_FRACTIONS: List[Decimal] = _csv_env_decimal("FLASH_ROUTE_TVL_FRACTIONS", "0.15,0.25,0.50")
FLASH_SIZE_LADDER_BPS: List[Decimal] = _csv_env_decimal("FLASH_SIZE_LADDER_BPS", "1000,1500")
DYNAMIC_SIZE_IMPACT_PENALTY_BPS: Decimal = Decimal(_env("DYNAMIC_SIZE_IMPACT_PENALTY_BPS", "120"))
DYNAMIC_SIZE_MAX_SEARCH_STEPS: int = int(_env("DYNAMIC_SIZE_MAX_SEARCH_STEPS", "18"))
DYNAMIC_SIZE_OPT_BINS_USD: List[Decimal] = _csv_env_decimal("DYNAMIC_SIZE_OPT_BINS_USD", "100,500,1000,2500,5000,10000,25000,50000")

# ── General Guardrails & Profitability ────────────────────────────────────────
MIN_PRINCIPAL_USD: Decimal = Decimal(_env("MIN_PRINCIPAL_USD", "10.0"))
MAX_PRINCIPAL_USD: Decimal = Decimal(_env("MAX_PRINCIPAL_USD", "100000.0"))
MIN_PROFIT_THRESHOLD_USD: Decimal = Decimal(_env("MIN_PROFIT_THRESHOLD_USD", "0.50"))
MAX_SLIPPAGE_BPS: int = int(_env("MAX_SLIPPAGE_BPS", "300"))
MIN_NET_PROFIT_USD: Decimal = Decimal(_env("MIN_NET_PROFIT_USD", "0.5"))
PROTOCOL_OVERHEAD_USD: Decimal = Decimal(_env("PROTOCOL_OVERHEAD_USD", "0.01"))

# ==============================================================================
# ML & QUANTUM SIZING
# ==============================================================================
# ── Official Capital Injector / Bellman + Quantum constants (new) ─────────────
BELLMAN_CURVE_DECAY_FACTOR: Decimal = Decimal(_env("BELLMAN_CURVE_DECAY_FACTOR", "0.85"))
BELLMAN_QUADRATIC_IMPACT: Decimal = Decimal(_env("BELLMAN_QUADRATIC_IMPACT", "0.5"))
ENABLE_QUANTUM_SIZING: bool = _bool_env("ENABLE_QUANTUM_SIZING", "true")
QUANTUM_SIZING_SHOTS: int = int(_env("QUANTUM_SIZING_SHOTS", "64"))
QUANTUM_ADJUSTMENT_SCALE: Decimal = Decimal(_env("QUANTUM_ADJUSTMENT_SCALE", "0.02"))

# ── ML Alpha Settings ─────────────────────────────────────────────────────────
ML_RANKING_ENABLED: bool = _bool_env("ML_RANKING_ENABLED", "true")
CURRENT_RANKER_MODEL: str = _env("CURRENT_RANKER_MODEL", "vqc_surplus_ranker_v1.1.0")

# ==============================================================================
# DISCOVERY PARAMETERS
# ==============================================================================
ENABLE_FACTORY_POOL_DISCOVERY: bool = _bool_env("ENABLE_FACTORY_POOL_DISCOVERY", "true")
DISCOVERY_MAX_TOKEN_PAIRS: int = int(_env("DISCOVERY_MAX_TOKEN_PAIRS", "160") or "160")
DISCOVERY_MAX_PROMOTED_POOLS: int = int(_env("DISCOVERY_MAX_PROMOTED_POOLS", "192") or "192")
POOL_LOAD_SLEEP_SECONDS: Decimal = Decimal(_env("POOL_LOAD_SLEEP_SECONDS", "0.02") or "0.02")
