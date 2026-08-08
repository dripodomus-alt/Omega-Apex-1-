import type {
  ApprovedTransactionEnvelope,
  C1MathResult,
  ExecutionIdentity,
  StateProvenance,
} from '../../types';

export type C1Status =
  | 'DISCOVERED'
  | 'C1_LOCKED'
  | 'C1_SIMULATED'
  | 'C1_BUILT'
  | 'C1_SENT'
  | 'C1_CONFIRMED'
  | 'CLOSED';

export interface C1Opportunity {
  identity: ExecutionIdentity & { executionType: 'C1_ARBITRAGE' };
  math: C1MathResult;
  preState: StateProvenance;
}

export interface C1Plan {
  opportunity: C1Opportunity;
  status: 'C1_LOCKED';
  buyPool: string;
  sellPool: string;
  routeHash: string;
  simulationHash: string;
}

export interface C1Receipt {
  txHash: string;
  blockNumber: number;
  status: 1 | 0;
  gasUsed: bigint;
  effectiveGasPrice: bigint;
}

export interface C1Commit {
  identity: C1Opportunity['identity'];
  confirmedBlock: number;
  txHash: string;
  preStateHash: string;
  routeHash: string;
  receipt: C1Receipt;
}

export interface C1Build {
  plan: C1Plan;
  transaction: ApprovedTransactionEnvelope;
  status: 'C1_BUILT';
}
