import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import executor_registry as registry


def test_polygon_rpc_uses_getblock_fallback(monkeypatch):
    monkeypatch.delenv("POLYGON_RPC_URL", raising=False)
    monkeypatch.delenv("ALCHEMY_HTTP_1", raising=False)
    monkeypatch.delenv("PRIVATE_RPC_URL", raising=False)
    monkeypatch.setenv("GETBLOCK_HTTP1", "https://example-rpc")

    assert registry.get_rpc_url("polygon") == "https://example-rpc"


def test_polygon_rpc_prioritizes_reliable_provider_over_generic_rpc(monkeypatch):
    monkeypatch.setenv("POLYGON_RPC_URL", "https://less-reliable-rpc")
    monkeypatch.setenv("GETBLOCK_HTTP1", "https://reliable-rpc")

    assert registry.get_rpc_url("polygon") == "https://reliable-rpc"


def test_polygon_rpc_skips_placeholder_values(monkeypatch):
    monkeypatch.setenv("POLYGON_RPC_URL", "https://polygon.example/YOUR_API_KEY")
    monkeypatch.setenv("GETBLOCK_HTTP1", "https://reliable-rpc")

    assert registry.get_rpc_url("polygon") == "https://reliable-rpc"


def test_polygon_wss_uses_getblock_fallback(monkeypatch):
    monkeypatch.delenv("WSS_PROVIDER", raising=False)
    monkeypatch.delenv("ALCHEMY_WSS", raising=False)
    monkeypatch.setenv("GETBLOCK_WSS1", "wss://example-wss")

    assert registry.get_wss_url("polygon") == "wss://example-wss"


def test_executor_wallet_falls_back_to_operational_wallet_aliases(monkeypatch):
    monkeypatch.delenv("PRIVATE_KEY", raising=False)
    monkeypatch.delenv("EXECUTOR_WALLET", raising=False)
    monkeypatch.setenv("DEPLOYER_WALLET", "0xaD3eF84259cFACB5D77a70911f85d39D2DBB49c6")

    assert (
        registry.get_configured_executor_wallet()
        == "0xaD3eF84259cFACB5D77a70911f85d39D2DBB49c6"
    )


def test_executor_registry_accepts_legacy_target_aliases(monkeypatch):
    monkeypatch.delenv("C1_CONTRACT_ADDRESS", raising=False)
    monkeypatch.delenv("C1_ARB_EXECUTOR_ADDRESS", raising=False)
    monkeypatch.delenv("C2_CONTRACT_ADDRESS", raising=False)
    monkeypatch.delenv("C2_ARB_EXECUTOR_ADDRESS", raising=False)
    monkeypatch.setenv("C1_TARGET", "0xe0cDe0255e1aFdcf0938Bed2A4329094b12b2642")
    monkeypatch.setenv("C2_TARGET", "0x31B591B984981Fb73BA111b08CeeF93AF150Dc22")

    configs = registry.get_executor_registry()

    assert configs["institutional_arbitrage"].checksum_address() == "0xe0cDe0255e1aFdcf0938Bed2A4329094b12b2642"
    assert configs["ultimate_arbitrage"].checksum_address() == "0x31B591B984981Fb73BA111b08CeeF93AF150Dc22"
