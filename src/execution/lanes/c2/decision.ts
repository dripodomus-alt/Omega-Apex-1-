import type { C1Commit } from '../c1/types';
import type { C2Action, C2Plan, PostC1Snapshot } from './types';
import type { C2MathResult } from '../../types';

export function decideC2(
  parent: C1Commit,
  postState: PostC1Snapshot,
  math: C2MathResult,
): C2Plan {
  if (math.executionType !== 'C2_ARBITRAGE') {
    throw new Error('[C2_DECISION] wrong-lane math result');
  }
  if (math.parentC1Id !== parent.identity.executionId) {
    throw new Error('[C2_DECISION] parent C1 mismatch');
  }
  if (math.postStateHash !== postState.stateHash) {
    throw new Error('[C2_DECISION] post-state hash mismatch');
  }
  const earliest = parent.confirmedBlock + 1;
  const latest = parent.confirmedBlock + 5;
  if (postState.blockNumber < earliest || postState.blockNumber > latest) {
    return { parent, postState, math, action: 'EXPIRE', expiryBlock: latest };
  }
  const action: C2Action =
    math.action === 'DO_NOTHING' || math.expectedNetProfitUsd <= 0 ? 'DO_NOTHING' : math.action;
  return { parent, postState, math, action, expiryBlock: latest };
}
