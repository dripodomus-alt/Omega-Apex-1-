import { ArbitrageRoute, ExecutionMode } from '../types';
import { BroadcastTransactionPayload, broadcastEthersOnChainTransaction } from './ethersBroadcaster';

// ─────────────────────────────────────────────────────────────────────────────
// Shared payload produced by the Staging stage and consumed by the Dispatch sink
// ─────────────────────────────────────────────────────────────────────────────

export interface StagedPayload {
  route: ArbitrageRoute;
  pathAddresses: string[];
  inputAmountUSD: number;
  expectedProfitUSD: number;
  timestamp: string;
}

export interface DispatchResult {
  success: boolean;
  txHash: string;
  isDryRun: boolean;
  mode: ExecutionMode;
  logs: string[];
  routeId: string;
  netProfitUSD: number;
  timestamp: string;
  polygonscanUrl?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Dispatcher interface — isolates the dispatch sink from the rest of the pipeline
// ─────────────────────────────────────────────────────────────────────────────

export interface IDispatcher {
  dispatch(payload: StagedPayload): Promise<DispatchResult>;
}

// ─────────────────────────────────────────────────────────────────────────────
// LiveDispatcher — connects to broadcast infrastructure and submits real txns
// ─────────────────────────────────────────────────────────────────────────────

export class LiveDispatcher implements IDispatcher {
  async dispatch(payload: StagedPayload): Promise<DispatchResult> {
    const broadcastPayload: BroadcastTransactionPayload = {
      routeId: payload.route.id,
      pathAddresses: payload.pathAddresses,
      inputAmountUSD: payload.inputAmountUSD,
      expectedProfitUSD: payload.expectedProfitUSD,
    };

    const result = await broadcastEthersOnChainTransaction(broadcastPayload);

    return {
      success: result.success,
      txHash: result.txHash,
      isDryRun: false,
      mode: 'LIVE',
      logs: result.confirmationLogs,
      routeId: payload.route.id,
      netProfitUSD: payload.route.netProfitUSD,
      timestamp: payload.timestamp,
      polygonscanUrl: result.polygonscanUrl,
    };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// DryRunDispatcher — formats the exact payload that would have been sent and
// logs it with [DRY RUN SIMULATION] indicators.  All external network writes,
// database mutations, and API state changes are disabled.
// ─────────────────────────────────────────────────────────────────────────────

export class DryRunDispatcher implements IDispatcher {
  async dispatch(payload: StagedPayload): Promise<DispatchResult> {
    const { route, timestamp } = payload;

    // Generate a deterministic-looking simulated tx hash for audit parity
    const simulatedTxHash =
      '0x' +
      Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join('');

    const logs: string[] = [
      `[DRY RUN SIMULATION] ============================================`,
      `[DRY RUN SIMULATION] Timestamp        : ${timestamp}`,
      `[DRY RUN SIMULATION] Route ID         : ${route.id}`,
      `[DRY RUN SIMULATION] Path             : ${route.pathString}`,
      `[DRY RUN SIMULATION] Input Capital    : $${payload.inputAmountUSD.toLocaleString()} USD`,
      `[DRY RUN SIMULATION] Gross Profit     : $${route.grossProfitUSD.toFixed(2)}`,
      `[DRY RUN SIMULATION] Estimated Gas    : $${route.estimatedGasUSD.toFixed(2)}`,
      `[DRY RUN SIMULATION] Net Profit (est) : $${route.netProfitUSD.toFixed(2)}`,
      `[DRY RUN SIMULATION] VQC Alpha Score  : ${route.vqcAlphaScore}`,
      `[DRY RUN SIMULATION] Win Probability  : ${(route.vqcWinProbability * 100).toFixed(1)}%`,
      `[DRY RUN SIMULATION] Simulated Tx Hash: ${simulatedTxHash}`,
      `[DRY RUN SIMULATION] NOTE: No on-chain transaction submitted. No state mutations applied.`,
      `[DRY RUN SIMULATION] ============================================`,
    ];

    // Write to console so the audit trail is visible in server logs
    logs.forEach((line) => console.log(line));

    return {
      success: true,
      txHash: simulatedTxHash,
      isDryRun: true,
      mode: 'DRY_RUN',
      logs,
      routeId: route.id,
      netProfitUSD: route.netProfitUSD,
      timestamp,
      polygonscanUrl: undefined,
    };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Factory — returns the correct dispatcher for the active execution mode
// ─────────────────────────────────────────────────────────────────────────────

export function createDispatcher(mode: ExecutionMode): IDispatcher {
  return mode === 'LIVE' ? new LiveDispatcher() : new DryRunDispatcher();
}
