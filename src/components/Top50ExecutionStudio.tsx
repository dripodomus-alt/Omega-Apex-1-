import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react';
import type {
  MarketEngineResult,
  RankedRouteCandidate,
} from '../engine/market/types';
import { x18ToDecimalString } from '../engine/market/fixedPoint';
import { fetchMarketSnapshot } from '../services/liveMarketClient';

const REFRESH_MS = 12_000;

function shortId(value: string): string {
  if (value.length <= 18) return value;
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

function assetLabel(
  candidate: RankedRouteCandidate,
  side: 'base' | 'quote',
): string {
  const asset = side === 'base'
    ? candidate.buy.baseAsset
    : candidate.buy.quoteAsset;

  return asset.symbol || shortId(asset.address);
}

function candidateStatus(
  candidate: RankedRouteCandidate,
): 'RANKED' | 'STALE' {
  return candidate.buyBlock > 0 && candidate.sellBlock > 0
    ? 'RANKED'
    : 'STALE';
}

export const Top50ExecutionStudio: React.FC = () => {
  const [snapshot, setSnapshot] = useState<MarketEngineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [query, setQuery] = useState<string>('');
  const [selected, setSelected] = useState<RankedRouteCandidate | null>(null);
  const [lastRefreshMs, setLastRefreshMs] = useState<number>(0);

  const load = useCallback(async () => {
    const controller = new AbortController();

    try {
      setLoading(true);
      const next = await fetchMarketSnapshot(controller.signal);
      setSnapshot(next);
      setLastRefreshMs(Date.now());
      setError(null);

      setSelected((current) => {
        if (!current) return null;
        return next.candidates.find(
          (candidate) => candidate.candidateHash === current.candidateHash,
        ) ?? null;
      });
    } catch (cause) {
      setSnapshot(null);
      setSelected(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }

    return () => controller.abort();
  }, []);

  useEffect(() => {
    void load();

    const interval = window.setInterval(() => {
      void load();
    }, REFRESH_MS);

    return () => window.clearInterval(interval);
  }, [load]);

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    return (snapshot?.candidates ?? [])
      .filter((candidate) => {
        if (!normalized) return true;

        return [
          candidate.candidateHash,
          candidate.buy.venue,
          candidate.sell.venue,
          candidate.buy.protocol,
          candidate.sell.protocol,
          candidate.buy.baseAsset.symbol ?? '',
          candidate.buy.quoteAsset.symbol ?? '',
          candidate.buy.poolId,
          candidate.sell.poolId,
        ].some((value) => value.toLowerCase().includes(normalized));
      })
      .slice(0, 50);
  }, [snapshot, query]);

  return (
    <div id="top50-execution-studio" className="space-y-5">
      <section className="rounded-xl border border-slate-800 bg-slate-950 p-5 shadow-xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-emerald-400" />
              <h2 className="font-mono text-sm font-bold uppercase tracking-wider text-white">
                Apex-Omega Live Discovery + Deterministic Ranking
              </h2>
            </div>
            <p className="mt-1 max-w-3xl text-xs text-slate-400">
              Chain 137 executable quote intake → $50K TVL gate → freshness gate →
              comparable markets → exhaustive distinct-destination ranking.
              This surface does not generate fallback routes.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-300">
              SOURCE: {snapshot?.source ?? 'OFFLINE'}
            </span>
            <span className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 font-mono text-xs text-slate-300">
              BLOCK: {snapshot?.latestBlock ?? '—'}
            </span>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg border border-emerald-800 bg-emerald-950 px-3 py-2 font-mono text-xs text-emerald-300 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {error && (
        <section className="rounded-xl border border-rose-900 bg-rose-950/40 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-rose-400" />
            <div>
              <div className="font-mono text-xs font-bold uppercase text-rose-300">
                Market data unavailable
              </div>
              <div className="mt-1 font-mono text-xs text-rose-200/80">
                {error}
              </div>
              <div className="mt-2 text-xs text-slate-400">
                No synthetic replacement data was generated.
              </div>
            </div>
          </div>
        </section>
      )}

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {[
          ['Input Rows', snapshot?.inputRows ?? 0],
          ['Eligible', snapshot?.eligibleRows ?? 0],
          ['Rejected', snapshot?.rejectedRows.length ?? 0],
          ['Markets', snapshot?.comparableMarkets ?? 0],
          ['Candidates', snapshot?.candidateCount ?? 0],
          ['Top 50', visible.length],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className="rounded-xl border border-slate-800 bg-slate-950 p-4"
          >
            <div className="font-mono text-[10px] uppercase text-slate-500">
              {label}
            </div>
            <div className="mt-1 font-mono text-xl font-bold text-white">
              {value}
            </div>
          </div>
        ))}
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-950 p-4">
        <div className="flex items-center gap-2">
          <Search className="h-4 w-4 text-slate-500" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search venue, protocol, token, pool, candidate hash"
            className="w-full bg-transparent font-mono text-xs text-slate-200 outline-none placeholder:text-slate-600"
          />
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left font-mono text-xs">
            <thead className="border-b border-slate-800 bg-slate-900/80 text-[10px] uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Rank</th>
                <th className="px-4 py-3">Market</th>
                <th className="px-4 py-3">Buy</th>
                <th className="px-4 py-3">Sell</th>
                <th className="px-4 py-3">Buy Px</th>
                <th className="px-4 py-3">Sell Px</th>
                <th className="px-4 py-3">Spread</th>
                <th className="px-4 py-3">Block</th>
                <th className="px-4 py-3">State</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((candidate) => {
                const status = candidateStatus(candidate);

                return (
                  <tr
                    key={candidate.candidateHash}
                    onClick={() => setSelected(candidate)}
                    className="cursor-pointer border-b border-slate-900 text-slate-300 hover:bg-slate-900/60"
                  >
                    <td className="px-4 py-3 font-bold text-white">
                      {candidate.rank}
                    </td>
                    <td className="px-4 py-3">
                      {assetLabel(candidate, 'base')} / {assetLabel(candidate, 'quote')}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-emerald-300">{candidate.buy.venue}</div>
                      <div className="text-[10px] text-slate-600">
                        {shortId(candidate.buy.poolId)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-cyan-300">{candidate.sell.venue}</div>
                      <div className="text-[10px] text-slate-600">
                        {shortId(candidate.sell.poolId)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {x18ToDecimalString(BigInt(candidate.buyPriceX18), 8)}
                    </td>
                    <td className="px-4 py-3">
                      {x18ToDecimalString(BigInt(candidate.sellPriceX18), 8)}
                    </td>
                    <td className="px-4 py-3 font-bold text-emerald-400">
                      {candidate.rawSpreadBps} bps
                    </td>
                    <td className="px-4 py-3 text-slate-400">
                      {Math.min(candidate.buyBlock, candidate.sellBlock)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {status}
                      </span>
                    </td>
                  </tr>
                );
              })}

              {!error && visible.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                    No eligible distinct-destination executable routes exist in the current snapshot.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
            <div className="mb-4 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-emerald-400" />
              <h3 className="font-mono text-xs font-bold uppercase text-white">
                Ranked Candidate
              </h3>
            </div>

            <dl className="space-y-2 font-mono text-xs">
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">candidateHash</dt>
                <dd className="break-all text-right text-slate-300">
                  {selected.candidateHash}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">comparableKey</dt>
                <dd className="break-all text-right text-slate-300">
                  {selected.comparableKey}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">rawSpreadBps</dt>
                <dd className="text-emerald-400">{selected.rawSpreadBps}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">buyDestination</dt>
                <dd className="break-all text-right text-slate-300">
                  {selected.buy.destinationId}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">sellDestination</dt>
                <dd className="break-all text-right text-slate-300">
                  {selected.sell.destinationId}
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
            <div className="mb-4 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-cyan-400" />
              <h3 className="font-mono text-xs font-bold uppercase text-white">
                Truth Boundary
              </h3>
            </div>

            <div className="space-y-3 text-xs text-slate-400">
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4 text-cyan-400" />
                Source: {snapshot?.source}
              </div>
              <div className="flex items-center gap-2">
                <Clock3 className="h-4 w-4 text-cyan-400" />
                Last UI refresh:{' '}
                {lastRefreshMs
                  ? new Date(lastRefreshMs).toLocaleTimeString()
                  : '—'}
              </div>
              <p>
                Ranking proves only the current raw executable cross-destination
                edge. RustMath sizing, complete execution costs, simulation,
                transaction construction, submission, and settlement remain
                downstream permissions.
              </p>
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default Top50ExecutionStudio;
