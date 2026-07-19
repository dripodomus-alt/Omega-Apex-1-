# Sourced Logic Integration

Omega uses external sources in three different trust classes.

## Class 1: Execution Truth

These sources can affect C1/C2/liquidation execution eligibility:

- Direct Polygon RPC reads at the relevant block.
- CLMM quoters and exact-call simulation.
- Anvil fork simulation.
- Verified executor/adapters and on-chain adapter slots.
- Isolated writable broadcast RPC.

Class 1 data must be fresh, chain-matched, and block-aware. It is never replaced
by indexed REST APIs.

## Class 2: Discovery and Enrichment

These sources improve coverage and ranking context but cannot alone make a route
executable:

- dRPC Data & Wallet API.
- Moralis Data API.
- Balancer API.
- Polygon token list.
- DODOEX endpoint metadata provider.
- Future NodeCore metrics.

Use these for wallet positions, token metadata, historical PnL, candidate
discovery, and dashboard context. Every candidate promoted from Class 2 must
still pass Class 1 exact-call and fork gates.

## Class 3: Authorization and Operations

These sources can improve control-plane safety but do not create market truth:

- Smart Sessions.
- WaaS/session keys.
- Operator API tokens.
- UI live/dry-run controls.

Use them for scoped, revocable access and operator workflows. They should never
bypass profitability, flashloan repayment, adapter, or broadcast guards.

## Current Policy

- dRPC load-balanced endpoints are first-class read/WSS/exact-call candidates.
- NodeCore is configured as optional, disabled by default.
- dRPC Data API is configured as optional, disabled by default.
- Smart Sessions are configured as an optional `SESSION_SIGNER` dry-run proof
  lane. `WAAS_BROADCAST_ADAPTER` remains disabled and outside the live arbitrage
  hot path until a separate canary proves external WaaS Prepare/Execute
  behavior.
- Broadcast remains isolated in `BROADCAST_RPC_URL`.

## Proof Commands

Run these before treating the runtime as production-aligned:

```powershell
python -m omega_v5.session_proof --samples 5 --json
python -m omega_v5.runtime_alignment --probe --json
```

Artifacts:

- `out/session_signer_proof_latest.json`
- `out/runtime_alignment_latest.json`

API:

- `GET /api/proofs/session-signer`
- `POST /api/proofs/session-signer/run?samples=5`
- `GET /api/proofs/runtime-alignment`
- `POST /api/proofs/runtime-alignment/run?probe=true`

The session proof passes only when the delegated lane is dry-run scoped,
allowlisted, exact-call backed, and remote execution remains fail-closed. It does
not claim external WaaS transaction behavior is proven unless a real WaaS URL,
credential, and wallet binding are configured and a dedicated canary is run.
