# AGENTS.md — Grok Chat rules for this project

> Auto-generated for **Grok Chat** (xGrok). Keep this file updated so the agent stays efficient.

## Project
- **Name / stack:** Hybrid Python + Rust (Omega V5 arbitrage engine)
- **Primary language:** Python (core) + Rust (engine)
- **Run:** `python -m omega_v5.main` or `.\scripts\ops\start_direct.ps1`
- **Test:** `pytest`
- **Benchmark + Readiness:** `.\scripts\run_full_benchmark_and_readiness.ps1`

## Canonical Modules (Finalized)
- **Capital Injector**: `omega_v5/capital_injector.py` is the OFFICIAL and ONLY path for flash loan sizing.
  - Segregated CAPITAL_SOURCE_REGISTRY vs EXECUTION_VENUE_REGISTRY
  - Hard self-cannibalization guard (blocks before any math)
  - Exact derivative formula: OptimalSize = (sqrt(Rin * Rout * (1-f_swap)*(1-f_flash)) - Rin) / (1 - f_swap)
  - Must be called via `compute_optimal_injection` / `prepare_sizing_for_rust` / `optimal_flash_injection` before Rust engine or stager sizing.
- All sizing in opportunity_ranker, route_execution_stager, and notebooks MUST go through it.

## How Grok should work here
1. Prefer **read_file / write_file** over shell for source changes.
2. Write **complete files** (no partial patches unless asked).
3. Stay inside the workspace; never invent secrets or API keys.
4. After tools, give a short summary: what changed + paths.
5. Match existing style (format, naming, folder layout).
6. Do not open editor tabs for the user — files are saved on disk by tools.

## Layout
- `omega_v5/` — main Python package
- `rust_engine/` — high-performance Rust component
- `scripts/` — PowerShell orchestration (ops, pm2, reporting)
- `tests/` — pytest suite
- `docs/` — architecture and runbooks
- `notebooks/` — Jupyter matrix setups (asset + capital injector)

## Quality bar
- Clear names, small functions, typed public APIs when the language supports it.
- Handle errors explicitly; no silent swallows.
- Keep configs consistent with the stack.

## Security (non-negotiable)
- Never commit secrets, tokens, or `.env` with real credentials.
- Validate untrusted input at boundaries.
- Prefer dependency lockfiles.
- Path access only under project root.

## Context efficiency
- Read only files needed for the task.
- Avoid dumping entire build dirs.
- Prefer focused edits.

## Benchmarking & Readiness
When asked to "run all scripts and benchmark", use the master script:
`.\scripts\run_full_benchmark_and_readiness.ps1`

It safely runs:
- Prerequisite checks
- pytest
- preflight + pipeline_validation
- Anvil fork benchmark (never live-fire)
- Dry-run simulator
- Computes 0-100 readiness score

Always prefer this over manually calling individual scripts.

## Commands Grok may use
- Build/test/package via allowlisted terminal tools only
- Prefer the master benchmark script for evaluation tasks

## Finalized Build Notes
- Capital injector + cannibal guard + derivative formula are now the single source of truth for sizing.
- Notebook matrix setup includes asset registry + injector simulation.
- Validate with: python scripts/ops/validate_config.py and python scripts/ops/simulate_capital_injector.py
