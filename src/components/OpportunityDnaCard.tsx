import React, { useState } from 'react';
import { ArbitrageRoute, PipelineStage, PoolInfo } from '../types';
import { validateRouteAssetRegistry } from '../utils/mathEngine';
import { VqcSparklineChart } from './VqcSparklineChart';
import { DnaCardModal3D } from './DnaCardModal3D';
import {
  Dna,
  Zap,
  ShieldCheck,
  AlertTriangle,
  Play,
  ArrowRight,
  BarChart2,
  Sparkles,
  CheckCircle2,
  Clock,
  Layers,
  ChevronRight,
  Activity,
  Database,
  Lock,
  Maximize2,
} from 'lucide-react';

interface OpportunityDnaCardProps {
  route: ArbitrageRoute;
  pools?: PoolInfo[];
  maxSlippageBps?: number;
  maxGasRatioPercent?: number;
  isSelected?: boolean;
  onToggleSelect?: (routeId: string) => void;
  onExecuteRoute: (routeId: string) => void;
  onAdvanceRouteStage?: (routeId: string) => void;
  onSelectRouteForInjector: (route: ArbitrageRoute) => void;
  onAnalyzeRouteWithAI: (route: ArbitrageRoute) => void;
  onHoverRoute?: (route: ArbitrageRoute | null) => void;
}

const STAGE_ORDER: PipelineStage[] = [
  'DISCOVERED',
  'RANKED',
  'SIMULATED',
  'PREPARED',
  'EXECUTED',
  'ACCOUNTED',
];

const STAGE_LABELS: Record<PipelineStage, { name: string; step: number; color: string }> = {
  DISCOVERED: { name: '1. Discovered', step: 1, color: 'text-slate-300 border-slate-700 bg-slate-900' },
  RANKED: { name: '2. VQC Ranked', step: 2, color: 'text-purple-300 border-purple-800 bg-purple-950/60' },
  SIMULATED: { name: '3. Apex Solved', step: 3, color: 'text-indigo-300 border-indigo-800 bg-indigo-950/60' },
  PREPARED: { name: '4. Vault Approved', step: 4, color: 'text-cyan-300 border-cyan-800 bg-cyan-950/60' },
  EXECUTED: { name: '5. Relay Mined', step: 5, color: 'text-emerald-300 border-emerald-800 bg-emerald-950/60' },
  ACCOUNTED: { name: '6. SQL Logged', step: 6, color: 'text-amber-300 border-amber-800 bg-amber-950/60' },
};

