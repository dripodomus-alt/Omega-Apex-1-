#!/usr/bin/env python3
# ==============================================================================
# mainnet_finalizer.py -- consolidated APEX-OMEGA mainnet readiness verdict.
#
# This module turns the finalizer doctrine into repo-native status output. It
# does not sign, broadcast, or mutate runtime state; it consolidates the live
# safety surfaces that already exist in the backend.
# ==============================================================================

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .apex_live_design import live_design_status
from .config import CHAIN_ID, HTTP_URL
from .execution import execution_guard_status
from .paths import output_path
from .ml_alpha import ml_alpha_plan, ml_alpha_status
from .pnl_tracker import current_snapshot
from .redis_cache import status as redis_status
from .runtime_alignment import load_latest_alignment
from .runtime_control import get_runtime_state
from .session_proof import load_latest_proof


FINALIZER_REPORT_PATH = output_path("mainnet_finalizer_latest.json")
PIPELINE_VALIDATION_REPORT_PATH = output_path("pipeline_validation_latest.json")
PIPELINE_INTEGRITY_PROOF_PATH = output_path("pipeline_integrity_proof_latest.json")


def _load_live_pool_scan() -> dict[str, Any]:
    path = output_path("live_pool_scan_report.json")
    if not path.exists():
        return {"ok": False, "detail": "live_pool_scan_report_missing"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _load_pipeline_validation() -> dict[str, Any]:
    if not PIPELINE_VALIDATION_REPORT_PATH.exists():
        return {"ok": False, "detail": "pipeline_validation_report_missing"}
    try:
        return json.loads(PIPELINE_VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _load_pipeline_integrity_proof() -> dict[str, Any]:
    if not PIPELINE_INTEGRITY_PROOF_PATH.exists():
        return {"ok": False, "detail": "pipeline_integrity_proof_missing"}
    try:
        return json.loads(PIPELINE_INTEGRITY_PROOF_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def _verdict(
    *,
    guards: dict[str, bool],
    alignment: dict[str, Any],
    pool_scan: dict[str, Any],
    pipeline_validation: dict[str, Any],
    integrity_proof: dict[str, Any],
) -> str:
    if not pool_scan.get("ok"):
        return "BUILDABLE_WITH_BLOCKERS"
    if alignment.get("status") not in {"PASS", "pass", "ok", "OK"}:
        return "SHADOW_READY"
    truth = pipeline_validation.get("executor_truth", {}) if isinstance(pipeline_validation, dict) else {}
    if int(truth.get("executable") or 0) <= 0 or not pipeline_validation.get("payload_execution_eligible"):
        return "SHADOW_READY"
    if not all(guards.values()):
        return "SHADOW_READY"
    if not integrity_proof.get("ok"):
        return "SHADOW_READY"
    return "CANARY_READY"


def finalizer_report(*, probe: bool = False) -> dict[str, Any]:
    redis_ok, redis_detail = redis_status()
    runtime = get_runtime_state()
    guards = execution_guard_status(probe=probe)
    alignment = load_latest_alignment()
    session_proof = load_latest_proof()
    pool_scan = _load_live_pool_scan()
    pipeline_validation = _load_pipeline_validation()
    integrity_proof = _load_pipeline_integrity_proof()
    design = live_design_status()
    ml_status = ml_alpha_status()
    pnl = current_snapshot()
    verdict = _verdict(
        guards=guards,
        alignment=alignment,
        pool_scan=pool_scan,
        pipeline_validation=pipeline_validation,
        integrity_proof=integrity_proof,
    )

    blockers: list[dict[str, str]] = []
    if not redis_ok:
        blockers.append({"severity": "high", "component": "redis", "detail": redis_detail})
    for name, ok in guards.items():
        if not ok:
            blockers.append({"severity": "critical", "component": "execution_guard", "detail": name})
    if not pool_scan.get("ok"):
        blockers.append({"severity": "high", "component": "pool_scan", "detail": str(pool_scan.get("detail") or pool_scan.get("failures") or "not ok")})
    if alignment.get("status") not in {"PASS", "pass", "ok", "OK"}:
        blockers.append({"severity": "medium", "component": "runtime_alignment", "detail": str(alignment.get("status", "missing"))})
    truth = pipeline_validation.get("executor_truth", {}) if isinstance(pipeline_validation, dict) else {}
    if not pipeline_validation.get("ok"):
        blockers.append({"severity": "high", "component": "pipeline_validation", "detail": str(pipeline_validation.get("detail") or pipeline_validation.get("failures") or "not ok")})
    if int(truth.get("executable") or 0) <= 0:
        blockers.append({
            "severity": "critical",
            "component": "executor_truth",
            "detail": "no exact-call executable route in latest validation",
        })
    if not pipeline_validation.get("payload_execution_eligible"):
        blockers.append({
            "severity": "critical",
            "component": "payload_execution",
            "detail": str(pipeline_validation.get("exact_call_gate") or "not eligible"),
        })
    if not integrity_proof.get("ok"):
        blockers.append({"severity": "high", "component": "pipeline_integrity", "detail": str(integrity_proof.get("blockers") or "not ok")})
    runtime_settings = runtime.get("settings", {}) if isinstance(runtime.get("settings"), dict) else {}
    if runtime_settings.get("canary_mode") is not True:
        blockers.append({
            "severity": "medium",
            "component": "canary_runtime",
            "detail": "canary_mode is not enabled; live canary must use effective execution cap=1",
        })

    report = {
        "ok": verdict in {"CANARY_READY", "CONTROLLED_LIVE_READY", "PRODUCTION_MAINNET_READY"},
        "verdict": verdict,
        "chain_id": CHAIN_ID,
        "timestamp": int(time.time()),
        "repository_state_assessment": {
            "runtime_mode": runtime.get("mode"),
            "backend_rpc": HTTP_URL,
            "redis_ok": redis_ok,
            "redis_detail": redis_detail,
            "transport_lanes": design.get("transport_lanes", {}),
            "archive_code_executed": design.get("integration_policy", {}).get("archive_code_executed") is True,
            "mock_data_imported": design.get("integration_policy", {}).get("mock_data_imported") is True,
        },
        "mainnet_blocker_register": blockers,
        "exact_patch_plan": [
            "Keep final route ranking exact-call-backed.",
            "Quarantine duplicate AdapterBadRoute signatures inside executor truth scans.",
            "Use size ladders to search executable depth without bypassing profit/slippage floors.",
            "Expose finalizer verdict to frontend through backend API only.",
            "Add fail-closed ML alpha lanes for route ranking, slippage sizing, and gas/MEV timing.",
        ],
        "completed_code_changes": [
            "executor truth route semantic signatures",
            "expanded exact-call size ladders",
            "global exact-call budget and duplicate bad-route skip",
            "pipeline and main CLI executor-truth diagnostics",
            "backend mainnet finalizer report",
            "fail-closed ML alpha readiness contract",
        ],
        "test_and_simulation_evidence": {
            "runtime_alignment": alignment,
            "session_signer": session_proof,
            "latest_pool_scan": pool_scan,
            "latest_pipeline_validation": pipeline_validation,
            "latest_pipeline_integrity_proof": integrity_proof,
            "ml_alpha": ml_status,
            "pnl": pnl,
        },
        "ml_enhancement_plan": ml_alpha_plan(),
        "deployment_manifest": {
            "pm2_apps": ["omega-redis", "omega-anvil-fork", "omega-dodo-rpc-provider", "omega-api", "omega-engine"],
            "api_endpoint": "/api/finalizer/report",
            "frontend_manager": "frontend_integration/ExecutionManager.ts",
        },
        "shadow_run_report": {
            "authority": "read_only_backend_status",
            "pool_scan_loaded": bool(pool_scan.get("ok")),
            "pipeline_validation_loaded": bool(pipeline_validation.get("ok")),
            "executor_truth_executable": int(truth.get("executable") or 0),
            "payload_execution_eligible": bool(pipeline_validation.get("payload_execution_eligible")),
            "canary_effective_cap": runtime_settings.get("execute_top") if not runtime_settings.get("canary_mode") else 1,
            "exact_call_required_for_execution": True,
        },
        "controlled_live_release_decision": {
            "can_frontend_broadcast": False,
            "can_backend_broadcast": verdict in {"CANARY_READY", "CONTROLLED_LIVE_READY", "PRODUCTION_MAINNET_READY"},
            "requires_exact_call_pass": True,
            "requires_execution_guards": True,
        },
        "unresolved_risk_register": [
            item for item in blockers if item["severity"] in {"critical", "high"}
        ],
    }
    FINALIZER_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINALIZER_REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return report


def main() -> int:
    report = finalizer_report(probe=False)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
