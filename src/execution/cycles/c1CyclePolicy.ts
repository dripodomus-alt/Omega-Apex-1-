import type { ApprovedExecutionEnvelope } from '../types';

export const MIN_C1_EXECUTABLE_LANES_PER_CYCLE = 10;

export interface C1CyclePlan {
  cycleId: string;
  c1Lanes: ApprovedExecutionEnvelope[];
  nonBlockingC2Queue: ApprovedExecutionEnvelope[];
}

export function getExecutableC1Lanes(
  envelopes: ApprovedExecutionEnvelope[],
): ApprovedExecutionEnvelope[] {
  return envelopes.filter(
    (envelope) =>
      envelope.identity.executionType === 'C1_ARBITRAGE' &&
      envelope.math.executionType === 'C1_ARBITRAGE' &&
      envelope.math.expectedNetProfitUsd > 0 &&
      envelope.nonceOwner === 'c1_lane',
  );
}

export function assertMinimumC1ExecutableLanes(
  envelopes: ApprovedExecutionEnvelope[],
  minimum = MIN_C1_EXECUTABLE_LANES_PER_CYCLE,
): ApprovedExecutionEnvelope[] {
  const c1Lanes = getExecutableC1Lanes(envelopes);
  if (c1Lanes.length < minimum) {
    throw new Error(
      `[C1_CYCLE] requires at least ${minimum} executable C1 lanes; got ${c1Lanes.length}`,
    );
  }
  return c1Lanes;
}

export function buildContinuousC1CyclePlan(
  cycleId: string,
  envelopes: ApprovedExecutionEnvelope[],
  minimum = MIN_C1_EXECUTABLE_LANES_PER_CYCLE,
): C1CyclePlan {
  return {
    cycleId,
    c1Lanes: assertMinimumC1ExecutableLanes(envelopes, minimum),
    nonBlockingC2Queue: envelopes.filter(
      (envelope) =>
        envelope.identity.executionType === 'C2_ARBITRAGE' &&
        envelope.math.executionType === 'C2_ARBITRAGE',
    ),
  };
}