export const OpportunityDnaCard: React.FC<OpportunityDnaCardProps> = ({
  route,
  pools = [],
  maxSlippageBps,
  maxGasRatioPercent,
  isSelected,
  onToggleSelect,
  onExecuteRoute,
  onAdvanceRouteStage,
  onSelectRouteForInjector,
  onAnalyzeRouteWithAI,
  onHoverRoute,
}) => {
  const [is3DModalOpen, setIs3DModalOpen] = useState<boolean>(false);

  const isExecuted = route.stage === 'EXECUTED' || route.stage === 'ACCOUNTED';
  const registryCheck = validateRouteAssetRegistry(route, pools);
  const canExecute = !isExecuted && registryCheck.isExecutable;

  // Threshold alert calculations
  const gasRatioPercent = route.grossProfitUSD > 0
    ? (route.estimatedGasUSD / route.grossProfitUSD) * 100
    : 100;
  const slippageExceeded = maxSlippageBps !== undefined && route.slippageToleranceBps > maxSlippageBps;
  const gasRatioExceeded = maxGasRatioPercent !== undefined && gasRatioPercent > maxGasRatioPercent;
  const isFlagged = slippageExceeded || gasRatioExceeded;

  // Derive DNA Gene Sequence from path tokens and pools
  const pathParts = route.pathString.split(' -> ');
  const primaryPool = route.pools[0];
  const rInUSD = primaryPool?.reserve0USD || 2800000;
  const rOutUSD = primaryPool?.reserve1USD || 2920000;

  // Generate deterministic DNA Genetic Hash
  const dnaHash = `0xDNA_${route.id.toUpperCase()}_${(route.vqcAlphaScore * 10000).toFixed(0)}_${route.optimalInputUSD}`;

  const currentStageIndex = STAGE_ORDER.indexOf(route.stage);
  const nextStage = currentStageIndex < STAGE_ORDER.length - 1 ? STAGE_ORDER[currentStageIndex + 1] : null;

  // Derive Routing Variation Badge
  const getVariationBadge = () => {
    const p = route.pathString.toLowerCase();
    if (p.includes('aave') || p.includes('liquidation')) {
      return { name: 'Aave Liquidation', color: 'bg-purple-950 text-purple-300 border-purple-800' };
    }
    if (p.includes('balancer v3') || p.includes('transient storage') || p.includes('spatial')) {
      return { name: 'Spatial Flashloan', color: 'bg-cyan-950 text-cyan-300 border-cyan-800' };
    }
    if (p.includes('jit') || p.includes('tricrypto')) {
      return { name: 'JIT Dynamic Rebalance', color: 'bg-indigo-950 text-indigo-300 border-indigo-800' };
    }
    if (p.includes('subgraph') || p.includes('sub-graph')) {
      return { name: 'Sub-Graph Transient', color: 'bg-teal-950 text-teal-300 border-teal-800' };
    }
    if (route.length === 2) {
      return { name: '2-Hop Triangular', color: 'bg-emerald-950 text-emerald-300 border-emerald-800' };
    }
    if (route.length === 3) {
      return { name: '3-Hop Cyclic', color: 'bg-amber-950 text-amber-300 border-amber-800' };
    }
    return { name: '4-Hop Multi-DEX', color: 'bg-rose-950 text-rose-300 border-rose-800' };
  };

  const variationBadge = getVariationBadge();

  return (
    <div
      id={`dna-card-${route.id}`}
      onMouseEnter={() => onHoverRoute?.(route)}
      onMouseLeave={() => onHoverRoute?.(null)}
      className={`bg-slate-900/90 border rounded-xl p-5 shadow-2xl space-y-4 relative overflow-hidden transition-all group ${
        isSelected
          ? 'border-emerald-500 bg-slate-900/95 ring-2 ring-emerald-500/50 shadow-emerald-950/30'
          : isFlagged
          ? 'border-amber-500/80 bg-slate-900/95 ring-1 ring-amber-500/40 shadow-amber-950/20'
          : 'border-slate-800 hover:border-slate-700'
      }`}
    >
      {/* Background Subtle Helix Gradient Accent */}
      <div className={`absolute -right-20 -top-20 w-56 h-56 rounded-full blur-3xl pointer-events-none transition-all ${
        isFlagged ? 'bg-amber-500/10' : 'bg-emerald-500/5 group-hover:bg-emerald-500/10'
      }`} />

      {/* Top Header: Selection Checkbox, DNA Identifier, Stage Badge, Tracking Indicator */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2 flex-wrap">
          {onToggleSelect && (
            <input
              type="checkbox"
              checked={!!isSelected}
              onChange={(e) => {
                e.stopPropagation();
                onToggleSelect(route.id);
              }}
              className="w-4 h-4 rounded border-slate-700 bg-slate-950 text-emerald-500 focus:ring-emerald-500 cursor-pointer shrink-0 accent-emerald-500"
              title="Select route for batch execution"
            />
          )}

          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-950/80 border border-emerald-700/60 rounded-lg text-emerald-300 font-mono text-xs font-bold shadow-sm">
            <Dna className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span>OPPORTUNITY DNA CARD</span>
          </div>

          <span className="px-2 py-0.5 bg-slate-800 text-slate-300 font-mono text-xs font-semibold rounded border border-slate-700">
            {route.id}
          </span>

          {/* Routing Variation Badge */}
          <span className={`px-2 py-0.5 font-mono text-xs font-extrabold rounded border ${variationBadge.color}`}>
            {variationBadge.name}
          </span>

          <span className={`px-2 py-0.5 border font-mono text-xs rounded font-semibold ${STAGE_LABELS[route.stage].color}`}>
            Stage {STAGE_LABELS[route.stage].step}/6: {route.stage}
          </span>

          {registryCheck.isExecutable ? (
            <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 border border-emerald-800/80 font-mono text-xs rounded flex items-center gap-1">
              <ShieldCheck className="w-3 h-3 text-emerald-400" />
              Registry Verified
            </span>
          ) : (
            <span className="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-800/80 font-mono text-xs rounded flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              Unregistered Asset Blocked
            </span>
          )}

          {/* Threshold Notification Flags */}
          {slippageExceeded && (
            <span className="px-2 py-0.5 bg-amber-950 text-amber-300 border border-amber-700/90 font-mono text-xs rounded flex items-center gap-1 font-bold animate-pulse">
              <AlertTriangle className="w-3 h-3 text-amber-400" />
              Slippage: {route.slippageToleranceBps}bps &gt; {maxSlippageBps}bps
            </span>
          )}

          {gasRatioExceeded && (
            <span className="px-2 py-0.5 bg-rose-950 text-rose-300 border border-rose-700/90 font-mono text-xs rounded flex items-center gap-1 font-bold animate-pulse">
              <AlertTriangle className="w-3 h-3 text-rose-400" />
              Gas/Profit: {gasRatioPercent.toFixed(1)}% &gt; {maxGasRatioPercent?.toFixed(1)}%
            </span>
          )}
        </div>

        {/* Live Opportunity Tracking Indicator */}
        <div className="flex items-center gap-2 bg-slate-950 px-2.5 py-1 rounded-full border border-slate-800/80 text-[11px] font-mono shrink-0">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-emerald-400 font-semibold uppercase tracking-wider">
            TRACKING ACTIVE
          </span>
          <span className="text-slate-500">|</span>
          <span className="text-slate-400 truncate max-w-[120px]">{dnaHash.slice(0, 14)}...</span>
        </div>
      </div>

      {/* Visual DNA Genetic Strand / Pathway */}
      <div className="space-y-1.5">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 flex items-center justify-between">
          <span className="flex items-center gap-1">
            <Activity className="w-3 h-3 text-emerald-400" />
            <span>Genomic Pathway Strand</span>
          </span>
          <span className="text-indigo-300">Length: {route.length} Hop Invariant Cycle</span>
        </div>

        <div className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 font-mono text-xs text-white flex items-center gap-2 overflow-x-auto scrollbar-thin">
          {pathParts.map((part, idx) => {
            const isPool = part.includes('Uni') || part.includes('Quick') || part.includes('Sushi') || part.includes('Curve') || part.includes('Aave') || part.includes('Balancer');
            return (
              <React.Fragment key={idx}>
                {idx > 0 && (
                  <span className="text-emerald-400 font-bold shrink-0 flex items-center">
                    🧬
                  </span>
                )}
                <span
                  className={`px-2.5 py-1 rounded-md text-xs font-semibold whitespace-nowrap shrink-0 border ${
                    isPool
                      ? 'bg-purple-950/80 border-purple-800/80 text-purple-200'
                      : 'bg-emerald-950/80 border-emerald-800/80 text-emerald-200'
                  }`}
                >
                  {part}
                </span>
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Genomic Attributes Matrix Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-950/80 p-3.5 rounded-xl border border-slate-800">
        <div>
          <div className="text-[10px] font-mono text-slate-400 uppercase">Virtual Reserve Gene (x_v, y_v)</div>
          <div className="text-xs font-bold font-mono text-slate-200 mt-0.5">
            ${rInUSD.toLocaleString()} / ${rOutUSD.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">x_v = L / sqrtP; y_v = L * sqrtP</div>
        </div>

        <div>
          <div className="text-[10px] font-mono text-slate-400 uppercase">Calculus Apex Gene (x*)</div>
          <div className="text-xs font-bold font-mono text-amber-300 mt-0.5">
            ${route.optimalInputUSD.toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-500 font-mono">Derivative dP/dx = 0 Apex</div>
        </div>

        <div className="space-y-1">
          <div className="text-[10px] font-mono text-slate-400 uppercase">VQC Quantum Gene</div>
          <VqcSparklineChart score={route.vqcAlphaScore} history={route.vqcAlphaHistory} />
        </div>

        <div>
          <div className="text-[10px] font-mono text-slate-400 uppercase flex items-center justify-between">
            <span>Net Yield Apex P(x*)</span>
            <span className="flex items-center gap-1 text-[9px] text-emerald-400 font-bold bg-emerald-950 px-1.5 py-0.2 rounded border border-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
              <span>LIVE TICK</span>
            </span>
          </div>
          <div className="text-sm font-extrabold font-mono text-emerald-400 mt-0.5 flex items-center gap-1.5">
            <span>+${route.netProfitUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>
          <div className="text-[10px] text-slate-500 font-mono">Gas: ~${route.estimatedGasUSD} | Bps: {route.slippageToleranceBps}</div>
        </div>
      </div>

      {/* Stage Progression Timeline Stepper & Controls */}
      <div className="space-y-2 border-t border-slate-800/80 pt-3">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-slate-400 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
            <span>Opportunity Staging Lifecycle Tracker</span>
          </span>

          {onAdvanceRouteStage && nextStage && (
            <button
              onClick={() => onAdvanceRouteStage(route.id)}
              className="flex items-center gap-1 px-2.5 py-1 bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800 text-cyan-300 rounded font-bold transition-all active:scale-95"
            >
              <span>Promote Stage ➔ {nextStage}</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* 6-Step Stage Bar */}
        <div className="grid grid-cols-6 gap-1.5">
          {STAGE_ORDER.map((s, idx) => {
            const isCompleted = idx <= currentStageIndex;
            const isCurrent = s === route.stage;
            return (
              <div
                key={s}
                className={`p-1.5 rounded text-center border font-mono text-[10px] transition-all ${
                  isCurrent
                    ? 'bg-emerald-950 text-emerald-300 border-emerald-500 font-bold ring-1 ring-emerald-400/50'
                    : isCompleted
                    ? 'bg-slate-800/80 text-slate-300 border-slate-700'
                    : 'bg-slate-950/40 text-slate-600 border-slate-800'
                }`}
              >
                <div className="truncate">{STAGE_LABELS[s].name.split('. ')[1]}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Actions Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/80 pt-3">
        <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
          <Lock className="w-3.5 h-3.5 text-indigo-400" />
          <span>Isolated Pot: Balancer V3 Vault</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setIs3DModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border border-emerald-700/80 text-xs font-bold rounded-lg transition-all active:scale-95 font-mono shadow-md"
            title="Open High-Fidelity 3D Opportunity DNA Pop-up"
          >
            <Maximize2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Inspect 3D DNA</span>
          </button>

          <button
            onClick={() => onSelectRouteForInjector(route)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600/90 hover:bg-indigo-600 text-white text-xs font-medium rounded-lg transition-all active:scale-95 font-mono"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span>Calculus Apex</span>
          </button>

          <button
            onClick={() => onAnalyzeRouteWithAI(route)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-900/60 hover:bg-purple-900 text-purple-200 text-xs font-medium rounded-lg border border-purple-700/50 transition-all font-mono"
          >
            <Sparkles className="w-3.5 h-3.5 text-purple-300" />
            <span>AI MEV Review</span>
          </button>

          <button
            onClick={() => canExecute && onExecuteRoute(route.id)}
            disabled={!canExecute}
            title={!registryCheck.isExecutable ? registryCheck.reason : undefined}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all active:scale-95 font-mono ${
              isExecuted
                ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                : !registryCheck.isExecutable
                ? 'bg-rose-950/60 text-rose-400 border border-rose-800/80 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/20'
            }`}
          >
            {isExecuted ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            ) : !registryCheck.isExecutable ? (
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
            <span>
              {isExecuted
                ? 'Mined & Accounted'
                : !registryCheck.isExecutable
                ? 'Asset Unregistered'
                : 'Execute Relay'}
            </span>
          </button>
        </div>
      </div>

      {/* High-Fidelity 3D DNA Modal Pop-up */}
      <DnaCardModal3D
        route={route}
        isOpen={is3DModalOpen}
        onClose={() => setIs3DModalOpen(false)}
        onExecuteRoute={onExecuteRoute}
      />
    </div>
  );
};
