from decimal import Decimal

from omega_v5.calldata_semantic_audit import build_calldata_semantic_audit


def test_semantic_audit_reconciles_clean_checkpoint():
    report = build_calldata_semantic_audit(
        calldata="0x12345678" + "0" * 63 + "1",
        expected_selector="0x12345678",
        identity_sources={"staging": "abc", "calldata": "abc"},
        execution_parameters={"loan_size": "1000", "gas_limit": "650000"},
        economic={"gross_profit_usd": "12", "gas_cost_usd": "2", "flash_fee_usd": "1", "net_profit_usd": "9"},
        reserve_state={"before": ["1000", "1000"], "after": ["1001", "999.001"], "actual_input": "1", "output": "0.999"},
        protocol="V2_CPMM",
        tstore_report={"uses_eip_1153": False},
        relay={"relay_tip_usd": "0", "relay_tip_bps": "0", "relay_tip_base_usd": "9"},
    )
    assert report["structural_validity"] == "PASS"
    assert report["identity_parity"] == "PASS"
    assert report["economic_validity"] == "PASS"
    assert report["execution_verdict"] in {"SAFE", "UNKNOWN"}


def test_semantic_audit_fails_on_selector_and_net_mismatch():
    report = build_calldata_semantic_audit(
        calldata="0x12345678" + "0" * 64,
        expected_selector="0xdeadbeef",
        identity_sources={"staging": "abc", "calldata": "def"},
        economic={"gross_profit_usd": "12", "gas_cost_usd": "2", "net_profit_usd": "12"},
    )
    assert report["execution_verdict"] == "UNSAFE"
    assert "selector_mismatch" in report["critical_findings"]
    assert "identity_hash_mismatch" in report["critical_findings"]
    assert "net_profit_reconciliation_mismatch" in report["critical_findings"]