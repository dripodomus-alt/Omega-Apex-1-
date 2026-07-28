import React, { useState } from 'react';
import { Cpu, Zap, Activity, ShieldCheck, Database, Layers, RefreshCw, ArrowUp, ArrowDown, Wifi, Radio, Flame, Sparkles, CheckCircle2 } from 'lucide-react';
import { EngineHealthWidget } from './EngineHealthWidget';
import { usePolygonGasTracker } from '../utils/usePolygonGasTracker';

import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';

interface HeaderProps {
  readinessScore: number;
  activeRoutesCount: number;
  totalNetProfitUSD: number;
  gasGwei: number;
  onUpdateGasGwei?: (gwei: number) => void;
  onRefreshData: () => void;
  isSimulating: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  readinessScore,
  activeRoutesCount,
  totalNetProfitUSD,
  gasGwei: initialGasGwei,
  onUpdateGasGwei,
  onRefreshData,
  isSimulating,
}) => {
  const [showGasDetail, setShowGasDetail] = useState(false);

  const {
    gasGwei,
    connectionType,
    isLive,
    lastUpdated,
    trend,
    gasHistory,
    refetchGasPrice,
    toggleConnectionMode,
  } = usePolygonGasTracker(initialGasGwei, onUpdateGasGwei);

  return (
    <header id="omega-header" className="bg-slate-900 border-b border-slate-800 text-slate-100 px-4 py-3 sm:px-6 relative">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* Brand & Engine Identity */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-600 to-emerald-500 p-0.5 shadow-lg shadow-indigo-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Zap className="w-5 h-5 text-emerald-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-white font-mono">
                OMEGA <span className="text-emerald-400">V5</span>
              </h1>
              <span className="px-2 py-0.5 text-xs font-mono font-medium rounded-md bg-purple-950/80 text-purple-300 border border-purple-800/50">
                Polygon PoS #137
              </span>
              <span className="px-2 py-0.5 text-xs font-mono font-medium rounded-md bg-emerald-950/80 text-emerald-300 border border-emerald-800/50 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                LIVE PIPELINE
              </span>
              <span className="px-2 py-0.5 text-[11px] font-mono font-bold rounded-md bg-gradient-to-r from-emerald-950 to-teal-950 text-emerald-300 border border-emerald-700/80 shadow-sm flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                RULE 026 ENABLED
              </span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-2 mt-0.5 font-sans">
              <span>Signer & Bot: <code className="text-emerald-300 font-mono">{POLYGON_CHAIN_CONFIG.userMainnetWallet.slice(0, 6)}...{POLYGON_CHAIN_CONFIG.userMainnetWallet.slice(-4)}</code></span>
              <span>•</span>
              <span>Target: <code className="text-cyan-300 font-mono">{POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress.slice(0,6)}...{POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress.slice(-4)}</code></span>
              <span>•</span>
              <span>Vault: <code className="text-slate-300 font-mono">Balancer V3 Vault</code></span>
            </p>
          </div>
        </div>

        {/* Live Metrics Quick Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/70 p-2.5 rounded-xl border border-slate-800/80 text-xs">
          <div className="px-2">
            <div className="text-slate-400 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Readiness</span>
            </div>
            <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">
              {readinessScore.toFixed(1)}%
            </div>
          </div>

          <div className="px-2 border-l border-slate-800">
            <div className="text-slate-400 flex items-center gap-1">
              <Activity className="w-3.5 h-3.5 text-indigo-400" />
              <span>24h Net Profit</span>
            </div>
            <div className="text-base font-bold text-white font-mono mt-0.5">
              ${totalNetProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          <div className="px-2 border-l border-slate-800">
            <div className="text-slate-400 flex items-center gap-1">
              <Cpu className="w-3.5 h-3.5 text-purple-400" />
              <span>Lat. / Pipeline</span>
            </div>
            <div className="text-base font-bold text-purple-300 font-mono mt-0.5">
              1.42ms <span className="text-[10px] text-slate-500 font-sans">/ {activeRoutesCount} routes</span>
            </div>
          </div>

          {/* Interactive Live Polygon Gas Metric */}
          <div
            className="px-2 border-l border-slate-800 cursor-pointer hover:bg-slate-900/60 transition-colors rounded-r-lg group relative"
            onClick={() => setShowGasDetail(!showGasDetail)}
            title="Click for Polygon Gas Oracle & WebSocket Feed Details"
          >
            <div className="text-slate-400 flex items-center justify-between">
              <div className="flex items-center gap-1">
                <Flame className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                <span>Polygon Gas</span>
              </div>
              <span className={`text-[10px] font-mono px-1 rounded flex items-center gap-0.5 ${
                connectionType === 'ws'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                  : connectionType === 'rpc'
                  ? 'bg-indigo-950 text-indigo-300 border border-indigo-800'
                  : 'bg-amber-950 text-amber-300 border border-amber-800'
              }`}>
                <span className={`w-1 h-1 rounded-full ${isLive ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'}`} />
                {connectionType.toUpperCase()}
              </span>
            </div>

            <div className="text-base font-bold text-amber-300 font-mono mt-0.5 flex items-center gap-1.5">
              <span>{gasGwei} Gwei</span>
              {trend === 'up' && <ArrowUp className="w-3 h-3 text-rose-400 animate-bounce" />}
              {trend === 'down' && <ArrowDown className="w-3 h-3 text-emerald-400 animate-bounce" />}
            </div>

            {/* Quick Gas Sparkline bar preview */}
            <div className="flex items-end gap-0.5 h-1.5 mt-1 opacity-70 group-hover:opacity-100 transition-opacity">
              {gasHistory.slice(-8).map((val, idx) => {
                const maxVal = Math.max(...gasHistory, 1);
                const heightPct = Math.max(20, Math.min(100, (val / maxVal) * 100));
                return (
                  <div
                    key={idx}
                    style={{ height: `${heightPct}%` }}
                    className={`w-1 rounded-t transition-all ${
                      val > 45 ? 'bg-rose-500' : val > 30 ? 'bg-amber-400' : 'bg-emerald-400'
                    }`}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* Action Controls & Engine Health Summary */}
        <div className="flex flex-wrap items-center gap-3">
          <EngineHealthWidget />

          <button
            id="omega-refresh-btn"
            onClick={onRefreshData}
            disabled={isSimulating}
            className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition-all hover:border-slate-600 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSimulating ? 'animate-spin text-emerald-400' : ''}`} />
            <span>{isSimulating ? 'Scanning...' : 'Scan Market'}</span>
          </button>
        </div>
      </div>

      {/* Popover / Expandable Gas Oracle Details Modal */}
      {showGasDetail && (
        <div className="absolute right-6 top-16 z-50 w-80 bg-slate-950 border border-amber-500/40 rounded-xl p-4 shadow-2xl space-y-3 font-mono animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-amber-400 animate-pulse" />
              <span className="text-xs font-bold text-white">Polygon Gas Oracle Feed</span>
            </div>
            <button
              onClick={() => setShowGasDetail(false)}
              className="text-slate-400 hover:text-white text-xs font-bold"
            >
              ✕
            </button>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between items-center bg-slate-900 p-2 rounded border border-slate-800">
              <span className="text-slate-400">Current Base Fee:</span>
              <span className="text-amber-300 font-bold text-sm">{gasGwei} Gwei</span>
            </div>

            <div className="flex justify-between items-center text-slate-400 text-[11px]">
              <span>Connection Strategy:</span>
              <span className="text-emerald-400 font-bold uppercase">{connectionType} Provider</span>
            </div>

            <div className="flex justify-between items-center text-slate-400 text-[11px]">
              <span>Last Network Update:</span>
              <span className="text-slate-200">{lastUpdated || 'Initializing...'}</span>
            </div>

            {/* Sparkline Bar Chart */}
            <div className="space-y-1 pt-1">
              <div className="text-[10px] text-slate-400 flex justify-between">
                <span>Recent Tick History (Gwei)</span>
                <span>Last 15 updates</span>
              </div>
              <div className="flex items-end gap-1 h-10 bg-slate-900 p-1.5 rounded border border-slate-800">
                {gasHistory.map((val, idx) => {
                  const maxVal = Math.max(...gasHistory, 60);
                  const heightPct = Math.max(15, Math.min(100, (val / maxVal) * 100));
                  return (
                    <div
                      key={idx}
                      style={{ height: `${heightPct}%` }}
                      title={`Tick #${idx + 1}: ${val} Gwei`}
                      className={`flex-1 rounded-t transition-all ${
                        val > 45 ? 'bg-rose-500' : val > 30 ? 'bg-amber-400' : 'bg-emerald-400'
                      }`}
                    />
                  );
                })}
              </div>
            </div>

            <div className="pt-2 flex items-center justify-between gap-2 border-t border-slate-800">
              <button
                onClick={toggleConnectionMode}
                className="flex-1 px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded border border-slate-700 text-[11px] font-bold flex items-center justify-center gap-1 transition-all"
              >
                <Wifi className="w-3 h-3 text-indigo-400" />
                <span>Switch to {connectionType === 'ws' ? 'RPC' : 'WebSocket'}</span>
              </button>

              <button
                onClick={refetchGasPrice}
                className="px-2.5 py-1.5 bg-amber-950 hover:bg-amber-900 text-amber-300 rounded border border-amber-800 text-[11px] font-bold flex items-center gap-1 transition-all"
              >
                <RefreshCw className="w-3 h-3 text-amber-400" />
                <span>Fetch Now</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

