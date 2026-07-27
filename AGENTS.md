# AGENTS.md — Grok Chat rules for this project

> Auto-generated for **Grok Chat** (xGrok). Keep this file updated so the agent stays efficient.

## Project
- **Name / stack:** Hybrid Python + Rust (Omega V5 arbitrage engine)
- **Primary language:** Python (core) + Rust (engine)
- **Run:** `python -m omega_v5.main` or `.\scripts\ops\start_direct.ps1`
- **Test:** `pytest`
- **Benchmark + Readiness:** `.\scripts\run_full_benchmark_and_readiness.ps1`

## Live Integration Tests (New)
- Use `OMEGA_LIVE_TEST=1` or `LIVE_TEST_RPC_URL=...` to enable live data paths.
- Run with: `pytest -m live_integration -q`
- Tests now cover:
  - Real scanner / opportunity_ranker with live pools
  - C1 / C2 / LIQUIDATION execution families
  - Re-profitability gate at broadcast time (`revalidate_profitability_at_broadcast`)
- Never run live tests with real mainnet broadcast unless `EXEC_MODE=live`, `LIVE_FLAG=1`, and `CONFIRM_FLAG=1` are explicitly set.
- Dry-run is the default.

## Rust Scanner Integration (Maturin) - Locked Canon
- The high-performance price-driven scanner lives in the root Rust crate (`scanner_core` via lib.rs).
- **Maturin setup (run these commands exactly):**
  1. In the workspace root (where Cargo.toml + lib.rs live):
     pip install maturin
     maturin develop
  2. Then run the tests:
     pytest tests/rust/test_scanner_core.py
  3. Optional benchmark:
     python scripts/benchmark_rust_scanner.py
  4. Optional Colab runner:
     python scripts/run_apex_omega_colab_scanner.py
- Python bridge: `omega_v5/rust_scanner.py` and root `rust_scanner.py` (auto-falls back to pure Python if extension not built).
- **Canon rules (Rust is the single source of truth):**
  - Pure price-driven selection only: min executable_buy_price for buy leg, max executable_sell_price for sell leg.
  - Strict gates enforced in Rust: TVL >= 50k USD, chain_id=137, different pools, buy_price < sell_price.
  - Metadata (protocol, address) carried for DNA/proof but NEVER used for selection or ranking.
  - Uniswap V

## Canonical Modules (Finalized + Updated)
- **Capital Injector**: `omega_v5/capital_injector.py` is the OFFICIAL and ONLY path for flash loan sizing.
- **Accountant**: `omega_v5/accountant.py` for fire-and-forget Redis + SQL audit.
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
