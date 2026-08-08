import type { ApprovedTransactionEnvelope } from '../../types';
import type { LiquidationBuild, LiquidationPlan } from './types';

export function buildLiquidationTransaction(
  plan: LiquidationPlan,
  transaction: ApprovedTransactionEnvelope,
): LiquidationBuild {
  if (transaction.identity.executionType !== 'LIQUIDATION') {
    throw new Error('[LIQ_BUILDER] wrong transaction lane');
  }
  if (transaction.identity.routeHash !== plan.math.routeHash) {
    throw new Error('[LIQ_BUILDER] unwind route hash mismatch');
  }
  if (!transaction.data.startsWith('0x') || transaction.data.length < 10) {
    throw new Error('[LIQ_BUILDER] malformed liquidation calldata');
  }
  return { plan, transaction, status: 'LIQ_BUILT' };
}
