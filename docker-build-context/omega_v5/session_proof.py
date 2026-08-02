#!/usr/bin/env python3
# ==============================================================================
# session_proof.py -- Smart Sessions / WaaS delegated-lane proof harness.
#
# This module proves the optional delegated UX lane without placing it in the
# arbitrage hot path. It validates strict allowlists, exact-call transport,
# target bytecode, dry-run transaction envelope construction, and fail-closed
# behavior when remote WaaS execution is unavailable or disabled.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from web3 import Web3

from . import redis_cache
from .config import (
    CHAIN_ID,
    ENABLE_SMART_SESSIONS,
    SESSION_PROOF_SAMPLES,
    SESSION_SIGNER_ENABLED,
    SESSION_SIGNER_MODE,
    SMART_SESSIONS_ALLOWED_SELECTORS,
    SMART_SESSIONS_ALLOWED_TARGETS,
    SMART_SESSIONS_CREDENTIAL_ID,
    SMART_SESSIONS_MAX_VALUE_WEI,
    SMART_SESSIONS_WAAS_API_URL,
    SMART_SESSIONS_WALLET_ID,
    WAAS_BROADCAST_ADAPTER_ENABLED,
    WAAS_BROADCAST_ADAPTER_MODE,
)
from .execution import EXECUTE_FLASH_ARB_SELECTOR
from .paths import output_path
from .transport_lanes import (
    LANE_EXACT_C1_ETH_CALL,
    _inject_poa,
    _mask_url,
    select_endpoint,
)


STREAM_SESSION_PROOFS = "omega:proofs:session_signer"
PROOF_JSON_PATH = output_path("session_signer_proof_latest.json")
PROOF_TEXT_PATH = output_path("session_signer_proof_latest.txt")


@dataclass
class ProofStep:
    name: str
    ok: bool
    latency_ms: float
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _now_ms() -> float:
    return time.perf_counter() * 1000


def _timed(name: str, fn: Callable[[], tuple[bool, str, dict[str, Any]]]) -> ProofStep:
    started = _now_ms()
    try:
        ok, detail, data = fn()
    except Exception as exc:
        ok, detail, data = False, f"{type(exc).__name__}: {exc}", {}
    return ProofStep(
        name=name,
        ok=bool(ok),
        latency_ms=round(_now_ms() - started, 3),
        detail=detail,
        data=data,
    )


def _normalize_address(value: str) -> str:
    return Web3.to_checksum_address(str(value).strip())


def _normalize_selector(value: str) -> str:
    selector = str(value).strip().lower()
    if not selector.startswith("0x"):
        selector = f"0x{selector}"
    if len(selector) != 10:
        raise ValueError(f"invalid selector length: {selector}")
    int(selector[2:], 16)
    return selector


def _configured_targets() -> list[str]:
    return [_normalize_address(value) for value in SMART_SESSIONS_ALLOWED_TARGETS]


def _configured_selectors() -> list[str]:
    return [_normalize_selector(value) for value in SMART_SESSIONS_ALLOWED_SELECTORS]


def _latency_summary(steps: list[ProofStep]) -> dict[str, Any]:
    values = [step.latency_ms for step in steps]
    if not values:
        return {"count": 0, "min_ms": 0, "p50_ms": 0, "p95_ms": 0, "max_ms": 0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "count": len(values),
        "min_ms": round(min(values), 3),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(values), 3),
    }


