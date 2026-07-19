# Explicit Execution Flow (Block-Based Lifespan)

## Core Rule (Updated)
- Every route has its own **discovery_block** = `n`
- The route **must be executed** (broadcast) no later than block `n + 4`
- **No artificial sleeps or delays** between stages.
- Goal: Execute **as soon as possible**.
- Cycles are **not synchronized**. Each route lives on its own timeline.
- "By the time data prints, execution for the next trade should already be underway."

## Stage-by-Stage Flow with Block Budgets

| Stage | Description | Block Window (from discovery) | Max Time Budget (approx) | Key Actions | Staleness Check |
|-------|-------------|-------------------------------|--------------------------|-------------|-----------------|
| 1. Discovery | Pools scanned, opportunities found | n | 0–1 block | Raw opportunity creation | None |
| 2. Initial Ranking + Early Gate | Score routes, apply raw gate early | n to n+1 | ~2s | `raw_execution_gate_passes`, filter bad routes | Optional |
| 3. Real Min-Out Simulation | eth_call / fork for actual `min_out` | n+1 to n+2 | ~2s | Get real `buy_min_out_raw`, `sell_min_out_raw` | Check current_block <= n+2 |
| 4. Executor Truth Gate | Final canonical gate with real values | n+1 to n+2 | ~1s | `simulate_route_with_real_min_out` + `raw_execution_gate_passes` | Hard filter |
| 5. Sizing | Decide principal (including partial salvage) | n+2 to n+3 | ~1.5s | `partial_size_salvage_passes_gate` | Check current_block <= n+3 |
| 6. Staging | Non-conflicting selection + nonce reservation | n+2 to n+3 | ~1s | `stage_payload`, final gate re-check | Hard filter |
| 7. Broadcast / Execution | Send transaction | **by n+4** | ~1s | Payload sent | **Must be <= n+4** |

**Total Lifespan**: Discovery block `n` → Execution deadline `n + 4`

## Key Principles

- **Execute ASAP**: Do not wait for the next cycle or for logging to finish. As soon as a route passes the gate and sizing, push it toward staging.
- **Individual Route Lifespan**: A route discovered at block 12345 must be executed by block 12349 at latest.
- **No Global Synchronization**: Different routes can be at different stages at the same time.
- **Early Dropping**: If a route is approaching its deadline (e.g. current_block > discovery_block + 3), drop it aggressively.
- **Printing / Logging**: Must be non-blocking. Data prints must never delay execution.

## Staleness Enforcement

A route is considered **stale** if:
```python
current_block > discovery_block + 4
```

Recommended enforcement points:
- After real simulation
- Before sizing
- Before staging (hard gate)
- In the stager itself

## Updated Flow Pseudocode

```
for each new block:
    for each newly discovered route (at its own n):
        if current_block > n + 4:
            drop(route)   # too late

        rank_and_early_gate(route)
        if not passes_raw_gate:
            continue

        if current_block > n + 2:
            drop(route)   # simulation window missed

        real_min_outs = simulate(route)
        if not raw_execution_gate_passes(real_min_outs):
            continue

        sized = size_with_gate_check(route)
        if not sized:
            continue

        if current_block > n + 3:
            drop(route)

        staged = stage_payload([sized])
        if staged:
            broadcast_asap(staged)   # no delay
```

## Notes on 2-Leg vs 3-Leg under n+4

- 2-leg routes have lower validation cost → higher chance of making it inside n+4.
- 3-leg routes are allowed but must clear the gate faster.
- The system should not artificially prefer one over the other — only net surplus + remaining time budget matters.

## Implementation Requirements

- Every route object must carry `discovery_block`.
- All major decision points must call a staleness check against `current_block`.
- No `time.sleep()` or blocking waits in the hot path.
- Logging / printing must be fire-and-forget.

This replaces the previous 9-second wall-clock stalemate with a per-route block-based lifespan of **n + 4**.
