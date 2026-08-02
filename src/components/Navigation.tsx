import React from 'react';
import { Network, Calculator, Server, Cpu, Database, Terminal, Sparkles, BookOpen, Radio, HardDrive, ShieldCheck, Volume2, Blocks, Layers, TrendingUp, Send, Zap, Flame, History } from 'lucide-react';

export type TabType =
  | 'top50_execution'
  | 'pipeline'
  | 'c1c2_logging'
  | 'apex_optimization'
  | 'vqc_ranker'
  | 'execution_integrity'
  | 'tx_builder'
  | 'onchain_parity'
  | 'capital_injector'
  | 'accountant'
  | 'transient_accounting'
  | 'protocols'
  | 'sonic_master'
  | 'main_net_engine'
  | 'math_indexer'
  | 'google_drive'
  | 'benchmark'
  | 'ai_assistant'
  | 'live_mainnet'
  | 'history_90d';

interface NavigationProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  unresolvedAuditsCount: number;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onTabChange,
  unresolvedAuditsCount,
}) => {
  const tabs = [
    // TIER 1: DIRECT EXECUTION & YIELD GENERATION
    { id: 'top50_execution', label: 'Top 50 Routes (12s Cycle)', icon: TrendingUp, tier: 'TIER 1 (YIELD)', badge: '50 Routes / 12s', badgeColor: 'bg-emerald-950 text-emerald-300 border border-emerald-800' },
    { id: 'history_90d', label: '90-Day Simulation', icon: History, tier: 'TIER 1 (YIELD)', badge: 'Alchemy Anchored', badgeColor: 'bg-emerald-950 text-emerald-300 border border-emerald-800' },
    { id: 'pipeline', label: 'Live Pipeline', icon: Network, tier: 'TIER 1 (YIELD)', badge: 'Direct Alpha', badgeColor: 'bg-emerald-950 text-emerald-300 border border-emerald-800' },
    { id: 'c1c2_logging', label: 'C1 × C2 Engine & Log', icon: Zap, tier: 'TIER 1 (YIELD)', badge: '4-Block Parity', badgeColor: 'bg-emerald-950 text-emerald-300 border border-emerald-800' },
    { id: 'apex_optimization', label: 'EIP-1153 & Latency Studio', icon: Flame, tier: 'TIER 1 (YIELD)', badge: 'Low-Latency', badgeColor: 'bg-amber-950 text-amber-300 border border-amber-800' },
    { id: 'vqc_ranker', label: 'VQC Alpha Ranker', icon: Cpu, tier: 'TIER 1 (YIELD)', badge: 'Quantum Score', badgeColor: 'bg-purple-950 text-purple-300 border border-purple-800' },
    { id: 'execution_integrity', label: 'Execution Integrity', icon: ShieldCheck, tier: 'TIER 1 (YIELD)', badge: 'Zero Revert', badgeColor: 'bg-emerald-950 text-emerald-300 border border-emerald-800' },
    { id: 'tx_builder', label: 'Tx Builder & Key Storage', icon: Send, tier: 'TIER 1 (YIELD)', badge: 'EIP-1559 & eth_call', badgeColor: 'bg-cyan-950 text-cyan-300 border border-cyan-800' },

    // TIER 2: ON-CHAIN PARITY & POSITION SIZING
    { id: 'onchain_parity', label: 'On-Chain Block Parity', icon: Blocks, tier: 'TIER 2 (PARITY)', badge: 'Mainnet #137', badgeColor: 'bg-cyan-950 text-cyan-300 border border-cyan-800' },
    { id: 'capital_injector', label: 'Capital Injector', icon: Calculator, tier: 'TIER 2 (PARITY)', badge: 'Calculus Sizing', badgeColor: 'bg-amber-950 text-amber-300 border border-amber-800' },

    // TIER 3: SETTLEMENT, ACCOUNTING & FINANCIAL PROJECTIONS
    {
      id: 'accountant',
      label: 'Accountant Stream',
      icon: Database,
      tier: 'TIER 3 (LEDGER)',
      badge: unresolvedAuditsCount > 0 ? `${unresolvedAuditsCount} Unsynced` : 'Synced & Projected',
      badgeColor: unresolvedAuditsCount > 0 ? 'bg-amber-900/80 text-amber-300' : 'bg-slate-800 text-slate-400',
    },
    { id: 'transient_accounting', label: 'Transient Accounting', icon: Layers, tier: 'TIER 3 (LEDGER)', badge: 'EIP-1153 Ledger', badgeColor: 'bg-purple-950 text-purple-300 border border-purple-800' },
    { id: 'protocols', label: 'Protocol Registry', icon: Server, tier: 'TIER 3 (LEDGER)', badge: 'Pots Isolated' },

    // TIER 4: HIGH-TECH INFRA & INVARIANTS
    { id: 'sonic_master', label: 'Sonic Master & Invariants', icon: Volume2, tier: 'TIER 4 (INFRA)', badge: '20Hz-20kHz DSP', badgeColor: 'bg-cyan-950 text-cyan-300 border border-cyan-800' },
    { id: 'main_net_engine', label: 'Main Net Engine', icon: Cpu, tier: 'TIER 4 (INFRA)', badge: 'AAA Audited' },
    { id: 'math_indexer', label: 'Math Equation Indexer', icon: BookOpen, tier: 'TIER 4 (INFRA)', badge: '11 Indexed' },
    { id: 'google_drive', label: 'Google Drive Sync', icon: HardDrive, tier: 'TIER 4 (INFRA)', badge: 'Cloud Vault' },
    { id: 'benchmark', label: 'Benchmark Suite', icon: Terminal, tier: 'TIER 4 (INFRA)', badge: 'Readiness' },
    { id: 'ai_assistant', label: 'Gemini AI Assistant', icon: Sparkles, tier: 'TIER 4 (INFRA)', badge: 'Server-Side' },
    { id: 'live_mainnet', label: 'Go Live (Mainnet)', icon: Radio, tier: 'TIER 4 (INFRA)', badge: 'Polygon #137' },
  ];

  return (
    <nav id="omega-navigation" className="bg-slate-900/90 backdrop-blur border-b border-slate-800 px-4 font-mono">
      <div className="max-w-7xl mx-auto flex items-center space-x-1.5 overflow-x-auto no-scrollbar py-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`tab-btn-${tab.id}`}
              onClick={() => onTabChange(tab.id as TabType)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-md shadow-emerald-500/10 font-bold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-emerald-400' : 'text-slate-400'}`} />
              <span>{tab.label}</span>
              {tab.badge && (
                <span
                  className={`px-1.5 py-0.2 text-[9px] rounded font-mono ${
                    tab.badgeColor ||
                    (isActive ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/60' : 'bg-slate-800 text-slate-400')
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};

