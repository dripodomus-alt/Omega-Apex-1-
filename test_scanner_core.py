"""
Root-level test entrypoint for the Rust scanner.
Delegates to the canonical tests in tests/rust/test_scanner_core.py
"""
import unittest
import sys
import os

# Add tests to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from tests.rust.test_scanner_core import TestRustScannerCore
except ImportError:
    TestRustScannerCore = None

if __name__ == "__main__":
    if TestRustScannerCore:
        suite = unittest.TestLoader().loadTestsFromTestCase(TestRustScannerCore)
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print("Rust tests not importable. Run 'maturin develop' first.")
        sys.exit(1)
