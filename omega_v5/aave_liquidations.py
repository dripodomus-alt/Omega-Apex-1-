#!/usr/bin/env python3
# ==============================================================================
# aave_liquidations.py -- read-only Aave V3 liquidation candidate scanner.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from decimal import Decimal
from typing import Any

from web3 import Web3

from .amm_adapters import quote_pool
from .config import (
    AAVE_BORROWER_SEED_ADDRESSES,
    AAVE_V3_POOL_ADDRESSES_PROVIDER,
    AAVE_V3_PROTOCOL_DATA_PROVIDER,
    LIQUIDATION_MAX_BORROWERS,
    LIQUIDATION_MIN_NET_PROFIT_USD,
    LIQUIDATION_SCAN_BLOCKS,
)
from .flash_loan import evaluate_profitability
from .flash_loan import FlashSource
from .liquidation_capital import CapitalSourceCheck, usable_capital_sources
from .oracle_layer import PriceUnavailable, token_price_usd
from .rpc_layer import ADDRESS_TO_SYMBOL, TOKEN_DECIMALS


WAD = Decimal("1e18")
HEALTH_FACTOR_LIQUIDATION_THRESHOLD = Decimal("1")
MAX_CLOSE_FACTOR_HF_THRESHOLD = Decimal("0.95")
DEFAULT_CLOSE_FACTOR = Decimal("0.5")
MAX_CLOSE_FACTOR = Decimal("1")
BORROW_EVENT_TOPIC = Web3.keccak(
    text="Borrow(address,address,address,uint256,uint8,uint256,uint16)"
).hex()


_PROVIDER_ABI = [
    {
        "name": "getPool",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "getPoolDataProvider",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
]

_POOL_ABI = [
    {
        "name": "getUserAccountData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [
            {"name": "totalCollateralBase", "type": "uint256"},
            {"name": "totalDebtBase", "type": "uint256"},
            {"name": "availableBorrowsBase", "type": "uint256"},
            {"name": "currentLiquidationThreshold", "type": "uint256"},
            {"name": "ltv", "type": "uint256"},
            {"name": "healthFactor", "type": "uint256"},
        ],
    },
    {
        "name": "getReservesList",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address[]"}],
    },
    {
        "name": "getConfiguration",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [{"name": "data", "type": "uint256"}],
    },
]

_DATA_PROVIDER_ABI = [
    {
        "name": "getUserReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "user", "type": "address"},
        ],
        "outputs": [
            {"name": "currentATokenBalance", "type": "uint256"},
            {"name": "currentStableDebt", "type": "uint256"},
            {"name": "currentVariableDebt", "type": "uint256"},
            {"name": "principalStableDebt", "type": "uint256"},
            {"name": "scaledVariableDebt", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "stableRateLastUpdated", "type": "uint40"},
            {"name": "usageAsCollateralEnabled", "type": "bool"},
        ],
    }
]


@dataclass(frozen=True)
class AaveReserveRisk:
    symbol: str
    asset: str
    decimals: int
    ltv_bps: int
    liquidation_threshold_bps: int
    liquidation_bonus_bps: int
    liquidation_protocol_fee_bps: int
    borrowing_enabled: bool
    collateral_enabled: bool

    def as_packet(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset": self.asset,
            "decimals": self.decimals,
            "ltvBps": self.ltv_bps,
            "liquidationThresholdBps": self.liquidation_threshold_bps,
            "liquidationBonusBps": self.liquidation_bonus_bps,
            "liquidationProtocolFeeBps": self.liquidation_protocol_fee_bps,
            "borrowingEnabled": self.borrowing_enabled,
            "collateralEnabled": self.collateral_enabled,
        }


@dataclass(frozen=True)
class ReservePosition:
    symbol: str
    asset: str
    raw_collateral: int
    raw_stable_debt: int
    raw_variable_debt: int
    usage_as_collateral: bool
    risk: AaveReserveRisk

    @property
    def raw_debt(self) -> int:
        return self.raw_stable_debt + self.raw_variable_debt

    def normalized_collateral(self) -> Decimal:
        return Decimal(self.raw_collateral) / (Decimal(10) ** self.risk.decimals)

    def normalized_debt(self) -> Decimal:
        return Decimal(self.raw_debt) / (Decimal(10) ** self.risk.decimals)


