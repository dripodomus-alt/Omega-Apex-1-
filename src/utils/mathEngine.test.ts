import { describe, it, expect } from 'vitest';
import {
  convertSqrtPriceX96ToVirtualReserves,
  solveProfitApex,
  validatePotIsolation,
  validateRouteAssetRegistry,
} from './mathEngine';
import type { ArbitrageRoute, PoolInfo } from '../types';

// ---------------------------------------------------------------------------
// convertSqrtPriceX96ToVirtualReserves
// ---------------------------------------------------------------------------

describe('convertSqrtPriceX96ToVirtualReserves', () => {
  it('returns fallback reserves for zero sqrtPriceX96', () => {
    const result = convertSqrtPriceX96ToVirtualReserves('0', '1000000');
    expect(result.r0Virtual).toBe(1000000);
    expect(result.r1Virtual).toBe(1000000);
    expect(result.virtualPrice0in1).toBe(1.0);
    expect(result.virtualPrice1in0).toBe(1.0);
  });

  it('returns fallback reserves for zero liquidity', () => {
    const result = convertSqrtPriceX96ToVirtualReserves(
      '79228162514264337593543950336', // 2^96 (price = 1)
      '0'
    );
    expect(result.r0Virtual).toBe(1000000);
    expect(result.r1Virtual).toBe(1000000);
  });

  it('returns fallback reserves for invalid (non-numeric) inputs', () => {
    const result = convertSqrtPriceX96ToVirtualReserves('not-a-number', '1000');
    expect(result.r0Virtual).toBe(1000000);
    expect(result.r1Virtual).toBe(1000000);
    expect(result.sqrtPriceX96Num).toBe(0);
    expect(result.liquidityNum).toBe(0);
  });

  it('computes symmetric virtual reserves when price == 1 (sqrtPriceX96 == Q96)', () => {
    const Q96 = '79228162514264337593543950336'; // 2^96
    const L = '1000000000000000000'; // 1e18
    const result = convertSqrtPriceX96ToVirtualReserves(Q96, L);

    // When price == 1, sqrtP == 1 → r0_v = L/1 == r1_v = L*1
    expect(result.r0Virtual).toBeCloseTo(result.r1Virtual, 3);
    expect(result.virtualPrice0in1).toBeCloseTo(1.0, 6);
    expect(result.virtualPrice1in0).toBeCloseTo(1.0, 6);
  });

  it('satisfies r0_v * r1_v == L^2 (constant-product invariant)', () => {
    const Q96 = BigInt('79228162514264337593543950336');
    // sqrtPriceX96 for price ≈ 4 → sqrtP = 2 → sqrtPriceX96 = 2 * Q96
    const sqrtPriceX96 = (BigInt(2) * Q96).toString();
    const L = '1000000000000000000'; // 1e18
    const result = convertSqrtPriceX96ToVirtualReserves(sqrtPriceX96, L);

    const product = result.r0Virtual * result.r1Virtual;
    const Lnum = Number(L);
    // r0_v * r1_v should equal L^2
    expect(product).toBeCloseTo(Lnum * Lnum, -3); // large numbers, allow rounding
  });

  it('stores the raw sqrtPriceX96 and liquidity as numeric fields', () => {
    const sqrtPriceX96 = '79228162514264337593543950336';
    const liquidity = '5000000000';
    const result = convertSqrtPriceX96ToVirtualReserves(sqrtPriceX96, liquidity);
    expect(result.sqrtPriceX96Num).toBe(Number(sqrtPriceX96));
    expect(result.liquidityNum).toBe(Number(liquidity));
  });
});

// ---------------------------------------------------------------------------
// solveProfitApex
// ---------------------------------------------------------------------------

describe('solveProfitApex', () => {
  it('returns zero profit when rIn >= rOut (no arbitrage opportunity)', () => {
    const result = solveProfitApex(1000000, 1000000);
    // optimalInput should be 0 when there is no price discrepancy
    expect(result.optimalInputUSD).toBe(0);
    expect(result.maxNetProfitUSD).toBe(0);
  });

  it('returns positive profit when rOut > rIn (valid arbitrage)', () => {
    // rOut significantly larger → price discrepancy exists
    const result = solveProfitApex(500000, 1000000);
    expect(result.optimalInputUSD).toBeGreaterThan(0);
    expect(result.maxNetProfitUSD).toBeGreaterThan(0);
  });

  it('derivativeAtZero is positive when rOut/rIn > costFactor/gammaSwap', () => {
    // rOut = 2 * rIn → clearly profitable at baseline
    const result = solveProfitApex(100000, 200000);
    expect(result.derivativeAtZero).toBeGreaterThan(0);
  });

  it('derivativeAtZero is negative when rOut == rIn (no alpha at baseline)', () => {
    const result = solveProfitApex(1000000, 1000000);
    // gammaSwap * (rOut/rIn) - costFactor = 0.997 * 1 - 1.0005 < 0
    expect(result.derivativeAtZero).toBeLessThan(0);
  });

  it('generates 26 curve data points (0 through 25)', () => {
    const result = solveProfitApex(500000, 600000);
    expect(result.curveData).toHaveLength(26);
  });

  it('first curve point has inputUSD == 0', () => {
    const result = solveProfitApex(500000, 600000);
    expect(result.curveData[0].inputUSD).toBe(0);
  });

  it('accepts custom fee and gas parameters', () => {
    const defaultResult = solveProfitApex(500000, 1000000);
    // Higher swap fee → lower optimal input & profit
    const highFeeResult = solveProfitApex(500000, 1000000, 100); // 1%
    expect(highFeeResult.optimalInputUSD).toBeLessThan(defaultResult.optimalInputUSD);
  });

  it('optimalInputUSD is non-negative', () => {
    const result = solveProfitApex(1000000, 500000); // inverted (no arb)
    expect(result.optimalInputUSD).toBeGreaterThanOrEqual(0);
  });
});

