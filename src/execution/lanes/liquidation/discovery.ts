import type { BorrowerState, LiquidationOpportunity } from './types';

const ONE_X18 = 10n ** 18n;

export function discoverLiquidationOpportunity(borrower: BorrowerState): LiquidationOpportunity | null {
  if (borrower.healthFactorX18 >= ONE_X18) return null;
  const maxDebtToCoverRaw = (borrower.totalDebtBaseRaw * BigInt(borrower.closeFactorBps)) / 10_000n;
  if (maxDebtToCoverRaw <= 0n) return null;
  return {
    borrower,
    status: 'LIQ_ELIGIBLE',
    maxDebtToCoverRaw,
  };
}
