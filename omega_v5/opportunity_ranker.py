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
)
from . import arbitrage
from . import rust_scanner
from . import scanner as py_scanner
from . import rpc_layer
from .pricing.net_delta import route_within_lifespan
from .sizing import compute_optimal_principal
from .payload_envelope import build_payload_envelope

logger = logging.getLogger(__name__)

RUST_SCANNER_AVAILABLE = rust_scanner.is_available()
SCANNER_MODE = os.environ.get("SCANNER_MODE", "rust").lower()


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


def find_opportunities(live_pools: dict, principal_usd: Decimal, max_slippage_bps: Decimal = Decimal("50")) -> list[LiveOpportunity]:
    """Router that dispatches to Rust or Python reference based on SCANNER_MODE."""
    mode = os.environ.get("SCANNER_MODE", "rust").lower()
    if mode == "rust" and RUST_SCANNER_AVAILABLE:
        return find_opportunities_with_rust(live_pools, principal_usd, max_slippage_bps)
    elif mode == "python_reference":
        return _find_opportunities_with_python_reference(live_pools, principal_usd, max_slippage_bps)
    else:
        logger.warning(f"SCANNER_MODE={mode} is not recognized")
        return []


# ... (rest of the module: evaluate, rank, etc. preserved in original)
# The LiveOpportunity dataclass now includes `family` for C1/C2/Liq support.
