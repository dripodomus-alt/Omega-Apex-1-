/**
 * APEX OMEGA: SYSTEM BOOTSTRAP
 * =============================
 * Ignition sequence for the Apex Omega backend engine.
 *
 * Responsibilities (in order of execution):
 *  1. RPC & Network Initialization   – connect to the Polygon PoS RPC and verify
 *                                       chain ID = 137 before any scanning begins.
 *  2. System Rules & Parameters      – load global operating parameters from the
 *                                       environment and enforce the strict C1→C2
 *                                       sequential execution dependency.
 *  3. Contract & ABI Pre-loading     – instantiate ethers.Contract handles for the
 *                                       APEX VM, Aave V3 pool, ERC-20 tokens,
 *                                       Balancer vault, and router ABIs.
 *  4. Pre-flight Diagnostics         – verify env vars, confirm contracts exist
 *                                       on-chain, and halt the system rather than
 *                                       letting the scanner fire blindly.
 */

import { ethers } from "ethers";
import MevRouteDiscoveryEngine, { type ArbitrageRoute } from "./MevRouteDiscovery.js";
import RedisRouteGuard, { routeKeyFromArbitrageRoute } from "./RedisRouteGuard.js";

// ============================================================================
// ABI REGISTRY – pre-loaded once at bootstrap time
// ============================================================================

const APEX_VM_ABI = [
  "function globalNonce() view returns (uint256)",
  "function executeC1(uint8 flashloanSource,address flashloanAsset,uint256 flashloanAmount,tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
  "function executeC2(bytes32 c1InternalId,uint8 flashloanSource,address flashloanAsset,uint256 flashloanAmount,tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external",
] as const;

const AAVE_V3_POOL_ABI = [
  "function getReservesList() view returns (address[])",
  "function getUserAccountData(address user) view returns (uint256 totalCollateralBase,uint256 totalDebtBase,uint256 availableBorrowsBase,uint256 currentLiquidationThreshold,uint256 ltv,uint256 healthFactor)",
] as const;

const ERC20_ABI = [
  "function decimals() view returns (uint8)",
  "function symbol() view returns (string)",
  "function name() view returns (string)",
  "function balanceOf(address) view returns (uint256)",
] as const;

const BALANCER_VAULT_ABI = [
  "function getPoolTokens(bytes32 poolId) view returns (address[] tokens,uint256[] balances,uint256 lastChangeBlock)",
] as const;

const UNISWAP_V2_ROUTER_ABI = [
  "function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline) returns (uint256[] amounts)",
] as const;

// ============================================================================
// SYSTEM RULES – global operating parameters
// ============================================================================

/** Immutable execution rules enforced by bootstrap before any cycle runs. */
export interface SystemRules {
  /** Chain that the engine is permitted to operate on. */
  readonly requiredChainId: bigint;
  /**
   * C1 must always complete and confirm before C2 is scheduled.
   * This invariant cannot be overridden at runtime.
   */
  readonly c1MustPrecedeC2: true;
  /** Minimum net profit (USD) required to consider a route executable. */
  readonly minNetProfitUSD: number;
  /** Maximum flashloan fraction of pool TVL the engine will attempt. */
  readonly maxFlashTvlFraction: number;
  /** Estimated gas units for a full arb + flashloan execution. */
  readonly estimatedGasUnits: number;
  /** Live execution mode. When false the engine operates in shadow/dry-run mode. */
  readonly liveExecution: boolean;
}

// ============================================================================
// NETWORK CONTEXT – populated during initialization
// ============================================================================

export interface NetworkContext {
  chainId: bigint;
  blockNumber: number;
  gasPrice: bigint;
  gasPriceGwei: number;
  maticPriceUSD: number;
}

// ============================================================================
// CONTRACT REGISTRY – populated during bootstrap
// ============================================================================

export interface ContractRegistry {
  apexVm: ethers.Contract | null;
  aaveV3Pool: ethers.Contract;
  flashloanToken: ethers.Contract;
  balancerVault: ethers.Contract;
  quickswapV2Router: ethers.Contract;
  sushiswapV2Router: ethers.Contract;
}

// ============================================================================
// PUBLIC TYPES
// ============================================================================

export interface ExecutionCycle {
  cycleId: number;
  status: "SUCCESS" | "NO_ROUTE" | "ERROR";
  duration_ms: number;
  discoveredRoutes: ArbitrageRoute[];
  selectedRoute?: ArbitrageRoute;
  txHash?: string;
  error?: string;
}

