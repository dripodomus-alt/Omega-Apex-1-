import { ArbitrageRoute, ExecutionMode } from '../types';
import { BroadcastTransactionPayload, broadcastEthersOnChainTransaction } from './ethersBroadcaster';

export interface StagedPayload {
  route: ArbitrageRoute;
  pathAddresses: string[];
  inputAmountUSD: number;
  expectedProfitUSD: number;
  timestamp: string;
}

export type SubmissionOutcome = 'NOT_BROADCAST' | 'BROADCAST_SUBMITTED';

export interface DispatchResult {
  success: boolean;
  txHash?: string;
  approvedEnvelopeHash: string;
  submissionOutcome: SubmissionOutcome;
  isDryRun: boolean;
  mode: ExecutionMode;
  logs: string[];
  routeId: string;
  netProfitUSD: number;
  timestamp: string;
  polygonscanUrl?: string;
}

export interface IDispatcher {
  dispatch(payload: StagedPayload): Promise<DispatchResult>;
}

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `0x${hash.toString(16).padStart(8, '0')}`;
}

function buildApprovedEnvelopeHash(payload: StagedPayload): string {
  const canonical = JSON.stringify({
    routeId: payload.route.id,
    pathString: payload.route.pathString,
    pathAddresses: payload.pathAddresses,
    inputAmountUSD: payload.inputAmountUSD,
    expectedProfitUSD: payload.expectedProfitUSD,
    netProfitUSD: payload.route.netProfitUSD,
    slippageToleranceBps: payload.route.slippageToleranceBps,
  });
  return stableHash(canonical);
}

export class ModeTerminal implements IDispatcher {
  constructor(private readonly mode: ExecutionMode) {}

  async dispatch(payload: StagedPayload): Promise<DispatchResult> {
    const approvedEnvelopeHash = buildApprovedEnvelopeHash(payload);
    const baseLogs = [
      `[MODE TERMINAL] Envelope Hash   : ${approvedEnvelopeHash}`,
      `[MODE TERMINAL] Mode            : ${this.mode}`,
      `[MODE TERMINAL] Route ID        : ${payload.route.id}`,
      `[MODE TERMINAL] Path            : ${payload.route.pathString}`,
      `[MODE TERMINAL] Expected Net    : $${payload.route.netProfitUSD.toFixed(2)}`,
    ];

    if (this.mode !== 'LIVE') {
      const logs = [
        ...baseLogs,
        `[MODE TERMINAL] Outcome         : NOT_BROADCAST`,
        `[MODE TERMINAL] Note            : Approved envelope archived; no signature or chain submission in ${this.mode}.`,
      ];
      logs.forEach((line) => console.log(line));
      return {
        success: true,
        approvedEnvelopeHash,
        submissionOutcome: 'NOT_BROADCAST',
        isDryRun: true,
        mode: this.mode,
        logs,
        routeId: payload.route.id,
        netProfitUSD: payload.route.netProfitUSD,
        timestamp: payload.timestamp,
      };
    }

    const broadcastPayload: BroadcastTransactionPayload = {
      route: payload.route,
      routeId: payload.route.id,
      pathAddresses: payload.pathAddresses,
      inputAmountUSD: payload.inputAmountUSD,
      expectedProfitUSD: payload.expectedProfitUSD,
    };
    const result = await broadcastEthersOnChainTransaction(broadcastPayload);
    const logs = [...baseLogs, ...result.confirmationLogs];
    return {
      success: result.success,
      txHash: result.txHash,
      approvedEnvelopeHash,
      submissionOutcome: 'BROADCAST_SUBMITTED',
      isDryRun: false,
      mode: 'LIVE',
      logs,
      routeId: payload.route.id,
      netProfitUSD: payload.route.netProfitUSD,
      timestamp: payload.timestamp,
      polygonscanUrl: result.polygonscanUrl,
    };
  }
}

export class LiveDispatcher extends ModeTerminal {
  constructor() { super('LIVE'); }
}

export class DryRunDispatcher extends ModeTerminal {
  constructor() { super('DRY_RUN'); }
}

export function createDispatcher(mode: ExecutionMode): IDispatcher {
  return new ModeTerminal(mode);
}
