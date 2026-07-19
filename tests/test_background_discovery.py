from omega_v5.background_discovery import UNBOUNDED_DEFAULTS, apply_background_discovery_defaults


def test_background_discovery_applies_unbounded_defaults(monkeypatch):
    for key in UNBOUNDED_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BACKGROUND_DISCOVERY_UNBOUNDED", "true")

    applied = apply_background_discovery_defaults()

    assert applied["DISCOVERY_MAX_TOKEN_PAIRS"] == "0"
    assert applied["DISCOVERY_MAX_PROMOTED_POOLS"] == "0"
    assert applied["DYNAMIC_POOL_REGISTRY_MAX_POOLS"] == "0"
    assert applied["CURVE_POOL_REGISTRY_MAX_POOLS"] == "0"
    assert applied["POLYGON_TOKEN_LIST_MAX_CANDIDATES"] == "0"


def test_background_discovery_can_leave_existing_caps(monkeypatch):
    monkeypatch.setenv("BACKGROUND_DISCOVERY_UNBOUNDED", "false")
    monkeypatch.setenv("DISCOVERY_MAX_TOKEN_PAIRS", "320")

    applied = apply_background_discovery_defaults()

    assert applied == {}
    assert applied.get("DISCOVERY_MAX_TOKEN_PAIRS") is None
