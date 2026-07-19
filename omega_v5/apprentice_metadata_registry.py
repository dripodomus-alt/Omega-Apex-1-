#!/usr/bin/env python3
# ==============================================================================
# apprentice_metadata_registry.py -- staged metadata proposals and promotion gate.
# ==============================================================================

from __future__ import annotations

import json
import time
from typing import Any

from web3 import Web3

from . import rpc_layer
from .paths import cache_path, output_path


PROPOSALS_PATH = cache_path("apprentice_metadata_proposals.json")
APPROVED_PATH = cache_path("apprentice_metadata_approved.json")
REJECTED_PATH = cache_path("apprentice_metadata_rejected.json")
REVIEW_REPORT_PATH = output_path("apprentice_metadata_promotion_review_latest.json")
REASONING_REPORT_PATH = output_path("apprentice_metadata_promotion_reasoning_latest.md")


def _load_rows(path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _write_rows(path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated_at": int(time.time()), "rows": rows}, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _proposal_key(row: dict[str, Any]) -> tuple[str, str]:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    return (
        str(candidate.get("symbol") or row.get("symbol") or "").upper(),
        str(candidate.get("address") or row.get("address") or "").lower(),
    )


def write_missing_metadata_proposal(
    *,
    case: dict[str, Any],
    runner: str,
    candidate: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    row = {
        "written_at": int(time.time()),
        "case": case,
        "runner": runner,
        "candidate": candidate,
        "validation": validation,
        "status": "pending_review",
        "registry_policy": "apprentice proposal only; discovery promotion review required",
    }
    rows = _load_rows(PROPOSALS_PATH)
    rows_by_key = {_proposal_key(existing): existing for existing in rows if _proposal_key(existing) != ("", "")}
    key = _proposal_key(row)
    if key == ("", ""):
        row["status"] = "rejected_before_registry"
        row["reject_reasons"] = ["missing_symbol_and_address"]
        return row
    rows_by_key[key] = row
    _write_rows(PROPOSALS_PATH, list(rows_by_key.values()))
    return row


def _next_actions(reasons: list[str]) -> list[str]:
    actions: list[str] = []
    if "validation_not_promotable" in reasons:
        actions.append("rerun apprentice validation after missing fields are resolved")
    if "missing_symbol" in reasons:
        actions.append("resolve token symbol from runtime registry, verified token list, or on-chain ERC20 symbol")
    if "invalid_address" in reasons:
        actions.append("find a valid Polygon contract address before another promotion attempt")
    if "missing_decimals" in reasons or "decimals_out_of_range" in reasons:
        actions.append("read ERC20 decimals on-chain or from a verified protocol/token registry")
    if "missing_evidence_urls" in reasons:
        actions.append("attach evidence URLs from protocol docs, token list, explorer, or market metadata source")
    if "onchain_metadata_not_verified" in reasons:
        actions.append("connect RPC and verify bytecode, symbol, name, and decimals on-chain")
    if any(reason.startswith("address_conflicts_existing_symbol") for reason in reasons):
        actions.append("resolve the address-to-symbol conflict before promotion")
    if "symbol_conflicts_existing_address" in reasons:
        actions.append("resolve the symbol-to-address conflict before promotion")
    return actions or ["no action required; approved for registry promotion"]


def _decision_reasoning(reviewed: dict[str, Any]) -> dict[str, Any]:
    candidate = reviewed.get("candidate") if isinstance(reviewed.get("candidate"), dict) else {}
    validation = reviewed.get("validation") if isinstance(reviewed.get("validation"), dict) else {}
    onchain = validation.get("onchain") if isinstance(validation.get("onchain"), dict) else {}
    reasons = [str(reason) for reason in reviewed.get("promotion_reasons") or []]
    status = str(reviewed.get("promotion_status") or "rejected")
    approved = status == "approved"
    gate_results = [
        {
            "gate": "candidate_validation_promotable",
            "passed": "validation_not_promotable" not in reasons,
            "detail": f"validation_status={validation.get('status', 'missing')}",
        },
        {
            "gate": "symbol_present",
            "passed": "missing_symbol" not in reasons,
            "detail": f"symbol={candidate.get('symbol') or validation.get('symbol') or ''}",
        },
        {
            "gate": "polygon_address_valid",
            "passed": "invalid_address" not in reasons,
            "detail": f"address={candidate.get('address') or validation.get('address') or ''}",
        },
        {
            "gate": "decimals_verified",
            "passed": "missing_decimals" not in reasons and "decimals_out_of_range" not in reasons,
            "detail": f"decimals={validation.get('decimals')}",
        },
        {
            "gate": "evidence_present",
            "passed": "missing_evidence_urls" not in reasons,
            "detail": f"evidence_count={len(candidate.get('evidence_urls') or validation.get('evidence_urls') or [])}",
        },
        {
            "gate": "onchain_metadata_verified",
            "passed": "onchain_metadata_not_verified" not in reasons,
            "detail": f"onchain_status={onchain.get('status', 'missing')}",
        },
        {
            "gate": "no_registry_conflict",
            "passed": not any(reason.startswith("address_conflicts_existing_symbol") for reason in reasons)
            and "symbol_conflicts_existing_address" not in reasons,
            "detail": "checked address-to-symbol and symbol-to-address maps",
        },
    ]
    if approved:
        summary = (
            "Approved because all promotion gates passed: candidate validation was promotable, "
            "metadata was present, on-chain ERC20 metadata was verified, evidence was attached, "
            "and no registry conflict was detected."
        )
    else:
        summary = "Rejected because promotion gates failed: " + ", ".join(reasons)
    return {
        "decision": status,
        "summary": summary,
        "gate_results": gate_results,
        "blocking_reasons": reasons,
        "next_actions": _next_actions(reasons),
    }


def _review_row(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    onchain = validation.get("onchain") if isinstance(validation.get("onchain"), dict) else {}
    symbol = str(candidate.get("symbol") or validation.get("symbol") or "").strip()
    address = str(candidate.get("address") or validation.get("address") or "").strip()
    name = str(candidate.get("name") or onchain.get("name") or "").strip()
    evidence_urls = candidate.get("evidence_urls") or validation.get("evidence_urls") or []
    if not isinstance(evidence_urls, list):
        evidence_urls = []
    reasons: list[str] = []
    if validation.get("status") != "promotable":
        reasons.append("validation_not_promotable")
    if not symbol:
        reasons.append("missing_symbol")
    if not Web3.is_address(address):
        reasons.append("invalid_address")
    decimals = validation.get("decimals")
    try:
        decimals_int = int(decimals)
        if decimals_int < 0 or decimals_int > 36:
            reasons.append("decimals_out_of_range")
    except Exception:
        decimals_int = None
        reasons.append("missing_decimals")
    if not evidence_urls:
        reasons.append("missing_evidence_urls")
    if onchain.get("status") != "pass":
        reasons.append("onchain_metadata_not_verified")
    if Web3.is_address(address):
        existing = rpc_layer.ADDRESS_TO_SYMBOL.get(address.lower())
        if existing and existing != symbol:
            reasons.append(f"address_conflicts_existing_symbol:{existing}")
    if symbol in rpc_layer.TOKEN_ADDRESSES and rpc_layer.TOKEN_ADDRESSES[symbol].lower() != address.lower():
        reasons.append("symbol_conflicts_existing_address")

    reviewed = {
        **row,
        "reviewed_at": int(time.time()),
        "promotion_status": "approved" if not reasons else "rejected",
        "promotion_reasons": reasons,
        "approved_metadata": {
            "symbol": symbol,
            "name": name,
            "address": Web3.to_checksum_address(address) if Web3.is_address(address) else address,
            "decimals": decimals_int,
            "evidence_urls": evidence_urls,
            "source_runner": row.get("runner", ""),
        },
    }
    reviewed["decision_reasoning"] = _decision_reasoning(reviewed)
    return reviewed


def _write_reasoning_report(report: dict[str, Any]) -> None:
    lines = [
        "# Apprentice Metadata Promotion Reasoning",
        "",
        f"- mode: {report.get('mode')}",
        f"- proposals: {report.get('proposal_count')}",
        f"- approved: {report.get('approved_count')}",
        f"- rejected: {report.get('rejected_count')}",
        f"- applied: {report.get('applied_count')}",
        f"- apply: {report.get('apply')}",
        "",
        "## Policy",
        "",
    ]
    for key, value in (report.get("policy") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Decisions", ""])
    rows = list(report.get("approved") or []) + list(report.get("rejected") or [])
    if not rows:
        lines.append("No proposals were available for review.")
    for index, row in enumerate(rows, start=1):
        meta = row.get("approved_metadata") if isinstance(row.get("approved_metadata"), dict) else {}
        reasoning = row.get("decision_reasoning") if isinstance(row.get("decision_reasoning"), dict) else {}
        evidence = meta.get("evidence_urls") or []
        lines.extend([
            f"### {index}. {meta.get('symbol') or '-'}",
            "",
            f"- decision: {reasoning.get('decision') or row.get('promotion_status')}",
            f"- source_runner: {meta.get('source_runner') or row.get('runner') or '-'}",
            f"- address: {meta.get('address') or '-'}",
            f"- decimals: {meta.get('decimals')}",
            f"- summary: {reasoning.get('summary') or '-'}",
            f"- blocking_reasons: {', '.join(reasoning.get('blocking_reasons') or []) or 'none'}",
            f"- next_actions: {'; '.join(reasoning.get('next_actions') or []) or 'none'}",
            f"- evidence_urls: {', '.join(str(url) for url in evidence) or 'none'}",
            "",
            "Gate results:",
            "",
        ])
        for gate in reasoning.get("gate_results") or []:
            mark = "pass" if gate.get("passed") else "fail"
            lines.append(f"- {gate.get('gate')}: {mark} ({gate.get('detail')})")
        lines.append("")
    REASONING_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REASONING_REPORT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def review_apprentice_metadata_promotions(
    *,
    apply: bool = False,
    max_promotions: int = 0,
) -> dict[str, Any]:
    proposals = _load_rows(PROPOSALS_PATH)
    reviewed = [_review_row(row) for row in proposals]
    approved = [row for row in reviewed if row["promotion_status"] == "approved"]
    rejected = [row for row in reviewed if row["promotion_status"] == "rejected"]
    selected = approved if max_promotions <= 0 else approved[:max_promotions]

    applied: list[dict[str, Any]] = []
    if apply:
        for row in selected:
            meta = row["approved_metadata"]
            symbol = str(meta["symbol"])
            address = str(meta["address"])
            decimals = int(meta["decimals"])
            rpc_layer.TOKEN_ADDRESSES[symbol] = address
            rpc_layer.TOKEN_DECIMALS[symbol] = decimals
            rpc_layer.TOKEN_DISCOVERY_STATUS[symbol] = "APPRENTICE_METADATA_PROMOTED_REVIEWED"
            rpc_layer.ADDRESS_TO_SYMBOL[address.lower()] = symbol
            applied.append(meta)

    _write_rows(APPROVED_PATH, approved)
    _write_rows(REJECTED_PATH, rejected)
    report = {
        "ok": True,
        "mode": "apprentice_metadata_promotion_review",
        "proposal_count": len(proposals),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "applied_count": len(applied),
        "apply": apply,
        "reasoning_report_path": str(REASONING_REPORT_PATH),
        "applied": applied,
        "approved": approved,
        "rejected": rejected,
        "policy": {
            "apprentices_write_proposals": True,
            "discovery_approves_or_rejects": True,
            "requires_onchain_metadata_pass": True,
            "requires_evidence_urls": True,
            "requires_no_symbol_or_address_conflict": True,
        },
    }
    REVIEW_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    _write_reasoning_report(report)
    return report
