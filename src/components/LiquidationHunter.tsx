import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, ShieldAlert, ShieldCheck, Target, Zap } from 'lucide-react';

type LiquidationPayload = {
  targetContract?: string;
  collateralAsset?: string;
  debtAsset?: string;
  user?: string;
  debtToCover?: string;
  minDebtAmountOut?: string;
  minProfitBps?: number;
  swapProtocol?: number;
  swapFee?: number;
  curvePool?: string;
  maxSlippageBps?: number;
};

export interface LiquidatablePosition extends LiquidationPayload {
  user_address?: string;
  user?: string;
  health_factor?: number;
  healthFactor?: number;
  collateral_value_usd?: number;
  collateralValue?: number;
  debt_value_usd?: number;
  debtValue?: number;
  max_liquidatable_debt_usd?: number;
  liquidation_bonus_usd?: number;
  estimated_profit_usd?: number;
  profitPotential?: number;
  is_executable?: boolean;
  isExecutable?: boolean;
  executionPayload?: LiquidationPayload;
  liquidation?: LiquidationPayload;
}

type NormalizedPosition = {
  key: string;
  user: string;
  healthFactor: number;
  collateralUsd: number;
  debtUsd: number;
  maxDebtUsd: number;
  bonusUsd: number;
  estimatedProfitUsd: number;
  scannerExecutable: boolean;
  executionPayload: LiquidationPayload | null;
};

type ExecuteState = {
  key: string;
  status: 'running' | 'success' | 'error';
  message: string;
  hashLink?: string;
} | null;

const MIN_PROFIT_USD = 10;
const REFRESH_MS = 30_000;
const ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/;

function asNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function shortAddress(address: string): string {
  return ADDRESS_RE.test(address) ? `${address.slice(0, 6)}...${address.slice(-4)}` : 'Unknown';
}

