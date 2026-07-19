from pathlib import Path

from omega_v5.logic_data_audit import audit_paths
from omega_v5.pipeline_integrity_proof import build_integrity_proof


def test_logic_data_audit_finds_import_return_mutation_and_math(tmp_path: Path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        """
from decimal import Decimal
import requests
from omega_v5 import redis_cache

TOKEN_DECIMALS = {"USDC": 6}

def quote_profit(amount_usd, gas_price_gwei):
    payload = requests.get("https://example.invalid").json()
    gas_cost_usd = Decimal(str(gas_price_gwei)) * Decimal("21000") / Decimal("1e9")
    redis_cache.set_json("route", {"gas": str(gas_cost_usd)})
    return {"profit_usd": Decimal(str(amount_usd)) - gas_cost_usd, "payload": payload}
""",
        encoding="utf-8",
    )

    report = audit_paths([sample])

    assert report["ok"] is True
    assert report["summary"]["files_scanned"] == 1
    assert report["summary"]["external_import_points"] >= 1
    assert report["summary"]["mutation_points"] >= 2
    assert report["summary"]["math_sensitive_points"] >= 1
    assert report["summary"]["return_points"] >= 1


def test_pipeline_integrity_proof_includes_canonical_math_and_runtime_modules():
    report = build_integrity_proof(["omega_v5/accounting.py", "omega_v5/logic_data_audit.py"])

    assert "canonical_route_math" in report
    assert any(row["name"] == "net_gain" for row in report["canonical_route_math"])
    assert report["required_runtime_modules"]["omega_v5/accounting.py"] is True
