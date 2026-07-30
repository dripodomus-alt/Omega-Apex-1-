import React, { useState, useEffect } from "react";
import {
  Terminal,
  Database,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

export default function SimulationConsole() {
  const [snapshot, setSnapshot] = useState<any>(null);

  useEffect(() => {
    const fetchSnapshot = async () => {
      try {
        const [pipeline, opportunities, readiness, superState] = await Promise.all([
          fetch("/api/execution/pipeline").then((res) => res.json()),
          fetch("/api/execution/opportunities").then((res) => res.json()),
          fetch("/api/system/readiness").then((res) => res.json()),
          fetch("/api/state/super-state").then((res) => res.json()),
        ]);
        setSnapshot({ pipeline, opportunities, readiness, superState, at: new Date().toLocaleTimeString() });
      } catch {
        setSnapshot((prev: any) => prev);
      }
    };
    fetchSnapshot();
    const interval = setInterval(fetchSnapshot, 1500);
    return () => clearInterval(interval);
  }, []);

  const simStage = snapshot?.pipeline?.stages?.find((stage: any) => stage.name === "C1_PRE_STATE_SIMULATION");
  const rows = (snapshot?.opportunities?.opportunities || []).slice(0, 12);
  const stateHash = snapshot?.superState?.snapshot?.stateHash;

  return (
    <div className="flex flex-col h-full bg-[#07080a] border border-[#1e2025] rounded-sm font-mono text-[10px] glass-specular glass-inset">
      <div className="flex items-center justify-between p-2 border-b border-[#1e2025] bg-[#0d0e12]">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-cyan-400" />
          <h2 className="font-bold text-gray-300 uppercase tracking-wider">
            C1 Live Mainnet Execution Console
          </h2>
        </div>
        <div className="flex items-center gap-2 text-[8px] text-gray-500 uppercase font-bold">
          <div className="flex items-center gap-1">
            <Database size={10} className="text-emerald-500" />
            {snapshot?.readiness?.dry_run ? "Dry Sim Monitor" : "Live Gate Monitor"}
          </div>
        </div>
      </div>
      <div className="flex-1 p-2 overflow-y-auto space-y-1.5 custom-scrollbar bg-[#0b0c10]">
        <div className="grid grid-cols-3 gap-1.5 mb-2">
          <div className="border border-[#1e2025] bg-black/30 p-1.5">
            <div className="text-[7px] text-gray-500 uppercase">Pre-Broadcast Sim</div>
            <div className="text-cyan-400 font-bold">{simStage?.count ?? 0}</div>
          </div>
          <div className="border border-[#1e2025] bg-black/30 p-1.5">
            <div className="text-[7px] text-gray-500 uppercase">C1 Visible</div>
            <div className="text-emerald-400 font-bold">{snapshot?.opportunities?.c1ExecutableVisible ?? 0}</div>
          </div>
          <div className="border border-[#1e2025] bg-black/30 p-1.5">
            <div className="text-[7px] text-gray-500 uppercase">State Hash</div>
            <div className="text-gray-300 font-bold truncate">{stateHash ? stateHash.slice(0, 10) : "NO_STATE"}</div>
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="text-center text-gray-600 mt-4 uppercase animate-pulse">
            Waiting for quote-ready simulated routes...
          </div>
        ) : (
          rows.map((sim: any, i: number) => (
            <div
              key={i}
              className={`flex items-start gap-2 p-1.5 border-l-2 ${sim.c1ExecutionEligible || sim.status === "EXECUTABLE_PROFIT_CANDIDATE" ? "border-emerald-500 bg-emerald-500/5" : "border-yellow-500 bg-yellow-500/5"}`}
            >
              <div className="text-gray-500 shrink-0">[{snapshot?.at}]</div>
              <div className="flex-1 flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">
                    Target ID:{" "}
                    <span className="text-gray-300 select-all">{sim.routeId || sim.redisId || "UNRANKED"}</span>
                  </span>
                  <span className="text-gray-500">|</span>
                  <span className="text-cyan-400">{sim.path || sim.pair || "DISCOVERY_ROUTE"}</span>
                </div>
                <div className="flex items-center gap-4 text-[9px]">
                  <span className="text-emerald-400 font-bold">
                    ${Number(sim.netProfitUsd ?? sim.profit_usd ?? 0).toFixed(4)} Net
                  </span>
                  <span className="text-gray-500">{sim.venues || "venues=pending"}</span>
                  {sim.c1ExecutionEligible || sim.status === "EXECUTABLE_PROFIT_CANDIDATE" ? (
                    <span className="text-emerald-500 flex items-center gap-1">
                      <CheckCircle2 size={10} /> PRE-BROADCAST PASS
                    </span>
                  ) : (
                    <span className="text-yellow-500 flex items-center gap-1">
                      <AlertCircle size={10} /> {sim.status || "LISTED"}
                    </span>
                  )}
                </div>
              </div>
              <span className="shrink-0 px-2 py-0.5 border border-cyan-500/30 text-cyan-400 bg-cyan-500/10 rounded-sm uppercase tracking-wider text-[8px]">
                Rank {sim.rank ?? i + 1}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
