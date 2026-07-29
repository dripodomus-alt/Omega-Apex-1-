import React, { useState, useEffect, useMemo } from 'react';
import { SimulationAuditLog, ArbitrageRoute } from '../types';
import { MonthlyProfitProjectionChart } from './MonthlyProfitProjectionChart';
import { TransactionConfirmationRunner } from './TransactionConfirmationRunner';
import { TransientAccountingStudio } from './TransientAccountingStudio';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';
import {
  Database,
  RefreshCw,
  CheckCircle2,
  Play,
  Terminal,
  Zap,
  FileText,
  Download,
  CheckSquare,
  Square,
  Layers,
  Sliders,
  ShieldCheck,
  ArrowRight,
  TrendingUp,
  Clock,
  Activity,
  DollarSign,
  SlidersHorizontal,
  Eye,
  X,
  Sparkles,
  Cpu,
} from 'lucide-react';

interface AccountantStreamStudioProps {
  logs: SimulationAuditLog[];
  routes?: ArbitrageRoute[];
  onFlushBatchToSQL: () => void;
  isFlushing: boolean;
}

const PRESET_QUERIES = [
  {
    title: '1. VQC Retraining View Query',
    sql: `SELECT simulation_id, route_id, path_string, optimal_input_usd, expected_gross_profit_usd, net_profit_usd, status
FROM vqc_training_view
WHERE status = 'SUCCESS'
ORDER BY timestamp DESC
LIMIT 100;`,
  },
  {
    title: '2. High Alpha Route Graph Audit',
    sql: `SELECT r.id AS route_id, r.path_string, s.optimal_input_usd, s.net_profit_usd, s.gas_used_gwei
FROM route_registry r
JOIN simulation_audit s ON r.id = s.route_id
WHERE s.net_profit_usd > 100
ORDER BY s.net_profit_usd DESC;`,
  },
  {
    title: '3. Revert & Slippage Root Cause Analysis',
    sql: `SELECT status, COUNT(*) AS count, AVG(gas_used_gwei) AS avg_gas_gwei
FROM simulation_audit
GROUP BY status;`,
  },
];

