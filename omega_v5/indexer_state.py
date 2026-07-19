#!/usr/bin/env python3
# ==============================================================================
# indexer_state.py -- Optional local pool-state bridge for Polygon Chain Indexer.
#
# The indexer is a discovery accelerator, not an execution oracle. Rows are
# accepted only when recent enough, and exact-call/fork gates still decide
# payload eligibility before live execution.
# ==============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import INDEXER_SQLITE_PATH, INDEXER_STATE_MAX_AGE_BLOCKS
from .paths import resolve_repo_relative


SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_state (
    pool_address TEXT PRIMARY KEY,
    protocol TEXT NOT NULL,
    state_json TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pool_state_block ON pool_state(block_number);

CREATE TABLE IF NOT EXISTS pool_events (
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    block_number INTEGER NOT NULL,
    pool_address TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (tx_hash, log_index)
);

CREATE INDEX IF NOT EXISTS idx_pool_events_pool_block ON pool_events(pool_address, block_number);
"""


def _connect(path: str = INDEXER_SQLITE_PATH) -> sqlite3.Connection:
    db_path = resolve_repo_relative(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_indexer_db(path: str = INDEXER_SQLITE_PATH) -> None:
    with _connect(path) as conn:
        conn.executescript(SCHEMA)


def upsert_pool_state(
    pool_address: str,
    protocol: str,
    state: dict[str, Any],
    block_number: int,
    *,
    path: str = INDEXER_SQLITE_PATH,
) -> None:
    if not pool_address or not protocol or not isinstance(state, dict):
        raise ValueError("pool_address, protocol, and state are required")
    init_indexer_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT INTO pool_state(pool_address, protocol, state_json, block_number, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pool_address) DO UPDATE SET
                protocol = excluded.protocol,
                state_json = excluded.state_json,
                block_number = excluded.block_number,
                updated_at = excluded.updated_at
            """,
            (
                pool_address.lower(),
                protocol,
                json.dumps(state, separators=(",", ":"), default=str),
                int(block_number),
                time.time(),
            ),
        )


def insert_pool_event(
    *,
    tx_hash: str,
    log_index: int,
    block_number: int,
    pool_address: str,
    event_type: str,
    event: dict[str, Any],
    path: str = INDEXER_SQLITE_PATH,
) -> None:
    init_indexer_db(path)
    with _connect(path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pool_events(
                tx_hash, log_index, block_number, pool_address, event_type, event_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx_hash,
                int(log_index),
                int(block_number),
                pool_address.lower(),
                event_type,
                json.dumps(event, separators=(",", ":"), default=str),
                time.time(),
            ),
        )


def get_indexed_pool_state(
    pool_address: str,
    *,
    current_block: int | None = None,
    max_age_blocks: int = INDEXER_STATE_MAX_AGE_BLOCKS,
    path: str = INDEXER_SQLITE_PATH,
) -> dict[str, Any] | None:
    if not pool_address:
        return None
    db_path = resolve_repo_relative(path)
    if not db_path.exists():
        return None
    try:
        with _connect(path) as conn:
            row = conn.execute(
                "SELECT * FROM pool_state WHERE pool_address = ?",
                (pool_address.lower(),),
            ).fetchone()
    except sqlite3.DatabaseError:
        return None
    if not row:
        return None
    block_number = int(row["block_number"])
    if current_block is not None and max_age_blocks >= 0:
        if int(current_block) - block_number > max_age_blocks:
            return None
    try:
        state = json.loads(row["state_json"])
    except json.JSONDecodeError:
        return None
    if not isinstance(state, dict):
        return None
    state.setdefault("_meta", {})
    state["_meta"].update({
        "state_source": "chain_indexer_sqlite",
        "indexer_block_number": block_number,
        "indexer_max_age_blocks": max_age_blocks,
    })
    return state


def indexer_status(path: str = INDEXER_SQLITE_PATH) -> dict[str, Any]:
    db_path = resolve_repo_relative(path)
    if not db_path.exists():
        return {"enabled": True, "present": False, "path": str(db_path)}
    try:
        with _connect(path) as conn:
            pool_count = conn.execute("SELECT COUNT(*) FROM pool_state").fetchone()[0]
            event_count = conn.execute("SELECT COUNT(*) FROM pool_events").fetchone()[0]
            latest_block = conn.execute("SELECT MAX(block_number) FROM pool_state").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        return {"enabled": True, "present": True, "healthy": False, "error": str(exc), "path": str(db_path)}
    return {
        "enabled": True,
        "present": True,
        "healthy": True,
        "path": str(db_path),
        "pool_state_rows": int(pool_count or 0),
        "pool_event_rows": int(event_count or 0),
        "latest_pool_state_block": int(latest_block or 0),
    }
