from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .paths import output_path

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"


@dataclass
class AuditPhase:
    name: str
    status: str
    findings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "findings": self.findings,
            "evidence": self.evidence,
        }


def _status_from_findings(failures: list[str], warnings: list[str]) -> str:
    if failures:
        return STATUS_FAIL
    if warnings:
        return STATUS_WARNING
    return STATUS_PASS


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _calldata_bytes(calldata: str) -> tuple[bytes, list[str]]:
    failures: list[str] = []
    if not isinstance(calldata, str) or not calldata.startswith("0x"):
        return b"", ["calldata_missing_0x_prefix"]
    body = calldata[2:]
    if len(body) % 2:
        return b"", ["calldata_odd_hex_length"]
    try:
        return bytes.fromhex(body), failures
    except ValueError:
        return b"", ["calldata_non_hex"]


def audit_abi_integrity(calldata: str, expected_selector: str | None = None) -> AuditPhase:
    data, failures = _calldata_bytes(calldata)
    warnings: list[str] = []
    evidence: dict[str, Any] = {"calldata_bytes": len(data), "expected_selector": expected_selector or ""}

    selector = ""
    words: list[str] = []
    if data:
        if len(data) < 4:
            failures.append("calldata_shorter_than_selector")
        else:
            selector = "0x" + data[:4].hex()
            payload = data[4:]
            if len(payload) % 32 != 0:
                warnings.append("payload_not_32_byte_aligned_dynamic_or_malformed")
            words = [payload[i:i + 32].hex() for i in range(0, len(payload), 32) if len(payload[i:i + 32]) == 32]
            if expected_selector and selector.lower() != expected_selector.lower():
                failures.append("selector_mismatch")
            round_trip = "0x" + data.hex()
            if round_trip.lower() != calldata.lower():
                failures.append("decoder_round_trip_mismatch")

    evidence.update({
        "selector": selector,
        "abi_words": len(words),
        "static_payload_bytes": len(data[4:]) if len(data) >= 4 else 0,
        "word_aligned": len(data) >= 4 and (len(data) - 4) % 32 == 0,
        "words_sha256": hashlib.sha256(("|".join(words)).encode()).hexdigest() if words else "",
    })
    return AuditPhase("ABI Integrity", _status_from_findings(failures, warnings), failures + warnings, evidence)


def _word_interpretations(raw: bytes) -> list[dict[str, Any]]:
    value = int.from_bytes(raw, "big")
    out = [{"type": "uint256", "value": str(value), "confidence": "medium"}]
    if value in (0, 1):
        out.append({"type": "bool", "value": bool(value), "confidence": "medium"})
    if raw[:12] == b"\x00" * 12 and value != 0:
        out.append({"type": "address", "value": "0x" + raw[12:].hex(), "confidence": "low"})
    out.append({"type": "bytes32", "value": "0x" + raw.hex(), "confidence": "low"})
    return out


def audit_semantic_decode(calldata: str) -> AuditPhase:
    data, failures = _calldata_bytes(calldata)
    decoded: list[dict[str, Any]] = []
    if not failures and len(data) >= 4:
        payload = data[4:]
        for idx in range(0, len(payload), 32):
            word = payload[idx:idx + 32]
            if len(word) != 32:
                continue
            decoded.append({
                "index": idx // 32,
                "raw_hex": "0x" + word.hex(),
                "decoded_integer": str(int.from_bytes(word, "big")),
                "possible_interpretations": _word_interpretations(word),
                "engineering_units": "unknown_without_abi_or_field_manifest",
            })
    status = STATUS_FAIL if failures else (STATUS_WARNING if decoded else STATUS_WARNING)
    findings = failures or (["no_abi_field_manifest_meanings_are_unknown"] if decoded else ["no_abi_words_to_decode"])
    return AuditPhase("Semantic Decode", status, findings, {"fields": decoded})


