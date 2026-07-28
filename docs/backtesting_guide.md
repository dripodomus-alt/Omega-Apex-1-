# Backtesting, Benchmarking & Performance Tuning Guide for Omega V5

This guide explains how to validate, benchmark, and tune the hybrid Rust+Python arbitrage engine for maximum performance.

## Running the Master Readiness Script

Use the enhanced script for both validation and bottleneck discovery:

```powershell
# Baseline (quick check)
.\benchmarks\run_full_benchmark_and_readiness.ps1

# Full stress test + bottleneck analysis
.\benchmarks\run_full_benchmark_and_readiness.ps1 -ScannerTokens 100 -ScannerPoolsPerPair 20 -BottleneckAnalysis
```

The script now:
- Accepts `-ScannerTokens`, `-ScannerPoolsPerPair`, `-MinTvlUsd`, `-BottleneckAnalysis`
- Outputs structured JSON to `out/benchmark_results/`
- Detects multiplier degradation or latency spikes
- Integrates into the final readiness score

## Bottleneck Discovery Process

1. Run at increasing complexity (25/5 → 50/10 → 100/20).
2. Observe:
   - **Rust vs Python Multiplier**: Should stay high (ideally >5-10x). Drop indicates Python fallback overhead or Rust scaling limit.
   - **Absolute Rust Time**: Target <150ms for production cycles. >500ms flags a bottleneck.
   - **Opportunities Found**: Scales with pool count but must match between implementations.
3. JSON reports contain full metrics for offline analysis (e.g., plot with matplotlib in notebooks/).

When a bottleneck appears, switch to a tuned `.env` template (see below).

## Reverse-Engineered Configuration Templates

These `.env` files were derived from benchmark runs. Copy the one that matches your market conditions.

### .env.max_speed (Low-Latency, Competitive Markets)
```env
SCANNER_MODE=rust
TARGET_TOKENS="USDC,WETH,WBTC,MATIC,USDT,DAI"
MIN_TVL_USD=500000
RPC_QUOTA_ENFORCEMENT=true
RPC_RPS_LIMIT=25
```
**When to use**: High-frequency trading where cycle time must stay ~5s. Benchmarks show best multiplier here.

### .env.deep_scan (Broad Market Exploration)
```env
SCANNER_MODE=rust
TARGET_TOKENS="*"
MIN_TVL_USD=50000
RPC_QUOTA_ENFORCEMENT=true
RPC_RPS_LIMIT=15
```
**When to use**: Offline discovery or when hunting long-tail opportunities. Higher pool counts are tolerated.

## Interpreting Results & Next Steps

- If multiplier collapses at high complexity → adopt `.env.max_speed` and limit TARGET_TOKENS in code.
- If Rust time grows linearly but stays acceptable → `.env.deep_scan` is viable.
- Always re-run the readiness script after swapping .env files.
- For visualization, see `notebooks/` or `docs/plot_pipeline_performance.py`.
- Update this guide when new templates are reverse-engineered from fresh benchmarks.
- Benchmark results form a key part of the continuous improvement and review process outlined in the project's Data Governance policy.

This turns the readiness script into an active optimization tool. Combine with ML alpha ranker and pipeline_validation for production readiness.

Last updated: Bottleneck analysis and templates added per performance transition plan.