function money(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

function extractExecutionPayload(raw: LiquidatablePosition, user: string): LiquidationPayload | null {
  const source = raw.executionPayload || raw.liquidation || raw;
  const payload: LiquidationPayload = {
    targetContract: source.targetContract,
    collateralAsset: source.collateralAsset,
    debtAsset: source.debtAsset,
    user: source.user || user,
    debtToCover: source.debtToCover,
    minDebtAmountOut: source.minDebtAmountOut,
    minProfitBps: source.minProfitBps,
    swapProtocol: source.swapProtocol,
    swapFee: source.swapFee,
    curvePool: source.curvePool,
    maxSlippageBps: source.maxSlippageBps,
  };

  const hasRequiredPayload =
    ADDRESS_RE.test(payload.user || '') &&
    ADDRESS_RE.test(payload.collateralAsset || '') &&
    ADDRESS_RE.test(payload.debtAsset || '') &&
    typeof payload.debtToCover === 'string' &&
    typeof payload.minDebtAmountOut === 'string';

  return hasRequiredPayload ? payload : null;
}

function normalizePosition(raw: LiquidatablePosition): NormalizedPosition {
  const user = raw.user_address || raw.user || '';
  const healthFactor = asNumber(raw.health_factor ?? raw.healthFactor, 1);
  const estimatedProfitUsd = asNumber(raw.estimated_profit_usd ?? raw.profitPotential, 0);
  const executionPayload = extractExecutionPayload(raw, user);

  return {
    key: `${user || 'unknown'}:${raw.debtAsset || raw.collateralAsset || 'summary'}`,
    user,
    healthFactor,
    collateralUsd: asNumber(raw.collateral_value_usd ?? raw.collateralValue, 0),
    debtUsd: asNumber(raw.debt_value_usd ?? raw.debtValue, 0),
    maxDebtUsd: asNumber(raw.max_liquidatable_debt_usd, 0),
    bonusUsd: asNumber(raw.liquidation_bonus_usd, 0),
    estimatedProfitUsd,
    scannerExecutable: Boolean(raw.is_executable ?? raw.isExecutable ?? (healthFactor < 1 && estimatedProfitUsd >= MIN_PROFIT_USD)),
    executionPayload,
  };
}

function parsePositionsResponse(data: unknown): LiquidatablePosition[] {
  if (Array.isArray(data)) return data as LiquidatablePosition[];
  if (data && typeof data === 'object' && Array.isArray((data as { liquidations?: unknown }).liquidations)) {
    return (data as { liquidations: LiquidatablePosition[] }).liquidations;
  }
  return [];
}

export const LiquidationHunter: React.FC = () => {
  const [positions, setPositions] = useState<NormalizedPosition[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [executeState, setExecuteState] = useState<ExecuteState>(null);
  const abortRef = useRef<AbortController | null>(null);

  const executableCount = useMemo(
    () => positions.filter((pos) => pos.scannerExecutable && pos.executionPayload).length,
    [positions],
  );

  const fetchLiquidations = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/liquidations?min_profit_usd=${MIN_PROFIT_USD}`, { signal: controller.signal });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((data as { error?: string; message?: string } | null)?.error || (data as { message?: string } | null)?.message || `API Error: ${res.status}`);
      }
      if (data && typeof data === 'object' && 'error' in data) {
        throw new Error(String((data as { error: unknown }).error));
      }
      setPositions(parsePositionsResponse(data).map(normalizePosition));
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        setError((err as Error).message || 'Failed to fetch liquidation opportunities.');
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchLiquidations();
    const interval = window.setInterval(fetchLiquidations, REFRESH_MS);
    return () => {
      window.clearInterval(interval);
      abortRef.current?.abort();
    };
  }, [fetchLiquidations]);

  const handleExecute = async (position: NormalizedPosition) => {
    if (!position.executionPayload) {
      setExecuteState({ key: position.key, status: 'error', message: 'Scanner did not return a complete execution payload.' });
      return;
    }

    setExecuteState({ key: position.key, status: 'running', message: 'Submitting liquidation payload...' });
    try {
      const res = await fetch('/api/liquidations/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          healthFactor: position.healthFactor,
          ...position.executionPayload,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || data?.success === false) {
        throw new Error(data?.error || data?.message || `Execution rejected: ${res.status}`);
      }
      setExecuteState({
        key: position.key,
        status: 'success',
        message: data?.hash ? `Submitted ${data.hash.slice(0, 10)}...${data.hash.slice(-6)}` : 'Execution accepted.',
        hashLink: data?.hashLink,
      });
      void fetchLiquidations();
    } catch (err) {
      setExecuteState({ key: position.key, status: 'error', message: (err as Error).message || 'Liquidation execution failed.' });
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-xl space-y-4">
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-rose-950 border border-rose-800/80 rounded-lg text-rose-400 shrink-0">
            <Target className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-white font-mono uppercase">Aave V3 Liquidation Hunter</h3>
            <p className="text-xs text-slate-400 font-mono">{executableCount} executable payloads / {positions.length} watched positions</p>
          </div>
        </div>
        <button
          onClick={fetchLiquidations}
          disabled={isLoading}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-slate-800 px-3 py-2 text-xs font-bold font-mono text-slate-300 transition-colors hover:bg-slate-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Scanning' : 'Refresh'}</span>
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-800 bg-rose-950/50 p-3 text-xs font-mono text-rose-300">
          <strong>Error:</strong> {error}
        </div>
      )}

      {executeState && (
        <div className={`rounded-lg border p-3 text-xs font-mono ${executeState.status === 'error' ? 'border-rose-800 bg-rose-950/50 text-rose-300' : 'border-emerald-800 bg-emerald-950/40 text-emerald-300'}`}>
          {executeState.hashLink ? <a href={executeState.hashLink} target="_blank" rel="noreferrer" className="underline">{executeState.message}</a> : executeState.message}
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
        <span>Last updated: {lastUpdated || '...'}</span>
        <span>Min profit: ${MIN_PROFIT_USD}</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-950 text-slate-400">
              <th className="p-3">Health</th>
              <th className="p-3">User</th>
              <th className="p-3 text-right">Collateral</th>
              <th className="p-3 text-right">Debt</th>
              <th className="p-3 text-right">Max Debt</th>
              <th className="p-3 text-right">Est. Profit</th>
              <th className="p-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {positions.length > 0 ? (
              positions.map((pos) => {
                const canExecute = pos.scannerExecutable && Boolean(pos.executionPayload);
                const isSubmitting = executeState?.key === pos.key && executeState.status === 'running';
                return (
                  <tr key={pos.key} className="transition-colors hover:bg-slate-800/40">
                    <td className="p-3 font-bold">
                      <div className={`flex items-center gap-2 ${pos.healthFactor < 1 ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {pos.healthFactor < 1 ? <ShieldAlert className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                        <span>{pos.healthFactor.toFixed(4)}</span>
                      </div>
                    </td>
                    <td className="p-3 font-semibold text-slate-300">{shortAddress(pos.user)}</td>
                    <td className="p-3 text-right text-emerald-300">${money(pos.collateralUsd)}</td>
                    <td className="p-3 text-right text-rose-300">${money(pos.debtUsd)}</td>
                    <td className="p-3 text-right text-slate-300">${money(pos.maxDebtUsd)}</td>
                    <td className="p-3 text-right font-bold text-emerald-400">${money(pos.estimatedProfitUsd)}</td>
                    <td className="p-3 text-center">
                      <button
                        onClick={() => handleExecute(pos)}
                        disabled={!canExecute || isSubmitting}
                        className="inline-flex min-w-[112px] items-center justify-center gap-1.5 rounded bg-emerald-600 px-3 py-1.5 text-[11px] font-bold text-white shadow-md transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
                      >
                        <Zap className="w-3 h-3" />
                        <span>{isSubmitting ? 'Submitting' : canExecute ? 'Execute' : 'Payload Needed'}</span>
                      </button>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={7} className="p-8 text-center text-slate-500">
                  {isLoading ? 'Scanning Aave V3 positions...' : 'No liquidation candidates found.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};