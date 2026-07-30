import "dotenv/config";
import { ethers } from "ethers";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import {
  buildAlgebraExactInputSingleCalldata,
  buildBalancerSingleSwapCalldata,
  buildCurveRouterExchangeCalldata,
  buildStableSwapExchangeCalldata,
  buildV2SwapCalldata,
  buildV3ExactInputSingleCalldata,
  preSendRevalidate,
  quoteAlgebraExactInputSingle,
  quoteBalancerWeighted,
  quoteCurveGetDy,
  quoteStableSwapGetDy,
  quoteV2Cpmm,
  quoteV3ExactInputSingle,
  routeAdapterCapabilities,
  type InvariantKind,
  type PoolEdge,
  ROUTE_ADAPTER_TARGETS,
} from "../server/engine/routeAdapters.js";
import {
  enforceExecutionInvariants,
  InvariantViolationError,
  type QuotedRouteStep,
  type RouteCostsInAsset,
} from "../server/engine/executionInvariants.js";
import {
  flushLaneEventBatch,
  lockOpportunityForExecution,
  publishOpportunitySnapshot,
  recordLaneEvent,
  releaseOpportunityLock,
} from "../server/redisLedger.js";
import { DiscoveryCache } from "../server/engine/DiscoveryCache.js";
import { PoolStateCache } from "../server/engine/PoolStateCache.js";

const CHAIN_ID = 137n;
const API_BASE = process.env.APEX_API_BASE || "http://127.0.0.1:3000";
const DEFAULT_DISCOVERY_LOOKBACK_BLOCKS = 2_500;
const DEFAULT_DISCOVERY_LOG_CHUNK_BLOCKS = 1_000;
const DEFAULT_CURVE_MAX_POOLS = 25;
const DEFAULT_BALANCER_MAX_POOLS = 50;
const DEFAULT_V2_MAX_POOLS = 75;
const DEFAULT_V3_MAX_POOLS = 75;
const DEFAULT_ALGEBRA_MAX_POOLS = 75;
const DEFAULT_ROUTE_MAX_CYCLES = 1000;
const DEFAULT_DISCOVERY_CONCURRENCY = 16;
const DEFAULT_QUOTE_LANES = 32;
const DEFAULT_RPC_CALL_TIMEOUT_MS = 8_000;
const DEFAULT_DISCOVERY_POOL_SCAN_MULTIPLIER = 4;
const DEFAULT_RAW_SPREAD_TOP_N_PER_SIDE = 5;
const DEFAULT_ROUTE_MAX_STATE_AGE_BLOCKS = 128;
const DEFAULT_TOP_ROUTE_DISPLAY_LIMIT = 20;
const DEFAULT_C1_EXECUTABLE_LIMIT = 10;
const DEFAULT_OPTIMAL_SIZING_USD_LADDER = [25, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000];
const AAVE_V3_POOL = process.env.AAVE_V3_POOL_ADDRESS || "0x794a61358D6845594F94dc1DB02A252b5b4814aD";
const DEFAULT_USDC_SETTLEMENT_ADDRESSES = [
  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
  "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
];
const USDCE_SETTLEMENT_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
const FLASHLOAN_STRATEGY_BUY_LOW_SELL_HIGH_TO_USDCE = "BUY_LOW_SELL_HIGH_TO_USDCE";
const DEFAULT_FLASHLOAN_CAPITAL_BASKET = [
  "WBTC:0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
  "WPOL:0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
  "USDC.e:0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
];
const BALANCER_RECEIVE_FLASHLOAN_SELECTOR = ethers.id("receiveFlashLoan(address[],uint256[],uint256[],bytes)").slice(2, 10).toLowerCase();
const MINIMAL_O5_22_DISCOVERY_UNIVERSE = [
  "USDC.e:0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
  "USDC:0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
  "USDT:0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
  "DAI:0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
  "FRAX:0x45c32fA6DF82ead1e2EF74d17b76547EDdFaFF89",
  "MAI:0xa3Fa99A148fA48D14Ed51d610c367C61876997F1",
  "WETH:0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
  "WBTC:0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
  "WPOL:0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
  "stMATIC:0x3A58a54C066FdC0f2D55FC9C89F0415C92eBf3C4",
  "MaticX:0xfa68FB4628DFF1028CFEc22b4162FCcd0d45efb6",
  "wstETH:0x03b54A6e9a984069379fae1a4fC4dBAE93B3bCCD",
  "AAVE:0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
  "LINK:0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
  "CRV:0x172370d5Cd63279eFa6d502DAB29171933a610AF",
  "QUICK:0x831753DD7087CaC61aB5644b308642cc1c33Dc13",
  "SUSHI:0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",
  "BAL:0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3",
  "GHST:0x385Eeac5cB85A38A9a07A70c73e0a3271CfB54A7",
  "DPI:0x85955046DF4668e1DD369D2DE9f3AEB98DD2A369",
  "EURS:0xE111178A87A3BFf0c8d18DECBa5798827539Ae99",
  "EURA:0xE0B52e49357Fd4DAf2c15e02058DCE6BC0057db4",
];
const DEFAULT_C1_TARGET =
  process.env.C1_ARB_EXECUTOR_ADDRESS ||
  process.env.C1_TARGET ||
  process.env.ARB_CONTRACT_ADDRESS ||
  process.env.C1_CONTRACT_ADDRESS ||
  process.env.CONTRACT_ADDRESS ||
  process.env.EXECUTOR_ADDRESS ||
  "";
const ZERO_ADDRESS = ethers.ZeroAddress;

const AAVE_POOL_ABI = [
  "function getReservesList() view returns (address[])",
];
const ERC20_ABI = [
  "function decimals() view returns (uint8)",
  "function symbol() view returns (string)",
  "function balanceOf(address) view returns (uint256)",
];
const V2_FACTORY_ABI = [
  "event PairCreated(address indexed token0,address indexed token1,address pair,uint256)",
  "function getPair(address,address) view returns (address)",
];
const V2_PAIR_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function getReserves() view returns (uint112 reserve0,uint112 reserve1,uint32 blockTimestampLast)",
];
const V3_FACTORY_ABI = [
  "event PoolCreated(address indexed token0,address indexed token1,uint24 indexed fee,int24 tickSpacing,address pool)",
  "function getPool(address,address,uint24) view returns (address)",
];
const V3_POOL_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function fee() view returns (uint24)",
  "function tickSpacing() view returns (int24)",
  "function liquidity() view returns (uint128)",
  "function slot0() view returns (uint160 sqrtPriceX96,int24 tick,uint16 observationIndex,uint16 observationCardinality,uint16 observationCardinalityNext,uint8 feeProtocol,bool unlocked)",
];
const ALGEBRA_FACTORY_ABI = [
  "event Pool(address indexed token0,address indexed token1,address pool)",
  "function poolByPair(address,address) view returns (address)",
];
const ALGEBRA_POOL_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function tickSpacing() view returns (int24)",
  "function liquidity() view returns (uint128)",
  "function globalState() view returns (uint160 price,int24 tick,uint16 fee,uint16 timepointIndex,uint8 communityFeeToken0,uint8 communityFeeToken1,bool unlocked)",
];
const CURVE_ADDRESS_PROVIDER_ABI = [
  "function get_registry() view returns (address)",
];
const CURVE_REGISTRY_ABI = [
  "function pool_count() view returns (uint256)",
  "function pool_list(uint256 index) view returns (address)",
  "function get_coins(address pool) view returns (address[8])",
  "function get_balances(address pool) view returns (uint256[8])",
];
const BALANCER_VAULT_ABI = [
  "event PoolRegistered(bytes32 indexed poolId,address indexed poolAddress,uint8 specialization)",
  "function getPoolTokens(bytes32 poolId) view returns (address[] tokens,uint256[] balances,uint256 lastChangeBlock)",
];
const BALANCER_WEIGHTED_POOL_ABI = [
  "function getNormalizedWeights() view returns (uint256[])",
  "function getSwapFeePercentage() view returns (uint256)",
];
const VM_ABI = [
  "function globalNonce() view returns (uint256)",
];

type TokenMeta = {
  chainId: 137;
  address: string;
  symbol: string;
  decimals: number;
  priceUsd?: number;
  priceSource?: "STABLE_ANCHOR" | "MANUAL_PINNED" | "DEX_DERIVED";
  priceConfidence?: "HIGH" | "MEDIUM" | "LOW" | "REJECTED";
  flashloanEligible: boolean;
};

type FlashloanProviderId = "BALANCER_V2_VAULT" | "AAVE_V3_POOL";

type FlashloanLiquidity = {
  provider: FlashloanProviderId;
  sourceCode: number;
  providerAddress: string;
  asset: TokenMeta;
  liquidity: bigint;
  feeBps: bigint;
};

type Edge = PoolEdge & {
  edgeId: string;
  venueName: string;
  router: string;
  tokenInSymbol: string;
  tokenOutSymbol: string;
  tokenInPriceUsd?: number;
  tokenOutPriceUsd?: number;
  extra?: {
    v3Fee?: number;
    sqrtPriceX96?: string;
    tick?: number;
    tickSpacing?: number;
    liquidity?: string;
    curveIndexType?: "int128" | "uint256";
    balancerWeightIn?: bigint;
    balancerWeightOut?: bigint;
    balancerSwapFeeBps?: bigint;
  };
};

type RouteQuoteStep = {
  edge: Edge;
  amountIn: bigint;
  amountOut: bigint;
  minAmountOut: bigint;
  calldata: string;
};

type Candidate = {
  rank?: number;
  routeId: string;
  status: "EXECUTABLE_PROFIT_CANDIDATE" | "REJECTED_NO_PROFIT" | "REJECTED_ROUTE_INVALID";
  flashloanAsset: TokenMeta;
  flashloanLiquidity: FlashloanLiquidity;
  flashloanProviderExecutable: boolean;
  flashloanProviderReason: string;
  providerLiquidityRaw: bigint;
  routeRiskCapRaw: bigint;
  routeTvlRiskCapRaw: bigint;
  routePoolStateCapRaw: bigint;
  maxApplicableCapitalRaw: bigint;
  minFlashloanRaw: bigint;
  routeDynamicCapUsd: number;
  routePoolStateCapUsd?: number;
  routeMaxPoolReserveFractionBps: number;
  sizingRule: string;
  sizeSearchCandidates: number;
  capitalLimitedBy: "PROVIDER_LIQUIDITY" | "ROUTE_TVL_RISK_CAP" | "POOL_STATE_CAP";
  rawLeg1BuyPrice?: number;
  rawLeg2SellPrice?: number;
  rawSpreadDelta?: number;
  rawSpreadBps?: number;
  rawSpreadDirection?: "BUY_LT_SELL" | "BUY_GTE_SELL" | "NO_DIRECT_REVERSE_LEG";
  path: TokenMeta[];
  steps: RouteQuoteStep[];
  amountIn: bigint;
  amountOut: bigint;
  grossProfitRaw: bigint;
  grossProfitUsd?: number;
  gasCostUsd?: number;
  gasCostInAssetRaw: bigint;
  relayTipUsd: number;
  relayTipInAssetRaw: bigint;
  executorCostUsd: number;
  executorCostInAssetRaw: bigint;
  riskBufferUsd: number;
  riskBufferInAssetRaw: bigint;
  breakEvenGrossUsd?: number;
  grossProfitCoverageRatio?: number;
  gasAdjustedDeficitUsd?: number;
  actualProfitRaw: bigint;
  flashFeeRaw: bigint;
  flashFeeUsd?: number;
  netProfitUsd?: number;
  lowestPoolTvlUsd: number;
  rejectionReason: string;
  c1ExecutionEligible?: boolean;
  c1ExecutionSlot?: number;
};

type ReverseRouteMetadata = {
  available: boolean;
  error?: string;
  reverseFlashloanSource?: number;
  reverseFlashloanAsset?: string;
  reverseFlashloanAmount?: string;
  reverseContext?: any;
  reversePath?: string;
  reverseVenues?: string;
  sizingRule?: string;
};

type RawSpreadRoute = {
  route: Edge[];
  flashloanAsset: TokenMeta;
  token1Symbol: string;
  token1Address: string;
  buyPrice: number;
  sellPrice: number;
  rawSpreadDelta: number;
  rawSpreadBps: number;
  lowestPoolTvlUsd: number;
  rawCapitalCapUsd: number;
  rawEstimatedGrossUsdAtCap: number;
  rawEstimatedGrossBpsAtCap: number;
  buyVenue: string;
  sellVenue: string;
};

type RawSpreadBuild = {
  routes: RawSpreadRoute[];
  rejectedSameDestination: number;
  rejectedSamePoolVenue: number;
  matrixPairs: number;
  matrixPrunedByTopN: number;
  topNBuysPerPair: number;
  topNSellsPerPair: number;
  rejectedInvalidPrice: number;
  rejectedNonPositiveSpread: number;
  rejectedLowTvl: number;
  groupsWithoutSell: number;
};

type DiscoveryStats = {
  discoveryUniverseConfigured: number;
  discoveryUniverseLoaded: number;
  flashloanAssets: number;
  flashloanBalancerAssets: number;
  flashloanAaveAssets: number;
  tokens: number;
  discoveredEdges: number;
  discoveredPools: number;
  rejectedDuplicateEdge: number;
  rejectedMetadata: number;
  rejectedZeroLiquidity: number;
  rejectedUnsupportedInvariant: number;
  rejectedLogScan: number;
  rejectedPreSend: number;
  preSendRefreshes: number;
  preSendRejects: Record<string, number>;
  routeCyclesEnumerated: number;
  routeCyclesRejectedLowTvl: number;
  routeCyclesRejectedRepeatedPool: number;
  routeCyclesRejectedNonFlashloan: number;
  routeCyclesRejectedQuote: number;
  quoteRejects: Record<string, number>;
  truncated: boolean;
  sourceCounts: Record<string, number>;
};

type TrustedPriceSeed = {
  priceUsd: number;
  source: TokenMeta["priceSource"];
  confidence: TokenMeta["priceConfidence"];
};

let activePoolStateCache: PoolStateCache | undefined;

function rpcUrl() {
  return process.env.DISCOVERY_RPC_URL ||
    process.env.POLYGON_RPC_URL ||
    process.env.POLYGON_RPC ||
    process.env.DODO_RPC_PROVIDER_URL ||
    process.env.DODO_RPC_PROXY_URL ||
    process.env.RPC_URL ||
    "https://polygon-bor-rpc.publicnode.com";
}

function discoveryBackfillRpcUrl() {
  return process.env.DISCOVERY_BACKFILL_RPC_URL ||
    process.env.DISCOVERY_RPC_URL ||
    process.env.RPC_URL ||
    process.env.POLYGON_RPC_URL ||
    process.env.POLYGON_RPC ||
    process.env.BROADCAST_RPC_URL ||
    rpcUrl();
}

function wssUrl() {
  return process.env.BROADCAST_WSS_URL ||
    process.env.DISCOVERY_RPC_WSS ||
    process.env.POLYGON_WSS_URL ||
    process.env.WSS_URL ||
    "";
}

function maskRpcUrl(url: string) {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname ? "/..." : ""}`;
  } catch {
    return url ? "configured" : "missing";
  }
}

function useWssDiscovery() {
  return process.env.ENABLE_WSS_DISCOVERY === "true";
}

let backfillProvider: ethers.JsonRpcProvider | undefined;

function getBackfillProvider() {
  if (!backfillProvider) {
    backfillProvider = new ethers.JsonRpcProvider(discoveryBackfillRpcUrl(), Number(CHAIN_ID), { staticNetwork: true });
  }
  return backfillProvider;
}

function createDiscoveryProvider(): ethers.JsonRpcProvider {
  return new ethers.JsonRpcProvider(discoveryBackfillRpcUrl(), Number(CHAIN_ID), { staticNetwork: true });
}

function discoveryTransportLabel() {
  return useWssDiscovery() ? "WSS_ENABLED_HTTPS_STATE" : "HTTPS_STATE";
}

function discoveryTransportEndpoint() {
  return useWssDiscovery() && wssUrl() ? `${maskRpcUrl(wssUrl())}+${maskRpcUrl(discoveryBackfillRpcUrl())}` : maskRpcUrl(discoveryBackfillRpcUrl());
}

async function closeDiscoveryProvider(provider: ethers.JsonRpcProvider) {
  const maybeProvider = provider as any;
  await maybeProvider.destroy?.();
  await backfillProvider?.destroy?.();
  backfillProvider = undefined;
}

function intEnv(name: string, fallback: number) {
  const parsed = Number(process.env[name]);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function optionalIntEnv(name: string) {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function numberEnv(name: string, fallback: number) {
  const parsed = Number(process.env[name]);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function positiveNumberListEnv(name: string, fallback: number[]) {
  const raw = process.env[name];
  if (!raw || raw.trim() === "") return fallback;
  const parsed = raw
    .split(",")
    .map((item) => Number(item.trim().replace(/_/g, "")))
    .filter((value) => Number.isFinite(value) && value > 0);
  return parsed.length > 0 ? parsed : fallback;
}

function nativeTokenUsd() {
  return numberEnv("NATIVE_TOKEN_USD", numberEnv("TRUSTED_WPOL_USD", 0.4));
}

function positiveNumberEnv(name: string, fallback: number) {
  const parsed = Number(process.env[name]);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function discoveryPoolScanMultiplier() {
  return Math.max(1, intEnv("LIVE_DISCOVERY_POOL_SCAN_MULTIPLIER", DEFAULT_DISCOVERY_POOL_SCAN_MULTIPLIER));
}

function discoveryCandidatePoolLimit(maxPools: number) {
  if (!Number.isFinite(maxPools) || maxPools <= 0) return 0;
  return Math.max(maxPools, Math.floor(maxPools * discoveryPoolScanMultiplier()));
}

function rawSpreadTopNBuysPerPair() {
  return Math.max(0, intEnv("RAW_SPREAD_TOP_N_BUYS_PER_PAIR", DEFAULT_RAW_SPREAD_TOP_N_PER_SIDE));
}

function rawSpreadTopNSellsPerPair() {
  return Math.max(0, intEnv("RAW_SPREAD_TOP_N_SELLS_PER_PAIR", DEFAULT_RAW_SPREAD_TOP_N_PER_SIDE));
}

function optimalSizingUsdLadder() {
  return positiveNumberListEnv("OPTIMAL_SIZING_USD_LADDER", DEFAULT_OPTIMAL_SIZING_USD_LADDER);
}

function uniqueSortedAmounts(amounts: bigint[]) {
  return Array.from(new Set(amounts.map((amount) => amount.toString())))
    .map((amount) => BigInt(amount))
    .sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
}

function buildAdaptiveSizingAmounts(
  asset: TokenMeta,
  minAmountRaw: bigint,
  maxAmountRaw: bigint,
  linearSteps: number,
) {
  if (!asset.priceUsd || asset.priceUsd <= 0 || maxAmountRaw <= 0n) return [];
  const amounts: bigint[] = [];
  const include = (amount: bigint) => {
    if (amount <= 0n) return;
    if (minAmountRaw > 0n && amount < minAmountRaw) return;
    if (amount > maxAmountRaw) return;
    amounts.push(amount);
  };

  include(minAmountRaw > 0n ? minAmountRaw : maxAmountRaw / BigInt(Math.max(1, linearSteps)));
  for (const usd of optimalSizingUsdLadder()) {
    include(floatToRaw(usd / asset.priceUsd, asset.decimals));
  }

  const steps = Math.max(1, linearSteps);
  for (let i = 1; i <= steps; i++) {
    const amount = minAmountRaw > 0n
      ? minAmountRaw + ((maxAmountRaw - minAmountRaw) * BigInt(i - 1)) / BigInt(Math.max(1, steps - 1))
      : (maxAmountRaw * BigInt(i)) / BigInt(steps);
    include(amount);
  }
  include(maxAmountRaw);

  return uniqueSortedAmounts(amounts);
}

function boolEnv(name: string, fallback = false) {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  return raw === "true" || raw === "1";
}

function discoveryUniverseProfile() {
  return process.env.DISCOVERY_UNIVERSE_PROFILE || "MINIMAL_O5_22";
}

function discoveryUniverseEntries() {
  const raw = process.env.DISCOVERY_UNIVERSE_TOKENS || MINIMAL_O5_22_DISCOVERY_UNIVERSE.join(",");
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function parseUniverseAddress(entry: string) {
  const parts = entry.split(":");
  const rawAddress = parts.length > 1 ? parts[parts.length - 1] : entry;
  return normalize(rawAddress.trim());
}

function configuredDiscoveryUniverseTokenAddresses() {
  const addresses: string[] = [];
  const seen = new Set<string>();
  for (const entry of discoveryUniverseEntries()) {
    try {
      const address = parseUniverseAddress(entry);
      const key = address.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      addresses.push(address);
    } catch {
      // Invalid operator-provided universe entries are ignored fail-closed.
    }
  }
  return addresses;
}

function normalize(address: string) {
  if (/^0x[a-fA-F0-9]{40}$/.test(address)) {
    return ethers.getAddress(address.toLowerCase());
  }
  return ethers.getAddress(address);
}

function sameAddress(left: string, right: string) {
  return normalize(left).toLowerCase() === normalize(right).toLowerCase();
}

function normalizedAddressSet(raw: string | undefined, fallback: string[]) {
  const values = (raw || fallback.join(","))
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const result = new Set<string>();
  for (const value of values) {
    try {
      result.add(normalize(value).toLowerCase());
    } catch {
      // Invalid operator-provided settlement addresses are ignored fail-closed.
    }
  }
  return result;
}

function settlementSymbols() {
  return new Set((process.env.SETTLEMENT_ASSET_SYMBOLS || "USDC,USDC.E")
    .split(",")
    .map((symbol) => symbol.trim().toUpperCase())
    .filter(Boolean));
}

function settlementAddressSet() {
  return normalizedAddressSet(process.env.SETTLEMENT_ASSET_ADDRESSES, DEFAULT_USDC_SETTLEMENT_ADDRESSES);
}

function usdceSettlementAddress() {
  return normalize(process.env.USDCE_SETTLEMENT_ASSET_ADDRESS || USDCE_SETTLEMENT_ADDRESS);
}

function flashloanStrategyMode() {
  return (process.env.FLASHLOAN_STRATEGY_MODE || FLASHLOAN_STRATEGY_BUY_LOW_SELL_HIGH_TO_USDCE).trim().toUpperCase();
}

function useBuyLowSellHighToUsdceStrategy() {
  return flashloanStrategyMode() === FLASHLOAN_STRATEGY_BUY_LOW_SELL_HIGH_TO_USDCE;
}

function flashloanCapitalBasketEntries() {
  return (process.env.FLASHLOAN_CAPITAL_BASKET || DEFAULT_FLASHLOAN_CAPITAL_BASKET.join(","))
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function flashloanCapitalBasketAddressSet() {
  const result = new Set<string>();
  for (const entry of flashloanCapitalBasketEntries()) {
    try {
      result.add(parseUniverseAddress(entry).toLowerCase());
    } catch {
      // Invalid operator-provided basket entries are ignored fail-closed.
    }
  }
  return result;
}

function requireUsdcSettlement() {
  return boolEnv("REQUIRE_USDC_SETTLEMENT", true);
}

function isUsdcSettlementAsset(token: TokenMeta) {
  const addressAllowed = settlementAddressSet().has(token.address.toLowerCase());
  const symbolAllowed = settlementSymbols().has(token.symbol.toUpperCase());
  return addressAllowed || symbolAllowed;
}

function isUsdceSettlementAsset(token: TokenMeta) {
  return sameAddress(token.address, usdceSettlementAddress());
}

function isFlashloanCapitalBasketAsset(token: TokenMeta) {
  return flashloanCapitalBasketAddressSet().has(token.address.toLowerCase());
}

function formatAssetList(assets: TokenMeta[]) {
  return assets.map((asset) => `${asset.symbol}:${asset.address}`).join(",");
}

function buildStrategyFlashloanPolicy(flashloanAssets: TokenMeta[]) {
  const settlementAssets = settlementFlashloanAssets(flashloanAssets);
  if (!useBuyLowSellHighToUsdceStrategy()) {
    return {
      mode: flashloanStrategyMode(),
      settlementAssets,
      basketAssets: settlementAssets,
      atomicCandidateSeedAssets: settlementAssets,
      deferredFlashloanAssets: [] as TokenMeta[],
      finalSettlementAsset: "FLASHLOAN_ASSET",
      deferredReason: "NONE",
    };
  }

  const basketAssets = flashloanAssets.filter(isFlashloanCapitalBasketAsset);
  const atomicCandidateSeedAssets = basketAssets.filter(isUsdceSettlementAsset);
  const deferredFlashloanAssets = basketAssets.filter((asset) => !isUsdceSettlementAsset(asset));
  return {
    mode: flashloanStrategyMode(),
    settlementAssets,
    basketAssets,
    atomicCandidateSeedAssets,
    deferredFlashloanAssets,
    finalSettlementAsset: usdceSettlementAddress(),
    deferredReason: "REQUIRES_ATOMIC_REPAYMENT_CONVERSION_BEFORE_USDCE_SURPLUS_SETTLEMENT",
  };
}

function settlementFlashloanAssets(flashloanAssets: TokenMeta[]) {
  return requireUsdcSettlement()
    ? flashloanAssets.filter(isUsdcSettlementAsset)
    : flashloanAssets;
}

type BalancerC1Capability = {
  operatorEnabled: boolean;
  executable: boolean;
  reason: string;
  callbackSelector: string;
};

function balancerC1OperatorEnabled() {
  return process.env.C1_BALANCER_FLASHLOAN_SUPPORTED === "true" &&
    process.env.LIVE_MARKET_ALLOW_BALANCER_C1 === "true";
}

function balancerC1FlashloanSupported() {
  return balancerC1OperatorEnabled();
}

async function verifyBalancerC1Capability(provider: ethers.Provider, targetContract: string): Promise<BalancerC1Capability> {
  const operatorEnabled = balancerC1OperatorEnabled();
  if (!operatorEnabled) {
    return {
      operatorEnabled,
      executable: false,
      reason: "OPERATOR_DISABLED",
      callbackSelector: BALANCER_RECEIVE_FLASHLOAN_SELECTOR,
    };
  }
  if (!boolEnv("VERIFY_BALANCER_C1_CALLBACK", true)) {
    return {
      operatorEnabled,
      executable: true,
      reason: "CALLBACK_VERIFICATION_DISABLED_BY_OPERATOR",
      callbackSelector: BALANCER_RECEIVE_FLASHLOAN_SELECTOR,
    };
  }
  const code = await provider.getCode(targetContract).catch(() => "0x");
  const hasCode = code !== "0x";
  const selectorPresent = code.toLowerCase().includes(BALANCER_RECEIVE_FLASHLOAN_SELECTOR);
  return {
    operatorEnabled,
    executable: hasCode && selectorPresent,
    reason: !hasCode
      ? "TARGET_CODE_MISSING"
      : selectorPresent
        ? "CALLBACK_SELECTOR_PRESENT"
        : "CALLBACK_SELECTOR_MISSING",
    callbackSelector: BALANCER_RECEIVE_FLASHLOAN_SELECTOR,
  };
}

function executableFlashloanOptions(options: FlashloanLiquidity[], balancerCapability?: BalancerC1Capability) {
  if (balancerCapability?.executable ?? balancerC1FlashloanSupported()) return options;
  return options.filter((item) => item.provider === "AAVE_V3_POOL");
}

function defaultFlashloanProvider() {
  return (process.env.FLASHLOAN_DEFAULT_PROVIDER || "BALANCER_V2_VAULT").trim().toUpperCase();
}

function rankFlashloanCapitalOptions(options: FlashloanLiquidity[]) {
  const preferred = defaultFlashloanProvider();
  return [...options].sort((a, b) => {
    const aPreferred = a.provider === preferred ? 0 : 1;
    const bPreferred = b.provider === preferred ? 0 : 1;
    if (aPreferred !== bPreferred) return aPreferred - bPreferred;
    if (a.provider !== b.provider) return a.provider.localeCompare(b.provider);
    if (a.liquidity !== b.liquidity) return a.liquidity > b.liquidity ? -1 : 1;
    return Number(a.feeBps - b.feeBps);
  });
}

function flashloanProviderExecutable(option: FlashloanLiquidity, balancerCapability?: BalancerC1Capability) {
  if (option.provider !== "BALANCER_V2_VAULT") return true;
  return Boolean(balancerCapability?.executable ?? balancerC1FlashloanSupported());
}

function flashloanProviderReason(option: FlashloanLiquidity, balancerCapability?: BalancerC1Capability) {
  if (option.provider !== "BALANCER_V2_VAULT") return "AAVE_C1_SUPPORTED";
  return balancerCapability?.executable
    ? "BALANCER_C1_CALLBACK_VERIFIED"
    : `BALANCER_C1_NOT_EXECUTABLE:${balancerCapability?.reason || "OPERATOR_DISABLED"}`;
}

function hasRankableMinFlashloanCapital(asset: TokenMeta, flashloanBook: Map<string, FlashloanLiquidity[]>) {
  if (!asset.priceUsd || asset.priceUsd <= 0) return false;
  const minAmountRaw = floatToRaw(positiveNumberEnv("MIN_FLASHLOAN_USD", 0) / asset.priceUsd, asset.decimals);
  if (minAmountRaw <= 0n) return true;
  return rankFlashloanCapitalOptions(flashloanBook.get(asset.address.toLowerCase()) || [])
    .some((item) => item.liquidity >= minAmountRaw);
}

function hasExecutableMinFlashloanCapital(asset: TokenMeta, flashloanBook: Map<string, FlashloanLiquidity[]>, balancerCapability?: BalancerC1Capability) {
  if (!asset.priceUsd || asset.priceUsd <= 0) return false;
  const minAmountRaw = floatToRaw(positiveNumberEnv("MIN_FLASHLOAN_USD", 0) / asset.priceUsd, asset.decimals);
  if (minAmountRaw <= 0n) return true;
  return executableFlashloanOptions(flashloanBook.get(asset.address.toLowerCase()) || [], balancerCapability)
    .some((item) => item.liquidity >= minAmountRaw);
}

function hasAnyExecutableFlashloanCapital(asset: TokenMeta, flashloanBook: Map<string, FlashloanLiquidity[]>, balancerCapability?: BalancerC1Capability) {
  return executableFlashloanOptions(flashloanBook.get(asset.address.toLowerCase()) || [], balancerCapability)
    .some((item) => item.liquidity > 0n);
}

function allowDiagnosticRankingBelowMinFlashloan() {
  return boolEnv("ALLOW_DIAGNOSTIC_RANKING_BELOW_MIN_FLASHLOAN", true);
}

function allowRouteCapBelowMinFlashloan() {
  return boolEnv("ALLOW_ROUTE_CAP_BELOW_MIN_FLASHLOAN", false);
}

function formatCostFlag(name: string, value: number) {
  return `${name}=${Number.isFinite(value) ? value : "UNRESOLVED"}`;
}

function rawToFloat(raw: bigint, decimals: number) {
  return Number(ethers.formatUnits(raw, decimals));
}

function floatToRaw(value: number, decimals: number) {
  if (!Number.isFinite(value) || value <= 0) return 0n;
  const scale = 10 ** Math.min(decimals, 12);
  const truncated = Math.floor(value * scale) / scale;
  return ethers.parseUnits(truncated.toFixed(Math.min(decimals, 12)), decimals);
}

function bpsMin(amount: bigint, slippageBps: bigint) {
  if (amount <= 0n) return 0n;
  const keepBps = 10000n - slippageBps;
  return amount * keepBps / 10000n;
}

async function runWithConcurrency<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
) {
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      await worker(items[index]);
    }
  });
  await Promise.all(workers);
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label}_TIMEOUT_${timeoutMs}MS`)), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function usdStableSeed(symbol: string) {
  const upper = symbol.toUpperCase();
  if (upper === "USDC" || upper === "USDC.E" || upper === "USDT" || upper === "USDT0" || upper === "DAI" || upper === "FRAX" || upper === "MAI" || upper === "MIMATIC") return 1;
  return undefined;
}

