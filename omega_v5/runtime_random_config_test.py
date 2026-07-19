#!/usr/bin/env python3
# ==============================================================================
# runtime_random_config_test.py -- fast runtime toggle/config proof.
# ==============================================================================

from __future__ import annotations

import random

from .execution import execution_guard_status, execution_armed
from .runtime_control import get_runtime_state, set_runtime_mode, update_runtime_settings


def _effective_cap(settings: dict) -> int:
    return 1 if settings.get("canary_mode") else int(settings.get("execute_top", 5))


def main() -> int:
    random.seed()
    print("Omega runtime random config dry-run proof")
    print("mode_policy=toggle_test_no_broadcast")
    set_runtime_mode("dry_run", actor="runtime_random_config_test_start")

    candidates = [
        {
            "execute_top": execute_top,
            "print_top_routes": print_top,
            "ticks": ticks,
            "principal_usd": str(principal),
            "interval_seconds": interval,
            "no_scan": no_scan,
            "canary_mode": canary,
        }
        for execute_top in [5, 10, 15]
        for print_top in [20, 50, 75]
        for ticks in [1, 2, 3]
        for principal in [5000, 10000, 25000, 50000]
        for interval in [30, 45, 60]
        for no_scan in [True, False]
        for canary in [True, False]
    ]
    for idx, settings in enumerate(random.sample(candidates, 3), 1):
        state = update_runtime_settings(settings, actor=f"runtime_random_config_test_{idx}")
        dry_state = set_runtime_mode("dry_run", actor=f"runtime_random_config_test_{idx}_dry")
        dry_guards = execution_guard_status(probe=False)
        dry_armed = execution_armed()
        live_state = set_runtime_mode("live", actor=f"runtime_random_config_test_{idx}_live_toggle")
        live_guards = execution_guard_status(probe=False)
        set_runtime_mode("dry_run", actor=f"runtime_random_config_test_{idx}_restore_dry")
        final_state = get_runtime_state()

        print(
            f"test_{idx}=PASS "
            f"settings_execute_top={state['settings']['execute_top']} "
            f"print_top={state['settings']['print_top_routes']} "
            f"ticks={state['settings']['ticks']} "
            f"principal_usd={state['settings']['principal_usd']} "
            f"interval_seconds={state['settings']['interval_seconds']} "
            f"no_scan={state['settings']['no_scan']} "
            f"settings_canary={state['settings']['canary_mode']} "
            f"effective_cap={_effective_cap(state['settings'])} "
            f"dry_mode={dry_state['mode']} "
            f"dry_execution_armed={dry_armed} "
            f"live_toggle_mode={live_state['mode']} "
            f"live_toggle_guard_runtime={live_guards.get('runtime_mode=live')} "
            f"restored_mode={final_state['mode']} "
            f"broadcast_guard={dry_guards.get('BROADCAST_RPC configured')}"
        )

    final = update_runtime_settings(
        {
            "execute_top": 5,
            "print_top_routes": 50,
            "ticks": 1,
            "principal_usd": "50000",
            "interval_seconds": 60,
            "no_scan": True,
            "canary_mode": True,
        },
        actor="runtime_random_config_test_final_canary_dry",
    )
    set_runtime_mode("dry_run", actor="runtime_random_config_test_final_dry")
    print(
        "final_runtime=PASS "
        f"mode={get_runtime_state()['mode']} "
        f"canary_mode={final['settings']['canary_mode']} "
        f"execute_top={final['settings']['execute_top']} "
        f"effective_cap={_effective_cap(final['settings'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
