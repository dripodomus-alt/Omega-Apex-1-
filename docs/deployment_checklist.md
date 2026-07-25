# Deployment Checklist for Omega V5

This document outlines prerequisites and known issues for running the system.

## 1. Software Prerequisites

- `python` (3.10+)
- `node` + `npm` (for optional PM2)
- `pm2` (optional, `npm install -g pm2`)
- `anvil` (Foundry) — recommended for simulation
- `redis-server` (optional for local)

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

## 5. Verification

After starting, check:
- API available at http://127.0.0.1:8080
- Logs in the terminal windows
- Use `pm2 status` only if using PM2

By following the direct path on Windows you avoid most permission and daemon problems.
