import React, { useState } from 'react';
import { Settings, ToggleLeft, ToggleRight } from 'lucide-react';

export function EngineControlPanel() {
  const [gasPriority, setGasPriority] = useState(30);
  const [slippage, setSlippage] = useState(0.5);
  const [modules, setModules] = useState({
    aave: true,
    balancer: true,
    quickswap: false,
  });

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-md h-full">
      <div className="flex items-center gap-2 mb-6">
        <Settings className="w-5 h-5 text-amber-400" />
        <h2 className="text-base font-bold text-slate-100">Engine Tuning</h2>
      </div>

      <div className="space-y-6">
        <div>
          <label className="text-xs text-slate-400 block mb-2">Gas Priority (Gwei): {gasPriority}</label>
          <input type="range" min="1" max="100" value={gasPriority} onChange={e => setGasPriority(Number(e.target.value))} className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500" />
        </div>
        
        <div>
          <label className="text-xs text-slate-400 block mb-2">Target Slippage: {slippage}%</label>
          <input type="range" min="0.1" max="5" step="0.1" value={slippage} onChange={e => setSlippage(Number(e.target.value))} className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500" />
        </div>

        <div>
          <p className="text-xs text-slate-400 mb-3">Active Modules</p>
          <div className="space-y-2">
            {Object.entries(modules).map(([key, enabled]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-sm text-slate-200 capitalize">{key}</span>
                <button onClick={() => setModules(prev => ({ ...prev, [key]: !enabled }))}>
                  {enabled ? <ToggleRight className="w-6 h-6 text-emerald-500" /> : <ToggleLeft className="w-6 h-6 text-slate-600" />}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