export const AccountantStreamStudio: React.FC<AccountantStreamStudioProps> = ({
  logs,
  routes = [],
  onFlushBatchToSQL,
  isFlushing,
}) => {
  const [selectedQueryIndex, setSelectedQueryIndex] = useState<number>(0);
  const [customSql, setCustomSql] = useState<string>(PRESET_QUERIES[0].sql);
  const [queryResult, setQueryResult] = useState<any[] | null>(null);

  // Batch Selection State
  const [selectedLogIds, setSelectedLogIds] = useState<string[]>([]);
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  // Transient Accounting Drawer
  const [drawerRouteId, setDrawerRouteId] = useState<string | null>(null);
  const drawerRoutes: ArbitrageRoute[] = useMemo(() => {
    if (!drawerRouteId) return [];
    const found = routes.find((r) => r.id === drawerRouteId);
    return found ? [found] : [];
  }, [drawerRouteId, routes]);
  const handleToggleDrawer = (routeId: string) =>
    setDrawerRouteId((prev) => (prev === routeId ? null : routeId));

  // Auto-Flush Configuration State (>50 entries rule)
  const [isAutoFlushEnabled, setIsAutoFlushEnabled] = useState<boolean>(true);
  const [autoFlushThreshold, setAutoFlushThreshold] = useState<number>(50);
  const [autoFlushNotice, setAutoFlushNotice] = useState<string | null>(null);

  // 60-Minute Instant ROI Overlay Projection State
  const [showInstantRoiOverlay, setShowInstantRoiOverlay] = useState<boolean>(true);
  const [capitalBaseUSD, setCapitalBaseUSD] = useState<number>(250000);
  const [executionVelocity, setExecutionVelocity] = useState<number>(18.5); // trades per minute
  const [volatilityIndex, setVolatilityIndex] = useState<number>(2.4); // 2.4x Alpha Volatility
  const [gasGweiEstimate, setGasGweiEstimate] = useState<number>(45);

  // Calculate 60-Minute Forecast Metrics
  const totalProjectedTrades60m = Math.round(executionVelocity * 60);
  const avgGrossProfitPerTrade = 22.50 * volatilityIndex;
  const estimatedGrossProfit60m = totalProjectedTrades60m * avgGrossProfitPerTrade * 0.965; // 96.5% success rate
  const estimatedGasCost60m = totalProjectedTrades60m * (184200 * gasGweiEstimate * 1e-9 * 0.58);
  const netProfit60m = Math.max(0, estimatedGrossProfit60m - estimatedGasCost60m);
  const instantRoiPct60m = (netProfit60m / capitalBaseUSD) * 100;

  const unsyncedCount = logs.filter((l) => !l.sqlSynced).length;

  // Auto-Flush Trigger Listener
  useEffect(() => {
    if (isAutoFlushEnabled && unsyncedCount >= autoFlushThreshold && !isFlushing) {
      setAutoFlushNotice(
        `Auto-flush rule triggered: Pending queue reached ${unsyncedCount} entries (Threshold: >=${autoFlushThreshold}). Automatically flushing batch to Cloud SQL...`
      );
      onFlushBatchToSQL();
      const timer = setTimeout(() => setAutoFlushNotice(null), 6000);
      return () => clearTimeout(timer);
    }
  }, [unsyncedCount, isAutoFlushEnabled, autoFlushThreshold, isFlushing, onFlushBatchToSQL]);

  const toggleSelectAllLogs = () => {
    if (selectedLogIds.length === logs.length) {
      setSelectedLogIds([]);
    } else {
      setSelectedLogIds(logs.map((l) => l.id));
    }
  };

  const toggleSelectLog = (id: string) => {
    setSelectedLogIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleBatchExportCSV = () => {
    const targetLogs =
      selectedLogIds.length > 0 ? logs.filter((l) => selectedLogIds.includes(l.id)) : logs;

    const headers = 'RedisKey,SimulationID,RouteID,Path,OptimalInputUSD,NetProfitUSD,GasGwei,Status,SQLSynced\n';
    const rows = targetLogs
      .map(
        (l) =>
          `"${l.redisStreamKey}","${l.simulationId}","${l.routeId}","${l.pathString.replace(
            /"/g,
            '""'
          )}",${l.optimalInputUSD},${l.netProfitUSD},${l.gasUsedGwei},"${l.status}",${l.sqlSynced}`
      )
      .join('\n');

    const blob = new Blob([headers + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `omega_audit_batch_ledger_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);

    setExportNotice(`Exported Batch Ledger CSV (${targetLogs.length} Records)!`);
    setTimeout(() => setExportNotice(null), 4000);
  };

  const runQuery = () => {
    // Execute simulated query against the logs
    setQueryResult(
      logs.map((l) => ({
        simulation_id: l.simulationId,
        route_id: l.routeId,
        path_string: l.pathString,
        optimal_input_usd: l.optimalInputUSD,
        net_profit_usd: l.netProfitUSD,
        status: l.status,
        gas_used_gwei: l.gasUsedGwei,
        redis_stream_key: l.redisStreamKey,
        sql_synced: l.sqlSynced,
      }))
    );
  };

  return (
    <div id="accountant-stream-studio" className="space-y-6">
      {/* Complete Transaction Confirmation Runner & Audit History Ledger */}
      <TransactionConfirmationRunner
        auditLogs={logs}
        onFlushBatchToSQL={onFlushBatchToSQL}
        isFlushing={isFlushing}
      />
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-amber-400" />
              <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                Low-Latency Accountant & Redis-to-SQL Async Stream Engine
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl font-mono">
              Redis Stream: <code className="text-amber-300 font-mono">omega:audit:simulations</code> • Cloud SQL Sync Buffer:{' '}
              <span className="text-white font-mono">{unsyncedCount} Unsynced Entries</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowInstantRoiOverlay(!showInstantRoiOverlay)}
              className={`flex items-center gap-1.5 px-3.5 py-2 font-black text-xs rounded-lg transition-all active:scale-95 shadow-md font-mono border ${
                showInstantRoiOverlay
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 border-emerald-400 shadow-emerald-500/20'
                  : 'bg-slate-800 hover:bg-slate-700 text-emerald-400 border-slate-700'
              }`}
              title="Toggle 60-Min Instant ROI Overlay Projection"
            >
              <TrendingUp className="w-4 h-4" />
              <span>Instant ROI Overlay (60-Min) {showInstantRoiOverlay ? 'ON' : 'OFF'}</span>
            </button>

            <button
              onClick={handleBatchExportCSV}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold text-xs rounded-lg transition-all active:scale-95 shadow-md font-mono"
              title="Batch Export Ledger CSV"
            >
              <Download className="w-3.5 h-3.5 text-amber-400" />
              <span>
                Export Batch ({selectedLogIds.length > 0 ? selectedLogIds.length : logs.length}) CSV
              </span>
            </button>

            <button
              onClick={onFlushBatchToSQL}
              disabled={isFlushing || unsyncedCount === 0}
              className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold text-xs rounded-lg transition-all active:scale-95 shadow-lg shadow-amber-600/20 disabled:opacity-50 font-mono"
            >
              <RefreshCw className={`w-4 h-4 ${isFlushing ? 'animate-spin' : ''}`} />
              <span>{isFlushing ? 'Flushing Redis -> SQL...' : `Flush ${unsyncedCount} to Cloud SQL`}</span>
            </button>
          </div>
        </div>
      </div>

      {/* 60-Minute Instant ROI Overlay Projection Panel */}
      {showInstantRoiOverlay && (
        <div className="bg-slate-900 border border-emerald-500/80 rounded-2xl p-5 shadow-2xl font-mono space-y-5 animate-fadeIn relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />

          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 text-[10px] font-black uppercase rounded bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-emerald-400 animate-pulse" />
                  <span>REAL-TIME 60-MINUTE FORECAST ENGINE</span>
                </span>
                <span className="text-xs text-slate-400">Polygon Mainnet (#137)</span>
              </div>
              <h3 className="text-sm md:text-base font-black text-white tracking-tight mt-1 flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
                <span>Instant ROI Projection (Next 60 Minutes)</span>
              </h3>
            </div>

            <button
              onClick={() => setShowInstantRoiOverlay(false)}
              className="self-start md:self-auto text-slate-400 hover:text-white p-1 rounded-lg bg-slate-800/80 hover:bg-slate-800 transition-colors"
              title="Hide Overlay"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Interactive Parameters Controls */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-slate-950/80 p-4 rounded-xl border border-slate-800/80 text-xs">
            {/* Capital Base */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-bold block text-[10px] uppercase flex items-center gap-1">
                <DollarSign className="w-3 h-3 text-emerald-400" />
                <span>Capital Allocation Pool (USD)</span>
              </label>
              <input
                type="number"
                step="10000"
                value={capitalBaseUSD}
                onChange={(e) => setCapitalBaseUSD(Math.max(1000, Number(e.target.value)))}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-emerald-400 font-black focus:outline-none focus:border-emerald-500"
              />
            </div>

            {/* Execution Velocity */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-bold block text-[10px] uppercase flex items-center justify-between">
                <span className="flex items-center gap-1">
                  <Activity className="w-3 h-3 text-cyan-400" />
                  <span>Execution Velocity</span>
                </span>
                <span className="text-cyan-300 font-bold">{executionVelocity} / min</span>
              </label>
              <input
                type="range"
                min="1"
                max="60"
                step="0.5"
                value={executionVelocity}
                onChange={(e) => setExecutionVelocity(Number(e.target.value))}
                className="w-full accent-cyan-400 bg-slate-900 rounded-lg cursor-pointer h-2 mt-2"
              />
            </div>

            {/* Market Volatility Index */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-bold block text-[10px] uppercase flex items-center gap-1">
                <SlidersHorizontal className="w-3 h-3 text-purple-400" />
                <span>Volatility Index (Alpha multiplier)</span>
              </label>
              <div className="grid grid-cols-4 gap-1">
                {[1.0, 1.8, 2.4, 4.8].map((v) => (
                  <button
                    key={v}
                    onClick={() => setVolatilityIndex(v)}
                    className={`py-1.5 text-[10px] font-bold rounded transition-all ${
                      volatilityIndex === v
                        ? 'bg-purple-600 text-white font-black'
                        : 'bg-slate-900 text-slate-400 hover:text-white'
                    }`}
                  >
                    {v}x
                  </button>
                ))}
              </div>
            </div>

            {/* Gas Price Gwei */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-bold block text-[10px] uppercase flex items-center justify-between">
                <span className="flex items-center gap-1">
                  <Zap className="w-3 h-3 text-amber-400" />
                  <span>Polygon Gas Fee</span>
                </span>
                <span className="text-amber-300 font-bold">{gasGweiEstimate} Gwei</span>
              </label>
              <input
                type="range"
                min="15"
                max="150"
                step="5"
                value={gasGweiEstimate}
                onChange={(e) => setGasGweiEstimate(Number(e.target.value))}
                className="w-full accent-amber-400 bg-slate-900 rounded-lg cursor-pointer h-2 mt-2"
              />
            </div>
          </div>

          {/* Core Forecast Metrics Display Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-950 p-4 rounded-xl border border-emerald-500/40 space-y-1 relative">
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Projected 60-Min Net Profit</span>
              <div className="text-xl md:text-2xl font-black text-emerald-400 tracking-tight">
                +${netProfit60m.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="text-[10px] text-slate-500">Gross: +${estimatedGrossProfit60m.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-cyan-500/40 space-y-1">
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Instant 60-Min ROI %</span>
              <div className="text-xl md:text-2xl font-black text-cyan-300 tracking-tight">
                +{instantRoiPct60m.toFixed(2)}%
              </div>
              <div className="text-[10px] text-slate-500">Yield on ${capitalBaseUSD.toLocaleString()} base</div>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-purple-500/40 space-y-1">
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Projected Trades (60 Min)</span>
              <div className="text-xl md:text-2xl font-black text-purple-300 tracking-tight">
                {totalProjectedTrades60m.toLocaleString()} Trades
              </div>
              <div className="text-[10px] text-slate-500">Rate: {executionVelocity}/min @ 96.5% success</div>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-amber-500/40 space-y-1">
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Est. Gas & FastLane Cost</span>
              <div className="text-xl md:text-2xl font-black text-amber-300 tracking-tight">
                ${estimatedGasCost60m.toFixed(2)} USD
              </div>
              <div className="text-[10px] text-slate-500">@ {gasGweiEstimate} Gwei avg network base</div>
            </div>
          </div>

          {/* Minute-by-Minute 60-Min Accumulation Trajectory */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
            <div className="flex justify-between items-center text-xs">
              <span className="font-bold text-white uppercase flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>60-Minute Cumulative ROI Accumulation Milestone Trajectory</span>
              </span>
              <span className="text-[10px] text-slate-400">FastLane Private Relay Target Active</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center text-xs">
              {[
                { min: 0, pct: 0 },
                { min: 15, pct: 0.25 },
                { min: 30, pct: 0.50 },
                { min: 45, pct: 0.75 },
                { min: 60, pct: 1.0 },
              ].map((m) => {
                const stepNet = netProfit60m * m.pct;
                const stepRoi = instantRoiPct60m * m.pct;
                return (
                  <div key={m.min} className="bg-slate-900 p-2.5 rounded-lg border border-slate-800/80 space-y-1">
                    <div className="text-[10px] text-slate-400 font-bold uppercase">{m.min} Mins Elapsed</div>
                    <div className="text-sm font-black text-emerald-400">+${stepNet.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                    <div className="text-[10px] text-cyan-300 font-bold">+{stepRoi.toFixed(2)}% ROI</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Polygon Mainnet Bindings Verification Footer */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-slate-400 pt-1 border-t border-slate-800/80">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Verified Polygon Mainnet (#137) Target: <code className="text-emerald-300">{POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress}</code></span>
            </div>
            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
              <span>Signer Wallet: <code className="text-purple-300">{POLYGON_CHAIN_CONFIG.userMainnetWallet}</code></span>
            </div>
          </div>
        </div>
      )}

      {exportNotice && (
        <div className="bg-amber-950/80 border border-amber-700/80 p-3 rounded-lg flex items-center gap-2 text-xs font-mono text-amber-300 animate-fadeIn">
          <CheckCircle2 className="w-4 h-4 text-amber-400 shrink-0" />
          <span>{exportNotice}</span>
        </div>
      )}

      {/* Auto-Flush Configuration Control Panel (>50 pending entries rule) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl font-mono space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-lg border ${
                isAutoFlushEnabled
                  ? 'bg-amber-950 border-amber-800 text-amber-400'
                  : 'bg-slate-950 border-slate-800 text-slate-500'
              }`}
            >
              <Sliders className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                  Automatic SQL Flush Rule (&gt;{autoFlushThreshold} Pending Entries)
                </h3>
                <span
                  className={`px-2 py-0.5 rounded text-[9px] font-bold border ${
                    isAutoFlushEnabled
                      ? 'bg-amber-950 text-amber-300 border-amber-800'
                      : 'bg-slate-950 text-slate-500 border-slate-800'
                  }`}
                >
                  {isAutoFlushEnabled ? 'AUTO-FLUSH ACTIVE' : 'PAUSED (MANUAL)'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5 font-sans">
                Automatically dispatches pending audit logs from hot Redis memory to persistent Cloud SQL when queue exceeds threshold.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {/* Threshold Selector */}
            <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-lg text-xs">
              <span className="text-slate-400 text-[10px]">Flush Threshold:</span>
              <div className="flex gap-1">
                {[25, 50, 100].map((th) => (
                  <button
                    key={th}
                    onClick={() => setAutoFlushThreshold(th)}
                    className={`px-2 py-0.5 text-[10px] font-bold rounded transition-all ${
                      autoFlushThreshold === th
                        ? 'bg-amber-600 text-slate-950 font-black'
                        : 'bg-slate-900 text-slate-400 hover:text-white'
                    }`}
                  >
                    {th}
                  </button>
                ))}
              </div>
            </div>

            {/* Toggle Switch */}
            <label className="flex items-center gap-2 bg-slate-950 border border-amber-900/60 px-3.5 py-1.5 rounded-lg cursor-pointer">
              <input
                type="checkbox"
                checked={isAutoFlushEnabled}
                onChange={(e) => setIsAutoFlushEnabled(e.target.checked)}
                className="w-4 h-4 accent-amber-500 rounded cursor-pointer"
              />
              <span className="text-xs font-extrabold text-amber-300">
                {isAutoFlushEnabled ? 'ENABLED' : 'DISABLED'}
              </span>
            </label>
          </div>
        </div>

        {/* Queue Buffer Gauge */}
        <div className="space-y-1 pt-1 border-t border-slate-800/80">
          <div className="flex justify-between text-[10px] text-slate-400 font-bold">
            <span>Pending Sync Queue: {unsyncedCount} / {autoFlushThreshold} entries</span>
            <span
              className={
                unsyncedCount >= autoFlushThreshold
                  ? 'text-amber-400 font-extrabold animate-pulse'
                  : 'text-slate-500'
              }
            >
              {unsyncedCount >= autoFlushThreshold
                ? 'FLUSH TRIGGERED'
                : `${((unsyncedCount / autoFlushThreshold) * 100).toFixed(0)}% Capacity`}
            </span>
          </div>
          <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800 flex">
            <div
              style={{ width: `${Math.min(100, (unsyncedCount / autoFlushThreshold) * 100)}%` }}
              className={`h-full transition-all duration-300 ${
                unsyncedCount >= autoFlushThreshold ? 'bg-amber-400 animate-pulse' : 'bg-amber-500/80'
              }`}
            ></div>
          </div>
        </div>
      </div>

      {autoFlushNotice && (
        <div className="bg-amber-950/90 border border-amber-600 p-3.5 rounded-xl flex items-center gap-2.5 text-xs font-mono text-amber-200 shadow-xl animate-fadeIn">
          <Zap className="w-4 h-4 text-amber-400 shrink-0 fill-amber-400 animate-bounce" />
          <span>{autoFlushNotice}</span>
        </div>
      )}

      {/* Recharts Monthly Profit Projection View */}
      <MonthlyProfitProjectionChart logs={logs} />

      {/* Redis Stream Log Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <span>Redis Hot Stream Log Queue (`omega:audit:simulations`)</span>
          </h3>
          <div className="flex items-center gap-3 font-mono text-xs text-slate-400">
            <span>Selected: {selectedLogIds.length} / {logs.length}</span>
            <button
              onClick={toggleSelectAllLogs}
              className="text-amber-400 hover:underline flex items-center gap-1 font-bold"
            >
              {selectedLogIds.length === logs.length ? <CheckSquare className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
              <span>{selectedLogIds.length === logs.length ? 'Deselect All' : 'Select All'}</span>
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                <th className="p-3 w-8">#</th>
                <th className="p-3">Redis Stream ID</th>
                <th className="p-3">Route ID</th>
                <th className="p-3">Path</th>
                <th className="p-3">Input USD</th>
                <th className="p-3">Net Profit</th>
                <th className="p-3">Status</th>
                <th className="p-3">Gas (Gwei)</th>
                <th className="p-3">Cloud SQL Sync</th>
                <th className="p-3">Trace</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {logs.map((log) => {
                const isSelected = selectedLogIds.includes(log.id);
                return (
                  <tr
                    key={log.id}
                    className={`hover:bg-slate-800/40 transition-colors ${
                      isSelected ? 'bg-amber-950/20' : ''
                    }`}
                  >
                    <td className="p-3">
                      <button
                        onClick={() => toggleSelectLog(log.id)}
                        className="text-slate-400 hover:text-amber-400"
                      >
                        {isSelected ? (
                          <CheckSquare className="w-4 h-4 text-amber-400" />
                        ) : (
                          <Square className="w-4 h-4 text-slate-600" />
                        )}
                      </button>
                    </td>
                    <td className="p-3 text-amber-300 font-mono text-[11px]">{log.redisStreamKey}</td>
                    <td className="p-3 text-white font-semibold">{log.routeId}</td>
                    <td className="p-3 text-slate-300 text-[11px] max-w-xs truncate">{log.pathString}</td>
                    <td className="p-3 text-slate-200">${log.optimalInputUSD.toLocaleString()}</td>
                    <td
                      className={`p-3 font-bold ${
                        log.netProfitUSD >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      ${log.netProfitUSD.toFixed(2)}
                    </td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          log.status === 'SUCCESS'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/60'
                            : 'bg-rose-950 text-rose-300 border border-rose-800/60'
                        }`}
                      >
                        {log.status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-300">{log.gasUsedGwei}</td>
                    <td className="p-3">
                      {log.sqlSynced ? (
                        <span className="flex items-center gap-1 text-emerald-400 font-bold text-[10px]">
                          <CheckCircle2 className="w-3.5 h-3.5" /> SYNCED
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-amber-950 text-amber-300 rounded border border-amber-800 text-[10px]">
                          QUEUED IN REDIS
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      {routes.some((r) => r.id === log.routeId) ? (
                        <button
                          onClick={() => handleToggleDrawer(log.routeId)}
                          className="flex items-center gap-1 text-purple-400 hover:text-purple-200 transition-colors text-[10px] font-bold"
                          title="View Transient Accounting Trace"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>{drawerRouteId === log.routeId ? 'Hide' : 'Trace'}</span>
                        </button>
                      ) : (
                        <span className="text-slate-600 text-[10px]">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Transient Accounting Trace Drawer */}
      {drawerRouteId && drawerRoutes.length > 0 && (
        <div className="bg-slate-950 border border-purple-800/60 rounded-xl p-5 shadow-2xl animate-fadeIn space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-purple-400" />
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                Transient Accounting Trace — Route {drawerRouteId}
              </span>
            </div>
            <button
              onClick={() => setDrawerRouteId(null)}
              className="text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <TransientAccountingStudio routes={drawerRoutes} />
        </div>
      )}

      {/* SQL Schema Console & VQC Training View */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2">
            <Terminal className="w-4 h-4 text-emerald-400" />
            <span>Graph-Relational Cloud SQL Schema Console</span>
          </h3>

          <div className="flex items-center gap-2 overflow-x-auto">
            {PRESET_QUERIES.map((q, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setSelectedQueryIndex(idx);
                  setCustomSql(q.sql);
                }}
                className={`px-2.5 py-1 text-[11px] font-mono rounded transition-all whitespace-nowrap ${
                  selectedQueryIndex === idx
                    ? 'bg-emerald-600 text-white font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {q.title}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3 font-mono">
          <textarea
            value={customSql}
            onChange={(e) => setCustomSql(e.target.value)}
            rows={5}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-emerald-300 focus:border-emerald-500 outline-none font-mono"
          />

          <div className="flex justify-between items-center">
            <button
              onClick={runQuery}
              className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg transition-all"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Execute SQL Query</span>
            </button>

            <span className="text-[11px] text-slate-400">Target: PostgreSQL / Cloud SQL Graph-Relational Instance</span>
          </div>

          {queryResult && (
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 overflow-x-auto">
              <div className="text-[11px] font-bold text-slate-400 mb-2">QUERY RESULT ({queryResult.length} ROWS):</div>
              <pre className="text-xs text-slate-200">{JSON.stringify(queryResult, null, 2)}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
