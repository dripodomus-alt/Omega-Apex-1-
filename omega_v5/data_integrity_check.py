"""
data_integrity_check.py - Executable module for verifying data store health.

This script is called by the master readiness benchmark to ensure that persistent
data stores like Redis and the SQLite indexer are connected and healthy, in
accordance with the project's data governance policy.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the project root is on the Python path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5 import config, indexer_state, redis_cache  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def check_redis() -> bool:
    """Checks the status of the Redis connection."""
    logger.info("Checking Redis connection...")
    if not redis_cache.enabled():
        logger.info("Redis is disabled via config. Skipping check.")
        return True

    is_ok, message = redis_cache.status()
    if is_ok:
        logger.info(f"Redis status: OK ({message})")
        return True
    else:
        logger.error(f"Redis status: FAILED ({message})")
        return False


def check_indexer() -> bool:
    """Checks the status of the SQLite indexer database."""
    logger.info("Checking SQLite Indexer status...")
    status = indexer_state.indexer_status()

    if not status.get("present"):
        logger.info("SQLite Indexer DB not found. This is acceptable. Skipping check.")
        return True

    if status.get("healthy"):
        logger.info(f"SQLite Indexer status: OK. Found {status.get('pool_state_rows', 0)} pool states.")
        return True
    else:
        logger.error(f"SQLite Indexer status: FAILED. Error: {status.get('error', 'Unknown')}")
        return False


def main() -> int:
    """Runs all data integrity checks and exits with an appropriate status code."""
    checks = [check_redis, check_indexer]
    results = [check() for check in checks]

    if all(results):
        logger.info("All data integrity checks passed.")
        return 0
    else:
        logger.error("One or more data integrity checks failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())