from decimal import Decimal
from types import SimpleNamespace

from omega_v5.execution_truth import _truth_min_principal_floor
from omega_v5.sizing import optimize_route_principal


def test_below_minimum_route_cap_can_be_proof_sized_without_live_eligibility(monkeypatch):
    monkeypatch.setenv("OMEGA_ALLOW_BELOW_MIN_PRINCIPAL_PROOF", "true")
    monkeypatch.setattr("omega_v5.sizing.token_price_usd", lambda symbol: Decimal("1"))
    pools = {
        "P1": {
            "tokens": ["A", "B"],
            "reserves": [Decimal("1500"), Decimal("1500")],
        },
        "P2": {
            "tokens": ["B", "A"],
            "reserves": [Decimal("1500"), Decimal("1500")],
        },
    }

    sizing = optimize_route_principal(Decimal("10000"), ["P1", "P2"], pools)

    assert sizing.selected_principal_usd > 0
    assert sizing.selected_principal_usd < sizing.minimum_principal_usd
    assert sizing.live_principal_eligible is False
    assert sizing.proof_only_below_minimum is True
    assert sizing.method == "proof_only_below_min_flash_principal"


def test_truth_min_floor_stays_live_minimum_when_live_env_is_armed(monkeypatch):
    op = SimpleNamespace(metadata={"principal_gate": {"proof_only_below_minimum": True}})
    monkeypatch.setenv("OMEGA_TRUTH_ALLOW_BELOW_MIN_PRINCIPAL_PROOF", "true")
    monkeypatch.setenv("OMEGA_RUNTIME_MODE", "live")

    assert _truth_min_principal_floor(op) == Decimal("5000")


def test_truth_min_floor_allows_small_proof_sizes_only_in_dry_run(monkeypatch):
    op = SimpleNamespace(metadata={"principal_gate": {"proof_only_below_minimum": True}})
    monkeypatch.setenv("OMEGA_TRUTH_ALLOW_BELOW_MIN_PRINCIPAL_PROOF", "true")
    monkeypatch.setenv("OMEGA_RUNTIME_MODE", "dry_run")
    monkeypatch.setenv("EXECUTION_MODE", "dry_run")
    monkeypatch.setenv("LIVE_TRADING", "0")
    monkeypatch.setenv("OMEGA_TRUTH_MIN_PROOF_PRINCIPAL_USD", "25")

    assert _truth_min_principal_floor(op) == Decimal("25")
