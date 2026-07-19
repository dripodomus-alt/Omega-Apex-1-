from omega_v5 import oracle_layer


class _FakeEth:
    def contract(self, address, abi):
        return object()


class _FakeCodec:
    def decode(self, *_args, **_kwargs):
        raise AssertionError("empty Chainlink bytes should be skipped before decode")


class _FakeWeb3:
    eth = _FakeEth()
    codec = _FakeCodec()


def test_chainlink_multicall_skips_empty_return_bytes(monkeypatch):
    monkeypatch.setattr(oracle_layer.rpc_layer, "RPC_LIVE", True)
    monkeypatch.setattr(oracle_layer.rpc_layer, "w3", _FakeWeb3())
    monkeypatch.setattr(oracle_layer, "CHAINLINK_FEEDS", {"WPOL": "0x0000000000000000000000000000000000000001"})
    monkeypatch.setattr(oracle_layer.rpc_layer, "_encode_fn", lambda *_args, **_kwargs: b"call")
    monkeypatch.setattr(
        oracle_layer.rpc_layer,
        "multicall3_aggregate",
        lambda calls: [(True, b""), (True, b"")],
    )

    assert oracle_layer._chainlink_prices_multicall(["WPOL"]) == {}
