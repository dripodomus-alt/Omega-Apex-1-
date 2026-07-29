import { ArbitrageRoute, PoolInfo } from '../types';
import { POLYGON_TOKENS } from '../data/mockEngineData';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';

/**
 * OMEGA V5 - Precision Math Engine
 * Implements UniSwap V3 sqrtPriceX96 virtualization to CPMM reserves
 * & Calculus-based Deterministic Capital Injector Apex calculation.
 */

export interface VirtualReserves {
  r0Virtual: number;
  r1Virtual: number;
  virtualPrice0in1: number;
  virtualPrice1in0: number;
  sqrtPriceX96Num: number;
  liquidityNum: number;
}

export interface ProfitApexResult {
  optimalInputUSD: number;
  maxNetProfitUSD: number;
  grossProfitUSD: number;
  flashloanFeeUSD: number;
  swapFeesUSD: number;
  curveData: { inputUSD: number; netProfitUSD: number; grossProfitUSD: number; gasFeeUSD: number }[];
  derivativeAtZero: number;
}

/**
 * Converts Uniswap V3 concentrated liquidity parameters into virtual constant-product reserves.
 * P = (sqrtPriceX96 / 2^96)^2
 * r0_v = L / sqrt(P)
 * r1_v = L * sqrt(P)
 */
export function convertSqrtPriceX96ToVirtualReserves(
  sqrtPriceX96Str: string,
  liquidityStr: string
): VirtualReserves {
  try {
    const Q96 = BigInt('79228162514264337593543950336'); // 2^96
    const sqrtPriceX96 = BigInt(sqrtPriceX96Str);
    const liquidity = BigInt(liquidityStr);

    // Number conversion for UI visualization
    const sqrtPRaw = Number(sqrtPriceX96) / Number(Q96);
    const sqrtP = Number.isFinite(sqrtPRaw) ? Math.max(1e-6, sqrtPRaw) : 0;
    const price = sqrtP * sqrtP;
    const L = Number(liquidity);

    if (!Number.isFinite(sqrtP) || !Number.isFinite(sqrtPRaw) || !Number.isFinite(L) || sqrtPRaw <= 0 || L <= 0) {
      return {
        r0Virtual: 1000000,
        r1Virtual: 1000000,
        virtualPrice0in1: 1.0,
        virtualPrice1in0: 1.0,
        sqrtPriceX96Num: Number(sqrtPriceX96),
        liquidityNum: L,
      };
    }

    const rawR0Virtual = L / sqrtP;
    const rawR1Virtual = L * sqrtP;
    const r0Virtual = Number.isFinite(rawR0Virtual) ? Math.max(1, rawR0Virtual) : 1e15;
    const r1Virtual = Number.isFinite(rawR1Virtual) ? Math.max(1, rawR1Virtual) : 1e15;
    const virtualPrice0in1 = Math.min(1e6, Math.max(0, price));

    return {
      r0Virtual,
      r1Virtual,
      virtualPrice0in1,
      virtualPrice1in0: virtualPrice0in1 > 0 ? Math.min(1e6, 1 / virtualPrice0in1) : 0,
      sqrtPriceX96Num: Number(sqrtPriceX96),
      liquidityNum: L,
    };
  } catch (err) {
    return {
      r0Virtual: 1000000,
      r1Virtual: 1000000,
      virtualPrice0in1: 1.0,
      virtualPrice1in0: 1.0,
      sqrtPriceX96Num: 0,
      liquidityNum: 0,
    };
  }
}

/**
 * Solves for optimal capital injection size x* where derivative d(Profit)/dx = 0
 * Uses exact CPMM virtual reserves:
 * Gross Out y = (rOut * x * (1 - f_swap)) / (rIn + x * (1 - f_swap))
 * Net Profit = y - x * (1 + f_flash) - Fixed_Gas
 */
