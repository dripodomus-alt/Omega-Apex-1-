import React from "react";

interface Lane {
  id: number;
  status: string;
  latency_ms: number | null;
  profit_usd: number | null;
}

interface LanesGridProps {
  lanes: Lane[];
}

export default function LanesGrid({ lanes }: LanesGridProps) {
  const [isMinimized, setIsMinimized] = React.useState(true);

  const getDotColor = (status: string) => {
    switch (status) {
      case "idle":
        return "bg-white/10";
      case "queued":
        return "bg-yellow-400 shadow-[0_0_8px_rgba(250,204,21,0.5)] animate-pulse";
      case "simulating":
        return "bg-[#00e5ff] shadow-[0_0_8px_rgba(0,229,255,0.5)] animate-ping";
      case "submitted":
        return "bg-[#00f5a0] shadow-[0_0_8px_rgba(0,245,160,0.5)]";
      case "failed":
        return "bg-[#ff3d57] shadow-[0_0_8px_rgba(255,61,87,0.5)]";
      default:
        return "bg-white/10";
    }
  };

  const getCellBorderAndBg = (status: string) => {
    switch (status) {
      case "simulating":
        return "border-[#00e5ff]/20 bg-[#00e5ff]/5";
      case "submitted":
        return "border-[#00f5a0]/20 bg-[#00f5a0]/5";
      case "failed":
        return "border-[#ff3d57]/20 bg-[#ff3d57]/5";
      default:
        return "border-[#1e2025] bg-white/2 hover:border-white/10";
    }
  };

  if (isMinimized) {
    return (
      <div className="border-t border-[#1e2025] bg-[#040508] shrink-0 font-mono text-[9px] select-none flex items-center px-4 py-1.5 justify-between relative z-20">
        <button
          onClick={() => setIsMinimized(false)}
          className="flex items-center gap-2 hover:opacity-80 transition-opacity"
        >
          <span className="text-gray-500 uppercase tracking-[0.15em] font-bold text-[7.5px]">
            32-LANE PARALLEL EXECUTOR CLUSTERS
          </span>
          <div className="flex gap-0.5 ml-2">
            {lanes.map((lane) => (
              <div
                key={lane.id}
                className={`w-1 h-2 rounded-sm ${getDotColor(lane.status)}`}
                title={`Lane ${lane.id}: ${lane.status}`}
              />
            ))}
          </div>
        </button>
        <div className="flex items-center gap-4 text-gray-500 text-[7.5px] uppercase">
          <span>
            ACTIVE:{" "}
            <span className="text-[#00e5ff] font-bold">
              {lanes.filter((l) => l.status !== "idle").length}/32
            </span>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-28 min-h-[96px] border-t border-[#1e2025] bg-black/40 flex flex-col font-mono text-[9px] shrink-0 select-none relative z-20 glass-specular glass-inset">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#1e2025]/50 shrink-0">
        <span className="text-gray-500 uppercase tracking-[0.15em] font-bold text-[7.5px]">
          32-LANE PARALLEL EXECUTOR CLUSTERS
        </span>
        <div className="flex items-center gap-4 text-gray-500 text-[7.5px] uppercase">
          <span>
            ACTIVE:{" "}
            <span className="text-[#00e5ff] font-bold">
              {lanes.filter((l) => l.status !== "idle").length}/32
            </span>
          </span>
          <span>
            SOLVING:{" "}
            <span className="text-[#00f5a0] font-bold">
              {lanes.filter((l) => l.status === "simulating").length} lanes
            </span>
          </span>
          <button
            onClick={() => setIsMinimized(true)}
            className="ml-2 text-gray-500 hover:text-white px-2 py-0.5 border border-[#1e2025] rounded-sm bg-[#0d0e12]"
          >
            MINIMIZE
          </button>
        </div>
      </div>

      <div className="grid grid-cols-8 sm:grid-cols-16 lg:grid-cols-32 gap-1 px-3 py-2 flex-1 items-center overflow-y-auto">
        {lanes.map((lane) => (
          <div
            key={lane.id}
            className={`flex flex-col items-center justify-center border rounded-sm p-1 gap-1 transition-all duration-300 glass-specular glass-inset-sm ${getCellBorderAndBg(
              lane.status,
            )}`}
            title={`Lane ${lane.id}: ${lane.status === "simulating" ? "SOLVING" : lane.status.toUpperCase()}${
              lane.profit_usd ? ` (Solved +$${lane.profit_usd})` : ""
            }`}
          >
            <span className="text-gray-500 text-[6.5px] leading-none shrink-0 font-bold">
              {lane.id.toString().padStart(2, "0")}
            </span>
            <div
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${getDotColor(lane.status)}`}
            />
            <span className="text-[6px] text-gray-400 font-medium leading-none min-h-[7px] shrink-0">
              {lane.latency_ms ? `${lane.latency_ms}ms` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
