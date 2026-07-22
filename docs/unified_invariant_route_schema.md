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


## Execution Doctrine And Dynamic Envelope Canon

### Canon Lock

```text
System: OMEGA_V5
Mode: multi-protocol live scanner + RustMath staging + execution-ready route envelope
Chain: Polygon PoS / Chain ID 137
Scanner status: Python production-ready
RustMath status: next build layer
Hybrid status: incomplete until Rust crate + PyO3 bindings + Python wrapper + benchmark harness exist
```

The scanner is not asset-specific, protocol-specific, or venue-prioritized. It is
a dynamic opportunist engine: any Chain 137 asset, pool, route, or venue may enter
if it satisfies eligibility gates and produces a live executable quote.

### C1 / C2 Semantics

```text
C1 = first execution cycle
C2 = second execution cycle after confirmed C1 mutation
LEG1 = buy-side swap inside one execution cycle
LEG2 = sell-side swap inside one execution cycle
```

C1 and C2 are execution cycles, not swap legs. C2 cannot inherit C1 assumptions
and cannot be pre-bundled as deterministic. C2 is valid only after all of the
following are true:

```text
C1 is confirmed
C1 receipt is successful
post-C1 state is observed
post-C1 state block > C1 block
post-C1 state hash differs from pre-C1 state hash
opportunity is recomputed from updated state
```

### Core Pipeline

```text
Polygon Chain 137 RPC / WSS
  -> multi-protocol pool discovery
  -> pool-native state intake
  -> TVL / TLV eligibility gate
  -> executable quote extraction
  -> destination normalization
  -> same-pool rejection
  -> comparable-market grouping
  -> unified opportunity object created
  -> staging: freeze opp_id, route, principal intent, flash source, block
  -> math: Rust/Python profitability and invariant math
  -> lowest executable buy price ranking
  -> highest executable sell price ranking
  -> route edge validation
  -> optimal sizing
  -> simulation
  -> transaction build
  -> bundle batching
  -> private broadcast / dry-run broadcast
  -> receipt verification
  -> C1/C2 state-machine ledger
```

Pipeline truth: scanner finds eligible markets; RustMath ranks executable price
surfaces; simulation proves viability; transaction builder converts route
envelopes into calldata; bundle layer preserves state isolation; broadcaster
submits privately or dry-runs; ledger records state truth.

### Supported Scanner Scope

Protocol families must use separate adapters. Flashloan capital is a liquidity
source, not a pricing venue.

```text
1. V2 CPMM
   QuickSwap V2, SushiSwap V2, ApeSwap, Dfyn, Uniswap V2-compatible factories

2. V3 / CLMM
   Uniswap V3, SushiSwap V3, Uniswap V3-compatible deployments

3. Algebra CLMM
   QuickSwap Algebra and Algebra-compatible concentrated-liquidity venues

4. Balancer Weighted Pools
   Balancer pool surfaces with pool_id-aware destination identity

5. Curve Stable Pools
   Registry / factory discovered Curve stable pools and swap invariant surfaces

6. Flashloan Capital Layer
   Balancer unlock/settle logic, Aave-style sources, and available base-token capital
```

Forbidden adapter shortcuts:

```text
forcing Algebra through Uniswap V3 ABI
forcing all CLMM venues through one factory method
treating flashloan source as a pricing venue
ranking by preferred protocol
ranking by preferred token
ranking by static route template
```

### Dynamic Opportunist Rules

```text
No asset allowlist or blacklist for opportunity ranking.
No protocol allowlist or priority for opportunity ranking.
No venue priority.
No fixed DEX route template.
No USDC/WETH hardcode.
No QuickSwap/Sushi hardcode.
No fixed stablecoin-only path.
No same-pool round trip.
```

A route may enter only when:

```text
chain_id == 137
pool-native TVL / TLV is present
pool-native TVL / TLV >= 50000 USD-equivalent
live executable quote exists
destination identity is normalized
there are 2+ comparable executable destinations
buy and sell destinations are distinct
buy pool/address/id differs from sell pool/address/id
pool invariant family is supported
state is fresh and block-anchored
```

