#!/usr/bin/env python3
# ==============================================================================
# validate_config.py -- Performs startup validation of core configuration.
#
# This script runs a series of checks against the centralized configuration
# to ensure system integrity and prevent common misconfiguration errors before
# a full system boot.
# ==============================================================================

import os
import sys

# Add project root to path to allow direct script execution from anywhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# It's crucial to handle potential import errors if config is malformed
try:
    from omega_v5.config import PROTOCOL_ID_MAP
except ImportError as e:
    print(f"[FATAL] Failed to import configuration from omega_v5.config: {e}")
    print("       This may be due to a syntax error in config.py or a missing dependency.")
    sys.exit(1)

# This set should be the source of truth for all protocols that have a
# functional adapter implemented in the system. When adding a new protocol
# adapter, it must also be added to this list.
KNOWN_PROTOCOLS = {
    "UniswapV3",
    "QuickSwapV2",
    "Balancer",
    "QuickSwapV3",
    "Algebra",
    "Sushiswap",
    "Curve",
}

def check_protocol_map() -> bool:
    """
    Ensures that all known, executable protocols have a valid ID mapping.
    This prevents payload generation failures for newly added protocols.
    """
    print("Verifying PROTOCOL_ID_MAP integrity...")
    errors_found = False

    # Check 1: Are all known protocols present in the map?
    missing_protocols = KNOWN_PROTOCOLS - set(PROTOCOL_ID_MAP.keys())
    if missing_protocols:
        errors_found = True
        for protocol in sorted(list(missing_protocols)):
            print(f"  [FAIL] Protocol '{protocol}' is a known protocol but is missing from PROTOCOL_ID_MAP in config.py.")

    # Check 2: Are there any unknown protocols in the map?
    unknown_protocols = set(PROTOCOL_ID_MAP.keys()) - KNOWN_PROTOCOLS
    if unknown_protocols:
        # This is a warning, not a failure, but still indicates a problem.
        for protocol in sorted(list(unknown_protocols)):
            print(f"  [WARN] Protocol '{protocol}' is in PROTOCOL_ID_MAP but is not in the KNOWN_PROTOCOLS list. This may indicate a typo or a deprecated protocol.")

    # Check 3: Are any protocol IDs invalid (e.g., 0)?
    for protocol, protocol_id in PROTOCOL_ID_MAP.items():
        if not isinstance(protocol_id, int) or protocol_id <= 0:
            errors_found = True
            print(f"  [FAIL] Protocol '{protocol}' has an invalid ID '{protocol_id}'. IDs must be integers greater than 0.")

    if not errors_found:
        print("  [SUCCESS] PROTOCOL_ID_MAP is consistent with all known protocols.")
        return True
    else:
        print("\n  [ACTION REQUIRED] Please update PROTOCOL_ID_MAP in omega_v5/config.py to resolve the issues above.")
        return False

def main() -> int:
    """Entry point for the configuration validation script."""
    print("\n--- System Configuration Integrity Check ---")
    results = [check_protocol_map()]
    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())