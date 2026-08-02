import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from omega_v5.opportunity_ranker import _calculate_profitability
from omega_v5.flash_loan import FlashSource


class TestProfitabilityCalculation(unittest.TestCase):
    """Unit tests for the _calculate_profitability function."""

    @patch("omega_v5.opportunity_ranker.profitability_gas_price_gwei")
    @patch("omega_v5.opportunity_ranker.current_pol_price_usd")
    @patch("omega_v5.opportunity_ranker.live_relay_tip_usd")
    @patch("omega_v5.opportunity_ranker.live_risk_buffer_usd")
    @patch("omega_v5.opportunity_ranker._default_slippage_bps")
    @patch("omega_v5.opportunity_ranker.live_min_net_profit_usd")
    def test_profitable_balancer_route(
        self,
        mock_min_profit,
        mock_slippage,
        mock_risk_buffer,
        mock_relay_tip,
        mock_pol_price,
        mock_gas_price,
    ):
        """
        Tests a clearly profitable 2-hop route using a Balancer flash loan.
        - Balancer has a 0% flash loan fee.
        - All other costs are mocked to be predictable.
        """
        # --- Arrange: Mock all external dependencies ---
        mock_gas_price.return_value = (Decimal("100"), "mock")
        mock_pol_price.return_value = (Decimal("0.75"), "mock")
        mock_relay_tip.return_value = Decimal("0.01")
        mock_risk_buffer.return_value = Decimal("0.05")
        mock_slippage.return_value = Decimal("10")  # 0.10%
        mock_min_profit.return_value = Decimal("0.50")

        # --- Act: Call the function with test data ---
        result = _calculate_profitability(
            gross_out=Decimal("10100"),
            principal=Decimal("10000"),
            base_asset="USDC",
            hops=2,
            flash_source=FlashSource.BALANCER,
        )

        # --- Assert: Verify the calculations ---
        self.assertIsInstance(result, MagicMock) # Should be Profitability, but it's mocked
        
        # Expected gas cost: 500,000 units * 100 Gwei * 1e-9 * $0.75/POL = $37.50
        self.assertAlmostEqual(result.gas_cost_usd, Decimal("37.5"))

        # Expected flash fee: $10,000 * 0 / 10000 = $0
        self.assertEqual(result.flashloan.fee_usd, Decimal("0"))

        # Expected slippage cost: $10,100 * (10 / 10000) = $10.10
        slippage_cost = result.gross_amount_out - result.gross_amount_out_min
        self.assertAlmostEqual(slippage_cost, Decimal("10.1"))

        # Expected net profit:
        # raw_delta = 10100 - 10000 = 100
        # slippage_adjusted_delta = (10100 * 0.999) - 10000 = 89.9
        # net_profit = 89.9 - 0 (flash) - 37.5 (gas) - 0.01 (relay) - 0.05 (risk) = 52.34
        self.assertAlmostEqual(result.net_profit_usd, Decimal("52.34"))
        self.assertTrue(result.passes_gate)

    @patch("omega_v5.opportunity_ranker.profitability_gas_price_gwei")
    @patch("omega_v5.opportunity_ranker.current_pol_price_usd")
    @patch("omega_v5.opportunity_ranker.live_relay_tip_usd")
    @patch("omega_v5.opportunity_ranker.live_risk_buffer_usd")
    @patch("omega_v5.opportunity_ranker._default_slippage_bps")
    @patch("omega_v5.opportunity_ranker.live_min_net_profit_usd")
    def test_unprofitable_aave_route(
        self,
        mock_min_profit,
        mock_slippage,
        mock_risk_buffer,
        mock_relay_tip,
        mock_pol_price,
        mock_gas_price,
    ):
        """
        Tests a marginally profitable route that becomes unprofitable after
        accounting for Aave's 0.05% flash loan fee.
        """
        # --- Arrange: Mock all external dependencies ---
        mock_gas_price.return_value = (Decimal("100"), "mock")
        mock_pol_price.return_value = (Decimal("0.75"), "mock")
        mock_relay_tip.return_value = Decimal("0.01")
        mock_risk_buffer.return_value = Decimal("0.05")
        mock_slippage.return_value = Decimal("10")  # 0.10%
        mock_min_profit.return_value = Decimal("0.50")

        # --- Act: Call the function with test data ---
        result = _calculate_profitability(
            gross_out=Decimal("50050"),
            principal=Decimal("50000"),
            base_asset="USDC",
            hops=3,  # 3 hops = higher gas
            flash_source=FlashSource.AAVE_V3,
        )

        # --- Assert: Verify the calculations ---
        self.assertIsInstance(result, MagicMock)

        # Expected gas cost: 650,000 units * 100 Gwei * 1e-9 * $0.75/POL = $48.75
        self.assertAlmostEqual(result.gas_cost_usd, Decimal("48.75"))

        # Expected flash fee: $50,000 * 5 / 10000 = $25
        self.assertAlmostEqual(result.flashloan.fee_usd, Decimal("25"))

        # Expected slippage cost: $50,050 * (10 / 10000) = $50.05
        slippage_cost = result.gross_amount_out - result.gross_amount_out_min
        self.assertAlmostEqual(slippage_cost, Decimal("50.05"))

        # Expected net profit:
        # raw_delta = 50050 - 50000 = 50
        # slippage_adjusted_delta = (50050 * 0.999) - 50000 = -0.05
        # net_profit = -0.05 - 25 (flash) - 48.75 (gas) - 0.01 (relay) - 0.05 (risk) = -73.86
        self.assertAlmostEqual(result.net_profit_usd, Decimal("-73.86"))
        self.assertFalse(result.passes_gate)

    @patch("omega_v5.opportunity_ranker.profitability_gas_price_gwei")
    @patch("omega_v5.opportunity_ranker.current_pol_price_usd")
    @patch("omega_v5.opportunity_ranker.live_relay_tip_usd")
    @patch("omega_v5.opportunity_ranker.live_risk_buffer_usd")
    @patch("omega_v5.opportunity_ranker._default_slippage_bps")
    @patch("omega_v5.opportunity_ranker.live_min_net_profit_usd")
    def test_profitable_4_hop_route(
        self,
        mock_min_profit,
        mock_slippage,
        mock_risk_buffer,
        mock_relay_tip,
        mock_pol_price,
        mock_gas_price,
    ):
        """
        Tests a profitable 4-hop route to verify gas cost calculation for longer routes.
        """
        # --- Arrange: Mock all external dependencies ---
        mock_gas_price.return_value = (Decimal("120"), "mock")
        mock_pol_price.return_value = (Decimal("0.70"), "mock")
        mock_relay_tip.return_value = Decimal("0.02")
        mock_risk_buffer.return_value = Decimal("0.10")
        mock_slippage.return_value = Decimal("15")  # 0.15%
        mock_min_profit.return_value = Decimal("1.00")

        # --- Act: Call the function with test data ---
        result = _calculate_profitability(
            gross_out=Decimal("20200"),
            principal=Decimal("20000"),
            base_asset="USDC",
            hops=4,
            flash_source=FlashSource.BALANCER,
        )

        # --- Assert: Verify the calculations ---
        self.assertIsInstance(result, MagicMock)

        # Expected gas cost: 800,000 units * 120 Gwei * 1e-9 * $0.70/POL = $67.20
        self.assertAlmostEqual(result.gas_cost_usd, Decimal("67.2"))

        # Expected net profit:
        # raw_delta = 20200 - 20000 = 200
        # slippage_adjusted_delta = (20200 * 0.9985) - 20000 = 169.7
        # net_profit = 169.7 - 0 (flash) - 67.2 (gas) - 0.02 (relay) - 0.10 (risk) = 102.38
        self.assertAlmostEqual(result.net_profit_usd, Decimal("102.38"))
        self.assertTrue(result.passes_gate)


if __name__ == "__main__":
    unittest.main()