### Eligibility Gate

Every pool-native quote row must pass:

```text
chain_id == 137
pool_tvl_usd is present and >= 50000
is_live_executable == true
executable_price, amount_in, amount_out are present
asset_in and asset_out are present
destination_id and pool_address_or_id are present
invariant_family is supported
block_number is present
```

Hard row rejects:

```text
missing_tvl_usd_required_for_pool_native_candidate
tvl_below_gate
missing_executable_quote
missing_destination_identity
missing_pool_identity
unsupported_invariant_family
invalid_reserve_or_liquidity_state
stale_block_state
malformed_quote_row
wrong_chain_id
```

Hard candidate rejects:

```text
less_than_two_comparable_executable_destinations
same_destination_round_trip
same_pool_round_trip
buy_price_not_below_sell_price
route_edge_invalid
optimal_size_invalid
simulation_required_before_execution
```

### Destination Normalization

```text
V2 CPMM: chain_id + factory + pair_address
V3 / CLMM: chain_id + factory + pool_address + fee_tier
Algebra CLMM: chain_id + factory + pool_address
Balancer Weighted: chain_id + vault + pool_id
Curve Stable: chain_id + registry_or_factory + pool_address_or_pool_id
Flashloan Capital: chain_id + lending_provider + asset, never ranked as buy/sell venue
```

Same-pool rejection requires both:

```text
buy.destination_id != sell.destination_id
buy.pool_address_or_id != sell.pool_address_or_id
```

For Balancer, `pool_id` is the primary destination identity when present.

### Comparable-Market Grouping

Canonical comparable key:

```text
chain_id|asset_in_address|asset_out_address|amount_in_raw|quote_direction|quote_unit
```

Assets must be address-normalized. Symbols are display metadata only. Decimals
must be normalized. Amounts must be raw-unit safe. Comparable rows must represent
the same trade direction and quote basis at the observed block state.

Forbidden comparable keys include symbol-only identity, venue-dependent identity,
protocol-dependent identity, and non-decimal-normalized amount keys.

### RustMath Staging Contract

RustMath is the deterministic math authority once the scanner emits eligible,
normalized state.

```text
RustMath owns quote normalization, fee-adjusted executable price, CPMM math,
V3 and Algebra tick-aware math, Balancer weighted math, Curve stable math,
slippage curves, optimal sizing, route edge validation, buy/sell ranking,
candidate hashing, state hashing, fixed-point profit identity, and benchmarks.
```

RustMath must not contain asset-specific ranking logic, protocol favoritism,
venue priority, symbol hardcodes, route-template hardcodes, or float math for
final price/profit/state comparison.

### Ranking Doctrine

For every comparable market group:

```text
BUY_LEG1 = destination with the lowest executable buy price
SELL_LEG2 = destination with the highest executable sell price
BUY_LEG1_EXECUTABLE_PRICE < SELL_LEG2_EXECUTABLE_PRICE
raw_spread = sell_leg2_executable_price - buy_leg1_executable_price
raw_spread_bps = raw_spread / buy_leg1_executable_price * 10000
```

A candidate passes only if price delta and spread bps are positive, same-pool and
same-destination rejection pass, route edge validates, optimal size is nonzero,
and simulation later confirms executable net profit.

### Route Edge Validation

```text
LEG1 buy venue can receive asset_in and output asset_out
LEG2 sell venue can receive asset_out and output asset_in or settlement asset
LEG1 output can become LEG2 input
asset decimals are known
token approvals or permit path are known
router/adapter path exists
calldata surface is constructible
deadline policy exists
min_out policy exists
```

Reject if output cannot feed the next leg, adapter/calldata is unavailable, pool
state is stale, quote is indicative but not executable, the route requires an
unsupported callback, or token transfer behavior is unsafe and unmodeled.

### Optimal Sizing

RustMath owns dynamic route-specific sizing. Default ladder:

