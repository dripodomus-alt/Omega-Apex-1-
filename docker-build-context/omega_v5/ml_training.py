#!/usr/bin/env python3
# ==============================================================================
# ml_training.py -- receipt-backed ML dataset and baseline model-card builder.
# Updated to include dynamic size bin features for optimizer training.
# + stablecoin gate features for specialized profitability training.
# ==============================================================================

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from .execution_trace import TRACE_LEDGER_PATH
from .ml_alpha import MODEL_SPECS, ROOT
from .paths import output_path
from .pnl_tracker import LEDGER_PATH


DATASET_PATH = output_path("ml/receipt_training_dataset.csv")
SUMMARY_PATH = output_path("ml/receipt_training_summary.json")


@dataclass(frozen=True)
class ReceiptTrainingRow:
    trace_hash: str
    stage: str
    status: str
    mode: str
    opp_id: str
    tx_hash: str
    block_number: int
    route: str
    hop_count: int
    pool_count: int
    expected_net_usd: str
    realized_net_usd: str
    gas_cost_usd: str
    gas_used: int
    receipt_status: int
    positive_realized: int
    reverted: int
    # NEW for dynamic size
    principal_usd: str = "0"
    selected_bin_usd: str = "0"
    optimizer_method: str = ""
    # NEW for stable gate
    is_stable_strategy: int = 0
    stable_gate_applied: int = 0
    stable_min_profit_override: str = "0.25"
    stable_risk_buffer_override: str = "0.10"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _pnl_by_trace() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in _read_jsonl(LEDGER_PATH):
        th = item.get("trace_hash") or item.get("tx_hash")
        if th:
            rows[th] = item
    return rows


def build_training_dataset() -> list[ReceiptTrainingRow]:
    """Builds rows that include dynamic bin + stable gate signals."""
    traces = _read_jsonl(TRACE_LEDGER_PATH)
    pnl_map = _pnl_by_trace()
    dataset: list[ReceiptTrainingRow] = []

    for t in traces:
        th = t.get("trace_hash") or t.get("tx_hash", "")
        pnl = pnl_map.get(th, {})
        route = t.get("route", "") or ""
        is_stable = 1 if "PEGGED_STABLE" in str(t.get("strategy", "")) or "stable" in route.lower() else 0
        stable_gate = 1 if t.get("metadata", {}).get("stable_gate_applied") else 0

        row = ReceiptTrainingRow(
            trace_hash=th,
            stage=t.get("stage", "unknown"),
            status=t.get("status", "unknown"),
            mode=t.get("mode", "dry"),
            opp_id=t.get("opp_id", ""),
            tx_hash=t.get("tx_hash", ""),
            block_number=int(t.get("block_number", 0)),
            route=route,
            hop_count=int(t.get("hop_count", 0)),
            pool_count=int(t.get("pool_count", 0)),
            expected_net_usd=str(_decimal(t.get("expected_net_usd"))),
            realized_net_usd=str(_decimal(pnl.get("realized_net_usd", t.get("expected_net_usd")))),
            gas_cost_usd=str(_decimal(t.get("gas_cost_usd"))),
            gas_used=int(t.get("gas_used", 0)),
            receipt_status=int(t.get("receipt_status", 0)),
            positive_realized=1 if _decimal(pnl.get("realized_net_usd", 0)) > 0 else 0,
            reverted=1 if t.get("status") == "reverted" else 0,
            principal_usd=str(_decimal(t.get("principal_usd", "0"))),
            selected_bin_usd=str(_decimal(t.get("selected_bin_usd", "0"))),
            optimizer_method=str(t.get("optimizer_method", "")),
            is_stable_strategy=is_stable,
            stable_gate_applied=stable_gate,
            stable_min_profit_override="0.25",
            stable_risk_buffer_override="0.10",
        )
        dataset.append(row)

    return dataset


def write_training_csv(rows: list[ReceiptTrainingRow]) -> Path:
    if not rows:
        return DATASET_PATH
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in asdict(rows[0]).keys()])
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))
    return DATASET_PATH


def main() -> None:
    rows = build_training_dataset()
    path = write_training_csv(rows)
    summary = {
        "rows": len(rows),
        "stable_rows": sum(r.is_stable_strategy for r in rows),
        "stable_gate_rows": sum(r.stable_gate_applied for r in rows),
        "generated_at": time.time(),
        "features": ["dynamic_bin", "stable_gate", "is_stable_strategy"],
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"ml_training: wrote {len(rows)} rows (stable={summary['stable_rows']}) to {path}")


if __name__ == "__main__":
    main()
