from decimal import Decimal


def assert_close(actual: Decimal, expected: Decimal, tolerance: Decimal = Decimal("1e-24")) -> None:
    """Asserts that two Decimals are close within a given tolerance."""
    assert abs(actual - expected) <= tolerance, f"Assertion failed: {actual} is not close to {expected}"


def is_live_mode() -> bool:
    """Helper used by live integration tests."""
    import os
    return bool(os.getenv("OMEGA_LIVE_TEST") or os.getenv("LIVE_TEST_RPC_URL"))
