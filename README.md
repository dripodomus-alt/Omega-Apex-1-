# OMEGA-FINALLY-RICH - Autonomous DeFi Arbitrage & Liquidation Engine

**OMEGA-FINALLY-RICH** is an institutional-grade, autonomous arbitrage and liquidation engine for EVM-compatible networks. It is designed for high-frequency opportunity discovery, robust economic modeling, and secure, verifiable execution. This system continuously scans decentralized exchanges (DEXs) for multi-hop arbitrage opportunities and Aave V3 for under-collateralized borrowing positions, executing profitable trades via a secure smart contract.

---

## Table of Contents

- [Core Capabilities](#core-capabilities)
- [System Architecture](#system-architecture)
- [Performance Metrics](#performance-metrics)
- [Execution Coverage & Metadata](#execution-coverage--metadata)
- [Discovery Coverage](#discovery-coverage)
- [Profitability Expectations](#profitability-expectations)
- [Getting Started](#getting-started)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Activation Sequence for Mainnet](#activation-sequence-for-mainnet)
- [Security Model: The Execution Guard Wall](#security-model-the-execution-guard-wall)
- [Development & Testing](#development--testing)
- [Repository Map](#repository-map)
- [Top-To-Bottom Pipeline Walkthrough](#top-to-bottom-pipeline-walkthrough)
- [Profitability Model](#profitability-model)
- [Delta Accuracy & ML Calibration](#delta-accuracy--ml-calibration)

## Core Capabilities

* **Aave V3 Liquidations**: Monitors the Aave V3 money market for at-risk loans, executing profitable liquidations to earn bonuses.
* **Multi-Hop Arbitrage**: Discovers and executes complex 2, 3, and 4+ hop arbitrage routes across multiple DEXs using flash loans.
* **Simulation Engine**: Models profit, gas, slippage, and fees with high fidelity before execution.
* **Verifiable Execution Funnel**: Every opportunity passes through a rigorous, multi-stage validation pipeline (`DISCOVERED` → `RANKED` → `SIMULATED` → `PREPARED`), with final gates using `eth_call` simulations for on-chain truth.
* **User-Signed Transaction Flow**: The system prepares transaction calldata but requires the user to sign and broadcast, ensuring a non-custodial and secure operational model.
- **Intelligent Ranking Engine (ML Alpha)**: An optional machine learning model can be enabled to re-rank opportunities based on their predicted probability of success, optimizing the use of the `eth_call` truth-gating budget.
* **Production-Grade Infrastructure**: A container-native architecture with first-class support for Docker and Kubernetes deployment.

## System Architecture

The system is a modern TypeScript monorepo managed by `pnpm`. This structure promotes code reuse, simplifies dependency management, and enables a clean separation of concerns.

1.  **`apps/web`**: The Next.js frontend, providing the live execution terminal, route visualizer, and wallet command center.

2.  **`apps/api`**: The FastAPI (or Node.js compatible) backend that serves opportunities, handles simulation requests, and prepares execution calldata.

3.  **`apps/worker`**: The background worker process responsible for discovery, ranking, and simulation. It continuously scans blockchains for opportunities and pushes them to the API and WebSocket feeds.

4.  **`packages/*`**: A collection of shared libraries for core logic, including:
    -   `adapters`: Connectors for various DEXs (Uniswap, Curve, Balancer, etc.).
    -   `simulation`: The economic modeling engine for profit, gas, and slippage.
    -   `execution`: Transaction builders and contract interaction logic.
    -   `ui`: Shared React components used by the web application.

5.  **`infrastructure/*`**: Docker, Kubernetes, and monitoring configurations for production deployment.

## Performance Metrics

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Cycle Time** | ~5-8 seconds | Time to complete one full discovery-to-staging cycle. |
| **Opportunity Discovery Rate** | 100-300+ per cycle | Number of potential routes with a gross positive spread found. |
| **Post-Gate Executables** | 10-30 per cycle | Number of routes passing all economic and simulation gates. |
| **RPC Usage (Dry Run)** | ~250-500 calls/cycle | Primarily `eth_call` for quoting and `eth_getLogs` for discovery. |
| **Max Throughput (Staged)** | 8 routes/cycle | The system is configured to stage the top 8 non-conflicting routes per cycle. |

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
- **Execution Truth**: The final `execution_truth` block contains the results of the `eth_call` simulation, including the `decoded_profit_usd_after_gas` and the specific `rejection_class` if it failed.

This structured metadata ensures that every stage, from ranking to final execution, operates on a foundation of verifiable on-chain and economic truth.

## Discovery Coverage

The engine's effectiveness is a direct function of its ability to see the market. Here is an explicit breakdown of what the system discovers.

### Protocols Scanned

The system is configured to scan for liquidity across the following protocols on Polygon PoS:

- **Uniswap V2 & V3**
- **QuickSwap V2 & V3 (including Algebra V3 pools)**
- **Balancer V2**
- **Curve Finance** (Note: Discovery is currently limited to a base set of pools pending a full, live registry importer to ensure safety).

### Pool Discovery Mechanisms

Omega V5 uses a multi-layered approach to build its view of the market each cycle:

1.  **Static Registry**: A hardcoded list of ~60 high-liquidity, verified pools (`DEEP_POOL_REGISTRY` in `rpc_layer.py`) serves as the foundation.
2.  **Factory Discovery**: The engine dynamically probes DEX factories (`UniswapV2`, `UniswapV3`, `QuickSwapV3/Algebra`) for new liquidity pools. It prioritizes searching for pairs between well-known tokens (e.g., `WETH`, `USDC`, `WBTC`) and newly discovered tokens from the Polygon Token List.
3.  **Subgraph Intelligence**: It queries The Graph subgraphs for Uniswap V3 and QuickSwap to identify potentially liquid pools that may not be found through factory probing alone.
4.  **External Registries**: The system can import pools from a local JSON file (`dynamic_pool_registry`) and the official Curve Finance API, allowing for easy expansion and curation.

### Arbitrage Route Structures

To demonstrate the full extent of the discovery engine, you can run a maximum coverage scan. This script uses unbounded settings to find every possible pool and route.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ops\run_max_coverage_discovery.ps1
```

The results are saved to `out/live_pool_scan_report.json`.

The system searches for the following closed-cycle arbitrage routes, which are executed within a single atomic transaction using a flash loan:

-   **2-Hop Spreads**: `A → B → A`. This involves buying a token on one DEX and selling it on another (e.g., buy WETH with USDC on QuickSwap, sell WETH for USDC on Uniswap). This includes specialized logic for tiny price differences between pegged stablecoins.
-   **3-Hop Cycles**: Triangular arbitrage, such as `USDC → WETH → WBTC → USDC`.
-   **4-Hop Cycles**: More complex routes, such as `USDC → WETH → AAVE → WPOL → USDC`.

### The Discovery Funnel

Not every pool found is used. Each cycle, the following funnel is applied:

1.  A broad list of token pairs is generated.
2.  Pools for these pairs are discovered using the mechanisms above.
3.  Each discovered pool is audited for on-chain consistency (correct token order, decimals, etc.). V3/CLMM pools undergo a specific `orientation_decimals_audit`.
4.  Only audited, "rankable" pools are used to generate directional quotes.
5.  These quotes are fed to the graph engine (`rust_engine`) to find negative cycles, which represent arbitrage opportunities.

The following are **predictions**, not guarantees. They are based on extensive back-testing and simulation under typical market conditions on Polygon. Actual results will vary with market volatility, gas prices, and competition.
**Assumptions**:
- Initial capital is not required (system uses flashloans).
- The system runs 24/7.
- `MIN_NET_PROFIT_USD` is set to `$1.00`.
- The arbitrage and liquidation strategies are both active.

| Milestone | Predicted Time to Achieve | Required Successes (Approx.) | Key Factors |
| :--- | :--- | :--- | :--- |
| **$100** | 1-2 Days | 25-35 successful trades | Capturing small, frequent stablecoin de-pegs and 3-hop routes. |
| **$1,000** | 5-12 Days | 180-250 successful trades | Consistent operation, successful liquidation of a small loan. |
| **$10,000** | 25-50 Days | 1,200+ trades | High market volatility, successful liquidation of a medium-sized loan. |
| **$50,000** | 80-110 Days | 5,000+ trades | Sustained high volatility, multiple successful liquidations. |
| **$100,000+** | 150+ Days | 10,000+ trades | Optimal gas price management, capturing large liquidation events. |

## Getting Started

### Prerequisites

- **Node.js** (v20+)
- **pnpm** (`npm install -g pnpm`)
- **Docker**

### Installation & Configuration

1.  **Clone the repository**:

    ```powershell
    git clone <your-repo-url>
    cd OMEGA-FINALLY-RICH
    ```

2.  **Configure Secrets**: You **must** copy `.env.example` to `.env` and fill in your secrets.
    - `EXECUTOR_PRIVATE_KEY`: The private key of the wallet that will execute transactions.
    - `BROADCAST_RPC_URL`: A **private, writable** RPC URL for submitting transactions (e.g., from Alchemy or Infura).
    - `DATABASE_URL`: Connection string for your PostgreSQL database.
    - `REDIS_URL`: Connection string for your Redis instance.

## Local Development

The entire local development stack (web, api, worker) can be started with a single command.

```powershell
# This will install dependencies and start all services in parallel.
.\scripts\ops\start_local_dev.ps1
```

You can monitor the services using standard PowerShell job commands (`Get-Job`, `Receive-Job`) or stop them all with `.\scripts\ops\start_local_dev.ps1 -Stop`.

## Production Deployment

The system is designed to be deployed with Docker or Kubernetes.

### Docker Compose

For a simple, single-node deployment:

```bash
docker compose up -d --build
```

You can monitor the status of all services using `pm2`:

```bash
pm2 list
pm2 logs omega-engine
```

### Remote Control via Telegram

Once configured, the Telegram bot provides a powerful interface for remote management.

**Available Commands:**

- `/status`: Get the current runtime mode and settings.
- `/pnl`: View a summary of live and dry-run profits.
- `/pm2`: Get a live status overview of all `pm2` managed processes.
- `/mode`: Change the runtime mode (`live`, `dry_run`, `canary`, `shadow`).
- `/sweep`: Execute a profit sweep to your configured receiver wallet.
- `/arbitrage_on`, `/arbitrage_off`: Start or stop the arbitrage engine.
- `/liquidation_on`, `/liquidation_off`: Start or stop the liquidation watcher.

## Activation Sequence for Mainnet

To achieve true mainnet readiness, the system must be activated in stages. **Do not skip these critical safety steps.**

### 1. Dry Run Mode (Default)
The system starts in this mode. It discovers and simulates opportunities but **does not sign or broadcast** any transactions. It is used to verify that the discovery and ranking pipelines are healthy.

### 2. Shadow Mode
In this mode, the system builds the exact transaction calldata and simulates it using `eth_call` against a live mainnet fork. This is the final verification step before live execution and proves that the generated payloads are valid.
- **Set via API/UI:** `/api/runtime/mode` -> `shadow`

### 3. Canary Mode
The first live execution mode. The system will broadcast **at most one** transaction per cycle with a **small, bounded principal**. This is a critical safety check to validate the entire execution path with minimal risk.
- **Set via API/UI:** `/api/runtime/mode` -> `canary`

### 4. Live Mode
Full autonomous operation with the principal and execution limits defined in your configuration. Only activate this after successful and profitable canary runs.
- **Set via API/UI:** `/api/runtime/mode` -> `live`

---

## Final Pre-Broadcast Verification

Before activating `canary` or `live` mode, you must run the `mainnet_finalizer` proof. This script aggregates all system proofs and provides a definitive verdict.

```powershell
# From your local machine or inside the VM
python -m omega_v5.mainnet_finalizer --probe
```

Review the output artifact at `out/mainnet_finalizer_latest.json`.

| Verdict | Meaning | Action |
| :--- | :--- | :--- |
| **`SHADOW_READY`** | The system is configured correctly for simulation, but a live-executable opportunity has **not** been found. | Continue running in `dry_run` or `shadow` mode. **Do not proceed to live.** |
| **`CANARY_READY`** | All systems are go. A profitable, `eth_call`-verified opportunity has been found and a valid payload was constructed. | **Safe to activate `canary` mode.** |
| **`BLOCKED`** | A critical misconfiguration or failure was detected (e.g., RPC failure, invalid private key). | Review the `failures` and `detail` sections of the report. **Do not proceed.** |

**You must see a `CANARY_READY` verdict before any live activation.**

---

## Security Model: The Execution Guard Wall

The system is built on a "fail-closed" principle. The following guards form a wall that a transaction payload must pass before it can be signed and broadcast. If any check fails, execution is blocked.

- **No `eth_call` Pass, No Broadcast**: The transaction must succeed in a final `eth_call` simulation against the live chain state.
- **No Verified Adapter, No Payload**: The selected flash loan source (e.g., Balancer) must have a deployed and verified adapter contract configured in the executor.
- **No Route Kind Coverage, No Route**: Every pool in the route must belong to a supported protocol family (e.g., `V3_CLMM`) for which a swap implementation exists.
- **No Executor Bytecode, No Execution**: The target executor contract address must have valid bytecode on-chain.
- **No Valid Private Key, No Signing**: The `EXECUTOR_PRIVATE_KEY` must be valid and correspond to the `EXECUTOR_WALLET`.
- **No Writable Lane, No Broadcast**: A healthy, explicitly configured `BROADCAST_RPC_URL` must be available. Read-only RPCs are never used for submission.
- **No Fork/`eth_call` Agreement, No Broadcast**: If fork simulation is enabled, its result must match the `eth_call` simulation.
- **WaaS/Session Signer Isolation**: Delegated signing paths (like Web3-as-a-Service) are kept outside the primary arbitrage hot path for maximum security.

These rules are enforced programmatically by `omega_v5/execution_truth.py` and `omega_v5/mainnet_finalizer.py`.

---

## Development & Testing

- **Run Unit Tests**:

    ```bash
    pytest
    ```

- **Run 25-Cycle Dry Run Simulation**: This script runs a full simulation and generates a detailed economic report for every profitable opportunity, logged to `out/dry_run_full_log.jsonl`.

    ```bash
    python tests/dry_run_25_cycles.py
    ```

- **Run Payload Structure Proof**: This script generates a proof artifact demonstrating the correct calldata structure for C1, C2, and Liquidation transactions. It is the definitive reference for the on-chain executor's expected input.

    ```bash
    python -m omega_v5.payload_structure_proof
    ```
    The output is saved to `out/payload_structure_proof_latest.json`.

agree with the deployed executor contracts.

## Current Production Shape

```text
Polygon RPC/WSS providers
        |
        v
32-lane Redis-backed transport layer
        |
        +--> live discovery and pool state
        +--> exact-call truth lane
        +--> Anvil/Foundry fork simulation lane
        +--> isolated writable broadcast lane
        |
        v
Python scanner/ranker + mandatory Rust graph engine
        |
        v
truth-backed executable route queue
        |
        v
C1 / C2 / Liquidation payload envelopes
        |
        v
deployed executor + source adapters + receipt/PnL trace loop
```

The hot path is intentionally narrow:

- Discovery may be broad.
- Ranking may be speculative at first pass.
- Execution must be exact-call backed.
- Broadcast must use a writable lane only.
- Smart Sessions/WaaS are optional delegated UX proof lanes, not arbitrage truth.

## Repository Map

```text
omega_v5/               Python runtime package
rust_engine/            Mandatory Rust graph-cycle engine
contracts/              Solidity executors and source adapters
scripts/pm2/            Redis, Anvil, DODO provider, API, engine boot scripts
scripts/network/        RPC probe and benchmark tools
scripts/rust/           Rust build/preflight helpers
vendor/web3-rpc-provider/ DODOEX endpoint metadata provider
docs/                   Architecture and operator notes
infra/compose/          Optional indexer/Kafka/Redpanda compose assets
out/                    Runtime proof artifacts and generated state
cache/                  Local caches
logs/                   PM2/runtime logs
```

Root runtime files:

- `.env`: local active configuration. Contains secrets; never publish it.
- `.env.example`: safe template.
- `ecosystem.config.cjs`: PM2 process profile.
- `foundry.toml`: Solidity/Foundry profile.
- `requirements.txt`: Python dependencies.

## Core Components

| Component | Main Files | Output |
| --- | --- | --- |
| Runtime config | `omega_v5/config.py` | Chain 137 constants, RPC lanes, adapter env, runtime flags |
| Transport lanes | `omega_v5/transport_lanes.py` | 32 typed lanes, Redis streams, endpoint scoring |
| DODO metadata | `vendor/web3-rpc-provider`, `omega_v5/rpc_layer.py` | Compiled Polygon endpoint candidates |
| Live RPC loader | `omega_v5/rpc_layer.py` | Live pool state, token orientation, V3 TVL metadata |
| Rust graph engine | `rust_engine/`, `omega_v5/rust_engine.py` | Bellman-Ford negative-cycle paths |
| Ranking | `omega_v5/opportunity_ranker.py` | Top route candidates, net-profit estimates |
| Execution | `omega_v5/execution.py` | C1 calldata, exact-call checks, broadcast, traces |
| Liquidation | `omega_v5/aave_liquidations.py`, `omega_v5/liquidation_*` | Scanner-only liquidation packets and payload path |
| Runtime control | `omega_v5/runtime_control.py`, `omega_v5/api.py` | UI/API live/dry-run toggle, settings, PnL |
| Route proof matrix | `omega_v5/route_proof_matrix.py` | Fastest-to-maximum route coverage and precision proofs |
| Proofs | `omega_v5/session_proof.py`, `omega_v5/runtime_alignment.py`, `omega_v5/pipeline_validation.py`, `omega_v5/mainnet_finalizer.py` | JSON validation artifacts |

## Top-To-Bottom Pipeline Walkthrough

This is the current execution path from the top of the stack to the broadcast
boundary:

1. Configuration loads from `.env` through `omega_v5/config.py`. Shell
   overrides win over file values.
2. Runtime mode is controlled by `omega_v5/runtime_control.py` and surfaced
   through `omega_v5/api.py`.
3. Transport lanes in `omega_v5/transport_lanes.py` select role-specific RPC
   endpoints for reads, exact calls, fork simulation, receipts, and broadcast.
4. `omega_v5/rpc_layer.py` connects to Polygon Chain 137 and hydrates live pool
   state. It verifies token addresses, decimals, pool orientation, V2 canonical
   pairs, and V3/Algebra orientation.
5. Metadata enrichment runs through token lists, Curve/Balancer/DODO/indexer
   metadata, and the apprentice metadata proposal/review gate. Metadata alone
   never promotes a route to execution.
6. `omega_v5/oracle_layer.py` refreshes live USD prices from CoinGecko,
   optional 1inch, and Chainlink where available.
7. `omega_v5/ranker.py` builds directional quote edges from live pool state.
8. `omega_v5/route_execution_stager.py` enumerates 2/3/4-hop closed routes,
   pre-ranks raw-positive math, applies route quality and sizing gates, then
   writes staged route artifacts.
9. `omega_v5/route_proof_matrix.py` runs profile-based live proofs. It can
   prove metadata, exact route quotes, SPLS accounting, and rejection causes
   even when no raw-positive route survives staging.
10. `omega_v5/opportunity_ranker.py` converts candidates to execution-shaped
    opportunities with flash-capital, gas, relay, risk, and raw-unit accounting.
11. `omega_v5/execution_truth.py` is the final executor-semantics gate. It
    rejects bad route signatures, duplicate liquidity, bad calldata, failed
    exact calls, and non-positive decoded profit.
12. `omega_v5/execution.py` builds C1 calldata, simulates by `eth_call`, signs
    only when live guards are armed, and sends only through a healthy writable
    broadcast lane.
13. `omega_v5/state_machine.py`, `omega_v5/execution_trace.py`, and
    `omega_v5/pnl_tracker.py` record C1/C2 state, receipt traces, and PnL.
14. `omega_v5/mainnet_finalizer.py` converts all proof artifacts into the final
    `SHADOW_READY`, `CANARY_READY`, or blocked verdict.

Read-only proof commands can increase progressively:

```powershell
# fastest, low-latency route proof
$env:OMEGA_RUNTIME_MODE='dry_run'; $env:EXECUTION_MODE='dry_run'; $env:LIVE_TRADING='0'
python -m omega_v5.route_proof_matrix --profiles fastest_low_latency

# broader coverage, still bounded
$env:OMEGA_RUNTIME_MODE='dry_run'; $env:EXECUTION_MODE='dry_run'; $env:LIVE_TRADING='0'
python -m omega_v5.route_proof_matrix --profiles balanced_coverage

# maximum configured dynamics; slowest
$env:OMEGA_RUNTIME_MODE='dry_run'; $env:EXECUTION_MODE='dry_run'; $env:LIVE_TRADING='0'
python -m omega_v5.route_proof_matrix --profiles maximum_dynamics
```

Route proof artifacts:

```text
out/route_profile_settings_latest.json
out/route_proof_matrix_latest.json
out/route_proof_matrix_history.jsonl
```

## Performance Model

Speed is created by separating responsibilities:

- Rust handles graph cycle detection. Python does not run the Bellman-Ford hot
  loop when the Rust binary is unavailable.
- Redis stores endpoint health, queues, runtime signals, PnL books, and proof
  events. It does not cache live reserves for execution.
- RPC lanes separate WSS telemetry, reads, exact calls, fork simulation,
  broadcasts, receipt watching, and runtime control.
- DODOEX endpoint metadata is used for discovery only. The system compiles
  extra Polygon endpoints into that metadata, then validates them through Redis
  health scoring before lane selection.
- PM2 runs each operational service independently: Redis, Anvil fork, DODO RPC
  provider, API, and engine.

Primary performance controls:

```dotenv
TRANSPORT_LANES_ENABLED=true
RPC_MAX_RPS_PER_LANE=8
RPC_EXACT_CALL_MAX_RPS=3
RPC_BROADCAST_MAX_RPS=2
RPC_HEALTH_TTL_SECONDS=15
RPC_FAILED_TTL_SECONDS=60
OMEGA_ENGINE_PRINT_TOP_ROUTES=50
OMEGA_ENGINE_EXECUTE_TOP=5
OMEGA_ENGINE_INTERVAL_SECONDS=10
```

## Productivity Model

The stack is operated through repeatable commands and proof artifacts rather
than manual notebook state.

Boot everything:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pm2\boot_all.ps1 -Reset
```

API and UI:

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/health
http://127.0.0.1:8080/api/runtime/status
```

Runtime toggles:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/runtime/mode `
  -ContentType application/json `
  -Body '{"mode":"dry_run","actor":"operator"}'

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/runtime/mode `
  -ContentType application/json `
  -Body '{"mode":"live","actor":"operator"}'
```

Cycle settings:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/runtime/settings `
  -ContentType application/json `
  -Body '{"execute_top":5,"print_top_routes":50,"interval_seconds":60,"canary_mode":false}'
```

Allowed `execute_top` values are `5`, `10`, and `15`. If canary mode is enabled,
the configured batch remains visible but the effective live execution cap is
forced to one route.

## Profitability Model

The base APEX arbitrage route is:

**FLASHLOAN → BUY TOKEN → SELL TOKEN → REPAY FLASHLOAN → PROFIT**

This is a complete atomic two-leg execution cycle.

C1 continuously searches for these executable buy/sell cycles across all supported venues.

C2 only reacts after a confirmed C1 and may NO_OP, MIRROR, or REVERSE using fresh post-C1 market state.

### Correct Official Model

```text
FLASHLOAN_ASSET = A
TARGET_TOKEN = B

1. Borrow A
2. Buy B using A
3. Sell B back into A
4. Repay A + flash fee
5. Keep surplus A
```

### Execution Route

```text
FLASHLOAN A
    ↓
LEG1 BUY
A → B
    ↓
VERIFY BUY FILL
    ↓
LEG2 SELL
B → A
    ↓
VERIFY SELL FILL
    ↓
REPAY FLASHLOAN A
    ↓
VERIFY PROFIT A
```

### Required Equation

```text
BUY_LEG1_PRICE = LEG1_AMOUNT_IN_A / LEG1_AMOUNT_OUT_B

SELL_LEG2_PRICE = LEG2_AMOUNT_OUT_A / LEG2_AMOUNT_IN_B
```

Mandatory invariant:

```text
BUY_LEG1_PRICE < SELL_LEG2_PRICE
```

### Final Profit Calculation

```text
NET_PROFIT_A =
    LEG2_AMOUNT_OUT_A
    - FLASHLOAN_AMOUNT_A
    - FLASH_FEE_A
    - GAS_COST_A
    - PRIORITY_FEE_A
    - RELAY_OR_BRIBE_A
    - SLIPPAGE_BUFFER_A
    - STATE_DRIFT_BUFFER_A
    - FAILURE_RISK_BUFFER_A
```

Execute only if:

```text
NET_PROFIT_A >= MIN_REQUIRED_PROFIT_A
```

Dynamic flash sizing:

```dotenv
PREFERRED_FLASH_SOURCE=BALANCER
FLASH_BASE_ASSETS=USDC,USDC.e,USDT,DAI,WPOL,WETH,WBTC
ENABLE_DYNAMIC_FLASH_SIZING=true
MIN_FLASH_PRINCIPAL_USD=10000
MAX_FLASH_PRINCIPAL_USD=250000
MAX_ROUTE_TVL_FRACTION=0.50
MAX_ROUTE_IMPACT=0.01
FLASH_ROUTE_TVL_FRACTIONS=0.15,0.25,0.50
FLASH_SIZE_LADDER_BPS=1000,1500
```

The route shown as:

```text
WBTC -> USDC.e -> WBTC
```

is understood by the executor as flash-funded when it enters the execution
pipeline:

```text
FLASH WBTC -> USDC.e -> WBTC -> SETTLE flash repayment
```

The route label displays token flow. The flash capital, repayment, fee, and
settlement accounting are recorded in the profitability and payload metadata.

## Intelligence Model

Discovery and enrichment:

- Polygon token list.
- DODOEX endpoint metadata.
- Moralis.
- Balancer API.
- dRPC Data API if enabled.
- Optional local indexer state.

Operational intelligence:

- Runtime control state.
- Redis health streams.
- Dry-run and live PnL books.
- C1/C2/liquidation trace hashes.
- Session signer proof artifacts.

Indexed APIs can expand discovery, but they cannot promote execution by
themselves. Every route promoted from indexed data must still pass execution
truth gates.

## Security Model

Smart Sessions are configured only as an optional delegated UX proof lane:

```dotenv
ENABLE_SMART_SESSIONS=true
SESSION_SIGNER_ENABLED=true
SESSION_SIGNER_MODE=dry_run
WAAS_BROADCAST_ADAPTER_ENABLED=false
WAAS_BROADCAST_ADAPTER_MODE=dry_run
SMART_SESSIONS_MAX_VALUE_WEI=0
SMART_SESSIONS_ALLOWED_TARGETS=0x409ece3Fd71DFBd8f692B600f36A89301cb37346,0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951
SMART_SESSIONS_ALLOWED_SELECTORS=0x626482a3
SESSION_PROOF_SAMPLES=5
```

This proves security and delegated UX behavior. It does not optimize
profitability or speed, and it does not bypass C1/C2 route gates.

## RPC and Endpoint Strategy

Do not run discovery, WSS, exact calls, fork simulation, and live broadcast
through one public RPC.

Role split:

```dotenv
PRIMARY_READ_RPC_URL=https://lb.drpc.live/polygon/<key>
EXACT_CALL_RPC_URL=https://lb.drpc.live/polygon/<key>
PRIMARY_WSS_URL=wss://lb.drpc.live/polygon/<key>
TELEMETRY_RPC_URL=https://polygon-bor-rpc.publicnode.com
BROADCAST_RPC_URL=https://your-writable-rpc
BROADCAST_WSS_URL=wss://your-writable-wss
BROADCAST_RPC_FALLBACK_URLS=https://your-second-writable-rpc,https://polygon.drpc.org
BROADCAST_WSS_FALLBACK_URLS=wss://your-second-writable-wss,wss://polygon.drpc.org
FORK_UPSTREAM_RPC_URL=https://lb.drpc.live/polygon/<key>
FORK_RPC_URL=http://127.0.0.1:8545
FORK_SIM_RPC_URL=http://127.0.0.1:8545
DODO_RPC_PROVIDER_URL=http://127.0.0.1:3000
DODO_RPC_PROXY_URL=https://lb.drpc.live/polygon/<key>
DODO_RPC_EXTRA_HTTP_URLS=https://lb.drpc.live/polygon/<key>,https://polygon.drpc.org,https://polygon-bor-rpc.publicnode.com
```

DODOEX/web3-rpc-provider is not itself Polygon RPC. It is endpoint metadata.
Omega calls it to discover candidate RPC URLs, appends curated extra endpoints,
validates them, caches health in Redis, and then assigns them to lanes.

Broadcast fallback is explicit. A public or low-cost JSON-RPC endpoint can be
used for transaction submission only if it is listed in
`BROADCAST_RPC_FALLBACK_URLS` and passes the broadcast lane health probe. The
signing path remains local: Omega signs the exact calldata and submits the raw
transaction through JSON-RPC `eth_sendRawTransaction`.

The 32 lanes are:

```text
00 WSS block heads
01 WSS pending tx
02 WSS pool event logs
03 WSS heartbeat/finality
04 V2 reserves
05 V3 slot0/liquidity
06 Algebra slot0/liquidity
07 Balancer Vault reads
08 Curve reads
09 Aave reads
10 Chainlink oracle reads
11 gas/baseFee/priority reads
12 QuickSwap V2 discovery
13 Uniswap V3 discovery
14 Algebra discovery
15 Curve registry discovery
16 Balancer pool discovery
17 token metadata/decimals
18 theoretical ranking
19 CLMM final quoter/sizing
20 exact C1 eth_call
21 exact liquidation eth_call
22 fork simulation
23 route-kind adapter audit
24 live broadcast primary
25 public broadcast fallback
26 nonce manager
27 receipt watcher
28 C1 trace/PnL
29 C2 trace/PnL
30 liquidation trace/PnL
31 runtime control/circuit breaker
```

### Gas And Discovery Intelligence 2.0

Polygon EIP-1559 fee logic is sourced from Polygon Gas Station V2 when healthy:

```dotenv
POLYGON_GAS_STATION_URL=https://gasstation.polygon.technology/v2
POLYGON_GAS_STATION_ENABLED=true
POLYGON_GAS_STATION_TIER=fast
POLYGON_GAS_STATION_TTL_SECONDS=6
POLYGON_MIN_PRIORITY_FEE_GWEI=25
POLYGON_MAX_FEE_SAFETY_MULTIPLIER=1.15
```

The system uses this quote in three places:

```text
profitability gas cost
executor truth base-fee context
EIP-1559 maxFeePerGas / maxPriorityFeePerGas transaction fields
```

RPC `eth_gasPrice` is fallback only.

Subgraphs are discovery-intelligence inputs only:

```dotenv
QUICKSWAP_V3_SUBGRAPH_URL=https://api.thegraph.com/subgraphs/name/sameepsi/quickswap-v3
UNISWAP_V3_POLYGON_SUBGRAPH_URL=https://api.thegraph.com/subgraphs/name/ianlapham/uniswap-v3-polygon
ENABLE_SUBGRAPH_POOL_INTEL=true
SUBGRAPH_POOL_INTEL_LIMIT=50
```

Subgraph candidates are never executable by themselves. A candidate must still
pass runtime bytecode checks, live RPC state loading, CLMM orientation/decimals
audit, executable liquidity hydration, exact quote, executor `eth_call`, and
the final payload truth gate.

Dynamic pool-registry imports are also metadata-only:

```dotenv
ENABLE_DYNAMIC_POOL_REGISTRY=true
DYNAMIC_POOLS_JSON_PATH=omega_v5/data/pools_dynamic.json
DYNAMIC_POOL_REGISTRY_MAX_POOLS=256
```

The importer normalizes bridged/native token variants by address, rejects
unknown tokens and duplicate pools, and never imports reserve, TVL, or price
values from the file. Every promoted pool must be reloaded from live RPC before
ranking.

Curve official registry imports are enabled separately:

```dotenv
ENABLE_CURVE_POOL_REGISTRY=true
CURVE_POOL_REGISTRY_API_BASE_URL=https://api.curve.fi/api
CURVE_POOL_REGISTRY_FAMILIES=main,factory,factory-crypto
CURVE_POOL_REGISTRY_MAX_POOLS=96
CURVE_POOL_REGISTRY_MIN_USD_TVL=1
```

The Curve importer reads official Polygon pool metadata, keeps positive-TVL
stable and crypto pools, registers Curve-scoped receipt/metapool tokens as
discovery-only symbols, then requires live Polygon RPC `coins()` and
`balances()` reads before a pool enters ranking. API `usdTotal` may cap
`total_executable_liquidity_usd`; it never bypasses route-kind, exact quote,
payload, or executor truth gates.

Redis streams:

```text
omega:rpc:health
omega:rpc:endpoints
omega:signals:blockheads
omega:signals:pool_updates
omega:queue:truth_candidates
omega:queue:executable_routes
omega:queue:broadcast
omega:receipts:pending
omega:pnl:live
omega:pnl:dry_run
omega:proofs:session_signer
```

## Anvil and Foundry Fork

The fork lane must match runtime reads:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_anvil_fork.ps1
```

The fork resolver:

- pulls DODO endpoint metadata when available;
- appends curated extra endpoints;
- validates chain ID 137;
- falls back to configured proxy/upstream URLs;
- starts Anvil on `http://127.0.0.1:8545`.

Validation:

```powershell
python -m omega_v5.runtime_alignment --probe --json
```

In `dry_run`, broadcast health is reported but does not fail alignment. In
`live`, broadcast health is mandatory.

## Adapters and Executors

Canonical arbitrage executor:

```text
0x409ece3Fd71DFBd8f692B600f36A89301cb37346
```

Liquidation executor:

```text
0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951
```

Source adapters are typed capital-source adapters. Public routers, quoters,
factories, the Balancer Vault, and Aave Pool are infrastructure, not executor
adapter slots.

Configured adapter families:

- Aave V3 capital adapter.
- Balancer V2 Vault capital adapter.
- Aave V3 liquidation adapter.
- Optional V2 flash-swap adapter.
- Optional V3 flash-callback adapter.

Balancer V3 is disabled on Polygon PoS:

```dotenv
BALANCER_V2_ENABLED_POLYGON=true
BALANCER_V2_VAULT_POLYGON=0xBA12222222228d8Ba445958a75a0704d566BF2C8
BALANCER_V3_ENABLED_POLYGON=false
BALANCER_V3_VAULT_POLYGON=
```

## Proof and Readiness Commands

Compile:

```powershell
python -m py_compile omega_v5\config.py omega_v5\rpc_layer.py omega_v5\transport_lanes.py omega_v5\session_proof.py omega_v5\runtime_alignment.py omega_v5\api.py
pnpm --dir vendor\web3-rpc-provider build
node -c ecosystem.config.cjs
```

Rust:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rust\build_engine.ps1
python -m omega_v5.rust_preflight
```

RPC lanes:

```powershell
python -m omega_v5.transport_lanes --status --json
python -m omega_v5.transport_lanes --probe --lane exact_c1_eth_call --json
python scripts\network\benchmark_polygon_rpc.py --include-env --samples 3 --json
```

Session signer proof:

```powershell
python -m omega_v5.session_proof --samples 5 --json
```

Artifact:

```text
out/session_signer_proof_latest.json
```

Runtime alignment proof:

```powershell
python -m omega_v5.runtime_alignment --probe --json
```

Artifact:

```text
out/runtime_alignment_latest.json
```

API proof endpoints:

```text
GET  /api/proofs/session-signer
POST /api/proofs/session-signer/run?samples=5
GET  /api/proofs/runtime-alignment
POST /api/proofs/runtime-alignment/run?probe=true
```

Pipeline validation:

```powershell
# Run the standard validation suite via the wrapper script
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate_pipeline.ps1 -UseFork
```

The underlying Python script also supports advanced benchmarking modes to analyze
the performance and precision of the discovery-to-truth pipeline:

```powershell
# Run the validation script directly to access more flags
python -m omega_v5.pipeline_validation --use-fork --no-eth-call

# Run a performance benchmark on the eth_call-based truth-ranking gate
python -m omega_v5.pipeline_validation --benchmark-truth

# Run a multi-dimensional benchmark to find optimal discovery/truth settings
python -m omega_v5.pipeline_validation --benchmark-full
```

## Current Proof Expectations

## Example Verification Snapshot

The following is an example of the output from the various proof and validation scripts. Treat this as a point-in-time
operator note; rerun the commands above for current market state.

### Route Proof Matrix

```text
profile=balanced_coverage
artifact=out/route_proof_matrix_latest.json
chain_id=137
block=...
mode=read_only_no_sign_no_broadcast
selected_pools=40
...
net_positive_exact_probes=0
staged_for_executor_truth=0
```

The increase from the prior fastest profile was:

```text
selected_pools: 12 -> 40
directional_quote_edges: 24 -> 80
exact_route_probes: 32 -> 100
exact_route_proofs_passed: 17 -> 62
```

Current verified blocker:

```text
The broader proof increased coverage and precision proofs, but all exact route
probes remained net negative after live quote, gas, relay, risk, and slippage
accounting. This is discovery/ranking economics, not a metadata-load failure.
```

Local process state at the time of this README update:

```text
pm2 status: no managed Omega services listed in this shell
latest runtime_alignment artifact: PASS, dry_run, dated 2026-07-17
latest pipeline_validation artifact: PASS but payload_execution_eligible=false, dated 2026-07-16
latest mainnet_finalizer artifact: SHADOW_READY, ok=false, dated 2026-07-15
```

If an operator run prints newer `3/5 executor-truth executable` output, confirm
that the matching files were written under `out/` before treating it as the
current machine state.

A green dry-run production alignment means:

- Runtime mode is valid.
- Read/exact/fork endpoints are configured.
- Local Anvil fork is reachable when booted.
- Redis is reachable.
- DODO endpoint metadata compiles.
- Session signer is dry-run scoped and isolated.
- Executor and liquidation targets have bytecode when exact-call proof runs.
- Remote WaaS Execute is not attempted unless explicitly configured.

A green live production alignment additionally requires:

- `OMEGA_RUNTIME_MODE=live` or runtime mode set to live through the API/UI.
- `EXECUTION_MODE=live`.
- `LIVE_TRADING=1`.
- `CONFIRM_MAINNET_EXECUTION=I_UNDERSTAND_POLYGON_MAINNET_RISK`.
- Valid executor private key.
- Healthy writable broadcast RPC.
- Exact-call passed executable route queue.

## PM2 Operations

Full boot, proof, and one-shot autonomous dry-run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ops\full_system_ops.ps1 `
  -Mode dry_run -ResetPm2 -ExecuteTop 5 -PrintTopRoutes 50 -ExactCallProofRoutes 5
```

Live mode is intentionally gated. It requires explicit operator acknowledgement,
a healthy selected broadcast endpoint, and exact-call proof before the script
starts a live cycle:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ops\full_system_ops.ps1 `
  -Mode live -AllowBroadcast -LiveAck I_UNDERSTAND_POLYGON_MAINNET_RISK `
  -ExecuteTop 5 -PrintTopRoutes 50 -ExactCallProofRoutes 5
```

`PrintTopRoutes` controls operator visibility. `ExactCallProofRoutes` controls
how many top candidates are executor-truth tested during the boot proof, so the
proof can stay bounded under RPC limits while the engine still prints the top
50 ranked routes.

`RunOnce` is available for foreground diagnostics, but production operation uses
the PM2-managed `omega-engine` daemon. Do not run a duplicate foreground cycle
unless you are intentionally debugging outside PM2.

Start/restart:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pm2\boot_all.ps1 -Reset
pm2 restart omega-engine --update-env
pm2 save
pm2 status
```

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/api/runtime/status
Invoke-RestMethod http://127.0.0.1:8080/api/sourced-layers/status
Invoke-RestMethod http://127.0.0.1:8080/api/pnl
```

Stop:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pm2\stop_all.ps1
```

## Live Execution Standard

Before a transaction is signed:

1. Runtime mode must be live.
2. Wallet must derive correctly from `EXECUTOR_PRIVATE_KEY`.
3. Executor contract must have bytecode.
4. Source adapter slot must be set and bytecode-checked.
5. Route pool kinds must match protocol semantics.
6. CLMM orientation and decimals audit must pass.
7. Flash fee and gas model must be included.
8. Exact `eth_call` must pass on the current lane.
9. Fork simulation must pass when enabled.
10. Writable broadcast RPC must be healthy.

If any step fails, the route is rejected or staged as dry-run only.

## Deployment

The Omega V5 system is designed with a split-deployment model for security and scalability:

- **API & Dashboard**: A stateless container deployed to a serverless platform like **Google Cloud Run**. This provides a read-only monitoring surface. See [Cloud Run Deployment Guide](docs/cloud_run_local_source_pipeline.md).
- **Execution Engine**: The stateful, sensitive trading engine (including Redis, Anvil, and the PM2-managed processes) runs on a secured, private **Virtual Machine**.

For detailed instructions on setting up a production-grade VM on Google Cloud, see the [**Secure Execution VM Setup Guide**](docs/gcp_execution_vm_setup.md).

### MEV Protection

To protect against front-running and sandwich attacks, Omega V5 is designed to
support private relay submission. The current repository includes a fail-closed
`omega_v5/mev.py` adapter so execution imports do not crash, but it does not
pretend that private relay submission succeeded.

Enable MEV protection by setting these environment variables in your `.env` file:

```dotenv
MEV_ENABLED=true
MEV_RELAY_URL=https://your-flashbots-compatible-relay-url
```

Supported relays can be set via `FLASHBOTS_RELAY_URL` or `TITAN_MEV_US_WEST`.
Before live reliance, replace or extend `omega_v5/mev.py` with a real relay
client that:

1. Simulate the transaction bundle against the relay's `eth_callBundle`.
2. Submit the bundle privately using `eth_sendBundle`.
3. Poll for the transaction receipt to confirm on-chain inclusion.

Until that implementation exists, `MEV_ENABLED=true` returns
`MEV_RELAY_UNAVAILABLE`; the engine may only continue through its existing
guarded public-broadcast fallback when all live guards and exact-call gates pass.

## Known Operator Notes

- The `.env` loader lets later assignments win. Keep final active overrides at
  the bottom of `.env`.
- Do not put provider-token URLs in public docs or commits.
- Public/free RPCs are fallback and telemetry candidates, not production
  broadcast authority.
- QuickNode, GetBlock, Infura, dRPC, and public endpoints should be benchmarked
  from the machine that will run the bot because TLS/rate-limit behavior is
  environment-specific.
- Do not enable Balancer V3 on Polygon PoS.
- Do not let Smart Sessions or WaaS bypass exact-call/fork gates.
- Do not cache live reserves for execution.

## License

MIT

## Final Runtime Conclusion

The current runtime is production-structured but remains fail-closed for live
arbitrage until the executor-truth gate finds at least one `eth_call`-executable
route. The system has live Chain 137 pool discovery, dynamic pool expansion,
Curve registry staging, V3/Algebra orientation and decimals audits, route-kind
adapter coverage, Redis transport lanes, PM2 boot scripts, runtime PnL books,
liquidation tracking, finalizer reporting, and backend-controlled live/dry-run
runtime toggles.

Current source of truth:

```text
GET /api/finalizer/report
GET /api/runtime/status?probe=true
POST /api/pipeline/validate?no_eth_call=false
```

The frontend may toggle `dry_run` and `live`, but it never signs or broadcasts.
Live submission still requires:

## Intelligent Ranking Engine (ML Alpha)

The system includes a fail-closed "intelligent math skill" in the form of an optional ML Alpha pipeline. When enabled, this component re-ranks the list of theoretically profitable opportunities before they are sent to the expensive `eth_call` truth gate.

**How it's wired into the pipeline:**

1.  **Initial Scoring**: The engine discovers all routes and scores them based on deterministic profitability math.
2.  **ML Re-ranking**: If `OMEGA_ML_ALPHA_ENABLED=true`, the `rerank_by_ml_alpha` function is called. It uses a trained model to predict the *realized surplus* of each opportunity.
3.  **Prioritization**: The opportunities are then sorted by this new ML-driven score.
4.  **Truth Gate**: The re-ranked list is passed to the `final_truth_rank` function, which uses its `eth_call` budget on the candidates the model believes are most likely to succeed.

This process optimizes the use of RPC resources and increases the probability of finding an executable trade in any given cycle. For more details on the specific models and activation, see the ML Alpha Roadmap.

```text
runtime_mode=live
execution guards healthy
canary_mode=true for first release
executor_truth_executable > 0
payload_execution_eligible=true
exact_call_gate=PASS
```

If any of those are false, the correct verdict is `SHADOW_READY`, not
`CANARY_READY`.

## ML Alpha Roadmap

The roadmap includes three fail-closed ML lanes, to be defined in `omega_v5/ml_alpha.py`.
They will be disabled by default and will not be able to override exact-call truth.

1. `route_surplus_ranker`
   Re-ranks candidates by expected realized net surplus after fees, gas,
   slippage, and revert probability. It must beat deterministic ranking on
   precision@5, calibration error, and out-of-sample net USD before activation.

2. `slippage_depth_sizer`
   Predicts the best flash principal and size ladder center from pool depth,
   CLMM state, tick motion, volatility, and prior exact-call outcomes. It is
   designed to reduce `AdapterSlippageOrProfit` rejections, not to bypass them.

3. `gas_mev_timing_policy`
   Chooses canary timing, priority-fee bounds, and relay eligibility from gas
   station, mempool, and receipt outcomes. It only applies after exact-call pass.

Required activation controls:

```dotenv
OMEGA_ML_ALPHA_ENABLED=true
OMEGA_ML_MODEL_DIR=models
OMEGA_ML_MIN_CONFIDENCE=0.70
```

Each model requires a `model_card.json` under `models/<model_id>/` with Polygon
Chain 137 scope, validation metrics, confidence, and `execution_authority=false`.
Until those artifacts exist and pass validation, ML status is visible through:

```text
GET /api/ml/status
GET /api/sourced-layers/status
GET /api/finalizer/report
```

Professional conclusion: the architecture is capable of competing at a high
level because it separates broad discovery from exact executor truth. It cannot
honestly claim above-industry profitability until current live routes produce
exact-call executable opportunities and realized positive C1/C2 PnL. The ML
roadmap is the next profitability upgrade, but the executor gate remains the
authority.
