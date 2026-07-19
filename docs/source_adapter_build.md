# Omega Source Adapter Build

Built adapters:

- `OmegaBalancerCapitalSourceAdapter`
- `OmegaBalancerV3CapitalSourceAdapter`
- `OmegaAaveV3CapitalSourceAdapter`
- `OmegaAaveV3LiquidationAdapter`

Both implement the executor-required entrypoint:

```solidity
executeAtomic(
    address asset,
    uint256 amount,
    address[] calldata poolSequence,
    address[] calldata tokenPath,
    uint256 minProfit,
    bytes32 stateHash
) external returns (uint256 profit)
```

The adapters receive their own flash-loan callbacks, execute the route, repay
the capital source, transfer realized profit to the canonical executor, and
return the same realized profit value to the executor.

`OmegaBalancerCapitalSourceAdapter` is the Balancer V2 Vault adapter. It uses
the legacy `flashLoan(...) -> receiveFlashLoan(...)` callback path, repays
`amount + feeAmount` directly to the Vault, and only then reports realized
profit.

`OmegaBalancerV3CapitalSourceAdapter` is the separate Balancer V3 transient
accounting adapter. It uses:

```text
Vault.unlock(...)
→ adapter receiveUnlocked(...)
→ Vault.sendTo(token, adapter, amount)
→ _executeRoute(...)
→ transfer repayment back to Vault
→ Vault.settle(token, amount)
→ transfer realized profit to executor
```

Do not deploy the V3 adapter against the V2 Vault address. `BALANCER_V3_VAULT`
must be explicitly configured for that path.

`OmegaAaveV3LiquidationAdapter` is a separate liquidation execution adapter. It
uses Aave V3 `flashLoanSimple`, calls `liquidationCall`, exits seized collateral
through the same pool-route swap engine, repays flash principal plus premium,
and transfers realized profit back to its configured liquidation executor.

## Route Semantics

`poolSequence` stays as concrete liquidity pool addresses. The route swapper
dynamically supports:

- Uniswap V2 / QuickSwap V2 pairs through `getReserves()` and `swap()`.
- Uniswap V3 pools through exact-input `swap()` and adapter-owned
  `uniswapV3SwapCallback`.
- QuickSwap V3 / Algebra pools through exact-input `swap()` and adapter-owned
  `algebraSwapCallback`.
- Curve stable pools through bounded `coins(i)` index discovery and
  `exchange(i,j,dx,minDy)`.
- Balancer pools through `getPoolId()` and Vault `swap()`.

Public routers, quoters, factories, Aave Pool, Balancer Vault, and Multicall3
are still infrastructure only. They are not adapter addresses.

## Typed Route Pool Allowlist

`OmegaRouteSwapAdapter` now includes an owner-managed pool-kind registry:

```solidity
configureRoutePoolKinds(address[] pools, RoutePoolKind[] kinds)
```

The route pool kinds are:

```text
1 = V2_CPMM
2 = V3_CLMM
3 = ALGEBRA_CLMM
4 = CURVE_STABLE
5 = BALANCER_WEIGHTED
```

`routePoolKindEnforced` defaults to `true`. That keeps every newly deployed
adapter fail-closed until the owner writes the exact pool-family allowlist. This
preserves compatibility with the current executor ABI because
`executeFlashArb(...)` still passes only `poolSequence` and `tokenPath`, but the
adapter no longer needs to rely on pure contract-shape inference in live mode.

Dry-run the allowlist write:

```powershell
python -m omega_v5.configure_route_pool_kinds --adapter capital --rpc-url https://polygon-bor-rpc.publicnode.com
```

Use live discovered pools instead of only the base registry:

```powershell
python -m omega_v5.configure_route_pool_kinds --adapter all --live-registry --rpc-url https://polygon-bor-rpc.publicnode.com
```

Broadcast only after the adapter addresses are deployed, bytecode exists, the
signer owns those adapters, and the normal mainnet guards are intentionally set:

```powershell
python -m omega_v5.configure_route_pool_kinds --adapter capital --live-registry --send
```

Do not disable enforcement for production. The `--disable-enforcement` flag is
dry-run only and exists to make accidental live weakening impossible.

## Deploy

Compile:

```powershell
forge build
```

Dry-run deployment:

```powershell
python -m omega_v5.deploy_adapters --rpc-url https://polygon-bor-rpc.publicnode.com
```

Dry-run Balancer V3 unlock/settle adapter only after setting the real V3 Vault:

```powershell
python -m omega_v5.deploy_adapters --adapter balancer-v3 --balancer-v3-vault 0x... --rpc-url https://polygon-bor-rpc.publicnode.com
```

Dry-run only the liquidation adapter:

```powershell
python -m omega_v5.deploy_adapters --adapter aave-liquidation --liquidation-executor 0x1111111111111111111111111111111111111111 --rpc-url https://polygon-bor-rpc.publicnode.com
```

For a real deployment, replace the stand-in address with the deployed
`LIQUIDATION_EXECUTOR_ADDRESS` or set that value in `.env`.

Broadcast deployment only with the normal live guards and a funded deployer key:

```powershell
python -m omega_v5.deploy_adapters --send
```

After deployment, write the emitted addresses into `.env`:

```dotenv
BALANCER_VAULT_CAPITAL_ADAPTER=0x...
BALANCER_V3_VAULT_CAPITAL_ADAPTER=0x...
AAVE_V3_CAPITAL_ADAPTER=0x...
AAVE_V3_LIQUIDATION_ADAPTER=0x...
```

For capital adapters, the runtime uses this order:

```text
1. Local env override, such as BALANCER_VAULT_CAPITAL_ADAPTER
2. Canonical executor adapterForSource(sourceId), when env is empty
3. Fail closed
```

This fixes the operational gap where owner-configured custom adapters existed
on-chain but the local env file had not been synced yet. Public routers and
quoters are never used as source adapters.

To sync local env after owner configuration:

```powershell
python -m omega_v5.sync_adapter_env --rpc-url https://polygon-bor-rpc.publicnode.com --write
```

The sync command refuses to write predicted addresses or zero-code addresses.

To broadcast the pre-signed Balancer adapter bundle, the normal live guards must
be set first. The broadcaster verifies the bundle, sends transactions in nonce
order, and can sync `.env` after bytecode exists:

```powershell
python -m omega_v5.broadcast_adapter_slot_bundle --rpc-url https://polygon-bor-rpc.publicnode.com --write-env
```

Then dry-run owner configuration:

```powershell
python -m omega_v5.configure_adapters --rpc-url https://polygon-bor-rpc.publicnode.com
```

Broadcast `configureAdapter(uint8,address)` only after the owner signer is set
and the dry-run confirms bytecode:

```powershell
python -m omega_v5.configure_adapters --send
```

## V2/V3 Flash-Source Slots

`adapterForSource[2]` and `adapterForSource[3]` are intentionally still
fail-closed. V2/V3 flash-source adapters need an additional source-pool
convention that the current executor ABI does not cleanly separate from the
route `poolSequence`. Balancer and Aave are the executable capital-source path
for the current pipeline.

The liquidation adapter is not configured through `adapterForSource`; it needs a
liquidation executor/caller boundary exposed through `LIQUIDATION_EXECUTOR_ADDRESS`.
Until that address and a fork-simulated liquidation payload builder are present,
the Aave liquidation scanner emits `SCANNER_ONLY` packets and does not broadcast.
