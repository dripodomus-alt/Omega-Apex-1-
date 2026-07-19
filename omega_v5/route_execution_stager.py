#!/usr/bin/env python3
# ==============================================================================
# route_execution_stager.py -- math-driven 2/3/4-hop pre-rank and staging layer.
#
# PRIMARY multi-hop producer for the main funnel (via pre_rank_routes).
# Produces PreRankedRoute blueprints for 2/3/4-hop closed flash cycles using
# exhaustive token-path + pool-option product search.
# ==============================================================================

from __future__ import annotations

import itertools
import logging
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from . import rpc_layer
from .executable_quotes import quote_route_for_executor
from .flash_loan import FlashSource, MIN_NET_PROFIT_USD, evaluate_profitability
from .oracle_layer import token_price_usd
from .paths import output_path
from .sizing import optimize_route_principal
from .pricing.net_delta import route_within_lifespan
from .pnl_tracker import record_lifespan_event, record_stage_event

logger = logging.getLogger("omega.stager")
logger.setLevel(logging.INFO)

LATEST_STAGE_REPORT = output_path("route_execution_stage_latest.json")
HISTORY_STAGE_REPORT = output_path("route_execution_stage_history.jsonl")
SUPPORTED_HOPS = (2, 3, 4)
N_PLUS_4_LIFESPAN = 4


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _hop_fee_fraction(hop: dict[str, Any] | None = None, pool: dict[str, Any] | None = None) -> Decimal:
    """
    Normalize hop/pool fee metadata to a 0..1 fraction.

    Accepts:
    - already-normalized fractions (0.003, 0.0005)
    - Uniswap V3 fee-tier units (500, 3000, 10000) -> / 1_000_000
    - small integer bps (5, 30) -> / 10_000

    Default when missing: Uniswap V3 mid tier 3000 (0.30%).
    Never divides by zero.
    """
    raw: Any = None
    if hop:
        raw = hop.get("fee", hop.get("fee_tier", hop.get("fee_bps")))
    if raw is None and pool:
        raw = pool.get("fee_tier", pool.get("fee", pool.get("fee_bps", pool.get("swap_fee"))))
    if raw is None:
        raw = 3000

    try:
        fee = Decimal(str(raw))
    except Exception:
        return Decimal("0")

    if fee < 0:
        return Decimal("0")
    if fee <= Decimal("1"):
        return fee
    if fee >= Decimal("100"):
        return fee / Decimal("1000000")
    return fee / Decimal("10000")


def _estimate_hop_fees_usd(
    edge_entries: Iterable[dict[str, Any]],
    *,
    base_amount_in: Decimal,
    base_token: str,
    pools: dict[str, dict] | None = None,
    pool_sequence: Iterable[str] | None = None,
) -> tuple[list[Decimal], Decimal]:
    """
    Estimate explicit hop fee drag on flash notional.

    Model: fee_usd_i = base_amount_in * fee_fraction_i * price(base_token)

    Note: executable AMM quotes already embed protocol fees in amount_out.
    This estimate is for audit / explicit fee visibility in net_formula.
    """
    pools = pools or {}
    pool_ids = list(pool_sequence or [])
    try:
        price = Decimal(str(token_price_usd(base_token)))
    except Exception:
        price = Decimal("0")

    fees: list[Decimal] = []
    for idx, hop in enumerate(edge_entries or ()):
        pool_id = str(hop.get("pool_id") or (pool_ids[idx] if idx < len(pool_ids) else "") or "")
        pool = pools.get(pool_id) or {}
        frac = _hop_fee_fraction(hop, pool)
        fees.append(base_amount_in * frac * price)
    total = sum(fees, Decimal("0"))
    return fees, total


def _get_min_tvl(pool_sequence: tuple[str, ...], pools: dict[str, dict]) -> Decimal:
    tvls = [
        _decimal(pools.get(pool_id, {}).get("total_executable_liquidity_usd"))
        for pool_id in pool_sequence
    ]
    return min(tvls) if tvls and all(tvl > 0 for tvl in tvls) else Decimal("0")


@dataclass(frozen=True)
class PreRankedRoute:
    path: tuple[str, ...]
    pool_sequence: tuple[str, ...]
    protocol_seq: tuple[str, ...]
    liquidity_keys: tuple[str, ...]
    route_class_seq: tuple[str, ...]
    approximate_gross_rate: Decimal
    approximate_raw_delta_usd: Decimal
    approximate_raw_delta_bps: Decimal
    edge_entries: tuple[dict[str, Any], ...]
    discovery_block: int = 0


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)) or default)
    except Exception:
        return default


def _decimal_env(key: str, default: str) -> Decimal:
    try:
        return Decimal(os.environ.get(key, default) or default)
    except Exception:
        return Decimal(default)


