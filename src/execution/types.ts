import type { RankedRouteCandidate } from '../engine/market/types';

export type ExecutionType = 'C1_ARBITRAGE' | 'C2_ARBITRAGE' | 'LIQUIDATION';
export type ExecutionMode = 'DEV' | 'TEST' | 'SIM' | 'DRY_RUN' | 'LIVE';

export type ExecutionStatus =
  | 'DISCOVERED'
  | 'C1_LOCKED'
  | 'C1_SIMULATED'
  | 'C1_BUILT'
  | 'C1_SENT'
  | 'C1_CONFIRMED'
  | 'POST_C1_RECOMPUTED'
  | 'C2_DECIDED'
  | 'C2_SIMULATED'
  | 'C2_BUILT'
  | 'C2_SENT'
  | 'C2_SKIPPED'
  | 'C2_EXPIRED'
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

export interface StateProvenance {
  chainId: 137;
  blockNumber: number;
  blockHash: string;
  stateHash: string;
  observedAtMs: number;
}

export interface ExecutionIdentity {
  executionId: string;
  executionType: ExecutionType;
  candidateHash: string;
  routeHash: string;
}

export interface RustMathBaseResult {
  executionType: ExecutionType;
  state: StateProvenance;
  routeHash: string;
  simulationHash: string;
  calldataHash?: string;
  optimalInputRaw: string;
  expectedNetProfitUsd: number;
  gasCostUsd: number;
  flashFeeUsd: number;
  slippageBps: number;
}

export interface C1MathResult extends RustMathBaseResult {
  executionType: 'C1_ARBITRAGE';
  candidate: RankedRouteCandidate;
  leg1ExpectedOutputRaw: string;
  leg2ExpectedOutputRaw: string;
}

export interface C2MathResult extends RustMathBaseResult {
  executionType: 'C2_ARBITRAGE';
  parentC1Id: string;
  parentC1Block: number;
  sequence: number;
  precedingExecutionId: string;
  precedingExecutionBlock: number;
  postStateHash: string;
  action: 'MIRROR' | 'REVERSE' | 'DO_NOTHING' | 'EXPIRE';
  expiryBlock: number;
}

export interface LiquidationMathResult extends RustMathBaseResult {
  executionType: 'LIQUIDATION';
  borrower: string;
  debtAsset: string;
  collateralAsset: string;
  debtToCoverRaw: string;
  expectedCollateralSeizedRaw: string;
  liquidationBonusBps: number;
  unwindRouteHash: string;
}

export type RustMathResult = C1MathResult | C2MathResult | LiquidationMathResult;

export interface ResourceLock {
  kind: 'ROUTE' | 'POOL' | 'BORROWER' | 'ASSET' | 'STATE';
  id: string;
}

export interface ApprovedExecutionEnvelope {
  schemaVersion: 'apex.execution.approved.v1';
  identity: ExecutionIdentity;
  mode: ExecutionMode;
  math: RustMathResult;
  resources: ResourceLock[];
  nonceOwner: 'c1_lane' | 'c2_lane' | 'liquidation_lane';
  createdAtMs: number;
}

export interface ApprovedTransactionEnvelope {
  schemaVersion: 'apex.execution.tx.v1';
  identity: ExecutionIdentity;
  mode: ExecutionMode;
  to: string;
  data: string;
  valueRaw: string;
  nonce: number;
  stateHash: string;
  simulationHash: string;
  calldataHash: string;
  expectedNetProfitUsd: number;
  createdAtMs: number;
}

export interface ExecutionDispatchResult {
  accepted: boolean;
  executionType: ExecutionType;
  lane: 'C1' | 'C2' | 'LIQUIDATION';
  status: ExecutionStatus;
  reason?: string;
}