// ---------------------------------------------------------------------------
// validatePotIsolation
// ---------------------------------------------------------------------------

describe('validatePotIsolation', () => {
  it('returns isIsolated true when funding pool is not in route pools', () => {
    const result = validatePotIsolation('pool-A', ['pool-B', 'pool-C', 'pool-D']);
    expect(result.isIsolated).toBe(true);
    expect(result.conflictPoolId).toBeUndefined();
  });

  it('returns isIsolated false when funding pool appears in route pools', () => {
    const result = validatePotIsolation('pool-A', ['pool-B', 'pool-A', 'pool-C']);
    expect(result.isIsolated).toBe(false);
    expect(result.conflictPoolId).toBe('pool-A');
  });

  it('is case-insensitive in pool ID comparison', () => {
    const result = validatePotIsolation('POOL-A', ['pool-b', 'pool-a']);
    expect(result.isIsolated).toBe(false);
    expect(result.conflictPoolId).toBe('pool-a');
  });

  it('returns isIsolated true for an empty route pool list', () => {
    const result = validatePotIsolation('pool-A', []);
    expect(result.isIsolated).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// validateRouteAssetRegistry
// ---------------------------------------------------------------------------

function makePool(overrides: Partial<PoolInfo> = {}): PoolInfo {
  return {
    id: 'pool-1',
    name: 'TestPool',
    protocol: 'V2_CPMM',
    category: 'SWAPPABLE_EXECUTION',
    address: '0xabc',
    token0: { symbol: 'WMATIC / WPOL', decimals: 18, address: '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270' },
    token1: { symbol: 'USDC.e', decimals: 6, address: '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174' },
    feeBps: 30,
    reserve0USD: 100000,
    reserve1USD: 100000,
    isFundingPool: false,
    status: 'ACTIVE',
    ...overrides,
  };
}

function makeRoute(pools: PoolInfo[]): ArbitrageRoute {
  return {
    id: 'route-1',
    pathString: 'WMATIC→USDC→WETH',
    length: pools.length,
    pools,
    expectedYieldUSD: 0,
    vqcAlphaScore: 0,
    vqcWinProbability: 0,
    optimalInputUSD: 1000,
    optimalInputWei: '1000000000000000000',
    grossProfitUSD: 10,
    estimatedGasUSD: 0.45,
    netProfitUSD: 9.55,
    stage: 'SIMULATED',
    timestamp: new Date().toISOString(),
    slippageToleranceBps: 50,
    isSelfFundingRisk: false,
  };
}

describe('validateRouteAssetRegistry', () => {
  it('marks route executable when all tokens are in registry and no registered-pool list provided', () => {
    const pool = makePool();
    const route = makeRoute([pool]);
    const result = validateRouteAssetRegistry(route, []);
    expect(result.isExecutable).toBe(true);
    expect(result.unregisteredAssets).toHaveLength(0);
  });

  it('rejects an unregistered swappable asset even when max discovery is enabled', () => {
    const pool = makePool({
      token0: { symbol: 'UNKNOWN_TOKEN', decimals: 18, address: '0xdeadbeef' },
    });
    const route = makeRoute([pool]);
    const result = validateRouteAssetRegistry(route, []);
    expect(result.isExecutable).toBe(false);
    expect(result.unregisteredAssets).toEqual(['UNKNOWN_TOKEN']);
  });

  it('rejects an unregistered pool when a registered-pool list is supplied', () => {
    const pool = makePool({ id: 'pool-unknown', address: '0x0000000000000000000000000000000000000abc' });
    const route = makeRoute([pool]);
    const registeredPool = makePool({ id: 'pool-registered', address: '0x0000000000000000000000000000000000000def' });
    const result = validateRouteAssetRegistry(route, [registeredPool]);
    expect(result.isExecutable).toBe(false);
    expect(result.unregisteredPools).toEqual(['TestPool']);
  });

  it('counts pools correctly in result', () => {
    const pools = [makePool(), makePool({ id: 'pool-2', address: '0xdef' })];
    const route = makeRoute(pools);
    const result = validateRouteAssetRegistry(route, []);
    expect(result.totalPoolsCount).toBe(2);
    expect(result.registeredPoolsCount).toBe(2);
  });

  it('deduplicates unregistered assets (same token appearing in multiple pools)', () => {
    const badAsset = { symbol: 'UNKNOWN_TOKEN', decimals: 18, address: '0xdeadbeef' };
    const pool1 = makePool({ id: 'p1', token0: badAsset });
    const pool2 = makePool({ id: 'p2', token0: badAsset });
    const route = makeRoute([pool1, pool2]);
    const result = validateRouteAssetRegistry(route, []);
    const uniqueCount = new Set(result.unregisteredAssets).size;
    expect(result.isExecutable).toBe(false);
    expect(uniqueCount).toBe(result.unregisteredAssets.length);
    expect(result.unregisteredAssets).toEqual(['UNKNOWN_TOKEN']);
  });

  it('rejects funding pools inside swap execution legs', () => {
    const pool = makePool({ category: 'FUNDING_FLASHLOAN', isFundingPool: true });
    const route = makeRoute([pool]);
    const result = validateRouteAssetRegistry(route, []);
    expect(result.isExecutable).toBe(false);
    expect(result.invalidPoolCategories[0]).toContain('FUNDING_FLASHLOAN');
  });
});
