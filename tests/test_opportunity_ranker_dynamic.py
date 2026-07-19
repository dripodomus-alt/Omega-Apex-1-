ELINE FROM BOOT UP TO WAKLLET CONFIG & NETWORK CHEfrom decimal import Decimal

from omega_v5.flash_loan import FlashLoanParams, FlashSource, Profitability
from omega_v5.sizing import dynamic_size_optimizer
from omega_v5.ranker import CrossPoolSpread
from omega_v5.stable_strategies import PeggedStableSpread
from omega_v5 import opportunity_ranker


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


def test_dynamic_optimizer_selects_bin_with_highest_scaled_net(monkeypatch):
    """Verify the optimizer correctly uses gross_rate to find the best bin."""
    monkeypatch.setattr("omega_v5.sizing.DYNAMIC_SIZE_OPT_BINS_USD", [Decimal("10000"), Decimal("20000")])
    monkeypatch.setattr("omega_v5.sizing.MAX_FLASH_PRINCIPAL_USD", Decimal("50000"))
    monkeypatch.setattr("omega_v5.sizing.MAX_ROUTE_TVL_FRACTION", Decimal("0.5"))

    # Net for 10k: 10000 * 1.005 - 10000 - 10 - 5 = 35
    # Net for 20k: 20000 * 1.005 - 20000 - 10 - 15 = 75  <- should be chosen
    monkeypatch.setattr(
        "omega_v5.sizing._apply_impact_penalty",
        lambda principal, min_tvl, gross: Decimal("5") if principal == 10000 else Decimal("15")
    )

    result = dynamic_size_optimizer(
        gross_amount_out_usd=Decimal("10050"), # From initial sizing
        gross_rate=Decimal("1.005"),
        min_tvl_usd=Decimal("100000"),
        base_gas_cost_usd=Decimal("10"),
    )

    assert result.best_principal_usd == Decimal("20000")
    assert result.best_profitability.net_profit_usd == Decimal("75")
    assert result.best_profitability.passes_gate is True
    assert result.best_method == "dynamic_bin_search_with_impact"


def test_stable_spreads_use_stable_profitability_overrides(monkeypatch):
    calls = []
    monkeypatch.setattr(opportunity_ranker, "route_quality_passed", lambda pool_sequence, pools: True)
    monkeypatch.setattr(opportunity_ranker, "token_price_usd", lambda symbol: Decimal("1"))
    monkeypatch.setattr(
        opportunity_ranker,
        "_quote_hop_amount",
        lambda pool, token_in, token_out, amount_in: amount_in * (Decimal("1.001") if pool["id"] == "sell" else Decimal("1")),
    )

    def fake_profitability(gross, principal, **kwargs):
        calls.append(kwargs)
        stable_gate = kwargs.get("min_net_profit_usd_override") == Decimal("0.25")
        return _profitability(gross, principal, passes=stable_gate, risk=kwargs.get("risk_buffer_usd_override") or Decimal("1"))

    monkeypatch.setattr(opportunity_ranker, "evaluate_profitability", fake_profitability)

    class _Pricer:
        def get_stable_to_stable_rate(self, *_args):
            return Decimal("1.0001")

    monkeypatch.setattr(opportunity_ranker, "StableSwapPricer", _Pricer)
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

    ops = opportunity_ranker.score_pegged_stable_spreads([stable], pools, principal_usd=Decimal("10000"))

    assert len(ops) == 1
    assert any(call.get("min_net_profit_usd_override") == Decimal("0.25") for call in calls)
    assert ops[0].metadata["raw_spread_engine"]["stable_profitability_gate"]["enabled"] is True
    assert ops[0].sizing is not None
