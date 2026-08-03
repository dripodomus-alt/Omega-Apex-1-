import { buildAssetUniverseProfile, resolveFlashloanCapitalAsset, resolveSwappableAsset } from '../src/config/assetUniverse';
import { MID_TOKEN_EXECUTION_POOLS, type MidTokenExecutionPool } from '../src/config/midTokenPoolUniverse';
import { validateRouteAssetRegistry } from '../src/utils/mathEngine';
import type { ArbitrageRoute, PoolInfo, ProtocolType } from '../src/types';

const CAPITAL_USD = Number(process.env.APEX_DRY_RUN_CAPITAL_USD ?? 50_000);
const GAS_USD = Number(process.env.APEX_DRY_RUN_GAS_USD ?? 0.85);
const FLASHLOAN_SYMBOL = process.env.APEX_DRY_RUN_FLASH_ASSET ?? 'USDC.e';

const protocolTypeByArchitecture: Record<string, ProtocolType> = {
  V2_CPMM: 'V2_CPMM',
  V3_CLMM: 'V3_CLMM',
  QS_V2_CPMM: 'QS_V2_CPMM',
  QS_V3_ALGEBRA: 'QS_V3_ALGEBRA',
  BAL_WEIGHTED: 'BAL_WEIGHTED',
  CURVE_STABLE: 'CURVE_STABLE',
  DODO_V2_PMM: 'DODO_V2_PMM',
};

interface RankedDryRunRoute {
  routeId: string;
  midToken: string;
  buyPool: MidTokenExecutionPool;
  sellPool: MidTokenExecutionPool;
  unitsBought: number;
  grossProfitUSD: number;
  swapFeesUSD: number;
  flashFeeUSD: number;
  gasUSD: number;
  netProfitUSD: number;
  spreadBps: number;
  gate: ReturnType<typeof validateRouteAssetRegistry>;
}

function toPoolInfo(pool: MidTokenExecutionPool, leg: 'BUY' | 'SELL'): PoolInfo {
  const base = resolveSwappableAsset(pool.baseTokenSymbol);
  const mid = resolveSwappableAsset(pool.midTokenSymbol);
  if (!base || !mid) {
    throw new Error(`Missing configured asset for ${pool.id}`);
  }

  return {
    id: `${pool.id}_${leg.toLowerCase()}`,
    name: `${leg} ${pool.poolName}`,
    protocol: protocolTypeByArchitecture[pool.protocolArchitecture] ?? 'V3_CLMM',
    protocolArchitecture: pool.protocolArchitecture,
    category: 'SWAPPABLE_EXECUTION',
    address: pool.address,
    token0: { symbol: base.symbol, decimals: base.decimals, address: base.address },
    token1: { symbol: mid.symbol, decimals: mid.decimals, address: mid.address },
    feeBps: pool.feeBps,
    reserve0USD: pool.reserveBaseToken,
    reserve1USD: pool.reserveMidToken * pool.executablePriceUSD,
    isFundingPool: false,
    status: pool.isActive ? 'ACTIVE' : 'PAUSED',
  };
}

function routeFor(candidate: Omit<RankedDryRunRoute, 'gate'>): ArbitrageRoute {
  const pools = [toPoolInfo(candidate.buyPool, 'BUY'), toPoolInfo(candidate.sellPool, 'SELL')];
  return {
    id: candidate.routeId,
    pathString: `${FLASHLOAN_SYMBOL}->${candidate.midToken}->${FLASHLOAN_SYMBOL}`,
    length: pools.length,
    pools,
    expectedYieldUSD: candidate.grossProfitUSD,
    vqcAlphaScore: candidate.netProfitUSD,
    vqcWinProbability: candidate.netProfitUSD > 0 ? 0.91 : 0,
    optimalInputUSD: CAPITAL_USD,
    optimalInputWei: '0',
    grossProfitUSD: candidate.grossProfitUSD,
    estimatedGasUSD: GAS_USD,
    netProfitUSD: candidate.netProfitUSD,
    stage: 'SIMULATED',
    timestamp: new Date().toISOString(),
    slippageToleranceBps: 15,
    isSelfFundingRisk: false,
  };
}