def audit_identity_parity(identity_sources: dict[str, Any] | None) -> AuditPhase:
    sources = identity_sources or {}
    failures: list[str] = []
    warnings: list[str] = []
    normalized: dict[str, str] = {}
    for name, value in sources.items():
        if value in (None, ""):
            warnings.append(f"identity_missing:{name}")
            continue
        normalized[name] = str(value).lower()
    unique = set(normalized.values())
    if len(unique) > 1:
        failures.append("identity_hash_mismatch")
    elif not normalized:
        warnings.append("no_identity_sources_provided")
    return AuditPhase("Opportunity Identity Parity", _status_from_findings(failures, warnings), failures + warnings, {"normalized_sources": normalized})


def audit_execution_parameters(parameters: dict[str, Any] | None) -> AuditPhase:
    params = parameters or {}
    known = {
        "loan_size", "principal_usd", "minimum_profit", "min_profit", "gas_limit",
        "gas_price", "builder_tip", "relay_payment", "deadline", "nonce",
        "route_id", "mode_flag", "boolean_flag",
    }
    classified: dict[str, dict[str, str]] = {}
    warnings: list[str] = []
    for key, value in params.items():
        dec = _decimal(value)
        label = key.lower()
        matches = [k for k in known if k in label]
        classified[key] = {
            "value": str(value),
            "numeric": str(dec) if dec is not None else "not_numeric",
            "classification": matches[0] if matches else "unknown",
            "confidence": "high" if matches else "low",
        }
        if not matches:
            warnings.append(f"unclassified_execution_parameter:{key}")
    if not params:
        warnings.append("no_execution_parameters_provided")
    return AuditPhase("Execution Parameter Validation", STATUS_WARNING if warnings else STATUS_PASS, warnings, {"parameters": classified})


def audit_economic_consistency(economic: dict[str, Any] | None) -> AuditPhase:
    econ = economic or {}
    failures: list[str] = []
    warnings: list[str] = []
    gross = _decimal(econ.get("gross_profit_usd", econ.get("gross_surplus_usd")))
    net = _decimal(econ.get("net_profit_usd"))
    cost_keys = [
        "gas_cost_usd", "flash_fee_usd", "flashloan_fee_usd", "builder_tip_usd",
        "relay_tip_usd", "builder_fee_usd", "risk_reserve_usd", "risk_buffer_usd",
        "approval_cost_usd", "protocol_fee_usd", "safety_reserve_usd",
    ]
    costs = {key: _decimal(econ.get(key, 0)) or Decimal("0") for key in cost_keys if key in econ}
    if gross is None or net is None:
        warnings.append("gross_or_net_profit_missing")
        expected_net = None
    else:
        expected_net = gross - sum(costs.values(), Decimal("0"))
        if expected_net != net:
            failures.append("net_profit_reconciliation_mismatch")
    if not costs:
        warnings.append("no_cost_components_provided")
    return AuditPhase(
        "Economic Consistency",
        _status_from_findings(failures, warnings),
        failures + warnings,
        {
            "gross_profit_usd": str(gross) if gross is not None else "missing",
            "costs_usd": {k: str(v) for k, v in costs.items()},
            "reported_net_profit_usd": str(net) if net is not None else "missing",
            "recomputed_net_profit_usd": str(expected_net) if expected_net is not None else "unknown",
        },
    )


def audit_reserve_state(reserve_state: dict[str, Any] | None) -> AuditPhase:
    state = reserve_state or {}
    warnings: list[str] = []
    failures: list[str] = []
    before = state.get("before") or []
    after = state.get("after") or []
    actual_input = _decimal(state.get("actual_input"))
    output = _decimal(state.get("output"))
    if not before or not after:
        warnings.append("reserve_before_after_missing")
    elif len(before) != len(after):
        failures.append("reserve_vector_length_mismatch")
    if actual_input is None:
        warnings.append("actual_input_missing")
    if output is None:
        warnings.append("output_missing")
    return AuditPhase("Reserve State Validation", _status_from_findings(failures, warnings), failures + warnings, {"state": state})


