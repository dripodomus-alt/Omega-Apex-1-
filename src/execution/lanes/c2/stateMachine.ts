import type { C2Status } from './types';

const C2_ORDER: C2Status[] = [
  'C1_CONFIRMED',
  'POST_C1_RECOMPUTED',
  'C2_DECIDED',
  'C2_SIMULATED',
  'C2_BUILT',
  'C2_SENT',
  'C2_SKIPPED',
  'C2_EXPIRED',
  'CLOSED',
];

export function assertC2Transition(from: C2Status, to: C2Status): void {
  const fromIndex = C2_ORDER.indexOf(from);
  const toIndex = C2_ORDER.indexOf(to);
  if (fromIndex < 0 || toIndex < 0 || toIndex < fromIndex) {
    throw new Error(`[C2_STATE] illegal transition ${from} -> ${to}`);
  }
}
