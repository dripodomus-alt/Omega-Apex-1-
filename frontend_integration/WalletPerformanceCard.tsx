import React, { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Wallet, TrendingUp, DollarSign } from 'lucide-react';

export function WalletPerformanceCard() {
  // Mock data for visualization
  const data = useMemo(() => Array.from({ length: 20 }, (_, i) => ({
    time: i,
    surplus: Math.random() * 100 + 50,
  })), []);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-md h-full">
      <div className="flex items-center gap-2 mb-6">
        <Wallet className="w-5 h-5 text-emerald-400" />
        <h2 className="text-base font-bold text-slate-100">Wallet Performance</h2>
      </div>
      
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-slate-800/50 p-3 rounded-lg">
          <p className="text-xs text-slate-400">Balance</p>
          <p className="text-lg font-bold text-slate-100">$42,305.80</p>
        </div>
        <div className="bg-emerald-950/20 p-3 rounded-lg border border-emerald-900/30">
          <p className="text-xs text-emerald-400">Total Surplus</p>
          <p className="text-lg font-bold text-emerald-400">+$2,450.12</p>
        </div>
      </div>

      <div className="h-[150px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="time" hide />
            <YAxis hide domain={['auto', 'auto']} />
            <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', fontSize: '12px' }} />
            <Area type="monotone" dataKey="surplus" stroke="#10b981" fill="#065f46" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
