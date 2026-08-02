from pathlib import Path
import sys
import os
import pytest

from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs into os.environ without overriding existing values."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _bootstrap_test_env() -> None:
    """Force pytest runs onto test configuration by default."""
    test_env_path = ROOT / "test.env"
    os.environ.setdefault("OMEGA_ENV_PATH", str(test_env_path))
    _load_env_file(Path(os.environ["OMEGA_ENV_PATH"]))

    defaults = {
        "OMEGA_RUNTIME_MODE": "dry_run",
        "EXECUTION_MODE": "dry_run",
        "LIVE_TRADING": "0",
        "CONFIRM_MAINNET_EXECUTION": "",
        "API_FRONTEND_TOKEN_REQUIRED": "false",
        "OMEGA_LIVE_TEST": "",
        "CHAIN_ID": "137",
        "FORK_RPC_URL": "http://127.0.0.1:8545",
        "FORK_SIM_RPC_URL": "http://127.0.0.1:8545",
        "FORK_UPSTREAM_RPC_URL": "https://polygon-rpc.com",
        "POLYGON_RPC_URL": "https://polygon-rpc.com",
        "POLYGON_WSS_URL": "wss://rpc-mainnet.matic.network",
        "PRIMARY_READ_RPC_URL": "https://polygon-rpc.com",
        "PRIMARY_WSS_URL": "wss://rpc-mainnet.matic.network",
        "BROADCAST_RPC_URL": "https://polygon-rpc.com",
        "BROADCAST_WSS_URL": "wss://rpc-mainnet.matic.network",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "REDIS_ENABLED": "false",
        "DATABASE_URL": "sqlite:///./out/omega_test.db",
        "EXECUTOR_WALLET": "0x000000000000000000000000000000000000dEaD",
        "PRIVATE_KEY": "0x" + "11" * 32,
        "EXECUTOR_PRIVATE_KEY": "0x" + "11" * 32,
        "PROFIT_RECIPIENT_ADDRESS": "0x000000000000000000000000000000000000dEaD",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


_bootstrap_test_env()


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

    if "fork" in request.node.keywords:
        fork_url = os.getenv("FORK_RPC_URL", "http://127.0.0.1:8545")
        try:
            if not Web3(Web3.HTTPProvider(fork_url)).is_connected():
                pytest.skip(f"fork: local fork RPC unavailable at {fork_url}")
        except Exception:
            pytest.skip(f"fork: local fork RPC unavailable at {fork_url}")

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