def _session_config_gate() -> tuple[bool, str, dict[str, Any]]:
    targets = _configured_targets()
    selectors = _configured_selectors()
    issues: list[str] = []
    if not ENABLE_SMART_SESSIONS:
        issues.append("ENABLE_SMART_SESSIONS=false")
    if not SESSION_SIGNER_ENABLED:
        issues.append("SESSION_SIGNER_ENABLED=false")
    if SESSION_SIGNER_MODE != "dry_run":
        issues.append(f"SESSION_SIGNER_MODE={SESSION_SIGNER_MODE}; expected dry_run")
    if WAAS_BROADCAST_ADAPTER_ENABLED and WAAS_BROADCAST_ADAPTER_MODE != "dry_run":
        issues.append(
            f"WAAS_BROADCAST_ADAPTER_MODE={WAAS_BROADCAST_ADAPTER_MODE}; expected dry_run"
        )
    if not targets:
        issues.append("SMART_SESSIONS_ALLOWED_TARGETS empty")
    if not selectors:
        issues.append("SMART_SESSIONS_ALLOWED_SELECTORS empty")
    if EXECUTE_FLASH_ARB_SELECTOR.lower() not in selectors:
        issues.append(f"missing executeFlashArb selector {EXECUTE_FLASH_ARB_SELECTOR}")
    if str(SMART_SESSIONS_MAX_VALUE_WEI or "0").strip() != "0":
        issues.append("SMART_SESSIONS_MAX_VALUE_WEI must be 0 for delegated executor calls")

    return (
        not issues,
        "pass" if not issues else "; ".join(issues),
        {
            "targets": targets,
            "selectors": selectors,
            "session_signer_mode": SESSION_SIGNER_MODE,
            "waas_adapter_enabled": WAAS_BROADCAST_ADAPTER_ENABLED,
            "waas_adapter_mode": WAAS_BROADCAST_ADAPTER_MODE,
            "waas_url_configured": bool(SMART_SESSIONS_WAAS_API_URL),
            "credential_configured": bool(SMART_SESSIONS_CREDENTIAL_ID),
            "wallet_configured": bool(SMART_SESSIONS_WALLET_ID),
        },
    )


def _hot_path_isolation_gate() -> tuple[bool, str, dict[str, Any]]:
    if WAAS_BROADCAST_ADAPTER_ENABLED:
        return (
            False,
            "WAAS_BROADCAST_ADAPTER_ENABLED must remain false until external canary approval",
            {"smart_sessions_in_hot_path": False, "adapter_enabled": True},
        )
    return (
        True,
        "delegated lane is isolated from live arbitrage broadcast",
        {"smart_sessions_in_hot_path": False, "adapter_enabled": False},
    )


def _select_exact_call_endpoint() -> tuple[bool, str, dict[str, Any]]:
    endpoint = select_endpoint(LANE_EXACT_C1_ETH_CALL, probe_if_stale=True)
    return (
        bool(endpoint),
        "selected" if endpoint else "no exact-call endpoint passed health scoring",
        {"endpoint_masked": _mask_url(endpoint)},
    )


