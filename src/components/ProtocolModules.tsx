import React, { useState, useEffect } from "react";
import { Server, Zap, Shield, Waves } from "lucide-react";

export default function ProtocolModules() {
  const [config, setConfig] = useState<any>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => setConfig(data))
      .catch((err) => console.error("Failed to load config:", err));
  }, []);

  const toggleModule = async (key: string, currentValue: boolean) => {
    const newValue = !currentValue;
    setConfig((prev: any) => ({ ...prev, [key]: newValue }));
    
    setSaving(true);
    try {
      await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: newValue }),
      });
    } catch (err) {
      console.error("Failed to save config:", err);
      // Revert on failure
      setConfig((prev: any) => ({ ...prev, [key]: currentValue }));
    }
    setSaving(false);
  };

  const modules = [
    {
      id: "MODULE_BALANCER_ENABLED",
      name: "Balancer Integration",
      description: "Enable Balancer V2 Vault interactions and flash loan capabilities.",
      icon: <Waves className="w-4 h-4 text-cyan-400" />,
      color: "cyan"
    },
    {
      id: "MODULE_CURVE_ENABLED",
      name: "Curve Exchange",
      description: "Enable execution paths through Curve stableswap and crypto pools.",
      icon: <Server className="w-4 h-4 text-purple-400" />,
      color: "purple"
    },
    {
      id: "MODULE_LIQUIDATION_ENABLED",
      name: "Flash Liquidations",
      description: "Enable monitoring and flash-liquidating undercollateralized debt positions.",
      icon: <Shield className="w-4 h-4 text-emerald-400" />,
      color: "emerald"
    },
    {
      id: "MODULE_AAVE_FLASH",
      name: "Aave Flash Loans",
      description: "Enable Aave V3 flash loan sourcing for capital intensive arbitrage.",
      icon: <Zap className="w-4 h-4 text-amber-400" />,
      color: "amber"
    }
  ];

  return (
    <section className="bg-[#050505] rounded-lg border border-[#1e2025] flex flex-col min-h-0 flex-1 min-w-[300px] glass-specular glass-inset">
      <div className="flex px-4 py-2 border-b border-[#1e2025]/60 justify-between items-center bg-[#07090b]">
        <span className="text-[10px] font-mono text-gray-500 font-bold tracking-[0.2em]">PROTOCOL MODULES</span>
        {saving && <span className="text-[9px] text-cyan-500 animate-pulse uppercase tracking-widest">Syncing with Engine...</span>}
      </div>
      <div className="p-4 flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4">
        {modules.map((m) => {
          // Initialize boolean if undefined
          const isEnabled = config[m.id] === true || config[m.id] === "true";
          
          return (
            <div 
              key={m.id}
              className={`p-4 rounded-xl border flex flex-col gap-3 transition-colors ${isEnabled ? 'bg-[#0a0f18] border-cyan-500/30' : 'bg-[#0a0a0c] border-[#1e2025] opacity-60 hover:opacity-100'}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={`p-1.5 rounded-lg bg-${m.color}-500/10 border border-${m.color}-500/20`}>
                    {m.icon}
                  </div>
                  <h3 className={`text-xs font-bold tracking-wider ${isEnabled ? 'text-white' : 'text-gray-400'}`}>
                    {m.name}
                  </h3>
                </div>
                <button
                  onClick={() => toggleModule(m.id, isEnabled)}
                  className={`
                    w-10 h-5 rounded-full relative transition-colors duration-300 focus:outline-none
                    ${isEnabled ? 'bg-cyan-500 text-white' : 'bg-[#1e2025]'}
                  `}
                >
                  <div 
                    className={`
                      w-3.5 h-3.5 rounded-full absolute top-0.5 transition-transform duration-300 flex items-center justify-center
                      ${isEnabled ? 'translate-x-6 bg-white shadow-[0_0_5px_rgba(0,255,255,0.8)]' : 'translate-x-0.5 bg-gray-500'}
                    `}
                  />
                </button>
              </div>
              <p className="text-[10px] text-gray-500 font-mono pr-4">
                {m.description}
              </p>
              <div className="mt-auto pt-2 flex items-center justify-between border-t border-[#1e2025]/50">
                <span className="text-[9px] font-mono tracking-widest text-[#1e2025]">ENV: {m.id}</span>
                <span className={`text-[8px] font-bold tracking-[0.2em] px-2 py-0.5 rounded ${isEnabled ? 'text-cyan-400 bg-cyan-400/10' : 'text-gray-600 bg-gray-900'}`}>
                  {isEnabled ? 'ACTIVE' : 'DISABLED'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
