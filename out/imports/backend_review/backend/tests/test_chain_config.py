import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chain_config


def test_polygon_chain_config_prioritizes_reliable_provider(monkeypatch):
    monkeypatch.setenv("POLYGON_RPC_URL", "https://less-reliable-rpc")
    monkeypatch.setenv("GETBLOCK_HTTP1", "https://reliable-rpc")

    assert chain_config.get_rpc_url(137) == "https://reliable-rpc"


def test_polygon_chain_config_skips_placeholder_values(monkeypatch):
    monkeypatch.setenv("POLYGON_RPC_URL", "https://polygon.example/YOUR_API_KEY")
    monkeypatch.setenv("GETBLOCK_HTTP1", "https://reliable-rpc")

    assert chain_config.get_rpc_url(137) == "https://reliable-rpc"
