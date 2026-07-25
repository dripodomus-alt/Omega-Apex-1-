# AGENTS.md — Grok Chat rules for this project

> Auto-generated for **Grok Chat** (xGrok). Keep this file updated so the agent stays efficient.

## Project
- **Name / stack:** Hybrid Python + Rust (Omega V5 arbitrage engine)
- **Primary language:** Python (core) + Rust (engine)
- **Run:** `python -m omega_v5.main` or `.\scripts\ops\start_direct.ps1`
- **Test:** `pytest`
- **Benchmark + Readiness:** `.\scripts\run_full_benchmark_and_readiness.ps1`

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
