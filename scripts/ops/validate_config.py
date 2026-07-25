#!/usr/bin/env python3
# ==============================================================================
# validate_config.py -- Startup validation of core configuration + capital injector.
# ==============================================================================

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    from omega_v5.config import PROTOCOL_ID_MAP
except ImportError as e:
    print(f"[FATAL] Failed to import configuration from omega_v5.config: {e}")
    print("       This may be due to a syntax error in config.py or a missing dependency.")
    sys.exit(1)

KNOWN_PROTOCOLS = {
    "V3_CLMM",
    "QS_V2_CPMM",
    "BAL_WEIGHTED",
    "QS_V3_ALGEBRA",
    "SUSHI_V2_CPMM",
}


def check_protocol_map() -> bool:
    print("Verifying PROTOCOL_ID_MAP integrity...")
    errors_found = False

    missing_protocols = KNOWN_PROTOCOLS - set(PROTOCOL_ID_MAP.keys())
    if missing_protocols:
        errors_found = True
        for protocol in sorted(missing_protocols):
            print(
                f"  [FAIL] Protocol '{protocol}' is a known protocol but is missing "
                "from PROTOCOL_ID_MAP in config.py."
            )

    unknown_protocols = set(PROTOCOL_ID_MAP.keys()) - KNOWN_PROTOCOLS
    if unknown_protocols:
        for protocol in sorted(unknown_protocols):
            print(
                f"  [WARN] Protocol '{protocol}' is in PROTOCOL_ID_MAP but is not in "
                "the KNOWN_PROTOCOLS list."
            )

    for protocol, protocol_id in PROTOCOL_ID_MAP.items():
        if not isinstance(protocol_id, int) or protocol_id <= 0:
            errors_found = True
            print(
                f"  [FAIL] Protocol '{protocol}' has an invalid ID '{protocol_id}'. "
                "IDs must be integers greater than 0."
            )

    if not errors_found:
        print("  [SUCCESS] PROTOCOL_ID_MAP is consistent with known protocols.")
        return True
    print("\n  [ACTION REQUIRED] Update PROTOCOL_ID_MAP in omega_v5/config.py.")
    return False


def check_capital_injector() -> bool:
    """Validate segregated registries, cannibalization guard, and derivative formula."""
    print("Verifying capital_injector registries + sizing formula...")
    try:
        from omega_v5.capital_injector import (
            CAPITAL_SOURCE_REGISTRY,
            EXECUTION_VENUE_REGISTRY,
            check_self_cannibalization,
            compute_derivative_optimal_size,
            compute_optimal_injection,
        )
        from omega_v5.flash_loan import FlashSource
    except Exception as exc:
        print(f"  [FAIL] Could not import capital_injector: {exc}")
        return False

    ok = True

    if "BALANCER" not in CAPITAL_SOURCE_REGISTRY or "AAVE_V3" not in CAPITAL_SOURCE_REGISTRY:
        print("  [FAIL] CAPITAL_SOURCE_REGISTRY missing BALANCER or AAVE_V3.")
        ok = False
    else:
        print("  [SUCCESS] CAPITAL_SOURCE_REGISTRY has funding silos.")

    # Registries must not share keys by construction (funding vs empty/dynamic venues)
    overlap = set(CAPITAL_SOURCE_REGISTRY.keys()) & set(EXECUTION_VENUE_REGISTRY.keys())
    if overlap:
        print(f"  [FAIL] Registry key overlap (cannibal risk): {overlap}")
        ok = False
    else:
        print("  [SUCCESS] No static key overlap between funding and execution registries.")

    # Cannibalization: route includes funding pool id
    funding_id = CAPITAL_SOURCE_REGISTRY["BALANCER"]["pool_id"]
    is_c, msg = check_self_cannibalization("BALANCER", [funding_id, "POOL_TRADE_A"])
    if not is_c or "SELF-CANNIBALIZATION" not in msg:
        print("  [FAIL] Cannibalization guard did not trip on funding pool overlap.")
        ok = False
    else:
        print("  [SUCCESS] Cannibalization guard trips on funding/route overlap.")

    is_c2, _ = check_self_cannibalization("BALANCER", ["POOL_A", "POOL_B"])
    if is_c2:
        print("  [FAIL] Cannibalization guard false-positive on clean route.")
        ok = False
    else:
        print("  [SUCCESS] Clean route passes cannibalization guard.")

    # Derivative formula: friction fails when sqrt <= Rin
    zero_size = compute_derivative_optimal_size(
        Decimal("100000"),
        Decimal("100000"),
        Decimal("0.003"),
        Decimal("0.0005"),
    )
    # Equal reserves + fees should yield ~0 or small; with fees sqrt(R^2*(1-f)^2) < R
    if zero_size < 0:
        print("  [FAIL] Derivative size went negative.")
        ok = False
    else:
        print(f"  [SUCCESS] Derivative formula returns non-negative size ({zero_size}).")

    # Positive edge case: Rout >> Rin
    pos = compute_derivative_optimal_size(
        Decimal("10000"),
        Decimal("12000"),
        Decimal("0.003"),
        Decimal("0"),
    )
    if pos <= 0:
        print("  [WARN] Derivative size was 0 on mild positive spread (may be friction).")
    else:
        print(f"  [SUCCESS] Derivative formula finds positive size on spread ({pos}).")

    # End-to-end injector blocks cannibal route
    pools = {
        funding_id: {
            "total_executable_liquidity_usd": "500000",
            "fee_bps": 3000,
            "tokens": ["USDC", "WETH"],
            "reserves": ["250000", "100"],
        },
        "POOL_B": {
            "total_executable_liquidity_usd": "400000",
            "fee_bps": 3000,
        },
    }
    result = compute_optimal_injection(
        pool_sequence=[funding_id, "POOL_B"],
        pools=pools,
        flash_source=FlashSource.BALANCER,
    )
    if not result.cannibalization_detected or result.optimal_injection_usd != 0:
        print("  [FAIL] compute_optimal_injection did not block cannibal route.")
        ok = False
    else:
        print("  [SUCCESS] compute_optimal_injection blocks cannibal route with size 0.")

    return ok


def main() -> int:
    print("\n--- System Configuration Integrity Check ---")
    results = [check_protocol_map(), check_capital_injector()]
    print()
    if all(results):
        print("All checks passed.")
        return 0
    print("One or more checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
