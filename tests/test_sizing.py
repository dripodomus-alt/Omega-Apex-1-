import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from omega_v5.sizing import dynamic_size_optimizer, optimize_principal_with_dynamic
from omega_v5.opportunity_ranker import LiveOpportunity
from omega_v5.flash_loan import FlashSource, Profitability


@pytest.fixture
def mock_profitability():
    """Creates a mock Profitability object."""
    def _mock_profitability(net_profit_usd, passes_gate=True):
        mock_prof = MagicMock(spec=Profitability)
        mock_prof.net_profit_usd = Decimal(str(net_profit_usd))
        mock_prof.passes_gate = passes_gate
        return mock_prof
    return _mock_profitability


def test_dynamic_size_optimizer_finds_peak(mock_profitability):
    """
    Tests that the optimizer finds the principal that maximizes net profit
    on a simple parabolic profit curve.
    """
    # Profit curve: π(p) = -0.001 * (p - 20000)^2 + 100
    # Peak profit of 100 at principal of 20000.
    def profit_function(principal_usd: Decimal):
        profit = Decimal("-0.000001") * (principal_usd - 20000)**2 + 100
        return mock_profitability(profit, passes_gate=profit > 0)

    best_principal, best_profit = dynamic_size_optimizer(
        profit_function=profit_function,
        min_principal=Decimal("1000"),
        max_principal=Decimal("40000"),
        steps=30,
    )

    assert best_profit is not None
    # The optimizer samples points, so it should be close to the true peak.
    assert 19000 < best_principal < 21000
    assert 99 < best_profit.net_profit_usd <= 100


def test_dynamic_size_optimizer_handles_no_profit(mock_profitability):
    """
    Tests that the optimizer returns zero/None when no principal size is profitable.
    """
    def profit_function(principal_usd: Decimal):
        return mock_profitability(-10, passes_gate=False)

    best_principal, best_profit = dynamic_size_optimizer(
        profit_function=profit_function,
        min_principal=Decimal("1000"),
        max_principal=Decimal("50000"),
        steps=10,
    )

    assert best_principal == Decimal("0")
    assert best_profit is None


def test_dynamic_size_optimizer_stops_on_decline(mock_profitability):
    """
    Tests that the optimizer stops searching after the profit peak has clearly passed
    to save on unnecessary quoting/simulation.
    """
    call_count = 0

    def profit_function(principal_usd: Decimal):
        nonlocal call_count
        call_count += 1
        # Simple linear rise then fall
        if principal_usd <= 20000:
            profit = principal_usd / 100
        else:
            profit = (40000 - principal_usd) / 100
        return mock_profitability(profit, passes_gate=profit > 0)

    dynamic_size_optimizer(
        profit_function=profit_function,
        min_principal=Decimal("1000"),
        max_principal=Decimal("100000"),
        steps=100, # High number of steps to test early exit
    )

    # With 100 steps, a full search would call the function 100 times.
    # The early exit on profit decline should stop it much sooner.
    assert call_count < 50


@patch("omega_v5.sizing.evaluate_profitability")
@patch("omega_v5.sizing.estimate_route_tvl_usd")
def test_optimize_principal_with_dynamic_respects_tvl_cap(
    mock_estimate_tvl, mock_evaluate_profitability, mock_profitability
):
    """
    Verifies that the main sizing wrapper correctly caps the search space
    based on the route's TVL.
    """
    # Mock a route with a bottleneck TVL of $100,000
    mock_estimate_tvl.return_value = Decimal("100000")

    # Mock a simple quote function
    def quote_fn(p):
        return p * Decimal("1.01")

    # Mock profitability to always be positive
    mock_evaluate_profitability.side_effect = lambda **kwargs: mock_profitability(
        kwargs["principal_usd"] * Decimal("0.001")
    )

    # Mock a LiveOpportunity
    mock_opp = MagicMock(spec=LiveOpportunity)
    mock_opp.pool_sequence = ["P1", "P2"]
    mock_opp.path = ["USDC", "WETH", "USDC"]
    mock_opp.flash_source = FlashSource.BALANCER

    # With MAX_ROUTE_TVL_FRACTION=0.15 (default), the cap should be $15,000
    # The search space upper bound will be min(MAX_FLASH_PRINCIPAL_USD, 15000)
    # Let's assume MAX_FLASH_PRINCIPAL_USD is 100,000.
    with patch("omega_v5.sizing.MAX_FLASH_PRINCIPAL_USD", Decimal("100000")):
        with patch("omega_v5.sizing.FLASH_ROUTE_TVL_FRACTIONS", [Decimal("0.15")]):
            sizing_result = optimize_principal_with_dynamic(
                opportunity=mock_opp,
                live_pools={},
                quote_function=quote_fn,
            )

    # The upper bound of the search should be capped at 15% of the TVL
    assert sizing_result.search_upper_bound_usd == Decimal("15000")
    # The selected principal must be less than or equal to this cap
    assert sizing_result.selected_principal_usd <= Decimal("15000")


@patch("omega_v5.sizing.evaluate_profitability")
@patch("omega_v5.sizing.estimate_route_tvl_usd")
def test_optimize_principal_with_dynamic_handles_low_tvl(
    mock_estimate_tvl, mock_evaluate_profitability, mock_profitability
):
    """
    Verifies that the sizer handles cases where the TVL cap is below the
    minimum flash loan principal.
    """
    # TVL is so low that the cap is below MIN_FLASH_PRINCIPAL_USD
    mock_estimate_tvl.return_value = Decimal("10000") # -> cap of $1500
    mock_evaluate_profitability.side_effect = lambda **kwargs: mock_profitability(-10, False)

    mock_opp = MagicMock(spec=LiveOpportunity)
    mock_opp.pool_sequence = ["P1"]
    mock_opp.path = ["USDC", "WETH", "USDC"]
    mock_opp.flash_source = FlashSource.BALANCER

    with patch("omega_v5.sizing.MIN_FLASH_PRINCIPAL_USD", Decimal("5000")):
        sizing_result = optimize_principal_with_dynamic(opportunity=mock_opp, live_pools={}, quote_function=lambda p: p)

    # The search space should be clamped to the minimum, but no profitable size is found
    assert sizing_result.search_upper_bound_usd == Decimal("5000")
    assert sizing_result.selected_principal_usd == Decimal("0")
    assert sizing_result.max_profit_usd == Decimal("0")