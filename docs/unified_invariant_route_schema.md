# Unified Invariant Route Schema

Schema id: `omega_v5.unified_invariant_route.v1`

Purpose: one route schema that can describe discovery, ranking, quote proof,
payload construction, exact-call validation, and post-trade accounting across
all supported invariant families.

The schema is intentionally split into:

- route identity
- capital source
- ordered hop semantics
- protocol-specific invariant state
- quote chain
- USD and raw-unit accounting
- execution gates
- proof and trace metadata

This prevents mixing principal, units, spread, raw delta, expenses, and executor
truth.

## Precision Pricing Layer (new canonical requirement)

All USD and cross-token accounting **MUST** be performed with the
`PrecisionPricingEngine` (Python port of the APEX Ω TS engine) or its pure
helper functions:

- `PRICE_SCALE = 10**18`
- `token_atomic_to_usd_x18`
- `usd_x18_to_token_atomic`
- `mul_div`
- `derive_pair_price` / `quote_per_base_x18`
- `convert_token_atomic`
- `executable_price_x18`

All values are integers. No JavaScript Number / Python float / loose Decimal
is allowed for monetary results that reach execution or payload construction.

Oracle observations are validated with:
- maxAgeSeconds
- maxBlockLag
- minimumValidSources
- maximumDeviationBps
- minimumConfidenceBps
- aggregation (MEDIAN / CONSERVATIVE_LOW / CONSERVATIVE_HIGH)

Stale, divergent, low-confidence, or incomplete-round observations are rejected
with explicit `PricingError` codes that map 1:1 to the TS implementation.

See:
- `omega_v5/pricing/precision_pricing.py`
- `omega_v5/units.py` (precision bridges)
- `omega_v5/oracle_layer.py` (LegacyOracleSource adapter)

## Execution Doctrine And Dynamic Envelope Canon

### Canon Lock

```text
System: OMEGA_V5
Mode: multi-protocol live scanner + RustMath staging + execution-ready route envelope
Chain: Polygon PoS / Chain ID 137
Scanner status: Python production-ready
RustMath status: next build layer
Hybrid status: incomplete until Rust crate + PyO3 bindings + Python wrapper + benchmark harness
```

The envelope must carry:

- `principal_raw`
- `min_out_raw` per leg (exact on-chain simulation truth)
- `gross_profit_raw`
- `expenses` broken into:
  - flash_loan_fee_raw
  - gas_cost_usd_x18 (converted via precision engine)
  - relay_tip_usd_x18
- `net_profit_usd_x18` (final canonical number)

All conversions between raw token units and USD must go through the
precision engine so that the numbers that reach the executor are bit-identical
to what a reference TS implementation would compute.

## Route Identity

```json
{
  "opp_id": "string",
  "path": ["0x..", "0x.."],
  "pool_sequence": ["0x..", "0x.."],
  "protocol_seq": ["UNISWAP_V2", "QUICKSWAP_V3"],
  "hop_count": 2
}
```

## Capital Source

```json
{
  "capital_source": "AAVE_V3_FLASH" | "BALANCER_FLASH" | ...,
  "principal_token": "0x...",
  "principal_raw": "123456789000000000000"
}
```

## Quote Chain (example 2-hop)

```json
{
  "quote_chain": [
    {
      "leg": 1,
      "action": "BUY",
      "pool": "0x...",
      "amount_in_raw": "...",
      "amount_out_raw": "...",
      "price_x18": "..."   // produced by executablePriceX18 or equivalent
    },
    ...
  ]
}
```

## USD Accounting (must be x18)

```json
{
  "profitability": {
    "gross_out_usd_x18": "...",
    "flash_loan_fee_usd_x18": "...",
    "gas_cost_usd_x18": "...",
    "relay_tip_usd_x18": "...",
    "net_profit_usd_x18": "..."
  }
}
```

All fields ending in `_x18` are produced by `PrecisionPricingEngine` or the
pure helpers in `precision_pricing.py`.

## Execution Gates

A route is only executable when:

1. All oracle observations pass the policy (via `get_usd_price`).
2. `raw_execution_gate_passes(net_surplus_raw, min_profit_raw)`.
3. `eth_call` simulation on the executor returns success + correct minOut values.
4. Net profit after all expenses (converted via precision math) > 0.

## Post-Trade Truth

After execution the actual on-chain amounts are fed back through the same
`executable_price_x18` and `net_profit_usd_from_raw` functions to produce the
final accounting record.

This guarantees that the numbers used for ranking, sizing, and P&L are
produced by the identical integer logic that the TS reference engine uses.
