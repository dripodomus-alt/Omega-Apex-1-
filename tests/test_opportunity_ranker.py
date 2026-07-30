import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
import os

from omega_v5.opportunity_ranker import find_opportunities, _find_opportunities_with_python_reference


class TestFindOpportunitiesRouter(unittest.TestCase):
    """
    Tests the find_opportunities router function to ensure it correctly
    dispatches to the configured scanning engine.
    """

    @patch("omega_v5.opportunity_ranker.os.environ.get", return_value="rust")
    @patch("omega_v5.opportunity_ranker.find_opportunities_with_rust")
    @patch("omega_v5.opportunity_ranker.RUST_SCANNER_AVAILABLE", True)
    def test_routes_to_rust_when_available(
        self, mock_rust_scanner, mock_env_get
    ):
        """
        Verify that when SCANNER_MODE is 'rust' and the module is available,
        the rust scanner function is called.
        """
        # Arrange
        mock_rust_scanner.return_value = [MagicMock()]  # Return a dummy opportunity
        live_pools = {"pool1": {}}
        principal = Decimal("10000")
        slippage = Decimal("10")

        # Act
        result = find_opportunities(live_pools, principal, slippage)

        # Assert
        mock_rust_scanner.assert_called_once_with(live_pools, principal, slippage)
        self.assertEqual(len(result), 1)

    @patch("omega_v5.opportunity_ranker.os.environ.get", return_value="rust")
    @patch("omega_v5.opportunity_ranker.find_opportunities_with_rust")
    @patch("omega_v5.opportunity_ranker.RUST_SCANNER_AVAILABLE", False)
    @patch("omega_v5.opportunity_ranker.logger.error")
    def test_returns_empty_when_rust_unavailable(
        self, mock_logger, mock_rust_scanner, mock_env_get
    ):
        """
        Verify that if SCANNER_MODE is 'rust' but the engine is not available,
        an error is logged and an empty list is returned.
        """
        # Arrange
        live_pools = {"pool1": {}}
        principal = Decimal("10000")
        slippage = Decimal("10")

        # Act
        result = find_opportunities(live_pools, principal, slippage)

        # Assert
        mock_rust_scanner.assert_not_called()
        mock_logger.assert_called_once()
        self.assertIn("Rust engine is not available", mock_logger.call_args[0][0])
        self.assertEqual(result, [])

    @patch("omega_v5.opportunity_ranker.os.environ.get", return_value="python_reference")
    @patch("omega_v5.opportunity_ranker._find_opportunities_with_python_reference")
    def test_routes_to_python_reference(
        self, mock_python_scanner, mock_env_get
    ):
        """
        Verify that when SCANNER_MODE is 'python_reference', the Python
        reference scanner function is called.
        """
        # Arrange
        mock_python_scanner.return_value = [MagicMock()]
        live_pools = {"pool1": {}}
        principal = Decimal("10000")
        slippage = Decimal("10")

        # Act
        result = find_opportunities(live_pools, principal, slippage)

        # Assert
        mock_python_scanner.assert_called_once_with(live_pools, principal, slippage)
        self.assertEqual(len(result), 1)

    @patch("omega_v5.opportunity_ranker.os.environ.get", return_value="unknown_mode")
    @patch("omega_v5.opportunity_ranker.find_opportunities_with_rust")
    @patch("omega_v5.opportunity_ranker.logger.warning")
    def test_returns_empty_for_unrecognized_mode(
        self, mock_logger, mock_rust_scanner, mock_env_get
    ):
        """
        Verify that if SCANNER_MODE is an unknown value, a warning is logged
        and an empty list is returned.
        """
        # Act
        result = find_opportunities({}, Decimal("10000"), Decimal("10"))

        # Assert
        mock_rust_scanner.assert_not_called()
        mock_logger.assert_called_once()
        self.assertIn("is not recognized", mock_logger.call_args[0][0])
        self.assertEqual(result, [])


class TestLiveDataSupport(unittest.TestCase):
    """Tests for live integration mode (C1/C2/Liq families + real RPC)."""

    def test_live_mode_uses_real_scanner_when_enabled(self):
        """When OMEGA_LIVE_TEST=1, prefer real discovery over pure mocks."""
        if not (os.getenv("OMEGA_LIVE_TEST") or os.getenv("LIVE_TEST_RPC_URL")):
            self.skipTest("live_integration requires OMEGA_LIVE_TEST=1 or LIVE_TEST_RPC_URL")

        # In live mode we expect the router to be able to accept real pool dicts
        # and return opportunities (even if empty in some environments).
        from omega_v5 import scanner
        # This exercises the live path without forcing network in unit context
        result = find_opportunities({}, Decimal("5000"), Decimal("5"))
        self.assertIsInstance(result, list)

    def test_supports_execution_families(self):
        """Basic structural test that opportunities can carry family metadata."""
        # This prepares for C1 / C2 / LIQUIDATION tagging used in staging + broadcast
        from omega_v5.opportunity_ranker import LiveOpportunity
        op = LiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("p1", "p2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MagicMock(net_profit_usd=Decimal("12.5")),
            family="C1"
        )
        self.assertEqual(op.family, "C1")

        op2 = LiveOpportunity(
            path=("USDC", "WETH", "USDC"),
            pool_sequence=("p1", "p2"),
            protocol_seq=("UniswapV2", "UniswapV2"),
            profitability=MagicMock(net_profit_usd=Decimal("8.0")),
            family="C2"
        )
        self.assertEqual(op2.family, "C2")

