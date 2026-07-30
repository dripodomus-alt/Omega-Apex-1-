import React, { useState, useEffect, useRef } from "react";
import {
  X,
  CheckCircle,
  CircleDashed,
  Terminal,
  ArrowRight,
  Activity,
  ShieldCheck,
} from "lucide-react";

interface ArbAlert {
  id: string;
  profit: number;
  path: string;
  dex: string;
  timestamp: string;
}

interface ExecutionModalProps {
  alert: ArbAlert | null;
  onClose: () => void;
}

const STAGES = [
  {
    id: "c1",
    label: "C1 CONFIRMATION",
    desc: "AAVE Flash Loan Verification & Liquidity State Lock",
  },
  {
    id: "c2",
    label: "C2 INITIATION",
    desc: "Leg 1 Target Swap Execution on Target DEX",
  },
  {
    id: "c3",
    label: "ROUTING RESOLVED",
    desc: "Leg 2 Return Swap & Arbitrage Spread Captured",
  },
  {
    id: "bundle",
    label: "MEV BUNDLE",
    desc: "Flashbots RPC Payload Broadcast & Bundling",
  },
  {
    id: "settled",
    label: "CHAIN SETTLEMENT",
    desc: "Transaction Confirmed in Latest Block",
  },
];

export default function ExecutionModal({
  alert,
  onClose,
}: ExecutionModalProps) {
  const [currentStageIndex, setCurrentStageIndex] = useState(-1);
  const [logs, setLogs] = useState<string[]>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!alert) {
      setCurrentStageIndex(-1);
      setLogs([]);
      return;
    }

    setLogs([
      `[SYS] Received target alert ID: ${alert.id}`,
      `[SYS] Analyzing path: ${alert.path} on ${alert.dex}...`,
    ]);
    setCurrentStageIndex(0); // start at index 0
    let stage = 0;

    const interval = setInterval(() => {
      stage++;
      if (stage <= STAGES.length) {
        setCurrentStageIndex(stage);

        // Emit stage-specific execution telemetry
        if (stage === 1) {
          setLogs((prev) => [
            ...prev,
            `[C1] AAVE Flash Loan $50,000 USDC Approved.`,
            `[C1] State lock confirmed for execution block.`,
          ]);
        } else if (stage === 2) {
          setLogs((prev) => [
            ...prev,
            `[C2] Initiating swap 1 across ${alert.dex}...`,
            `[C2] Slippage tolerance locked at 0.1%.`,
          ]);
        } else if (stage === 3) {
          setLogs((prev) => [
            ...prev,
            `[ROUTING] Swap 2 executing via configured live router adapter.`,
            `[ROUTING] Arbitrage condition verified. Net positive.`,
          ]);
        } else if (stage === 4) {
          setLogs((prev) => [
            ...prev,
            `[BUNDLE] Compiling MEV bundle with private builder endpoint...`,
            `[BUNDLE] Bribe fee attached: 0.05 ETH.`,
          ]);
        } else if (stage === 5) {
          setLogs((prev) => [
            ...prev,
            `[SETTLED] Block digested.`,
            `[PROFIT] Secured $${alert.profit.toFixed(2)} to cold storage.`,
          ]);
          clearInterval(interval);
        }
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [alert]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  if (!alert) return null;

  const isCompleted = currentStageIndex >= STAGES.length;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[#0b0c10] border border-[#1e2025] rounded-lg shadow-[inset_0_1px_0_rgba(255,255,255,0.07),inset_0_0_32px_rgba(0,0,0,0.38),0_25px_50px_-12px_rgba(0,0,0,0.5)] glass-specular w-full max-w-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#1e2025] bg-[#0d0e12]">
          <div className="flex items-center gap-3">
            <Activity className="text-emerald-400" size={20} />
            <div>
              <h2 className="text-sm font-semibold tracking-widest text-white">
                LIVE EXECUTION TRACE
              </h2>
              <div className="text-[10px] text-gray-500 font-mono mt-0.5">
                TARGET: {alert.id}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors cursor-pointer p-1"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 flex flex-col gap-6">
          {/* Top summary stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-[#13151a] border border-[#1e2025] p-3 rounded">
              <div className="text-[10px] text-gray-500 font-mono mb-1">
                EXPECTED PROFIT
              </div>
              <div className="text-emerald-400 font-mono text-xl font-bold">
                ${alert.profit.toFixed(2)}
              </div>
            </div>
            <div className="bg-[#13151a] border border-[#1e2025] p-3 rounded col-span-2">
              <div className="text-[10px] text-gray-500 font-mono mb-1">
                TARGET PATH / DEX
              </div>
              <div className="text-gray-300 font-mono text-sm truncate">
                {alert.path}
              </div>
              <div className="text-indigo-400 font-mono text-xs mt-1">
                {alert.dex}
              </div>
            </div>
          </div>

          {/* Stepper */}
          <div className="relative py-2 mt-2">
            <div className="absolute left-[15px] top-4 bottom-4 w-px bg-[#1e2025] -z-10" />
            <div className="space-y-6">
              {STAGES.map((stage, i) => {
                const isPast = currentStageIndex > i;
                const isCurrent = currentStageIndex === i;
                const isFuture = currentStageIndex < i;

                return (
                  <div key={stage.id} className="flex gap-4 group">
                    <div className="relative flex-none">
                      {isPast ? (
                        <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center">
                          <CheckCircle size={14} className="text-emerald-400" />
                        </div>
                      ) : isCurrent ? (
                        <div className="w-8 h-8 rounded-full bg-blue-500/20 border border-blue-500/50 flex items-center justify-center shadow-[0_0_15px_rgba(59,130,246,0.5)]">
                          <CircleDashed
                            size={14}
                            className="text-blue-400 animate-spin"
                          />
                        </div>
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-[#1e2025]/50 border border-[#2a2d36] flex items-center justify-center">
                          <div className="w-2 h-2 rounded-full bg-gray-600" />
                        </div>
                      )}
                    </div>
                    <div className="flex-1 pt-1">
                      <h3
                        className={`text-xs font-bold tracking-wider mb-1 ${isPast ? "text-emerald-400" : isCurrent ? "text-blue-400" : "text-gray-500"}`}
                      >
                        {stage.label}
                      </h3>
                      <p
                        className={`text-[11px] font-mono leading-relaxed ${isFuture ? "text-gray-600" : "text-gray-400"}`}
                      >
                        {stage.desc}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Terminal Logs */}
          <div className="mt-4 border border-[#1e2025] rounded bg-[#07080a] overflow-hidden flex flex-col h-40">
            <div className="flex items-center gap-2 bg-[#13151a] p-2 border-b border-[#1e2025]">
              <Terminal size={12} className="text-gray-500" />
              <span className="text-[10px] text-gray-500 font-mono tracking-widest">
                EXECUTION LOGS
              </span>
            </div>
            <div className="flex-1 p-3 overflow-y-auto font-mono text-[10px] sm:text-xs text-gray-400 space-y-1.5 custom-scrollbar">
              {logs.map((log, index) => (
                <div key={index} className="flex gap-2">
                  <span className="text-gray-600">
                    [{new Date().toLocaleTimeString()}]
                  </span>
                  <span
                    className={
                      log.includes("PROFIT")
                        ? "text-emerald-400"
                        : log.includes("BUNDLE")
                          ? "text-blue-400"
                          : "text-gray-300"
                    }
                  >
                    {log}
                  </span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>

          {/* Action Button */}
          {isCompleted && (
            <button
              onClick={onClose}
              className="mt-2 w-full flex items-center justify-center gap-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 p-3 rounded font-bold text-xs uppercase tracking-widest transition-colors border border-emerald-500/30"
            >
              <ShieldCheck size={16} />
              Return to Monitoring
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

