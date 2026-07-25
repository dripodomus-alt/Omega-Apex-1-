#!/usr/bin/env python3
"""
compute_readiness.py

Standalone Python helper to compute a 0-100 readiness score from benchmark artifacts.
Can be called by the master PowerShell script or used directly.

Usage:
    python scripts/reporting/compute_readiness.py out/readiness_report.json
    python scripts/reporting/compute_readiness.py --from-pipeline out/pipeline_validation_latest.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any


def load_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}", file=sys.stderr)
        return {}


def compute_readiness(report: Dict[str, Any]) -> int:
    """Compute a simple 0-100 readiness score from a report dict."""
    score = 0

    # Step success contribution (max 40)
    steps = report.get("Steps", [])
    if steps:
        passed = sum(1 for s in steps if s.get("Success"))
        score += int((passed / len(steps)) * 40)

    # Prerequisite contribution (max 25)
    prereq = report.get("Details", {}).get("PrerequisiteScore", 0)
    score += int(prereq * 0.25)

    # Benchmark success (max 20)
    if report.get("Details", {}).get("Anvil fork benchmark") or report.get("Details", {}).get("Pipeline validation"):
        score += 20

    # Pipeline output quality (max 15)
    if report.get("Details", {}).get("LatestReport"):
        score += 15

    return max(0, min(100, score))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="out/readiness_report.json", help="Path to readiness_report.json")
    parser.add_argument("--from-pipeline", help="Alternative: compute from a pipeline_validation_latest.json")
    args = parser.parse_args()

    if args.from_pipeline:
        data = load_json(Path(args.from_pipeline))
        # Very rough heuristic if only pipeline data
        opps = len(data.get("opportunities", []))
        readiness = min(100, max(20, opps * 2))
        print(f"Readiness (from pipeline): {readiness}/100")
        return

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"Report not found: {report_path}")
        sys.exit(1)

    data = load_json(report_path)
    readiness = compute_readiness(data)
    print(f"Computed Readiness: {readiness}/100")

    # Also print breakdown if available
    if "Steps" in data:
        passed = sum(1 for s in data["Steps"] if s.get("Success"))
        print(f"Steps passed: {passed}/{len(data['Steps'])}")


if __name__ == "__main__":
    main()
