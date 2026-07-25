#!/usr/bin/env python3
# ==============================================================================
# generate_benchmark_report.py
#
# Parses a directory of `pipeline_validation` JSON artifacts and generates a
# consolidated performance and PnL report.
#
# Now also supports simple readiness scoring hints for the master benchmark script.
#
# Usage:
#   python scripts/reporting/generate_benchmark_report.py <path_to_report_dir>
#
# Example:
#   python scripts/reporting/generate_benchmark_report.py out
# ==============================================================================

import argparse
import json
from pathlib import Path
from typing import Dict, Any


def parse_report(file_path: Path) -> Dict[str, Any]:
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


def generate_report(directory: Path, readiness_mode: bool = False):
    """Parses all JSON reports in a directory and generates a summary."""
    try:
        import pandas as pd
    except ImportError:
        print("Warning: pandas not installed. Using basic summary.")
        pd = None

    if not directory.is_dir():
        print(f"Error: Directory not found at '{directory}'")
        return

    report_files = list(directory.glob("*.json"))
    if not report_files:
        print(f"No JSON report files found in '{directory}'")
        return

    print(f"Found {len(report_files)} reports to analyze in '{directory}'...")

    all_results = [parse_report(f) for f in report_files]
    success_results = [r for r in all_results if r.get("error") is None]

    if not success_results:
        print("\nNo successful reports to analyze.")
        return

    if pd is not None:
        df = pd.DataFrame(success_results)
        print("\n--- Aggregate Performance Summary ---")
        print(f"Total Cycles Analyzed: {len(df)}")
        print(f"Total Estimated Profit: ${df['total_estimated_profit_usd'].sum():,.2f}")
        print(f"Total Payloads Built:   {df['payloads_built'].sum()}")
        print("\n--- Averages Per Cycle ---")
        print(df.mean(numeric_only=True).to_string())
    else:
        total_profit = sum(r["total_estimated_profit_usd"] for r in success_results)
        total_payloads = sum(r["payloads_built"] for r in success_results)
        print(f"\nTotal successful reports: {len(success_results)}")
        print(f"Total estimated profit: ${total_profit:,.2f}")
        print(f"Total payloads built: {total_payloads}")

    if readiness_mode:
        # Simple readiness hint
        avg_candidates = sum(r["total_candidates"] for r in success_results) / len(success_results)
        readiness_hint = min(100, max(0, int(avg_candidates / 5)))  # rough heuristic
        print(f"\n[Readiness Hint] Based on candidate volume: ~{readiness_hint}/100")


def main():
    parser = argparse.ArgumentParser(description="Parse benchmark artifacts and generate a performance report.")
    parser.add_argument(
        "report_dir",
        type=str,
        help="Directory containing the JSON report artifacts (e.g. 'out')."
    )
    parser.add_argument(
        "--readiness",
        action="store_true",
        help="Include simple readiness scoring hints."
    )
    args = parser.parse_args()
    generate_report(Path(args.report_dir), readiness_mode=args.readiness)


if __name__ == "__main__":
    main()
