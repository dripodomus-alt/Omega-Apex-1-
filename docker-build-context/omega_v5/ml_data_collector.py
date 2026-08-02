#!/usr/bin/env python3
# ==============================================================================
# ml_data_collector.py -- Collects training data from execution traces.
#
# This script reads the PnL and execution trace ledgers to build a dataset
# for training the ML Alpha models. It extracts features from each opportunity
# and labels it with the final on-chain outcome (success, revert, slippage).
# ==============================================================================

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .paths import output_path

PNL_LEDGER_PATH = output_path("pnl_events.jsonl")
TRACE_LEDGER_PATH = output_path("execution_traces.jsonl")
DATASET_PATH = output_path("ml", "receipt_training_dataset.csv")
SUMMARY_PATH = output_path("ml", "receipt_training_summary.json")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def collect_training_data() -> dict[str, Any]:
    pnl_events = _read_jsonl(PNL_LEDGER_PATH)
    traces = {trace["trace_hash"]: trace for trace in _read_jsonl(TRACE_LEDGER_PATH)}

    rows: list[dict[str, Any]] = []
    stats = {"pnl_events": len(pnl_events), "traces": len(traces), "rows": 0}

    # This is a simplified feature extraction process. A real implementation
    # would extract dozens of features from the opportunity, pools, and market state.
    for event in pnl_events:
        if event.get("type") != "PNL":
            continue

        # Find the corresponding execution trace
        trace = traces.get(event.get("metadata", {}).get("trace_hash"))
        if not trace:
            continue

        # Extract features
        opp = trace.get("metadata", {}).get("opportunity", {})
        if not opp:
            continue

        # Label: 1 for success, 0 for failure/revert
        label = 1 if event.get("status") == "CONFIRMED" else 0

        rows.append({
            "opp_id": opp.get("opp_id"),
            "hop_count": len(opp.get("path", [])) - 1,
            "principal_usd": opp.get("profitability", {}).get("flashloan", {}).get("principal_usd"),
            "min_tvl_usd": opp.get("metadata", {}).get("sizing", {}).get("min_pool_tvl_usd"),
            "expected_net_usd": event.get("expected_net_usd"),
            "realized_net_usd": event.get("realized_net_usd"),
            "label": label,
        })

    if not rows:
        summary = {"status": "NO_DATA", "rows": 0, "dataset_path": str(DATASET_PATH)}
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    # Write to CSV
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    stats["rows"] = len(rows)
    summary = {"status": "OK", **stats, "dataset_path": str(DATASET_PATH)}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    summary = collect_training_data()
    print(f"ML data collection complete. Status: {summary['status']}, Rows: {summary['rows']}")
    print(f"Dataset saved to: {summary['dataset_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())