function rankRoutes(): RankedDryRunRoute[] {
  const flashAsset = resolveFlashloanCapitalAsset(FLASHLOAN_SYMBOL);
  if (!flashAsset) throw new Error(`Flashloan asset is not configured: ${FLASHLOAN_SYMBOL}`);

  const grouped = new Map<string, MidTokenExecutionPool[]>();
  for (const pool of MID_TOKEN_EXECUTION_POOLS.filter((pool) => pool.isActive)) {
    const list = grouped.get(pool.midTokenSymbol) ?? [];
    list.push(pool);
    grouped.set(pool.midTokenSymbol, list);
  }

  const candidates: RankedDryRunRoute[] = [];
  for (const [midToken, pools] of grouped) {
    if (pools.length < 2) continue;
    const sorted = [...pools].sort((a, b) => a.executablePriceUSD - b.executablePriceUSD);
    const buyPool = sorted[0];
    const sellPool = sorted[sorted.length - 1];
    if (buyPool.id === sellPool.id || buyPool.executablePriceUSD >= sellPool.executablePriceUSD) continue;

    const unitsBought = CAPITAL_USD / buyPool.executablePriceUSD;
    const grossProfitUSD = unitsBought * (sellPool.executablePriceUSD - buyPool.executablePriceUSD);
    const swapFeesUSD = CAPITAL_USD * ((buyPool.feeBps + sellPool.feeBps) / 10_000);
    const flashFeeUSD = CAPITAL_USD * ((flashAsset.flashFeeBps ?? 0) / 10_000);
    const netProfitUSD = grossProfitUSD - swapFeesUSD - flashFeeUSD - GAS_USD;
    const spreadBps = ((sellPool.executablePriceUSD / buyPool.executablePriceUSD) - 1) * 10_000;

    const candidate = {
      routeId: `dry_${midToken.toLowerCase()}_${buyPool.id}_to_${sellPool.id}`,
      midToken,
      buyPool,
      sellPool,
      unitsBought,
      grossProfitUSD,
      swapFeesUSD,
      flashFeeUSD,
      gasUSD: GAS_USD,
      netProfitUSD,
      spreadBps,
    };
    const gate = validateRouteAssetRegistry(routeFor(candidate));
    candidates.push({ ...candidate, gate });
  }

  return candidates.sort((a, b) => b.netProfitUSD - a.netProfitUSD);
}

const profile = buildAssetUniverseProfile();
const routes = rankRoutes();
const executable = routes.filter((route) => route.gate.isExecutable && route.netProfitUSD > 0);

console.log('APEX_OMEGA_DISCOVERY_RANKING_DRY_RUN');
console.log(`capitalUsd=${CAPITAL_USD.toFixed(2)} flashloanAsset=${FLASHLOAN_SYMBOL} gasUsd=${GAS_USD.toFixed(2)}`);
console.log(`baseTokens=${profile.baseRouteAssets.join(', ')}`);
console.log(`midTokens=${profile.midTokenAssets.join(', ')}`);
console.log(`swappablePoolStateAssets=${profile.swappablePoolStateAssets.join(', ')}`);
console.log(`priceAssets=${profile.priceAssets.join(', ')}`);
console.log(`dexVenues=${profile.executableDexes.join(', ')}`);
console.log(`aggregatorDiscovery=${profile.discoveryAggregators.join(', ')}`);
console.log(`protocols=${profile.executableProtocols.join(', ')}`);
console.log('equation=units=capitalUsd/buyPrice; gross=(sellPrice-buyPrice)*units; net=gross-swapFees-flashFee-gas; executable=buyPrice<sellPrice && net>0 && routeGatePASS');
console.log(`routesDiscovered=${routes.length} executableProfitable=${executable.length}`);

for (const [index, route] of routes.entries()) {
  const status = route.gate.isExecutable && route.netProfitUSD > 0 ? 'EXECUTABLE_PROFITABLE' : 'REJECT';
  console.log([
    `rank=${index + 1}`,
    `status=${status}`,
    `mid=${route.midToken}`,
    `buyLowest=${route.buyPool.venue}:${route.buyPool.executablePriceUSD.toFixed(6)}`,
    `sellHighest=${route.sellPool.venue}:${route.sellPool.executablePriceUSD.toFixed(6)}`,
    `units=${route.unitsBought.toFixed(6)}`,
    `spreadBps=${route.spreadBps.toFixed(2)}`,
    `grossUsd=${route.grossProfitUSD.toFixed(2)}`,
    `swapFeesUsd=${route.swapFeesUSD.toFixed(2)}`,
    `flashFeeUsd=${route.flashFeeUSD.toFixed(2)}`,
    `gasUsd=${route.gasUSD.toFixed(2)}`,
    `netUsd=${route.netProfitUSD.toFixed(2)}`,
    `gate=${route.gate.isExecutable ? 'PASS' : 'FAIL'}`,
    route.gate.reason ? `reason=${route.gate.reason}` : '',
  ].filter(Boolean).join('|'));
}
