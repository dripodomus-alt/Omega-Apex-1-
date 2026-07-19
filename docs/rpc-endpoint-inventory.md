# Polygon RPC Endpoint Inventory

This system keeps RPCs organized by execution role. Do not promote a fallback
or discovery endpoint into live broadcast unless it is explicitly writable,
healthy, and intended for transaction submission.

## Primary read and exact-call

- `NODECORE_HTTP_URL`: optional local RPC gateway; when enabled and healthy it
  can front the read/exact/fork lanes.
- `DRPC_LB_HTTP_URL`: preferred dRPC load-balanced paid HTTP lane.
- `PRIMARY_READ_RPC_URL`: active primary HTTP read lane.
- `EXACT_CALL_RPC_URL`: exact `eth_call` and final quote truth lane.

## Primary WSS

- `NODECORE_WSS_URL`: optional local WebSocket gateway.
- `DRPC_LB_WSS_URL`: preferred dRPC load-balanced paid WSS lane.
- `PRIMARY_WSS_URL`: active block/event listener lane.

## Rotation candidates

- `RPC_ROTATION_HTTP_URLS`: measured read/discovery/exact/fork/receipt candidates.
- `RPC_ROTATION_WSS_URLS`: measured WSS candidates.

The transport layer ranks candidates by:

- Chain ID match.
- Success rate.
- Median latency.
- Freshest observed block.
- Recent failure status in Redis.

## Discovery and metadata

- `DODO_RPC_PROVIDER_URL`: local DODOEX endpoint metadata service.
- `DODO_RPC_PROXY_URL`: fallback proxy URL for metadata/provider flows.
- `DODO_RPC_EXTRA_HTTP_URLS`: curated Polygon HTTP endpoints appended to DODO
  metadata and then health-scored by Redis-backed transport lanes.
- `ENABLE_DRPC_DATA_API`: indexed wallet/portfolio/position enrichment only.
- Moralis and Balancer API keys support off-chain discovery/data import, not raw
  EVM transaction broadcast or exact route truth.

Indexed REST APIs can enrich dashboards, accounting, liquidation discovery, and
wallet/portfolio context. They must not decide route executability.

## Smart Sessions

- `ENABLE_SMART_SESSIONS`: optional delegated wallet permissioning.
- `SESSION_SIGNER_ENABLED`: enables the optional local dry-run proof lane.
- `SESSION_SIGNER_MODE`: must be `dry_run` until a canary proves external WaaS behavior.
- `WAAS_BROADCAST_ADAPTER_ENABLED`: remains `false` until the canary phase.
- `SMART_SESSIONS_ALLOWED_TARGETS`: contract allowlist.
- `SMART_SESSIONS_ALLOWED_SELECTORS`: selector allowlist.
- `SMART_SESSIONS_MAX_VALUE_WEI`: value cap.

Smart Sessions are an authorization layer, not an arbitrage truth layer. Keep
them out of C1/C2 hot execution until a dedicated WaaS adapter is canary-tested.
Use `python -m omega_v5.session_proof --samples 5 --json` to produce the current
dry-run behavior proof.

## Fork and simulation

- `FORK_UPSTREAM_RPC_URL`: upstream source for Anvil fork creation.
- `FORK_RPC_URL`: local Anvil endpoint.
- `FORK_SIM_RPC_URL`: exact fork simulation endpoint.

The Anvil service, runtime API, engine, and transport layer should resolve the
same read/exact/fork upstream profile. Use `python -m omega_v5.runtime_alignment
--probe --json` to prove file/runtime/fork/broadcast alignment.

## Writable broadcast

- `BROADCAST_RPC_URL`: primary writable transaction submission lane.
- `BROADCAST_WSS_URL`: writable provider WSS companion.
- `BROADCAST_RPC_FALLBACK_URLS`: ordered, explicit HTTP JSON-RPC fallback
  lanes allowed for `eth_sendRawTransaction` after health scoring.
- `BROADCAST_WSS_FALLBACK_URLS`: optional fallback WSS companions.

Live broadcast is isolated from read rotation. Public/free read endpoints are
not automatically promoted merely because they work for reads. They become
broadcast candidates only when they are explicitly present in
`BROADCAST_RPC_FALLBACK_URLS`, pass Chain 137 health probing, and are selected
by the broadcast lane. The sender still signs locally and submits standard
JSON-RPC `eth_sendRawTransaction`; the fallback only changes the transport URL.
The broadcast probe also checks method availability with an intentionally
invalid raw transaction and accepts only the expected invalid-transaction class
of response. It does not submit a real transaction during proofing.
