/**
 * OMEGA V5 — Off-Chain Transient Accounting Math Engine
 *
 * Simulates the EIP-1153 transient storage ledger that runs inside the executor
 * contract during a flashloan callback chain.  All arithmetic is USD-denominated
 * floating-point so the UI can verify conservation before broadcasting.
 *
 * Execution-type awareness:
 *   C1_ARBITRAGE  — forward route: Balancer Vault UNLOCK → swap hops → SETTLE
 *   C2_ARBITRAGE  — same structure; reverse/mirror direction handled by pool ordering
 *   LIQUIDATION   — UNLOCK → Aave repay/seize → optional swap back → SETTLE
 *
 * Pool-category awareness:
 *   FUNDING_FLASHLOAN  → Balancer Vault UNLOCK phase (opens D₀)
 *   SWAPPABLE_EXECUTION → standard SWAP legs
 *   LIQUIDATION_TARGET  → AAVE_LIQUIDATION leg (repay debt, seize collateral + bonus)
 *
 * Balancer Vault is treated as a unified concept (not V2 or V3 specific).
 * Flash fee rate = 0 for the Balancer Vault on Polygon (both compat modes).
 *
 * Spec reference: "Transient Accounting Math for Algebra, Route State, and ML/Quantum Inputs"
 */

import {
  ArbitrageRoute,
  ExecutionType,
  PoolCategory,
  PoolInfo,
  TransientAccountingTrace,
  TransientLeg,
  TransientLegPhase,
} from '../types';
import { TRANSIENT_EPSILON_USD_MAX } from '../config/chainConfig';

// ---------------------------------------------------------------------------
// Integrity hash (deterministic, synchronous — no external deps)
// ---------------------------------------------------------------------------

/**
 * Builds a deterministic 256-bit integrity commitment for a route using a
 * djb2 polynomial hash over the canonical route descriptor.  Returns a
 * 0x-prefixed 64-char hex string that can be stored in transient slot H_j
 * on-chain (via TSTORE) and verified before each leg executes.
 *
 * The underlying hash primitive is exported as `djb2HashHex` so callers
 * that need to hash a non-route canonical string (e.g. the payload builder)
 * can reuse the same algorithm without duplicating it.
 */

/**
 * Core primitive: djb2 polynomial hash over 8 independent words.
 * Returns a 0x-prefixed 64-character hex string (256 bits).
 */
export function djb2HashHex(canonical: string): string {
  const words = new Uint32Array(8);
  for (let i = 0; i < canonical.length; i++) {
    const ch = canonical.charCodeAt(i);
    for (let w = 0; w < 8; w++) {
      words[w] = Math.imul(words[w], 33) ^ (ch + w * 0x9e3779b9);
    }
  }
  return '0x' + Array.from(words).map((n) => (n >>> 0).toString(16).padStart(8, '0')).join('');
}

export function buildIntegrityHash(route: ArbitrageRoute): string {
  const canonical = [
    route.id,
    route.pathString,
    route.executionType ?? 'C1_ARBITRAGE',
    ...route.pools.map((p) => `${p.address}:${p.feeBps}:${p.category}`),
    route.optimalInputUSD.toFixed(6),
    route.grossProfitUSD.toFixed(6),
  ].join('|');
  return djb2HashHex(canonical);
}

// ---------------------------------------------------------------------------
// Conservation check
// ---------------------------------------------------------------------------

export interface ConservationCheckResult {
  passed: boolean;
  residualUSD: number;
}

/**
 * Per-leg conservation equation (spec §3):
 *   valueBefore + externalInflow == valueAfter + cost + deltaMarket  (±ε)
 *
 * Sign conventions:
 *   cost        — always positive (protocol fees + gas + reserves)
 *   deltaMarket — signed as a **cost** (positive = slippage / value lost to AMM;
 *                 negative = net value inflow, e.g. the Aave liquidation bonus)
 *   externalInflow — folded into deltaMarket for this implementation (always 0 here)
 *
 * Rearranging with externalInflow = 0:
 *   residual = |valueBefore − valueAfter − cost − deltaMarket|
 *
 * Rejects with TRANSIENT_LEG_ACCOUNTING_MISMATCH if |ε_j| > epsilon.
 */
export function checkConservation(
  valueBefore: number,
  valueAfter: number,
  cost: number,
  deltaMarket: number,
  epsilon: number = TRANSIENT_EPSILON_USD_MAX
): ConservationCheckResult {
  // residual = |valueBefore − valueAfter − cost − deltaMarket|
  // When deltaMarket < 0 (e.g. liquidation bonus), it effectively adds to valueAfter.
  const residualUSD = Math.abs(valueBefore - valueAfter - cost - deltaMarket);
  return { passed: residualUSD <= epsilon, residualUSD };
}

// ---------------------------------------------------------------------------
// Debt schedule
// ---------------------------------------------------------------------------

export interface DebtSchedule {
  /** D₀ = borrowedAmount × (1 + feeRate).  Zero fee for Balancer Vault. */
  D0: number;
  finalBalance: number;
  finalRepaymentPassed: boolean;
}

