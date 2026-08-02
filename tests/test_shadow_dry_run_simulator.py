import importlib.util
import os
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
    module.LIVE_MODE = False
    report = module.run_dry_cycles(num_cycles=3, use_live=False, emit_report=False)

    assert report["summary"]["cycles"] == 3
    assert report["summary"]["discovered_total"] >= report["summary"]["shadow_executed_total"]
    assert "execution_rate" in report["summary"]
    assert "discovery_rate" in report["summary"]
    assert "ranked_total" in report["summary"]
    assert "data_source" in report["summary"]
    assert report["summary"]["data_source"] == "live_proof"
    assert report["summary"]["accepted_total"] <= report["summary"]["shadow_executed_total"]
    assert "ranked" in report["cycles"][0]


def test_shadow_dry_run_summary_exposes_pipeline_mode_and_live_discovery_count():
    module = load_module()
    module.LIVE_MODE = False
    report = module.run_dry_cycles(num_cycles=1, use_live=False, emit_report=False)

    assert report["summary"]["pipeline_mode"] == "dry_run"
    assert "live_discovery_count" in report["summary"]
    assert report["summary"]["live_discovery_count"] >= 0
    assert report["summary"]["tx_broadcasting"] is False


def test_live_mode_falls_back_to_synthetic_report_when_discovery_is_empty(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_discover_live_opportunities", lambda: [])

    report = module.run_dry_cycles(num_cycles=1, use_live=True, emit_report=False)

    assert report["summary"]["discovered_total"] == 0
    assert report["summary"]["shadow_executed_total"] == 0
    assert report["summary"]["data_source"] == "live_proof"
    assert report["cycles"][0]["data_source"] == "live_proof"


def test_runtime_reads_polygon_rpc_from_env_file_when_available():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    assert env_path.exists(), "Expected repository .env file to exist"

    env_text = env_path.read_text(encoding="utf-8")
    assert "POLYGON_RPC_URL=" in env_text
    assert "OMEGA_LIVE_TEST=" in env_text or "LIVE_TRADING=0" in env_text
    assert "POLYGON_RPC_URL=https://polygon-bor-rpc.publicnode.com" in env_text


def test_rotation_endpoints_are_discovered_from_env(monkeypatch):
    module = load_module()
    monkeypatch.setenv("RPC_ROTATION_HTTP_URLS", "https://one.example,https://two.example")

    assert module._iter_rpc_urls() == ["https://one.example", "https://two.example"]


def test_live_cycles_report_live_proof_per_cycle(monkeypatch):
    module = load_module()

    monkeypatch.setattr(module, "_discover_live_opportunities", lambda: [])
    report = module.run_dry_cycles(num_cycles=3, use_live=True, emit_report=False)

    assert report["summary"]["data_source"] == "live_proof"
    assert report["summary"]["pipeline_mode"] == "dry_run"
    assert all(cycle["data_source"] == "live_proof" for cycle in report["cycles"])


def test_live_mode_opens_discovery_and_execution_gates(monkeypatch):
    module = load_module()

    monkeypatch.setenv("OMEGA_ENGINE_NO_SCAN", "true")
    monkeypatch.delenv("ENGINE_STRATEGY", raising=False)
    monkeypatch.setattr(module, "_discover_live_opportunities", lambda: [])

    module.run_dry_cycles(num_cycles=1, use_live=True, emit_report=False)

    assert os.environ["OMEGA_ENGINE_NO_SCAN"] == "false"
    assert os.environ["EXECUTION_MODE"] == "dry_run"
    assert os.environ["LIVE_TRADING"] == "0"


def test_no_synthetic_pipeline_path_used_in_non_live_mode(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_discover_live_opportunities", lambda: [])

    report = module.run_dry_cycles(num_cycles=1, use_live=False, emit_report=False)

    assert report["summary"]["data_source"] == "live_proof"
    assert report["summary"]["discovered_total"] == 0
    assert report["summary"]["shadow_executed_total"] == 0
    assert report["summary"]["tx_broadcasting"] is False


def test_live_opportunity_builder_injects_real_market_snapshot_from_pool_state():
    module = load_module()

    class DummyPool:
        def __init__(self):
            self.address = "0xabc"
            self.reserve_usd = 50000
            self.reserve0 = 1000
            self.reserve1 = 2000
            self.token0 = "USDC"
            self.token1 = "WETH"
            self.price = 2000
            self.protocol = "UniswapV3"

    class DummyOpportunity:
        def __init__(self):
            self.path = ("USDC", "WETH")
            self.pool_sequence = ("pool-1",)
            self.protocol_seq = ("uniswap",)
            self.profitability = SimpleNamespace(net_profit_usd=25.0)
            self.metadata = {}
            self.buy_pool = DummyPool()
            self.sell_pool = DummyPool()

    opportunity = module._build_live_opportunity(1, 0, DummyOpportunity())

    assert opportunity.market_snapshot is not None
    assert opportunity.market_snapshot["source"] == "live_discovery"
    assert opportunity.market_snapshot["pool_states"][0]["address"] == "0xabc"
    assert opportunity.market_snapshot["pool_states"][0]["reserve_usd"] == 50000


def test_live_opportunity_payload_includes_market_snapshot():
    module = load_module()
    opportunity = module.LiveOpportunity(
        path=("USDC", "WETH"),
        pool_sequence=("pool-1",),
        protocol_seq=("uniswap",),
        profitability=SimpleNamespace(net_profit_usd=25.0),
        metadata={},
    )
    opportunity.market_snapshot = {
        "source": "live_discovery",
        "pool_states": [{"address": "0xabc", "reserve_usd": 50000}],
    }

    payload = opportunity.to_payload()

    assert payload["path"] == ["USDC", "WETH"]
    assert payload["market_snapshot"]["source"] == "live_discovery"
    assert payload["market_snapshot"]["pool_states"][0]["address"] == "0xabc"
