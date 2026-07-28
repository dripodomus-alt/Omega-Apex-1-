import React, { useState, useEffect } from 'react';
import { Radio, Wifi, Server, CheckCircle2, Activity, ArrowUpRight } from 'lucide-react';

export const EngineHealthWidget: React.FC = () => {
  const [rpcLatency, setRpcLatency] = useState<number>(38);
  const [blockHeight, setBlockHeight] = useState<number>(62849312);
  const [scannerStatus, setScannerStatus] = useState<'Active' | 'Optimal' | 'Scanning'>('Active');
  const [mempoolRate, setMempoolRate] = useState<number>(1420);

  useEffect(() => {
    const interval = setInterval(() => {
      // Simulate subtle realistic telemetry fluctuations
      const latencyDelta = Math.floor(Math.random() * 7) - 3; // -3 to +3
      setRpcLatency((prev) => Math.min(65, Math.max(22, prev + latencyDelta)));

      // Randomly bump block height occasionally
      if (Math.random() > 0.4) {
        setBlockHeight((prev) => prev + 1);
      }

      // Randomize mempool stream throughput slightly
      const rateDelta = Math.floor(Math.random() * 40) - 20;
      setMempoolRate((prev) => Math.min(1800, Math.max(1200, prev + rateDelta)));

      // Random status ticker
      const statuses: ('Active' | 'Optimal' | 'Scanning')[] = ['Active', 'Optimal', 'Scanning'];
      setScannerStatus(statuses[Math.floor(Math.random() * statuses.length)]);
    }, 2500);

    return () => clearInterval(interval);
  }, []);

  return (
    <div id="engine-health-widget" className="bg-slate-950/90 border border-slate-800/90 rounded-xl px-3 py-1.5 font-mono text-xs flex items-center gap-3 text-slate-300 shadow-inner">
      {/* Engine Live Signal Indicator */}
      <div className="flex items-center gap-1.5 shrink-0 border-r border-slate-800/80 pr-2.5">
        <div className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </div>
        <span className="text-[10px] font-bold tracking-wider text-emerald-400 uppercase">Engine Health</span>
      </div>

      {/* Latency Metric */}
      <div className="flex items-center gap-1 text-[11px] shrink-0">
        <Wifi className="w-3 h-3 text-indigo-400 shrink-0" />
        <span className="text-slate-400">RPC:</span>
        <span className={`font-bold ${rpcLatency < 45 ? 'text-emerald-400' : 'text-amber-400'}`}>
          {rpcLatency}ms
        </span>
      </div>

      {/* Scanner Node Metric */}
      <div className="hidden sm:flex items-center gap-1 text-[11px] shrink-0 border-l border-slate-800/80 pl-2.5">
        <Server className="w-3 h-3 text-purple-400 shrink-0" />
        <span className="text-slate-400">Scanner:</span>
        <span className="text-purple-300 font-bold flex items-center gap-0.5">
          <CheckCircle2 className="w-2.5 h-2.5 text-purple-400" />
          {scannerStatus}
        </span>
      </div>

      {/* Mempool Throughput */}
      <div className="hidden md:flex items-center gap-1 text-[11px] shrink-0 border-l border-slate-800/80 pl-2.5">
        <Activity className="w-3 h-3 text-cyan-400 shrink-0" />
        <span className="text-slate-400">Mempool:</span>
        <span className="text-cyan-300 font-bold">
          {mempoolRate.toLocaleString()} tx/s
        </span>
      </div>

      {/* Block Height */}
      <div className="hidden lg:flex items-center gap-1 text-[11px] shrink-0 border-l border-slate-800/80 pl-2.5">
        <Radio className="w-3 h-3 text-amber-400 shrink-0 animate-pulse" />
        <span className="text-slate-400">Block:</span>
        <span className="text-amber-300 font-bold">
          #{blockHeight.toLocaleString()}
        </span>
      </div>
    </div>
  );
};
