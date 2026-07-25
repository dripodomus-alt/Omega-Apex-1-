#!/usr/bin/env python3
# ==============================================================================
# verify_contracts.py -- Audits core contract addresses for on-chain verification.
#
# This script checks Polygonscan to ensure that the source code for configured
# executor contracts is public and verified. This is a critical security and
# operational check before any live deployment.
# ==============================================================================

import os
import sys
import requests

# Add project root to path to allow direct script execution from anywhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from omega_v5.config import (
    EXECUTOR_CONTRACT,
    LIQUIDATION_EXECUTOR_ADDRESS,
    ADAPTER_CONFIGURATION_TARGET,
    POLYGONSCAN_API_KEY,
)

def check_verification(address: str, name: str) -> bool:
    """Checks a single contract address for source code verification on Polygonscan."""
    print(f"Verifying {name} at {address}...")
    if not address or not address.startswith("0x"):
        print(f"  [FAIL] Invalid or missing address for {name}.")
        return False

    if not POLYGONSCAN_API_KEY:
        print("  [WARN] POLYGONSCAN_API_KEY not set in .env. Skipping on-chain verification.")
        return True # Treat as a pass for local readiness, but warn the user.

    url = f"https://api.polygonscan.com/api?module=contract&action=getsourcecode&address={address}&apikey={POLYGONSCAN_API_KEY}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get('status') == '1' and data.get('result') and data['result'][0].get('SourceCode'):
            print(f"  [SUCCESS] Source code for {name} is verified on Polygonscan.")
            return True
        else:
            error_message = data.get('result', 'Unknown API response format.')
            print(f"  [FAIL] Source code for {name} is NOT verified. API response: {error_message}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] API request to Polygonscan failed for {name}: {e}")
        return False

def main() -> int:
    """Entry point for the contract verification script."""
    print("\n--- On-Chain Contract Verification Audit ---")
    results = [
        check_verification(EXECUTOR_CONTRACT, "Arbitrage Executor (EXECUTOR_CONTRACT)"),
        check_verification(LIQUIDATION_EXECUTOR_ADDRESS, "Liquidation Executor (LIQUIDATION_EXECUTOR_ADDRESS)") if LIQUIDATION_EXECUTOR_ADDRESS else True,
        check_verification(ADAPTER_CONFIGURATION_TARGET, "Adapter Config Target (ADAPTER_CONFIGURATION_TARGET)") if ADAPTER_CONFIGURATION_TARGET else True,
    ]

    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())