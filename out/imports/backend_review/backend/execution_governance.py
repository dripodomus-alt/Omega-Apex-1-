"""
Performance Audit & Execution Governance
Unified policy, metrics, activation pipeline, audit runner, and test orchestration.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MINIMUM_NET_PROFIT_USD = 5.0


def get_minimum_net_profit_usd() -> float:
    """Single source of truth for execution minimum net profit policy."""
    return MINIMUM_NET_PROFIT_USD


@dataclass
class OpportunityDecision:
    opportunity_id: str
    stage: str
    accepted: bool
    net_profit_after_costs_usd: float
    minimum_required_usd: float
    reason: str
    timestamp: str
    metadata: Dict[str, Any]


class GovernanceService:
    def __init__(self):
        self._lock = threading.Lock()
        self._decisions: List[OpportunityDecision] = []
        self._latency_samples_ms: List[float] = []
        self._tx_metrics: List[Dict[str, Any]] = []
        self._run_state: Dict[str, Any] = {
            "active": False,
            "run_id": None,
            "mode": None,
            "started_at": None,
            "profile": {},
            "iterations": 0,
            "status": "idle",
        }
        self._test_state: Dict[str, Any] = {
            "active": False,
            "job_id": None,
            "kind": None,
            "component": None,
            "scheduled_interval_sec": 0,
            "runs": [],
            "status": "idle",
        }
        self._run_thread: Optional[threading.Thread] = None
        self._test_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._test_stop_event = threading.Event()
        self.history_path = Path(__file__).parent / "data" / "performance_audit_history.json"
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._persisted_history = self._load_history()

    def _load_history(self) -> List[Dict[str, Any]]:
        try:
            if self.history_path.exists():
                with open(self.history_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
        return []

    def _save_history(self) -> None:
        try:
            with open(self.history_path, "w", encoding="utf-8") as fh:
                json.dump(self._persisted_history[-500:], fh, indent=2)
        except Exception:
            pass

    def evaluate_activation(
        self,
        *,
        opportunity_id: str,
        stage: str,
        net_profit_after_costs_usd: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OpportunityDecision:
        threshold = get_minimum_net_profit_usd()
        accepted = net_profit_after_costs_usd >= threshold
        reason = (
            "accepted"
            if accepted
            else f"net after costs ${net_profit_after_costs_usd:.2f} below ${threshold:.2f}"
        )
        decision = OpportunityDecision(
            opportunity_id=opportunity_id,
            stage=stage,
            accepted=accepted,
            net_profit_after_costs_usd=float(net_profit_after_costs_usd),
            minimum_required_usd=threshold,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        with self._lock:
            self._decisions.append(decision)
            if len(self._decisions) > 5000:
                self._decisions = self._decisions[-5000:]
        return decision

    def record_latency_ms(self, value_ms: float) -> None:
        with self._lock:
            self._latency_samples_ms.append(float(value_ms))
            if len(self._latency_samples_ms) > 5000:
                self._latency_samples_ms = self._latency_samples_ms[-5000:]

    def record_tx_metric(self, metric: Dict[str, Any]) -> None:
        with self._lock:
            self._tx_metrics.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **metric,
                }
            )
            if len(self._tx_metrics) > 2000:
                self._tx_metrics = self._tx_metrics[-2000:]

    def _snapshot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            total_decisions = len(self._decisions)
            accepted = sum(1 for d in self._decisions if d.accepted)
            rejected = total_decisions - accepted
            avg_latency = (
                sum(self._latency_samples_ms) / len(self._latency_samples_ms)
                if self._latency_samples_ms
                else 0.0
            )
            p95_latency = 0.0
            if self._latency_samples_ms:
                ordered = sorted(self._latency_samples_ms)
                p95_index = max(0, int(len(ordered) * 0.95) - 1)
                p95_latency = ordered[p95_index]
            return {
                "policy": {
                    "minimum_net_profit_usd": get_minimum_net_profit_usd(),
                    "description": "Reject only when net profit after all costs is below minimum threshold.",
                },
                "system": {
                    "decisions_total": total_decisions,
                    "accepted": accepted,
                    "rejected": rejected,
                    "acceptance_rate_pct": (accepted / total_decisions * 100.0) if total_decisions else 0.0,
                },
                "latency": {
                    "samples": len(self._latency_samples_ms),
                    "avg_ms": avg_latency,
                    "p95_ms": p95_latency,
                },
                "recent_decisions": [asdict(d) for d in self._decisions[-50:]],
                "recent_txs": self._tx_metrics[-50:],
                "audit_run": dict(self._run_state),
                "test_orchestration": dict(self._test_state),
            }

    def get_metrics(self) -> Dict[str, Any]:
        return self._snapshot_metrics()

    def start_audit_run(self, mode: str = "dry_run", profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            if self._run_state["active"]:
                return {"status": "already_running", "run": dict(self._run_state)}
            run_id = str(uuid.uuid4())
            self._run_state = {
                "active": True,
                "run_id": run_id,
                "mode": mode,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "profile": profile or {},
                "iterations": 0,
                "status": "running",
            }
        self._stop_event.clear()
        self._run_thread = threading.Thread(target=self._audit_loop, daemon=True)
        self._run_thread.start()
        return {"status": "started", "run": dict(self._run_state)}

    def _audit_loop(self):
        while not self._stop_event.is_set():
            t0 = time.perf_counter()
            time.sleep(0.01)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.record_latency_ms(latency_ms)
            with self._lock:
                if not self._run_state["active"]:
                    break
                self._run_state["iterations"] += 1
                interval = int(self._run_state.get("profile", {}).get("interval_sec", 2))
            self._persisted_history.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "kind": "audit_sample",
                    "run_id": self._run_state.get("run_id"),
                    "mode": self._run_state.get("mode"),
                    "latency_ms": latency_ms,
                    "metrics": self._snapshot_metrics()["system"],
                }
            )
            self._save_history()
            time.sleep(max(1, interval))

    def stop_audit_run(self) -> Dict[str, Any]:
        with self._lock:
            if not self._run_state["active"]:
                return {"status": "not_running"}
            self._run_state["active"] = False
            self._run_state["status"] = "stopped"
            self._run_state["stopped_at"] = datetime.now(timezone.utc).isoformat()
            snapshot = dict(self._run_state)
        self._stop_event.set()
        return {"status": "stopped", "run": snapshot}

    def start_test_job(
        self,
        *,
        kind: str,
        component: Optional[str] = None,
        scheduled_interval_sec: int = 0,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._test_state["active"]:
                return {"status": "already_running", "job": dict(self._test_state)}
            job_id = str(uuid.uuid4())
            self._test_state = {
                "active": True,
                "job_id": job_id,
                "kind": kind,
                "component": component,
                "scheduled_interval_sec": int(scheduled_interval_sec or 0),
                "runs": [],
                "status": "running",
            }
        self._test_stop_event.clear()
        self._test_thread = threading.Thread(target=self._test_loop, daemon=True)
        self._test_thread.start()
        return {"status": "started", "job": dict(self._test_state)}

    def _resolve_test_command(self, kind: str, component: Optional[str]) -> List[str]:
        repo_root = Path(__file__).resolve().parents[1]
        if kind == "full_suite":
            return ["python", "-m", "pytest", "backend/tests", "-q"]
        if kind == "component":
            target = component or "backend/tests/test_settings_api.py"
            safe = shlex.split(target) if isinstance(target, str) else [str(target)]
            return ["python", "-m", "pytest", *safe, "-q"]
        if kind == "latency_probe":
            return ["python", "-c", "import time; t=time.perf_counter(); time.sleep(0.02); print((time.perf_counter()-t)*1000)"]
        return ["python", "-m", "pytest", "backend/tests/test_settings_api.py", "-q"]

    def _execute_command(self, cmd: List[str]) -> Dict[str, Any]:
        repo_root = Path(__file__).resolve().parents[1]
        started = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=int(os.getenv("AUDIT_TEST_TIMEOUT_SEC", "600")),
        )
        elapsed_ms = (time.time() - started) * 1000.0
        return {
            "command": cmd,
            "return_code": proc.returncode,
            "elapsed_ms": elapsed_ms,
            "stdout_tail": proc.stdout[-3000:],
            "stderr_tail": proc.stderr[-3000:],
            "success": proc.returncode == 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _test_loop(self):
        while not self._test_stop_event.is_set():
            with self._lock:
                if not self._test_state["active"]:
                    break
                kind = self._test_state["kind"]
                component = self._test_state["component"]
                interval = int(self._test_state["scheduled_interval_sec"] or 0)
            cmd = self._resolve_test_command(kind, component)
            result = self._execute_command(cmd)
            self.record_latency_ms(result["elapsed_ms"])
            with self._lock:
                self._test_state["runs"].append(result)
                self._test_state["runs"] = self._test_state["runs"][-30:]
            self._persisted_history.append(
                {
                    "timestamp": result["timestamp"],
                    "kind": "test_run",
                    "job_id": self._test_state.get("job_id"),
                    "result": result,
                }
            )
            self._save_history()
            if interval <= 0:
                break
            time.sleep(max(1, interval))
        with self._lock:
            self._test_state["active"] = False
            self._test_state["status"] = "stopped"

    def stop_test_job(self) -> Dict[str, Any]:
        with self._lock:
            if not self._test_state["active"]:
                return {"status": "not_running"}
            snapshot = dict(self._test_state)
            self._test_state["active"] = False
            self._test_state["status"] = "stopping"
        self._test_stop_event.set()
        return {"status": "stopping", "job": snapshot}

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._persisted_history[-max(1, int(limit)) :]


_governance_service: Optional[GovernanceService] = None


def get_governance_service() -> GovernanceService:
    global _governance_service
    if _governance_service is None:
        _governance_service = GovernanceService()
    return _governance_service
