"""
APEX_OMEGA Live Executor
Integrates with WebSocket block streaming for real-time arbitrage execution
"""

import os
import sys
import time
import json
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from web3 import Web3
from websockets import connect as ws_connect
from dotenv import load_dotenv
from execution_governance import get_minimum_net_profit_usd, get_governance_service
from execution_logger import get_execution_logger

load_dotenv(Path(__file__).parent / '.env')
logger = logging.getLogger(__name__)

# Import components
from arbitrage_engine import ArbitrageEngine, SpreadOpportunity, get_arbitrage_engine
from institutional_executor import InstitutionalExecutor
from executor_registry import get_active_executor_address, get_rpc_url, get_wss_url

DEFAULT_GAS_UNITS = int(os.getenv('ESTIMATED_GAS_UNITS', '450000'))
DISCOVERY_MIN_REFRESH_SEC = int(os.getenv('DISCOVERY_MIN_REFRESH_SEC', '30'))
OPPORTUNITY_MAX_AGE_SEC = float(os.getenv('OPPORTUNITY_MAX_AGE_SEC', '30'))
OPPORTUNITY_MAX_FUTURE_SKEW_SEC = float(os.getenv('OPPORTUNITY_MAX_FUTURE_SKEW_SEC', '5'))


class ExecutionMode(Enum):
    SIMULATION = "simulation"
    DRY_RUN = "dry_run"
    LIVE = "live"


@dataclass
class ExecutorConfig:
    """Live executor configuration"""
    mode: ExecutionMode = ExecutionMode.SIMULATION
    min_profit_usd: float = get_minimum_net_profit_usd()
    max_position_usd: float = 10000
    max_gas_gwei: float = 100
    slippage_tolerance_pct: float = 0.5
    auto_execute: bool = False
    max_trades_per_day: int = 10
    max_daily_gas_budget_usd: float = 5.0


