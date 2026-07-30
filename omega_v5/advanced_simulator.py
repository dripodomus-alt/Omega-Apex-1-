"""Controlled concurrent exact-call simulation helpers."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Optional

from . import config
from .execution import simulate_tx_payload
from .flash_loan import FlashSource
if TYPE_CHECKING:
    from .opportunity_ranker import LiveOpportunity


def _v6_enabled() -> bool:
    return bool(getattr(config, "V6_ENABLED", False))


def _v6_sim_concurrency() -> int:
    try:
        return max(1, int(getattr(config, "V6_SIM_CONCURRENCY", 4)))
    except Exception:
        return 4


async def _simulate_one(
    tx_builder: Callable,
    size_usd: Decimal,
    source: FlashSource,
    from_addr: Optional[str] = None,
) -> tuple[Decimal, bool, str]:
    try:
        tx = tx_builder(size_usd=size_usd, flash_source=source)
        ok, detail = simulate_tx_payload(tx, from_addr=from_addr)
        return size_usd, ok, detail
    except Exception as exc:
        return size_usd, False, f"sim_error:{type(exc).__name__}:{exc}"


async def simulate_route_sizes_concurrent(
    opportunity: "LiveOpportunity" | Any,
    sizes_usd: list[Decimal],
    tx_builder: Callable,
    max_concurrency: int = 4,
    from_addr: Optional[str] = None,
) -> list[tuple[Decimal, bool, str]]:
    if not _v6_enabled():
        return [
            await _simulate_one(tx_builder, size, opportunity.flash_source, from_addr)
            for size in sizes_usd
        ]

    sem = asyncio.Semaphore(max(1, min(int(max_concurrency), _v6_sim_concurrency())))

    async def limited(size: Decimal) -> tuple[Decimal, bool, str]:
        async with sem:
            return await _simulate_one(tx_builder, size, opportunity.flash_source, from_addr)

    return await asyncio.gather(*(limited(size) for size in sizes_usd))


def run_controlled_simulations(
    opportunity: "LiveOpportunity" | Any,
    sizes_usd: list[Decimal],
    tx_builder: Callable,
    from_addr: Optional[str] = None,
) -> list[tuple[Decimal, bool, str]]:
    if not sizes_usd:
        return []
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return [
                (size, *simulate_tx_payload(tx_builder(size_usd=size, flash_source=opportunity.flash_source), from_addr=from_addr))
                for size in sizes_usd
            ]
        return loop.run_until_complete(
            simulate_route_sizes_concurrent(opportunity, sizes_usd, tx_builder, from_addr=from_addr)
        )
    except RuntimeError:
        return asyncio.run(
            simulate_route_sizes_concurrent(opportunity, sizes_usd, tx_builder, from_addr=from_addr)
        )