```text
0.001 x eligible liquidity
0.0025 x eligible liquidity
0.005 x eligible liquidity
0.01 x eligible liquidity
0.02 x eligible liquidity
0.03 x eligible liquidity
0.05 x eligible liquidity
```

Safety cap:

```text
flash_size <= 0.15 x first-leg executable liquidity / TVL basis
```

Stop when marginal profit decreases or `dP/dx < 0`. Sizing must include pool fees,
price impact, slippage, gas estimate, flashloan fee, adapter cost, settlement
asset, and route-edge inventory handoff.

### Fee Conversion Alignment

Every fee starts in its native unit and is converted into the same normalized USD
unit exactly once. Route math may only sum normalized `fee_usd` values from the
fee ledger.

Canonical rule:

```text
native fee amount -> asset decimals -> asset USD price -> fee_usd/NUSD
```

Required fee component record:

```json
{
  "fee_component": "leg1_pool_fee",
  "chain_id": 137,
  "block_number": 73920000,
  "asset": {
    "address": "0x...",
    "symbol": "display_only",
    "decimals": 6
  },
  "native_amount_raw": "3000000",
  "native_amount_decimal": "3.0",
  "usd_price": "1.0001",
  "fee_usd": "3.0003",
  "price_source": "oracle_or_twap",
  "calibration_id": "omega_v5.nusd.v1:sha256",
  "state_hash": "sha256_fee_inputs"
}
```

Gas conversion:

```text
gas_fee_native = gas_used * gas_price_wei / 1e18
gas_fee_usd = gas_fee_native * POL_usd_price
```

Flashloan conversion:

```text
flashloan_fee_raw = principal_raw * flashloan_fee_bps / 10000
flashloan_fee_usd = flashloan_fee_decimal * borrowed_asset_usd_price
```

Fee components to normalize:

```text
leg1_pool_fee
leg2_pool_fee
gas_fee
flashloan_fee
adapter_fee
relay_fee
builder_tip
approval_fee
slippage_buffer
price_impact_cost
```

Hard rejects:

```text
missing_fee_asset
missing_fee_decimals
missing_fee_usd_price
fee_block_mismatch
fee_calibration_mismatch
negative_fee_without_rebate_policy
raw_fee_summed_with_usd_fee
gas_fee_missing_pol_price
flashloan_fee_missing_borrowed_asset_price
```

Unified envelope placement:

```json
{
  "fees": {
    "schema_version": "omega_v5.fee_ledger.v1",
    "calibration_id": "omega_v5.nusd.v1:sha256",
    "normalized_unit": "NUSD",
    "total_fee_usd": "14.2381",
    "components": []
  }
}
```

The route-level net equation must consume only the ledger total:

```text
net_profit_usd = final_value_usd - initial_value_usd - fees.total_fee_usd
```

This prevents raw units, gas units, token decimals, and USD values from being
mixed incorrectly.

### Simulation And Transaction Build

Simulation begins only after RustMath ranking and optimal sizing. No simulation
pass means no transaction build. Live transaction build requires real calldata,
fresh nonce, approved executor, valid adapter path, successful simulation hash,
private relay configuration, and receipt verification. Synthetic calldata is
forbidden in live mode.

### Bundle And C1/C2 State Machine

Bundle batching is state-isolated. Rejected bundle shapes include C1 and its own
C2 in the same bundle, nonce collisions, same-pool collisions, route replacement
collisions, duplicate opportunities, cross-opportunity state collisions, expired
route envelopes, and unconfirmed parent state for C2.

Canonical state machine:

```text
DISCOVERED
  -> C1_LOCKED
  -> C1_BUILT
  -> C1_SENT
  -> C1_CONFIRMED
  -> POST_C1_RECOMPUTED
  -> C2_DECIDED
  -> C2_SENT | C2_SKIPPED | C2_EXPIRED
  -> CLOSED
```

C2 may execute only from `C1 block + 1` through `C1 block + 5`. Valid C2 actions
are `MIRROR`, `REVERSE`, `DO_NOTHING`, and `EXPIRE`.

### Typed Route Identity Layers

