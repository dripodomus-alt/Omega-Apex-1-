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

Below is the production-grade rewrite, aligned to the current Apex-Omega architecture while preserving the distinction between what exists now and what must be proven before the system can be represented as production-live. The scanner doctrine already defines live Chain 137 intake, executable quote discovery, protocol-aware normalization, RustMath staging, simulation gating, transaction construction, private submission, and receipt-backed settlement as the target pipeline. Apex-Omega Scanner Execution.txt

APEX-OMEGA — SYSTEM STATUS & PRODUCTION READINESS

Apex-Omega is a Chain 137 multi-protocol trading-engine architecture currently operating across development, live-data discovery, simulation, and execution-integration layers.

The repository is substantially beyond a static UI prototype: its architecture defines live Polygon market discovery, protocol-native state normalization, deterministic opportunity ranking, simulation gating, transaction construction, private submission, and receipt-backed settlement.

However, production status is determined by verified runtime capability—not architectural intent, seeded demonstrations, UI presentation, or the presence of incomplete adapters.

Accordingly, any subsystem that has not been connected to live Chain 137 state, exercised end-to-end, and validated against actual execution outcomes must remain classified as development, simulation, integration, or validation-stage functionality.

Production Truth Standard

Apex-Omega follows one governing rule:

Hard logic protects correctness.
Dynamic configuration controls behavior.
Live state controls opportunity.
Simulation controls permission.
Settlement controls truth.

The system therefore distinguishes between:

ARCHITECTED
    capability exists in system design
IMPLEMENTED
    executable source exists
CONNECTED
    implementation is wired to its required live dependency
VALIDATED
    implementation has passed deterministic/runtime testing
SIMULATED
    complete execution path has passed state-accurate simulation
EXECUTED
    transaction has been submitted to Chain 137
SETTLED
    successful on-chain receipt confirms the final state transition

No lower state may be represented as a higher state.

A simulated opportunity is not realized profit.

A transaction envelope is not an execution.

A broadcast transaction is not settlement.

A projected P&L value is not realized P&L.

On-chain settlement is the final execution authority.

⸻

Current Data Classification

Repository outputs must explicitly identify their provenance.

Permitted classifications:

MOCK
SEEDED
DERIVED
LIVE_RPC
LIVE_QUOTE
SIMULATED
SUBMITTED
SETTLED

Seeded benchmark results, synthetic route opportunities, demonstration pool metrics, and simulated profitability values must remain clearly labeled and must never be represented as historical live trading performance.

Live values may only be labeled as such when sourced directly from current Chain 137 state or an explicitly identified live external provider.

Realized profit may only be recorded after successful settlement and receipt reconciliation.

⸻

Live Connectivity

The architecture supports a multi-lane external connectivity model.

Chain 137 State Layer

Live RPC/WSS infrastructure is responsible for:

block synchronization
contract reads
pool-state acquisition
balances
allowances
nonces
gas state
transaction submission
receipt retrieval
settlement verification

All execution-critical state must be block-anchored.

The scanner must reject stale or internally inconsistent state before execution permission is granted.

⸻

Multi-Protocol Discovery

Apex-Omega is designed as a protocol-family-aware Polygon Chain 137 scanner, rather than a scanner built around a single DEX ABI or fixed token pair.

Supported architecture families include:

V2 Constant Product / CPMM
V3 Concentrated Liquidity / CLMM
Algebra CLMM
Curve StableSwap
Balancer Weighted
Balancer Stable
Balancer Composable Stable
Order-book-compatible normalized surfaces

Protocol families remain independently modeled because their invariants, state requirements, quoting mechanisms, and execution interfaces differ.

For example, Uniswap V3 and QuickSwap Algebra must remain separate discovery/execution adapters rather than being forced through a common factory ABI.

⸻

Dynamic Market Intake

The scanner operates under an opportunistic market-selection doctrine.

It must not assume that a particular:

token
token pair
DEX
protocol
pool
fee tier
route template

is inherently preferable.

Current scanner eligibility doctrine requires:

Chain ID = 137
pool-native TVL available
pool-native TVL >= $50,000 USD-equivalent
live executable quote
supported invariant family
fresh block-anchored state
normalized execution destination
2+ comparable executable destinations
distinct buy and sell destinations

Same-pool round trips are invalid.

No asset is excluded solely because of its identity, and no protocol receives ranking priority solely because of its identity.

⸻

Deterministic Opportunity Engine

Eligible live state flows into the deterministic mathematical layer.

