/**
 * OMEGA V5 — Off-Chain Transient Accounting Math Engine
 *
 * Simulates the EIP-1153 transient storage accounting that would run inside the
 * executor contract during a flashloan callback chain.  All arithmetic is done
 * in USD-denominated floating-point so the UI can verify conservation before
 * broadcasting any real transaction.
 *
 * Spec reference: "Transient Accounting Math for Algebra, Route State, and ML/Quantum Inputs"
 */

import { ArbitrageRoute, TransientAccountingTrace, TransientLeg } from '../types';
import { TRANSIENT_EPSILON_USD_MAX } from '../config/chainConfig';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Deterministic keccak-style integrity hash that does NOT depend on the
 * `ethers` library at runtime (avoids async import and keeps this module
 * synchronous).  We use a djb2 polynomial hash over a canonical string
 * representation of the route and return a 0x-prefixed 64-char hex string.
 */
export function buildIntegrityHash(route: ArbitrageRoute): string {
  const canonical = [
    route.id,
    route.pathString,
    ...route.pools.map((p) => p.address),
    route.optimalInputUSD.toFixed(6),
    route.grossProfitUSD.toFixed(6),
  ].join('|');

  // djb2 over UTF-16 code units, extended to 256-bit (8 × 32-bit words)
  const words = new Uint32Array(8);
  for (let i = 0; i < canonical.length; i++) {
    const ch = canonical.charCodeAt(i);
    for (let w = 0; w < 8; w++) {
      words[w] = Math.imul(words[w], 33) ^ (ch + w * 0x9e3779b9);
    }
  }
  const hex = Array.from(words)
    .map((n) => (n >>> 0).toString(16).padStart(8, '0'))
    .join('');
  return '0x' + hex;
}

// ---------------------------------------------------------------------------
// Core conservation check
// ---------------------------------------------------------------------------

export interface ConservationCheckResult {
  passed: boolean;
  residualUSD: number;
}

/**
 * Per-leg conservation:
 *   valueBefore + externalInflow == valueAfter + cost + deltaMarket  (±ε)
 *
 * We model `externalInflow` as 0 for normal swap legs.
 * `deltaMarket` is the price-impact term: gross output minus the ideal 1:1
 * conversion of amountIn.  For a profitable leg it is negative (slippage cost).
 */
export function checkConservation(
  valueBefore: number,
  valueAfter: number,
  cost: number,
  deltaMarket: number,
  epsilon: number = TRANSIENT_EPSILON_USD_MAX
): ConservationCheckResult {
  const residualUSD = Math.abs(valueBefore - valueAfter - cost - deltaMarket);
  return {
    passed: residualUSD <= epsilon,
    residualUSD,
  };
}

// ---------------------------------------------------------------------------
// Debt schedule
// ---------------------------------------------------------------------------

export interface DebtSchedule {
  D0: number;
  finalBalance: number;
  finalRepaymentPassed: boolean;
}

/**
 * Opens D₀ at flashloan initiation and checks that the terminal inventory
 * covers the debt after all legs are processed.
 *
 * For zero-fee flash sources (Balancer V3 on Polygon), feeRate = 0.
 */
export function computeDebtSchedule(
  borrowedAmount: number,
  feeRate: number,
  finalInventory: number
): DebtSchedule {
  const D0 = borrowedAmount * (1 + feeRate);
  return {
    D0,
    finalBalance: finalInventory,
    finalRepaymentPassed: finalInventory >= D0,
  };
}

// ---------------------------------------------------------------------------
// Full leg ledger
// ---------------------------------------------------------------------------

/**
 * Runs the token-level balance update rule for every pool hop in a route and
 * produces a `TransientAccountingTrace`.
 *
 * Model assumptions (suitable for UI simulation):
 * - Flash-borrowed token is the input token of leg 0.
 * - Each leg converts `amountIn` of `tokenIn` to `amountOut` of `tokenOut`
 *   using the constant-product swap formula with the pool's feeBps.
 * - Gas, tip, risk, and model reserves are computed as small fractions of the
 *   leg's gross output, matching the proportions implied by the spec's state
 *   vector.
 * - Flash fee rate is 0 (Balancer V3 Polygon — zero-fee vault).
 */
export function computeLegLedger(
  route: ArbitrageRoute,
  epsilon: number = TRANSIENT_EPSILON_USD_MAX
): TransientAccountingTrace {
  const flashFeeRate = 0; // Balancer V3 = 0 bps
  const borrowedAmount = route.optimalInputUSD;
  const borrowedToken = route.pools[0]?.token0.symbol ?? 'USDC';

  // Running inventory (USD) per token — simplified to aggregate USD value
  let inventory = borrowedAmount;

  const legs: TransientLeg[] = route.pools.map((pool, idx) => {
    const tokenIn = idx === 0 ? borrowedToken : route.pools[idx - 1]?.token1.symbol ?? pool.token0.symbol;
    const tokenOut = pool.token1.symbol;
    const feeFraction = pool.feeBps / 10_000;

    // CPMM output: y(x) = (y_v * x * (1 - fee)) / (x_v + x * (1 - fee))
    const xv = pool.reserve0USD || 1_000_000;
    const yv = pool.reserve1USD || 1_000_000;
    const xEff = inventory * (1 - feeFraction);
    const amountOut = (yv * xEff) / (xv + xEff);

    const feeUSD = inventory * feeFraction;
    // Gas / tip / risk / model reserves — small fractions of gross output
    const gasReserveUSD = amountOut * 0.0012;
    const tipUSD = amountOut * 0.0004;
    const riskReserveUSD = amountOut * 0.0008;
    const modelReserveUSD = amountOut * 0.0006;
    const totalCost = feeUSD + gasReserveUSD + tipUSD + riskReserveUSD + modelReserveUSD;

    // deltaMarket: slippage value change (ideal minus actual)
    const deltaMarket = inventory - amountOut - feeUSD;

    const conservation = checkConservation(
      inventory,
      amountOut,
      totalCost,
      deltaMarket,
      epsilon
    );

    const leg: TransientLeg = {
      legIndex: idx,
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
    };

    inventory = amountOut;
    return leg;
  });

  const debtSchedule = computeDebtSchedule(borrowedAmount, flashFeeRate, inventory);
  const integrityHash = buildIntegrityHash(route);

  return {
    routeId: route.id,
    borrowedToken,
    borrowedAmount,
    debtWithFee: debtSchedule.D0,
    legs,
    integrityHash,
    finalRepaymentPassed: debtSchedule.finalRepaymentPassed,
  };
}
