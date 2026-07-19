from decimal import Decimal

from omega_v5.asset_state_research import build_asset_state_research
from omega_v5.pool_quality import V2_AUDIT_KEY


def _pool():
    return {
        "protocol": "UniswapV2",
        "tokens": ["USDC", "DAI"],
        "reserves": [Decimal("1000000"), Decimal("1000000")],
        "fee": Decimal("0.003"),
        "fee_bps": Decimal("30"),
        "address": "0x" + "2" * 40,
        "liquidity_key": "USDC-DAI",
        "total_executable_liquidity_usd": Decimal("2000000"),
        "executable_token_depth_usd": {
            "USDC": Decimal("1000000"),
            "DAI": Decimal("1000000"),
        },
        "_meta": {
            V2_AUDIT_KEY: {"status": "pass", "reject_reasons": []},
            "discovery_source": "unit_test",
        },
    }


def test_asset_state_research_marks_live_assets_ready(monkeypatch):
    monkeypatch.setattr("omega_v5.asset_state_research.refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr("omega_v5.asset_state_research.token_price_usd", lambda symbol: Decimal("1"))

    pools = {"P1": _pool()}
    rates = {
        ("USDC", "DAI"): [{"pool_id": "P1", "rate": Decimal("0.997"), "token_in": "USDC", "token_out": "DAI"}],
        ("DAI", "USDC"): [{"pool_id": "P1", "rate": Decimal("0.997"), "token_in": "DAI", "token_out": "USDC"}],
    }

    report = build_asset_state_research(pools=pools, rates=rates)
    rows = {row["symbol"]: row for row in report["assets"]}

    assert report["summary"]["asset_count"] >= 2
    assert rows["USDC"]["metadata_status"] == "pass"
    assert rows["USDC"]["live_state_status"] == "pass"
    assert rows["USDC"]["route_research_status"] == "ready_for_route_search"
    assert rows["USDC"]["pool_count"] == 1
    assert rows["USDC"]["directional_edges_out"] == 1
    assert rows["USDC"]["directional_edges_in"] == 1


def test_asset_state_research_exposes_missing_live_state_blockers(monkeypatch):
    monkeypatch.setattr("omega_v5.asset_state_research.refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr("omega_v5.asset_state_research.token_price_usd", lambda symbol: Decimal("1"))

    report = build_asset_state_research(pools={}, rates={})
    rows = {row["symbol"]: row for row in report["assets"]}

    assert "not_in_any_loaded_pool" in rows["USDC"]["execution_blockers"]
    assert "no_directional_quote_edges" in rows["USDC"]["execution_blockers"]


def test_asset_state_research_resolves_metadata_from_pool_when_runtime_missing(monkeypatch):
    monkeypatch.setattr("omega_v5.asset_state_research.refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr("omega_v5.asset_state_research.token_price_usd", lambda symbol: Decimal("1"))
    monkeypatch.delitem("omega_v5.rpc_layer.TOKEN_ADDRESSES", "XNEW", raising=False)
    monkeypatch.delitem("omega_v5.rpc_layer.TOKEN_DECIMALS", "XNEW", raising=False)

    pools = {
        "PX": {
            "protocol": "Curve",
            "tokens": ["XNEW", "USDC"],
            "token_addresses": ["0x" + "3" * 40, "0x" + "4" * 40],
            "token_decimals": [18, 6],
            "reserves": [Decimal("1000"), Decimal("1000")],
            "address": "0x" + "5" * 40,
            "total_executable_liquidity_usd": Decimal("2000"),
            "executable_token_depth_usd": {"XNEW": Decimal("1000"), "USDC": Decimal("1000")},
            "_meta": {"discovery_source": "curve_official_api"},
        }
    }
    rates = {
        ("XNEW", "USDC"): [{"pool_id": "PX", "rate": Decimal("1"), "token_in": "XNEW", "token_out": "USDC"}],
        ("USDC", "XNEW"): [{"pool_id": "PX", "rate": Decimal("1"), "token_in": "USDC", "token_out": "XNEW"}],
    }

    report = build_asset_state_research(pools=pools, rates=rates)
    row = {item["symbol"]: item for item in report["assets"]}["XNEW"]

    assert row["metadata_status"] == "pass"
    assert row["metadata_resolution"]["status"] == "resolved"
    assert row["metadata_resolution"]["address"] == "0x" + "3" * 40
    assert row["metadata_resolution"]["decimals"] == 18
    assert "live_pool_metadata:curve_official_api" in row["metadata_resolution"]["sources_used"]
    assert len(row["metadata_resolution"]["attempted_sources"]) >= 4
