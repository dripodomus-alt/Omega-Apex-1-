import unittest
from decimal import Decimal

from omega_v5 import accounting, units


class TestUnitsSynchronization(unittest.TestCase):
    def test_decimal_x18_roundtrip_is_stable(self):
        value = Decimal("123.456789")
        value_x18 = units.decimal_to_x18(value)
        self.assertEqual(value_x18, 123456789000000000000)
        self.assertEqual(units.x18_to_decimal(value_x18), value)
        self.assertEqual(accounting.value_to_x18(value), value_x18)
        self.assertEqual(accounting.x18_to_value(value_x18), value)

    def test_x18_equivalence_uses_shared_deviation_math(self):
        reference = 10**18
        within_threshold = reference + 500_000_000_000_000
        outside_threshold = reference + 20_000_000_000_000_000

        self.assertTrue(units.value_equivalent_x18(within_threshold, reference, max_deviation_bps=5))
        self.assertFalse(units.value_equivalent_x18(outside_threshold, reference, max_deviation_bps=5))
        self.assertEqual(units.x18_deviation_bps(within_threshold, reference), 5)

    def test_accounting_raw_floor_uses_explicit_decimals(self):
        self.assertEqual(accounting.token_units_to_raw_floor(Decimal("1.234567"), 6), 1234567)
        self.assertEqual(units.to_raw_units("USDC", Decimal("1.234567"), decimals_override=6), 1234567)


if __name__ == "__main__":
    unittest.main()
