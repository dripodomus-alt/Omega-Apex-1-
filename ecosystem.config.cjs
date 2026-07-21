/**
 * @file PM2 Ecosystem Configuration for Omega V5
 *
 * CRITICAL: This file contains placeholders for RPC provider API keys.
 * You MUST replace "<YOUR_KEY_HERE>" with your actual keys before deployment.
 * Do not commit your real keys to source control.
 */
const fs = require("node:fs");
const path = require("node:path");
const cwd = __dirname;

function loadLocalEnvIfPresent(envPath) {
  if (!fs.existsSync(envPath)) {
    return;
  }
  const fileEnv = {};
  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      continue;
    }
    const eq = trimmed.indexOf("=");
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (!key) {
      continue;
    }
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    fileEnv[key] = value;
  }
  for (const [key, value] of Object.entries(fileEnv)) {
    if (process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

loadLocalEnvIfPresent(path.join(cwd, ".env"));

const pythonBin = process.env.PYTHON_BIN || (process.platform === "win32" ? "python" : "python3");
const truthy = (value) => ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
const falsey = (value) => ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
const drpcRpc = process.env.DRPC_POLYGON_RPC_HTTP || "https://polygon.drpc.org";
const drpcWss = process.env.DRPC_POLYGON_RPC_WSS || "wss://polygon.drpc.org";
const drpcLbRpc = process.env.DRPC_LB_HTTP_URL || process.env.PRIMARY_READ_RPC_URL || `https://lb.drpc.live/polygon/${process.env.DRPC_API_KEY || "YOUR_DRPC_KEY_HERE"}`;
const drpcLbWss = process.env.DRPC_LB_WSS_URL || process.env.PRIMARY_WSS_URL || `wss://lb.drpc.live/polygon/${process.env.DRPC_API_KEY || "YOUR_DRPC_KEY_HERE"}`;
const telemetryRpc = process.env.TELEMETRY_RPC_URL || "https://polygon-bor-rpc.publicnode.com";
const telemetryWss = process.env.TELEMETRY_WSS_URL || "wss://polygon-bor-rpc.publicnode.com";
const primaryReadRpc = process.env.PRIMARY_READ_RPC_URL || process.env.POLYGON_RPC_URL || drpcLbRpc;
const primaryReadWss = process.env.PRIMARY_WSS_URL || process.env.POLYGON_WSS_URL || drpcLbWss;
const broadcastRpc = process.env.BROADCAST_RPC_URL || "https://polygon-mainnet.infura.io/v3/<YOUR_INFURA_KEY_HERE>";
const broadcastWss = process.env.BROADCAST_WSS_URL || "wss://polygon-mainnet.infura.io/ws/v3/<YOUR_INFURA_KEY_HERE>";
const getBlockRpc = process.env.GETBLOCK_POLYGON_RPC_HTTP || `https://go.getblock.io/${process.env.GETBLOCK_API_KEY || "YOUR_GETBLOCK_KEY_HERE"}`;
const getBlockWss = process.env.GETBLOCK_POLYGON_RPC_WSS || `wss://go.getblock.io/${process.env.GETBLOCK_API_KEY || "YOUR_GETBLOCK_KEY_HERE"}`;
const infuraRpc = process.env.INFURA_HTTP || `https://polygon-mainnet.infura.io/v3/${process.env.INFURA_API_KEY || "YOUR_INFURA_KEY_HERE"}`;
const infuraWss = process.env.INFURA_WSS || process.env.INFURA_POLYGON_RPC_WS || `wss://polygon-mainnet.infura.io/ws/v3/${process.env.INFURA_API_KEY || "YOUR_INFURA_KEY_HERE"}`;
const broadcastFallbackRpcUrls = [
  getBlockRpc,
  infuraRpc,
  drpcRpc,
  telemetryRpc,
  "https://polygon.publicnode.com",
  "https://1rpc.io/matic",
  "https://polygon.api.onfinality.io/public"
].join(",");
const broadcastFallbackWssUrls = [
  getBlockWss,
  infuraWss,
  drpcWss,
  telemetryWss
].join(",");
const apiHost = process.env.API_HOST || "127.0.0.1";
const apiPort = process.env.API_PORT || "8080";
const dodoProviderPort = process.env.DODO_RPC_PROVIDER_PORT || "3001";
const configuredDodoProviderUrl = process.env.DODO_RPC_PROVIDER_URL || "";
const dodoProviderUrl = configuredDodoProviderUrl && !configuredDodoProviderUrl.includes(":3000")
  ? configuredDodoProviderUrl
  : `http://127.0.0.1:${dodoProviderPort}`;
const liveExecutionRequested = truthy(process.env.LIVE_EXECUTION);
const shadowModeOff = process.env.SHADOW_MODE === undefined || falsey(process.env.SHADOW_MODE);
const executionEnabled = process.env.EXECUTION_DISABLED === undefined || falsey(process.env.EXECUTION_DISABLED);
const runtimeMode = (liveExecutionRequested && shadowModeOff && executionEnabled)
  ? "live"
  : (process.env.OMEGA_RUNTIME_MODE || process.env.EXECUTION_MODE || "dry_run");
const executionMode = runtimeMode;
const liveTrading = process.env.LIVE_TRADING || (runtimeMode === "live" ? "1" : "0");
const mainnetConfirm = process.env.CONFIRM_MAINNET_EXECUTION || "";
const canaryMode = process.env.OMEGA_ENGINE_CANARY_MODE || "true";
const engineNoScan = process.env.OMEGA_ENGINE_NO_SCAN || "true";
const rpcRotationHttpUrls = [
  drpcLbRpc,
  drpcRpc,
  "https://tenderly.rpc.polygon.community",
  telemetryRpc,
  "https://polygon.publicnode.com",
  "https://polygon-mainnet.gateway.tatum.io",
  "https://polygon-public.nodies.app",
  "https://1rpc.io/matic",
  "https://rpc-mainnet.matic.quiknode.pro",
  "https://polygon.api.onfinality.io/public",
  getBlockRpc,
  infuraRpc,
  broadcastRpc
].join(",");
const rpcRotationWssUrls = [
  drpcLbWss,
  drpcWss,
  telemetryWss,
  getBlockWss,
  infuraWss,
  broadcastWss
].join(",");
const dodoExtraHttpUrls = [
  drpcLbRpc,
  drpcRpc,
  "https://tenderly.rpc.polygon.community",
  telemetryRpc,
  "https://polygon.publicnode.com",
  "https://polygon-mainnet.gateway.tatum.io",
  "https://polygon-public.nodies.app",
  "https://1rpc.io/matic",
  "https://polygon.api.onfinality.io/public",
  getBlockRpc,
  infuraRpc
].join(",");
const rustEngineBin = process.env.OMEGA_RUST_ENGINE_BIN || path.join(cwd, "rust_engine", "target", "release", process.platform === "win32" ? "omega_rust_engine.exe" : "omega_rust_engine");
const redisUrl = process.env.REDIS_URL || "redis://127.0.0.1:6379/0";
const pythonRuntimeEnv = {
  PYTHONUTF8: "1",
  PYTHONIOENCODING: "utf-8"
};
const engineUsesSecretWrapper = process.platform !== "win32";
const sessionAllowedTargets = [
  "0x409ece3Fd71DFBd8f692B600f36A89301cb37346",
  "0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951"
].join(",");
const discoveryEnv = {
  ENABLE_FACTORY_POOL_DISCOVERY: process.env.ENABLE_FACTORY_POOL_DISCOVERY || "true",
  DISCOVERY_MAX_TOKEN_PAIRS: process.env.DISCOVERY_MAX_TOKEN_PAIRS || "320",
  DISCOVERY_MAX_PROMOTED_POOLS: process.env.DISCOVERY_MAX_PROMOTED_POOLS || "384",
  ENABLE_DYNAMIC_POOL_REGISTRY: process.env.ENABLE_DYNAMIC_POOL_REGISTRY || "true",
  DYNAMIC_POOL_REGISTRY_MAX_POOLS: process.env.DYNAMIC_POOL_REGISTRY_MAX_POOLS || "512",
  ENABLE_CURVE_POOL_REGISTRY: process.env.ENABLE_CURVE_POOL_REGISTRY || "true",
  CURVE_POOL_REGISTRY_MAX_POOLS: process.env.CURVE_POOL_REGISTRY_MAX_POOLS || "192",
  CURVE_POOL_REGISTRY_MIN_USD_TVL: process.env.CURVE_POOL_REGISTRY_MIN_USD_TVL || "1",
  ENABLE_SUBGRAPH_POOL_INTEL: process.env.ENABLE_SUBGRAPH_POOL_INTEL || "true",
  SUBGRAPH_POOL_INTEL_LIMIT: process.env.SUBGRAPH_POOL_INTEL_LIMIT || "100",
  ENABLE_POLYGON_TOKEN_LIST_DISCOVERY: process.env.ENABLE_POLYGON_TOKEN_LIST_DISCOVERY || "true",
  POLYGON_TOKEN_LIST_MAX_CANDIDATES: process.env.POLYGON_TOKEN_LIST_MAX_CANDIDATES || "320",
  POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS: process.env.POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS || "86400",
  POLYGON_TOKEN_LIST_BASES: process.env.POLYGON_TOKEN_LIST_BASES || "USDC.e,WETH,WPOL,WBTC,USDT,DAI,USDC,LINK,AAVE,CRV,BAL,UNI,SUSHI,QUICK"
};
const backgroundDiscoveryEnv = {
  ...discoveryEnv,
  BACKGROUND_DISCOVERY_UNBOUNDED: process.env.BACKGROUND_DISCOVERY_UNBOUNDED || "true",
  BACKGROUND_DISCOVERY_INTERVAL_SECONDS: process.env.BACKGROUND_DISCOVERY_INTERVAL_SECONDS || "900",
  BACKGROUND_DISCOVERY_TOP: process.env.BACKGROUND_DISCOVERY_TOP || "50",
  BACKGROUND_DISCOVERY_CALLDATA_PROBE: process.env.BACKGROUND_DISCOVERY_CALLDATA_PROBE || "10",
  DISCOVERY_PAIR_WINDOW_SIZE: process.env.BACKGROUND_DISCOVERY_PAIR_WINDOW_SIZE || "640",
  DISCOVERY_MAX_TOKEN_PAIRS: process.env.BACKGROUND_DISCOVERY_MAX_TOKEN_PAIRS || "0",
  DISCOVERY_MAX_PROMOTED_POOLS: process.env.BACKGROUND_DISCOVERY_MAX_PROMOTED_POOLS || "0",
  DYNAMIC_POOL_REGISTRY_MAX_POOLS: process.env.BACKGROUND_DYNAMIC_POOL_REGISTRY_MAX_POOLS || "0",
  CURVE_POOL_REGISTRY_MAX_POOLS: process.env.BACKGROUND_CURVE_POOL_REGISTRY_MAX_POOLS || "0",
  POLYGON_TOKEN_LIST_MAX_CANDIDATES: process.env.BACKGROUND_POLYGON_TOKEN_LIST_MAX_CANDIDATES || "0",
  SUBGRAPH_POOL_INTEL_LIMIT: process.env.BACKGROUND_SUBGRAPH_POOL_INTEL_LIMIT || "1000"
};
const routeStagingEnv = {
  ...backgroundDiscoveryEnv,
  ROUTE_STAGING_INTERVAL_SECONDS: process.env.ROUTE_STAGING_INTERVAL_SECONDS || "900",
  ROUTE_STAGING_PRINCIPAL_USD: process.env.ROUTE_STAGING_PRINCIPAL_USD || "10000",
  ROUTE_STAGING_HOPS: process.env.ROUTE_STAGING_HOPS || "2,3,4",
  ROUTE_STAGING_LIMIT: process.env.ROUTE_STAGING_LIMIT || "50",
  ROUTE_STAGING_MAX_QUOTE_OPTIONS_PER_PAIR: process.env.ROUTE_STAGING_MAX_QUOTE_OPTIONS_PER_PAIR || "0",
  ROUTE_STAGING_MAX_TOKEN_PATHS: process.env.ROUTE_STAGING_MAX_TOKEN_PATHS || "0",
  ROUTE_STAGING_MAX_PRE_RANKED: process.env.ROUTE_STAGING_MAX_PRE_RANKED || "0",
  ROUTE_STAGING_SLIPPAGE_BPS: process.env.ROUTE_STAGING_SLIPPAGE_BPS || "0"
};
const missingMetadataBackgroundEnv = {
  ...backgroundDiscoveryEnv,
  MISSING_METADATA_BACKGROUND_INTERVAL_SECONDS: process.env.MISSING_METADATA_BACKGROUND_INTERVAL_SECONDS || "300",
  MISSING_METADATA_BACKGROUND_ACTIVE_INTERVAL_SECONDS: process.env.MISSING_METADATA_BACKGROUND_ACTIVE_INTERVAL_SECONDS || "15",
  MISSING_METADATA_BACKGROUND_IDLE_INTERVAL_SECONDS: process.env.MISSING_METADATA_BACKGROUND_IDLE_INTERVAL_SECONDS || "300",
  MISSING_METADATA_BACKGROUND_LIMIT: process.env.MISSING_METADATA_BACKGROUND_LIMIT || "25",
  MISSING_METADATA_BACKGROUND_SEARCH_LIMIT: process.env.MISSING_METADATA_BACKGROUND_SEARCH_LIMIT || "5",
  MISSING_METADATA_RESEARCH_TIMEOUT_SECONDS: process.env.MISSING_METADATA_RESEARCH_TIMEOUT_SECONDS || "12",
  ENABLE_APPRENTICE_METADATA_PROMOTIONS: process.env.ENABLE_APPRENTICE_METADATA_PROMOTIONS || "true",
  APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE: process.env.APPRENTICE_METADATA_MAX_PROMOTIONS_PER_CYCLE || "50"
};

module.exports = {
  apps: [
    {
      name: "omega-redis",
      cwd,
      script: "scripts/pm2/run_redis.cjs",
      autorestart: true,
      max_restarts: 10,
      env: {
        REDIS_PORT: "6379",
        REDIS_BIND: "127.0.0.1"
      }
    },
    {
      name: "omega-anvil-fork",
      cwd,
      script: "scripts/pm2/run_anvil_fork.cjs",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        DRPC_LB_HTTP_URL: drpcLbRpc,
        DRPC_LB_WSS_URL: drpcLbWss,
        GETBLOCK_POLYGON_RPC_HTTP: getBlockRpc,
        GETBLOCK_POLYGON_RPC_WSS: getBlockWss,
        INFURA_HTTP: infuraRpc,
        INFURA_POLYGON_RPC_WS: infuraWss,
        INFURA_WSS: infuraWss,
        INFURA_WSS_URL: infuraWss,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        EXACT_CALL_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        FORK_UPSTREAM_RPC_URL: primaryReadRpc,
        FORK_RPC_URL: "http://127.0.0.1:8545",
        FORK_SIM_RPC_URL: "http://127.0.0.1:8545",
        ANVIL_HOST: process.env.ANVIL_HOST || "127.0.0.1"
      }
    },
    {
      name: "omega-dodo-rpc-provider",
      cwd,
      script: "scripts/pm2/run_dodo_rpc_provider.cjs",
      autorestart: true,
      max_restarts: 5,
      env: {
        PORT: dodoProviderPort,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls
      }
    },
    {
      name: "omega-api",
      cwd,
      script: pythonBin,
      args: `-m uvicorn omega_v5.api:app --host ${apiHost} --port ${apiPort}`,
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        API_HOST: apiHost,
        API_PORT: apiPort,
        API_PROXY_TARGET: `http://localhost:${apiPort}`,
        API_CORS_ORIGINS: process.env.API_CORS_ORIGINS || "http://127.0.0.1:8080,http://localhost:8080,http://127.0.0.1:5173,http://localhost:5173,https://ai.studio",
        API_FRONTEND_TOKEN_REQUIRED: "false",
        GETBLOCK_POLYGON_RPC_HTTP: getBlockRpc,
        GETBLOCK_POLYGON_RPC_WSS: getBlockWss,
        INFURA_HTTP: infuraRpc,
        INFURA_POLYGON_RPC_WS: infuraWss,
        INFURA_WSS: infuraWss,
        INFURA_WSS_URL: infuraWss,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        DRPC_LB_HTTP_URL: drpcLbRpc,
        DRPC_LB_WSS_URL: drpcLbWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        EXACT_CALL_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        BROADCAST_RPC_URL: broadcastRpc,
        BROADCAST_WSS_URL: broadcastWss,
        BROADCAST_RPC_FALLBACK_URLS: broadcastFallbackRpcUrls,
        BROADCAST_WSS_FALLBACK_URLS: broadcastFallbackWssUrls,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        TRANSPORT_LANES_ENABLED: "true",
        RPC_ENDPOINT_TTL_SECONDS: "60",
        RPC_HEALTH_TTL_SECONDS: "15",
        RPC_FAILED_TTL_SECONDS: "60",
        RPC_MAX_RPS_PER_LANE: "8",
        RPC_EXACT_CALL_MAX_RPS: "3",
        RPC_BROADCAST_MAX_RPS: "2",
        OMEGA_RUST_ENGINE_BIN: rustEngineBin,
        OMEGA_TRUTH_MAX_CANDIDATES: "5",
        ...discoveryEnv,
        ENABLE_INDEXER_STATE_READS: "false",
        INDEXER_SQLITE_PATH: "cache/omega_indexer_state.sqlite",
        INDEXER_STATE_MAX_AGE_BLOCKS: "4",
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        FORK_RPC_URL: "http://127.0.0.1:8545",
        FORK_SIM_RPC_URL: "http://127.0.0.1:8545",
        ANVIL_HOST: process.env.ANVIL_HOST || "127.0.0.1",
        OMEGA_RUNTIME_MODE: runtimeMode,
        EXECUTION_MODE: executionMode,
        LIVE_TRADING: liveTrading,
        CONFIRM_MAINNET_EXECUTION: mainnetConfirm,
        ENABLE_SMART_SESSIONS: "true",
        SESSION_SIGNER_ENABLED: "true",
        SESSION_SIGNER_MODE: "dry_run",
        WAAS_BROADCAST_ADAPTER_ENABLED: "false",
        WAAS_BROADCAST_ADAPTER_MODE: "dry_run",
        SMART_SESSIONS_MAX_VALUE_WEI: "0",
        SMART_SESSIONS_ALLOWED_TARGETS: sessionAllowedTargets,
        SMART_SESSIONS_ALLOWED_SELECTORS: "0x626482a3",
        SESSION_PROOF_SAMPLES: "5"
      }
    },
    {
      name: "omega-engine",
      cwd,
      ...(engineUsesSecretWrapper ? { interpreter: "bash" } : {}),
      script: engineUsesSecretWrapper ? "omega_v5/run_with_secrets.sh" : pythonBin,
      args: engineUsesSecretWrapper ? `${pythonBin} -m omega_v5.engine_daemon` : "-m omega_v5.engine_daemon",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        DRPC_LB_HTTP_URL: drpcLbRpc,
        DRPC_LB_WSS_URL: drpcLbWss,
        GETBLOCK_POLYGON_RPC_HTTP: getBlockRpc,
        GETBLOCK_POLYGON_RPC_WSS: getBlockWss,
        INFURA_HTTP: infuraRpc,
        INFURA_POLYGON_RPC_WS: infuraWss,
        INFURA_WSS: infuraWss,
        INFURA_WSS_URL: infuraWss,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        EXACT_CALL_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        BROADCAST_RPC_URL: broadcastRpc,
        BROADCAST_WSS_URL: broadcastWss,
        BROADCAST_RPC_FALLBACK_URLS: broadcastFallbackRpcUrls,
        BROADCAST_WSS_FALLBACK_URLS: broadcastFallbackWssUrls,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        TRANSPORT_LANES_ENABLED: "true",
        RPC_ENDPOINT_TTL_SECONDS: "60",
        RPC_HEALTH_TTL_SECONDS: "15",
        RPC_FAILED_TTL_SECONDS: "60",
        RPC_MAX_RPS_PER_LANE: "8",
        RPC_EXACT_CALL_MAX_RPS: "3",
        RPC_BROADCAST_MAX_RPS: "2",
        OMEGA_RUST_ENGINE_BIN: rustEngineBin,
        OMEGA_TRUTH_MAX_CANDIDATES: "5",
        ...discoveryEnv,
        ENABLE_INDEXER_STATE_READS: "false",
        INDEXER_SQLITE_PATH: "cache/omega_indexer_state.sqlite",
        INDEXER_STATE_MAX_AGE_BLOCKS: "4",
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        FORK_RPC_URL: "http://127.0.0.1:8545",
        FORK_SIM_RPC_URL: "http://127.0.0.1:8545",
        ANVIL_HOST: process.env.ANVIL_HOST || "127.0.0.1",
        OMEGA_RUNTIME_MODE: runtimeMode,
        EXECUTION_MODE: executionMode,
        LIVE_TRADING: liveTrading,
        CONFIRM_MAINNET_EXECUTION: mainnetConfirm,
        OMEGA_ENGINE_RPC_URL: primaryReadRpc,
        OMEGA_ENGINE_TICKS: "1",
        OMEGA_ENGINE_NO_SCAN: engineNoScan,
        OMEGA_ENGINE_PRINCIPAL_USD: "50000",
        OMEGA_ENGINE_PRINT_TOP_ROUTES: "50",
        OMEGA_ENGINE_EXECUTE_TOP: "5",
        OMEGA_ENGINE_CANARY_MODE: canaryMode,
        OMEGA_ENGINE_INTERVAL_SECONDS: "60",
        ENABLE_SMART_SESSIONS: "true",
        SESSION_SIGNER_ENABLED: "true",
        SESSION_SIGNER_MODE: "dry_run",
        WAAS_BROADCAST_ADAPTER_ENABLED: "false",
        WAAS_BROADCAST_ADAPTER_MODE: "dry_run",
        SMART_SESSIONS_MAX_VALUE_WEI: "0",
        SMART_SESSIONS_ALLOWED_TARGETS: sessionAllowedTargets,
        SMART_SESSIONS_ALLOWED_SELECTORS: "0x626482a3",
        SESSION_PROOF_SAMPLES: "5",
        MEV_ENABLED: process.env.MEV_ENABLED || "false",
        MEV_RELAY_URL: process.env.MEV_RELAY_URL || "https://relay.flashbots.net",
        OMEGA_ML_ALPHA_ENABLED: process.env.OMEGA_ML_ALPHA_ENABLED || "false",
      }
    },
    {
      name: "omega-telegram-bot",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.telegram_bot",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        // Inherits TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, etc.
        // from the main .env file loaded at the top.
        NODE_ENV: "production",
      }
    },
    {
      name: "omega-liquidation-watcher",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.liquidation_watcher",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        EXACT_CALL_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        BROADCAST_RPC_URL: broadcastRpc,
        BROADCAST_WSS_URL: broadcastWss,
        BROADCAST_RPC_FALLBACK_URLS: broadcastFallbackRpcUrls,
        BROADCAST_WSS_FALLBACK_URLS: broadcastFallbackWssUrls,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        TRANSPORT_LANES_ENABLED: "true",
        RPC_ENDPOINT_TTL_SECONDS: "60",
        RPC_HEALTH_TTL_SECONDS: "15",
        RPC_FAILED_TTL_SECONDS: "60",
        RPC_MAX_RPS_PER_LANE: "8",
        RPC_EXACT_CALL_MAX_RPS: "3",
        RPC_BROADCAST_MAX_RPS: "2",
        OMEGA_RUST_ENGINE_BIN: rustEngineBin,
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        FORK_RPC_URL: "http://127.0.0.1:8545",
        FORK_SIM_RPC_URL: "http://127.0.0.1:8545",
        OMEGA_RUNTIME_MODE: runtimeMode,
        EXECUTION_MODE: executionMode,
        LIVE_TRADING: liveTrading,
        CONFIRM_MAINNET_EXECUTION: mainnetConfirm,
        ENABLE_LIQUIDATION_PIPELINE: "true",
        OMEGA_LIQUIDATION_WATCH_INTERVAL_SECONDS: process.env.OMEGA_LIQUIDATION_WATCH_INTERVAL_SECONDS || "300",
        OMEGA_LIQUIDATION_MAX_PER_CYCLE: process.env.OMEGA_LIQUIDATION_MAX_PER_CYCLE || "2"
      }
    },
    {
      name: "omega-protocol-update-watcher",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.protocol_update_watcher",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        PROTOCOL_WATCH_INTERVAL_SECONDS: process.env.PROTOCOL_WATCH_INTERVAL_SECONDS || "1800",
        ...discoveryEnv
      }
    },
    {
      name: "omega-background-discovery",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.background_discovery",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        OMEGA_RUNTIME_MODE: runtimeMode,
        EXECUTION_MODE: executionMode,
        LIVE_TRADING: liveTrading,
        CONFIRM_MAINNET_EXECUTION: mainnetConfirm,
        ...backgroundDiscoveryEnv
      }
    },
    {
      name: "omega-route-execution-stager",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.route_execution_stager",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        OMEGA_RUNTIME_MODE: runtimeMode,
        EXECUTION_MODE: executionMode,
        LIVE_TRADING: liveTrading,
        CONFIRM_MAINNET_EXECUTION: mainnetConfirm,
        ...routeStagingEnv
      }
    },
    {
      name: "omega-missing-metadata-background",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.missing_metadata_background",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        POLYGON_RPC_URL: primaryReadRpc,
        RPC_URL: primaryReadRpc,
        POLYGON_WSS_URL: primaryReadWss,
        PRIMARY_READ_RPC_URL: primaryReadRpc,
        PRIMARY_WSS_URL: primaryReadWss,
        TELEMETRY_RPC_URL: telemetryRpc,
        RPC_ROTATION_HTTP_URLS: rpcRotationHttpUrls,
        RPC_ROTATION_WSS_URLS: rpcRotationWssUrls,
        DODO_RPC_PROVIDER_URL: dodoProviderUrl,
        DODO_RPC_PROXY_URL: primaryReadRpc,
        DODO_RPC_EXTRA_HTTP_URLS: dodoExtraHttpUrls,
        REDIS_URL: redisUrl,
        OMEGA_OUT_DIR: "out",
        OMEGA_CACHE_DIR: "cache",
        OMEGA_LOG_DIR: "logs",
        OMEGA_RUNTIME_MODE: runtimeMode,
        EXECUTION_MODE: executionMode,
        LIVE_TRADING: liveTrading,
        CONFIRM_MAINNET_EXECUTION: mainnetConfirm,
        ...missingMetadataBackgroundEnv
      }
    },
    {
      name: "omega-ml-data-collector",
      cwd,
      script: pythonBin,
      args: "-m omega_v5.ml_data_collector",
      autorestart: true,
      max_restarts: 10,
      env: {
        ...pythonRuntimeEnv,
        REDIS_URL: redisUrl,
        OMEGA_ML_MODEL_DIR: "models",
        OMEGA_OUT_DIR: "out",
        OMEGA_LOG_DIR: "logs",
      }
    }
  ].filter((app) => {
    if (process.env.OMEGA_DISABLE_EMBEDDED_REDIS === "true" && app.name === "omega-redis") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_ENGINE === "true" && app.name === "omega-engine") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_LIQUIDATION_WATCHER === "true" && app.name === "omega-liquidation-watcher") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_PROTOCOL_UPDATE_WATCHER === "true" && app.name === "omega-protocol-update-watcher") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_BACKGROUND_DISCOVERY === "true" && app.name === "omega-background-discovery") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_ROUTE_EXECUTION_STAGER === "true" && app.name === "omega-route-execution-stager") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_MISSING_METADATA_BACKGROUND === "true" && app.name === "omega-missing-metadata-background") {
      return false;
    }
    if (process.env.OMEGA_ML_ALPHA_ENABLED !== "true" && app.name === "omega-ml-data-collector") {
      return false;
    }
    if (process.env.ARBITRAGE_ENABLED === "false" && app.name === "omega-engine") {
        return false;
    }
    if (process.env.OMEGA_ML_ALPHA_ENABLED !== "true" && app.name === "omega-ml-data-collector") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_LIQUIDATION_WATCHER === "true" && app.name === "omega-liquidation-watcher") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_PROTOCOL_UPDATE_WATCHER === "true" && app.name === "omega-protocol-update-watcher") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_BACKGROUND_DISCOVERY === "true" && app.name === "omega-background-discovery") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_ROUTE_EXECUTION_STAGER === "true" && app.name === "omega-route-execution-stager") {
      return false;
    }
    if (process.env.OMEGA_DISABLE_MISSING_METADATA_BACKGROUND === "true" && app.name === "omega-missing-metadata-background") {
      return false;
    }
    return true;
  })
};
