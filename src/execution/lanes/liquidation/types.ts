import type { ApprovedTransactionEnvelope, LiquidationMathResult, StateProvenance } from '../../types';

export type LiquidationStatus =
  | 'BORROWER_DISCOVERED'
  | 'LIQ_ELIGIBLE'
  | 'LIQ_LOCKED'
  | 'LIQ_SIZED'
  | 'LIQ_SIMULATED'
  | 'LIQ_BUILT'
  | 'LIQ_SENT'
  | 'LIQ_CONFIRMED'
  | 'LIQ_SETTLED'
  | 'CLOSED';

export interface BorrowerState {
  borrower: string;
  healthFactorX18: bigint;
  debtAsset: string;
  collateralAsset: string;
  totalDebtBaseRaw: bigint;
  collateralRaw: bigint;
  closeFactorBps: number;
  liquidationBonusBps: number;
  state: StateProvenance;
}

export interface LiquidationOpportunity {
  borrower: BorrowerState;
  status: 'LIQ_ELIGIBLE';
  maxDebtToCoverRaw: bigint;
}

export interface LiquidationPlan {
  opportunity: LiquidationOpportunity;
  math: LiquidationMathResult;
  status: 'LIQ_SIZED';
}

export interface LiquidationBuild {
  plan: LiquidationPlan;
  transaction: ApprovedTransactionEnvelope;
  status: 'LIQ_BUILT';
}

export interface LiquidationReceipt {
  txHash: string;
  blockNumber: number;
  status: 1 | 0;
  gasUsed: bigint;
  effectiveGasPrice: bigint;
  seizedCollateralRaw: bigint;
}
