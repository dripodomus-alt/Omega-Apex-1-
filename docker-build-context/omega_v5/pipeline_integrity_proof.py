#!/usr/bin/env python3
# ==============================================================================
# pipeline_integrity_proof.py -- proof artifact for repo data/math integrity.
# ==============================================================================

from __future__ import annotations

import argparse
import ast
import json
import time
from pathlib import Path
from typing import Any

from . import logic_data_audit
from .apex_live_design import live_design_status
from .paths import output_path, repo_path, resolve_repo_relative


PIPELINE_INTEGRITY_PROOF_PATH = output_path("pipeline_integrity_proof_latest.json")
CANONICAL_RUNTIME_PACKAGE = "omega_v5"
TARGET_OWNERSHIP_DOC = "docs/pipeline_ownership.md"
WEBHOOK_ADAPTER_MODULE = "omega_v5/webhook_dispatcher.py"
FORBIDDEN_WEBHOOK_RUNTIME_IMPORTS = ("aiohttp", "httpx")

STRICT_PIPELINE_ORDER = (
    "environment",
    "discovery",
    "math",
    "simulation",
    "transactions",
    "observability",
    "storage",
)

FORBIDDEN_PIPELINE_IMPORTS: dict[str, tuple[str, ...]] = {
    "discovery": ("simulation", "transactions"),
    "math": ("environment.rpc", "discovery.protocols", "simulation", "transactions"),
    "simulation": ("transactions.broadcast", "transactions.coordinator"),
    "transactions": ("discovery", "math.ranking", "math.sizing"),
}

INTEGRATION_SURFACES = (
    "contracts",
    "rust_engine",
    "vendor",
    "frontend_integration",
    "indexer",
    "infra",
    "scripts",
    "docs",
)


def _exists(rel: str) -> bool:
    return repo_path(rel).exists()


