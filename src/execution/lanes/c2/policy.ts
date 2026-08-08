import type { C2MathResult } from '../../types';

export const MAX_C2_EXECUTIONS_PER_C1 = 5;
export const C2_MAX_BLOCKS_AFTER_PRECEDING_EXECUTION = 2;

export interface C2SequencePolicyResult {
  ok: boolean;
  expiryBlock: number;
  reason?: string;
}

export function validateC2SequencePolicy(math: C2MathResult): C2SequencePolicyResult {
  if (!Number.isInteger(math.sequence) || math.sequence < 1) {
    return {
      ok: false,
      expiryBlock: math.precedingExecutionBlock + C2_MAX_BLOCKS_AFTER_PRECEDING_EXECUTION,
      reason: 'C2_SEQUENCE_INVALID',
    };
  }

  if (math.sequence > MAX_C2_EXECUTIONS_PER_C1) {
    return {
      ok: false,
      expiryBlock: math.precedingExecutionBlock + C2_MAX_BLOCKS_AFTER_PRECEDING_EXECUTION,
      reason: 'C2_SEQUENCE_LIMIT_EXCEEDED',
    };
  }

  if (!math.precedingExecutionId) {
    return {
      ok: false,
      expiryBlock: math.precedingExecutionBlock + C2_MAX_BLOCKS_AFTER_PRECEDING_EXECUTION,
      reason: 'C2_PRECEDING_EXECUTION_MISSING',
    };
  }

  if (math.precedingExecutionBlock < math.parentC1Block) {
    return {
      ok: false,
      expiryBlock: math.parentC1Block + C2_MAX_BLOCKS_AFTER_PRECEDING_EXECUTION,
      reason: 'C2_PRECEDING_BLOCK_BEFORE_PARENT',
    };
  }

  const expiryBlock = math.precedingExecutionBlock + C2_MAX_BLOCKS_AFTER_PRECEDING_EXECUTION;
  if (math.state.blockNumber <= math.precedingExecutionBlock) {
    return {
      ok: false,
      expiryBlock,
      reason: 'C2_STATE_NOT_AFTER_PRECEDING_EXECUTION',
    };
  }

  if (math.state.blockNumber > expiryBlock) {
    return {
      ok: false,
      expiryBlock,
      reason: 'C2_TWO_BLOCK_WINDOW_EXPIRED',
    };
  }

  return { ok: true, expiryBlock };
}