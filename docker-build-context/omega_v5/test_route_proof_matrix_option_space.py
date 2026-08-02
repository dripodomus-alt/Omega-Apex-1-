import unittest

from omega_v5.route_proof_matrix import _option_space_estimate_for_path


class TestRouteProofMatrixOptionSpace(unittest.TestCase):
    def test_estimate_counts_with_capped_options(self):
        path = ("USDC", "WETH", "USDC")
        rates = {
            ("USDC", "WETH"): [{"pool_id": "a"}, {"pool_id": "b"}, {"pool_id": "c"}],
            ("WETH", "USDC"): [{"pool_id": "d"}, {"pool_id": "e"}],
        }

        combinations, has_full_path, counts = _option_space_estimate_for_path(path, rates, 2)

        self.assertTrue(has_full_path)
        self.assertEqual(counts, [2, 2])
        self.assertEqual(combinations, 4)

    def test_estimate_reports_missing_edge(self):
        path = ("USDC", "WBTC", "USDC")
        rates = {
            ("USDC", "WBTC"): [{"pool_id": "a"}],
        }

        combinations, has_full_path, counts = _option_space_estimate_for_path(path, rates, 3)

        self.assertFalse(has_full_path)
        self.assertEqual(combinations, 0)
        self.assertEqual(counts, [1])


if __name__ == "__main__":
    unittest.main()