The math layer is responsible for protocol-correct:

quote normalization
fee accounting
executable-price calculation
price-impact calculation
slippage modeling
liquidity-depth analysis
route comparison
optimal sizing
profit calculation
candidate hashing
state hashing

The canonical ranking relation is:

BUY_LEG1_EXEC_PRICE < SELL_LEG2_EXEC_PRICE

For each comparable executable market:

LEG1 = lowest executable acquisition price
LEG2 = highest executable disposal price

A positive quoted spread alone is insufficient.

The route must remain profitable after execution size, price impact, venue fees, flash-capital costs, gas, slippage constraints, and all other deterministic execution costs are incorporated.

⸻

Invariant-Native Mathematics

Apex-Omega does not approximate heterogeneous protocols through a single reserve-ratio model.

The deterministic engine architecture explicitly distinguishes:

CPMM
CLMM
Algebra CLMM
StableSwap
Balancer Weighted
Balancer Stable
Balancer Composable Stable

Each invariant family exposes normalized execution operations while retaining its native mathematical implementation.

Canonical adapter behavior includes:

quote_exact_in()
quote_exact_out()
apply_swap()
marginal_price()
state_hash()
pool_identity()
supports_simulation()
supports_execution()

This allows strategy logic to consume normalized executable state without corrupting protocol-specific mathematics.

⸻

Dynamic Capital Sizing

Flash capital is an execution resource, not a fixed trade size.

Capital sizing must be determined dynamically from the executable route.

Conceptually:

MAX_EXECUTABLE_SIZE =
min(
    capital_provider_limit,
    executable_pool_depth,
    configured TVL/TLV safety ceiling,
    price-impact ceiling,
    slippage ceiling,
    route-profit optimum
)

The selected size must maximize net executable profit, rather than nominal spread.

No route receives execution permission merely because its smallest test quote is profitable.

⸻

RustMath Staging and Ranking

The canonical execution architecture separates discovery from deterministic ranking:

Scanner
    ↓
normalized eligible Chain 137 state
    ↓
RustMath
    ↓
deterministic executable-price staging
    ↓
candidate ranking
    ↓
optimal sizing

RustMath is the deterministic authority once its production implementation, PyO3 boundary, benchmark harness, and runtime integration have been completed and validated.

Until those components are actually present and exercised, the repository must distinguish the specified RustMath architecture from a verified production RustMath runtime.

⸻

Simulation Permission Layer

No ranked opportunity automatically receives execution permission.

Simulation must independently prove the transaction path against sufficiently fresh Chain 137 state.

Required validations include:

route does not revert
protocol calldata is valid
LEG1 output correctly feeds LEG2
expected output remains inside tolerance
gas requirement is viable
flash-capital repayment succeeds
slippage remains within policy
route remains net profitable
route hash matches simulated route
calldata hash matches approved transaction
state has not exceeded its freshness window

Simulation therefore acts as the boundary between:

PROFITABLE IN DETERMINISTIC MATH

and:

PERMITTED FOR EXECUTION

⸻

Transaction Construction

Simulation-approved opportunities are transformed into execution envelopes containing the complete transaction state required for submission.

This includes:

chain_id
cycle_id
route_hash
candidate_hash
simulation_hash
executor
protocol adapters
asset path
amount_in
minimum outputs
deadline
gas parameters
nonce
calldata
calldata_hash
execution mode

Synthetic or demonstration calldata must never enter live submission.

Live mode requires actual protocol-compatible executable calldata.

⸻

Execution Modes

The architecture supports logically identical upstream processing across:

DEV
SIMULATION
LIVE

Discovery, normalization, deterministic math, ranking, sizing, and execution gating should remain common.

The primary divergence occurs at submission.

DEV
→ inspect and diagnose
SIMULATION
→ construct and validate without chain submission
LIVE
→ sign and submit the already-approved transaction

This prevents the simulation environment from becoming a materially different trading engine than the production environment.

⸻

C1 / C2 Execution Architecture

Apex-Omega treats C1 and C2 as execution cycles, not individual swap legs.

C1
  LEG1 → buy
  LEG2 → sell
C1 settles
POST-C1 STATE RECOMPUTE
C2
  MIRROR
  REVERSE
  DO_NOTHING
  EXPIRE

C2 must never assume that the state predicted before C1 still exists afterward.

It requires:

successful C1 receipt
confirmed C1 block
newer post-C1 state
changed state hash
fresh executable quotes
fresh deterministic ranking
fresh sizing
fresh simulation

