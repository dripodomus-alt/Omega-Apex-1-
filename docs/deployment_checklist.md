# Deployment Checklist for Omega V5

This document outlines prerequisites and known issues for running the system.

## 1. Software Prerequisites

- `python` (3.10+)
- `node` + `npm` (for optional PM2)
- `pm2` (optional, `npm install -g pm2`)
- `anvil` (Foundry) — recommended for simulation and benchmarks
- `redis-server` (optional for local)
- `cast` (from Foundry) for benchmark scripts

## 2. Important: Windows PM2 Issues

PM2 frequently fails on Windows with errors like:
- `EPERM` when opening pm2.log
- `connect EPERM //./pipe/rpc.sock`

**Recommended solutions (in order):**

1. **Best for local dev on Windows** — Use the direct starter (no PM2):
   ```powershell
   .\scripts\ops\start_direct.ps1
   ```

2. Use the improved PM2 boot script:
   ```powershell
   .\scripts\pm2\boot_all.ps1 -Reset
   ```

3. Manually set safe PM2 home:
   ```powershell
   $env:PM2_HOME = "$env:USERPROFILE\.pm2"
   pm2 kill
   ```

If you still have problems, avoid PM2 entirely for local work.

## 3. Environment Configuration

Copy `.env.example` to `.env` and fill in required values:
- `EXECUTOR_WALLET`
- `EXECUTOR_PRIVATE_KEY`
- `BROADCAST_RPC_URL`
- `FORK_SIM_RPC_URL` (critical for benchmarks)
- `FORK_UPSTREAM_RPC_URL`

## 4. Running the System

### Direct (Recommended for Windows)
```powershell
.\scripts\ops\start_direct.ps1
```

### With PM2 (better on Linux/macOS)
```powershell
.\scripts\pm2\boot_all.ps1
.\scripts\pm2\boot_all.ps1 -Reset
```

### Direct Python (quick test)
```powershell
python -m omega_v5.main
```

## 5. Full Benchmark + Readiness Assessment (New)

Use the master script to run safe scripts, benchmarks, and get a 0-100 readiness score:

```powershell
# Basic run (2 cycles)
.\scripts\run_full_benchmark_and_readiness.ps1

# More cycles, skip heavy Anvil part
.\scripts\run_full_benchmark_and_readiness.ps1 -Cycles 5 -SkipAnvil

# Readiness-only (no benchmarks)
.\scripts\run_full_benchmark_and_readiness.ps1 -ReadinessOnly
```

This script:
- Validates prerequisites
- Runs unit tests + preflight + pipeline validation
- Runs the safe Anvil fork benchmark (never runs live-fire)
- Aggregates results
- Computes and prints a readiness percentage

Results are saved to `out/readiness_report.json`.

## 6. Verification

After starting, check:
- API available at http://127.0.0.1:8080
- Logs in the terminal windows
- Use `pm2 status` only if using PM2
- Run the readiness script above for a quantitative score

By following the direct path on Windows you avoid most permission and daemon problems.

## 7. Safety

- The master benchmark script explicitly avoids `run_live_fire_benchmark.ps1`.
- Always start with fork / dry-run modes.
- Never use real private keys with real funds until readiness score is high and you understand the risks.

## Deployed Contract Bytecode Gate

Before authorizing Capital Injector simulations against production executor targets, run:

```powershell
python scripts/ops/verify_deployed_contracts.py
```

A passing infrastructure gate must print `VERDICT: INFRASTRUCTURE COMPATIBLE`. This check uses `eth_getCode` only; it verifies deployed bytecode presence for the configured HFT/C1 executor and liquidation executor, not source-code verification.