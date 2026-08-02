"""
Regression coverage for the standalone live-executor startup script.

The script should await the coroutine that LiveExecutor actually exposes for
block streaming, rather than the stale generic start() call.
"""
import ast
import inspect
import sys
import types
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
STARTUP_SCRIPT = BACKEND_DIR / "start_live_executor.py"


def _install_live_executor_import_stubs(monkeypatch):
    """Stub optional runtime-only dependencies so LiveExecutor can be imported."""

    web3_module = types.ModuleType("web3")

    class Web3:
        @staticmethod
        def HTTPProvider(url):
            return url

    web3_module.Web3 = Web3
    monkeypatch.setitem(sys.modules, "web3", web3_module)

    websockets_module = types.ModuleType("websockets")
    websockets_module.connect = object()
    monkeypatch.setitem(sys.modules, "websockets", websockets_module)

    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_module)

    governance_module = types.ModuleType("execution_governance")
    governance_module.get_minimum_net_profit_usd = lambda: 5.0
    governance_module.get_governance_service = lambda: None
    monkeypatch.setitem(sys.modules, "execution_governance", governance_module)

    execution_logger_module = types.ModuleType("execution_logger")

    class ExecutionLogger:
        async def start_execution_lifecycle(self, *args, **kwargs):
            return {"execution_id": "exec-test"}

        async def append_lifecycle_event(self, *args, **kwargs):
            return None

        async def complete_execution_lifecycle(self, *args, **kwargs):
            return None

    execution_logger_module.get_execution_logger = lambda: ExecutionLogger()
    monkeypatch.setitem(sys.modules, "execution_logger", execution_logger_module)

    arbitrage_module = types.ModuleType("arbitrage_engine")

    class ArbitrageEngine:
        pass

    class SpreadOpportunity:
        pass

    arbitrage_module.ArbitrageEngine = ArbitrageEngine
    arbitrage_module.SpreadOpportunity = SpreadOpportunity
    arbitrage_module.get_arbitrage_engine = lambda: None
    monkeypatch.setitem(sys.modules, "arbitrage_engine", arbitrage_module)

    institutional_module = types.ModuleType("institutional_executor")

    class InstitutionalExecutor:
        pass

    institutional_module.InstitutionalExecutor = InstitutionalExecutor
    institutional_module.C1_ADDRESS = "0x0000000000000000000000000000000000000000"
    monkeypatch.setitem(sys.modules, "institutional_executor", institutional_module)

    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    sys.modules.pop("live_executor", None)


def _executor_awaited_methods_in_main():
    tree = ast.parse(STARTUP_SCRIPT.read_text())
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main"
    )

    awaited_methods = []
    for node in ast.walk(main):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "executor"
        ):
            awaited_methods.append(func.attr)

    return awaited_methods


def test_startup_script_awaits_live_executor_block_stream_coroutine(monkeypatch):
    _install_live_executor_import_stubs(monkeypatch)
    from live_executor import LiveExecutor

    awaited_methods = _executor_awaited_methods_in_main()

    assert "start" not in awaited_methods
    assert "start_block_stream" in awaited_methods
    assert inspect.iscoroutinefunction(LiveExecutor.start_block_stream)
