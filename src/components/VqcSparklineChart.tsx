import React from 'react';
import { ResponsiveContainer, LineChart, Line, YAxis, Tooltip } from 'recharts';

interface VqcSparklineChartProps {
  score: number;
  history?: number[];
}

export const VqcSparklineChart: React.FC<VqcSparklineChartProps> = ({
  score,
  history,
}) => {
  // Derive 5 simulation cycle points if explicit history is missing
  const rawHistory =
    history && history.length >= 5
      ? history.slice(-5)
      : [
          Math.max(0.5, score - 0.038),
          Math.max(0.5, score - 0.015),
          Math.max(0.5, score + 0.018),
          Math.max(0.5, score - 0.008),
          score,
        ];

  const chartData = rawHistory.map((val, idx) => ({
    cycle: `Cycle C-${4 - idx}`,
    alpha: Number((val * 100).toFixed(1)),
  }));

  const startVal = rawHistory[0];
  const endVal = rawHistory[rawHistory.length - 1];
  const diffPct = ((endVal - startVal) * 100).toFixed(1);
  const isUp = endVal >= startVal;

  return (
    <div className="flex items-center gap-2 bg-slate-950/90 p-2 rounded-lg border border-purple-900/60 shadow-inner">
      <div className="space-y-0.5 shrink-0">
        <div className="text-[10px] text-purple-300 font-mono font-bold uppercase flex items-center gap-1">
          <span>VQC Trend</span>
          <span
            className={`text-[9px] px-1 rounded font-bold ${
              isUp ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-rose-950 text-rose-300 border border-rose-800'
            }`}
          >
            {isUp ? '+' : ''}
            {diffPct}%
          </span>
        </div>
        <div className="text-xs font-mono font-bold text-white flex items-baseline gap-1">
          <span>{(score * 100).toFixed(1)}%</span>
          <span className="text-[9px] text-slate-400 font-normal">(5 cycles)</span>
        </div>
      </div>

      <div className="w-28 h-8 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
            <YAxis domain={['dataMin - 1', 'dataMax + 1']} hide />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="bg-slate-900 border border-purple-700 text-purple-200 text-[10px] px-2 py-1 rounded font-mono shadow-xl">
                      <div>
                        {payload[0].payload.cycle}: <strong className="text-white">{payload[0].value}%</strong>
                      </div>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Line
              type="monotone"
              dataKey="alpha"
              stroke="#c084fc"
              strokeWidth={2}
              dot={{ r: 1.5, fill: '#e9d5ff' }}
              activeDot={{ r: 3.5, fill: '#f472b6' }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
