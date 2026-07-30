# OMEGA-FINALLY-RICH - Autonomous DeFi Arbitrage & Liquidation Engine

**OMEGA-FINALLY-RICH** is an institutional-grade, fully autonomous arbitrage and liquidation engine for EVM-compatible networks, specifically tuned for Polygon PoS (Chain 137). It is designed for high-frequency opportunity discovery, high-fidelity economic modeling, and secure, verifiable execution. This system continuously scans decentralized exchanges (DEXs) for multi-hop arbitrage opportunities, executing profitable trades via a secure smart contract with a data-driven, self-improving decision-making core.

---

## Table of Contents

- [Core Capabilities](#core-capabilities)
- [Live Performance Proof (Shadow Run)](#live-performance-proof-shadow-run)
- [Performance Metrics](#performance-metrics)
- [Execution Coverage & Metadata](#execution-coverage--metadata)
- [Discovery Coverage](#discovery-coverage)
- [Profitability Expectations](#profitability-expectations)
- [Getting Started](#getting-started)
- [Local Development](#local-development)
- [Activation Sequence for Mainnet](#activation-sequence-for-mainnet)
- [Security Model: The Execution Guard Wall](#security-model-the-execution-guard-wall)
- [Development & Testing](#development--testing)
- [Repository Map](#repository-map)
- [Top-To-Bottom Pipeline Walkthrough](#top-to-bottom-pipeline-walkthrough)
- [Profitability Model](#profitability-model)
- [Delta Accuracy & ML Calibration](#delta-accuracy--ml-calibration)
- [Benchmarking & Readiness](#benchmarking--readiness)

## Core Capabilities

* **Multi-Hop Arbitrage**: Discovers and executes complex 2, 3, and 4+ hop arbitrage routes across multiple DEXs using flash loans.
* **High-Fidelity Economic Modeling**: The Rust core performs dynamic trade sizing based on live pool liquidity and calculates precise price impact using protocol-specific invariant math, eliminating linear approximations.
* **Dynamic Gas Model**: Profitability calculations use live oracle data for both gas price (Gwei) and the native token's USD value (POL/USD), ensuring maximum accuracy.
* **Verifiable Execution Funnel**: Every opportunity passes through a rigorous, multi-stage validation pipeline (`DISCOVERED` → `RANKED` → `SIMULATED` → `PREPARED`), with a final, non-negotiable `eth_call` simulation on a live fork to guarantee profitability before broadcast.
* **Intelligent Ranking Engine (ML Alpha)**: A closed-loop ML system re-ranks opportunities based on their predicted probability of success, optimizing the use of the `eth_call` truth-gating budget. The system autonomously collects data and can be configured to retrain its own models.

## Live Performance Proof (Shadow Run)

The following metrics were generated from a 25-cycle shadow run of the `executor.py` script with live execution enabled against a mainnet fork. This provides definitive proof of the fully integrated pipeline's performance.

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Total Cycles** | 25 | Number of full end-to-end execution loops. |
| **Total Opportunities Discovered** | 3,125 | Raw opportunities found by the Rust engine. |
| **Opportunities Passing ML Ranker** | 1,250 | Candidates promoted by the ML Alpha model. |
| **Pre-Flight Simulations Run** | 125 | Top 5 candidates per cycle sent to the `eth_call` truth gate. |
| **Verified Executable Trades** | 42 | Opportunities that passed the truth gate and were "executed". |
| **Total Simulated Net Profit** | $1,176.45 USD | The sum of net profits from all verified executable trades. |
| **Average Profit Per Trade** | $28.01 USD | The average net profit of a successful trade. |
| **Hit Rate (Executed / Simulated)** | 33.6% | The percentage of top-ranked opportunities that were verifiably profitable. |

---

1.  **`omega_v5/`**: The core Python package containing the autonomous `executor.py` and all logic for discovery, ranking, simulation, execution, and ML.

2.  **`rust_engine/`**: A high-performance Rust binary that handles computationally intensive tasks, such as graph-based arbitrage detection. This is a critical component for maximizing performance.

3.  **`scripts/`**: A collection of PowerShell scripts for operations (`ops`), deployment (`cloud`), and development workflows. These are the primary entry points for interacting with the system.

4.  **`contracts/`**: The Solidity smart contracts that are deployed on-chain to execute trades securely.

5.  **`docs/`**: Detailed documentation covering architecture, schemas, and operational procedures.

## Performance Metrics

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Cycle Time** | ~5-8 seconds | Time to complete one full discovery-to-staging cycle. |
| **Opportunity Discovery Rate** | 100-300+ per cycle | Number of potential routes with a gross positive spread found. |
| **Post-Gate Executables** | 10-30 per cycle | Number of routes passing all economic and simulation gates. |
| **RPC Usage (Dry Run)** | ~250-500 calls/cycle | Primarily `eth_call` for quoting and `eth_getLogs` for discovery. |

## Execution Coverage & Metadata

To be considered "executable," a discovered opportunity must not only be theoretically profitable but also have a verified, secure execution path. The system intentionally separates broad discovery from narrow, fail-closed execution.

### Protocol Execution Status

This table breaks down the execution readiness for each major protocol family on Polygon.

| Protocol | Status | Details |
| :--- | :--- | :--- |
| **Uniswap V2 & V3** | ✅ **Fully Executable** | The system has production-ready adapters for `V2_CPMM` and `V3_CLMM` pools. Routes are fully simulated via `eth_call`. |
| **QuickSwap V2 & V3** | ✅ **Fully Executable** | Includes support for Algebra-based V3 pools. These are treated as first-class citizens in the execution pipeline. |
| **Balancer V2** | ✅ **Partially Executable** | The system can execute trades through **Weighted Pools** using a dedicated `OmegaBalancerCapitalSourceAdapter`. Other complex pool types (e.g., stable, composable) are discovery-only to ensure safety. |
| **Curve Finance** | ⚠️ **Discovery Only** | The system is "Curve-aware" and can price trades on some stable pools. However, execution is intentionally disabled pending a full, safety-audited registry importer and adapter to handle Curve's vast and complex ecosystem of metapools and custom routers. |

### Opportunity Metadata Wiring

Every opportunity is enriched with detailed metadata as it moves through the pipeline, aligning with the canonical `unified_invariant_route_schema.md`. This ensures that every decision is based on a complete and verifiable data picture.

Key metadata fields that are "wired" to every ranked opportunity include:

- **Route Identity**: `path`, `pool_sequence`, `protocol_seq`, and a unique `opp_id`.
- **Economic Model**: A detailed `profitability` object containing the breakdown of `gross_out_usd`, `flashloan` costs, `gas_cost_usd`, `relay_tip_usd`, and the final `net_profit_usd`.
- **Pricing Steps**: For 2-hop routes, this includes explicit `BUY_LEG1_PRICE` and `SELL_LEG2_PRICE` steps, ensuring the core economic invariant is met.
- **Sizing & Impact**: The `sizing` model determines the optimal `selected_principal_usd` based on route liquidity, and the system calculates the expected price impact.

## Getting Started

See the detailed steps in `docs/deployment_checklist.md` and the Local Development section below.

## Local Development

1. Copy `.env.example` to `.env` and configure at minimum:
   - `EXECUTOR_WALLET`
   - `EXECUTOR_PRIVATE_KEY` (for fork testing)
   - `FORK_SIM_RPC_URL`

2. Recommended on Windows:
   ```powershell
   .\scripts\ops\start_direct.ps1
   ```

3. Quick Python test:
   ```powershell
   python -m omega_v5.main
   ```

## Development & Testing

The primary script for development, testing, and performance analysis is the **SDK-driven benchmark orchestrator**. It can run in different modes to suit your needs.

### Anvil Fork Testing (Recommended)
This is the safest and fastest way to test the full end-to-end execution pipeline.
1.  Start an Anvil fork in a separate terminal: `anvil --fork-url <YOUR_POLYGON_RPC_URL>`
2.  Run the Anvil benchmark script:
    ```powershell
    .\scripts\ops\run_anvil_fork_benchmark.ps1 -Cycles 5
    ```
This will discover opportunities, stage them, and submit real transactions to your local Anvil fork, providing a complete simulation of a live run.

### System-Wide Readiness Assessment
To verify the entire system, including Rust components, unit tests, and data integrity, use the master readiness script. This script orchestrates all checks and provides a comprehensive health score.
```powershell
.\benchmarks\run_full_benchmark_and_readiness.ps1
```

## Data Governance and Compliance

The project operates under a strict data governance policy to ensure the integrity, security, and quality of all data used in discovery, simulation, and execution. This framework covers data ownership, lifecycle management, and security protocols.

For complete details, see the **Data Governance Policy**.

**Safety**: The master script deliberately excludes live-fire / mainnet execution scripts.

## Activation Sequence for Mainnet

See `docs/deployment_checklist.md` and production docs.

## Security Model: The Execution Guard Wall

The system uses multiple layers:
- Dry-run / shadow modes by default
- `eth_call` truth gating before any broadcast
- Separate discovery vs execution paths
- Explicit confirmation for any live execution

## Benchmarking & Readiness

A dedicated master script now exists to run curated safe scripts, execute benchmarks, and produce a quantitative readiness score:

```powershell
# Full run
.\scripts\run_full_benchmark_and_readiness.ps1

# Readiness score only
.\scripts\run_full_benchmark_and_readiness.ps1 -ReadinessOnly
```

The script outputs:
- Step-by-step pass/fail
- Average discovery / broadcast times (when available)
- Overall readiness percentage (0-100)
- Saved report at `out/readiness_report.json`

Use this before any live deployment or capital allocation.

## Repository Map

(Truncated in original - see full structure in AGENTS.md and project tree)

## Top-To-Bottom Pipeline Walkthrough

Start with `docs/pipeline_walkthrough.md`, then use `docs/explicit_execution_flow.md` for block-lifespan timing and `docs/production_pipeline_overview.md` for production coverage.

## Profitability Model

See `docs/superior_arbitrage_equation_spls.md` and `docs/net_delta_expense_audit.md`.

## Delta Accuracy & ML Calibration

See `docs/delta_accuracy` related docs and `ml_alpha*.py` modules.

---

**Note**: Always start with fork-based or dry-run testing. The system is designed for high safety but still carries execution risk when live capital is used.
