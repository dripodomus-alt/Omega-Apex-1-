/**
 * APEX OMEGA: EXECUTION INVARIANT ENFORCEMENT
 * ============================================
 * Strictly enforces the required execution invariants before any
 * route is promoted to "executable" and dispatched to the mempool or
 * payload disseminator.
 *
 * Invariant 1  VENUE_AGNOSTIC     – Leg 1 and Leg 2 may execute on ANY
 *                                   combination of supported DEX venues.
 *                                   Every discovered pool edge is eligible.
 *
 * Invariant 2  DIRECTION_AGNOSTIC – Token A→B or B→A is chosen entirely
 *                                   based on real-time spread discovery.
 *                                   No direction is pre-fixed.
 *
 * Invariant 3  VENUE_EXCLUSIVITY  – No atomic route may buy and sell through
 *                                   the same liquidity venue / pool address.
 *
 * Invariant 4  PRICE_INVARIANT    – The effective Ask price for the
 *                                   acquisition leg MUST be strictly less
 *                                   than the effective Bid price for the
 *                                   distribution leg:  P_buy < P_sell.
 *
 * Invariant 5  YIELD_INVARIANT    – Total Output (final leg) MUST strictly
 *                                   exceed Total Input plus all costs:
 *                                   Output > Input + FlashloanFee + Gas + Bribes
 */

export type InvariantId =
  | "VENUE_AGNOSTIC"
  | "DIRECTION_AGNOSTIC"
  | "VENUE_EXCLUSIVITY"
  | "PRICE_INVARIANT"
  | "YIELD_INVARIANT";

export class InvariantViolationError extends Error {
  readonly invariant: InvariantId;
  readonly detail: string;

  constructor(invariant: InvariantId, detail: string) {
    super(`INVARIANT_VIOLATION:${invariant}|${detail}`);
    this.name = "InvariantViolationError";
    this.invariant = invariant;
    this.detail = detail;
  }
}

/**
 * A single fully-quoted swap step inside a route.
 * All amounts are in the raw (integer, wei-equivalent) units of the
 * respective token.
 */
export interface QuotedRouteStep {
  /** DEX / venue identifier (must be non-empty – VENUE_AGNOSTIC check) */
  venueId: string;
  /** Pool-level liquidity venue identifier. Prefer `${chainId}:${poolAddress}`. */
  poolKey?: string;
  /** Input token address */
  tokenIn: string;
  /** Output token address */
  tokenOut: string;
  /** Amount of tokenIn consumed by this step */
  amountIn: bigint;
  /** Amount of tokenOut produced by this step */
  amountOut: bigint;
}

/**
 * All costs that must be subtracted from gross profit before a route may
 * be considered executable (used by the YIELD_INVARIANT check).
 *
 * All values must be denominated in the **flashloan asset's raw units**
 * (i.e., already converted from gas-token wei into flashloan-asset units).
 */
export interface RouteCostsInAsset {
  /** Flashloan fee in flashloan-asset raw units */
  flashloanFeeRaw: bigint;
  /**
   * Gas cost converted to flashloan-asset raw units.
   * Caller is responsible for the wei→asset conversion.
   */
  gasCostInAssetRaw: bigint;
  /**
   * Validator / relay / MEV tip converted to flashloan-asset raw units.
   * Pass 0n when no relay tip is used.
   */
  relayTipInAssetRaw: bigint;
  /**
   * Extra executor cost converted to flashloan-asset raw units.
   * This is for operator-configured per-route overhead not captured by gas.
   */
  executorCostInAssetRaw: bigint;
  /**
   * Risk buffer converted to flashloan-asset raw units.
   * This must be part of the raw invariant, not only USD reporting.
   */
  riskBufferInAssetRaw: bigint;
}

/**
 * Compute the effective price for a swap step as a fixed-point rational,
 * scaled to 18 decimal places to allow integer comparison.
 *
 * Returned value = (amountIn * 1e18) / amountOut
 * (i.e. "price of one unit of tokenOut expressed in tokenIn units × 1e18")
 */
function effectivePriceScaled(amountIn: bigint, amountOut: bigint): bigint {
  if (amountOut === 0n) throw new RangeError("ZERO_AMOUNT_OUT_IN_PRICE_CALC");
  return (amountIn * 10n ** 18n) / amountOut;
}

