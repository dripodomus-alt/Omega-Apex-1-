# ==============================================================================
# flash_loan.py  —  Flash loan capital layer + profitability gate + dynamic size opt
# Extracted from Cell 7 of notebooks/omega_v5.ipynb
#
# Models Aave V3 and Balancer Vault flash liquidity sources on Polygon.
# Computes available capital, flash fees, and net repayment obligations.
# Dynamic size optimizer added on top of core net equation.
# Specialized stablecoin gate support added.
#
# Expense model (Polygon micro-gas recalibration):
#   raw_delta_usd = gross_amount_out_usd - principal_usd
#   expenses      = flash_fee + gas + relay_tip + risk_buffer [+ impact]
#   net_profit    = raw_delta_usd - expenses
#
# Static gas fallback targets ~$0.001 / 2-hop flash arb at ~10 gwei and POL~$0.30.
# Live gas always prefers oracle/RPC when available.
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
# gas_usd ≈ gas_units * gwei * 1e-9 * pol_usd
# 350_000 * 10e-9 * 0.30 ≈ $0.00105  (matches ~$0.001/tx class on Polygon)
GAS_PRICE_GWEI = Decimal("10")
GAS_UNITS_SIMPLE_ARB = Decimal("350000")  # 2-hop flash arb
GAS_UNITS_THREE_HOP_ARB = Decimal("500000")  # 3-hop flash arb
GAS_UNITS_FOUR_HOP_ARB = Decimal("650000")  # 4-hop flash arb
POL_USD_PRICE = Decimal("0.076")  # fallback; overridden by oracle layer when live

# ── Profitability gate constants (defaults; runtime env overrides below) ──────
# Floors are intentionally micro so min→max surplus scans are not gas-starved.
MIN_NET_PROFIT_USD = Decimal("0.001")  # ~1× static 2-hop gas
MIN_PROFIT_TO_GAS_RATIO = Decimal("0")  # allow thin surplus when gas is micro
RELAY_TIP_USD = Decimal("0.001")  # public path tip; env override for private relays
RISK_BUFFER_USD = Decimal("0.005")  # residual non-slippage reserve (slippage via minOut)
FEE_CACHE_TTL_SECONDS = 20

_FEE_CACHE: dict[tuple[str, int], tuple[float, Decimal, str]] = {}


def _env_decimal(key: str, default: Decimal) -> Decimal:
    raw = os.environ.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return Decimal(str(raw).strip())
    except Exception:
        return default


def live_min_net_profit_usd() -> Decimal:
    return _env_decimal("MIN_NET_PROFIT_USD", MIN_NET_PROFIT_USD)


def live_min_profit_to_gas_ratio() -> Decimal:
    return _env_decimal("MIN_PROFIT_TO_GAS_RATIO", MIN_PROFIT_TO_GAS_RATIO)


def live_risk_buffer_usd() -> Decimal:
    return _env_decimal("RISK_BUFFER_USD", RISK_BUFFER_USD)


def live_relay_tip_usd() -> Decimal:
    return _env_decimal("RELAY_TIP_USD", RELAY_TIP_USD)


def live_protocol_overhead_usd() -> Decimal:
    return _env_decimal("PROTOCOL_OVERHEAD_USD", PROTOCOL_OVERHEAD_USD)


class FlashSource(str, Enum):
    AAVE = "Aave_V3"
    BALANCER = "Balancer_Vault"


@dataclass
class FlashLoanParams:
    source: FlashSource
    asset: str  # token symbol
    principal_usd: Decimal
    fee_bps: Decimal
    fee_usd: Decimal
    repayment_usd: Decimal  # principal + fee
    fee_verified: bool = False
    fee_source: str = "static_config"
    fee_block: int = 0


