# C1_VANGUARD ↔ Omega-Apex Live Sync

**Goal:** 100% synchronized live data & logic between the lean C1 scanner and the Omega control center.

## Single source of truth

| Concern | Module | Rule |
|---------|--------|------|
| Gates (min net, slippage, gas) | `src/utils/c1SyncContract.ts` | Identical thresholds |
| Flash sizing | `solveProfitApex` + `syncFlashSizeUsd` | Analytical optimal, 25% depth cap, gas shrink |
| Live vs mock | `isLiveRoute` / `requireLiveQuotesForRanking` | Mock never enters executable ranking |
| Runtime mode | `resolveRuntimeMode()` | Default **dry-run**; live only if env allows |
| Pipeline stages | `executionPipeline.ts` | Discovery → Ranking → Staging → Dispatch |

## Runtime env (Cloud Run)

```
OMEGA_RUNTIME_MODE=dry-run|simulate|live
EXECUTION_MODE=dry-run|simulate|live
LIVE_TRADING=0|1
EXECUTOR_PRIVATE_KEY=          # required for live only
ON_CHAIN_MUSCLE=               # executor contract for live only
```

Default image ships with dry-run. Live requires explicit flags + keys.

## What “100% sync” means

1. **Same gates** — a route that fails C1 fails Omega ranking and vice versa.
2. **Same size** — optimal flash USD computed the same way.
3. **Same live filter** — synthetic/mock/seed routes cannot be `EXECUTABLE`.
4. **Same dry-run semantics** — no broadcast unless live mode is fully armed.
5. **Same chain** — Polygon 137 only for this contract.

## Mock data policy

- `src/data/mockEngineData.ts` may still feed **UI demos / charts**.
- Ranking, pipeline staging, and dispatch must call `isLiveRoute` + `runSyncSafetyGates`.
- When `C1_SYNC.allowMockInExecutablePath === false` (default), mock routes are rejected at Ranking.

## Deploy order

1. Dockerfile + .dockerignore (done)
2. `c1SyncContract.ts` (this commit)
3. Wire `executionPipeline` + Top50 / FullAutomation to use sync gates
4. Point discovery at live RPC multicall path (C1-style) when ready
5. Keep `LIVE_TRADING=0` until operator sign-off
