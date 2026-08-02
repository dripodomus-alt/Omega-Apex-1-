import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_benchmark", ROOT / "scripts" / "ops" / "run_benchmark.py")
run_benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(run_benchmark)


def test_format_top_route_summary_includes_profitability_and_status():
    routes = [
        {
            "opp_id": "opp-1",
            "status": "staged_for_executor_truth",
            "profitability": {"net_profit_usd": "12.34"},
            "path": ["USDC", "WETH", "USDC"],
        },
        {
            "opp_id": "opp-2",
            "status": "pending",
            "profitability": {"net_profit_usd": "3.21"},
            "path": ["USDC", "WBTC", "USDC"],
        },
    ]

    summary = run_benchmark.format_top_route_summary(routes, limit=1)

    assert len(summary) == 1
    assert summary[0]["opp_id"] == "opp-1"
    assert summary[0]["status"] == "staged_for_executor_truth"
    assert summary[0]["net_profit_usd"] == "12.34"
    assert summary[0]["path"] == ["USDC", "WETH", "USDC"]
