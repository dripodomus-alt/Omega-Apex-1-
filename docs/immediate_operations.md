# Apex Omega V5 Immediate Operations

This repository is the merged operational root:

`C:\Users\The Urban Genius\Documents\DO OBVER ARBITRAGE\Apex-OmegaV5`

## Source Layers Merged

- Core engine: `omega_v5/`, `omega_v6/`, `rust_engine/`, `contracts/`
- Live TypeScript control surface: `server.ts`, `ExecutionManager.ts`, `server/engine/`, `server/redisLedger.ts`
- Dashboard UI: `src/`, `frontend_integration/`
- Operational scripts: `scripts/ops/`, `scripts/pm2/`, `scripts/cloud/`, `scripts/*.ts`
- Indexer and RPC provider: `indexer/omega-polygon-indexer/`, `vendor/web3-rpc-provider/`

## Safe Local Start Paths

Use dry-run or paper mode first. Do not enable live broadcasting until all env values, deployed contract addresses, and simulation gates are verified.

```powershell
cd "C:\Users\The Urban Genius\Documents\DO OBVER ARBITRAGE\Apex-OmegaV5"
python -m omega_v5.main
```

```powershell
cd "C:\Users\The Urban Genius\Documents\DO OBVER ARBITRAGE\Apex-OmegaV5"
.\scripts\ops\start_direct.ps1
```

```powershell
cd "C:\Users\The Urban Genius\Documents\DO OBVER ARBITRAGE\Apex-OmegaV5"
npm run dev
```

## Verification Paths

```powershell
python -m py_compile omega_v5\main.py omega_v5\config.py omega_v5\execution.py omega_v5\pipeline_validation.py
cargo check
npm run lint
.\scripts\run_full_benchmark_and_readiness.ps1 -DataGovernanceAudit -BottleneckAnalysis
```

## Live Execution Gates

- Keep private keys out of git and only in environment variables or secret storage.
- Require fork or `eth_call` simulation before submit.
- Require Polygon chain ID `137` on every RPC/broadcast path.
- Keep Redis as a cache/lock layer, not a source of execution truth.
- Use private relay or protected routing for live broadcast where configured.
- Fall back to public mempool only after explicit operator approval.

## Critical Environment Names

- `DISCOVERY_RPC_URL`, `DISCOVERY_RPC_WSS`
- `BROADCAST_RPC_URL`, `BROADCAST_WSS_URL`
- `FORK_UPSTREAM_RPC_URL`, `FORK_SIM_RPC_URL`
- `EXECUTOR_ADDRESS`, `C1_ARB_EXECUTOR_ADDRESS`, `C2_ARB_EXECUTOR_ADDRESS`
- `LIQUIDATION_EXECUTOR_ADDRESS`
- `BOT_PROFIT_RECEIVER`, `PROFIT_ASSET`
- `EXECUTOR_PRIVATE_KEY` or `BOT_PRIVATE_KEY`
- `REQUIRE_FORK_SIM_BEFORE_SUBMIT=true`
- `REQUIRE_CHAIN_ID_MATCH=true`
