#!/usr/bin/env python3
# ==============================================================================
# pnl_tracker.py -- append-only dry-run/live C1/C2 PnL ledger + pipeline metrics.
#
# Tracks:
# - PNL events (C1/C2/LIQUIDATION)
# - Lifespan events (staged, executed, expired)
# - Stage / Execute / Expire counts
# - Successful submission/staging
# - Full logging of pipeline alignment events
#
# All events are JSONL for auditability. Snapshots for UI.
# ==============================================================================

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from decimal import Decimal
from typing import Any

from .paths import output_path
from .redis_cache import client as redis_client, key as redis_key
from .runtime_control import normalize_mode

# Setup logging for pipeline events
logger = logging.getLogger("omega.pipeline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [PIPELINE] %(levelname)s: %(message)s"))
    logger.addHandler(handler)

LEDGER_PATH = output_path("pnl_events.jsonl")
SNAPSHOT_PATH = output_path("pnl_snapshot.json")
REDIS_SNAPSHOT_KEY = redis_key("runtime", "pnl_snapshot")
LIVE_RESET_CONFIRM = "RESET_LIVE_PNL"

_LOCK = threading.Lock()

# Pipeline metrics (in-memory for current run, persisted via events)
_pipeline_metrics = {
    "staged_count": 0,
    "executed_count": 0,
    "expired_lifespan_count": 0,
    "successful_submissions": 0,
    "successful_stagings": 0,
    "lifespan_checks": 0,
}


def _now_ns() -> int:
    return time.time_ns()


def _decimal_text(value: Decimal | int | float | str | None) -> str:
    if value is None:
        return ""
    try:
        return str(Decimal(str(value)))
    except Exception:
        return ""