Only then may C2 receive execution permission.

⸻

State Freshness

Market state is transient.

Apex-Omega therefore treats freshness as a dynamic execution property rather than a permanently hardcoded number of blocks.

The validity window must be derived from measured production cycle duration:

STATE_TTL =
measured complete discovery-to-execution cycle
+
3 additional cycle-equivalents

Hard revalidation remains mandatory before simulation and execution.

The TTL provides operational time for the system to discover, normalize, rank, size, simulate, construct, and submit an opportunity.

It does not override state correctness.

⸻

Settlement and Realized P&L

Settlement is the final truth source.

After submission, the system must reconcile:

transaction hash
receipt status
confirmed block
gas actually consumed
effective gas price
actual token movements
flash-capital repayment
protocol fees
wallet balance delta
settlement asset delta

Canonical accounting distinction:

RAW_DELTA
    ↓
deterministic execution deductions
AFTER_MATH_DELTA
    ↓
simulation / submission / settlement
REAL_DELTA

Only REAL_DELTA derived from confirmed settlement may be represented as realized trading P&L.

⸻

Risk and Execution Controls

Production execution requires active controls covering at minimum:

state freshness
nonce integrity
allowances
wallet balances
flash-capital availability
pool identity
same-pool rejection
price divergence
slippage
gas economics
minimum net profit
profit-to-gas ratio
simulation success
calldata integrity
duplicate opportunity suppression
transaction replacement
receipt verification
C1/C2 state isolation

Missing production functionality must be implemented rather than hidden behind permanent feature gates.

Fail-closed behavior is reserved for genuine runtime safety violations such as:

stale state
invalid signature
failed simulation
broken invariant
nonce conflict
unsafe price divergence
invalid calldata
insufficient capital
unprofitable recomputation
expired execution envelope

⸻

Security and Audit Status

Apex-Omega must not be described as formally audited, formally verified, or mainnet battle-tested unless those milestones have actually occurred and their evidence is available.

Until independent security review and sustained production validation are completed:

formal audit status        = UNVERIFIED
formal verification status = UNVERIFIED
mainnet battle-test status  = UNVERIFIED

This classification does not invalidate implemented functionality.

It prevents architecture, implementation, simulation, and production validation from being conflated.

⸻

Core System Capabilities

The target integrated system consists of:

01. Chain 137 RPC/WSS state ingestion
02. Multi-protocol pool discovery
03. Protocol-native invariant adapters
04. $50K minimum pool-TVL eligibility enforcement
05. Dynamic asset and venue discovery
06. Executable quote acquisition
07. Block-anchored state normalization
08. Comparable-market construction
09. Same-pool / same-destination rejection
10. Deterministic RustMath staging
11. Lowest-buy / highest-sell executable ranking
12. Dynamic capital and flashloan sizing
13. Complete cost and net-profit accounting
14. State-accurate simulation
15. Transaction-envelope construction
16. Protocol-specific calldata generation
17. Nonce and submission-lane management
18. Private transaction submission
19. Receipt monitoring and reconciliation
20. C1/C2 execution-state management
21. Settlement-derived realized P&L
22. Persistent telemetry and execution ledger
23. Firebase / application-state integration
24. Operator-console observability
25. DEV / SIMULATION / LIVE operating modes

⸻

Production Classification Rule

Apex-Omega should be represented according to the strongest state that can be demonstrated for each subsystem.

Design alone       ≠ implementation.
Implementation     ≠ connectivity.
Connectivity       ≠ validation.
Validation         ≠ simulation.
Simulation         ≠ execution.
Execution          ≠ settlement.
Settlement         = operational truth.

The production objective is therefore not to make the repository appear production-ready.

The objective is to make every critical path independently provable:

LIVE STATE
    ↓
ELIGIBILITY
    ↓
DETERMINISTIC MATH
    ↓
RANKING
    ↓
SIZING
    ↓
SIMULATION
    ↓
EXECUTION GATE
    ↓
TRANSACTION BUILD
    ↓
PRIVATE SUBMISSION
    ↓
RECEIPT
    ↓
SETTLEMENT
    ↓
REALIZED P&L

When that entire chain is operational, instrumented, security-reviewed, and repeatedly validated against Chain 137 settlement, Apex-Omega can correctly transition from an execution-capable development system into a production trading system.

This version is suitable as the repository’s SYSTEM_STATUS.md, README production-status section, or operator-console disclosure.

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
