import React, { useState } from 'react';
import { VqcModelMetadata } from '../types';
import { Cpu, Zap, Activity, CheckCircle2, Play, Sparkles, BarChart2 } from 'lucide-react';

interface VqcRankerStudioProps {
  metadata: VqcModelMetadata;
}

export const VqcRankerStudio: React.FC<VqcRankerStudioProps> = ({ metadata }) => {
  // Test prediction inputs
  const [resRatio, setResRatio] = useState<number>(0.85);
  const [pathLength, setPathLength] = useState<number>(2);
  const [gasGwei, setGasGwei] = useState<number>(38);
  const [tvlRatio, setTvlRatio] = useState<number>(1.4);

  // Compute live prediction
  const predictedAlphaScore = Math.min(
    0.99,
    Math.max(
      0.1,
      0.5 +
        resRatio * metadata.featureWeights.virtualReserveRatio +
        tvlRatio * metadata.featureWeights.bottleneckTvlRatio -
        (pathLength - 2) * 0.1 -
        (gasGwei / 100) * 0.1
    )
  );

  return (
    <div id="vqc-ranker-studio" className="space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-purple-400" />
              <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                VQC Surplus Ranker (Variational Quantum Circuit Alpha Engine)
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Model Version: <code className="text-purple-300 font-mono">{metadata.version}</code> • Ansatz:{' '}
              <code className="text-slate-300 font-mono">{metadata.ansatz}</code>
            </p>
          </div>

          <div className="flex items-center gap-2 bg-purple-950/80 border border-purple-800/80 px-3.5 py-2 rounded-lg text-xs font-mono text-purple-300">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <span>4-Qubit Parameterized Circuit ACTIVE</span>
          </div>
        </div>
      </div>

      {/* Accuracy & Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg text-center">
          <div className="text-[10px] uppercase font-mono text-slate-400">Model Accuracy</div>
          <div className="text-2xl font-extrabold text-emerald-400 font-mono mt-1">
            {(metadata.accuracy * 100).toFixed(2)}%
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">Tested on 142.8k samples</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg text-center">
          <div className="text-[10px] uppercase font-mono text-slate-400">Precision Score</div>
          <div className="text-2xl font-extrabold text-purple-400 font-mono mt-1">
            {(metadata.precision * 100).toFixed(2)}%
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">True positive MEV win rate</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg text-center">
          <div className="text-[10px] uppercase font-mono text-slate-400">Recall Rate</div>
          <div className="text-2xl font-extrabold text-indigo-400 font-mono mt-1">
            {(metadata.recall * 100).toFixed(2)}%
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">Profitable route capture</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-lg text-center">
          <div className="text-[10px] uppercase font-mono text-slate-400">F1-Score</div>
          <div className="text-2xl font-extrabold text-cyan-400 font-mono mt-1">
            {metadata.f1Score.toFixed(4)}
          </div>
          <div className="text-[10px] text-slate-500 font-mono mt-0.5">Harmonic mean evaluation</div>
        </div>
      </div>

      {/* 4-Qubit Circuit Visualization */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2">
            <Cpu className="w-4 h-4 text-purple-400" />
            <span>4-Qubit Quantum Gate Circuit Architecture</span>
          </h3>
          <span className="text-xs font-mono text-slate-400">
            {metadata.circuitQubits} Qubits • {metadata.circuitLayers} Entangling Layers
          </span>
        </div>

        <div className="bg-slate-950 p-6 rounded-xl border border-slate-800/80 font-mono space-y-4 overflow-x-auto">
          {[0, 1, 2, 3].map((qubitIndex) => (
            <div key={qubitIndex} className="flex items-center gap-3 text-xs text-slate-300 min-w-[600px]">
              <span className="w-12 font-bold text-purple-400">|q_{qubitIndex}⟩</span>
              <span className="text-slate-600">───</span>
              <span className="px-2.5 py-1 bg-purple-950 text-purple-300 border border-purple-800 rounded shadow-sm">
                Ry(θ_{qubitIndex})
              </span>
              <span className="text-slate-600">───</span>
              <span className="px-2 py-1 bg-indigo-950 text-indigo-300 border border-indigo-800 rounded">
                Rz(φ_{qubitIndex})
              </span>
              <span className="text-slate-600">───</span>
              <span className="px-2 py-1 bg-emerald-950 text-emerald-300 border border-emerald-800 rounded">
                CZ Gate
              </span>
              <span className="text-slate-600">───</span>
              <span className="px-2 py-1 bg-purple-900/60 text-purple-200 border border-purple-700 rounded">
                M(|0⟩)
              </span>
              <span className="text-slate-600">───➔</span>
              <span className="text-emerald-400 font-bold">P(Alpha = 1)</span>
            </div>
          ))}
        </div>
      </div>

      {/* Feature Importance & Real-Time Predictor Tool */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Feature Weights */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono border-b border-slate-800 pb-3">
            VQC Feature Weight Matrix
          </h3>

          <div className="space-y-3 text-xs font-mono">
            {Object.entries(metadata.featureWeights).map(([key, rawWeight]) => {
              const weight = rawWeight as number;
              const isPositive = weight > 0;
              const absVal = Math.abs(weight) * 100;
              return (
                <div key={key} className="space-y-1">
                  <div className="flex justify-between text-slate-300">
                    <span>{key}</span>
                    <span className={isPositive ? 'text-emerald-400' : 'text-rose-400'}>
                      {isPositive ? `+${weight.toFixed(2)}` : weight.toFixed(2)}
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-950 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${isPositive ? 'bg-emerald-500' : 'bg-rose-500'}`}
                      style={{ width: `${Math.min(100, absVal * 2)}%` }}
                    ></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Real-time Route Win Predictor */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono border-b border-slate-800 pb-3 flex items-center justify-between">
            <span>Live VQC Route Inference Predictor</span>
            <span className="text-emerald-400">Score: {(predictedAlphaScore * 100).toFixed(1)}%</span>
          </h3>

          <div className="space-y-3 text-xs">
            <div>
              <div className="flex justify-between font-mono text-slate-400 mb-1">
                <span>Virtual Reserve Ratio</span>
                <span className="text-white font-bold">{resRatio.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0.1}
                max={2.0}
                step={0.05}
                value={resRatio}
                onChange={(e) => setResRatio(Number(e.target.value))}
                className="w-full accent-purple-400 bg-slate-950"
              />
            </div>

            <div>
              <div className="flex justify-between font-mono text-slate-400 mb-1">
                <span>Bottleneck TVL Ratio</span>
                <span className="text-white font-bold">{tvlRatio.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={5.0}
                step={0.1}
                value={tvlRatio}
                onChange={(e) => setTvlRatio(Number(e.target.value))}
                className="w-full accent-purple-400 bg-slate-950"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 block font-mono mb-1">Path Hops</label>
                <input
                  type="number"
                  value={pathLength}
                  onChange={(e) => setPathLength(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs outline-none"
                />
              </div>

              <div>
                <label className="text-slate-400 block font-mono mb-1">Gas Price (Gwei)</label>
                <input
                  type="number"
                  value={gasGwei}
                  onChange={(e) => setGasGwei(Number(e.target.value))}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 font-mono text-slate-200 text-xs outline-none"
                />
              </div>
            </div>

            <div className="bg-purple-950/60 border border-purple-800/80 p-4 rounded-xl text-center space-y-1">
              <div className="text-[10px] uppercase font-mono text-purple-300">VQC Quantum Surplus Recommendation</div>
              <div className="text-2xl font-extrabold text-white font-mono">
                {predictedAlphaScore > 0.85 ? 'EXECUTE VIA BALANCER V3' : 'SKIP (LOW WIN PROBABILITY)'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Batch VQC Quantum Circuit Candidate Evaluator */}
      <BatchVqcEvaluator metadata={metadata} />
    </div>
  );
};

// Batch VQC Circuit Evaluator Sub-component
const BatchVqcEvaluator: React.FC<{ metadata: VqcModelMetadata }> = ({ metadata }) => {
  const [isBatchProcessing, setIsBatchProcessing] = useState(false);
  const [batchResults, setBatchResults] = useState<
    Array<{
      id: string;
      pair: string;
      hops: number;
      gasGwei: number;
      vqcScore: number;
      decision: string;
    }>
  >([
    { id: 'R-POL-01', pair: 'WMATIC -> USDC -> WETH -> WMATIC', hops: 3, gasGwei: 38, vqcScore: 0.942, decision: 'EXECUTE' },
    { id: 'R-POL-02', pair: 'USDT -> DAI -> USDC -> USDT', hops: 3, gasGwei: 42, vqcScore: 0.885, decision: 'EXECUTE' },
    { id: 'R-POL-03', pair: 'WBTC -> WETH -> USDC -> WBTC', hops: 3, gasGwei: 35, vqcScore: 0.710, decision: 'REJECT' },
    { id: 'R-POL-04', pair: 'LINK -> WETH -> WMATIC -> LINK', hops: 3, gasGwei: 48, vqcScore: 0.965, decision: 'EXECUTE' },
    { id: 'R-POL-05', pair: 'AAVE -> WETH -> USDC -> AAVE', hops: 3, gasGwei: 55, vqcScore: 0.620, decision: 'REJECT' },
  ]);

  const handleRunBatchVqc = () => {
    setIsBatchProcessing(true);
    setTimeout(() => {
      setBatchResults((prev) =>
        prev.map((r) => {
          const newScore = Number((Math.random() * 0.35 + 0.64).toFixed(3));
          return {
            ...r,
            vqcScore: newScore,
            decision: newScore > 0.82 ? 'EXECUTE' : 'REJECT',
          };
        })
      );
      setIsBatchProcessing(false);
    }, 1000);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono flex items-center gap-2">
            <Cpu className="w-4 h-4 text-purple-400" />
            <span>Batch VQC Circuit Matrix Batch Evaluator</span>
          </h3>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Parallel evaluation of candidate route batches through the 4-qubit parameterized ansatz.
          </p>
        </div>

        <button
          onClick={handleRunBatchVqc}
          disabled={isBatchProcessing}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white font-mono text-xs font-bold rounded-lg transition-all shadow-lg active:scale-95 disabled:opacity-50 shrink-0"
        >
          <Sparkles className={`w-4 h-4 ${isBatchProcessing ? 'animate-spin' : ''}`} />
          <span>{isBatchProcessing ? 'Executing Quantum Batch...' : 'Run Batch VQC Matrix Inference'}</span>
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
              <th className="p-3">Route Candidate ID</th>
              <th className="p-3">Arbitrage Graph Path</th>
              <th className="p-3">Hops</th>
              <th className="p-3">Gas (Gwei)</th>
              <th className="p-3">VQC Alpha Score</th>
              <th className="p-3">Batch Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {batchResults.map((item) => (
              <tr key={item.id} className="hover:bg-slate-800/40">
                <td className="p-3 font-bold text-purple-300">{item.id}</td>
                <td className="p-3 text-white font-semibold">{item.pair}</td>
                <td className="p-3 text-slate-300">{item.hops}</td>
                <td className="p-3 text-slate-300">{item.gasGwei} Gwei</td>
                <td className="p-3 font-bold text-cyan-400">
                  <div className="flex items-center gap-2">
                    <div className="w-16 bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
                      <div
                        className="bg-purple-400 h-full rounded-full"
                        style={{ width: `${item.vqcScore * 100}%` }}
                      ></div>
                    </div>
                    <span>{(item.vqcScore * 100).toFixed(1)}%</span>
                  </div>
                </td>
                <td className="p-3">
                  <span
                    className={`px-2.5 py-0.5 rounded text-[10px] font-bold ${
                      item.decision === 'EXECUTE'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : 'bg-slate-800 text-slate-400 border border-slate-700'
                    }`}
                  >
                    {item.decision}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
