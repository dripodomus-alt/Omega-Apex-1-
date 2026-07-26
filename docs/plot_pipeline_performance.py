#!/usr/bin/env python3
"""
plot_pipeline_performance.py

This script reads the JSON report from `walk_pipeline.py` and generates a pie
chart to visualize the performance breakdown of the different pipeline stages.

This helps identify bottlenecks in the discovery and validation process.
"""

import argparse
import json
from pathlib import Path

try:
    import matplotlib.pyplot as plt
except ImportError:
    print("matplotlib is not installed. Please install it with: pip install matplotlib")
    exit(1)


def plot_performance(report_path: Path, output_path: Path):
    """Loads the report, extracts performance data, and generates a pie chart."""
    if not report_path.exists():
        print(f"Error: Report file not found at {report_path}")
        return

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    perf_analysis = data.get("performance_analysis")
    if not perf_analysis or "stage_breakdown" not in perf_analysis:
        print("Error: No performance_analysis section found in the report.")
        return

    stage_breakdown = perf_analysis["stage_breakdown"]
    labels = list(stage_breakdown.keys())
    sizes = [stage["percentage_of_total"] for stage in stage_breakdown.values()]
    total_duration = perf_analysis["total_cycle_time_seconds"]

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

    plt.title(f"Pipeline Stage Performance Breakdown\nTotal Cycle Time: {total_duration:.2f} seconds")
    plt.savefig(output_path)
    print(f"✅ Performance chart saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize pipeline performance from a JSON report.")
    parser.add_argument("--report", default="out/pipeline_walk_latest.json", help="Path to the input JSON report file.")
    parser.add_argument("--output", default="out/pipeline_performance.png", help="Path to save the output chart image.")
    args = parser.parse_args()

    plot_performance(Path(args.report), Path(args.output))