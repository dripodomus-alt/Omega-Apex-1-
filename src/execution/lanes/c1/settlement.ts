import type { C1Commit } from './types';

export interface RealizedC1Delta {
  executionId: string;
  lane: 'C1';
  txHash: string;
  gasCostWei: bigint;
  realizedProfitRaw: bigint;
}

export function settleC1(commit: C1Commit, realizedProfitRaw: bigint): RealizedC1Delta {
  return {
    executionId: commit.identity.executionId,
    lane: 'C1',
    txHash: commit.txHash,
    gasCostWei: commit.receipt.gasUsed * commit.receipt.effectiveGasPrice,
    realizedProfitRaw,
  };
}
