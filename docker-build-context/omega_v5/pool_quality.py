#!/usr/bin/env python3
# ==============================================================================
# pool_quality.py -- fail-closed pool-state gates before ranking/execution.
# ==============================================================================

from __future__ import annotations

from collections import Counter
from typing import Any


CLMM_PROTOCOLS = {"UniswapV3", "QuickSwapV3", "Algebra"}
CLMM_AUDIT_KEY = "clmm_orientation_decimals_audit"
V2_AUDIT_KEY = "v2_pair_canonical_audit"


def is_clmm_pool(pool: dict[str, Any]) -> bool:
    return pool.get("protocol") in CLMM_PROTOCOLS


def clmm_audit(pool: dict[str, Any]) -> dict[str, Any]:
    return dict(pool.get("_meta", {}).get(CLMM_AUDIT_KEY, {}))


def clmm_audit_passed(pool: dict[str, Any]) -> bool:
    if not is_clmm_pool(pool):
        return True
    return clmm_audit(pool).get("status") == "pass"


def clmm_reject_reason(pool: dict[str, Any]) -> str:
    audit = clmm_audit(pool)
    reasons = audit.get("reject_reasons") or []
    if reasons:
        return ",".join(str(reason) for reason in reasons)
    return str(audit.get("status") or "missing_clmm_audit")


def is_v2_pool(pool: dict[str, Any]) -> bool:
    return pool.get("protocol") == "UniswapV2"


def v2_audit(pool: dict[str, Any]) -> dict[str, Any]:
    return dict(pool.get("_meta", {}).get(V2_AUDIT_KEY, {}))


def v2_audit_passed(pool: dict[str, Any]) -> bool:
    if not is_v2_pool(pool):
        return True
    return v2_audit(pool).get("status") == "pass"


def v2_reject_reason(pool: dict[str, Any]) -> str:
    audit = v2_audit(pool)
    reasons = audit.get("reject_reasons") or []
    if reasons:
        return ",".join(str(reason) for reason in reasons)
    return str(audit.get("status") or "missing_v2_audit")


def route_quality_metadata(pool_sequence: list[str], pools: dict[str, dict]) -> dict[str, Any]:
    clmm_total = 0
    clmm_failed: list[dict[str, Any]] = []
    v2_total = 0
    v2_failed: list[dict[str, Any]] = []

    for pool_id in pool_sequence:
        pool = pools.get(pool_id)
        if not pool:
            continue
        if is_clmm_pool(pool):
            clmm_total += 1
            if not clmm_audit_passed(pool):
                clmm_failed.append({
                    "pool_id": pool_id,
                    "protocol": pool.get("protocol", ""),
                    "reason": clmm_reject_reason(pool),
                })
        if is_v2_pool(pool):
            v2_total += 1
            if not v2_audit_passed(pool):
                v2_failed.append({
                    "pool_id": pool_id,
                    "protocol": pool.get("protocol", ""),
                    "reason": v2_reject_reason(pool),
                })

    return {
        "clmm_orientation_decimals": "pass" if not clmm_failed else "fail",
        "clmm_pools_checked": clmm_total,
        "clmm_pools_failed": len(clmm_failed),
        "clmm_failures": clmm_failed,
        "v2_pair_canonical": "pass" if not v2_failed else "fail",
        "v2_pools_checked": v2_total,
        "v2_pools_failed": len(v2_failed),
        "v2_failures": v2_failed,
    }


def route_quality_passed(pool_sequence: list[str], pools: dict[str, dict]) -> bool:
    metadata = route_quality_metadata(pool_sequence, pools)
    return (
        metadata["clmm_orientation_decimals"] == "pass"
        and metadata["v2_pair_canonical"] == "pass"
    )


def summarize_clmm_audits(pools: dict[str, dict]) -> dict[str, Any]:
    total = 0
    passed = 0
    failed = 0
    reasons: Counter[str] = Counter()

    for pool in pools.values():
        if not is_clmm_pool(pool):
            continue
        total += 1
        if clmm_audit_passed(pool):
            passed += 1
        else:
            failed += 1
            for reason in clmm_audit(pool).get("reject_reasons") or [clmm_reject_reason(pool)]:
                reasons[str(reason)] += 1

    return {
        "clmm_total": total,
        "clmm_passed": passed,
        "clmm_failed": failed,
        "reject_reasons": dict(sorted(reasons.items())),
    }


def summarize_v2_audits(pools: dict[str, dict]) -> dict[str, Any]:
    total = 0
    passed = 0
    failed = 0
    reasons: Counter[str] = Counter()

    for pool in pools.values():
        if not is_v2_pool(pool):
            continue
        total += 1
        if v2_audit_passed(pool):
            passed += 1
        else:
            failed += 1
            for reason in v2_audit(pool).get("reject_reasons") or [v2_reject_reason(pool)]:
                reasons[str(reason)] += 1

    return {
        "v2_total": total,
        "v2_passed": passed,
        "v2_failed": failed,
        "reject_reasons": dict(sorted(reasons.items())),
    }


def rejection_samples(pools: dict[str, dict], limit: int = 25) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for pool_id, pool in pools.items():
        audit = None
        gate = ""
        reason = ""
        if is_v2_pool(pool) and not v2_audit_passed(pool):
            audit = v2_audit(pool)
            gate = "v2_pair_canonical"
            reason = v2_reject_reason(pool)
        elif is_clmm_pool(pool) and not clmm_audit_passed(pool):
            audit = clmm_audit(pool)
            gate = "v3_algebra_orientation_decimals"
            reason = clmm_reject_reason(pool)
        if not gate:
            continue
        samples.append({
            "pool_id": pool_id,
            "protocol": pool.get("protocol", ""),
            "address": pool.get("address", ""),
            "tokens": list(pool.get("tokens") or []),
            "gate": gate,
            "reason": reason,
            "registered_tokens": audit.get("registered_tokens", []) if audit else [],
            "onchain_tokens": audit.get("onchain_tokens", []) if audit else [],
            "onchain_addresses": audit.get("onchain_addresses", []) if audit else [],
            "reject_reasons": audit.get("reject_reasons", []) if audit else [],
        })
        if len(samples) >= limit:
            break
    return samples


def filter_rankable_pools(pools: dict[str, dict]) -> tuple[dict[str, dict], dict[str, Any]]:
    filtered = {
        pool_id: pool
        for pool_id, pool in pools.items()
        if clmm_audit_passed(pool) and v2_audit_passed(pool)
    }
    summary = {
        "v3_algebra_orientation_decimals": summarize_clmm_audits(pools),
        "v2_pair_canonical": summarize_v2_audits(pools),
        "rejection_samples": rejection_samples(pools),
    }
    summary["filtered_out"] = len(pools) - len(filtered)
    summary["rankable_pools"] = len(filtered)
    return filtered, summary