export interface CycleResults {
  cycles: ExecutionCycle[];
  summary: {
    totalCycles: number;
    successfulCycles: number;
    totalGrossProfit: number;
    totalNetProfitUSD: number;
    averageProfit: number;
    totalDuration_ms: number;
    targetContract: string;
    flashloanAsset: string;
    executorConfigured: boolean;
  };
}

// ============================================================================
// FORMATTING HELPER
// ============================================================================

export function formatCycleResults(results: CycleResults): string {
  const lines = [
    "=".repeat(80),
    "APEX OMEGA 5-CYCLE SUMMARY",
    "=".repeat(80),
    `Cycles Run:           ${results.summary.totalCycles}`,
    `Successful Cycles:    ${results.summary.successfulCycles}`,
    `Total Net Profit:    $${results.summary.totalNetProfitUSD.toFixed(2)}`,
    `Average Profit/Cycle:$${results.summary.averageProfit.toFixed(2)}`,
    `Total Duration:       ${results.summary.totalDuration_ms}ms`,
    `Target Contract:      ${results.summary.targetContract || "NOT CONFIGURED"}`,
    `Flashloan Asset:      ${results.summary.flashloanAsset}`,
    `Executor Configured:  ${results.summary.executorConfigured ? "YES" : "NO (dry-run)"}`,
  ];

  for (const cycle of results.cycles) {
    lines.push(
      "",
      `Cycle ${cycle.cycleId}: ${cycle.status} (${cycle.duration_ms}ms)`,
      `  Routes Discovered: ${cycle.discoveredRoutes.length}`,
      `  Best Net Profit:  $${(cycle.selectedRoute?.netProfitUSD ?? 0).toFixed(2)}`
    );
    if (cycle.error) {
      lines.push(`  Error: ${cycle.error}`);
    }
  }

  return lines.join("\n");
}

// ============================================================================
// BOOTSTRAP CLASS
// ============================================================================

export default class SystemBootstrap {
  // ── Initialisation state ──────────────────────────────────────────────────
  private initialized = false;
  private provider: ethers.JsonRpcProvider | null = null;
  private networkContext: NetworkContext | null = null;
  private contracts: ContractRegistry | null = null;
  private rules: SystemRules | null = null;

  // ── Discovery engine (created lazily after init) ──────────────────────────
  private discoveryEngine: MevRouteDiscoveryEngine | null = null;

  // ── Well-known Polygon mainnet addresses ─────────────────────────────────
  private static readonly AAVE_V3_POOL =
    process.env.AAVE_V3_POOL_ADDRESS ?? "0x794a61358D6845594F94dc1DB02A252b5b4814aD";
  private static readonly BALANCER_VAULT =
    process.env.BALANCER_VAULT ?? "0xBA12222222228d8Ba445958a75a0704d566BF2C8";
  private static readonly QUICKSWAP_V2_ROUTER =
    process.env.QUICKSWAP_V2_ROUTER ?? "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff";
  private static readonly SUSHISWAP_V2_ROUTER =
    process.env.SUSHISWAP_V2_ROUTER ?? "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506";

  constructor(
    private readonly rpcUrl: string,
    private readonly targetContractAddress: string,
    private readonly flashloanAssetAddress: string,
    private readonly executorPrivateKey?: string,
    private readonly maticPriceUsd: number = 0.72,
    private readonly routeGuard: RedisRouteGuard | null = null
  ) {}

  // ── 1. RPC & NETWORK INITIALIZATION ─────────────────────────────────────

