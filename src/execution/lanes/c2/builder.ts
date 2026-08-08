import type { ApprovedTransactionEnvelope } from '../../types';
import type { C2Build, C2Plan } from './types';

export function buildC2Transaction(plan: C2Plan, transaction: ApprovedTransactionEnvelope): C2Build {
  if (transaction.identity.executionType !== 'C2_ARBITRAGE') {
    throw new Error('[C2_BUILDER] wrong transaction lane');
  }
  if (transaction.identity.executionId === plan.parent.identity.executionId) {
    throw new Error('[C2_BUILDER] C2 cannot reuse parent C1 execution id');
  }
  if (transaction.stateHash !== plan.postState.stateHash) {
    throw new Error('[C2_BUILDER] transaction state hash is not post-C1 state hash');
  }
  if (!transaction.data.startsWith('0x') || transaction.data.length < 10) {
    throw new Error('[C2_BUILDER] malformed calldata');
  }
  return { plan, transaction, status: 'C2_BUILT' };
}
