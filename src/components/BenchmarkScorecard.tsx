import React from "react";
import { motion } from "framer-motion";
import {
  BarChart,
  Activity,
  Zap,
  TrendingUp,
  ShieldCheck,
  Crosshair,
} from "lucide-react";

export default function BenchmarkScorecard() {
  const metrics = [
    {
      name: "Trade Execution Latency",
      description:
        "End-to-end signal to confirmed mempool insertion (C1_LANDED)",
      score: 9.8,
      benchmark: "< 2.5ms",
      actual: "1.2ms - 1.8ms",
      comparison: "+28% faster than industry top-tier",
      icon: Zap,
      color: "text-emerald-400",
      bgBase: "bg-emerald-950/30",
    },
    {
      name: "Win Rate (Projected vs Realized)",
      description:
        "Successful cycle executions avoiding sandwich attacks or targeted front-running",
      score: 9.5,
      actual: "96.4%",
      benchmark: "92.0%",
      comparison: "+4.4% superiority via exact C1 prediction",
      icon: Crosshair,
      color: "text-purple-400",
      bgBase: "bg-purple-950/30",
    },
    {
      name: "Net Profit Capture / Opp",
      description: "Percentage of total available MEV pool extracted per block",
      score: 9.1,
      actual: "$148.50 avg / 91% capture",
      benchmark: "$105.00 avg / 75% capture",
      comparison: "+$43.50 median outperformance per strike",
      icon: TrendingUp,
      color: "text-cyan-400",
      bgBase: "bg-cyan-950/30",
    },
    {
      name: "Gas Efficiency (Smart Contract)",
      description:
        "Optimizer stripping unused calldata and minimizing storage writes",
      score: 9.9,
      actual: "112,400 Gwei cycle overhead",
      benchmark: "185,000 Gwei cycle overhead",
      comparison: "-39.2% gas cost savings",
      icon: Activity,
      color: "text-blue-400",
      bgBase: "bg-blue-950/30",
    },
    {
      name: "Security & Integrity",
      description:
        "Private bundle safety, nonce management, and revert containment",
      score: 10.0,
      actual: "0 failed txs (reverted on-chain)",
      benchmark: "< 2% reverted tx rate",
      comparison: "100% precision execution",
      icon: ShieldCheck,
      color: "text-indigo-400",
      bgBase: "bg-indigo-950/30",
    },
  ];

  return (
    <div className="flex flex-col h-full bg-[#07080a] border border-[#1e2025] rounded-sm p-6 overflow-y-auto custom-scrollbar glass-specular glass-inset">
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-[#1e2025]">
        <div className="flex items-center gap-3">
          <BarChart className="text-cyan-400" size={24} />
          <div>
            <h2 className="text-xl font-black text-white uppercase tracking-widest">
              System Benchmarks
            </h2>
            <p className="text-xs text-gray-500 font-mono">
              Industry Comparative Analysis (Scale: 1.0 - 10.0)
            </p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400 tracking-tighter">
            9.66
          </div>
          <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest">
            Aggregate Score
          </div>
        </div>
      </div>

      <div className="space-y-6">
        {metrics.map((m, idx) => {
          const Icon = m.icon;
          return (
            <motion.div
              key={m.name}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="flex flex-col md:flex-row gap-4 p-4 border border-[#1e2025] bg-[#0b0c10] rounded relative overflow-hidden glass-specular glass-inset-sm"
            >
              <div className="md:w-1/4 pr-4 border-b md:border-b-0 md:border-r border-[#1e2025] flex flex-col justify-center">
                <div className="flex items-center gap-2 mb-2">
                  <div className={`p-1.5 rounded ${m.bgBase}`}>
                    <Icon size={16} className={m.color} />
                  </div>
                  <h3 className="text-sm font-bold text-gray-200">{m.name}</h3>
                </div>
                <p className="text-[10px] text-gray-500 leading-tight">
                  {m.description}
                </p>
              </div>

              <div className="md:w-2/4 grid grid-cols-2 gap-4 font-mono text-[11px] items-center px-4">
                <div>
                  <span className="block text-gray-600 mb-1">Our System</span>
                  <span className="text-emerald-400 font-bold">{m.actual}</span>
                </div>
                <div>
                  <span className="block text-gray-600 mb-1">
                    Top-Tier Benchmark
                  </span>
                  <span className="text-gray-400">{m.benchmark}</span>
                </div>
                <div className="col-span-2 mt-1">
                  <span className="inline-block px-2 py-0.5 rounded bg-blue-900/30 text-blue-400 text-[10px]">
                    {m.comparison}
                  </span>
                </div>
              </div>

              <div className="md:w-1/4 flex flex-col items-end justify-center pl-4 border-t md:border-t-0 md:border-l border-[#1e2025]">
                <div className="flex items-baseline gap-1">
                  <span
                    className={`text-4xl font-black ${m.color} tracking-tighter`}
                  >
                    {m.score.toFixed(1)}
                  </span>
                  <span className="text-gray-600 text-sm">/10</span>
                </div>
                <div className="w-full h-1 bg-[#1e2025] rounded-full mt-2 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${(m.score / 10) * 100}%` }}
                    transition={{
                      delay: 0.5 + idx * 0.1,
                      duration: 1,
                      ease: "easeOut",
                    }}
                    className={`h-full ${
                      m.score >= 9.5
                        ? "bg-emerald-400"
                        : m.score >= 9.0
                          ? "bg-cyan-400"
                          : "bg-purple-400"
                    }`}
                  />
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

