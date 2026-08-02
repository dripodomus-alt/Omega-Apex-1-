#!/usr/bin/env python3
# ==============================================================================
# logic_data_audit.py -- static map of critical data and math interaction points.
# ==============================================================================

from __future__ import annotations

import argparse
import ast
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .paths import output_path, repo_path, resolve_repo_relative


LOGIC_DATA_AUDIT_REPORT_PATH = output_path("logic_data_audit_latest.json")

CRITICAL_DEBUGGING_AREAS: list[dict[str, str]] = [
    {
        "area": "time_and_state_freshness",
        "why_it_matters": "Arbitrage and AI decisions decay when block, cache, quote, or model state is stale.",
        "proof_focus": "block numbers, quote timestamps, Redis TTLs, report freshness, fork upstream block.",
    },
    {
        "area": "units_decimals_and_rounding",
        "why_it_matters": "Wei, gwei, POL, token decimals, USD, raw units, and rounding direction decide whether calldata reverts.",
        "proof_focus": "Decimal usage, floor conversions, raw/unit transforms, gas native/USD accounting.",
    },
    {
        "area": "token_identity_and_metadata",
        "why_it_matters": "Symbol collisions, bridged variants, stale decimals, and bad pool metadata can create false spreads.",
        "proof_focus": "TOKEN_ADDRESSES, TOKEN_DECIMALS, apprentice promotions, token calibration, on-chain ERC20 checks.",
    },
    {
        "area": "liquidity_quality_and_duplicate_edges",
        "why_it_matters": "Raw-positive routes collapse when duplicate or shallow liquidity is counted as executable depth.",
        "proof_focus": "pool quality filters, route signatures, protocol family semantics, pool hydration completeness.",
    },
    {
        "area": "expense_accounting",
        "why_it_matters": "Flash fee, swap fee, gas, relay cost, slippage, and risk buffers must be subtracted before execution.",
        "proof_focus": "net_profit_usd, gas_cost_usd, flashloan_fee_usd, extra_slippage_buffer_usd, min profit floors.",
    },
    {
        "area": "rpc_oracle_and_cache_boundaries",
        "why_it_matters": "RPC, oracle, Redis, subgraph, and file snapshots are separate trust boundaries with different failure modes.",
        "proof_focus": "requests/httpx/aiohttp, Web3 providers, redis writes, JSON report imports, fallback sources.",
    },
    {
        "area": "calldata_and_executor_semantics",
        "why_it_matters": "A profitable quote is not executable unless adapter semantics and encoded route calldata match the executor.",
        "proof_focus": "payload envelopes, exact-call simulation, adapter source IDs, ABI encoding, revert decoding.",
    },
    {
        "area": "async_background_mutation",
        "why_it_matters": "Discovery, metadata runners, watchers, API controls, and engine loops can race over shared registries.",
        "proof_focus": "background loops, Redis streams, JSON writes, runtime settings, registry mutation points.",
    },
    {
        "area": "wallet_nonce_and_broadcast_control",
        "why_it_matters": "Only the user wallet pays gas; nonce, balance, signing key, and broadcast lane mistakes are live-risk events.",
        "proof_focus": "sign_transaction, send_raw_transaction, receipt gas, owner checks, canary mode, live acknowledgements.",
    },
    {
        "area": "ml_decision_feedback",
        "why_it_matters": "ML can improve prioritization, but stale labels or leakage can promote routes that fail executor truth.",
        "proof_focus": "feature inputs, labels, model version, fail-closed status, ranker overrides versus hard gates.",
    },
]

