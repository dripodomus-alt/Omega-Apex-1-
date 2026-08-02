import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

motor_module = types.ModuleType("motor")
motor_asyncio_module = types.ModuleType("motor.motor_asyncio")


class _DummyAsyncIOMotorClient:
    def __init__(self, *args, **kwargs):
        pass


motor_asyncio_module.AsyncIOMotorClient = _DummyAsyncIOMotorClient
sys.modules.setdefault("motor", motor_module)
sys.modules.setdefault("motor.motor_asyncio", motor_asyncio_module)

pandas_module = types.ModuleType("pandas")
pandas_module.DataFrame = lambda *args, **kwargs: []
sys.modules.setdefault("pandas", pandas_module)

from execution_logger import ExecutionLogger, EXECUTION_STATUSES, RECEIPT_PENDING_STATUSES


def test_payload_hash_is_stable_for_key_ordering():
    left = {"opportunity_id": "opp-1", "payload": {"b": 2, "a": 1}}
    right = {"payload": {"a": 1, "b": 2}, "opportunity_id": "opp-1"}

    assert ExecutionLogger.compute_payload_hash(left) == ExecutionLogger.compute_payload_hash(right)


def test_execution_status_contract_matches_durable_storage_states():
    assert EXECUTION_STATUSES == {
        "quoted",
        "simulated",
        "submitted",
        "confirmed",
        "reverted",
        "expired",
    }
    assert RECEIPT_PENDING_STATUSES == {"submitted"}
