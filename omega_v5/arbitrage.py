#!/usr/bin/env python3
# ==============================================================================
# arbitrage.py -- Hybrid Python/Rust engine for arbitrage discovery.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from . import rust_engine
from .flash_loan import FlashLoanParams, FlashSource, Profitability
from .opportunity_ranker import LiveOpportunity


def _reconstruct_opportunities(opp_data_list: list[dict]) -> list[LiveOpportunity]:
    """Deserializes a list of opportunity dicts from Rust back into LiveOpportunity objects."""
    opps = []
    for data in opp_data_list:
        try:
            prof_data = data.pop("profitability", {})
            flash_data = prof_data.pop("flashloan", {})

            # Convert all flashloan fields to Decimal where needed
            for k, v in flash_data.items():
                if k not in ["asset", "source"] and v is not None:
                    flash_data[k] = Decimal(str(v))
            if "source" in flash_data and flash_data["source"]:
                flash_data["source"] = FlashSource(flash_data["source"])
            flash_params = FlashLoanParams(**flash_data)

            # Convert all other profitability fields to Decimal where possible
            for k, v in prof_data.items():
                if isinstance(v, (str, int, float)) and v is not None:
                    try:
                        prof_data[k] = Decimal(str(v))
                    except InvalidOperation:
                        pass  # Keep as is if not a valid decimal

            profitability = Profitability(flashloan=flash_params, **prof_data)

            data["path"] = tuple(data.get("path", []))
            data["pool_sequence"] = tuple(data.get("pool_sequence", []))
            data["protocol_seq"] = tuple(data.get("protocol_seq", []))
            opp = LiveOpportunity(profitability=profitability, **data)
            opps.append(opp)
        except (InvalidOperation, TypeError, KeyError, ValueError) as e:
            print(f"  [ARBITRAGE_ENGINE] Skipping malformed opportunity data from Rust: {e}")
            continue
    return opps


class ArbitrageGraphEngine:
    """
    Hybrid Python/Rust engine for arbitrage discovery.
    Supports both legacy rate-based Bellman-Ford and the new unified
    find-and-rank pipeline that offloads the entire process to Rust.
    """

    def __init__(self, rates_or_pools: dict, prices: dict | None = None):
        # The constructor is now flexible.
        # If `prices` is provided, we are in the new "unified" mode.
        # Otherwise, we are in the legacy "rates-only" mode.
        if prices is not None:
            self.mode = "unified"
            self.pools = rates_or_pools
            self.prices = prices
            self.rates = {}  # Not used in this mode
        else:
            self.mode = "legacy"
            self.rates = rates_or_pools
            self.pools = {}
            self.prices = {}

    def bellman_ford_all_sources(self) -> list[dict]:
        """
        Legacy method for Bellman-Ford cycle detection.
        This method is maintained for compatibility with older parts of the codebase.
        """
        if self.mode != "legacy":
            raise RuntimeError("bellman_ford_all_sources can only be called in legacy (rates-only) mode.")
        return rust_engine.rust_bellman_ford_cycles(self.rates)

    def find_and_rank_opportunities(
        self,
        *,
        principal_usd: Decimal,
        flash_source: FlashSource,
        stager_max_token_paths: int,
        stager_max_pre_ranked: int,
        stager_max_quote_options_per_pair: int,
    ) -> tuple[list[LiveOpportunity], dict[str, Any]]:
        """
        Delegates the entire discovery and ranking process to the Rust engine.
        This is the new, high-performance entry point.
        """
        if self.mode != "unified":
            raise RuntimeError("find_and_rank_opportunities can only be called in unified (pools/prices) mode.")

        ranked_dicts, report = rust_engine.rust_find_and_rank_opportunities(
            pools=self.pools,
            prices=self.prices,
            principal_usd=principal_usd,
            flash_source=flash_source.value,
            stager_max_token_paths=stager_max_token_paths,
            stager_max_pre_ranked=stager_max_pre_ranked,
            stager_max_quote_options_per_pair=stager_max_quote_options_per_pair,
        )

        ranked_opportunities = _reconstruct_opportunities(ranked_dicts)
        return ranked_opportunities, report