import type { C1Status } from './types';

const C1_ORDER: C1Status[] = [
  'DISCOVERED',
  'C1_LOCKED',
  'C1_SIMULATED',
  'C1_BUILT',
  'C1_SENT',
  'C1_CONFIRMED',
  'CLOSED',
];

export function assertC1Transition(from: C1Status, to: C1Status): void {
  const fromIndex = C1_ORDER.indexOf(from);
  const toIndex = C1_ORDER.indexOf(to);
  if (fromIndex < 0 || toIndex < 0 || toIndex < fromIndex) {
    throw new Error(`[C1_STATE] illegal transition ${from} -> ${to}`);
  }
}

export function transitionC1(from: C1Status, to: C1Status): C1Status {
  assertC1Transition(from, to);
  return to;
}