const TRUSTED_PRICE_ANCHORS_USD: Record<string, TrustedPriceSeed> = {
  "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": { priceUsd: 1, source: "STABLE_ANCHOR", confidence: "HIGH" },
  "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": { priceUsd: 1, source: "STABLE_ANCHOR", confidence: "HIGH" },
  "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": { priceUsd: 1, source: "STABLE_ANCHOR", confidence: "HIGH" },
  "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": { priceUsd: 1, source: "STABLE_ANCHOR", confidence: "HIGH" },
  "0x45c32fa6df82ead1e2ef74d17b76547eddfaff89": { priceUsd: 1, source: "STABLE_ANCHOR", confidence: "HIGH" },
  "0xa3fa99a148fa48d14ed51d610c367c61876997f1": { priceUsd: 1, source: "STABLE_ANCHOR", confidence: "HIGH" },
  "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": { priceUsd: numberEnv("TRUSTED_WETH_USD", 3500), source: "MANUAL_PINNED", confidence: "MEDIUM" },
  "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6": { priceUsd: numberEnv("TRUSTED_WBTC_USD", 65000), source: "MANUAL_PINNED", confidence: "MEDIUM" },
  "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": { priceUsd: numberEnv("TRUSTED_WPOL_USD", numberEnv("NATIVE_TOKEN_USD", 0.4)), source: "MANUAL_PINNED", confidence: "MEDIUM" },
};

function trustedPriceSeed(address: string, symbol: string): TrustedPriceSeed | undefined {
  const anchored = TRUSTED_PRICE_ANCHORS_USD[address.toLowerCase()];
  if (anchored) return anchored;
  const stable = usdStableSeed(symbol);
  if (stable !== undefined) return { priceUsd: stable, source: "STABLE_ANCHOR", confidence: "HIGH" };
  const upper = symbol.toUpperCase();
  const envPrice = process.env[`TRUSTED_${upper.replace(/[^A-Z0-9]/g, "_")}_USD`];
  if (envPrice !== undefined) {
    const parsed = Number(envPrice);
    if (Number.isFinite(parsed) && parsed > 0) return { priceUsd: parsed, source: "MANUAL_PINNED", confidence: "MEDIUM" };
  }
  return undefined;
}

function isTrustedPricePinned(token: TokenMeta) {
  return token.priceSource === "STABLE_ANCHOR" || token.priceSource === "MANUAL_PINNED";
}

function saneDerivedPrice(symbol: string, priceUsd: number) {
  if (!Number.isFinite(priceUsd) || priceUsd <= 0) return false;
  const upper = symbol.toUpperCase();
  if (upper === "USDC" || upper === "USDC.E" || upper === "USDT" || upper === "USDT0" || upper === "DAI" || upper === "FRAX" || upper === "MAI" || upper === "MIMATIC") return priceUsd >= 0.985 && priceUsd <= 1.015;
  if (upper === "WETH" || upper === "ETH") return priceUsd >= 500 && priceUsd <= 10000;
  if (upper === "WBTC" || upper === "BTC") return priceUsd >= 5000 && priceUsd <= 200000;
  if (upper === "WPOL" || upper === "WMATIC" || upper === "MATIC" || upper === "POL") return priceUsd >= 0.01 && priceUsd <= 5;
  return priceUsd >= 0.000001 && priceUsd <= 1_000_000;
}

const BPS_DENOMINATOR = 10_000n;

const Q96 = 2n ** 96n;

function v3ActiveReserves(liquidityRaw: bigint, sqrtPriceX96Raw: bigint) {
  if (liquidityRaw <= 0n || sqrtPriceX96Raw <= 0n) return { reserve0: 0n, reserve1: 0n };
  return {
    reserve0: liquidityRaw * Q96 / sqrtPriceX96Raw,
    reserve1: liquidityRaw * sqrtPriceX96Raw / Q96,
  };
}

function tupleValue(result: any, key: string, index: number) {
  return result?.[key] ?? result?.[index];
}

function superStateHash(latestBlock: number, edges: Edge[]) {
  const payload = edges
    .map((edge) => [
      edge.dexId,
      edge.poolAddress,
      edge.tokenIn,
      edge.tokenOut,
      edge.invariant,
      edge.feeBps,
      edge.reserveIn.toString(),
      edge.reserveOut.toString(),
      edge.stateBlock,
    ].join(":"))
    .sort()
    .join("|");
  return ethers.id(`${latestBlock}|${payload}`);
}

function quoteUsd(raw: bigint, token: TokenMeta) {
  if (!token.priceUsd) return undefined;
  return rawToFloat(raw, token.decimals) * token.priceUsd;
}

function routeLowestTvlUsd(route: Edge[]) {
  return Math.min(...route.map((edge) => edge.tvlUsd).filter((value) => Number.isFinite(value) && value > 0));
}

function maxPoolsForDexId(dexId: string) {
  if (dexId.includes("QUICKSWAPV2") || dexId.includes("SUSHISWAPV2") || dexId.endsWith("_V2") || dexId.includes("V2")) {
    return intEnv("LIVE_V2_MAX_POOLS", DEFAULT_V2_MAX_POOLS);
  }
  if (dexId.includes("UNISWAPV3") || dexId.endsWith("_V3") || dexId.includes("V3")) {
    return intEnv("LIVE_V3_MAX_POOLS", DEFAULT_V3_MAX_POOLS);
  }
  if (dexId.includes("ALGEBRA")) {
    return intEnv("LIVE_ALGEBRA_MAX_POOLS", DEFAULT_ALGEBRA_MAX_POOLS);
  }
  if (dexId.includes("BALANCER")) {
    return intEnv("LIVE_BALANCER_MAX_POOLS", DEFAULT_BALANCER_MAX_POOLS);
  }
  if (dexId.includes("CURVE")) {
    return intEnv("LIVE_CURVE_MAX_POOLS", DEFAULT_CURVE_MAX_POOLS);
  }
  return intEnv("LIVE_V2_MAX_POOLS", DEFAULT_V2_MAX_POOLS);
}

function edgePoolSelectionKey(edge: Edge) {
  return `${edge.dexId}:${edge.poolId || edge.poolAddress}`.toLowerCase();
}

function edgeLiquidityVenueKey(edge: Edge) {
  return `${CHAIN_ID.toString()}:${edge.poolAddress.toLowerCase()}`;
}

function selectDeepLiquidityEdges(edges: Edge[]) {
  if (process.env.LIVE_DISCOVERY_LIQUIDITY_FIRST === "false") {
    return { selected: edges, seenPools: new Set(edges.map(edgePoolSelectionKey)), selectedPools: new Set(edges.map(edgePoolSelectionKey)) };
  }
  const poolRows = new Map<string, { dexId: string; tvlUsd: number; edges: Edge[] }>();
  for (const edge of edges) {
    const key = edgePoolSelectionKey(edge);
    const existing = poolRows.get(key);
    if (!existing) {
      poolRows.set(key, { dexId: edge.dexId, tvlUsd: Number.isFinite(edge.tvlUsd) ? edge.tvlUsd : 0, edges: [edge] });
    } else {
      existing.tvlUsd = Math.max(existing.tvlUsd, Number.isFinite(edge.tvlUsd) ? edge.tvlUsd : 0);
      existing.edges.push(edge);
    }
  }

  const byDex = new Map<string, Array<{ key: string; tvlUsd: number; edges: Edge[] }>>();
  for (const [key, row] of poolRows) {
    const list = byDex.get(row.dexId) || [];
    list.push({ key, tvlUsd: row.tvlUsd, edges: row.edges });
    byDex.set(row.dexId, list);
  }

  const selectedPoolKeys = new Set<string>();
  const selected: Edge[] = [];
  for (const [dexId, rows] of byDex) {
    const maxPools = maxPoolsForDexId(dexId);
    const sorted = rows
      .sort((a, b) => b.tvlUsd - a.tvlUsd || a.key.localeCompare(b.key))
      .slice(0, Math.max(0, maxPools));
    for (const row of sorted) {
      selectedPoolKeys.add(row.key);
      selected.push(...row.edges);
    }
  }

  return {
    selected: selected.sort((a, b) => b.tvlUsd - a.tvlUsd || a.dexId.localeCompare(b.dexId) || a.poolAddress.localeCompare(b.poolAddress)),
    seenPools: new Set(poolRows.keys()),
    selectedPools: selectedPoolKeys,
  };
}

function routeMaxPoolReserveFractionBps() {
  return positiveNumberEnv("ROUTE_MAX_POOL_RESERVE_FRACTION_BPS", 50);
}

function edgeInputReserveCapRaw(edge: Edge) {
  const bps = BigInt(Math.floor(routeMaxPoolReserveFractionBps()));
  if (edge.reserveIn <= 0n || bps <= 0n) return 0n;
  const cap = (edge.reserveIn * bps) / 10000n;
  return cap > 0n ? cap : 1n;
}

function edgeInputReserveCapUsd(edge: Edge) {
  if (!edge.tokenInPriceUsd || edge.tokenInPriceUsd <= 0) return undefined;
  return rawToFloat(edgeInputReserveCapRaw(edge), edge.tokenInDecimals) * edge.tokenInPriceUsd;
}

function routePoolStateCapRaw(route: Edge[], flashloanAsset: TokenMeta) {
  if (!flashloanAsset.priceUsd || flashloanAsset.priceUsd <= 0) return 0n;
  let capRaw: bigint | undefined;
  for (const edge of route) {
    const edgeCapRaw = edgeInputReserveCapRaw(edge);
    if (edgeCapRaw <= 0n) return 0n;
    const equivalentFlashRaw = sameAddress(edge.tokenIn, flashloanAsset.address)
      ? edgeCapRaw
      : (() => {
          const edgeCapUsd = edgeInputReserveCapUsd(edge);
          return edgeCapUsd === undefined
            ? undefined
            : floatToRaw(edgeCapUsd / flashloanAsset.priceUsd!, flashloanAsset.decimals);
        })();
    if (equivalentFlashRaw === undefined || equivalentFlashRaw <= 0n) continue;
    capRaw = capRaw === undefined || equivalentFlashRaw < capRaw ? equivalentFlashRaw : capRaw;
  }
  return capRaw ?? 0n;
}

function minRoutePoolTvlUsd() {
  const explicit = Number(process.env.ROUTE_MIN_POOL_TVL_USD || process.env.MIN_ROUTE_POOL_TVL_USD);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  const minFlashloanUsd = positiveNumberEnv("MIN_FLASHLOAN_USD", 0);
  const alpha = positiveNumberEnv("RISK_ALPHA_LIQUIDITY_FRACTION", 0.05);
  if (minFlashloanUsd > 0 && alpha > 0) return minFlashloanUsd / alpha;
  return 0;
}

function tokenAmount(raw: bigint, token: TokenMeta) {
  return ethers.formatUnits(raw, token.decimals);
}

function tokenUsd(raw: bigint, token: TokenMeta) {
  return token.priceUsd ? rawToFloat(raw, token.decimals) * token.priceUsd : undefined;
}

function sortedObject<T>(record: Record<string, T>) {
  return Object.fromEntries(Object.entries(record).sort(([a], [b]) => a.localeCompare(b)));
}

function discoveryTransparencyPath(latestBlock: number, stateHash: string) {
  const configured = process.env.DISCOVERY_TRANSPARENCY_PATH;
  if (configured && configured.trim()) return resolve(process.cwd(), configured.trim());
  const suffix = `${latestBlock}-${stateHash.slice(2, 10)}`;
  return resolve(process.cwd(), ".cache", `discovery-transparency-${suffix}.json`);
}