Route identity must be deterministic across Python, Rust, Solidity, and storage
layers. String-concatenated IDs are forbidden for canonical identity.

Canonical encoding:

```text
keccak256(abi.encode(...))
```

Identity layers are separated:

```text
route_pair_id = immutable ordered route definition at a block hash
quote_snapshot_id = route_pair_id plus exact input-size snapshot
simulation_id = execution proof for a quote snapshot
execution_attempt_id = one submission attempt
transaction_hash = chain inclusion artifact
```

`block_number` is not sufficient identity because a reorg can replace the state
behind that number. Canonical identity uses `block_hash`. Offline dry runs may use
a synthetic block hash only when marked with `block_hash_source =
offline_synthetic_block_hash`; live execution must use an RPC-proven block hash.

Destination identity is canonicalized before route identity:

```text
destination_id = keccak256(abi.encode(
  chain_id,
  protocol_family,
  factory_or_vault,
  pool_id,
  fee_tier
))
```

Ordered route identity is direction-safe:

```text
route_pair_id = keccak256(abi.encode(
  schema_version,
  chain_id,
  block_hash,
  settlement_asset,
  base_asset,
  leg1_destination_id,
  leg2_destination_id
))
```

Therefore:

```text
route(A -> B) != route(B -> A)
```

Quote snapshot identity is size-specific:

```text
quote_snapshot_id = keccak256(abi.encode(
  schema_version,
  route_pair_id,
  initial_amount_raw
))
```

Mandatory route invariants before ranking/execution:

```text
LEG1.asset_in == settlement_asset
LEG1.asset_out == base_asset
LEG2.asset_in == base_asset
LEG2.asset_out == settlement_asset
LEG1.destination_id != LEG2.destination_id
initial_amount_raw == LEG1.amount_in_raw when raw units are available
```

If a current stage does not yet have asset-decimal-safe `initial_amount_raw`, it
must mark `initial_amount_raw_status = unresolved_at_current_stager_boundary` and
must not pretend that display USD, symbols, or decimals are raw token units.

C1/C2 contamination rule:

```text
C1 route identity binds pre-C1 block_hash.
C2 route identity binds post-C1 block_hash after receipt-confirmed recompute.
```

### Candidate And Route Views Inside The Unified Object

The runtime schema remains `omega_v5.unified_invariant_route.v1`. Candidate and
route envelope names such as `apex_omega_candidate_v1` and
`apex_omega_route_envelope_v1` are compatibility/view labels only; they must not
become separate runtime schema owners.

Candidate view lives under `ranking`; route-envelope view lives under `staging`
and `payload` of the same `UnifiedRouteEnvelope`.

Canonical dynamic candidate view:

```json
{
  "view_schema": "apex_omega_candidate_v1",
  "chain_id": 137,
  "cycle": "C1",
  "comparable_key": "<chain_id>|<asset_in_address>|<asset_out_address>|<amount_in_raw>|<quote_direction>|<quote_unit>",
  "selection_rule": "lowest_executable_buy_price_vs_highest_executable_sell_price",
  "opportunist_mode": true,
  "buy": "<dynamic_buy_quote_row>",
  "sell": "<dynamic_sell_quote_row>",
  "buy_leg1_executable_price": "<dynamic_fixed_point_price>",
  "sell_leg2_executable_price": "<dynamic_fixed_point_price>",
  "price_delta": "<dynamic_fixed_point_delta>",
  "raw_spread_bps": "<dynamic_fixed_point_bps>",
  "candidate_hash": "<sha256_candidate_hash>"
}
```

Canonical dynamic route-envelope view:

