from pathlib import Path
import sys
import os
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config):
    """Register custom markers so they are recognized."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "requires_anvil: tests requiring Anvil fork (skipped if FORK_SIM_RPC_URL not set to local)"
    )
    config.addinivalue_line(
        "markers", "requires_redis: tests requiring Redis (skipped if no REDIS config)"
    )
    config.addinivalue_line(
        "markers", "live_integration: tests using live RPC or real pool data (skipped unless OMEGA_LIVE_TEST=1 or LIVE_TEST_RPC_URL set)"
    )


@pytest.fixture(autouse=True)
def _auto_skip_service_dependent_tests(request):
    """Prevent stalling by auto-skipping tests that need external services when not available."""
    if "requires_anvil" in request.node.keywords:
        fork_url = os.getenv("FORK_SIM_RPC_URL", "")
        if not fork_url or ("127.0.0.1" not in fork_url and "localhost" not in fork_url and "anvil" not in fork_url.lower()):
            pytest.skip("requires_anvil: No local Anvil fork detected (FORK_SIM_RPC_URL must point to 127.0.0.1)")

    if "requires_redis" in request.node.keywords:
        redis_url = os.getenv("REDIS_URL", "") or os.getenv("REDIS_HOST", "")
        if not redis_url:
            pytest.skip("requires_redis: No Redis configured (set REDIS_URL or REDIS_HOST)")

    if "live_integration" in request.node.keywords:
        live_flag = os.getenv("OMEGA_LIVE_TEST", "") or os.getenv("LIVE_TEST_RPC_URL", "")
        if not live_flag:
            pytest.skip("live_integration: Set OMEGA_LIVE_TEST=1 or LIVE_TEST_RPC_URL to run live data tests")


@pytest.fixture
def live_rpc():
    """Provides a live or fork Web3 instance when live tests are enabled."""
    from omega_v5.rpc_layer import w3
    live_flag = os.getenv("OMEGA_LIVE_TEST", "") or os.getenv("LIVE_TEST_RPC_URL", "")
    if not live_flag:
        pytest.skip("live_rpc fixture requires OMEGA_LIVE_TEST=1 or LIVE_TEST_RPC_URL")
    return w3


def pytest_collection_modifyitems(config, items):
    """Further filter to avoid stalling: deselect slow/requires when in benchmark mode."""
    if config.getoption("-m"):
        marker_expr = str(config.getoption("-m"))
        if "not slow" in marker_expr or "not requires_anvil" in marker_expr:
            skipped = []
            for item in items:
                if "slow" in item.keywords or "requires_anvil" in item.keywords:
                    item.add_marker(pytest.mark.skip(reason="Skipped in benchmark run for speed/no-stall"))
            # Note: actual deselection happens via -m flag in addopts


# Optional: ensure no test runs longer than configured even if plugin missing
def pytest_runtest_setup(item):
    # Fallback safety
    pass
