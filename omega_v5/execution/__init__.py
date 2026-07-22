"""Execution, flash selection, staging, submission modules."""

from .flash_source_selector import select_best_flash_source
from .calldata_validator import validate_calldata
from .payload_stager import stage_payload
from .nonce_lane_manager import NonceLaneManager
from .submission_router import choose_submission_channel
from .receipt_reconciler import reconcile_receipt

# Re-export core functions from the top-level execution.py module.
# This resolves the package vs module name collision (execution/ dir vs execution.py).
# Always use explicit file load to reliably bypass package shadowing.
import importlib.util
import os


def _load_from_sibling_execution():
    _exec_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "execution.py")
    _spec = importlib.util.spec_from_file_location("omega_v5._execution_impl", _exec_path)
    _exec_mod = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_exec_mod)
    return _exec_mod


# Always use the explicit loader to avoid package/module name collision.
# The try/except provides a last-resort fallback to prevent total import
# failure if execution.py has a syntax error or is otherwise unloadable.
try:
    _exec_mod = _load_from_sibling_execution()
    build_tx_payload = _exec_mod.build_tx_payload
    simulate_tx_payload = _exec_mod.simulate_tx_payload
    simulation_from_address = _exec_mod.simulation_from_address
    run_dry_run_cycles = _exec_mod.run_dry_run_cycles
    run_execution_loop = _exec_mod.run_execution_loop
    _await_next_block = _exec_mod._await_next_block
    execution_armed = _exec_mod.execution_armed
    execution_guard_status = _exec_mod.execution_guard_status
    AdapterSemanticError = _exec_mod.AdapterSemanticError
    EXECUTE_FLASH_ARB_SELECTOR = _exec_mod.EXECUTE_FLASH_ARB_SELECTOR
    executor_owner = _exec_mod.executor_owner
    executor_code_status = _exec_mod.executor_code_status
    _receipt_dict = _exec_mod._receipt_dict
    _broadcast_w3 = _exec_mod._broadcast_w3
    wallet_address = _exec_mod.wallet_address
except Exception:
    # Last resort placeholders to avoid total import failure
    import asyncio

    build_tx_payload = lambda *a, **k: {}
    simulate_tx_payload = lambda *a, **k: (True, "")
    simulation_from_address = lambda: "0x0"
    run_dry_run_cycles = lambda *a, **k: {}
    run_execution_loop = lambda *a, **k: asyncio.sleep(0)
    _await_next_block = lambda: asyncio.sleep(0)
    execution_armed = lambda: False
    execution_guard_status = lambda: {}
    executor_owner = lambda: ""
    _receipt_dict = lambda receipt: {}
    wallet_address = lambda: ""
    executor_code_status = lambda: (False, "execution_import_failed")
    _broadcast_w3 = lambda: None
    AdapterSemanticError = RuntimeError
    EXECUTE_FLASH_ARB_SELECTOR = "0x626482a3"

__all__ = [
    "select_best_flash_source",
    "validate_calldata",
    "stage_payload",
    "NonceLaneManager",
    "choose_submission_channel",
    "reconcile_receipt",
    "build_tx_payload",
    "simulate_tx_payload",
    "simulation_from_address",
    "run_dry_run_cycles",
    "run_execution_loop",
    "_await_next_block",
    "execution_armed",
    "execution_guard_status",
    "AdapterSemanticError",
    "EXECUTE_FLASH_ARB_SELECTOR",
    "executor_owner",
    "executor_code_status",
    "_receipt_dict",
    "_broadcast_w3",
    "wallet_address",
]

