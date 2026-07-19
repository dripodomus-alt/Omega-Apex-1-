"""
V6 Controlled Concurrent Simulator

Runs multiple exact-call simulations concurrently (bounded) for different
sizes or sources, but still uses the exact same simulate_tx_payload from V5.

This improves throughput for truth ranking without weakening the gate.
All results must still pass final_truth_rank in execution_truth.py.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import List, Tuple, Optional, Callable

from ..omega_v5.execution import simulate_tx_payload, build_tx_payload
from ..omega_v5.config import V6_ENABLED, V6_SIM_CONCURRENCY
from ..omega_v5.opportunity_ranker import LiveOpportunity
from ..omega_v5.flash_loan import FlashSource


async def _simulate_one(
    tx_builder: Callable,
    size_usd: Decimal,
    source: FlashSource,
    from_addr: Optional[str] = None,
) -> Tuple[Decimal, bool, str]:
    """Run one simulation for a given size/source."""
    try:
        tx = tx_builder(size_usd=size_usd, flash_source=source)
        ok, detail = simulate_tx_payload(tx, from_addr=from_addr)
        return size_usd, ok, detail
    except Exception as e:
        return size_usd, False, f"sim_error:{e}"


async def simulate_route_sizes_concurrent(
    opportunity: LiveOpportunity,
    sizes_usd: List[Decimal],
    tx_builder: Callable,
    max_concurrency: int = 4,
    from_addr: Optional[str] = None,
) -> List[Tuple[Decimal, bool, str]]:
    """
    Concurrently test multiple sizes for the same route.

    Returns list of (size, success, detail).
    Concurrency is bounded to avoid overwhelming RPC.
    """
    if not V6_ENABLED:
        # Fall back to sequential
        results = []
        for sz in sizes_usd:
            tx = tx_builder(size_usd=sz, flash_source=opportunity.flash_source)
            ok, detail = simulate_tx_payload(tx, from_addr=from_addr)
            results.append((sz, ok, detail))
        return results

    sem = asyncio.Semaphore(max(1, min(max_concurrency, V6_SIM_CONCURRENCY)))

    async def limited_sim(size: Decimal):
        async with sem:
            return await _simulate_one(tx_builder, size, opportunity.flash_source, from_addr)

    tasks = [limited_sim(sz) for sz in sizes_usd]
    return await asyncio.gather(*tasks)


def run_controlled_simulations(
    opportunity: LiveOpportunity,
    sizes_usd: List[Decimal],
    tx_builder: Callable,
    from_addr: Optional[str] = None,
) -> List[Tuple[Decimal, bool, str]]:
    """
    Synchronous wrapper for the concurrent simulator.
    Safe to call from existing V5 sync code.
    """
    if not sizes_usd:
        return []

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context - run sequentially to avoid issues
            results = []
            for sz in sizes_usd:
                tx = tx_builder(size_usd=sz, flash_source=opportunity.flash_source)
                ok, detail = simulate_tx_payload(tx, from_addr=from_addr)
                results.append((sz, ok, detail))
            return results
        else:
            return loop.run_until_complete(
                simulate_route_sizes_concurrent(
                    opportunity, sizes_usd, tx_builder, from_addr=from_addr
                )
            )
    except RuntimeError:
        # No event loop - create one
        return asyncio.run(
            simulate_route_sizes_concurrent(
                opportunity, sizes_usd, tx_builder, from_addr=from_addr
            )
        )
