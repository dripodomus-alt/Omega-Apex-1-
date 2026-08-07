import type { PoolInfo } from '../types';

export interface AmountOutQuote {
  amountOut: bigint;
  feeAmount: bigint;
  reserveIn: bigint;
  reserveOut: bigint;
}

function usdReserveToNativeUnits(reserveUsd: number, decimals: number): bigint {
  if (!Number.isFinite(reserveUsd) || reserveUsd <= 0) return 0n;
  const scale = 10 ** Math.min(decimals, 12);
  const scaled = BigInt(Math.max(0, Math.round(reserveUsd * scale)));
  return decimals > 12 ? scaled * 10n ** BigInt(decimals - 12) : scaled;
}

function resolveReserves(pool: PoolInfo, tokenInAddress?: string): { reserveIn: bigint; reserveOut: bigint } {
  const tokenIn = tokenInAddress?.toLowerCase();
  const token0 = pool.token0.address.toLowerCase();
  const token1 = pool.token1.address.toLowerCase();

  const reserve0 = usdReserveToNativeUnits(pool.reserve0USD, pool.token0.decimals);
  const reserve1 = usdReserveToNativeUnits(pool.reserve1USD, pool.token1.decimals);

  if (tokenIn === token1) {
    return { reserveIn: reserve1, reserveOut: reserve0 };
  }

  if (tokenIn && tokenIn !== token0) {
    throw new Error(`[Pricing] tokenIn ${tokenInAddress} does not match pool ${pool.id}`);
  }

  return { reserveIn: reserve0, reserveOut: reserve1 };
}

export async function getAmountOut(pool: PoolInfo, amountIn: bigint): Promise<AmountOutQuote> {
  if (amountIn <= 0n) {
    return { amountOut: 0n, feeAmount: 0n, reserveIn: 0n, reserveOut: 0n };
  }

  const { reserveIn, reserveOut } = resolveReserves(pool, pool.tokenInAddress);
  if (reserveIn <= 0n || reserveOut <= 0n) {
    throw new Error(`[Pricing] pool ${pool.id} has insufficient reserve data`);
  }

  const feeBps = BigInt(Math.max(0, Math.min(10_000, Math.trunc(pool.feeBps))));
  const amountInAfterFee = (amountIn * (10_000n - feeBps)) / 10_000n;
  const denominator = reserveIn + amountInAfterFee;
  const amountOut = denominator === 0n ? 0n : (amountInAfterFee * reserveOut) / denominator;

  return {
    amountOut,
    feeAmount: amountIn - amountInAfterFee,
    reserveIn,
    reserveOut,
  };
}