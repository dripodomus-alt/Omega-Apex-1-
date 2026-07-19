from omega_v5 import mev


def test_mev_adapter_imports_without_optional_relay_dependencies():
    result = mev.submit_and_poll_for_receipt({"data": "0x"})

    assert result["ok"] is False
    assert result["status"] == "MEV_RELAY_UNAVAILABLE"