/**
 * Enforce Invariant 3: PRICE_INVARIANT
 *
 * For every pair of steps (i, j) where i < j, step_i.tokenIn == step_j.tokenOut
 * and step_i.tokenOut == step_j.tokenIn (i.e. they form a buy/sell pair on the
 * same two tokens), verify that:
 *
 *   effectiveAsk(step_i) < effectiveBid(step_j)
 *
 * In cross-multiplied form (avoids division):
 *
 *   step_i.amountIn × step_j.amountIn  <  step_i.amountOut × step_j.amountOut
 *
 * For a standard two-leg cycle A→B→A this reduces to amountIn_total < amountOut_final,
 * which is the gross-profit condition.  For longer cycles the check covers every
 * reversed token-pair leg combination found in the route.
 *
 * @throws InvariantViolationError if any acquisition/distribution pair violates
 *         P_buy < P_sell.
 */
function enforcePriceInvariant(steps: QuotedRouteStep[]): void {
  const n = steps.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const si = steps[i];
      const sj = steps[j];
      // Only check pairs that are reversed (form a buy/sell on the same token pair)
      if (
        si.tokenIn.toLowerCase() === sj.tokenOut.toLowerCase() &&
        si.tokenOut.toLowerCase() === sj.tokenIn.toLowerCase()
      ) {
        // Cross-multiplication avoids floating-point:
        // P_buy < P_sell  ⟺  amountIn_i / amountOut_i  <  amountOut_j / amountIn_j
        //                ⟺  amountIn_i * amountIn_j    <  amountOut_i * amountOut_j
        const lhs = si.amountIn * sj.amountIn;
        const rhs = si.amountOut * sj.amountOut;
        if (lhs >= rhs) {
          const askScaled = effectivePriceScaled(si.amountIn, si.amountOut);
          const bidScaled = effectivePriceScaled(sj.amountOut, sj.amountIn);
          throw new InvariantViolationError(
            "PRICE_INVARIANT",
            `step[${i}] ask=${askScaled} >= step[${j}] bid=${bidScaled}` +
              `|tokenPair=${si.tokenIn}-${si.tokenOut}` +
              `|acquireVenue=${si.venueId}|distributeVenue=${sj.venueId}`,
          );
        }
      }
    }
  }
}

/**
 * Enforce Invariant 4: YIELD_INVARIANT
 *
 * The final output of the route (last step's amountOut) must strictly exceed
 * the initial input (first step's amountIn) plus ALL costs:
 *
 *   totalOutput > totalInput + flashloanFee + gasCost + relayTip + executorCost + riskBuffer
 *
 * All values must be in the same raw-unit denomination (flashloan asset units).
 *
 * @throws InvariantViolationError if net yield is zero or negative.
 */
function enforceYieldInvariant(
  steps: QuotedRouteStep[],
  costs: RouteCostsInAsset,
): void {
  const totalInput = steps[0].amountIn;
  const totalOutput = steps[steps.length - 1].amountOut;
  const totalCosts =
    costs.flashloanFeeRaw +
    costs.gasCostInAssetRaw +
    costs.relayTipInAssetRaw +
    costs.executorCostInAssetRaw +
    costs.riskBufferInAssetRaw;
  const repaymentRequired = totalInput + totalCosts;

  if (totalOutput <= repaymentRequired) {
    const deficit = repaymentRequired - totalOutput;
    throw new InvariantViolationError(
      "YIELD_INVARIANT",
      `totalOutput(${totalOutput}) <= repaymentRequired(${repaymentRequired})` +
        `|input=${totalInput}|flashFee=${costs.flashloanFeeRaw}` +
        `|gas=${costs.gasCostInAssetRaw}|relayTip=${costs.relayTipInAssetRaw}` +
        `|executorCost=${costs.executorCostInAssetRaw}|riskBuffer=${costs.riskBufferInAssetRaw}` +
        `|deficit=${deficit}`,
    );
  }
}

/**
 * Enforce Invariant 1: VENUE_AGNOSTIC
 *
 * Every step must name a non-empty venue.  A blank venueId means the route was
 * constructed with a hardcoded or null adapter, which is prohibited.
 *
 * @throws InvariantViolationError if any step has a blank venue identifier.
 */
function enforceVenueAgnostic(steps: QuotedRouteStep[]): void {
  for (let i = 0; i < steps.length; i++) {
    if (!steps[i].venueId || steps[i].venueId.trim() === "") {
      throw new InvariantViolationError(
        "VENUE_AGNOSTIC",
        `step[${i}] has no venueId; all legs must be assigned a discovered DEX venue`,
      );
    }
  }
}