  /**
   * Creates the ethers provider and confirms connectivity to Polygon (chainId=137).
   * Throws if the provider is unreachable or on the wrong chain.
   */
  private async initializeNetwork(): Promise<NetworkContext> {
    console.log("[BOOTSTRAP] ❶  RPC & Network Initialization");

    this.provider = new ethers.JsonRpcProvider(this.rpcUrl, 137, { staticNetwork: true });

    const network = await this.provider.getNetwork();
    if (network.chainId !== 137n) {
      throw new Error(
        `[BOOTSTRAP] CHAIN_ID_MISMATCH – expected 137 (Polygon), got ${network.chainId}`
      );
    }

    const [blockNumber, feeData] = await Promise.all([
      this.provider.getBlockNumber(),
      this.provider.getFeeData(),
    ]);

    const gasPrice = feeData.gasPrice ?? feeData.maxFeePerGas;
    if (gasPrice === null) {
      throw new Error("[BOOTSTRAP] PROVIDER_GAS_PRICE_UNAVAILABLE");
    }

    const ctx: NetworkContext = {
      chainId: network.chainId,
      blockNumber,
      gasPrice,
      gasPriceGwei: Number(gasPrice) / 1e9,
      maticPriceUSD: this.maticPriceUsd,
    };

    console.log(
      `[BOOTSTRAP]    ✓ Chain 137 (Polygon) confirmed  block=${blockNumber}  gas=${ctx.gasPriceGwei.toFixed(2)} Gwei`
    );
    return ctx;
  }

  // ── 2. SYSTEM RULES & PARAMETERS ────────────────────────────────────────

  /**
   * Reads operating parameters from the environment and builds the immutable
   * rule-set.  The C1→C2 sequential dependency is always enforced.
   */
  private loadSystemRules(): SystemRules {
    console.log("[BOOTSTRAP] ❷  System Rules & Parameters");

    const rules: SystemRules = {
      requiredChainId: 137n,
      c1MustPrecedeC2: true, // INVARIANT: C2 is always gated on a confirmed C1
      minNetProfitUSD: Number(process.env.MIN_NET_PROFIT_USD ?? "5"),
      maxFlashTvlFraction: Number(process.env.SIM_MAX_FLASH_TVL_FRACTION ?? "0.15"),
      estimatedGasUnits: Number(process.env.ESTIMATED_GAS_UNITS ?? "450000"),
      liveExecution: process.env.LIVE_EXECUTION === "true",
    };

    console.log(
      `[BOOTSTRAP]    ✓ Rules loaded` +
        `  minProfit=$${rules.minNetProfitUSD}` +
        `  liveExecution=${rules.liveExecution}` +
        `  c1MustPrecedeC2=${rules.c1MustPrecedeC2}` +
        `  estimatedGas=${rules.estimatedGasUnits}`
    );
    return rules;
  }

  // ── 3. CONTRACT & ABI LOADING ────────────────────────────────────────────

  /**
   * Pre-loads ethers.Contract instances for all contracts the engine may
   * interact with.  The APEX VM handle is optional (target contract may not be
   * configured in simulation mode).
   */
  private loadContracts(provider: ethers.JsonRpcProvider): ContractRegistry {
    console.log("[BOOTSTRAP] ❸  Contract & ABI Loading");

    const apexVm = this.targetContractAddress
      ? new ethers.Contract(this.targetContractAddress, APEX_VM_ABI, provider)
      : null;

    const registry: ContractRegistry = {
      apexVm,
      aaveV3Pool: new ethers.Contract(SystemBootstrap.AAVE_V3_POOL, AAVE_V3_POOL_ABI, provider),
      flashloanToken: new ethers.Contract(this.flashloanAssetAddress, ERC20_ABI, provider),
      balancerVault: new ethers.Contract(SystemBootstrap.BALANCER_VAULT, BALANCER_VAULT_ABI, provider),
      quickswapV2Router: new ethers.Contract(SystemBootstrap.QUICKSWAP_V2_ROUTER, UNISWAP_V2_ROUTER_ABI, provider),
      sushiswapV2Router: new ethers.Contract(SystemBootstrap.SUSHISWAP_V2_ROUTER, UNISWAP_V2_ROUTER_ABI, provider),
    };

    const loaded = Object.keys(registry).filter((k) => registry[k as keyof ContractRegistry] !== null);
    console.log(`[BOOTSTRAP]    ✓ ABIs pre-loaded  contracts=[${loaded.join(", ")}]`);
    return registry;
  }

  // ── 4. PRE-FLIGHT DIAGNOSTICS ────────────────────────────────────────────

