import pytest
from decimal import Decimal
from types import SimpleNamespace

from omega_v5 import opportunity_ranker
from omega_v5.opportunity_ranker import LiveOpportunity
from omega_v5.flash_loan import FlashSource


@pytest.fixture
def mock_dependencies(monkeypatch):
    """
    Mocks the actual dependencies for the current _score_closed_path function.
    This is aligned with the control flow map from the code review.
    """
    # 1. Lifespan check
    monkeypatch.setattr(opportunity_ranker, "route_within_lifespan", lambda *args, **kwargs: True)
    monkeypatch.setattr(opportunity_ranker.rpc_layer, "BLOCK", 100)

    # 2. Base price check
    monkeypatch.setattr(opportunity_ranker, "token_price_usd", lambda symbol: Decimal("1.0"))

    # 3. Quoting
    monkeypatch.setattr(
        opportunity_ranker,
        "_quote_route_amount",
        lambda *args, **kwargs: (
            Decimal("10010"),
            SimpleNamespace(amount_out=Decimal("10010"), clmm_unquoted=0, hop_proofs=[]),
        ),
    )

    # 4. Profitability
    monkeypatch.setattr(
        opportunity_ranker,
        "evaluate_profitability",
        lambda *args, **kwargs: SimpleNamespace(
            passes_gate=True,
            flashloan=SimpleNamespace(principal_usd=Decimal("10000")),
            net_profit_usd=Decimal("5"),
        ),
    )

    # 5. Suppress logging during tests
    monkeypatch.setattr(opportunity_ranker.logger, "debug", lambda *args: None)
    monkeypatch.setattr(opportunity_ranker.logger, "warning", lambda *args, **kwargs: None)


@pytest.fixture
def default_kwargs():
    """Provides default valid keyword arguments for _score_closed_path."""
    return {
        "path": ("USDC", "WETH", "USDC"),
        "pool_seq": ("P1", "P2"),
        "proto_seq": ("UniswapV3", "UniswapV2"),
        "pools": {},
        "principal_usd": Decimal("10000"),
        "slippage_bps": Decimal("10"),
        "flash_source": FlashSource.BALANCER,
        "disc_block": 100,
    }


def test_score_closed_path_returns_live_opportunity_on_success(mock_dependencies, default_kwargs):
    """On a successful run, the function should return a LiveOpportunity instance."""
    result = opportunity_ranker._score_closed_path(**default_kwargs)
    assert isinstance(result, LiveOpportunity)
    # This also implicitly checks that it's not a tuple
    assert not isinstance(result, tuple)


def test_score_closed_path_returns_none_on_lifespan_failure(mock_dependencies, default_kwargs, monkeypatch):
    """If the lifespan check fails, it must return None, not a tuple."""
    monkeypatch.setattr(opportunity_ranker, "route_within_lifespan", lambda *args, **kwargs: False)
    result = opportunity_ranker._score_closed_path(**default_kwargs)
    assert result is None
    assert not isinstance(result, tuple)


def test_score_closed_path_returns_none_on_quote_failure(mock_dependencies, default_kwargs, monkeypatch):
    """If quoting returns an unprofitable amount, it must return None, not a tuple."""
    monkeypatch.setattr(
        opportunity_ranker,
        "_quote_route_amount",
        lambda *args, **kwargs: (Decimal("9990"), SimpleNamespace(amount_out=Decimal("9990"))),
    )
    result = opportunity_ranker._score_closed_path(**default_kwargs)
    assert result is None
    assert not isinstance(result, tuple)


def test_score_closed_path_returns_none_on_profitability_failure(mock_dependencies, default_kwargs, monkeypatch):
    """If profitability fails, it must return None, not a tuple."""
    monkeypatch.setattr(
        opportunity_ranker,
        "evaluate_profitability",
        lambda *args, **kwargs: SimpleNamespace(passes_gate=False),
    )
    result = opportunity_ranker._score_closed_path(**default_kwargs)
    assert result is None
    # This is the key assertion. If the function returns (None, "reason"), this will fail.
    assert not isinstance(result, tuple)