import sys
from types import SimpleNamespace

from omega_v5 import main as main_module


def test_main_routes_discovered_opportunities_to_execution_loop(monkeypatch, capsys):
    captured = {}

    def fake_discovery(**kwargs):
        return [
            SimpleNamespace(
                path=("USDC", "WETH", "USDC"),
                pool_sequence=("p1", "p2"),
                protocol_seq=("UniswapV2", "UniswapV2"),
            )
        ]

    async def fake_execution_loop(opportunities=None, pools=None, nonce=0):
        captured["opportunities"] = opportunities
        captured["nonce"] = nonce
        return [SimpleNamespace(success=True, detail="simulated")]

    monkeypatch.setattr(main_module, "run_arbitrage_discovery", fake_discovery)
    monkeypatch.setattr(main_module, "run_execution_loop", fake_execution_loop, raising=False)
    monkeypatch.setattr(sys, "argv", ["omega_v5.main", "--dry-run", "--cycles", "1"])

    main_module.main()

    out = capsys.readouterr().out
    assert captured["opportunities"] is not None
    assert captured["nonce"] == 1
    assert "discovered 1 opportunities" in out


def test_main_stages_discovery_result_before_execution_loop(monkeypatch, capsys):
    captured = {}

    def fake_discovery(**kwargs):
        return [
            SimpleNamespace(
                opp_id="OPP-TEST-001",
                path=("USDC", "WETH", "USDC"),
                pool_sequence=("p1", "p2"),
                protocol_seq=("UniswapV2", "UniswapV2"),
                profitability=SimpleNamespace(
                    gross_surplus_usd=120.0,
                    flashloan_fee_usd=5.0,
                    gas_cost_usd=2.0,
                    relay_tip_usd=1.0,
                    risk_buffer_usd=0.5,
                    net_profit_usd=111.5,
                ),
            )
        ]

    async def fake_execution_loop(opportunities=None, pools=None, nonce=0):
        captured["opportunities"] = opportunities
        captured["nonce"] = nonce
        return [SimpleNamespace(success=True, detail="simulated")]

    monkeypatch.setattr(main_module, "run_arbitrage_discovery", fake_discovery)
    monkeypatch.setattr(main_module, "run_execution_loop", fake_execution_loop, raising=False)
    monkeypatch.setattr(sys, "argv", ["omega_v5.main", "--dry-run", "--cycles", "1"])

    main_module.main()

    staged_payload = captured["opportunities"][0]
    assert isinstance(staged_payload, dict)
    assert staged_payload["opp_id"] == "OPP-TEST-001"
    assert staged_payload["path"] == ["USDC", "WETH", "USDC"]
    assert staged_payload["pool_sequence"] == ["p1", "p2"]
    assert staged_payload["principal_usd"] == "1000"
    assert staged_payload["profitability"]["net_profit_usd"] == 111.5
    assert staged_payload["unified_route_envelope"]["staging"]["principal_usd"] == "1000"
