import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Database, Radio, RefreshCw, ShieldCheck, Wallet, XCircle } from 'lucide-react';
import { fetchMarketSnapshot } from '../services/liveMarketClient';
import type { MarketEngineResult } from '../engine/market/types';

type ReadinessCheck = {
  name: string;
  passed: boolean;
  status: string;
  detail: string;
};

type ReadinessStage = {
  name: string;
  passed: boolean;
  severity?: 'PASS' | 'WARN' | 'BLOCKER';
  checks: ReadinessCheck[];
};

type ReadinessResponse = {
  success?: boolean;
  ready: boolean;
  status: string;
  dry_run: boolean;
  paused?: boolean;
  readiness_score?: number;
  blocking_count: number;
  warning_count: number;
  stages: ReadinessStage[];
  signer?: { ready: boolean; address: string };
  execution?: {
    mode: string;
    liveExecutionAllowed: boolean;
    c1Target: string | null;
    c2Target: string | null;
    liquidationTarget: string | null;
  };
  settlement?: {
    ready: boolean;
    profitReceiver: string;
    profitAsset: string;
    pendingCount: number;
    verifiedCount: number;
    sessionPnl: number;
    lifetimePnl: number;
  };
  activeLedgerCount?: number;
  c2?: { pendingCount: number; totalCount: number };
};

type StateProof = {
  ok: boolean;
  network?: string;
  current_rpc_block_height?: number;
  latest_c1_block_hash?: string;
  executor_wallet_address?: string;
  executor_nonce?: number;
  active_wallet_balance_pol?: number;
  derived_usd_value?: number;
  profit_receiver_address?: string;
  profit_asset_balance?: string;
  rpc_provider?: string;
  math_proof?: string;
  error?: string;
};

type PnlSummary = {
  sessionPnl: number;
  lifetimePnl: number;
  sessionPnlRaw: string;
  lifetimePnlRaw: string;
  pnlAttribution: string;
  totalTrades: number;
  totalSettledCycles: number;
  blockNumber: number;
  gasGwei: number;
};

type ConsoleSnapshot = {
  readiness: ReadinessResponse | null;
  stateProof: StateProof | null;
  pnl: PnlSummary | null;
  market: MarketEngineResult | null;
};

const REFRESH_MS = 10_000;

