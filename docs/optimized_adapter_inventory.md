# Optimized Apex-Omega Adapter Inventory

This repo should not treat a single generic DEX adapter as production-ready.
Adapters are split by pipeline responsibility and promoted to live execution
only when they have bytecode, typed route semantics, same-block state, exact
payload construction, and fork-simulation proof.

## Live Spine

The first production spine is intentionally narrow:

```text
asset metadata/canonicalization
→ RPC health + same-block reads + Multicall3
→ V2/V3/Algebra/Curve/Balancer discovery and state
→ invariant quote adapters
→ route continuity and pool exclusivity
→ typed route pool allowlist
→ Aave or Balancer capital-source adapter
→ executeFlashArb C1 payload
→ exact eth_call/fork simulation
→ receipt and realized-PnL accounting
→ C2 payload decision
```

Liquidation is a parallel lane with its own payload domain:

```text
Aave borrower discovery
→ same-block reserve/account reads
→ debt/collateral pair ranking
→ executable collateral-exit route
→ liquidation payload
→ liquidation executor
→ Aave liquidation adapter
→ fork simulation
```

The payload families are exactly:

```text
ARBITRAGE_C1
ARBITRAGE_C2
LIQUIDATION
```

## Adapter Status Map

| Area | Adapter | Repo Status | Live Rule |
| --- | --- | --- | --- |
| Asset metadata | token address/decimals/symbol registry | implemented in `rpc_layer.py` | usable for discovery/ranking; execution requires verified address + decimals |
| Canonical assets | WPOL/WMATIC and MAI/miMATIC aliases | implemented | canonical address identity wins over symbol text |
| Token behavior | fee-on-transfer/rebase/blacklist detection | not fully implemented | unsupported tokens stay scanner-visible but execution-rejected |
| RPC health | chain, block, WSS/HTTP fallback | implemented | live execution still needs writable RPC guards |
| Same-block state | scan block pinning | implemented for liquidation and pool validation paths | all execution payloads must simulate against current or fork block |
| Multicall | metadata/pool-state batching | implemented | failed batch falls back to direct read, not synthetic data |
| V2 discovery/state/math | factory + reserves + CPMM quote | implemented | live-eligible only through typed pool kind `V2_CPMM` |
| V3 discovery/state/math | factory + slot0/liquidity + audit gate | implemented | execution requires orientation/decimals audit pass and typed pool kind `V3_CLMM` |
| Algebra discovery/state/math | QuickSwap/Algebra state path | implemented | execution requires Algebra-specific state path and typed pool kind `ALGEBRA_CLMM` |
| Curve stable | state/math/exchange path | implemented for stable pools | crypto/metapool variants remain separate future adapters |
| Balancer weighted | Vault reads, weights/fee, swap path | implemented | weighted only; stable/composable/boosted require separate adapters |
| Capital source | Balancer Vault flash loan | contract implemented | live blocked until deployed and `adapterForSource(1)` is configured |
| Capital source | Balancer V3 unlock/settle | contract implemented | requires explicit `BALANCER_V3_VAULT`; never use the V2 Vault address |
| Capital source | Aave V3 flash loan | contract implemented | live blocked until deployed and `adapterForSource(0)` is configured |
| Capital source | V2 flash swap | not implemented | fail-closed; current executor ABI does not separate source pair from route pool cleanly |
| Capital source | V3/Algebra flash callback | not implemented | fail-closed until callback pool-key validation is added |
| Route envelope | route shape, pool exclusivity, payload envelope | implemented | no repeated pool, closed cycle, explicit price steps |
| Typed route pool allowlist | owner-configured pool kind registry | implemented in `OmegaRouteSwapAdapter` | `routePoolKindEnforced=true` by default |
| Simulation | exact `eth_call` + fork URL support | implemented for arb payloads; liquidation builder added | inconclusive simulation rejects live broadcast |
| Execution | C1 transaction builder | implemented | blocked if capital-source adapter is unset |
| Execution | C2 envelope | implemented as unique domain envelope | final C2 action must use receipt-derived state |
| Liquidation | Aave scanner + candidate packet | implemented | scanner-only until executor, adapter, payload, and fork proof are live |
| Settlement | receipt/realized PnL | partial | predicted profit must not be credited as realized PnL |
| Observability | pipeline validation counters | implemented | add receipt-level prediction error before full live release |

## Optimized Contract Adapter Shape

The best compatible on-chain design is:

```text
OmegaRouteSwapAdapter
  shared typed route execution
  owner route-pool kind allowlist
  V2/V3/Algebra/Curve/Balancer swap internals

OmegaBalancerCapitalSourceAdapter
  Balancer flashLoan callback
  _executeRoute(...)
  repay Vault
  transfer realized profit to executor

OmegaBalancerV3CapitalSourceAdapter
  Vault.unlock(...)
  receiveUnlocked callback
  Vault.sendTo(token, adapter, amount)
  _executeRoute(...)
  transfer repayment to Vault
  Vault.settle(token, amount)
  transfer realized profit to executor

OmegaAaveV3CapitalSourceAdapter
  Aave flashLoanSimple callback
  _executeRoute(...)
  approve principal + premium
  transfer realized profit to executor

OmegaAaveV3LiquidationAdapter
  Aave flashLoanSimple callback
  liquidationCall(...)
  exit seized collateral through _executeRoute(...)
  approve principal + premium
  transfer realized profit to liquidation executor
```

This keeps the current executor interface intact while adding the missing
production semantic: a pool address is not enough by itself; it must be paired
with its approved invariant family.

## Deliberate Fail-Closed Boundaries

The following should remain discovery/ranking only until separate adapters are
implemented and fork-proven:

```text
Uniswap v4 hooks
Curve crypto pools
Curve metapools requiring underlying exchange variants
Balancer stable/composable/boosted pools
DODO PMM execution
Aggregator calldata/RFQ
V2/V3 flash-source callbacks
fee-on-transfer or rebasing tokens
```

These families can contribute intelligence to discovery, but they must not be
promoted to executable payloads through the existing native pool-route adapter.
