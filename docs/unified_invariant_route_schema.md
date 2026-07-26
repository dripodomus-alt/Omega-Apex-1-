# Unified Invariant Route Schema (updated)

## Key Additions from Implementation Plan
- **protocol_ids**: Integer array from `config.build_protocol_sequence_ids()` – ensures payload encoding lines up with `PROTOCOL_ID_MAP` and `PROTOCOL_REGISTRY`.
- **sequence_proof**: Explicit `buy_low_sell_high` verification using `invariant_math.verify_buy_low_sell_high_sequence()`. All staged routes must pass or are rejected.
- **payload.protocol_id_alignment**: "verified" flag added in `payload_envelope.py`.

This closes the highest-risk gaps in execution payload and stager.

See `omega_v5/config.py`, `invariant_math.py`, `route_execution_stager.py`, `pipeline_validation.py` for implementation.
