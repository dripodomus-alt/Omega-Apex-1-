import type { C2Receipt } from './types';

export interface RealizedC2Delta {
  executionId: string;
  parentC1Id: string;
  lane: 'C2';
  txHash: string;
  gasCostWei: bigint;
  realizedProfitRaw: bigint;
}

export function settleC2(
  executionId: string,
  parentC1Id: string,
  receipt: C2Receipt,
  realizedProfitRaw: bigint,
): RealizedC2Delta {
  if (receipt.status !== 1) {
    throw new Error('[C2_SETTLEMENT] receipt failed');
  }
  return {
    executionId,
    parentC1Id,
    lane: 'C2',
    txHash: receipt.txHash,
    gasCostWei: receipt.gasUsed * receipt.effectiveGasPrice,
    realizedProfitRaw,
  };
}