@dataclass(frozen=True)
class ExpenseBreakdown:
    """
    Canonical USD expense stack deducted from raw delta.

    raw_delta_usd = gross_amount_out_usd - principal_usd
    (swap fees / AMM impact already embedded in gross via executable quotes)

    Separately deducted (never double-count embedded quote fees):
      flash_fee, gas, relay_tip, risk_buffer, optional impact_penalty, optional builder_fee
    """

    raw_delta_usd: Decimal
    principal_usd: Decimal
    gross_amount_out_usd: Decimal
    flash_fee_usd: Decimal
    gas_cost_usd: Decimal
    relay_tip_usd: Decimal
    risk_buffer_usd: Decimal
    protocol_overhead_usd: Decimal = Decimal("0")
    impact_penalty_usd: Decimal = Decimal("0")
    builder_fee_usd: Decimal = Decimal("0")
    total_expenses_usd: Decimal = Decimal("0")
    net_after_expenses_usd: Decimal = Decimal("0")
    min_net_profit_usd: Decimal = Decimal("0")
    passes_min_net: bool = False
    notes: tuple[str, ...] = ()
    as_of_block: int = 0
    fee_source: str = "static_config"
    gas_source: str = "static_config"

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_delta_usd": str(self.raw_delta_usd),
            "principal_usd": str(self.principal_usd),
            "gross_amount_out_usd": str(self.gross_amount_out_usd),
            "flash_fee_usd": str(self.flash_fee_usd),
            "gas_cost_usd": str(self.gas_cost_usd),
            "relay_tip_usd": str(self.relay_tip_usd),
            "protocol_overhead_usd": str(self.protocol_overhead_usd),
            "risk_buffer_usd": str(self.risk_buffer_usd),
            "impact_penalty_usd": str(self.impact_penalty_usd),
            "builder_fee_usd": str(self.builder_fee_usd),
            "total_expenses_usd": str(self.total_expenses_usd),
            "net_after_expenses_usd": str(self.net_after_expenses_usd),
            "min_net_profit_usd": str(self.min_net_profit_usd),
            "passes_min_net": self.passes_min_net,
            "notes": list(self.notes),
            "as_of_block": self.as_of_block,
            "fee_source": self.fee_source,
            "gas_source": self.gas_source,
        }


@dataclass(frozen=True)
class RouteEconomics:
    gross_surplus_usd: Decimal
    flash_fee_usd: Decimal
    gas_cost_usd: Decimal
    relay_tip_usd: Decimal
    builder_fee_usd: Decimal
    protocol_overhead_usd: Decimal
    risk_buffer_usd: Decimal
    impact_penalty_usd: Decimal
    economic_net_profit_usd: Decimal
    required_profit_usd: Decimal
    headroom_usd: Decimal
    passes_gate: bool
    impact_ratio: Decimal


def _apply_impact_penalty(principal: Decimal, min_tvl: Decimal, gross: Decimal) -> Decimal:
    """Delegate to the canonical implementation in the sizing package."""
    from .sizing.dynamic_optimizer import _apply_impact_penalty as sizer_penalty

    return sizer_penalty(principal, min_tvl, gross)


@dataclass
class Profitability:
    gross_amount_out: Decimal  # raw output from math engine (USD)
    flashloan: FlashLoanParams | None
    gas_cost_usd: Decimal
    relay_tip_usd: Decimal
    risk_buffer_usd: Decimal
    net_profit_usd: Decimal
    profit_to_gas: Decimal
    passes_gate: bool
    protocol_overhead_usd: Decimal = Decimal("0")
    gas_units: Decimal = Decimal("0")
    gas_price_gwei: Decimal = GAS_PRICE_GWEI
    gas_price_source: str = "static_config"
    gas_price_wei: int = 0
    gas_cost_pol: Decimal = Decimal("0")
    pol_price_usd: Decimal = POL_USD_PRICE
    gas_payer: str = "user_wallet"
    gas_accounting: dict | None = None
    raw_delta_usd: Decimal = Decimal("0")
    flash_fee_usd: Decimal = Decimal("0")
    total_expenses_usd: Decimal = Decimal("0")
    expense_breakdown: dict | None = None


def route_gas_units(hops: int) -> Decimal:
    """Route gas model by executable swap count."""
    if hops <= 2:
        return GAS_UNITS_SIMPLE_ARB
    if hops == 3:
        return GAS_UNITS_THREE_HOP_ARB
    return GAS_UNITS_FOUR_HOP_ARB


def route_tx_gas_limit(hops: int) -> int:
    """Execution transaction gas limit with a 20% buffer over the route model."""
    return int((route_gas_units(hops) * Decimal("1.20")).to_integral_value())


def estimate_static_gas_usd(
    hops: int = 2,
    gas_price_gwei: Decimal = GAS_PRICE_GWEI,
    pol_price_usd: Decimal = POL_USD_PRICE,
) -> Decimal:
    """Offline estimate used for docs/tests; live path uses oracle + accounting."""
    units = route_gas_units(hops)
    native = units * gas_price_gwei / Decimal("1000000000")
    return native * pol_price_usd


