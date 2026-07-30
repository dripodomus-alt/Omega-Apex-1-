# Omega V5 Production Pipeline Overview

Last validated: 2026-07-13 on Polygon Chain 137.

## Canonical Arbitrage Equation

The executable equation is defined in `docs/arb_equation_and_execution_gate.md`. The pipeline supports broad cross-protocol discovery, but live execution is fail-closed until every route leg has exact quote, calldata, source-adapter, simulation, and settlement verification.

## End-to-End Cycle

1. RPC connection
   - Runtime connects to Polygon RPC/WSS endpoints only.
   - Offline synthetic pool fallback is refused.
   - `WRITABLE_RPC_URL` / `POLYGON_WRITABLE_RPC_URL` aliases feed the broadcast lane and are also used as read fallbacks when primary discovery RPCs fail.
   - Optional DODO RPC provider and Redis cache are used only for endpoint discovery and validation acceleration.

2. Live pool state loading
   - Base registry contains 19 production-acceptable pools.
   - Live factory discovery can expand the active registry from QuickSwap V2 and Uniswap V3 factories across the known token universe.
   - Uniswap V2 pools read `token0`, `token1`, and `getReserves`.
   - Uniswap V3 pools read `token0`, `token1`, `slot0`, and `liquidity`.
   - QuickSwap V3 / Algebra pools read `token0`, `token1`, `globalState`, and `liquidity`.
   - V3/Algebra pools must pass the orientation + decimals audit before they are rankable.
   - Balancer V2 reads reserves from Vault `getPoolTokens(poolId)` and normalized weights from the pool contract.
   - Curve infrastructure is configured, but deprecated Aave V2 and nested ATriCrypto pools are excluded from active discovery until a Curve registry/router importer maps current executable pools safely.

3. Live price sourcing
   - `TOKEN_USD_PRICE` now starts empty.
   - Prices enter scoring only from live sources: CoinGecko, 1inch when keyed, and Chainlink on-chain feeds.
   - Missing price data raises `PriceUnavailable`; callers skip that route instead of defaulting to constants.

4. Quote generation
   - Protocol-specific math is routed through `amm_adapters.quote_pool`.
   - V2, V3, Balancer, and supported Curve semantics remain separated by adapter.
   - `quote_pool()` refuses V3/Algebra pools whose `clmm_orientation_decimals_audit` did not pass.
   - The hardcoded arbitrage rule is only:
     - final net profit after expenses must be positive and pass configured profitability gates;
     - two-leg routes must buy leg 1 at a lower effective price than sell leg 2.

5. Opportunity detection
   - Every ranked opportunity carries `schema_version=omega_v5.opportunity.v2`.
   - Every ranked route carrying a V3/Algebra leg includes `data_quality.v3_algebra_orientation_decimals_gate`.
   - Two-leg opportunities must include mandatory `BUY_LEG1_PRICE` and `SELL_LEG2_PRICE` metadata steps.
   - Two-leg cross-pool detection requires distinct canonical liquidity keys.
   - Bellman-Ford cycles are scored only if they do not reuse the same native liquidity key.
   - Pegged/stable strategies are enabled as a same-peg specialization, but they do not bypass net-profit, adapter, or execution gates.

6. Profitability gate
   - `evaluate_profitability()` subtracts principal, flash fee, gas, relay tip, and risk buffer.
   - Dynamic flash-loan sizing prefers Balancer Vault and selects principal from the smallest route pool TVL cap.
   - Opportunities are ranked only after the final net-profit gate.

7. C1/C2 preparation
   - C1 captures pre-state only for a real ranked opportunity.
   - C2 waits for a real C1 receipt; synthetic confirmations were removed.

