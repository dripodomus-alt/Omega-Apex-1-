# OMEGA V5 — Polygon Arbitrage, Liquidation, and VQC Control Center

OMEGA V5 is an operator-facing control center for Polygon PoS arbitrage and liquidation workflows. It combines a React/Vite front end, an Express server, route and wallet state management, live RPC balance checks, Firestore sync helpers, Google Drive backup support, and a Gemini-backed route analysis endpoint.

## Executive Summary

This repository presents a **discovery → ranking → simulation → preparation → execution → accounting** workflow for Polygon-based opportunities. It is designed to visualize:

- high-frequency route discovery across a multi-protocol Polygon graph,
- VQC-based ranking and execution gating,
- flash-loan sized opportunity analysis,
- wallet, nonce, and gas posture,
- benchmark and readiness diagnostics,
- audit logging and historical performance views,
- controlled progression from simulation-safe operation to live-mainnet readiness.

## Preferred Local Workflow

For local development, this repository is set up to use:

- Yarn for Node.js dependencies and scripts
- a project-local virtual environment for Python
- the hybrid bootstrap script for the Rust/Python bridge

Recommended commands from the repo root:

- `yarn install`
- `yarn hybrid:bootstrap`
- `yarn hybrid:launch`

This keeps the Node toolchain and Python runtime separated while still enabling the hybrid engine bootstrap path.

## Important Reality Check

### Technology Stack

| Category      | Technology / Service                                      |
|---------------|-----------------------------------------------------------|
| **Front End**   | React 19, Vite, TypeScript, Recharts, Lucide              |
| **Back End**    | Node.js, Express                                          |
| **APIs**        | Gemini API (AI Analysis), Google Drive API (Backup)       |
| **Blockchain**  | Polygon PoS (RPC/WSS), Ethers.js                          |
| **Database**    | Google Firestore (Cloud Sync), Browser Local Storage      |
| **Auth**        | Firebase Authentication, Google Auth                      |
| **Tooling**     | ESLint, Prettier                                          |
| **Concepts**    | DeFi Arbitrage, Flash Loans, AMMs, EIP-1153, VQC Modeling |

---

### Important Notice — Current System Status

This repository currently operates as a **prototype operator console and simulation environment**, not as an audited production trading system.

**Key limitations:**

- Benchmark results, route profitability figures, and pool metrics are **seeded / simulated mock data**. They do not represent live traded performance or real P&L.
- Live external connectivity is limited to:
  - RPC calls for balance and nonce checks
  - Gemini AI route analysis
  - Firebase persistence
- No production-grade execution, risk management, or capital custody layers are active.
- The system has **not** undergone formal security audits, formal verification, or mainnet battle-testing.

Until these components are replaced with live data feeds, audited execution paths, and production infrastructure, this codebase should be treated strictly as a development and simulation surface.

## Core System Capabilities

### 1. Opportunity Discovery

The repository models a Polygon mainnet discovery graph with:

- **14 indexed protocols**
- **14 indexed assets**
- **4,186 indexed pools**
- **12,558 swappable edges**
- **$1.24B tracked TVL**
- **17 Chainlink feeds**
- **0.88 ms average full graph sweep** in the supplied metrics model

These values are defined in `FULL_CHAIN_137_METRICS` inside `src/data/mockEngineData.ts`.

The `Top50ExecutionStudio` also runs a 12-second cycle model that:

- regenerates the top 50 opportunities,
- labels routes as `EXECUTABLE`, `WATCHING`, or `SIMULATED`,
- shows route hashes and opportunity IDs,
- preserves per-route staging math,
- exposes execution candidates under `discoverableIsExecutableUponGating` logic.

### 2. Route Ranking

Ranking is driven by the VQC metadata model defined in `src/data/mockEngineData.ts` and visualized in `src/components/VqcRankerStudio.tsx`.

Documented model metrics:

- **Accuracy:** 89.42%
- **Precision:** 91.25%
- **Recall:** 86.90%
- **F1 score:** 0.8902
- **Training samples:** 142,850
- **Circuit shape:** 4 qubits, 3 layers

Feature weighting includes:

- virtual reserve ratio,
- path length penalty,
- pool fee weight,
- gas density,
- bottleneck TVL ratio,
- slippage variance.

The UI also exposes a live inference panel that converts route conditions into an execute/skip recommendation.

### 3. Pipeline Staging

The route lifecycle is explicitly modeled in `src/types.ts`:

`DISCOVERED → RANKED → SIMULATED → PREPARED → EXECUTED → ACCOUNTED`

That lifecycle is exercised in `src/App.tsx`, where routes can be:

- discovered,
- promoted through stages,
- checked against registry constraints,
- executed,
- logged into audit history,
- flushed to an accounting-ready state.

### 4. Execution Gating and Registry Safety

Execution is not purely cosmetic. The app contains explicit safety logic:

- wallet validation and nonce tracking,
- route asset registry validation before execution,
- stage promotion logic,
- audit log generation,
- gas and PnL updates after execution,
- live/safe signing separation in the mainnet guide.

