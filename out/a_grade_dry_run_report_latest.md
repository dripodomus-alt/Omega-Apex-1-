# A-Grade Dry-Run Report

Generated: 2026-07-17
Mode forced for local probes: dry_run
Broadcast attempted: no

## Source Review

- Python compile gate: PASS after fixing two source defects.
- Focused tests: PASS, 23 passed.
- Docker Compose config: PASS.
- PM2 ecosystem config: PASS.

## Source Defects Found And Fixed

1. omega_v5/main.py
   - Problem: run_execution_loop call used a positional argument after a keyword argument.
   - Fix: changed live_pools to an explicit keyword argument.

2. omega_v5/pipeline_validation.py
   - Problem: _validate_runtime_settings referenced rpc_url out of scope.
   - Fix: read target_rpc from the report.

3. omega_v5/pipeline_validation.py
   - Problem: cached pool path referenced redis_cache without importing it.
   - Fix: imported omega_v5.redis_cache.

## Runtime Dry-Run Proofs

- Runtime alignment: PASS.
- Session signer / WaaS isolation: PASS.
- Remote Execute attempted: false.
- Missing metadata background worker: PASS, active continuous cycle.
- Metadata promotion review: PASS, fail-closed.

## Current Artifact Counters

- Missing metadata cases: 364.
- Apprentice proposals reviewed: 62.
- Apprentice proposals approved: 0.
- Apprentice proposals rejected: 62.
- Asset state research:
  - assets: 394
  - metadata pass: 371
  - ready for route search: 21
  - rate pairs: 390
  - directional quote edges: 605
- Route execution staging:
  - attempted: 1
  - staged for executor truth: 0
  - rejected: 1
  - rejection stage: sizing_rejected

## Cloud Run Runtime Evidence

Service: flashloan-execution-monitor
Revision: flashloan-execution-monitor-00022-jqf
Runtime mode: dry_run
Live trading: 0

Recent Cloud Run dry-run logs show:

- RPC connected to Polygon chain 137.
- Factory discovery promoted 182 live pools from 390 live found.
- Dynamic pool registry staged 256 metadata pools.
- Curve official registry staged 77 pools.
- 569 pools loaded live with 0 failed.
- V3/Algebra audit: 207 passed, 82 filtered out.
- LIVE_POOLS ready: 487 pools across 5 protocol families.
- Total executable liquidity hydrated: 478/487 pools.
- CoinGecko and Chainlink price paths executed; one CoinGecko 429 was observed and Chainlink still confirmed 15 prices.
- Macro scanner mounted and processed 5 cross-protocol mutations.
- Liquidation watcher ran in dry_run with 0 packets ready.

## Local Long-Run Blocks

- Local asset_state_research live refresh exceeded 4 minutes and was stopped.
- Local route_execution_stager live refresh exceeded 4 minutes and was stopped.
- Local pipeline_validation --cache --no-eth-call exceeded 5 minutes and was stopped.
- Local main one-shot --no-scan exceeded 3 minutes and was stopped.

These are runtime-duration blocks in the local shell, not broadcast attempts. Cloud Run is currently completing the long-running discovery/hydration cycle in dry_run mode.

## Grade

A- for safety and source integrity:

- PASS: no broadcast attempted.
- PASS: dry-run runtime alignment.
- PASS: session/WaaS fail-closed proof.
- PASS: focused source tests.
- PASS: config parse.
- PASS: Cloud Run dry-run discovery/hydration evidence.
- WARN: local full pipeline validation still needs a bounded/cached fast path to finish under local shell time limits.
- WARN: no route is currently staged for executor truth; current staged candidate was rejected at sizing.
- WARN: metadata promotion remains fail-closed with 0 approvals.
