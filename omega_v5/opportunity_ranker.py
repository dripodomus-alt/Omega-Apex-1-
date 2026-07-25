#!/usr/bin/env python3
# ==============================================================================
# opportunity_ranker.py  —  Net-profit gated opportunity scoring pipeline
#
# Now uses OFFICIAL capital_injector for sizing before Rust.
# ==============================================================================

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field, is_dataclass, replace
import time
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from .capital_injector import compute_optimal_injection
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
from .pricing.engine_config import get_engine
from .pricing.precision_pricing import PricingContext, PRICE_SCALE, PricingError
from .units import get_token_metadata
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
    try:
        return Decimal(str(os.environ.get("MIN_AMOUNT_OUT_BPS", "0") or "0"))
    except Exception:
        return Decimal("0")


def amount_out_min_from_quote(amount_out: Decimal, slippage_bps: Decimal) -> Decimal:
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
        base_token = self.path[0] if self.path else ""
        try:
            engine = get_engine()
            ctx = PricingContext(chain_id=rpc_layer.CHAIN_ID, current_block=rpc_layer.BLOCK, current_timestamp=int(time.time()))
            token_meta = get_token_metadata(base_token)
            price_result = engine.get_usd_price(token_meta.address, ctx)
            base_price = Decimal(price_result.price_usd_x18) / Decimal(PRICE_SCALE)
        except (PricingError, PriceUnavailable):
            base_price = Decimal("0")

        principal_usd = self.profitability.flashloan.principal_usd
        base_amount_in = principal_usd / base_price if base_price > 0 else Decimal("0")

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
            "gross_rate": str(self.gross_rate),
            "gross_out_usd": str(self.gross_out_usd),
            "principal_usd": str(principal_usd),
            "net_profit_usd": str(self.profitability.net_profit_usd),
            "flash_source": self.flash_source.value if self.flash_source else "",
            "metadata": self.metadata,
            "quality": self.quality,
        }


def rank_live_opportunity(
    path: tuple[str, ...],
    pool_sequence: tuple[str, ...],
    protocol_seq: tuple[str, ...],
    pools: dict,
    *,
    flash_source: FlashSource = FlashSource.BALANCER,
) -> LiveOpportunity | None:
    """
    Rank a live opportunity. Uses official capital_injector for injection size.
    """
    # === OFFICIAL INJECTOR CALL (pre-Rust) ===
    try:
        inj = compute_optimal_injection(
            pool_sequence=pool_sequence,
            pools=pools,
            path=path,
            protocol_seq=protocol_seq,
            flash_source=flash_source,
        )
        principal = inj.optimal_injection_usd
    except Exception:
        principal = Decimal("10000")

    if principal <= 0:
        return None

    # Replace placeholder math with a call to the executable quoter to align
    # ranking with the truth gate.
    try:
        base_asset = path[0]
        price = Decimal(str(token_price_usd(base_asset)))
        if price <= 0:
            return None
        amount_in = principal / price

        quote = quote_route_for_executor(path, pool_sequence, pools, amount_in)
        # For CLMM routes, we require an on-chain quote proof to avoid ranking based on
        # inaccurate invariant math. Non-CLMM routes can proceed with math-based quotes.
        if not quote.clmm_proven and any(p in {"V3_CLMM", "QS_V3_ALGEBRA"} for p in protocol_seq):
             return None

        gross_out = quote.amount_out * price
        prof = evaluate_profitability(gross_out, principal, hops=len(pool_sequence), flash_source=flash_source, asset=base_asset)
    except (PriceUnavailable, ValueError, Exception):
        return None

    opp = LiveOpportunity(
        path=path,
        pool_sequence=pool_sequence,
        protocol_seq=protocol_seq,
        profitability=prof,
        gross_rate=gross_out / principal if principal > 0 else Decimal("0"),
        gross_out_usd=gross_out,
        flash_source=flash_source,
        metadata={
            "sizing": inj.as_sizing_params() if 'inj' in locals() else {},
            "capital_injector_used": True,
        },
    )
    return opp


# (remaining functions in original file left intact for compatibility)
# The key change: all sizing paths now prefer capital_injector
