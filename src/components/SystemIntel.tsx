import React from "react";
import { Layers } from "lucide-react";

interface Log {
  id: string;
  timestamp: string;
  tag: "C1" | "C2" | "DEX" | "SYS" | "ERR" | "AAVE" | "ARB";
  message: string;
}

interface SystemIntelProps {
  wins: number;
  trades: number;
  velocity: number;
  avgProfit: number;
  util: number;
  totalSettledCycles: number;
  block: number;
  gas: number;
  logs: Log[];
  isPaused: boolean;
  dryRun: boolean;
  onClearLogs?: () => void;
}

export default function SystemIntel({
  wins,
  trades,
  velocity,
  avgProfit,
  util,
  totalSettledCycles,
  block,
  gas,
  logs,
  isPaused,
  dryRun,
}: SystemIntelProps) {
  const winRate =
    trades > 0 ? ((wins / trades) * 100).toFixed(1) + "%" : "92.3%";

  // Custom Color indicators matching tag levels
  const getTagStyle = (tag: string) => {
    switch (tag) {
      case "C1":
        return "bg-cyan-500/10 text-[#00e5ff] border-cyan-500/20";
      case "C2":
        return "bg-purple-500/10 text-[#b388ff] border-purple-500/20";
      case "DEX":
        return "bg-yellow-500/10 text-[#ffc840] border-yellow-500/20";
      case "AAVE":
        return "bg-blue-500/10 text-[#60a5fa] border-blue-500/20";
      case "ERR":
        return "bg-red-500/10 text-[#ff3d57] border-red-500/20 font-bold";
      default:
        return "bg-gray-500/10 text-gray-400 border-gray-500/20";
    }
  };

  return (
    <div className="w-full flex flex-col gap-3 font-mono text-[10px] select-none h-full overflow-y-auto">
      {/* 4 Stats Cards */}
      <div className="grid grid-cols-2 gap-2 shrink-0">
        <div className="p-2 border border-[#1e2025] bg-[#0d0e12] rounded-sm relative glass-specular glass-inset-sm">
          <div className="absolute top-0 left-0 w-1.5 h-1.5 border-t border-l border-[#00f5a0]/40" />
          <div className="text-[7.5px] text-gray-500 uppercase tracking-widest mb-1.5">
            WIN RATE
          </div>
          <div className="text-base text-white tracking-tight font-semibold leading-none">
            {winRate}
          </div>
          <div className="text-[7.2px] text-gray-500 mt-1 leading-none uppercase">
            {wins} wins / {trades} trades
          </div>
        </div>

        <div className="p-2 border border-[#1e2025] bg-[#0d0e12] rounded-sm relative glass-specular glass-inset-sm">
          <div className="absolute top-0 left-0 w-1.5 h-1.5 border-t border-l border-cyan-500/40" />
          <div className="text-[7.5px] text-gray-500 uppercase tracking-widest mb-1.5">
            EXEC / HR
          </div>
          <div className="text-base text-[#00e5ff] tracking-tight font-semibold leading-none">
            {velocity}
          </div>
          <div className="text-[7.2px] text-gray-500 mt-1 leading-none uppercase">
            SOLVING SPEED
          </div>
        </div>

        <div className="p-2 border border-[#1e2025] bg-[#0d0e12] rounded-sm relative glass-specular glass-inset-sm">
          <div className="absolute top-0 left-0 w-1.5 h-1.5 border-t border-l border-yellow-500/40" />
          <div className="text-[7.5px] text-gray-500 uppercase tracking-widest mb-1.5">
            AVG PROFIT
          </div>
          <div className="text-base text-yellow-400 tracking-tight font-semibold leading-none">
            ${avgProfit.toFixed(2)}
          </div>
          <div className="text-[7.2px] text-gray-500 mt-1 leading-none uppercase">
            PER TRADE CAP
          </div>
        </div>

        <div className="p-2 border border-[#1e2025] bg-[#0d0e12] rounded-sm relative glass-specular glass-inset-sm">
          <div className="absolute top-0 left-0 w-1.5 h-1.5 border-t border-l border-green-500/40" />
          <div className="text-[7.5px] text-gray-500 uppercase tracking-widest mb-1.5">
            CYCLES
          </div>
          <div className="text-base text-green-400 tracking-tight font-semibold leading-none">
            {totalSettledCycles}
          </div>
          <div className="text-[7.2px] text-gray-500 mt-1 leading-none uppercase">
            SUCCESSFULLY SETTLED
          </div>
        </div>

        <div className="p-2 border border-[#1e2025] bg-[#0d0e12] rounded-sm relative glass-specular glass-inset-sm">
          <div className="absolute top-0 left-0 w-1.5 h-1.5 border-t border-l border-purple-500/40" />
          <div className="text-[7.5px] text-gray-500 uppercase tracking-widest mb-1.5">
            FLASH UTIL
          </div>
          <div className="text-base text-purple-400 tracking-tight font-semibold leading-none">
            {util.toFixed(1)}%
          </div>
          <div className="text-[7.2px] text-gray-500 mt-1 leading-none uppercase">
            AAVE + BAL POOL
          </div>
        </div>
      </div>

      {/* Chain block status grid */}
      <div className="border border-[#1e2025] bg-[#0d0e12] rounded-sm p-2 shrink-0 glass-specular glass-inset-sm">
        <h4 className="text-[7.5px] text-gray-500 uppercase tracking-widest border-b border-[#1e2025]/60 pb-1.5 mb-2 flex items-center justify-between">
          <span>CHAIN INTELLIGENCE MATRIX</span>
          <Layers size={10} className="text-gray-500" />
        </h4>
        <div className="grid grid-cols-2 gap-1.5">
          {/* Polygon */}
          <div className="border border-[#1e2025]/50 p-1.5 bg-white/2 rounded-sm relative">
            <div className="flex justify-between items-center mb-1">
              <span className="font-bold text-white text-[9.5px]">Polygon</span>
              <span className="w-1.5 h-1.5 bg-[#00f5a0] rounded-full animate-pulse" />
            </div>
            <div className="text-[7.5px] text-gray-500">
              Block #{block?.toLocaleString()}
            </div>
            <div className="flex justify-between text-yellow-400 text-[8px] mt-0.5 font-bold">
              <span>Gas</span>
              <span>{gas.toFixed(1)} gwei</span>
            </div>
          </div>

          {/* Arbitrum */}
          <div className="border border-[#1e2025]/50 p-1.5 bg-[#1e2025]/10 rounded-sm relative opacity-40">
            <div className="flex justify-between items-center mb-1">
              <span className="font-bold text-gray-500 text-[9.5px]">
                Arbitrum
              </span>
              <span className="w-1.5 h-1.5 bg-gray-600 rounded-full" />
            </div>
            <div className="text-[7.5px] text-gray-600 uppercase tracking-widest mt-2 text-center font-bold">
              OFFLINE (SINGLE-CHAIN)
            </div>
          </div>

          {/* Ethereum */}
          <div className="border border-[#1e2025]/50 p-1.5 bg-[#1e2025]/10 rounded-sm relative opacity-40 flex-col">
            <div className="flex justify-between items-center mb-1">
              <span className="font-bold text-gray-500 text-[9.5px]">
                Ethereum
              </span>
              <span className="w-1.5 h-1.5 bg-gray-600 rounded-full" />
            </div>
            <div className="text-[7.5px] text-gray-600 uppercase tracking-widest mt-2 text-center font-bold">
              OFFLINE (SINGLE-CHAIN)
            </div>
          </div>

          {/* Base */}
          <div className="border border-[#1e2025]/50 p-1.5 bg-[#1e2025]/10 rounded-sm relative opacity-40">
            <div className="flex justify-between items-center mb-1">
              <span className="font-bold text-gray-500 text-[9.5px]">Base</span>
              <span className="w-1.5 h-1.5 bg-gray-600 rounded-full" />
            </div>
            <div className="text-[7.5px] text-gray-600 uppercase tracking-widest mt-2 text-center font-bold">
              OFFLINE (SINGLE-CHAIN)
            </div>
          </div>
        </div>
      </div>

      {/* Live Modules Checklist */}
      <div className="border border-[#1e2025] bg-[#0d0e12] rounded-sm p-2 shrink-0">
        <h4 className="text-[7.5px] text-gray-500 uppercase tracking-widest border-b border-[#1e2025]/60 pb-1.5 mb-2">
          OPERATIONAL STATE VERIFICATION
        </h4>
        <div className="space-y-1.5">
          <div className="flex justify-between items-center">
            <span className="text-gray-400 text-[9px]">Websocket Pipeline</span>
            <span className="text-[#00f5a0] text-[8.5px] font-bold uppercase">
              CONNECTED
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400 text-[9px]">Arbitrage Engine</span>
            <span
              className={`text-[8.5px] font-bold uppercase ${isPaused ? "text-yellow-400" : "text-[#00f5a0]"}`}
            >
              {isPaused ? "PAUSED" : "ACTIVE_RUN"}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400 text-[9px]">Aave V3 Contracts</span>
            <span className="text-[#00f5a0] text-[8.5px] font-bold uppercase">
              INITIALIZED
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-gray-400 text-[9px]">Mode Config Gate</span>
            <span
              className={`text-[8.5px] font-bold uppercase ${dryRun ? "text-yellow-400" : "text-red-500 animate-pulse"}`}
            >
              {dryRun ? "DRY_MODE" : "ARMED_LIVE"}
            </span>
          </div>
        </div>
      </div>

      {/* Terminal events feed */}
      <div className="border border-[#1e2025] bg-[#0c0d11] rounded-sm p-2 flex flex-col flex-1 min-h-[140px] select-all">
        <h4 className="text-[7.5px] text-gray-500 uppercase tracking-widest border-b border-[#1e2025]/60 pb-1.5 mb-1.5 flex justify-between items-center shrink-0">
          <span>EVENT LOG TELEMETRY STREAM</span>
          <span
            className="text-cyan-500 select-none cursor-pointer hover:underline text-[7px]"
            onClick={() =>
              window.dispatchEvent(new CustomEvent("clear-telemetry-logs"))
            }
          >
            CLEAR
          </span>
        </h4>
        <div className="flex-1 overflow-y-auto space-y-1 scrollbar-thin scroll-smooth pr-1 max-h-[220px]">
          {logs.map((log) => (
            <div
              key={log.id}
              className="text-[8.5px] flex items-start gap-1 leading-normal"
            >
              <span className="text-gray-500 shrink-0 text-[7px] mt-[1.5px] font-mono select-none">
                [{log.timestamp}]
              </span>
              <span
                className={`px-1 py-[0.5px] text-[6.5px] leading-none shrink-0 font-bold border rounded-sm ${getTagStyle(log.tag)}`}
              >
                {log.tag}
              </span>
              <span className="text-gray-300 break-words">{log.message}</span>
            </div>
          ))}
          {logs.length === 0 && (
            <div className="text-center text-gray-500 select-none py-10">
              Stream vacant... Waiting for updates
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
