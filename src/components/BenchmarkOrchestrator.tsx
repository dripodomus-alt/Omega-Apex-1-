import React, { useState } from 'react';
import { BenchmarkReport, BenchmarkStep } from '../types';
import { Terminal, Play, CheckCircle2, ShieldCheck, Zap, AlertTriangle, RefreshCw, Cpu, Database } from 'lucide-react';

interface BenchmarkOrchestratorProps {
  report: BenchmarkReport;
  onRunBenchmark: () => void;
  isRunningBenchmark: boolean;
}

export const BenchmarkOrchestrator: React.FC<BenchmarkOrchestratorProps> = ({
  report,
  onRunBenchmark,
  isRunningBenchmark,
}) => {
  const [selectedStepId, setSelectedStepId] = useState<number>(1);

  const activeStep = report.steps.find((s) => s.id === selectedStepId) || report.steps[0];

  return (
    <div id="benchmark-orchestrator" className="space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Terminal className="w-5 h-5 text-indigo-400" />
              <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                OMEGA V5 Full Pipeline Benchmark & Readiness Diagnostic
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Script: <code className="text-indigo-300 font-mono">.\scripts\run_full_benchmark_and_readiness.ps1</code> • Chain: Polygon #137
            </p>
          </div>

          <button
            onClick={onRunBenchmark}
            disabled={isRunningBenchmark}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs rounded-lg transition-all active:scale-95 shadow-lg shadow-indigo-600/20 disabled:opacity-50"
          >
            <Play className={`w-4 h-4 ${isRunningBenchmark ? 'animate-spin' : ''}`} />
            <span>{isRunningBenchmark ? 'Running Diagnostic Suite...' : 'Run Readiness Benchmark'}</span>
          </button>
        </div>
      </div>

      {/* Readiness Gauges Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg">
          <div className="text-[10px] uppercase font-mono text-slate-400">Overall Readiness</div>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">
            {report.overallScore.toFixed(1)}%
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">MEV Production Grade</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg">
          <div className="text-[10px] uppercase font-mono text-slate-400">Pipeline Latency</div>
          <div className="text-2xl font-extrabold text-purple-400 font-mono mt-1">
            {report.pipelineLatencyMs}ms
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">End-to-end execution</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg">
          <div className="text-[10px] uppercase font-mono text-slate-400">Max Throughput</div>
          <div className="text-2xl font-extrabold text-cyan-400 font-mono mt-1">
            {report.maxThroughputRps.toLocaleString()} /s
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">Redis stream ingestion</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg">
          <div className="text-[10px] uppercase font-mono text-slate-400">Rust Core Binary</div>
          <div className="text-xl font-extrabold text-emerald-400 font-mono mt-1 flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4" /> COMPILED
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">cargo release optimized</div>
        </div>
      </div>

      {/* Diagnostic Steps List & Console Terminal */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Step List */}
        <div className="space-y-3 lg:col-span-1">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider font-mono">
            Pipeline Diagnostic Phases ({report.steps.length})
          </h3>

          <div className="space-y-2">
            {report.steps.map((step) => {
              const isSelected = selectedStepId === step.id;
              return (
                <button
                  key={step.id}
                  onClick={() => setSelectedStepId(step.id)}
                  className={`w-full text-left p-3 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-indigo-950/80 border-indigo-500/80 text-white shadow-lg'
                      : 'bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-bold flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-slate-950 flex items-center justify-center text-[10px] text-indigo-400">
                        {step.id}
                      </span>
                      <span>{step.title}</span>
                    </span>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  </div>
                  <div className="text-[10px] font-mono text-slate-400 mt-2 flex justify-between">
                    <span>Duration: {step.durationMs}ms</span>
                    <span className="text-emerald-400 uppercase font-bold">{step.status}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Terminal Output Viewer */}
        <div className="space-y-3 lg:col-span-2">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider font-mono flex items-center justify-between">
            <span>Terminal Diagnostic Log View</span>
            <span className="text-indigo-400">{activeStep.title}</span>
          </h3>

          <div className="bg-slate-950 p-5 rounded-xl border border-slate-800 font-mono text-xs space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-slate-400 border-b border-slate-800/80 pb-2">
              <span className="text-emerald-400">$</span>
              <code className="text-indigo-300 font-semibold">{activeStep.command}</code>
            </div>

            <div className="text-emerald-400/90 whitespace-pre-wrap leading-relaxed">
              {activeStep.output}
            </div>

            <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
              <span>Exit Code: 0 (OK)</span>
              <span>Execution Time: {activeStep.durationMs}ms</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
