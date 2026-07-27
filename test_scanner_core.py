import unittest
import json

# This assumes the Rust code has been compiled into a loadable Python module,
# e.g., by running `maturin develop`.
try:
    from scanner_core import Candidate, GateConfig, find_best_quote, scan_opportunities
except ImportError:
    # Create dummy classes if the module isn't compiled, so the file can be
    # discovered by test runners without crashing. The tests will be skipped.
    print("WARNING: `scanner_core` rust module not found. Skipping Rust-specific tests.")
    Candidate = None
    find_best_quote = None
    GateConfig = None
    scan_opportunities = None


@unittest.skipIf(Candidate is None, "Rust module `scanner_core` not compiled.")
class TestScannerCore(unittest.TestCase):
    """
    Tests the core, price-driven selection logic of the Rust scanner engine.
    """

    def setUp(self):
        """Set up a list of candidates with varying prices."""
        self.candidates = []

        # Candidate 1: Mid-range buy, mid-range sell
        c1 = Candidate()
        c1.buy_pool_address = "0x0000000000000000000000000000000000000001"
        c1.executable_buy_price = "3000.0"
        c1.executable_sell_price = "3050.0"
        self.candidates.append(c1)

        # Candidate 2: Best buy price (lowest)
        c2 = Candidate()
        c2.buy_pool_address = "0x0000000000000000000000000000000000000002"
        c2.executable_buy_price = "2990.5"
        c2.executable_sell_price = "3040.0"
        self.candidates.append(c2)

        # Candidate 3: Best sell price (highest)
        c3 = Candidate()
        c3.buy_pool_address = "0x0000000000000000000000000000000000000003"
        c3.executable_buy_price = "3010.0"
        c3.executable_sell_price = "3065.5"
        self.candidates.append(c3)

    def test_find_best_quote_min_price(self):
        """
        Verify that `find_best_quote` with `find_min=True` returns the
        candidate with the lowest executable_buy_price.
        """
        best_buy_candidate = find_best_quote(self.candidates, find_min=True)
        self.assertIsNotNone(best_buy_candidate)
        # The best buy price is 2990.5 from the second candidate
        self.assertEqual(best_buy_candidate.executable_buy_price, "2990.5")
        self.assertEqual(best_buy_candidate.buy_pool_address, "0x0000000000000000000000000000000000000002")

    def test_find_best_quote_max_price(self):
        """
        Verify that `find_best_quote` with `find_min=False` returns the
        candidate with the highest executable_sell_price.
        """
        best_sell_candidate = find_best_quote(self.candidates, find_min=False)
        self.assertIsNotNone(best_sell_candidate)
        # The best sell price is 3065.5 from the third candidate
        self.assertEqual(best_sell_candidate.executable_sell_price, "3065.5")
        self.assertEqual(best_sell_candidate.buy_pool_address, "0x0000000000000000000000000000000000000003")

    def test_find_best_quote_empty_list(self):
        """
        Verify that `find_best_quote` returns None when given an empty list.
        """
        result = find_best_quote([], find_min=True)
        self.assertIsNone(result)

    def test_scan_opportunities_with_realistic_input(self):
        """
        Verify that `scan_opportunities` correctly processes a realistic
        JSON input with explicit prices and finds a valid arbitrage opportunity.
        """
        # Arrange: Create a gate configuration that the candidate will pass.
        gate_config = GateConfig(min_tvl_usd="50000.0")

        # Define token addresses for a realistic test case (USDC and WETH on Polygon)
        usdc_addr = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
        weth_addr = "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"

        # Create a realistic JSON input with three pools.
        # The Rust engine should pick the best buy (Pool A) and best sell (Pool C).
        pools_data = {
            "POOL_A_BUY_CHEAP": {
                "protocol": "UniswapV3",
                "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "tokens": [usdc_addr, weth_addr],
                "total_executable_liquidity_usd": "1000000.0",
                "executable_price": "3000.0" # Buy WETH for 3000 USDC
            },
            "POOL_B_BUY_EXPENSIVE": {
                "protocol": "QuickSwapV3",
                "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "tokens": [usdc_addr, weth_addr],
                "total_executable_liquidity_usd": "1000000.0",
                "executable_price": "3000.5" # Worse buy price
            },
            "POOL_C_SELL_HIGH": {
                "protocol": "Algebra",
                "address": "0xcccccccccccccccccccccccccccccccccccccccc",
                "tokens": [weth_addr, usdc_addr],
                "total_executable_liquidity_usd": "2000000.0",
                "executable_price": "3001.0" # Sell WETH for 3001 USDC
            }
        }
        pools_json = json.dumps(pools_data)

        # Act: Call the main scanner function.
        valid_candidates = scan_opportunities(pools_json, gate_config)

        # Assert: The logic should find exactly one profitable 2-hop route.
        self.assertEqual(len(valid_candidates), 1)

        # Verify the properties of the returned candidate.
        candidate = valid_candidates[0]
        self.assertEqual(candidate.token_in_address.lower(), usdc_addr)
        self.assertEqual(candidate.token_mid_address.lower(), weth_addr)

        # It should choose the cheapest buy pool and the most expensive sell pool.
        self.assertEqual(candidate.buy_pool_address.lower(), pools_data["POOL_A_BUY_CHEAP"]["address"])
        self.assertEqual(candidate.sell_pool_address.lower(), pools_data["POOL_C_SELL_HIGH"]["address"])

        self.assertEqual(candidate.buy_pool_protocol, "UniswapV3")
        self.assertEqual(candidate.sell_pool_protocol, "Algebra")

        # The prices should match the best options provided in the JSON.
        self.assertEqual(candidate.executable_buy_price, "3000.0")
        self.assertEqual(candidate.executable_sell_price, "3001.0")