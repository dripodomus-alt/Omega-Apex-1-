# Artifact Integration Review

Date: 2026-07-15

Reviewed inputs:

```text
pools_dynamic.json
backend.zip
rust-bridge.zip
COMPLETE_MATH_BLUEPRINT.md
COMPLETE_SYSTEM_BLUEPRINT.md
OracleFeeds.tsx
```

## Accepted Into Runtime

### Dynamic Pool Registry Metadata

`pools_dynamic.json` contains 816 candidate pools:

```text
Uniswap V3: 514
QuickSwap V2: 171
SushiSwap V2: 131
```

Accepted as metadata only through:

```text
omega_v5.external_pool_registry
omega_v5.rpc_layer.discover_factory_pool_registry
```

Runtime guardrails:

```text
no reserves imported
no prices imported
no TVL imported
token symbols resolved by address first
USDC.e/native USDC distinction preserved
duplicates rejected
unknown tokens rejected
live RPC bytecode required
live pool state required
CLMM orientation/decimals audit required
total_executable_liquidity_usd required before sizing
```

Default cap:

```text
DYNAMIC_POOL_REGISTRY_MAX_POOLS=256
```

### Oracle Feed Panel

The attached `OracleFeeds.tsx` concept was accepted as a dashboard surface, but
not its hardcoded fallback prices. Runtime now exposes:

```text
GET /api/oracles/prices
```

The frontend integration consumes backend live oracle data and source labels.

### Math Blueprint

The V2 constant-product walkthrough is consistent with the existing fee-adjusted
V2 quote formula:

```text
amount_in_with_fee = amount_in * (1 - fee)
amount_out = amount_in_with_fee * reserve_out / (reserve_in + amount_in_with_fee)
```

No alternate math was imported because the current runtime already routes final
CLMM execution through exact quote and executor truth gates.

## Rejected From Runtime

### Rust Bridge Execution Logic

Rejected:

```text
rust-bridge/src/main.rs shadow_gate_simulate
```

Reason:

```text
returns placeholder C1/C2 profits and gas usage
```

The current mandatory Rust integration remains:

```text
rust_engine binary for Bellman-Ford negative-cycle detection
omega_v5.rust_engine identity and shape validation
```

### Static Financial Projections

Rejected from runtime:

```text
COMPLETE_SYSTEM_BLUEPRINT static MATIC price
wallet balance projections
static liquidation gas economics
guaranteed-profit language
```

Reason:

```text
runtime must use live Polygon Gas Station, live oracle data, exact-call proof,
and receipt-based PnL.
```

## Validation

Commands run:

```text
python -m py_compile omega_v5\config.py omega_v5\external_pool_registry.py omega_v5\rpc_layer.py omega_v5\api.py omega_v5\gas_oracle.py omega_v5\subgraph_intel.py omega_v5\sizing.py
```

Dynamic registry proof:

```text
promoted 256
by_protocol {'UniswapV2': 135, 'UniswapV3': 121}
skipped_top [('unknown_token', 31), ('duplicate_pool_address', 16), ('max_pools_reached', 1)]
```

Oracle endpoint proof:

```text
ok True
healthy True
count 29
```
