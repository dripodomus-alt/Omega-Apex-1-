import unittest
from decimal import Decimal
from unittest.mock import patch

import random
from omega_v5.route_execution_stager import build_stage_report
from omega_v5.ranker import compute_all_pool_rates

# Rust scanner integration for price-driven selection (single source of truth)
try:
    from scanner_core import GateConfig, scan_opportunities
    from omega_v5.rust_scanner import RustScanner
    RUST_SCANNER_AVAILABLE = True
except ImportError:
    RUST_SCANNER_AVAILABLE = False


def _v2_pool(tokens, reserves, address_tail):
    """Factory for creating synthetic Uniswap V2 style pools for testing."""
    return {
        "protocol": "UniswapV2",
        "tokens": list(tokens),
        "reserves": [Decimal(reserves[0]), Decimal(reserves[1])],
        "fee": Decimal("0.003"), "fee_bps": 30,
        "address": f"0x{'0'*39}{address_tail}",
        "total_executable_liquidity_usd": Decimal("10000000"),
    }


class TestStagingInvariants(unittest.TestCase):
    """
    Tests the core economic invariants enforced by the staging process.
    This suite verifies that the "buy low, sell high" logic is correctly
    applied and that invalid economic routes are rejected.
    Uses Rust scanner when available for price-driven leg selection.
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
            # Same executable price as BUY_LOW, so no buy-low/sell-high spread exists.
            "SELL_LOW": _v2_pool(("WETH", "USDC"), ("1000", "3000000"), 3),
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
        is rejected during staging.
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

    def test_liquidity_gate_sufficient_vs_insufficient(self):
        """
        Verifies that the liquidity gate correctly stages a route with
        sufficient liquidity and rejects one that is insufficient.
        """
        # Arrange: A profitable base route
        pools = {
            "BUY_OK": _v2_pool(("USDC", "WETH"), ("3000000", "1000"), 1),
            "SELL_OK": _v2_pool(("WETH", "USDC"), ("1000", "3010000"), 2),
        }
        principal = Decimal("10000")

        # --- Scenario 1: Insufficient Liquidity ---
        pools["SELL_OK"]["total_executable_liquidity_usd"] = principal - 1
        rates = compute_all_pool_rates(pools)
        report_insufficient = build_stage_report(
            pools=pools,
            rates=rates,
            principal_usd=principal,
            base_tokens=["USDC"],
            hops=(2,),
        )
        staged_insufficient = [r for r in report_insufficient["routes"] if r["status"] == "staged_for_executor_truth"]
        self.assertEqual(len(staged_insufficient), 0, "A route with insufficient liquidity must be rejected.")

        # --- Scenario 2: Sufficient Liquidity ---
        pools["SELL_OK"]["total_executable_liquidity_usd"] = principal + 1
        rates = compute_all_pool_rates(pools)
        report_sufficient = build_stage_report(
            pools=pools, rates=rates, principal_usd=principal, base_tokens=["USDC"], hops=(2,)
        )
        staged_sufficient = [r for r in report_sufficient["routes"] if r["status"] == "staged_for_executor_truth"]
        self.assertEqual(len(staged_sufficient), 1, "A route with just-enough liquidity should be staged.")

    def test_staging_at_scale(self):
        """
        Tests the Python stager with a large, programmatically generated set of
        pools to validate performance and logic at scale, ensuring it can find
        a profitable route within a noisy dataset.
        """
        # Arrange: Generate a large, complex pool set to stress the stager.
        num_tokens = 10
        num_pools_per_pair = 5
        tokens = [f"TOKEN_{i}" for i in range(num_tokens)]
        pools = {}
        pool_counter = 100  # Start address tails high to avoid collision

        for i in range(num_tokens):
            for j in range(i + 1, num_tokens):
                token_a, token_b = tokens[i], tokens[j]
                for k in range(num_pools_per_pair):
                    # Create random reserves to simulate market noise
                    reserves_a = 1_000_000 * (1 + (random.random() - 0.5) * 0.2)
                    reserves_b = 1_000_000 * (1 + (random.random() - 0.5) * 0.2)
                    pool_id = f"SCALE_POOL_{pool_counter}"
                    pools[pool_id] = _v2_pool((token_a, token_b), (str(reserves_a), str(reserves_b)), pool_counter)
                    pool_counter += 1

        # Inject a guaranteed profitable route (USDC -> WETH -> USDC)
        pools["GUARANTEED_BUY"] = _v2_pool(("USDC", "WETH"), ("3000000", "1000"), 998) # Price: 3000
        pools["GUARANTEED_SELL"] = _v2_pool(("WETH", "USDC"), ("1000", "3010000"), 999) # Price: 3010

        # Act: Run the full staging report against the large, noisy dataset.
        rates = compute_all_pool_rates(pools)
        report = build_stage_report(
            pools=pools,
            rates=rates,
            principal_usd=Decimal("10000"),
            base_tokens=["USDC"],
            hops=(2,),
            max_pre_ranked=500 # Use a high pre-rank limit to process the large set
        )

        # Assert: The stager should still find and stage the guaranteed profitable route.
        staged_routes = [r for r in report["routes"] if r["status"] == "staged_for_executor_truth"]
        self.assertGreater(len(staged_routes), 0, "Stager should find at least one profitable route.")

        guaranteed_route_staged = any(
            r["pool_sequence"] == ["GUARANTEED_BUY", "GUARANTEED_SELL"] for r in staged_routes
        )
        self.assertTrue(guaranteed_route_staged, "The guaranteed profitable route was not found or staged.")

if __name__ == "__main__":
    unittest.main()

