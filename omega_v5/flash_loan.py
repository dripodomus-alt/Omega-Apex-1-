# ==============================================================================
# flash_loan.py  —  Flash loan capital layer + profitability gate + dynamic size opt
#
# Now integrates with official capital_injector for injection decisions.
# ==============================================================================

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal
from enum import Enum
from decimal import InvalidOperation
from typing import Any, Optional, Callable

from .accounting import GasCost, gas_cost_from_gwei
from .config import (
    DYNAMIC_SIZE_OPT_BINS_USD,
    ENABLE_DYNAMIC_SIZE_OPTIMIZER,
    STABLE_MIN_NET_PROFIT_USD,
    DYNAMIC_SIZE_IMPACT_PENALTY_BPS,
    PROTOCOL_OVERHEAD_USD,
    STABLE_RISK_BUFFER_USD,
)
from .pricing.engine_config import get_engine
from .pricing.precision_pricing import PricingContext, PRICE_SCALE, PricingError
from .units import get_token_metadata

# ── Flash loan source addresses (Polygon mainnet) ─────────────────────────────
AAVE_V3_POOL_POLYGON = "0x794a61358D6845594F94dc1DB02A252b5b4814aD"
BALANCER_VAULT_POLYGON = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"

# ── Fee schedule ──────────────────────────────────────────────────────────────
AAVE_FLASH_FEE_BPS = Decimal("5")  # 0.05 %
BALANCER_FLASH_FEE_BPS = Decimal("0")  # 0 % on Polygon

# ── Gas parameters (Polygon micro-fee recalibration) ──────────────────────────
GAS_PRICE_GWEI = Decimal("5")
GAS_UNITS_SIMPLE_ARB = Decimal("35000")
GAS_UNITS_THREE_HOP_ARB = Decimal("50000")
GAS_UNITS_FOUR_HOP_ARB = Decimal("65000")
POL_USD_PRICE = Decimal("0.0766")

MIN_NET_PROFIT_USD = Decimal("0.001")
MIN_PROFIT_TO_GAS_RATIO = Decimal("0")
RELAY_TIP_USD = Decimal("0.001")
RISK_BUFFER_USD = Decimal("0.005")
FEE_CACHE_TTL_SECONDS = 30


def route_tx_gas_limit(hops: int) -> int:
    """Conservative gas limit by route hop count for Polygon execution payloads."""
    try:
        hop_count = max(1, int(hops))
    except Exception:
        hop_count = 2
    if hop_count <= 2:
        return int(GAS_UNITS_SIMPLE_ARB)
    if hop_count == 3:
        return int(GAS_UNITS_THREE_HOP_ARB)
    return int(GAS_UNITS_FOUR_HOP_ARB)


def current_gas_price_gwei() -> tuple[Decimal, str]:
    return GAS_PRICE_GWEI, "static_config"


def current_pol_price_usd() -> tuple[Decimal, str]:
    return POL_USD_PRICE, "static_config"


def _read_live_flash_fee_bps(source: FlashSource) -> tuple[Decimal, str, int, bool]:
    fee = BALANCER_FLASH_FEE_BPS if source == FlashSource.BALANCER else AAVE_FLASH_FEE_BPS
    return fee, "static_config", 0, True
class FlashSource(str, Enum):
    AAVE_V3 = "AAVE_V3"
    BALANCER = "BALANCER"

@dataclass(frozen=True)
class FlashLoanParams:
    source: FlashSource
    asset: str
    principal_usd: Decimal
    fee_bps: Decimal
    fee_usd: Decimal
    repayment_usd: Decimal

@dataclass(frozen=True)
class ExpenseBreakdown:
    raw_delta_usd: Decimal
    flash_fee_usd: Decimal
    gas_cost_usd: Decimal
    relay_tip_usd: Decimal
    risk_buffer_usd: Decimal
    total_expenses_usd: Decimal
    net_after_expenses_usd: Decimal
    min_net_profit_usd: Decimal
    passes_min_net: bool


@dataclass(frozen=True)
class Profitability:
    gross_amount_out: Decimal
    gross_amount_out_min: Decimal
    flashloan: FlashLoanParams
    gas_cost_usd: Decimal
    relay_tip_usd: Decimal
    risk_buffer_usd: Decimal
    net_profit_usd: Decimal
    profit_to_gas: Decimal
    passes_gate: bool
    raw_delta_usd: Decimal = Decimal("0")
    expense_breakdown: dict[str, Any] = field(default_factory=dict)


