from decimal import Decimal

from omega_v5 import token_calibration


def test_token_calibration_classifies_base_mid_and_oracle_state(monkeypatch):
    rates = {
        ("USDC", "WETH"): [{"pool_id": "P1"}, {"pool_id": "P3"}],
        ("WETH", "USDC"): [{"pool_id": "P2"}],
    }
    pools = {
        "P1": {
            "protocol": "UniswapV3",
            "tokens": ["USDC", "WETH"],
            "total_executable_liquidity_usd": Decimal("1000000"),
        },
        "P2": {
            "protocol": "Balancer",
            "tokens": ["WETH", "USDC"],
            "total_executable_liquidity_usd": Decimal("250000"),
        },
    }
    routes = [{"path": ["USDC", "WETH", "USDC"]}]

    monkeypatch.setattr(token_calibration, "refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr(token_calibration, "_fetch_live_decimals_multicall", lambda symbols: {"USDC": 6, "WETH": 18})
    monkeypatch.setattr(token_calibration, "redis_status", lambda: (True, "connected"))
    monkeypatch.setattr(token_calibration, "TOKEN_USD_SOURCE", {"USDC": "chainlink_multicall", "WETH": "chainlink_multicall"})
    monkeypatch.setattr(token_calibration, "token_price_usd", lambda symbol: Decimal("1") if symbol == "USDC" else Decimal("3000"))

    report = token_calibration.build_token_calibration_report(rates=rates, pools=pools, routes=routes)

    assert report["scope"]["base_tokens"] == ["USDC"]
    assert report["scope"]["mid_tokens"] == ["WETH"]
    assert report["all_clear"] is True
    rows = {row["symbol"]: row for row in report["tokens"]}
    assert rows["USDC"]["roles"] == ["base"]
    assert rows["WETH"]["roles"] == ["mid"]
    assert rows["USDC"]["directional_edges_out"] == 2
    assert rows["WETH"]["directional_edges_in"] == 2
    assert rows["USDC"]["oracle_source"] == "chainlink_multicall"
    assert rows["USDC"]["decimals_status"] == "pass"


def test_token_calibration_surfaces_missing_metadata_without_blocking(monkeypatch):
    rates = {("X", "Y"): [{"pool_id": "P1"}]}
    pools = {"P1": {"protocol": "Unknown", "tokens": ["X", "Y"]}}

    monkeypatch.setattr(token_calibration, "refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr(token_calibration, "_fetch_live_decimals_multicall", lambda symbols: {})
    monkeypatch.setattr(token_calibration, "redis_status", lambda: (False, "unavailable"))

    def missing_price(symbol):
        raise token_calibration.PriceUnavailable(symbol)

    monkeypatch.setattr(token_calibration, "token_price_usd", missing_price)

    report = token_calibration.build_token_calibration_report(rates=rates, pools=pools, routes=[])

    assert report["all_clear"] is False
    assert report["issue_counts"]["missing_registry_address"] == 2
    assert report["issue_counts"]["missing_registry_decimals"] == 2
    assert report["issue_counts"]["missing_live_oracle_price"] == 2
    assert report["runtime"]["redis_metadata_cache"]["detail"] == "unavailable"

def test_calibrate_tokens_compatibility_api(monkeypatch):
    monkeypatch.setattr(token_calibration, "refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr(token_calibration, "_fetch_live_decimals_multicall", lambda symbols: {"USDC": 6})
    monkeypatch.setattr(token_calibration, "redis_status", lambda: (True, "connected"))
    monkeypatch.setattr(token_calibration, "TOKEN_USD_SOURCE", {"USDC": "chainlink_multicall"})
    monkeypatch.setattr(token_calibration, "token_price_usd", lambda symbol: Decimal("1"))

    report = token_calibration.calibrate_tokens(["USDC"])

    assert report["scope"]["mode"] == "direct_token_list"
    assert report["scope"]["requested_tokens"] == ["USDC"]
    assert report["tokens"][0]["roles"] == ["requested"]