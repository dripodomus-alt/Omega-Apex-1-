/**
 * APEX_OMEGA Math Core
 * Precision AMM formulas for DEX Arbitrage
 */

export interface Pool {
  id: string;
  dex: string;
  token0: string;
  token1: string;
  reserve0: bigint;
  reserve1: bigint;
  fee: number; // e.g. 0.003 for 0.3%
}

/**
 * Uniswap V2 Get Amount Out
 * Formula: (amountIn * 997 * reserveOut) / (reserveIn * 1000 + amountIn * 997)
 */
export function getAmountOutV2(
  amountIn: bigint,
  reserveIn: bigint,
  reserveOut: bigint,
  feeBps: number = 30 // 0.3%
): bigint {
  if (amountIn <= 0n) return 0n;
  if (reserveIn <= 0n || reserveOut <= 0n) return 0n;

  const amountInWithFee = amountIn * BigInt(10000 - feeBps);
  const numerator = amountInWithFee * reserveOut;
  const denominator = reserveIn * 10000n + amountInWithFee;
  return numerator / denominator;
}

/**
 * Uniswap V2 Get Amount In
 * Formula: (reserveIn * amountOut * 1000) / ((reserveOut - amountOut) * 997) + 1
 */
export function getAmountInV2(
  amountOut: bigint,
  reserveIn: bigint,
  reserveOut: bigint,
  feeBps: number = 30
): bigint {
  if (amountOut <= 0n) return 0n;
  if (reserveIn <= 0n || reserveOut <= 0n) return 0n;
  if (amountOut >= reserveOut) throw new Error("INSUFFICIENT_LIQUIDITY");

  const numerator = reserveIn * amountOut * 10000n;
  const denominator = (reserveOut - amountOut) * BigInt(10000 - feeBps);
  return (numerator / denominator) + 1n;
}

/**
 * Calculate spread between two pools
 */
export function calculateSpread(poolA: Pool, poolB: Pool, amountIn: bigint): {
  profit: bigint,
  path: string[]
} {
  // Assume poolA is buy (token0 -> token1) and poolB is sell (token1 -> token0)
  const buyOut = getAmountOutV2(amountIn, poolA.reserve0, poolA.reserve1, Math.floor(poolA.fee * 10000));
  const sellOut = getAmountOutV2(buyOut, poolB.reserve1, poolB.reserve0, Math.floor(poolB.fee * 10000));

  const profit = sellOut - amountIn;

  return {
    profit,
    path: [poolA.dex, poolB.dex]
  };
}

/**
 * Aave V3 Liquidation Math
 * Health Factor = (Sum of Collateral in ETH * Liquidation Threshold) / Total Debt in ETH
 */
export function calculateHealthFactor(
  collateralInEth: number,
  debtInEth: number,
  liquidationThreshold: number // e.g. 0.8
): number {
  if (debtInEth === 0) return Infinity;
  return (collateralInEth * liquidationThreshold) / debtInEth;
}
