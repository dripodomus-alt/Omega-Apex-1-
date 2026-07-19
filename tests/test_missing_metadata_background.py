from omega_v5 import missing_metadata_background as bg
from omega_v5.missing_metadata_apprentices import MetadataCase


def _patch_report_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(bg, "LATEST_BACKGROUND_REPORT", tmp_path / "missing_metadata_background_latest.json")
    monkeypatch.setattr(bg, "HISTORY_BACKGROUND_REPORT", tmp_path / "missing_metadata_background_history.jsonl")


def test_next_cycle_sleep_uses_active_interval_when_cases_remain():
    payload = {"case_count": 12, "processed": 3}

    sleep_seconds = bg.next_cycle_sleep_seconds(
        payload,
        active_interval_seconds=15,
        idle_interval_seconds=300,
        elapsed_seconds=2.4,
    )

    assert sleep_seconds == 12


def test_next_cycle_sleep_uses_idle_interval_when_no_cases():
    payload = {"case_count": 0, "processed": 0}

    sleep_seconds = bg.next_cycle_sleep_seconds(
        payload,
        active_interval_seconds=15,
        idle_interval_seconds=300,
        elapsed_seconds=2.4,
    )

    assert sleep_seconds == 297


def test_background_cycle_marks_active_when_cases_exist(monkeypatch, tmp_path):
    _patch_report_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(bg, "write_report", lambda payload: None)
    monkeypatch.setattr(bg, "xadd", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        bg,
        "collect_missing_metadata_cases",
        lambda include_price_missing=True: [
            MetadataCase(
                symbol="X",
                address="",
                blockers=("metadata_address_unresolved_after_all_sources",),
                attempted_sources=("runtime_registry",),
                pool_ids=("PX",),
            )
        ],
    )
    monkeypatch.setattr(
        bg,
        "run_assigned_apprentice_for_case",
        lambda case, runner_name, search_limit: {
            "case": case.__dict__,
            "assigned_runner": runner_name,
            "runners": [],
            "validations": [],
            "promotable_candidates": [],
        },
    )

    payload = bg.run_background_cycle(limit=1, search_limit=1)

    assert payload["loop_state"] == "active_missing_metadata_research"
    assert payload["continuous_cycle"]["active_while_cases_exist"] is True
    assert payload["processed"] == 1


def test_background_cycle_marks_idle_when_no_cases(monkeypatch, tmp_path):
    _patch_report_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(bg, "collect_missing_metadata_cases", lambda include_price_missing=True: [])

    payload = bg.run_background_cycle(limit=1, search_limit=1)

    assert payload["loop_state"] == "idle_no_missing_metadata_cases"
    assert payload["case_count"] == 0
    assert payload["processed"] == 0
