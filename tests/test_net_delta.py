import unittest
from decimal import Decimal
import pytest
from omega_v5.pricing.net_delta import raw_execution_gate_passes, route_within_lifespan


def _transparent_dry_run(
    test_name: str,
    sell_amount_out_raw: int,
    flash_principal_raw: int,
    flash_fee_raw: int,
    gas_cost_raw: int,
    relay_cost_raw: int,
    risk_buffer_raw: int,
    minimum_profit_raw: int,
) -> bool:
    """Prints fully transparent dry-run calculation for the raw gate."""
    total_costs_raw = flash_fee_raw + gas_cost_raw + relay_cost_raw + risk_buffer_raw
    threshold = flash_principal_raw + total_costs_raw + minimum_profit_raw
    surplus = sell_amount_out_raw - threshold
    passes = sell_amount_out_raw > threshold

    print(f"\n=== DRY RUN: {test_name} ===")
    print(f"  sell_amount_out_raw     = {sell_amount_out_raw}")
    print(f"  flash_principal_raw     = {flash_principal_raw}")
    print(f"  flash_fee_raw           = {flash_fee_raw}")
    print(f"  gas_cost_raw            = {gas_cost_raw}")
    print(f"  relay_cost_raw          = {relay_cost_raw}")
    print(f"  risk_buffer_raw         = {risk_buffer_raw}")
    print(f"  minimum_profit_raw      = {minimum_profit_raw}")
    print(f"  ---------------------------------------------")
    print(f"  total_costs_raw         = {total_costs_raw}")
    print(f"  threshold (principal + costs + min_profit) = {threshold}")
    print(f"  surplus (out - threshold) = {surplus}")
    print(f"  passes (out > threshold)  = {passes}")
    print(f"  =============================================")
    return passes


@pytest.mark.parametrize("test_name, sell_amount_out_raw, flash_principal_raw, flash_fee_raw, gas_cost_raw, relay_cost_raw, risk_buffer_raw, minimum_profit_raw, expected_pass", [
    ("clear_profit", 10100, 10000, 0, 20, 10, 5, 1, True),
    ("exact_break_even_fails", 10036, 10000, 0, 20, 10, 5, 1, False),
    ("one_unit_profit_passes", 10037, 10000, 0, 20, 10, 5, 1, True),
    ("high_gas_cost_fails", 10100, 10000, 0, 200, 10, 5, 1, False),
    ("with_aave_flash_fee (pass)", 10100, 10000, 5, 20, 10, 5, 1, True),
    ("with_aave_flash_fee (fail)", 10041, 10000, 5, 20, 10, 5, 1, False),
    ("zero_minimum_profit_requirement", 10036, 10000, 0, 20, 10, 5, 0, True),
    pytest.param(
        "realistic_combination_of_all_costs",
        50000000000000000000 + 250000000000000000,
        50000000000000000000,
        2500000000000000,
        15000000000000000,
        5000000000000000,
        10000000000000000,
        5000000000000000,
        True,
        id="realistic_large_values"
    ),
])
def test_raw_execution_gate(test_name, sell_amount_out_raw, flash_principal_raw, flash_fee_raw, gas_cost_raw, relay_cost_raw, risk_buffer_raw, minimum_profit_raw, expected_pass):
    """Comprehensive test for the raw execution gate with various scenarios."""
    result = _transparent_dry_run(
        test_name,
        sell_amount_out_raw,
        flash_principal_raw,
        flash_fee_raw,
        gas_cost_raw,
        relay_cost_raw,
        risk_buffer_raw,
        minimum_profit_raw,
    )
    assert result is expected_pass


class TestRouteLifespanNPlus4(unittest.TestCase):
    """Tests for the new per-route block-based stalemate (n + 4)."""

    def test_within_lifespan(self):
        """Route discovered at n=100 must pass at current=103 (n+3)."""
        self.assertTrue(route_within_lifespan(discovery_block=100, current_block=103))

    def test_exactly_at_deadline(self):
        """Route discovered at n=100 must pass at current=104 (n+4)."""
        self.assertTrue(route_within_lifespan(discovery_block=100, current_block=104))

    def test_one_block_over_deadline_fails(self):
        """Route discovered at n=100 must FAIL at current=105 (n+5)."""
        self.assertFalse(route_within_lifespan(discovery_block=100, current_block=105))

    def test_early_blocks(self):
        """Should pass in the first blocks after discovery."""
        self.assertTrue(route_within_lifespan(discovery_block=5000, current_block=5000))
        self.assertTrue(route_within_lifespan(discovery_block=5000, current_block=5001))
        self.assertTrue(route_within_lifespan(discovery_block=5000, current_block=5002))

    def test_missing_discovery_block_is_stale(self):
        """Routes without discovery_block are treated as stale."""
        self.assertFalse(route_within_lifespan(discovery_block=None, current_block=100)) # type: ignore
        self.assertFalse(route_within_lifespan(discovery_block=0, current_block=100))
        self.assertFalse(route_within_lifespan(discovery_block=100, current_block=None)) # type: ignore
        self.assertFalse(route_within_lifespan(discovery_block=100, current_block=0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
