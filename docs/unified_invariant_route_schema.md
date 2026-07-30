# Unified Invariant Route Schema (updated)

## Key Additions from Implementation Plan
- **protocol_ids**: Integer array from `config.build_protocol_sequence_ids()` – ensures payload encoding lines up with `PROTOCOL_ID_MAP` and `PROTOCOL_REGISTRY`.
- **sequence_proof**: Explicit `buy_low_sell_high` verification using `invariant_math.verify_buy_low_sell_high_sequence()`. All staged routes must pass or are rejected.
- **payload.protocol_id_alignment**: "verified" flag added in `payload_envelope.py`.

This closes the highest-risk gaps in execution payload and stager.

See `omega_v5/config.py`, `invariant_math.py`, `route_execution_stager.py`, `pipeline_validation.py` for implementation.

## Canonical Arb Equation

The canonical equation and execution gate contract are defined in `docs/arb_equation_and_execution_gate.md`.

Short form:

```text
base_out = Q_n(...Q_1(Q_0(P_base)))
raw_delta_base = base_out - P_base
economic_net_profit_usd = gross_surplus_usd - total_costs_usd
headroom_usd = economic_net_profit_usd - minimum_profit_usd
execute = all_adapter_gates_pass && exact_eth_call_pass && headroom_usd >= 0
```

Minimum profit is a threshold, not an expense. Unsupported protocol variations remain discovery-only until their exact quote, calldata, simulation, and settlement gates pass.
