import { useEffect, useState } from "react";
import { collection, query, orderBy, limit, getDocs, where } from "firebase/firestore";
import { db, auth } from "../lib/firebase.ts";
import { handleFirestoreError, OperationType } from "../lib/firebaseError.ts";
import { Play, Database, DollarSign, Calendar, Cpu, Layers } from "lucide-react";

interface SimulationRecord {
  id: string;
  operatorId: string;
  opportunityId: string;
  netProfitUsd: number;
  gasCostUsd: number;
  decision: string;
  c1StateHash: string;
  timestamp: string;
}

export function SimulationsHistory() {
  const [logs, setLogs] = useState<SimulationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = async () => {
    const user = auth.currentUser;
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const q = query(
        collection(db, "simulations"),
        where("operatorId", "==", user.uid),
        orderBy("timestamp", "desc"),
        limit(50)
      );

      const querySnapshot = await getDocs(q);
      const records: SimulationRecord[] = [];
      querySnapshot.forEach((doc) => {
        records.push(doc.data() as SimulationRecord);
      });
      setLogs(records);
    } catch (err) {
      console.error("Error fetching simulation logs:", err);
      try {
        handleFirestoreError(err, OperationType.LIST, "simulations");
      } catch (wrappedErr: any) {
        setError(wrappedErr.message || String(err));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const formatMoney = (val: number) => {
    return val.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    });
  };

  const formatDate = (isoStr: string) => {
    try {
      return new Date(isoStr).toLocaleString();
    } catch {
      return isoStr;
    }
  };

  return (
    <div className="bg-[#111622]/95 border border-slate-800/80 rounded-xl p-6 shadow-xl backdrop-blur-md relative overflow-hidden font-mono text-slate-200">
      <div className="absolute -top-24 -left-24 w-48 h-48 rounded-full bg-cyan-500/5 blur-[80px]" />
      
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-sm font-bold tracking-widest text-slate-100 flex items-center gap-2">
            <Database className="w-4 h-4 text-cyan-400" />
            FIRESTORE SIMULATION HISTORY
          </h2>
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">
            Audit logs of transaction simulations executed by the active session
          </span>
        </div>
        <button
          onClick={fetchLogs}
          className="text-[10px] border border-cyan-500/30 hover:border-cyan-400 bg-cyan-950/20 hover:bg-cyan-950/40 text-cyan-400 hover:text-white px-3 py-1.5 rounded transition duration-200 active:scale-95"
        >
          REFRESH HISTORY
        </button>
      </div>

      {loading ? (
        <div className="py-12 flex flex-col items-center justify-center text-slate-400 text-xs">
          <Cpu className="w-8 h-8 text-cyan-400 animate-spin mb-3" />
          RETRIEVING ENCRYPTED AUDIT TRAILS...
        </div>
      ) : error ? (
        <div className="border border-red-500/30 bg-red-950/15 text-red-400 p-4 rounded-lg text-xs leading-relaxed max-w-full overflow-x-auto">
          <span className="font-bold text-red-300 block mb-1">DURABLE STORAGE EXCEPTION</span>
          {error}
        </div>
      ) : logs.length === 0 ? (
        <div className="py-12 border border-dashed border-slate-800/80 rounded-xl text-center text-xs text-slate-500">
          <Layers className="w-8 h-8 text-slate-700 mx-auto mb-3" />
          NO SIMULATION LOGS FOUND FOR THIS OPERATOR IN THE DATABASE.
          <p className="text-[10px] text-slate-600 mt-1 uppercase">
            Run a simulation on any 3D Opportunity Card to record the first persistent log entry.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="pb-3 font-semibold uppercase tracking-wider">Timestamp</th>
                <th className="pb-3 font-semibold uppercase tracking-wider">Opp ID</th>
                <th className="pb-3 font-semibold uppercase tracking-wider">Decision</th>
                <th className="pb-3 font-semibold uppercase tracking-wider text-right">Net Profit</th>
                <th className="pb-3 font-semibold uppercase tracking-wider text-right">Gas Cost</th>
                <th className="pb-3 font-semibold uppercase tracking-wider">State Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {logs.map((log) => {
                const profitColor = log.netProfitUsd > 0 ? "text-emerald-400" : "text-rose-400";
                const decisionBg =
                  log.decision === "EXECUTED"
                    ? "bg-emerald-950/40 text-emerald-400 border-emerald-800/40"
                    : log.decision === "NO_OP"
                    ? "bg-slate-900 text-slate-400 border-slate-800"
                    : "bg-cyan-950/40 text-cyan-400 border-cyan-800/40";

                return (
                  <tr key={log.id} className="hover:bg-slate-900/20 transition-colors">
                    <td className="py-3 text-slate-400 text-[11px] whitespace-nowrap">
                      {formatDate(log.timestamp)}
                    </td>
                    <td className="py-3 font-bold text-cyan-400">
                      {log.opportunityId}
                    </td>
                    <td className="py-3">
                      <span className={`px-2 py-0.5 border text-[9px] rounded font-bold ${decisionBg}`}>
                        {log.decision}
                      </span>
                    </td>
                    <td className={`py-3 text-right font-bold ${profitColor}`}>
                      {formatMoney(log.netProfitUsd)}
                    </td>
                    <td className="py-3 text-right text-slate-400">
                      {formatMoney(log.gasCostUsd)}
                    </td>
                    <td className="py-3 font-mono text-[10px] text-slate-500">
                      <code>{log.c1StateHash.substring(0, 14)}...</code>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
