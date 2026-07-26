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
- All sizing MUST go through `compute_optimal_injection`.
- **Accountant**: `omega_v5/accountant.py` for fire-and-forget Redis + SQL audit.
- **RPC Quota Manager (NEW)**: Plan quota feature in `omega_v5/rpc_layer.py` + `config.py`.
  - Enforces Developer plan limits (25 RPS, 3M request units).
  - Use `quota_manager.can_make_request()`, `record_request()`, `get_quota_stats()`.
  - Integrated into Web3 providers (QuotaAwareHTTPProvider), preflight, pnl_analyzer, and verification paths.
  - Set `RPC_QUOTA_ENFORCEMENT=true` in .env.
  - Heavy methods (eth_getLogs, debug_trace*) cost more units per RPC_UNIT_COSTS.

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
- `notebooks/` — Jupyter matrix setups

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

Always prefer this over manually calling individual scripts.

## Commands Grok may use
- Build/test/package via allowlisted terminal tools only
- Prefer the master benchmark script for evaluation tasks

## Finalized Build Notes
- Capital injector + cannibal guard + derivative formula are now the single source of truth for sizing.
- Notebook matrix setup includes asset registry + injector simulation.
- Validate with: python scripts/ops/validate_config.py
- RPC quota now gates heavy operations to respect provider plans.
- Always call get_quota_stats() before expensive discovery loops.