/**
 * Opens D₀ at flashloan initiation (Balancer Vault UNLOCK) and verifies
 * the terminal inventory covers it at SETTLE.
 * Flash fee for the Balancer Vault on Polygon is 0 (feeRate = 0).
 */
export function computeDebtSchedule(
  borrowedAmount: number,
  feeRate: number,
  finalInventory: number
): DebtSchedule {
  const D0 = borrowedAmount * (1 + feeRate);
  return { D0, finalBalance: finalInventory, finalRepaymentPassed: finalInventory >= D0 };
}

// ---------------------------------------------------------------------------
// Pool-category → leg phase mapping
// ---------------------------------------------------------------------------

function resolvePhase(category: PoolCategory, executionType: ExecutionType): TransientLegPhase {
  if (category === 'FUNDING_FLASHLOAN') return 'BALANCER_VAULT_UNLOCK';
  if (category === 'LIQUIDATION_TARGET') return 'AAVE_LIQUIDATION';
  return 'SWAP';
}

// ---------------------------------------------------------------------------
// Per-leg swap accounting (CPMM / CLMM virtual reserve model)
// ---------------------------------------------------------------------------

function computeSwapOutput(inventory: number, pool: PoolInfo): number {
  const feeFraction = pool.feeBps / 10_000;
  const xv = pool.reserve0USD || 1_000_000;
  const yv = pool.reserve1USD || 1_000_000;
  const xEff = inventory * (1 - feeFraction);
  // CPMM: y(x) = (y_v × x_eff) / (x_v + x_eff)
  return (yv * xEff) / (xv + xEff);
}

// ---------------------------------------------------------------------------
// Aave liquidation leg
// ---------------------------------------------------------------------------

/**
 * Models one Aave V3 liquidation step:
 *   - Executor repays debtToken (amountIn) for the borrower
 *   - Receives collateralToken = amountIn × (1 + liquidationBonus)
 *   - Aave fee (close factor applied to debt) accounted as feeUSD
 *
 * The default Aave V3 liquidation bonus on Polygon is 5–10%.  We model 7.5%.
 */
function computeLiquidationOutput(inventory: number): {
  amountOut: number;
  feeUSD: number;
  bonusUSD: number;
} {
  const aaveFeeRate = 0.0009;      // 9 bps Aave protocol fee
  const liquidationBonus = 0.075;  // 7.5% collateral bonus
  const feeUSD = inventory * aaveFeeRate;
  const bonusUSD = inventory * liquidationBonus;
  const amountOut = inventory - feeUSD + bonusUSD;
  return { amountOut, feeUSD, bonusUSD };
}

// ---------------------------------------------------------------------------
// Main ledger computation
// ---------------------------------------------------------------------------

/**
 * Runs the token-level balance update rule across all pool hops and produces a
 * fully populated `TransientAccountingTrace`.
 *
 * The trace models the exact sequence that would execute inside the on-chain
 * contract's flashloan callback:
 *
 *   1. BALANCER_VAULT_UNLOCK  — identifies the flashloan funding pool (FUNDING_FLASHLOAN)
 *                                and opens D₀
 *   2. One or more legs       — SWAP or AAVE_LIQUIDATION based on pool category
 *   3. BALANCER_VAULT_SETTLE  — verifies finalInventory ≥ D₀
 *
 * For C2_ARBITRAGE the pools are the same route structure; the REVERSE/MIRROR
 * decision is reflected in the route's pool ordering by the caller.
 *
 * For LIQUIDATION routes the LIQUIDATION_TARGET pool triggers an Aave-specific
 * accounting leg (collateral bonus instead of CPMM slippage).
 */
