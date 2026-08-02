import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from execution_governance import get_minimum_net_profit_usd, GovernanceService
from strategy_manager import StrategyConfig


def test_minimum_profit_policy_locked_to_five_usd():
    assert get_minimum_net_profit_usd() == 5.0


def test_activation_pipeline_rejects_below_threshold_and_accepts_above():
    svc = GovernanceService()
    rejected = svc.evaluate_activation(
        opportunity_id="opp-low",
        stage="unit",
        net_profit_after_costs_usd=4.99,
    )
    accepted = svc.evaluate_activation(
        opportunity_id="opp-high",
        stage="unit",
        net_profit_after_costs_usd=5.01,
    )
    assert rejected.accepted is False
    assert accepted.accepted is True
    metrics = svc.get_metrics()
    assert metrics["system"]["decisions_total"] >= 2
    assert metrics["system"]["rejected"] >= 1
    assert metrics["system"]["accepted"] >= 1


def test_audit_runner_and_latency_probe_test_job():
    svc = GovernanceService()
    start = svc.start_audit_run(mode="dry_run", profile={"interval_sec": 1})
    assert start["status"] in {"started", "already_running"}
    # latency_probe executes quickly and updates latency samples
    job = svc.start_test_job(kind="latency_probe")
    assert job["status"] in {"started", "already_running"}
    time.sleep(1.0)
    svc.stop_test_job()
    stop = svc.stop_audit_run()
    assert stop["status"] in {"stopped", "not_running"}
    metrics = svc.get_metrics()
    assert metrics["latency"]["samples"] >= 1


def test_strategy_config_enforces_governance_floor():
    cfg = StrategyConfig(min_profit_usd=1.0)
    assert cfg.min_profit_usd == get_minimum_net_profit_usd()
