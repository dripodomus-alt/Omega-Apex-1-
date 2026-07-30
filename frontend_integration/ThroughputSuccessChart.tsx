import React, { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Zap, Activity } from 'lucide-react';

export function ThroughputSuccessChart({ omega }: { omega: any }) {
  // Simulating real-time throughput/success data
  const chartData = useMemo(() => {
    const data = [];
    const now = Date.now();
    for (let i = 15; i >= 0; i--) {
      const time = new Date(now - i * 5000);
      data.push({
        time: time.toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }),
        throughput: Math.floor(Math.random() * 20 + 30),
        successRate: Math.floor(Math.random() * 15 + 85),
      });
    }
    return data;
  }, []);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-md flex flex-col h-full">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="w-5 h-5 text-sky-400" />
        <h2 className="text-base font-bold text-slate-100">Engine Performance: Throughput & Success</h2>
      </div>

      <div className="flex-1 w-full h-[250px] min-h-[250px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="time" stroke="#475569" fontSize={10} />
            <YAxis yAxisId="left" stroke="#38bdf8" fontSize={10} />
            <YAxis yAxisId="right" orientation="right" stroke="#34d399" fontSize={10} domain={[0, 100]} />
            <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', fontSize: '12px' }} />
            <Legend wrapperStyle={{ fontSize: '11px' }} />
            <Line yAxisId="left" type="monotone" dataKey="throughput" stroke="#38bdf8" name="Throughput (tx/s)" strokeWidth={2} dot={false} />
            <Line yAxisId="right" type="monotone" dataKey="successRate" stroke="#34d399" name="Success Rate (%)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