function short(value?: string | null): string {
  if (!value) return 'Missing';
  return value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-6)}` : value;
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store', signal });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error || payload?.message || `${url} failed with HTTP ${response.status}`);
  }
  return payload as T;
}

const statusStyles: Record<string, string> = {
  LIVE_READY: 'border-emerald-800 bg-emerald-950/50 text-emerald-300',
  BLOCKED: 'border-rose-800 bg-rose-950/40 text-rose-300',
  WARN: 'border-amber-800 bg-amber-950/40 text-amber-300',
};

export const SimulationReadinessConsole: React.FC = () => {
  const [snapshot, setSnapshot] = useState<ConsoleSnapshot>({ readiness: null, stateProof: null, pnl: null, market: null });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<number>(0);

  const refresh = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    try {
      const [readiness, stateProof, pnl, marketResult] = await Promise.allSettled([
        getJson<ReadinessResponse>('/api/system/readiness', controller.signal),
        getJson<StateProof>('/api/system/state-proof', controller.signal),
        getJson<PnlSummary>('/api/dashboard/pnl-summary', controller.signal),
        fetchMarketSnapshot(controller.signal),
      ]);

      const next: ConsoleSnapshot = {
        readiness: readiness.status === 'fulfilled' ? readiness.value : null,
        stateProof: stateProof.status === 'fulfilled' ? stateProof.value : null,
        pnl: pnl.status === 'fulfilled' ? pnl.value : null,
        market: marketResult.status === 'fulfilled' ? marketResult.value : null,
      };

      const failures = [readiness, stateProof, pnl, marketResult]
        .filter((item): item is PromiseRejectedResult => item.status === 'rejected')
        .map((item) => item.reason instanceof Error ? item.reason.message : String(item.reason));

      setSnapshot(next);
      setError(failures.length ? failures.join(' | ') : null);
      setLastRefresh(Date.now());
    } finally {
      setLoading(false);
    }
    return () => controller.abort();
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), REFRESH_MS);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const readiness = snapshot.readiness;
  const liveReady = Boolean(readiness?.ready);
  const statusClass = liveReady ? statusStyles.LIVE_READY : statusStyles.BLOCKED;
  const executableCandidates = snapshot.market?.candidates.filter((candidate) => candidate.buyBlock > 0 && candidate.sellBlock > 0).length ?? 0;

  const topBlockers = useMemo(() => {
    return (readiness?.stages ?? [])
      .flatMap((stage) => stage.checks.map((check) => ({ ...check, stage: stage.name, severity: stage.severity })))
      .filter((check) => !check.passed && check.severity !== 'WARN')
      .slice(0, 6);
  }, [readiness]);

  return (
    <div id="simulation-readiness-console" className="space-y-5">
      <section className="rounded-lg border border-slate-800 bg-slate-950 p-5 shadow-xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
              <h2 className="font-mono text-sm font-bold uppercase text-white">Simulation to Live Readiness Console</h2>
            </div>
            <p className="mt-1 max-w-3xl text-xs text-slate-400">
              Operator view for the final bridge: live RPC proof, signer state, execution contracts, route locks, candidate intake, and receipt-proven settlement.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-lg border px-3 py-2 font-mono text-xs font-bold ${statusClass}`}>
              {readiness?.status ?? 'LOADING'} {readiness?.readiness_score !== undefined ? `${readiness.readiness_score}%` : ''}
            </span>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-300 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {error && (
        <section className="rounded-lg border border-amber-800 bg-amber-950/30 p-4 text-xs text-amber-200">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-300" />
            <div className="font-mono">{error}</div>
          </div>
        </section>
      )}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={<Radio className="h-4 w-4" />} label="Live Mode" value={readiness?.execution?.mode ?? 'Unknown'} tone={liveReady ? 'emerald' : 'rose'} detail={readiness?.paused ? 'Engine paused' : readiness?.dry_run ? 'Monitor only' : 'Broadcast path armed'} />
        <MetricCard icon={<Activity className="h-4 w-4" />} label="Candidate Intake" value={String(executableCandidates)} tone="cyan" detail={`${snapshot.market?.candidateCount ?? 0} ranked / ${snapshot.market?.latestBlock ?? 'no block'}`} />
        <MetricCard icon={<Database className="h-4 w-4" />} label="Settlement" value={`${readiness?.settlement?.pendingCount ?? 0} pending`} tone={(readiness?.settlement?.pendingCount ?? 0) > 0 ? 'amber' : 'emerald'} detail={`${readiness?.settlement?.verifiedCount ?? 0} verified receipts`} />
        <MetricCard icon={<Wallet className="h-4 w-4" />} label="Session P&L" value={`$${(snapshot.pnl?.sessionPnl ?? 0).toFixed(4)}`} tone="emerald" detail="Verified receipt transfers only" />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="font-mono text-xs font-bold uppercase text-white">Readiness Gate Matrix</h3>
            <span className="font-mono text-[11px] text-slate-500">{readiness?.blocking_count ?? 0} blockers / {readiness?.warning_count ?? 0} warnings</span>
          </div>
          <div className="space-y-3">
            {(readiness?.stages ?? []).map((stage) => (
              <div key={stage.name} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 font-mono text-xs font-bold text-slate-200">
                    {stage.passed ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <XCircle className="h-4 w-4 text-rose-400" />}
                    {stage.name}
                  </div>
                  <span className="font-mono text-[10px] text-slate-500">{stage.severity || (stage.passed ? 'PASS' : 'BLOCKER')}</span>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  {stage.checks.map((check) => (
                    <div key={`${stage.name}:${check.name}`} className="rounded border border-slate-800 bg-slate-950 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[11px] text-slate-400">{check.name}</span>
                        <span className={`font-mono text-[10px] ${check.passed ? 'text-emerald-400' : 'text-rose-300'}`}>{check.status}</span>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500">{check.detail}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-5">
            <h3 className="mb-4 font-mono text-xs font-bold uppercase text-white">State Proof</h3>
            <dl className="space-y-2 font-mono text-xs">
              <ProofRow label="RPC Provider" value={snapshot.stateProof?.rpc_provider || 'Unavailable'} />
              <ProofRow label="Block" value={String(snapshot.stateProof?.current_rpc_block_height ?? 'Unavailable')} />
              <ProofRow label="Block Hash" value={short(snapshot.stateProof?.latest_c1_block_hash)} />
              <ProofRow label="Executor" value={short(snapshot.stateProof?.executor_wallet_address)} />
              <ProofRow label="Nonce" value={String(snapshot.stateProof?.executor_nonce ?? 'Unknown')} />
              <ProofRow label="POL Balance" value={String(snapshot.stateProof?.active_wallet_balance_pol ?? 'Unknown')} />
              <ProofRow label="Wallet Value" value={`$${(snapshot.stateProof?.derived_usd_value ?? 0).toFixed(2)}`} />
              <ProofRow label="Profit Receiver" value={short(snapshot.stateProof?.profit_receiver_address)} />
            </dl>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950 p-5">
            <h3 className="mb-4 font-mono text-xs font-bold uppercase text-white">Live Bridge Action Plan</h3>
            {topBlockers.length > 0 ? (
              <div className="space-y-2">
                {topBlockers.map((blocker) => (
                  <div key={`${blocker.stage}:${blocker.name}`} className="rounded border border-rose-900/70 bg-rose-950/30 p-3 font-mono text-xs text-rose-200">
                    {blocker.stage}: {blocker.name} -&gt; {blocker.status}
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded border border-emerald-800 bg-emerald-950/30 p-3 font-mono text-xs text-emerald-200">
                All blocking gates are clear. Broadcast endpoints will submit real signed transactions; settlement still requires receipt verification before P&L updates.
              </div>
            )}
            <div className="mt-4 grid gap-2 font-mono text-[11px] text-slate-400">
              <span>C1: {short(readiness?.execution?.c1Target)}</span>
              <span>C2: {short(readiness?.execution?.c2Target)}</span>
              <span>Liquidation: {short(readiness?.execution?.liquidationTarget)}</span>
              <span>Last refresh: {lastRefresh ? new Date(lastRefresh).toLocaleTimeString() : '...'}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

function MetricCard({ icon, label, value, tone, detail }: { icon: React.ReactNode; label: string; value: string; tone: 'emerald' | 'rose' | 'amber' | 'cyan'; detail: string }) {
  const toneClass = {
    emerald: 'text-emerald-300 border-emerald-900/60 bg-emerald-950/20',
    rose: 'text-rose-300 border-rose-900/60 bg-rose-950/20',
    amber: 'text-amber-300 border-amber-900/60 bg-amber-950/20',
    cyan: 'text-cyan-300 border-cyan-900/60 bg-cyan-950/20',
  }[tone];
  return (
    <div className={`rounded-lg border p-4 ${toneClass}`}>
      <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase text-slate-400">{icon}{label}</div>
      <div className="font-mono text-xl font-bold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-500">{detail}</div>
    </div>
  );
}

function ProofRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-900 pb-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="break-all text-right text-slate-300">{value}</dd>
    </div>
  );
}

export default SimulationReadinessConsole;