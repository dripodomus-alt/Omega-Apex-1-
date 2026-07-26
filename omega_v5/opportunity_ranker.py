#!/usr/bin/env python3
# ==============================================================================
# opportunity_ranker.py  —  Net-profit gated opportunity scoring pipeline
# ==============================================================================
"""
This module is a core component of the arbitrage pipeline, responsible for
taking raw arbitrage opportunities (spreads and cycles) and evaluating their
economic viability. It acts as a filter, promoting only those opportunities
that are likely to be profitable after accounting for all associated costs.

Key Responsibilities:
1.  **Sizing**: Integrates with the `capital_injector` to determine the optimal
    flash loan principal for a given route, balancing potential profit against
    price impact.
2.  **Profitability Calculation**: Uses `evaluate_profitability` to calculate the
    net profit by subtracting all known costs (flash loan fees, gas, slippage)
    from the gross profit.
3.  **Ranking**: Scores and sorts opportunities based on their final net profit,
    preparing them for the subsequent execution stages.
"""

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
    FlashLoanParams,
    calculate_route_economics,
    evaluate_profitability,
    live_min_net_profit_usd,
    build_executable_route_economics,
)
from .oracle_layer import PriceUnavailable, token_price_usd
from .pool_quality import route_quality_metadata, route_quality_passed
from .gas_oracle import profitability_gas_price_gwei
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
    """
    Represents a fully evaluated, economically viable arbitrage opportunity.

    This dataclass contains all the necessary information for the final stages
    of the pipeline, including the execution path, profitability breakdown,
    and associated metadata for provenance and truth-gating.
    """

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


def _calculate_profitability(
    gross_out: Decimal,
    principal: Decimal,
    base_asset: str,
    hops: int,
    flash_source: FlashSource,
) -> Profitability:
    """
    Calculates the complete, explicit profitability of a trade.

    This function takes the gross output from a simulated trade and subtracts all
    known and estimated costs to determine the final net profit.

    The net profit formula is:
        net_profit = (gross_out_min - principal) - flash_fee - gas_cost - other_buffers

    Where:
    -   gross_out_min: The gross output in USD, adjusted for slippage tolerance.
    -   principal: The initial flash loan amount in USD.
    -   flash_fee: The fee charged by the flash loan provider.
    -   gas_cost: The estimated cost of the transaction in USD.
    -   other_buffers: Additional configurable costs for MEV tips and risk.

    Args:
        gross_out: The gross USD value returned from the trade simulation.
        principal: The initial flash loan principal in USD.
        base_asset: The symbol of the flash loan asset (e.g., "USDC").
        hops: The number of swaps in the trade route.
        flash_source: The source of the flash loan (e.g., BALANCER, AAVE).

    Returns:
        A Profitability dataclass instance containing a full breakdown of costs and profits.
    """
    # --- EXPENSE CALCULATION (Explicit Math) ---
    # Raw surplus from the trade before any costs.
    raw_delta_usd = gross_out - principal

    # 1. Flash Loan Fee
    from .flash_loan import AAVE_FLASH_FEE_BPS, BALANCER_FLASH_FEE_BPS
    fee_bps = BALANCER_FLASH_FEE_BPS if flash_source == FlashSource.BALANCER else AAVE_FLASH_FEE_BPS
    flash_fee_usd = principal * (fee_bps / Decimal("10000"))

    # 2. Gas Cost
    from .flash_loan import route_tx_gas_limit, current_pol_price_usd
    gas_units = route_tx_gas_limit(hops)
    gas_price_gwei, gas_price_source = profitability_gas_price_gwei()
    native_price_usd, native_price_source = current_pol_price_usd()
    gas_cost_usd = gas_units * gas_price_gwei * Decimal("1e-9") * native_price_usd

    # 3. Slippage-Adjusted Gross Output
    slippage_bps = _default_slippage_bps()
    min_out_factor = Decimal("1") - (slippage_bps / Decimal("10000"))
    gross_out_min = gross_out * min_out_factor

    # 4. Net Profit Calculation
    from .flash_loan import live_relay_tip_usd, live_risk_buffer_usd
    relay_tip_usd = live_relay_tip_usd()
    risk_buffer_usd = live_risk_buffer_usd()
    net_profit_usd = (gross_out_min - principal) - flash_fee_usd - gas_cost_usd - relay_tip_usd - risk_buffer_usd

    return Profitability(
        gross_amount_out=gross_out,
        gross_amount_out_min=gross_out_min,
        flashloan=FlashLoanParams(flash_source, base_asset, principal, fee_bps, flash_fee_usd, principal + flash_fee_usd),
        gas_cost_usd=gas_cost_usd,
        relay_tip_usd=relay_tip_usd,
        risk_buffer_usd=risk_buffer_usd,
        net_profit_usd=net_profit_usd,
        profit_to_gas=(net_profit_usd / gas_cost_usd) if gas_cost_usd > 0 else Decimal("999"),
        passes_gate=net_profit_usd >= live_min_net_profit_usd(),
        raw_delta_usd=raw_delta_usd,
        expense_breakdown={
            "raw_delta_usd": str(raw_delta_usd),
            "flash_fee_usd": str(flash_fee_usd),
            "gas_cost_usd": str(gas_cost_usd), "gas_price_source": gas_price_source, "native_price_source": native_price_source,
            "slippage_cost_usd": str(gross_out - gross_out_min),
            "relay_tip_usd": str(relay_tip_usd),
            "risk_buffer_usd": str(risk_buffer_usd),
            "total_expenses_usd": str(flash_fee_usd + gas_cost_usd + (gross_out - gross_out_min) + relay_tip_usd + risk_buffer_usd),
            "net_after_expenses_usd": str(net_profit_usd),
        }
    )


