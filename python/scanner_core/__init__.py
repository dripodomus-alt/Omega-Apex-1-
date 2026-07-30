from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable


@dataclass
class GateConfig:
    min_tvl_usd: str = "50000"
    chain_id: int = 137


class Candidate:
    def __init__(self) -> None:
        self.buy_pool_address = ""
        self.sell_pool_address = ""
        self.token_in = ""
        self.token_mid = ""
        self.buy_pool_tvl_usd = "0"
        self.executable_buy_price = "0"
        self.executable_sell_price = "0"
        self.buy_pool_protocol = ""
        self.sell_pool_protocol = ""

    def validate(self, config: GateConfig) -> None:
        if Decimal(str(self.buy_pool_tvl_usd or "0")) < Decimal(str(config.min_tvl_usd)):
            raise ValueError("tvl_below_minimum")
        if self.buy_pool_address and self.buy_pool_address == self.sell_pool_address:
            raise ValueError("same_pool")
        if Decimal(str(self.executable_buy_price or "0")) >= Decimal(str(self.executable_sell_price or "0")):
            raise ValueError("not_profitable")
        return None


class ScanResults(list):
    def __await__(self):
        async def _return_self():
            return self
        return _return_self().__await__()


def _dec(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _pool_price(pool: dict[str, Any]) -> Decimal:
    if "executable_price" in pool:
        return _dec(pool.get("executable_price"))
    reserves = pool.get("reserves") or pool.get("state", {}).get("reserves")
    tokens = pool.get("tokens") or []
    if reserves and len(reserves) >= 2 and len(tokens) >= 2:
        r0 = _dec(reserves[0])
        r1 = _dec(reserves[1])
        if r0 > 0 and r1 > 0:
            return r0 / r1
    return Decimal("0")


def find_best_quote(candidates: Iterable[Candidate], find_min: bool = True) -> Candidate | None:
    candidates = list(candidates)
    if not candidates:
        return None
    key = (lambda c: _dec(c.executable_buy_price)) if find_min else (lambda c: _dec(c.executable_sell_price))
    return min(candidates, key=key) if find_min else max(candidates, key=key)


def scan_opportunities(pools_json: str, config: GateConfig) -> ScanResults:
    pools = json.loads(pools_json) if isinstance(pools_json, str) else dict(pools_json)
    by_pair: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for pool_id, pool in pools.items():
        tokens = pool.get("tokens") or []
        if len(tokens) < 2:
            continue
        by_pair.setdefault((tokens[0], tokens[1]), []).append((pool_id, pool))

    out = ScanResults()
    seen: set[tuple[str, str, str, str]] = set()
    for (token_in, token_mid), buy_pools in by_pair.items():
        sell_pools = by_pair.get((token_mid, token_in), [])
        if not sell_pools:
            continue
        for _, buy in buy_pools:
            for _, sell in sell_pools:
                buy_addr = str(buy.get("address", ""))
                sell_addr = str(sell.get("address", ""))
                if buy_addr == sell_addr:
                    continue
                buy_tvl = _dec(buy.get("total_executable_liquidity_usd", "0"))
                if buy_tvl < Decimal(str(config.min_tvl_usd)):
                    continue
                buy_price = _pool_price(buy)
                sell_price = _pool_price(sell)
                if buy_price <= 0 or sell_price <= 0 or buy_price >= sell_price:
                    continue
                key = (token_in, token_mid, buy_addr, sell_addr)
                if key in seen:
                    continue
                seen.add(key)
                cand = Candidate()
                cand.buy_pool_address = buy_addr
                cand.sell_pool_address = sell_addr
                cand.token_in = token_in
                cand.token_mid = token_mid
                cand.buy_pool_tvl_usd = str(buy_tvl)
                cand.executable_buy_price = str(buy_price.normalize())
                cand.executable_sell_price = str(sell_price.normalize())
                cand.buy_pool_protocol = str(buy.get("protocol", ""))
                cand.sell_pool_protocol = str(sell.get("protocol", ""))
                out.append(cand)
    out.sort(key=lambda c: _dec(c.executable_sell_price) - _dec(c.executable_buy_price), reverse=True)
    return out


async def test_only_quote(pool_json: str, token_in: str, amount_in: str) -> str:
    pool = json.loads(pool_json)
    state = pool.get("state", {})
    reserves = state.get("reserves") or pool.get("reserves") or state.get("balances")
    tokens = pool.get("tokens") or []
    if not reserves or token_in not in tokens:
        return "0"
    idx_in = tokens.index(token_in)
    idx_out = 1 if idx_in == 0 and len(tokens) > 1 else 0
    reserve_in = _dec(reserves[idx_in])
    reserve_out = _dec(reserves[idx_out])
    amt = _dec(amount_in)
    if reserve_in <= 0 or reserve_out <= 0 or amt <= 0:
        return "0"
    fee = Decimal("0.003")
    amount_after_fee = amt * (Decimal("1") - fee)
    result = (amount_after_fee * reserve_out) / (reserve_in + amount_after_fee)
    return str(int(result))