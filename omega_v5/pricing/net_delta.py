"""
net_delta.py — Dimensionally correct net profit engine for APEX-OMEGA.

Implements the mandatory economic model from the audit:
- Executable round-trip using MIN_OUTs only.
- Raw integer accounting for execution.
- Correct conversion: FLASH_USD → MID_UNITS → SPREAD_RATIO.
- No double deduction of embedded fees/impact.
- All non-embedded expenses deducted separately from raw delta.
"""

from decimal import Decimal, ROUND_FLOOR
from typing import Any, Dict, Optional, cast

from ..units import usd_expense_to_base_raw
from ..flash_loan import (
    ExpenseBreakdown,
    FlashLoanParams,
    FlashSource,
    evaluate_profitability,
    Profitability,
    deduct_expenses_from_raw_delta,
    estimate_static_gas_usd,
)
from ..rpc_layer import TOKEN_DECIMALS


def _to_raw(symbol: str, amount: Decimal) -> int:
    dec = int(TOKEN_DECIMALS.get(symbol, 18))
    raw = amount * (Decimal(10) ** dec)
    return max(0, int(raw.to_integral_value(rounding=ROUND_FLOOR)))


def _from_raw(symbol: str, raw: int) -> Decimal:
    dec = int(TOKEN_DECIMALS.get(symbol, 18))
    return Decimal(int(raw)) / (Decimal(10) ** dec)


def raw_execution_gate_passes(
    sell_amount_out_raw: int,
    flash_principal_raw: int,
    flash_fee_raw: int,
    gas_cost_raw: int,
    relay_cost_raw: int,
    risk_buffer_raw: int,
    minimum_profit_raw: int,
) -> bool:
    """
    Canonical raw-integer execution gate.
    sellAmountOutRaw > flashPrincipalRaw + totalCostsRaw + minimumProfitRaw

    This is the single source of truth for whether a route is profitable
    enough to stage for execution.
    """
    total_costs_raw = flash_fee_raw + gas_cost_raw + relay_cost_raw + risk_buffer_raw
    return sell_amount_out_raw > (flash_principal_raw + total_costs_raw + minimum_profit_raw)


def route_within_lifespan(
    discovery_block: int,
    current_block: int,
    max_blocks: int = 4,
) -> bool:
    """
    Per-route stalemate / lifespan check.
    A route discovered at block `n` must be executed by block `n + max_blocks`.
    No artificial delays. Execute as soon as possible.
    """
    if not discovery_block or not current_block:  # Fails for None or 0
        return False
    return discovery_block <= current_block <= (discovery_block + max_blocks)


def simulate_route_with_real_min_out(
    base_asset: str,
    flash_principal_usd: Decimal,
    buy_min_out_raw: int,
    sell_min_out_raw: int,
    flash_fee_raw: int = 0,
    gas_cost_raw: int = 0,
    relay_cost_raw: int = 0,
    risk_buffer_raw: int = 0,
    minimum_profit_raw: int = 1,
) -> Dict[str, Any]:
    """
    End-to-end simulation helper.
    Takes real min_out values (from eth_call / fork / executable quote)
    and feeds them directly into the canonical raw gate.
    """
    flash_principal_raw = _to_raw(base_asset, flash_principal_usd)

    passes = raw_execution_gate_passes(
        sell_amount_out_raw=sell_min_out_raw,
        flash_principal_raw=flash_principal_raw,
        flash_fee_raw=flash_fee_raw,
        gas_cost_raw=gas_cost_raw,
        relay_cost_raw=relay_cost_raw,
        risk_buffer_raw=risk_buffer_raw,
        minimum_profit_raw=minimum_profit_raw,
    )

    gross_surplus_raw = sell_min_out_raw - flash_principal_raw
    total_costs_raw = flash_fee_raw + gas_cost_raw + relay_cost_raw + risk_buffer_raw
    # Economic Net Profit (π)
    economic_net_raw = gross_surplus_raw - total_costs_raw
    # Headroom (π - m)
    headroom_raw = economic_net_raw - minimum_profit_raw

    return {
        "passes_raw_gate": passes,
        "flash_principal_raw": flash_principal_raw,
        "buy_min_out_raw": buy_min_out_raw,
        "sell_min_out_raw": sell_min_out_raw,
        "gross_surplus_raw": gross_surplus_raw,
        "total_costs_raw": total_costs_raw,
        "economic_net_raw": economic_net_raw,
        "headroom_raw": headroom_raw,
        "flash_fee_raw": flash_fee_raw,
        "gas_cost_raw": gas_cost_raw,
        "relay_cost_raw": relay_cost_raw,
        "risk_buffer_raw": risk_buffer_raw,
        "minimum_profit_raw": minimum_profit_raw,
    }