def estimate_static_gas_usd(*, hops: int = 2) -> Decimal:
    units = GAS_UNITS_SIMPLE_ARB if hops <= 2 else (GAS_UNITS_THREE_HOP_ARB if hops == 3 else GAS_UNITS_FOUR_HOP_ARB)
    return units * GAS_PRICE_GWEI / Decimal("1000000000") * POL_USD_PRICE


def deduct_expenses_from_raw_delta(
    *,
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    flash_fee_usd: Decimal,
    gas_cost_usd: Decimal,
    relay_tip_usd: Decimal,
    risk_buffer_usd: Decimal,
    min_net_profit_usd: Decimal = MIN_NET_PROFIT_USD,
) -> ExpenseBreakdown:
    raw_delta = Decimal(str(gross_amount_out_usd)) - Decimal(str(principal_usd))
    total = Decimal(str(flash_fee_usd)) + Decimal(str(gas_cost_usd)) + Decimal(str(relay_tip_usd)) + Decimal(str(risk_buffer_usd))
    net = raw_delta - total
    return ExpenseBreakdown(
        raw_delta_usd=raw_delta,
        flash_fee_usd=Decimal(str(flash_fee_usd)),
        gas_cost_usd=Decimal(str(gas_cost_usd)),
        relay_tip_usd=Decimal(str(relay_tip_usd)),
        risk_buffer_usd=Decimal(str(risk_buffer_usd)),
        total_expenses_usd=total,
        net_after_expenses_usd=net,
        min_net_profit_usd=Decimal(str(min_net_profit_usd)),
        passes_min_net=net >= Decimal(str(min_net_profit_usd)),
    )


def evaluate_profitability(
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    *,
    hops: int = 2,
    flash_source: FlashSource = FlashSource.BALANCER,
    asset: str = "USDC",
) -> Profitability:
    """Core profitability. Can be called after capital_injector decides size."""
    principal = Decimal(str(principal_usd))
    gross = Decimal(str(gross_amount_out_usd))
    fee_bps = BALANCER_FLASH_FEE_BPS if flash_source == FlashSource.BALANCER else AAVE_FLASH_FEE_BPS
    fee_usd = principal * fee_bps / Decimal("10000")
    gas = Decimal("0.001") * Decimal(str(hops))
    relay = RELAY_TIP_USD
    risk = RISK_BUFFER_USD
    raw_delta = gross - principal
    net = raw_delta - fee_usd - gas - relay - risk
    passes = net >= MIN_NET_PROFIT_USD
    flash = FlashLoanParams(flash_source, asset, principal, fee_bps, fee_usd, principal + fee_usd)
    expenses = {
        "raw_delta_usd": str(raw_delta),
        "flash_fee_usd": str(fee_usd),
        "gas_cost_usd": str(gas),
        "relay_tip_usd": str(relay),
        "risk_buffer_usd": str(risk),
        "total_expenses_usd": str(fee_usd + gas + relay + risk),
        "net_after_expenses_usd": str(net),
        "min_net_profit_usd": str(MIN_NET_PROFIT_USD),
        "passes_min_net": passes,
    }
    return Profitability(
        gross_amount_out=gross,
        gross_amount_out_min=gross, # Placeholder for legacy calls
        flashloan=flash,
        gas_cost_usd=gas,
        relay_tip_usd=relay,
        risk_buffer_usd=risk,
        net_profit_usd=net,
        profit_to_gas=(net / gas) if gas > 0 else Decimal("999"),
        passes_gate=passes,
        raw_delta_usd=raw_delta,
        expense_breakdown=expenses,
    )

def calculate_route_economics(
    route: dict,
    pools: dict,
    *,
    flash_source: FlashSource = FlashSource.BALANCER,
) -> dict:
    """Route level. Prefers capital_injector result if present in route."""
    principal = Decimal(str(route.get("selected_principal_usd", "10000")))
    # If injector already ran, use its value
    if "sizing" in route and "principal_usd" in route["sizing"]:
        try:
            principal = Decimal(route["sizing"]["principal_usd"])
        except Exception:
            pass

    gross = principal * Decimal("1.0015")  # placeholder
    prof = evaluate_profitability(gross, principal, hops=len(route.get("pool_sequence", [])), flash_source=flash_source)
    return {
        "principal_usd": str(principal),
        "net_profit_usd": str(prof.net_profit_usd),
        "passes": prof.passes_gate,
    }

# Backwards compat
live_min_net_profit_usd = lambda: MIN_NET_PROFIT_USD
live_relay_tip_usd = lambda: RELAY_TIP_USD
live_risk_buffer_usd = lambda: RISK_BUFFER_USD

def build_executable_route_economics(*args, **kwargs):
    return calculate_route_economics(*args, **kwargs)