8. Parallel liquidation lane
   - Aave V3 borrower discovery reads recent `Borrow` events plus optional seed addresses.
   - Each scan uses one block number for account, reserve, and risk reads.
   - Candidate packets use `authority=SCANNER_ONLY` and `nextStage=LIQUIDATION` or `REJECTED`.
   - Candidates evaluate all debt/collateral pairs, close factor, liquidation bonus, protocol fee, exit quote, capital-source availability, and expected net USD.
   - `adapterForSource(source)` is checked before source selection, so an unset Balancer slot rejects Balancer early instead of failing during payload build.
   - Liquidation execution remains fail-closed until a liquidation executor address, adapter deployment, calldata builder, and fork simulation are configured.

9. Execution handoff
   - C1 and C2 both target `0x409ece3Fd71DFBd8f692B600f36A89301cb37346`.
   - `poolSequence` is the ordered pool route and must contain concrete pool contract addresses.
   - The executor dispatches through `adapterForSource[flashSource]`; source adapters are configured by owner through `configureAdapter(uint8,address)`.
   - Public routers, quoters, factories, Aave Pool, Balancer Vault, and Multicall3 are not treated as internal executor adapters.
   - Missing `AAVE_V3_CAPITAL_ADAPTER`, `BALANCER_VAULT_CAPITAL_ADAPTER`, `V2_FLASH_SWAP_ADAPTER`, or `V3_FLASH_CALLBACK_ADAPTER` blocks executable payload construction unless the executor already has that source configured on-chain.

## Current Validation Snapshot

Command:

```powershell
python -m omega_v5.pipeline_validation --rpc-url https://polygon-bor-rpc.publicnode.com --no-eth-call
```

Result:

- `pipeline_validation=PASS`
- `pools_loaded=263 base_registry_size=19 active_registry_size=263`
- `prices_loaded=32`
- `directional_quotes=332`
- `two_leg_spreads=10`
- `stable_spreads=0`
- `cycles_detected=1`
- `gate_passed_opportunities=6`
- `pricing_steps=['BUY_LEG1_PRICE', 'SELL_LEG2_PRICE']` for the top ranked two-leg opportunity
- `execution_armed=False`

Final orchestrator check:

```powershell
python -m omega_v5.main --rpc-url https://polygon-bor-rpc.publicnode.com --ticks 1 --no-scan
```

Result: full cycle completed with live data, no mock opportunities, and no execution queue.

## Mainnet Source Registry

The researched Chain 137 infrastructure is centralized in `omega_v5/contract_deployments.py` and exposed in `.env.example` for override:

- Multicall3: read batching.
- Uniswap V3: factory, quoters, routers, Universal Router, Permit2, TickLens.
- QuickSwap: V2 router/factory and Algebra infrastructure.
- Balancer: Vault and Authorizer.
- Curve: address provider, meta-registry, stable factory, router, calc zap.
- DODO: route/proxy and DVM/DPP/DSP factories.

Sources used for the current registry:

- Uniswap V3 Polygon deployments: https://developers.uniswap.org/docs/protocols/v3/deployments/v3-polygon-deployments
- QuickSwap contracts: https://docs.quickswap.exchange/overview/contracts-and-addresses
- Multicall3: https://github.com/mds1/multicall3
- Curve deployments: https://docs.curve.finance/developer/deployments
- Curve router docs: https://docs.curve.finance/developer/amm/router/curve-router-ng
- DODO Polygon contracts: https://docs.dodoex.io/en/developer/contracts/dodo-v1-v2/contracts-address/polygon
- Balancer deployments: https://github.com/balancer/balancer-deployments

## Remaining Blockers

- On-chain `adapterForSource(0..3)` currently reads as unset on the canonical executor, so live payload construction remains blocked until owner configuration writes verified source adapter contracts.
- Liquidation execution is source-ready but not live-armed: `OmegaAaveV3LiquidationAdapter` is deployable source, while the scanner remains `SCANNER_ONLY` until `LIQUIDATION_EXECUTOR_ADDRESS`, adapter deployment, calldata build, and fork simulation are proven.
- Live broadcasting is intentionally not armed. The local signer value must be a valid private key before it can pass `EXECUTOR_PRIVATE_KEY valid`.
- Curve pool ingestion needs a current registry/router importer before Curve routes should re-enter active execution discovery.

