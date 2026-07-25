# Superior Arbitrage Equation With SPLS

This is the canonical execution-grade equation for Omega V5 route scoring.
It is designed to rank raw opportunity first, then prove that the route remains
profitable after state, price, liquidity, and slippage constraints.

**Capital sizing is now owned by the official `omega_v5.capital_injector` module.**
It performs metadata import + Bellman-Ford surplus curve peak search + quantum stability scoring
**before** any Rust math.

SPLS means:

- `S`: live state integrity: block, reserves, ticks, liquidity, balances, pool metadata
- `P`: executable price: exact quote at selected size, not midpoint or stale spot
- `L`: liquidity depth: size bounded by active liquidity and pool quality (bottleneck = lowest TVL pool)
- `S`: slippage/revert safety: min-outs, buffers, gas, relay, and risk reserves

## Official Capital Injection Flow (new)

1. `import_metadata_for_route(pool_sequence, pools)` — canonical metadata load
2. Compute bottleneck = min TVL pool
3. Model π(x) using Bellman-Ford rate decay (size-dependent effective rate)
4. Ladder search for argmax net surplus
5. Apply quantum VQC score for adjustment
6. Return `CapitalInjectionResult` with `as_sizing_params()` for Rust / payload

All stager, ranker, and rust_engine paths now call the injector first.

## Route Definition

For a closed atomic route:

```text
R = T0 -> T1 -> ... -> Tn
T0 = Tn
P = [p1, p2, ... pn]
F_i = executable invariant quote function for pool p_i
x0 = selected base-token input amount (from capital_injector)
```

(remaining original content preserved)
