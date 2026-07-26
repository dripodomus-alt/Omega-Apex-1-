# Omega V5 Pipeline Walkthrough

This document walks the Omega V5 arbitrage and liquidation pipeline from environment setup through staging and execution handoff. It is an operator map, not a second architecture. The authoritative ownership boundary remains `docs/pipeline_ownership.md`.

## Prime Directive

The hot path is:

```text
Environment -> Discovery -> Math -> Simulation -> Transactions -> Observability -> Storage
```

For two-leg arbitrage, the economic invariant is stricter:

```text
1. Buy the mid token on the lowest executable base-asset cost per unit.
2. Sell that same mid token back into the base asset at a higher executable base-asset return per unit.
3. Count surplus only in the original base asset after flash fee, gas, relay/private-submit cost, slippage buffer, and risk buffer.
```

If the sell leg cannot prove a higher executable base-per-mid price than the buy leg, the route is not execution eligible even if a rough spread looked positive.

## Stage 0: Environment And Contract Gate

Owner: Environment

Inputs:
- `.env` / process environment
- `omega_v5/config.py`
- RPC read and broadcast URLs
- canonical executor targets

Required checks:
- Chain ID must be Polygon `137` for production paths.
- Read RPC must answer current block and `eth_getCode`.
- HFT/C1 executor and liquidation executor must have deployed bytecode before production simulations target them.

Commands:

```powershell
python scripts/ops/verify_deployed_contracts.py
python scripts/ops/simulate_capital_injector.py --verify-contracts
python -m omega_v5.preflight
```

Passing bytecode gate output must end with:

```text
VERDICT: INFRASTRUCTURE COMPATIBLE
```

## Stage 1: Discovery

Owner: Discovery

Primary responsibilities:
- Load live pool state from configured Polygon RPCs.
- Normalize pool identity, token ordering, protocol family, liquidity keys, reserves, fees, and executable status.
- Reject stale, malformed, non-native, unsupported, or duplicate-liquidity candidates before math.

Main code paths:
- `omega_v5/rpc_layer.py`
- `omega_v5/ranker.py`
- `omega_v5/route_execution_stager.py::enumerate_closed_token_paths`
- `omega_v5/route_execution_stager.py::pre_rank_routes`

Discovery emits candidate paths and pool sequences. It must not size trades, rank final net profit, build calldata, simulate execution, or broadcast.

## Stage 2: Quote And Math

Owner: Math

Primary responsibilities:
- Quote every hop with protocol-specific math or exact quoter proof.
- Compute gross output in the original base asset.
- Run official flash sizing through the Capital Injector.
- Subtract all required costs before declaring net profit.

Main code paths:
- `omega_v5/capital_injector.py`
- `omega_v5/executable_quotes.py`
- `omega_v5/flash_loan.py::evaluate_profitability`
- `omega_v5/pricing/net_delta.py`
- `omega_v5/route_execution_stager.py::stage_pre_ranked_route`

Capital sizing rule:
- `omega_v5/capital_injector.py` is the official and only flash-loan sizing authority.
- It must run before Rust, staging, or executor sizing.
- Self-cannibalization blocks before math if the funding source overlaps route liquidity.

Two-leg price rule:
- Buy leg is ranked by lowest executable `base per mid` unit price.
- Sell leg must prove higher executable `base per mid` return after min-out/slippage floor.
- The staged row records this under `execution_sequence` and `profitable_execution_staging`.

## Stage 3: Staging

Owner: Math until the staged candidate is handed to Transactions

Primary responsibilities:
- Apply n+4 lifespan checks.
- Select non-conflicting routes by liquidity key.
- Freeze route identity and opportunity ID.
- Emit unified envelope fields for staging, fees, math, and quote.

Main code paths:
- `omega_v5/route_execution_stager.py::build_stage_report`
- `omega_v5/payload_envelope.py::add_staging_to_unified_envelope`
- `tests/dry_run_25_cycles.py::simulate_staging`

Staged report artifacts:
- `out/route_execution_stage_latest.json`
- `out/benchmark_profitable_execution_latest.json`

Benchmark command:

```powershell
python scripts/ops/run_benchmark.py --mode dry-run --cycles 1 --max-parallel-tx 4 --print-top 2
```