The app also models:

- Balancer V3 flash-loan funding,
- concentrated liquidity and CPMM route surfaces,
- Aave V3 liquidation targets,
- zero-revert intent through execution integrity views.

### 5. Wallet, Balance, and Nonce Verification

`persistentState.ts` performs:

- native POL balance checks,
- USDC balance checks,
- nonce retrieval,
- RPC fallback handling,
- state persistence to local storage,
- deterministic wallet validation hashes.

This gives the console a measurable connection to live chain state even when opportunity generation remains simulated.

### 6. Historical Performance Reconstruction

The 90-day simulation studio:

- anchors to live Polygon block state,
- reconstructs 90 days of day-by-day records,
- tracks discovered vs executed trades,
- tracks gas, gross profit, net profit, cumulative PnL, flash-loan volume, and win rate,
- uses a deterministic seeded generator so repeated runs remain reproducible given the same anchor assumptions.

It is best understood as a **reconstruction and scenario visualization** backed by live anchors, not as a ledger export of independently verified historical fills.

### 7. Benchmark and Readiness Diagnostics

The benchmark panel publishes a six-step readiness narrative including:

1. Rust core math engine build
2. Uniswap V3 virtual reserve precision test
3. Capital injector calculus solver validation
4. Self-funding isolation and registry check
5. Redis stream throughput benchmark
6. VQC retraining and evaluation

Current displayed benchmark metrics:

- **Overall readiness:** 98.2%
- **Pipeline latency:** 0.98 ms
- **Max throughput:** 18,500 simulations/sec
- **Routes tested:** 2,842
- **Valid routes:** 2,710

These values are currently sourced from `INITIAL_BENCHMARK` in `mockEngineData.ts`.

### 8. Audit, Ledger, and Persistence Surfaces

The repository includes:

- local storage persistence for wallet/routes/audit logs,
- Firestore sync helpers for routes and audit logs,
- Firebase auth integration,
- audit stream modeling with SQL-sync state,
- Google Drive export and archival helpers.

### 9. AI-Assisted Analysis

The Express server exposes `/api/gemini/analyze-route`, which accepts route data and returns structured JSON with:

- analysis summary,
- risk level,
- key risk factors,
- execution optimization advice,
- suggested slippage,
- audit SQL query ideas,
- score recommendation.

## Discovery, Ranking, Executability, Profitability, and ROI

### Discovery Proof Surface

Discovery evidence in the repository is shown through:

- the full-chain metrics object,
- the Top 50 cycle dashboard,
- protocol/token universe definitions,
- route generation over the indexed token and DEX lists,
- discovery status changes in the automation loop.

### Ranking Proof Surface

Ranking evidence is shown through:

- VQC model metrics,
- per-route VQC scores,
- batch VQC evaluation,
- execute/skip recommendation logic,
- promotion of candidates from discovered to prepared states.

### Executability Proof Surface

Executability is represented by:

- positive-net gating,
- VQC thresholding in Top 50 views,
- asset-registry validation before execution,
- wallet nonce/balance checks,
- explicit `PREPARED`, `EXECUTED`, and `ACCOUNTED` stages,
- transaction hash assignment during execution/accounting progression.

### Profitability Proof Surface

Profitability is surfaced in several places:

- route-level `grossProfitUSD`, `estimatedGasUSD`, and `netProfitUSD`
- audit logs for successful vs reverted scenarios
- 90-day cumulative net PnL
- flash-loan volume summaries
- benchmark valid-route totals
- wallet total net profit accumulation in app state

Representative seeded route economics in `INITIAL_ROUTES` show:

- net profits from roughly **$142** to **$889**
- inputs from **$28.5k** to **$110k**
- gas estimates from roughly **$0.42** to **$1.25**

### Potential ROI Interpretation

This repository exposes ROI in two ways:

1. **Route-level opportunity scoring** in the Top 50 dashboard through `roiBps`
2. **Scenario profitability tracking** through net PnL, gas, flash volume, and historical totals

For professional interpretation:

- treat `roiBps` as a **ranking and prioritization signal** unless independently reconciled against actual capital, builder tip, and settlement cost inputs,
- treat 90-day net PnL as a **deterministic simulation output anchored to live chain state**,
- treat seeded initial route profits as **scenario examples** rather than audited realized performance.

In short: the repository already demonstrates how profitability and ROI are *modeled, ranked, and surfaced*, but it does **not** by itself constitute an independently audited book of realized returns.

## Current Test and Validation Story

### Repository-Level Commands

The root package currently exposes:

- `npm run dev`
- `npm run build`
- `npm run start`
- `npm run clean`
- `npm run lint`

`npm run lint` is a TypeScript no-emit check.

### In-Repository Proof Artifacts

#### A. Benchmark Suite Claims

The benchmark data currently asserts:

- Rust build success
- V3 virtual reserve precision test pass
- capital injector derivative solver pass
- isolation/registry verification pass
- Redis/SQL accounting throughput pass
- VQC evaluation pass

#### B. Security Specification

