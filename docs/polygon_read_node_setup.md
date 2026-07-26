# Polygon Read Node Setup For Omega V5

This setup uses `mawi001/ansible-matic-mainnet-full-node` as a remote bootstrap template for a Polygon PoS full/read node, then wires Omega V5 read and simulation lanes to the node.

Use it for:

- `PRIMARY_READ_RPC_URL`
- `EXACT_CALL_RPC_URL`
- `FORK_UPSTREAM_RPC_URL`
- `TELEMETRY_RPC_URL`

Do not use it for `BROADCAST_RPC_URL` until it passes the broadcast readiness checks.

## Hardware Gate

Current Polygon mainnet guidance is much heavier than the old Ansible repo README. Budget at least:

- 32 GB RAM minimum, 64 GB preferred
- 8 CPU cores minimum, 16 preferred
- 4 TB storage minimum, 6 TB preferred
- 1 Gbit/s network

## Deploy To A Linux Host

From this repo on Windows PowerShell:

```powershell
.\scripts\ops\setup_polygon_read_node.ps1 `
  -NodeHost YOUR_SERVER_IP `
  -SshUser ubuntu `
  -SshKey C:\path\to\key.pem `
  -Deploy `
  -WriteEnvOverlay
```

The script installs dependencies, clones the Ansible repo on the remote host, runs its playbook, probes Bor RPC at `http://YOUR_SERVER_IP:8545`, probes Heimdall at `http://YOUR_SERVER_IP:26657/status`, and writes `out/polygon_read_node.env`.

## Wire Omega To An Existing Node

```powershell
.\scripts\ops\setup_polygon_read_node.ps1 `
  -NodeRpcUrl http://YOUR_NODE_IP:8545 `
  -WriteEnvOverlay
```

Then copy the generated read-lane values from `out/polygon_read_node.env` into your real `.env` if the probe passes.

## Required Verification

Run these gates after the node reports `eth_chainId=0x89`:

```powershell
python scripts\ops\verify_deployed_contracts.py
python scripts\ops\validate_config.py
.\scripts\run_full_benchmark_and_readiness.ps1
```

A self-hosted node is only an Omega read/simulation source until these pass cleanly. Broadcast remains on the existing gated broadcast provider.
