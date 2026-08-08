import type { LiquidationStatus } from './types';

const LIQ_ORDER: LiquidationStatus[] = [
  'BORROWER_DISCOVERED',
  'LIQ_ELIGIBLE',
  'LIQ_LOCKED',
  'LIQ_SIZED',
  'LIQ_SIMULATED',
  'LIQ_BUILT',
  'LIQ_SENT',
  'LIQ_CONFIRMED',
  'LIQ_SETTLED',
  'CLOSED',
];

export function assertLiquidationTransition(from: LiquidationStatus, to: LiquidationStatus): void {
  const fromIndex = LIQ_ORDER.indexOf(from);
  const toIndex = LIQ_ORDER.indexOf(to);
  if (fromIndex < 0 || toIndex < 0 || toIndex < fromIndex) {
    throw new Error(`[LIQ_STATE] illegal transition ${from} -> ${to}`);
  }
}
