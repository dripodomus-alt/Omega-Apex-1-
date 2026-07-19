#!/usr/bin/env python3
# ==============================================================================
# pipeline_integrity_proof.py -- proof artifact for repo data/math integrity.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from . import logic_data_audit
from .apex_live_design import live_design_status
from .paths import output_path, repo_path, resolve_repo_relative


PIPELINE_INTEGRITY_PROOF_PATH = output_path("pipeline_integrity_proof_latest.json")


def _exists(rel: str) -> bool:
    return repo_path(rel).exists()


def build_integrity_proof(
    roots: list[str] | None = None,
    *,
    audit_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = audit_report or logic_data_audit.audit_paths(roots or ["omega_v5", "scripts"])
    design = live_design_status()
    required_runtime_modules = [
        "omega_v5/accounting.py",
        "omega_v5/token_calibration.py",
        "omega_v5/stable_swap_pricer.py",
        "omega_v5/route_execution_stager.py",
        "omega_v5/execution_truth.py",
        "omega_v5/wallet_config_verification.py",
        "omega_v5/pipeline_validation.py",
    ]
    module_status = {rel: _exists(rel) for rel in required_runtime_modules}
    blockers: list[dict[str, str]] = []
    if audit["summary"]["parse_errors"]:
        blockers.append(
            {
                "severity": "critical",
                "component": "logic_data_audit",
                "detail": f"{audit['summary']['parse_errors']} Python parse error(s)",
            }
        )
    for rel, present in module_status.items():
        if not present:
            blockers.append({"severity": "critical", "component": "required_module", "detail": rel})

    report = {
        "ok": not blockers,
        "schema_version": "omega_v5.pipeline_integrity_proof.v1",
        "generated_at": int(time.time()),
        "blockers": blockers,
        "logic_data_audit_summary": audit["summary"],
        "logic_data_audit_report": str(logic_data_audit.LOGIC_DATA_AUDIT_REPORT_PATH),
        "required_runtime_modules": module_status,
        "critical_debugging_areas": logic_data_audit.CRITICAL_DEBUGGING_AREAS,
        "canonical_route_math": logic_data_audit.CANONICAL_ROUTE_MATH,
        "design_policy": {
            "archive_code_executed": design.get("integration_policy", {}).get("archive_code_executed"),
            "mock_data_imported": design.get("integration_policy", {}).get("mock_data_imported"),
            "runtime_source_of_truth": design.get("integration_policy", {}).get("runtime_source_of_truth"),
            "rejected_archive_surface_count": len(design.get("rejected_archive_surfaces", [])),
        },
        "audit_extracts": {
            "high_risk_mutation_points": audit["high_risk_mutation_points"][:100],
            "top_category_counts": audit["category_counts"],
        },
    }
    return report


def write_report(report: dict[str, Any], path: Path | None = None) -> Path:
    target = path or PIPELINE_INTEGRITY_PROOF_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate pipeline data/math integrity proof.")
    parser.add_argument("--root", action="append", default=None, help="Repo-relative file or directory to scan. Repeatable.")
    parser.add_argument("--out", default=str(PIPELINE_INTEGRITY_PROOF_PATH), help="Output JSON report path.")
    args = parser.parse_args(argv)
    audit_report = logic_data_audit.audit_paths(args.root or ["omega_v5", "scripts"])
    logic_data_audit.write_report(audit_report)
    integrity_report = build_integrity_proof(audit_report=audit_report)
    write_report(integrity_report, resolve_repo_relative(args.out))
    report = integrity_report
    summary = report["logic_data_audit_summary"]
    print(
        "pipeline_integrity_proof="
        f"{'PASS' if report['ok'] else 'FAIL'} "
        f"files={summary['files_scanned']} "
        f"imports={summary['external_import_points']} "
        f"returns={summary['return_points']} "
        f"mutations={summary['mutation_points']} "
        f"math={summary['math_sensitive_points']} "
        f"path={PIPELINE_INTEGRITY_PROOF_PATH}"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
