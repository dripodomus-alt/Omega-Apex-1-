import json

import scanner_core


def test_public_scanner_core_imports_and_runs():
    cfg = scanner_core.GateConfig(min_tvl_usd="100", chain_id=137)
    assert cfg.min_tvl_usd == "100"
    assert cfg.chain_id == 137

    pools = {
        "pool_a": {
            "protocol": "UniswapV2",
            "address": "0x1111111111111111111111111111111111111111",
            "tokens": ["USDC", "WETH"],
            "total_executable_liquidity_usd": "1000",
            "executable_price": "1000",
        },
        "pool_b": {
            "protocol": "UniswapV2",
            "address": "0x2222222222222222222222222222222222222222",
            "tokens": ["WETH", "USDC"],
            "total_executable_liquidity_usd": "1000",
            "executable_price": "1010",
        },
    }

    results = scanner_core.scan_opportunities(json.dumps(pools), cfg)
    assert len(results) == 1
    assert results[0].buy_pool_address == "0x1111111111111111111111111111111111111111"
