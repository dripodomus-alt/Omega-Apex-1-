# Omega Engine: Logistics & Architectural Map

This document defines the high-level and low-level logistics of the Omega arbitrage engine.

## 1. High-Level Architecture
The Omega engine employs an optimized architecture designed for high-speed, low-latency financial execution on Polygon Mainnet (Chain 137).

- **Orchestration & Simulation Layer (TypeScript/Node.js - `server.ts`)**: Acts as the central coordinator ("Race Engineer"). In development, testing, and sandbox environments, it runs an advanced, inline multi-lane RPC/WSS provider pool (supporting dRPC, Tenderly, and PublicNode profiles) with dynamic block progression and auto-benchmarking latency. It drives simulated arbitrage pipelines (covering C1, C2, and Liquidation paths) with realistic execution telemetry.
- **Execution & Discovery Layer (TypeScript / Rust)**: Core system layers (`rust_engine/` and `indexer/omega-polygon-indexer`) define fast, deterministic data processing models, while the full-stack server exposes their lifecycle controls, custom oracle pricing, and validation gates.
- **Monitoring & Control (Frontend - `frontend_integration/`)**: Provides real-time operator observability and control. Features direct stream log terminal connections (optimized with polling state reference preservation to prevent query loops), block-by-block execution traces, and state reconciliation metrics.

## 2. Pipeline Logistics & Task Mapping

| Stage | Responsible Component | Task | Logic/Reasoning |
| :--- | :--- | :--- | :--- |
| **0. Ingestion** | `Multi-Lane Simulated RPC Pool` | Track block progression & latencies | Orchestrates simulated dRPC, Tenderly, and PublicNode endpoints to feed block metrics and events. |
| **1. Discovery** | `Express Pipeline Orchestrator` | Route candidate discovery | Conducts virtual scans of token pairs against production base assets (USDC, WETH, USDT). |
| **2. Evaluation** | `EVM Pipeline Evaluator` | High-fidelity simulation | Evaluates C1/C2 opportunities, calculating gas costs, gross/net profits, and slippage thresholds. |
| **3. Risk/Gate** | `Automated Risk Controller` | Guard-rail validation | Validates candidate integrity, execution probability, and margin safety metrics. |
| **4. Execution** | `Simulated Chain Dispatcher` | Dispatch simulated transaction payload | Generates deterministic TX hashes linked to verified Polygon scans and persists history to state. |
| **5. Visualization** | `Operator Panel (React/TS)` | Polling, telemetry, & logs | Provides low-overhead log terminal rendering, latency visualization, and live controls. |

## 3. Strengthening Strategy

- **Simulated Provider Pool**: We replaced the previous external/unstable TypeScript `RpcManager` module with an inline simulated RPC/WSS pool directly in `server.ts`. This simulated pool represents several high-performance production routes with dynamic latency tracking, solving platform sandboxing limits and enabling 100% reliable offline testing.
- **Low-Overhead Log Terminal**: The real-time engine console (`EngineLogsConsole.tsx`) uses a ref-based polling strategy (`lastIndexRef`) to query only new delta log entries from the server. This prevents stale closure state errors, eliminates duplicate fetch calls, and fixes log fetch poll errors in the iframe view.
- **Gas & Price Oracle Syncing**: An integrated interval loop dynamically adjusts Gwei prices and RPC latencies every 12 seconds, mirroring realistic active chain conditions for robust front-end verification.
- **Deterministic Economics**: Net and gross profitability calculations are calculated server-side to guarantee a single, unified source of financial truth.

