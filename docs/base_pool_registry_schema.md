# Base Pool Registry Schema

Schema id: `omega_v5.base_pool_registry.v1`

Every pool that enters discovery, ranking, route sizing, reports, or execution
must be normalized into this shape. Protocol-specific fields may be present, but
these base fields are required.

## Required Fields

```text
pool_id
registry_id
chain_id
address
protocol
pool_family
route_class
liquidity_key
tokens[]
token_addresses[]
token_decimals[]
fee_bps | swap_fee
tvl_usd
total_executable_liquidity_usd
executable_token_depth_usd
liquidity_source
liquidity_block
adapter_status
execution_status
promotion_stage
_meta.base_pool_registry_schema
_meta.total_executable_liquidity_source
```

## Liquidity Contract

`total_executable_liquidity_usd` is the canonical value used for flashloan
sizing and route-depth ranking. It is not a marketing TVL number.

Source priority:

```text
1. Reserve x verified oracle price, summed across live token balances.
2. CLMM active virtual reserve x verified oracle price from sqrtPriceX96 + liquidity.
3. Conservative min(CLMM active virtual liquidity, hydrated pool TVL), when both exist.
4. Verified live pool TVL when token-side state cannot be valued.
5. Zero, with source = unavailable.
```

For each token in the pool:

```text
executable_token_depth_usd[token] =
    live reserve(token) * verified USD price(token)
```

When only pool-level TVL exists and token-side depth cannot be read, token depth
may be marked as an even split estimate for diagnostics only. Exact execution
still requires quote and executor truth gates.

## Sizing Rule

For a route with pools `p1...pn`:

```text
RouteExecutableLiquidityUSD =
    min(total_executable_liquidity_usd[p] for p in route)
```

Candidate flashloan principals are evaluated at:

```text
10% * RouteExecutableLiquidityUSD
15% * RouteExecutableLiquidityUSD
```

and capped by:

```text
MAX_FLASH_PRINCIPAL_USD
requested_principal_usd
```

Routes below `MIN_FLASH_PRINCIPAL_USD` are rejected rather than resized into
toy notional values.

## Dynamic Registry Sources

The base registry is intentionally a composed registry, not a static list. The
runtime registry may include:

```text
1. Curated base pools embedded in rpc_layer.DEEP_POOL_REGISTRY.
2. Dynamic V2/V3 metadata from omega_v5/data/pools_dynamic.json.
3. Official Curve Polygon pool metadata from https://api.curve.fi/api.
4. Factory-discovered V2/V3/Algebra pools verified by live bytecode.
5. Polygon token-list candidates used as discovery probes only.
6. Subgraph hints, only after RPC bytecode/state verification.
```

Curve registry rows are metadata-only until the pool's Polygon contract returns
live `coins()` and `balances()` successfully. API `usdTotal` is allowed only as
a TVL seed for `total_executable_liquidity_usd`; it does not bypass quote,
route-kind, payload, exact-call, or executor truth gates.

## Execution Gate

No pool is rankable or executable when:

```text
total_executable_liquidity_usd <= 0
```

No route is executable until the final executor truth gate proves:

```text
QuoteFinalLeg(...QuoteLeg1(P)) >
P + flash_fee + gas + relay_tip + risk_buffer + minimum_profit
```