`security_spec.md` documents a Firestore rules test matrix covering:

- anonymous writes,
- missing required fields,
- spoofed user IDs,
- immutable-field tampering,
- oversized payloads,
- invalid audit status values,
- shadow fields,
- unauthorized blanket reads,
- unverified email use,
- non-owner deletion,
- PII injection,
- malformed document ID attacks.

#### C. Execution-State Validation

At the application level, the code validates:

- route asset registry alignment before execution,
- wallet addresses and nonce posture,
- balance refresh behavior,
- persistence load/save/reset paths,
- audit log promotion into synced state.

## Architecture Overview

### Front End

- React 19
- Vite
- TypeScript
- Recharts
- Lucide icons

Primary orchestration lives in `src/App.tsx`.

### Back End

- Express server in `server.ts`
- health endpoint at `/api/health`
- Gemini route-analysis endpoint at `/api/gemini/analyze-route`

### Data and Domain Surfaces

- `src/data/mockEngineData.ts` — seeded routes, pools, metrics, benchmark data
- `src/types.ts` — route, pool, benchmark, audit, wallet, and config types
- `src/utils/persistentState.ts` — wallet live-state fetch and persistence
- `src/lib/*` — Firebase, auth, Firestore, and Drive helpers

## Operator Feature Inventory

The navigation surface exposes:

- Top 50 Routes (12s cycle)
- 90-Day Simulation
- Live Pipeline
- C1 × C2 logging
- EIP-1153 / latency studio
- VQC Alpha Ranker
- Execution Integrity
- Transaction builder
- On-chain block parity
- Capital injector
- Accountant stream
- Protocol registry
- Sonic/invariant studio
- Rust/Python hybrid studio
- Math equation indexer
- Google Drive sync
- Benchmark suite
- Gemini AI assistant
- Live-mainnet guide

### Transient Accounting Studio (EIP-1153)

The Transient Accounting Studio provides an off-chain simulation of the EIP-1153 transient
storage ledger that runs inside the executor contract during a flashloan callback chain.

Key features:

- **Execution-type awareness**: C1 (forward arbitrage), C2 (reverse/mirror arbitrage), and
  LIQUIDATION (Aave V3 borrower) paths are each modelled with the correct leg sequence.
- **Pool-role awareness**: pools classified as `FUNDING_FLASHLOAN` (Balancer Vault source),
  `SWAPPABLE_EXECUTION` (AMM swap hops), and `LIQUIDATION_TARGET` (Aave collateral/debt)
  produce the correct accounting phase for each leg.
- **Balancer Vault (dual V2/V3 compatible)**: both compatibility modes are addressed via a
  single vault address. Flash fee = 0% in both modes on Polygon.
- **UNLOCK / SETTLE lifecycle**: D₀ is opened at Balancer Vault UNLOCK, carried unchanged
  through intermediate legs, and verified at SETTLE. Profit = B_final − D₀.
- **Per-leg conservation checks**: each leg verifies |ε_j| ≤ ε_allowed ($0.01 USD by default
  — configurable in `src/config/chainConfig.ts`). Any violation surfaces as
  `TRANSIENT_LEG_ACCOUNTING_MISMATCH`.
- **Integrity hash H_j**: deterministic commitment over route path, pool addresses, feeBps,
  and amounts. Displayed as a 64-char hex string (TSTORE(INTEGRITY_SLOT, H_j)).
- **B_j / D_j / F_j timeline chart**: Recharts line chart showing running inventory, debt,
  and fee accumulation across all legs.
- **AccountantStream drawer**: click the "Trace" button on any audit log row in the
  Accountant Stream to open the Transient Accounting Studio for that route inline.
- **ExecutionIntegritySentinel badge**: every route in the pre-flight dispatch table now
  shows its transient accounting status (ε_max, legs checked, H truncated).
- **TransactionPayloadBuilder panel**: shows computed D₀, SETTLE pass condition, and the
  payload integrity hash before any transaction is submitted.

## Setup

```bash
npm install
npm run dev
```

Build production assets:

```bash
npm run build
```

Run the type check:

```bash
npm run lint
```

## Environment Notes

The repository includes an `.env.example`, but any operator should treat all environment values as examples that must be reviewed, replaced, and rotated before real use.

Relevant integrations include:

- Gemini API
- Polygon RPC / WSS
- executor wallet and target contract configuration
- Firebase app configuration
- Google auth / Drive access

## Professional Assessment

This repository is strongest today as:

- a richly detailed Polygon arbitrage operations console,
- a route discovery/ranking demonstration environment,
- a profitability and readiness visualization surface,
- a live-chain anchored simulation tool,
- a prototype control plane for future production hardening.

It is not yet sufficient, by this repository alone, to claim independently audited live profitability. What it does provide is a comprehensive, structured, and measurable framework for:

- proving discovery coverage,
- proving ranking methodology,
- proving execution gating,
- proving state persistence and operator readiness,
- surfacing profitable candidates and modeled ROI,
- documenting the safety boundaries between simulation mode and live mode.
