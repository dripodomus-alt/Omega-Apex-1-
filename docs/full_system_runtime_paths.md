# Omega V5 Full-System Runtime Paths

This manifest lists the operational paths for the Cloud Run full-stack dry-run
runtime, proof artifacts, and local source controls.

## Cloud Runtime

| Item | Path / Value |
| --- | --- |
| Project | `apex-scanner-live1` |
| Region | `us-east1` |
| Service | `flashloan-execution-monitor` |
| Dashboard/API URL | `https://flashloan-execution-monitor-o66zgqortq-ue.a.run.app` |
| Local proxy command | `gcloud run services proxy flashloan-execution-monitor --region us-east1 --project apex-scanner-live1 --port=8080` |
| Local proxy dashboard | `http://127.0.0.1:8080` |
| Current full-stack image tag file | `out/last_fullstack_cloudrun_image.txt` |
| Local source deploy script | `scripts/cloud/deploy_dashboard_cloud_run.ps1` |
| Cloud env apply script | `scripts/cloud/apply_env_to_cloud_run.ps1` |

## Runtime Services

| Service | Runtime Path |
| --- | --- |
| API | `http://127.0.0.1:8080` inside Cloud Run |
| Redis | `redis://127.0.0.1:6379/0` inside Cloud Run |
| Anvil fork | `http://127.0.0.1:8545` inside Cloud Run |
| DODO RPC provider | `http://127.0.0.1:3000` inside Cloud Run |
| PM2 manifest endpoint | `/api/pm2/manifest` |
| Health endpoint | `/health` |
| Runtime status endpoint | `/api/runtime/status?probe=true` |
| Protocol update watch endpoint | `/api/protocol/watch/status` |
| Route surface endpoint | `/api/routes/surface/status` |
| Background discovery endpoint | `/api/discovery/background/status` |
| Transport status endpoint | `/api/transport/status?probe=true` |
| Finalizer endpoint | `/api/finalizer/report?probe=true` |

## Proof Artifact Paths

| Proof | API / File Path |
| --- | --- |
| Health | `GET /health` |
| Runtime status | `GET /api/runtime/status?probe=true` |
| Runtime alignment run | `POST /api/proofs/runtime-alignment/run?probe=true` |
| Runtime alignment artifact | `out/runtime_alignment_latest.json` |
| Session signer proof run | `POST /api/proofs/session-signer/run?samples=5` |
| Session signer artifact | `out/session_signer_proof_latest.json` |
| Read-only pipeline validation | `POST /api/pipeline/validate?no_eth_call=true&timeout_seconds=600` |
| Executor truth validation | `POST /api/pipeline/validate?no_eth_call=false&max_opps=1&max_size_rungs=2&max_exact_calls=2&timeout_seconds=600` |
| Fork-backed executor truth | `POST /api/pipeline/validate?exact_rpc_url=http%3A%2F%2F127.0.0.1%3A8545&no_eth_call=false&max_opps=1&max_size_rungs=2&max_exact_calls=2&timeout_seconds=600` |
| Live pool scan artifact | `out/live_pool_scan_report.json` |
| Protocol update watch run | `python -m omega_v5.protocol_update_watcher --once` |
| Protocol update watch artifact | `out/protocol_update_watch_latest.json` |
| Protocol update watch history | `out/protocol_update_watch_history.jsonl` |
| Route surface run | `python -m omega_v5.route_surface_report --top 25 --calldata-probe 5` |
| Route surface artifact | `out/route_surface_report_latest.json` |
| Background discovery run | `python -m omega_v5.background_discovery --once` |
| Background discovery artifact | `out/background_discovery_latest.json` |
| Background discovery history | `out/background_discovery_history.jsonl` |
| Pipeline validation artifact | `out/pipeline_validation_latest.json` |
| PnL snapshot | `out/pnl_snapshot.json` |
| PnL event log | `out/pnl_events.jsonl` |
| Execution traces | `logs/` and `/api/traces` |

## Configurable Runtime Environment

| Variable | Purpose | Current Safe Value |
| --- | --- | --- |
| `OMEGA_RUNTIME_MODE` | Authoritative runtime mode | `dry_run` |
| `EXECUTION_MODE` | Process execution mode | `dry_run` |
| `LIVE_TRADING` | Live triplet gate | `0` |
| `CONFIRM_MAINNET_EXECUTION` | Required only for live | unset |
| `LIVE_EXECUTION` | External live flag | `false` |
| `SHADOW_MODE` | External shadow flag | `true` |
| `PAPER_TRADING_MODE` | Paper/dry-run flag | `true` |
| `OMEGA_ENGINE_NO_SCAN` | Keep background engine scan disabled | `true` |
| `OMEGA_ENGINE_CANARY_MODE` | Cap live-capable execution count | `true` |
| `OMEGA_DISABLE_EMBEDDED_REDIS` | Exclude PM2 Redis app | `false` |
| `OMEGA_DISABLE_ENGINE` | Exclude PM2 engine worker | `true` for proof mode |
| `OMEGA_DISABLE_LIQUIDATION_WATCHER` | Exclude liquidation watcher | `true` for proof mode |
| `OMEGA_DISABLE_PROTOCOL_UPDATE_WATCHER` | Exclude protocol update watcher | `false` |
| `PROTOCOL_WATCH_INTERVAL_SECONDS` | Protocol watcher loop interval | `1800` |
| `OMEGA_DISABLE_BACKGROUND_DISCOVERY` | Exclude unbounded background discovery | `false` |
| `BACKGROUND_DISCOVERY_UNBOUNDED` | Apply `0 = unbounded` discovery caps in the background worker | `true` |
| `BACKGROUND_DISCOVERY_INTERVAL_SECONDS` | Background discovery loop interval | `900` |
| `BACKGROUND_DISCOVERY_PAIR_WINDOW_SIZE` | Per-cycle pair window for unbounded background scans | `640` |
| `REDIS_URL` | Redis cache/transport URL | `redis://127.0.0.1:6379/0` |
| `FORK_RPC_URL` | Local fork URL | `http://127.0.0.1:8545` |
| `FORK_SIM_RPC_URL` | Fork simulation URL | `http://127.0.0.1:8545` |
| `API_HOST` | API bind host | `0.0.0.0` |
| `API_PORT` | API bind port | `8080` |
| `POLYGON_RPC_URL` | Primary Polygon read RPC | configured in Cloud Run |
| `POLYGON_WSS_URL` | Primary Polygon WSS RPC | configured in Cloud Run |
| `BROADCAST_RPC_URL` | Broadcast RPC, guarded by runtime mode | configured but disarmed |
| `OMEGA_TRUTH_MAX_SIZE_RUNGS` | Per-candidate exact-call size ladder cap | request-scoped |
| `OMEGA_TRUTH_MAX_EXACT_CALLS` | Exact-call budget cap | request-scoped |

## Safety Boundary

The full-stack Cloud Run runtime can connect Redis and Anvil while remaining
dry-run only. A route is not live-eligible until `pipeline_validation_latest.json`
shows:

- `execution_armed=false` during proof mode,
- `executor_truth.executable >= 1`,
- `payload_execution_eligible=true`,
- `exact_call_gate=PASS`.

Only after that proof exists should the live triplet be restored.