@dataclass(frozen=True)
class ExitQuote:
    ok: bool
    debt_symbol: str
    collateral_symbol: str
    collateral_amount: Decimal
    debt_out: Decimal
    pool_id: str = ""
    protocol: str = ""
    route: list[str] = field(default_factory=list)
    reject_reason: str = ""

    def as_packet(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "debtSymbol": self.debt_symbol,
            "collateralSymbol": self.collateral_symbol,
            "collateralAmount": str(self.collateral_amount),
            "debtOut": str(self.debt_out),
            "poolId": self.pool_id,
            "protocol": self.protocol,
            "route": list(self.route),
            "rejectReason": self.reject_reason,
        }


@dataclass(frozen=True)
class ApexLiquidationCandidatePacket:
    authority: str
    nextStage: str
    borrower: str
    block_number: int
    health_factor: Decimal
    debt_symbol: str
    collateral_symbol: str
    debt_to_cover_raw: int
    debt_to_cover: Decimal
    seized_collateral_estimate: Decimal
    gross_profit_usd: Decimal
    expected_net_profit_usd: Decimal
    capital_sources: list[CapitalSourceCheck]
    selected_capital_source: CapitalSourceCheck | None
    exit_quote: ExitQuote
    reject_reasons: list[str] = field(default_factory=list)

    def as_packet(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "nextStage": self.nextStage,
            "borrower": self.borrower,
            "blockNumber": self.block_number,
            "healthFactor": str(self.health_factor),
            "debtSymbol": self.debt_symbol,
            "collateralSymbol": self.collateral_symbol,
            "debtToCoverRaw": str(self.debt_to_cover_raw),
            "debtToCover": str(self.debt_to_cover),
            "seizedCollateralEstimate": str(self.seized_collateral_estimate),
            "grossProfitUsd": str(self.gross_profit_usd),
            "expectedNetProfitUsd": str(self.expected_net_profit_usd),
            "capitalSources": [source.as_packet() for source in self.capital_sources],
            "selectedCapitalSource": self.selected_capital_source.as_packet() if self.selected_capital_source else None,
            "exitQuote": self.exit_quote.as_packet(),
            "rejectReasons": list(self.reject_reasons),
        }


def _decode_configuration(symbol: str, asset: str, raw: int) -> AaveReserveRisk:
    decimals = (raw >> 48) & 0xFF
    return AaveReserveRisk(
        symbol=symbol,
        asset=Web3.to_checksum_address(asset),
        decimals=int(decimals or TOKEN_DECIMALS.get(symbol, 18)),
        ltv_bps=int(raw & 0xFFFF),
        liquidation_threshold_bps=int((raw >> 16) & 0xFFFF),
        liquidation_bonus_bps=int((raw >> 32) & 0xFFFF),
        liquidation_protocol_fee_bps=int((raw >> 152) & 0xFFFF),
        borrowing_enabled=bool((raw >> 58) & 1),
        collateral_enabled=bool((raw >> 56) & 1) and int((raw >> 16) & 0xFFFF) > 0,
    )