def _as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _append_event(event: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with LEDGER_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")


def _read_events() -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    with _LOCK:
        for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    events.append(item)
            except Exception:
                continue
    return events


def record_pnl_event(
    *,
    mode: str,
    stage: str,
    status: str,
    opp_id: str = "",
    route: list[str] | None = None,
    expected_net_usd: Decimal | int | float | str | None = None,
    realized_net_usd: Decimal | int | float | str | None = None,
    gas_cost_usd: Decimal | int | float | str | None = None,
    tx_hash: str = "",
    block: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_mode = normalize_mode(mode)
    normalized_stage = stage.strip().upper()
    if normalized_stage not in {"C1", "C2", "LIQUIDATION"}:
        raise ValueError(f"unsupported PnL stage: {stage}")
    event = {
        "type": "PNL",
        "event_id": f"pnl-{_now_ns()}",
        "created_at_ns": _now_ns(),
        "mode": normalized_mode,
        "stage": normalized_stage,
        "status": status.strip().upper(),
        "opp_id": opp_id,
        "route": list(route or []),
        "expected_net_usd": _decimal_text(expected_net_usd),
        "realized_net_usd": _decimal_text(realized_net_usd),
        "gas_cost_usd": _decimal_text(gas_cost_usd),
        "tx_hash": tx_hash,
        "block": block,
        "metadata": metadata or {},
    }
    _append_event(event)
    snapshot = pnl_summary()
    _write_snapshot(snapshot)
    logger.info(f"PNL recorded: mode={normalized_mode} stage={normalized_stage} status={status} opp={opp_id}")
    return event


def record_lifespan_event(
    *,
    event_type: str,  # "STAGED", "EXECUTED", "EXPIRED", "SUBMITTED"
    discovery_block: int,
    current_block: int,
    route: list[str] | None = None,
    opp_id: str = "",
    status: str = "OK",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record lifespan-related pipeline events for staging/execution/expiry tracking."""
    event = {
        "type": "LIFESPAN",
        "event_id": f"lifespan-{_now_ns()}",
        "created_at_ns": _now_ns(),
        "event_type": event_type.upper(),
        "discovery_block": discovery_block,
        "current_block": current_block,
        "lifespan_used": current_block - discovery_block if current_block and discovery_block else 0,
        "route": list(route or []),
        "opp_id": opp_id,
        "status": status.upper(),
        "metadata": metadata or {},
    }
    _append_event(event)
    # Update in-memory metrics
    if event_type.upper() == "STAGED":
        _pipeline_metrics["staged_count"] += 1
        _pipeline_metrics["successful_stagings"] += 1 if status.upper() == "OK" else 0
    elif event_type.upper() == "EXECUTED":
        _pipeline_metrics["executed_count"] += 1
    elif event_type.upper() == "EXPIRED":
        _pipeline_metrics["expired_lifespan_count"] += 1
    elif event_type.upper() == "SUBMITTED":
        _pipeline_metrics["successful_submissions"] += 1
    _pipeline_metrics["lifespan_checks"] += 1

    snapshot = pnl_summary()
    _write_snapshot(snapshot)
    logger.info(
        f"LIFESPAN {event_type}: discovery={discovery_block} current={current_block} "
        f"used={event['lifespan_used']} opp={opp_id} status={status}"
    )
    return event


def record_stage_event(
    *,
    stage: str,
    status: str,
    route: list[str] | None = None,
    opp_id: str = "",
    block: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Document all staging events with full pipeline alignment logging."""
    event = {
        "type": "STAGE",
        "event_id": f"stage-{_now_ns()}",
        "created_at_ns": _now_ns(),
        "stage": stage.upper(),
        "status": status.upper(),
        "route": list(route or []),
        "opp_id": opp_id,
        "block": block,
        "metadata": metadata or {},
    }
    _append_event(event)
    logger.info(f"STAGE {stage}: status={status} opp={opp_id} block={block}")
    return event


def record_successful_submission(
    *,
    tx_hash: str,
    route: list[str] | None = None,
    opp_id: str = "",
    block: int | None = None,
    net_pnl_usd: Decimal | str = "0",
) -> dict[str, Any]:
    """Track successful on-chain submissions."""
    event = {
        "type": "SUBMISSION",
        "event_id": f"submit-{_now_ns()}",
        "created_at_ns": _now_ns(),
        "tx_hash": tx_hash,
        "route": list(route or []),
        "opp_id": opp_id,
        "block": block,
        "net_pnl_usd": _decimal_text(net_pnl_usd),
    }
    _append_event(event)
    _pipeline_metrics["successful_submissions"] += 1
    logger.info(f"SUCCESSFUL SUBMISSION: tx={tx_hash} opp={opp_id} pnl={net_pnl_usd}")
    return event


def record_reset(mode: str, *, actor: str = "api", confirm: str = "") -> dict[str, Any]:
    normalized = normalize_mode(mode)
    if normalized == "live" and confirm != LIVE_RESET_CONFIRM:
        raise ValueError(f"live PnL reset requires confirm={LIVE_RESET_CONFIRM}")
    event = {
        "type": "RESET",
        "event_id": f"reset-{_now_ns()}",
        "created_at_ns": _now_ns(),
        "mode": normalized,
        "actor": actor or "api",
        "confirm": confirm if normalized == "live" else "",
    }
    _append_event(event)
    snapshot = pnl_summary()
    _write_snapshot(snapshot)
    logger.info(f"RESET recorded for mode={normalized}")
    return event


def _empty_bucket() -> dict[str, Any]:
    return {
        "events": 0,
        "confirmed": 0,
        "failed": 0,
        "pending": 0,
        "positive": 0,
        "expected_net_usd": "0",
        "realized_net_usd": "0",
        "display_pnl_usd": "0",
        "gas_cost_usd": "0",
    }


def _add(bucket: dict[str, Any], *, mode: str, event: dict[str, Any]) -> None:
    expected = _as_decimal(event.get("expected_net_usd"))
    realized = _as_decimal(event.get("realized_net_usd"))
    gas = _as_decimal(event.get("gas_cost_usd"))
    status = str(event.get("status", "")).upper()
    failed_statuses = {"FAILED", "REVERTED", "ERROR", "SIMULATION_REJECTED"}

    bucket["events"] += 1
    bucket["expected_net_usd"] = str(_as_decimal(bucket["expected_net_usd"]) + expected)
    bucket["realized_net_usd"] = str(_as_decimal(bucket["realized_net_usd"]) + realized)
    bucket["gas_cost_usd"] = str(_as_decimal(bucket["gas_cost_usd"]) + gas)
    display_delta = realized if mode == "live" or status in failed_statuses else expected
    bucket["display_pnl_usd"] = str(_as_decimal(bucket["display_pnl_usd"]) + display_delta)
    if status in {"CONFIRMED", "SIMULATED", "DRY_RUN_STAGED", "C2_DECISION"}:
        bucket["confirmed"] += 1
    elif status in failed_statuses:
        bucket["failed"] += 1
    else:
        bucket["pending"] += 1
    if display_delta > 0:
        bucket["positive"] += 1


def _combine(*buckets: dict[str, Any]) -> dict[str, Any]:
    combined = _empty_bucket()
    for bucket in buckets:
        for key in ("events", "confirmed", "failed", "pending", "positive"):
            combined[key] = int(combined[key]) + int(bucket[key])
        for key in ("expected_net_usd", "realized_net_usd", "display_pnl_usd", "gas_cost_usd"):
            combined[key] = str(_as_decimal(combined[key]) + _as_decimal(bucket[key]))
    return combined


def pnl_summary(*, recent_limit: int = 50) -> dict[str, Any]:
    events = _read_events()
    reset_cutoff = {"dry_run": 0, "live": 0}
    for event in events:
        if event.get("type") == "RESET":
            mode = normalize_mode(str(event.get("mode", "")))
            reset_cutoff[mode] = max(reset_cutoff[mode], int(event.get("created_at_ns", 0) or 0))

    summary = {
        "dry_run": {"C1": _empty_bucket(), "C2": _empty_bucket(), "LIQUIDATION": _empty_bucket(), "combined": _empty_bucket()},
        "live": {"C1": _empty_bucket(), "C2": _empty_bucket(), "LIQUIDATION": _empty_bucket(), "combined": _empty_bucket()},
        "live_reset_policy": "explicit_user_reset_only",
        "live_reset_confirm": LIVE_RESET_CONFIRM,
        "updated_at_ns": _now_ns(),
        "recent": [],
        # New pipeline metrics for lifespan, stages, submissions
        "pipeline_metrics": {
            "staged_count": _pipeline_metrics["staged_count"],
            "executed_count": _pipeline_metrics["executed_count"],
            "expired_lifespan_count": _pipeline_metrics["expired_lifespan_count"],
            "successful_submissions": _pipeline_metrics["successful_submissions"],
            "successful_stagings": _pipeline_metrics["successful_stagings"],
            "lifespan_checks": _pipeline_metrics["lifespan_checks"],
            "n_plus_4_lifespan": 4,
        },
    }
    active_events: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "PNL":
            continue
        mode = normalize_mode(str(event.get("mode", "")))
        created = int(event.get("created_at_ns", 0) or 0)
        if created <= reset_cutoff[mode]:
            continue
        stage = str(event.get("stage", "")).upper()
        if stage not in {"C1", "C2", "LIQUIDATION"}:
            continue
        _add(summary[mode][stage], mode=mode, event=event)
        active_events.append(event)

    for mode in ("dry_run", "live"):
        summary[mode]["combined"] = _combine(summary[mode]["C1"], summary[mode]["C2"], summary[mode]["LIQUIDATION"])

    summary["recent"] = active_events[-max(1, recent_limit):]
    return summary


def _write_snapshot(snapshot: dict[str, Any]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="pnl_snapshot_", suffix=".json", dir=str(SNAPSHOT_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, sort_keys=True)
        os.replace(tmp_name, SNAPSHOT_PATH)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
    c = redis_client()
    if c is not None:
        try:
            c.set(REDIS_SNAPSHOT_KEY, json.dumps(snapshot, sort_keys=True))
        except Exception:
            pass


def current_snapshot() -> dict[str, Any]:
    snapshot = pnl_summary()
    _write_snapshot(snapshot)
    return snapshot
