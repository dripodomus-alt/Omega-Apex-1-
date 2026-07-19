#!/usr/bin/env python3
# ==============================================================================
# execution_truth.py -- final executor-semantics route truth filter.
#
# Discovery/ranking may use invariant math and pool state. This module is the
# final boundary before staging or live submission: the same calldata that would
# be sent to the executor must pass eth_call at a tested flash size.
#
# Timing model (fully aligned):
# - Internal Consistency (Discovery): All prices in a route come from the same block.
# - External Lifespan (Execution): Once discovered at block N, the route must reach
#   execution within N + 4 blocks or it is discarded as stale.
#
# All stages log via pnl_tracker. Lifespan enforced here as final gate.
# Pipeline + PATH alignment: only closed, same-block routes survive.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import hashlib
import logging
import os
from typing import Any, Iterable

from web3 import Web3
from .config import MIN_FLASH_PRINCIPAL_USD
from .executable_quotes import quote_route_for_executor
from .flash_loan import FlashSource, Profitability, evaluate_profitability
from .opportunity_ranker import LiveOpportunity, _quote_route_amount
from .oracle_layer import PriceUnavailable, token_price_usd
from .pricing.net_delta import route_within_lifespan
from .rpc_layer import TOKEN_DECIMALS, TOKEN_ADDRESSES
from . import rpc_layer
from .pnl_tracker import record_lifespan_event, record_stage_event

logger = logging.getLogger("omega.truth")
logger.setLevel(logging.INFO)

CLMM_PROTOCOLS = {"UniswapV3", "QuickSwapV3", "Algebra"}
N_PLUS_4 = 4


@dataclass(frozen=True)
class ExecutionTruthResult:
    original: LiveOpportunity
    opportunity: LiveOpportunity | None
    executable: bool
    tested_sizes_usd: list[str]
    selected_size_usd: str = ""
    decoded_profit_usd: str = "0"
    exact_call_detail: str = ""
    rejection_class: str = ""
    quote_detail: str = ""
    exact_calls: int = 0
    route_signature: str = ""


def _is_clmm_route(op: LiveOpportunity) -> bool:
    return any(protocol in CLMM_PROTOCOLS for protocol in op.protocol_seq)


