import type { ApprovedExecutionEnvelope } from '../../types';
import type { C1Opportunity, C1Plan } from './types';

export function buildC1Opportunity(envelope: ApprovedExecutionEnvelope): C1Opportunity {
  if (envelope.identity.executionType !== 'C1_ARBITRAGE' || envelope.math.executionType !== 'C1_ARBITRAGE') {
    throw new Error('[C1_PLANNER] wrong-lane envelope');
  }
  if (envelope.math.expectedNetProfitUsd <= 0) {
    throw new Error('[C1_PLANNER] unprofitable C1 math result');
  }
  return {
    identity: {
      ...envelope.identity,
      executionType: 'C1_ARBITRAGE',
    },
    math: envelope.math,
    preState: envelope.math.state,
  };
}

export function planC1(envelope: ApprovedExecutionEnvelope): C1Plan {
  const opportunity = buildC1Opportunity(envelope);
  const buyPool = opportunity.math.candidate.buy.poolId;
  const sellPool = opportunity.math.candidate.sell.poolId;
  if (!buyPool || !sellPool || buyPool === sellPool) {
    throw new Error('[C1_PLANNER] C1 requires distinct executable buy/sell pools');
  }
  return {
    opportunity,
    status: 'C1_LOCKED',
    buyPool,
    sellPool,
    routeHash: opportunity.math.routeHash,
    simulationHash: opportunity.math.simulationHash,
  };
}
