import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from omega_v5.opportunity_ranker import find_opportunities


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

    @patch("omega_v5.opportunity_ranker.os.environ.get", return_value="unrecognized_mode_value")
    @patch("omega_v5.opportunity_ranker.find_opportunities_with_rust")
    @patch("omega_v5.opportunity_ranker.logger.warning")
    def test_returns_empty_for_unrecognized_mode(
        self, mock_logger, mock_rust_scanner, mock_env_get
    ):
        """
        Verify that if SCANNER_MODE is set to an unknown value, a warning is
        logged and an empty list is returned.
        """
        # Act
        result = find_opportunities({}, Decimal("10000"), Decimal("10"))

        # Assert
        mock_rust_scanner.assert_not_called()
        mock_logger.assert_called_once()
        self.assertIn("Unrecognized SCANNER_MODE", mock_logger.call_args[0][0])
        self.assertEqual(result, [])
