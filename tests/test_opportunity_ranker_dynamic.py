from decimal import Decimal
from unittest.mock import patch

from omega_v5.flash_loan import FlashLoanParams, FlashSource, Profitability
from omega_v5.stable_strategies import PeggedStableSpread
from omega_v5 import opportunity_ranker
from omega_v5.opportunity_ranker import LiveOpportunity
from omega_v5.ranker import CrossPoolSpread

def _profitability(gross, principal, *, passes=True, risk=Decimal("1")):
    flash = FlashLoanParams(
        source=FlashSource.BALANCER,
        asset="USDC",
        principal_usd=Decimal(str(principal)),
        fee_bps=Decimal("0"),
        fee_usd=Decimal("0"),
        repayment_usd=Decimal(str(principal)),
    )
    net = Decimal(str(gross)) - Decimal(str(principal)) - risk
    return Profitability(
        gross_amount_out=Decimal(str(gross)),
        flashloan=flash,
        gas_cost_usd=Decimal("0"),
        relay_tip_usd=Decimal("0"),
        risk_buffer_usd=risk,
        net_profit_usd=net,
        profit_to_gas=Decimal("999"),
        passes_gate=passes,
    )


def _spread():
    return CrossPoolSpread(
        path=["USDC", "DAI", "USDC"],
        pool_sequence=["buy", "sell"],
        protocol_seq=["UniswapV2", "UniswapV2"],
        buy_pool_id="buy",
        sell_pool_id="sell",
        buy_liquidity_key="buy",
        sell_liquidity_key="sell",
        buy_protocol="UniswapV2",
        sell_protocol="UniswapV2",
        buy_rate=Decimal("1"),
        sell_rate=Decimal("1.002"),
        buy_price=Decimal("1"),
        sell_price=Decimal("1.002"),
        round_trip_rate=Decimal("1.002"),
        gross_profit_pct=Decimal("0.2"),
        cross_protocol=False,
        cross_invariant=False,
    )


def test_stable_spreads_use_stable_profitability_overrides(monkeypatch):
    """
    Verify that `score_pegged_stable_spreads` calls the underlying scoring
    function with the correct low-profitability overrides.
    """
    pools = {
        "buy": {"id": "buy", "tokens": ["USDC", "DAI"], "total_executable_liquidity_usd": Decimal("1000000")},
        "sell": {"id": "sell", "tokens": ["DAI", "USDC"], "total_executable_liquidity_usd": Decimal("1000000")},
    }
    stable = PeggedStableSpread(
        spread=_spread(),
        peg_group="USD_STABLE",
        buy_deviation_bps=Decimal("1"),
        sell_deviation_bps=Decimal("1"),
        max_deviation_bps=Decimal("150"),
    )

    with patch("omega_v5.opportunity_ranker._score_closed_path") as mock_score:
        # Create a dummy LiveOpportunity to be returned by the mock
        mock_opp = LiveOpportunity(
            path=("USDC", "DAI", "USDC"),
            pool_sequence=("buy", "sell"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=_profitability(10010, 10000),
            metadata={"strategy": "PEGGED_STABLE_TWO_LEG"}
        )
        mock_score.return_value = mock_opp

        ops = opportunity_ranker.score_pegged_stable_spreads([stable], pools, principal_usd=Decimal("10000"))

        assert len(ops) == 1
        mock_score.assert_called_once()
        call_kwargs = mock_score.call_args.kwargs
        assert call_kwargs.get("min_net_override") == opportunity_ranker.STABLE_MIN_NET_PROFIT_USD
        assert call_kwargs.get("risk_buffer_override") == opportunity_ranker.STABLE_RISK_BUFFER_USD
        assert call_kwargs.get("strategy") == "PEGGED_STABLE_TWO_LEG"