def _live_w3():
    try:
        from . import rpc_layer

        if rpc_layer.w3 is not None and rpc_layer.RPC_LIVE:
            return rpc_layer.w3
    except Exception:
        return None
    return None


def current_gas_price_gwei() -> tuple[Decimal, str]:
    try:
        from .gas_oracle import profitability_gas_price_gwei

        return profitability_gas_price_gwei()
    except Exception:
        pass

    w3 = _live_w3()
    if w3 is None:
        return GAS_PRICE_GWEI, "static_config_no_rpc"
    try:
        return Decimal(str(w3.eth.gas_price)) / Decimal("1e9"), "polygon_rpc_gas_price"
    except Exception:
        return GAS_PRICE_GWEI, "static_config_gas_read_failed"


def current_pol_price_usd() -> tuple[Decimal, str]:
    try:
        from .oracle_layer import token_price_usd

        price = token_price_usd("WPOL")
        if price > 0:
            return price, "oracle_layer.WPOL"
    except Exception:
        pass
    try:
        from .oracle_layer import token_price_usd

        price = token_price_usd("POL")
        if price > 0:
            return price, "oracle_layer.POL"
    except Exception:
        pass
    return POL_USD_PRICE, "static_config_POL_USD_PRICE"


def _fallback_fee_bps(source: FlashSource) -> Decimal:
    return BALANCER_FLASH_FEE_BPS if source == FlashSource.BALANCER else AAVE_FLASH_FEE_BPS


def _read_live_flash_fee_bps(source: FlashSource, as_of_block: int) -> tuple[Decimal, str, int, bool]:
    """Reads live flash fee in BPS, with block-aware caching."""
    now = time.time()
    w3 = _live_w3()
    # If we can't get a live block number, we can't reliably cache.
    if as_of_block <= 0 and w3:
        as_of_block = w3.eth.block_number

    cache_key = (source.value, as_of_block)
    cached = _FEE_CACHE.get(cache_key)
    if cached:
        cached_time, fee_bps, fee_source = cached
        if (now - cached_time) <= FEE_CACHE_TTL_SECONDS:
            return fee_bps, f"{fee_source}_cached", as_of_block, True

    if w3 is None:
        return _fallback_fee_bps(source), "static_config_no_rpc", 0, False

    try:
        if source == FlashSource.AAVE:
            abi = [
                {
                    "name": "FLASHLOAN_PREMIUM_TOTAL",
                    "type": "function",
                    "stateMutability": "view",
                    "inputs": [],
                    "outputs": [{"name": "", "type": "uint128"}],
                }
            ]
            contract = w3.eth.contract(address=AAVE_V3_POOL_POLYGON, abi=abi)
            fee_bps = Decimal(str(contract.functions.FLASHLOAN_PREMIUM_TOTAL().call()))
            fee_source = "aave_pool.FLASHLOAN_PREMIUM_TOTAL"
            # Note: Aave fee is a constant, not block-dependent, but we cache by block for consistency
        else:
            vault_abi = [
                {
                    "name": "getProtocolFeesCollector",
                    "type": "function",
                    "stateMutability": "view",
                    "inputs": [],
                    "outputs": [{"name": "", "type": "address"}],
                }
            ]
            collector_abi = [
                {
                    "name": "getFlashLoanFeePercentage",
                    "type": "function",
                    "stateMutability": "view",
                    "inputs": [],
                    "outputs": [{"name": "", "type": "uint256"}],
                }
            ]
            vault = w3.eth.contract(address=BALANCER_VAULT_POLYGON, abi=vault_abi)
            collector_address = vault.functions.getProtocolFeesCollector().call()
            collector = w3.eth.contract(address=collector_address, abi=collector_abi)
            raw_pct_1e18 = Decimal(str(collector.functions.getFlashLoanFeePercentage().call()))
            fee_bps = raw_pct_1e18 * Decimal("10000") / Decimal("1e18")
            fee_source = "balancer_vault.protocolFeesCollector.getFlashLoanFeePercentage"

        _FEE_CACHE[cache_key] = (now, fee_bps, fee_source)
        return fee_bps, fee_source, as_of_block, True
    except Exception:
        return _fallback_fee_bps(source), "static_config_live_fee_read_failed", 0, False


