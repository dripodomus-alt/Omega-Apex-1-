# ==============================================================================
# config.py  —  Asset matrix, chain constants, environment helpers
# Extracted from Cell 1 of notebooks/omega_v5.ipynb
# ==============================================================================

import os
from decimal import Decimal
from typing import List

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

# ── Comprehensive Multi-Asset Registry for Chain 137 (61 Assets) ──────────────
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

# ── Environment helpers ───────────────────────────────────────────────────────
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


WSS_URL: str = _first_env(
    "POLYGON_WSS_URL",
    "DISCOVERY_RPC_WSS",
    "POLYGON_WSS",
    "POLYGON_WS",
    default="wss://polygon-bor-rpc.publicnode.com",
)
HTTP_URL: str = _first_env(
    "POLYGON_RPC_URL",
    "RPC_URL",
    "DISCOVERY_RPC_URL",
    "POLYGON_RPC",
    default="https://polygon-bor-rpc.publicnode.com",
)
HTTP_URL_2: str = _env("POLYGON_RPC2")
CHAINSTACK_URL: str  = _env("CHAINSTACK_URL",    "https://polygon-mainnet.chainstackapis.com")
ONEINCH_API_KEY: str = _env("ONEINCH_API_KEY")
COINGECKO_KEY: str   = _env("COINGECKO_API_KEY")
POLYGONSCAN_API_KEY: str = _env("POLYGONSCAN_API_KEY")
ETHERSCAN_API_KEY: str = _first_env("ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY")
ETHERSCAN_API_URL: str = _env("ETHERSCAN_API_URL", "https://api.etherscan.io/v2/api")
SOLC_VERSION: str = _env("SOLC_VERSION", "0.8.24")
MORALIS_API: str = _env("MORALIS_API", "https://deep-index.moralis.io/api/v2.2")
MORALIS_API_KEY: str = _env("MORALIS_API_KEY")
BALANCER_API_URL: str = _env("BALANCER_API_URL", "https://api-v3.balancer.fi/")
GETBLOCK_POLYGON_RPC_HTTP: str = _first_env("GETBLOCK_POLYGON_RPC_HTTP", "GETBLOCK_HTTP", "POLYGON_RPC_GETBLOCK")
GETBLOCK_POLYGON_RPC_WSS: str = _first_env("GETBLOCK_POLYGON_RPC_WSS", "GETBLOCK_WSS", "POLYGON_WSS_GETBLOCK")
INFURA_HTTP: str = _first_env("INFURA_HTTP", "INFURA_POLYGON_RPC_HTTP")
INFURA_WSS: str = _first_env("INFURA_WSS", "INFURA_WSS_URL", "INFURA_POLYGON_RPC_WS")
DRPC_LB_HTTP_URL: str = _first_env("DRPC_LB_HTTP_URL", "DRPC_POLYGON_LB_HTTP", "DRPC_POLYGON_HTTP")
DRPC_LB_WSS_URL: str = _first_env("DRPC_LB_WSS_URL", "DRPC_POLYGON_LB_WSS", "DRPC_POLYGON_WSS")
ENABLE_NODECORE: bool = _env("ENABLE_NODECORE", "false").lower() in {"1", "true", "yes", "on"}
NODECORE_HTTP_URL: str = _env("NODECORE_HTTP_URL")
NODECORE_WSS_URL: str = _env("NODECORE_WSS_URL")
ENABLE_DRPC_DATA_API: bool = _env("ENABLE_DRPC_DATA_API", "false").lower() in {"1", "true", "yes", "on"}
DRPC_DATA_API_URL: str = _env("DRPC_DATA_API_URL", "https://api.drpc.org")
DRPC_DATA_API_KEY: str = _env("DRPC_DATA_API_KEY")
DRPC_DATA_CACHE_TTL_SECONDS: int = int(_env("DRPC_DATA_CACHE_TTL_SECONDS", "120") or "120")
ENABLE_SMART_SESSIONS: bool = _env("ENABLE_SMART_SESSIONS", "false").lower() in {"1", "true", "yes", "on"}
SESSION_SIGNER_ENABLED: bool = _env("SESSION_SIGNER_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
SESSION_SIGNER_MODE: str = _env("SESSION_SIGNER_MODE", "dry_run").lower()
WAAS_BROADCAST_ADAPTER_ENABLED: bool = _env("WAAS_BROADCAST_ADAPTER_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
WAAS_BROADCAST_ADAPTER_MODE: str = _env("WAAS_BROADCAST_ADAPTER_MODE", "dry_run").lower()
SMART_SESSIONS_WAAS_API_URL: str = _env("SMART_SESSIONS_WAAS_API_URL")
SMART_SESSIONS_CREDENTIAL_ID: str = _env("SMART_SESSIONS_CREDENTIAL_ID")
SMART_SESSIONS_WALLET_ID: str = _env("SMART_SESSIONS_WALLET_ID")
SMART_SESSIONS_MAX_VALUE_WEI: str = _env("SMART_SESSIONS_MAX_VALUE_WEI", "0")
SMART_SESSIONS_ALLOWED_TARGETS: List[str] = _csv_env("SMART_SESSIONS_ALLOWED_TARGETS")
SMART_SESSIONS_ALLOWED_SELECTORS: List[str] = _csv_env("SMART_SESSIONS_ALLOWED_SELECTORS")
SESSION_PROOF_SAMPLES: int = int(_env("SESSION_PROOF_SAMPLES", "5") or "5")
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
API_FRONTEND_TOKEN_REQUIRED: bool = _env("API_FRONTEND_TOKEN_REQUIRED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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
PRIMARY_READ_RPC_URL: str = _first_env(
    "PRIMARY_READ_RPC_URL",
    "EXACT_CALL_RPC_URL",
    "DISCOVERY_RPC_URL",
    "POLYGON_RPC_URL",
    "RPC_URL",
    "POLYGON_RPC",
    default=HTTP_URL,
)
EXACT_CALL_RPC_URL: str = _first_env(
    "EXACT_CALL_RPC_URL",
    "PRIMARY_READ_RPC_URL",
    "DISCOVERY_RPC_URL",
    "POLYGON_RPC_URL",
    "RPC_URL",
    default=PRIMARY_READ_RPC_URL,
)
PRIMARY_WSS_URL: str = _first_env(
    "PRIMARY_WSS_URL",
    "POLYGON_WSS_URL",
    "DISCOVERY_RPC_WSS",
    "POLYGON_WSS",
    "POLYGON_WS",
    default=WSS_URL,
)
TELEMETRY_RPC_URL: str = _first_env(
    "TELEMETRY_RPC_URL",
    "POLYGON_RPC2",
    "DODO_RPC_PROXY_URL",
    "POLYGON_RPC_URL",
    default=HTTP_URL_2 or HTTP_URL,
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
FLASHBOTS_RELAY_URL: str = _env("FLASHBOTS_RELAY_URL")
TITAN_MEV_US_WEST: str = _env("TITAN_MEV_US_WEST")
DODO_RPC_PROVIDER_URL: str = _env("DODO_RPC_PROVIDER_URL")
DODO_RPC_PROXY_URL: str = _env("DODO_RPC_PROXY_URL")
DODO_RPC_SOURCES: str = _env("DODO_RPC_SOURCES", "ChainList")
DODO_RPC_EXTRA_HTTP_URLS: List[str] = _csv_env(
    "DODO_RPC_EXTRA_HTTP_URLS",
    ",".join(
        [
            DRPC_LB_HTTP_URL,
            "https://polygon.drpc.org",
            "https://tenderly.rpc.polygon.community",
            "https://polygon-bor-rpc.publicnode.com",
            "https://polygon.publicnode.com",
            "https://polygon-mainnet.gateway.tatum.io",
            "https://polygon-public.nodies.app",
            "https://1rpc.io/matic",
            "https://polygon.api.onfinality.io/public",
            GETBLOCK_POLYGON_RPC_HTTP,
            INFURA_HTTP,
        ]
    ),
)
BOT_ADDRESS: str = _env("BOT_ADDRESS")
EXECUTOR_WALLET: str = _env("EXECUTOR_WALLET")
OWNER_ADDRESS: str = _first_env("OWNER_ADDRESS", "EXECUTOR_WALLET", "BOT_ADDRESS")
FORK_UPSTREAM_RPC_URL: str = _env("FORK_UPSTREAM_RPC_URL")
FORK_RPC_URL: str = _env("FORK_RPC_URL", "http://127.0.0.1:8545")
FORK_SIM_RPC_URL: str = _env("FORK_SIM_RPC_URL", "http://127.0.0.1:8545")
REDIS_URL: str = _env("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_ENABLED: str = _env("REDIS_ENABLED", "true")
REDIS_KEY_PREFIX: str = _env("REDIS_KEY_PREFIX", "omega_v5")
REDIS_RPC_CACHE_TTL_SECONDS: int = int(_env("REDIS_RPC_CACHE_TTL_SECONDS", "60") or "60")
TRANSPORT_LANES_ENABLED: bool = (
    _env("TRANSPORT_LANES_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
)
RPC_HEALTH_TTL_SECONDS: int = int(_env("RPC_HEALTH_TTL_SECONDS", "15") or "15")
RPC_FAILED_TTL_SECONDS: int = int(_env("RPC_FAILED_TTL_SECONDS", "60") or "60")
RPC_ENDPOINT_TTL_SECONDS: int = int(_env("RPC_ENDPOINT_TTL_SECONDS", "60") or "60")
RPC_MAX_RPS_PER_LANE: int = int(_env("RPC_MAX_RPS_PER_LANE", "8") or "8")
RPC_EXACT_CALL_MAX_RPS: int = int(_env("RPC_EXACT_CALL_MAX_RPS", "3") or "3")
RPC_BROADCAST_MAX_RPS: int = int(_env("RPC_BROADCAST_MAX_RPS", "2") or "2")
REQUIRE_EXECUTABLE_ROUTE_STREAM: bool = (
    _env("REQUIRE_EXECUTABLE_ROUTE_STREAM", "false").lower() in {"1", "true", "yes", "on"}
)
EXECUTION_ROUTE_TARGET_MODE: str = _env("EXECUTION_ROUTE_TARGET_MODE", "capital_source_adapters").lower()
ALLOW_POOL_TARGETS_FOR_SCHEMA_CHECK: bool = (
    _env("ALLOW_POOL_TARGETS_FOR_SCHEMA_CHECK", "true").lower() in {"1", "true", "yes", "on"}
)
ENABLE_STABLE_SWAP_STRATEGIES: bool = (
    _env("ENABLE_STABLE_SWAP_STRATEGIES", "true").lower() in {"1", "true", "yes", "on"}
)
ENABLE_LIQUIDATION_PIPELINE: bool = (
    _env("ENABLE_LIQUIDATION_PIPELINE", "true").lower() in {"1", "true", "yes", "on"}
)
LIQUIDATION_SCAN_BLOCKS: int = int(_env("LIQUIDATION_SCAN_BLOCKS", "2500") or "2500")
LIQUIDATION_MAX_BORROWERS: int = int(_env("LIQUIDATION_MAX_BORROWERS", "200") or "200")
LIQUIDATION_MIN_NET_PROFIT_USD: Decimal = Decimal(_env("LIQUIDATION_MIN_NET_PROFIT_USD", "5") or "5")
AAVE_V3_POOL_ADDRESSES_PROVIDER: str = _env(
    "AAVE_V3_POOL_ADDRESSES_PROVIDER",
    "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
)
AAVE_V3_PROTOCOL_DATA_PROVIDER: str = _env("AAVE_V3_PROTOCOL_DATA_PROVIDER")
AAVE_BORROWER_SEED_ADDRESSES: List[str] = [
    item.strip()
    for item in _env("AAVE_BORROWER_SEED_ADDRESSES", "").split(",")
    if item.strip()
]
STABLE_SWAP_MIN_PROFIT_BPS: Decimal = Decimal(_env("STABLE_SWAP_MIN_PROFIT_BPS", "0") or "0")
STABLE_SWAP_MAX_PEG_DEVIATION_BPS: Decimal = Decimal(
    _env("STABLE_SWAP_MAX_PEG_DEVIATION_BPS", "250") or "250"
)
FLASH_BASE_ASSETS: List[str] = [
    item.strip()
    for item in _env("FLASH_BASE_ASSETS", "USDC,USDC.e,USDT,DAI,WPOL,WETH,WBTC").split(",")
    if item.strip()
]
PREFERRED_FLASH_SOURCE: str = _env("PREFERRED_FLASH_SOURCE", "BALANCER").upper()
ENABLE_DYNAMIC_FLASH_SIZING: bool = (
    _env("ENABLE_DYNAMIC_FLASH_SIZING", "true").lower() in {"1", "true", "yes", "on"}
)
MIN_FLASH_PRINCIPAL_USD: Decimal = Decimal(_env("MIN_FLASH_PRINCIPAL_USD", "5000") or "5000")
MAX_FLASH_PRINCIPAL_USD: Decimal = Decimal(_env("MAX_FLASH_PRINCIPAL_USD", "250000") or "250000")
MAX_ROUTE_TVL_FRACTION: Decimal = Decimal(_env("MAX_ROUTE_TVL_FRACTION", "0.50") or "0.50")
MAX_ROUTE_IMPACT: Decimal = Decimal(_env("MAX_ROUTE_IMPACT", "0.01") or "0.01")
FLASH_ROUTE_TVL_FRACTIONS: List[Decimal] = [
    Decimal(item.strip())
    for item in _env("FLASH_ROUTE_TVL_FRACTIONS", "0.15,0.25,0.50").split(",")
    if item.strip()
]
FLASH_SIZE_LADDER_BPS: List[Decimal] = [
    Decimal(item.strip())
    for item in _env("FLASH_SIZE_LADDER_BPS", "1000,1500").split(",")
    if item.strip()
]
ENABLE_FACTORY_POOL_DISCOVERY: bool = (
    _env("ENABLE_FACTORY_POOL_DISCOVERY", "true").lower() in {"1", "true", "yes", "on"}
)
DISCOVERY_MAX_TOKEN_PAIRS: int = int(_env("DISCOVERY_MAX_TOKEN_PAIRS", "160") or "160")
DISCOVERY_MAX_PROMOTED_POOLS: int = int(_env("DISCOVERY_MAX_PROMOTED_POOLS", "192") or "192")
RPC_REQUEST_TIMEOUT_SECONDS: int = int(_env("RPC_REQUEST_TIMEOUT_SECONDS", "6") or "6")
POOL_LOAD_SLEEP_SECONDS: Decimal = Decimal(_env("POOL_LOAD_SLEEP_SECONDS", "0.01") or "0.01")
POLYGON_GAS_STATION_URL: str = _env(
    "POLYGON_GAS_STATION_URL",
    "https://gasstation.polygon.technology/v2",
)
POLYGON_GAS_STATION_ENABLED: bool = (
    _env("POLYGON_GAS_STATION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
)
POLYGON_GAS_STATION_TIER: str = _env("POLYGON_GAS_STATION_TIER", "fast").lower()
POLYGON_GAS_STATION_TTL_SECONDS: int = int(_env("POLYGON_GAS_STATION_TTL_SECONDS", "6") or "6")
POLYGON_GAS_STATION_TIMEOUT_SECONDS: Decimal = Decimal(_env("POLYGON_GAS_STATION_TIMEOUT_SECONDS", "2.5") or "2.5")
# Micro-arb priority floor (was 25 gwei and dwarfed ~$0.001 gas economics)
POLYGON_MIN_PRIORITY_FEE_GWEI: Decimal = Decimal(_env("POLYGON_MIN_PRIORITY_FEE_GWEI", "5") or "5")
POLYGON_MAX_FEE_SAFETY_MULTIPLIER: Decimal = Decimal(_env("POLYGON_MAX_FEE_SAFETY_MULTIPLIER", "1.15") or "1.15")
QUICKSWAP_V3_SUBGRAPH_URL: str = _env(
    "QUICKSWAP_V3_SUBGRAPH_URL",
    "https://api.thegraph.com/subgraphs/name/sameepsi/quickswap-v3",
)
UNISWAP_V3_POLYGON_SUBGRAPH_URL: str = _env(
    "UNISWAP_V3_POLYGON_SUBGRAPH_URL",
    "https://api.thegraph.com/subgraphs/name/ianlapham/uniswap-v3-polygon",
)
ENABLE_SUBGRAPH_POOL_INTEL: bool = (
    _env("ENABLE_SUBGRAPH_POOL_INTEL", "true").lower() in {"1", "true", "yes", "on"}
)
SUBGRAPH_POOL_INTEL_LIMIT: int = int(_env("SUBGRAPH_POOL_INTEL_LIMIT", "50") or "50")
SUBGRAPH_TIMEOUT_SECONDS: Decimal = Decimal(_env("SUBGRAPH_TIMEOUT_SECONDS", "5") or "5")
ENABLE_DYNAMIC_POOL_REGISTRY: bool = (
    _env("ENABLE_DYNAMIC_POOL_REGISTRY", "true").lower() in {"1", "true", "yes", "on"}
)
DYNAMIC_POOLS_JSON_PATH: str = _env("DYNAMIC_POOLS_JSON_PATH", "omega_v5/data/pools_dynamic.json")
DYNAMIC_POOL_REGISTRY_MAX_POOLS: int = int(_env("DYNAMIC_POOL_REGISTRY_MAX_POOLS", "256") or "256")
ENABLE_CURVE_POOL_REGISTRY: bool = (
    _env("ENABLE_CURVE_POOL_REGISTRY", "true").lower() in {"1", "true", "yes", "on"}
)
CURVE_POOL_REGISTRY_API_BASE_URL: str = _env(
    "CURVE_POOL_REGISTRY_API_BASE_URL",
    "https://api.curve.fi/api",
)
CURVE_POOL_REGISTRY_FAMILIES: List[str] = [
    item.strip()
    for item in _env("CURVE_POOL_REGISTRY_FAMILIES", "main,factory,factory-crypto").split(",")
    if item.strip()
]
CURVE_POOL_REGISTRY_MAX_POOLS: int = int(_env("CURVE_POOL_REGISTRY_MAX_POOLS", "96") or "96")
CURVE_POOL_REGISTRY_MIN_USD_TVL: Decimal = Decimal(_env("CURVE_POOL_REGISTRY_MIN_USD_TVL", "1") or "1")
ENABLE_POLYGON_TOKEN_LIST_DISCOVERY: bool = (
    _env("ENABLE_POLYGON_TOKEN_LIST_DISCOVERY", "true").lower() in {"1", "true", "yes", "on"}
)
POLYGON_TOKEN_LIST_MAX_CANDIDATES: int = int(_env("POLYGON_TOKEN_LIST_MAX_CANDIDATES", "160") or "160")
POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS: int = int(_env("POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS", "86400") or "86400")
POLYGON_TOKEN_LIST_BASES: List[str] = [
    item.strip()
    for item in _env("POLYGON_TOKEN_LIST_BASES", "USDC.e,WETH,WPOL,WBTC,USDT,DAI,USDC").split(",")
    if item.strip()
]
ENABLE_INDEXER_STATE_READS: bool = (
    _env("ENABLE_INDEXER_STATE_READS", "false").lower() in {"1", "true", "yes", "on"}
)
INDEXER_SQLITE_PATH: str = _env("INDEXER_SQLITE_PATH", "cache/omega_indexer_state.sqlite")
INDEXER_STATE_MAX_AGE_BLOCKS: int = int(_env("INDEXER_STATE_MAX_AGE_BLOCKS", "4") or "4")

# ── Execution guards ──────────────────────────────────────────────────────────
EXEC_MODE: str    = _env("EXECUTION_MODE",             "simulation")
LIVE_FLAG: str    = _env("LIVE_TRADING",               "0")
CONFIRM_FLAG: str = _env("CONFIRM_MAINNET_EXECUTION",  "")
REQUIRED_CONFIRM  = "I_UNDERSTAND_POLYGON_MAINNET_RISK"

PRIVATE_KEY: str = _env("EXECUTOR_PRIVATE_KEY")
CANONICAL_ON_CHAIN_MUSCLE: str = _first_env(
    "CANONICAL_ON_CHAIN_MUSCLE",
    default="0x409ece3Fd71DFBd8f692B600f36A89301cb37346",
)
C1_PAYLOAD_TARGET: str = _first_env(
    "C1_PAYLOAD_TARGET",
    "C1_TARGET",
    "C1_ARB_EXECUTOR_ADDRESS",
    "EXECUTOR_CONTRACT_ADDR",
    default=CANONICAL_ON_CHAIN_MUSCLE,
)
C2_PAYLOAD_TARGET: str = _first_env(
    "C2_PAYLOAD_TARGET",
    "C2_TARGET",
    "C2_ARB_EXECUTOR_ADDRESS",
    "EXECUTOR_CONTRACT_ADDR",
    default=CANONICAL_ON_CHAIN_MUSCLE,
)
LIQUIDATION_EXECUTOR_ADDRESS: str = _first_env(
    "LIQUIDATION_EXECUTOR_ADDRESS",
)
ADAPTER_CONFIGURATION_TARGET: str = _first_env(
    "ADAPTER_CONFIGURATION_TARGET",
    "EXECUTOR_CONTRACT_ADDR",
    default=CANONICAL_ON_CHAIN_MUSCLE,
)
EXECUTOR_CONTRACT: str = _first_env(
    "EXECUTOR_CONTRACT_ADDR",
    "C1_PAYLOAD_TARGET",
    "C1_TARGET",
    "C1_ARB_EXECUTOR_ADDRESS",
    "HFT_DEFAULT_TARGET",
    default=CANONICAL_ON_CHAIN_MUSCLE,
)

# ── Dynamic sizing, stable micro-arb, and newer runtime compatibility knobs ────
V6_ENABLED: bool = _env("V6_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
V6_CAPITAL_ALLOCATION_ENABLED: bool = (
    _env("V6_CAPITAL_ALLOCATION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
)
ENABLE_DYNAMIC_SIZE_OPTIMIZER: bool = (
    _env("ENABLE_DYNAMIC_SIZE_OPTIMIZER", "true").lower() in {"1", "true", "yes", "on"}
)
ML_SIZE_PREDICTION_ENABLED: bool = (
    _env("ML_SIZE_PREDICTION_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
)
DYNAMIC_SIZE_OPT_BINS_USD: List[Decimal] = [
    Decimal(item.strip())
    for item in _env("DYNAMIC_SIZE_OPT_BINS_USD", "500,1000,2500,5000,7500,10000,15000,25000").split(",")
    if item.strip()
]
DYNAMIC_SIZE_MAX_SEARCH_STEPS: int = int(_env("DYNAMIC_SIZE_MAX_SEARCH_STEPS", "20") or "20")
DYNAMIC_SIZE_IMPACT_PENALTY_BPS: Decimal = Decimal(_env("DYNAMIC_SIZE_IMPACT_PENALTY_BPS", "25"))
# Stable micro-arb floors aligned with ~$0.001 Polygon gas (not $0.25 legacy)
STABLE_MIN_NET_PROFIT_USD: Decimal = Decimal(_env("STABLE_MIN_NET_PROFIT_USD", "0.01"))
STABLE_RISK_BUFFER_USD: Decimal = Decimal(_env("STABLE_RISK_BUFFER_USD", "0.005"))

TOKEN_CALIBRATION_CACHE_TTL_SECONDS: int = int(_env("TOKEN_CALIBRATION_CACHE_TTL_SECONDS", "300") or "300")
TOKEN_CALIBRATION_MAX_MULTICALL_BATCH: int = int(_env("TOKEN_CALIBRATION_MAX_MULTICALL_BATCH", "40") or "40")
OMEGA_ML_MODEL_DIR: str = _env("OMEGA_ML_MODEL_DIR", "models")
MIN_WALLET_GAS_BUFFER_POL: Decimal = Decimal(_env("MIN_WALLET_GAS_BUFFER_POL", "1"))
MEV_ENABLED: bool = _env("MEV_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
MEV_PUBLIC_FALLBACK_ENABLED: bool = (
    _env("MEV_PUBLIC_FALLBACK_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
)
ENABLE_APPRENTICE_METADATA_PROMOTIONS: bool = (
    _env("ENABLE_APPRENTICE_METADATA_PROMOTIONS", "true").lower() in {"1", "true", "yes", "on"}
)
APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE: int = int(
    _env("APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE", "25") or "25"
)

# Default protocol overhead fee, can be overridden by environment variables.
# This represents a small, fixed USD cost for any on-chain activity (e.g., contract deployment, one-time approvals).
PROTOCOL_OVERHEAD_USD: Decimal = Decimal(_env("PROTOCOL_OVERHEAD_USD", "0.001"))


if __name__ == "__main__":
    print(f"✅ Asset Matrix verified. Initialized {len(ASSET_MATRIX)} core tokens for Chain {CHAIN_ID} evaluation.")


def get_config_value(name: str, default=None):
    """Return a loaded config constant or environment value."""
    if name in globals():
        return globals()[name]
    return os.environ.get(name, default)
