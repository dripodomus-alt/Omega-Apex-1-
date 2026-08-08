import type { ApprovedExecutionEnvelope, ExecutionDispatchResult } from './types';
import { planC1 } from './lanes/c1/planner';
import { decideC2 } from './lanes/c2/decision';
import type { C1Commit } from './lanes/c1/types';
import type { PostC1Snapshot } from './lanes/c2/types';
import { planLiquidation } from './lanes/liquidation/planner';
import type { LiquidationOpportunity } from './lanes/liquidation/types';

export interface StrategyDispatchContext {
  parentC1?: C1Commit;
  postC1State?: PostC1Snapshot;
  liquidationOpportunity?: LiquidationOpportunity;
}

export function dispatchApprovedExecution(
  envelope: ApprovedExecutionEnvelope,
  context: StrategyDispatchContext = {},
): ExecutionDispatchResult {
  switch (envelope.identity.executionType) {
    case 'C1_ARBITRAGE': {
      planC1(envelope);
      return {
        accepted: true,
        executionType: 'C1_ARBITRAGE',
        lane: 'C1',
        status: 'C1_LOCKED',
      };
    }
    case 'C2_ARBITRAGE': {
      if (!context.parentC1 || !context.postC1State || envelope.math.executionType !== 'C2_ARBITRAGE') {
        throw new Error('[EXECUTION_DISPATCH] C2 requires parent C1 commit and post-C1 state');
      }
      const plan = decideC2(context.parentC1, context.postC1State, envelope.math);
      return {
        accepted: plan.action !== 'DO_NOTHING' && plan.action !== 'EXPIRE',
        executionType: 'C2_ARBITRAGE',
        lane: 'C2',
        status: plan.action === 'EXPIRE' ? 'C2_EXPIRED' : plan.action === 'DO_NOTHING' ? 'C2_SKIPPED' : 'C2_DECIDED',
        reason: plan.action,
      };
    }
    case 'LIQUIDATION': {
      if (!context.liquidationOpportunity) {
        throw new Error('[EXECUTION_DISPATCH] liquidation requires liquidation opportunity context');
      }
      planLiquidation(envelope, context.liquidationOpportunity);
      return {
        accepted: true,
        executionType: 'LIQUIDATION',
        lane: 'LIQUIDATION',
        status: 'LIQ_SIZED',
      };
    }
    default:
      throw new Error('[EXECUTION_DISPATCH] unsupported execution type');
  }
}