def compute_flash_params(
    principal_usd: Decimal,
    source: FlashSource = FlashSource.BALANCER,
    asset: str = "USDC",
    as_of_block: int = 0,
) -> FlashLoanParams:
    """Returns flash loan cost structure for a given principal and source."""
    from . import rpc_layer
    block = as_of_block or getattr(rpc_layer, "BLOCK", 0)
    try:
        fee_bps, fee_source, fee_block, fee_verified = _read_live_flash_fee_bps(source, block)
    except TypeError as exc:
        try:
            fee_bps, fee_source, fee_block, fee_verified = _read_live_flash_fee_bps(source)
        except TypeError:
            raise exc
    fee_usd = principal_usd * fee_bps / Decimal("10000")
    return FlashLoanParams(
        source=source,
        asset=asset,
        principal_usd=principal_usd,
        fee_bps=fee_bps,
        fee_usd=fee_usd,
        repayment_usd=principal_usd + fee_usd,
        fee_verified=fee_verified,
        fee_source=fee_source,
        fee_block=fee_block,
    )


def deduct_expenses_from_raw_delta(
    *,
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    flash_fee_usd: Decimal = Decimal("0"),
    gas_cost_usd: Decimal = Decimal("0"),
    relay_tip_usd: Decimal | None = None,
    risk_buffer_usd: Decimal | None = None,
    impact_penalty_usd: Decimal = Decimal("0"),
    builder_fee_usd: Decimal = Decimal("0"),
    protocol_overhead_usd: Decimal | None = None,
    min_net_profit_usd: Decimal | None = None,
    as_of_block: int = 0,
    notes: tuple[str, ...] = (),
) -> ExpenseBreakdown:
    """
    Recalculate net surplus from raw delta by subtracting every non-embedded expense.

    Embedded in gross (DO NOT subtract again):
      - pool swap fees, curve/v3/balancer impact already in executable quote

    Deducted here:
      - flash provider fee
      - native gas (USD)
      - relay / inclusion tip
      - risk buffer (non-slippage residual)
      - optional impact penalty (sizing layer)
      - optional builder fee
    """
    relay = live_relay_tip_usd() if relay_tip_usd is None else relay_tip_usd
    risk = live_risk_buffer_usd() if risk_buffer_usd is None else risk_buffer_usd
    protocol_cost = live_protocol_overhead_usd() if protocol_overhead_usd is None else protocol_overhead_usd
    min_net = live_min_net_profit_usd() if min_net_profit_usd is None else min_net_profit_usd

    raw_delta = gross_amount_out_usd - principal_usd
    # Per canonical formula, risk buffer is an uncertainty margin, not a realized cost.
    # It is used to calculate the required profit floor, not to reduce economic profit.
    total_expenses_usd = (
        flash_fee_usd
        + gas_cost_usd
        + relay
        + protocol_cost
        + impact_penalty_usd
        + builder_fee_usd
    )
    net_after_expenses_usd = raw_delta - total_expenses_usd
    default_notes = (
        "swap_fees_embedded_in_gross",
        "slippage_enforced_via_amountOutMin_not_usd_buffer",
        "polygon_micro_gas_model",
    )
    breakdown = ExpenseBreakdown(
        raw_delta_usd=raw_delta,
        principal_usd=principal_usd,
        gross_amount_out_usd=gross_amount_out_usd,
        flash_fee_usd=flash_fee_usd,
        gas_cost_usd=gas_cost_usd,
        relay_tip_usd=relay,
        protocol_overhead_usd=protocol_cost,
        risk_buffer_usd=risk,
        impact_penalty_usd=impact_penalty_usd,
        builder_fee_usd=builder_fee_usd,
        total_expenses_usd=total_expenses_usd,
        net_after_expenses_usd=net_after_expenses_usd,
        min_net_profit_usd=min_net,
        passes_min_net=net_after_expenses_usd >= min_net,
        notes=notes or default_notes,
        as_of_block=as_of_block,
    )
    return breakdown