def _exact_call_probe(endpoint: str, targets: list[str]) -> tuple[bool, str, dict[str, Any]]:
    if not endpoint:
        return False, "missing endpoint", {}
    w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={"timeout": 8}))
    _inject_poa(w3)
    chain_id = int(w3.eth.chain_id)
    block = int(w3.eth.block_number)
    if chain_id != CHAIN_ID:
        return False, f"wrong chain_id {chain_id}", {"chain_id": chain_id, "block": block}

    target_records: list[dict[str, Any]] = []
    for target in targets:
        code = w3.eth.get_code(target).hex()
        code_ok = code not in ("", "0x")
        owner_result = ""
        owner_ok = False
        try:
            owner_raw = w3.eth.call({"to": target, "data": "0x8da5cb5b"}, block_identifier="latest")
            owner_result = Web3.to_checksum_address("0x" + owner_raw.hex()[-40:]) if owner_raw else ""
            owner_ok = bool(owner_result)
        except Exception as exc:
            owner_result = f"{type(exc).__name__}: owner() unavailable"
        target_records.append(
            {
                "target": target,
                "bytecode_present": code_ok,
                "bytecode_length": max(0, (len(code) - 2) // 2),
                "owner_call_ok": owner_ok,
                "owner": owner_result,
            }
        )

    all_code_ok = all(row["bytecode_present"] for row in target_records)
    return (
        all_code_ok,
        "bytecode/exact-call path proven" if all_code_ok else "one or more targets missing bytecode",
        {
            "chain_id": chain_id,
            "block": block,
            "endpoint_masked": _mask_url(endpoint),
            "targets": target_records,
        },
    )


def _build_prepare_envelope(target: str, selector: str) -> dict[str, Any]:
    return {
        "lane": "SESSION_SIGNER",
        "adapter": "WaaS_BROADCAST_ADAPTER",
        "mode": "dry_run",
        "operation": "PrepareEthereumContractCall",
        "walletId": "<configured>" if SMART_SESSIONS_WALLET_ID else "",
        "credentialId": "<configured>" if SMART_SESSIONS_CREDENTIAL_ID else "",
        "chainId": CHAIN_ID,
        "to": target,
        "value": "0",
        "data": selector,
        "permissions": {
            "allowedTargets": _configured_targets(),
            "allowedSelectors": _configured_selectors(),
            "maxValueWei": SMART_SESSIONS_MAX_VALUE_WEI,
        },
        "dryRun": True,
    }


def _envelope_build_probe() -> tuple[bool, str, dict[str, Any]]:
    targets = _configured_targets()
    selectors = _configured_selectors()
    if not targets or not selectors:
        return False, "missing targets/selectors", {}
    envelope = _build_prepare_envelope(targets[0], EXECUTE_FLASH_ARB_SELECTOR.lower())
    selector_ok = str(envelope["data"]).lower() in selectors
    target_ok = envelope["to"] in targets
    value_ok = str(envelope["value"]) == "0"
    return (
        selector_ok and target_ok and value_ok,
        "prepare envelope constructed without secret material",
        {
            "envelope": envelope,
            "selector_allowed": selector_ok,
            "target_allowed": target_ok,
            "zero_value": value_ok,
        },
    )


def _remote_execute_fail_closed_probe() -> tuple[bool, str, dict[str, Any]]:
    configured = all(
        [
            SMART_SESSIONS_WAAS_API_URL,
            SMART_SESSIONS_CREDENTIAL_ID,
            SMART_SESSIONS_WALLET_ID,
        ]
    )
    if WAAS_BROADCAST_ADAPTER_ENABLED:
        return (
            False,
            "remote execute adapter is enabled; canary proof must be explicit and separate",
            {"remote_configured": configured, "adapter_enabled": True},
        )
    if not configured:
        return (
            True,
            "expected fail-closed: WaaS URL/credential/wallet are not fully configured",
            {"remote_configured": False, "execute_attempted": False},
        )
    return (
        True,
        "expected fail-closed: dry-run mode blocks remote Execute despite complete config",
        {"remote_configured": True, "execute_attempted": False},
    )


def _redis_proof_log_probe(payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    proof_id = redis_cache.xadd(
        STREAM_SESSION_PROOFS,
        {
            "status": payload.get("status", "UNKNOWN"),
            "ok": payload.get("ok", False),
            "latency": payload.get("latency_summary", {}),
            "remote_waas_configured": payload.get("remote_waas_configured", False),
        },
        maxlen=1000,
    )
    redis_ok, redis_detail = redis_cache.status()
    return (
        bool(proof_id) or not redis_ok,
        "redis stream logged" if proof_id else f"redis unavailable/non-fatal: {redis_detail}",
        {"redis_ok": redis_ok, "redis_detail": redis_detail, "stream": STREAM_SESSION_PROOFS, "proof_id": proof_id},
    )


def run_session_signer_proof(samples: int = SESSION_PROOF_SAMPLES) -> dict[str, Any]:
    samples = max(1, int(samples or 1))
    started_wall = time.time()
    steps: list[ProofStep] = []

    config_step = _timed("config_gate", _session_config_gate)
    steps.append(config_step)
    isolation_step = _timed("hot_path_isolation_gate", _hot_path_isolation_gate)
    steps.append(isolation_step)
    endpoint_step = _timed("exact_call_lane_selection", _select_exact_call_endpoint)
    steps.append(endpoint_step)

    endpoint = str(endpoint_step.data.get("endpoint_masked", ""))
    raw_endpoint = select_endpoint(LANE_EXACT_C1_ETH_CALL, probe_if_stale=False)
    targets = config_step.data.get("targets", []) if config_step.ok else []
    for index in range(samples):
        steps.append(
            _timed(
                f"exact_call_bytecode_probe_{index + 1}",
                lambda raw_endpoint=raw_endpoint, targets=targets: _exact_call_probe(raw_endpoint, targets),
            )
        )

    steps.append(_timed("dry_run_prepare_envelope", _envelope_build_probe))
    steps.append(_timed("remote_execute_fail_closed", _remote_execute_fail_closed_probe))

    partial_payload = {
        "ok": all(step.ok for step in steps),
        "status": "PASS" if all(step.ok for step in steps) else "FAIL",
        "latency_summary": _latency_summary(steps),
        "remote_waas_configured": all(
            [
                SMART_SESSIONS_WAAS_API_URL,
                SMART_SESSIONS_CREDENTIAL_ID,
                SMART_SESSIONS_WALLET_ID,
            ]
        ),
    }
    redis_step = _timed("proof_log_redis_stream", lambda: _redis_proof_log_probe(partial_payload))
    steps.append(redis_step)

    ok = all(step.ok for step in steps)
    proof = {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "generated_at_unix": started_wall,
        "chain_id": CHAIN_ID,
        "scope": "optional SESSION_SIGNER / WaaS_BROADCAST_ADAPTER dry-run proof lane",
        "hot_path_policy": "not in live arbitrage hot path",
        "exact_call_endpoint_masked": endpoint,
        "remote_waas_configured": partial_payload["remote_waas_configured"],
        "remote_execute_attempted": False,
        "definition_of_done": {
            "local_gates_proven": ok,
            "external_waas_prepare_execute_proven": False,
            "external_waas_reason": (
                "missing WaaS URL/credential/wallet"
                if not partial_payload["remote_waas_configured"]
                else "remote Execute intentionally blocked by dry-run canary policy"
            ),
        },
        "latency_summary": _latency_summary(steps),
        "steps": [
            {
                "name": step.name,
                "ok": step.ok,
                "latency_ms": step.latency_ms,
                "detail": step.detail,
                "data": step.data,
            }
            for step in steps
        ],
    }
    PROOF_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_JSON_PATH.write_text(json.dumps(proof, indent=2, default=str), encoding="utf-8")
    PROOF_TEXT_PATH.write_text(_render_text(proof), encoding="utf-8")
    return proof


def _render_text(proof: dict[str, Any]) -> str:
    lines = [
        f"Session signer proof: {proof['status']}",
        f"Scope: {proof['scope']}",
        f"Hot path policy: {proof['hot_path_policy']}",
        f"Exact-call endpoint: {proof['exact_call_endpoint_masked']}",
        f"Remote WaaS configured: {proof['remote_waas_configured']}",
        f"Remote Execute attempted: {proof['remote_execute_attempted']}",
        f"Latency: {proof['latency_summary']}",
        "",
        "Steps:",
    ]
    for step in proof["steps"]:
        lines.append(
            f"- {'PASS' if step['ok'] else 'FAIL'} {step['name']} "
            f"{step['latency_ms']}ms :: {step['detail']}"
        )
    return "\n".join(lines) + "\n"


def load_latest_proof() -> dict[str, Any]:
    if not PROOF_JSON_PATH.exists():
        return {"ok": False, "status": "MISSING", "path": str(PROOF_JSON_PATH)}
    try:
        return json.loads(PROOF_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "status": "INVALID", "path": str(PROOF_JSON_PATH), "error": f"{type(exc).__name__}: {exc}"}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run SESSION_SIGNER / WaaS dry-run proof")
    parser.add_argument("--samples", type=int, default=SESSION_PROOF_SAMPLES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    proof = run_session_signer_proof(samples=args.samples)
    if args.json:
        print(json.dumps(proof, indent=2, default=str))
    else:
        print(_render_text(proof))
        print(f"JSON proof: {PROOF_JSON_PATH}")
    return 0 if proof.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
