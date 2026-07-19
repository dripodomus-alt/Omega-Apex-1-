# Protocol Update Watchers

Omega V5 uses protocol metadata as discovery hints only. The protocol update
watcher refreshes those hint sources, fingerprints them, and reports drift before
the route scorer or executor sees stale metadata.

## Runner

```powershell
python -m omega_v5.protocol_update_watcher --once
python -m omega_v5.protocol_update_watcher
python -m omega_v5.background_discovery --once
python -m omega_v5.background_discovery
```

PM2 service:

```powershell
pm2 start ecosystem.config.cjs --only omega-protocol-update-watcher
pm2 start ecosystem.config.cjs --only omega-background-discovery
```

Disable in Cloud Run or PM2:

```powershell
$env:OMEGA_DISABLE_PROTOCOL_UPDATE_WATCHER = "true"
$env:OMEGA_DISABLE_BACKGROUND_DISCOVERY = "true"
```

## Artifacts

| Path | Purpose |
| --- | --- |
| `out/protocol_update_watch_latest.json` | Latest source fingerprints, source stats, drift diff, and recommended actions |
| `out/protocol_update_watch_history.jsonl` | Append-only history of source snapshots |
| `out/background_discovery_latest.json` | Latest unbounded background discovery and surplus route summary |
| `out/background_discovery_history.jsonl` | Append-only background discovery history |
| `out/route_surface_report_latest.json` | Detailed route surface, raw delta, and calldata-build proof |
| `out/live_pool_scan_report.json` | Latest pool/rate/quality proof used by the watcher for context |

API endpoint:

```text
GET /api/protocol/watch/status
GET /api/discovery/background/status
GET /api/routes/surface/status
```

The same payload is also included in:

```text
GET /api/runtime/status
```

## Watched Sources

| Source | Role |
| --- | --- |
| Deployment catalog | Factories, routers, quoters, vaults, pool managers, and protocol infrastructure addresses |
| Polygon token list | Token candidates used to expand factory pair probes |
| Dynamic pool registry | Locally persisted pool metadata, still live-RPC verified before use |
| Curve official API | Curve pool and coin metadata, still live-RPC hydrated before use |
| V3 subgraph intel | Optional V3 pool hints, never execution-authoritative |

## Max-Coverage Knobs

The PM2 profile sets a wider but still bounded discovery profile:

```text
DISCOVERY_MAX_TOKEN_PAIRS=320
DISCOVERY_MAX_PROMOTED_POOLS=384
DYNAMIC_POOL_REGISTRY_MAX_POOLS=512
CURVE_POOL_REGISTRY_MAX_POOLS=192
SUBGRAPH_POOL_INTEL_LIMIT=100
POLYGON_TOKEN_LIST_MAX_CANDIDATES=320
POLYGON_TOKEN_LIST_BASES=USDC.e,WETH,WPOL,WBTC,USDT,DAI,USDC,LINK,AAVE,CRV,BAL,UNI,SUSHI,QUICK
```

These increase discovery surface area. They do not loosen execution gates:
V2 canonical token checks, V3 orientation/decimal checks, quoteability, route
quality, profit gates, fork/exact-call truth, and live broadcast guards still
decide payload eligibility.

For the separate background discovery worker, `0` means no local cap:

```text
BACKGROUND_DISCOVERY_UNBOUNDED=true
DISCOVERY_MAX_TOKEN_PAIRS=0
DISCOVERY_MAX_PROMOTED_POOLS=0
DISCOVERY_PAIR_WINDOW_SIZE=640
DYNAMIC_POOL_REGISTRY_MAX_POOLS=0
CURVE_POOL_REGISTRY_MAX_POOLS=0
POLYGON_TOKEN_LIST_MAX_CANDIDATES=0
SUBGRAPH_POOL_INTEL_LIMIT=1000
```

This worker runs outside the foreground engine loop, so unbounded discovery does
not add latency to the main scan/execution cycle. `DISCOVERY_PAIR_WINDOW_SIZE`
is a per-cycle RPC pressure control, not a permanent discovery cap: the worker
persists `next_pair_window_offset` in `out/background_discovery_latest.json` and
advances through the full pair universe over repeated cycles.

## Operational Rule

If the watcher reports a changed source, treat it as a discovery refresh signal,
not as an automatic permission to trade. Run the normal read-only validation:

```powershell
python -m omega_v5.pipeline_validation --no-eth-call --max-opps 3
```

Only run exact-call/fork truth after the read-only scan remains clean.