function venueExclusivityKey(step: QuotedRouteStep): string {
  if (step.poolKey && step.poolKey.trim() !== "") return step.poolKey.toLowerCase();

  // Backward-compatible fallback for legacy callers that only populate
  // venueId as "dexId:poolAddress:tokenIn->tokenOut".
  const parts = step.venueId.split(":");
  return (parts[1] || step.venueId).toLowerCase();
}

/**
 * Enforce Invariant 3: VENUE_EXCLUSIVITY
 *
 * Same protocol architecture and same fee tier are allowed, but the same
 * liquidity venue / pool address must not appear in more than one leg of the
 * same atomic route. The canonical key is `${chainId}:${poolAddress}`. This
 * rejects A->B and B->A round-trips through the same pool, and any duplicate
 * pool reuse in deeper routes.
 *
 * @throws InvariantViolationError if any pool-level venue is reused.
 */
function enforceVenueExclusivity(steps: QuotedRouteStep[]): void {
  const seen = new Map<string, number>();
  for (let i = 0; i < steps.length; i++) {
    const key = venueExclusivityKey(steps[i]);
    const firstSeen = seen.get(key);
    if (firstSeen !== undefined) {
      throw new InvariantViolationError(
        "VENUE_EXCLUSIVITY",
        `step[${i}] reuses pool-level venue "${key}" first seen at step[${firstSeen}]; ` +
          `buy and sell legs must not route through the same liquidity pool`,
      );
    }
    seen.set(key, i);
  }
}

/**
 * Enforce Invariant 2: DIRECTION_AGNOSTIC
 *
 * No two steps may share the same (tokenIn, tokenOut) pair AND the same pool
 * address.  This prevents a fixed-direction route where a single pool is
 * consumed multiple times in the same direction (which would indicate a
 * pre-wired, non-dynamic path).
 *
 * Pool reuse in the reverse direction is prohibited separately by
 * VENUE_EXCLUSIVITY.
 *
 * @throws InvariantViolationError if any step pair shares both pool and direction.
 */
function enforceDirectionAgnostic(steps: QuotedRouteStep[]): void {
  // venueId alone is not a pool address; this invariant is checked here
  // on the (venueId, tokenIn, tokenOut) triple because the discovery engine
  // provides direction-aware venueIds (pool-level unique edges).
  const seen = new Set<string>();
  for (let i = 0; i < steps.length; i++) {
    const key =
      `${steps[i].venueId.toLowerCase()}:${steps[i].tokenIn.toLowerCase()}:${steps[i].tokenOut.toLowerCase()}`;
    if (seen.has(key)) {
      throw new InvariantViolationError(
        "DIRECTION_AGNOSTIC",
        `step[${i}] duplicates venue+direction key "${key}"; execution path must not re-use ` +
          `the same pool in the same swap direction`,
      );
    }
    seen.add(key);
  }
}

/**
 * Enforce all execution invariants in order.
 *
 * Call this function after quoting a candidate route and before promoting it
 * to "EXECUTABLE_PROFIT_CANDIDATE" or submitting a payload to the chain.
 *
 * @param steps   - Fully-quoted route steps (at least 2 required for a cycle)
 * @param costs   - All cost components in flashloan-asset raw units
 *
 * @throws InvariantViolationError (with `.invariant` field) on first violation.
 *         The invariants are checked in the order:
 *           1. VENUE_AGNOSTIC
 *           2. DIRECTION_AGNOSTIC
 *           3. VENUE_EXCLUSIVITY
 *           4. PRICE_INVARIANT
 *           5. YIELD_INVARIANT
 */
export function enforceExecutionInvariants(
  steps: QuotedRouteStep[],
  costs: RouteCostsInAsset,
): void {
  if (!steps || steps.length < 2) {
    // This is a precondition failure on the caller, not an invariant violation.
    throw new Error(
      "ROUTE_STRUCTURE_INVALID: route must contain at least 2 steps to form a valid arbitrage cycle",
    );
  }
  enforceVenueAgnostic(steps);
  enforceDirectionAgnostic(steps);
  enforceVenueExclusivity(steps);
  enforcePriceInvariant(steps);
  enforceYieldInvariant(steps, costs);
}