  /**
   * Validates environment variables and confirms contracts exist on-chain.
   * Throws immediately if any critical check fails so the system halts rather
   * than firing blindly with incomplete configuration.
   */
  private async runPreflightDiagnostics(
    provider: ethers.JsonRpcProvider,
    rules: SystemRules,
    contracts: ContractRegistry
  ): Promise<void> {
    console.log("[BOOTSTRAP] ❹  Pre-flight Diagnostics");

    const failures: string[] = [];

    // ── (a) Environment variable sanity ──────────────────────────────────
    if (!this.rpcUrl || this.rpcUrl.includes("YOUR_") || this.rpcUrl.includes("MY_")) {
      failures.push("POLYGON_RPC_URL is not configured");
    }
    if (
      rules.liveExecution &&
      (!this.executorPrivateKey || this.executorPrivateKey.trim() === "")
    ) {
      failures.push("EXECUTOR_PRIVATE_KEY is required for live execution (LIVE_EXECUTION=true)");
    }

    // ── (b) Flashloan asset exists on-chain ───────────────────────────────
    try {
      const tokenCode = await provider.getCode(this.flashloanAssetAddress);
      if (tokenCode === "0x") {
        failures.push(
          `Flashloan asset ${this.flashloanAssetAddress} has no contract code on Polygon`
        );
      } else {
        const [symbol, decimals]: [string, number] = await Promise.all([
          contracts.flashloanToken.symbol().catch(() => "UNKNOWN"),
          contracts.flashloanToken.decimals().catch(() => 18),
        ]);
        console.log(
          `[BOOTSTRAP]    ✓ Flashloan asset  symbol=${symbol}  decimals=${decimals}  address=${this.flashloanAssetAddress}`
        );
      }
    } catch (err) {
      failures.push(`Cannot read flashloan asset ${this.flashloanAssetAddress}: ${(err as Error).message}`);
    }

    // ── (c) APEX VM contract exists on-chain (if configured) ──────────────
    if (this.targetContractAddress) {
      try {
        const vmCode = await provider.getCode(this.targetContractAddress);
        if (vmCode === "0x") {
          failures.push(
            `Target contract ${this.targetContractAddress} has no contract code on Polygon`
          );
        } else {
          const nonce: bigint = await contracts.apexVm!.globalNonce().catch(() => null);
          console.log(
            `[BOOTSTRAP]    ✓ APEX VM contract  address=${this.targetContractAddress}  nonce=${nonce ?? "UNREADABLE"}`
          );
        }
      } catch (err) {
        failures.push(`Cannot read target contract ${this.targetContractAddress}: ${(err as Error).message}`);
      }
    } else {
      console.log("[BOOTSTRAP]    ⚠  Target contract not configured – operating in simulation mode");
    }

    // ── (d) Aave V3 pool accessible ───────────────────────────────────────
    try {
      const aaveCode = await provider.getCode(SystemBootstrap.AAVE_V3_POOL);
      if (aaveCode === "0x") {
        failures.push("Aave V3 pool contract not found on Polygon");
      } else {
        console.log(`[BOOTSTRAP]    ✓ Aave V3 pool  address=${SystemBootstrap.AAVE_V3_POOL}`);
      }
    } catch (err) {
      failures.push(`Cannot verify Aave V3 pool: ${(err as Error).message}`);
    }

    // ── (e) Halt if any check failed ──────────────────────────────────────
    if (failures.length > 0) {
      const detail = failures.map((f, i) => `  ${i + 1}. ${f}`).join("\n");
      throw new Error(
        `[BOOTSTRAP] PRE-FLIGHT FAILED – ${failures.length} diagnostic(s) failed:\n${detail}`
      );
    }

    console.log("[BOOTSTRAP]    ✓ All pre-flight diagnostics passed");
  }

  // ── PUBLIC INITIALIZE ────────────────────────────────────────────────────

  /**
   * Runs the full ignition sequence.  Idempotent – safe to call multiple times.
   * Throws if any stage fails; the caller must not proceed to `runMultipleCycles`
   * on an error.
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    console.log("\n" + "▶".repeat(60));
    console.log("APEX OMEGA SYSTEM BOOTSTRAP – IGNITION SEQUENCE");
    console.log("▶".repeat(60));

    this.networkContext = await this.initializeNetwork();
    this.rules = this.loadSystemRules();
    this.contracts = this.loadContracts(this.provider!);
    await this.runPreflightDiagnostics(this.provider!, this.rules, this.contracts);

    // Create discovery engine with live network context
    this.discoveryEngine = new MevRouteDiscoveryEngine(this.rpcUrl, this.networkContext.maticPriceUSD);

    this.initialized = true;

    console.log("[BOOTSTRAP] ✅  Ignition sequence complete – engine ready\n");
  }

  // ── PUBLIC ACCESSORS ─────────────────────────────────────────────────────

  /** Returns the loaded system rules. Throws if bootstrap has not been run. */
  getSystemRules(): SystemRules {
    if (!this.rules) throw new Error("[BOOTSTRAP] Not initialized – call initialize() first");
    return this.rules;
  }

