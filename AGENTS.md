# AGENTS.md — Grok Chat rules for this project

> Auto-generated for **Grok Chat** (xGrok). Keep this file updated so the agent stays efficient.

## Project
* **Name / stack:** Hybrid Python + Rust (Omega V5 arbitrage engine)
* **Primary language:** Python (core) + Rust (engine)
* **Run:** `python -m omega_v5.main` or `.\scripts\ops\start_direct.ps1`
* **Test:** `pytest`
* **Benchmark + Readiness:** `.\scripts\run_full_benchmark_and_readiness.ps1 -DataGovernanceAudit -BottleneckAnalysis`

## Project Snapshot (as of 2026-07-15)

The project is a high-performance arbitrage engine for EVM chains, primarily Polygon. It uses a hybrid Python/Rust architecture. Python handles high-level orchestration, data loading, state management, and pricing models. Rust is used for specialized, high-speed scanning and rule-based tasks. The system is designed to be inseparable; both components are required for it to function.

**Key Features:**
- **Arbitrage & Liquidations:** Supports multi-hop DEX arbitrage and Aave V3 liquidations.
- **Simulation & Validation:** A rigorous multi-stage validation pipeline (`DISCOVERED` → `RANKED` → `SIMULATED` → `PREPARED`) ensures opportunities are economically sound before execution. Final gates use `eth_call` simulations for on-chain truth.
- **ML Alpha Ranker:** An optional machine learning model can re-rank opportunities to optimize the use of the `eth_call` truth-gating budget.
- **Security:** Strong emphasis on safety with dry-run modes, `eth_call` truth gating, and explicit confirmations for live execution. Secrets are managed via environment variables or secure secret stores, never committed to git.

**Recent Major Updates:**
- **Data Governance Framework:** A comprehensive data governance policy (`docs/data_governance.md`) has been implemented. This includes policies for data ownership, quality, security, and lifecycle management. All data flows (pool data, opportunities, execution traces) now adhere to this policy.
- **Revert Prevention:** The `execution.py` module now uses a pre-flight `eth_call` simulation on the pending block to catch potential reverts. A strict profit check (`actualProfit < MIN_PROFIT_POL`) has been added to suppress unprofitable transactions. The `mev.py` module implements a private relay to avoid revert gas fees by dropping conflicting transactions off-chain.
- **Performance & Bottleneck Analysis:** The `compare_scanners.py` script and its PowerShell wrapper have been enhanced with structured JSON output, support for multi-configuration runs, and data integrity gates to help identify performance bottlenecks.
- **New: Sequence Proof & Payload Alignment**: `invariant_math.verify_buy_low_sell_high_sequence()` and `config.build_protocol_sequence_ids()` are now **required** in `route_execution_stager.py`, `pipeline_validation.py`, `payload_envelope.py`, `execution.py`, and `execution_truth.py`. All routes must pass before staging or execution. Updated per the plan to fix protocol ID misalignment and missing economic invariant enforcement.

## How Grok should work here

**Data Governance:** This project now adheres to a strict data governance policy outlined in `docs/data_governance.md`. All code changes must respect the principles of data ownership, quality, security, and lifecycle management defined therein. As an agent, you are a steward of this data and must act accordingly.

1. Prefer **read_file / write_file** over shell for source changes.
2. Write **complete files** (no partial patches unless asked).
3. Stay inside the workspace; never invent secrets or API keys.
4. **Always respect the data governance and security policies** (`docs/data_governance.md`, `.xgrok/SECURITY.md`).
5. When modifying operational scripts (PowerShell), ensure they remain robust and provide clear user feedback.
6. For Python code, adhere to the existing architecture (e.g., use `web3.py` for core logic, respect the module structure).
7. When adding new features, consider how they fit into the existing testing and readiness framework (`benchmarks/run_full_benchmark_and_readiness.ps1`).
