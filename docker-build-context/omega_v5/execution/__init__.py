"""Execution, flash selection, staging, submission modules."""

from importlib import import_module

_LAZY_EXPORTS = {
    "select_best_flash_source": ("flash_source_selector", "select_best_flash_source"),
    "validate_calldata": ("calldata_validator", "validate_calldata"),
    "stage_payload": ("payload_stager", "stage_payload"),
    "NonceLaneManager": ("nonce_lane_manager", "NonceLaneManager"),
    "choose_submission_channel": ("submission_router", "choose_submission_channel"),
    "reconcile_receipt": ("receipt_reconciler", "reconcile_receipt"),
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        value = getattr(import_module(f".{module_name}", __name__), attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
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
try:
    _exec_mod = _load_from_sibling_execution()
    _PATCHABLE_EXECUTION_SYMBOLS = (
        "TOKEN_ADDRESSES",
        "TOKEN_DECIMALS",
        "C1_PAYLOAD_TARGET",
        "CHAIN_ID",
        "to_raw_units",
        "eip1559_fee_params",
        "route_tx_gas_limit",
        "revalidate_profitability_at_broadcast",
        "build_tx_payload",
    )
    for _name in _PATCHABLE_EXECUTION_SYMBOLS:
        if hasattr(_exec_mod, _name):
            globals()[_name] = getattr(_exec_mod, _name)

    def _sync_patchable_execution_symbols():
        for _name in _PATCHABLE_EXECUTION_SYMBOLS:
            if _name in globals():
                setattr(_exec_mod, _name, globals()[_name])
        # Keep the implementation module in sync with patched package-entrypoint wrappers.
        if "revalidate_profitability_at_broadcast" in globals():
            _exec_mod.revalidate_profitability_at_broadcast = globals()["revalidate_profitability_at_broadcast"]
        if "build_tx_payload" in globals():
            _exec_mod.build_tx_payload = globals()["build_tx_payload"]

    def build_tx_payload(*args, **kwargs):
        _sync_patchable_execution_symbols()
        if build_tx_payload.__wrapped__ is not None:
            return build_tx_payload.__wrapped__(*args, **kwargs)
        return _exec_mod.build_tx_payload(*args, **kwargs)
    build_tx_payload.__wrapped__ = _exec_mod.build_tx_payload

    simulate_tx_payload = _exec_mod.simulate_tx_payload
    simulation_from_address = _exec_mod.simulation_from_address
    run_dry_run_cycles = getattr(_exec_mod, "run_dry_run_cycles", lambda *a, **k: {})
    run_execution_loop = _exec_mod.run_execution_loop
    ExecutionResult = _exec_mod.ExecutionResult
    StagedForSubmission = _exec_mod.StagedForSubmission
    simulate_and_maybe_broadcast = _exec_mod.simulate_and_maybe_broadcast
    def revalidate_profitability_at_broadcast(*args, **kwargs):
        _sync_patchable_execution_symbols()
        _exec_mod.simulate_on_pending_block = globals().get("simulate_on_pending_block", _exec_mod.simulate_on_pending_block)
        if revalidate_profitability_at_broadcast.__wrapped__ is not None:
            return revalidate_profitability_at_broadcast.__wrapped__(*args, **kwargs)
        return _exec_mod.revalidate_profitability_at_broadcast(*args, **kwargs)
    revalidate_profitability_at_broadcast.__wrapped__ = _exec_mod.revalidate_profitability_at_broadcast

    simulate_on_pending_block = _exec_mod.simulate_on_pending_block

    def execute_route(op, pools, nonce=0):
        _sync_patchable_execution_symbols()
        try:
            if not revalidate_profitability_at_broadcast(op, pools):
                return ExecutionResult(success=False, detail="Failed re-profitability gate at execution entry")
            tx = build_tx_payload(op, pools, nonce)
            staged = StagedForSubmission(tx=tx, opportunity=op, payload_hash="legacy", envelope=None)
            loop = importlib.import_module("asyncio").get_event_loop()
            return loop.run_until_complete(simulate_and_maybe_broadcast(staged, pools))
        except (ValueError, TypeError) as e:
            return ExecutionResult(success=False, detail=f"Failed to build transaction payload: {e}")
        except Exception as e:
            return ExecutionResult(success=False, detail=f"Execution error: {e}")
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
except Exception as exc:
    raise ImportError("omega_v5.execution failed to load top-level execution.py; refusing unsafe fallback stubs") from exc

__all__ = [
    "select_best_flash_source",
    "validate_calldata",
    "stage_payload",
    "NonceLaneManager",
    "choose_submission_channel",
    "reconcile_receipt",
    "build_tx_payload",
    "TOKEN_ADDRESSES",
    "TOKEN_DECIMALS",
    "C1_PAYLOAD_TARGET",
    "CHAIN_ID",
    "to_raw_units",
    "eip1559_fee_params",
    "route_tx_gas_limit",
    "simulate_tx_payload",
    "simulation_from_address",
    "run_dry_run_cycles",
    "run_execution_loop",
    "ExecutionResult",
    "StagedForSubmission",
    "revalidate_profitability_at_broadcast",
    "simulate_on_pending_block",
    "execute_route",
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