function writeDiscoveryTransparencyExport(params: {
  latestBlock: number;
  tokenCache: Map<string, TokenMeta>;
  flashloanAssets: TokenMeta[];
  discoveryAssets: TokenMeta[];
  flashloanBook: {
    ordered: FlashloanLiquidity[];
    byAsset: Map<string, FlashloanLiquidity[]>;
    aave: FlashloanLiquidity[];
    balancer: FlashloanLiquidity[];
  };
  edges: Edge[];
  stats: DiscoveryStats;
  stateHash: string;
  stateCacheStats: { entries: number; updated: number };
}) {
  const { latestBlock, tokenCache, flashloanAssets, discoveryAssets, flashloanBook, edges, stats, stateHash, stateCacheStats } = params;
  const tokens = Array.from(tokenCache.values())
    .sort((a, b) => a.symbol.localeCompare(b.symbol) || a.address.localeCompare(b.address))
    .map((token) => ({
      symbol: token.symbol,
      address: token.address,
      decimals: token.decimals,
      priceUsd: token.priceUsd ?? null,
      priceSource: token.priceSource ?? null,
      priceConfidence: token.priceConfidence ?? null,
      flashloanEligible: token.flashloanEligible,
      settlementAsset: isUsdcSettlementAsset(token),
    }));

  const sourceBuckets = new Map<string, {
    dexId: string;
    venueNames: Set<string>;
    directedEdges: number;
    uniquePools: Set<string>;
    maxPoolTvlUsd: Map<string, number>;
  }>();
  for (const edge of edges) {
    const bucket = sourceBuckets.get(edge.dexId) || {
      dexId: edge.dexId,
      venueNames: new Set<string>(),
      directedEdges: 0,
      uniquePools: new Set<string>(),
      maxPoolTvlUsd: new Map<string, number>(),
    };
    bucket.venueNames.add(edge.venueName);
    bucket.directedEdges += 1;
    const poolKey = edge.poolAddress.toLowerCase();
    bucket.uniquePools.add(poolKey);
    bucket.maxPoolTvlUsd.set(poolKey, Math.max(bucket.maxPoolTvlUsd.get(poolKey) || 0, edge.tvlUsd || 0));
    sourceBuckets.set(edge.dexId, bucket);
  }

  const sourceSummary = Array.from(sourceBuckets.values())
    .map((bucket) => ({
      dexId: bucket.dexId,
      venueNames: Array.from(bucket.venueNames).sort(),
      directedEdges: bucket.directedEdges,
      uniquePools: bucket.uniquePools.size,
      uniquePoolTvlUsd: Array.from(bucket.maxPoolTvlUsd.values()).reduce((sum, value) => sum + value, 0),
    }))
    .sort((a, b) => b.directedEdges - a.directedEdges || a.dexId.localeCompare(b.dexId));

  const flashloanLiquidity = flashloanBook.ordered
    .map((item) => ({
      provider: item.provider,
      sourceCode: item.sourceCode,
      providerAddress: item.providerAddress,
      assetSymbol: item.asset.symbol,
      assetAddress: item.asset.address,
      assetDecimals: item.asset.decimals,
      liquidityRaw: item.liquidity.toString(),
      liquidityFormatted: tokenAmount(item.liquidity, item.asset),
      liquidityUsd: tokenUsd(item.liquidity, item.asset) ?? null,
      feeBps: item.feeBps.toString(),
      currentlyExecutableProvider: executableFlashloanOptions([item]).length > 0,
      settlementAsset: isUsdcSettlementAsset(item.asset),
      meetsMinFlashloanUsd: hasExecutableMinFlashloanCapital(item.asset, flashloanBook.byAsset),
    }))
    .sort((a, b) =>
      Number(b.currentlyExecutableProvider) - Number(a.currentlyExecutableProvider) ||
      Number(b.settlementAsset) - Number(a.settlementAsset) ||
      (b.liquidityUsd ?? 0) - (a.liquidityUsd ?? 0) ||
      a.provider.localeCompare(b.provider)
    );

  const directedEdges = edges
    .map((edge) => {
      const tokenIn = tokenCache.get(edge.tokenIn.toLowerCase());
      const tokenOut = tokenCache.get(edge.tokenOut.toLowerCase());
      return {
        edgeId: edge.edgeId,
        dexId: edge.dexId,
        venueName: edge.venueName,
        invariant: edge.invariant,
        poolAddress: edge.poolAddress,
        router: edge.router,
        feeBps: edge.feeBps,
        stateBlock: edge.stateBlock,
        stateAgeBlocks: latestBlock - edge.stateBlock,
        tvlUsd: edge.tvlUsd,
        tokenIn: {
          symbol: edge.tokenInSymbol,
          address: edge.tokenIn,
          decimals: tokenIn?.decimals ?? null,
          priceUsd: edge.tokenInPriceUsd ?? null,
          reserveRaw: edge.reserveIn.toString(),
          reserveFormatted: tokenIn ? tokenAmount(edge.reserveIn, tokenIn) : null,
          reserveUsd: tokenIn ? tokenUsd(edge.reserveIn, tokenIn) ?? null : null,
        },
        tokenOut: {
          symbol: edge.tokenOutSymbol,
          address: edge.tokenOut,
          decimals: tokenOut?.decimals ?? null,
          priceUsd: edge.tokenOutPriceUsd ?? null,
          reserveRaw: edge.reserveOut.toString(),
          reserveFormatted: tokenOut ? tokenAmount(edge.reserveOut, tokenOut) : null,
          reserveUsd: tokenOut ? tokenUsd(edge.reserveOut, tokenOut) ?? null : null,
        },
        extra: {
          v3Fee: edge.extra?.v3Fee ?? null,
          sqrtPriceX96: edge.extra?.sqrtPriceX96 ?? null,
          tick: edge.extra?.tick ?? null,
          tickSpacing: edge.extra?.tickSpacing ?? null,
          liquidity: edge.extra?.liquidity ?? null,
          curveIndexType: edge.extra?.curveIndexType ?? null,
          balancerWeightIn: edge.extra?.balancerWeightIn?.toString() ?? null,
          balancerWeightOut: edge.extra?.balancerWeightOut?.toString() ?? null,
          balancerSwapFeeBps: edge.extra?.balancerSwapFeeBps?.toString() ?? null,
        },
      };
    })
    .sort((a, b) => b.tvlUsd - a.tvlUsd || a.dexId.localeCompare(b.dexId) || a.poolAddress.localeCompare(b.poolAddress));

  const rawSpreadPolicy = buildStrategyFlashloanPolicy(flashloanAssets);
  const rawSpreadBuild = buildRawSpreadRoutes(rawSpreadPolicy.atomicCandidateSeedAssets, edges);
  const rawSpreadRoutes = rawSpreadBuild.routes.map((item, index) => ({
    rank: index + 1,
    flashloanSymbol: item.flashloanAsset.symbol,
    flashloanAsset: item.flashloanAsset.address,
    token1Symbol: item.token1Symbol,
    token1Address: item.token1Address,
    rawBuyPrice: item.buyPrice,
    rawSellPrice: item.sellPrice,
    rawSpreadDelta: item.rawSpreadDelta,
    rawSpreadBps: item.rawSpreadBps,
    rawCapitalCapUsd: item.rawCapitalCapUsd,
    rawEstimatedGrossUsdAtCap: item.rawEstimatedGrossUsdAtCap,
    rawEstimatedGrossBpsAtCap: item.rawEstimatedGrossBpsAtCap,
    rawRankPolicy: "CAPACITY_ADJUSTED_GROSS_THEN_SPREAD",
    direction: "BUY_LT_SELL",
    lowestPoolTvlUsd: item.lowestPoolTvlUsd,
    buyVenue: item.buyVenue,
    sellVenue: item.sellVenue,
    buyDexId: item.route[0]?.dexId ?? null,
    sellDexId: item.route[1]?.dexId ?? null,
    buyInvariant: item.route[0]?.invariant ?? null,
    sellInvariant: item.route[1]?.invariant ?? null,
    path: item.route.map((edge) => edge.tokenInSymbol).concat(item.route[item.route.length - 1].tokenOutSymbol),
    pools: item.route.map((edge) => edge.poolId || edge.poolAddress),
  }));

  const output = {
    generatedAt: new Date().toISOString(),
    phase: "PRE_MATH_DISCOVERY_GRAPH_END",
    guarantee: "No route quote ladder, invariant promotion, C1 payload construction, or broadcast decision has been applied to this export.",
    chainId: Number(CHAIN_ID),
    latestBlock,
    stateHash,
    counts: {
      tokens: tokenCache.size,
      discoveryUniverseConfigured: configuredDiscoveryUniverseTokenAddresses().length,
      discoveryUniverseLoaded: discoveryAssets.length,
      flashloanAssets: flashloanAssets.length,
      flashloanLiquidityRows: flashloanBook.ordered.length,
      directedEdges: edges.length,
      uniquePools: new Set(edges.map((edge) => edge.poolAddress.toLowerCase())).size,
      rawSpreadRankedRoutes: rawSpreadRoutes.length,
    },
    intakeUsage: {
      discoveryUniverseProfile: discoveryUniverseProfile(),
      discoveryOrder: [
        "flashloan_liquidity",
        "v2_pairs",
        "v3_pools",
        "algebra_pools",
        "curve_pools",
        "balancer_weighted_pools",
        "deep_liquidity_pool_selection",
        "price_derivation",
        "presend_revalidation",
        "state_hash",
        "transparency_export",
        "route_ranking_math",
      ],
      edgeSort: "tvlUsd DESC, dexId ASC, poolAddress ASC",
      tokenSort: "symbol ASC, address ASC",
      sourceSummarySort: "directedEdges DESC, dexId ASC",
      amountUnits: "raw on-chain integer plus formatted token units using discovered decimals",
      priceUsage: "priceUsd is used only for TVL, USD cost conversion, and reporting; route output math uses raw token units.",
      settlementPolicy: {
        requireUsdc: requireUsdcSettlement(),
        symbols: Array.from(settlementSymbols()).sort(),
        addresses: Array.from(settlementAddressSet()).sort(),
        strategyMode: flashloanStrategyMode(),
        finalSettlementAsset: useBuyLowSellHighToUsdceStrategy() ? usdceSettlementAddress() : "FLASHLOAN_ASSET",
        flashloanCapitalBasket: Array.from(flashloanCapitalBasketAddressSet()).sort(),
        balancerC1Supported: balancerC1FlashloanSupported(),
      },
      protocolCoverage: routeAdapterCapabilities.map((adapter) => ({
        poolType: adapter.poolType,
        discoverySource: adapter.discoverySource,
        stateReader: adapter.stateReader,
        quoteAdapter: adapter.quoteAdapter,
        calldataAdapter: adapter.calldataAdapter,
        preSendRevalidation: adapter.preSendRevalidation,
        adapterPresent: adapter.adapterPresent,
        executable: adapter.executable,
        rejectionReason: adapter.rejectionReason ?? null,
      })),
    },
    envKnobs: {
      minFlashloanUsd: positiveNumberEnv("MIN_FLASHLOAN_USD", 0),
      allowRouteCapBelowMinFlashloan: allowRouteCapBelowMinFlashloan(),
      minRoutePoolTvlUsd: minRoutePoolTvlUsd(),
      riskAlphaLiquidityFraction: positiveNumberEnv("RISK_ALPHA_LIQUIDITY_FRACTION", 0.05),
      routeMaxPoolReserveFractionBps: routeMaxPoolReserveFractionBps(),
      liquidityFirstDiscovery: process.env.LIVE_DISCOVERY_LIQUIDITY_FIRST === "false" ? false : true,
      discoveryPoolScanMultiplier: discoveryPoolScanMultiplier(),
      liveV2MaxPools: intEnv("LIVE_V2_MAX_POOLS", DEFAULT_V2_MAX_POOLS),
      liveV3MaxPools: intEnv("LIVE_V3_MAX_POOLS", DEFAULT_V3_MAX_POOLS),
      liveAlgebraMaxPools: intEnv("LIVE_ALGEBRA_MAX_POOLS", DEFAULT_ALGEBRA_MAX_POOLS),
      liveCurveMaxPools: intEnv("LIVE_CURVE_MAX_POOLS", DEFAULT_CURVE_MAX_POOLS),
      liveBalancerMaxPools: intEnv("LIVE_BALANCER_MAX_POOLS", DEFAULT_BALANCER_MAX_POOLS),
      preSendRevalidationLanes: intEnv("LIVE_PRESEND_REVALIDATION_LANES", intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY)),
      preSendRevalidationTimeoutMs: intEnv("LIVE_PRESEND_REVALIDATION_TIMEOUT_MS", intEnv("LIVE_RPC_CALL_TIMEOUT_MS", DEFAULT_RPC_CALL_TIMEOUT_MS) * 2),
      maxDynamicRoutes: intEnv("MAX_DYNAMIC_ROUTES", intEnv("LIVE_ROUTE_MAX_CYCLES", DEFAULT_ROUTE_MAX_CYCLES)),
      maxRouteHops: Math.max(2, Math.min(4, intEnv("MAX_ROUTE_HOPS", 4))),
      maxStateAgeBlocks: intEnv("LIVE_ROUTE_MAX_STATE_AGE_BLOCKS", DEFAULT_ROUTE_MAX_STATE_AGE_BLOCKS),
      slippageBps: numberEnv("SLIPPAGE_BPS", 10),
      estimatedGasUnits: intEnv("ESTIMATED_GAS_UNITS", 450000),
      nativeTokenUsd: nativeTokenUsd(),
      minNetProfitUsd: numberEnv("MIN_NET_PROFIT_USD", 5),
      relayTipUsd: numberEnv("RELAY_TIP_USD", numberEnv("BRIBES_USD", 0)),
      executorCostUsd: numberEnv("EXECUTOR_COST_USD", 0),
      riskBufferUsd: numberEnv("RISK_BUFFER_USD", 0),
      flashloanStrategyMode: flashloanStrategyMode(),
      usdceSettlementAssetAddress: usdceSettlementAddress(),
      rawSpreadRoutePrintLimit: optionalIntEnv("RAW_SPREAD_ROUTE_PRINT_LIMIT") ?? 0,
    },
    stats: {
      ...stats,
      sourceCounts: sortedObject(stats.sourceCounts),
      preSendRejects: sortedObject(stats.preSendRejects),
      quoteRejects: sortedObject(stats.quoteRejects),
    },
    stateCacheStats,
    sourceSummary,
    discoveryUniverse: discoveryAssets
      .slice()
      .sort((a, b) => a.symbol.localeCompare(b.symbol) || a.address.localeCompare(b.address))
      .map((token) => ({
        symbol: token.symbol,
        address: token.address,
        decimals: token.decimals,
        priceUsd: token.priceUsd ?? null,
        priceSource: token.priceSource ?? null,
        priceConfidence: token.priceConfidence ?? null,
        flashloanEligible: token.flashloanEligible,
        settlementAsset: isUsdcSettlementAsset(token),
      })),
    tokens,
    flashloanLiquidity,
    directedEdges,
    rawSpread: {
      policy: "PRE_PROTOCOL_MATH_BUY_LT_SELL_ONLY",
      rankedRoutes: rawSpreadRoutes,
      matrix: {
        policy: "TOP_N_BUY_SELL_FALLBACK",
        pairs: rawSpreadBuild.matrixPairs,
        topNBuysPerPair: rawSpreadBuild.topNBuysPerPair,
        topNSellsPerPair: rawSpreadBuild.topNSellsPerPair,
        prunedByTopN: rawSpreadBuild.matrixPrunedByTopN,
      },
      rejects: {
        samePoolVenue: rawSpreadBuild.rejectedSamePoolVenue,
        sameDestination: rawSpreadBuild.rejectedSameDestination,
        invalidPrice: rawSpreadBuild.rejectedInvalidPrice,
        nonPositiveSpread: rawSpreadBuild.rejectedNonPositiveSpread,
        lowTvl: rawSpreadBuild.rejectedLowTvl,
        groupsWithoutSell: rawSpreadBuild.groupsWithoutSell,
      },
    },
  };

  const primaryPath = discoveryTransparencyPath(latestBlock, stateHash);
  mkdirSync(dirname(primaryPath), { recursive: true });
  writeFileSync(primaryPath, `${JSON.stringify(output, null, 2)}\n`);
  const latestPath = resolve(process.cwd(), ".cache", "discovery-transparency-latest.json");
  mkdirSync(dirname(latestPath), { recursive: true });
  writeFileSync(latestPath, `${JSON.stringify(output, null, 2)}\n`);
  console.log(`DISCOVERY_TRANSPARENCY|phase=PRE_MATH_DISCOVERY_GRAPH_END|path=${primaryPath}|latest=${latestPath}|profile=${discoveryUniverseProfile()}|discoveryUniverseLoaded=${discoveryAssets.length}|tokens=${tokens.length}|flashloanLiquidity=${flashloanLiquidity.length}|directedEdges=${directedEdges.length}|uniquePools=${output.counts.uniquePools}|stateHash=${stateHash}`);
}

function parseSourceList(envName: string, fallback: string) {
  return (process.env[envName] || fallback)
    .split(";")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => entry.split(":").map((part) => part.trim()));
}

async function getJson(path: string) {
  const response = await fetch(`${API_BASE}${path}`);
  return await response.json();
}

async function postJson(path: string, body: unknown) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body, (_key, value) => typeof value === "bigint" ? value.toString() : value),
  });
  return { status: response.status, json: await response.json() };
}

async function safeGetLogs(
  provider: ethers.JsonRpcProvider,
  filter: Omit<ethers.Filter, "fromBlock" | "toBlock">,
  fromBlock: number,
  toBlock: number,
  chunkSize: number,
) {
  if (process.env.LIVE_DISCOVERY_DISABLE_LOG_SCAN === "true") {
    return { logs: [], rejected: 0 };
  }
  const logs: ethers.Log[] = [];
  let rejected = 0;
  const callTimeoutMs = intEnv("LIVE_RPC_CALL_TIMEOUT_MS", DEFAULT_RPC_CALL_TIMEOUT_MS);
  const logProvider = useWssDiscovery() ? getBackfillProvider() : provider;
  for (let start = fromBlock; start <= toBlock; start += chunkSize) {
    const end = Math.min(toBlock, start + chunkSize - 1);
    try {
      logs.push(...await withTimeout(
        logProvider.getLogs({ ...filter, fromBlock: start, toBlock: end }),
        callTimeoutMs,
        "GET_LOGS",
      ));
    } catch {
      rejected += 1;
    }
  }
  return { logs, rejected };
}

async function loadTokenMeta(provider: ethers.JsonRpcProvider, cache: Map<string, TokenMeta>, address: string, flashloanEligible = false) {
  const normalized = normalize(address);
  const cached = cache.get(normalized.toLowerCase());
  if (cached) {
    cached.flashloanEligible = cached.flashloanEligible || flashloanEligible;
    return cached;
  }
  const token = new ethers.Contract(normalized, ERC20_ABI, provider);
  const [symbolResult, decimalsResult] = await Promise.allSettled([token.symbol(), token.decimals()]);
  if (symbolResult.status !== "fulfilled" || decimalsResult.status !== "fulfilled") {
    throw new Error(`TOKEN_METADATA_UNRESOLVED:${normalized}`);
  }
  const priceSeed = trustedPriceSeed(normalized, String(symbolResult.value));
  const meta: TokenMeta = {
    chainId: 137,
    address: normalized,
    symbol: String(symbolResult.value),
    decimals: Number(decimalsResult.value),
    priceUsd: priceSeed?.priceUsd,
    priceSource: priceSeed?.source,
    priceConfidence: priceSeed?.confidence,
    flashloanEligible,
  };
  cache.set(normalized.toLowerCase(), meta);
  return meta;
}

async function loadDiscoveryUniverseAssets(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>) {
  const assets: TokenMeta[] = [];
  for (const address of configuredDiscoveryUniverseTokenAddresses()) {
    try {
      assets.push(await loadTokenMeta(provider, tokenCache, address, false));
    } catch {
      // Universe entries that do not resolve metadata are excluded fail-closed.
    }
  }
  return assets;
}

async function discoverFlashloanAssets(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>) {
  const pool = new ethers.Contract(normalize(AAVE_V3_POOL), AAVE_POOL_ABI, provider);
  const reserves = await pool.getReservesList() as string[];
  const assets: TokenMeta[] = [];
  for (const reserve of reserves) {
    try {
      assets.push(await loadTokenMeta(provider, tokenCache, reserve, true));
    } catch {
      // Token metadata failure means this reserve cannot safely anchor a live route.
    }
  }
  return assets;
}

async function tokenBalance(provider: ethers.JsonRpcProvider, tokenAddress: string, holder: string) {
  const token = new ethers.Contract(normalize(tokenAddress), ERC20_ABI, provider);
  return BigInt(await token.balanceOf(normalize(holder)));
}

async function discoverAaveFlashloanLiquidity(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>) {
  const poolAddress = normalize(AAVE_V3_POOL);
  const pool = new ethers.Contract(poolAddress, AAVE_POOL_ABI, provider);
  const reserves = await pool.getReservesList() as string[];
  const liquidity: FlashloanLiquidity[] = [];
  for (const reserve of reserves) {
    try {
      const asset = await loadTokenMeta(provider, tokenCache, reserve, true);
      const available = await tokenBalance(provider, asset.address, poolAddress).catch(() => 0n);
      if (available <= 0n) continue;
      liquidity.push({
        provider: "AAVE_V3_POOL",
        sourceCode: 1,
        providerAddress: poolAddress,
        asset,
        liquidity: available,
        feeBps: BigInt(Math.floor(numberEnv("FLASH_LOAN_FEE_BPS", 9))),
      });
    } catch {
      // Unresolved reserve metadata cannot anchor a live flashloan route.
    }
  }
  return liquidity;
}

async function discoverBalancerFlashloanLiquidity(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, latestBlock: number) {
  const vaultAddress = normalize(ROUTE_ADAPTER_TARGETS.balancerVault);
  const lookback = intEnv("LIVE_BALANCER_LOOKBACK_BLOCKS", intEnv("LIVE_DISCOVERY_LOOKBACK_BLOCKS", DEFAULT_DISCOVERY_LOOKBACK_BLOCKS));
  const chunk = Math.max(1, intEnv("LIVE_DISCOVERY_LOG_CHUNK_BLOCKS", DEFAULT_DISCOVERY_LOG_CHUNK_BLOCKS));
  const fromBlock = Math.max(0, latestBlock - lookback);
  const iface = new ethers.Interface(BALANCER_VAULT_ABI);
  const topic = iface.getEvent("PoolRegistered")?.topicHash;
  const assetSet = new Set<string>();
  for (const token of tokenCache.values()) {
    if (token.flashloanEligible) assetSet.add(token.address.toLowerCase());
  }
  for (const token of (process.env.FLASHLOAN_ASSET_TOKENS || "").split(",").map((item) => item.trim()).filter(Boolean)) {
    try {
      assetSet.add(normalize(token).toLowerCase());
    } catch {
      // Ignore invalid operator-provided token addresses.
    }
  }
  for (const token of configuredDiscoveryUniverseTokenAddresses()) {
    assetSet.add(token.toLowerCase());
  }
  if (topic) {
    const scan = await safeGetLogs(provider, { address: vaultAddress, topics: [topic] }, fromBlock, latestBlock, chunk);
    const vault = new ethers.Contract(vaultAddress, BALANCER_VAULT_ABI, provider);
    for (const log of scan.logs) {
      try {
        const parsed = iface.parseLog(log);
        const poolId = parsed?.args?.poolId as string;
        const poolTokens = await vault.getPoolTokens(poolId);
        for (const token of poolTokens.tokens as string[]) {
          if (token && token !== ZERO_ADDRESS) assetSet.add(normalize(token).toLowerCase());
        }
      } catch {
        // Ignore malformed pool records; liquidity is discovered again through arb pool validation.
      }
    }
  }

  const liquidity: FlashloanLiquidity[] = [];
  for (const tokenAddress of assetSet) {
    try {
      const asset = await loadTokenMeta(provider, tokenCache, tokenAddress, true);
      const available = await tokenBalance(provider, asset.address, vaultAddress).catch(() => 0n);
      if (available <= 0n) continue;
      liquidity.push({
        provider: "BALANCER_V2_VAULT",
        sourceCode: 2,
        providerAddress: vaultAddress,
        asset,
        liquidity: available,
        feeBps: BigInt(Math.floor(numberEnv("BALANCER_FLASH_FEE_BPS", 0))),
      });
    } catch {
      // Token metadata failure means this token is not live-executable.
    }
  }
  return liquidity;
}

async function discoverFlashloanLiquidity(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, latestBlock: number) {
  const aave = await discoverAaveFlashloanLiquidity(provider, tokenCache).catch(() => [] as FlashloanLiquidity[]);
  const balancer = await discoverBalancerFlashloanLiquidity(provider, tokenCache, latestBlock).catch(() => [] as FlashloanLiquidity[]);
  const byAsset = new Map<string, FlashloanLiquidity[]>();
  for (const item of [...balancer, ...aave]) {
    const key = item.asset.address.toLowerCase();
    const list = byAsset.get(key) || [];
    list.push(item);
    byAsset.set(key, list.sort((a, b) => a.provider === "BALANCER_V2_VAULT" ? -1 : b.provider === "BALANCER_V2_VAULT" ? 1 : Number(a.feeBps - b.feeBps)));
  }
  return {
    ordered: Array.from(byAsset.values()).flat(),
    byAsset,
    balancer,
    aave,
  };
}

function addEdge(edges: Map<string, Edge>, stats: DiscoveryStats, edge: Edge) {
  const key = `${edge.dexId}:${edge.poolAddress}:${edge.tokenIn}:${edge.tokenOut}:${edge.invariant}:${edge.feeBps}:${edge.tokenInIndex ?? ""}:${edge.tokenOutIndex ?? ""}`.toLowerCase();
  if (edges.has(key)) {
    stats.rejectedDuplicateEdge += 1;
    return;
  }
  edges.set(key, edge);
  stats.sourceCounts[edge.dexId] = (stats.sourceCounts[edge.dexId] || 0) + 1;
}

function edgeBase(params: {
  dexId: string;
  venueName: string;
  poolAddress: string;
  router: string;
  tokenIn: TokenMeta;
  tokenOut: TokenMeta;
  invariant: InvariantKind;
  feeBps: number;
  reserveIn: bigint;
  reserveOut: bigint;
  tvlUsd: number;
  stateBlock: number;
  quoteAdapter: string;
  calldataAdapter: string;
  executorTarget: string;
  poolId?: string;
  tokenInIndex?: number;
  tokenOutIndex?: number;
  extra?: Edge["extra"];
}): Edge {
  return {
    chainId: 137,
    dexId: params.dexId,
    venueName: params.venueName,
    poolAddress: normalize(params.poolAddress),
    poolId: params.poolId,
    tokenIn: params.tokenIn.address,
    tokenOut: params.tokenOut.address,
    tokenInIndex: params.tokenInIndex,
    tokenOutIndex: params.tokenOutIndex,
    tokenInDecimals: params.tokenIn.decimals,
    tokenOutDecimals: params.tokenOut.decimals,
    tokenInSymbol: params.tokenIn.symbol,
    tokenOutSymbol: params.tokenOut.symbol,
    tokenInPriceUsd: params.tokenIn.priceUsd,
    tokenOutPriceUsd: params.tokenOut.priceUsd,
    invariant: params.invariant,
    feeBps: params.feeBps,
    reserveIn: params.reserveIn,
    reserveOut: params.reserveOut,
    tvlUsd: params.tvlUsd,
    stateBlock: params.stateBlock,
    quoteAdapter: params.quoteAdapter,
    calldataAdapter: params.calldataAdapter,
    executorTarget: normalize(params.executorTarget),
    router: normalize(params.router),
    edgeId: `${params.dexId}:${normalize(params.poolAddress)}:${params.tokenIn.symbol}->${params.tokenOut.symbol}`,
    extra: params.extra,
  };
}

function estimateTvlUsd(tokenA: TokenMeta, reserveA: bigint, tokenB: TokenMeta, reserveB: bigint) {
  const left = tokenA.priceUsd ? rawToFloat(reserveA, tokenA.decimals) * tokenA.priceUsd : undefined;
  const right = tokenB.priceUsd ? rawToFloat(reserveB, tokenB.decimals) * tokenB.priceUsd : undefined;
  if (left !== undefined && right !== undefined) return left + right;
  if (left !== undefined) return left * 2;
  if (right !== undefined) return right * 2;
  return 0;
}

async function addV2Pair(
  provider: ethers.JsonRpcProvider,
  tokenCache: Map<string, TokenMeta>,
  edges: Map<string, Edge>,
  stats: DiscoveryStats,
  venueName: string,
  dexId: string,
  router: string,
  pairAddress: string,
  feeBps: number,
  stateBlock: number,
) {
  const pair = new ethers.Contract(pairAddress, V2_PAIR_ABI, provider);
  const [token0Raw, token1Raw, reserves] = await Promise.all([pair.token0(), pair.token1(), pair.getReserves()]);
  const token0 = await loadTokenMeta(provider, tokenCache, token0Raw).catch(() => undefined);
  const token1 = await loadTokenMeta(provider, tokenCache, token1Raw).catch(() => undefined);
  if (!token0 || !token1) {
    stats.rejectedMetadata += 1;
    return;
  }
  const reserve0 = BigInt(reserves.reserve0);
  const reserve1 = BigInt(reserves.reserve1);
  if (reserve0 <= 0n || reserve1 <= 0n) {
    stats.rejectedZeroLiquidity += 1;
    return;
  }
  const tvlUsd = estimateTvlUsd(token0, reserve0, token1, reserve1);
  addEdge(edges, stats, edgeBase({
    dexId,
    venueName,
    poolAddress: pairAddress,
    router,
    tokenIn: token0,
    tokenOut: token1,
    invariant: "V2_CPMM",
    feeBps,
    reserveIn: reserve0,
    reserveOut: reserve1,
    tvlUsd,
    stateBlock,
    quoteAdapter: "quoteV2Cpmm",
    calldataAdapter: "buildV2SwapCalldata",
    executorTarget: router,
  }));
  addEdge(edges, stats, edgeBase({
    dexId,
    venueName,
    poolAddress: pairAddress,
    router,
    tokenIn: token1,
    tokenOut: token0,
    invariant: "V2_CPMM",
    feeBps,
    reserveIn: reserve1,
    reserveOut: reserve0,
    tvlUsd,
    stateBlock,
    quoteAdapter: "quoteV2Cpmm",
    calldataAdapter: "buildV2SwapCalldata",
    executorTarget: router,
  }));
}

