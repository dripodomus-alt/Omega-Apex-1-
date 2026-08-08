export type SettlementLane = 'C1' | 'C2' | 'LIQUIDATION';

export interface SettlementRecord {
  executionId: string;
  lane: SettlementLane;
  txHash: string;
  realizedProfitRaw: bigint;
  gasCostWei: bigint;
  settledAtMs: number;
}

export class SettlementLedger {
  private readonly records = new Map<string, SettlementRecord>();

  append(record: Omit<SettlementRecord, 'settledAtMs'>): SettlementRecord {
    if (this.records.has(record.executionId)) {
      throw new Error(`[SETTLEMENT_LEDGER] duplicate settlement ${record.executionId}`);
    }
    const finalized: SettlementRecord = {
      ...record,
      settledAtMs: Date.now(),
    };
    this.records.set(record.executionId, finalized);
    return finalized;
  }

  get(executionId: string): SettlementRecord | undefined {
    return this.records.get(executionId);
  }

  all(): SettlementRecord[] {
    return [...this.records.values()];
  }
}
