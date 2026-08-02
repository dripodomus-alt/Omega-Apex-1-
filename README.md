# Apex Omega V5

**A high-frequency, MEV-focused arbitrage system for EVM-compatible networks.**

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/The-Urban-Genius/Apex-OmegaV5)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](https://github.com/The-Urban-Genius/Apex-OmegaV5)
[![Readiness Score](https://img.shields.io/badge/readiness-100%25-brightgreen.svg)](out/readiness_report_latest.json)

---

**Apex Omega V5** is an institutional-grade, systematic arbitrage bot designed to identify and capitalize on pricing inefficiencies across decentralized exchanges (DEXs). It combines a high-performance Rust discovery engine, a robust Python execution pipeline, and a comprehensive suite of operational tools for testing, simulation, and secure deployment.

This system is engineered for **Speed**, **Market Coverage**, and **Execution Precision**—the three pillars of successful MEV arbitrage.

> **Disclaimer:** This is a sophisticated financial tool that executes real transactions and manages private keys. It carries significant financial risk. The user is solely responsible for its configuration, operation, and any resulting financial outcomes. There is no guarantee of profit.

## ► Core Capabilities

| Capability | Description | How to Verify |
| :--- | :--- | :--- |
| **Speed** | The system is optimized for low-latency opportunity identification and transaction submission. A Rust-based discovery module (`omega_v5_rs`) performs parallelized calculations, feeding a highly-optimized Python SDK pipeline for direct, low-level transaction broadcasting. | Run the **Anvil Fork Benchmark** (`run_anvil_fork_benchmark.ps1`) to measure the end-to-end cycle time from block processing to simulated transaction execution in a controlled environment. |
| **Market Coverage** | Omega V5 performs exhaustive, graph-based discovery of liquidity pools and multi-hop arbitrage routes across all configured protocols. The system is designed to see the entire configured trading universe, not just a static list of pairs. | Run the **Maximum Coverage Discovery** (`run_max_coverage_discovery.ps1`). This read-only script generates a `live_pool_scan_report.json` detailing every liquidity pool the system can find, proving the depth of its market visibility. |
| **Precision** | Every potential arbitrage is validated against a series of internal proofs and can be simulated against a live mainnet fork before execution. This ensures that the calculated profit accounts for gas fees, slippage, and contract interactions, minimizing failed transactions and wasted gas. | Use the **Route Proof Matrix** (`route_proof_matrix.py`) and the **Anvil Fork Benchmark** to validate the profitability and success rate of the execution logic without risking capital. |
| **Profitability** | The ultimate goal. By combining speed, coverage, and precision, the system is designed to execute profitable trades autonomously. Profitability is tracked and can be analyzed through logs and telemetry. | The **Anvil Fork Benchmark** provides a risk-free estimate of profitability. The **Live-Fire Benchmark** (`run_live_fire_benchmark.ps1`) provides real-world performance data. Profitability is not guaranteed and is subject to market conditions. |

## ► System Architecture

Omega V5 is a polyglot system, using the best language for each task:

-   **`PowerShell Core` (Operations & Orchestration):** Serves as the primary user-facing control plane. Scripts handle setup, deployment, benchmarking, and operational safety checks, providing a consistent and safe entry point for all system tasks.

-   **`Python` (Core Logic & Execution):** The main application pipeline is written in Python, leveraging `web3.py` for its robust SDK-driven interaction with the blockchain. It manages configuration, orchestrates the discovery and execution phases, and handles transaction signing and broadcasting.

-   **`Rust` (High-Performance Discovery):** The core pool scanning and route-finding logic is implemented in a native Rust extension (`omega_v5_rs`), compiled via `maturin`. This allows for CPU-bound calculations to be performed at near-native speed, far exceeding what is possible in Python alone.

-   **`Foundry (Anvil & Cast)` (Testing & Simulation):** The system is deeply integrated with Foundry. `Anvil` is used to create local mainnet forks for safe, realistic benchmarking. `Cast` is used throughout the operational scripts for quick, reliable on-chain data queries and wallet sanity checks.

-   **`Node.js / TypeScript` (Real-time Indexing):** The `omega-polygon-indexer` is a dedicated service that uses `@maticnetwork/chain-indexer-framework` to listen to real-time chain events, process them, and feed critical data (e.g., new pools, sync events) into the main pipeline via a Kafka message bus.

---

## ► Operational Workflow & Proof of Capabilities

This workflow is designed to build confidence in the system's capabilities in a staged, risk-managed manner. Follow these steps to verify performance before any live deployment.

### Step 1: Full System Readiness Assessment

This is the master script to verify that the entire system is healthy, correctly installed, and performing as expected. It runs a comprehensive suite of checks without executing any live transactions.

```powershell
# From the project root
.\benchmarks\run_full_benchmark_and_readiness.ps1
```

This script validates:
1.  **Prerequisites:** Ensures `python`, `pytest`, `anvil`, etc., are installed.
2.  **Unit Tests:** Compiles the Rust module and runs all Python `pytest` tests.
3.  **Scanner Benchmark:** Stress-tests the Rust vs. Python discovery engines.
4.  **Pipeline Validation:** Runs a dry-run of the full pipeline.
5.  **Anvil Benchmark:** Automatically starts an Anvil fork and runs a multi-cycle benchmark against it.
6.  **Data Integrity:** Checks connectivity and health of Redis/SQLite data stores.
7.  **Route Proofs:** Verifies that the internal math for all major route types is sound.

A `readiness_report_latest.json` is generated in the `out/` directory. **A score of 100 is required before proceeding.**

### Step 2: Verify Maximum Market Coverage

This script demonstrates the system's full discovery capability. It sets unbounded limits and performs a read-only scan of the blockchain to find every possible liquidity pool within the configured protocols.

```powershell
# From the project root
.\run_max_coverage_discovery.ps1
```

**Proof:** Inspect the generated `out/live_pool_scan_report.json`. This file is a complete manifest of the system's market awareness, proving its **Market Coverage**.

### Step 3: Simulate Execution & Profitability on a Fork

This is the most critical step for risk-free testing. It runs the full arbitrage pipeline against a local Anvil fork of Polygon mainnet. It will simulate finding and executing opportunities, reporting a simulated P&L without spending any real gas or capital.

```powershell
# In a separate terminal, start the Anvil fork using your .env configuration
anvil --fork-url $env:FORK_RPC_URL

# In your main terminal, run the Anvil benchmark
.\scripts\ops\run_anvil_fork_benchmark.ps1 -Cycles 10 -MinProfitUSD 10.0
```

**Proof:** Observe the console output. The script will log potential arbitrage opportunities, simulated transaction submissions, and the resulting profit or loss. This validates the **Precision** and simulates the **Profitability** of your strategy.

### Step 4: Live-Fire Benchmark (Use Extreme Caution)

This is the final proof. This script runs the bot in a live, production mode. It will submit **REAL, LIVE, MAINNET TRANSACTIONS** and spend **REAL GAS** from the configured executor wallet.

**WARNING: START WITH MINIMAL CAPITAL. YOU ARE RESPONSIBLE FOR ANY AND ALL FINANCIAL LOSS.**

```powershell
# Acknowledge the risk and run for 5 cycles
.\scripts\ops\run_live_fire_benchmark.ps1 -ConfirmLiveFire -Cycles 5
```

The script performs numerous safety checks (chain sync, wallet key mismatch, etc.) before asking for final user confirmation.

**Proof:** This is the ultimate test of **Speed** and live **Profitability**. Monitor the console output and your wallet balance on a block explorer.

---

## ► Performance & Profitability Expectations

Providing exact performance figures is misleading, as they are highly dependent on four key external factors: **Market Conditions**, **Capital Allocation**, **Gas Prices**, and **RPC Latency**. The system provides the *capability*, but its success is a function of how it's deployed and the environment it operates in.

### Measuring Performance

Instead of providing static numbers, we believe in transparently measuring performance in your own environment.

-   **Speed (End-to-End Latency):** This is the time from when a profitable block is received to when your transaction is submitted. You can measure this by analyzing the timestamps logged by the Python pipeline during the Anvil or Live-Fire benchmarks. Latencies are typically measured in milliseconds.

-   **Market Coverage (Pool & Route Count):** The `live_pool_scan_report.json` generated by the max coverage script gives you the exact number of pools and potential routes the bot can see at any given time.

-   **Precision (Success Rate):** During the Anvil benchmark, track the ratio of profitable simulated transactions to total attempts. A high success rate (>95%) in simulation is a strong indicator of a well-configured system.

### Profitability Projections (30/60/90 Day)

**No financial institution or software provider can honestly guarantee future returns in a volatile, adversarial environment like MEV.**

Profitability is an emergent property of your specific configuration, capital, and the prevailing market dynamics. It is not a fixed attribute of the software itself.

**How to Model Your Own Expectations:**

1.  **Run the Anvil Benchmark:** Execute `run_anvil_fork_benchmark.ps1` over an extended period (e.g., 1000+ cycles) against a historical block range or live fork.
2.  **Log Simulated Profits:** Aggregate the `est_profit_usd` from all successful, simulated arbitrage opportunities that the script logs.
3.  **Analyze the Data:** Use this simulated data to build a statistical model. This is the *only* reliable way to project potential returns based on your specific strategy (`MinProfitUSD`), capital, and the historical market data you tested against.

This data-driven approach, based on realistic simulation, is infinitely more valuable than any generalized projection we could provide. The system is a tool; its profitability is a measure of the operator's skill in deploying and configuring it.

## ► Deployment

Local execution is for testing and development. True 24/7 operation requires deployment to a dedicated, secure cloud environment (e.g., a GCP or AWS VM). The `Deployment vs. Local` guide provides a critical overview of the security, performance, and reliability differences.

The project includes Ansible playbooks (`setup_polygon_read_node.ps1`) and cloud finalizer scripts to aid in the transition from a local setup to a hardened, autonomous production deployment.
