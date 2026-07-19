from omega_v5 import apprentice_metadata_registry as registry
from omega_v5 import rpc_layer


def _patch_registry_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(registry, "PROPOSALS_PATH", tmp_path / "proposals.json")
    monkeypatch.setattr(registry, "APPROVED_PATH", tmp_path / "approved.json")
    monkeypatch.setattr(registry, "REJECTED_PATH", tmp_path / "rejected.json")
    monkeypatch.setattr(registry, "REVIEW_REPORT_PATH", tmp_path / "review.json")
    monkeypatch.setattr(registry, "REASONING_REPORT_PATH", tmp_path / "reasoning.md")


def _complete_candidate():
    return {
        "symbol": "XAPPTEST",
        "name": "Apprentice Test Token",
        "address": "0x1111111111111111111111111111111111111111",
        "decimals": 18,
        "evidence_urls": ["https://example.com/token/xapptest"],
    }


def _promotable_validation():
    return {
        "status": "promotable",
        "symbol": "XAPPTEST",
        "address": "0x1111111111111111111111111111111111111111",
        "decimals": 18,
        "evidence_urls": ["https://example.com/token/xapptest"],
        "onchain": {
            "status": "pass",
            "symbol": "XAPPTEST",
            "name": "Apprentice Test Token",
            "decimals": 18,
        },
    }


def test_review_approves_complete_apprentice_proposal(monkeypatch, tmp_path):
    _patch_registry_paths(monkeypatch, tmp_path)
    monkeypatch.delitem(rpc_layer.TOKEN_ADDRESSES, "XAPPTEST", raising=False)
    monkeypatch.delitem(rpc_layer.TOKEN_DECIMALS, "XAPPTEST", raising=False)
    monkeypatch.delitem(rpc_layer.TOKEN_DISCOVERY_STATUS, "XAPPTEST", raising=False)
    monkeypatch.delitem(rpc_layer.ADDRESS_TO_SYMBOL, "0x1111111111111111111111111111111111111111", raising=False)

    registry.write_missing_metadata_proposal(
        case={"symbol": "XAPPTEST"},
        runner="openai_metadata_apprentice",
        candidate=_complete_candidate(),
        validation=_promotable_validation(),
    )

    report = registry.review_apprentice_metadata_promotions(apply=False)

    assert report["approved_count"] == 1
    assert report["rejected_count"] == 0
    assert report["applied_count"] == 0
    assert report["approved"][0]["decision_reasoning"]["decision"] == "approved"
    assert (tmp_path / "reasoning.md").exists()
    assert "Approved because all promotion gates passed" in (tmp_path / "reasoning.md").read_text(encoding="utf-8")


def test_review_apply_promotes_to_rpc_layer_registry(monkeypatch, tmp_path):
    _patch_registry_paths(monkeypatch, tmp_path)
    monkeypatch.delitem(rpc_layer.TOKEN_ADDRESSES, "XAPPTEST", raising=False)
    monkeypatch.delitem(rpc_layer.TOKEN_DECIMALS, "XAPPTEST", raising=False)
    monkeypatch.delitem(rpc_layer.TOKEN_DISCOVERY_STATUS, "XAPPTEST", raising=False)
    monkeypatch.delitem(rpc_layer.ADDRESS_TO_SYMBOL, "0x1111111111111111111111111111111111111111", raising=False)

    registry.write_missing_metadata_proposal(
        case={"symbol": "XAPPTEST"},
        runner="gemini_metadata_apprentice",
        candidate=_complete_candidate(),
        validation=_promotable_validation(),
    )

    report = registry.review_apprentice_metadata_promotions(apply=True)

    assert report["applied_count"] == 1
    assert rpc_layer.TOKEN_ADDRESSES["XAPPTEST"].lower() == "0x1111111111111111111111111111111111111111"
    assert rpc_layer.TOKEN_DECIMALS["XAPPTEST"] == 18
    assert rpc_layer.TOKEN_DISCOVERY_STATUS["XAPPTEST"] == "APPRENTICE_METADATA_PROMOTED_REVIEWED"


def test_review_rejects_without_onchain_metadata_pass(monkeypatch, tmp_path):
    _patch_registry_paths(monkeypatch, tmp_path)
    validation = _promotable_validation()
    validation["onchain"] = {"status": "skipped", "reason": "rpc_not_connected"}

    registry.write_missing_metadata_proposal(
        case={"symbol": "XAPPTEST"},
        runner="grok_metadata_apprentice",
        candidate=_complete_candidate(),
        validation=validation,
    )

    report = registry.review_apprentice_metadata_promotions(apply=True)

    assert report["approved_count"] == 0
    assert report["rejected_count"] == 1
    assert "onchain_metadata_not_verified" in report["rejected"][0]["promotion_reasons"]
    reasoning = report["rejected"][0]["decision_reasoning"]
    assert reasoning["decision"] == "rejected"
    assert any("connect RPC and verify bytecode" in action for action in reasoning["next_actions"])
