import importlib.util
from pathlib import Path


def load_module():
    module_path = Path(__file__).resolve().parents[1] / "tests" / "dry_run_25_cycles.py"
    spec = importlib.util.spec_from_file_location("dry_run_25_cycles", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_shadow_dry_run_report_contains_expected_summary_metrics():
    module = load_module()
    report = module.run_dry_cycles(num_cycles=3, use_live=False, emit_report=False)

    assert report["summary"]["cycles"] == 3
    assert report["summary"]["discovered_total"] >= report["summary"]["shadow_executed_total"]
    assert "execution_rate" in report["summary"]
    assert "discovery_rate" in report["summary"]
    assert "data_source" in report["summary"]
    assert report["summary"]["data_source"] == "synthetic"
    assert report["summary"]["accepted_total"] <= report["summary"]["shadow_executed_total"]


def test_shadow_dry_run_summary_exposes_pipeline_mode_and_live_discovery_count():
    module = load_module()
    report = module.run_dry_cycles(num_cycles=1, use_live=False, emit_report=False)

    assert report["summary"]["pipeline_mode"] in {"synthetic", "live"}
    assert "live_discovery_count" in report["summary"]
    assert report["summary"]["live_discovery_count"] >= 0


def test_live_mode_falls_back_to_synthetic_report_when_discovery_is_empty(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_discover_live_opportunities", lambda: [])

    report = module.run_dry_cycles(num_cycles=1, use_live=True, emit_report=False)

    assert report["summary"]["discovered_total"] >= 1
    assert report["summary"]["shadow_executed_total"] >= 1
    assert report["summary"]["data_source"] == "synthetic_fallback"
