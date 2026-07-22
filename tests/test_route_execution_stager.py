from decimal import Decimal
from types import SimpleNamespace

from omega_v5 import route_execution_stager
from omega_v5.payload_envelope import UNIFIED_ROUTE_SCHEMA_VERSION
from omega_v5.pool_quality import V2_AUDIT_KEY
from omega_v5.ranker import compute_all_pool_rates
from omega_v5.route_execution_stager import (
    PreRankedRoute,
    build_route_identity,
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
    assert stats["rejection_counts"]["rejected_duplicate_liquidity_key"] == 1


def test_stage_report_uses_exact_net_gain_formula(monkeypatch):
    pools = {
        "P1": _v2_pool(("A", "B"), ("1000000000", "3000000000")),
        "P2": _v2_pool(("B", "A"), ("1000000000", "1000000000")),
    }
    rates = compute_all_pool_rates(pools)
    monkeypatch.setattr("omega_v5.route_execution_stager.rpc_layer.BLOCK", 11, raising=False)
    monkeypatch.setitem(route_execution_stager.rpc_layer.TOKEN_DECIMALS, "A", 6)
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
        discovery_block=10,
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
    assert row["opp_id"] == f"OPP-{row['quote_snapshot_id'][2:18]}"
    assert row["opp_id"] != route.opp_id
    assert row["opportunity_id"] == row["opp_id"]
    assert row["opportunity_id_frozen"] is True
    assert row["identity"]["hash_encoding"] == "keccak256(abi.encode(...))"
    assert row["identity"]["block_hash"].startswith("0x")
    assert len(row["identity"]["route_pair_id"]) == 66
    assert len(row["identity"]["quote_snapshot_id"]) == 66
    assert row["identity"]["route_pair_id"] == row["route_pair_id"]
    assert row["identity"]["quote_snapshot_id"] == row["quote_snapshot_id"]
    assert row["identity"]["initial_amount_raw_status"] == "resolved"
    assert row["identity"]["initial_amount_raw_source"] == "resolved_from_selected_principal_price_and_registry_decimals"
    assert row["identity"]["initial_amount_raw"] == str(int(Decimal(row["principal_usd"]) * Decimal("1000000")))
    assert formula["gas_payer"] == "user_wallet"
    assert formula["gas_accounting"]["native_symbol"] == "POL"

    schema = row["unified_route_envelope"]
    assert schema["schema_version"] == UNIFIED_ROUTE_SCHEMA_VERSION
    assert schema["opp_id"] == row["opp_id"]
    assert schema["route"]["path"] == ["A", "B", "A"]
    assert schema["staging"]["opportunity_id_frozen"] is True
    assert schema["staging"]["principal_usd"] == row["principal_usd"]
    assert schema["staging"]["identity"]["route_pair_id"] == row["route_pair_id"]
    assert schema["staging"]["identity"]["quote_snapshot_id"] == row["quote_snapshot_id"]
    assert schema["staging"]["route_pair_id"] == row["route_pair_id"]
    assert schema["staging"]["quote_snapshot_id"] == row["quote_snapshot_id"]
    assert schema["math"]["net_gain_usd"] == str(formula["net_gain_usd"])

    fee_ledger = schema["fees"]
    fee_keys = [
        "flashloan_fee_usd",
        "gas_cost_usd",
        "relay_or_private_submit_cost_usd",
        "risk_buffer_usd",
        "extra_slippage_buffer_usd",
        "hop_fees_usd",
    ]
    expected_fee_total = sum(Decimal(str(formula[key])) for key in fee_keys)
    assert fee_ledger["schema_version"] == "omega_v5.fee_ledger.v1"
    assert fee_ledger["normalized_unit"] == "NUSD"
    assert Decimal(fee_ledger["total_fee_usd"]) == expected_fee_total
    assert {item["fee_component"] for item in fee_ledger["components"]} >= {
        "flashloan_fee",
        "gas_fee",
        "relay_fee",
        "risk_buffer",
        "slippage_buffer",
        "pool_hop_fees",
    }
    assert fee_ledger["alignment_rule"] == "route_math_sums_only_normalized_fee_usd"
    assert list(schema).index("staging") < list(schema).index("fees") < list(schema).index("math")


def test_stage_rejects_quote_exception_without_aborting(monkeypatch):
    pools = {
        "P1": _v2_pool(("A", "B"), ("1000000000", "3000000000")),
        "P2": _v2_pool(("B", "A"), ("1000000000", "1000000000")),
    }
    monkeypatch.setattr("omega_v5.route_execution_stager.rpc_layer.BLOCK", 11, raising=False)
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
        discovery_block=10,
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
    assert row["opp_id"] == route.opp_id
    assert row["opportunity_id_frozen"] is True

    schema = row["unified_route_envelope"]
    assert schema["schema_version"] == UNIFIED_ROUTE_SCHEMA_VERSION
    assert schema["staging"]["stage"] == "exact_quote_exception"
    assert schema["staging"]["opportunity_id_frozen"] is True
    assert schema["fees"] == {}
    assert schema["math"] == {}
    assert list(schema).index("staging") < list(schema).index("fees") < list(schema).index("math")



def test_typed_route_identity_is_block_direction_and_size_safe():
    block_hash = "0x" + "ab" * 32
    route_ab = PreRankedRoute(
        path=("A", "B", "A"),
        pool_sequence=("P1", "P2"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        liquidity_keys=("P1", "P2"),
        route_class_seq=("NATIVE_POOL_ROUTE", "NATIVE_POOL_ROUTE"),
        approximate_gross_rate=Decimal("1.2"),
        approximate_raw_delta_usd=Decimal("2000"),
        approximate_raw_delta_bps=Decimal("2000"),
        edge_entries=(
            {"pool_id": "P1", "protocol": "UniswapV2", "token_in": "A", "token_out": "B", "fee_bps": Decimal("30")},
            {"pool_id": "P2", "protocol": "UniswapV2", "token_in": "B", "token_out": "A", "fee_bps": Decimal("30")},
        ),
        discovery_block=10,
        discovery_block_hash=block_hash,
    )
    route_ba = PreRankedRoute(
        path=("A", "B", "A"),
        pool_sequence=("P2", "P1"),
        protocol_seq=("UniswapV2", "UniswapV2"),
        liquidity_keys=("P2", "P1"),
        route_class_seq=("NATIVE_POOL_ROUTE", "NATIVE_POOL_ROUTE"),
        approximate_gross_rate=Decimal("1.2"),
        approximate_raw_delta_usd=Decimal("2000"),
        approximate_raw_delta_bps=Decimal("2000"),
        edge_entries=(
            {"pool_id": "P2", "protocol": "UniswapV2", "token_in": "A", "token_out": "B", "fee_bps": Decimal("30")},
            {"pool_id": "P1", "protocol": "UniswapV2", "token_in": "B", "token_out": "A", "fee_bps": Decimal("30")},
        ),
        discovery_block=10,
        discovery_block_hash=block_hash,
    )

    identity_ab_size_1 = build_route_identity(route_ab, initial_amount_raw=1_000_000_000)
    identity_ab_size_2 = build_route_identity(route_ab, initial_amount_raw=2_000_000_000)
    identity_ba_size_1 = build_route_identity(route_ba, initial_amount_raw=1_000_000_000)

    assert identity_ab_size_1["block_hash"] == block_hash
    assert identity_ab_size_1["block_hash_source"] == "route.discovery_block_hash"
    assert identity_ab_size_1["hash_encoding"] == "keccak256(abi.encode(...))"
    assert identity_ab_size_1["route_pair_id"] != identity_ba_size_1["route_pair_id"]
    assert identity_ab_size_1["route_pair_id"] == identity_ab_size_2["route_pair_id"]
    assert identity_ab_size_1["quote_snapshot_id"] != identity_ab_size_2["quote_snapshot_id"]
    assert identity_ab_size_1["initial_amount_raw"] == "1000000000"
    assert identity_ab_size_1["initial_amount_raw_status"] == "resolved"
    assert identity_ab_size_1["invariants"]["leg1_destination_differs_from_leg2_destination"] is True