```json
{
  "view_schema": "apex_omega_route_envelope_v1",
  "chain_id": 137,
  "cycle": "C1",
  "opportunity_id": "<candidate_hash_or_frozen_opp_id>",
  "route_hash": "<sha256_route_hash>",
  "comparable_key": "<dynamic_comparable_market_key>",
  "selection_rule": "lowest_executable_buy_price_vs_highest_executable_sell_price",
  "opportunist_mode": true,
  "asset_path": ["<input_asset>", "<intermediate_asset>", "<settlement_asset>"],
  "amounts": "<raw-unit-safe_amount_object>",
  "prices": "<fixed-point_price_object>",
  "gate_assertions": {
    "asset_blacklist_enabled": false,
    "protocol_priority_enabled": false,
    "same_pool_round_trip_allowed": false,
    "requires_two_or_more_comparable_destinations": true,
    "buy_price_must_be_below_sell_price": true,
    "min_pool_tvl_usd": "50000"
  },
  "legs": ["<LEG1>", "<LEG2>"],
  "simulation": {"required": true, "simulation_hash": null, "status": "pending"},
  "execution": {
    "mode": "dry_run",
    "calldata_required_for_live": true,
    "private_broadcast_first": true,
    "public_fallback_enabled": false
  }
}
```

Example values may use USDC/WETH or named venues for tests, but schema and route
logic must not depend on those values.

### Runtime Outputs

```text
outputs/run_manifest.json
outputs/raw_pool_rows.jsonl
outputs/normalized_quote_rows.jsonl
outputs/ranked_price_surface.jsonl
outputs/valid_candidates.jsonl
outputs/rejected_rows.jsonl
outputs/rejected_candidates.jsonl
outputs/route_envelopes.jsonl
outputs/simulation_results.jsonl
outputs/transaction_envelopes.jsonl
outputs/receipt_ledger.jsonl
outputs/scanner_summary.json
outputs/benchmarks/rustmath_bench.json
outputs/benchmarks/rustmath_bench.csv
```

Required scanner summary fields include scanner name, chain id, hybrid mode,
RustMath enabled flag, min pool TVL, no asset blacklist, no protocol priority,
same-pool rejection enabled, dynamic row/candidate counts, latest block, output
schema version, and completion status.

### Final Doctrine

The Python scanner can be production-ready before the hybrid layer is complete.
Do not call the system a complete hybrid implementation until the Rust crate,
PyO3 bindings, Python wrapper, and benchmark harness exist.

Every opportunity must be proven from live Chain 137 state, executable quote
surfaces, TVL eligibility, destination distinctness, RustMath ranking, simulation,
transaction build, and receipt verification.


## Progressive Pipeline Collection

Runtime owner: `omega_v5.payload_envelope.UnifiedRouteEnvelope`.

The opportunity is one object for the full path. Each pipeline stage owns one bucket
inside that object and may only add its own parameters. The route identity remains
wrapped and unbreakable through the entire path:

```text
DISCOVERY / INTAKE / NORMALIZE META
  -> RANKING
  -> STAGING
  -> MATH
  -> QUOTE / SIMULATION
  -> TX CALLDATA BUILD / ENCODE
  -> SUBMISSION
  -> SETTLEMENT / TRACE
```

`STAGING` is required before `MATH`. Staging freezes `opp_id`, route path,
`pool_sequence`, `protocol_seq`, current block, principal intent, flash source,
and slippage policy. Math then consumes that staged setup and fills accounting
outputs such as raw delta, gas, flash fee, slippage buffer, hop fees, and net gain.
If quote or sizing fails before math can run, the same unified envelope is still
attached with the `staging` bucket populated and the `math` bucket empty.

No stage should emit a disconnected schema copy. The row-level field
`unified_route_envelope` carries the accumulated object forward.

## Top-Level Envelope

```json
{
  "schema": "omega_v5.unified_invariant_route.v1",
  "chainId": 137,
  "routeId": "OPP-0001",
  "strategy": "CROSS_POOL_TWO_LEG | PEGGED_STABLE_TWO_LEG | TRIANGLE_ARB | FOUR_LEG_CYCLE | LIQUIDATION_EXIT",
  "authority": "SCANNER_ONLY | C1 | C2 | LIQUIDATION | EXECUTOR_READY",
  "status": "DISCOVERED | RANKED | QUOTE_PROVEN | PAYLOAD_READY | EXACT_CALL_PASSED | REJECTED | SUBMITTED | SETTLED",
  "block": {
    "detected": 0,
    "quoted": 0,
    "validated": 0,
    "maxStalenessBlocks": 1
  },
  "path": ["BASE", "MID", "BASE"],
  "capital": {},
  "hops": [],
  "quoteChain": {},
  "accounting": {},
  "executionGate": {},
  "payload": {},
  "proofs": {},
  "trace": {}
}
```

