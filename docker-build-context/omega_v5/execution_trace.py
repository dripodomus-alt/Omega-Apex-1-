#!/usr/bin/env python3
# ==============================================================================
# execution_trace.py -- hash-addressable C1/C2 execution trace ledger.
# ==============================================================================

from __future__ import annotations

import json
import os
import tempfile
import time
from decimal import Decimal
from typing import Any

from web3 import Web3

from .config import CHAIN_ID
from .paths import output_path


TRACE_LEDGER_PATH = output_path("execution_traces.jsonl")
TRACE_DIR = output_path("execution_traces")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "hex") and callable(value.hex):
        try:
            return value.hex()
        except Exception:
            pass
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_trace_hash(payload: dict[str, Any]) -> str:
    return Web3.keccak(text=canonical_json(payload)).hex()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + "_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(_json_safe(payload), fh, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def record_execution_trace(
    *,
    stage: str,
    status: str,
    mode: str,
    opp_id: str = "",
    c1_id: str = "",
    c2_id: str = "",
    route: list[str] | None = None,
    pool_sequence: list[str] | None = None,
    pool_addresses: list[str] | None = None,
    parent_trace_hash: str = "",
    c1_tx_hash: str = "",
    c2_tx_hash: str = "",
    receipt: dict[str, Any] | None = None,
    envelope: dict[str, Any] | None = None,
    payload_hash: str = "",
    activation: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "chain_id": CHAIN_ID,
        "stage": stage.strip().upper(),
        "status": status.strip().upper(),
        "mode": mode,
        "opp_id": opp_id,
        "c1_id": c1_id,
        "c2_id": c2_id,
        "route": list(route or []),
        "pool_sequence": list(pool_sequence or []),
        "pool_addresses": list(pool_addresses or []),
        "parent_trace_hash": parent_trace_hash,
        "c1_tx_hash": c1_tx_hash,
        "c2_tx_hash": c2_tx_hash,
        "receipt": receipt or {},
        "envelope": envelope or {},
        "payload_hash": payload_hash,
        "activation": activation or {},
        "metadata": metadata or {},
    }
    trace_hash = compute_trace_hash(body)
    event = {
        "trace_hash": trace_hash,
        "created_at_ns": time.time_ns(),
        **body,
    }
    TRACE_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_LEDGER_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_safe(event), sort_keys=True) + "\n")
    _atomic_write_json(TRACE_DIR / f"{trace_hash}.json", event)
    return event


def _read_ledger() -> list[dict[str, Any]]:
    if not TRACE_LEDGER_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in TRACE_LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                events.append(item)
        except Exception:
            continue
    return events


def get_trace(trace_hash: str) -> dict[str, Any] | None:
    normalized = trace_hash.strip()
    candidates = [normalized]
    if normalized.startswith("0x"):
        candidates.append(normalized[2:])
    else:
        candidates.append("0x" + normalized)

    for candidate in dict.fromkeys(candidates):
        path = TRACE_DIR / f"{candidate}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else None
            except Exception:
                return None
    for event in reversed(_read_ledger()):
        if str(event.get("trace_hash", "")).lower() in {c.lower() for c in candidates}:
            return event
    return None


def recent_traces(limit: int = 50, *, stage: str = "") -> list[dict[str, Any]]:
    events = _read_ledger()
    if stage:
        wanted = stage.strip().upper()
        events = [event for event in events if str(event.get("stage", "")).upper() == wanted]
    return events[-max(1, int(limit)):]