def _import_name_roots(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        if not node.module:
            return []
        return [node.module]
    return []


def _matches_forbidden_import(import_name: str, forbidden: str) -> bool:
    candidates = {import_name}
    if import_name.startswith("apex_omega."):
        candidates.add(import_name.removeprefix("apex_omega."))
    return any(candidate == forbidden or candidate.startswith(f"{forbidden}.") for candidate in candidates)


def _ownership_boundary_report() -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    scanned_files = 0
    present_owners: dict[str, bool] = {}

    for owner in STRICT_PIPELINE_ORDER:
        owner_root = repo_path(owner)
        present_owners[owner] = owner_root.exists()
        if not owner_root.exists():
            continue
        for path in owner_root.rglob("*.py"):
            scanned_files += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                violations.append(
                    {
                        "owner": owner,
                        "file": str(path.relative_to(repo_path())),
                        "forbidden_import": "parse_error",
                        "detail": str(exc),
                    }
                )
                continue
            forbidden_imports = FORBIDDEN_PIPELINE_IMPORTS.get(owner, ())
            for node in ast.walk(tree):
                for import_name in _import_name_roots(node):
                    for forbidden in forbidden_imports:
                        if _matches_forbidden_import(import_name, forbidden):
                            violations.append(
                                {
                                    "owner": owner,
                                    "file": str(path.relative_to(repo_path())),
                                    "forbidden_import": forbidden,
                                    "actual_import": import_name,
                                }
                            )

    return {
        "strict_order": list(STRICT_PIPELINE_ORDER),
        "present_owners": present_owners,
        "scanned_files": scanned_files,
        "forbidden_imports": {
            key: list(value) for key, value in FORBIDDEN_PIPELINE_IMPORTS.items()
        },
        "violations": violations,
        "ok": not violations,
        "compatibility_runtime": CANONICAL_RUNTIME_PACKAGE,
    }


def _package_imports(package_name: str, import_prefix: str) -> bool:
    package_root = repo_path(package_name)
    if not package_root.exists():
        return False
    for path in package_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            for import_name in _import_name_roots(node):
                if import_name == import_prefix or import_name.startswith(f"{import_prefix}."):
                    return True
    return False


def _single_architecture_report(design: dict[str, Any]) -> dict[str, Any]:
    repo_root = repo_path()
    extension_packages = sorted(
        path.name
        for path in repo_root.iterdir()
        if path.is_dir() and path.name.startswith("omega_v") and path.name != CANONICAL_RUNTIME_PACKAGE
    )
    extension_status = [
        {
            "package": package,
            "imports_canonical_runtime": _package_imports(package, CANONICAL_RUNTIME_PACKAGE),
            "allowed_role": "extension_only",
        }
        for package in extension_packages
    ]
    design_policy = design.get("integration_policy", {})
    purge_status = design.get("purge_status", {})
    archive_safe = (
        design_policy.get("archive_code_executed") is False
        and design_policy.get("mock_data_imported") is False
        and purge_status.get("runtime_imports_archive_code") is False
    )
    extension_safe = all(row["imports_canonical_runtime"] for row in extension_status)

    return {
        "canonical_runtime_package": CANONICAL_RUNTIME_PACKAGE,
        "target_ownership_doc": TARGET_OWNERSHIP_DOC,
        "single_runtime_architecture": True,
        "runtime_source_of_truth": design_policy.get("runtime_source_of_truth"),
        "integration_surfaces": {name: repo_path(name).exists() for name in INTEGRATION_SURFACES},
        "extension_packages": extension_status,
        "archive_design_only": archive_safe,
        "extension_packages_depend_inward": extension_safe,
        "ok": archive_safe and extension_safe and _exists(TARGET_OWNERSHIP_DOC),
    }



def _webhook_adapter_report() -> dict[str, Any]:
    path = repo_path(WEBHOOK_ADAPTER_MODULE)
    imports: list[str] = []
    if path.exists():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imports.extend(_import_name_roots(node))
        except SyntaxError as exc:
            return {
                "module": WEBHOOK_ADAPTER_MODULE,
                "present": True,
                "ok": False,
                "role": "observability_adapter",
                "forbidden_imports": list(FORBIDDEN_WEBHOOK_RUNTIME_IMPORTS),
                "violations": [f"parse_error:{exc}"],
            }
    violations = [
        name
        for name in imports
        if any(name == forbidden or name.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_WEBHOOK_RUNTIME_IMPORTS)
    ]
    return {
        "module": WEBHOOK_ADAPTER_MODULE,
        "present": path.exists(),
        "ok": path.exists() and not violations,
        "role": "observability_adapter",
        "authority": "emit_events_only_no_profit_simulation_or_broadcast_decisions",
        "forbidden_imports": list(FORBIDDEN_WEBHOOK_RUNTIME_IMPORTS),
        "violations": violations,
    }
def build_integrity_proof(
    roots: list[str] | None = None,
    *,
    audit_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audit = audit_report or logic_data_audit.audit_paths(roots or ["omega_v5", "scripts"])
    design = live_design_status()
    ownership = _ownership_boundary_report()
    single_architecture = _single_architecture_report(design)
    webhook = _webhook_adapter_report()
    required_runtime_modules = [
        "omega_v5/accounting.py",
        "omega_v5/token_calibration.py",
        "omega_v5/stable_swap_pricer.py",
        "omega_v5/route_execution_stager.py",
        "omega_v5/execution_truth.py",
        "omega_v5/wallet_config_verification.py",
        "omega_v5/pipeline_validation.py",
        WEBHOOK_ADAPTER_MODULE,
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
    for violation in ownership["violations"]:
        blockers.append(
            {
                "severity": "critical",
                "component": "strict_pipeline_ownership",
                "detail": (
                    f"{violation['file']} imports {violation.get('actual_import', '')}; "
                    f"forbidden for {violation['owner']}: {violation['forbidden_import']}"
                ),
            }
        )
    if not single_architecture["ok"]:
        blockers.append(
            {
                "severity": "critical",
                "component": "single_architecture",
                "detail": "Canonical runtime architecture policy failed",
            }
        )
    if not webhook["ok"]:
        blockers.append(
            {
                "severity": "critical",
                "component": "webhook_adapter",
                "detail": "Webhook adapter must stay dependency-light and observability-only",
            }
        )

    report = {
        "ok": not blockers,
        "schema_version": "omega_v5.pipeline_integrity_proof.v1",
        "generated_at": int(time.time()),
        "blockers": blockers,
        "logic_data_audit_summary": audit["summary"],
        "logic_data_audit_report": str(logic_data_audit.LOGIC_DATA_AUDIT_REPORT_PATH),
        "required_runtime_modules": module_status,
        "single_architecture_policy": single_architecture,
        "webhook_adapter_policy": webhook,
        "strict_pipeline_ownership": ownership,
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

