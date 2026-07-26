import unittest
from decimal import Decimal

from omega_v5.pricing.net_delta import raw_execution_gate_passes


class TestRawExecutionGate(unittest.TestCase):
    """Unit tests for the raw_execution_gate_passes function."""

    def test_legacy_mode_pass(self):
        """Tests that the legacy positional mode passes when net surplus > min profit."""
        # net_surplus_raw (100) > min_profit_raw (50)
        self.assertTrue(raw_execution_gate_passes(100, 50))

    def test_legacy_mode_fail(self):
        """Tests that the legacy positional mode fails when net surplus <= min profit."""
        # net_surplus_raw (50) == min_profit_raw (50) -> fails because it must be strictly greater
        self.assertFalse(raw_execution_gate_passes(50, 50))
        # net_surplus_raw (49) < min_profit_raw (50)
        self.assertFalse(raw_execution_gate_passes(49, 50))

    def test_keyword_mode_pass(self):
        """Tests that the keyword-based mode passes when sell_amount_out > total costs."""
        # sell_amount_out (10100) > threshold (10000 + 5 + 50 + 1 + 2 + 10 = 10068)
        self.assertTrue(
            raw_execution_gate_passes(
                sell_amount_out_raw=10100,
                flash_principal_raw=10000,
                flash_fee_raw=5,
                gas_cost_raw=50,
                relay_cost_raw=1,
                risk_buffer_raw=2,
                minimum_profit_raw=10,
            )
        )

    def test_keyword_mode_fail_exact(self):
        """Tests that the keyword-based mode fails when sell_amount_out is exactly the threshold."""
        # sell_amount_out (10068) == threshold (10068) -> fails because it must be strictly greater
        self.assertFalse(
            raw_execution_gate_passes(
                sell_amount_out_raw=10068,
                flash_principal_raw=10000,
                flash_fee_raw=5,
                gas_cost_raw=50,
                relay_cost_raw=1,
                risk_buffer_raw=2,
                minimum_profit_raw=10,
            )
        )

    def test_keyword_mode_fail_below(self):
        """Tests that the keyword-based mode fails when sell_amount_out is below the threshold."""
        # sell_amount_out (10067) < threshold (10068)
        self.assertFalse(
            raw_execution_gate_passes(
                sell_amount_out_raw=10067,
                flash_principal_raw=10000,
                flash_fee_raw=5,
                gas_cost_raw=50,
                relay_cost_raw=1,
                risk_buffer_raw=2,
                minimum_profit_raw=10,
            )
        )

if __name__ == "__main__":
    unittest.main()