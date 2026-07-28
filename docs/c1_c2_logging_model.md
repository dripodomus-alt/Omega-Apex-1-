# C1 × C2 Logging Model

Canonical hierarchical logging for Omega V5 opportunities.

## Core Logging Law

```text
1 opportunity_id
  ├── C1 cycle log
  └── C2 cycle log
```

C1 and C2 are linked by:

```text
opportunity_id
c1_cycle_id
c2_cycle_id
parent_c1_tx_hash
route_hash
state_hash
config_hash
block_anchor
```

**Rule:** If `c1_status != CONFIRMED_SUCCESS`, then `c2_status = CANCELLED`. C2 cannot exist without C1.

## Canonical IDs

Implemented in `omega_v5/cycle_ids.py`:

- `opportunity_id` — hash(chain_id, discovered_block, buy_pool, sell_pool, borrow_asset, route_hash, state_hash, config_hash)
- `c1_cycle_id` — hash(opportunity_id, "C1", discovery_block, route_hash)
- `c2_cycle_id` — hash(opportunity_id, "C2", c1_tx_hash, c1_confirmed_block, post_c1_state_hash, c2_route_hash)

## Modules

| Module | Role |
|--------|------|
| `omega_v5/cycle_ids.py` | Deterministic ID builders |
| `omega_v5/cycle_logger.py` | Hierarchical logger, JSONL, machine-state object |
| `omega_v5/db/schema.sql` | PostgreSQL tables: opportunities, c1_cycles, c2_cycles, cycle_events, … |
| `omega_v5/state_machine.py` | Emits C1/C2 lifecycle into cycle_logger |
| `omega_v5/api.py` | `/cycles/recent`, `/cycles/{opportunity_id}` dashboard endpoints |

## Cycle Log Shape

```text
OPPORTUNITY
  ├── DISCOVERY LOG
  ├── C1 LOG (candidate → quote → sizing → sim → payload → submission → settlement)
  └── C2 LOG (post-C1 reload → mirror/reverse/noop → sim → payload → submission → settlement)
```

## Event Types

`DISCOVERED`, `PRICE_EDGE_VALIDATED`, `SIZE_SELECTED`, `PROFIT_VALIDATED`, `SIM_STARTED`, `SIM_PASSED`, `SIM_FAILED`, `PAYLOAD_BUILT`, `SUBMITTED_PRIVATE`, `SUBMITTED_PUBLIC`, `CONFIRMED`, `REVERTED`, `SETTLED`, `C2_WINDOW_OPENED`, `POST_C1_STATE_RELOADED`, `C2_MIRROR_EVALUATED`, `C2_REVERSE_EVALUATED`, `C2_NOOP_SELECTED`, `C2_EXPIRED`, `ARCHIVED`, `CANCELLED`

## Closure Paths

```text
DISCOVERED → C1_SIMULATED → C1_SUBMITTED → C1_SETTLED
  → POST_C1_STATE_RELOADED → C2_DECIDED
  → C2_SETTLED | C2_NOOP | C2_EXPIRED
  → OPPORTUNITY_CLOSED
```

Combined PnL:

```text
combined_realized_net_usd = c1_realized_net_usd + c2_realized_net_usd
```

## Durability

- Hot path: in-memory + append-only JSONL under `out/cycle_events.jsonl`, `out/opportunities.jsonl`
- Dashboard snapshot: `out/cycle_machine_state.json`
- Cold path: PostgreSQL via `schema.sql` / `migrate.py` (same fire-and-forget pattern as accountant)

## Security / Governance

- No private keys or secrets in cycle logs
- Retention and ownership follow `docs/data_governance.md`
- Dry-run default; live submission still gated by EXEC_MODE / LIVE_FLAG

## Tests

```bash
pytest tests/test_cycle_logging.py -q
```
