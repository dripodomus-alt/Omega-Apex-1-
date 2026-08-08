import React, { useState, useEffect, useCallback } from 'react';
import { Target, Activity, Zap, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react';

export interface LiquidatablePosition {
  user_address: string;
  health_factor: number;
  collateral_value_usd: number;
  debt_value_usd: number;
  max_liquidatable_debt_usd: number;
  liquidation_bonus_usd: number;
  estimated_profit_usd: number;
  is_executable: boolean;
}

export const LiquidationHunter: React.FC = () => {
  const [positions, setPositions] = useState<LiquidatablePosition[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchLiquidations = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // In a real app, the server would scan a dynamic list of borrowers.
      // For the dashboard, we can use a known set of large, active wallets.
      const res = await fetch('/api/liquidations/scan?min_profit_usd=10');
      if (!res.ok) {
        throw new Error(`API Error: ${res.statusText}`);
      }
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      setPositions(data.liquidations || []);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err: any) {
      setError(err.message || 'Failed to fetch liquidation opportunities.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLiquidations();
    const interval = setInterval(fetchLiquidations, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [fetchLiquidations]);

  const handleExecute = (position: LiquidatablePosition) => {
    // This would trigger the execution pipeline for liquidations
    console.log(`Executing liquidation for ${position.user_address}...`);
    // In a real implementation, you'd call a method similar to runExecutionPipeline
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-rose-950 border border-rose-800/80 rounded-lg text-rose-400">
            <Target className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white font-mono uppercase tracking-wider">
              Aave V3 Liquidation Hunter
            </h3>
            <p className="text-xs text-slate-400">Live monitoring of at-risk positions on Polygon.</p>
          </div>
        </div>
        <button
          onClick={fetchLiquidations}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-mono font-bold transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>{isLoading ? 'Scanning...' : 'Refresh'}</span>
        </button>
      </div>

      {error && (
        <div className="bg-rose-950/50 text-rose-300 text-xs font-mono p-3 rounded-lg border border-rose-800">
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className="text-xs text-slate-400 font-mono">
        Last updated: {lastUpdated || '...'}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 bg-slate-950">
              <th className="p-3">Health Factor</th>
              <th className="p-3">User</th>
              <th className="p-3 text-right">Collateral (USD)</th>
              <th className="p-3 text-right">Debt (USD)</th>
              <th className="p-3 text-right">Est. Profit (USD)</th>
              <th className="p-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {positions.length > 0 ? (
              positions.map((pos) => (
                <tr key={pos.user_address} className="hover:bg-slate-800/40 transition-colors">
                  <td className="p-3 font-bold">
                    <div className={`flex items-center gap-2 ${pos.health_factor < 1.0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {pos.health_factor < 1.0 ? <ShieldAlert className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                      <span>{pos.health_factor.toFixed(4)}</span>
                    </div>
                  </td>
                  <td className="p-3 text-slate-300 font-semibold">
                    {`${pos.user_address.slice(0, 6)}...${pos.user_address.slice(-4)}`}
                  </td>
                  <td className="p-3 text-right text-emerald-300">
                    ${pos.collateral_value_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                  <td className="p-3 text-right text-rose-300">
                    ${pos.debt_value_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                  <td className="p-3 text-right font-bold text-emerald-400">
                    ${pos.estimated_profit_usd.toFixed(2)}
                  </td>
                  <td className="p-3 text-center">
                    {pos.is_executable ? (
                      <button
                        onClick={() => handleExecute(pos)}
                        className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[11px] font-bold transition-all shadow-md flex items-center gap-1.5"
                      >
                        <Zap className="w-3 h-3" />
                        <span>Execute</span>
                      </button>
                    ) : (
                      <span className="text-slate-500 text-[11px]">Not Profitable</span>
                    )}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="text-center p-8 text-slate-500">
                  {isLoading ? 'Scanning Aave V3 for at-risk positions...' : 'No profitable liquidations found.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
