import type { ApprovedTransactionEnvelope } from '../../types';
import type { C1Build, C1Plan } from './types';

export function buildC1Transaction(
  plan: C1Plan,
  transaction: ApprovedTransactionEnvelope,
): C1Build {
  if (transaction.identity.executionType !== 'C1_ARBITRAGE') {
    throw new Error('[C1_BUILDER] wrong transaction lane');
  }
  if (transaction.identity.routeHash !== plan.routeHash) {
    throw new Error('[C1_BUILDER] route hash mismatch');
  }
  if (transaction.simulationHash !== plan.simulationHash) {
    throw new Error('[C1_BUILDER] simulation hash mismatch');
  }
  if (!transaction.data.startsWith('0x') || transaction.data.length < 10) {
    throw new Error('[C1_BUILDER] malformed calldata');
  }
  return { plan, transaction, status: 'C1_BUILT' };
}