def audit_constant_product(reserve_state: dict[str, Any] | None, protocol: str = "") -> AuditPhase:
    state = reserve_state or {}
    protocol_upper = protocol.upper()
    if protocol_upper and not any(tag in protocol_upper for tag in ("V2", "CPMM", "UNISWAP", "SUSHI", "QUICK")):
        return AuditPhase("Constant Product Validation", STATUS_WARNING, ["non_cpmm_protocol_requires_family_specific_invariant"], {"protocol": protocol})
    before = [_decimal(x) for x in (state.get("before") or [])]
    after = [_decimal(x) for x in (state.get("after") or [])]
    warnings: list[str] = []
    failures: list[str] = []
    evidence: dict[str, Any] = {"protocol": protocol or "unknown"}
    if len(before) < 2 or len(after) < 2 or before[0] is None or before[1] is None or after[0] is None or after[1] is None:
        warnings.append("insufficient_cpmm_reserves")
    else:
        k_before = before[0] * before[1]
        k_after = after[0] * after[1]
        evidence.update({"k_before": str(k_before), "k_after": str(k_after)})
        if k_after < k_before:
            failures.append("constant_product_decreased")
    return AuditPhase("Constant Product Validation", _status_from_findings(failures, warnings), failures + warnings, evidence)


def audit_bps(economic: dict[str, Any] | None) -> AuditPhase:
    econ = economic or {}
    warnings: list[str] = []
    bps_keys = [k for k in econ if "bps" in k.lower()]
    for key in bps_keys:
        if not any(base in key.lower() for base in ("profit", "gross", "principal", "notional", "spread")):
            warnings.append(f"bps_base_ambiguous:{key}")
    if "slippage_cost_usd" in econ and "amount_out_after_slippage" in econ:
        warnings.append("possible_slippage_double_count_requires_trace")
    if not bps_keys:
        warnings.append("no_bps_fields_provided")
    return AuditPhase("Basis Point Audit", STATUS_WARNING if warnings else STATUS_PASS, warnings, {"bps_fields": bps_keys})


def audit_tstore(tstore_report: dict[str, Any] | None) -> AuditPhase:
    report = tstore_report or {}
    warnings: list[str] = []
    if not report:
        warnings.append("tstore_usage_not_reported")
    elif report.get("uses_eip_1153") is True and report.get("transaction_scoped") is not True:
        warnings.append("tstore_scope_not_proven")
    return AuditPhase("TSTORE Audit", STATUS_WARNING if warnings else STATUS_PASS, warnings, {"tstore_report": report})


def audit_relay(relay: dict[str, Any] | None) -> AuditPhase:
    data = relay or {}
    warnings: list[str] = []
    failures: list[str] = []
    tip = _decimal(data.get("relay_tip_usd"))
    bps = _decimal(data.get("relay_tip_bps"))
    base = _decimal(data.get("relay_tip_base_usd"))
    if tip is not None and bps is not None and base is not None:
        expected = base * bps / Decimal("10000")
        if expected != tip:
            failures.append("relay_tip_formula_mismatch")
    else:
        warnings.append("relay_tip_formula_incomplete")
    if data.get("relay_tip_bps_label") and "15% bps" in str(data.get("relay_tip_bps_label")).lower():
        failures.append("ambiguous_relay_tip_label")
    return AuditPhase("Relay Audit", _status_from_findings(failures, warnings), failures + warnings, {"relay": data})


