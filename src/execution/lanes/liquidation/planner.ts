import type { ApprovedExecutionEnvelope } from '../../types';
import type { LiquidationOpportunity, LiquidationPlan } from './types';

export function planLiquidation(
  envelope: ApprovedExecutionEnvelope,
  opportunity: LiquidationOpportunity,
): LiquidationPlan {
  if (envelope.identity.executionType !== 'LIQUIDATION' || envelope.math.executionType !== 'LIQUIDATION') {
    throw new Error('[LIQ_PLANNER] wrong-lane envelope');
  }
  if (envelope.math.borrower.toLowerCase() !== opportunity.borrower.borrower.toLowerCase()) {
    throw new Error('[LIQ_PLANNER] borrower mismatch');
  }
  if (envelope.math.expectedNetProfitUsd <= 0) {
    throw new Error('[LIQ_PLANNER] unprofitable liquidation');
  }
  return {
    opportunity,
    math: envelope.math,
    status: 'LIQ_SIZED',
  };
}
