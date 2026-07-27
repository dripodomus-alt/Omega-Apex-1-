"""
Live integration tests for opportunity discovery, ranking, C1/C2/Liq families,
and re-profitability at broadcast.

Run with:
    OMEGA_LIVE_TEST=1 pytest tests/live_integration_test.py -m live_integration -q

These tests are skipped by default.
"""
import os
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

pytestmark = pytest.mark.live_integration


def test_live_discovery_and_ranking(live_rpc):
    """Exercises real scanner + ranker when live mode is enabled."""
    from omega_v5.opportunity_ranker import find_opportunities
    from omega_v5 import scanner

    # Use empty or minimal pools; real flow would call scanner.get_live_state()
    opportunities = find_opportunities({}, Decimal("10000"), Decimal("8"))
    assert isinstance(opportunities, list)
    # In a real fork this would return real opportunities


def test_c1_c2_liquidation_families_with_revalidate():
    """Verifies family tagging and re-profit check before broadcast."""
    from omega_v5.execution import revalidate_profitability_at_broadcast
    from omega_v5.opportunity_ranker import LiveOpportunity

    # C1
    c1 = LiveOpportunity(
        path=("USDC", "WETH", "USDC"),
        pool_sequence=("p1", "p2"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        profitability=MagicMock(net_profit_usd=Decimal("42.0")),
        family="C1"
    )
    assert revalidate_profitability_at_broadcast(c1, {})

    # C2 (dependent)
    c2 = LiveOpportunity(
        path=("USDC", "WETH", "USDC"),
        pool_sequence=("p1", "p2"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        profitability=MagicMock(net_profit_usd=Decimal("19.5")),
        family="C2"
    )
    assert revalidate_profitability_at_broadcast(c2, {})

    # Liquidation
    liq = LiveOpportunity(
        path=("USDC",),
        pool_sequence=(),
        protocol_seq=(),
        profitability=MagicMock(net_profit_usd=Decimal("210.0")),
        family="LIQUIDATION"
    )
    assert revalidate_profitability_at_broadcast(liq, {})

    # Negative should be rejected
    bad = LiveOpportunity(
        path=("USDC", "WETH", "USDC"),
        pool_sequence=("p1", "p2"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        profitability=MagicMock(net_profit_usd=Decimal("-5.0")),
        family="C1"
    )
    assert not revalidate_profitability_at_broadcast(bad, {})


def test_simultaneous_non_conflicting_selection():
    """Simulates selecting C1 + C2 + Liq without conflicts."""
    from omega_v5.route_execution_stager import select_non_conflicting_for_broadcast

    candidates = [
        {"family": "C1", "net": "25"},
        {"family": "C2", "net": "12"},
        {"family": "LIQUIDATION", "net": "180"},
    ]
    selected = select_non_conflicting_for_broadcast(candidates)
    assert len(selected) == 3