This benchmark is stage-only. It does not sign or broadcast.

## Stage 4: Simulation / Truth Gate

Owner: Simulation

Primary responsibilities:
- Convert staged economics into execution truth checks.
- Use real min-out, fork, or `eth_call` proof where configured.
- Reject stale routes and any route whose final raw/base delta cannot repay capital plus costs.

Main code paths:
- `omega_v5/execution_truth.py`
- `omega_v5/pricing/net_delta.py`
- `docs/explicit_execution_flow.md`

Block lifespan:
- Each route has `discovery_block = n`.
- Broadcast must happen no later than `n + 4`.
- Stale routes are rejected at staging and before execution handoff.

## Stage 5: Transaction Handoff

Owner: Transactions

Primary responsibilities:
- Build calldata only from staged, truth-proven opportunities.
- Reserve nonce lanes.
- Apply gas policy and broadcast guard.
- Submit only when runtime is explicitly armed.

Main code paths:
- `omega_v5/execution/__init__.py`
- `omega_v5/execution.py`
- `omega_v5/execution/payload_stager.py`
- `omega_v5/execution/submission_router.py`

Hard restrictions:
- Transactions must not rescan pools.
- Transactions must not recompute ranking economics.
- Public routers, quoters, factories, Aave Pool, Balancer Vault, and Multicall3 are not executor adapters.
- Live broadcast remains disabled unless execution mode, live flag, confirmation flag, signer, RPC, and executor checks all pass.

## Stage 6: Observability And Storage

Owners: Observability and Storage

Primary responsibilities:
- Record stage, lifespan, simulation, transaction, receipt, and PnL events.
- Persist artifacts without influencing domain decisions.
- Keep dashboards and reports read-only over the hot path.

Main code paths:
- `omega_v5/pnl_tracker.py`
- `omega_v5/payload_envelope.py`
- `omega_v5/db/schema.sql`
- `scripts/reporting/compute_readiness.py`
- `scripts/reporting/generate_benchmark_report.py`

Storage must not own formulas, simulation decisions, or transaction construction.

## Liquidation Parallel Lane

Liquidations run beside arbitrage, not through the two-leg buy/sell spread rule.

Lane summary:
- Scanner reads Aave V3 borrower and reserve state.
- Candidate evaluates close factor, liquidation bonus, protocol fee, exit quote, capital source, gas, and net USD.
- Execution remains fail-closed until liquidation executor address, adapter, calldata builder, and fork simulation are proven.
- The deployed liquidation executor bytecode is checked by `scripts/ops/verify_deployed_contracts.py`.

## Safe Operator Walk

Use this sequence for a local proof pass:

```powershell
python scripts/ops/verify_deployed_contracts.py
python scripts/ops/simulate_capital_injector.py --verify-contracts
python scripts/ops/run_benchmark.py --mode dry-run --cycles 1 --max-parallel-tx 4 --print-top 2
python -m pytest tests\test_staging_simulation.py tests\test_route_execution_stager.py
```

Use the master readiness script for the broader safe run:

```powershell
.\scripts\run_full_benchmark_and_readiness.ps1
```

The master readiness path is preferred over manually chaining every script because it avoids live-fire execution and produces a single readiness score.

## Failure Reading Guide

- `missing_rpc_url` or wrong chain ID: fix environment/RPC before discovery.
- `no_deployed_bytecode`: do not authorize simulations against that target.
- `self_cannibalization`: route borrows from the same liquidity it tries to trade; reject immediately.
- `sell_min_price_not_above_buy_price`: buy-low/sell-high invariant failed; reject route.
- `clmm_quote_unproven`: concentrated-liquidity leg lacks exact quote proof; reject route.
- `lifespan_expired`: route exceeded `n + 4`; reject route.
- `execution_armed=False`: system is intentionally safe and will not broadcast.

## Non-Negotiables

- Never invent or hardcode secrets.
- Never treat discovery data as execution authority.
- Never use midpoint, stale spot, or raw spread as final profit.
- Never bypass the Capital Injector sizing guard.
- Never broadcast from benchmark or dry-run paths.
- Always collect surplus in the original base asset.