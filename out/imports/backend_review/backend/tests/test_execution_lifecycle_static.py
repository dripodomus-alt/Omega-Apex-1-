"""Static regression tests for persisted execution lifecycle wiring."""
import ast
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
LIVE_EXECUTOR = BACKEND_DIR / "live_executor.py"
SERVER = BACKEND_DIR / "server.py"
UNIFIED_CONTROLLER = BACKEND_DIR / "unified_strategy_controller.py"


def _function_node(tree, name):
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_live_executor_persists_real_lifecycle_stages():
    tree = ast.parse(LIVE_EXECUTOR.read_text())
    source = LIVE_EXECUTOR.read_text()
    execute = _function_node(tree, "execute_opportunity")
    execute_source = ast.get_source_segment(source, execute)

    assert "self._start_lifecycle" in execute_source
    assert "transaction_submitted" in execute_source
    assert "receipt_confirmed" in execute_source
    assert "self._complete_lifecycle" in execute_source
    assert "execution_id" in execute_source
    assert "tx_hash_hex = self._tx_hash_hex(tx_hash)" in execute_source


def test_server_exposes_persisted_history_and_trace_routes():
    tree = ast.parse(SERVER.read_text())

    routes = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and func.attr == "get"):
                continue
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                routes[decorator.args[0].value] = node.name

    assert routes["/executor/history"] == "api_get_execution_history"
    assert routes["/executor/trace/{execution_id}"] == "api_get_execution_trace"


def test_unified_controller_does_not_return_fabricated_tx_hashes():
    source = UNIFIED_CONTROLLER.read_text()

    assert "'0x' + 'c1'" not in source
    assert "'0x' + 'c2liq'" not in source
    assert "'0x' + 'front'" not in source
    assert "'0x' + 'back'" not in source
    assert "C1 live broadcaster is not configured" in source
    assert "C2 liquidation broadcaster is not configured" in source
    assert "sandwich transaction broadcaster is not configured" in source