def _quote_options(entries: list[dict[str, Any]], max_options: int) -> list[dict[str, Any]]:
    if max_options <= 0:
        return list(entries)
    return list(entries[:max_options])


def _tokens_from_rates(rates: dict) -> set[str]:
    tokens: set[str] = set()
    for token_in, token_out in rates:
        tokens.add(str(token_in))
        tokens.add(str(token_out))
    return {token for token in tokens if token}


def enumerate_closed_token_paths(
    rates: dict,
    *,
    hops: Iterable[int] = SUPPORTED_HOPS,
    base_tokens: Iterable[str] | None = None,
    max_token_paths: int = 0,
) -> list[tuple[str, ...]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for token_in, token_out in rates:
        if token_in != token_out:
            adjacency[str(token_in)].add(str(token_out))

    bases = list(dict.fromkeys(base_tokens or sorted(_tokens_from_rates(rates))))
    paths: list[tuple[str, ...]] = []
    hop_set = {int(hop) for hop in hops if int(hop) in SUPPORTED_HOPS}

    def walk(base: str, current: str, remaining: int, path: list[str]) -> None:
        if max_token_paths > 0 and len(paths) >= max_token_paths:
            return
        if remaining == 1:
            if base in adjacency.get(current, set()):
                paths.append(tuple(path + [base]))
            return
        for nxt in sorted(adjacency.get(current, set())):
            if nxt == base or nxt in path:
                continue
            walk(base, nxt, remaining - 1, path + [nxt])

    for hop_count in sorted(hop_set):
        for base in bases:
            if base not in adjacency:
                continue
            walk(base, base, hop_count, [base])

    return paths


def _pricing_steps_from_entries(entries: tuple[dict[str, Any], ...]) -> list[Any]:
    from .opportunity_ranker import RoutePriceStep

    steps: list[Any] = []
    for idx, entry in enumerate(entries, 1):
        rate = Decimal(str(entry.get("rate") or "0"))
        token_in = str(entry.get("token_in") or "")
        token_out = str(entry.get("token_out") or "")
        steps.append(
            RoutePriceStep(
                step_id=idx,
                label=f"CYCLE_HOP_{idx}_PRICE",
                token_in=token_in,
                token_out=token_out,
                pool_id=str(entry.get("pool_id") or ""),
                protocol=str(entry.get("protocol") or ""),
                liquidity_key=str(entry.get("liquidity_key") or entry.get("pool_id") or ""),
                rate=rate,
                effective_price=(Decimal("1") / rate) if rate > 0 else Decimal("0"),
                price_unit=f"{token_in} per {token_out}",
                invariant=str(entry.get("invariant") or ""),
            )
        )
    return steps


def pre_rank_routes(
    rates: dict,
    pools: dict[str, dict],
    *,
    principal_usd: Decimal,
    hops: Iterable[int] = SUPPORTED_HOPS,
    max_quote_options_per_pair: int = 0,
    max_token_paths: int = 0,
    max_pre_ranked: int = 0,
    base_tokens: Iterable[str] | None = None,
) -> tuple[list[PreRankedRoute], dict[str, Any]]:
    """Primary multi-hop discovery for the funnel."""
    counters: Counter[str] = Counter()
    scored_candidates: list[tuple[PreRankedRoute, Decimal]] = []
    token_paths = enumerate_closed_token_paths(
        rates,
        hops=hops,
        base_tokens=base_tokens,
        max_token_paths=max_token_paths,
    )

    discovery_block = getattr(rpc_layer, "BLOCK", 0)
    principal = _decimal(principal_usd)

    for path in token_paths:
        option_sets: list[list[dict[str, Any]]] = []
        missing_edge = False
        for idx in range(len(path) - 1):
            options = _quote_options(
                list(rates.get((path[idx], path[idx + 1]), [])),
                max_quote_options_per_pair,
            )
            if not options:
                missing_edge = True
                break
            option_sets.append(options)
        if missing_edge:
            counters["missing_directional_edge"] += 1
            continue

        for combo in itertools.product(*option_sets):
            pool_sequence = tuple(str(entry.get("pool_id") or "") for entry in combo)
            liquidity_keys = tuple(
                str(entry.get("liquidity_key") or entry.get("pool_id") or "") for entry in combo
            )
            route_classes = tuple(
                str(entry.get("route_class") or "NATIVE_POOL_ROUTE") for entry in combo
            )
            protocol_seq = tuple(str(entry.get("protocol") or "") for entry in combo)
            reject_reasons: list[str] = []
            if any(pool_id not in pools for pool_id in pool_sequence):
                reject_reasons.append("missing_live_pool")
            if any(route_class != "NATIVE_POOL_ROUTE" for route_class in route_classes):
                reject_reasons.append("non_native_route_class")
            if len(liquidity_keys) != len(set(liquidity_keys)):
                reject_reasons.append("duplicate_liquidity_key")

            if reject_reasons:
                counters["rejected_" + "_".join(reject_reasons)] += 1
                continue

            approx_rate = Decimal("1")
            for entry in combo:
                approx_rate *= Decimal(str(entry.get("rate") or "1"))

            raw_delta_usd = (approx_rate - Decimal("1")) * principal
            raw_delta_bps = (approx_rate - Decimal("1")) * Decimal("10000")

            pre_ranked = PreRankedRoute(
                path=path,
                pool_sequence=pool_sequence,
                protocol_seq=protocol_seq,
                liquidity_keys=liquidity_keys,
                route_class_seq=route_classes,
                approximate_gross_rate=approx_rate,
                approximate_raw_delta_usd=raw_delta_usd,
                approximate_raw_delta_bps=raw_delta_bps,
                edge_entries=tuple(combo),
                discovery_block=discovery_block,
            )
            scored_candidates.append((pre_ranked, approx_rate))

    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    if max_pre_ranked > 0:
        scored_candidates = scored_candidates[:max_pre_ranked]

    final_routes = [c[0] for c in scored_candidates]
    stats = {
        "token_paths_considered": len(token_paths),
        "candidates_generated": len(final_routes),
        "rejection_counts": dict(counters),
        "discovery_block": discovery_block,
        "raw_positive_count": sum(
            1 for r in final_routes if r.approximate_gross_rate > Decimal("1")
        ),
    }
    logger.info(
        "pre_rank_routes: generated=%s raw_positive=%s at block=%s",
        len(final_routes),
        stats["raw_positive_count"],
        discovery_block,
    )
    return final_routes, stats


def stage_pre_ranked_route(
    route: PreRankedRoute,
    principal_usd: Decimal | dict | None = None,
    pools: dict | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    slippage_bps: Decimal = Decimal("0"),
    *,
    requested_principal_usd: Decimal | None = None,
) -> dict[str, Any]:
    """
    Convert a PreRankedRoute into a staged candidate.

    Accepts either:
      stage_pre_ranked_route(route, principal_usd, pools)
      stage_pre_ranked_route(route, pools, requested_principal_usd=...)
    """
    # Compatibility: stage_pre_ranked_route(route, pools, requested_principal_usd=...)
    if pools is None and isinstance(principal_usd, dict):
        pools = principal_usd
        principal_usd = requested_principal_usd
    if requested_principal_usd is not None and (
        principal_usd is None or isinstance(principal_usd, dict)
    ):
        principal_usd = requested_principal_usd
    if pools is None:
        pools = {}
    if principal_usd is None or isinstance(principal_usd, dict):
        principal_usd = Decimal("0")
    else:
        principal_usd = _decimal(principal_usd)

    current_block = getattr(rpc_layer, "BLOCK", 0)
    base_token = str(route.path[0]) if route.path else ""
    hop_fee_breakdown: list[Decimal] = []
    hop_fees_total = Decimal("0")
    base_amount_in = Decimal("0")

    if not route_within_lifespan(route.discovery_block, current_block, N_PLUS_4_LIFESPAN):
        record_lifespan_event(
            event_type="EXPIRED",
            discovery_block=route.discovery_block,
            current_block=current_block,
            route=list(route.path),
            status="EXPIRED_AT_STAGING",
        )
        record_stage_event(
            stage="PRE_RANKED",
            status="EXPIRED_LIFESPAN",
            route=list(route.path),
            block=current_block,
        )
        return {
            "status": "rejected",
            "stage": "lifespan_expired",
            "reason": "n+4 block lifespan exceeded",
            "hop_fees_usd": str(hop_fees_total),
        }

    sizing = optimize_route_principal(principal_usd, route.pool_sequence, pools)
    if sizing.selected_principal_usd <= 0:
        record_stage_event(
            stage="SIZING",
            status="FAILED",
            route=list(route.path),
            block=current_block,
        )
        return {
            "status": "rejected",
            "stage": "sizing_failed",
            "reason": "selected_principal_usd <= 0",
            "hop_fees_usd": str(hop_fees_total),
        }

    try:
        px = Decimal(str(token_price_usd(base_token)))
        base_amount_in = (
            sizing.selected_principal_usd / px if px > 0 else Decimal("0")
        )
    except Exception:
        base_amount_in = Decimal("0")

    hop_fee_breakdown, hop_fees_total = _estimate_hop_fees_usd(
        route.edge_entries,
        base_amount_in=base_amount_in,
        base_token=base_token,
        pools=pools,
        pool_sequence=route.pool_sequence,
    )

    try:
        quote = quote_route_for_executor(
            list(route.path),
            list(route.pool_sequence),
            pools,
            base_amount_in,
        )
    except Exception as exc:
        record_stage_event(
            stage="QUOTE",
            status="EXACT_QUOTE_EXCEPTION",
            route=list(route.path),
            block=current_block,
        )
        return {
            "status": "rejected",
            "stage": "exact_quote_exception",
            "reason": type(exc).__name__,
            "detail": str(exc),
            "hop_fees_usd": str(hop_fees_total),
        }

    clmm_proven = bool(
        getattr(quote, "clmm_proven", getattr(quote, "clmm_unquoted", 0) == 0)
    )
    if not clmm_proven:
        record_stage_event(
            stage="QUOTE",
            status="CLMM_UNPROVEN",
            route=list(route.path),
            block=current_block,
        )
        return {
            "status": "rejected",
            "stage": "clmm_quote_unproven",
            "reason": str(getattr(quote, "hop_proofs", [])),
            "hop_fees_usd": str(hop_fees_total),
        }

    amount_out = _decimal(getattr(quote, "amount_out", 0))
    try:
        out_usd = amount_out * Decimal(str(token_price_usd(base_token)))
    except Exception:
        out_usd = amount_out

    # amountOutMin floor from real-market slippage (min->max surplus friendly).
    slip = _decimal(slippage_bps)
    if slip <= 0:
        try:
            slip = _decimal_env("DEFAULT_SLIPPAGE_BPS", "15")
        except Exception:
            slip = Decimal("15")
    extra_min_bps = _decimal_env("MIN_AMOUNT_OUT_BPS", "0")
    min_out_factor = (Decimal("1") - slip / Decimal("10000")) * (
        Decimal("1") - extra_min_bps / Decimal("10000")
    )
    if min_out_factor < 0:
        min_out_factor = Decimal("0")
    amount_out_min = amount_out * min_out_factor
    out_usd_min = out_usd * min_out_factor
    extra_slippage_buffer_usd = out_usd - out_usd_min

    prof = evaluate_profitability(
        out_usd_min,
        sizing.selected_principal_usd,
        hops=len(route.pool_sequence),
        flash_source=flash_source,
        asset=base_token,
    )

    status = "staged_for_executor_truth" if prof.passes_gate else "rejected"
    record_stage_event(
        stage="PRE_RANKED",
        status=status.upper(),
        route=list(route.path),
        block=current_block,
    )
    if status == "staged_for_executor_truth":
        record_lifespan_event(
            event_type="STAGED",
            discovery_block=route.discovery_block,
            current_block=current_block,
            route=list(route.path),
            status="OK",
        )

    return {
        "path": route.path,
        "pool_sequence": route.pool_sequence,
        "protocol_seq": route.protocol_seq,
        "principal_usd": str(sizing.selected_principal_usd),
        "approximate_gross_rate": str(route.approximate_gross_rate),
        "approximate_raw_delta_usd": str(route.approximate_raw_delta_usd),
        "sizing": sizing,
        "flash_source": flash_source.value,
        "raw_gate_eligible": route.approximate_gross_rate > Decimal("1"),
        "status": status,
        "stage": status,
        "reason": (
            "profitability_gate_passed"
            if prof.passes_gate
            else f"net_gain_usd={prof.net_profit_usd} < min_profit={MIN_NET_PROFIT_USD}"
        ),
        "discovery_block": route.discovery_block,
        "current_block": current_block,
        "amount_out": str(amount_out),
        "amount_out_min": str(amount_out_min),
        "slippage_bps": str(slip),
        "min_amount_out_bps": str(extra_min_bps),
        "hop_fees_usd": str(hop_fees_total),
        "net_formula": {
            "raw_delta_usd": prof.gross_amount_out - prof.flashloan.principal_usd,
            "pre_math_raw_delta_usd": route.approximate_raw_delta_usd,
            "flashloan_fee_usd": prof.flashloan.fee_usd,
            "gas_cost_usd": prof.gas_cost_usd,
            "relay_or_private_submit_cost_usd": prof.relay_tip_usd,
            "risk_buffer_usd": prof.risk_buffer_usd,
            "extra_slippage_buffer_usd": str(extra_slippage_buffer_usd),
            "hop_fees_usd": hop_fees_total,
            "hop_fee_breakdown_usd": hop_fee_breakdown,
            "net_gain_usd": prof.net_profit_usd,
            "gas_accounting": prof.gas_accounting,
            "gas_payer": prof.gas_payer,
        },
    }


def build_stage_report(routes: list[PreRankedRoute], stats: dict) -> dict:
    return {
        "routes": [_json_ready(r.__dict__ if hasattr(r, "__dict__") else r) for r in routes],
        "stats": stats,
        "timestamp": time.time(),
        "n_plus_4_lifespan": N_PLUS_4_LIFESPAN,
    }
