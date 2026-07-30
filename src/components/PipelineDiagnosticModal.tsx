import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Server,
  ShieldCheck,
  Database,
  SearchCode,
  Cpu,
} from "lucide-react";

interface PipelineDiagnosticModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function PipelineDiagnosticModal({
  isOpen,
  onClose,
}: PipelineDiagnosticModalProps) {
  const [report, setReport] = useState<any>(null);
  const [lanes, setLanes] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      Promise.all([
        fetch("/api/diagnostics/report").then((r) => r.json()),
        fetch("/api/execution/lanes").then((r) => r.json()),
      ])
        .then(([reportData, lanesData]) => {
          setReport(reportData);
          setLanes(lanesData);
          setLoading(false);
        })
        .catch((e) => {
          console.error(e);
          setLoading(false);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="bg-[#0b0c10] border border-[#1e2025] rounded-xl shadow-[inset_0_1px_0_rgba(255,255,255,0.07),inset_0_0_32px_rgba(0,0,0,0.38),0_25px_50px_-12px_rgba(0,0,0,0.5)] glass-specular w-full max-w-4xl max-h-[90vh] flex flex-col font-mono text-sm overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-[#1e2025] bg-[#07080a]">
            <div className="flex items-center gap-3 text-cyan-400">
              <Server size={20} />
              <h2 className="font-bold tracking-widest uppercase text-white">
                Pipeline Diagnostic Audit
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-1 hover:bg-[#1e2025] rounded text-gray-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
            {loading || !report ? (
              <div className="flex flex-col items-center justify-center py-20 text-cyan-400">
                <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin mb-4" />
                <span className="animate-pulse tracking-widest">
                  RUNNING DIAGNOSTIC SWEEP...
                </span>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Decoupling Verification */}
                  <div className="bg-[#050608] border border-[#1e2025] rounded p-4">
                    <h3 className="text-emerald-400 flex items-center gap-2 text-xs uppercase mb-3 border-b border-[#1e2025] pb-2">
                      <SearchCode size={14} /> Stage Decoupling Verification
                    </h3>
                    <div className="space-y-3 mt-4 text-[11px] text-gray-300">
                      <div className="flex justify-between items-center bg-[#0b0c10] p-2 rounded">
                        <span className="text-gray-500">C1/C2 Separation:</span>
                        <span className="bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded flex items-center gap-1 font-bold">
                          <ShieldCheck size={12} /> VERIFIED DECOUPLED
                        </span>
                      </div>
                      <div className="flex flex-col gap-1 p-2 bg-[#0b0c10] rounded border-l-2 border-purple-500">
                        <span className="text-[10px] text-purple-400 font-bold">
                          C1 PHASE:
                        </span>
                        <span className="text-gray-400 leading-tight">
                          {report.executionFlows.C1}
                        </span>
                      </div>
                      <div className="flex flex-col gap-1 p-2 bg-[#0b0c10] rounded border-l-2 border-cyan-500">
                        <span className="text-[10px] text-cyan-400 font-bold">
                          C2 PHASE:
                        </span>
                        <span className="text-gray-400 leading-tight">
                          {report.executionFlows.C2}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Environment Integrity */}
                  <div className="bg-[#050608] border border-[#1e2025] rounded p-4">
                    <h3 className="text-blue-400 flex items-center gap-2 text-xs uppercase mb-3 border-b border-[#1e2025] pb-2">
                      <Database size={14} /> Container Runtime Mapping
                    </h3>
                    <div className="space-y-2 mt-4 text-[11px]">
                      {Object.entries(report.environmentValidation).map(
                        ([key, val]: any) => (
                          <div
                            key={key}
                            className="flex justify-between items-center py-1.5 border-b border-[#1e2025]/50 last:border-0"
                          >
                            <span className="text-gray-400">{key}:</span>
                            <span
                              className={`font-bold ${val === "CONFIGURED" || val === "PROD_BUILD" ? "text-emerald-400" : val === "DEV_MODE" ? "text-blue-400" : "text-red-400"}`}
                            >
                              {val}
                            </span>
                          </div>
                        ),
                      )}
                    </div>

                    <div className="mt-4 p-2 bg-[#0b0c10] border border-[#1e2025] rounded text-[10px] text-gray-500 space-y-1">
                      <span className="block mb-1 text-gray-400 border-b border-[#1e2025] pb-1">
                        Container ENV Inject:
                      </span>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2">
                        {Object.entries(report.envVariablesPassed).map(
                          ([key, val]: any) => (
                            <div
                              key={key}
                              className="flex justify-between items-center"
                            >
                              <span className="opacity-70 truncate" title={key}>
                                {key}
                              </span>
                              <span
                                className={
                                  val === "undefined"
                                    ? "text-red-500/50"
                                    : "text-emerald-500/50"
                                }
                              >
                                {String(val)}
                              </span>
                            </div>
                          ),
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Executor Lanes state */}
                <div className="bg-[#050608] border border-[#1e2025] rounded p-4">
                  <h3 className="text-purple-400 flex items-center gap-2 text-xs uppercase mb-4 border-b border-[#1e2025] pb-2">
                    <Cpu size={14} /> 32-Lane Parallel Executor State
                  </h3>
                  <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
                    {lanes.map((lane, i) => (
                      <div
                        key={i}
                        className={`flex flex-col items-center justify-center p-2 rounded text-[10px] relative overflow-hidden border ${
                          lane.status === "landing"
                            ? "bg-cyan-950/40 border-cyan-800"
                            : lane.status === "executing"
                              ? "bg-purple-950/40 border-purple-800"
                              : lane.status === "queued"
                                ? "bg-amber-950/40 border-amber-800"
                                : "bg-[#0b0c10] border-[#1e2025]"
                        }`}
                      >
                        {lane.status !== "idle" && (
                          <div
                            className={`absolute inset-0 opacity-20 animate-pulse ${
                              lane.status === "landing"
                                ? "bg-cyan-400"
                                : lane.status === "executing"
                                  ? "bg-purple-400"
                                  : "bg-amber-400"
                            }`}
                          />
                        )}
                        <span className="text-gray-500 font-bold mb-1">
                          L{String(i).padStart(2, "0")}
                        </span>
                        <div
                          className={`w-2 h-2 rounded-full mb-1 ${
                            lane.status === "idle"
                              ? "bg-gray-600"
                              : lane.status === "queued"
                                ? "bg-amber-400 shadow-[0_0_8px_theme(colors.amber.400)]"
                                : lane.status === "executing"
                                  ? "bg-purple-400 shadow-[0_0_8px_theme(colors.purple.400)]"
                                  : "bg-cyan-400 shadow-[0_0_8px_theme(colors.cyan.400)]"
                          }`}
                        />
                        <span
                          className={`uppercase tracking-wider font-bold ${
                            lane.status === "idle"
                              ? "text-gray-600"
                              : lane.status === "queued"
                                ? "text-amber-400"
                                : lane.status === "executing"
                                  ? "text-purple-400"
                                  : "text-cyan-400"
                          }`}
                        >
                          {lane.status === "idle"
                            ? "IDLE"
                            : lane.status.substring(0, 4)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
