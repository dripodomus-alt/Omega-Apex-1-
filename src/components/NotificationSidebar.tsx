import React, { useState, useEffect } from "react";
import { useWebSocketWithBackoff } from "../hooks/useWebSocketWithBackoff";
import {
  Bell,
  Zap,
  CheckCircle2,
  History,
  BellOff,
  ArrowDownToLine,
  ArrowUpToLine,
} from "lucide-react";
import ExecutionModal from "./ExecutionModal";

interface ArbAlert {
  id: string;
  profit: number;
  path: string;
  dex: string;
  timestamp: string;
}

export default function NotificationSidebar() {
  const [alerts, setAlerts] = useState<ArbAlert[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [selectedAlert, setSelectedAlert] = useState<ArbAlert | null>(null);

  // We connect to the unified oracle stream that also pushes alerts
  const wsProtocol =
    typeof window !== "undefined" && window.location.protocol === "https:"
      ? "wss:"
      : "ws:";
  const wsUrl =
    typeof window !== "undefined"
      ? `${wsProtocol}//${window.location.host}/api/oracle-stream`
      : "ws://localhost/api/oracle-stream";

  const { lastMessage } = useWebSocketWithBackoff(wsUrl);

  useEffect(() => {
    if (
      alertsEnabled &&
      lastMessage &&
      lastMessage.type === "arbitrage_alert"
    ) {
      const alert = lastMessage.data as ArbAlert;
      setAlerts((prev) => {
        if (prev.some((a) => a.id === alert.id)) return prev;
        const newAlerts = [alert, ...prev];
        // Keep only last 20 alerts
        return newAlerts.slice(0, 20);
      });
      // Optionally auto-open the sidebar when a high-value alert comes in
      if (!isOpen) {
        setIsOpen(true);
      }
    }
  }, [lastMessage, alertsEnabled, isOpen]);

  const toggleSidebar = () => setIsOpen(!isOpen);

  if (!isOpen) {
    return (
      <button
        onClick={toggleSidebar}
        className="fixed bottom-0 right-4 bg-[#0d0e12] border border-b-0 border-[#1e2025] px-4 py-2 rounded-t-sm shadow-lg text-gray-400 hover:text-white transition-colors cursor-pointer z-50 flex items-center gap-2 group"
      >
        {alertsEnabled ? (
          <Bell size={16} className="group-hover:animate-pulse" />
        ) : (
          <BellOff size={16} className="text-gray-600" />
        )}
        <span className="text-[10px] uppercase font-bold tracking-widest font-mono">
          Alerts
        </span>
        {alerts.length > 0 && (
          <span className="text-[9px] bg-emerald-500/20 text-emerald-400 px-1.5 rounded-full font-bold ml-1">
            {alerts.length}
          </span>
        )}
      </button>
    );
  }

  return (
    <>
      <div className="fixed left-0 right-0 bottom-0 h-[220px] bg-[#07080a]/95 backdrop-blur-sm border-t border-[#1e2025] shadow-[inset_0_1px_0_rgba(255,255,255,0.07),inset_0_0_32px_rgba(0,0,0,0.38),0_-4px_32px_rgba(0,0,0,0.6)] glass-specular z-50 flex flex-col transform transition-transform duration-300">
        <div className="px-4 py-2 border-b border-[#1e2025] flex items-center justify-between bg-[#0d0e12]">
          <div className="flex items-center gap-3">
            <Zap size={16} className="text-emerald-400" />
            <h2 className="text-xs font-semibold tracking-wider text-white">
              OPPORTUNITY FEED
            </h2>

            <div className="w-px h-4 bg-[#1e2025] mx-2"></div>

            <label className="flex items-center gap-2 cursor-pointer">
              <div className="relative">
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={alertsEnabled}
                  onChange={() => setAlertsEnabled(!alertsEnabled)}
                />
                <div
                  className={`block w-8 h-4 rounded-full transition-colors ${alertsEnabled ? "bg-emerald-500/50" : "bg-[#1e2025]"}`}
                ></div>
                <div
                  className={`dot absolute left-1 top-1 bg-white w-2 h-2 rounded-full transition-transform ${alertsEnabled ? "transform translate-x-4" : ""}`}
                ></div>
              </div>
              <span className="text-[9px] text-gray-400 font-mono uppercase">
                {alertsEnabled ? "ALERTS ON" : "ALERTS OFF"}
              </span>
            </label>
          </div>

          <button
            onClick={toggleSidebar}
            className="text-gray-500 hover:text-white flex items-center gap-1 text-[9px] font-mono tracking-widest uppercase"
          >
            <span>Minimize</span>
            <ArrowDownToLine size={12} />
          </button>
        </div>

        <div className="flex-1 overflow-x-auto overflow-y-hidden p-3 flex gap-3 custom-scrollbar items-center">
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center w-full text-gray-500 h-full text-center gap-2">
              {alertsEnabled ? (
                <>
                  <History size={24} className="opacity-20 mx-auto" />
                  <p className="text-[10px] uppercase tracking-widest font-mono">
                    No opportunities
                    <br />
                    detected yet
                  </p>
                </>
              ) : (
                <>
                  <BellOff size={24} className="opacity-20 mx-auto" />
                  <p className="text-[10px] uppercase tracking-widest font-mono">
                    Alerts disabled
                  </p>
                </>
              )}
            </div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.id}
                onClick={() => setSelectedAlert(alert)}
                className="shrink-0 w-[240px] h-full bg-[#0d0e12]/80 border border-[#1e2025] rounded-sm p-3 hover:border-emerald-500/30 transition-colors relative overflow-hidden group cursor-pointer flex flex-col justify-between"
              >
                <div className="absolute top-0 right-0 p-2">
                  <CheckCircle2
                    size={12}
                    className="text-emerald-500 opacity-50"
                  />
                </div>

                <div>
                  <div className="text-[9px] text-gray-500 font-mono mb-2">
                    {new Date(alert.timestamp).toLocaleTimeString()}
                  </div>
                  <div className="flex items-end gap-1 mb-2">
                    <span className="text-emerald-400 font-mono text-lg font-bold leading-none">
                      ${alert.profit.toFixed(2)}
                    </span>
                    <span className="text-[8px] text-gray-400 uppercase tracking-wider mb-0.5">
                      PROFIT EXP.
                    </span>
                  </div>
                </div>

                <div>
                  <div
                    className="text-[10px] text-gray-300 font-mono mb-1.5 truncate"
                    title={alert.path}
                  >
                    {alert.path}
                  </div>
                  <div className="text-[8px] bg-[#1e2025]/50 inline-block px-1.5 py-0.5 rounded-sm text-indigo-300 border border-[#1e2025]">
                    {alert.dex}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
      <ExecutionModal
        alert={selectedAlert}
        onClose={() => setSelectedAlert(null)}
      />
    </>
  );
}
