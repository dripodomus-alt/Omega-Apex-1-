import type { SettlementRecord } from './ledger';

export interface RealizedPnlSummary {
  c1Raw: bigint;
  c2Raw: bigint;
  liquidationRaw: bigint;
  totalRaw: bigint;
}

export function summarizeRealizedPnl(records: SettlementRecord[]): RealizedPnlSummary {
  const summary: RealizedPnlSummary = {
    c1Raw: 0n,
    c2Raw: 0n,
    liquidationRaw: 0n,
    totalRaw: 0n,
  };

  for (const record of records) {
    if (record.lane === 'C1') summary.c1Raw += record.realizedProfitRaw;
    if (record.lane === 'C2') summary.c2Raw += record.realizedProfitRaw;
    if (record.lane === 'LIQUIDATION') summary.liquidationRaw += record.realizedProfitRaw;
    summary.totalRaw += record.realizedProfitRaw;
  }

  return summary;
}
