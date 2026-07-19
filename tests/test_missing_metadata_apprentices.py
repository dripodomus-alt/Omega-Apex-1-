from omega_v5.missing_metadata_apprentices import (
    MetadataCase,
    assign_apprentice_runner,
    _parse_json_candidate,
    _validate_candidate,
    missing_cases_from_asset_report,
    run_apprentices_for_case,
)


def test_missing_cases_include_metadata_exhaustion_and_price_research():
    report = {
        "assets": [
            {
                "symbol": "X",
                "address": "",
                "metadata_resolution": {
                    "blockers": ["metadata_address_unresolved_after_all_sources"],
                    "attempted_sources": ["runtime_registry", "polygon_token_list_cache"],
                },
                "execution_blockers": ["price_unavailable"],
                "pool_ids": ["PX"],
            }
        ]
    }

    cases = missing_cases_from_asset_report(report)

    assert len(cases) == 1
    assert cases[0].symbol == "X"
    assert "metadata_address_unresolved_after_all_sources" in cases[0].blockers
    assert "price_unavailable_requires_external_research" in cases[0].blockers


def test_parse_json_candidate_strips_code_fence():
    text = '```json\n{"symbol":"X","address":"0x1111111111111111111111111111111111111111","decimals":18}\n```'

    candidate = _parse_json_candidate(text)

    assert candidate["symbol"] == "X"
    assert candidate["decimals"] == 18


def test_validation_rejects_candidate_without_evidence_urls():
    case = MetadataCase(
        symbol="X",
        address="",
        blockers=("metadata_address_unresolved_after_all_sources",),
        attempted_sources=("runtime_registry",),
        pool_ids=(),
    )
    candidate = {
        "symbol": "X",
        "address": "0x1111111111111111111111111111111111111111",
        "decimals": 18,
        "evidence_urls": [],
    }

    validation = _validate_candidate(candidate, case)

    assert validation["status"] == "rejected"
    assert "candidate_evidence_urls_missing" in validation["failures"]


def test_apprentice_run_skips_external_providers_without_keys(monkeypatch):
    for key in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "GROK_API_KEY",
        "METADATA_SEARCH_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)
    case = MetadataCase(
        symbol="X",
        address="",
        blockers=("metadata_address_unresolved_after_all_sources",),
        attempted_sources=("runtime_registry",),
        pool_ids=(),
    )

    result = run_apprentices_for_case(case)

    statuses = {row["runner"]: row["status"] for row in result["runners"]}
    assert statuses["web_search_apprentice"] == "skipped"
    assert statuses["openai_metadata_apprentice"] == "skipped"
    assert statuses["gemini_metadata_apprentice"] == "skipped"
    assert statuses["grok_metadata_apprentice"] == "skipped"
    assert result["promotable_candidates"] == []


def test_assigned_runner_routes_protocol_and_price_cases():
    protocol_case = MetadataCase(
        symbol="X",
        address="",
        blockers=("metadata_address_unresolved_after_all_sources",),
        attempted_sources=(),
        pool_ids=("pool-x",),
    )
    price_case = MetadataCase(
        symbol="Y",
        address="0x1111111111111111111111111111111111111111",
        blockers=("price_unavailable_requires_external_research",),
        attempted_sources=(),
        pool_ids=(),
    )

    assert assign_apprentice_runner(protocol_case, index=3) == "venue_protocol_apprentice"
    assert assign_apprentice_runner(price_case, index=3) == "public_market_apprentice"
