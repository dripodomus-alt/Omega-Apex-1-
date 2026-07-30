import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, XCircle, AlertTriangle, Info, Zap, X, Copy, Check } from "lucide-react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  message: string;
  timestamp: string;
  durationMs?: number;
  details?: {
    opportunityId?: string;
    netProfitUsd?: number;
    gasCostUsd?: number;
    expectedPnlUsd?: number;
    decision?: string;
    c1StateHash?: string;
    blockNumber?: number;
    route?: string;
    traceHash?: string;
  };
}

interface ToastContextValue {
  toasts: ToastMessage[];
  addToast: (toast: Omit<ToastMessage, "id" | "timestamp">) => string;
  removeToast: (id: string) => void;
  clearAllToasts: () => void;
  notifySimSuccess: (data: {
    opportunityId?: string;
    netProfitUsd: number;
    gasCostUsd?: number;
    expectedPnlUsd?: number;
    decision?: string;
    c1StateHash?: string;
    blockNumber?: number;
    route?: string;
  }) => void;
  notifySimError: (data: {
    opportunityId?: string;
    error: string;
    route?: string;
  }) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearAllToasts = useCallback(() => {
    setToasts([]);
  }, []);

  const addToast = useCallback((toast: Omit<ToastMessage, "id" | "timestamp">): string => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const newToast: ToastMessage = {
      ...toast,
      id,
      timestamp: new Date().toLocaleTimeString(),
      durationMs: toast.durationMs ?? (toast.type === "error" ? 7000 : 5000),
    };

    setToasts((prev) => [newToast, ...prev].slice(0, 6)); // Keep max 6 active toasts

    if (newToast.durationMs && newToast.durationMs > 0) {
      setTimeout(() => {
        removeToast(id);
      }, newToast.durationMs);
    }

    return id;
  }, [removeToast]);

  const notifySimSuccess = useCallback((data: {
    opportunityId?: string;
    netProfitUsd: number;
    gasCostUsd?: number;
    expectedPnlUsd?: number;
    decision?: string;
    c1StateHash?: string;
    blockNumber?: number;
    route?: string;
  }) => {
    addToast({
      type: "success",
      title: `Simulated Transaction Succeeded: ${data.opportunityId || "OPP-ROUTE"}`,
      message: `Net Profit: +$${data.netProfitUsd.toFixed(2)}${data.gasCostUsd ? ` (Gas Deduction: -$${data.gasCostUsd.toFixed(2)})` : ""}`,
      details: {
        opportunityId: data.opportunityId,
        netProfitUsd: data.netProfitUsd,
        gasCostUsd: data.gasCostUsd,
        expectedPnlUsd: data.expectedPnlUsd,
        decision: data.decision || "MIRROR",
        c1StateHash: data.c1StateHash,
        blockNumber: data.blockNumber,
        route: data.route,
      },
      durationMs: 6000,
    });
  }, [addToast]);

  const notifySimError = useCallback((data: {
    opportunityId?: string;
    error: string;
    route?: string;
  }) => {
    addToast({
      type: "error",
      title: `Simulated Transaction Failed: ${data.opportunityId || "OPP-ROUTE"}`,
      message: `Pipeline execution halted: ${data.error}`,
      details: {
        opportunityId: data.opportunityId,
        route: data.route,
      },
      durationMs: 8000,
    });
  }, [addToast]);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <ToastContext.Provider
      value={{
        toasts,
        addToast,
        removeToast,
        clearAllToasts,
        notifySimSuccess,
        notifySimError,
      }}
    >
      {children}

      {/* Floating Toast Container (Top Right Position) */}
      <div className="fixed top-5 right-5 z-[9999] flex flex-col gap-3 max-w-md w-full pointer-events-none px-3">
        {toasts.map((toast) => {
          const isSuccess = toast.type === "success";
          const isError = toast.type === "error";
          const isWarning = toast.type === "warning";

          return (
            <div
              key={toast.id}
              className={`pointer-events-auto relative overflow-hidden rounded-xl p-4 border backdrop-blur-xl shadow-2xl transition-all duration-300 animate-in fade-in slide-in-from-top-4 ${
                isSuccess
                  ? "bg-slate-950/95 border-emerald-500/70 text-emerald-100 shadow-[0_0_25px_rgba(16,185,129,0.25)]"
                  : isError
                  ? "bg-slate-950/95 border-rose-500/70 text-rose-100 shadow-[0_0_25px_rgba(244,63,94,0.25)]"
                  : isWarning
                  ? "bg-slate-950/95 border-amber-500/70 text-amber-100 shadow-[0_0_25px_rgba(245,158,11,0.25)]"
                  : "bg-slate-950/95 border-sky-500/70 text-sky-100 shadow-[0_0_25px_rgba(14,165,233,0.25)]"
              }`}
            >
              {/* Top Accent Glowing Line */}
              <div
                className={`absolute top-0 left-0 right-0 h-1 ${
                  isSuccess
                    ? "bg-gradient-to-r from-emerald-500 via-teal-300 to-emerald-500"
                    : isError
                    ? "bg-gradient-to-r from-rose-500 via-red-300 to-rose-500"
                    : isWarning
                    ? "bg-gradient-to-r from-amber-500 via-yellow-300 to-amber-500"
                    : "bg-gradient-to-r from-sky-500 via-cyan-300 to-sky-500"
                }`}
              />

              {/* Toast Header */}
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`p-1.5 rounded-lg border ${
                      isSuccess
                        ? "bg-emerald-950/90 border-emerald-600 text-emerald-400"
                        : isError
                        ? "bg-rose-950/90 border-rose-600 text-rose-400"
                        : isWarning
                        ? "bg-amber-950/90 border-amber-600 text-amber-400"
                        : "bg-sky-950/90 border-sky-600 text-sky-400"
                    }`}
                  >
                    {isSuccess && <CheckCircle2 className="w-5 h-5 text-emerald-400 animate-pulse" />}
                    {isError && <XCircle className="w-5 h-5 text-rose-400" />}
                    {isWarning && <AlertTriangle className="w-5 h-5 text-amber-400" />}
                    {toast.type === "info" && <Info className="w-5 h-5 text-sky-400" />}
                  </div>

                  <div>
                    <div className="text-xs font-mono font-bold tracking-tight text-slate-100 flex items-center gap-2">
                      <span>{toast.title}</span>
                      <span className="text-[9px] text-slate-400 font-normal">[{toast.timestamp}]</span>
                    </div>
                    <div className="text-xs font-mono mt-0.5 text-slate-200 font-semibold">
                      {toast.message}
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => removeToast(toast.id)}
                  className="text-slate-400 hover:text-slate-100 transition p-1 rounded-lg hover:bg-slate-800/80"
                  title="Dismiss notification"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Toast Detailed Context Block for Simulation Alerts */}
              {toast.details && (
                <div className="mt-3 pt-2.5 border-t border-slate-800/90 text-[10px] font-mono grid grid-cols-2 gap-2 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                  {toast.details.route && (
                    <div className="col-span-2 text-slate-300 truncate">
                      <span className="text-slate-500">Route: </span>
                      <span className="font-bold text-purple-300">{toast.details.route}</span>
                    </div>
                  )}

                  {toast.details.netProfitUsd !== undefined && (
                    <div>
                      <span className="text-slate-500">Net Profit: </span>
                      <span className="font-extrabold text-emerald-400">+${toast.details.netProfitUsd.toFixed(2)}</span>
                    </div>
                  )}

                  {toast.details.gasCostUsd !== undefined && (
                    <div className="text-right">
                      <span className="text-slate-500">Est. Gas: </span>
                      <span className="font-bold text-rose-300">-${toast.details.gasCostUsd.toFixed(2)}</span>
                    </div>
                  )}

                  {toast.details.decision && (
                    <div>
                      <span className="text-slate-500">Decision: </span>
                      <span className="font-bold text-sky-300">{toast.details.decision}</span>
                    </div>
                  )}

                  {toast.details.blockNumber && (
                    <div className="text-right">
                      <span className="text-slate-500">Block #: </span>
                      <span className="font-bold text-slate-300">{toast.details.blockNumber}</span>
                    </div>
                  )}

                  {toast.details.c1StateHash && (
                    <div className="col-span-2 flex items-center justify-between text-[9px] text-slate-400 pt-1 border-t border-slate-800/60 mt-1">
                      <span className="truncate max-w-[280px]">
                        Hash: <code className="text-purple-400 font-mono">{toast.details.c1StateHash}</code>
                      </span>
                      <button
                        onClick={() => copyToClipboard(toast.details?.c1StateHash || "", toast.id)}
                        className="text-slate-400 hover:text-emerald-400 transition flex items-center gap-1 text-[9px] bg-slate-800 px-1.5 py-0.5 rounded"
                      >
                        {copiedId === toast.id ? (
                          <>
                            <Check className="w-2.5 h-2.5 text-emerald-400" />
                            <span>Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-2.5 h-2.5" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