def build_executable_route_economics(
    *,
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    base_asset: str,
    hops: int,
    flash_source: FlashSource,
    discovery_block: int,
    base_usd_price: Decimal | None = None,
    min_net_profit_usd: Decimal | None = None,
    risk_buffer_usd: Decimal | None = None,
    impact_penalty_usd: Decimal = Decimal("0"),
    builder_fee_usd: Decimal = Decimal("0"),
) -> dict[str, Any]:
    """
    Single entry point to build the full USD and raw economic profile for a route.
    It calls evaluate_profitability and then derives all raw-unit fields for the
    execution gate, ensuring USD and raw gates are perfectly aligned.
    """
    from ..oracle_layer import token_price_usd
    from ..units import to_raw_units, usd_to_token

    # 1. Evaluate USD-based profitability
    # This is the correct function to get live gas/fees and the full profitability profile.
    prof: Profitability = evaluate_profitability(
        gross_amount_out_usd=gross_amount_out_usd,
        principal_usd=principal_usd,
        hops=hops,
        flash_source=flash_source,
        asset=base_asset,
        min_net_profit_usd_override=min_net_profit_usd,
        risk_buffer_usd_override=risk_buffer_usd,
        impact_penalty_usd=impact_penalty_usd,
        builder_fee_usd=builder_fee_usd,
        as_of_block=discovery_block,
    )

    # 2. Build raw-unit fields from the USD profitability breakdown
    # The price is needed to convert USD values (principal, gross_out) to token units.
    price = base_usd_price if base_usd_price is not None else token_price_usd(base_asset)
    breakdown = prof.expense_breakdown or {}

    # Correctly convert USD principal and gross_out to raw units via price.
    flash_principal_raw = to_raw_units(base_asset, usd_to_token(base_asset, principal_usd))
    sell_amount_out_raw = to_raw_units(base_asset, usd_to_token(base_asset, gross_amount_out_usd))

    # Use the correct expense fields from the Profitability object or its breakdown.
    flash_fee_raw = usd_expense_to_base_raw(prof.flash_fee_usd, base_asset, price)
    gas_cost_raw = usd_expense_to_base_raw(prof.gas_cost_usd, base_asset, price)
    relay_raw = usd_expense_to_base_raw(prof.relay_tip_usd, base_asset, price)
    risk_raw = usd_expense_to_base_raw(prof.risk_buffer_usd, base_asset, price)
    min_profit_raw = usd_expense_to_base_raw(Decimal(str(breakdown.get("min_net_profit_usd", "0"))), base_asset, price)

    # 3. Run the canonical raw gate
    passes_raw = raw_execution_gate_passes(
        sell_amount_out_raw=sell_amount_out_raw,
        flash_principal_raw=flash_principal_raw,
        flash_fee_raw=flash_fee_raw,
        gas_cost_raw=gas_cost_raw,
        relay_cost_raw=relay_raw,
        risk_buffer_raw=risk_raw,
        minimum_profit_raw=min_profit_raw,
    )

    return {
        "profitability": prof,
        "expense_breakdown": breakdown,
        "passes_usd_gate": prof.passes_gate, # Use the correct attribute from Profitability
        "passes_raw_gate": passes_raw,
        "deadline_block": discovery_block + 4,
        "raw_gate_fields": {
            "flash_principal_raw": flash_principal_raw,
            "sell_amount_out_raw": sell_amount_out_raw,
            "flash_fee_raw": flash_fee_raw,
            "gas_cost_raw": gas_cost_raw,
            "relay_cost_raw": relay_raw,
            "risk_buffer_raw": risk_raw,
            "minimum_profit_raw": min_profit_raw,
        },
    }


def compute_executable_round_trip(
    base_asset: str,
    mid_asset: str,
    flash_principal_usd: Decimal,
    buy_pool_quote: Dict[str, Any],
    sell_pool_quote: Dict[str, Any],
    flash_fee_raw: int,
    gas_cost_raw: int,
    builder_fee_raw: int = 0,
    relay_fee_raw: int = 0,
    explicit_reserve_raw: int = 0,
) -> Dict[str, Any]:
    """
    Authoritative executable round-trip.

    FLASH_BASE_RAW → buy using exact quote → MID_MIN_OUT_RAW (conservative)
    → sell using MID_MIN_OUT_RAW → BASE_MIN_OUT_RAW

    Returns raw values + expense stack on gross surplus.
    """
    flash_base_raw = _to_raw(base_asset, flash_principal_usd)

    mid_min_out_raw = buy_pool_quote.get("min_out_raw") or buy_pool_quote.get("amount_out_raw", 0)
    if mid_min_out_raw <= 0:
        return {"valid": False, "reason": "no_buy_min_out"}

    base_min_out_raw = sell_pool_quote.get("min_out_raw") or sell_pool_quote.get("amount_out_raw", 0)
    if base_min_out_raw <= 0:
        return {"valid": False, "reason": "no_sell_min_out"}

    gross_base_surplus_raw = base_min_out_raw - flash_base_raw
    total_expenses_raw = (
        flash_fee_raw + gas_cost_raw + builder_fee_raw + relay_fee_raw + explicit_reserve_raw
    )
    net_base_surplus_raw = gross_base_surplus_raw - total_expenses_raw

    return {
        "valid": net_base_surplus_raw > 0,
        "flash_base_raw": flash_base_raw,
        "mid_min_out_raw": mid_min_out_raw,
        "base_min_out_raw": base_min_out_raw,
        "gross_base_surplus_raw": gross_base_surplus_raw,
        "total_expenses_raw": total_expenses_raw,
        "net_base_surplus_raw": net_base_surplus_raw,
        "flash_fee_raw": flash_fee_raw,
        "gas_cost_raw": gas_cost_raw,
        "builder_fee_raw": builder_fee_raw,
        "relay_fee_raw": relay_fee_raw,
        "explicit_reserve_raw": explicit_reserve_raw,
    }