async function discoverV2(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, edges: Map<string, Edge>, stats: DiscoveryStats, latestBlock: number, flashloanAssets: TokenMeta[], cache: DiscoveryCache) {
  const sources = parseSourceList(
    "LIVE_DISCOVERY_V2_FACTORIES",
    "QuickSwapV2:0x5757371414417b8c6caad45baef941abc7d3ab32:0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff:30;SushiSwapV2:0xc35DADB65012eC5796536bD9864eD8773aBc74C4:0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506:30",
  );
  const lookback = intEnv("LIVE_DISCOVERY_LOOKBACK_BLOCKS", DEFAULT_DISCOVERY_LOOKBACK_BLOCKS);
  const chunk = Math.max(1, intEnv("LIVE_DISCOVERY_LOG_CHUNK_BLOCKS", DEFAULT_DISCOVERY_LOG_CHUNK_BLOCKS));
  const iface = new ethers.Interface(V2_FACTORY_ABI);
  const topic = iface.getEvent("PairCreated")?.topicHash;

  for (const [venueName, factoryAddress, router, feeRaw] of sources) {
    if (!factoryAddress || !router) continue;
    const dexId = venueName.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
    const factory = new ethers.Contract(factoryAddress, V2_FACTORY_ABI, provider);
    const cacheKey = `v2:${dexId}:${factoryAddress.toLowerCase()}`;
    const cachedPairs = cache.getCachedPools(cacheKey);
    const maxPools = intEnv("LIVE_V2_MAX_POOLS", DEFAULT_V2_MAX_POOLS);
    const candidatePoolLimit = discoveryCandidatePoolLimit(maxPools);
    const callTimeoutMs = intEnv("LIVE_RPC_CALL_TIMEOUT_MS", DEFAULT_RPC_CALL_TIMEOUT_MS);
    const boundedCachedPairs = cachedPairs.slice(0, Math.max(0, candidatePoolLimit));
    const seen = new Set<string>(boundedCachedPairs.map((pair) => pair.toLowerCase()));
    const newPairs: string[] = [];
    let directAdded = 0;

    await runWithConcurrency(boundedCachedPairs, intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY), async (pair) => {
      try {
        await withTimeout(
          addV2Pair(provider, tokenCache, edges, stats, venueName, dexId, router, pair, Number(feeRaw || 30), latestBlock),
          callTimeoutMs * 2,
          "V2_ADD_PAIR_CACHED",
        );
      } catch {
        stats.rejectedMetadata += 1;
      }
    });

    const fromBlock = cache.getIncrementalFromBlock(cacheKey, latestBlock, lookback);
    if (topic && fromBlock <= latestBlock) {
      const scan = await safeGetLogs(provider, { address: normalize(factoryAddress), topics: [topic] }, fromBlock, latestBlock, chunk);
      stats.rejectedLogScan += scan.rejected;
      for (const log of scan.logs) {
        if (newPairs.length >= candidatePoolLimit) break;
        try {
          const parsed = iface.parseLog(log);
          const pair = normalize(parsed?.args?.pair);
          if (seen.has(pair.toLowerCase())) continue;
          seen.add(pair.toLowerCase());
          newPairs.push(pair);
          await withTimeout(
            addV2Pair(provider, tokenCache, edges, stats, venueName, dexId, router, pair, Number(feeRaw || 30), latestBlock),
            callTimeoutMs * 2,
            "V2_ADD_PAIR",
          );
        } catch {
          stats.rejectedMetadata += 1;
        }
      }
    }

    const pairQueries: Array<[TokenMeta, TokenMeta]> = [];
    for (let i = 0; i < flashloanAssets.length; i += 1) {
      for (let j = i + 1; j < flashloanAssets.length; j += 1) {
        pairQueries.push([flashloanAssets[i], flashloanAssets[j]]);
      }
    }
    await runWithConcurrency(pairQueries, intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY), async ([left, right]) => {
      if (directAdded >= candidatePoolLimit) return;
      try {
        const pair = normalize(await withTimeout(
          factory.getPair(left.address, right.address) as Promise<string>,
          callTimeoutMs,
          "V2_GET_PAIR",
        ));
        if (pair === ZERO_ADDRESS || seen.has(pair.toLowerCase())) return;
        if (directAdded >= candidatePoolLimit) return;
        directAdded += 1;
        seen.add(pair.toLowerCase());
        newPairs.push(pair);
        await withTimeout(
          addV2Pair(provider, tokenCache, edges, stats, venueName, dexId, router, pair, Number(feeRaw || 30), latestBlock),
          callTimeoutMs * 2,
          "V2_ADD_PAIR",
        );
      } catch {
        stats.rejectedMetadata += 1;
      }
    });

    cache.updateEntry(cacheKey, latestBlock, newPairs);
  }
}

async function addV3Pool(
  provider: ethers.JsonRpcProvider,
  tokenCache: Map<string, TokenMeta>,
  edges: Map<string, Edge>,
  stats: DiscoveryStats,
  venueName: string,
  dexId: string,
  router: string,
  poolAddress: string,
  fee: number,
  stateBlock: number,
) {
  const pool = new ethers.Contract(poolAddress, V3_POOL_ABI, provider);
  const [token0Raw, token1Raw, liquidity, slot0, tickSpacingResult] = await Promise.all([
    pool.token0(),
    pool.token1(),
    pool.liquidity(),
    pool.slot0(),
    pool.tickSpacing().catch(() => undefined),
  ]);
  const liquidityRaw = BigInt(liquidity);
  const sqrtPriceX96 = BigInt(tupleValue(slot0, "sqrtPriceX96", 0));
  const unlocked = Boolean(tupleValue(slot0, "unlocked", 6));
  if (liquidityRaw <= 0n || sqrtPriceX96 <= 0n || unlocked === false) {
    stats.rejectedZeroLiquidity += 1;
    return;
  }
  const token0 = await loadTokenMeta(provider, tokenCache, token0Raw).catch(() => undefined);
  const token1 = await loadTokenMeta(provider, tokenCache, token1Raw).catch(() => undefined);
  if (!token0 || !token1) {
    stats.rejectedMetadata += 1;
    return;
  }
  const { reserve0, reserve1 } = v3ActiveReserves(liquidityRaw, sqrtPriceX96);
  if (reserve0 <= 0n || reserve1 <= 0n) {
    stats.rejectedZeroLiquidity += 1;
    return;
  }
  const tvlUsd = estimateTvlUsd(token0, reserve0, token1, reserve1);
  const feeBps = Math.max(1, Math.floor(fee / 100));
  for (const [tokenIn, tokenOut, reserveIn, reserveOut] of [[token0, token1, reserve0, reserve1], [token1, token0, reserve1, reserve0]] as const) {
    addEdge(edges, stats, edgeBase({
      dexId,
      venueName,
      poolAddress,
      router,
      tokenIn,
      tokenOut,
      invariant: "V3_CONCENTRATED_LIQUIDITY",
      feeBps,
      reserveIn,
      reserveOut,
      tvlUsd,
      stateBlock,
      quoteAdapter: "quoteV3ExactInputSingle",
      calldataAdapter: "buildV3ExactInputSingleCalldata",
      executorTarget: router,
      extra: {
        v3Fee: fee,
        sqrtPriceX96: sqrtPriceX96.toString(),
        tick: Number(tupleValue(slot0, "tick", 1)),
        tickSpacing: tickSpacingResult === undefined ? undefined : Number(tickSpacingResult),
        liquidity: liquidityRaw.toString(),
      },
    }));
  }
}

async function discoverV3(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, edges: Map<string, Edge>, stats: DiscoveryStats, latestBlock: number, flashloanAssets: TokenMeta[], cache: DiscoveryCache) {
  const sources = parseSourceList(
    "LIVE_DISCOVERY_V3_FACTORIES",
    `UniswapV3:0x1F98431c8aD98523631AE4a59f267346ea31F984:${ROUTE_ADAPTER_TARGETS.uniswapV3Router}:${ROUTE_ADAPTER_TARGETS.uniswapV3Quoter}:100,500,3000,10000`,
  );
  const lookback = intEnv("LIVE_DISCOVERY_LOOKBACK_BLOCKS", DEFAULT_DISCOVERY_LOOKBACK_BLOCKS);
  const chunk = Math.max(1, intEnv("LIVE_DISCOVERY_LOG_CHUNK_BLOCKS", DEFAULT_DISCOVERY_LOG_CHUNK_BLOCKS));
  const iface = new ethers.Interface(V3_FACTORY_ABI);
  const topic = iface.getEvent("PoolCreated")?.topicHash;

  for (const [venueName, factoryAddress, router, , feeListRaw] of sources) {
    if (!factoryAddress || !router) continue;
    const dexId = venueName.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
    const factory = new ethers.Contract(factoryAddress, V3_FACTORY_ABI, provider);
    const cacheKey = `v3:${dexId}:${factoryAddress.toLowerCase()}`;
    const cachedEntries = cache.getCachedPools(cacheKey); // "address:fee"
    const maxPools = intEnv("LIVE_V3_MAX_POOLS", DEFAULT_V3_MAX_POOLS);
    const candidatePoolLimit = discoveryCandidatePoolLimit(maxPools);
    const callTimeoutMs = intEnv("LIVE_RPC_CALL_TIMEOUT_MS", DEFAULT_RPC_CALL_TIMEOUT_MS);
    const boundedCachedEntries = cachedEntries.slice(0, Math.max(0, candidatePoolLimit));
    const seen = new Set<string>(boundedCachedEntries.map((e) => e.split(":")[0]?.toLowerCase() ?? ""));
    const newEntries: string[] = [];
    let directAdded = 0;

    // Re-validate all previously discovered pools with current on-chain state.
    await runWithConcurrency(boundedCachedEntries, intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY), async (entry) => {
      const [poolAddr, feeStr] = entry.split(":");
      if (!poolAddr) return;
      try {
        await withTimeout(
          addV3Pool(provider, tokenCache, edges, stats, venueName, dexId, router, poolAddr, Number(feeStr || 0), latestBlock),
          callTimeoutMs * 2,
          "V3_ADD_POOL_CACHED",
        );
      } catch {
        stats.rejectedMetadata += 1;
      }
    });

    // Scan only the incremental block range for newly created pools.
    const fromBlock = cache.getIncrementalFromBlock(cacheKey, latestBlock, lookback);
    if (fromBlock <= latestBlock) {
      const scan = topic
        ? await safeGetLogs(provider, { address: normalize(factoryAddress), topics: [topic] }, fromBlock, latestBlock, chunk)
        : { logs: [], rejected: 0 };
      stats.rejectedLogScan += scan.rejected;
      for (const log of scan.logs) {
        if (newEntries.length >= candidatePoolLimit) break;
        try {
          const parsed = iface.parseLog(log);
          const pool = normalize(parsed?.args?.pool);
          if (seen.has(pool.toLowerCase())) continue;
          seen.add(pool.toLowerCase());
          const fee = Number(parsed?.args?.fee);
          newEntries.push(`${pool}:${fee}`);
          await withTimeout(
            addV3Pool(provider, tokenCache, edges, stats, venueName, dexId, router, pool, fee, latestBlock),
            callTimeoutMs * 2,
            "V3_ADD_POOL",
          );
        } catch {
          stats.rejectedMetadata += 1;
        }
      }
    }

    const fees = (feeListRaw || "100,500,3000,10000").split(",").map((fee) => Number(fee.trim())).filter(Number.isFinite);
    const poolQueries: Array<[TokenMeta, TokenMeta, number]> = [];
    for (let i = 0; i < flashloanAssets.length; i += 1) {
      for (let j = i + 1; j < flashloanAssets.length; j += 1) {
        for (const fee of fees) {
          poolQueries.push([flashloanAssets[i], flashloanAssets[j], fee]);
        }
      }
    }
    await runWithConcurrency(poolQueries, intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY), async ([left, right, fee]) => {
          if (directAdded >= candidatePoolLimit) return;
          try {
            const pool = normalize(await withTimeout(
              factory.getPool(left.address, right.address, fee) as Promise<string>,
              callTimeoutMs,
              "V3_GET_POOL",
            ));
            if (pool === ZERO_ADDRESS || seen.has(pool.toLowerCase())) return;
            if (directAdded >= candidatePoolLimit) return;
            directAdded += 1;
            seen.add(pool.toLowerCase());
            newEntries.push(`${pool}:${fee}`);
            await withTimeout(
              addV3Pool(provider, tokenCache, edges, stats, venueName, dexId, router, pool, fee, latestBlock),
              callTimeoutMs * 2,
              "V3_ADD_POOL",
            );
          } catch {
            stats.rejectedMetadata += 1;
          }
    });

    cache.updateEntry(cacheKey, latestBlock, newEntries);
  }
}

async function addAlgebraPool(
  provider: ethers.JsonRpcProvider,
  tokenCache: Map<string, TokenMeta>,
  edges: Map<string, Edge>,
  stats: DiscoveryStats,
  venueName: string,
  dexId: string,
  router: string,
  poolAddress: string,
  stateBlock: number,
) {
  const pool = new ethers.Contract(poolAddress, ALGEBRA_POOL_ABI, provider);
  const [token0Raw, token1Raw, liquidity, globalState, tickSpacingResult] = await Promise.all([
    pool.token0(),
    pool.token1(),
    pool.liquidity(),
    pool.globalState(),
    pool.tickSpacing().catch(() => undefined),
  ]);
  const liquidityRaw = BigInt(liquidity);
  const sqrtPriceX96 = BigInt(tupleValue(globalState, "price", 0));
  const unlocked = Boolean(tupleValue(globalState, "unlocked", 6));
  if (liquidityRaw <= 0n || sqrtPriceX96 <= 0n || unlocked === false) {
    stats.rejectedZeroLiquidity += 1;
    return;
  }
  const token0 = await loadTokenMeta(provider, tokenCache, token0Raw).catch(() => undefined);
  const token1 = await loadTokenMeta(provider, tokenCache, token1Raw).catch(() => undefined);
  if (!token0 || !token1) {
    stats.rejectedMetadata += 1;
    return;
  }
  const { reserve0, reserve1 } = v3ActiveReserves(liquidityRaw, sqrtPriceX96);
  if (reserve0 <= 0n || reserve1 <= 0n) {
    stats.rejectedZeroLiquidity += 1;
    return;
  }
  const tvlUsd = estimateTvlUsd(token0, reserve0, token1, reserve1);
  const feeBps = Math.max(1, Math.floor(Number(tupleValue(globalState, "fee", 2)) / 100));
  for (const [tokenIn, tokenOut, reserveIn, reserveOut] of [[token0, token1, reserve0, reserve1], [token1, token0, reserve1, reserve0]] as const) {
    addEdge(edges, stats, edgeBase({
      dexId,
      venueName,
      poolAddress,
      router,
      tokenIn,
      tokenOut,
      invariant: "ALGEBRA_CONCENTRATED_LIQUIDITY",
      feeBps,
      reserveIn,
      reserveOut,
      tvlUsd,
      stateBlock,
      quoteAdapter: "quoteAlgebraExactInputSingle",
      calldataAdapter: "buildAlgebraExactInputSingleCalldata",
      executorTarget: router,
      extra: {
        sqrtPriceX96: sqrtPriceX96.toString(),
        tick: Number(tupleValue(globalState, "tick", 1)),
        tickSpacing: tickSpacingResult === undefined ? undefined : Number(tickSpacingResult),
        liquidity: liquidityRaw.toString(),
      },
    }));
  }
}

async function discoverAlgebra(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, edges: Map<string, Edge>, stats: DiscoveryStats, latestBlock: number, flashloanAssets: TokenMeta[], cache: DiscoveryCache) {
  const sources = parseSourceList(
    "LIVE_DISCOVERY_ALGEBRA_FACTORIES",
    `QuickSwapAlgebra:${ROUTE_ADAPTER_TARGETS.algebraFactory}:${ROUTE_ADAPTER_TARGETS.algebraRouter}:${ROUTE_ADAPTER_TARGETS.algebraQuoter}`,
  );
  const lookback = intEnv("LIVE_DISCOVERY_LOOKBACK_BLOCKS", DEFAULT_DISCOVERY_LOOKBACK_BLOCKS);
  const chunk = Math.max(1, intEnv("LIVE_DISCOVERY_LOG_CHUNK_BLOCKS", DEFAULT_DISCOVERY_LOG_CHUNK_BLOCKS));
  const iface = new ethers.Interface(ALGEBRA_FACTORY_ABI);
  const topic = iface.getEvent("Pool")?.topicHash;

  for (const [venueName, factoryAddress, router] of sources) {
    if (!factoryAddress || !router) continue;
    const dexId = venueName.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
    const factory = new ethers.Contract(factoryAddress, ALGEBRA_FACTORY_ABI, provider);
    const cacheKey = `algebra:${dexId}:${factoryAddress.toLowerCase()}`;
    const cachedPools = cache.getCachedPools(cacheKey);
    const maxPools = intEnv("LIVE_ALGEBRA_MAX_POOLS", DEFAULT_ALGEBRA_MAX_POOLS);
    const candidatePoolLimit = discoveryCandidatePoolLimit(maxPools);
    const callTimeoutMs = intEnv("LIVE_RPC_CALL_TIMEOUT_MS", DEFAULT_RPC_CALL_TIMEOUT_MS);
    const boundedCachedPools = cachedPools.slice(0, Math.max(0, candidatePoolLimit));
    const seen = new Set<string>(boundedCachedPools.map((p) => p.toLowerCase()));
    const newPools: string[] = [];
    let directAdded = 0;

    // Re-validate all previously discovered pools with current on-chain state.
    await runWithConcurrency(boundedCachedPools, intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY), async (pool) => {
      try {
        await withTimeout(
          addAlgebraPool(provider, tokenCache, edges, stats, venueName, dexId, router, pool, latestBlock),
          callTimeoutMs * 2,
          "ALGEBRA_ADD_POOL_CACHED",
        );
      } catch {
        stats.rejectedMetadata += 1;
      }
    });

    // Scan only the incremental block range for newly created pools.
    const fromBlock = cache.getIncrementalFromBlock(cacheKey, latestBlock, lookback);
    if (fromBlock <= latestBlock) {
      const scan = topic
        ? await safeGetLogs(provider, { address: normalize(factoryAddress), topics: [topic] }, fromBlock, latestBlock, chunk)
        : { logs: [], rejected: 0 };
      stats.rejectedLogScan += scan.rejected;
      for (const log of scan.logs) {
        if (newPools.length >= candidatePoolLimit) break;
        try {
          const parsed = iface.parseLog(log);
          const pool = normalize(parsed?.args?.pool);
          if (seen.has(pool.toLowerCase())) continue;
          seen.add(pool.toLowerCase());
          newPools.push(pool);
          await withTimeout(
            addAlgebraPool(provider, tokenCache, edges, stats, venueName, dexId, router, pool, latestBlock),
            callTimeoutMs * 2,
            "ALGEBRA_ADD_POOL",
          );
        } catch {
          stats.rejectedMetadata += 1;
        }
      }
    }

    const assetPairs: Array<[TokenMeta, TokenMeta]> = [];
    for (let i = 0; i < flashloanAssets.length; i += 1) {
      for (let j = i + 1; j < flashloanAssets.length; j += 1) {
        assetPairs.push([flashloanAssets[i], flashloanAssets[j]]);
      }
    }
    await runWithConcurrency(assetPairs, intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY), async ([left, right]) => {
        if (directAdded >= candidatePoolLimit) return;
        try {
          const pool = normalize(await withTimeout(
            factory.poolByPair(left.address, right.address) as Promise<string>,
            callTimeoutMs,
            "ALGEBRA_POOL_BY_PAIR",
          ));
          if (pool === ZERO_ADDRESS || seen.has(pool.toLowerCase())) return;
          if (directAdded >= candidatePoolLimit) return;
          directAdded += 1;
          seen.add(pool.toLowerCase());
          newPools.push(pool);
          await withTimeout(
            addAlgebraPool(provider, tokenCache, edges, stats, venueName, dexId, router, pool, latestBlock),
            callTimeoutMs * 2,
            "ALGEBRA_ADD_POOL",
          );
        } catch {
          stats.rejectedMetadata += 1;
        }
    });

    cache.updateEntry(cacheKey, latestBlock, newPools);
  }
}

async function discoverCurve(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, edges: Map<string, Edge>, stats: DiscoveryStats, latestBlock: number) {
  const addressProvider = process.env.CURVE_ADDRESS_PROVIDER || "0x0000000022D53366457F9d5E68Ec105046FC4383";
  const maxPools = intEnv("LIVE_CURVE_MAX_POOLS", DEFAULT_CURVE_MAX_POOLS);
  try {
    const providerContract = new ethers.Contract(addressProvider, CURVE_ADDRESS_PROVIDER_ABI, provider);
    const registryAddress = process.env.CURVE_REGISTRY || await providerContract.get_registry();
    const registry = new ethers.Contract(registryAddress, CURVE_REGISTRY_ABI, provider);
    const poolCount = Number(await registry.pool_count());
    const limit = maxPools === undefined ? poolCount : Math.min(poolCount, discoveryCandidatePoolLimit(maxPools));
    for (let index = 0; index < limit; index += 1) {
      try {
        const poolAddress = normalize(await registry.pool_list(index));
        const [coinsRaw, balancesRaw] = await Promise.all([registry.get_coins(poolAddress), registry.get_balances(poolAddress)]);
        const coins = (coinsRaw as string[]).filter((coin) => coin && coin !== ZERO_ADDRESS);
        const balances = balancesRaw as bigint[];
        const metas: TokenMeta[] = [];
        for (const coin of coins) metas.push(await loadTokenMeta(provider, tokenCache, coin));
        for (let i = 0; i < metas.length; i += 1) {
          for (let j = 0; j < metas.length; j += 1) {
            if (i === j) continue;
            const reserveIn = BigInt(balances[i] || 0n);
            const reserveOut = BigInt(balances[j] || 0n);
            if (reserveIn <= 0n || reserveOut <= 0n) {
              stats.rejectedZeroLiquidity += 1;
              continue;
            }
            const tvlUsd = estimateTvlUsd(metas[i], reserveIn, metas[j], reserveOut);
            addEdge(edges, stats, edgeBase({
              dexId: "CURVE",
              venueName: "Curve",
              poolAddress,
              router: ROUTE_ADAPTER_TARGETS.curveRouter,
              tokenIn: metas[i],
              tokenOut: metas[j],
              tokenInIndex: i,
              tokenOutIndex: j,
              invariant: "CURVE_STABLE_SWAP",
              feeBps: 4,
              reserveIn,
              reserveOut,
              tvlUsd,
              stateBlock: latestBlock,
              quoteAdapter: "quoteCurveGetDy",
              calldataAdapter: "buildCurveRouterExchangeCalldata",
              executorTarget: ROUTE_ADAPTER_TARGETS.curveRouter,
              extra: { curveIndexType: "int128" },
            }));
          }
        }
      } catch {
        stats.rejectedMetadata += 1;
      }
    }
  } catch {
    stats.rejectedUnsupportedInvariant += 1;
  }
}

async function addBalancerPool(
  provider: ethers.JsonRpcProvider,
  tokenCache: Map<string, TokenMeta>,
  edges: Map<string, Edge>,
  stats: DiscoveryStats,
  vault: ethers.Contract,
  vaultAddress: string,
  poolId: string,
  poolAddress: string,
  latestBlock: number,
) {
  const weightedPool = new ethers.Contract(poolAddress, BALANCER_WEIGHTED_POOL_ABI, provider);
  const [poolTokens, weights, swapFee] = await Promise.all([vault.getPoolTokens(poolId), weightedPool.getNormalizedWeights(), weightedPool.getSwapFeePercentage()]);
  const tokens = poolTokens.tokens as string[];
  const balances = poolTokens.balances as bigint[];
  const metas: TokenMeta[] = [];
  for (const token of tokens) metas.push(await loadTokenMeta(provider, tokenCache, token));
  for (let i = 0; i < metas.length; i += 1) {
    for (let j = 0; j < metas.length; j += 1) {
      if (i === j) continue;
      const reserveIn = BigInt(balances[i] || 0n);
      const reserveOut = BigInt(balances[j] || 0n);
      const weightIn = BigInt(weights[i] || 0n);
      const weightOut = BigInt(weights[j] || 0n);
      if (reserveIn <= 0n || reserveOut <= 0n || weightIn <= 0n || weightOut <= 0n) {
        stats.rejectedZeroLiquidity += 1;
        continue;
      }
      const tvlUsd = estimateTvlUsd(metas[i], reserveIn, metas[j], reserveOut);
      addEdge(edges, stats, edgeBase({
        dexId: "BALANCER_WEIGHTED",
        venueName: "BalancerWeighted",
        poolAddress,
        poolId,
        router: vaultAddress,
        tokenIn: metas[i],
        tokenOut: metas[j],
        tokenInIndex: i,
        tokenOutIndex: j,
        invariant: "BALANCER_WEIGHTED",
        feeBps: Number(BigInt(swapFee) * 10000n / 10n ** 18n),
        reserveIn,
        reserveOut,
        tvlUsd,
        stateBlock: latestBlock,
        quoteAdapter: "quoteBalancerWeighted",
        calldataAdapter: "buildBalancerSingleSwapCalldata",
        executorTarget: vaultAddress,
        extra: {
          balancerWeightIn: weightIn,
          balancerWeightOut: weightOut,
          balancerSwapFeeBps: BigInt(swapFee) * 10000n / 10n ** 18n,
        },
      }));
    }
  }
}

