import unittest
from decimal import Decimal
from unittest.mock import patch

from omega_v5.capital_injector import (
    check_self_cannibalization,
    compute_derivative_optimal_size,
    compute_optimal_injection,
    register_execution_venue,
    CAPITAL_SOURCE_REGISTRY,
)
from omega_v5.flash_loan import FlashSource


class TestSelfCannibalization(unittest.TestCase):
    """Tests the self-cannibalization guard."""

    def test_direct_overlap_is_blocked(self):
        """A route containing the funding pool ID must be blocked."""
        funding_pool_id = CAPITAL_SOURCE_REGISTRY["BALANCER"]["pool_id"]
        is_cannibal, _ = check_self_cannibalization(
            "BALANCER", [funding_pool_id, "some_other_pool"]
        )
        self.assertTrue(is_cannibal, "Direct overlap should be detected as cannibalization.")

    def test_clean_route_is_allowed(self):
        """A route with no overlapping pools should pass."""
        is_cannibal, _ = check_self_cannibalization(
            "BALANCER", ["pool_A", "pool_B"]
        )
        self.assertFalse(is_cannibal, "A clean route should not be marked as cannibalization.")


class TestDerivativeSizing(unittest.TestCase):
    """Tests the exact derivative sizing formula."""

    def test_positive_spread_yields_positive_size(self):
        """With Rout > Rin and no fees, optimal size should be > 0."""
        optimal_size = compute_derivative_optimal_size(
            rin=Decimal("100000"),
            rout=Decimal("101000"),
            f_swap=Decimal("0"),
            f_flash=Decimal("0"),
        )
        self.assertGreater(optimal_size, 0)

    def test_no_spread_with_friction_yields_zero_size(self):
        """With equal reserves, any fee should make the trade unprofitable."""
        optimal_size = compute_derivative_optimal_size(
            rin=Decimal("100000"),
            rout=Decimal("100000"),
            f_swap=Decimal("0.003"),
            f_flash=Decimal("0"),
        )
        self.assertEqual(optimal_size, 0)


class TestFullInjector(unittest.TestCase):
    """Tests the end-to-end compute_optimal_injection function."""

    def setUp(self):
        """Set up mock pools for testing."""
        self.mock_pools = {
            "POOL_A": {
                "protocol": "UniswapV2",
                "tokens": ["USDC", "WETH"],
                "reserves": ["500000", "150"],
                "total_executable_liquidity_usd": "1000000",
            },
            "POOL_B": {
                "protocol": "UniswapV2",
                "tokens": ["WETH", "USDC"],
                "reserves": ["150", "505000"],
                "total_executable_liquidity_usd": "1010000",
            },
        }
        register_execution_venue("POOL_A", self.mock_pools["POOL_A"])
        register_execution_venue("POOL_B", self.mock_pools["POOL_B"])

    @patch("omega_v5.capital_injector.token_price_usd", return_value=Decimal("1.0"))
    def test_clean_route_sizing(self, mock_token_price):
        """Tests a standard, clean route through the injector."""
        result = compute_optimal_injection(
            pool_sequence=["POOL_A", "POOL_B"],
            pools=self.mock_pools,
            path=["USDC", "WETH", "USDC"],
            protocol_seq=["V2_CPMM", "V2_CPMM"],
            flash_source=FlashSource.BALANCER,
        )
        self.assertFalse(result.cannibalization_detected)
        self.assertGreater(result.optimal_injection_usd, 0)
        self.assertEqual(result.method, "derivative")

    @patch("omega_v5.capital_injector.token_price_usd", return_value=Decimal("1.0"))
    def test_cannibal_route_is_blocked(self, mock_token_price):
        """Ensures a self-cannibalizing route is blocked with a zero injection size."""
        funding_pool_id = CAPITAL_SOURCE_REGISTRY["AAVE_V3"]["pool_id"]
        self.mock_pools[funding_pool_id] = {"protocol": "AAVE_V3", "tokens": ["USDC"]}

        result = compute_optimal_injection(
            pool_sequence=[funding_pool_id, "POOL_A"],
            pools=self.mock_pools,
            path=["USDC", "WETH", "USDC"],
            protocol_seq=["AAVE_V3", "V2_CPMM"],
            flash_source=FlashSource.AAVE_V3,
        )
        self.assertTrue(result.cannibalization_detected)
        self.assertEqual(result.optimal_injection_usd, 0)
        self.assertEqual(result.method, "cannibal_block")


if __name__ == "__main__":
    unittest.main()