def route_semantic_signature(op: LiveOpportunity) -> str:
    """Stable signature for duplicate executor-route semantics in one scan."""
    pools = [str(item).lower() for item in (op.pool_addresses or op.pool_sequence)]
    payload = {
        "path": list(op.path),
        "protocol_seq": list(op.protocol_seq),
        "pools": pools,
        "flash_source": op.flash_source.value,
    }
    raw = repr(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _truth_size_factors() -> list[Decimal]:
    raw = os.environ.get("OMEGA_TRUTH_SIZE_FACTORS", "1,0.75,0.5,0.35,0.25,0.15,0.1")
    factors: list[Decimal] = []
    for item in raw.split(","):
        try:
            value = Decimal(item.strip())
        except Exception:
            continue
        if value > 0:
            factors.append(value)
    return factors or [Decimal("1"), Decimal("0.5"), Decimal("0.25"), Decimal("0.1")]


def _truth_min_principal_floor(op: LiveOpportunity) -> Decimal:
    proof_only = bool(
        getattr(op, "metadata", {})
        .get("principal_gate", {})
        .get("proof_only_below_minimum", False)
    )
    allow_proof = os.environ.get(
        "OMEGA_TRUTH_ALLOW_BELOW_MIN_PRINCIPAL_PROOF",
        "true",
    ).lower() in {"1", "true", "yes", "on"}
    runtime_mode = os.environ.get("OMEGA_RUNTIME_MODE", "").lower()
    execution_mode = os.environ.get("EXECUTION_MODE", "").lower()
    live_flag = os.environ.get("LIVE_TRADING", "0")
    live_like = runtime_mode == "live" or execution_mode == "live" or live_flag == "1"
    if proof_only and allow_proof and not live_like:
        try:
            value = Decimal(os.environ.get("OMEGA_TRUTH_MIN_PROOF_PRINCIPAL_USD", "25"))
            return value if value > 0 else MIN_FLASH_PRINCIPAL_USD
        except Exception:
            return Decimal("25")
    return MIN_FLASH_PRINCIPAL_USD


def _size_ladder_from_metadata(op: LiveOpportunity) -> list[Decimal]:
    sizing = op.metadata.get("sizing", {}) if isinstance(op.metadata, dict) else {}
    raw_ladder = sizing.get("flash_size_ladder_usd") or []
    selected = Decimal(str(op.profitability.flashloan.principal_usd))
    sizes: list[Decimal] = []
    for item in raw_ladder:
        try:
            value = Decimal(str(item))
        except Exception:
            continue
        if value > 0:
            sizes.append(value)
    if selected > 0:
        sizes.append(selected)
        for factor in _truth_size_factors():
            sizes.append(selected * factor)

    if _is_clmm_route(op):
        for divisor in (2, 4, 10, 20):
            value = selected / Decimal(divisor)
            if value > 0:
                sizes.append(value)

    min_floor = _truth_min_principal_floor(op)
    deduped = sorted({size for size in sizes if size >= min_floor}, reverse=True)
    try:
        max_rungs = max(1, int(os.environ.get("OMEGA_TRUTH_MAX_SIZE_RUNGS", "7")))
    except Exception:
        max_rungs = 7
    selected = Decimal(str(op.profitability.flashloan.principal_usd))
    selected_rows = [item for item in deduped if item == selected]
    other_rows = [item for item in deduped if item != selected]
    deduped = (selected_rows + other_rows)[:max_rungs]
    return deduped


def _retarget_opportunity(
    op: LiveOpportunity,
    pools: dict,
    principal_usd: Decimal,
) -> tuple[LiveOpportunity | None, str]:
    # Enforce the n+4 block lifespan gate as the external bound.
    # This must happen early, before expensive price/quote work.
    current_block = getattr(rpc_layer, "BLOCK", 0)
    if not route_within_lifespan(op.block_detected, current_block, N_PLUS_4):
        record_lifespan_event(
            event_type="EXPIRED",
            discovery_block=op.block_detected,
            current_block=current_block,
            route=list(op.path),
            opp_id=str(id(op)),
            status="EXPIRED_IN_TRUTH",
        )
        return None, f"route_lifespan_exceeded: discovered_at={op.block_detected} current_block={current_block}"

    semantic_ok, semantic_detail = _route_semantics_preflight(op, pools)
    if not semantic_ok:
        return None, semantic_detail

    try:
        price = token_price_usd(op.path[0])
    except PriceUnavailable:
        return None, "base_price_unavailable"
    if price <= 0 or principal_usd <= 0:
        return None, "invalid_price_or_principal"

    amount_in = principal_usd / price
    quote_detail: dict[str, Any] = {}
    if _is_clmm_route(op):
        executable_quote = quote_route_for_executor(op.path, op.pool_sequence, pools, amount_in)
        quote_detail = {
            "source": "onchain_clmm_quoter_plus_math_non_clmm",
            "clmm_quoted": executable_quote.clmm_quoted,
            "clmm_unquoted": executable_quote.clmm_unquoted,
            "hop_proofs": executable_quote.hop_proofs,
            "amount_out_raw": str(executable_quote.amount_out_raw),
        }
        if not executable_quote.clmm_proven:
            return None, f"onchain_clmm_quote_unproven:{quote_detail}"
        amount_out = executable_quote.amount_out
    else:
        amount_out = _quote_route_amount(op.path, op.pool_sequence, pools, amount_in)
        quote_detail = {"source": "invariant_math_non_clmm"}
    if amount_out <= 0:
        return None, f"non_positive_retarget_output:{quote_detail}"
    gross_out_usd = amount_out * price
    profitability = evaluate_profitability(
        gross_out_usd,
        principal_usd,
        hops=len(op.path) - 1,
        flash_source=op.flash_source,
        asset=op.path[0],
    )
    if not profitability.passes_gate:
        return None, (
            "quote_aligned_profitability_gate_failed:"
            f"net_usd={profitability.net_profit_usd}:principal_usd={principal_usd}:gross_out_usd={gross_out_usd}"
        )

    gross_rate = gross_out_usd / principal_usd if principal_usd > 0 else Decimal("0")
    metadata = dict(op.metadata)
    truth = dict(metadata.get("execution_truth", {}))
    truth.update({
        "sizing_pass": "candidate_retargeted",
        "tested_principal_usd": str(principal_usd),
        "clmm_route": _is_clmm_route(op),
        "executor_semantics_quote": quote_detail,
    })
    metadata["execution_truth"] = truth
    return replace(
        op,
        gross_rate=gross_rate,
        gross_out_usd=gross_out_usd,
        profitability=profitability,
        metadata=metadata,
    ), ""


def _route_semantics_preflight(op: LiveOpportunity, pools: dict) -> tuple[bool, str]:
    if len(op.path) < 3:
        return False, "route_semantics_failed:path_too_short"
    if op.path[0] != op.path[-1]:
        return False, "route_semantics_failed:path_not_closed"
    if len(op.pool_sequence) != len(op.path) - 1:
        return False, (
            "route_semantics_failed:pool_hop_count_mismatch:"
            f"pools={len(op.pool_sequence)}:hops={len(op.path) - 1}"
        )
    for symbol in op.path:
        address = TOKEN_ADDRESSES.get(symbol)
        if not address or address.lower() == "0x" + "00" * 20:
            return False, f"route_semantics_failed:missing_token_address:{symbol}"
    seen_pool_addresses: set[str] = set()
    for idx, pool_id in enumerate(op.pool_sequence):
        pool = pools.get(pool_id)
        if not isinstance(pool, dict):
            return False, f"route_semantics_failed:missing_live_pool:{pool_id}"
        pool_address = str(pool.get("address", "")).lower()
        if not pool_address or pool_address == "0x" + "00" * 20:
            return False, f"route_semantics_failed:missing_pool_address:{pool_id}"
        if pool_address in seen_pool_addresses:
            return False, f"route_semantics_failed:duplicate_pool_address:{pool_id}:{pool_address}"
        seen_pool_addresses.add(pool_address)
        token_in = op.path[idx]
        token_out = op.path[idx + 1]
        tokens = list(pool.get("tokens") or [])
        if token_in == token_out:
            return False, f"route_semantics_failed:same_token_hop:{token_in}:{idx}"
        if token_in not in tokens or token_out not in tokens:
            return False, (
                "route_semantics_failed:pool_token_mismatch:"
                f"pool={pool_id}:token_in={token_in}:token_out={token_out}:pool_tokens={tokens}"
            )
    return True, "route_semantics_pass"


def _decode_profit_usd(op: LiveOpportunity, result_hex: str, gas_cost_usd: Decimal) -> Decimal:
    raw = Web3.to_int(hexstr=result_hex) if result_hex and result_hex != "0x" else 0
    try:
        price = token_price_usd(op.path[0])
    except PriceUnavailable:
        return Decimal("0")
    if price <= 0:
        return Decimal("0")

    decimals = int(TOKEN_DECIMALS.get(op.path[0], 18))
    profit_asset = Decimal(raw) / (Decimal(10) ** decimals)
    return (profit_asset * price) - gas_cost_usd


def _failure_class(detail: str) -> str:
    lowered = detail.lower()
    if any(marker in lowered for marker in ["429", "too many requests", "rate limit", "timeout", "tls", "ssl", "connection"]):
        return "exact_call_transport_failed"
    if "AdapterSlippageOrProfit" in detail:
        return "slippage_or_profit_floor"
    if "AdapterPoolKindUnset" in detail:
        return "route_pool_kind_unset"
    if "AdapterBadRoute" in detail:
        return "bad_route_semantics"
    if "AdapterUnsupportedPool" in detail:
        return "unsupported_pool"
    if "AdapterTransferFailed" in detail:
        return "token_transfer_failed"
    if "execution reverted" in lowered:
        return "executor_revert"
    return "eth_call_failed"


def prove_execution_truth(
    op: LiveOpportunity,
    pools: dict,
    *,
    base_fee_gwei: Decimal,
    max_exact_calls: int | None = None,
) -> ExecutionTruthResult:
    # Defer import to break circular dependency with execution.py
    from .execution import build_tx_payload, simulate_tx_payload, simulation_from_address # type: ignore
 
    tested: list[str] = []
    last_detail = ""
    last_class = ""
    exact_calls = 0
    signature = route_semantic_signature(op)

    current_block = getattr(rpc_layer, "BLOCK", 0)

    for size_usd in _size_ladder_from_metadata(op):
        tested.append(str(size_usd))
        candidate, reject_detail = _retarget_opportunity(op, pools, size_usd)
        if candidate is None:
            last_detail = reject_detail or "candidate_retarget_failed"
            if str(last_detail).startswith("quote_aligned_profitability_gate_failed"):
                last_class = "quote_aligned_not_profitable"
            elif str(last_detail).startswith("route_semantics_failed"):
                last_class = "route_semantics_failed"
            elif "lifespan" in str(last_detail).lower():
                last_class = "route_lifespan_exceeded"
            else:
                last_class = "executor_semantics_quote_failed" if _is_clmm_route(op) else "candidate_retarget_failed"
            continue
        try:
            tx = build_tx_payload(candidate, nonce=0, base_fee_gwei=base_fee_gwei)
        except Exception as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
            last_class = "payload_build_failed"
            continue
        if max_exact_calls is not None and exact_calls >= max_exact_calls:
            last_detail = f"exact call budget exhausted before size_usd={size_usd}"
            last_class = "exact_call_budget_exhausted"
            break
        exact_calls += 1
        ok, detail = simulate_tx_payload(tx, from_addr=simulation_from_address() or None)
        last_detail = detail
        if not ok:
            last_class = _failure_class(detail)
            continue
        try:
            decoded_profit_usd = _decode_profit_usd(candidate, detail, candidate.profitability.gas_cost_usd)
        except Exception:
            decoded_profit_usd = Decimal("0")
        if decoded_profit_usd <= 0:
            last_class = "decoded_non_positive_profit"
            last_detail = f"eth_call_passed_but_decoded_profit_usd={decoded_profit_usd}"
            continue

        metadata = dict(candidate.metadata)
        truth = dict(metadata.get("execution_truth", {}))
        truth.update({
            "exact_call": "pass",
            "final_ranking_source": "executor_eth_call",
            "selected_principal_usd": str(size_usd),
            "decoded_profit_usd_after_gas": str(decoded_profit_usd),
            "tested_sizes_usd": tested,
        })
        metadata["execution_truth"] = truth
        executable = replace(
            candidate,
            profitability=replace(candidate.profitability, net_profit_usd=decoded_profit_usd),
            metadata=metadata,
        )
        record_lifespan_event(
            event_type="EXECUTED",
            discovery_block=op.block_detected,
            current_block=current_block,
            route=list(op.path),
            status="TRUTH_PASSED",
        )
        record_stage_event(stage="TRUTH", status="PASSED", route=list(op.path), block=current_block)
        return ExecutionTruthResult(
            original=op,
            opportunity=executable,
            executable=True,
            tested_sizes_usd=tested,
            selected_size_usd=str(size_usd),
            decoded_profit_usd=str(decoded_profit_usd),
            exact_call_detail=detail,
            exact_calls=exact_calls,
            route_signature=signature,
        )

    record_stage_event(stage="TRUTH", status="FAILED", route=list(op.path), block=current_block)
    return ExecutionTruthResult(
        original=op,
        opportunity=None,
        executable=False,
        tested_sizes_usd=tested,
        exact_call_detail=last_detail,
        rejection_class=last_class or "no_candidate_size_passed",
        quote_detail=last_detail if last_class in {"executor_semantics_quote_failed", "candidate_retarget_failed", "quote_aligned_not_profitable"} else "",
        exact_calls=exact_calls,
        route_signature=signature,
    )


def final_truth_rank(
    opportunities: Iterable[LiveOpportunity],
    pools: dict,
    *,
    base_fee_gwei: Decimal,
    max_candidates: int = 50,
    max_executable: int | None = None,
    max_exact_calls: int | None = None,
    skip_bad_route_signatures: bool | None = None,
) -> tuple[list[LiveOpportunity], list[ExecutionTruthResult]]:
    results: list[ExecutionTruthResult] = []
    executable: list[LiveOpportunity] = []
    bad_route_signatures: set[str] = set()
    exact_calls_used = 0
    if max_exact_calls is None:
        try:
            max_exact_calls = max(1, int(os.environ.get("OMEGA_TRUTH_MAX_EXACT_CALLS", "80")))
        except Exception:
            max_exact_calls = 80
    if skip_bad_route_signatures is None:
        skip_bad_route_signatures = os.environ.get(
            "OMEGA_TRUTH_SKIP_BAD_ROUTE_SIGNATURES",
            "true",
        ).lower() in {"1", "true", "yes", "on"}
    for op in list(opportunities)[:max_candidates]:
        signature = route_semantic_signature(op)
        if skip_bad_route_signatures and signature in bad_route_signatures:
            result = ExecutionTruthResult(
                original=op,
                opportunity=None,
                executable=False,
                tested_sizes_usd=[],
                exact_call_detail=f"skipped duplicate bad route signature {signature}",
                rejection_class="skipped_bad_route_signature",
                route_signature=signature,
            )
            results.append(result)
            continue
        if exact_calls_used >= max_exact_calls:
            result = ExecutionTruthResult(
                original=op,
                opportunity=None,
                executable=False,
                tested_sizes_usd=[],
                exact_call_detail=f"global exact call budget exhausted at {exact_calls_used}",
                rejection_class="exact_call_budget_exhausted",
                route_signature=signature,
            )
            results.append(result)
            continue
        result = prove_execution_truth(
            op,
            pools,
            base_fee_gwei=base_fee_gwei,
            max_exact_calls=max_exact_calls - exact_calls_used,
        )
        results.append(result)
        exact_calls_used += result.exact_calls
        if result.rejection_class == "bad_route_semantics":
            bad_route_signatures.add(result.route_signature or signature)
        if result.executable and result.opportunity is not None:
            executable.append(result.opportunity)
            if max_executable is not None and len(executable) >= max_executable:
                break
    executable.sort(key=lambda item: item.profitability.net_profit_usd, reverse=True)
    return executable, results


def truth_summary(results: Iterable[ExecutionTruthResult]) -> dict[str, Any]:
    rows = list(results)
    by_class: dict[str, int] = {}
    for row in rows:
        if row.executable:
            by_class["executable"] = by_class.get("executable", 0) + 1
        else:
            key = row.rejection_class or "rejected"
            by_class[key] = by_class.get(key, 0) + 1
    return {
        "inspected": len(rows),
        "executable": sum(1 for row in rows if row.executable),
        "exact_calls": sum(row.exact_calls for row in rows),
        "skipped_bad_route_signatures": sum(1 for row in rows if row.rejection_class == "skipped_bad_route_signature"),
        "unique_route_signatures": len({row.route_signature for row in rows if row.route_signature}),
        "rejection_classes": by_class,
    }
