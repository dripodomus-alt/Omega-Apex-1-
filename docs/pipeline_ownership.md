# Strict Pipeline Ownership

This document is the logistics checkpoint for the Apex Omega modular refactor.
Do not add parallel replacement modules or duplicate "v2" files until the
existing owner has been mapped and the retirement path is explicit.

## Canonical Pipeline

```text
Environment -> Discovery -> Math -> Simulation -> Transactions -> Observability -> Storage
```

The hot-path doctrine remains:

```text
Scanner discovers.
Math sizes and ranks.
Simulation proves.
Transactions construct and execute.
Observability records.
Storage persists.
```

## Replacement Logistics Rule

Before replacing a file, function, or module:

1. Identify the current owner and all imports.
2. Decide whether the change is an in-place edit, a move, or a true new
   boundary.
3. If a new boundary is required, keep a compatibility wrapper at the old import
   path.
4. Delete or retire the old implementation in the same change once callers have
   moved.
5. Add or update tests proving the old and new paths do not diverge.

Do not leave deprecated copies with overlapping authority.

## Ownership Rules

### Environment

Owns settings, RPC/WSS clients, chain validation, block anchors, runtime feature
flags, secret loading, and redaction.

Must not discover pools, rank opportunities, simulate execution, or broadcast.

### Discovery

Owns Chain 137 intake and normalization: pool state loading, token/destination
normalization, freshness checks, TVL/depth checks, executable quote-source
validation, and normalized candidate emission.

Discovery emits `DiscoveryBatch`. It must not optimize size, rank net profit,
build calldata, simulate, or broadcast.

### Math

Owns deterministic economic truth: quotes, sizing, executable buy/sell prices,
gross profit, flash fees, gas, relay tips, risk buffer, net profit, and ranking.

Math consumes normalized discovery data and emits immutable ranked
opportunities. It must not query live chain state or build transactions.

### Simulation

Owns execution proof: fork setup, C1 simulation, post-C1 reload, C2
recomputation input, C2 decision, parity checks, revert decoding, and evidence.

Simulation must not broadcast.

### Transactions

Owns calldata, nonces, gas policy, bundles, broadcast guard, broadcast,
confirmation, receipts, and emergency stop.

Transactions must not rescan, rerank, or recompute opportunity economics.

The deployed-contract model remains explicit:

```text
C1 Aggressor = first contract / first transaction
C2 Surgeon   = second contract / second transaction
Liquidation  = separate third contract
```

### Observability

Owns structured append-only events, metrics, latency, health, and audits.

Observability must not influence domain decisions.

### Storage

Owns persistence interfaces and implementations for cycles, pools,
opportunities, simulations, executions, receipts, and manifests.

Domain logic depends on storage interfaces, not concrete PostgreSQL, Redis, CSV,
JSONL, or filesystem writers.

## Forbidden Imports

```text
discovery    -> simulation, transactions, concrete storage implementations
math         -> environment.rpc, discovery.protocol loaders, simulation, transactions
simulation   -> transactions.broadcast, transactions.coordinator
transactions -> discovery, math.ranking, math.sizing
observability-> domain decision logic
storage      -> math formulas, simulation engines, transaction builders
```

## Migration Order

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
