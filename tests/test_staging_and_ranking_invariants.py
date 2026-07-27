import unittest
from decimal import Decimal
from unittest.mock import patch

from omega_v5.route_execution_stager import build_stage_report
from omega_v5.ranker import compute_all_pool_rates


def _v2_pool(tokens, reserves, address_tail):
    """Factory for creating synthetic Uniswap V2 style pools for testing."""
    return {
        "protocol": "UniswapV2",
        "tokens": list(tokens),
        "reserves": [Decimal(reserves[0]), Decimal(reserves[1])],
        "fee": Decimal("0.003"),
        "address": f"0x{'0'*39}{address_tail}",
        "total_executable_liquidity_usd": Decimal("10000000"),
    }


class TestStagingInvariants(unittest.TestCase):
    """
    Tests the core economic invariants enforced by the staging process.
    This suite verifies that the "buy low, sell high" logic is correctly
    applied and that invalid economic routes are rejected.
    """

    def setUp(self):
        """Set up a controlled set of pools for testing."""
        self.profitable_pools = {
            # Buy WETH for 3000 USDC
            "BUY_LOW": _v2_pool(("USDC", "WETH"), ("3000000", "1000"), 1),
            # Sell WETH for 3010 USDC
            "SELL_HIGH": _v2_pool(("WETH", "USDC"), ("1000", "3010000"), 2),
        }
        self.unprofitable_pools = {
            # Buy WETH for 3000 USDC
            "BUY_LOW": _v2_pool(("USDC", "WETH"), ("3000000", "1000"), 1),
            # Sell WETH for only 2990 USDC (a loss)
            "SELL_LOW": _v2_pool(("WETH", "USDC"), ("1000", "2990000"), 3),
        }

    def test_profitable_route_is_staged(self):
        """
        Ensures a route that respects the 'buy low, sell high' invariant
        is successfully staged for execution.
        """
        rates = compute_all_pool_rates(self.profitable_pools)
        report = build_stage_report(
            pools=self.profitable_pools,
            rates=rates,
            principal_usd=Decimal("10000"),
            base_tokens=["USDC"],
            hops=(2,),
        )
        staged_routes = [r for r in report["routes"] if r["status"] == "staged_for_executor_truth"]
        self.assertEqual(len(staged_routes), 1, "A profitable route should be staged.")
        self.assertEqual(staged_routes[0]["pool_sequence"], ["BUY_LOW", "SELL_HIGH"])

    def test_unprofitable_route_is_rejected(self):
        """
        Ensures a route that violates the 'buy low, sell high' invariant
        is rejected by the stager and not passed to the executor.
        """
        rates = compute_all_pool_rates(self.unprofitable_pools)
        report = build_stage_report(
            pools=self.unprofitable_pools,
            rates=rates,
            principal_usd=Decimal("10000"),
            base_tokens=["USDC"],
            hops=(2,),
        )
        staged_routes = [r for r in report["routes"] if r["status"] == "staged_for_executor_truth"]
        self.assertEqual(len(staged_routes), 0, "An unprofitable route should be rejected by the stager.")


if __name__ == "__main__":
    unittest.main()