import type { ApprovedTransactionEnvelope, StateProvenance } from '../../types';
import type { C1Plan } from './types';

export function preflightC1(
  plan: C1Plan,
  tx: ApprovedTransactionEnvelope,
  currentState: StateProvenance,
): true {
  if (currentState.blockNumber < plan.opportunity.preState.blockNumber) {
    throw new Error('[C1_PREFLIGHT] current block regressed');
  }
  if (currentState.stateHash !== tx.stateHash) {
    throw new Error('[C1_PREFLIGHT] state hash drift');
  }
  if (tx.expectedNetProfitUsd <= 0) {
    throw new Error('[C1_PREFLIGHT] non-positive net profit');
  }
  return true;
}
