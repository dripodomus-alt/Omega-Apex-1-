import unittest
from decimal import Decimal

from omega_v5.config import MAX_FLASH_PRINCIPAL_USD
from omega_v5.route_proof_matrix import ProofProfile


class TestProofProfileValidation(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "name": "test_profile",
            "rank_fast_to_slow": 99,
            "intent": "validation test",
            "principal_usd": Decimal("1000"),
            "hops": (2,),
            "max_pools": 10,
            "stage_limit": 5,
            "max_quote_options_per_pair": 2,
            "max_token_paths": 100,
            "max_pre_ranked": 20,
            "slippage_bps": Decimal("5"),
        }

    def test_normalizes_hops_and_decimals(self):
        kwargs = self._base_kwargs()
        kwargs["hops"] = [2, 3]
        kwargs["principal_usd"] = "2500"
        kwargs["slippage_bps"] = "12"

        profile = ProofProfile(**kwargs)

        self.assertEqual(profile.hops, (2, 3))
        self.assertEqual(profile.principal_usd, Decimal("2500"))
        self.assertEqual(profile.slippage_bps, Decimal("12"))

    def test_rejects_principal_above_global_max(self):
        kwargs = self._base_kwargs()
        kwargs["principal_usd"] = Decimal(str(MAX_FLASH_PRINCIPAL_USD)) + Decimal("0.00000001")

        with self.assertRaises(ValueError):
            ProofProfile(**kwargs)

    def test_rejects_unsupported_hops(self):
        kwargs = self._base_kwargs()
        kwargs["hops"] = (5,)

        with self.assertRaises(ValueError):
            ProofProfile(**kwargs)

    def test_rejects_invalid_slippage(self):
        kwargs = self._base_kwargs()
        kwargs["slippage_bps"] = Decimal("-1")

        with self.assertRaises(ValueError):
            ProofProfile(**kwargs)


if __name__ == "__main__":
    unittest.main()
