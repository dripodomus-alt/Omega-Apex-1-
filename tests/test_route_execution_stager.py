from decimal import Decimal
from types import SimpleNamespace

from omega_v5.pool_quality import V2_AUDIT_KEY
from omega_v5.ranker import compute_all_pool_rates
from omega_v5.route_execution_stager import (
    PreRankedRoute,
    build_stage_report,
    enumerate_closed_token_paths,
    pre_rank_routes,
    stage_pre_ranked_route,
)
from omega_v5.flash_loan import MIN_NET_PROFIT_USD


def _v2_pool(tokens, reserves, fee=Decimal("0.003")):
    return {
        "protocol": "UniswapV2",
        "tokens": list(tokens),
        "reserves": [Decimal(str(item)) for item in reserves],
        "fee": Decimal(str(fee)),
        "fee_bps": Decimal("30"),
        "route_class": "NATIVE_POOL_ROUTE",
        "liquidity_key": ":".join(tokens),
        "address": "0x" + "1" * 40,
        "total_executable_liquidity_usd": Decimal("1000000000"),
        "_meta": {V2_AUDIT_KEY: {"status": "pass", "reject_reasons": []}},
    }


def test_enumerates_closed_two_three_and_four_hop_token_paths():
    rates = {
        ("A", "B"): [{"pool_id": "AB"}],
        ("B", "A"): [{"pool_id": "BA"}],
        ("A", "C"): [{"pool_id": "AC"}],
        ("C", "D"): [{"pool_id": "CD"}],
        ("D", "A"): [{"pool_id": "DA"}],
        ("A", "E"): [{"pool_id": "AE"}],
        ("E", "F"): [{"pool_id": "EF"}],
        ("F", "G"): [{"pool_id": "FG"}],
        ("G", "A"): [{"pool_id": "GA"}],
    }

    paths = set(enumerate_closed_token_paths(rates, hops=(2, 3, 4), base_tokens=["A"]))

    assert ("A", "B", "A") in paths
    assert ("A", "C", "D", "A") in paths
    assert ("A", "E", "F", "G", "A") in paths


def test_pre_rank_rejects_duplicate_liquidity_key():
    pools = {
        "P1": _v2_pool(("A", "B"), ("1000000", "2000000")),
    }
    rates = {
        ("A", "B"): [{
            "pool_id": "P1",
            "protocol": "UniswapV2",
            "route_class": "NATIVE_POOL_ROUTE",
            "liquidity_key": "same",
            "token_in": "A",
            "token_out": "B",
            "rate": Decimal("2"),
        }],
        ("B", "A"): [{
            "pool_id": "P1",
            "protocol": "UniswapV2",
            "route_class": "NATIVE_POOL_ROUTE",
            "liquidity_key": "same",
            "token_in": "B",
            "token_out": "A",
            "rate": Decimal("0.6"),
        }],
    }

    candidates, stats = pre_rank_routes(
        rates,
        pools,
        principal_usd=Decimal("10000"),
        hops=(2,),
        base_tokens=["A"],
    )

    assert candidates == []
    assert stats["rejection_counts"]["duplicate_liquidity_key"] == 1


def test_stage_report_uses_exact_net_gain_formula(monkeypatch):
    pools = {
        "P1": _v2_pool(("A", "B"), ("1000000000", "3000000000")),
        "P2": _v2_pool(("B", "A"), ("1000000000", "1000000000")),
    }
    rates = compute_all_pool_rates(pools)
    monkeypatch.setattr("omega_v5.route_execution_stager.token_price_usd", lambda symbol: Decimal("1"))
    monkeypatch.setattr("omega_v5.flash_loan.current_gas_price_gwei", lambda: (Decimal("1"), "test_gas"))
    monkeypatch.setattr("omega_v5.flash_loan.current_pol_price_usd", lambda: (Decimal("1"), "test_pol"))
    monkeypatch.setattr(
        "omega_v5.route_execution_stager.quote_route_for_executor",
        lambda *args, **kwargs: SimpleNamespace(
            amount_out=Decimal("12000"),
            clmm_quoted=0,
            clmm_unquoted=0,
            hop_proofs=[],
        ),
    )

    route = PreRankedRoute(
        path=("A", "B", "A"),
        pool_sequence=("P1", "P2"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        liquidity_keys=("P1", "P2"),
        route_class_seq=("NATIVE_POOL_ROUTE", "NATIVE_POOL_ROUTE"),
        approximate_gross_rate=Decimal("1.2"),
        approximate_raw_delta_usd=Decimal("2000"),
        approximate_raw_delta_bps=Decimal("2000"),
        edge_entries=(
            {
                "pool_id": "P1",
                "protocol": "UniswapV2",
                "liquidity_key": "P1",
                "token_in": "A",
                "token_out": "B",
                "rate": Decimal("2"),
                "invariant": "constant_product",
            },
            {
                "pool_id": "P2",
                "protocol": "UniswapV2",
                "liquidity_key": "P2",
                "token_in": "B",
                "token_out": "A",
                "rate": Decimal("0.6"),
                "invariant": "constant_product",
            },
        ),
    )
    row = stage_pre_ranked_route(
        route,
        pools,
        requested_principal_usd=Decimal("10000"),
        slippage_bps=Decimal("10"),
    )

    assert "net_formula" in row
    formula = row.get("net_formula", {})
    assert "net_gain_usd" in formula
    assert formula["net_gain_usd"] > MIN_NET_PROFIT_USD

    assert row["status"] in {"staged_for_executor_truth", "rejected"}
    assert row["sizing"]
    assert formula["gas_payer"] == "user_wallet"
    assert formula["gas_accounting"]["native_symbol"] == "POL"


def test_stage_rejects_quote_exception_without_aborting(monkeypatch):
    pools = {
        "P1": _v2_pool(("A", "B"), ("1000000000", "3000000000")),
        "P2": _v2_pool(("B", "A"), ("1000000000", "1000000000")),
    }
    monkeypatch.setattr("omega_v5.route_execution_stager.token_price_usd", lambda symbol: Decimal("1"))

    def raise_quote(*args, **kwargs):
        raise ValueError("bad quote data")

    monkeypatch.setattr("omega_v5.route_execution_stager.quote_route_for_executor", raise_quote)
    route = PreRankedRoute(
        path=("A", "B", "A"),
        pool_sequence=("P1", "P2"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        liquidity_keys=("P1", "P2"),
        route_class_seq=("NATIVE_POOL_ROUTE", "NATIVE_POOL_ROUTE"),
        approximate_gross_rate=Decimal("1.2"),
        approximate_raw_delta_usd=Decimal("2000"),
        approximate_raw_delta_bps=Decimal("2000"),
        edge_entries=(),
    )

    row = stage_pre_ranked_route(
        route,
        pools,
        requested_principal_usd=Decimal("10000"),
        slippage_bps=Decimal("10"),
    )

    assert row["status"] == "rejected"
    assert row["stage"] == "exact_quote_exception"
    assert row["reason"] == "ValueError"