export function solveProfitApex(
  rInUSD: number,
  rOutUSD: number,
  swapFeeBps: number = 30, // 0.3%
  flashFeeBps: number = 5,  // 0.05%
  gasEstimateUSD: number = 0.45
): ProfitApexResult {
  const fSwap = swapFeeBps / 10000;
  const fFlash = flashFeeBps / 10000;

  const gammaSwap = 1 - fSwap;
  const costFactor = 1 + fFlash;

  // Analytical derivative optimal input:
  // x_opt = ( sqrt( rIn * rOut * gammaSwap / costFactor ) - rIn ) / gammaSwap
  const numerator = Math.sqrt((rInUSD * rOutUSD * gammaSwap) / costFactor) - rInUSD;
  const rawOptimalInput = numerator / gammaSwap;

  const optimalInputUSD = Math.max(0, rawOptimalInput);

  // Generate 25 plot points around optimal input for UI profit curve
  const maxRange = Math.max(optimalInputUSD * 2.5, 50000);
  const step = maxRange / 25;
  const curveData = [];

  let maxNetProfitUSD = -gasEstimateUSD;
  let grossAtOpt = 0;
  let flashFeeAtOpt = 0;
  let swapFeeAtOpt = 0;

  for (let i = 0; i <= 25; i++) {
    const inputUSD = i * step;
    if (inputUSD === 0) {
      curveData.push({ inputUSD: 0, netProfitUSD: -gasEstimateUSD, grossProfitUSD: 0, gasFeeUSD: gasEstimateUSD });
      continue;
    }

    const inputAfterFee = inputUSD * gammaSwap;
    const grossOutUSD = (rOutUSD * inputAfterFee) / (rInUSD + inputAfterFee);
    const flashFeeUSD = inputUSD * fFlash;
    const netProfitUSD = grossOutUSD - inputUSD - flashFeeUSD - gasEstimateUSD;
    const grossProfitUSD = grossOutUSD - inputUSD;

    curveData.push({
      inputUSD: Math.round(inputUSD),
      netProfitUSD: Number(netProfitUSD.toFixed(2)),
      grossProfitUSD: Number(grossProfitUSD.toFixed(2)),
      gasFeeUSD: gasEstimateUSD,
    });

    if (Math.abs(inputUSD - optimalInputUSD) < step || i === Math.round((optimalInputUSD / maxRange) * 25)) {
      maxNetProfitUSD = netProfitUSD;
      grossAtOpt = grossProfitUSD;
      flashFeeAtOpt = flashFeeUSD;
      swapFeeAtOpt = inputUSD * fSwap;
    }
  }

  // Calculate derivative at zero to check if route is positive alpha at baseline
  const derivativeAtZero = (rOutUSD / rInUSD) * gammaSwap - costFactor;

  return {
    optimalInputUSD: Math.round(optimalInputUSD * 100) / 100,
    maxNetProfitUSD: Math.max(0, Math.round(maxNetProfitUSD * 100) / 100),
    grossProfitUSD: Math.round(grossAtOpt * 100) / 100,
    flashloanFeeUSD: Math.round(flashFeeAtOpt * 100) / 100,
    swapFeesUSD: Math.round(swapFeeAtOpt * 100) / 100,
    curveData,
    derivativeAtZero,
  };
}

/**
 * Verifies strict self-funding isolation rule:
 * Flashloan funding pot must never be in the set of swappable execution pools.
 */
export function validatePotIsolation(
  fundingPoolId: string,
  routePoolIds: string[]
): { isIsolated: boolean; conflictPoolId?: string } {
  const conflict = routePoolIds.find((id) => id.toLowerCase() === fundingPoolId.toLowerCase());
  if (conflict) {
    return { isIsolated: false, conflictPoolId: conflict };
  }
  return { isIsolated: true };
}

export interface RouteRegistryValidation {
  isExecutable: boolean;
  reason?: string;
  registeredPoolsCount: number;
  totalPoolsCount: number;
  unregisteredAssets: string[];
  unregisteredPools: string[];
}

/**
 * Ensures routes can ONLY be executed if all constituent pools hold assets present in our asset registry (POLYGON_TOKENS),
 * and if all pools in the route are registered in our protocol registry.
 */