export function computeLegLedger(
  route: ArbitrageRoute,
  epsilon: number = TRANSIENT_EPSILON_USD_MAX
): TransientAccountingTrace {
  // Balancer Vault flash fee = 0 for both V2 and V3 compat modes on Polygon
  const BALANCER_VAULT_FLASH_FEE = 0;
  const executionType: ExecutionType = route.executionType ?? 'C1_ARBITRAGE';

  // Identify the flashloan funding pool (Balancer Vault).
  // Any pool with category FUNDING_FLASHLOAN is the vault source.
  const fundingPool = route.pools.find((p) => p.category === 'FUNDING_FLASHLOAN');
  const borrowedToken = fundingPool?.token0.symbol ?? 'USDC';
  const borrowedAmount = route.optimalInputUSD;

  let inventory = borrowedAmount;
  const legs: TransientLeg[] = [];
  let legIndex = 0;

  // ── Phase 0: BALANCER_VAULT_UNLOCK ──────────────────────────────────────
  // The Balancer Vault (dual V2/V3 compatible) initiates the flashloan.
  // In transient storage: TSTORE(DEBT_SLOT, D₀).
  // We record this as leg 0 — no swap math, just debt opening.
  if (fundingPool) {
    legs.push({
      legIndex: legIndex++,
      phase: 'BALANCER_VAULT_UNLOCK',
      poolCategory: fundingPool.category,
      poolProtocol: fundingPool.protocol,
      tokenIn: borrowedToken,
      tokenOut: borrowedToken,
      amountIn: 0,
      amountOut: borrowedAmount, // vault releases funds to executor
      feeUSD: 0,                 // Balancer Vault = 0 fee
      gasReserveUSD: 0,
      tipUSD: 0,
      riskReserveUSD: 0,
      modelReserveUSD: 0,
      residualUSD: 0,
      passed: true,
    });
  }

  // ── Phases 1..n: Swap or Liquidation legs ────────────────────────────────
  // Iterate all non-funding pools in route order.
  const executionPools = route.pools.filter((p) => p.category !== 'FUNDING_FLASHLOAN');

  for (const pool of executionPools) {
    const phase = resolvePhase(pool.category, executionType);
    const tokenIn =
      legIndex > 0 ? legs[legIndex - 1].tokenOut : borrowedToken;
    const tokenOut = pool.token1.symbol;

    let amountOut: number;
    let feeUSD: number;
    let gasReserveUSD: number;
    let tipUSD: number;
    let riskReserveUSD: number;
    let modelReserveUSD: number;
    let deltaMarket: number;

    if (phase === 'AAVE_LIQUIDATION') {
      // ── Aave liquidation accounting ──────────────────────────────────────
      // Repay borrower debt (amountIn), seize collateral + bonus (amountOut).
      const liq = computeLiquidationOutput(inventory);
      amountOut = liq.amountOut;
      feeUSD = liq.feeUSD;
      gasReserveUSD = amountOut * 0.0018; // liquidation gas is slightly higher
      tipUSD = amountOut * 0.0004;
      riskReserveUSD = amountOut * 0.0012;
      modelReserveUSD = amountOut * 0.0008;
      // deltaMarket is signed as a **cost** (positive = value lost to AMM).
      // The Aave liquidation bonus is a net value inflow, so it must be stored as a
      // negative deltaMarket value — this offsets the cost in the conservation check,
      // keeping the residual within ε_allowed.
      deltaMarket = -(liq.bonusUSD);
    } else {
      // ── Standard SWAP leg (CPMM / CLMM / Algebra / Curve / Balancer pool) ─
      amountOut = computeSwapOutput(inventory, pool);
      feeUSD = inventory * (pool.feeBps / 10_000);
      gasReserveUSD = amountOut * 0.0012;
      tipUSD = amountOut * 0.0004;
      riskReserveUSD = amountOut * 0.0008;
      modelReserveUSD = amountOut * 0.0006;
      // deltaMarket: price-impact slippage (ideal minus actual, excluding protocol fee)
      const idealOut = inventory - feeUSD;
      deltaMarket = idealOut - amountOut; // positive = slippage cost
    }

    const totalCost = feeUSD + gasReserveUSD + tipUSD + riskReserveUSD + modelReserveUSD;
    const conservation = checkConservation(inventory, amountOut, totalCost, deltaMarket, epsilon);

    legs.push({
      legIndex: legIndex++,
      phase,
      poolCategory: pool.category,
      poolProtocol: pool.protocol,
      tokenIn,
      tokenOut,
      amountIn: inventory,
      amountOut,
      feeUSD,
      gasReserveUSD,
      tipUSD,
      riskReserveUSD,
      modelReserveUSD,
      residualUSD: conservation.residualUSD,
      passed: conservation.passed,
    });

    inventory = amountOut;
  }

  // ── Final phase: BALANCER_VAULT_SETTLE ───────────────────────────────────
  // Executor transfers borrowedAmount back to the Balancer Vault.
  // In transient storage: TLOAD(DEBT_SLOT) checked, then TSTORE(DEBT_SLOT, 0).
  const debtSchedule = computeDebtSchedule(borrowedAmount, BALANCER_VAULT_FLASH_FEE, inventory);
  legs.push({
    legIndex: legIndex++,
    phase: 'BALANCER_VAULT_SETTLE',
    poolCategory: fundingPool?.category ?? 'FUNDING_FLASHLOAN',
    poolProtocol: fundingPool?.protocol ?? 'BALANCER_VAULT',
    tokenIn: legs.length > 0 ? legs[legs.length - 1].tokenOut : borrowedToken,
    tokenOut: borrowedToken,
    amountIn: inventory,
    amountOut: inventory - debtSchedule.D0, // net profit released after repayment
    feeUSD: 0,
    gasReserveUSD: 0,
    tipUSD: 0,
    riskReserveUSD: 0,
    modelReserveUSD: 0,
    residualUSD: 0,
    passed: debtSchedule.finalRepaymentPassed,
  });

  return {
    routeId: route.id,
    executionType,
    borrowedToken,
    borrowedAmount,
    debtWithFee: debtSchedule.D0,
    legs,
    integrityHash: buildIntegrityHash(route),
    finalRepaymentPassed: debtSchedule.finalRepaymentPassed,
  };
}
