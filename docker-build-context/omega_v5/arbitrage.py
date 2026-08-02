#!/usr/bin/env python3
# ==============================================================================
# arbitrage.py -- Hybrid Python/Rust engine for arbitrage discovery.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, TYPE_CHECKING

from . import rust_engine
from .config import normalize_protocol
from .flash_loan import FlashLoanParams, FlashSource, Profitability
from .pricing.precision_pricing import (
    PrecisionPricingEngine,
    get_price_usd_x18,  # re-exported convenience from oracle bridge
    PRICE_SCALE,
)

if TYPE_CHECKING:
    from .opportunity_ranker import LiveOpportunity

# Re-export for the rest of the pipeline
__all__ = ["run_arbitrage_discovery", "PrecisionPricingEngine", "PRICE_SCALE"]


def _reconstruct_opportunities(opp_data_list: list[dict]) -> list[LiveOpportunity]:
    from .opportunity_ranker import LiveOpportunity
    """Deserializes a list of opportunity dicts from Rust back into LiveOpportunity objects.
    Ensures protocol_seq uses canonical internal keys.
    """
    opps = []
    for data in opp_data_list:
        try:
            prof_data = data.pop("profitability", {})
            flash_data = prof_data.pop("flashloan", {})

            # Convert all flashloan fields to Decimal where needed
            for k, v in flash_data.items():
                if k not in ["asset", "fee_bps"]:
                    try:
                        flash_data[k] = Decimal(str(v))
                    except Exception:
                        pass

            prof_data["flashloan"] = flash_data

            # Normalize protocol_seq to canonical keys
            if "protocol_seq" in data:
                raw = data["protocol_seq"]
                if isinstance(raw, (list, tuple)):
                    canon = []
                    for p in raw:
                        try:
                            canon.append(normalize_protocol(str(p)))
                        except Exception:
                            canon.append(str(p))
                    data["protocol_seq"] = tuple(canon)
                elif isinstance(raw, str):
                    try:
                        data["protocol_seq"] = (normalize_protocol(raw),)
                    except Exception:
                        data["protocol_seq"] = (raw,)

            opps.append(LiveOpportunity(**data))
        except Exception:
            continue
    return opps


def run_arbitrage_discovery(
    chain_id: int = 137,
    use_precision_pricing: bool = True,
) -> list[LiveOpportunity]:
    """
    Main entry for discovery.

    When use_precision_pricing=True (recommended), downstream code should
    obtain prices via PrecisionPricingEngine / get_price_usd_x18 so that
    all USD x18 values and atomic conversions follow the canonical rules.
    """
    raw_opps = rust_engine.discover_opportunities(chain_id=chain_id)

    # Example of how the pipeline can now obtain a precision price
    if use_precision_pricing:
        # In a real loop you would build a real engine with live sources
        # and a current PricingContext. This shows the import path.
        _ = get_price_usd_x18("USDC")  # exercises the legacy->precision bridge

    return _reconstruct_opportunities(raw_opps)


# Back-compat
def discover_opportunities(*args: Any, **kwargs: Any) -> list[LiveOpportunity]:
    return run_arbitrage_discovery(*args, **kwargs)


class ArbitrageGraphEngine:
    def discover(self, chain_id: int = 137) -> list[Any]:
        return run_arbitrage_discovery(chain_id=chain_id)

    def run(self, chain_id: int = 137) -> list[Any]:
        return self.discover(chain_id=chain_id)