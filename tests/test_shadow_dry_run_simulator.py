import importlib.util
from pathlib import Path
from types import SimpleNamespace


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
    context = SimpleNamespace(engine=SimpleNamespace(pools_loading=False, pools={"p": object()}))
    monkeypatch.setattr(module, "_get_live_discovery_context", lambda: context)
    monkeypatch.setattr(module, "_discover_live_opportunities", lambda _context=None: [])

    report = module.run_dry_cycles(num_cycles=1, use_live=True, emit_report=False)

    assert report["summary"]["discovered_total"] >= 1
    assert report["summary"]["shadow_executed_total"] >= 1
    assert report["summary"]["data_source"] == "synthetic_fallback"


def test_live_mode_initializes_discovery_context_once(monkeypatch):
    module = load_module()
    calls = {"init": 0, "discover": 0}
    context = SimpleNamespace(engine=SimpleNamespace(pools_loading=False, pools={"p": object()}))

    def fake_context():
        calls["init"] += 1
        return context

    def fake_discover(received_context=None):
        calls["discover"] += 1
        assert received_context is context
        return []

    monkeypatch.setattr(module, "_get_live_discovery_context", fake_context)
    monkeypatch.setattr(module, "_discover_live_opportunities", fake_discover)

    report = module.run_dry_cycles(num_cycles=3, use_live=True, emit_report=False)

    assert calls == {"init": 1, "discover": 3}
    assert report["summary"]["data_source"] == "synthetic_fallback"


def test_live_pool_wait_timeout_prints_bootstrap_diagnostics(monkeypatch, capsys):
    module = load_module()

    class LoadingEngine:
        pools_loading = True
        pools = {}

        def get_pool_bootstrap_status(self):
            return {
                "state": "loading",
                "providers_connected": ["polygon_rpc"],
                "pools_discovered": 4,
                "local_pools": 2,
                "unique_pools": 6,
                "pools_with_reserves": 0,
                "pools_normalized": 0,
                "pools_published": 0,
                "active_scanners": ["multicall3"],
                "failed_scanners": ["curve"],
                "cache_ready": False,
                "last_exception": "registry call failed",
            }

    monkeypatch.setenv("OMEGA_LIVE_DISCOVERY_READY_TIMEOUT", "0.01")
    context = SimpleNamespace(engine=LoadingEngine(), waited_for_pool_data=False)

    assert module._wait_for_pool_data(context) is False
    output = capsys.readouterr().out
    assert "Live discovery timed out waiting for pool data" in output
    assert "discovered=4" in output
    assert "failed=curve" in output
    assert "last_exception=registry call failed" in output