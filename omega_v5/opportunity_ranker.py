#!/usr/bin/env python3
# ==============================================================================
# opportunity_ranker.py  —  Net-profit gated opportunity scoring pipeline
#
# Canonical executable cycle shape (fully expanded):
#
#   FLASHLOAN_ASSET
#     -> BUY any mid-token on ANY invariant/protocol/pool
#     -> [hop any further mid-token on ANY invariant]*
#     -> SELL back to FLASHLOAN_ASSET on ANY invariant
#     -> repay flash + keep SURPLUS
# ==============================================================================

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from .config import (
    DYNAMIC_SIZE_IMPACT_PENALTY_BPS,
    DYNAMIC_SIZE_MAX_SEARCH_STEPS,
    DYNAMIC_SIZE_OPT_BINS_USD,
    ENABLE_DYNAMIC_SIZE_OPTIMIZER,
    MAX_ROUTE_IMPACT,
    STABLE_MIN_NET_PROFIT_USD,
    STABLE_RISK_BUFFER_USD,
)
from .cycle_shape import (
    FLASH_CYCLE_STRATEGIES,
    expand_cycle_shape,
    hop_role,
    invariant_for_protocol,
    normalized_cycle_surplus,
    rotate_cycle_to_flash_asset,
    tag_cycle_dict,
)
from .executable_quotes import quote_route_for_executor
from .flash_loan import ( # type: ignore
    FlashSource,
    Profitability,
    calculate_route_economics,
    evaluate_profitability,
    live_min_net_profit_usd,
    build_executable_route_economics,
)
from .oracle_layer import PriceUnavailable, token_price_usd
from .pool_quality import route_quality_metadata, route_quality_passed
from .ranker import CrossPoolSpread
from .sizing import RouteSizing, optimal_flash_for_route, apply_injection_to_route_dict, estimate_route_tvl_usd
from .stable_strategies import PeggedStableSpread
from .route_execution_stager import PreRankedRoute
from .pricing.net_delta import raw_execution_gate_passes, route_within_lifespan
from . import rpc_layer
from .pnl_tracker import record_lifespan_event, record_stage_event

logger = logging.getLogger("omega.ranker")
logger.setLevel(logging.INFO)

SHAPE_FORMULA = (
    "FLASHLOAN_ASSET -> BUY_ANY_MID(ANY_INVARIANT) "
    "[-> ANY_MID(ANY_INVARIANT)]* -> SELL_TO_FLASH(ANY_INVARIANT) -> SURPLUS"
)


def _default_slippage_bps() -> Decimal:
    try:
        return Decimal(str(os.environ.get("DEFAULT_SLIPPAGE_BPS", "15") or "15"))
    except Exception:
        return Decimal("15")


def _min_amount_out_bps() -> Decimal:
    """Extra haircut on amountOutMin beyond slippage. 0 = pure slippage floor."""
    try:
        return Decimal(str(os.environ.get("MIN_AMOUNT_OUT_BPS", "0") or "0"))
    except Exception:
        return Decimal("0")


def amount_out_min_from_quote(amount_out: Decimal, slippage_bps: Decimal) -> Decimal:
    """
    Min-out setting for min -> max surplus capture:
      amountOutMin = amount_out * (1 - slippage_bps/10000) * (1 - min_amount_out_bps/10000)

    With MIN_AMOUNT_OUT_BPS=0 this is pure market-slippage protection and does not
    artificially crush small surplus.
    """
    slip = max(Decimal("0"), Decimal(str(slippage_bps))) / Decimal("10000")
    extra = max(Decimal("0"), _min_amount_out_bps()) / Decimal("10000")
    factor = (Decimal("1") - slip) * (Decimal("1") - extra)
    if factor < 0:
        factor = Decimal("0")
    return Decimal(str(amount_out)) * factor


@dataclass(frozen=True)
class RoutePriceStep:
    step_id: int
    label: str
    token_in: str
    token_out: str
    pool_id: str
    protocol: str
    liquidity_key: str
    rate: Decimal
    effective_price: Decimal
    price_unit: str
    invariant: str


