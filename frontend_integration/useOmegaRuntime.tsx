import { useCallback, useEffect, useMemo, useState } from "react";
import { OmegaApiClient, OmegaMode, RuntimeSettings } from "./omegaApiClient";

export type OmegaRuntimeState = {
  loading: boolean;
  error: string;
  health: any;
  status: any;
  mode: any;
  pnl: any;
  liquidations: any;
  oraclePrices: any;
  traces: any[];
  sessionProof: any;
  runtimeAlignment: any;
  finalizer: any;
};

const initialState: OmegaRuntimeState = {
  loading: true,
  error: "",
  health: null,
  status: null,
  mode: null,
  pnl: null,
  liquidations: null,
  oraclePrices: null,
  traces: [],
  sessionProof: null,
  runtimeAlignment: null,
  finalizer: null,
};

export function useOmegaRuntime(apiBaseUrl: string, apiToken = "", pollMs = 5000) {
  const client = useMemo(
    () => new OmegaApiClient({ baseUrl: apiBaseUrl, apiToken }),
    [apiBaseUrl, apiToken],
  );
  const [state, setState] = useState<OmegaRuntimeState>(initialState);

  const refresh = useCallback(async () => {
    try {
      const [health, status, mode, pnl, liquidations, oraclePrices, traces, sessionProof, runtimeAlignment, finalizer] = await Promise.all([
        client.health(),
        client.runtimeStatus(false),
        client.runtimeMode(),
        client.pnl(),
        client.liquidationTracker("1.10", 50),
        client.oraclePrices(false),
        client.traces(25),
        client.sessionProof(),
        client.runtimeAlignmentProof(),
        client.finalizerReport(false),
      ]);
      setState({
        loading: false,
        error: "",
        health,
        status,
        mode,
        pnl,
        liquidations,
        oraclePrices,
        traces: traces.traces || [],
        sessionProof,
        runtimeAlignment,
        finalizer,
      });
    } catch (err) {
      setState((current) => ({
        ...current,
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      }));
    }
  }, [client]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, refresh]);

  const setMode = useCallback(
    async (mode: OmegaMode) => {
      await client.setRuntimeMode(mode, "ai_studio_frontend");
      await refresh();
    },
    [client, refresh],
  );

  const updateSettings = useCallback(
    async (settings: RuntimeSettings) => {
      await client.updateRuntimeSettings(settings);
      await refresh();
    },
    [client, refresh],
  );

  const runProofs = useCallback(async () => {
    await client.runRuntimeAlignmentProof(true);
    await client.runSessionProof(5);
    await refresh();
  }, [client, refresh]);

  const validatePipeline = useCallback(async () => {
    const result = await client.validatePipeline(true, 300);
    await refresh();
    return result;
  }, [client, refresh]);

  return {
    ...state,
    client,
    refresh,
    setMode,
    updateSettings,
    runProofs,
    validatePipeline,
  };
}
