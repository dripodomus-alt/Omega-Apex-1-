import unittest
from decimal import Decimal
import json

try:
    from scanner_core import GateConfig, Candidate, find_best_quote, scan_opportunities
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

@unittest.skipUnless(RUST_AVAILABLE, "Rust scanner_core extension not built (run maturin develop)")
class TestRustScannerCore(unittest.TestCase):
    def setUp(self):
        self.config = GateConfig(min_tvl_usd="50000", chain_id=137)

    def test_gate_config(self):
        cfg = GateConfig(min_tvl_usd="100000", chain_id=137)
        self.assertEqual(cfg.min_tvl_usd, "100000")
        self.assertEqual(cfg.chain_id, 137)

    def test_candidate_validate_profitable(self):
        cand = Candidate()
        cand.buy_pool_address = "0x1111111111111111111111111111111111111111"
        cand.sell_pool_address = "0x2222222222222222222222222222222222222222"
        cand.token_in = "USDC"
        cand.token_mid = "WETH"
        cand.buy_pool_tvl_usd = "100000"
        cand.executable_buy_price = "3000"
        cand.executable_sell_price = "3010"
        cand.buy_pool_protocol = "UniswapV2"
        cand.sell_pool_protocol = "UniswapV2"
        self.assertIsNone(cand.validate(self.config))

    def test_candidate_validate_unprofitable(self):
        cand = Candidate()
        cand.buy_pool_address = "0x1111111111111111111111111111111111111111"
        cand.sell_pool_address = "0x2222222222222222222222222222222222222222"
        cand.buy_pool_tvl_usd = "100000"
        cand.executable_buy_price = "3010"
        cand.executable_sell_price = "3000"
        with self.assertRaises(Exception):
            cand.validate(self.config)

    def test_candidate_validate_low_tvl(self):
        cand = Candidate()
        cand.buy_pool_address = "0x1111111111111111111111111111111111111111"
        cand.sell_pool_address = "0x2222222222222222222222222222222222222222"
        cand.buy_pool_tvl_usd = "10000"
        cand.executable_buy_price = "3000"
        cand.executable_sell_price = "3010"
        with self.assertRaises(Exception):
            cand.validate(self.config)

    def test_candidate_validate_same_pool(self):
        cand = Candidate()
        cand.buy_pool_address = "0x1111111111111111111111111111111111111111"
        cand.sell_pool_address = "0x1111111111111111111111111111111111111111"
        cand.buy_pool_tvl_usd = "100000"
        cand.executable_buy_price = "3000"
        cand.executable_sell_price = "3010"
        with self.assertRaises(Exception):
            cand.validate(self.config)

    def test_find_best_quote_min(self):
        c1 = Candidate()
        c1.executable_buy_price = "3000"
        c2 = Candidate()
        c2.executable_buy_price = "2990"
        best = find_best_quote([c1, c2], find_min=True)
        self.assertIsNotNone(best)
        self.assertEqual(best.executable_buy_price, "2990")

    def test_find_best_quote_max(self):
        c1 = Candidate()
        c1.executable_sell_price = "3010"
        c2 = Candidate()
        c2.executable_sell_price = "3020"
        best = find_best_quote([c1, c2], find_min=False)
        self.assertIsNotNone(best)
        self.assertEqual(best.executable_sell_price, "3020")

    def test_scan_opportunities_profitable(self):
        pools = {
            "pool1": {
                "protocol": "UniswapV2",
                "address": "0x1111111111111111111111111111111111111111",
                "tokens": ["USDC", "WETH"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3000"
            },
            "pool2": {
                "protocol": "UniswapV2",
                "address": "0x2222222222222222222222222222222222222222",
                "tokens": ["WETH", "USDC"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3010"
            }
        }
        pools_json = json.dumps(pools)
        results = scan_opportunities(pools_json, self.config)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].executable_buy_price, "3000")
        self.assertEqual(results[0].executable_sell_price, "3010")

    def test_scan_opportunities_unprofitable_rejected(self):
        pools = {
            "pool1": {
                "protocol": "UniswapV2",
                "address": "0x1111111111111111111111111111111111111111",
                "tokens": ["USDC", "WETH"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3010"
            },
            "pool2": {
                "protocol": "UniswapV2",
                "address": "0x2222222222222222222222222222222222222222",
                "tokens": ["WETH", "USDC"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3000"
            }
        }
        pools_json = json.dumps(pools)
        results = scan_opportunities(pools_json, self.config)
        self.assertEqual(len(results), 0)

    def test_scan_opportunities_tvl_gate(self):
        pools = {
            "pool1": {
                "protocol": "UniswapV2",
                "address": "0x1111111111111111111111111111111111111111",
                "tokens": ["USDC", "WETH"],
                "total_executable_liquidity_usd": "10000",
                "executable_price": "3000"
            },
            "pool2": {
                "protocol": "UniswapV2",
                "address": "0x2222222222222222222222222222222222222222",
                "tokens": ["WETH", "USDC"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3010"
            }
        }
        pools_json = json.dumps(pools)
        results = scan_opportunities(pools_json, self.config)
        self.assertEqual(len(results), 0)

    def test_scan_opportunities_different_protocols(self):
        pools = {
            "pool1": {
                "protocol": "UniswapV3",
                "address": "0x1111111111111111111111111111111111111111",
                "tokens": ["USDC", "WETH"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3000"
            },
            "pool2": {
                "protocol": "Algebra",
                "address": "0x2222222222222222222222222222222222222222",
                "tokens": ["WETH", "USDC"],
                "total_executable_liquidity_usd": "100000",
                "executable_price": "3010"
            }
        }
        pools_json = json.dumps(pools)
        results = scan_opportunities(pools_json, self.config)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].buy_pool_protocol, "UniswapV3")
        self.assertEqual(results[0].sell_pool_protocol, "Algebra")

if __name__ == "__main__":
    unittest.main()