@dataclass(frozen=True)
class LiveOpportunity:
    """Executable opportunity with full provenance for truth + execution."""

    path: tuple[str, ...]
    pool_sequence: tuple[str, ...]
    protocol_seq: tuple[str, ...]
    profitability: Profitability
    gross_rate: Decimal = Decimal("0")
    gross_out_usd: Decimal = Decimal("0")
    flash_source: FlashSource = FlashSource.BALANCER
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    block_detected: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Converts the opportunity to a dictionary format compatible with legacy reporting tools."""
        base_token = self.path[0] if self.path else ""
        try:
            base_price = token_price_usd(base_token)
        except PriceUnavailable:
            base_price = Decimal("0")

        principal_usd = self.profitability.flashloan.principal_usd
        base_amount_in = principal_usd / base_price if base_price > 0 else Decimal("0")

        # Attempt to get the detailed expense breakdown if it exists
        expense_breakdown = {}
        if hasattr(self.profitability, "expense_breakdown") and self.profitability.expense_breakdown:
            if is_dataclass(self.profitability.expense_breakdown):
                expense_breakdown = asdict(self.profitability.expense_breakdown)
            elif isinstance(self.profitability.expense_breakdown, dict):
                expense_breakdown = self.profitability.expense_breakdown

        return {
            "path": self.path,
            "pool_sequence": self.pool_sequence,
            "protocol_seq": self.protocol_seq,
            "opp_id": self.metadata.get("opp_id", f"OPP-RUST-{id(self)}"),
            "status": "staged_for_executor_truth",
            "stage": "staged_for_executor_truth",
            "reason": "profitability_gate_passed",
            "selected_principal_usd": principal_usd,
            "principal_usd": principal_usd,
            "selected_base_amount_in": base_amount_in,
            "base_token": base_token,
            "base_token_usd": base_price,
            "net_gain_usd": self.profitability.net_profit_usd,
            "net_formula": expense_breakdown,
            "sizing": self.metadata.get("sizing", {}),
            "flash_source": self.flash_source.value,
            "discovery_block": self.block_detected,
            "current_block": getattr(rpc_layer, "BLOCK", 0),
        }


def _normalize_pre_ranked(candidate: Any) -> dict:
    """Convert PreRankedRoute / dict / cycle object into a scoring dict."""
    if isinstance(candidate, PreRankedRoute):
        return {
            "path": list(candidate.path),
            "edges": list(candidate.edge_entries),
            "pool_sequence": list(candidate.pool_sequence),
            "protocol_seq": list(candidate.protocol_seq),
            "discovery_block": getattr(candidate, "discovery_block", 0),
            "approximate_gross_rate": candidate.approximate_gross_rate,
        }
    if isinstance(candidate, dict):
        path = list(candidate.get("path") or [])
        edges = list(candidate.get("edges") or candidate.get("edge_entries") or [])
        pool_sequence = list(
            candidate.get("pool_sequence")
            or [e.get("pool_id") for e in edges if e]
            or []
        )
        protocol_seq = list(
            candidate.get("protocol_seq")
            or [e.get("protocol") for e in edges if e]
            or []
        )
        return {
            "path": path,
            "edges": edges,
            "pool_sequence": pool_sequence,
            "protocol_seq": protocol_seq,
            "discovery_block": candidate.get("discovery_block")
            or candidate.get("block_detected")
            or 0,
            "approximate_gross_rate": candidate.get("approximate_gross_rate")
            or candidate.get("gross_rate")
            or 0,
        }
    # Bellman / object-style candidates
    path = list(getattr(candidate, "path", ()) or [])
    edges = list(getattr(candidate, "edge_entries", ()) or getattr(candidate, "edges", ()) or [])
    pool_sequence = list(
        getattr(candidate, "pool_sequence", ())
        or [e.get("pool_id") for e in edges if isinstance(e, dict)]
        or []
    )
    protocol_seq = list(
        getattr(candidate, "protocol_seq", ())
        or [e.get("protocol") for e in edges if isinstance(e, dict)]
        or []
    )
    return {
        "path": path,
        "edges": edges,
        "pool_sequence": pool_sequence,
        "protocol_seq": protocol_seq,
        "discovery_block": getattr(candidate, "discovery_block", 0)
        or getattr(candidate, "block_detected", 0)
        or 0,
        "approximate_gross_rate": getattr(candidate, "approximate_gross_rate", 0)
        or getattr(candidate, "gross_rate", 0)
        or 0,
    }


def _quote_route_amount(
    path: tuple[str, ...],
    pool_sequence: tuple[str, ...],
    pools: dict,
    amount_in: Decimal,
) -> tuple[Decimal, Any]:
    """Real market quote via executable_quotes (not a placeholder)."""
    quote = quote_route_for_executor(
        list(path),
        list(pool_sequence),
        pools,
        amount_in,
    )
    amount_out = Decimal(str(getattr(quote, "amount_out", 0) or 0))
    return amount_out, quote


def _score_closed_path(
    *,
    path: tuple[str, ...],
    pool_seq: tuple[str, ...],
    proto_seq: tuple[str, ...],
    pools: dict,
    principal_usd: Decimal,
    slippage_bps: Decimal,
    flash_source: FlashSource,
    disc_block: int,
    pre_math_rate: Optional[Decimal] = None,
    min_net_override: Optional[Decimal] = None,
    risk_buffer_override: Optional[Decimal] = None,
    strategy: str = "FLASH_MULTI_MID_CYCLE"
) -> LiveOpportunity | None:
    current_block = getattr(rpc_layer, "BLOCK", 0)
    opp_id_for_logs = f"{strategy}-{'-'.join(path)}-{'-'.join(pool_seq)}"

    # This function is designed to fail closed, returning `None` on any failure.
    # It no longer returns a tuple `(None, "reason")` on failure, which was
    # a critical bug as tuples are truthy.

    if len(path) < 3 or path[0] != path[-1]:
        record_stage_event(
            stage="RANK",
            status="PATH_MISALIGN",
            route=list(path),
            opp_id=opp_id_for_logs,
            block=current_block,
        )
        return None

    if disc_block and not route_within_lifespan(disc_block, current_block):
        record_lifespan_event(
            event_type="EXPIRED",
            discovery_block=disc_block,
            current_block=current_block,
            route=list(path),
            opp_id=opp_id_for_logs,
            status="EXPIRED_AT_RANK",
        )
        return None

    try:
        base_price = Decimal(str(token_price_usd(path[0])))
    except Exception:
        base_price = Decimal("0")
    if base_price <= 0 or principal_usd <= 0:
        logger.debug(
            "Path %s rejected at pre-flight: invalid base price (%.4f) or principal (%.2f)",
            path, base_price, principal_usd
        )
        return None

    # Use the authoritative build_executable_route_economics early.
    # This reduces duplication, trusts the central sizing + profitability,
    # and makes the Python coordinator thinner.
    econ = build_executable_route_economics(
        path=path,
        pool_sequence=pool_seq,
        pools=pools,
        principal_usd=principal_usd,
        flash_source=flash_source,
        slippage_bps=slippage_bps,
    )

    if not econ.get("passes_gate", False):
        logger.debug(
            "Path %s rejected at authoritative economics: %s",
            path, econ.get("reason", "gate_failed")
        )
        return None

    selected_principal_usd = Decimal(str(econ.get("selected_principal_usd", principal_usd)))
    gross_out_usd = Decimal(str(econ.get("gross_out_usd", "0")))

    # Build minimal profitability from the authoritative result
    flash_params = FlashLoanParams(
        source=flash_source,
        asset=path[0],
        principal_usd=selected_principal_usd,
        fee_bps=Decimal("0"),
        fee_usd=Decimal(str(econ.get("flash_fee_usd", "0"))),
        repayment_usd=selected_principal_usd + Decimal(str(econ.get("flash_fee_usd", "0"))),
    )
    final_profitability = Profitability(
        gross_amount_out=gross_out_usd,
        flashloan=flash_params,
        gas_cost_usd=Decimal(str(econ.get("gas_cost_usd", "0"))),
        relay_tip_usd=Decimal(str(econ.get("relay_tip_usd", "0"))),
        risk_buffer_usd=Decimal("0.005"),
        net_profit_usd=Decimal(str(econ.get("net_profit_usd", "0"))),
        profit_to_gas=Decimal("0"),
        passes_gate=True,
        expense_breakdown=econ.get("profitability", {}).get("expense_breakdown"),
    )

    # Metadata from authoritative source
    metadata = econ.get("sizing", {})
    metadata["slippage_bps"] = str(slippage_bps)
    metadata["pre_math_gross_rate"] = str(pre_math_rate) if pre_math_rate else None
    metadata["strategy"] = strategy
    metadata["principal_usd"] = str(selected_principal_usd)
    metadata["authoritative_economics"] = True  # proof we used central path

    gross_rate = gross_out_usd / selected_principal_usd if selected_principal_usd > 0 else Decimal("0")

    opp = LiveOpportunity(
        path=path,
        pool_sequence=pool_seq,
        protocol_seq=proto_seq,
        profitability=final_profitability,
        gross_rate=gross_rate,
        gross_out_usd=gross_out_usd,
        flash_source=flash_source,
        metadata=metadata,
        block_detected=int(disc_block or current_block or 0),
    )
    record_stage_event(
        stage="RANK",
        status="SCORED",
        route=list(path),
        opp_id=opp_id_for_logs,
        block=current_block,
    )
    return opp


def score_opportunities(
    candidates: list[Any],
    pools: dict,
    principal_usd: Decimal,
    *,
    slippage_bps: Decimal | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
) -> list[LiveOpportunity]:
    """Score pre-ranked / cycle candidates into LiveOpportunity with real quotes + slippage."""
    slip = Decimal(str(slippage_bps if slippage_bps is not None else _default_slippage_bps()))
    opportunities: list[LiveOpportunity] = []
    current_block = getattr(rpc_layer, "BLOCK", 0)

    for cand in candidates:
        norm = _normalize_pre_ranked(cand)
        path = tuple(str(t) for t in (norm.get("path") or []))
        pool_seq = tuple(str(p) for p in (norm.get("pool_sequence") or []) if p)
        proto_seq = tuple(str(p) for p in (norm.get("protocol_seq") or []))
        disc_block = int(norm.get("discovery_block") or current_block or 0)
        try:
            pre_math_rate = Decimal(str(norm.get("approximate_gross_rate") or "0"))
        except Exception:
            pre_math_rate = Decimal("0")

        opp = _score_closed_path(
            path=path,
            pool_seq=pool_seq,
            proto_seq=proto_seq,
            pools=pools,
            principal_usd=principal_usd,
            slippage_bps=slip,
            flash_source=flash_source,
            disc_block=disc_block,
            pre_math_rate=pre_math_rate if pre_math_rate > 0 else None,
            strategy="FLASH_MULTI_MID_CYCLE",
        )
        if opp is not None:
            opportunities.append(opp)

    opportunities.sort(key=lambda o: o.profitability.net_profit_usd, reverse=True)
    logger.info(
        "score_opportunities: %s live opps at block=%s slip_bps=%s",
        len(opportunities),
        current_block,
        slip,
    )
    return opportunities


def score_cross_pool_spreads(
    spreads: Iterable[CrossPoolSpread],
    pools: dict,
    principal_usd: Decimal,
    *,
    slippage_bps: Decimal | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
) -> list[LiveOpportunity]:
    """Score two-leg cross-pool spreads with the same slippage-aware math path."""
    slip = Decimal(str(slippage_bps if slippage_bps is not None else _default_slippage_bps()))
    out: list[LiveOpportunity] = []
    current_block = getattr(rpc_layer, "BLOCK", 0)

    for spread in spreads or []:
        path = tuple(str(t) for t in (getattr(spread, "path", None) or []))
        if len(path) == 2:
            # Normalize to closed flash cycle [A, B, A]
            path = (path[0], path[1], path[0])
        elif len(path) >= 3 and path[0] != path[-1]:
            path = tuple(list(path) + [path[0]])

        pool_seq = tuple(str(p) for p in (getattr(spread, "pool_sequence", None) or []) if p)
        if not pool_seq:
            buy_id = str(getattr(spread, "buy_pool_id", "") or "")
            sell_id = str(getattr(spread, "sell_pool_id", "") or "")
            pool_seq = tuple(p for p in (buy_id, sell_id) if p)

        proto_seq = tuple(str(p) for p in (getattr(spread, "protocol_seq", None) or []) if p)
        if not proto_seq:
            proto_seq = tuple(
                p
                for p in (
                    str(getattr(spread, "buy_protocol", "") or ""),
                    str(getattr(spread, "sell_protocol", "") or ""),
                )
                if p
            )

        try:
            pre_math_rate = Decimal(str(getattr(spread, "round_trip_rate", "0") or "0"))
        except Exception:
            pre_math_rate = Decimal("0")

        opp = _score_closed_path(
            path=path,
            pool_seq=pool_seq,
            proto_seq=proto_seq,
            pools=pools,
            principal_usd=principal_usd,
            slippage_bps=slip,
            flash_source=flash_source,
            disc_block=current_block,
            pre_math_rate=pre_math_rate if pre_math_rate > 0 else None,
            strategy="CROSS_POOL_TWO_LEG",
        )
        if opp is not None:
            out.append(opp)

    out.sort(key=lambda o: o.profitability.net_profit_usd, reverse=True)
    return out


def score_pegged_stable_spreads(
    spreads: Iterable[Any],
    pools: dict,
    principal_usd: Decimal,
    *,
    slippage_bps: Decimal | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
) -> list[LiveOpportunity]:
    """Score pegged stable spreads with lower min-net / risk buffer overrides."""
    slip = Decimal(str(slippage_bps if slippage_bps is not None else _default_slippage_bps()))
    out: list[LiveOpportunity] = []
    current_block = getattr(rpc_layer, "BLOCK", 0)

    for item in spreads or []:
        spread = getattr(item, "spread", item)
        path = tuple(str(t) for t in (getattr(spread, "path", None) or []))
        if len(path) == 2:
            path = (path[0], path[1], path[0])
        elif len(path) >= 3 and path[0] != path[-1]:
            path = tuple(list(path) + [path[0]])

        pool_seq = tuple(str(p) for p in (getattr(spread, "pool_sequence", None) or []) if p)
        if not pool_seq:
            buy_id = str(getattr(spread, "buy_pool_id", "") or "")
            sell_id = str(getattr(spread, "sell_pool_id", "") or "")
            pool_seq = tuple(p for p in (buy_id, sell_id) if p)

        proto_seq = tuple(str(p) for p in (getattr(spread, "protocol_seq", None) or []) if p)
        try:
            pre_math_rate = Decimal(str(getattr(spread, "round_trip_rate", "0") or "0"))
        except Exception:
            pre_math_rate = Decimal("0")

        opp = _score_closed_path(
            path=path,
            pool_seq=pool_seq,
            proto_seq=proto_seq,
            pools=pools,
            principal_usd=principal_usd,
            slippage_bps=slip,
            flash_source=flash_source,
            disc_block=current_block,
            pre_math_rate=pre_math_rate if pre_math_rate > 0 else None,
            min_net_override=STABLE_MIN_NET_PROFIT_USD,
            risk_buffer_override=STABLE_RISK_BUFFER_USD,
            strategy="PEGGED_STABLE_TWO_LEG",
        )
        if opp is not None:
            out.append(opp)

    out.sort(key=lambda o: o.profitability.net_profit_usd, reverse=True)
    return out


def print_live_opportunities(
    opportunities: list[LiveOpportunity],
    max_count: int = 50,
) -> None:
    """Operator-facing ranked dump."""
    rows = list(opportunities or [])[: max(0, int(max_count))]
    if not rows:
        print("   (no live opportunities)")
        return
    print(f"   Top {len(rows)} opportunities (high → low net):")
    for idx, op in enumerate(rows, 1):
        path_s = "->".join(op.path)
        net = op.profitability.net_profit_usd
        gross = op.gross_rate
        pre = (op.metadata or {}).get("pre_math_gross_rate")
        slip = (op.metadata or {}).get("slippage_bps")
        amin = (op.metadata or {}).get("amount_out_min")
        print(
            f"     #{idx:03d} net=${net:,.6f} gross_rate={gross:.8f} "
            f"pre_math={pre} slip_bps={slip} amount_out_min={amin} path={path_s}"
        )


def _cycle_to_live_opportunity(
    cycle: dict,
    pools: dict,
    principal_usd: Decimal,
) -> LiveOpportunity | None:
    """Legacy bridge used by older callers. Rerouted to the canonical scoring path."""
    return _score_closed_path(
        path=tuple(str(t) for t in (cycle.get("path") or [])),
        pool_seq=tuple(str(p) for p in (cycle.get("pool_sequence") or []) if p),
        proto_seq=tuple(str(p) for p in (cycle.get("protocol_seq") or [])),
        pools=pools,
        principal_usd=principal_usd,
        slippage_bps=_default_slippage_bps(), # Uses default slippage
        flash_source=FlashSource.BALANCER,
        disc_block=int(cycle.get("block_detected") or cycle.get("discovery_block") or 0),
        pre_math_rate=Decimal(str(cycle.get("gross_rate", "0"))),
        strategy=str(cycle.get("strategy") or "LEGACY_CYCLE"),
    )
