import React, { useState, useEffect } from "react";
import { Shield, Zap, RefreshCw, Pause, Play, Eye, Flame, Activity } from "lucide-react";

interface HeaderProps {
  pnl: number;
  lifetimePnl: number;
  gas: number;
  block: number;
  dryRun: boolean;
  isPaused: boolean;
  onScan: () => void;
  onPauseToggle: () => void;
  onDryRunToggle: () => void;
  onArmLive: () => void;
  onTestLanes?: () => void;
  lanesHealth?: "idle" | "testing" | "healthy" | "error";
  connectionStatus: "live" | "poll" | "connecting" | "error";
  onDiagnosticOpen?: () => void;
}

export default function Header({
  pnl,
  lifetimePnl,
  gas,
  block,
  dryRun,
  isPaused,
  onScan,
  onPauseToggle,
  onDryRunToggle,
  onArmLive,
  onTestLanes,
  lanesHealth = "idle",
  connectionStatus,
  onDiagnosticOpen,
}: HeaderProps) {
  const [utcTime, setUtcTime] = useState("");
  const [isArmConfirming, setIsArmConfirming] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setUtcTime(new Date().toUTCString().replace("GMT", "UTC"));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleArmClick = () => {
    if (!isArmConfirming) {
      setIsArmConfirming(true);
      setTimeout(() => setIsArmConfirming(false), 4000);
    } else {
      setIsArmConfirming(false);
      onArmLive();
    }
  };

  const getConnBadge = () => {
    switch (connectionStatus) {
      case "live":
        return (
          <div className="flex items-center gap-1.5 bg-green-500/10 border border-green-500/30 px-2 py-0.5 rounded-sm text-green-400 font-bold tracking-wider">
            <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-ping" />
            <span>LIVE · SYNCED</span>
          </div>
        );
      case "poll":
        return (
          <div className="flex items-center gap-1.5 bg-yellow-500/10 border border-yellow-500/30 px-2 py-0.5 rounded-sm text-yellow-500 font-bold tracking-wider">
            <span className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-pulse" />
            <span>API POLL</span>
          </div>
        );
      case "connecting":
        return (
          <div className="flex items-center gap-1.5 bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 rounded-sm text-blue-400 font-bold tracking-wider">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
            <span>CONNECTING</span>
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-1.5 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded-sm text-red-500 font-bold tracking-wider">
            <span className="w-1.5 h-1.5 bg-red-400 rounded-full" />
            <span>OFFLINE</span>
          </div>
        );
    }
  };

  return (
    <header className="h-10 bg-[#030408]/90 backdrop-blur-xl border-b border-cyan-900/30 flex items-center px-4 justify-between gap-4 font-mono text-[9px] shrink-0 relative z-30 select-none shadow-[inset_0_-1px_0_rgba(255,255,255,0.04),inset_0_1px_0_rgba(255,255,255,0.07),0_4px_30px_rgba(0,255,255,0.05)] glass-specular">
      {/* Logo Section */}
      <div className="flex items-center gap-3">
        <div className="w-6 h-6 bg-gradient-to-br from-cyan-500/20 to-fuchsia-500/20 rounded shadow-[inset_0_0_8px_rgba(0,255,255,0.2)] flex items-center justify-center font-bold text-white text-[12px] border border-cyan-500/50">
          Ω
        </div>
        <div>
          <h1 className="text-[11px] font-bold tracking-[0.2em] uppercase leading-none">
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 to-[#00f5a0]">
              APEX
            </span>{" "}
            OMEGA 2.0
          </h1>
        </div>
      </div>

      <div className="h-4 w-px bg-cyan-900/50" />

      {/* Backend Status Flag */}
      {getConnBadge()}

      <div className="h-4 w-px bg-cyan-900/50 hidden md:block" />

      {/* Real-time Telemetry Headers */}
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-end">
          <span className="text-gray-500 uppercase text-[7.5px] tracking-widest">
            SESSION P&L
          </span>
          <span
            className={`font-bold transition-all text-[11.5px] ${pnl >= 0 ? "text-[#00f5a0]" : "text-red-400"}`}
          >
            $
            {pnl.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>

        <div className="flex flex-col items-end hidden md:flex">
          <span className="text-gray-500 uppercase text-[7.5px] tracking-widest">
            LIFETIME P&L
          </span>
          <span
            className={`font-bold transition-all text-[11.5px] ${lifetimePnl >= 0 ? "text-[#00f5a0]" : "text-red-400"}`}
          >
            ${lifetimePnl.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>

        <div className="flex flex-col items-end">
          <span className="text-gray-500 uppercase text-[7.5px] tracking-widest">
            POLYGON GAS
          </span>
          <span className="text-yellow-400 font-bold text-[11.5px]">
            {gas.toFixed(1)} gwei
          </span>
        </div>

        <div className="flex flex-col items-end hidden sm:flex">
          <span className="text-gray-500 uppercase text-[7.5px] tracking-widest">
            BLOCK_HEIGHT
          </span>
          <span className="text-white text-[11.5px]">
            {block ? block.toLocaleString() : "—"}
          </span>
        </div>

        <div className="flex flex-col items-end hidden sm:flex">
          <span className="text-gray-500 uppercase text-[7.5px] tracking-widest">
            DRY RUN
          </span>
          <span
            className={`font-bold text-[11px] ${dryRun ? "text-[#ffc840]" : "text-[#00f5a0]"}`}
          >
            {dryRun ? "YES (SHADOW)" : "NO (LIVE)"}
          </span>
        </div>
      </div>

      {/* Master Commands and Time */}
      <div className="flex items-center gap-1.5 ml-auto">
        <button
          onClick={onTestLanes}
          disabled={lanesHealth === "testing"}
          className={`px-1.5 py-0.5 border rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer ${
            lanesHealth === "testing" 
              ? "bg-blue-950/20 border-blue-500 text-blue-400 animate-pulse cursor-wait"
              : lanesHealth === "healthy"
                ? "bg-green-950/20 hover:bg-green-950/40 border-green-500/30 hover:border-green-500/50 text-[#00f5a0]"
                : lanesHealth === "error"
                  ? "bg-red-950/20 hover:bg-red-950/40 border-red-500/30 hover:border-red-500/50 text-red-500"
                  : "bg-indigo-950/20 hover:bg-indigo-950/40 border-indigo-500/30 hover:border-indigo-500/50 text-indigo-400"
          }`}
          title="Run lightweight RPC heartbeat check for C1/C2 targets"
        >
          <Activity size={10} className={lanesHealth === "testing" ? "animate-spin" : ""} />
          <span>
            {lanesHealth === "testing" ? "TESTING LANES..." 
             : lanesHealth === "healthy" ? "LANES OK" 
             : lanesHealth === "error" ? "LANES ERR" 
             : "TEST LANES"}
          </span>
        </button>

        <button
          onClick={onDiagnosticOpen}
          className="px-1.5 py-0.5 bg-purple-950/20 hover:bg-purple-950/40 border border-purple-500/30 hover:border-purple-500/50 text-purple-400 rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer"
          title="Run Diagnostics"
        >
          <Zap size={10} />
          <span>DIAGNOSTICS</span>
        </button>

        <button
          onClick={onScan}
          className="px-1.5 py-0.5 bg-cyan-950/20 hover:bg-cyan-950/40 border border-cyan-500/30 hover:border-cyan-500/50 text-cyan-400 rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer"
          title="Trigger on-demand DEX spread scanning"
        >
          <RefreshCw size={10} className="animate-spin-slow" />
          <span>⟳ SCAN</span>
        </button>

        {isPaused ? (
          <button
            onClick={onPauseToggle}
            className="px-1.5 py-0.5 bg-green-950/20 hover:bg-green-950/40 border border-green-500/40 hover:border-green-500/60 text-[#00f5a0] rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer"
          >
            <Play size={10} />
            <span>▶ RESUME</span>
          </button>
        ) : (
          <button
            onClick={onPauseToggle}
            className="px-1.5 py-0.5 bg-yellow-950/20 hover:bg-yellow-950/40 border border-yellow-500/40 hover:border-yellow-500/60 text-yellow-400 rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer"
          >
            <Pause size={10} />
            <span>⏸ PAUSE</span>
          </button>
        )}

        <button
          onClick={onDryRunToggle}
          className="px-1.5 py-0.5 bg-orange-950/20 hover:bg-orange-950/40 border border-orange-500/40 hover:border-orange-500/60 text-orange-400 rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer"
        >
          <Eye size={10} />
          <span>◈ FORCE DRY</span>
        </button>

        <button
          onClick={handleArmClick}
          className={`px-1.5 py-0.5 border rounded-sm font-bold uppercase transition-all tracking-wider flex items-center gap-1 cursor-pointer ${
            isArmConfirming
              ? "bg-red-600 border-red-500 text-white animate-pulse"
              : "bg-red-950/20 hover:bg-red-950/40 border-red-500/40 hover:border-red-500/60 text-red-500"
          }`}
        >
          <Flame size={10} />
          <span>{isArmConfirming ? "⚠ CONFIRM ARM" : "⚠ ARM LIVE"}</span>
        </button>

        <span className="text-gray-500 font-bold ml-2 text-right hidden lg:inline-block w-20">
          {utcTime ? utcTime.split(" ")[4] : "00:00:00"}
        </span>
      </div>
    </header>
  );
}
