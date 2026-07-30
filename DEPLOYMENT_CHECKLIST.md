# Apex Omega Production Readiness

## Execution Contract

Live submission is directly wired behind fork simulation:

1. C1/C2/liquidation payload is normalized.
2. The exact calldata is encoded.
3. `FORK_SIM_RPC_URL` is called with that exact calldata and the live signer address.
4. If the fork simulation fails, broadcast returns `FORK_SIMULATION_BLOCKED`.
5. If the fork simulation passes, the same calldata is submitted live.

Anvil is a mandatory hot boot service in Docker deployment. It starts before Apex, passes a healthcheck, and Apex is wired directly to `http://anvil-fork:8545`. The execution path never boots Anvil per trade; it only performs the exact fork-simulation RPC call before live submission.

## Required Cloud Secrets

- `POLYGON_RPC_URL`
- `DISCOVERY_RPC_URL`
- `FORK_UPSTREAM_RPC_URL`
- `FORK_SIM_RPC_URL`
- `EXECUTOR_PRIVATE_KEY` or `BOT_PRIVATE_KEY`
- `BOT_PROFIT_RECEIVER`
- `MIN_NET_PROFIT_USD`

## Safe Deploy Default

The image defaults to:

```env
LIVE_EXECUTION=false
SHADOW_MODE=true
```

To arm live execution in cloud:

```env
LIVE_EXECUTION=true
SHADOW_MODE=false
FORK_UPSTREAM_RPC_URL=<low latency Polygon RPC for Anvil fork>
FORK_SIM_RPC_URL=http://anvil-fork:8545
```

## Build And Verify

```powershell
npm run lint
npm run build
npm run cloud:readiness
npm run routes:verify
npm run fork:calldata
```

## Docker App Deploy

```powershell
docker compose --env-file .env.production up -d --build apex-omega
```

## Bor Build Target

The Bor profile only builds/prepares the binary image. Full Bor node sync/bootstrap remains an ops step.

```powershell
docker compose --profile bor build bor-rpc
```

## Non-Negotiable Gates

- No P&L update from wallet balance movement alone.
- No live broadcast without successful exact fork simulation.
- No live mode unless `npm run cloud:readiness` returns `CLOUD_READINESS|status=PASS`.
- No route execution if final asset does not repay the flashloan asset.
- No route execution if net profit, gas, fee, stale-state, or pre-send gates fail.
