import type { LiquidationReceipt } from './types';

export interface RealizedLiquidationDelta {
  executionId: string;
  lane: 'LIQUIDATION';
  txHash: string;
  seizedCollateralRaw: bigint;
  gasCostWei: bigint;
  realizedProfitRaw: bigint;
}

export function settleLiquidation(
  executionId: string,
  receipt: LiquidationReceipt,
  realizedProfitRaw: bigint,
): RealizedLiquidationDelta {
  if (receipt.status !== 1) {
    throw new Error('[LIQ_SETTLEMENT] receipt failed');
  }
  return {
    executionId,
    lane: 'LIQUIDATION',
    txHash: receipt.txHash,
    seizedCollateralRaw: receipt.seizedCollateralRaw,
    gasCostWei: receipt.gasUsed * receipt.effectiveGasPrice,
    realizedProfitRaw,
  };
}
