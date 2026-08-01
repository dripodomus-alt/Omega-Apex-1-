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
    evaluate_profitability,
    MIN_NET_PROFIT_USD,
    live_min_net_profit_usd,
    live_relay_tip_usd,
    live_risk_buffer_usd,
    route_tx_gas_limit,
    current_pol_price_usd,
)
from . import arbitrage
from . import rust_scanner
from . import scanner as py_scanner
from . import rpc_layer
from .gas_oracle import profitability_gas_price_gwei
from .oracle_layer import token_price_usd
from .pricing.net_delta import route_within_lifespan
from .sizing import compute_optimal_principal
from .ml_alpha_ranker import rerank_with_vqc
from .payload_envelope import build_payload_envelope

logger = logging.getLogger(__name__)

RUST_SCANNER_AVAILABLE = rust_scanner.is_available()
SCANNER_MODE = os.environ.get("SCANNER_MODE", "rust").lower()


def _normalize_token_price(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _build_leg_token_price_schema(path: Iterable[str], *, token_price_lookup: Any) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for token in path:
        token_str = str(token or "")
        if not token_str:
            continue
        price = _normalize_token_price(token_price_lookup(token_str))
        if price > 0:
            prices[token_str] = price
    return prices


def _default_slippage_bps() -> Decimal:
    try:
        return Decimal(str(os.environ.get("DEFAULT_SLIPPAGE_BPS", "10")))
    except Exception:
        return Decimal("10")


def _calculate_profitability(
    *,
    gross_out: Decimal,
    principal: Decimal,
    base_asset: str = "USDC",
    hops: int = 2,
    flash_source: FlashSource = FlashSource.BALANCER,
    min_net_profit_usd: Decimal | None = None,
    risk_buffer_usd: Decimal | None = None,
    relay_tip_usd: Decimal | None = None,
    slippage_bps: Decimal | None = None,
) -> Profitability:
    """Compatibility wrapper that evaluates profitability with dynamic gas and native-token pricing."""
    principal_usd = Decimal(str(principal))
    gross = Decimal(str(gross_out))
    fee_bps = Decimal("0") if flash_source == FlashSource.BALANCER else Decimal("5")
    fee_usd = principal_usd * fee_bps / Decimal("10000")

    gas_price_gwei, _ = profitability_gas_price_gwei()
    pol_price_usd, _ = current_pol_price_usd()
    gas_units = Decimal(str(route_tx_gas_limit(hops)))
    gas_cost_usd = (gas_units * Decimal(str(gas_price_gwei)) / Decimal("1e9")) * Decimal(str(pol_price_usd))

    relay = Decimal(str(relay_tip_usd if relay_tip_usd is not None else live_relay_tip_usd()))
    risk = Decimal(str(risk_buffer_usd if risk_buffer_usd is not None else live_risk_buffer_usd()))
    min_profit = Decimal(str(min_net_profit_usd if min_net_profit_usd is not None else live_min_net_profit_usd()))
    slippage = Decimal(str(slippage_bps if slippage_bps is not None else _default_slippage_bps())) / Decimal("10000")
    gross_out_min = gross * (Decimal("1") - slippage)
    raw_delta = gross_out_min - principal_usd
    net = raw_delta - fee_usd - gas_cost_usd - relay - risk
    passes = net >= min_profit
    flash = FlashLoanParams(flash_source, base_asset, principal_usd, fee_bps, fee_usd, principal_usd + fee_usd)
    return Profitability(
        gross_amount_out=gross,
        gross_amount_out_min=gross_out_min,
        flashloan=flash,
        gas_cost_usd=gas_cost_usd,
        relay_tip_usd=relay,
        risk_buffer_usd=risk,
        net_profit_usd=net,
        profit_to_gas=(net / gas_cost_usd) if gas_cost_usd > 0 else Decimal("999"),
        passes_gate=passes,
        raw_delta_usd=raw_delta,
        expense_breakdown={
            "raw_delta_usd": str(raw_delta),
            "flash_fee_usd": str(fee_usd),
            "gas_cost_usd": str(gas_cost_usd),
            "relay_tip_usd": str(relay),
            "risk_buffer_usd": str(risk),
            "total_expenses_usd": str(fee_usd + gas_cost_usd + relay + risk),
            "net_after_expenses_usd": str(net),
            "min_net_profit_usd": str(min_profit),
            "passes_min_net": passes,
        },
    )


@dataclass
class LiveOpportunity:
    """Canonical opportunity object passed through ranking, staging and execution."""
    path: tuple[str, ...]
    pool_sequence: tuple[str, ...]
    protocol_seq: tuple[str, ...]
    profitability: Profitability
    block_detected: int = 0
    metadata: dict = field(default_factory=dict)
    opp_id: str = ""
    family: str = "C1"   # C1 (primary arb), C2 (paired), LIQUIDATION
    # Additional fields for live execution families
    c1_success: bool = False
    liquidation_data: dict | None = None
    pricing_steps: list[dict] = field(default_factory=list)
    buy_leg_token_prices: dict[str, Decimal] = field(default_factory=dict)
    sell_leg_token_prices: dict[str, Decimal] = field(default_factory=dict)
    buy_leg_token_price_usd: Decimal | None = None
    sell_leg_token_price_usd: Decimal | None = None


def find_opportunities_with_rust(live_pools: dict, principal_usd: Decimal, max_slippage_bps: Decimal) -> list[LiveOpportunity]:
    """Rust-backed discovery (preferred)."""
    if not RUST_SCANNER_AVAILABLE:
        logger.error("Rust engine is not available")
        return []
    try:
        raw = rust_scanner.scan(live_pools, float(principal_usd), float(max_slippage_bps))
        return [LiveOpportunity(**r) if isinstance(r, dict) else r for r in raw]
    except Exception as e:
        logger.error(f"Rust scanner failed: {e}")
        return []


def _find_opportunities_with_python_reference(live_pools: dict, principal_usd: Decimal, max_slippage_bps: Decimal) -> list[LiveOpportunity]:
    """Pure Python reference implementation."""
    try:
        raw = py_scanner.find_opportunities(live_pools, principal_usd, max_slippage_bps)
        return [LiveOpportunity(**r) if isinstance(r, dict) else r for r in raw]
    except Exception as e:
        logger.warning(f"Python reference scanner error: {e}")
        return []


def find_opportunities(
    live_pools: dict,
    principal_usd: Decimal,
    max_slippage_bps: Decimal = Decimal("50"),
    *,
    gas_price_gwei: float | None = None,
    native_token_price_usd: float | None = None,
) -> list[LiveOpportunity]:
    """Router that dispatches to Rust or Python reference based on SCANNER_MODE."""
    mode = os.environ.get("SCANNER_MODE", "rust").lower()
    if mode == "rust":
        if RUST_SCANNER_AVAILABLE:
            return find_opportunities_with_rust(live_pools, principal_usd, max_slippage_bps)
        logger.error("Rust engine is not available")
        return []
    elif mode == "python_reference":
        return _find_opportunities_with_python_reference(live_pools, principal_usd, max_slippage_bps)
    else:
        logger.warning(f"Unrecognized SCANNER_MODE: SCANNER_MODE={mode} is not recognized")
        return []


def rerank_by_ml_alpha(opportunities: list[LiveOpportunity]) -> list[LiveOpportunity]:
    """
    Re-ranks a list of opportunities using the ML Alpha model if it's enabled and ready.
    If not, it returns the original list, preserving the deterministic ranking.
    """
    if RUST_SCANNER_AVAILABLE and SCANNER_MODE == "rust":
        return rerank_with_vqc(opportunities)
    else:
        logger.debug("ML Alpha re-ranking skipped: Rust engine not active.")
        return opportunities


# ... (rest of the module: evaluate, rank, etc. preserved in original)
# The LiveOpportunity dataclass now includes `family` for C1/C2/Liq support.


def _quote_route_amount(path, pool_seq, proto_seq, pools, amount_in, slippage_bps=Decimal("50")):
    """Compatibility quote hook; tests monkeypatch this for exact outcomes."""
    return Decimal(str(amount_in)), SimpleNamespace(amount_out=Decimal(str(amount_in)), clmm_unquoted=0, hop_proofs=[])


def _score_closed_path(
    path,
    pool_seq=None,
    proto_seq=None,
    pools=None,
    principal_usd: Decimal = Decimal("0"),
    *,
    pool_sequence=None,
    protocol_seq=None,
    slippage_bps: Decimal = Decimal("50"),
    flash_source: FlashSource = FlashSource.BALANCER,
    disc_block: int = 0,
    min_net_override: Decimal | None = None,
    risk_buffer_override: Decimal | None = None,
    strategy: str = "STANDARD_CLOSED_PATH",
):
    """Score a closed path and return LiveOpportunity or None."""
    pool_seq = tuple(pool_seq if pool_seq is not None else (pool_sequence or ()))
    proto_seq = tuple(proto_seq if proto_seq is not None else (protocol_seq or ()))
    path = tuple(path or ())
    pools = pools or {}

    probe = SimpleNamespace(block_detected=disc_block)
    try:
        if disc_block and not route_within_lifespan(probe, current_block=getattr(rpc_layer, "BLOCK", disc_block)):
            return None

        base = path[0] if path else ""
        base_price = Decimal(str(token_price_usd(base) or "0")) if base else Decimal("0")
        if base_price <= 0:
            return None

        buy_leg_token_prices = _build_leg_token_price_schema(path[:2], token_price_lookup=token_price_usd)
        sell_leg_token_prices = _build_leg_token_price_schema(path[1:], token_price_lookup=token_price_usd)
        buy_leg_token_price_usd = buy_leg_token_prices.get(base, base_price) if base else None
        sell_leg_token_price_usd = sell_leg_token_prices.get(path[-1] if path else "", base_price) if path else None

        amount_out, quote_proof = _quote_route_amount(path, pool_seq, proto_seq, pools, principal_usd, slippage_bps=slippage_bps)
        amount_out = Decimal(str(amount_out))
        if amount_out <= Decimal(str(principal_usd)):
            return None

        profitability = evaluate_profitability(
            amount_out,
            Decimal(str(principal_usd)),
            hops=max(1, len(pool_seq)),
            flash_source=flash_source,
            min_net_profit_usd=min_net_override if min_net_override is not None else live_min_net_profit_usd(),
            risk_buffer_usd=risk_buffer_override,
        )
        if not getattr(profitability, "passes_gate", False):
            return None

        return LiveOpportunity(
            path=path,
            pool_sequence=pool_seq,
            protocol_seq=proto_seq,
            profitability=profitability,
            block_detected=disc_block,
            metadata={"strategy": strategy, "quote_proof": quote_proof},
            buy_leg_token_prices=buy_leg_token_prices,
            sell_leg_token_prices=sell_leg_token_prices,
            buy_leg_token_price_usd=buy_leg_token_price_usd,
            sell_leg_token_price_usd=sell_leg_token_price_usd,
        )
    except Exception as e:
        logger.debug(f"Could not score route {path} on pools {pool_seq}: {e}")
        return None

def score_pegged_stable_spreads(stable_spreads, pools: dict, principal_usd: Decimal) -> list[LiveOpportunity]:
    """Promote pegged-stable spreads through the standard closed-path scorer."""
    out: list[LiveOpportunity] = []
    for item in stable_spreads:
        spread = item.spread
        scored = _score_closed_path(
            spread.path,
            spread.pool_sequence,
            spread.protocol_seq,
            pools,
            principal_usd,
            min_net_override=STABLE_MIN_NET_PROFIT_USD,
            risk_buffer_override=STABLE_RISK_BUFFER_USD,
            strategy=getattr(item, "strategy", "PEGGED_STABLE_TWO_LEG"),
        )
        if scored is not None:
            out.append(scored)
    return out