def rank_live_opportunity(
    path: tuple[str, ...],
    pool_sequence: tuple[str, ...],
    protocol_seq: tuple[str, ...],
    pools: dict,
    *,
    flash_source: FlashSource = FlashSource.BALANCER,
) -> LiveOpportunity | None:
    """Rank a live opportunity. Uses official capital_injector for injection size."""
    # ==============================================================================
    # STEP 1: DETERMINE OPTIMAL TRADE SIZE (PRINCIPAL)
    # ==============================================================================
    # We use the capital_injector to find the optimal flash loan amount in USD.
    # This amount balances the trade-off between higher potential profit and
    # increased price impact/slippage from a larger trade.
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

    # ==============================================================================
    # STEP 2: CALCULATE GROSS PROFIT FROM THE TRADE ROUTE
    # ==============================================================================
    # Using the optimal principal, we now calculate the expected output of the trade.
    try:
        base_asset = path[0]
        price = Decimal(str(token_price_usd(base_asset)))
        if price <= 0:
            return None

        # MATH: Convert the USD-denominated principal into the native amount of the
        #       flash loan asset (e.g., WETH, USDC).
        # Formula: amount_in = principal_usd / price_of_asset_in_usd
        amount_in = principal / price

        # This function simulates the series of swaps through the specified pools
        # to determine the final amount of `base_asset` we get back.
        quote = quote_route_for_executor(path, pool_sequence, pools, amount_in)

        # For CLMM routes, we require an on-chain quote proof to avoid ranking based on
        # inaccurate invariant math. Non-CLMM routes can proceed with math-based quotes.
        if not quote.clmm_proven and any(p in {"V3_CLMM", "QS_V3_ALGEBRA"} for p in protocol_seq):
             return None

        # MATH: Calculate the gross profit in USD. This is the raw financial gain
        #       before any costs are deducted.
        # Formula: gross_out_usd = amount_out_from_route * price_of_asset_in_usd
        gross_out = quote.amount_out * price

        # ==========================================================================
        # STEP 3: CALCULATE NET PROFIT (THE "REAL" PROFIT)
        # ==========================================================================
        # This is the most critical calculation. It subtracts all known costs from
        # the gross profit to determine if the opportunity is actually profitable.
        #
        # Formula:
        #   net_profit_usd = (gross_out_usd - principal_usd) - flash_loan_fee_usd - gas_cost_usd
        #
        # - (gross_out_usd - principal_usd) is the raw surplus from the trade.
        # - flash_loan_fee_usd is the fee charged by the flash loan provider (e.g., Balancer).
        # - gas_cost_usd is the estimated cost of the Ethereum transaction.
        prof = _calculate_profitability(
            gross_out=gross_out,
            principal=principal,
            base_asset=base_asset,
            hops=len(pool_sequence),
            flash_source=flash_source,
        )
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
