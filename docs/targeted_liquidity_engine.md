# Targeted Executable Liquidity Engine

This repo now separates broad discovery from executable liquidity.

## Runtime Registry

`omega_v5.liquidity_registry` builds a canonical runtime table with:

- `pair`
- `pool_address` / `pool_id`
- `protocol`
- `pool_family`
- `fee_tier`
- `TVL`
- `24h_volume`
- `token-side depth`
- `adapter_status`
- `fork_sim_status`
- `execution_status`

Promotion stages:

```text
DISCOVERED
LIQUIDITY_VERIFIED
MULTI_VENUE
MATH_SUPPORTED
CALLDATA_SUPPORTED
FORK_SIM_PASSED
LIVE_ELIGIBLE
```

## Routing Spine

The first production spine is encoded as:

```text
USDC    -> USDT, USDC.e, DAI, WPOL, WETH
USDC.e  -> WETH, WBTC, USDT, DAI
WETH    -> WBTC, WPOL, USDC.e
```

The scanner now exposes:

- 2-hop buy-leg/sell-leg cross-pool spreads.
- 3-leg explicit triangle cycles.
- 4-leg explicit cycles.
- Bellman-Ford negative cycles as the general detector.

All ranked opportunities carry `hop_count` and exact `pool_sequence` /
`pool_addresses` metadata for execution payload construction.

## Pool Families

Executable today through first-party adapters:

- `V2_CPMM`
- `V3_CLMM`
- `ALGEBRA_CLMM`
- `BALANCER_WEIGHTED`

Math-only or discovery-only until adapters/classification are built:

- `CURVE_STABLE`: math supported, calldata adapter not active.
- `UNISWAP_V4_HOOK_AMM`: discovery-only until PoolManager, hooks, dynamic fee, and side-effect simulation are classified.

## V3 / Algebra Orientation Gate

Every Uniswap V3, QuickSwap V3, and Algebra pool is audited before ranking:

- live `token0` / `token1` addresses must resolve to known registry symbols;
- on-chain ERC-20 decimals must match `TOKEN_DECIMALS`;
- registered pair metadata must match the on-chain token pair set;
- runtime quote order is forced to on-chain token0/token1 order;
- `sqrtPriceX96`, liquidity, and recomputed decimal adjustment must be positive and coherent.

Pools that fail this gate remain visible in loader diagnostics, but are removed
from the rankable pool set. `quote_pool()` and executable payload construction
also fail closed if a CLMM route lacks passed `data_quality` metadata.

## Balancer Upgrades

The live Balancer loader now:

- Reads Vault `getPoolTokens(poolId)`.
- Reads pool `getNormalizedWeights()`.
- Reads pool `getSwapFeePercentage()`.
- Runtime-remaps registered token metadata when Vault tokens differ.
- Persists remap audit data in `_meta.balancer_remap`.

The Solidity source adapters use Balancer Vault swaps internally for Balancer
pool legs. This belongs in the adapter layer because the canonical executor ABI
passes `poolSequence` and `tokenPath`, not a custom `Leg` struct.

## Rejection Rules

Candidates are rejected before execution when:

- pool is not in the verified runtime registry;
- family adapter is missing;
- fee tier is unresolved;
- state blocks differ;
- pool depth is unavailable or below threshold;
- pool is reused in the same route;
- v4 hook is unclassified;
- V3/Algebra orientation or decimals audit fails;
- price discrepancy exceeds sanity bounds;
- flash size exceeds weakest route depth;
- fork output differs from C1 quote.

## Safe Flash Sizing

The target rule is:

```text
maximum flash size =
min(
    15% * weakest pool TVL,
    effective token-side depth,
    flash-source available liquidity,
    configured risk ceiling
)
```

The current runtime sizing remains conservative and route-aware. The ladder
percentages to add before live scale-up are:

```text
0.1%, 0.25%, 0.5%, 1%, 2.5%, 5%
```

Scaling stops when:

```text
P(x + delta) <= P(x)
```

where `P(x)` is final base output minus principal, flash fee, gas, relay cost,
and risk buffer.