def compute_net_base_surplus(
    gross_out_raw: int,
    flash_principal_raw: int,
    flash_fee_raw: int,
    gas_cost_raw: int,
    builder_fee_raw: int = 0,
    relay_fee_raw: int = 0,
    risk_reserve_raw: int = 0,
) -> int:
    """Pure raw-integer net surplus after all non-embedded expenses."""
    raw_delta = gross_out_raw - flash_principal_raw
    expenses = flash_fee_raw + gas_cost_raw + builder_fee_raw + relay_fee_raw + risk_reserve_raw
    return raw_delta - expenses


def net_profit_usd_from_raw(
    net_base_surplus_raw: int,
    base_asset: str,
    base_usd_price: Decimal,
) -> Decimal:
    """Normalize retained raw surplus to USD. Never use for execution decisions."""
    base_amount = _from_raw(base_asset, net_base_surplus_raw)
    return base_amount * base_usd_price


def deduct_usd_expenses_from_raw_delta(
    *,
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    flash_fee_usd: Decimal = Decimal("0"),
    gas_cost_usd: Decimal | None = None,
    hops: int = 2,
    relay_tip_usd: Decimal | None = None,
    risk_buffer_usd: Decimal | None = None,
    impact_penalty_usd: Decimal = Decimal("0"),
    builder_fee_usd: Decimal = Decimal("0"),
    min_net_profit_usd: Decimal | None = None,
) -> ExpenseBreakdown:
    """
    USD mirror of the raw gate: start from raw_delta, subtract every
    non-embedded expense. Uses static micro-gas estimate when gas not supplied.
    """
    gas = estimate_static_gas_usd(hops=hops) if gas_cost_usd is None else gas_cost_usd
    return deduct_expenses_from_raw_delta(
        gross_amount_out_usd=gross_amount_out_usd, # type: ignore
        principal_usd=principal_usd,
        flash_fee_usd=flash_fee_usd,
        gas_cost_usd=gas,
        relay_tip_usd=relay_tip_usd,
        risk_buffer_usd=risk_buffer_usd,
        impact_penalty_usd=impact_penalty_usd,
        builder_fee_usd=builder_fee_usd,
        min_net_profit_usd=min_net_profit_usd,
    )


def indicative_raw_delta_usd(
    flash_principal_usd: Decimal,
    buy_price_usd_per_mid: Decimal,
    sell_price_usd_per_mid: Decimal,
) -> Decimal:
    """
    Diagnostic only. Correct dimensional formula.
    MID_UNITS = FLASH_USD / BUY_PRICE
    RAW_DELTA_USD = (SELL - BUY) * MID_UNITS
    or FLASH_USD * SPREAD_RATIO
    """
    if buy_price_usd_per_mid <= 0:
        return Decimal("0")
    mid_units = flash_principal_usd / buy_price_usd_per_mid
    spread_usd_per_mid = sell_price_usd_per_mid - buy_price_usd_per_mid
    return spread_usd_per_mid * mid_units


def spread_ratio(buy_price: Decimal, sell_price: Decimal) -> Decimal:
    if buy_price <= 0:
        return Decimal("0")
    return (sell_price - buy_price) / buy_price


def usd_costs_to_base_raw(
    *,
    base_asset: str,
    base_usd_price: Decimal,
    flash_fee_usd: Decimal = Decimal("0"),
    gas_cost_usd: Decimal = Decimal("0"),
    relay_tip_usd: Decimal = Decimal("0"),
    risk_buffer_usd: Decimal = Decimal("0"),
    builder_fee_usd: Decimal = Decimal("0"),
) -> Dict[str, int]:
    """Convert USD expense legs into base-token raw units for the integer gate. 0 USD -> 0 raw."""
    if base_usd_price <= 0:
        raise ValueError("base_usd_price must be positive")

    def _leg(usd: Decimal) -> int:
        if not isinstance(usd, Decimal) or usd <= 0:
            return 0
        return _to_raw(base_asset, usd / base_usd_price)

    return {
        "flash_fee_raw": _leg(flash_fee_usd),
        "gas_cost_raw": _leg(gas_cost_usd),
        "relay_cost_raw": _leg(relay_tip_usd),
        "risk_buffer_raw": _leg(risk_buffer_usd),
        "builder_fee_raw": _leg(builder_fee_usd),
    }