async function discoverBalancer(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, edges: Map<string, Edge>, stats: DiscoveryStats, latestBlock: number, cache: DiscoveryCache) {
  const vaultAddress = ROUTE_ADAPTER_TARGETS.balancerVault;
  const lookback = intEnv("LIVE_BALANCER_LOOKBACK_BLOCKS", intEnv("LIVE_DISCOVERY_LOOKBACK_BLOCKS", DEFAULT_DISCOVERY_LOOKBACK_BLOCKS));
  const chunk = Math.max(1, intEnv("LIVE_DISCOVERY_LOG_CHUNK_BLOCKS", DEFAULT_DISCOVERY_LOG_CHUNK_BLOCKS));
  const maxPools = intEnv("LIVE_BALANCER_MAX_POOLS", DEFAULT_BALANCER_MAX_POOLS);
  if (maxPools <= 0) return;
  const candidatePoolLimit = discoveryCandidatePoolLimit(maxPools);
  const cacheKey = `balancer:${vaultAddress.toLowerCase()}`;
  const cachedEntries = cache.getCachedPools(cacheKey); // "poolId:poolAddress"
  const iface = new ethers.Interface(BALANCER_VAULT_ABI);
  const topic = iface.getEvent("PoolRegistered")?.topicHash;
  if (!topic) return;
  const vault = new ethers.Contract(vaultAddress, BALANCER_VAULT_ABI, provider);
  const seen = new Set<string>(cachedEntries.map((e) => e.split(":").slice(1).join(":").toLowerCase()));
  const newEntries: string[] = [];
  let count = 0;

  // Re-validate all previously discovered pools with current on-chain state.
  for (const entry of cachedEntries) {
    if (count >= candidatePoolLimit) break;
    const colonIdx = entry.indexOf(":");
    if (colonIdx < 0) continue;
    const poolId = entry.slice(0, colonIdx);
    const poolAddress = entry.slice(colonIdx + 1);
    try {
      await addBalancerPool(provider, tokenCache, edges, stats, vault, vaultAddress, poolId, poolAddress, latestBlock);
      count += 1;
    } catch {
      stats.rejectedMetadata += 1;
    }
  }

  // Scan only the incremental block range for newly registered pools.
  const fromBlock = cache.getIncrementalFromBlock(cacheKey, latestBlock, lookback);
  if (fromBlock <= latestBlock) {
    const scan = await safeGetLogs(provider, { address: normalize(vaultAddress), topics: [topic] }, fromBlock, latestBlock, chunk);
    stats.rejectedLogScan += scan.rejected;
    for (const log of scan.logs) {
      if (count >= candidatePoolLimit) break;
      try {
        const parsed = iface.parseLog(log);
        const poolId = parsed?.args?.poolId as string;
        const poolAddress = normalize(parsed?.args?.poolAddress);
        if (seen.has(poolAddress.toLowerCase())) continue;
        seen.add(poolAddress.toLowerCase());
        newEntries.push(`${poolId}:${poolAddress}`);
        await addBalancerPool(provider, tokenCache, edges, stats, vault, vaultAddress, poolId, poolAddress, latestBlock);
        count += 1;
      } catch {
        stats.rejectedMetadata += 1;
      }
    }
  }

  cache.updateEntry(cacheKey, latestBlock, newEntries);
}

async function derivePrices(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, edges: Edge[]) {
  for (const token of tokenCache.values()) {
    const seed = trustedPriceSeed(token.address, token.symbol);
    if (seed) {
      token.priceUsd = seed.priceUsd;
      token.priceSource = seed.source;
      token.priceConfidence = seed.confidence;
    }
  }

  const derivationMinTvlUsd = numberEnv("TRUSTED_PRICE_DERIVATION_MIN_TVL_USD", 50_000);
  let changed = true;
  for (let pass = 0; pass < 4 && changed; pass += 1) {
    changed = false;
    for (const edge of edges) {
      if (edge.tvlUsd < derivationMinTvlUsd) continue;
      const tokenIn = tokenCache.get(edge.tokenIn.toLowerCase());
      const tokenOut = tokenCache.get(edge.tokenOut.toLowerCase());
      if (!tokenIn || !tokenOut) continue;
      if (tokenIn.priceUsd && !tokenOut.priceUsd && !isTrustedPricePinned(tokenOut) && edge.reserveIn > 0n && edge.reserveOut > 0n) {
        const derived = rawToFloat(edge.reserveIn, tokenIn.decimals) * tokenIn.priceUsd / rawToFloat(edge.reserveOut, tokenOut.decimals);
        if (!saneDerivedPrice(tokenOut.symbol, derived)) continue;
        tokenOut.priceUsd = derived;
        tokenOut.priceSource = "DEX_DERIVED";
        tokenOut.priceConfidence = edge.tvlUsd >= derivationMinTvlUsd ? "MEDIUM" : "LOW";
        changed = true;
      } else if (!tokenIn.priceUsd && !isTrustedPricePinned(tokenIn) && tokenOut.priceUsd && edge.reserveIn > 0n && edge.reserveOut > 0n) {
        const derived = rawToFloat(edge.reserveOut, tokenOut.decimals) * tokenOut.priceUsd / rawToFloat(edge.reserveIn, tokenIn.decimals);
        if (!saneDerivedPrice(tokenIn.symbol, derived)) continue;
        tokenIn.priceUsd = derived;
        tokenIn.priceSource = "DEX_DERIVED";
        tokenIn.priceConfidence = edge.tvlUsd >= derivationMinTvlUsd ? "MEDIUM" : "LOW";
        changed = true;
      }
    }
  }

  for (const edge of edges) {
    const tokenIn = tokenCache.get(edge.tokenIn.toLowerCase());
    const tokenOut = tokenCache.get(edge.tokenOut.toLowerCase());
    edge.tokenInPriceUsd = tokenIn?.priceUsd;
    edge.tokenOutPriceUsd = tokenOut?.priceUsd;
    if (tokenIn && tokenOut && edge.tvlUsd <= 0) {
      edge.tvlUsd = estimateTvlUsd(tokenIn, edge.reserveIn, tokenOut, edge.reserveOut);
    }
  }
}

async function discoverGraph(provider: ethers.JsonRpcProvider) {
  console.log("LIVE_CYCLE_PHASE|phase=DISCOVERY_GRAPH_START");
  const latestBlock = await provider.getBlockNumber();
  const tokenCache = new Map<string, TokenMeta>();
  const stats: DiscoveryStats = {
    discoveryUniverseConfigured: configuredDiscoveryUniverseTokenAddresses().length,
    discoveryUniverseLoaded: 0,
    flashloanAssets: 0,
    flashloanBalancerAssets: 0,
    flashloanAaveAssets: 0,
    tokens: 0,
    discoveredEdges: 0,
    discoveredPools: 0,
    rejectedDuplicateEdge: 0,
    rejectedMetadata: 0,
    rejectedZeroLiquidity: 0,
    rejectedUnsupportedInvariant: 0,
    rejectedLogScan: 0,
    rejectedPreSend: 0,
    preSendRefreshes: 0,
    preSendRejects: {},
    routeCyclesEnumerated: 0,
    routeCyclesRejectedLowTvl: 0,
    routeCyclesRejectedRepeatedPool: 0,
    routeCyclesRejectedNonFlashloan: 0,
    routeCyclesRejectedQuote: 0,
    quoteRejects: {},
    truncated: false,
    sourceCounts: {},
  };

  const cache = new DiscoveryCache();
  activePoolStateCache = new PoolStateCache();

  console.log(`LIVE_CYCLE_PHASE|phase=FLASHLOAN_LIQUIDITY_START|block=${latestBlock}`);
  const flashloanBook = await discoverFlashloanLiquidity(provider, tokenCache, latestBlock);
  const flashloanAssets = Array.from(new Map(flashloanBook.ordered.map((item) => [item.asset.address.toLowerCase(), item.asset])).values());
  const universeAssets = await loadDiscoveryUniverseAssets(provider, tokenCache);
  const discoveryAssets = universeAssets;
  stats.discoveryUniverseLoaded = discoveryAssets.length;
  stats.flashloanAssets = flashloanAssets.length;
  stats.flashloanBalancerAssets = flashloanBook.balancer.length;
  stats.flashloanAaveAssets = flashloanBook.aave.length;
  const edges = new Map<string, Edge>();
  console.log(`DISCOVERY_UNIVERSE|profile=${discoveryUniverseProfile()}|configured=${stats.discoveryUniverseConfigured}|loaded=${stats.discoveryUniverseLoaded}|assets=${discoveryAssets.map((asset) => `${asset.symbol}:${asset.address}`).join(",")}`);

  console.log(`LIVE_CYCLE_PHASE|phase=V2_DISCOVERY_START|discoveryAssets=${discoveryAssets.length}|flashloanAssets=${flashloanAssets.length}`);
  await discoverV2(provider, tokenCache, edges, stats, latestBlock, discoveryAssets, cache);
  console.log(`LIVE_CYCLE_PHASE|phase=V2_DISCOVERY_END|edges=${edges.size}`);
  console.log("LIVE_CYCLE_PHASE|phase=V3_DISCOVERY_START");
  await discoverV3(provider, tokenCache, edges, stats, latestBlock, discoveryAssets, cache);
  console.log(`LIVE_CYCLE_PHASE|phase=V3_DISCOVERY_END|edges=${edges.size}`);
  console.log("LIVE_CYCLE_PHASE|phase=ALGEBRA_DISCOVERY_START");
  await discoverAlgebra(provider, tokenCache, edges, stats, latestBlock, discoveryAssets, cache);
  console.log(`LIVE_CYCLE_PHASE|phase=ALGEBRA_DISCOVERY_END|edges=${edges.size}`);
  console.log("LIVE_CYCLE_PHASE|phase=CURVE_DISCOVERY_START");
  await discoverCurve(provider, tokenCache, edges, stats, latestBlock);
  console.log(`LIVE_CYCLE_PHASE|phase=CURVE_DISCOVERY_END|edges=${edges.size}`);
  console.log("LIVE_CYCLE_PHASE|phase=BALANCER_DISCOVERY_START");
  await discoverBalancer(provider, tokenCache, edges, stats, latestBlock, cache);
  console.log(`LIVE_CYCLE_PHASE|phase=BALANCER_DISCOVERY_END|edges=${edges.size}`);

  const candidateEdgeList = Array.from(edges.values());
  const deepSelection = selectDeepLiquidityEdges(candidateEdgeList);
  const edgeList = deepSelection.selected;
  stats.truncated = stats.truncated || edgeList.length < candidateEdgeList.length;
  console.log(`DISCOVERY_POOL_SELECTION|policy=LIQUIDITY_FIRST_BY_DEX|candidatePools=${deepSelection.seenPools.size}|selectedPools=${deepSelection.selectedPools.size}|candidateEdges=${candidateEdgeList.length}|selectedEdges=${edgeList.length}|scanMultiplier=${discoveryPoolScanMultiplier()}|liquidityFirst=${process.env.LIVE_DISCOVERY_LIQUIDITY_FIRST === "false" ? "false" : "true"}`);
  console.log(`LIVE_CYCLE_PHASE|phase=PRICE_DERIVATION_START|edges=${edgeList.length}`);
  await derivePrices(provider, tokenCache, edgeList);
  const maxStateAgeBlocks = intEnv("LIVE_ROUTE_MAX_STATE_AGE_BLOCKS", DEFAULT_ROUTE_MAX_STATE_AGE_BLOCKS);
  const liveEdges: Edge[] = [];
  console.log(`LIVE_CYCLE_PHASE|phase=PRESEND_REVALIDATION_START|edges=${edgeList.length}`);
  const revalidationBlock = await provider.getBlockNumber();
  const preSendLanes = intEnv("LIVE_PRESEND_REVALIDATION_LANES", intEnv("LIVE_DISCOVERY_CONCURRENCY", DEFAULT_DISCOVERY_CONCURRENCY));
  const preSendTimeoutMs = intEnv("LIVE_PRESEND_REVALIDATION_TIMEOUT_MS", intEnv("LIVE_RPC_CALL_TIMEOUT_MS", DEFAULT_RPC_CALL_TIMEOUT_MS) * 2);
  await runWithConcurrency(edgeList, preSendLanes, async (edge) => {
    const result: Awaited<ReturnType<typeof preSendRevalidate>> = await withTimeout(
      preSendRevalidate(provider, edge, maxStateAgeBlocks, revalidationBlock),
      preSendTimeoutMs,
      "PRE_SEND_REVALIDATION",
    ).catch((error) => ({ ok: false, error: error?.message || "PRE_SEND_REVALIDATION_FAILED" }));
    if (!result.ok) {
      stats.rejectedPreSend += 1;
      const reason = result.error || "UNKNOWN";
      stats.preSendRejects[reason] = (stats.preSendRejects[reason] || 0) + 1;
      return;
    }
    if (result.stateRefreshed) {
      stats.preSendRefreshes += 1;
      edge.stateBlock = result.currentBlock ?? revalidationBlock;
    }
    liveEdges.push(edge);
  });
  stats.tokens = tokenCache.size;
  stats.discoveredEdges = liveEdges.length;
  stats.discoveredPools = new Set(liveEdges.map((edge) => edge.poolAddress.toLowerCase())).size;
  for (const edge of liveEdges) activePoolStateCache.upsertEdge(edge, latestBlock);
  const stateHash = superStateHash(latestBlock, liveEdges);
  const stateCacheStats = activePoolStateCache.stats();
  console.log(`SUPER_STATE_SNAPSHOT|chainId=137|latestBlock=${latestBlock}|poolCountSeen=${new Set(edgeList.map((edge) => edge.poolAddress.toLowerCase())).size}|poolCountSupported=${stats.discoveredPools}|poolCountQuoteReady=${liveEdges.length}|executableEdges=${liveEdges.length}|trustedPrices=${Array.from(tokenCache.values()).filter((token) => token.priceUsd && token.priceConfidence !== "REJECTED").length}|stateHash=${stateHash}|cacheEntries=${stateCacheStats.entries}|cacheUpdated=${stateCacheStats.updated}`);
  console.log(`LIVE_CYCLE_PHASE|phase=DISCOVERY_GRAPH_END|liveEdges=${liveEdges.length}|tokens=${tokenCache.size}|stateHash=${stateHash}`);
  cache.save();
  activePoolStateCache.save();
  await activePoolStateCache.publishToRedis(stateHash, latestBlock);
  return { latestBlock, tokenCache, flashloanAssets, discoveryAssets, flashloanBook, edges: liveEdges, stats, stateHash, stateCacheStats };
}

async function quoteEdge(provider: ethers.JsonRpcProvider, edge: Edge, amountIn: bigint) {
  if (edge.invariant === "V2_CPMM") {
    return quoteV2Cpmm(amountIn, edge.reserveIn, edge.reserveOut, edge.feeBps);
  }
  if (edge.invariant === "V3_CONCENTRATED_LIQUIDITY") {
    return await quoteV3ExactInputSingle(provider, {
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      fee: edge.extra?.v3Fee || edge.feeBps * 100,
      amountIn,
    });
  }
  if (edge.invariant === "ALGEBRA_CONCENTRATED_LIQUIDITY") {
    return await quoteAlgebraExactInputSingle(provider, {
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      amountIn,
    });
  }
  if (edge.invariant === "CURVE_STABLE_SWAP") {
    if (edge.tokenInIndex === undefined || edge.tokenOutIndex === undefined) throw new Error("CURVE_INDEX_MISSING");
    return await quoteCurveGetDy(provider, {
      pool: edge.poolAddress,
      i: edge.tokenInIndex,
      j: edge.tokenOutIndex,
      amountIn,
      indexType: edge.extra?.curveIndexType || "int128",
    });
  }
  if (edge.invariant === "BALANCER_WEIGHTED") {
    if (!edge.extra?.balancerWeightIn || !edge.extra?.balancerWeightOut || edge.extra?.balancerSwapFeeBps === undefined) {
      throw new Error("BALANCER_WEIGHT_DATA_MISSING");
    }
    return quoteBalancerWeighted(amountIn, {
      balanceIn: edge.reserveIn,
      balanceOut: edge.reserveOut,
      weightIn: edge.extra.balancerWeightIn,
      weightOut: edge.extra.balancerWeightOut,
      swapFeeBps: edge.extra.balancerSwapFeeBps,
    });
  }
  if (edge.invariant === "STABLE_SWAP") {
    if (edge.tokenInIndex === undefined || edge.tokenOutIndex === undefined) throw new Error("STABLE_SWAP_INDEX_MISSING");
    return await quoteStableSwapGetDy(provider, {
      pool: edge.poolAddress,
      i: edge.tokenInIndex,
      j: edge.tokenOutIndex,
      amountIn,
    });
  }
  throw new Error(`UNSUPPORTED_INVARIANT:${edge.invariant}`);
}

function buildStepCalldata(edge: Edge, amountIn: bigint, minAmountOut: bigint, targetContract: string, deadline: number) {
  if (edge.invariant === "V2_CPMM") {
    return buildV2SwapCalldata(amountIn, minAmountOut, [edge.tokenIn, edge.tokenOut], targetContract, deadline);
  }
  if (edge.invariant === "V3_CONCENTRATED_LIQUIDITY") {
    return buildV3ExactInputSingleCalldata({
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      fee: edge.extra?.v3Fee || edge.feeBps * 100,
      receiver: targetContract,
      deadline,
      amountIn,
      minAmountOut,
    });
  }
  if (edge.invariant === "ALGEBRA_CONCENTRATED_LIQUIDITY") {
    return buildAlgebraExactInputSingleCalldata({
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      receiver: targetContract,
      deadline,
      amountIn,
      minAmountOut,
    });
  }
  if (edge.invariant === "CURVE_STABLE_SWAP") {
    return buildCurveRouterExchangeCalldata({
      pool: edge.poolAddress,
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      amountIn,
      minAmountOut,
      receiver: targetContract,
    });
  }
  if (edge.invariant === "BALANCER_WEIGHTED") {
    if (!edge.poolId) throw new Error("BALANCER_POOL_ID_MISSING");
    return buildBalancerSingleSwapCalldata({
      poolId: edge.poolId,
      tokenIn: edge.tokenIn,
      tokenOut: edge.tokenOut,
      amountIn,
      minAmountOut,
      sender: targetContract,
      receiver: targetContract,
      deadline,
    });
  }
  if (edge.invariant === "STABLE_SWAP") {
    if (edge.tokenInIndex === undefined || edge.tokenOutIndex === undefined) throw new Error("STABLE_SWAP_INDEX_MISSING");
    return buildStableSwapExchangeCalldata({
      i: edge.tokenInIndex,
      j: edge.tokenOutIndex,
      amountIn,
      minAmountOut,
    });
  }
  throw new Error(`CALldata_UNSUPPORTED_INVARIANT:${edge.invariant}`);
}

function reverseEdge(edge: Edge): Edge {
  const extra = edge.extra ? { ...edge.extra } : undefined;
  if (extra?.balancerWeightIn !== undefined || extra?.balancerWeightOut !== undefined) {
    const weightIn = extra.balancerWeightIn;
    extra.balancerWeightIn = extra.balancerWeightOut;
    extra.balancerWeightOut = weightIn;
  }
  return {
    ...edge,
    edgeId: `${edge.dexId}:${edge.poolAddress}:${edge.tokenOutSymbol}->${edge.tokenInSymbol}:reverse`,
    tokenIn: edge.tokenOut,
    tokenOut: edge.tokenIn,
    tokenInIndex: edge.tokenOutIndex,
    tokenOutIndex: edge.tokenInIndex,
    tokenInDecimals: edge.tokenOutDecimals,
    tokenOutDecimals: edge.tokenInDecimals,
    tokenInSymbol: edge.tokenOutSymbol,
    tokenOutSymbol: edge.tokenInSymbol,
    tokenInPriceUsd: edge.tokenOutPriceUsd,
    tokenOutPriceUsd: edge.tokenInPriceUsd,
    reserveIn: edge.reserveOut,
    reserveOut: edge.reserveIn,
    extra,
  };
}

function buildAdjacency(edges: Edge[]) {
  const byIn = new Map<string, Edge[]>();
  for (const edge of edges) {
    const key = edge.tokenIn.toLowerCase();
    const list = byIn.get(key) || [];
    list.push(edge);
    byIn.set(key, list);
  }
  for (const list of byIn.values()) {
    list.sort((a, b) => b.tvlUsd - a.tvlUsd);
  }
  return byIn;
}

function enumerateCycles(flashloanAssets: TokenMeta[], edges: Edge[], stats: DiscoveryStats) {
  const byIn = buildAdjacency(edges);
  const maxHops = Math.max(2, Math.min(4, intEnv("MAX_ROUTE_HOPS", 4)));
  const maxCycles = intEnv("MAX_DYNAMIC_ROUTES", intEnv("LIVE_ROUTE_MAX_CYCLES", DEFAULT_ROUTE_MAX_CYCLES));
  const minPoolTvlUsd = minRoutePoolTvlUsd();
  const cycles: Edge[][] = [];
  const flashSet = new Set(flashloanAssets.map((asset) => asset.address.toLowerCase()));

  for (const asset of flashloanAssets) {
    const walk = (currentToken: string, route: Edge[], usedPools: Set<string>) => {
      if (maxCycles !== undefined && cycles.length >= maxCycles) {
        stats.truncated = true;
        return;
      }
      if (route.length >= 2 && sameAddress(currentToken, asset.address)) {
        const lowestTvlUsd = routeLowestTvlUsd(route);
        if (lowestTvlUsd >= minPoolTvlUsd) {
          cycles.push([...route]);
          stats.routeCyclesEnumerated += 1;
        } else {
          stats.routeCyclesRejectedLowTvl += 1;
        }
      }
      if (route.length >= maxHops) return;
      for (const edge of byIn.get(currentToken.toLowerCase()) || []) {
        if (usedPools.has(edge.poolAddress.toLowerCase())) {
          stats.routeCyclesRejectedRepeatedPool += 1;
          continue;
        }
        if (route.length + 1 === maxHops && !sameAddress(edge.tokenOut, asset.address)) {
          continue;
        }
        usedPools.add(edge.poolAddress.toLowerCase());
        route.push(edge);
        walk(edge.tokenOut, route, usedPools);
        route.pop();
        usedPools.delete(edge.poolAddress.toLowerCase());
      }
    };
    if (!flashSet.has(asset.address.toLowerCase())) {
      stats.routeCyclesRejectedNonFlashloan += 1;
      continue;
    }
    if (requireUsdcSettlement() && !isUsdcSettlementAsset(asset)) {
      stats.routeCyclesRejectedNonFlashloan += 1;
      continue;
    }
    walk(asset.address, [], new Set());
  }
  return cycles;
}

function edgeBuySpotPrice(edge: Edge) {
  const amountIn = rawToFloat(edge.reserveIn, edge.tokenInDecimals);
  const amountOut = rawToFloat(edge.reserveOut, edge.tokenOutDecimals);
  return amountOut > 0 ? amountIn / amountOut : Number.POSITIVE_INFINITY;
}

function edgeSellSpotPrice(edge: Edge) {
  const amountIn = rawToFloat(edge.reserveIn, edge.tokenInDecimals);
  const amountOut = rawToFloat(edge.reserveOut, edge.tokenOutDecimals);
  return amountIn > 0 ? amountOut / amountIn : Number.NEGATIVE_INFINITY;
}

function edgeVenueKey(edge: Edge) {
  return `${edge.dexId}:${edge.poolAddress.toLowerCase()}`;
}

function edgeDestinationIdentity(edge: Edge) {
  return [
    edge.dexId,
    edge.poolId || edge.poolAddress,
    edge.extra?.v3Fee ?? "",
    edge.tokenIn,
    edge.tokenOut,
  ].join(":").toLowerCase();
}

function rawSpreadForRoute(route: Edge[]) {
  const buyEdge = route[0];
  const sellEdge = route.find((edge, index) =>
    index > 0 &&
    sameAddress(edge.tokenIn, buyEdge.tokenOut) &&
    sameAddress(edge.tokenOut, buyEdge.tokenIn));
  if (!buyEdge || !sellEdge) {
    return {
      buyPrice: undefined,
      sellPrice: undefined,
      rawSpreadDelta: undefined,
      rawSpreadBps: undefined,
      direction: "NO_DIRECT_REVERSE_LEG" as const,
    };
  }
  const buyPrice = edgeBuySpotPrice(buyEdge);
  const sellPrice = edgeSellSpotPrice(sellEdge);
  const rawSpreadDelta = sellPrice - buyPrice;
  const rawSpreadBps = buyPrice > 0 ? (rawSpreadDelta / buyPrice) * 10_000 : Number.NEGATIVE_INFINITY;
  return {
    buyPrice,
    sellPrice,
    rawSpreadDelta,
    rawSpreadBps,
    direction: rawSpreadDelta > 0 ? "BUY_LT_SELL" as const : "BUY_GTE_SELL" as const,
  };
}

function isDirectBuySellRoute(route: Edge[]) {
  if (route.length !== 2) return false;
  const [buyEdge, sellEdge] = route;
  return Boolean(
    buyEdge &&
    sellEdge &&
    sameAddress(sellEdge.tokenIn, buyEdge.tokenOut) &&
    sameAddress(sellEdge.tokenOut, buyEdge.tokenIn) &&
    edgeLiquidityVenueKey(sellEdge) !== edgeLiquidityVenueKey(buyEdge),
  );
}