## Capital Source

```json
{
  "capital": {
    "sourceId": 1,
    "sourceName": "BALANCER_VAULT | AAVE_V3 | V2_FLASH_SWAP | V3_FLASH_CALLBACK",
    "adapter": "0x...",
    "adapterCodeHash": "0x...",
    "asset": {
      "symbol": "USDC.e",
      "address": "0x2791...",
      "decimals": 6,
      "usd": "1.000134"
    },
    "principal": {
      "requestedUsd": "50000",
      "selectedUsd": "9588.57",
      "baseUnits": "9589.855040575437108572548722",
      "raw": "9589855040",
      "sizingPolicy": "min(10pct route depth, requested, max)",
      "routeDepthUsd": "47942.85",
      "routeDepthFraction": "0.10",
      "minimumUsd": "5000"
    },
    "fee": {
      "bps": "0",
      "usd": "0",
      "raw": "0",
      "verified": true,
      "source": "balancer_vault_live"
    }
  }
}
```

## Hop Schema

Each hop has common fields plus an `invariant` object. The common hop shape
never changes.

```json
{
  "hopIndex": 1,
  "kind": "UNISWAP_V2 | UNISWAP_V3 | ALGEBRA_V3 | CURVE_STABLE | BALANCER_V2 | DODO_PMM | UNISWAP_V4",
  "poolId": "V3_USDC_e_USDT_500",
  "poolAddress": "0x...",
  "liquidityKey": "137:V3_CLMM:factory:pool:500",
  "tokenIn": {
    "symbol": "USDC.e",
    "address": "0x...",
    "decimals": 6
  },
  "tokenOut": {
    "symbol": "USDT",
    "address": "0x...",
    "decimals": 6
  },
  "amountInRaw": "9589855040",
  "amountOutRaw": "9595937715",
  "amountInUnits": "9589.855040",
  "amountOutUnits": "9595.937715",
  "effectivePriceUsdPerOutUnit": "0.9992322047913584232763019763",
  "fee": {
    "feeTier": "500",
    "feeBps": "5",
    "source": "factory_or_pool_state"
  },
  "invariant": {},
  "readProof": {
    "blockNumber": 90283753,
    "source": "live_rpc",
    "stateFresh": true,
    "orientationDecimalsPass": true
  }
}
```

## Invariant Families

### Constant Product

Use for QuickSwap/Uniswap V2-style pools.

```json
{
  "family": "CONSTANT_PRODUCT_XY_K",
  "formula": "amountOut = reserveOut * amountInAfterFee / (reserveIn + amountInAfterFee)",
  "reserveInRaw": "0",
  "reserveOutRaw": "0",
  "reserveInUnits": "0",
  "reserveOutUnits": "0",
  "kRaw": "0",
  "feeBps": "30"
}
```

### Concentrated Liquidity

Use for Uniswap V3 and QuickSwap Algebra. Keep Algebra separated by `kind`
because its pool ABI and dynamic fee semantics differ.

```json
{
  "family": "CONCENTRATED_LIQUIDITY",
  "engine": "UNISWAP_V3 | ALGEBRA_V3",
  "sqrtPriceX96": "0",
  "tick": 0,
  "liquidityRaw": "0",
  "tickSpacing": 10,
  "feeTier": 500,
  "feeBps": "5",
  "zeroForOne": true,
  "sqrtPriceLimitX96": "0",
  "quoter": {
    "address": "0x...",
    "method": "quoteExactInputSingle",
    "quotedAmountOutRaw": "0",
    "gasEstimate": "0"
  }
}
```

### Curve StableSwap