def calculate_route_economics(
    *,
    flash_principal_usd: Decimal,
    gross_sell_out_usd: Decimal,
    min_tvl_usd: Decimal,
    flash_fee_usd: Decimal,
    gas_cost_usd: Decimal,
    relay_tip_usd: Decimal,
    builder_fee_usd: Decimal,
    protocol_overhead_usd: Decimal,
    risk_buffer_usd: Decimal,
    minimum_profit_usd: Decimal,
) -> RouteEconomics:
    values = {
        "flash_principal_usd": flash_principal_usd,
        "gross_sell_out_usd": gross_sell_out_usd,
        "min_tvl_usd": min_tvl_usd,
        "flash_fee_usd": flash_fee_usd,
        "gas_cost_usd": gas_cost_usd,
        "relay_tip_usd": relay_tip_usd,
        "builder_fee_usd": builder_fee_usd,
        "protocol_overhead_usd": protocol_overhead_usd,
        "risk_buffer_usd": risk_buffer_usd,
        "minimum_profit_usd": minimum_profit_usd,
    }

    normalized = {name: Decimal(value) for name, value in values.items()}

    principal = normalized["flash_principal_usd"]
    gross_sell_out = normalized["gross_sell_out_usd"]
    min_tvl = normalized["min_tvl_usd"]

    gross_surplus = gross_sell_out - principal

    impact_penalty = _apply_impact_penalty(
        principal=principal,
        min_tvl=min_tvl,
        gross=max(Decimal("0"), gross_surplus),
    )

    # Per canonical formula: economic_net_profit = gross_profit - realized_execution_costs
    # Risk buffer is an uncertainty margin, not a realized cost.
    operating_expenses = (
        normalized["flash_fee_usd"]
        + normalized["gas_cost_usd"]
        + normalized["relay_tip_usd"]
        + normalized["builder_fee_usd"]
        + normalized["protocol_overhead_usd"]
        + impact_penalty
    )

    economic_net = gross_surplus - operating_expenses

    # Per canonical formula: authorize if economic_net_profit >= required_profit_floor
    # required_profit_floor = base_floor + uncertainty_buffers
    required_profit_floor = normalized["minimum_profit_usd"] + normalized["risk_buffer_usd"]

    headroom = economic_net - required_profit_floor

    impact_ratio = principal / min_tvl if min_tvl > 0 else Decimal("Infinity")

    return RouteEconomics(
        gross_surplus_usd=gross_surplus,
        flash_fee_usd=normalized["flash_fee_usd"],
        gas_cost_usd=normalized["gas_cost_usd"],
        relay_tip_usd=normalized["relay_tip_usd"],
        builder_fee_usd=normalized["builder_fee_usd"],
        protocol_overhead_usd=normalized["protocol_overhead_usd"],
        risk_buffer_usd=normalized["risk_buffer_usd"],
        impact_penalty_usd=impact_penalty,
        economic_net_profit_usd=economic_net,
        required_profit_usd=required_profit_floor,
        headroom_usd=headroom,
        passes_gate=headroom >= Decimal("0"),
        impact_ratio=impact_ratio,
    )

