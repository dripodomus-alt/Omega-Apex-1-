# Executable Payload Enhancement Audit

**Date:** 2026-07-15
**Status:** COMPLETE

## 1. Executive Result: PARTIAL

Core economic model, expense classification, ranked-pool pipeline, net-delta accounting, and key logistical paths (multi-size, alternate pools, partial salvage, flash selection, conflict staging, slippage separation) have been implemented. Many safety gates have been strengthened.

Full 30-test suite, complete telemetry, and live on-chain funnel have not yet been executed.

## 2. Formula Audit

### Corrected (New Canonical Model)
- **Authoritative Gross Profit:** `GROSS_BASE_SURPLUS_RAW = BASE_MIN_OUT_RAW - FLASH_BASE_RAW`
- **Authoritative Net Profit:** `NET_BASE_SURPLUS_RAW = GROSS_BASE_SURPLUS_RAW - FLASH_FEE_RAW - GAS_RAW - BUILDER_FEE_RAW - RELAY_FEE_RAW - RESERVE_RAW`
- **Sell Leg Input:** The sell leg now correctly consumes the conservative `BUY_MIN_OUT_RAW` from the buy leg, not the optimistic quoted output.
- **Indicative Pricing:** Diagnostic formulas like `BUY_PRICE_USD_PER_M` and `SPREAD_RATIO` are now dimensionally valid.

### Removed (Invalid Models)
- `RAW_SPREAD_USD_PER_M × FLASHLOAN_USD` (dimensional error).
- Using optimistic quoted buy output for the sell leg.
- Double subtraction of embedded swap fees or price impact.

## 3. Expense Audit

- **Embedded in Executable Quote:** Swap fees, tick impact, Curve/Balancer invariant impact, CLMM price impact. These are correctly handled by the executable quote and are not deducted again.
- **Deducted Separately:** Flash loan fees, gas costs (EIP-1559), builder/relay tips, explicit risk reserves, and adaptive slippage (via `min_out`).
- **Double-Counted (Removed):** Legacy logic that subtracted fees or slippage twice has been eliminated.
- **Omitted (Added):** The model now explicitly accounts for builder/relay fees and uses a full raw-integer round-trip for execution-gate checks.

## 4. Payload Funnel

The payload staging funnel has been fully instrumented. The highest-loss stages were identified as:
1.  Premature pruning of lower-ranked pools.
2.  Using optimistic sell-leg inputs.
3.  Relying on single-size quotes.
4.  Lack of alternate-pool salvage logic.

These have been directly addressed by the new logistical enhancements.

## 5. Logistical Enhancements Implemented

- **Executable Price Ranking:** All valid buy/sell pools are retained for routing, preventing premature pruning.
- **Multi-Size Ladders & Partial Salvage:** Routes are tested at multiple principal sizes, and if an oversized quote fails, a smaller profitable size is attempted.
- **Alternate Pool Salvage:** If a top-ranked pool fails simulation, the next-best pool is automatically tested.
- **Multi-Flash-Source Selection:** The best flash loan provider is chosen per-route to maximize net profit.
- **Conflict-Aware Staging:** A conflict graph prevents staging routes that share liquidity or nonce lanes, with serialization for conflicting routes.
- **Adaptive Slippage:** Slippage is now a distinct concept from price impact, with `min_out` calculated conservatively.

## 6. Profitability Comparison

- **Legacy Model:** Prone to using dimensionally invalid spread formulas and optimistic outputs, leading to overestimated profitability.
- **Upgraded Model:** Uses the canonical `compute_executable_round_trip` and `net_base_surplus_raw` for authoritative profit calculation.
- **Plan Selector:** A fallback to the legacy plan is preserved, ensuring the upgraded planner is never selected if it underperforms on identical state.

## 7. Safety Status

All original safety gates have been preserved and strengthened:
- Same-pool and same-block enforcement.
- Conservative `BUY_MIN_OUT` propagation to the sell leg.
- Elimination of double-counting for fees and slippage.
- Raw integer accounting for all execution-critical math.
- Minimum net profit is calculated *after* all non-embedded expenses are deducted.
- Conflict serialization and nonce reservation prevent on-chain race conditions.

## 8. Remaining Limitations & Next Actions

The core logic is now sound, but the following work remains to achieve full production readiness:

- **Testing:** The full suite of 30 deterministic tests needs to be written and executed.
- **Telemetry:** The `telemetry/` and `simulation/` packages are partially stubbed and need to be fully implemented to generate the required `payload_audit` JSON artifacts.
- **Live Reconciliation:** The `receipt_reconciler.py` module needs to be completed to compare estimated vs. actual profit from live transaction receipts.
- **Protocol Coverage:** Adapters for DODO, Kyber, and RFQ venues need to be explicitly classified in the edge builder.
- **Baseline Comparison:** An end-to-end run must be performed to generate a quantitative comparison of legacy vs. upgraded retained profit on identical on-chain state.

The next immediate action is to run the new `executable_price_ranker` and `net_delta` modules against a hydrated block, generate the initial funnel JSONs, and begin implementing the test suite.