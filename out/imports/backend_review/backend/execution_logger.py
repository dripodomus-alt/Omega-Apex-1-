"""
APEX_OMEGA Execution Logger
Logs execution results for ML model retraining

Records:
- Trade amount
- Pool liquidity
- Volatility metrics
- Actual slippage observed
- Profit/loss
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
import os
import pandas as pd
import uuid

logger = logging.getLogger(__name__)

EXECUTION_STATUSES = {"quoted", "simulated", "submitted", "confirmed", "reverted", "expired"}
RECEIPT_PENDING_STATUSES = {"submitted"}
TERMINAL_EXECUTION_STATUSES = {"confirmed", "reverted", "expired"}


class ExecutionLogger:
    """
    Logs all execution results to MongoDB for ML retraining.
    
    Collection: execution_history
    
    Schema:
        {
            'timestamp': datetime,
            'strategy': 'arbitrage' | 'liquidation',
            'trade_amount_usd': float,
            'pool_liquidity_usd': float,
            'pool_utilization': float,
            'volatility_1h': float,
            'volatility_24h': float,
            'gas_price_gwei': float,
            'spread_bps': float,
            'actual_slippage': float,  # Key target for ML
            'profit_usd': float,
            'gas_cost_usd': float,
            'net_profit_usd': float,
            'tx_hash': str
        }
    """
    
    def __init__(self):
        mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        db_name = os.environ.get('DB_NAME', 'apex_omega')
        
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
        self.collection = self.db['execution_history']
        self.lifecycle_collection = self.db['execution_lifecycle']
        self.state_collection = self.db['execution_state']
        self._indexes_ready = False
        
        self.retraining_threshold = 100  # Retrain ML after 100 executions
        self._lifecycle_indexes_ready = False
        
        logger.info("📊 Execution Logger initialized")
    

    async def _ensure_lifecycle_indexes(self) -> None:
        """Create lifecycle indexes used by execution idempotency checks."""
        if self._lifecycle_indexes_ready:
            return

        await self.lifecycle_collection.create_index("execution_id", unique=True)
        await self.lifecycle_collection.create_index(
            "idempotency_key",
            unique=True,
            sparse=True
        )

        # Align the database uniqueness rule with reserve_execution_submission():
        # only one active lifecycle record may exist for a given opportunity_id,
        # but terminal states such as "failed" must allow a later retry record.
        opportunity_index_name = "uniq_active_opportunity_id"
        index_info = await self.lifecycle_collection.index_information()
        legacy_index = index_info.get("opportunity_id_1")
        if (
            legacy_index
            and legacy_index.get("unique")
            and "partialFilterExpression" not in legacy_index
        ):
            await self.lifecycle_collection.drop_index("opportunity_id_1")

        await self.lifecycle_collection.create_index(
            "opportunity_id",
            name=opportunity_index_name,
            unique=True,
            partialFilterExpression={
                "opportunity_id": {"$exists": True},
                "status": {"$in": ["pending", "submitted", "executed"]}
            }
        )
        await self.lifecycle_collection.create_index("tx_hash")
        self._lifecycle_indexes_ready = True

    async def reserve_execution_submission(
        self,
        idempotency_key: str,
        opportunity_id: str,
        quote: Dict,
        tx: Dict,
        strategy: str = "arbitrage"
    ) -> Dict:
        """
        Atomically reserve an opportunity for execution submission.

        The idempotency key protects request retries, while the opportunity ID
        prevents submitting the same opportunity under a different key.
        """
        await self._ensure_lifecycle_indexes()

        active_statuses = ["pending", "submitted", "executed"]
        existing = await self.lifecycle_collection.find_one({
            "$or": [
                {"idempotency_key": idempotency_key},
                {"opportunity_id": opportunity_id, "status": {"$in": active_statuses}}
            ]
        })
        if existing:
            return {
                "reserved": False,
                "duplicate": True,
                "record": self._serialize_mongo_doc(existing)
            }

        now = datetime.utcnow()
        execution_id = f"exec-{uuid.uuid4().hex}"
        doc = {
            "execution_id": execution_id,
            "strategy": strategy,
            "status": "pending",
            "idempotency_key": idempotency_key,
            "opportunity_id": opportunity_id,
            "metadata": {
                "quote": quote,
                "tx": tx
            },
            "tx_hash": None,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "lifecycle": [
                {
                    "stage": "submission_reserved",
                    "status": "pending",
                    "timestamp": now,
                    "details": {
                        "idempotency_key": idempotency_key,
                        "opportunity_id": opportunity_id
                    }
                }
            ]
        }

        try:
            await self.lifecycle_collection.insert_one(doc)
        except DuplicateKeyError:
            existing = await self.lifecycle_collection.find_one({
                "$or": [
                    {"idempotency_key": idempotency_key},
                    {"opportunity_id": opportunity_id}
                ]
            })
            return {
                "reserved": False,
                "duplicate": True,
                "record": self._serialize_mongo_doc(existing) if existing else None
            }

        return {
            "reserved": True,
            "duplicate": False,
            "record": self._serialize_mongo_doc(doc)
        }

    async def update_execution_state(
        self,
        execution_id: str,
        status: str,
        stage: str,
        details: Optional[Dict] = None,
        tx_hash: Optional[str] = None,
        finished: bool = False
    ) -> None:
        """Append a state transition to an execution lifecycle record."""
        await self._ensure_lifecycle_indexes()
        now = datetime.utcnow()
        event = {
            "stage": stage,
            "status": status,
            "timestamp": now,
            "details": details or {}
        }
        if tx_hash:
            event["tx_hash"] = tx_hash

        set_doc = {
            "status": status,
            "updated_at": now
        }
        if tx_hash:
            set_doc["tx_hash"] = tx_hash
        if finished:
            set_doc["finished_at"] = now

        result = await self.lifecycle_collection.update_one(
            {"execution_id": execution_id},
            {"$set": set_doc, "$push": {"lifecycle": event}}
        )
        if result.matched_count == 0:
            logger.error(
                "Failed to update execution state: no lifecycle record found for execution_id=%s",
                execution_id
            )
            raise ValueError(
                f"No lifecycle record found for execution_id={execution_id}"
            )

    async def get_execution_by_tx_hash(self, tx_hash: str) -> Optional[Dict]:
        """Return a lifecycle record associated with a transaction hash."""
        await self._ensure_lifecycle_indexes()
        record = await self.lifecycle_collection.find_one({"tx_hash": tx_hash})
        if not record:
            return None
        return self._serialize_mongo_doc(record)

    async def log_execution(
        self,
        strategy: str,
        trade_amount_usd: float,
        pool_liquidity_usd: float,
        volatility_1h: float,
        volatility_24h: float,
        gas_price_gwei: float,
        spread_bps: float,
        actual_slippage: float,
        profit_usd: float,
        gas_cost_usd: float,
        tx_hash: Optional[str] = None
    ) -> Dict:
        """
        Log a single execution result.
        
        Returns execution count (for retraining trigger).
        """
        pool_utilization = trade_amount_usd / pool_liquidity_usd if pool_liquidity_usd > 0 else 0
        net_profit_usd = profit_usd - gas_cost_usd
        
        execution_record = {
            'timestamp': datetime.now(),
            'strategy': strategy,
            'trade_amount_usd': trade_amount_usd,
            'pool_liquidity_usd': pool_liquidity_usd,
            'pool_utilization': pool_utilization,
            'volatility_1h': volatility_1h,
            'volatility_24h': volatility_24h,
            'gas_price_gwei': gas_price_gwei,
            'spread_bps': spread_bps,
            'actual_slippage': actual_slippage,
            'profit_usd': profit_usd,
            'gas_cost_usd': gas_cost_usd,
            'net_profit_usd': net_profit_usd,
            'tx_hash': tx_hash
        }
        
        # Insert into MongoDB
        await self.collection.insert_one(execution_record)
        
        # Get total execution count
        execution_count = await self.collection.count_documents({})
        
        logger.info(f"📝 Execution logged: {strategy} | ${profit_usd:.2f} profit | Slippage: {actual_slippage*100:.3f}%")
        logger.info(f"   Total executions recorded: {execution_count}")
        
        # Check if retraining needed
        should_retrain = (execution_count % self.retraining_threshold == 0) and execution_count > 0
        
        return {
            'logged': True,
            'execution_count': execution_count,
            'should_retrain': should_retrain
        }
    
    async def get_training_data(self, limit: int = None) -> pd.DataFrame:
        """
        Retrieve execution history as pandas DataFrame for ML retraining.
        """
        query = {}
        cursor = self.collection.find(query, {"_id": 0})
        
        if limit:
            cursor = cursor.limit(limit)
        
        executions = await cursor.to_list(length=None)
        
        if not executions:
            logger.warning("⚠️  No execution history found for training")
            return pd.DataFrame()
        
        df = pd.DataFrame(executions)
        
        logger.info(f"📊 Retrieved {len(df)} executions for training")
        
        return df

    @staticmethod
    def _serialize_mongo_doc(doc: Dict) -> Dict:
        """Serialize Mongo document to API-safe dict."""
        serialized = dict(doc)
        if '_id' in serialized:
            serialized['_id'] = str(serialized['_id'])

        datetime_fields = ['timestamp', 'started_at', 'updated_at', 'finished_at', 'created_at', 'expires_at', 'submitted_at', 'confirmed_at']
        for field in datetime_fields:
            value = serialized.get(field)
            if isinstance(value, datetime):
                serialized[field] = value.isoformat()

        for event_list_field in ['lifecycle', 'events']:
            events = serialized.get(event_list_field)
            if isinstance(events, list):
                for event in events:
                    ts = event.get('timestamp') if isinstance(event, dict) else None
                    if isinstance(ts, datetime):
                        event['timestamp'] = ts.isoformat()

        return serialized


    @staticmethod
    def compute_payload_hash(payload: Optional[Dict[str, Any]]) -> str:
        """Return a stable SHA-256 hash for an execution payload/opportunity."""
        normalized = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def ensure_execution_state_indexes(self) -> None:
        """Create indexes used to gate duplicate opportunity/nonce submissions."""
        if self._indexes_ready:
            return

        await self.state_collection.create_index("opportunity_id")
        await self.state_collection.create_index("payload_hash")
        await self.state_collection.create_index([("chain_id", 1), ("nonce", 1)])
        await self.state_collection.create_index("tx_hash")
        await self.state_collection.create_index("status")
        self._indexes_ready = True

    async def record_execution_state(
        self,
        opportunity_id: str,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "quoted",
        chain_id: Optional[int] = None,
        nonce: Optional[int] = None,
        tx_hash: Optional[str] = None,
        gas_estimate: Optional[int] = None,
        gas_used: Optional[int] = None,
        expected_profit_usd: Optional[float] = None,
        realized_profit_usd: Optional[float] = None,
        failure_detail: Optional[str] = None,
        revert_reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        payload_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upsert durable execution state for an opportunity attempt."""
        await self.ensure_execution_state_indexes()
        if status not in EXECUTION_STATUSES:
            raise ValueError(f"Unsupported execution status: {status}")
        now = datetime.utcnow()
        payload_hash = payload_hash or self.compute_payload_hash(payload)

        identity: Dict[str, Any]
        if chain_id is not None and nonce is not None:
            identity = {"chain_id": chain_id, "nonce": nonce}
        elif tx_hash:
            identity = {"tx_hash": tx_hash}
        else:
            identity = {"opportunity_id": opportunity_id, "payload_hash": payload_hash}

        set_doc: Dict[str, Any] = {
            "opportunity_id": opportunity_id,
            "payload_hash": payload_hash,
            "status": status,
            "updated_at": now,
        }
        optional_fields = {
            "chain_id": chain_id,
            "nonce": nonce,
            "tx_hash": tx_hash,
            "gas_estimate": gas_estimate,
            "gas_used": gas_used,
            "expected_profit_usd": expected_profit_usd,
            "realized_profit_usd": realized_profit_usd,
            "failure_detail": failure_detail,
            "revert_reason": revert_reason,
            "metadata": metadata,
        }
        set_doc.update({k: v for k, v in optional_fields.items() if v is not None})
        if status == "submitted":
            set_doc["submitted_at"] = now
        if status in TERMINAL_EXECUTION_STATUSES:
            set_doc["finished_at"] = now
        if status == "confirmed":
            set_doc["confirmed_at"] = now

        update_doc = {
            "$set": set_doc,
            "$setOnInsert": {"created_at": now, "payload": payload or {}},
            "$push": {
                "events": {
                    "status": status,
                    "timestamp": now,
                    "tx_hash": tx_hash,
                    "failure_detail": failure_detail,
                    "revert_reason": revert_reason,
                }
            },
        }

        await self.state_collection.update_one(identity, update_doc, upsert=True)
        record = await self.state_collection.find_one(identity)
        return self._serialize_mongo_doc(record or {})

    async def find_blocking_execution(
        self,
        opportunity_id: Optional[str] = None,
        chain_id: Optional[int] = None,
        nonce: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find an active execution that should block duplicate submission."""
        await self.ensure_execution_state_indexes()
        active_statuses = list(RECEIPT_PENDING_STATUSES)
        clauses: List[Dict[str, Any]] = []
        if opportunity_id:
            clauses.append({"opportunity_id": opportunity_id})
        if chain_id is not None and nonce is not None:
            clauses.append({"chain_id": chain_id, "nonce": nonce})
        if not clauses:
            return None

        record = await self.state_collection.find_one(
            {"$and": [{"status": {"$in": active_statuses}}, {"$or": clauses}]},
            sort=[("updated_at", -1)],
        )
        return self._serialize_mongo_doc(record) if record else None

    async def get_execution_states(
        self,
        limit: int = 50,
        status: Optional[str] = None,
        opportunity_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve durable execution state records, newest first."""
        await self.ensure_execution_state_indexes()
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        if opportunity_id:
            query["opportunity_id"] = opportunity_id
        cursor = self.state_collection.find(query).sort("updated_at", -1).limit(limit)
        records = await cursor.to_list(length=limit)
        return [self._serialize_mongo_doc(record) for record in records]

    async def reconcile_submitted_transactions(
        self,
        w3: Any,
        max_age_seconds: Optional[int] = None,
    ) -> Dict[str, int]:
        """Reconcile submitted transactions against on-chain receipts."""
        await self.ensure_execution_state_indexes()
        summary = {"checked": 0, "confirmed": 0, "reverted": 0, "expired": 0, "pending": 0}
        query: Dict[str, Any] = {"status": {"$in": list(RECEIPT_PENDING_STATUSES)}, "tx_hash": {"$ne": None}}
        cursor = self.state_collection.find(query)
        records = await cursor.to_list(length=None)
        now = datetime.utcnow()

        for record in records:
            summary["checked"] += 1
            tx_hash = record.get("tx_hash")
            try:
                receipt = await asyncio.to_thread(w3.eth.get_transaction_receipt, tx_hash)
            except Exception as exc:
                receipt = None
                if "not found" not in str(exc).lower():
                    logger.debug(f"Receipt lookup failed for {tx_hash}: {exc}")

            if receipt:
                receipt_status = int(receipt.get("status", 0))
                new_status = "confirmed" if receipt_status == 1 else "reverted"
                failure_detail = None if receipt_status == 1 else "Transaction receipt status=0"
                await self.record_execution_state(
                    opportunity_id=record.get("opportunity_id", "unknown"),
                    payload=record.get("payload", {}),
                    payload_hash=record.get("payload_hash"),
                    status=new_status,
                    chain_id=record.get("chain_id"),
                    nonce=record.get("nonce"),
                    tx_hash=tx_hash,
                    gas_estimate=record.get("gas_estimate"),
                    gas_used=receipt.get("gasUsed"),
                    expected_profit_usd=record.get("expected_profit_usd"),
                    realized_profit_usd=record.get("realized_profit_usd"),
                    failure_detail=failure_detail,
                    revert_reason=failure_detail,
                    metadata={"block_number": receipt.get("blockNumber")},
                )
                summary[new_status] += 1
                continue

            submitted_at = record.get("submitted_at") or record.get("updated_at")
            if max_age_seconds and isinstance(submitted_at, datetime) and now - submitted_at > timedelta(seconds=max_age_seconds):
                await self.record_execution_state(
                    opportunity_id=record.get("opportunity_id", "unknown"),
                    payload=record.get("payload", {}),
                    payload_hash=record.get("payload_hash"),
                    status="expired",
                    chain_id=record.get("chain_id"),
                    nonce=record.get("nonce"),
                    tx_hash=tx_hash,
                    gas_estimate=record.get("gas_estimate"),
                    expected_profit_usd=record.get("expected_profit_usd"),
                    failure_detail="No receipt found before reconciliation expiry window",
                )
                summary["expired"] += 1
            else:
                summary["pending"] += 1

        return summary

    async def start_execution_lifecycle(
        self,
        strategy: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Start and persist an execution lifecycle record.
        """
        now = datetime.utcnow()
        execution_id = f"exec-{uuid.uuid4().hex}"

        doc = {
            "execution_id": execution_id,
            "strategy": strategy,
            "status": "started",
            "metadata": metadata or {},
            "tx_hash": None,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "lifecycle": [
                {
                    "stage": "execution_started",
                    "status": "started",
                    "timestamp": now,
                    "details": metadata or {}
                }
            ]
        }

        await self.lifecycle_collection.insert_one(doc)
        return {
            "execution_id": execution_id,
            "status": "started"
        }

    async def append_lifecycle_event(
        self,
        execution_id: str,
        stage: str,
        status: str,
        details: Optional[Dict] = None,
        tx_hash: Optional[str] = None
    ) -> None:
        """
        Append lifecycle event to existing execution record.
        """
        now = datetime.utcnow()
        event = {
            "stage": stage,
            "status": status,
            "timestamp": now,
            "details": details or {}
        }
        if tx_hash:
            event["tx_hash"] = tx_hash

        update_doc = {
            "$set": {
                "status": status,
                "updated_at": now
            },
            "$push": {
                "lifecycle": event
            }
        }
        if tx_hash:
            update_doc["$set"]["tx_hash"] = tx_hash

        await self.lifecycle_collection.update_one(
            {"execution_id": execution_id},
            update_doc
        )

    async def complete_execution_lifecycle(
        self,
        execution_id: str,
        success: bool,
        result: Optional[Dict] = None,
        tx_hash: Optional[str] = None
    ) -> None:
        """
        Mark lifecycle as completed and persist final state.
        """
        now = datetime.utcnow()
        final_status = "completed" if success else "failed"
        final_event = {
            "stage": "execution_finished",
            "status": final_status,
            "timestamp": now,
            "details": result or {}
        }
        if tx_hash:
            final_event["tx_hash"] = tx_hash

        update_doc = {
            "$set": {
                "status": final_status,
                "updated_at": now,
                "finished_at": now
            },
            "$push": {
                "lifecycle": final_event
            }
        }
        if tx_hash:
            update_doc["$set"]["tx_hash"] = tx_hash

        await self.lifecycle_collection.update_one(
            {"execution_id": execution_id},
            update_doc
        )

    async def get_execution_history(
        self,
        limit: int = 50,
        strategy: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve persisted execution lifecycle history (newest first).
        """
        query = {}
        if strategy:
            query["strategy"] = strategy
        if status:
            query["status"] = status

        cursor = self.lifecycle_collection.find(query).sort("updated_at", -1).limit(limit)
        records = await cursor.to_list(length=limit)
        return [self._serialize_mongo_doc(record) for record in records]

    async def get_execution_lifecycle_trace(self, execution_id: str) -> Optional[Dict]:
        """
        Retrieve full persisted lifecycle trace for an execution.
        """
        record = await self.lifecycle_collection.find_one({"execution_id": execution_id})
        if not record:
            return None
        return self._serialize_mongo_doc(record)
    
    async def get_execution_stats(self) -> Dict:
        """
        Get execution statistics.
        """
        total_count = await self.collection.count_documents({})
        
        # Aggregate stats
        pipeline = [
            {
                '$group': {
                    '_id': None,
                    'total_profit': {'$sum': '$net_profit_usd'},
                    'avg_slippage': {'$avg': '$actual_slippage'},
                    'avg_profit': {'$avg': '$net_profit_usd'},
                }
            }
        ]
        
        result = await self.collection.aggregate(pipeline).to_list(length=1)
        
        if result:
            stats = result[0]
            return {
                'total_executions': total_count,
                'total_profit_usd': stats.get('total_profit', 0),
                'avg_slippage': stats.get('avg_slippage', 0),
                'avg_profit_usd': stats.get('avg_profit', 0)
            }
        else:
            return {
                'total_executions': 0,
                'total_profit_usd': 0,
                'avg_slippage': 0,
                'avg_profit_usd': 0
            }


# Singleton
_logger_instance = None


def get_execution_logger() -> ExecutionLogger:
    """Get or create singleton Execution Logger."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ExecutionLogger()
    return _logger_instance
