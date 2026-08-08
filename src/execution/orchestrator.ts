import type { ApprovedExecutionEnvelope, ApprovedTransactionEnvelope, StateProvenance } from './types';
import { dispatchApprovedExecution, type StrategyDispatchContext } from './dispatcher';
import { StateLockManager } from './locks/stateLockManager';
import { LaneNonceManager } from './nonce/laneNonceManager';
import { runExecutionGate } from './gates/executionGate';

export interface OrchestratorResult {
  laneDispatch: ReturnType<typeof dispatchApprovedExecution>;
  gatePassed: boolean;
  gateReasons: string[];
  nonce: number;
}

export class ExecutionOrchestrator {
  constructor(
    private readonly locks: StateLockManager,
    private readonly nonces: LaneNonceManager,
  ) {}

  prepare(
    envelope: ApprovedExecutionEnvelope,
    transaction: ApprovedTransactionEnvelope,
    currentState: StateProvenance,
    context: StrategyDispatchContext = {},
  ): OrchestratorResult {
    const laneDispatch = dispatchApprovedExecution(envelope, context);
    this.locks.acquire(envelope);
    const nonce = this.nonces.reserve(envelope);
    const gate = runExecutionGate({
      envelope,
      transaction,
      currentState,
      nonce,
      simulationPassed: true,
    });

    return {
      laneDispatch,
      gatePassed: gate.passed,
      gateReasons: gate.reasons,
      nonce: nonce.nonce,
    };
  }
}
