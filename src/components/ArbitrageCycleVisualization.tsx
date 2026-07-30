import React, { useState, useEffect } from "react";
import {
  Network,
  Database,
  Cpu,
  Search,
  Activity,
  Layers,
  ArrowRight,
  TrendingUp,
} from "lucide-react";

export default function ArbitrageCycleVisualization() {
  const [pipeline, setPipeline] = useState<any[]>([]);

  useEffect(() => {
    const fetchPipeline = () => {
      fetch("/api/execution/pipeline")
        .then((res) => res.json())
        .then((data) => {
          if (data.stages) setPipeline(data.stages);
        })
        .catch(() => {});
    };
    fetchPipeline();
    const interval = setInterval(fetchPipeline, 1000);
    return () => clearInterval(interval);
  }, []);

  const getCount = (name: string) => {
    const stage = pipeline.find((p) => p.name === name);
    return stage ? stage.count : 0;
  };

  const PipelineNode = ({ name, label, icon: Icon, color }: any) => {
    const count = getCount(name);
    return (
      <div className="flex flex-col items-center">
        <div
          className={`w-12 h-12 rounded-full bg-[#0d0e12] border-2 border-[#1e2025] flex items-center justify-center shadow-[0_0_15px_rgba(0,0,0,0.5)] mb-3 relative`}
        >
          <Icon size={14} className={color} />
          {count > 0 && (
            <div className="absolute -top-1 -right-1 flex h-4 w-4">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-[${color.split("-")[1]}]`}
              ></span>
              <span
                className={`relative inline-flex rounded-full h-4 w-4 items-center justify-center text-[7px] text-black font-bold whitespace-nowrap bg-gray-300`}
              >
                {count > 99 ? "99+" : count}
              </span>
            </div>
          )}
        </div>
        <div className="text-center font-mono uppercase">
          <div className="text-[9px] font-bold text-gray-200 tracking-widest leading-tight">
            {label}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <Layers className="text-[#00f5a0]" size={14} />
        <h3 className="font-mono text-xs uppercase tracking-wider text-[#00f5a0] font-bold">
          Execution Strategy Families
        </h3>
      </div>

      {/* Arbitrage Component */}
      <div className="bg-[#090a0d] border border-[#1e2025] rounded-sm p-5 relative flex flex-col glass-specular glass-inset">
        <div className="text-[10px] uppercase font-bold text-cyan-400 mb-4 tracking-widest border-b border-[#1e2025]/60 pb-2">
          Arbitrage Family (C1 & C2)
        </div>

        <div className="absolute top-[40%] left-10 right-10 h-0.5 bg-[#1e2025] -z-10" />

        <div className="grid grid-cols-6 gap-2 w-full relative z-10">
          <PipelineNode
            name="DISCOVERY"
            label="DISCOVERY"
            icon={Search}
            color="text-cyan-400"
          />
          <PipelineNode
            name="C1_PRE_STATE_SIMULATION"
            label="C1 STATE CHECK"
            icon={Cpu}
            color="text-cyan-400"
          />
          <PipelineNode
            name="C1_EXECUTION"
            label="C1 EXECUTION"
            icon={Network}
            color="text-cyan-400"
          />
          <PipelineNode
            name="POST_C1_STATE_UPDATE"
            label="POST-C1 STATE"
            icon={Database}
            color="text-[#b388ff]"
          />
          <PipelineNode
            name="C2_RECOMPUTE_FROM_PAIRED_C1"
            label="C2 RECOMPUTE"
            icon={Cpu}
            color="text-[#b388ff]"
          />
          <PipelineNode
            name="C2_ACTION"
            label="C2 MIRROR/REVERSE"
            icon={TrendingUp}
            color="text-[#b388ff]"
          />
        </div>
      </div>

      {/* Liquidation Component */}
      <div className="bg-[#090a0d] border border-[#1e2025] rounded-sm p-5 relative flex flex-col mt-4 glass-specular glass-inset">
        <div className="text-[10px] uppercase font-bold text-yellow-500 mb-4 tracking-widest border-b border-[#1e2025]/60 pb-2">
          Liquidation Family
        </div>

        <div className="absolute top-[40%] left-10 right-10 h-0.5 bg-[#1e2025] -z-10" />

        <div className="grid grid-cols-5 gap-2 w-full relative z-10">
          <PipelineNode
            name="LIQUIDATION_MONITOR"
            label="LIQ MONITOR"
            icon={Search}
            color="text-yellow-500"
          />
          <PipelineNode
            name="HEALTH_FACTOR_CHECK"
            label="HEALTH CHECK"
            icon={Activity}
            color="text-yellow-500"
          />
          <PipelineNode
            name="COLLATERAL_DEBT_SIMULATION"
            label="COL/DEBT EST"
            icon={Cpu}
            color="text-yellow-500"
          />
          <PipelineNode
            name="LIQUIDATION_PROFIT_CHECK"
            label="PROFIT CHECK"
            icon={Database}
            color="text-yellow-500"
          />
          <PipelineNode
            name="LIQUIDATION_EXECUTION"
            label="LIQ EXECUTION"
            icon={Network}
            color="text-yellow-500"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        {/* Detailed Stages Log */}
        <div className="border border-[#1e2025] bg-[#090a0d] p-3 rounded-sm space-y-3">
          <h4 className="font-mono text-[9px] uppercase text-cyan-500 mb-1 font-bold">
            Raw Pipeline Telemetry
          </h4>
          <div className="space-y-1 pb-3 border-b border-[#1e2025]/60 h-[150px] overflow-y-auto pr-2 scrollbar-thin">
            {pipeline.map((p) => (
              <div
                key={p.name}
                className="flex items-center justify-between font-mono text-[10px]"
              >
                <span className="text-gray-400">{p.name}</span>
                <span className="text-white font-bold">
                  {p.count.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
          <div>
            <h4 className="font-mono text-[9px] uppercase text-yellow-500 mb-1 font-bold">
              Capital Commitment
            </h4>
            <p className="font-mono text-[8px] text-gray-400 uppercase tracking-wide leading-relaxed">
              FLASHLOAN TARGET AMOUNT = TVL VALUE OF THE LOWEST USD EQUIVALENT
              VALUE REGARDING THE SPECIFIC POOLS CHOSEN FOR SWAPS IN THE ACTIVE
              ARBITRAGE OPPORTUNITY. THIS MINIMIZES BORROW COSTS WHILE
              MAXIMIZING LIQUIDITY UTILIZATION THROUGH THE NARROWEST BOTTLENECK.
            </p>
          </div>
        </div>

        {/* Opportunity Trigger log */}
        <div className="border border-[#1e2025] bg-[#090a0d] p-4 rounded-sm flex flex-col">
          <h4 className="font-mono text-[9px] uppercase text-[#b388ff] mb-2 font-bold border-b border-[#1e2025]/60 pb-2">
            Execution Doctrine
          </h4>

          <div className="flex-1 mt-1 overflow-x-auto">
            <table className="w-full text-[8.5px] font-mono text-left whitespace-normal">
              <thead className="text-gray-500">
                <tr>
                  <th className="w-[18%] font-normal uppercase tracking-wider pb-2 pr-2">
                    Execution Family
                  </th>
                  <th className="w-[20%] font-normal uppercase tracking-wider pb-2 pr-2">
                    Dependency
                  </th>
                  <th className="w-[25%] font-normal uppercase tracking-wider pb-2 pr-2">
                    Trigger Condition
                  </th>
                  <th className="w-[37%] font-normal uppercase tracking-wider pb-2">
                    Operational Goal
                  </th>
                </tr>
              </thead>
              <tbody className="space-y-1">
                <tr className="bg-[#1e2025]/30 border border-[#1e2025]">
                  <td className="p-2 text-cyan-400 font-bold uppercase rounded-l-sm">
                    C1 (Primary)
                  </td>
                  <td className="p-2 text-gray-300 border-l border-[#1e2025]/50">
                    Independent
                  </td>
                  <td className="p-2 text-gray-400 border-l border-[#1e2025]/50">
                    Discovery Scan Result
                  </td>
                  <td className="p-2 text-gray-400 leading-relaxed border-l border-[#1e2025]/50 rounded-r-sm">
                    Extract spread from pre-trade state.
                  </td>
                </tr>
                {/* Spacing spacer */}
                <tr>
                  <td colSpan={4} className="h-1"></td>
                </tr>
                <tr className="bg-[#1e2025]/30 border border-[#1e2025]">
                  <td className="p-2 text-[#b388ff] font-bold uppercase rounded-l-sm">
                    C2 (Paired)
                  </td>
                  <td className="p-2 text-gray-300 border-l border-[#1e2025]/50">
                    C1 Required
                  </td>
                  <td className="p-2 text-gray-400 border-l border-[#1e2025]/50">
                    Successful C1 Execution
                  </td>
                  <td className="p-2 text-gray-400 leading-relaxed border-l border-[#1e2025]/50 rounded-r-sm">
                    Recompute/React to post-C1 state mutation.
                  </td>
                </tr>
                <tr>
                  <td colSpan={4} className="h-1"></td>
                </tr>
                <tr className="bg-[#1e2025]/30 border border-[#1e2025]">
                  <td className="p-2 text-yellow-500 font-bold uppercase rounded-l-sm">
                    Liquidation
                  </td>
                  <td className="p-2 text-gray-300 border-l border-[#1e2025]/50">
                    Independent
                  </td>
                  <td className="p-2 text-gray-400 border-l border-[#1e2025]/50">
                    Health Factor &lt; 1
                  </td>
                  <td className="p-2 text-gray-400 leading-relaxed border-l border-[#1e2025]/50 rounded-r-sm">
                    Extract liquidation bonus via debt repayment.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