class AaveLiquidationScanner:
    def __init__(self, pools: dict[str, dict] | None = None):
        from . import rpc_layer
        if rpc_layer.w3 is None or not rpc_layer.RPC_LIVE:
            raise RuntimeError("AaveLiquidationScanner requires a live RPC connection")
        self.w3 = rpc_layer.w3
        self.pools = pools or {}
        provider = self.w3.eth.contract(
            address=Web3.to_checksum_address(AAVE_V3_POOL_ADDRESSES_PROVIDER),
            abi=_PROVIDER_ABI,
        )
        self.aave_pool_address = Web3.to_checksum_address(provider.functions.getPool().call())
        data_provider = AAVE_V3_PROTOCOL_DATA_PROVIDER or provider.functions.getPoolDataProvider().call()
        self.data_provider_address = Web3.to_checksum_address(data_provider)
        self.pool = self.w3.eth.contract(address=self.aave_pool_address, abi=_POOL_ABI)
        self.data_provider = self.w3.eth.contract(
            address=self.data_provider_address,
            abi=_DATA_PROVIDER_ABI,
        )

    def discover_recent_borrowers(self, block_number: int) -> list[str]:
        borrowers = {
            Web3.to_checksum_address(addr)
            for addr in AAVE_BORROWER_SEED_ADDRESSES
            if Web3.is_address(addr)
        }
        from_block = max(0, block_number - LIQUIDATION_SCAN_BLOCKS)
        try:
            logs = self.w3.eth.get_logs({
                "address": self.aave_pool_address,
                "fromBlock": from_block,
                "toBlock": block_number,
                "topics": [BORROW_EVENT_TOPIC],
            })
            for log in logs:
                if len(log.get("topics", [])) >= 3:
                    raw = log["topics"][2].hex()[-40:]
                    borrowers.add(Web3.to_checksum_address("0x" + raw))
                if len(borrowers) >= LIQUIDATION_MAX_BORROWERS:
                    break
        except Exception as e:
            logging.warning(f"Failed to discover recent borrowers from logs: {e}")
        return list(borrowers)[:LIQUIDATION_MAX_BORROWERS]

    def reserve_risks(self, block_number: int) -> dict[str, AaveReserveRisk]:
        risks: dict[str, AaveReserveRisk] = {}
        reserves = self.pool.functions.getReservesList().call(block_identifier=block_number)
        for asset in reserves:
            symbol = ADDRESS_TO_SYMBOL.get(str(asset).lower())
            if not symbol:
                continue
            config_result = self.pool.functions.getConfiguration(Web3.to_checksum_address(asset)).call(
                block_identifier=block_number
            )
            raw_cfg = int(config_result[0] if isinstance(config_result, (tuple, list)) else config_result)
            risks[symbol] = _decode_configuration(symbol, asset, raw_cfg)
        return risks

    def borrower_positions(
        self,
        borrower: str,
        risks: dict[str, AaveReserveRisk],
        block_number: int,
    ) -> list[ReservePosition]:
        positions: list[ReservePosition] = []
        for risk in risks.values():
            data = self.data_provider.functions.getUserReserveData(
                Web3.to_checksum_address(risk.asset),
                Web3.to_checksum_address(borrower),
            ).call(block_identifier=block_number)
            pos = ReservePosition(
                symbol=risk.symbol,
                asset=risk.asset,
                raw_collateral=int(data[0]),
                raw_stable_debt=int(data[1]),
                raw_variable_debt=int(data[2]),
                usage_as_collateral=bool(data[8]),
                risk=risk,
            )
            if pos.raw_collateral > 0 or pos.raw_debt > 0:
                positions.append(pos)
        return positions

    def account_health(self, borrower: str, block_number: int) -> Decimal:
        data = self.pool.functions.getUserAccountData(Web3.to_checksum_address(borrower)).call(
            block_identifier=block_number
        )
        return Decimal(int(data[5])) / WAD

    def _exit_quote(
        self,
        collateral_symbol: str,
        debt_symbol: str,
        collateral_amount: Decimal,
    ) -> ExitQuote:
        if collateral_symbol == debt_symbol:
            return ExitQuote(
                ok=True,
                debt_symbol=debt_symbol,
                collateral_symbol=collateral_symbol,
                collateral_amount=collateral_amount,
                debt_out=collateral_amount,
                route=[debt_symbol],
            )

        best: ExitQuote | None = None

        # --- Pass 1: One-hop routes ---
        for pool_id, pool in self.pools.items():
            toks = pool.get("tokens", [])
            if collateral_symbol not in toks or debt_symbol not in toks:
                continue
            for quote in quote_pool(pool, collateral_amount, collateral_symbol, debt_symbol):
                if quote.amount_out > 0 and (best is None or quote.amount_out > best.debt_out):
                    best = ExitQuote(
                        ok=True, debt_symbol=debt_symbol, collateral_symbol=collateral_symbol,
                        collateral_amount=collateral_amount, debt_out=quote.amount_out,
                        pool_id=pool_id, protocol=pool.get("protocol", ""), route=[collateral_symbol, debt_symbol],
                    )

        # --- Pass 2: Two-hop routes ---
        all_tokens = {t for p in self.pools.values() for t in p.get("tokens", [])}
        for mid_symbol in all_tokens:
            if mid_symbol in {collateral_symbol, debt_symbol}:
                continue

            best_leg1_quote = max(
                (q for p in self.pools.values() for q in quote_pool(p, collateral_amount, collateral_symbol, mid_symbol)),
                key=lambda q: q.amount_out, default=None,
            )
            if not best_leg1_quote or best_leg1_quote.amount_out <= 0:
                continue

            best_leg2_quote = max(
                (q for p in self.pools.values() for q in quote_pool(p, best_leg1_quote.amount_out, mid_symbol, debt_symbol)),
                key=lambda q: q.amount_out, default=None,
            )
            if not best_leg2_quote or best_leg2_quote.amount_out <= 0:
                continue

            if best is None or best_leg2_quote.amount_out > best.debt_out:
                best = ExitQuote(
                    ok=True, debt_symbol=debt_symbol, collateral_symbol=collateral_symbol,
                    collateral_amount=collateral_amount, debt_out=best_leg2_quote.amount_out,
                    protocol="2-hop", route=[collateral_symbol, mid_symbol, debt_symbol],
                )

        return best or ExitQuote(
            ok=False,
            debt_symbol=debt_symbol,
            collateral_symbol=collateral_symbol,
            collateral_amount=collateral_amount,
            debt_out=Decimal("0"),
            reject_reason="no executable 1- or 2-hop collateral exit quote",
        )

    def scan(self) -> list[ApexLiquidationCandidatePacket]:
        block_number = int(self.w3.eth.block_number)
        risks = self.reserve_risks(block_number)
        borrowers = self.discover_recent_borrowers(block_number)
        packets: list[ApexLiquidationCandidatePacket] = []

        for borrower in borrowers:
            health = self.account_health(borrower, block_number)
            if health >= HEALTH_FACTOR_LIQUIDATION_THRESHOLD:
                continue
            positions = self.borrower_positions(borrower, risks, block_number)
            debt_positions = [p for p in positions if p.raw_debt > 0 and p.risk.borrowing_enabled]
            collateral_positions = [
                p for p in positions
                if p.raw_collateral > 0 and p.usage_as_collateral and p.risk.collateral_enabled
            ]
            close_factor = MAX_CLOSE_FACTOR if health <= MAX_CLOSE_FACTOR_HF_THRESHOLD else DEFAULT_CLOSE_FACTOR

            for debt in debt_positions:
                try:
                    debt_price = token_price_usd(debt.symbol)
                except PriceUnavailable:
                    continue
                debt_to_cover_raw = int(Decimal(debt.raw_debt) * close_factor)
                if debt_to_cover_raw <= 0:
                    continue
                debt_to_cover = Decimal(debt_to_cover_raw) / (Decimal(10) ** debt.risk.decimals)
                debt_to_cover_usd = debt_to_cover * debt_price

                source_checks = usable_capital_sources(debt.symbol, debt_to_cover_raw)
                selected_source = next((source for source in source_checks if source.usable), None)

                for collateral in collateral_positions:
                    if collateral.symbol == debt.symbol:
                        continue
                    try:
                        collateral_price = token_price_usd(collateral.symbol)
                    except PriceUnavailable:
                        continue
                    bonus = Decimal(collateral.risk.liquidation_bonus_bps) / Decimal("10000")
                    protocol_fee = Decimal(collateral.risk.liquidation_protocol_fee_bps) / Decimal("10000")
                    seized_usd = debt_to_cover_usd * bonus * (Decimal("1") - protocol_fee)
                    seized_amount = seized_usd / collateral_price if collateral_price > 0 else Decimal("0")
                    seized_amount = min(seized_amount, collateral.normalized_collateral())
                    if seized_amount <= 0:
                        continue

                    exit_quote = self._exit_quote(collateral.symbol, debt.symbol, seized_amount)
                    gross_out_usd = exit_quote.debt_out * debt_price if exit_quote.ok else Decimal("0")
                    prof = evaluate_profitability(
                        gross_out_usd,
                        debt_to_cover_usd,
                        hops=2,
                        flash_source=FlashSource.AAVE,
                        asset=debt.symbol,
                        gas_units_override=Decimal("900000"),
                    )
                    reject_reasons: list[str] = []
                    if selected_source is None:
                        reject_reasons.append("no usable capital source")
                    if not exit_quote.ok:
                        reject_reasons.append(exit_quote.reject_reason)
                    if prof.net_profit_usd < LIQUIDATION_MIN_NET_PROFIT_USD:
                        reject_reasons.append("net profit below liquidation gate")

                    packets.append(ApexLiquidationCandidatePacket(
                        authority="SCANNER_ONLY",
                        nextStage="LIQUIDATION" if not reject_reasons else "REJECTED",
                        borrower=borrower,
                        block_number=block_number,
                        health_factor=health,
                        debt_symbol=debt.symbol,
                        collateral_symbol=collateral.symbol,
                        debt_to_cover_raw=debt_to_cover_raw,
                        debt_to_cover=debt_to_cover,
                        seized_collateral_estimate=seized_amount,
                        gross_profit_usd=gross_out_usd - debt_to_cover_usd,
                        expected_net_profit_usd=prof.net_profit_usd,
                        capital_sources=source_checks,
                        selected_capital_source=selected_source,
                        exit_quote=exit_quote,
                        reject_reasons=reject_reasons,
                    ))

        packets.sort(key=lambda packet: packet.expected_net_profit_usd, reverse=True)
        return packets
