/**
 * OMEGA V5 — Transaction Logger Helper & Runner
 *
 * Fetches transaction hashes and their on-chain receipts with maximum speed
 * and accuracy using two complementary strategies:
 *
 *   SPEED  — `TxHashFetcher` races ALL configured RPC endpoints in parallel
 *             (Promise.race) and returns the first successful receipt.
 *
 *   ACCURACY — Quorum cross-validation: before a receipt is accepted as final
 *              it must be confirmed by at least `quorumThreshold` independent
 *              RPC nodes.  This prevents acting on a stale or incorrect response
 *              from a single misbehaving node.
 *
 * The `TxRunner` ties these together into a polling loop that drives each
 * tracked hash through a defined lifecycle:
 *
 *   PENDING → CONFIRMING → CONFIRMED (success=true)
 *                        → REVERTED  (success=false)
 *                        → DROPPED   (timeout)
 *
 * When a transaction is REVERTED, the runner will attempt to fetch the revert
 * reason by re-playing the transaction via `eth_call`.
 *
 * Output is compatible with the existing `LiveTradeLog` shape so results can
 * be written directly to the Firestore audit trail or rendered by the UI.
 *
 * Design constraints:
 *   - Uses existing project dependencies (`ethers`) and utils.
 *   - Safe for concurrent callers (JS single-threaded event loop, no shared mutable state
 *     across `TxRunner` instances).
 *   - Works in both browser (import.meta.env) and Node.js (process.env) environments.
 */

import { ethers } from 'ethers';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';
import { getOmegaRpcRouter } from './rpcRouter';
import type { LiveTradeLog } from '../types';

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

export type TxStatus = 'PENDING' | 'CONFIRMING' | 'CONFIRMED' | 'REVERTED' | 'DROPPED';

/** Enriched record maintained by TxRunner for every tracked hash. */
export interface TxRecord {
  /** The 0x-prefixed 32-byte transaction hash. */
  txHash: string;
  /** Lifecycle status of this record. */
  status: TxStatus;
  /** Unix timestamp (ms) when this record was first registered. */
  registeredAt: number;
  /** Unix timestamp (ms) of the most recent poll attempt. */
  lastPolledAt: number;
  /** Block number in which the tx was included (undefined while PENDING). */
  blockNumber?: number;
  /** Number of block confirmations seen so far. */
  confirmations: number;
  /** Gas used by the tx (in gas units), populated after receipt. */
  gasUsed?: bigint;
  /** Effective gas price in Wei, populated after receipt. */
  effectiveGasPriceWei?: bigint;
  /** Decoded revert reason, if available. */
  revertReason?: string;
  /** Which RPC endpoint provided the authoritative receipt. */
  confirmedByEndpoint?: string;
  /** How many independent RPC nodes agreed on the receipt. */
  quorumCount: number;
  /** Number of polling rounds attempted. */
  pollCount: number;
  /** Free-form metadata attached at registration (routeId, assetPair, etc.). */
  meta: TxMeta;
}

/** Optional metadata attached to a tx at registration time. */
export interface TxMeta {
  routeId?: string;
  assetPair?: string;
  executionType?: 'HFT_ARBITRAGE' | 'AAVE_LIQUIDATION';
  contractAddress?: string;
  flashloanAmount?: string;
  expectedProfitUSD?: number;
  mevRelay?: string;
}

