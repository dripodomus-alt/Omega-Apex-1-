from omega_v5.execution import sdk_core


def test_sdk_core_imports_without_geth_poa_middleware_dependency():
    assert hasattr(sdk_core, "get_web3_instance")
    assert hasattr(sdk_core, "submit_staged_routes")
    assert hasattr(sdk_core, "wait_for_receipts")
