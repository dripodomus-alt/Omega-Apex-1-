import type { ApprovedTransactionEnvelope, C2MathResult, StateProvenance } from '../../types';
import type { C1Commit } from '../c1/types';

export type C2Action = 'MIRROR' | 'REVERSE' | 'DO_NOTHING' | 'EXPIRE';

export type C2Status =
  | 'C1_CONFIRMED'
  | 'POST_C1_RECOMPUTED'
  | 'C2_DECIDED'
  | 'C2_SIMULATED'
  | 'C2_BUILT'
  | 'C2_SENT'
  | 'C2_SKIPPED'
  | 'C2_EXPIRED'
  | 'CLOSED';

export interface PostC1Snapshot extends StateProvenance {
  parentC1Id: string;
  parentConfirmedBlock: number;
}

export interface C2Plan {
  parent: C1Commit;
  postState: PostC1Snapshot;
  math: C2MathResult;
  action: C2Action;
  expiryBlock: number;
}

export interface C2Build {
  plan: C2Plan;
  transaction: ApprovedTransactionEnvelope;
  status: 'C2_BUILT';
}

export interface C2Receipt {
  txHash: string;
  blockNumber: number;
  status: 1 | 0;
  gasUsed: bigint;
  effectiveGasPrice: bigint;
}