/** Configuration for `TxHashFetcher` and `TxRunner`. */
export interface TxLoggerConfig {
  /**
   * Ordered list of RPC endpoints to poll.  Defaults to all endpoints in
   * `POLYGON_CHAIN_CONFIG.rpcEndpoints` when omitted.
   */
  endpoints?: { url: string; label: string }[];
  /**
   * Number of independent RPC nodes that must agree on a receipt before
   * the result is accepted.  Higher values increase accuracy at the cost of
   * latency.  Default: 2.
   */
  quorumThreshold?: number;
  /**
   * Milliseconds before a single RPC call is considered a timeout failure.
   * Default: 3 500.
   */
  rpcTimeoutMs?: number;
  /**
   * Milliseconds to wait before the first poll attempt.
   * Default: 1 000 (roughly half a Polygon block).
   */
  initialPollDelayMs?: number;
  /**
   * Polling interval base (ms).  Actual delay = base * (2^attempt) + jitter.
   * Default: 1 500.
   */
  pollBaseIntervalMs?: number;
  /**
   * Maximum polling interval cap (ms).  Prevents runaway backoff on long-
   * pending transactions.  Default: 12 000 (≈6 Polygon blocks).
   */
  pollMaxIntervalMs?: number;
  /**
   * Maximum total time (ms) to track a hash before marking it DROPPED.
   * Default: 120 000 (2 minutes).
   */
  maxTrackingDurationMs?: number;
  /**
   * Number of block confirmations required before a receipt is elevated from
   * CONFIRMING → CONFIRMED.  Default: 1 (Polygon's fast finality is adequate
   * for most MEV scenarios; set higher for settlement-critical operations).
   */
  requiredConfirmations?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Internal types
// ─────────────────────────────────────────────────────────────────────────────

interface RawReceipt {
  blockNumber: string | null;
  status: string | null;        // '0x1' = success, '0x0' = revert
  gasUsed: string | null;
  effectiveGasPrice: string | null;
  transactionHash: string;
}

interface QuorumResult {
  receipt: RawReceipt;
  agreementCount: number;
  confirmedByEndpoint: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Default configuration values
// ─────────────────────────────────────────────────────────────────────────────

const DEFAULTS = {
  quorumThreshold: 2,
  rpcTimeoutMs: 3_500,
  initialPollDelayMs: 1_000,
  pollBaseIntervalMs: 1_500,
  pollMaxIntervalMs: 12_000,
  maxTrackingDurationMs: 120_000,
  requiredConfirmations: 1,
} as const;

// All configured HTTP endpoints in priority order
function buildDefaultEndpoints(): { url: string; label: string }[] {
  const cfg = POLYGON_CHAIN_CONFIG.rpcEndpoints;
  return [
    { url: cfg.primaryAlchemyHttp,    label: 'Alchemy'    },
    { url: cfg.drpcLoadBalancedHttp,  label: 'DRPC'       },
    { url: cfg.chainstackHttp,        label: 'Chainstack' },
    { url: cfg.getBlockHttp,          label: 'GetBlock'   },
    { url: cfg.infuraWritableHttp,    label: 'Infura'     },
    { url: 'https://polygon-bor-rpc.publicnode.com', label: 'PublicNode' },
    { url: 'https://polygon-rpc.com',                label: 'PolygonRPC' },
    { url: 'https://rpc.ankr.com/polygon',           label: 'Ankr'       },
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// TxHashFetcher — low-level, stateless helper
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Stateless helper that fetches a transaction receipt from multiple RPC nodes.
 *
 * Two call patterns:
 *   - `fetchFastest`   — returns the first successful (non-null) receipt
 *   - `fetchWithQuorum` — returns only when ≥quorumThreshold nodes agree
 */
export class TxHashFetcher {
  private readonly endpoints: { url: string; label: string }[];
  private readonly quorumThreshold: number;
  private readonly rpcTimeoutMs: number;

  constructor(config: Pick<TxLoggerConfig, 'endpoints' | 'quorumThreshold' | 'rpcTimeoutMs'> = {}) {
    this.endpoints    = config.endpoints      ?? buildDefaultEndpoints();
    this.quorumThreshold = config.quorumThreshold ?? DEFAULTS.quorumThreshold;
    this.rpcTimeoutMs    = config.rpcTimeoutMs    ?? DEFAULTS.rpcTimeoutMs;
  }

  /**
   * Races ALL endpoints simultaneously and returns the first endpoint that
   * responds with a non-null receipt (i.e. the tx has been mined).
   *
   * Returns `null` if no endpoint found a receipt within the timeout window.
   */
  async fetchFastest(txHash: string): Promise<{ receipt: RawReceipt; label: string } | null> {
    const probes = this.endpoints.map(({ url, label }) =>
      this._getReceipt(url, txHash).then((receipt) =>
        receipt ? { receipt, label } : Promise.reject(new Error('null'))
      )
    );

    try {
      return await Promise.any(probes);
    } catch {
      return null;
    }
  }

  /**
   * Queries all endpoints in parallel and groups results by block hash.
   * Returns a receipt only when `quorumThreshold` or more independent nodes
   * agree on the same receipt.  Returns `null` if quorum is not reached.
   */
  async fetchWithQuorum(txHash: string): Promise<QuorumResult | null> {
    const settlements = await Promise.allSettled(
      this.endpoints.map(async ({ url, label }) => {
        const receipt = await this._getReceipt(url, txHash);
        return receipt ? { receipt, label } : null;
      })
    );

    // Gather successful, non-null responses
    const responses: { receipt: RawReceipt; label: string }[] = [];
    for (const s of settlements) {
      if (s.status === 'fulfilled' && s.value !== null) {
        responses.push(s.value);
      }
    }

    if (responses.length === 0) return null;

    // Group by blockNumber (most stable canonical field)
    const groups = new Map<string, { receipt: RawReceipt; labels: string[]; count: number }>();
    for (const { receipt, label } of responses) {
      const key = receipt.blockNumber ?? 'null';
      const existing = groups.get(key);
      if (existing) {
        existing.count += 1;
        existing.labels.push(label);
      } else {
        groups.set(key, { receipt, labels: [label], count: 1 });
      }
    }

    // Find the group with the highest agreement that meets quorum
    let best: { receipt: RawReceipt; labels: string[]; count: number } | null = null;
    for (const [groupKey, g] of groups.entries()) {
      if (groupKey === 'null') continue; // skip "tx not found" responses
      if (!best || g.count > best.count) best = g;
    }

    if (!best || best.count < this.quorumThreshold) return null;

    return {
      receipt: best.receipt,
      agreementCount: best.count,
      confirmedByEndpoint: best.labels[0],
    };
  }

  // ── Private ────────────────────────────────────────────────────────────────

  /** Calls eth_getTransactionReceipt on a single endpoint with timeout. */
  private async _getReceipt(url: string, txHash: string): Promise<RawReceipt | null> {
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), this.rpcTimeoutMs);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'eth_getTransactionReceipt',
          params: [txHash],
        }),
        signal: controller.signal,
      });
      if (!res.ok) return null;
      const json = await res.json() as { result?: RawReceipt | null };
      return json.result ?? null;
    } catch {
      return null;
    } finally {
      clearTimeout(tid);
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// TxRunner — stateful polling runner
// ─────────────────────────────────────────────────────────────────────────────

/** Fired on every status transition of a tracked tx. */
export type TxStatusChangeHandler = (record: Readonly<TxRecord>) => void;

/**
 * Stateful runner that tracks multiple transaction hashes concurrently.
 *
 * Call `track(txHash, meta?)` to register a hash.  The runner polls all
 * registered hashes in parallel, driving each through the lifecycle:
 *
 *   PENDING → CONFIRMING → CONFIRMED | REVERTED | DROPPED
 *
 * Attach a `onStatusChange` callback to receive real-time updates.
 *
 * Usage:
 * ```ts
 * const runner = new TxRunner({ requiredConfirmations: 2 });
 * runner.onStatusChange = (rec) => console.log(rec.status, rec.txHash);
 * runner.track('0xabc...', { routeId: 'route_001', assetPair: 'USDC/WETH' });
 * runner.start();
 * // ... later
 * runner.stop();
 * ```
 */
export class TxRunner {
  private readonly fetcher: TxHashFetcher;
  private readonly router = getOmegaRpcRouter();
  private readonly cfg: Required<Omit<TxLoggerConfig, 'endpoints'>>;
  private readonly records = new Map<string, TxRecord>();
  private readonly listeners: TxStatusChangeHandler[] = [];
  private _running = false;
  private _loopHandle: ReturnType<typeof setTimeout> | null = null;

  /** @deprecated Use `subscribe()` for new code. Kept for backward compatibility. */
  onStatusChange: TxStatusChangeHandler | null = null;

  constructor(config: TxLoggerConfig = {}) {
    this.cfg = {
      quorumThreshold:        config.quorumThreshold        ?? DEFAULTS.quorumThreshold,
      rpcTimeoutMs:           config.rpcTimeoutMs           ?? DEFAULTS.rpcTimeoutMs,
      initialPollDelayMs:     config.initialPollDelayMs     ?? DEFAULTS.initialPollDelayMs,
      pollBaseIntervalMs:     config.pollBaseIntervalMs     ?? DEFAULTS.pollBaseIntervalMs,
      pollMaxIntervalMs:      config.pollMaxIntervalMs      ?? DEFAULTS.pollMaxIntervalMs,
      maxTrackingDurationMs:  config.maxTrackingDurationMs  ?? DEFAULTS.maxTrackingDurationMs,
      requiredConfirmations:  config.requiredConfirmations  ?? DEFAULTS.requiredConfirmations,
    };
    this.fetcher = new TxHashFetcher({
      endpoints:       config.endpoints,
      quorumThreshold: this.cfg.quorumThreshold,
      rpcTimeoutMs:    this.cfg.rpcTimeoutMs,
    });
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Subscribes to status change events.
   * @param handler The function to call on each status change.
   * @returns An `unsubscribe` function to remove the listener.
   */
  subscribe(handler: TxStatusChangeHandler): () => void {
    this.listeners.push(handler);
    return () => {
      const index = this.listeners.indexOf(handler);
      if (index > -1) {
        this.listeners.splice(index, 1);
      }
    };
  }

  /** Registers a tx hash to be tracked.  Idempotent — re-registering a known hash is a no-op. */
  track(txHash: string, meta: TxMeta = {}): TxRecord {
    const existing = this.records.get(txHash.toLowerCase());
    if (existing) return existing;

    const record: TxRecord = {
      txHash: txHash.toLowerCase(),
      status: 'PENDING',
      registeredAt: Date.now(),
      lastPolledAt: 0,
      confirmations: 0,
      quorumCount: 0,
      pollCount: 0,
      meta,
    };
    this.records.set(record.txHash, record);
    return record;
  }

  /** Returns a snapshot of the current record for a hash. */
  getRecord(txHash: string): Readonly<TxRecord> | undefined {
    return this.records.get(txHash.toLowerCase());
  }

  /** Returns all tracked records, optionally filtered by status. */
  getAll(filterStatus?: TxStatus): Readonly<TxRecord>[] {
    const all = Array.from(this.records.values());
    return filterStatus ? all.filter((r) => r.status === filterStatus) : all;
  }

  /**
   * Converts a finalized `TxRecord` to the `LiveTradeLog` shape used by the
   * existing UI and Firestore audit trail.
   */
  toTradeLog(record: Readonly<TxRecord>): LiveTradeLog {
    const gasUsedGwei = record.gasUsed && record.effectiveGasPriceWei
      ? Number(record.gasUsed * record.effectiveGasPriceWei) / 1e9
      : 0;

    return {
      id: `txlog_${record.txHash.slice(2, 10)}`,
      txHash: record.txHash,
      timestamp: new Date(record.registeredAt).toISOString(),
      type: record.meta.executionType ?? 'HFT_ARBITRAGE',
      contractAddress: record.meta.contractAddress ?? POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress,
      assetPair: record.meta.assetPair ?? 'UNKNOWN',
      flashloanAmount: record.meta.flashloanAmount ?? '0',
      gasPaidGwei: Number(gasUsedGwei.toFixed(4)),
      netProfitUSD: record.meta.expectedProfitUSD ?? 0,
      blockNumber: record.blockNumber ?? 0,
      status:
        record.status === 'CONFIRMED' ? 'CONFIRMED_ON_CHAIN'
        : record.status === 'PENDING' || record.status === 'CONFIRMING' ? 'PENDING_RELAY'
        : 'REVERTED_PROTECTED',
      mevRelay: record.meta.mevRelay ?? 'FASTLANE',
    };
  }

  /** Starts the background polling loop. */
  start(): void {
    if (this._running) return;
    this._running = true;
    void this._scheduleNextRound(this.cfg.initialPollDelayMs);
  }

  /** Stops the background polling loop without clearing tracked records. */
  stop(): void {
    this._running = false;
    if (this._loopHandle !== null) {
      clearTimeout(this._loopHandle);
      this._loopHandle = null;
    }
  }

  /** Removes all records and stops the runner. */
  reset(): void {
    this.stop();
    this.records.clear();
  }

  // ── Core polling loop ──────────────────────────────────────────────────────

  private _scheduleNextRound(delayMs: number): void {
    if (!this._running) return;
    this._loopHandle = setTimeout(() => {
      void this._pollRound().then(() => {
        if (this._running) {
          // Determine next interval: scale down if many records still pending
          const pendingCount = this.getAll('PENDING').length + this.getAll('CONFIRMING').length;
          const nextDelay = pendingCount > 0
            ? this.cfg.pollBaseIntervalMs + _jitter(300)
            : Math.min(this.cfg.pollMaxIntervalMs, this.cfg.pollBaseIntervalMs * 4);
          this._scheduleNextRound(nextDelay);
        }
      });
    }, delayMs);
  }

  /**
   * One polling round: all PENDING/CONFIRMING records are queried in parallel.
   * Each record's interval is computed independently via exponential backoff
   * so recently-added hashes are polled more aggressively.
   */
  private async _pollRound(): Promise<void> {
    const now = Date.now();
    const active = Array.from(this.records.values()).filter(
      (r) => r.status === 'PENDING' || r.status === 'CONFIRMING'
    );

    if (active.length === 0) return;

    await Promise.allSettled(active.map((record) => this._pollOne(record, now)));
  }

  private async _pollOne(record: TxRecord, now: number): Promise<void> {
    // Drop if tracking window exceeded
    if (now - record.registeredAt > this.cfg.maxTrackingDurationMs) {
      this._transition(record, 'DROPPED');
      return;
    }

    // Exponential backoff: skip this round if not yet due
    const backoffMs = Math.min(
      this.cfg.pollBaseIntervalMs * Math.pow(2, record.pollCount),
      this.cfg.pollMaxIntervalMs
    );
    if (record.lastPolledAt > 0 && now - record.lastPolledAt < backoffMs - _jitter(200)) {
      return;
    }

    record.lastPolledAt = now;
    record.pollCount += 1;

    // Phase 1: race for first response (speed)
    const fastest = await this.fetcher.fetchFastest(record.txHash);
    if (!fastest) return; // still not mined

    // Phase 2: quorum cross-validation (accuracy)
    const quorum = await this.fetcher.fetchWithQuorum(record.txHash);
    if (!quorum) {
      // Speed got a hit but quorum disagrees — mark CONFIRMING and retry
      if (record.status === 'PENDING') {
        this._transition(record, 'CONFIRMING');
      }
      return;
    }

    // Apply confirmed receipt data
    record.quorumCount = quorum.agreementCount;
    record.confirmedByEndpoint = quorum.confirmedByEndpoint;

    const receipt = quorum.receipt;
    if (receipt.blockNumber) {
      record.blockNumber = parseInt(receipt.blockNumber, 16);
    }
    if (receipt.gasUsed) {
      record.gasUsed = BigInt(receipt.gasUsed);
    }
    if (receipt.effectiveGasPrice) {
      record.effectiveGasPriceWei = BigInt(receipt.effectiveGasPrice);
    }

    // Fetch current block height for confirmation count
    try {
      const blockResult = await this.router.send({
        jsonrpc: '2.0', id: 1, method: 'eth_blockNumber', params: [],
      });
      const currentBlock = parseInt(
        (blockResult.data as { result?: string }).result ?? '0x0', 16
      );
      if (record.blockNumber) {
        record.confirmations = Math.max(0, currentBlock - record.blockNumber + 1);
      }
    } catch {
      // Non-fatal; use 1 confirmation as conservative default
      if (!record.confirmations) record.confirmations = 1;
    }

    if (receipt.status === null) {
      // Pre-Byzantium tx — treat mined as confirmed
      if (record.confirmations >= this.cfg.requiredConfirmations) {
        this._transition(record, 'CONFIRMED');
      } else {
        this._transition(record, 'CONFIRMING');
      }
      return;
    }

    const success = receipt.status === '0x1';
    if (!success) {
      void this._fetchRevertReason(record);
      this._transition(record, 'REVERTED');
      return;
    }

    if (record.confirmations >= this.cfg.requiredConfirmations) {
      this._transition(record, 'CONFIRMED');
    } else {
      this._transition(record, 'CONFIRMING');
    }
  }

  private _transition(record: TxRecord, next: TxStatus): void {
    if (record.status === next) return;
    record.status = next;
    
    // Fire legacy handler
    this.onStatusChange?.(record);
    // Fire all subscribed listeners
    for (const listener of this.listeners) {
      try {
        listener(record);
      } catch (e) {
        // console.error('[TxRunner] Status change listener threw an error:', e);
      }
    }
  }

  /**
   * For a reverted transaction, attempts to discover the on-chain revert reason
   * by re-playing the transaction against the block in which it was mined.
   */
  private async _fetchRevertReason(record: TxRecord): Promise<void> {
    if (!record.blockNumber) return;

    try {
      // 1. Fetch the full transaction object
      const txResult = await this.router.send({
        jsonrpc: '2.0',
        id: 1,
        method: 'eth_getTransactionByHash',
        params: [record.txHash],
      });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const tx = (txResult.data as { result: any }).result;

      if (!tx || !tx.to) { // tx.to can be null for contract creation
        return;
      }

      // 2. Re-play the transaction via eth_call at the failure block
      const callParams = {
        from: tx.from,
        to: tx.to,
        gas: tx.gas,
        data: tx.data,
        value: tx.value,
        // For eth_call, we don't need to specify gas prices
      };

      const callResult = await this.router.send({
        jsonrpc: '2.0',
        id: 2,
        method: 'eth_call',
        params: [callParams, '0x' + record.blockNumber.toString(16)]
      });

      // 3. Decode the revert reason from the error data
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const errorData = (callResult.data as { error?: { data?: string } }).error?.data;
      if (errorData && errorData.startsWith('0x08c379a0')) { // Error(string) selector
        const iface = new ethers.Interface(['error Error(string)']);
        const decodedError = iface.decodeErrorResult('Error', errorData);
        record.revertReason = decodedError[0];
      } else if (errorData === '0x') {
        record.revertReason = 'Reverted with no reason';
      } else if (errorData) {
        record.revertReason = `Reverted with custom error: ${errorData}`;
      }

    } catch (e) {
      // This is a best-effort process; non-fatal if it fails.
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Singleton factory — shared runner for the Omega V5 pipeline
// ─────────────────────────────────────────────────────────────────────────────

let _sharedRunner: TxRunner | null = null;

/**
 * Returns the shared `TxRunner` for Omega V5, creating it on first call.
 * The runner is started automatically.
 *
 * @param config - Optional configuration override (applied only on first call).
 */
export function getOmegaTxRunner(config?: TxLoggerConfig): TxRunner {
  if (!_sharedRunner) {
    _sharedRunner = new TxRunner(config ?? { requiredConfirmations: 1 });
    _sharedRunner.start();
  }
  return _sharedRunner;
}

/**
 * Convenience one-shot helper: registers `txHash`, starts the shared runner if
 * needed, and returns a Promise that resolves when the hash reaches a terminal
 * state (CONFIRMED | REVERTED | DROPPED).
 *
 * @param txHash - The 0x-prefixed transaction hash to wait for.
 * @param meta   - Optional metadata for the audit trail.
 * @param config - Optional runner config (applied only on first call).
 */
export function waitForTx(
  txHash: string,
  meta: TxMeta = {},
  config?: TxLoggerConfig
): Promise<Readonly<TxRecord>> {
  const runner = getOmegaTxRunner(config);
  const record = runner.track(txHash, meta);

  // If already finalized (e.g. cached from a prior run), resolve immediately.
  if (_isTerminal(record.status)) {
    return Promise.resolve(record);
  }

  return new Promise((resolve) => {
    const unsubscribe = runner.subscribe((updated) => {
      if (updated.txHash === txHash.toLowerCase() && _isTerminal(updated.status)) {
        unsubscribe();
        resolve(updated);
      }
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function _isTerminal(status: TxStatus): boolean {
  return status === 'CONFIRMED' || status === 'REVERTED' || status === 'DROPPED';
}

/** Returns a random integer in [0, maxMs). */
function _jitter(maxMs: number): number {
  return Math.floor(Math.random() * maxMs);
}
