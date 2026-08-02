import sys
from pathlib import Path

from web3 import Web3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import liquidation_executor_contract as lec


def test_default_address_when_env_not_set(monkeypatch):
    monkeypatch.delenv("LIQUIDATION_EXECUTOR_ADDRESS", raising=False)

    assert (
        lec.get_configured_liquidation_executor_address()
        == "0xE41F15f340F8eFa17f9129e44F82A9C0ee9F8D94"
    )


def test_returns_none_for_undeployed_contract_marker(monkeypatch):
    monkeypatch.setenv("LIQUIDATION_EXECUTOR_ADDRESS", "NOT_DEPLOYED")

    assert lec.get_configured_liquidation_executor_address() is None


def test_get_liquidation_executor_respects_env_override(monkeypatch):
    test_override_address = "0x1111111111111111111111111111111111111111"
    captured = {}

    monkeypatch.setenv("LIQUIDATION_EXECUTOR_ADDRESS", test_override_address)

    class DummyExecutor:
        def __init__(self, w3, contract_address=None):
            captured["w3"] = w3
            captured["contract_address"] = contract_address

    monkeypatch.setattr(lec, "LiquidationExecutor", DummyExecutor)

    result = lec.get_liquidation_executor("fake-web3")

    assert result is not None
    assert captured["w3"] == "fake-web3"
    assert captured["contract_address"] == Web3.to_checksum_address(test_override_address)