function buildRawSpreadRoutes(flashloanAssets: TokenMeta[], edges: Edge[]): RawSpreadBuild {
  const minPoolTvlUsd = minRoutePoolTvlUsd();
  const routes: RawSpreadRoute[] = [];
  const flashSet = new Set(flashloanAssets.map((asset) => asset.address.toLowerCase()));
  const topNBuysPerPair = rawSpreadTopNBuysPerPair();
  const topNSellsPerPair = rawSpreadTopNSellsPerPair();
  const build: RawSpreadBuild = {
    routes,
    rejectedSameDestination: 0,
    rejectedSamePoolVenue: 0,
    matrixPairs: 0,
    matrixPrunedByTopN: 0,
    topNBuysPerPair,
    topNSellsPerPair,
    rejectedInvalidPrice: 0,
    rejectedNonPositiveSpread: 0,
    rejectedLowTvl: 0,
    groupsWithoutSell: 0,
  };

  for (const asset of flashloanAssets) {
    if (!flashSet.has(asset.address.toLowerCase())) {
      continue;
    }
    if (requireUsdcSettlement() && !isUsdcSettlementAsset(asset)) {
      continue;
    }

    const buyByTokenOut = new Map<string, Edge[]>();
    const sellByTokenIn = new Map<string, Edge[]>();
    for (const edge of edges) {
      if (sameAddress(edge.tokenIn, asset.address) && !sameAddress(edge.tokenOut, asset.address)) {
        const list = buyByTokenOut.get(edge.tokenOut.toLowerCase()) || [];
        list.push(edge);
        buyByTokenOut.set(edge.tokenOut.toLowerCase(), list);
      }
      if (sameAddress(edge.tokenOut, asset.address) && !sameAddress(edge.tokenIn, asset.address)) {
        const list = sellByTokenIn.get(edge.tokenIn.toLowerCase()) || [];
        list.push(edge);
        sellByTokenIn.set(edge.tokenIn.toLowerCase(), list);
      }
    }

    for (const [token1, buyEdges] of buyByTokenOut) {
      const sellEdges = sellByTokenIn.get(token1) || [];
      if (sellEdges.length === 0) {
        build.groupsWithoutSell += 1;
        continue;
      }
      const sortedBuyEdges = [...buyEdges]
        .filter((edge) => Number.isFinite(edgeBuySpotPrice(edge)))
        .sort((a, b) => edgeBuySpotPrice(a) - edgeBuySpotPrice(b) || b.tvlUsd - a.tvlUsd || edgeVenueKey(a).localeCompare(edgeVenueKey(b)));
      const sortedSellEdges = [...sellEdges]
        .filter((edge) => Number.isFinite(edgeSellSpotPrice(edge)))
        .sort((a, b) => edgeSellSpotPrice(b) - edgeSellSpotPrice(a) || b.tvlUsd - a.tvlUsd || edgeVenueKey(a).localeCompare(edgeVenueKey(b)));

      const matrixBuyEdges = topNBuysPerPair > 0 ? sortedBuyEdges.slice(0, topNBuysPerPair) : sortedBuyEdges;
      const matrixSellEdges = topNSellsPerPair > 0 ? sortedSellEdges.slice(0, topNSellsPerPair) : sortedSellEdges;
      build.matrixPairs += 1;
      build.matrixPrunedByTopN += Math.max(
        0,
        (sortedBuyEdges.length * sortedSellEdges.length) - (matrixBuyEdges.length * matrixSellEdges.length),
      );

      for (const buyEdge of matrixBuyEdges) {
        for (const sellEdge of matrixSellEdges) {
          if (edgeLiquidityVenueKey(sellEdge) === edgeLiquidityVenueKey(buyEdge)) {
            build.rejectedSamePoolVenue += 1;
            continue;
          }
          if (edgeDestinationIdentity(sellEdge) === edgeDestinationIdentity(buyEdge)) {
            build.rejectedSameDestination += 1;
            continue;
          }
          const buyPrice = edgeBuySpotPrice(buyEdge);
          const sellPrice = edgeSellSpotPrice(sellEdge);
          if (!Number.isFinite(buyPrice) || !Number.isFinite(sellPrice) || buyPrice <= 0 || sellPrice <= 0) {
            build.rejectedInvalidPrice += 1;
            continue;
          }
          const rawSpreadDelta = sellPrice - buyPrice;
          const rawSpreadBps = (rawSpreadDelta / buyPrice) * 10_000;
          if (rawSpreadDelta <= 0) {
            build.rejectedNonPositiveSpread += 1;
            continue;
          }
          const route = [buyEdge, sellEdge];
          if (!isDirectBuySellRoute(route)) {
            build.rejectedInvalidPrice += 1;
            continue;
          }
          const lowestPoolTvlUsd = routeLowestTvlUsd(route);
          if (lowestPoolTvlUsd < minPoolTvlUsd) {
            build.rejectedLowTvl += 1;
            continue;
          }
          const capFromTvlUsd = lowestPoolTvlUsd * numberEnv("RISK_ALPHA_LIQUIDITY_FRACTION", 0.05);
          const poolStateCapRaw = routePoolStateCapRaw(route, asset);
          const poolStateCapUsd = poolStateCapRaw > 0n && asset.priceUsd
            ? rawToFloat(poolStateCapRaw, asset.decimals) * asset.priceUsd
            : Number.POSITIVE_INFINITY;
          const rawCapitalCapUsd = Math.min(capFromTvlUsd, poolStateCapUsd);
          const rawEstimatedGrossUsdAtCap = Number.isFinite(rawCapitalCapUsd)
            ? rawCapitalCapUsd * ((sellPrice / buyPrice) - 1)
            : 0;
          routes.push({
            route,
            flashloanAsset: asset,
            token1Symbol: buyEdge.tokenOutSymbol,
            token1Address: buyEdge.tokenOut,
            buyPrice,
            sellPrice,
            rawSpreadDelta,
            rawSpreadBps,
            lowestPoolTvlUsd,
            rawCapitalCapUsd,
            rawEstimatedGrossUsdAtCap,
            rawEstimatedGrossBpsAtCap: rawSpreadBps,
            buyVenue: `${buyEdge.venueName}:${buyEdge.poolId || buyEdge.poolAddress}`,
            sellVenue: `${sellEdge.venueName}:${sellEdge.poolId || sellEdge.poolAddress}`,
          });
        }
      }
    }
  }

  routes.sort((a, b) =>
    b.rawEstimatedGrossUsdAtCap - a.rawEstimatedGrossUsdAtCap ||
    b.rawSpreadBps - a.rawSpreadBps ||
    b.rawSpreadDelta - a.rawSpreadDelta ||
    a.buyPrice - b.buyPrice ||
    b.sellPrice - a.sellPrice ||
    b.lowestPoolTvlUsd - a.lowestPoolTvlUsd ||
    a.buyVenue.localeCompare(b.buyVenue) ||
    a.sellVenue.localeCompare(b.sellVenue));

  return build;
}

function rawSpreadRoutePrintLimit() {
  const explicit = optionalIntEnv("RAW_SPREAD_ROUTE_PRINT_LIMIT");
  return explicit === undefined || explicit <= 0 ? Number.POSITIVE_INFINITY : explicit;
}

function printRawSpreadRoutes(build: RawSpreadBuild, stageLimit: number | undefined) {
  console.log(
    `RAW_SPREAD_SUMMARY|policy=PRE_PROTOCOL_MATH_BUY_LT_SELL_ONLY|ranked=${build.routes.length}` +
    `|stageLimit=${stageLimit === undefined ? "ALL" : stageLimit}` +
    `|matrixPolicy=TOP_N_BUY_SELL_FALLBACK` +
    `|matrixPairs=${build.matrixPairs}` +
    `|topNBuysPerPair=${build.topNBuysPerPair === 0 ? "ALL" : build.topNBuysPerPair}` +
    `|topNSellsPerPair=${build.topNSellsPerPair === 0 ? "ALL" : build.topNSellsPerPair}` +
    `|matrixPrunedByTopN=${build.matrixPrunedByTopN}` +
    `|venueExclusivity=POOL_ADDRESS_UNIQUE_PER_ATOMIC_ROUTE` +
    `|rejectedSamePoolVenue=${build.rejectedSamePoolVenue}` +
    `|rejectedSameDestination=${build.rejectedSameDestination}` +
    `|rejectedInvalidPrice=${build.rejectedInvalidPrice}` +
    `|rejectedNonPositiveSpread=${build.rejectedNonPositiveSpread}` +
    `|rejectedLowTvl=${build.rejectedLowTvl}` +
    `|groupsWithoutSell=${build.groupsWithoutSell}`,
  );
  const printLimit = rawSpreadRoutePrintLimit();
  for (const [index, item] of build.routes.entries()) {
    if (index >= printLimit) {
      console.log(`RAW_SPREAD_PRINT_TRUNCATED|printed=${printLimit}|total=${build.routes.length}|set_RAW_SPREAD_ROUTE_PRINT_LIMIT_0_for_all=true`);
      break;
    }
    console.log([
      `RAW_SPREAD_RANK|rank=${index + 1}`,
      `flashloanAsset=${item.flashloanAsset.symbol}:${item.flashloanAsset.address}`,
      `token1=${item.token1Symbol}:${item.token1Address}`,
      `routeShape=LEG1_BUY_LEG2_SELL`,
      `leg1Action=BUY`,
      `leg1PayToken=${item.route[0].tokenInSymbol}:${item.route[0].tokenIn}`,
      `leg1BuyToken=${item.route[0].tokenOutSymbol}:${item.route[0].tokenOut}`,
      `leg1BuyPrice=${formatPrice(item.buyPrice)}`,
      `leg1BuyUnit=${item.route[0].tokenInSymbol}/${item.route[0].tokenOutSymbol}`,
      `leg1BuyVenue=${item.buyVenue}`,
      `leg1PoolKey=${edgeLiquidityVenueKey(item.route[0])}`,
      `leg2Action=SELL`,
      `leg2SellToken=${item.route[1].tokenInSymbol}:${item.route[1].tokenIn}`,
      `leg2ReceiveToken=${item.route[1].tokenOutSymbol}:${item.route[1].tokenOut}`,
      `leg2SellPrice=${formatPrice(item.sellPrice)}`,
      `leg2SellUnit=${item.route[1].tokenOutSymbol}/${item.route[1].tokenInSymbol}`,
      `leg2SellVenue=${item.sellVenue}`,
      `leg2PoolKey=${edgeLiquidityVenueKey(item.route[1])}`,
      `rawBuyPrice=${formatPrice(item.buyPrice)}`,
      `rawSellPrice=${formatPrice(item.sellPrice)}`,
      `rawSpreadDelta=${formatPrice(item.rawSpreadDelta)}`,
      `rawSpreadBps=${formatPrice(item.rawSpreadBps)}`,
      `rawCapitalCapUsd=${formatPrice(item.rawCapitalCapUsd)}`,
      `rawEstimatedGrossUsdAtCap=${formatPrice(item.rawEstimatedGrossUsdAtCap)}`,
      `rawRankPolicy=CAPACITY_ADJUSTED_GROSS_THEN_SPREAD`,
      `direction=BUY_LT_SELL`,
      `lowestPoolTvlUsd=${item.lowestPoolTvlUsd.toFixed(2)}`,
      `buyVenue=${item.buyVenue}`,
      `sellVenue=${item.sellVenue}`,
      `path=${item.route.map((edge) => edge.tokenInSymbol).concat(item.route[item.route.length - 1].tokenOutSymbol).join("->")}`,
      `venues=${item.route.map((edge) => `${edge.venueName}:${edge.invariant}`).join("->")}`,
    ].join("|"));
  }
}

function enumerateBuyLowSellHighRoutes(flashloanAssets: TokenMeta[], edges: Edge[], stats: DiscoveryStats) {
  const maxRoutes = intEnv("MAX_DYNAMIC_ROUTES", intEnv("LIVE_ROUTE_MAX_CYCLES", DEFAULT_ROUTE_MAX_CYCLES));
  const rawSpreadBuild = buildRawSpreadRoutes(flashloanAssets, edges);
  printRawSpreadRoutes(rawSpreadBuild, maxRoutes);

  stats.routeCyclesRejectedRepeatedPool += rawSpreadBuild.rejectedSameDestination;
  stats.routeCyclesRejectedRepeatedPool += rawSpreadBuild.rejectedSamePoolVenue;
  stats.routeCyclesRejectedLowTvl += rawSpreadBuild.rejectedLowTvl;
  stats.quoteRejects.RAW_SPREAD_INVALID_PRICE = (stats.quoteRejects.RAW_SPREAD_INVALID_PRICE || 0) + rawSpreadBuild.rejectedInvalidPrice;
  stats.quoteRejects.RAW_SPREAD_NON_POSITIVE = (stats.quoteRejects.RAW_SPREAD_NON_POSITIVE || 0) + rawSpreadBuild.rejectedNonPositiveSpread;

  if (maxRoutes !== undefined && rawSpreadBuild.routes.length > maxRoutes) {
    stats.truncated = true;
  }
  const selectedRoutes = maxRoutes === undefined ? rawSpreadBuild.routes : rawSpreadBuild.routes.slice(0, maxRoutes);
  console.log(`RAW_SPREAD_STAGE_SUMMARY|rankedAll=${rawSpreadBuild.routes.length}|stagedForProtocolQuote=${selectedRoutes.length}|maxDynamicRoutes=${maxRoutes === undefined ? "ALL" : maxRoutes}|stagePolicy=RAW_BUY_LT_SELL_THEN_PROTOCOL_QUOTE`);
  stats.routeCyclesEnumerated += selectedRoutes.length;
  return selectedRoutes.map((item) => item.route);
}

async function quoteCandidate(
  provider: ethers.JsonRpcProvider,
  tokenCache: Map<string, TokenMeta>,
  flashloanBook: Map<string, FlashloanLiquidity[]>,
  route: Edge[],
  targetContract: string,
  gasCostUsd: number,
  relayTipUsd: number,
  executorCostUsd: number,
  riskBufferUsd: number,
  minProfitUsd: number,
  balancerCapability?: BalancerC1Capability,
  laneId = 0,
) {
  const flashloanAsset = tokenCache.get(route[0].tokenIn.toLowerCase());
  if (!flashloanAsset) throw new Error("FLASHLOAN_TOKEN_METADATA_MISSING");
  if (useBuyLowSellHighToUsdceStrategy() && !isDirectBuySellRoute(route)) {
    throw new Error("DIRECT_BUY_SELL_ROUTE_REQUIRED");
  }
  if (requireUsdcSettlement() && !isUsdcSettlementAsset(flashloanAsset)) {
    throw new Error(`USDC_SETTLEMENT_ASSET_REQUIRED:${flashloanAsset.symbol}:${flashloanAsset.address}`);
  }
  const finalTokenOut = route[route.length - 1]?.tokenOut;
  if (requireUsdcSettlement() && (!finalTokenOut || !sameAddress(finalTokenOut, flashloanAsset.address))) {
    throw new Error("USDC_SETTLEMENT_ROUTE_NOT_CLOSED");
  }
  const allLiquidityOptions = rankFlashloanCapitalOptions(flashloanBook.get(flashloanAsset.address.toLowerCase()) || []);
  const liquidityOptions = rankFlashloanCapitalOptions(
    executableFlashloanOptions(allLiquidityOptions, balancerCapability),
  );
  if (liquidityOptions.length === 0) throw new Error("FLASHLOAN_LIQUIDITY_MISSING");
  const lowestPoolTvlUsd = routeLowestTvlUsd(route);
  if (!Number.isFinite(lowestPoolTvlUsd) || lowestPoolTvlUsd <= 0 || !flashloanAsset.priceUsd) {
    throw new Error("ROUTE_TVL_OR_PRICE_UNRESOLVED");
  }
  const rawSpread = rawSpreadForRoute(route);

  const alpha = numberEnv("RISK_ALPHA_LIQUIDITY_FRACTION", 0.05);
  const capFromTvlUsd = lowestPoolTvlUsd * alpha;
  const maxAmountFromTvl = floatToRaw(capFromTvlUsd / flashloanAsset.priceUsd, flashloanAsset.decimals);
  const maxAmountFromPoolState = routePoolStateCapRaw(route, flashloanAsset);
  const routeRiskCapRaw = maxAmountFromPoolState > 0n && maxAmountFromPoolState < maxAmountFromTvl
    ? maxAmountFromPoolState
    : maxAmountFromTvl;
  const routeDynamicCapUsd = rawToFloat(routeRiskCapRaw, flashloanAsset.decimals) * flashloanAsset.priceUsd;
  const routePoolStateCapUsd = maxAmountFromPoolState > 0n
    ? rawToFloat(maxAmountFromPoolState, flashloanAsset.decimals) * flashloanAsset.priceUsd
    : undefined;
  const sizingRule = "min(providerLiquidity, routeTvlRiskCap, routePoolStateReserveCap) then adaptive USD+linear quote ladder max net output";
  const preferredCapitalOption = liquidityOptions[0];
  const maxFlashloanAmount = preferredCapitalOption.liquidity;
  const maxAmountIn = routeRiskCapRaw < maxFlashloanAmount ? routeRiskCapRaw : maxFlashloanAmount;
  const minAmountIn = floatToRaw(positiveNumberEnv("MIN_FLASHLOAN_USD", 0) / flashloanAsset.priceUsd, flashloanAsset.decimals);
  const belowMinFlashloanSizeReason = minAmountIn > 0n && maxAmountIn < minAmountIn
    ? `FLASHLOAN_SIZE_BELOW_MIN:max=${maxAmountIn}:min=${minAmountIn}:lowestPoolTvlUsd=${lowestPoolTvlUsd.toFixed(6)}:routeDynamicCapUsd=${routeDynamicCapUsd.toFixed(6)}`
    : "";
  const allowBelowMinDiagnostic = Boolean(belowMinFlashloanSizeReason) &&
    useBuyLowSellHighToUsdceStrategy() &&
    allowDiagnosticRankingBelowMinFlashloan();
  const allowRouteCapSoftMin = Boolean(belowMinFlashloanSizeReason) &&
    allowRouteCapBelowMinFlashloan() &&
    routeRiskCapRaw > 0n;
  const sizingMinAmountIn = allowBelowMinDiagnostic || allowRouteCapSoftMin ? 0n : minAmountIn;

  if (maxAmountIn <= 0n) throw new Error("MAX_FLASHLOAN_SIZE_ZERO");
  if (belowMinFlashloanSizeReason && !allowBelowMinDiagnostic && !allowRouteCapSoftMin) {
    throw new Error(belowMinFlashloanSizeReason);
  }

  const ladderSteps = intEnv("OPTIMAL_SIZING_LADDER_STEPS", 10);
  const sizingAmounts = buildAdaptiveSizingAmounts(flashloanAsset, sizingMinAmountIn, maxAmountIn, ladderSteps);
  if (sizingAmounts.length === 0) {
    throw new Error("OPTIMAL_SIZING_FAILED: No valid adaptive size found in ladder.");
  }
  const declinePatience = Math.max(0, intEnv("OPTIMAL_SIZING_DECLINE_PATIENCE", 3));
  let declineStreak = 0;
  let bestResult: Omit<Candidate, "routeId" | "rank"> | null = null;

  for (const amountIn of sizingAmounts) {
    if (amountIn <= 0n) continue;

    const flashloanLiquidity = liquidityOptions.find((item) => item.liquidity >= amountIn) || preferredCapitalOption;
    if (amountIn > flashloanLiquidity.liquidity) continue; // Not enough capital for this step

    try {
      const flashFeeRaw = (amountIn * flashloanLiquidity.feeBps) / 10000n;
      const slippageBps = BigInt(Math.floor(numberEnv("SLIPPAGE_BPS", 10)));
      const deadline = Math.floor(Date.now() / 1000) + intEnv("EXECUTION_SUBMISSION_EXPIRY_SECONDS", 300);

      let currentAmount = amountIn;
      const steps: RouteQuoteStep[] = [];
      for (const edge of route) {
        const stepReserveCap = edgeInputReserveCapRaw(edge);
        if (currentAmount > stepReserveCap) {
          throw new Error(`POOL_STATE_STEP_CAP_EXCEEDED:${edge.tokenInSymbol}:amount=${currentAmount}:cap=${stepReserveCap}:reserve=${edge.reserveIn}:maxReserveFractionBps=${routeMaxPoolReserveFractionBps()}`);
        }
        const amountOut = await quoteEdge(provider, edge, currentAmount);
        if (amountOut <= 0n) throw new Error("QUOTE_ZERO_OUTPUT");
        const minAmountOut = bpsMin(amountOut, slippageBps);
        const calldata = buildStepCalldata(edge, currentAmount, minAmountOut, targetContract, deadline);
        steps.push({ edge, amountIn: currentAmount, amountOut, minAmountOut, calldata });
        currentAmount = amountOut;
      }

      const amountOut = currentAmount;
      const grossProfitRaw = amountOut - amountIn;
      const grossProfitUsd = quoteUsd(grossProfitRaw, flashloanAsset);
      const flashFeeUsd = quoteUsd(flashFeeRaw, flashloanAsset);
      const breakEvenGrossUsd = flashFeeUsd === undefined
        ? undefined
        : flashFeeUsd + gasCostUsd + relayTipUsd + executorCostUsd + riskBufferUsd;
      const netProfitUsd = grossProfitUsd === undefined || flashFeeUsd === undefined
        ? undefined
        : grossProfitUsd - breakEvenGrossUsd!;
      const grossProfitCoverageRatio = grossProfitUsd !== undefined && breakEvenGrossUsd !== undefined && breakEvenGrossUsd > 0
        ? grossProfitUsd / breakEvenGrossUsd
        : undefined;
      const gasAdjustedDeficitUsd = netProfitUsd === undefined ? undefined : Math.max(0, -netProfitUsd);

      const priorBestNetUsd = bestResult?.netProfitUsd;
      const isDecline = priorBestNetUsd !== undefined && netProfitUsd !== undefined && netProfitUsd < priorBestNetUsd;
      declineStreak = isDecline ? declineStreak + 1 : 0;
      if (
        declinePatience > 0 &&
        declineStreak >= declinePatience &&
        priorBestNetUsd !== undefined &&
        priorBestNetUsd > 0
      ) {
        break;
      }

      if (!bestResult || (netProfitUsd !== undefined && netProfitUsd > bestResult.netProfitUsd!)) {
        bestResult = {
          status: "REJECTED_NO_PROFIT",
          flashloanAsset,
          flashloanLiquidity,
          flashloanProviderExecutable: flashloanProviderExecutable(flashloanLiquidity, balancerCapability),
          flashloanProviderReason: flashloanProviderReason(flashloanLiquidity, balancerCapability),
          providerLiquidityRaw: flashloanLiquidity.liquidity,
          routeRiskCapRaw,
          routeTvlRiskCapRaw: maxAmountFromTvl,
          routePoolStateCapRaw: maxAmountFromPoolState,
          maxApplicableCapitalRaw: maxAmountIn,
          minFlashloanRaw: minAmountIn,
          routeDynamicCapUsd,
          routePoolStateCapUsd,
          routeMaxPoolReserveFractionBps: routeMaxPoolReserveFractionBps(),
          sizingRule,
          sizeSearchCandidates: sizingAmounts.length,
          capitalLimitedBy: maxFlashloanAmount <= routeRiskCapRaw
            ? "PROVIDER_LIQUIDITY"
            : maxAmountFromPoolState > 0n && maxAmountFromPoolState <= maxAmountFromTvl
              ? "POOL_STATE_CAP"
              : "ROUTE_TVL_RISK_CAP",
          rawLeg1BuyPrice: rawSpread.buyPrice,
          rawLeg2SellPrice: rawSpread.sellPrice,
          rawSpreadDelta: rawSpread.rawSpreadDelta,
          rawSpreadBps: rawSpread.rawSpreadBps,
          rawSpreadDirection: rawSpread.direction,
          path: route.map((edge) => tokenCache.get(edge.tokenIn.toLowerCase())).filter(Boolean) as TokenMeta[],
          steps,
          amountIn,
          amountOut,
          grossProfitRaw,
          grossProfitUsd,
          gasCostUsd,
          gasCostInAssetRaw: 0n,
          relayTipUsd,
          relayTipInAssetRaw: 0n,
          executorCostUsd,
          executorCostInAssetRaw: 0n,
          riskBufferUsd,
          riskBufferInAssetRaw: 0n,
          breakEvenGrossUsd,
          grossProfitCoverageRatio,
          gasAdjustedDeficitUsd,
          actualProfitRaw: 0n,
          flashFeeRaw,
          flashFeeUsd,
          netProfitUsd,
          lowestPoolTvlUsd,
          rejectionReason: "NONE",
        };
      }
    } catch (error) {
      // If a step fails, it might be due to slippage or math issues at that size.
      // We can break here as larger sizes are unlikely to succeed.
      break;
    }
  }

  if (!bestResult) {
    throw new Error("OPTIMAL_SIZING_FAILED: No valid size found in ladder.");
  }

  // Re-check flashloan provider compatibility with the best found size
  const flashloanLiquidity = liquidityOptions.find((item) => item.liquidity >= bestResult!.amountIn) || liquidityOptions[0];

  if (bestResult.amountIn > flashloanLiquidity.liquidity) {
    throw new Error("INSUFFICIENT_LIQUIDITY_FOR_OPTIMAL_SIZE");
  }
  bestResult.flashloanLiquidity = flashloanLiquidity;

  // Build invariant-check inputs.  Gas, relay, executor, and risk costs are converted from USD
  // to flashloan-asset raw units so that the YIELD_INVARIANT can compare them
  // against on-chain amounts in the same denomination.
  // Note: flashloanAsset.priceUsd is guaranteed > 0 by the ROUTE_TVL_OR_PRICE_UNRESOLVED
  // guard above; the explicit check here prevents the fallback from silently masking
  // unprofitable routes if this function is ever reached with missing price data.
  const assetPriceUsd = flashloanAsset.priceUsd;
  if (!assetPriceUsd || assetPriceUsd <= 0) {
    throw new Error("FLASHLOAN_ASSET_PRICE_UNAVAILABLE: cannot convert route costs to asset units");
  }
  const gasCostInAssetRaw = floatToRaw(gasCostUsd / assetPriceUsd, flashloanAsset.decimals);
  const relayTipInAssetRaw = floatToRaw(relayTipUsd / assetPriceUsd, flashloanAsset.decimals);
  const executorCostInAssetRaw = floatToRaw(executorCostUsd / assetPriceUsd, flashloanAsset.decimals);
  const riskBufferInAssetRaw = floatToRaw(riskBufferUsd / assetPriceUsd, flashloanAsset.decimals);
  bestResult.gasCostInAssetRaw = gasCostInAssetRaw;
  bestResult.relayTipInAssetRaw = relayTipInAssetRaw;
  bestResult.executorCostInAssetRaw = executorCostInAssetRaw;
  bestResult.riskBufferInAssetRaw = riskBufferInAssetRaw;
  bestResult.actualProfitRaw =
    bestResult.amountOut -
    bestResult.amountIn -
    bestResult.flashFeeRaw -
    gasCostInAssetRaw -
    relayTipInAssetRaw -
    executorCostInAssetRaw -
    riskBufferInAssetRaw;

  const invariantSteps: QuotedRouteStep[] = bestResult.steps.map((s) => ({
    venueId: s.edge.edgeId,
    poolKey: edgeLiquidityVenueKey(s.edge),
    tokenIn: s.edge.tokenIn,
    tokenOut: s.edge.tokenOut,
    amountIn: s.amountIn,
    amountOut: s.amountOut,
  }));

  const routeCosts: RouteCostsInAsset = {
    flashloanFeeRaw: bestResult.flashFeeRaw,
    gasCostInAssetRaw,
    relayTipInAssetRaw,
    executorCostInAssetRaw,
    riskBufferInAssetRaw,
  };

  // Enforce all execution invariants. Any violation causes this route to
  // be discarded as REJECTED_INVARIANT_VIOLATION rather than broadcast.
  let status: Candidate["status"] = "EXECUTABLE_PROFIT_CANDIDATE";
  let rejectionReason = "NONE";

  try {
    enforceExecutionInvariants(invariantSteps, routeCosts);
    // Additional threshold guard: net USD profit must meet the configured minimum.
    if (bestResult.netProfitUsd === undefined || bestResult.netProfitUsd < minProfitUsd) {
      status = "REJECTED_NO_PROFIT";
      rejectionReason = `NET_PROFIT_BELOW_MIN:${bestResult.netProfitUsd === undefined ? "UNPRICED" : bestResult.netProfitUsd.toFixed(6)}<${minProfitUsd}`;
    }
  } catch (err) {
    status = "REJECTED_ROUTE_INVALID";
    if (err instanceof InvariantViolationError) {
      rejectionReason = `${err.invariant}:${err.detail}`;
    } else {
      rejectionReason = `INVARIANT_CHECK_FAILED:${err instanceof Error ? err.message : String(err)}`;
    }
  }

  if (allowBelowMinDiagnostic && !allowRouteCapSoftMin) {
    status = "REJECTED_ROUTE_INVALID";
    rejectionReason = rejectionReason && rejectionReason !== "NONE"
      ? `${belowMinFlashloanSizeReason};${rejectionReason}`
      : belowMinFlashloanSizeReason;
  }

  if (!bestResult.flashloanProviderExecutable) {
    status = "REJECTED_ROUTE_INVALID";
    rejectionReason = rejectionReason && rejectionReason !== "NONE"
      ? `${bestResult.flashloanProviderReason};${rejectionReason}`
      : bestResult.flashloanProviderReason;
  }

  return { ...bestResult, status, rejectionReason, routeId: "" };
}