class LiveExecutor:
    """
    Live arbitrage executor with WebSocket block streaming
    """
    
    def __init__(self, config: ExecutorConfig):
        self.config = config
        self.rpc_url = get_rpc_url('polygon')
        self.wss_url = get_wss_url('polygon')
        matic_price_env = os.getenv('MATIC_PRICE_USD')
        self.matic_price_usd = float(matic_price_env) if matic_price_env else 0.85
        if not matic_price_env:
            logger.warning("MATIC_PRICE_USD not set; using fallback price 0.85")
        self.discovery_refresh_interval_sec = int(os.getenv('DISCOVERY_REFRESH_INTERVAL_SEC', '300'))
        self.discovery_refresh_enabled = os.getenv('DISCOVERY_REFRESH_ENABLED', 'true').lower() == 'true'
        
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.engine = get_arbitrage_engine()
        if not self.w3.is_connected():
            logger.warning("RPC not connected — live execution will not function until RPC is configured")

        # Wallet for signing live transactions
        private_key = os.getenv('PRIVATE_KEY')
        self.wallet = None
        if private_key:
            self.wallet = self.w3.eth.account.from_key(private_key)
            logger.info(f"Wallet loaded: {self.wallet.address}")
        else:
            logger.warning("No PRIVATE_KEY configured — LIVE execution disabled")

        # InstitutionalExecutor wired to the deployed C1 contract
        c1_address = get_active_executor_address('institutional_arbitrage')
        self.inst_executor = None
        if c1_address:
            self.inst_executor = InstitutionalExecutor(self.w3, c1_address)
        else:
            message = (
                "No active institutional_arbitrage executor address configured "
                "(deployment missing, NOT_DEPLOYED, or ZERO_ADDRESS) — "
                "live execution disabled"
            )
            if self.config.mode == ExecutionMode.LIVE:
                logger.error(message)
                raise ValueError(message)
            logger.warning(message)
        
        # State
        self.is_running = False
        self.last_block = 0
        self.executions = []
        self.stats = {
            "blocks_processed": 0,
            "opportunities_found": 0,
            "executions_attempted": 0,
            "executions_successful": 0,
            "total_profit_usd": 0,
            "total_profit_after_gas_usd": 0,
        }
        self._daily_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._trades_today = 0
        self._gas_spent_today_usd = 0.0
        self._discovery_task: Optional[asyncio.Task] = None
        self._cached_gas_price_wei = 0
        self._cached_gas_price_ts = 0.0
        
        logger.info(f"LiveExecutor initialized | Mode: {config.mode.value}")

    def _roll_daily_counters_if_needed(self):
        current_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if current_bucket != self._daily_bucket:
            self._daily_bucket = current_bucket
            self._trades_today = 0
            self._gas_spent_today_usd = 0.0

    def _get_cached_gas_price_wei(self) -> int:
        now = time.time()
        ttl_sec = float(os.getenv('GAS_PRICE_CACHE_TTL_SEC', '15'))
        if self._cached_gas_price_wei > 0 and (now - self._cached_gas_price_ts) <= ttl_sec:
            return self._cached_gas_price_wei
        try:
            self._cached_gas_price_wei = self.w3.eth.gas_price
            self._cached_gas_price_ts = now
        except Exception:
            pass
        return self._cached_gas_price_wei

    def _estimate_gas_cost_usd(self, gas_units: int) -> float:
        try:
            gas_price_wei = self._get_cached_gas_price_wei()
            return (gas_units * gas_price_wei / 1e18) * self.matic_price_usd
        except Exception:
            return 0.0

    def _current_gas_gwei(self) -> float:
        try:
            return self._get_cached_gas_price_wei() / 1e9
        except Exception:
            return 0.0

    def _normalize_opportunity_timestamp(self, timestamp: int) -> float:
        """Normalize opportunity timestamp to epoch seconds."""
        try:
            ts = float(timestamp)
        except (TypeError, ValueError):
            return 0.0

        # Engine-created opportunities use milliseconds, but older integrations may
        # still provide seconds. Treat large epoch values as milliseconds.
        if ts > 10_000_000_000:
            return ts / 1000
        return ts

    def _slippage_gate_details(self, fl) -> Dict[str, Any]:
        leg1 = fl.leg1
        leg2 = fl.leg2
        loan_amount = float(fl.loan_amount_usd or 0)
        total_slippage_usd = float(fl.total_slippage_usd or 0)

        leg_slippages = []
        for label, leg in (("leg1", leg1), ("leg2", leg2)):
            if not leg:
                continue
            amount_in = float(getattr(leg, "amount_in_usd", 0) or 0)
            slippage_usd = float(getattr(leg, "slippage_usd", 0) or 0)
            slippage_pct = (slippage_usd / amount_in) * 100 if amount_in > 0 else 0.0
            leg_slippages.append({
                "leg": label,
                "slippage_usd": slippage_usd,
                "amount_in_usd": amount_in,
                "slippage_pct": slippage_pct,
            })

        if total_slippage_usd <= 0 and leg_slippages:
            total_slippage_usd = sum(item["slippage_usd"] for item in leg_slippages)

        total_slippage_pct = (total_slippage_usd / loan_amount) * 100 if loan_amount > 0 else 0.0
        return {
            "total_slippage_usd": total_slippage_usd,
            "total_slippage_pct": total_slippage_pct,
            "leg_slippages": leg_slippages,
        }

    def _passes_execution_gates(
        self,
        opp: SpreadOpportunity,
        estimated_gas_gwei: Optional[float] = None,
        estimated_gas: Optional[float] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate an opportunity immediately before execution.

        `estimated_gas_gwei` is a gas price expressed in gwei. `estimated_gas`
        is retained as a backward-compatible alias for older callers.

        Returns a `(passes, rejection)` tuple. `rejection` is a structured
        payload suitable for logging and API responses.
        """
        if estimated_gas_gwei is None:
            estimated_gas_gwei = estimated_gas
        elif estimated_gas is not None and estimated_gas != estimated_gas_gwei:
            logger.warning(
                "Conflicting gas price inputs provided to _passes_execution_gates; "
                "using estimated_gas_gwei=%s and ignoring deprecated estimated_gas=%s",
                estimated_gas_gwei,
                estimated_gas,
            )

        # Preserve the existing local variable name for the remainder of this
        # method body, which already treats the value as a gas price in gwei.
        estimated_gas = estimated_gas_gwei
        self._roll_daily_counters_if_needed()
        fl = opp.flash_loan
        now = time.time()
        opp_ts = self._normalize_opportunity_timestamp(getattr(opp, "timestamp", 0))
        age_sec = now - opp_ts if opp_ts > 0 else None

        def rejection(code: str, message: str, **details: Any) -> Tuple[bool, Dict[str, Any]]:
            payload = {
                "status": "rejected",
                "code": code,
                "reason": message,
                "opportunity_id": getattr(opp, "id", None),
                "token_pair": getattr(opp, "token_pair", None),
                "timestamp": int(now),
                "details": details,
            }
            if logger.isEnabledFor(logging.INFO):
                logger.info("Execution gate rejection: %s", json.dumps(payload, default=str))
            return False, payload

        if not fl.leg1 or not fl.leg2:
            return rejection(
                "missing_swap_legs",
                "opportunity must include both leg1 and leg2",
                has_leg1=bool(fl.leg1),
                has_leg2=bool(fl.leg2),
            )

        if opp_ts <= 0:
            return rejection(
                "invalid_timestamp",
                "opportunity timestamp is missing or invalid",
                opportunity_timestamp=getattr(opp, "timestamp", None),
            )

        if age_sec is not None and age_sec > OPPORTUNITY_MAX_AGE_SEC:
            return rejection(
                "stale_opportunity",
                f"opportunity age {age_sec:.2f}s exceeds max {OPPORTUNITY_MAX_AGE_SEC:.2f}s",
                opportunity_timestamp=opp_ts,
                current_timestamp=now,
                age_sec=age_sec,
                max_age_sec=OPPORTUNITY_MAX_AGE_SEC,
            )

        if age_sec is not None and age_sec < -OPPORTUNITY_MAX_FUTURE_SKEW_SEC:
            return rejection(
                "future_opportunity_timestamp",
                f"opportunity timestamp is {-age_sec:.2f}s in the future",
                opportunity_timestamp=opp_ts,
                current_timestamp=now,
                future_skew_sec=-age_sec,
                max_future_skew_sec=OPPORTUNITY_MAX_FUTURE_SKEW_SEC,
            )

        if fl.loan_amount_usd > self.config.max_position_usd:
            return rejection(
                "position_limit_exceeded",
                f"position ${fl.loan_amount_usd:.2f} exceeds max ${self.config.max_position_usd:.2f}",
                loan_amount_usd=fl.loan_amount_usd,
                max_position_usd=self.config.max_position_usd,
            )

        if fl.net_profit_usd < self.config.min_profit_usd:
            return rejection(
                "profit_below_minimum",
                f"net profit ${fl.net_profit_usd:.2f} below min ${self.config.min_profit_usd:.2f}",
                net_profit_usd=fl.net_profit_usd,
                min_profit_usd=self.config.min_profit_usd,
            )

        net_after_gas = fl.net_profit_after_gas_usd
        if net_after_gas < self.config.min_profit_usd:
            return rejection(
                "profit_after_gas_below_minimum",
                f"net after gas ${net_after_gas:.2f} below min ${self.config.min_profit_usd:.2f}",
                net_profit_after_gas_usd=net_after_gas,
                min_profit_usd=self.config.min_profit_usd,
            )

        gas_gwei = float(estimated_gas) if estimated_gas is not None else self._current_gas_gwei()
        if gas_gwei > self.config.max_gas_gwei:
            gas_source = "estimated" if estimated_gas is not None else "current"
            return rejection(
                "gas_price_exceeded",
                f"{gas_source} gas {gas_gwei:.2f} gwei exceeds limit {self.config.max_gas_gwei:.2f}",
                gas_gwei=gas_gwei,
                gas_source=gas_source,
                max_gas_gwei=self.config.max_gas_gwei,
            )

        slippage = self._slippage_gate_details(fl)
        if slippage["total_slippage_pct"] > self.config.slippage_tolerance_pct:
            return rejection(
                "slippage_exceeded",
                (
                    f"total slippage {slippage['total_slippage_pct']:.2f}% exceeds "
                    f"limit {self.config.slippage_tolerance_pct:.2f}%"
                ),
                **slippage,
                slippage_tolerance_pct=self.config.slippage_tolerance_pct,
            )

        for leg_slippage in slippage["leg_slippages"]:
            if leg_slippage["slippage_pct"] > self.config.slippage_tolerance_pct:
                return rejection(
                    "leg_slippage_exceeded",
                    (
                        f"{leg_slippage['leg']} slippage {leg_slippage['slippage_pct']:.2f}% "
                        f"exceeds limit {self.config.slippage_tolerance_pct:.2f}%"
                    ),
                    **leg_slippage,
                    total_slippage_usd=slippage["total_slippage_usd"],
                    total_slippage_pct=slippage["total_slippage_pct"],
                    slippage_tolerance_pct=self.config.slippage_tolerance_pct,
                )

        if self.config.max_trades_per_day > 0 and self._trades_today >= self.config.max_trades_per_day:
            return rejection(
                "daily_trade_cap_reached",
                f"daily trade cap reached ({self._trades_today}/{self.config.max_trades_per_day})",
                trades_today=self._trades_today,
                max_trades_per_day=self.config.max_trades_per_day,
            )

        estimated_gas_cost_usd = self._estimate_gas_cost_usd(fl.gas_units or DEFAULT_GAS_UNITS)
        projected_gas_spend = self._gas_spent_today_usd + estimated_gas_cost_usd
        if self.config.max_daily_gas_budget_usd > 0 and projected_gas_spend > self.config.max_daily_gas_budget_usd:
            return rejection(
                "daily_gas_budget_exceeded",
                (
                    f"daily gas budget exceeded (${projected_gas_spend:.2f} > "
                    f"${self.config.max_daily_gas_budget_usd:.2f})"
                ),
                gas_spent_today_usd=self._gas_spent_today_usd,
                estimated_gas_cost_usd=estimated_gas_cost_usd,
                projected_gas_spend_usd=projected_gas_spend,
                max_daily_gas_budget_usd=self.config.max_daily_gas_budget_usd,
            )

        return True, None

    def _pre_execution_rejection_reason(self, opp: SpreadOpportunity) -> Optional[str]:
        passes, rejection = self._passes_execution_gates(opp)
        return None if passes else rejection["reason"]

    def _ingest_scanned_pool(self, pool):
        from engine import POLYGON_POOLS

        pool_name = pool.name or ""
        default_token0, _, default_token1 = pool_name.partition("/")
        mapped_pair = POLYGON_POOLS.get(pool.name, '') if pool.name else ''
        mapped_token0 = mapped_pair.split('/')[0] if '/' in mapped_pair else ''
        lower_name = pool_name.lower()
        if "quickswap" in lower_name:
            dex_id = 4
        elif "sushi" in lower_name:
            dex_id = 5
        else:
            dex_id = 2

        pool_data = {
            'poolAddress': pool.address,
            'dexId': dex_id,
            'token0': pool.token0 or mapped_token0 or default_token0,
            'token1': pool.token1 or default_token1,
            'spotPrice': (pool.sqrt_price_x96 / (2**96)) ** 2 if pool.sqrt_price_x96 else 0,
            'reserveUsd': max(pool.liquidity / 1000, 0),
            'protocol': 3,
            'fee': pool.fee,
            'liquidity': pool.liquidity,
            'tick': pool.tick,
        }
        self.engine.update_pool(pool_data)

    async def refresh_discovery_once(self):
        """Refresh pool discovery and hydrate arbitrage engine."""
        try:
            from engine import Web3PoolScanner

            scanner = Web3PoolScanner(self.rpc_url)
            if not scanner.is_connected():
                logger.warning("Discovery refresh skipped: scanner RPC not connected")
                return

            pools = await asyncio.to_thread(scanner.scan_all_pools)
            for pool in pools:
                self._ingest_scanned_pool(pool)
            logger.info(f"Discovery refresh complete: {len(pools)} pools ingested")
        except Exception as e:
            logger.error(f"Discovery refresh failed: {e}")

    async def _discovery_refresh_loop(self):
        while self.is_running:
            try:
                await self.refresh_discovery_once()
                await asyncio.sleep(max(DISCOVERY_MIN_REFRESH_SEC, self.discovery_refresh_interval_sec))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Discovery refresh loop error: {e}")
                await asyncio.sleep(DISCOVERY_MIN_REFRESH_SEC)

    def _start_discovery_refresh_if_needed(self):
        if self.discovery_refresh_enabled and self._discovery_task is None:
            self._discovery_task = asyncio.create_task(self._discovery_refresh_loop())
    
    async def process_block(self, block_number: int):
        """Process a new block - scan for opportunities"""
        self.last_block = block_number
        self.stats["blocks_processed"] += 1
        
        # Scan for spreads
        spreads = self.engine.scan_for_spreads(self.config.max_position_usd)
        
        # Filter executable opportunities
        executable = [s for s in spreads if s.flash_loan.is_executable]
        
        if executable:
            self.stats["opportunities_found"] += len(executable)
            
            for opp in executable[:3]:  # Process top 3
                logger.info(
                    f"Block {block_number} | Opportunity: {opp.token_pair} | "
                    f"Profit: ${opp.flash_loan.net_profit_usd:.2f} | "
                    f"ROI: {opp.flash_loan.roi_percent:.4f}%"
                )
                
                if self.config.auto_execute:
                    passes, rejection = self._passes_execution_gates(opp)
                    if not passes:
                        self.executions.append({
                            "timestamp": int(time.time()),
                            "opportunity": opp.to_dict(),
                            "result": rejection,
                        })
                        continue

                    await self.execute_opportunity(opp)
    
    async def reconcile_pending_submissions(self, require_connected: bool = False) -> Dict[str, int]:
        """Reconcile previously submitted transactions before new live submissions."""
        if not self.w3.is_connected():
            message = "Execution state reconciliation skipped: RPC not connected"
            if require_connected:
                raise RuntimeError(message)
            logger.warning(message)
            return {"checked": 0, "confirmed": 0, "reverted": 0, "expired": 0, "pending": 0}

        expiry_env = int(os.getenv("EXECUTION_SUBMISSION_EXPIRY_SECONDS", "0"))
        max_age_seconds = expiry_env if expiry_env > 0 else None
        summary = await self.execution_logger.reconcile_submitted_transactions(
            self.w3,
            max_age_seconds=max_age_seconds,
        )
        logger.info(f"Execution state reconciliation complete: {summary}")
        return summary

    async def execute_opportunity(self, opp: SpreadOpportunity) -> Dict[str, Any]:
        """Execute an arbitrage opportunity"""
        passes, rejection = self._passes_execution_gates(opp)
        if not passes:
            self.executions.append({
                "timestamp": int(time.time()),
                "opportunity": opp.to_dict(),
                "result": rejection,
            })
            return rejection

        self.stats["executions_attempted"] += 1
        
        fl = opp.flash_loan
        opportunity_payload = opp.to_dict()
        expected_profit = fl.net_profit_after_gas_usd or fl.net_profit_usd
        default_gas_estimate = fl.gas_units or DEFAULT_GAS_UNITS
        
        # Initialize result to prevent UnboundLocalError
        result: Dict[str, Any] = {"status": "unknown", "execution_id": execution_id}
        tx_hash_hex: Optional[str] = None

        if self.config.mode == ExecutionMode.SIMULATION:
            # Simulation mode - log but don't execute and do not fabricate a tx hash.
            result = {
                "status": "simulated",
                "opportunity": opp.id,
                "profit_usd": fl.net_profit_usd,
                "timestamp": int(time.time()),
                "execution_id": execution_id,
            }
            await self.execution_logger.record_execution_state(
                opportunity_id=opp.id,
                payload=opportunity_payload,
                status="simulated",
                chain_id=self._safe_chain_id(),
                gas_estimate=default_gas_estimate,
                expected_profit_usd=expected_profit,
                metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
            )
            logger.info(f"[SIMULATION] {opp.token_pair}: ${fl.net_profit_usd:.2f}")

        elif self.config.mode == ExecutionMode.DRY_RUN:
            # Dry run - build transaction payload but don't broadcast and do not fabricate a tx hash.
            if self.wallet:
                build_result = self.inst_executor.build_execution_from_spread(
                    spread=opportunity_snapshot,
                    from_address=self.wallet.address,
                    use_balancer=True,
                    dry_run=True,
                )
                result = {"status": "dry_run", **build_result}
                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=build_result.get("payload", opportunity_payload),
                    status="quoted",
                    chain_id=self._safe_chain_id(),
                    gas_estimate=build_result.get("estimated_gas"),
                    expected_profit_usd=expected_profit,
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                )
            else:
                result = {"status": "dry_run", "message": "No PRIVATE_KEY configured"}
                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=opportunity_payload,
                    status="expired",
                    chain_id=self._safe_chain_id(),
                    gas_estimate=default_gas_estimate,
                    expected_profit_usd=expected_profit,
                    failure_detail="No PRIVATE_KEY configured",
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                )
            logger.info(f"[DRY RUN] {opp.token_pair}: estimated_gas={result.get('estimated_gas', 'N/A')}")

        elif self.config.mode == ExecutionMode.LIVE:
            # Live execution via InstitutionalExecutor → C1 contract
            if not self.wallet:
                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=opportunity_payload,
                    status="expired",
                    chain_id=self._safe_chain_id(),
                    gas_estimate=default_gas_estimate,
                    expected_profit_usd=expected_profit,
                    failure_detail="No PRIVATE_KEY configured",
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                )
                return {"status": "error", "message": "No PRIVATE_KEY configured"}

            try:
                await self.reconcile_pending_submissions(require_connected=True)
            except Exception as e:
                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=opportunity_payload,
                    status="expired",
                    chain_id=self._safe_chain_id(),
                    gas_estimate=default_gas_estimate,
                    expected_profit_usd=expected_profit,
                    failure_detail=str(e),
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                )
                return {"status": "error", "message": str(e)}

            blocking = await self.execution_logger.find_blocking_execution(opportunity_id=opp.id)
            if blocking and blocking.get("status") == "submitted":
                return {
                    "status": "blocked",
                    "reason": "existing submitted execution for opportunity",
                    "execution_state": blocking,
                }
            
            build_result: Dict[str, Any] = {}
            tx: Dict[str, Any] = {}
            tx_hash_hex: Optional[str] = None
            chain_id = self._safe_chain_id()
            nonce: Optional[int] = None

            try:
                build_result = self.inst_executor.build_execution_from_spread(
                    spread=opportunity_snapshot,
                    from_address=self.wallet.address,
                    use_balancer=True,
                    dry_run=False,
                )
                await self._append_lifecycle_event(
                    execution_id,
                    stage="transaction_built",
                    status="completed",
                    details={k: v for k, v in build_result.items() if k != "tx"},
                )

                tx = build_result.get("tx")
                if not tx:
                    await self.execution_logger.record_execution_state(
                        opportunity_id=opp.id,
                        payload=build_result.get("payload", opportunity_payload),
                        status="expired",
                        chain_id=self._safe_chain_id(),
                        gas_estimate=build_result.get("estimated_gas"),
                        expected_profit_usd=expected_profit,
                        failure_detail="Failed to build transaction",
                        metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                    )
                    return {"status": "error", "message": "Failed to build transaction"}

                chain_id = int(tx.get("chainId") or self._safe_chain_id() or 0)
                nonce = tx.get("nonce")
                blocking_nonce = await self.execution_logger.find_blocking_execution(
                    opportunity_id=opp.id,
                    chain_id=chain_id,
                    nonce=nonce,
                )
                if blocking_nonce and blocking_nonce.get("status") == "submitted":
                    return {
                        "status": "blocked",
                        "reason": "existing submitted execution for opportunity or nonce",
                        "execution_state": blocking_nonce,
                    }

                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=build_result.get("payload", opportunity_payload),
                    status="quoted",
                    chain_id=chain_id,
                    nonce=nonce,
                    gas_estimate=build_result.get("estimated_gas") or tx.get("gas"),
                    expected_profit_usd=expected_profit,
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                )
                
                # Sign and broadcast
                signed = self.w3.eth.account.sign_transaction(tx, self.wallet.key)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hash_hex = tx_hash.hex()
                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=build_result.get("payload", opportunity_payload),
                    status="submitted",
                    chain_id=chain_id,
                    nonce=nonce,
                    tx_hash=tx_hash_hex,
                    gas_estimate=build_result.get("estimated_gas") or tx.get("gas"),
                    expected_profit_usd=expected_profit,
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                )
                logger.info(f"[LIVE] {opp.token_pair}: tx submitted {tx_hash_hex}")
                
                # Wait for on-chain confirmation
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                receipt_status = "executed" if receipt["status"] == 1 else "failed"

                result = {
                    "status": "executed" if receipt["status"] == 1 else "failed",
                    "tx_hash": tx_hash_hex,
                    "gas_used": receipt["gasUsed"],
                    "block": receipt["blockNumber"],
                    "execution_id": execution_id,
                }
                
                state_status = "confirmed" if result["status"] == "executed" else "reverted"
                await self.execution_logger.record_execution_state(
                    opportunity_id=opp.id,
                    payload=build_result.get("payload", opportunity_payload),
                    status=state_status,
                    chain_id=chain_id,
                    nonce=nonce,
                    tx_hash=tx_hash_hex,
                    gas_estimate=build_result.get("estimated_gas") or tx.get("gas"),
                    gas_used=receipt.get("gasUsed"),
                    expected_profit_usd=expected_profit,
                    realized_profit_usd=expected_profit if result["status"] == "executed" else None,
                    failure_detail=None if result["status"] == "executed" else "Transaction receipt status=0",
                    revert_reason=None if result["status"] == "executed" else "Transaction receipt status=0",
                    metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair, "block_number": receipt.get("blockNumber")},
                )

                if result["status"] == "executed":
                    self.stats["executions_successful"] += 1
                    self.stats["total_profit_usd"] += fl.net_profit_usd
                    net_after_gas = fl.net_profit_after_gas_usd
                    self.stats["total_profit_after_gas_usd"] += net_after_gas
                    self._trades_today += 1
                    gas_used = receipt.get("gasUsed", 0)
                    effective_gas_price = receipt.get("effectiveGasPrice", tx.get("gasPrice", 0))
                    self._gas_spent_today_usd += (gas_used * effective_gas_price / 1e18) * self.matic_price_usd
                    try:
                        get_governance_service().record_tx_metric(
                            {
                                "opportunity_id": opp.id,
                                "status": "executed",
                                "tx_hash": result.get("tx_hash"),
                                "net_profit_after_gas_usd": net_after_gas,
                                "gas_used": gas_used,
                            }
                        )
                    except Exception:
                        pass

                logger.info(f"[LIVE] {opp.token_pair}: {result}")

            except Exception as e:
                result = {"status": "error", "message": str(e)}
                if tx_hash_hex:
                    await self.execution_logger.record_execution_state(
                        opportunity_id=opp.id,
                        payload=build_result.get("payload", opportunity_payload),
                        status="submitted",
                        chain_id=chain_id,
                        nonce=nonce,
                        tx_hash=tx_hash_hex,
                        gas_estimate=build_result.get("estimated_gas") or tx.get("gas") or default_gas_estimate,
                        expected_profit_usd=expected_profit,
                        failure_detail=f"Receipt reconciliation pending after error: {e}",
                        metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                    )
                else:
                    await self.execution_logger.record_execution_state(
                        opportunity_id=opp.id,
                        payload=opportunity_payload,
                        status="expired",
                        chain_id=chain_id,
                        gas_estimate=default_gas_estimate,
                        expected_profit_usd=expected_profit,
                        failure_detail=str(e),
                        metadata={"mode": self.config.mode.value, "token_pair": opp.token_pair},
                    )
                logger.error(f"Execution failed: {e}")

        else:
            result = {"status": "unknown_mode", "execution_id": execution_id}
            await self._append_lifecycle_event(
                execution_id,
                stage="mode_check",
                status="error",
                details={"mode": self.config.mode.value},
            )

        success = result.get("status") in {"simulated", "dry_run", "executed"}
        await self._complete_lifecycle(execution_id, success=success, result=result, tx_hash=tx_hash_hex)

        self.executions.append({
            "timestamp": int(time.time()),
            "execution_id": execution_id,
            "opportunity": opportunity_snapshot,
            "result": result,
        })

        return result
    
    def _safe_chain_id(self) -> Optional[int]:
        try:
            return int(self.w3.eth.chain_id)
        except Exception:
            return 137

    async def start_block_stream(self):
        """Start WebSocket block streaming"""
        await self.reconcile_pending_submissions()
        self.is_running = True
        self._start_discovery_refresh_if_needed()

        if not self.wss_url or 'YOUR_API_KEY' in self.wss_url:
            logger.warning("WSS not configured - using polling mode")
            await self._polling_mode()
            return
        
        logger.info(f"Starting block stream: {self.wss_url[:50]}...")
        
        while self.is_running:
            try:
                async with ws_connect(self.wss_url) as ws:
                    # Subscribe to new blocks
                    subscribe_msg = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"]
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    
                    response = await ws.recv()
                    logger.info(f"Subscribed to newHeads: {response[:100]}")
                    
                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)
                            
                            if "params" in data and "result" in data["params"]:
                                block = data["params"]["result"]
                                block_number = int(block["number"], 16)
                                await self.process_block(block_number)
                                
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            await ws.ping()
                            
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.is_running:
                    await asyncio.sleep(5)  # Reconnect delay
    
    async def _polling_mode(self):
        """Fallback polling mode when WSS not available"""
        self._start_discovery_refresh_if_needed()
        logger.info("Starting in polling mode...")
        
        while self.is_running:
            try:
                block_number = self.w3.eth.block_number
                if block_number > self.last_block:
                    await self.process_block(block_number)
                
                await asyncio.sleep(2)  # Poll every 2 seconds
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)
    
    def stop(self):
        """Stop the executor"""
        self.is_running = False
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
            self._discovery_task = None
        logger.info("LiveExecutor stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        return {
            "mode": self.config.mode.value,
            "isRunning": self.is_running,
            "lastBlock": self.last_block,
            "dailyDate": self._daily_bucket,
            "tradesToday": self._trades_today,
            "gasSpentTodayUsd": self._gas_spent_today_usd,
            "stats": self.stats,
            "recentExecutions": self.executions[-10:],  # Last 10
        }


# Global executor instance
_executor: Optional[LiveExecutor] = None
_executor_task: Optional[asyncio.Task] = None


def get_live_executor() -> LiveExecutor:
    """Get or create live executor"""
    global _executor
    if _executor is None:
        # Determine execution mode from environment
        live_execution = os.getenv('LIVE_EXECUTION', 'false').lower() == 'true'
        shadow_mode = os.getenv('SHADOW_MODE', 'true').lower() == 'true'
        
        if live_execution and not shadow_mode:
            mode = ExecutionMode.LIVE
        elif live_execution and shadow_mode:
            mode = ExecutionMode.DRY_RUN
        else:
            mode = ExecutionMode.SIMULATION
        
        config = ExecutorConfig(
            mode=mode,
            min_profit_usd=max(
                float(os.getenv('MIN_NET_PROFIT_USD', get_minimum_net_profit_usd())),
                get_minimum_net_profit_usd()
            ),
            max_position_usd=float(os.getenv('MAX_POSITION_USD', 100000)),
            max_gas_gwei=float(os.getenv('MAX_GAS_PRICE_GWEI', 150)),
            slippage_tolerance_pct=float(os.getenv('MAX_SLIPPAGE_TOLERANCE', 0.01)) * 100,
            auto_execute=os.getenv('AUTO_EXECUTE', 'true').lower() == 'true',
            max_trades_per_day=int(os.getenv('MAX_TRADES_PER_DAY', '10')),
            max_daily_gas_budget_usd=float(os.getenv('MAX_DAILY_GAS_BUDGET_USD', '5.0')),
        )
        _executor = LiveExecutor(config)
        logger.info(f"✅ LiveExecutor initialized | Mode: {mode.value} | Min Profit: ${config.min_profit_usd}")
    return _executor


def start_live_executor():
    """Start the live executor in background"""
    global _executor_task
    
    executor = get_live_executor()
    if executor.is_running:
        logger.info("LiveExecutor already running")
        return
    
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(executor.start_block_stream())
    
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    logger.info("LiveExecutor started in background thread")


async def initialize_arbitrage_system():
    """Initialize the full arbitrage system"""
    logger.info("Initializing APEX_OMEGA Arbitrage System...")
    
    # Get engine instance
    engine = get_arbitrage_engine()
    
    # Load initial pool data from scanner
    try:
        from engine import Web3PoolScanner, POLYGON_POOLS
        scanner = Web3PoolScanner(
            os.getenv('POLYGON_RPC_URL')
            or os.getenv('ALCHEMY_HTTP_1')
            or os.getenv('PRIVATE_RPC_URL')
            or ''
        )
        
        if scanner.is_connected():
            pools = scanner.scan_all_pools()
            for pool in pools:
                # Convert to pool update format
                pool_data = {
                    'poolAddress': pool.address,
                    'dexId': 2,  # Uniswap V3
                    'token0': pool.token0 or POLYGON_POOLS.get(pool.name, '').split('/')[0] if pool.name else '',
                    'token1': pool.token1 or '',
                    'spotPrice': (pool.sqrt_price_x96 / (2**96)) ** 2 if pool.sqrt_price_x96 else 0,
                    'reserveUsd': pool.liquidity / 1000,  # Approximate
                    'protocol': 3,  # V3
                    'fee': pool.fee,
                    'liquidity': pool.liquidity,
                    'tick': pool.tick,
                }
                engine.update_pool(pool_data)
            
            logger.info(f"Loaded {len(engine.pools)} pools")
    except Exception as e:
        logger.error(f"Failed to load initial pools: {e}")
    
    logger.info("Arbitrage system initialized")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )
    
    print("=" * 60)
    print("APEX_OMEGA LIVE EXECUTOR")
    print("=" * 60)
    
    # Run initialization and executor
    async def main():
        await initialize_arbitrage_system()
        executor = get_live_executor()
        await executor.start_block_stream()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested")
