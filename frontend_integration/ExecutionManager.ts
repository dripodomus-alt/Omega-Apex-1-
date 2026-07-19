import { OmegaApiClient, OmegaClientOptions, OmegaMode, RuntimeSettings } from "./omegaApiClient";

export type ExecutionManagerStatus = {
  mode: OmegaMode;
  executionArmed: boolean;
  guards: Record<string, boolean>;
  finalizerVerdict: string;
  walletAddress: string;
};

export type BackendValidationResult = {
  ok: boolean;
  exit_code?: number;
  timed_out?: boolean;
  stdout?: string;
  output?: string;
  [key: string]: unknown;
};

/**
 * Frontend-safe execution manager.
 *
 * This intentionally does not import ethers, hold private keys, fabricate dry-run
 * hashes, build executor calldata, or broadcast transactions. It is a typed
 * facade over the Omega backend, where exact-call, route semantics, signing,
 * broadcast, receipt, trace, and PnL gates already live.
 */
export class DeFiExecutorManager {
  private readonly client: OmegaApiClient;

  constructor(options: OmegaClientOptions) {
    this.client = new OmegaApiClient(options);
  }

  async setDryRun(dryRun: boolean) {
    return this.client.setRuntimeMode(dryRun ? "dry_run" : "live", "frontend_execution_manager");
  }

  async setRuntimeMode(mode: OmegaMode) {
    return this.client.setRuntimeMode(mode, "frontend_execution_manager");
  }

  async updateRuntimeSettings(settings: RuntimeSettings) {
    return this.client.updateRuntimeSettings(settings);
  }

  async status(probe = false): Promise<ExecutionManagerStatus> {
    const [runtime, status, finalizer] = await Promise.all([
      this.client.runtimeMode(),
      this.client.runtimeStatus(probe),
      this.client.finalizerReport(probe),
    ]);
    return {
      mode: runtime.mode,
      executionArmed: !!status.execution_armed,
      guards: status.guards || {},
      finalizerVerdict: String(finalizer.verdict || "UNKNOWN"),
      walletAddress: String((status.guards || {})["EXECUTOR_PRIVATE_KEY valid"] ? "backend_signer_configured" : ""),
    };
  }

  async isArmed(probe = false): Promise<boolean> {
    return (await this.status(probe)).executionArmed;
  }

  async getWalletAddress(): Promise<string> {
    const status = await this.client.runtimeStatus(false);
    return status.guards?.["EXECUTOR_PRIVATE_KEY valid"] ? "backend_signer_configured" : "";
  }

  async simulateTransaction(): Promise<BackendValidationResult> {
    return this.client.validatePipeline(false, 600) as Promise<BackendValidationResult>;
  }

  async validatePipeline(noEthCall = false, timeoutSeconds = 600): Promise<BackendValidationResult> {
    return this.client.validatePipeline(noEthCall, timeoutSeconds) as Promise<BackendValidationResult>;
  }

  async finalizerReport(probe = false) {
    return this.client.finalizerReport(probe);
  }

  async recentTraces(limit = 50, stage: "" | "C1" | "C2" | "LIQUIDATION" = "") {
    return this.client.traces(limit, stage);
  }

  async pnl() {
    return this.client.pnl();
  }

  async liquidationTracker(alertHealthFactor = "1.10", limit = 50) {
    return this.client.liquidationTracker(alertHealthFactor, limit);
  }

  async runProofs() {
    const [runtimeAlignment, sessionSigner, finalizer] = await Promise.all([
      this.client.runRuntimeAlignmentProof(true),
      this.client.runSessionProof(5),
      this.client.finalizerReport(true),
    ]);
    return { runtimeAlignment, sessionSigner, finalizer };
  }

  async generateSignedPayload(): Promise<null> {
    throw new Error("Frontend signing is disabled. Use backend exact-call and guarded submission lanes.");
  }

  async broadcastArbitragePayload(): Promise<never> {
    throw new Error("Frontend broadcast is disabled. The backend engine owns live submission after exact-call truth passes.");
  }

  async broadcastLiquidationPayload(): Promise<never> {
    throw new Error("Frontend liquidation broadcast is disabled. The backend liquidation pipeline owns payload simulation and submission.");
  }
}
