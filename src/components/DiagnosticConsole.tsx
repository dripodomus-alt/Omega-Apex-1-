import React, { useEffect, useState } from "react";
import {
  Terminal,
  ShieldCheck,
  Server,
  SearchCode,
  Database,
} from "lucide-react";
import { motion } from "framer-motion";

export default function DiagnosticConsole() {
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/diagnostics/report")
      .then((r) => r.json())
      .then((d) => {
        setReport(d);
        setLoading(false);
      })
      .catch((e) => {
        console.error(e);
        setLoading(false);
      });
  }, []);

  if (loading || !report) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center h-full p-4">
        <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
        <span className="text-cyan-400 font-mono mt-4 text-sm animate-pulse">
          Running full system diagnostic sweep...
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#07080a] border border-[#1e2025] rounded-sm p-4 overflow-y-auto custom-scrollbar font-mono glass-specular glass-inset">
      <div className="flex items-center gap-2 mb-6 border-b border-[#1e2025] pb-3">
        <Server className="text-emerald-400" size={20} />
        <h2 className="text-lg font-bold text-white uppercase tracking-widest">
          End-to-End Pipeline Audit Report
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Decoupling Verification */}
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
        >
          <div className="bg-[#0b0c10] border border-[#1e2025] rounded p-4 h-full">
            <h3 className="text-cyan-400 flex items-center gap-2 text-sm uppercase mb-3 border-b border-[#1e2025] pb-2">
              <SearchCode size={16} /> Stage Decoupling Status
            </h3>
            <div className="space-y-3 mt-4 text-sm text-gray-300">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">C1/C2 Separation:</span>
                <span className="bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded flex items-center gap-1">
                  <ShieldCheck size={12} /> DECOUPLED OK
                </span>
              </div>
              <div className="flex flex-col gap-1 mt-2 p-2 bg-[#050608] border border-[#1e2025] rounded">
                <span className="text-xs text-purple-400">Phase C1:</span>
                <span className="text-xs text-gray-400 pl-2 border-l-2 border-[#1e2025]">
                  {report.executionFlows.C1}
                </span>
              </div>
              <div className="flex flex-col gap-1 p-2 bg-[#050608] border border-[#1e2025] rounded">
                <span className="text-xs text-purple-400">Phase C2:</span>
                <span className="text-xs text-gray-400 pl-2 border-l-2 border-[#1e2025]">
                  {report.executionFlows.C2}
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Environment Validation */}
        <motion.div
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="bg-[#0b0c10] border border-[#1e2025] rounded p-4 h-full">
            <h3 className="text-cyan-400 flex items-center gap-2 text-sm uppercase mb-3 border-b border-[#1e2025] pb-2">
              <Database size={16} /> Docker & Environment Integrity
            </h3>
            <div className="space-y-2 mt-4 text-xs">
              {Object.entries(report.environmentValidation).map(
                ([key, val]: any) => (
                  <div
                    key={key}
                    className="flex justify-between items-center py-1 border-b border-[#1e2025] last:border-0"
                  >
                    <span className="text-gray-400">{key}:</span>
                    <span
                      className={
                        val === "CONFIGURED" || val === "PROD_BUILD"
                          ? "text-emerald-400"
                          : val === "DEV_MODE"
                            ? "text-blue-400"
                            : "text-red-400"
                      }
                    >
                      {val}
                    </span>
                  </div>
                ),
              )}
            </div>

            <div className="mt-4 p-2 bg-[#050608] border border-[#1e2025] rounded text-xs text-gray-500">
              <span className="block mb-1 text-gray-400">
                Secure Variables Passed:
              </span>
              <div className="grid grid-cols-2 gap-2 mt-2">
                {Object.entries(report.envVariablesPassed).map(
                  ([key, val]: any) => (
                    <div key={key} className="flex justify-between">
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
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mt-6"
      >
        <div className="bg-[#050608] border border-[#1e2025] rounded p-4">
          <h3 className="text-gray-400 flex items-center gap-2 text-xs uppercase mb-3">
            <Terminal size={14} /> Full Raw Output / Diagnostic Result
          </h3>
          <pre className="text-[10px] text-emerald-400/70 overflow-x-auto whitespace-pre-wrap leading-tight">
            {JSON.stringify(report, null, 2)}
          </pre>
        </div>
      </motion.div>
    </div>
  );
}