Use for Curve math-only discovery and executable Curve routes when the router
and pool semantics are configured.

```json
{
  "family": "CURVE_STABLESWAP",
  "poolType": "plain | meta | crypto | factory",
  "coins": ["0x...", "0x..."],
  "coinIndices": {
    "i": 0,
    "j": 1
  },
  "balancesRaw": ["0", "0"],
  "A": "0",
  "fee": "0",
  "adminFee": "0",
  "quoteMethod": "get_dy | calc_token_amount | router_get_exchange_amount"
}
```

### Balancer V2

Use only Balancer V2 on Polygon. Do not use Balancer V3 on Chain 137 unless
official deployment, bytecode, ABI, and pool registry all pass.

```json
{
  "family": "BALANCER_V2_VAULT",
  "vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
  "poolId": "0x...",
  "poolSpecialization": "GENERAL | MINIMAL_SWAP_INFO | TWO_TOKEN",
  "swapKind": "GIVEN_IN",
  "tokens": ["0x...", "0x..."],
  "balancesRaw": ["0", "0"],
  "weights": ["0.5e18", "0.5e18"],
  "swapFeePercentage": "0",
  "formula": "weighted_out_given_exact_in",
  "fundManagement": {
    "sender": "executor",
    "fromInternalBalance": false,
    "recipient": "executor",
    "toInternalBalance": false
  }
}
```

### DODO PMM

Use for DODO PMM pools when pool ABI and adapter semantics are explicitly
configured.

```json
{
  "family": "DODO_PMM",
  "poolType": "DVM | DPP | DSP",
  "baseToken": "0x...",
  "quoteToken": "0x...",
  "i": "0",
  "k": "0",
  "B": "0",
  "Q": "0",
  "B0": "0",
  "Q0": "0",
  "RStatus": "ONE | ABOVE_ONE | BELOW_ONE",
  "feeBps": "0",
  "quoteMethod": "querySellBase | querySellQuote"
}
```

### Uniswap V4

Use as discovery/ranking only until hook semantics and executor adapter support
are proven. Execution must fail closed unless `hookPolicy.executable=true`.

```json
{
  "family": "UNISWAP_V4_SINGLETON",
  "poolManager": "0x...",
  "poolKey": {
    "currency0": "0x...",
    "currency1": "0x...",
    "fee": 0,
    "tickSpacing": 0,
    "hooks": "0x..."
  },
  "poolId": "0x...",
  "sqrtPriceX96": "0",
  "tick": 0,
  "liquidityRaw": "0",
  "hookPolicy": {
    "hookAddress": "0x...",
    "beforeSwap": false,
    "afterSwap": false,
    "executable": false,
    "reason": "hook behavior not executor-classified"
  }
}
```

## Quote Chain

The quote chain enforces route parity:

```json
{
  "quoteChain": {
    "formula": "R = QuoteFinal(...QuoteLeg2(QuoteLeg1(P)))",
    "principalRaw": "9589855040",
    "legs": [
      {
        "hopIndex": 1,
        "amountInRaw": "9589855040",
        "amountOutRaw": "9595937715"
      },
      {
        "hopIndex": 2,
        "amountInRaw": "9595937715",
        "amountOutRaw": "9585072237"
      }
    ],
    "finalAmountOutRaw": "9585072237",
    "parityChecks": [
      {
        "left": "hop2.amountInRaw",
        "right": "hop1.amountOutRaw",
        "pass": true
      }
    ]
  }
}
```

## Accounting Schema

This is the canonical accounting block. It is independent of protocol family.