def evaluate_profitability(
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    hops: int = 2,
    flash_source: FlashSource = FlashSource.BALANCER,
    asset: str = "USDC",
    gas_units_override: Decimal | None = None,
    min_net_profit_usd_override: Decimal | None = None,
    risk_buffer_usd_override: Decimal | None = None,
    impact_penalty_usd: Decimal = Decimal("0"),
    builder_fee_usd: Decimal = Decimal("0"),
    protocol_overhead_usd_override: Decimal | None = None,
    relay_tip_usd_override: Decimal | None = None,
    as_of_block: int | None = None,
) -> Profitability:
    """
    Full net-profit path from raw delta:

        raw_delta = gross_out - principal
        net       = raw_delta - flash_fee - gas - relay_tip - risk_buffer
                    - impact_penalty - builder_fee

    Equivalent form:
        net = gross_out - repayment - gas - relay - risk - impact - builder
        where repayment = principal + flash_fee

    Gate thresholds are env-live for min→max surplus scans.
    """
    from . import rpc_layer
    block = as_of_block if as_of_block is not None else getattr(rpc_layer, "BLOCK", 0)

    flash = compute_flash_params(
        principal_usd, flash_source, asset, as_of_block=block
    )
    gas_units = gas_units_override if gas_units_override is not None else route_gas_units(hops)
    gas_price_gwei, gas_price_source = current_gas_price_gwei()
    pol_price_usd, pol_price_source = current_pol_price_usd()
    gas_accounting: GasCost = gas_cost_from_gwei(
        gas_units,
        gas_price_gwei,
        pol_price_usd,
        pol_price_source,
    )
    gas_usd = gas_accounting.gas_cost_usd

    min_net = (
        min_net_profit_usd_override
        if min_net_profit_usd_override is not None
        else live_min_net_profit_usd()
    )
    risk_buf = (
        risk_buffer_usd_override
        if risk_buffer_usd_override is not None
        else live_risk_buffer_usd()
    )
    relay_tip = live_relay_tip_usd() if relay_tip_usd_override is None else relay_tip_usd_override
    protocol_cost = live_protocol_overhead_usd() if protocol_overhead_usd_override is None else protocol_overhead_usd_override
    min_p2g = live_min_profit_to_gas_ratio()

    breakdown = deduct_expenses_from_raw_delta(
        gross_amount_out_usd=gross_amount_out_usd,
        principal_usd=principal_usd,
        flash_fee_usd=flash.fee_usd,
        gas_cost_usd=gas_usd,
        relay_tip_usd=relay_tip,
        protocol_overhead_usd=protocol_cost,
        risk_buffer_usd=risk_buf,
        impact_penalty_usd=impact_penalty_usd,
        builder_fee_usd=builder_fee_usd,
        min_net_profit_usd=min_net,
        as_of_block=block,
    )
    breakdown = replace(
        breakdown,
        gas_source=f"{gas_price_source}|{pol_price_source}",
        fee_source=flash.fee_source,
    )
    # `net_profit_usd` is now the economic net profit, with risk buffer not yet subtracted.
    net_profit_usd = breakdown.net_after_expenses_usd
    profit_to_gas = net_profit_usd / gas_usd if gas_usd > 0 else Decimal("0")

    # The authorization gate compares economic profit against a required floor,
    # which includes the base minimum and the risk buffer.
    required_profit_floor = breakdown.min_net_profit_usd + breakdown.risk_buffer_usd
    passes = (net_profit_usd >= required_profit_floor) and (profit_to_gas >= min_p2g)

    return Profitability(
        gross_amount_out=gross_amount_out_usd,
        flashloan=flash,
        gas_cost_usd=gas_usd,
        relay_tip_usd=relay_tip,
        protocol_overhead_usd=protocol_cost,
        risk_buffer_usd=risk_buf,
        net_profit_usd=net_profit_usd,
        profit_to_gas=profit_to_gas,
        passes_gate=passes,
        gas_units=gas_units,
        gas_price_gwei=gas_price_gwei,
        gas_price_source=f"{gas_price_source}|{pol_price_source}",
        gas_price_wei=gas_accounting.gas_price_wei,
        gas_cost_pol=gas_accounting.native_amount,
        pol_price_usd=pol_price_usd,
        gas_payer=gas_accounting.gas_payer,
        gas_accounting=gas_accounting.as_dict(),
        raw_delta_usd=breakdown.raw_delta_usd,
        flash_fee_usd=flash.fee_usd,
        total_expenses_usd=breakdown.total_expenses_usd,
        expense_breakdown=breakdown.as_dict(),
    )


def route_profitability(
    gross_amount_out_usd: Decimal,
    principal_usd: Decimal,
    hops: int = 2,
    flash_source: FlashSource = FlashSource.BALANCER,
    **kwargs,
) -> Decimal:
    """
    Expected net profitability of a route.
    Wrapper around evaluate_profitability for the execution layer.
    """
    prof = evaluate_profitability(
        gross_amount_out_usd,
        principal_usd,
        hops=hops,
        flash_source=flash_source,
        **kwargs,
    )
    return prof.net_profit_usd


def stable_profitability_overrides() -> dict[str, Decimal]:
    """Lower floors for pegged stable micro-arb (config-driven)."""
    return {
        "min_net_profit_usd_override": STABLE_MIN_NET_PROFIT_USD,
        "risk_buffer_usd_override": STABLE_RISK_BUFFER_USD,
    }


# ==============================================================================
# build_executable_route_economics - Authoritative single source for full P&L
# Uses sizing + full profitability engine with dimensional accuracy.
# Reduces duplication and boundary crossings by being the last word on economics.
# ==============================================================================