CANONICAL_ROUTE_MATH: list[dict[str, str]] = [
    {
        "name": "directional_mid_token_spread",
        "equation": "raw_spread_usd_per_mid = executable_sell_price_usd_per_mid - executable_buy_price_usd_per_mid",
    },
    {
        "name": "buy_leg_mid_units",
        "equation": "mid_units_min_in = base_capital_usd / executable_buy_price_usd_per_mid",
    },
    {
        "name": "sell_leg_base_out",
        "equation": "base_out_usd = mid_units_min_in * executable_sell_price_usd_per_mid",
    },
    {
        "name": "raw_delta",
        "equation": "raw_delta_usd = base_out_usd - base_capital_usd",
    },
    {
        "name": "net_gain",
        "equation": "net_gain_usd = raw_delta_usd - flashloan_fee_usd - gas_cost_usd - relay_or_private_submit_cost_usd - risk_buffer_usd - extra_slippage_buffer_usd",
    },
    {
        "name": "executor_truth_gate",
        "equation": "executable = exact_call_pass and net_gain_usd > minimum_profit_usd and calldata_semantics_valid",
    },
]

EXTERNAL_IMPORT_PATTERNS = {
    "requests.get": "http_read",
    "requests.post": "http_write_or_probe",
    "httpx.get": "http_read",
    "httpx.post": "http_write_or_probe",
    "aiohttp": "async_http",
    "websocket": "websocket_read",
    "Web3.HTTPProvider": "rpc_provider",
    "Web3.WebsocketProvider": "rpc_provider",
    "json.load": "json_import",
    "json.loads": "json_import",
    "read_text": "file_import",
    "open": "file_import",
}

RETURN_RISK_KEYWORDS = (
    "quote",
    "price",
    "profit",
    "delta",
    "gas",
    "fee",
    "slippage",
    "route",
    "calldata",
    "payload",
    "executor",
    "truth",
    "pool",
    "liquid",
    "metadata",
    "oracle",
    "token",
    "amount",
)

MATH_RISK_KEYWORDS = RETURN_RISK_KEYWORDS + (
    "usd",
    "raw",
    "wei",
    "gwei",
    "pol",
    "decimals",
    "reserve",
    "liquidity",
    "principal",
    "borrow",
    "repay",
    "bps",
)

MUTATION_CALL_PATTERNS = {
    "write_text": "file_report_write",
    "json.dump": "json_write",
    "redis_cache.set_json": "redis_cache_write",
    "redis_cache.xadd": "redis_stream_write",
    "redis_cache.publish": "redis_pubsub_write",
    "send_raw_transaction": "broadcast_write",
    "sign_transaction": "signing_operation",
    "set_runtime_mode": "runtime_control_mutation",
    "update_runtime_settings": "runtime_control_mutation",
}

LIVE_RPC_READ_PATTERNS = (
    "eth.get_balance",
    "eth.get_block",
    "eth.get_logs",
    "eth.get_code",
    "eth.chain_id",
    ".call",
    "simulate_tx_payload",
    "simulate_liquidation",
)

HIGH_RISK_ASSIGNMENT_KEYWORDS = (
    "TOKEN_ADDRESSES",
    "TOKEN_DECIMALS",
    "TOKEN_USD_PRICE",
    "DEEP_POOL_REGISTRY",
    "POOL",
    "PRICE",
    "DECIMAL",
    "GAS",
    "PROFIT",
    "SLIPPAGE",
    "EXECUTOR",
    "PRIVATE_KEY",
    "LIVE_FLAG",
    "EXEC_MODE",
)


