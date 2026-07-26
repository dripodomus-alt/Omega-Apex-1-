# AGENTS.md — Grok Chat rules for this project

> Auto-generated for **Grok Chat** (xGrok). Keep this file updated so the agent stays efficient.

## Project
- **Name / stack:** Hybrid Python + Rust (Omega V5 arbitrage engine)
- **Primary language:** Python (core) + Rust (engine)
- **Run:** `python -m omega_v5.main` or `.\scripts\ops\start_direct.ps1`
- **Test:** `pytest`
- **Benchmark + Readiness:** `.\scripts\run_full_benchmark_and_readiness.ps1`

## Canonical Modules (Finalized + Updated)
- **Capital Injector**: `omega_v5/capital_injector.py` is the OFFICIAL and ONLY path for flash loan sizing.
- **Accountant**: `omega_v5/accountant.py` for fire-and-forget Redis + SQL audit.
- **RPC Quota Manager**: ...
- **New: Sequence Proof & Payload Alignment**: `invariant_math.verify_buy_low_sell_high_sequence()` and `config.build_protocol_sequence_ids()` are now **required** in `route_execution_stager.py`, `pipeline_validation.py`, `payload_envelope.py`, `execution.py`, and `execution_truth.py`. All routes must pass before staging or execution. Updated per the plan to fix protocol ID misalignment and missing economic invariant enforcement.

## How Grok should work here
1. Prefer **read_file / write_file** over shell for source changes.
2. Write **complete files** (no partial patches unless asked).
3. Stay inside the workspace; never invent secrets or API keys.
4. After tools, give a short summary: what changed + paths.
5. Match existing style (format, naming, folder layout).
6. Do not open editor tabs for the user — files are saved on disk by tools.

## Layout
- `omega_v5/` — main Python package (now includes hardened execution/staging gates)
- ... (rest preserved)

## Quality bar
- Clear names, small functions, typed public APIs when the language supports it.
- **All staged routes must now pass sequence proof and ID alignment** (new non-negotiable gate).
- Handle errors explicitly; no silent swallows.
- Keep configs consistent with the stack.

(The rest of the file is preserved; this update documents the new invariants.)