async function rankCandidates(provider: ethers.JsonRpcProvider, tokenCache: Map<string, TokenMeta>, flashloanBook: Map<string, FlashloanLiquidity[]>, flashloanAssets: TokenMeta[], edges: Edge[], stats: DiscoveryStats, targetContract: string) {
  const strategyPolicy = buildStrategyFlashloanPolicy(flashloanAssets);
  const balancerCapability = await verifyBalancerC1Capability(provider, targetContract);
  const settlementAssets = strategyPolicy.settlementAssets;
  const executableCandidateFlashloanAssets = strategyPolicy.atomicCandidateSeedAssets.filter((asset) => hasExecutableMinFlashloanCapital(asset, flashloanBook, balancerCapability));
  const diagnosticCandidateFlashloanAssets = useBuyLowSellHighToUsdceStrategy() && allowDiagnosticRankingBelowMinFlashloan()
    ? strategyPolicy.atomicCandidateSeedAssets.filter((asset) => hasRankableMinFlashloanCapital(asset, flashloanBook) || hasAnyExecutableFlashloanCapital(asset, flashloanBook, balancerCapability))
    : executableCandidateFlashloanAssets;
  const candidateFlashloanAssets = diagnosticCandidateFlashloanAssets;
  const cycles = useBuyLowSellHighToUsdceStrategy()
    ? enumerateBuyLowSellHighRoutes(candidateFlashloanAssets, edges, stats)
    : enumerateCycles(candidateFlashloanAssets, edges, stats);
  const gasPrice = await provider.getFeeData().then((fee) => fee.gasPrice || 0n).catch(() => 0n);
  const nativeUsd = nativeTokenUsd();
  const estimatedGasUnits = BigInt(intEnv("ESTIMATED_GAS_UNITS", 450000));
  const gasCostUsd = Number(estimatedGasUnits * gasPrice) / 1e18 * nativeUsd;
  // Validator / relay / MEV tip cost in USD. RELAY_TIP_USD is canonical;
  // BRIBES_USD / BRIBES_WEI are retained as backward-compatible aliases.
  const relayTipWei = BigInt(process.env.RELAY_TIP_WEI || process.env.BRIBES_WEI || "0");
  const relayTipUsd = process.env.RELAY_TIP_USD
    ? numberEnv("RELAY_TIP_USD", 0)
    : process.env.BRIBES_USD
      ? numberEnv("BRIBES_USD", 0)
      : Number(relayTipWei) / 1e18 * nativeUsd;
  const executorCostUsd = numberEnv("EXECUTOR_COST_USD", 0);
  const riskBufferUsd = numberEnv("RISK_BUFFER_USD", 0);
  const minProfitUsd = numberEnv("MIN_NET_PROFIT_USD", 5);
  const nonzeroUserCosts = [
    ["relayTipUsd", relayTipUsd],
    ["executorCostUsd", executorCostUsd],
    ["riskBufferUsd", riskBufferUsd],
  ].filter(([, value]) => Number(value) !== 0);
  const candidates: Candidate[] = [];
  const quoteLanes = intEnv("LIVE_QUOTE_LANES", DEFAULT_QUOTE_LANES);
  const leg1Helpers = Math.max(1, Math.floor(quoteLanes / 2));
  const leg2Helpers = Math.max(1, quoteLanes - leg1Helpers);
  console.log(`SETTLEMENT_POLICY|requireUsdc=${requireUsdcSettlement()}|settlementSymbols=${Array.from(settlementSymbols()).join(",")}|settlementAddresses=${Array.from(settlementAddressSet()).join(",")}|defaultFlashloanProvider=${defaultFlashloanProvider()}|balancerC1Supported=${balancerCapability.executable}|balancerC1OperatorEnabled=${balancerCapability.operatorEnabled}|balancerC1Reason=${balancerCapability.reason}|balancerCallbackSelector=${balancerCapability.callbackSelector}|settlementAssets=${formatAssetList(settlementAssets)}|candidateFlashloanAssets=${formatAssetList(candidateFlashloanAssets)}`);
  console.log(`FLASHLOAN_STRATEGY|mode=${strategyPolicy.mode}|shape=FLASHLOAN_BASKET_BUY_TOKEN1_LOW_SELL_TOKEN1_HIGH_USDCE|routeSelection=${useBuyLowSellHighToUsdceStrategy() ? "LOWEST_BUY_HIGHEST_SELL_DIRECT_PAIR" : "TVL_SORTED_CYCLE_WALK"}|finalSettlementAsset=${strategyPolicy.finalSettlementAsset}|capitalBasket=${formatAssetList(strategyPolicy.basketAssets)}|atomicCandidateSeedAssets=${formatAssetList(strategyPolicy.atomicCandidateSeedAssets)}|atomicMinCapitalFlashloanAssets=${formatAssetList(executableCandidateFlashloanAssets)}|diagnosticRankFlashloanAssets=${formatAssetList(diagnosticCandidateFlashloanAssets)}|deferredFlashloanAssets=${formatAssetList(strategyPolicy.deferredFlashloanAssets)}|deferredReason=${strategyPolicy.deferredReason}|diagnosticBelowMin=${allowDiagnosticRankingBelowMinFlashloan()}|c1C2StateLaw=C1_MUTATES_C2_RECOMPUTES_POST_STATE_ONLY`);
  console.log(`OBJECTIVE_COST_AUDIT|objective=ATOMIC_USDCE_SURPLUS_AFTER_FLASHLOAN_REPAYMENT|costs=${[
    formatCostFlag("gasCostUsd", gasCostUsd),
    formatCostFlag("relayTipUsd", relayTipUsd),
    formatCostFlag("executorCostUsd", executorCostUsd),
    formatCostFlag("riskBufferUsd", riskBufferUsd),
    formatCostFlag("minNetProfitUsd", minProfitUsd),
  ].join(",")}|nativeTokenUsd=${nativeUsd}|estimatedGasUnits=${estimatedGasUnits}|flashloanDefaultProvider=${defaultFlashloanProvider()}|balancerFeeBps=${numberEnv("BALANCER_FLASH_FEE_BPS", 0)}|aaveFeeBps=${numberEnv("FLASH_LOAN_FEE_BPS", 9)}|userCostConflict=${nonzeroUserCosts.length > 0 ? nonzeroUserCosts.map(([name, value]) => `${name}:${value}`).join(",") : "NONE"}|settlementConflict=${strategyPolicy.deferredFlashloanAssets.length > 0 ? "NON_USDCE_BASKET_ASSETS_DEFERRED_UNTIL_ATOMIC_REPAYMENT_CONVERSION" : "NONE"}`);
  console.log(`LANE_TEAM_SUMMARY|quoteLanes=${quoteLanes}|leg1Helpers=${leg1Helpers}|leg2PlusHelpers=${leg2Helpers}|cycles=${cycles.length}|dependency=LEG2_REQUIRES_LEG1_OUTPUT`);

  await runWithConcurrency(cycles.map((route, index) => ({ route, index })), quoteLanes, async ({ route, index }) => {
    try {
      const laneId = index % quoteLanes;
      candidates.push(await quoteCandidate(
        provider,
        tokenCache,
        flashloanBook,
        route,
        targetContract,
        gasCostUsd,
        relayTipUsd,
        executorCostUsd,
        riskBufferUsd,
        minProfitUsd,
        balancerCapability,
        laneId,
      ));
    } catch (error: any) {
      stats.routeCyclesRejectedQuote += 1;
      const reason = error?.message || "QUOTE_FAILED";
      const bucket = reason.split(":")[0] || reason;
      stats.quoteRejects[bucket] = (stats.quoteRejects[bucket] || 0) + 1;
    }
  });

  candidates.sort((a, b) => (b.netProfitUsd ?? Number.NEGATIVE_INFINITY) - (a.netProfitUsd ?? Number.NEGATIVE_INFINITY));
  let executableSlot = 0;
  candidates.forEach((candidate, index) => {
    candidate.rank = index + 1;
    candidate.routeId = `LIVE-${String(index + 1).padStart(6, "0")}`;
    if (candidate.status === "EXECUTABLE_PROFIT_CANDIDATE" && executableSlot < intEnv("C1_EXECUTABLE_LIMIT_PER_CYCLE", DEFAULT_C1_EXECUTABLE_LIMIT)) {
      executableSlot += 1;
      candidate.c1ExecutionEligible = true;
      candidate.c1ExecutionSlot = executableSlot;
    } else {
      candidate.c1ExecutionEligible = false;
    }
  });
  const topRouteDisplayLimit = intEnv("TOP_ROUTE_DISPLAY_LIMIT", DEFAULT_TOP_ROUTE_DISPLAY_LIMIT);
  const profitableCandidates = candidates.filter((candidate) => candidate.status === "EXECUTABLE_PROFIT_CANDIDATE");
  const stagedCandidates = profitableCandidates.slice(0, topRouteDisplayLimit);
  writeRankedCandidateDiagnostics(candidates, topRouteDisplayLimit);
  console.log(`PRESTAGE_RANKING|policy=RANK_BEFORE_STAGING_PROFITABLE_ONLY|rankedCandidates=${candidates.length}|profitableCandidates=${profitableCandidates.length}|stagedOpportunities=${stagedCandidates.length}|diagnosticRejected=${candidates.length - profitableCandidates.length}|minProfitUsd=${minProfitUsd}`);
  await publishOpportunitySnapshot(stagedCandidates.map(candidateToLedgerPayload), "live-cycle-rank-candidates");
  console.log(`STAGING_SUMMARY|source=live-cycle-rank-candidates|stagedOpportunities=${stagedCandidates.length}|rejectedDiagnosticsNotStaged=${candidates.length - stagedCandidates.length}`);
  const noRouteReason = useBuyLowSellHighToUsdceStrategy() && executableCandidateFlashloanAssets.length === 0 && candidateFlashloanAssets.length === 0
    ? "NO_ATOMIC_USDCE_FLASHLOAN_CAPITAL"
    : "NO_DYNAMIC_ROUTE_CANDIDATES";
  return { candidates, gasCostUsd, relayTipUsd, executorCostUsd, riskBufferUsd, minProfitUsd, noRouteReason };
}

function settlementSurplusRaw(candidate: Candidate) {
  return candidate.amountOut - candidate.amountIn - candidate.flashFeeRaw;
}

function actualProfitRaw(candidate: Candidate) {
  return candidate.actualProfitRaw;
}

function formatSignedUnits(raw: bigint, decimals: number) {
  return raw < 0n ? `-${ethers.formatUnits(-raw, decimals)}` : ethers.formatUnits(raw, decimals);
}

function formatPrice(value: number | undefined) {
  if (value === undefined || !Number.isFinite(value)) return "NA";
  return value.toPrecision(12);
}

function stepBuyPrice(step: RouteQuoteStep) {
  const amountIn = rawToFloat(step.amountIn, step.edge.tokenInDecimals);
  const amountOut = rawToFloat(step.amountOut, step.edge.tokenOutDecimals);
  return amountOut > 0 ? amountIn / amountOut : undefined;
}

function stepSellPrice(step: RouteQuoteStep) {
  const amountIn = rawToFloat(step.amountIn, step.edge.tokenInDecimals);
  const amountOut = rawToFloat(step.amountOut, step.edge.tokenOutDecimals);
  return amountIn > 0 ? amountOut / amountIn : undefined;
}

function routeLegPriceSummary(candidate: Candidate) {
  const leg1 = candidate.steps[0];
  const leg2 = candidate.steps[1];
  const reverseSellStepIndex = leg1
    ? candidate.steps.findIndex((step, index) =>
      index > 0 &&
      sameAddress(step.edge.tokenIn, leg1.edge.tokenOut) &&
      sameAddress(step.edge.tokenOut, leg1.edge.tokenIn))
    : -1;
  const reverseSellStep = reverseSellStepIndex >= 0 ? candidate.steps[reverseSellStepIndex] : undefined;
  const leg1BuyPrice = leg1 ? stepBuyPrice(leg1) : undefined;
  const leg2SellPrice = leg2 ? stepSellPrice(leg2) : undefined;
  const reverseSellPrice = reverseSellStep ? stepSellPrice(reverseSellStep) : undefined;
  return {
    routeShape: leg1 && leg2 ? "LEG1_BUY_LEG2_SELL" : "INVALID_ROUTE_SHAPE",
    leg1Action: "BUY",
    leg1BuyPrice,
    leg1BuyUnit: leg1 ? `${leg1.edge.tokenInSymbol}/${leg1.edge.tokenOutSymbol}` : "NA",
    leg1BuyVenue: leg1 ? `${leg1.edge.venueName}:${leg1.edge.poolAddress}` : "NA",
    leg1PayToken: leg1 ? `${leg1.edge.tokenInSymbol}:${leg1.edge.tokenIn}` : "NA",
    leg1BuyToken: leg1 ? `${leg1.edge.tokenOutSymbol}:${leg1.edge.tokenOut}` : "NA",
    leg1PoolKey: leg1 ? edgeLiquidityVenueKey(leg1.edge) : "NA",
    leg2Action: "SELL",
    leg2SellPrice,
    leg2SellUnit: leg2 ? `${leg2.edge.tokenOutSymbol}/${leg2.edge.tokenInSymbol}` : "NA",
    leg2SellVenue: leg2 ? `${leg2.edge.venueName}:${leg2.edge.poolAddress}` : "NA",
    leg2SellToken: leg2 ? `${leg2.edge.tokenInSymbol}:${leg2.edge.tokenIn}` : "NA",
    leg2ReceiveToken: leg2 ? `${leg2.edge.tokenOutSymbol}:${leg2.edge.tokenOut}` : "NA",
    leg2PoolKey: leg2 ? edgeLiquidityVenueKey(leg2.edge) : "NA",
    reverseSellPrice,
    reverseSellUnit: reverseSellStep ? `${reverseSellStep.edge.tokenOutSymbol}/${reverseSellStep.edge.tokenInSymbol}` : "NA",
    reverseSellStep: reverseSellStepIndex >= 0 ? String(reverseSellStepIndex + 1) : "NONE",
    reverseSellVenue: reverseSellStep ? `${reverseSellStep.edge.venueName}:${reverseSellStep.edge.poolAddress}` : "NA",
    priceInvariantDirection: reverseSellPrice === undefined || leg1BuyPrice === undefined
      ? "NO_DIRECT_REVERSE_LEG"
      : leg1BuyPrice < reverseSellPrice
        ? "BUY_LT_SELL"
        : "BUY_GTE_SELL",
  };
}

function candidateToLedgerPayload(candidate: Candidate) {
  const surplusRaw = settlementSurplusRaw(candidate);
  const priceSummary = routeLegPriceSummary(candidate);
  return {
    routeId: candidate.routeId,
    payloadKind: "FLASHLOAN_INTEGRATED_C1_PAYLOADS",
    status: candidate.status,
    c1ExecutionEligible: Boolean(candidate.c1ExecutionEligible),
    c1ExecutionSlot: candidate.c1ExecutionSlot,
    pair: `${candidate.flashloanAsset.symbol} cycle`,
    path: routePath(candidate),
    venues: routeVenues(candidate),
    hops: candidate.steps.length,
    flashloanAsset: candidate.flashloanAsset.address,
    flashloanSymbol: candidate.flashloanAsset.symbol,
    settlementAsset: candidate.flashloanAsset.address,
    settlementSymbol: candidate.flashloanAsset.symbol,
    settlementSurplusRaw: surplusRaw,
    settlementSurplus: formatSignedUnits(surplusRaw, candidate.flashloanAsset.decimals),
    settlementPolicy: requireUsdcSettlement() ? "USDC_SURPLUS_AT_ATOMIC_SETTLEMENT" : "FLASHLOAN_ASSET_SURPLUS_AT_ATOMIC_SETTLEMENT",
    flashloanProvider: candidate.flashloanLiquidity.provider,
    flashloanSource: candidate.flashloanLiquidity.sourceCode,
    flashloanProviderExecutable: candidate.flashloanProviderExecutable,
    flashloanProviderReason: candidate.flashloanProviderReason,
    flashloanDefaultProvider: defaultFlashloanProvider(),
    providerLiquidityRaw: candidate.providerLiquidityRaw,
    providerLiquidity: ethers.formatUnits(candidate.providerLiquidityRaw, candidate.flashloanAsset.decimals),
    routeRiskCapRaw: candidate.routeRiskCapRaw,
    routeRiskCap: ethers.formatUnits(candidate.routeRiskCapRaw, candidate.flashloanAsset.decimals),
    routeTvlRiskCapRaw: candidate.routeTvlRiskCapRaw,
    routeTvlRiskCap: ethers.formatUnits(candidate.routeTvlRiskCapRaw, candidate.flashloanAsset.decimals),
    routePoolStateCapRaw: candidate.routePoolStateCapRaw,
    routePoolStateCap: ethers.formatUnits(candidate.routePoolStateCapRaw, candidate.flashloanAsset.decimals),
    routePoolStateCapUsd: candidate.routePoolStateCapUsd,
    maxApplicableCapitalRaw: candidate.maxApplicableCapitalRaw,
    maxApplicableCapital: ethers.formatUnits(candidate.maxApplicableCapitalRaw, candidate.flashloanAsset.decimals),
    minFlashloanRaw: candidate.minFlashloanRaw,
    minFlashloan: ethers.formatUnits(candidate.minFlashloanRaw, candidate.flashloanAsset.decimals),
    routeDynamicCapUsd: candidate.routeDynamicCapUsd,
    routeMaxPoolReserveFractionBps: candidate.routeMaxPoolReserveFractionBps,
    sizingRule: candidate.sizingRule,
    sizeSearchCandidates: candidate.sizeSearchCandidates,
    capitalLimitedBy: candidate.capitalLimitedBy,
    rawLeg1BuyPrice: formatPrice(candidate.rawLeg1BuyPrice),
    rawLeg2SellPrice: formatPrice(candidate.rawLeg2SellPrice),
    rawSpreadDelta: formatPrice(candidate.rawSpreadDelta),
    rawSpreadBps: formatPrice(candidate.rawSpreadBps),
    rawSpreadDirection: candidate.rawSpreadDirection || "NA",
    routeShape: priceSummary.routeShape,
    amountIn: candidate.amountIn,
    amountOut: candidate.amountOut,
    grossProfitRaw: candidate.grossProfitRaw,
    actualProfitRaw: actualProfitRaw(candidate),
    actualProfit: formatSignedUnits(actualProfitRaw(candidate), candidate.flashloanAsset.decimals),
    leg1Action: priceSummary.leg1Action,
    leg1PayToken: priceSummary.leg1PayToken,
    leg1BuyToken: priceSummary.leg1BuyToken,
    leg1BuyPrice: formatPrice(priceSummary.leg1BuyPrice),
    leg1BuyUnit: priceSummary.leg1BuyUnit,
    leg1BuyVenue: priceSummary.leg1BuyVenue,
    leg1PoolKey: priceSummary.leg1PoolKey,
    leg2Action: priceSummary.leg2Action,
    leg2SellToken: priceSummary.leg2SellToken,
    leg2ReceiveToken: priceSummary.leg2ReceiveToken,
    leg2SellPrice: formatPrice(priceSummary.leg2SellPrice),
    leg2SellUnit: priceSummary.leg2SellUnit,
    leg2SellVenue: priceSummary.leg2SellVenue,
    leg2PoolKey: priceSummary.leg2PoolKey,
    reverseSellPrice: formatPrice(priceSummary.reverseSellPrice),
    reverseSellUnit: priceSummary.reverseSellUnit,
    reverseSellStep: priceSummary.reverseSellStep,
    reverseSellVenue: priceSummary.reverseSellVenue,
    priceInvariantDirection: priceSummary.priceInvariantDirection,
    grossProfitUsd: candidate.grossProfitUsd,
    flashFeeUsd: candidate.flashFeeUsd,
    gasCostUsd: candidate.gasCostUsd,
    gasCostInAssetRaw: candidate.gasCostInAssetRaw,
    relayTipUsd: candidate.relayTipUsd,
    relayTipInAssetRaw: candidate.relayTipInAssetRaw,
    executorCostUsd: candidate.executorCostUsd,
    executorCostInAssetRaw: candidate.executorCostInAssetRaw,
    riskBufferUsd: candidate.riskBufferUsd,
    riskBufferInAssetRaw: candidate.riskBufferInAssetRaw,
    breakEvenGrossUsd: candidate.breakEvenGrossUsd,
    grossProfitCoverageRatio: candidate.grossProfitCoverageRatio,
    gasAdjustedDeficitUsd: candidate.gasAdjustedDeficitUsd,
    netProfitUsd: candidate.netProfitUsd,
    profit_usd: candidate.netProfitUsd,
    lowestPoolTvlUsd: candidate.lowestPoolTvlUsd,
    pools: candidate.steps.map((step) => step.edge.poolAddress),
    reason: candidate.rejectionReason,
    chain_id: 137,
    executionReady: Boolean(candidate.c1ExecutionEligible),
    c1ExecutableLimitPerCycle: intEnv("C1_EXECUTABLE_LIMIT_PER_CYCLE", DEFAULT_C1_EXECUTABLE_LIMIT),
  };
}

