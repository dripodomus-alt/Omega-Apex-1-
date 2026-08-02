#!/usr/bin/env python3
# ==============================================================================
# runtime_control.py -- Redis-backed runtime mode/settings control plane.
# ==============================================================================

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any

from .config import CONFIRM_FLAG, EXEC_MODE, LIVE_FLAG, REDIS_KEY_PREFIX, REQUIRED_CONFIRM
from .paths import output_path
from .redis_cache import client as redis_client, key as redis_key


STATE_PATH = output_path("runtime_control.json")
REDIS_STATE_KEY = redis_key("runtime", "control")
FILE_WRITE_LOCK = threading.Lock()

VALID_MODES = {"dry_run", "live"}
VALID_EXECUTE_TOP = {1, 5, 10, 15}


def _now_ns() -> int:
    return time.time_ns()


def normalize_mode(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw in {"live", "production", "prod", "mainnet"}:
        return "live"
    if raw in {"dry", "dry_run", "simulation", "sim", "paper", "paper_trading"}:
        return "dry_run"
    return "dry_run"


def _env_default_mode() -> str:
    explicit = normalize_mode(os.environ.get("OMEGA_RUNTIME_MODE"))
    if os.environ.get("OMEGA_RUNTIME_MODE"):
        return explicit
    if EXEC_MODE == "live" and LIVE_FLAG == "1" and CONFIRM_FLAG == REQUIRED_CONFIRM:
        return "live"
    return "dry_run"


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except Exception:
        return default


def default_state() -> dict[str, Any]:
    execute_top = _int_env("OMEGA_ENGINE_EXECUTE_TOP", 5)
    if execute_top not in VALID_EXECUTE_TOP:
        execute_top = 5
    return {
        "mode": _env_default_mode(),
        "updated_at_ns": _now_ns(),
        "updated_by": "default",
        "settings": {
            "execute_top": execute_top,
            "print_top_routes": max(1, _int_env("OMEGA_ENGINE_PRINT_TOP_ROUTES", 50)),
            "ticks": max(0, _int_env("OMEGA_ENGINE_TICKS", 1)),
            "principal_usd": str(os.environ.get("OMEGA_ENGINE_PRINCIPAL_USD", "50000")),
            "interval_seconds": max(5, _int_env("OMEGA_ENGINE_INTERVAL_SECONDS", 60)),
            "no_scan": os.environ.get("OMEGA_ENGINE_NO_SCAN", "true").strip().lower()
            in {"1", "true", "yes", "on"},
            "canary_mode": os.environ.get("OMEGA_ENGINE_CANARY_MODE", "false").strip().lower()
            in {"1", "true", "yes", "on"},
        },
        "live_reset_policy": "explicit_user_reset_only",
    }


def _read_file_state() -> dict[str, Any] | None:
    try:
        if not STATE_PATH.exists():
            return None
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_file_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="runtime_control_", suffix=".json", dir=str(STATE_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        with FILE_WRITE_LOCK:
            for attempt in range(5):
                try:
                    os.replace(tmp_name, STATE_PATH)
                    return
                except PermissionError:
                    time.sleep(0.05 * (attempt + 1))
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def _read_redis_state() -> dict[str, Any] | None:
    c = redis_client()
    if c is None:
        return None
    try:
        raw = c.get(REDIS_STATE_KEY)
        data = json.loads(raw) if raw else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_redis_state(state: dict[str, Any]) -> None:
    c = redis_client()
    if c is None:
        return
    try:
        c.set(REDIS_STATE_KEY, json.dumps(state, sort_keys=True))
    except Exception:
        return


def _validated(state: dict[str, Any]) -> dict[str, Any]:
    merged = default_state()
    merged.update({k: v for k, v in state.items() if k != "settings"})
    merged["mode"] = normalize_mode(str(merged.get("mode", "")))

    settings = dict(default_state()["settings"])
    raw_settings = state.get("settings")
    if isinstance(raw_settings, dict):
        settings.update(raw_settings)
    settings["execute_top"] = int(settings.get("execute_top", 5))
    if settings["execute_top"] not in VALID_EXECUTE_TOP:
        settings["execute_top"] = 5
    settings["print_top_routes"] = max(1, int(settings.get("print_top_routes", 50)))
    settings["ticks"] = max(0, int(settings.get("ticks", 1)))
    settings["interval_seconds"] = max(5, int(settings.get("interval_seconds", 60)))
    settings["principal_usd"] = str(settings.get("principal_usd", "50000"))
    raw_no_scan = settings.get("no_scan", True)
    if isinstance(raw_no_scan, str):
        settings["no_scan"] = raw_no_scan.strip().lower() in {"1", "true", "yes", "on"}
    else:
        settings["no_scan"] = bool(raw_no_scan)
    raw_canary = settings.get("canary_mode", False)
    if isinstance(raw_canary, str):
        settings["canary_mode"] = raw_canary.strip().lower() in {"1", "true", "yes", "on"}
    else:
        settings["canary_mode"] = bool(raw_canary)
    merged["settings"] = settings
    merged["live_reset_policy"] = "explicit_user_reset_only"
    return merged


def get_runtime_state() -> dict[str, Any]:
    """
    Gets the current runtime state with a Redis-first strategy.

    This is a read-only operation. It reads from Redis if available, otherwise
    falls back to the local file, and finally to environment defaults. It does
    not write or sync state back to the stores.
    """
    state = _read_redis_state()
    if state is None:
        state = _read_file_state()

    if state is None:
        state = default_state()

    return _validated(state)


def set_runtime_mode(mode: str, *, actor: str = "api") -> dict[str, Any]:
    """Sets the runtime mode and persists it to both Redis and the file cache."""
    normalized = normalize_mode(mode)
    if normalized not in VALID_MODES:
        raise ValueError(f"unsupported runtime mode: {mode}")
    state = get_runtime_state()
    state["mode"] = normalized
    state["updated_at_ns"] = _now_ns()
    state["updated_by"] = actor or "api"
    if normalized == "live":
        state["live_armed_at_ns"] = state["updated_at_ns"]
    else:
        state["dry_run_armed_at_ns"] = state["updated_at_ns"]
    _write_file_state(state)
    _write_redis_state(state)
    return state


def update_runtime_settings(settings: dict[str, Any], *, actor: str = "api") -> dict[str, Any]:
    """Updates runtime settings and persists them to both Redis and the file cache."""
    state = get_runtime_state()
    current = dict(state.get("settings", {}))
    allowed = {
        "execute_top",
        "print_top_routes",
        "ticks",
        "principal_usd",
        "interval_seconds",
        "no_scan",
        "canary_mode",
    }
    for key, value in settings.items():
        if key in allowed:
            current[key] = value
    state["settings"] = _validated({"settings": current})["settings"]
    state["updated_at_ns"] = _now_ns()
    state["updated_by"] = actor or "api"
    _write_file_state(state)
    _write_redis_state(state)
    return state


def runtime_mode() -> str:
    return str(get_runtime_state().get("mode", "dry_run"))


def runtime_settings() -> dict[str, Any]:
    return dict(get_runtime_state().get("settings", {}))
