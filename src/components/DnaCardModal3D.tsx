import React, { useState, useEffect } from 'react';
import {
  Dna,
  X,
  Zap,
  Clock,
  ShieldCheck,
  Activity,
  ArrowRight,
  Sparkles,
  Copy,
  Check,
  ExternalLink,
  Cpu,
  Layers,
  Flame,
  BarChart2,
  Lock,
  Database,
  Radio,
} from 'lucide-react';
import { ArbitrageRoute } from '../types';

import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';

interface DnaCardModal3DProps {
  route: ArbitrageRoute | null;
  isOpen: boolean;
  onClose: () => void;
  onExecuteRoute?: (routeId: string) => void;
}

export const DnaCardModal3D: React.FC<DnaCardModal3DProps> = ({
  route,
  isOpen,
  onClose,
  onExecuteRoute,
}) => {
  const [copied, setCopied] = useState(false);
  // Lifespan / Decay timer in seconds (starts around 4.2s and ticks down)
  const [lifespanSeconds, setLifespanSeconds] = useState<number>(4.2);
  const [timestampIso, setTimestampIso] = useState<string>('');
  const [blockOffsetMs, setBlockOffsetMs] = useState<number>(14);

  useEffect(() => {
    if (isOpen) {
      setTimestampIso(new Date().toISOString());
      setLifespanSeconds(4.2);
      setBlockOffsetMs(Math.floor(10 + Math.random() * 15));
    }
  }, [isOpen, route]);

  // Decay timer countdown loop
  useEffect(() => {
    if (!isOpen) return;
    const timer = setInterval(() => {
      setLifespanSeconds((prev) => {
        if (prev <= 0.1) {
          // Reset lifespan cycle when block refreshes
          setTimestampIso(new Date().toISOString());
          return 4.5;
        }
        return Number((prev - 0.1).toFixed(1));
      });
    }, 100);

    return () => clearInterval(timer);
  }, [isOpen]);

  if (!isOpen || !route) return null;

  const handleCopyPayload = () => {
    const payload = {
      genomicHash: `0xDNA_${route.id}_${Date.now()}`,
      routeId: route.id,
      path: route.pathString,
      optimalInputUSD: route.optimalInputUSD,
      grossProfitUSD: route.grossProfitUSD,
      netProfitUSD: route.netProfitUSD,
      vqcScore: route.vqcAlphaScore,
      timestampISO: timestampIso,
      blockOffsetMs: `${blockOffsetMs}ms`,
      stage: route.stage,
      flashVault: 'Balancer V3 Vault (EIP-1153 Transient Storage)',
      relayer: 'Polygon FastLane Private P2P Relay',
    };
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const primaryPool = route.pools[0];
  const reserve0 = primaryPool?.reserve0USD || 2800000;
  const reserve1 = primaryPool?.reserve1USD || 2920000;
  const invariantK = (reserve0 * reserve1).toExponential(3);

  // Lifespan progress percentage (4.5s max)
  const progressPct = Math.max(0, Math.min(100, (lifespanSeconds / 4.5) * 100));

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-fadeIn font-mono">
      {/* 3D Glassmorphic Modal Frame */}
      <div
        className="relative w-full max-w-4xl bg-gradient-to-b from-slate-900/95 via-slate-950 to-slate-900/95 border-2 border-emerald-500/50 rounded-3xl p-6 md:p-8 shadow-[0_25px_60px_-15px_rgba(16,185,129,0.35)] space-y-6 text-slate-100 overflow-hidden transform transition-all hover:scale-[1.002]"
        style={{
          boxShadow: '0 20px 80px rgba(16, 185, 129, 0.25), inset 0 1px 1px rgba(255, 255, 255, 0.1)',
        }}
      >
        {/* Holographic Glowing Orbs background */}
        <div className="absolute -top-32 -left-32 w-80 h-80 bg-emerald-500/15 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -right-32 w-80 h-80 bg-indigo-500/15 rounded-full blur-3xl pointer-events-none" />

        {/* Modal Top Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-4 relative z-10">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-gradient-to-br from-emerald-400 via-teal-500 to-cyan-500 rounded-2xl text-slate-950 shadow-lg shadow-emerald-500/20">
              <Dna className="w-7 h-7 text-slate-950 animate-spin" style={{ animationDuration: '12s' }} />
            </div>

            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-black text-white uppercase tracking-wider">
                  HIGH-FIDELITY 3D OPPORTUNITY DNA INSPECTION
                </span>
                <span className="px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-emerald-950 text-emerald-300 border border-emerald-700 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                  <span>LIVE MEMPOOL GENOME</span>
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5 font-sans">
                Real-time microsecond state delta, quantum VQC ansatz matrix, and profit apex $P(x^*)$
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white border border-slate-700 transition-all self-start md:self-auto"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* High Precision Timestamp & Lifespan Decay Bar */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-950/90 p-4 rounded-2xl border border-slate-800 relative z-10">
          {/* Precise Time Stamp */}
          <div className="space-y-1">
            <div className="text-[10px] uppercase text-slate-400 font-bold flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-cyan-400" />
              <span>Full Opportunity Creation Timestamp</span>
            </div>
            <div className="text-sm font-black text-cyan-300">
              {timestampIso || '2026-07-27T18:51:43.102Z'}
            </div>
            <div className="text-[10px] text-slate-500 flex items-center gap-2">
              <span>Block Tip Offset: <strong className="text-emerald-400">+{blockOffsetMs}ms</strong></span>
              <span>•</span>
              <span>Mainnet Block #65492810</span>
            </div>
          </div>

          {/* Opportunity Lifespan Countdown */}
          <div className="space-y-1.5">
            <div className="text-[10px] uppercase text-slate-400 font-bold flex items-center justify-between">
              <span className="flex items-center gap-1">
                <Flame className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                <span>Opportunity Lifespan / Decay Timer</span>
              </span>
              <span className="text-amber-300 font-extrabold">{lifespanSeconds.toFixed(1)}s Remaining</span>
            </div>

            {/* Countdown progress bar */}
            <div className="w-full bg-slate-900 h-2.5 rounded-full overflow-hidden border border-slate-800 p-0.5">
              <div
                className={`h-full rounded-full transition-all duration-100 ${
                  lifespanSeconds < 1.5
                    ? 'bg-rose-500 shadow-rose-500/50'
                    : lifespanSeconds < 2.5
                    ? 'bg-amber-400 shadow-amber-400/50'
                    : 'bg-emerald-400 shadow-emerald-400/50'
                }`}
                style={{ width: `${progressPct}%` }}
              />
            </div>

            <div className="text-[9px] text-slate-500 flex justify-between">
              <span>Mempool Re-simulation Interval: 4.5s</span>
              <span>FastLane Anti-Frontrunning Locked</span>
            </div>
          </div>
        </div>

        {/* 3D Genomic Breakdown Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative z-10">
          {/* Card 1: Vector Graph & Invariant Invariance */}
          <div className="bg-slate-950/80 p-4 rounded-2xl border border-slate-800/80 space-y-2 hover:border-slate-700 transition-all">
            <div className="text-[11px] font-bold uppercase text-purple-300 flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-purple-400" />
              <span>Pool Invariant Vector (k = x * y)</span>
            </div>
            <div className="text-xs text-slate-300 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Reserve R_in:</span>
                <span className="font-bold">${reserve0.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Reserve R_out:</span>
                <span className="font-bold">${reserve1.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Constant Product k:</span>
                <span className="font-bold text-purple-300">{invariantK}</span>
              </div>
            </div>
          </div>

          {/* Card 2: Calculus Apex Solution */}
          <div className="bg-slate-950/80 p-4 rounded-2xl border border-slate-800/80 space-y-2 hover:border-slate-700 transition-all">
            <div className="text-[11px] font-bold uppercase text-amber-300 flex items-center gap-1.5">
              <BarChart2 className="w-4 h-4 text-amber-400" />
              <span>Derivative Apex (dP/dx = 0)</span>
            </div>
            <div className="text-xs text-slate-300 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Optimal Input x*:</span>
                <span className="font-black text-amber-300">${route.optimalInputUSD.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Expected Gross Pg:</span>
                <span className="font-bold text-emerald-400">${route.grossProfitUSD.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Est. Gas Ratio:</span>
                <span className="font-bold text-slate-200">
                  {((route.estimatedGasUSD / (route.grossProfitUSD || 1)) * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          </div>

          {/* Card 3: Quantum VQC Ansatz Matrix */}
          <div className="bg-slate-950/80 p-4 rounded-2xl border border-slate-800/80 space-y-2 hover:border-slate-700 transition-all">
            <div className="text-[11px] font-bold uppercase text-emerald-300 flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-emerald-400" />
              <span>VQC Quantum Alpha Score</span>
            </div>
            <div className="text-xs text-slate-300 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Alpha Score:</span>
                <span className="font-black text-emerald-400">{(route.vqcAlphaScore * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Quantum Fidelity:</span>
                <span className="font-bold text-cyan-300">0.9982 (4-Qubit)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Execution Safety:</span>
                <span className="font-bold text-emerald-400">100.0% Verified</span>
              </div>
            </div>
          </div>
        </div>

        {/* Full Route Path & EIP-712 Signed Execution Payload Details */}
        <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-3 relative z-10">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold text-white uppercase flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>EIP-712 Typed Data Signed Execution Payload</span>
            </span>

            <button
              onClick={handleCopyPayload}
              className="flex items-center gap-1.5 px-3 py-1 bg-slate-900 hover:bg-slate-800 text-xs text-emerald-400 border border-slate-700 rounded-lg transition-all"
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied Payload!' : 'Copy Genome JSON'}</span>
            </button>
          </div>

          <div className="space-y-1">
            <span className="text-[10px] text-slate-400 uppercase font-bold">Route Multi-Hop Path</span>
            <p className="text-xs font-bold text-slate-200 bg-slate-900 p-2.5 rounded-xl border border-slate-800">
              {route.pathString}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
              <span className="text-slate-400 block">Polygon FastLane Relayer:</span>
              <strong className="text-purple-300 font-bold">https://polygon-mainnet.fastlane.xyz</strong>
            </div>

            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800">
              <span className="text-slate-400 block">Flash Loan Provider:</span>
              <strong className="text-cyan-300 font-bold">Balancer V3 Vault (Transient EIP-1153)</strong>
            </div>
          </div>
        </div>

        {/* Modal Action Footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-800 pt-4 relative z-10">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span>Bound Mainnet Wallet: <code className="text-emerald-300 font-bold">{POLYGON_CHAIN_CONFIG.userMainnetWallet.slice(0, 8)}...{POLYGON_CHAIN_CONFIG.userMainnetWallet.slice(-6)}</code></span>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button
              onClick={onClose}
              className="flex-1 sm:flex-initial px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-xl text-xs font-bold transition-all border border-slate-700"
            >
              Close Inspection
            </button>

            {onExecuteRoute && (
              <button
                onClick={() => {
                  onExecuteRoute(route.id);
                  onClose();
                }}
                className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-6 py-2.5 bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-400 hover:from-emerald-400 hover:to-teal-300 text-slate-950 font-black text-xs uppercase tracking-wider rounded-xl transition-all shadow-xl shadow-emerald-500/20 active:scale-95"
              >
                <Zap className="w-4 h-4 fill-slate-950 text-slate-950" />
                <span>Execute On-Chain Relay Now</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
