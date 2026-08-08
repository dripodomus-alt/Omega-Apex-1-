import type { ApprovedExecutionEnvelope } from '../types';

export interface BundlePolicyResult {
  ok: boolean;
  reason?: string;
}

export function validateBundleIsolation(envelopes: ApprovedExecutionEnvelope[]): BundlePolicyResult {
  const seenParentC2 = new Set<string>();
  for (const envelope of envelopes) {
    if (envelope.math.executionType === 'C2_ARBITRAGE') {
      seenParentC2.add(envelope.math.parentC1Id);
    }
  }
  for (const envelope of envelopes) {
    if (envelope.math.executionType === 'C1_ARBITRAGE' && seenParentC2.has(envelope.identity.executionId)) {
      return {
        ok: false,
        reason: 'parent C1 and child C2 cannot share one bundle',
      };
    }
    if (envelope.math.executionType === 'LIQUIDATION' && envelopes.length > 1) {
      return {
        ok: false,
        reason: 'liquidation execution must use an isolated bundle',
      };
    }
  }
  return { ok: true };
}