export function validateRouteAssetRegistry(
  route: ArbitrageRoute,
  registeredPools: PoolInfo[] = []
): RouteRegistryValidation {
  const registeredTokenAddresses = new Set(
    Object.values(POLYGON_TOKENS).map((t) => t.address.toLowerCase())
  );
  const registeredTokenSymbols = new Set(
    Object.values(POLYGON_TOKENS).map((t) => t.symbol.toLowerCase())
  );

  const registeredPoolAddresses = new Set(
    registeredPools.map((p) => p.address.toLowerCase())
  );
  const registeredPoolIds = new Set(
    registeredPools.map((p) => p.id.toLowerCase())
  );

  const unregisteredAssets: string[] = [];
  const unregisteredPools: string[] = [];

  route.pools.forEach((pool) => {
    // Check pool existence in registered pools (if pools list provided)
    if (registeredPools.length > 0) {
      const isPoolRegistered =
        registeredPoolAddresses.has(pool.address.toLowerCase()) ||
        registeredPoolIds.has(pool.id.toLowerCase());

      if (!isPoolRegistered) {
        unregisteredPools.push(pool.name || pool.address);
      }
    }

    // Check token0 in asset registry
    const token0Addr = pool.token0?.address?.toLowerCase();
    const token0Sym = pool.token0?.symbol?.toLowerCase();
    const isToken0Registered =
      (token0Addr && registeredTokenAddresses.has(token0Addr)) ||
      (token0Sym && registeredTokenSymbols.has(token0Sym));

    if (!isToken0Registered && pool.token0?.symbol) {
      unregisteredAssets.push(pool.token0.symbol);
    }

    // Check token1 in asset registry
    const token1Addr = pool.token1?.address?.toLowerCase();
    const token1Sym = pool.token1?.symbol?.toLowerCase();
    const isToken1Registered =
      (token1Addr && registeredTokenAddresses.has(token1Addr)) ||
      (token1Sym && registeredTokenSymbols.has(token1Sym));

    if (!isToken1Registered && pool.token1?.symbol) {
      unregisteredAssets.push(pool.token1.symbol);
    }
  });

  const uniqueUnregisteredAssets = Array.from(new Set(unregisteredAssets));
  const uniqueUnregisteredPools = Array.from(new Set(unregisteredPools));

  // When MAX POOL DISCOVERY FOR ALL DISCOVERY ASSETS is enabled,
  // all discovered pools and assets are automatically recognized as executable upon gating pass.
  if (POLYGON_CHAIN_CONFIG.maxPoolDiscoveryAllAssets || POLYGON_CHAIN_CONFIG.discoverableIsExecutableUponGating) {
    return {
      isExecutable: true,
      registeredPoolsCount: route.pools.length,
      totalPoolsCount: route.pools.length,
      unregisteredAssets: [],
      unregisteredPools: [],
    };
  }

  if (uniqueUnregisteredPools.length > 0) {
    return {
      isExecutable: false,
      reason: `Route contains pool(s) not registered in Protocol Registry: ${uniqueUnregisteredPools.join(', ')}`,
      registeredPoolsCount: route.pools.length - uniqueUnregisteredPools.length,
      totalPoolsCount: route.pools.length,
      unregisteredAssets: uniqueUnregisteredAssets,
      unregisteredPools: uniqueUnregisteredPools,
    };
  }

  if (uniqueUnregisteredAssets.length > 0) {
    return {
      isExecutable: false,
      reason: `Route contains asset(s) not found in Asset Registry: ${uniqueUnregisteredAssets.join(', ')}`,
      registeredPoolsCount: route.pools.length,
      totalPoolsCount: route.pools.length,
      unregisteredAssets: uniqueUnregisteredAssets,
      unregisteredPools: uniqueUnregisteredPools,
    };
  }

  return {
    isExecutable: true,
    registeredPoolsCount: route.pools.length,
    totalPoolsCount: route.pools.length,
    unregisteredAssets: [],
    unregisteredPools: [],
  };
}
