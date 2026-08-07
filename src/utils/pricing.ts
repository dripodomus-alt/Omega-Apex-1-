import type { PoolInfo } from '../types';

/**
 * Simulates a swap on a given pool to estimate the output amount in wei.
 * This is a simplified off-chain calculation for slippage protection.
 * For CLMM pools (like Uniswap V3), this uses a CPMM approximation based on current reserves.
 * A more precise CLMM simulation would involve iterating through price ranges,
 * which is too complex for a quick off-chain estimate for slippage.
 *
 * @param pool The pool information. `pool.tokenInAddress` and `pool.tokenOutAddress` must be set.
 * @param amountIn The input amount in wei (BigInt).
 * @returns An object containing the estimated amountOut in wei (BigInt).
 */
export async function getAmountOut(
  pool: PoolInfo,
  amountIn: bigint
): Promise<{ amountOut: bigint }> {
  const feeBps = BigInt(pool.feeBps); // Fee in basis points (e.g., 30 for 0.3%)

  const tokenInAddress = pool.tokenInAddress;
  const tokenOutAddress = pool.tokenOutAddress;

  if (!tokenInAddress || !tokenOutAddress) {
    throw new Error(`[Pricing] Pool ${pool.id} is missing tokenInAddress or tokenOutAddress.`);
  }

  let reserveIn: bigint;
  let reserveOut: bigint;

  // Determine which token is token0 and token1 for reserve mapping
  const isToken0In = pool.token0.address.toLowerCase() === tokenInAddress.toLowerCase();

  // For Uniswap V3, we'll use a simplified CPMM approximation based on its current reserves.
  // A true V3 simulation is complex (tick math). For off-chain slippage, this is a reasonable heuristic.
  // The `pool.reserve0` and `pool.reserve1` are assumed to be in token wei units.
  if (isToken0In) {
    reserveIn = BigInt(pool.reserve0);
    reserveOut = BigInt(pool.reserve1);
  } else {
    reserveIn = BigInt(pool.reserve1);
    reserveOut = BigInt(pool.reserve0);
  }

  // Handle potential zero reserves to prevent division by zero
  if (reserveIn === 0n || reserveOut === 0n) {
    console.warn(`[Pricing] Zero reserve detected for pool ${pool.id}. Returning 0 amountOut.`);
    return { amountOut: 0n };
  }

  // Apply fee: amountInAfterFee = amountIn * (10000 - feeBps) / 10000
  // Use 10000n for basis points calculation
  const amountInAfterFee = (amountIn * (10000n - feeBps)) / 10000n;

  // CPMM formula: amountOut = (reserveOut * amountInAfterFee) / (reserveIn + amountInAfterFee)
  const estimatedAmountOut = (reserveOut * amountInAfterFee) / (reserveIn + amountInAfterFee);

  return { amountOut: estimatedAmountOut };
}