def build_calldata_semantic_audit(
    *,
    calldata: str,
    expected_selector: str | None = None,
    identity_sources: dict[str, Any] | None = None,
    execution_parameters: dict[str, Any] | None = None,
    economic: dict[str, Any] | None = None,
    reserve_state: dict[str, Any] | None = None,
    protocol: str = "",
    tstore_report: dict[str, Any] | None = None,
    relay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    phases = [
        audit_abi_integrity(calldata, expected_selector),
        audit_semantic_decode(calldata),
        audit_identity_parity(identity_sources),
        audit_execution_parameters(execution_parameters),
        audit_economic_consistency(economic),
        audit_reserve_state(reserve_state),
        audit_constant_product(reserve_state, protocol),
        audit_bps(economic),
        audit_economic_consistency(economic),
        audit_tstore(tstore_report),
        audit_relay(relay),
    ]
    statuses = {phase.name: phase.status for phase in phases}
    hard_fail = any(phase.status == STATUS_FAIL for phase in phases)
    warnings = sum(1 for phase in phases if phase.status == STATUS_WARNING)
    confidence = 100 - (50 if hard_fail else 0) - min(40, warnings * 5)
    verdict = "UNSAFE" if hard_fail else ("UNKNOWN" if warnings else "SAFE")
    return {
        "schema_version": "apex_omega.calldata_semantic_audit.v1",
        "created_at_ns": time.time_ns(),
        "structural_validity": statuses.get("ABI Integrity", STATUS_UNKNOWN),
        "semantic_validity": statuses.get("Semantic Decode", STATUS_UNKNOWN),
        "economic_validity": statuses.get("Economic Consistency", STATUS_UNKNOWN),
        "state_parity": statuses.get("Reserve State Validation", STATUS_UNKNOWN),
        "identity_parity": statuses.get("Opportunity Identity Parity", STATUS_UNKNOWN),
        "execution_safety": "FAIL" if hard_fail else ("WARNING" if warnings else "PASS"),
        "overall_confidence_pct": max(0, confidence),
        "execution_verdict": verdict,
        "critical_findings": [finding for phase in phases for finding in phase.findings if phase.status == STATUS_FAIL],
        "recommended_fixes": _recommended_fixes(phases),
        "phases": [phase.as_dict() for phase in phases],
    }


def _recommended_fixes(phases: list[AuditPhase]) -> list[str]:
    fixes: list[str] = []
    for phase in phases:
        for finding in phase.findings:
            if "missing" in finding or "unknown" in finding:
                fixes.append(f"Provide authoritative evidence for {phase.name}: {finding}")
            elif "mismatch" in finding:
                fixes.append(f"Reconcile mismatch before execution: {phase.name}: {finding}")
            elif "ambiguous" in finding:
                fixes.append(f"Replace ambiguous label with explicit units/base: {phase.name}: {finding}")
    return list(dict.fromkeys(fixes))


def write_semantic_audit_checkpoint(report: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path) if path else output_path("semantic_audit_checkpoint.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an APEX-OMEGA calldata semantic audit checkpoint.")
    parser.add_argument("--calldata", default="0x12345678" + "0" * 64)
    parser.add_argument("--expected-selector", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = build_calldata_semantic_audit(
        calldata=args.calldata,
        expected_selector=args.expected_selector or None,
        identity_sources={"checkpoint": "dry_run_semantic_audit"},
        execution_parameters={"mode_flag": "dry_run"},
        economic={"gross_profit_usd": "10", "gas_cost_usd": "1", "flash_fee_usd": "1", "net_profit_usd": "8"},
        reserve_state={"before": ["1000", "1000"], "after": ["1001", "999.001"], "actual_input": "1", "output": "0.999"},
        protocol="V2_CPMM",
        tstore_report={"uses_eip_1153": False},
        relay={"relay_tip_usd": "0", "relay_tip_bps": "0", "relay_tip_base_usd": "8"},
    )
    path = write_semantic_audit_checkpoint(report, args.output or None)
    print(json.dumps({"checkpoint": str(path), "execution_verdict": report["execution_verdict"], "confidence": report["overall_confidence_pct"]}, sort_keys=True))
    return 0 if report["execution_verdict"] in {"SAFE", "UNKNOWN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())