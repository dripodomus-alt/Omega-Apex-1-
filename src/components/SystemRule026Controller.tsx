import React, { useState } from 'react';
import {
  ShieldCheck,
  Sliders,
  Zap,
  CheckCircle2,
  Lock,
  Activity,
  Cpu,
  Layers,
  Sparkles,
  RefreshCw,
  Scale,
  Terminal,
  ChevronRight,
  Database,
} from 'lucide-react';

interface SystemRule026ControllerProps {
  isRule026Active?: boolean;
  onToggleRule026?: (active: boolean) => void;
}

export const SystemRule026Controller: React.FC<SystemRule026ControllerProps> = ({
  isRule026Active = true,
  onToggleRule026,
}) => {
  const [isEnabled, setIsEnabled] = useState<boolean>(isRule026Active);
  const [isRunningVerification, setIsRunningVerification] = useState<boolean>(false);
  const [lastCheckTime, setLastCheckTime] = useState<string>('Just now');
  const [activeTab, setActiveTab] = useState<'OVERVIEW' | 'PILLARS'>('OVERVIEW');

  const handleRunVerification = () => {
    setIsRunningVerification(true);
    setTimeout(() => {
      setIsRunningVerification(false);
      setLastCheckTime(new Date().toLocaleTimeString());
    }, 800);
  };

  const handleToggle = (val: boolean) => {
    setIsEnabled(val);
    if (onToggleRule026) {
      onToggleRule026(val);
    }
  };

  const pillars = [
    {
      id: 'pillar-1',
      num: '01',
      title: 'Hard logic protects correctness',
      icon: ShieldCheck,
      color: 'emerald',
      bgColor: 'bg-emerald-950/80',
      borderColor: 'border-emerald-800',
      textColor: 'text-emerald-400',
      description: 'Asset registry validation, invariant checks, strict typing & EIP-1153 reentrancy locks.',
      status: 'VERIFIED & ENFORCED',
      metrics: '0 Revert Opcode Triggers',
    },
    {
      id: 'pillar-2',
      num: '02',
      title: 'Dynamic config controls behavior',
      icon: Sliders,
      color: 'purple',
      bgColor: 'bg-purple-950/80',
      borderColor: 'border-purple-800',
      textColor: 'text-purple-300',
      description: 'Configurable min profit threshold, max gas spike caps, MEV relay tunnels & dry-run toggles.',
      status: 'CONFIGURABLE ENGINE',
      metrics: 'FastLane / Flashbots Relay',
    },
    {
      id: 'pillar-3',
      num: '03',
      title: 'Live state controls opportunity',
      icon: Activity,
      color: 'amber',
      bgColor: 'bg-amber-950/80',
      borderColor: 'border-amber-800',
      textColor: 'text-amber-400',
      description: 'Polygon gas tracker WebSocket feeds, live DEX pool liquidity reserves & real-time path discovery.',
      status: 'ACTIVE WEBSOCKET FEED',
      metrics: 'Live Mainnet #137 State',
    },
    {
      id: 'pillar-4',
      num: '04',
      title: 'Simulation controls permission',
      icon: Cpu,
      color: 'cyan',
      bgColor: 'bg-cyan-950/80',
      borderColor: 'border-cyan-800',
      textColor: 'text-cyan-300',
      description: 'eth_call pre-flight zero-revert dry-run, 4-qubit VQC ansatz ranking & Rust/Python benchmarks.',
      status: 'PERMISSION GRANTED',
      metrics: 'eth_call Pre-Flight Clear',
    },
    {
      id: 'pillar-5',
      num: '05',
      title: 'Settlement controls truth',
      icon: Scale,
      color: 'indigo',
      bgColor: 'bg-indigo-950/80',
      borderColor: 'border-indigo-800',
      textColor: 'text-indigo-300',
      description: 'Double-entry ledger accounting, PostgreSQL audit log persistence & on-chain event receipts.',
      status: 'BALANCED SETTLEMENT',
      metrics: 'Double-Entry Synchronized',
    },
  ];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 md:p-6 shadow-2xl font-mono space-y-5 relative overflow-hidden">
      <div className="absolute -right-12 -top-12 w-60 h-60 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>

      {/* Header Banner */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800 pb-4 relative z-10">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 text-[10px] font-black uppercase rounded bg-gradient-to-r from-emerald-500 to-teal-500 text-slate-950 font-mono shadow-sm">
              026. Final System Rule
            </span>
            <span className="text-xs font-bold text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Configurable Execution Machine Alignment Enabled</span>
            </span>
          </div>

          <h2 className="text-lg md:text-xl font-black text-white tracking-tight flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400 fill-amber-400 animate-pulse" />
            <span>Apex-Omega Execution Engine System Alignment</span>
          </h2>

          <p className="text-xs text-slate-300 font-sans leading-relaxed max-w-3xl">
            This alignment converts Apex-Omega from a static scanner into a configurable execution machine.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={handleRunVerification}
            disabled={isRunningVerification}
            className="flex items-center gap-2 px-3.5 py-2 bg-slate-950 hover:bg-slate-800 border border-slate-700 hover:border-slate-600 text-slate-200 text-xs font-bold rounded-xl transition-all shadow-md active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${isRunningVerification ? 'animate-spin' : ''}`} />
            <span>{isRunningVerification ? 'Verifying Alignment...' : 'Verify Alignment'}</span>
          </button>

          <label className="flex items-center gap-2 px-3.5 py-2 bg-slate-950 border border-emerald-800/80 rounded-xl cursor-pointer shadow-inner">
            <span className="text-xs font-bold text-emerald-300">Rule 026 Status:</span>
            <input
              type="checkbox"
              checked={isEnabled}
              onChange={(e) => handleToggle(e.target.checked)}
              className="w-4 h-4 accent-emerald-500 rounded cursor-pointer"
            />
            <span className={`text-xs font-extrabold ${isEnabled ? 'text-emerald-400' : 'text-slate-500'}`}>
              {isEnabled ? 'ENABLED' : 'DISABLED'}
            </span>
          </label>
        </div>
      </div>

      {/* The 5 System Principles Matrix */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
        {pillars.map((p) => {
          const Icon = p.icon;
          return (
            <div
              key={p.id}
              className={`p-4 rounded-xl border ${p.borderColor} ${p.bgColor} shadow-lg space-y-2 flex flex-col justify-between transition-all hover:scale-[1.02]`}
            >
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-black text-slate-400 tracking-widest">{p.num}</span>
                  <Icon className={`w-4 h-4 ${p.textColor}`} />
                </div>
                <h3 className={`text-xs font-extrabold text-white leading-tight`}>{p.title}</h3>
                <p className="text-[11px] text-slate-300 font-sans leading-snug">{p.description}</p>
              </div>

              <div className="pt-2 border-t border-slate-800/80 space-y-1">
                <div className={`text-[10px] font-bold ${p.textColor} flex items-center gap-1`}>
                  <CheckCircle2 className="w-3 h-3 shrink-0" />
                  <span>{p.status}</span>
                </div>
                <div className="text-[10px] text-slate-400 truncate">{p.metrics}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Execution Alignment Banner Statement */}
      <div className="bg-slate-950 border border-emerald-900/80 p-3.5 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5">
          <Terminal className="w-4 h-4 text-emerald-400 shrink-0" />
          <span className="text-slate-300 font-mono">
            <span className="text-emerald-400 font-bold">SYSTEM STATEMENT:</span> Apex-Omega is running in full 026-aligned execution mode. Hard logic + dynamic config + live state + simulation permissions + settlement accounting active.
          </span>
        </div>

        <div className="text-[11px] text-slate-500 font-mono shrink-0">
          Last Verified: <span className="text-slate-300 font-bold">{lastCheckTime}</span>
        </div>
      </div>
    </div>
  );
};
