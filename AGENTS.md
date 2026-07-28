# AGENTS.md — Grok Chat rules for this project

> Auto-generated for **Grok Chat** (xGrok). Keep this file updated so the agent stays efficient.

## Project
- **Name / stack:** Hybrid Python + Rust (Omega V5 arbitrage engine)
- **Primary language:** Python (core) + Rust (engine)
- **Run:** `python -m omega_v5.main` or `.\scripts\ops\start_direct.ps1`
- **Test:** `pytest`
- **Benchmark + Readiness:** `.\scripts\run_full_benchmark_and_readiness.ps1 -DataGovernanceAudit -BottleneckAnalysis`

## Completed Plans
- **Data Governance:** Fully implemented via `docs/data_governance.md` (roles, lifecycle for cache/SQL/indexer, audits in readiness script, encryption, compliance). All data flows (pools, opportunities, execution traces) now follow the 9-point policy.
- **Revert Prevention:** `execution.py` now uses pending-block eth_call pre-flight simulation. Strict `actualProfit < MIN_PROFIT_POL` suppression added to `revalidate_profitability_at_broadcast`. `mev.py` implements FastLane Private Relay to drop conflicting txs off-chain, avoiding revert gas fees. Config vars added to `config.py`.
- **Performance/Bottleneck:** `compare_scanners.py` and PS1 enhanced with JSON output, multi-config runs, and integrity gates.
- **C1×C2 Logging Model:** Hierarchical OPPORTUNITY → C1 → C2 logging. Canonical IDs in `omega_v5/cycle_ids.py`, logger in `omega_v5/cycle_logger.py`, schema in `omega_v5/db/schema.sql`, state machine hooks in `omega_v5/state_machine.py`, API routes in `omega_v5/cycle_api.py`, docs in `docs/c1_c2_logging_model.md`. Tests: `pytest tests/test_cycle_logging.py`. Rule: C2 cancelled unless C1 confirmed success. No secrets in cycle logs; retention per `docs/data_governance.md`.

## Live Integration Tests
- Use `OMEGA_LIVE_TEST=1`. Dry-run default. Never broadcast without explicit flags.

## Rust Scanner & Quality
- Maturin build required for `scanner_core`.
- All staged routes pass sequence proof, ID alignment, pending simulation, and governance validation.
- Changes must respect `docs/data_governance.md` and `.xgrok/SECURITY.md`.
- Rust cycle event vocabulary: `rust_engine/src/cycle_events.rs` (aligned with Python logger).

This file is now in sync with all approved plans.