def _dotted(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        inner = _dotted(node.func)
        return f"{inner}()" if inner else "call()"
    if isinstance(node, ast.Subscript):
        return _dotted(node.value) + "[]"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _contains_keyword(value: str, keywords: Iterable[str]) -> bool:
    lowered = value.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _record(file_path: Path, root: Path, line: int, category: str, name: str, function: str, detail: str) -> dict[str, Any]:
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        rel = file_path
    return {
        "file": str(rel).replace("\\", "/"),
        "line": int(line or 0),
        "category": category,
        "name": name,
        "function": function,
        "detail": detail[:500],
    }


class LogicDataVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, root: Path) -> None:
        self.file_path = file_path
        self.root = root
        self.function_stack: list[str] = []
        self.external_import_points: list[dict[str, Any]] = []
        self.return_points: list[dict[str, Any]] = []
        self.mutation_points: list[dict[str, Any]] = []
        self.math_sensitive_points: list[dict[str, Any]] = []
        self.live_state_points: list[dict[str, Any]] = []

    @property
    def current_function(self) -> str:
        return ".".join(self.function_stack) if self.function_stack else "<module>"

    def _emit(self, collection: list[dict[str, Any]], node: ast.AST, category: str, name: str, detail: str) -> None:
        collection.append(
            _record(
                self.file_path,
                self.root,
                getattr(node, "lineno", 0),
                category,
                name,
                self.current_function,
                detail,
            )
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in {"requests", "httpx", "aiohttp", "websocket", "web3"}:
                self._emit(self.external_import_points, node, "external_library_import", alias.name, _source(node))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module.split(".")[0] in {"requests", "httpx", "aiohttp", "websocket", "web3"}:
            self._emit(self.external_import_points, node, "external_library_import", module, _source(node))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Return(self, node: ast.Return) -> None:
        value = _source(node.value) if node.value is not None else "None"
        function = self.current_function
        if _contains_keyword(function + " " + value, RETURN_RISK_KEYWORDS):
            self._emit(self.return_points, node, "critical_return", function, value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        target = ", ".join(_dotted(item) for item in node.targets)
        self._inspect_assignment(node, target, _source(node.value))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target = _dotted(node.target)
        self._inspect_assignment(node, target, _source(node.value) if node.value is not None else "")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        target = _dotted(node.target)
        self._inspect_assignment(node, target, _source(node))
        self.generic_visit(node)

    def _inspect_assignment(self, node: ast.AST, target: str, detail: str) -> None:
        joined = f"{target} {detail}"
        if _contains_keyword(joined, HIGH_RISK_ASSIGNMENT_KEYWORDS):
            self._emit(self.mutation_points, node, "high_risk_assignment", target, detail)
        if _contains_keyword(joined, MATH_RISK_KEYWORDS) and any(op in detail for op in ["/", "*", "+", "-", "Decimal", "int("]):
            self._emit(self.math_sensitive_points, node, "math_sensitive_assignment", target, detail)

    def visit_Call(self, node: ast.Call) -> None:
        name = _dotted(node.func)
        detail = _source(node)
        for pattern, category in EXTERNAL_IMPORT_PATTERNS.items():
            if pattern in name or pattern in detail:
                self._emit(self.external_import_points, node, category, name, detail)
                break
        for pattern, category in MUTATION_CALL_PATTERNS.items():
            if pattern in name or pattern in detail:
                self._emit(self.mutation_points, node, category, name, detail)
                break
        if any(pattern in name or pattern in detail for pattern in LIVE_RPC_READ_PATTERNS):
            self._emit(self.live_state_points, node, "live_state_read", name, detail)
        if (
            name in {"Decimal", "int", "float"}
            or "to_integral_value" in name
            or "quantize" in name
            or _contains_keyword(name + " " + detail, MATH_RISK_KEYWORDS)
        ):
            self._emit(self.math_sensitive_points, node, "math_sensitive_call", name, detail)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        detail = _source(node)
        if isinstance(node.op, (ast.Div, ast.Mult, ast.Add, ast.Sub, ast.Pow)) and _contains_keyword(detail, MATH_RISK_KEYWORDS):
            self._emit(self.math_sensitive_points, node, f"math_op_{type(node.op).__name__.lower()}", type(node.op).__name__, detail)
        self.generic_visit(node)


def _python_files(roots: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    ignored_parts = {"__pycache__", ".git", ".venv", "venv", "node_modules", "out", "cache"}
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in ignored_parts for part in path.parts):
                continue
            files.append(path)
    return sorted(set(files))


def audit_paths(roots: Iterable[str | Path] | None = None) -> dict[str, Any]:
    root = repo_path()
    resolved_roots = [resolve_repo_relative(item) for item in (roots or ["omega_v5"])]
    files = _python_files(resolved_roots)
    parse_errors: list[dict[str, Any]] = []
    combined: dict[str, list[dict[str, Any]]] = {
        "external_import_points": [],
        "return_points": [],
        "mutation_points": [],
        "math_sensitive_points": [],
        "live_state_points": [],
    }
    by_file: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            parse_errors.append(
                _record(path, root, 0, "parse_error", type(exc).__name__, "<module>", str(exc))
            )
            continue
        visitor = LogicDataVisitor(path, root)
        visitor.visit(tree)
        for key in combined:
            rows = getattr(visitor, key)
            combined[key].extend(rows)
            rel = str(path.relative_to(root)).replace("\\", "/") if path.is_relative_to(root) else str(path)
            by_file[rel][key] += len(rows)

    category_counts: Counter[str] = Counter()
    for key, rows in combined.items():
        category_counts.update(row["category"] for row in rows)

    high_risk_mutations = [
        row
        for row in combined["mutation_points"]
        if row["category"] in {"broadcast_write", "signing_operation", "runtime_control_mutation", "high_risk_assignment"}
    ]
    report = {
        "ok": not parse_errors,
        "schema_version": "omega_v5.logic_data_audit.v1",
        "generated_at": int(time.time()),
        "roots": [str(item) for item in resolved_roots],
        "critical_debugging_areas": CRITICAL_DEBUGGING_AREAS,
        "canonical_route_math": CANONICAL_ROUTE_MATH,
        "summary": {
            "files_scanned": len(files),
            "parse_errors": len(parse_errors),
            "external_import_points": len(combined["external_import_points"]),
            "return_points": len(combined["return_points"]),
            "mutation_points": len(combined["mutation_points"]),
            "high_risk_mutation_points": len(high_risk_mutations),
            "math_sensitive_points": len(combined["math_sensitive_points"]),
            "live_state_points": len(combined["live_state_points"]),
        },
        "category_counts": dict(sorted(category_counts.items())),
        "parse_errors": parse_errors,
        "high_risk_mutation_points": high_risk_mutations[:250],
        "external_import_points": combined["external_import_points"][:500],
        "return_points": combined["return_points"][:500],
        "mutation_points": combined["mutation_points"][:500],
        "math_sensitive_points": combined["math_sensitive_points"][:500],
        "live_state_points": combined["live_state_points"][:500],
        "by_file": {file: dict(counts) for file, counts in sorted(by_file.items())},
        "debugging_directive": {
            "executor_truth_priority": "All raw-positive opportunities must pass exact-call or fork executor truth before live eligibility.",
            "metadata_policy": "Missing metadata is a discoverability blocker, not a reason to invent values.",
            "rounding_policy": "Raw token input conversions must floor unless a specific protocol requires another rule.",
            "gas_policy": "Gas is paid by the user wallet in native POL and converted to USD with live oracle/gas data.",
            "cache_policy": "Redis and JSON reports are acceleration layers; live RPC/exact-call data remains authoritative for execution.",
        },
    }
    return report


def write_report(report: dict[str, Any], path: Path | None = None) -> Path:
    target = path or LOGIC_DATA_AUDIT_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit data import, return, mutation, and math-sensitive points.")
    parser.add_argument("--root", action="append", default=None, help="Repo-relative file or directory to scan. Repeatable.")
    parser.add_argument("--out", default=str(LOGIC_DATA_AUDIT_REPORT_PATH), help="Output JSON report path.")
    args = parser.parse_args(argv)
    report = audit_paths(args.root or ["omega_v5"])
    target = write_report(report, resolve_repo_relative(args.out))
    print(
        "logic_data_audit="
        f"{'PASS' if report['ok'] else 'FAIL'} "
        f"files={report['summary']['files_scanned']} "
        f"imports={report['summary']['external_import_points']} "
        f"returns={report['summary']['return_points']} "
        f"mutations={report['summary']['mutation_points']} "
        f"math={report['summary']['math_sensitive_points']} "
        f"path={target}"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