```json
{
  "accounting": {
    "schema": "omega_v5.arbitrage_accounting.v2",
    "principal": {
      "usd": "9588.57",
      "baseUnits": "9589.855040575437108572548722",
      "raw": "9589855040"
    },
    "spread": {
      "unitToken": "USDT",
      "unitsPurchased": "9595.937715",
      "buyCostUsdPerUnit": "0.9992322047913584232763019763",
      "sellValueUsdPerUnit": "0.9988677002565969656254693604",
      "spreadUsdPerUnit": "-0.0003645045347614576508326159"
    },
    "delta": {
      "grossOutputUsd": "9585.07223719",
      "rawDeltaUsd": "-3.49776281",
      "rawDeltaFormula1": "RawDeltaUSD = GrossOutputUSD - PrincipalUSD",
      "rawDeltaFormula2": "RawDeltaUSD = SpreadUSDPerUnit * UnitsPurchased",
      "principalAlreadyAccountedFor": true,
      "doNotSubtractPrincipalAgain": true
    },
    "expenses": {
      "flashFeeUsd": "0",
      "gasCostUsd": "0.00833288",
      "relayTipUsd": "0.5",
      "riskBufferUsd": "1",
      "otherCostsUsd": "0",
      "netDeltaUsd": "-5.00609569",
      "formula": "NetDeltaUSD = RawDeltaUSD - ExpensesUSD"
    },
    "rawExecutionGate": {
      "formula": "sellAmountOutRaw > principalRaw + flashFeeRaw + gasCostRaw + relayCostRaw + riskBufferRaw + otherCostsRaw + minimumProfitRaw",
      "sellAmountOutRaw": "9585072237",
      "requiredSellAmountOutRaw": "0",
      "pass": false
    }
  }
}
```

## Execution Gate

Execution is allowed only when all hard gates pass.

```json
{
  "executionGate": {
    "capitalSourceConfigured": true,
    "adapterBytecodePresent": true,
    "flashAssetSupported": true,
    "poolKindsConfigured": true,
    "routeStateFresh": true,
    "orientationDecimalsPass": true,
    "quoteChainParityPass": true,
    "rawExecutionGatePass": false,
    "minProfitPass": false,
    "exactCallPass": false,
    "nonceAvailable": false,
    "emergencyStopInactive": true,
    "liveEligible": false,
    "rejectionClass": "quote_aligned_not_profitable"
  }
}
```

## Payload Block

Payloads are unique by stage. C1, C2, and liquidation payloads do not share
meaning even if they use some common fields.

```json
{
  "payload": {
    "stage": "C1 | C2 | LIQUIDATION",
    "target": "0x409ece3Fd71DFBd8f692B600f36A89301cb37346",
    "selector": "0x626482a3",
    "calldata": "0x...",
    "calldataHash": "0x...",
    "signer": "0x...",
    "deadlineBlock": 0,
    "minProfitRaw": "0",
    "slippageBps": "0",
    "status": "NOT_BUILT | BUILT | EXACT_CALL_PASSED | SUBMITTED | REVERTED | SETTLED"
  }
}
```

## Proofs And Trace

```json
{
  "proofs": {
    "quoteSource": "live_rpc | quoter | vault_read | curve_calc | indexer_plus_rpc",
    "exactCall": {
      "performed": false,
      "rpc": "",
      "block": 0,
      "success": false,
      "returnData": "0x",
      "revertReason": ""
    },
    "forkSimulation": {
      "performed": false,
      "rpc": "http://anvil-fork:8545",
      "success": false,
      "txHash": ""
    }
  },
  "trace": {
    "traceHash": "0x...",
    "parentTraceHash": "",
    "c1TxHash": "",
    "c2TxHash": "",
    "receiptBlock": 0,
    "realizedPnlUsd": "0"
  }
}
```

## Required Invariants

Every route must satisfy:

```text
hop[i + 1].amountInRaw == hop[i].amountOutRaw
finalAmountOutRaw == quoteChain.finalAmountOutRaw
RawDeltaUSD == GrossOutputUSD - PrincipalUSD
RawDeltaUSD == SpreadUSDPerUnit * UnitsPurchased for 2-leg routes
NetDeltaUSD == RawDeltaUSD - ExpensesUSD
sellAmountOutRaw > principalRaw + allCostsRaw + minimumProfitRaw
```

No route is live executable if:

```text
protocol family is discovery-only
adapter bytecode is missing
pool kind is unset
quote chain parity fails
raw execution gate fails
exact-call fails
```

