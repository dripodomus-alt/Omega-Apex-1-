import type { ApprovedExecutionEnvelope, ApprovedTransactionEnvelope, StateProvenance } from '../types';
import type { NonceReservation } from '../nonce/laneNonceManager';

export interface ExecutionGateInput {
  envelope: ApprovedExecutionEnvelope;
  transaction: ApprovedTransactionEnvelope;
  currentState: StateProvenance;
  nonce: NonceReservation;
  simulationPassed: boolean;
}

export interface ExecutionGateResult {
  passed: boolean;
  reasons: string[];
}

export function runExecutionGate(input: ExecutionGateInput): ExecutionGateResult {
  const reasons: string[] = [];
  const { envelope, transaction, currentState, nonce } = input;

  if (!input.simulationPassed) reasons.push('SIMULATION_FAILED');
  if (currentState.chainId !== 137) reasons.push('WRONG_CHAIN');
  if (currentState.stateHash !== transaction.stateHash) reasons.push('STATE_HASH_DRIFT');
  if (transaction.simulationHash !== envelope.math.simulationHash) reasons.push('SIMULATION_HASH_MISMATCH');
  if (transaction.calldataHash !== envelope.math.calldataHash) reasons.push('CALLDATA_HASH_MISMATCH');
  if (transaction.expectedNetProfitUsd <= 0) reasons.push('UNPROFITABLE');
  if (nonce.lane !== envelope.nonceOwner) reasons.push('NONCE_LANE_MISMATCH');
  if (nonce.executionId !== envelope.identity.executionId) reasons.push('NONCE_OWNER_MISMATCH');

  return {
    passed: reasons.length === 0,
    reasons,
  };
}
