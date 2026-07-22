# Strict Pipeline Ownership

Omega migration work must preserve a one-way ownership model:

```text
Environment -> Discovery -> Math -> Simulation -> Transactions
```

`Observability` and `Storage` are side-effect ports owned by applications. They
must not decide profitability, execution eligibility, or transaction policy.

## Ownership Rules

### Environment

Owns infrastructure truth: settings, network definitions, RPC/WSS clients,
chain guards, block anchors, runtime feature flags, secret loading, and
redaction.

Environment must not discover pools, rank opportunities, simulate execution, or
broadcast transactions.

### Discovery

Owns Chain 137 intake and normalization: pool state loading, token and
destination normalization, freshness checks, TVL/depth checks, executable quote
source validation, and normalized candidate emission.

Discovery emits `DiscoveryBatch`. It must not optimize size, choose best
buy/sell, compute net profit, build calldata, simulate, or broadcast.

### Math

Owns deterministic economic truth: invariant-specific quotes, adaptive sizing,
buy/sell price determination, gross profit, full cost accounting, expected net
profit, and deterministic ranking.

Math consumes normalized discovery data and emits immutable
`RankedOpportunity` records. It must not import RPC providers, query live chain
state, build transactions, or write concrete storage.

### Simulation

Owns execution proof: fork setup, C1 simulation, post-C1 reload, C2
recomputation input, C2 decision, parity checks, revert decoding, and
simulation evidence.

Simulation emits `SimulationResult`. It must not broadcast.

### Transactions

Owns transaction construction and submission only: calldata, nonces, gas policy,
bundles, broadcast guard, broadcast, confirmation, receipts, and emergency stop.

Transactions must not rescan, rerank, or recompute opportunity economics.

The deployed-contract model remains explicit:

```text
C1 Aggressor = first contract / first transaction
C2 Surgeon   = second contract / second transaction
Liquidation  = separate third contract
```

### Observability

Owns structured append-only operational events, metrics, latency, health, and
audits. It must not influence domain decisions.

### Storage

Owns persistence interfaces and implementations for cycles, pools, ranked
opportunities, simulations, executions, receipts, and audit manifests.

Domain logic depends on storage interfaces, not concrete PostgreSQL, Redis, CSV,
JSONL, or filesystem writers.

## Forbidden Imports

```text
discovery    -> simulation, transactions, concrete storage implementations
math         -> environment.rpc, discovery.protocols loaders, simulation, transactions
simulation   -> transactions.broadcast, transactions.coordinator
transactions -> discovery, math.ranking, math.sizing
observability-> discovery, math, simulation, transactions domain decisions
storage      -> math formulas, simulation engines, transaction builders
```

## Migration Sequence

1. Inventory and freeze existing behavior.
2. Extract shared immutable models.
3. Extract environment providers behind interfaces.
4. Isolate discovery behind `DiscoveryEngine.discover() -> DiscoveryBatch`.
5. Isolate deterministic math behind `OpportunityRanker.rank(batch)`.
6. Extract simulation and C1/C2 parity proof.
7. Extract transactions, broadcast guard, and receipts.
8. Add repository and structured event ports.
9. Replace the old monolithic entrypoint with an application orchestrator.

The existing `omega_v5` package remains the compatibility runtime until parity
tests prove each moved boundary.