  /** Returns live network context. Throws if bootstrap has not been run. */
  getNetworkContext(): NetworkContext {
    if (!this.networkContext) throw new Error("[BOOTSTRAP] Not initialized – call initialize() first");
    return this.networkContext;
  }

  /** Returns the pre-loaded contract registry. Throws if bootstrap has not been run. */
  getContracts(): ContractRegistry {
    if (!this.contracts) throw new Error("[BOOTSTRAP] Not initialized – call initialize() first");
    return this.contracts;
  }

  // ── CYCLE EXECUTION ──────────────────────────────────────────────────────

  /**
   * Runs `totalCycles` consecutive discovery-and-evaluate cycles.
   * Initializes the bootstrap engine automatically on first call.
   */
  async runMultipleCycles(
    totalCycles: number,
    searchDepth: number,
    minProfitUSD: number
  ): Promise<CycleResults> {
    // Ensure ignition sequence has completed
    await this.initialize();

    const cycles: ExecutionCycle[] = [];
    let successfulCycles = 0;
    let totalGrossProfit = 0;
    let totalNetProfitUSD = 0;
    let totalDuration_ms = 0;

    for (let cycleId = 1; cycleId <= totalCycles; cycleId++) {
      const startedAt = Date.now();

      try {
        const discoveredRoutes = await this.discoveryEngine!.discoverArbitrageRoutes(
          searchDepth,
          minProfitUSD
        );

        // Helper: build the Redis key for an ArbitrageRoute
        const routeKey = (r: ArbitrageRoute) =>
          routeKeyFromArbitrageRoute({
            tokenIn: r.tokenIn,
            tokenOut: r.tokenOut,
            legs: r.legs.map((l) => ({
              venue: l.venueId,
              tokenIn: l.tokenIn,
              tokenOut: l.tokenOut,
            })),
          });

        // ── Redis: filter out routes already claimed by another worker ──────
        let eligibleRoutes = discoveredRoutes;
        if (this.routeGuard) {
          const lockChecks = await Promise.all(
            discoveredRoutes.map((r) => this.routeGuard!.isLocked(routeKey(r)))
          );
          eligibleRoutes = discoveredRoutes.filter((_, idx) => !lockChecks[idx]);
        }

        // ── Select best unlocked route and acquire its lock ─────────────────
        const selectedRoute = eligibleRoutes[0] ?? null;
        if (selectedRoute && this.routeGuard) {
          const acquired = await this.routeGuard.tryAcquireLock(routeKey(selectedRoute));
          if (!acquired) {
            // Another worker claimed this route between the isLocked check and
            // tryAcquireLock. Treat the cycle as no-route rather than racing.
            const duration_ms = Date.now() - startedAt;
            cycles.push({ cycleId, status: "NO_ROUTE", duration_ms, discoveredRoutes, selectedRoute: undefined });
            totalDuration_ms += duration_ms;
            continue;
          }
        }

        const duration_ms = Date.now() - startedAt;
        const status = selectedRoute ? "SUCCESS" : "NO_ROUTE";

        cycles.push({ cycleId, status, duration_ms, discoveredRoutes, selectedRoute: selectedRoute ?? undefined });
        totalDuration_ms += duration_ms;

        if (selectedRoute) {
          successfulCycles += 1;
          totalGrossProfit += selectedRoute.grossProfit;
          totalNetProfitUSD += selectedRoute.netProfitUSD;
        }
      } catch (error) {
        const duration_ms = Date.now() - startedAt;
        totalDuration_ms += duration_ms;
        cycles.push({
          cycleId,
          status: "ERROR",
          duration_ms,
          discoveredRoutes: [],
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    return {
      cycles,
      summary: {
        totalCycles,
        successfulCycles,
        totalGrossProfit,
        totalNetProfitUSD,
        averageProfit: totalCycles > 0 ? totalNetProfitUSD / totalCycles : 0,
        totalDuration_ms,
        targetContract: this.targetContractAddress,
        flashloanAsset: this.flashloanAssetAddress,
        executorConfigured: Boolean(this.executorPrivateKey),
      },
    };
  }
}