def build_executable_route_economics(
    *,
    path: tuple[str, ...],
    pool_sequence: tuple[str, ...],
    pools: dict,
    principal_usd: Decimal,
    flash_source: FlashSource = FlashSource.BALANCER,
    slippage_bps: Decimal = Decimal("15"),
    quote_fn: Optional[Callable[[Decimal], Decimal]] = None,
    base_price: Optional[Decimal] = None,
) -> dict:
    """
    Authoritative economics for a route.
    - Applies optimal flash sizing (TVL cap + peak delta)
    - Uses full evaluate_profitability + calculate_route_economics
    - Returns complete profile ready for payload / truth / execution
    - Dimensional: USD, raw, with sources
    """
    from .sizing import optimal_flash_for_route, estimate_route_tvl_usd
    from . import rpc_layer

    if not path or not pool_sequence:
        return {"passes_gate": False, "reason": "invalid_path"}

    base_asset = path[0]
    try:
        if base_price is None:
            # Use the canonical PrecisionPricingEngine for the base asset price.
            engine = get_engine()
            ctx = PricingContext(chain_id=rpc_layer.CHAIN_ID, current_block=rpc_layer.BLOCK, current_timestamp=int(time.time()))
            token_meta = get_token_metadata(base_asset)
            price_result = engine.get_usd_price(token_meta.address, ctx)
            # Convert to Decimal for compatibility with the rest of this function's logic.
            base_price = Decimal(price_result.price_usd_x18) / Decimal(PRICE_SCALE)

        if base_price <= 0:
            return {"passes_gate": False, "reason": "no_base_price"}
    except (PricingError, Exception):
        return {"passes_gate": False, "reason": "price_unavailable"}

    # Use provided quote or default to executable quote
    if quote_fn is None:
        from .executable_quotes import quote_route_for_executor
        from .opportunity_ranker import amount_out_min_from_quote

        def default_quote(p_usd: Decimal) -> Decimal:
            amt_in = p_usd / base_price
            gross_out, _ = quote_route_for_executor(list(path), list(pool_sequence), pools, amt_in)
            min_out = amount_out_min_from_quote(Decimal(str(gross_out)), slippage_bps)
            return min_out * base_price
        quote_fn = default_quote

    # Get TVL snapshot for cap
    min_tvl = estimate_route_tvl_usd(pool_sequence, pools) or Decimal("0")

    # Run optimal sizing (uses quote_fn for accurate curve)
    sizing = optimal_flash_for_route(
        pool_sequence=pool_sequence,
        pools=pools,
        base_asset=base_asset,
        hops=len(path) - 1,
        flash_source=flash_source,
        requested_principal_usd=principal_usd,
        quote_fn=quote_fn,
        base_usd_price=base_price,
    )

    selected_principal = Decimal(str(
        getattr(sizing, "selected_principal_usd", None) or
        getattr(sizing, "injection_usd", principal_usd)
    ))
    if selected_principal <= 0:
        selected_principal = principal_usd

    # Get gross at selected size (slippage adjusted)
    gross_out_usd = quote_fn(selected_principal)

    # Full profitability using the engine
    prof = evaluate_profitability(
        gross_amount_out_usd=gross_out_usd,
        principal_usd=selected_principal,
        hops=len(path) - 1,
        flash_source=flash_source,
        asset=base_asset,
    )

    # Authoritative economics object
    economics = calculate_route_economics(
        flash_principal_usd=selected_principal,
        gross_sell_out_usd=gross_out_usd,
        min_tvl_usd=min_tvl,
        flash_fee_usd=prof.flashloan.fee_usd if prof.flashloan else Decimal("0"),
        gas_cost_usd=prof.gas_cost_usd,
        relay_tip_usd=prof.relay_tip_usd,
        builder_fee_usd=Decimal("0"),
        protocol_overhead_usd=prof.protocol_overhead_usd,
        risk_buffer_usd=prof.risk_buffer_usd,
        minimum_profit_usd=live_min_net_profit_usd(),
    )

    # Complete profile
    return {
        "path": path,
        "pool_sequence": pool_sequence,
        "selected_principal_usd": str(selected_principal),
        "gross_out_usd": str(gross_out_usd),
        "flash_fee_usd": str(economics.flash_fee_usd),
        "gas_cost_usd": str(economics.gas_cost_usd),
        "relay_tip_usd": str(economics.relay_tip_usd),
        "impact_penalty_usd": str(economics.impact_penalty_usd),
        "net_profit_usd": str(economics.economic_net_profit_usd),
        "passes_gate": economics.passes_gate,
        "min_tvl_usd": str(min_tvl),
        "sizing": getattr(sizing, "as_payload_fields", lambda: {})(),
        "profitability": {
            "raw_delta_usd": str(prof.raw_delta_usd),
            "total_expenses_usd": str(prof.total_expenses_usd),
            "expense_breakdown": prof.expense_breakdown,
        },
        "source": "build_executable_route_economics",
    }