function writeRankedCandidateDiagnostics(candidates: Candidate[], limit: number) {
  const latestPath = resolve(process.cwd(), ".cache", "ranked-candidates-latest.json");
  const diagnosticRoutes = candidates
    .filter((candidate) => candidate.status !== "EXECUTABLE_PROFIT_CANDIDATE")
    .slice(0, limit)
    .map((candidate) => ({
      ...candidateToLedgerPayload(candidate),
      payloadKind: "POST_PROTOCOL_MATH_RANKED_DIAGNOSTIC",
      executionReady: false,
      c1ExecutionEligible: false,
    }));
  mkdirSync(dirname(latestPath), { recursive: true });
  writeFileSync(
    latestPath,
    `${JSON.stringify({
      generatedAt: Date.now(),
      rankedCandidates: candidates.length,
      diagnosticRoutes,
    }, (_key, value) => typeof value === "bigint" ? value.toString() : value, 2)}\n`,
  );
}

async function buildReverseRouteMetadata(
  provider: ethers.JsonRpcProvider,
  candidate: Candidate,
  targetContract: string,
  c1Nonce: bigint,
): Promise<ReverseRouteMetadata> {
  try {
    if (!candidate.flashloanAsset.priceUsd) throw new Error("REVERSE_FLASHLOAN_ASSET_PRICE_MISSING");
    const lowestPoolTvlUsd = Math.min(...candidate.steps.map((step) => step.edge.tvlUsd).filter((value) => Number.isFinite(value) && value > 0));
    if (!Number.isFinite(lowestPoolTvlUsd) || lowestPoolTvlUsd <= 0) throw new Error("REVERSE_LOWEST_POOL_TVL_UNRESOLVED");

    const targetAmountIn = floatToRaw(
      (lowestPoolTvlUsd * numberEnv("SIM_MAX_FLASH_TVL_FRACTION", 0.15)) / candidate.flashloanAsset.priceUsd,
      candidate.flashloanAsset.decimals,
    );
    const reverseFlashloanAmount = targetAmountIn <= candidate.flashloanLiquidity.liquidity
      ? targetAmountIn
      : candidate.flashloanLiquidity.liquidity;
    if (reverseFlashloanAmount <= 0n) throw new Error("REVERSE_FLASHLOAN_SIZE_ZERO");

    const slippageBps = BigInt(Math.floor(numberEnv("SLIPPAGE_BPS", 10)));
    const deadline = Math.floor(Date.now() / 1000) + intEnv("EXECUTION_SUBMISSION_EXPIRY_SECONDS", 300);
    const reverseSteps: RouteQuoteStep[] = [];
    let amount = reverseFlashloanAmount;
    for (const reverse of [...candidate.steps].reverse().map((step) => reverseEdge(step.edge))) {
      const amountOut = await quoteEdge(provider, reverse, amount);
      if (amountOut <= 0n) throw new Error("REVERSE_QUOTE_ZERO_OUTPUT");
      const minAmountOut = bpsMin(amountOut, slippageBps);
      const calldata = buildStepCalldata(reverse, amount, minAmountOut, targetContract, deadline);
      reverseSteps.push({ edge: reverse, amountIn: amount, amountOut, minAmountOut, calldata });
      amount = amountOut;
    }

    const flashFeeRaw = reverseFlashloanAmount * candidate.flashloanLiquidity.feeBps / 10000n;
    const reverseContext = {
      profitAsset: candidate.flashloanAsset.address,
      minNetProfit: flashFeeRaw + 1n,
      nonce: c1Nonce + 1n,
      merkleRoot: ethers.ZeroHash,
      proof: [],
      steps: reverseSteps.map((step) => ({
        venue: step.edge.executorTarget,
        tokenIn: step.edge.tokenIn,
        tokenOut: step.edge.tokenOut,
        amountIn: step.amountIn,
        minAmountOut: step.minAmountOut,
        callValue: 0n,
        payload: step.calldata,
      })),
    };

    const reversePathSymbols = reverseSteps.map((step) => step.edge.tokenInSymbol);
    reversePathSymbols.push(reverseSteps[reverseSteps.length - 1]?.edge.tokenOutSymbol || candidate.flashloanAsset.symbol);
    return {
      available: true,
      reverseFlashloanSource: candidate.flashloanLiquidity.sourceCode,
      reverseFlashloanAsset: candidate.flashloanAsset.address,
      reverseFlashloanAmount: reverseFlashloanAmount.toString(),
      reverseContext,
      reversePath: reversePathSymbols.join("->"),
      reverseVenues: reverseSteps.map((step) => `${step.edge.venueName}:${step.edge.invariant}`).join("->"),
      sizingRule: "REVERSE_FLASHLOAN_SIZE=min(15% x lowest route TVL, provider liquidity)",
    };
  } catch (error: any) {
    return {
      available: false,
      error: error?.message || "REVERSE_ROUTE_METADATA_BUILD_FAILED",
    };
  }
}

async function buildC1Context(provider: ethers.JsonRpcProvider, candidate: Candidate, targetContract: string, stateHash: string, latestBlock: number) {
  const vm = new ethers.Contract(targetContract, VM_ABI, provider);
  const nonce = await vm.globalNonce().catch(() => 0n);
  const reverseRouteMetadata = await buildReverseRouteMetadata(provider, candidate, targetContract, BigInt(nonce));
  return {
    profitAsset: candidate.flashloanAsset.address,
    minNetProfit: candidate.flashFeeRaw + 1n,
    nonce,
    merkleRoot: ethers.ZeroHash,
    proof: [],
    steps: candidate.steps.map((step) => ({
      venue: step.edge.executorTarget,
      tokenIn: step.edge.tokenIn,
      tokenOut: step.edge.tokenOut,
      amountIn: step.amountIn,
      minAmountOut: step.minAmountOut,
      callValue: 0n,
      payload: step.calldata,
    })),
    routeMetadata: {
      routeId: candidate.routeId,
      superStateHash: stateHash,
      superStateBlock: latestBlock,
      discoveryRpc: rpcUrl(),
      forkSimRpcConfigured: Boolean(process.env.FORK_SIM_RPC_URL),
      mirrorPath: routePath(candidate),
      mirrorVenues: routeVenues(candidate),
      mirrorFlashloanAmount: candidate.amountIn.toString(),
      settlementPolicy: requireUsdcSettlement() ? "USDC_SURPLUS_AT_ATOMIC_SETTLEMENT" : "FLASHLOAN_ASSET_SURPLUS_AT_ATOMIC_SETTLEMENT",
      settlementAsset: candidate.flashloanAsset.address,
      settlementSymbol: candidate.flashloanAsset.symbol,
      settlementSurplusRaw: settlementSurplusRaw(candidate).toString(),
      grossProfitRaw: candidate.grossProfitRaw.toString(),
      actualProfitRaw: actualProfitRaw(candidate).toString(),
      formula: "actualProfit=LEG2_AMOUNT_OUT_BORROW_ASSET-FLASHLOAN_PRINCIPAL-FLASHLOAN_FEE-GAS-RELAY_TIP-EXECUTOR_COST-RISK_BUFFER",
      reverseAutomation: reverseRouteMetadata.available ? "READY" : "UNAVAILABLE",
      ...reverseRouteMetadata,
    },
  };
}

function routePath(candidate: Candidate) {
  const symbols = candidate.steps.map((step) => step.edge.tokenInSymbol);
  symbols.push(candidate.steps[candidate.steps.length - 1]?.edge.tokenOutSymbol || candidate.flashloanAsset.symbol);
  return symbols.join("->");
}

function routeVenues(candidate: Candidate) {
  return candidate.steps.map((step) => `${step.edge.venueName}:${step.edge.invariant}`).join("->");
}

async function main() {
  console.log("LIVE_CYCLE_PHASE|phase=BOOT_START");
  const provider = createDiscoveryProvider();
  try {
    const network = await provider.getNetwork();
    if (network.chainId !== CHAIN_ID) throw new Error(`CHAIN_ID_MISMATCH:${network.chainId}`);
    const targetContract = DEFAULT_C1_TARGET ? normalize(DEFAULT_C1_TARGET) : "";
    if (!targetContract) throw new Error("C1_TARGET_MISSING");
    console.log(`LIVE_CYCLE_PROVIDER|transport=${discoveryTransportLabel()}|endpoint=${discoveryTransportEndpoint()}`);

    console.log("LIVE_CYCLE_PHASE|phase=API_PREFLIGHT_START");
    const health = await getJson("/api/system/healthz").catch((error) => ({ success: false, error: error.message }));
    const readiness = await getJson("/api/system/readiness").catch((error) => ({ ready: false, error: error.message }));
    console.log(`LIVE_CYCLE_PHASE|phase=API_PREFLIGHT_END|health=${health.status || health.success}|readiness=${readiness.status || readiness.ready}`);
    const { latestBlock, tokenCache, flashloanAssets, discoveryAssets, flashloanBook, edges, stats, stateHash, stateCacheStats } = await discoverGraph(provider); //
    writeDiscoveryTransparencyExport({
      latestBlock,
      tokenCache,
      flashloanAssets,
      discoveryAssets,
      flashloanBook,
      edges,
      stats,
      stateHash,
      stateCacheStats,
    });
    console.log(`LIVE_CYCLE_PHASE|phase=RANKING_START|edges=${edges.length}|flashloanAssets=${flashloanAssets.length}`);
    const { candidates, gasCostUsd, relayTipUsd, executorCostUsd, riskBufferUsd, minProfitUsd, noRouteReason } = await rankCandidates(provider, tokenCache, flashloanBook.byAsset, flashloanAssets, edges, stats, targetContract);
    const maxPrint = optionalIntEnv("LIVE_ROUTE_PRINT_LIMIT");

  console.log(`LIVE_CYCLE_START|chainId=${network.chainId}|block=${latestBlock}|api=${API_BASE}|serverHealth=${health.status || health.success}|serverReady=${readiness.status || readiness.ready}|broadcastPolicy=ONLY_AFTER_ALL_INVARIANTS_PASS|routeMode=FULL_DYNAMIC_OMNI_DIRECTIONAL|venueMode=VENUE_AGNOSTIC+POOL_EXCLUSIVE|directionMode=DIRECTION_AGNOSTIC|strategyMode=${flashloanStrategyMode()}|assetMode=BALANCER_FIRST_AAVE_FALLBACK_FLASHLOAN_LIQUIDITY|pnlUpdated=false`);
  console.log(`DISCOVERY_SUMMARY|discoveryUniverseProfile=${discoveryUniverseProfile()}|discoveryUniverseConfigured=${stats.discoveryUniverseConfigured}|discoveryUniverseLoaded=${stats.discoveryUniverseLoaded}|flashloanAssets=${stats.flashloanAssets}|flashloanBalancerAssets=${stats.flashloanBalancerAssets}|flashloanAaveAssets=${stats.flashloanAaveAssets}|tokens=${stats.tokens}|discoveredPools=${stats.discoveredPools}|directedEdges=${stats.discoveredEdges}|sourceCounts=${JSON.stringify(stats.sourceCounts)}|rejectedMetadata=${stats.rejectedMetadata}|rejectedZeroLiquidity=${stats.rejectedZeroLiquidity}|rejectedDuplicateEdge=${stats.rejectedDuplicateEdge}|rejectedUnsupportedInvariant=${stats.rejectedUnsupportedInvariant}|rejectedPreSend=${stats.rejectedPreSend}|preSendRefreshes=${stats.preSendRefreshes}|preSendRejects=${JSON.stringify(stats.preSendRejects)}|rejectedLogScanChunks=${stats.rejectedLogScan}|routeCycles=${stats.routeCyclesEnumerated}|routeCyclesRejectedLowTvl=${stats.routeCyclesRejectedLowTvl}|routeCyclesRejectedRepeatedPool=${stats.routeCyclesRejectedRepeatedPool}|routeQuoteRejects=${stats.routeCyclesRejectedQuote}|quoteRejects=${JSON.stringify(stats.quoteRejects)}|truncated=${stats.truncated}|stateHash=${stateHash}|poolStateCacheEntries=${stateCacheStats.entries}|poolStateCacheUpdated=${stateCacheStats.updated}|gasCostUsd=${gasCostUsd.toFixed(6)}|relayTipUsd=${relayTipUsd.toFixed(6)}|executorCostUsd=${executorCostUsd.toFixed(6)}|riskBufferUsd=${riskBufferUsd.toFixed(6)}|minProfitUsd=${minProfitUsd}|minFlashloanUsd=${positiveNumberEnv("MIN_FLASHLOAN_USD", 0)}|minRoutePoolTvlUsd=${minRoutePoolTvlUsd()}|invariants=VENUE_AGNOSTIC+DIRECTION_AGNOSTIC+VENUE_EXCLUSIVITY+PRICE_INVARIANT+YIELD_INVARIANT|pnlUpdated=false`);
  console.log(`FLASHLOAN_LIQUIDITY|${flashloanBook.ordered.map((item) => `${item.provider}:${item.asset.symbol}:${item.asset.address}:liquidity=${ethers.formatUnits(item.liquidity, item.asset.decimals)}:feeBps=${item.feeBps}`).join(",")}`);
  console.log(`FLASHLOAN_ASSETS|${flashloanAssets.map((asset) => `${asset.symbol}:${asset.address}`).join(",")}`);
  console.log(`PRICE_MAP|${JSON.stringify(Object.fromEntries(Array.from(tokenCache.values()).filter((token) => token.priceUsd).map((token) => [token.symbol, Number(token.priceUsd?.toFixed(8))])))}`);

  const topRouteDisplayLimit = intEnv("TOP_ROUTE_DISPLAY_LIMIT", DEFAULT_TOP_ROUTE_DISPLAY_LIMIT);
  console.log(`ROUTE_LIMITS|totalRoutes=${candidates.length}|topRouteDisplayLimit=${topRouteDisplayLimit}|c1ExecutableLimitPerCycle=${intEnv("C1_EXECUTABLE_LIMIT_PER_CYCLE", DEFAULT_C1_EXECUTABLE_LIMIT)}|c2DecisionLimitPerCycle=${Number(process.env.C2_DECISION_LIMIT_PER_CYCLE || 50)}`);

  for (const candidate of maxPrint === undefined ? candidates.slice(0, topRouteDisplayLimit) : candidates.slice(0, Math.min(maxPrint, topRouteDisplayLimit))) {
    const priceSummary = routeLegPriceSummary(candidate);
    console.log([
      `ROUTE_RANK|rank=${candidate.rank}`,
      `routeId=${candidate.routeId}`,
      `status=${candidate.status}`,
      `c1ExecutionEligible=${Boolean(candidate.c1ExecutionEligible)}`,
      `c1ExecutionSlot=${candidate.c1ExecutionSlot ?? "NONE"}`,
      `flashloanAsset=${candidate.flashloanAsset.symbol}:${candidate.flashloanAsset.address}`,
      `settlementAsset=${candidate.flashloanAsset.symbol}:${candidate.flashloanAsset.address}`,
      `settlementSurplus=${formatSignedUnits(settlementSurplusRaw(candidate), candidate.flashloanAsset.decimals)}`,
      `flashloanProvider=${candidate.flashloanLiquidity.provider}`,
      `flashloanProviderAddress=${candidate.flashloanLiquidity.providerAddress}`,
      `flashloanSource=${candidate.flashloanLiquidity.sourceCode}`,
      `flashloanProviderExecutable=${candidate.flashloanProviderExecutable}`,
      `flashloanProviderReason=${candidate.flashloanProviderReason}`,
      `flashloanDefaultProvider=${defaultFlashloanProvider()}`,
      `providerLiquidity=${ethers.formatUnits(candidate.providerLiquidityRaw, candidate.flashloanAsset.decimals)}`,
      `routeRiskCap=${ethers.formatUnits(candidate.routeRiskCapRaw, candidate.flashloanAsset.decimals)}`,
      `routeTvlRiskCap=${ethers.formatUnits(candidate.routeTvlRiskCapRaw, candidate.flashloanAsset.decimals)}`,
      `routePoolStateCap=${ethers.formatUnits(candidate.routePoolStateCapRaw, candidate.flashloanAsset.decimals)}`,
      `routePoolStateCapUsd=${candidate.routePoolStateCapUsd?.toFixed(6) ?? "UNPRICED"}`,
      `maxApplicableCapital=${ethers.formatUnits(candidate.maxApplicableCapitalRaw, candidate.flashloanAsset.decimals)}`,
      `minFlashloan=${ethers.formatUnits(candidate.minFlashloanRaw, candidate.flashloanAsset.decimals)}`,
      `routeDynamicCapUsd=${candidate.routeDynamicCapUsd.toFixed(6)}`,
      `routeMaxPoolReserveFractionBps=${candidate.routeMaxPoolReserveFractionBps}`,
      `sizingRule=${candidate.sizingRule}`,
      `sizeSearchCandidates=${candidate.sizeSearchCandidates}`,
      `capitalLimitedBy=${candidate.capitalLimitedBy}`,
      `rawLeg1BuyPrice=${formatPrice(candidate.rawLeg1BuyPrice)}`,
      `rawLeg2SellPrice=${formatPrice(candidate.rawLeg2SellPrice)}`,
      `rawSpreadDelta=${formatPrice(candidate.rawSpreadDelta)}`,
      `rawSpreadBps=${formatPrice(candidate.rawSpreadBps)}`,
      `rawSpreadDirection=${candidate.rawSpreadDirection || "NA"}`,
      `routeShape=${priceSummary.routeShape}`,
      `path=${routePath(candidate)}`,
      `venues=${routeVenues(candidate)}`,
      `hops=${candidate.steps.length}`,
      `amountIn=${ethers.formatUnits(candidate.amountIn, candidate.flashloanAsset.decimals)}`,
      `amountOut=${ethers.formatUnits(candidate.amountOut, candidate.flashloanAsset.decimals)}`,
      `grossProfit=${formatSignedUnits(candidate.grossProfitRaw, candidate.flashloanAsset.decimals)}`,
      `actualProfit=${formatSignedUnits(actualProfitRaw(candidate), candidate.flashloanAsset.decimals)}`,
      `leg1Action=${priceSummary.leg1Action}`,
      `leg1PayToken=${priceSummary.leg1PayToken}`,
      `leg1BuyToken=${priceSummary.leg1BuyToken}`,
      `leg1BuyPrice=${formatPrice(priceSummary.leg1BuyPrice)}`,
      `leg1BuyUnit=${priceSummary.leg1BuyUnit}`,
      `leg1BuyVenue=${priceSummary.leg1BuyVenue}`,
      `leg1PoolKey=${priceSummary.leg1PoolKey}`,
      `leg2Action=${priceSummary.leg2Action}`,
      `leg2SellToken=${priceSummary.leg2SellToken}`,
      `leg2ReceiveToken=${priceSummary.leg2ReceiveToken}`,
      `leg2SellPrice=${formatPrice(priceSummary.leg2SellPrice)}`,
      `leg2SellUnit=${priceSummary.leg2SellUnit}`,
      `leg2SellVenue=${priceSummary.leg2SellVenue}`,
      `leg2PoolKey=${priceSummary.leg2PoolKey}`,
      `reverseSellPrice=${formatPrice(priceSummary.reverseSellPrice)}`,
      `reverseSellUnit=${priceSummary.reverseSellUnit}`,
      `reverseSellStep=${priceSummary.reverseSellStep}`,
      `priceInvariantDirection=${priceSummary.priceInvariantDirection}`,
      `grossProfitUsd=${candidate.grossProfitUsd?.toFixed(6) ?? "UNPRICED"}`,
      `flashFeeUsd=${candidate.flashFeeUsd?.toFixed(6) ?? "UNPRICED"}`,
      `gasCostUsd=${candidate.gasCostUsd?.toFixed(6) ?? "UNPRICED"}`,
      `relayTipUsd=${candidate.relayTipUsd.toFixed(6)}`,
      `executorCostUsd=${candidate.executorCostUsd.toFixed(6)}`,
      `riskBufferUsd=${candidate.riskBufferUsd.toFixed(6)}`,
      `breakEvenGrossUsd=${candidate.breakEvenGrossUsd?.toFixed(6) ?? "UNPRICED"}`,
      `grossProfitCoverageRatio=${candidate.grossProfitCoverageRatio?.toFixed(6) ?? "UNPRICED"}`,
      `gasAdjustedDeficitUsd=${candidate.gasAdjustedDeficitUsd?.toFixed(6) ?? "UNPRICED"}`,
      `netProfitUsd=${candidate.netProfitUsd?.toFixed(6) ?? "UNPRICED"}`,
      `lowestPoolTvlUsd=${candidate.lowestPoolTvlUsd.toFixed(2)}`,
      `pools=${candidate.steps.map((step) => `${step.edge.venueName}:${step.edge.poolAddress}`).join(",")}`,
      `reason=${candidate.rejectionReason}`,
    ].join("|"));
  }

  const best = candidates.find((candidate) => candidate.c1ExecutionEligible) || candidates[0];
  if (!best) {
    console.log(`OPPORTUNITY_DECISION|decision=DO_NOTHING|reason=${noRouteReason}|hash=NONE|pnlUpdated=false`);
  } else if (best.status !== "EXECUTABLE_PROFIT_CANDIDATE") {
    console.log(`OPPORTUNITY_DECISION|decision=DO_NOTHING|bestRoute=${best.routeId}|reason=${best.rejectionReason}|hash=NONE|pnlUpdated=false`);
  } else {
    const ledgerPayload = candidateToLedgerPayload(best);
    const lock = await lockOpportunityForExecution(ledgerPayload);
    if (!lock.ok) {
      console.log(`OPPORTUNITY_DECISION|decision=DO_NOTHING|bestRoute=${best.routeId}|reason=${lock.reason}|redisId=${lock.id}|hash=NONE|pnlUpdated=false`);
      console.log("C2_DECISION|decision=DO_NOTHING|reason=NO_CONFIRMED_C1_HASH_IN_THIS_CYCLE|hash=NONE|pnlUpdated=false");
      return;
    }
    const context = await buildC1Context(provider, best, targetContract, stateHash, latestBlock);
    const exec = await postJson("/api/execution/c1", {
      redisId: lock.id,
      targetContract,
      flashloanSource: best.flashloanLiquidity.sourceCode,
      flashloanAsset: best.flashloanAsset.address,
      flashloanAmount: best.amountIn,
      context,
    });
    if (!exec.json.success) {
      await releaseOpportunityLock(lock.id, "C1_REJECTED", {
        routeId: best.routeId,
        error: exec.json.error || "C1 rejected by API",
      });
    }
    console.log(`C1_EXECUTION_RESULT|routeId=${best.routeId}|httpStatus=${exec.status}|success=${exec.json.success}|hash=${exec.json.hash || "NONE"}|hashLink=${exec.json.hashLink || "NONE"}|error=${exec.json.error || "NONE"}|forkOk=${exec.json.forkSimulation?.ok ?? "UNKNOWN"}|pnlUpdated=false`);
  }

  console.log("C2_DECISION|decision=DO_NOTHING|reason=NO_CONFIRMED_C1_HASH_IN_THIS_CYCLE|hash=NONE|pnlUpdated=false");
  const pnl = await getJson("/api/dashboard/pnl-summary").catch((error) => ({ error: error.message }));
  console.log(`PNL_STATUS|sessionRaw=${pnl.sessionPnlRaw ?? "UNKNOWN"}|lifetimeRaw=${pnl.lifetimePnlRaw ?? "UNKNOWN"}|attribution=${pnl.pnlAttribution ?? "UNKNOWN"}|pnlUpdated=false`);
  await flushLaneEventBatch("cycle_end");
  console.log("LIVE_CYCLE_END|status=COMPLETE|broadcasted=false_unless_hash_printed_above");
  } finally {
    await closeDiscoveryProvider(provider);
  }
}

main().then(() => {
  process.exit(0);
}).catch((error) => {
  console.error(`LIVE_CYCLE_FAILED|error=${error?.message || error}|broadcasted=false|pnlUpdated=false`);
  process.exit(1);
});
