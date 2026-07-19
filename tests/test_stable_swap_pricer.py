from decimal import Decimal

from omega_v5 import stable_swap_pricer
from omega_v5.stable_swap_pricer import StableSwapPricer


def test_stable_swap_pricer_uses_oracle_layer_and_returns_metadata(monkeypatch):
    monkeypatch.setattr(stable_swap_pricer, "refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr(stable_swap_pricer, "TOKEN_USD_SOURCE", {"USDC": "chainlink_multicall", "USDT": "chainlink_multicall"})
    monkeypatch.setattr(stable_swap_pricer, "token_price_usd", lambda symbol: Decimal("1.001") if symbol == "USDC" else Decimal("0.999"))
    monkeypatch.setattr(stable_swap_pricer.redis_cache, "get_json", lambda key: None)
    monkeypatch.setattr(stable_swap_pricer.redis_cache, "set_json", lambda *args, **kwargs: None)

    quote = StableSwapPricer(cache_ttl_seconds=5).get_stable_to_stable_quote("USDC", "USDT")

    assert quote["ok"] is True
    assert Decimal(quote["rate"]) == Decimal("1.001") / Decimal("0.999")
    assert quote["from_source"] == "chainlink_multicall"
    assert quote["to_source"] == "chainlink_multicall"


def test_stable_swap_pricer_fails_closed_when_price_missing(monkeypatch):
    monkeypatch.setattr(stable_swap_pricer, "refresh_token_prices", lambda force=False: {})
    monkeypatch.setattr(stable_swap_pricer.redis_cache, "get_json", lambda key: None)

    def missing(symbol):
        raise stable_swap_pricer.PriceUnavailable(symbol)

    monkeypatch.setattr(stable_swap_pricer, "token_price_usd", missing)

    quote = StableSwapPricer().get_stable_to_stable_quote("USDC", "USDT")

    assert quote["ok"] is False
    assert quote["reason"] == "missing_live_stable_oracle_price"