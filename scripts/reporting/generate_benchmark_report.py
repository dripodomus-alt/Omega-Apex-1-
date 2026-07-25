#!/usr/bin/env python3
# ==============================================================================
# generate_benchmark_report.py
#
# Parses a directory of `pipeline_validation` JSON artifacts and generates a
# consolidated performance and PnL report.
#
# Usage:
#   python scripts/reporting/generate_benchmark_report.py <path_to_report_dir>
#
# Example:
#   # After a finalizer run
#   python scripts/reporting/generate_benchmark_report.py out/finalizer/20260721-143000
#
#   # After manually saving benchmark cycle outputs
#   python scripts/reporting/generate_benchmark_report.py out/my_benchmark_run
# ==============================================================================

import argparse
import json
from pathlib import Path


def parse_report(file_path: Path) -> dict:
    """Parses a single pipeline_validation JSON report."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data.get("ok", False):
            return {"file": file_path.name, "error": data.get("error", "Unknown error")}

        opps = data.get("opportunities", [])
        perf_metrics = data.get("performance_metrics", {})
        truth_metrics = data.get("executor_truth", {})

        return {
            "file": file_path.name,
            "elapsed_seconds": data.get("elapsed_seconds", 0),
            "total_candidates": perf_metrics.get("total_candidates", 0),
            "python_quote_calls": perf_metrics.get("python_quote_calls", 0),
            "truth_passed": truth_metrics.get("passed", 0),
            "payloads_built": len(opps),
            "total_estimated_profit_usd": sum(o.get("estimated_profit_usd", 0) for o in opps),
            "error": None
        }
    except Exception as e:
        return {"file": file_path.name, "error": str(e)}


def generate_report(directory: Path):
    """Parses all JSON reports in a directory and generates a summary."""
    # For this script, we need pandas.
    try:
        import pandas as pd
    except ImportError:
        print("Error: pandas is not installed. Please run 'pip install pandas'")
        return

    if not directory.is_dir():
        print(f"Error: Directory not found at '{directory}'")
        return

    # The finalizer saves the JSON directly, but let's be flexible.
    report_files = list(directory.glob("*.json"))
    if not report_files:
        print(f"No JSON report files found in '{directory}'")
        return

    print(f"Found {len(report_files)} reports to analyze in '{directory}'...")

    all_results = [parse_report(f) for f in report_files]
    df = pd.DataFrame(all_results)

    error_df = df[df['error'].notna()]
    if not error_df.empty:
        print("\n--- Errors Encountered ---")
        print(error_df.to_string(index=False))

    success_df = df[df['error'].isna()].drop(columns=['error', 'file'])
    if success_df.empty:
        print("\nNo successful reports to analyze.")
        return

    print("\n--- Aggregate Performance Summary ---")
    print(f"Total Cycles Analyzed: {len(success_df)}")
    print(f"Total Estimated Profit: ${success_df['total_estimated_profit_usd'].sum():,.2f}")
    print(f"Total Payloads Built:   {success_df['payloads_built'].sum()}")
    print("\n--- Averages Per Cycle ---")
    print(success_df.mean().to_string())

    # Also analyze the synthetic dry run log if it exists in the output directory
    dry_run_log = directory / "dry_run_full_log.jsonl"
    if dry_run_log.is_file():
        print(f"\nAnalyzing synthetic dry run log: {dry_run_log}...")
        dry_run_data = []
        with open(dry_run_log, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    dry_run_data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if dry_run_data:
            dry_run_df = pd.DataFrame(dry_run_data)
            # Convert relevant columns to numeric for calculations
            numeric_cols = ['spread_bps', 'flash_principal_usd', 'economic_net_profit_usd', 'headroom_usd']
            for col in numeric_cols:
                if col in dry_run_df.columns:
                    dry_run_df[col] = pd.to_numeric(dry_run_df[col], errors='coerce')

            print("\n--- Synthetic Dry Run (25-cycle) Summary ---")
            passed_gate_df = dry_run_df[dry_run_df['passes_gate'] == True]
            print(f"Total Profitable Routes Found: {len(passed_gate_df)}")
            if not passed_gate_df.empty:
                print(f"Average Net Profit (USD): ${passed_gate_df['economic_net_profit_usd'].mean():.4f}")
                print(f"Max Net Profit (USD):     ${passed_gate_df['economic_net_profit_usd'].max():.4f}")
                print(f"Average Spread (BPS):     {passed_gate_df['spread_bps'].mean():.2f}")

def main():
    parser = argparse.ArgumentParser(description="Parse benchmark artifacts and generate a performance report.")
    parser.add_argument(
        "report_dir",
        type=str,
        help="Directory containing the JSON report artifacts to analyze (e.g., 'out/finalizer/20260720-123456')."
    )
    args = parser.parse_args()
    generate_report(Path(args.report_dir))


if __name__ == "__main__":
    main()