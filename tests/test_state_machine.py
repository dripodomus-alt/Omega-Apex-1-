#!/usr/bin/env python3
# ==============================================================================
# test_state_machine.py -- Unit tests for the C1/C2 state machine.
# ==============================================================================

import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from omega_v5.state_machine import create_c1_cycle, C1Status
from omega_v5.cycle_logger import cycle_logger, CycleEventType
from omega_v5.opportunity_ranker import LiveOpportunity
from omega_v5.flash_loan import FlashLoanParams, Profitability


class TestStateMachineValidation(unittest.TestCase):
    """
    Tests that the state machine correctly uses the integrated validation gates.
    """

    def setUp(self):
        """Clear the in-memory logger before each test."""
        cycle_logger.clear_memory()

    def test_create_c1_cycle_rejects_invalid_sequence(self):
        """
        Verify that create_c1_cycle rejects an opportunity that fails the
        buy-low-sell-high economic invariant and logs the failure.
        """
        # --- Arrange: Create an invalid opportunity ---
        # The 'sell_price_usd' is lower than the 'buy_price_usd', which should be caught.
        invalid_route = {
            "opp_id": "invalid-seq-opp-1",
            "protocol_seq": ["V2_CPMM", "V3_CLMM"],
            "path": ["USDC", "WETH", "USDC"],
            "pool_sequence": ["pool_A", "pool_B"],
            "pricing_steps": [{"BUY_LEG1_PRICE": "3001.0"}, {"SELL_LEG2_PRICE": "3000.0"}],
        }
        mock_opportunity = LiveOpportunity(
            **invalid_route,
            profitability=Profitability(
                gross_amount_out=Decimal("0"), gross_amount_out_min=Decimal("0"),
                flashloan=FlashLoanParams(source="BALANCER", asset="USDC", principal_usd=Decimal("10000"), fee_bps=Decimal("0"), fee_usd=Decimal("0"), repayment_usd=Decimal("10000")),
                gas_cost_usd=Decimal("0"), relay_tip_usd=Decimal("0"), risk_buffer_usd=Decimal("0"),
                net_profit_usd=Decimal("-1"), profit_to_gas=Decimal("-1"), passes_gate=False
            )
        )

        # --- Act: Create the C1 cycle ---
        c1_cycle = create_c1_cycle(mock_opportunity, pools={})

        # --- Assert: Check that the cycle was immediately failed ---
        self.assertEqual(c1_cycle.status, C1Status.FAILED)
        self.assertTrue(c1_cycle.log_opportunity_id)

        # Verify that a VALIDATION_FAILED event was logged
        events = cycle_logger.recent_events(opportunity_id=c1_cycle.log_opportunity_id)
        self.assertTrue(any(e["event_type"] == CycleEventType.VALIDATION_FAILED.value for e in events))
        self.assertTrue(any("Economic invariant" in e["message"] for e in events if e["event_type"] == "VALIDATION_FAILED"))

if __name__ == "__main__":
    unittest.main()

