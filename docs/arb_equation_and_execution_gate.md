# Apex-Omega Arbitrage Equation and Execution Gate Contract

This document is the canonical pipeline equation for discovery, staging, simulation, and execution on Chain 137.

## 1. Universal Route Form

A route is any closed token cycle:

```text
R = [A0 -> A1 -> A2 -> ... -> An]
where A0 == An
```

- `A0` is the base capital asset.
- `A1..A(n-1)` are mid assets.
- Each hop may use any protocol family, venue, router, adapter, pool, aggregator quote, or RFQ source only if that hop has its own state reader, quote adapter, calldata builder, simulation adapter, and settlement verifier.
- Hop order is not assumed. The only hard requirements are route continuity and final base-asset surplus.

## 2. Per-Hop Quote Equation

For an input amount `x_i` of token `A_i`, hop `i` produces:

```text
x_{i+1} = Q_i(A_i, A_{i+1}, x_i, S_i, F_i)
```

Where:

- `Q_i` is the protocol-specific exact quote function.
- `S_i` is the same-block pool or venue state.
- `F_i` is the protocol fee, dynamic fee, aggregator fee, or quoted fee.

`Q_i` must be selected by invariant family:

```text
V2 CPMM:              amountOut = amountInAfterFee * reserveOut / (reserveIn + amountInAfterFee)
V3 / Algebra CLMM:    tick-aware exact input quote, tick crossing, liquidity net, fee rounding
Curve StableSwap:     get_dy / get_dy_underlying stable invariant
Balancer Weighted:    weighted invariant with normalized weights and scaling
DODO PMM:             PMM sellBase / sellQuote curve
Kyber Elastic:        Kyber exact CLMM-style quote semantics
Aggregator/RFQ:       provider-returned exact quote with target, allowance target, calldata, expiry, minOut
```

If the correct `Q_i` is unavailable, stale, unproven, or not block-aligned, the hop is discovery-only and cannot execute.

## 3. Route Output Equation

Given starting base principal `P_base`:

```text
x_0 = P_base
x_1 = Q_0(x_0)
x_2 = Q_1(x_1)
...
x_n = Q_{n-1}(x_{n-1})
```

Because the route is closed:

```text
A_n == A_0
base_out = x_n
```

The raw market edge is:

```text
raw_delta_base = base_out - P_base
raw_delta_usd  = raw_delta_base * USD(A0, settlement_block)
raw_delta_bps  = ((base_out / P_base) - 1) * 10_000
```

## 4. Two-Leg Buy-Low / Sell-High Specialization

For a two-leg route:

```text
A -> M -> A
```

The buy leg must select the lowest executable buy price for the mid token:

```text
buy_price_A_per_M = A_in / M_out
```

The sell leg must sell the mid token back into the base asset at a higher executable price:

```text
sell_price_A_per_M = A_out / M_in
```

The sequence is valid only if:

```text
buy_price_A_per_M < sell_price_A_per_M
```

The two-leg spread identity is:

```text
mid_acquired       = P_base / buy_price_A_per_M
base_out           = mid_acquired * sell_price_A_per_M
raw_delta_base     = base_out - P_base
raw_delta_base     = mid_acquired * (sell_price_A_per_M - buy_price_A_per_M)
```

This rule is a specialization only. Multi-hop cycles are judged by final base surplus and route continuity.

## 5. Economic Net Equation

The pipeline must never treat minimum profit as an expense. It is a gate threshold.

```text
gross_surplus_usd = gross_sell_out_usd - flash_principal_usd

total_costs_usd =
    flash_fee_usd
  + gas_cost_usd
  + relay_tip_usd
  + builder_fee_usd
  + risk_buffer_usd
  + slippage_buffer_usd
  + impact_penalty_usd
  + protocol_specific_fees_usd

economic_net_profit_usd = gross_surplus_usd - total_costs_usd
headroom_usd            = economic_net_profit_usd - minimum_profit_usd
```

The economic gate passes only if:

```text
economic_net_profit_usd >= minimum_profit_usd
headroom_usd >= 0
```

## 6. Raw Executor Gate

The final raw base-token gate is authoritative before payload staging:

```text
sell_amount_out_raw >=
    flash_principal_raw
  + flash_fee_raw
  + gas_cost_raw
  + relay_cost_raw
  + risk_buffer_raw
  + minimum_profit_raw
```

This is the last mathematical gate before nonce reservation and broadcast.

## 7. Cross-Protocol Comparable Discovery

All routes are normalized into the same comparable unit:

```text
score_key = (
    base_asset,
    base_out,
    raw_delta_bps,
    raw_delta_usd,
    economic_net_profit_usd,
    block_number,
    route_identity_hash
)
```

This makes V2, V3, Algebra, Curve, Balancer, DODO, Kyber, aggregator, and RFQ routes comparable only after each hop is normalized to base-asset output at the same block.

## 8. Executable Coverage Rule

Discovery can be broad. Execution is fail-closed.

A route from any DEX, any asset, any order, or any protocol family is executable only when every leg passes all gates:

```text
for every hop:
  token metadata valid
  token behavior supported
  protocol ID aligned
  pool or venue has bytecode
  state read pinned to same block
  invariant quote adapter available
  calldata adapter available
  recipient is executor
  allowance/approval path valid
  flash capital source available
  source adapter configured on executor
  route pool kind allowlisted when enforced
  exact eth_call passes
  fork simulation passes when required
  settlement balance delta verifies base surplus
```

If any gate fails, route status must be one of:

```text
DISCOVERY_ONLY
MATH_ONLY
CALLDATA_SUPPORTED_BUT_UNSIMULATED
SIMULATION_REJECTED
EXECUTION_REJECTED
```

It must not be broadcast.

## 9. Current Implementation Anchors

- Discovery/ranking: `omega_v5.route_execution_stager.pre_rank_routes`
- Staging: `omega_v5.route_execution_stager.stage_pre_ranked_route`
- Exact quote gate: `omega_v5.executable_quotes.quote_route_for_executor`
- Raw execution gate: `omega_v5.execution.payload_stager.stage_payload`
- Economics: `omega_v5.flash_loan.calculate_route_economics`
- Protocol IDs: `omega_v5.config.PROTOCOL_ID_MAP`
- Executable source adapters: `omega_v5.adapter_registry.require_executable_source_adapter`

## 10. Broadcast Verdict

A route is broadcast-eligible only if:

```text
route_continuity_pass
and pool_exclusivity_pass
and protocol_id_alignment_pass
and exact_quote_pass
and economic_net_profit_usd >= minimum_profit_usd
and raw_executor_gate_pass
and exact_eth_call_pass
and source_adapter_pass
and execution_armed
```

Otherwise the route may be discovered, ranked, logged, and audited, but not executed.
