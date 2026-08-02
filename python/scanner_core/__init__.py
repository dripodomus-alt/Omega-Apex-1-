from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from web3 import Web3

from omega_v5.contract_deployments import deployment_address


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
        self.path: list[str] = []
        self.pools: list[str] = []
        self.estimated_profit_ratio: Decimal = Decimal("0")

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


def _fmt_dec(value: Decimal) -> str:
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


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


def _token_decimals(token: str) -> int:
    # Best-effort for legacy fixtures where token strings are addresses.
    # Defaults are intentionally conservative and match common mainnet units.
    token_l = str(token).lower()
    by_address = {
        # USDC (Ethereum + Polygon forms in legacy tests)
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,
        "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": 6,
        # USDT
        "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": 6,
        # DAI
        "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": 18,
        # WETH / WBTC
        "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": 18,
        "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6": 8,
    }
    if token_l in by_address:
        return by_address[token_l]

    by_symbol = {
        "USDC": 6,
        "USDC.E": 6,
        "USDT": 6,
        "DAI": 18,
        "WETH": 18,
        "WBTC": 8,
    }
    return by_symbol.get(str(token).upper(), 18)


def _pool_directional_rates(pool: dict[str, Any]) -> tuple[Decimal, Decimal]:
    """Return directed rates (token0->token1, token1->token0) in unit-space."""
    fee_factor = Decimal("0.997")
    if "executable_price" in pool:
        # executable_price is interpreted as token0-denominated price of token1.
        price = _dec(pool.get("executable_price"))
        if price <= 0:
            return Decimal("0"), Decimal("0")
        return (fee_factor / price), (fee_factor * price)

    state = pool.get("state", {}) if isinstance(pool.get("state"), dict) else {}
    reserves = pool.get("reserves") or state.get("reserves")
    if not reserves and "reserve0" in state and "reserve1" in state:
        reserves = [state.get("reserve0"), state.get("reserve1")]
    if not reserves or len(reserves) < 2:
        return Decimal("0"), Decimal("0")

    tokens = pool.get("tokens") or []
    if len(tokens) < 2:
        return Decimal("0"), Decimal("0")

    dec0 = _token_decimals(tokens[0])
    dec1 = _token_decimals(tokens[1])
    r0 = _dec(reserves[0]) / (Decimal(10) ** dec0)
    r1 = _dec(reserves[1]) / (Decimal(10) ** dec1)
    if r0 <= 0 or r1 <= 0:
        return Decimal("0"), Decimal("0")

    return (fee_factor * (r1 / r0)), (fee_factor * (r0 / r1))


def _candidate_from_cycle(
    path: list[str],
    edges: list[dict[str, Any]],
    ratio: Decimal,
) -> Candidate:
    buy = edges[0]
    sell = edges[-1]
    cand = Candidate()
    cand.buy_pool_address = str(buy.get("address", ""))
    cand.sell_pool_address = str(sell.get("address", ""))
    cand.token_in = str(path[0])
    cand.token_mid = str(path[1]) if len(path) > 2 else ""
    cand.buy_pool_tvl_usd = _fmt_dec(_dec(buy.get("tvl", "0")))
    cand.executable_buy_price = _fmt_dec(_dec(buy.get("price_token0_per_token1", "0")))
    cand.executable_sell_price = _fmt_dec(_dec(sell.get("price_token1_per_token0", "0")))
    cand.buy_pool_protocol = str(buy.get("protocol", ""))
    cand.sell_pool_protocol = str(sell.get("protocol", ""))
    cand.path = list(path)
    cand.pools = [str(edge.get("address", "")) for edge in edges]
    cand.estimated_profit_ratio = ratio
    return cand


def find_best_quote(candidates: Iterable[Candidate], find_min: bool = True) -> Candidate | None:
    candidates = list(candidates)
    if not candidates:
        return None
    key = (lambda c: _dec(c.executable_buy_price)) if find_min else (lambda c: _dec(c.executable_sell_price))
    return min(candidates, key=key) if find_min else max(candidates, key=key)


def scan_opportunities(pools_json: str, config: GateConfig) -> ScanResults:
    pools = json.loads(pools_json) if isinstance(pools_json, str) else dict(pools_json)
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    adjacency: dict[str, list[dict[str, Any]]] = {}
    min_tvl = Decimal(str(config.min_tvl_usd))

    for pool_id, pool in pools.items():
        tokens = pool.get("tokens") or []
        if len(tokens) < 2:
            continue
        t0, t1 = str(tokens[0]), str(tokens[1])
        tvl = _dec(pool.get("total_executable_liquidity_usd", "0"))
        if tvl < min_tvl:
            continue

        rate_01, rate_10 = _pool_directional_rates(pool)
        if rate_01 > 0:
            entry_01 = {
                "pool_id": str(pool_id),
                "address": str(pool.get("address", "")),
                "protocol": str(pool.get("protocol", "")),
                "token_in": t0,
                "token_out": t1,
                "rate": rate_01,
                "tvl": tvl,
                "price_token0_per_token1": _pool_price(pool),
                "price_token1_per_token0": Decimal("1") / _pool_price(pool) if _pool_price(pool) > 0 else Decimal("0"),
            }
            by_pair.setdefault((t0, t1), []).append(entry_01)
            adjacency.setdefault(t0, []).append(entry_01)

        if rate_10 > 0:
            entry_10 = {
                "pool_id": str(pool_id),
                "address": str(pool.get("address", "")),
                "protocol": str(pool.get("protocol", "")),
                "token_in": t1,
                "token_out": t0,
                "rate": rate_10,
                "tvl": tvl,
                "price_token0_per_token1": Decimal("1") / _pool_price(pool) if _pool_price(pool) > 0 else Decimal("0"),
                "price_token1_per_token0": _pool_price(pool),
            }
            by_pair.setdefault((t1, t0), []).append(entry_10)
            adjacency.setdefault(t1, []).append(entry_10)

    out = ScanResults()
    seen_cycles: set[tuple[str, ...]] = set()

    def _dfs(start: str, current: str, path: list[str], edges: list[dict[str, Any]], ratio: Decimal) -> None:
        hop_count = len(edges)
        if 2 <= hop_count <= 4 and current == start:
            pool_addresses = [str(edge.get("address", "")) for edge in edges]
            if len(set(pool_addresses)) != len(pool_addresses):
                return
            if ratio > Decimal("1"):
                cycle_key = tuple(path)
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    out.append(_candidate_from_cycle(path, edges, ratio))
            return

        if hop_count >= 4:
            return

        for edge in adjacency.get(current, []):
            nxt = str(edge.get("token_out", ""))
            if not nxt:
                continue
            address = str(edge.get("address", ""))
            if address and any(str(item.get("address", "")) == address for item in edges):
                continue
            if nxt != start and nxt in path:
                continue
            _dfs(start, nxt, path + [nxt], edges + [edge], ratio * _dec(edge.get("rate", "0"), "0"))

    for start_token in list(adjacency.keys()):
        _dfs(start_token, start_token, [start_token], [], Decimal("1"))

    out.sort(key=lambda c: _dec(c.estimated_profit_ratio, "0"), reverse=True)
    return out

async def test_only_quote(pool_json: str, token_in: str, amount_in: str) -> str:
    pool = json.loads(pool_json)
    protocol = str(pool.get("protocol", "")).upper()
    state = pool.get("state", {})
    tokens = pool.get("tokens") or []
    if token_in not in tokens:
        return "0"

    # For fork-parity tests, prefer exact on-chain quote paths for adapter families.
    fork_rpc = os.environ.get("FORK_RPC_URL", "http://127.0.0.1:8545")
    try:
        w3 = Web3(Web3.HTTPProvider(fork_rpc))
    except Exception:
        w3 = None

    if w3 is not None and w3.is_connected():
        try:
            if protocol in {"UNISWAP_V3", "QUICKSWAP_V3", "ALGEBRA"}:
                quoter = deployment_address("UNISWAP_V3_QUOTER")
                fee = int(state.get("fee") or state.get("fee_tier") or pool.get("fee") or 500)
                quoter_abi = [
                    {
                        "inputs": [
                            {"internalType": "address", "name": "tokenIn", "type": "address"},
                            {"internalType": "address", "name": "tokenOut", "type": "address"},
                            {"internalType": "uint24", "name": "fee", "type": "uint24"},
                            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                        ],
                        "name": "quoteExactInputSingle",
                        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
                        "stateMutability": "nonpayable",
                        "type": "function",
                    }
                ]
                token_out = tokens[1] if tokens[0] == token_in else tokens[0]
                contract = w3.eth.contract(address=Web3.to_checksum_address(quoter), abi=quoter_abi)
                out = contract.functions.quoteExactInputSingle(
                    Web3.to_checksum_address(token_in),
                    Web3.to_checksum_address(token_out),
                    fee,
                    int(_dec(amount_in)),
                    0,
                ).call()
                return str(int(out))

            if protocol == "CURVE_STABLE":
                curve_abi = [
                    {
                        "inputs": [
                            {"internalType": "int128", "name": "i", "type": "int128"},
                            {"internalType": "int128", "name": "j", "type": "int128"},
                            {"internalType": "uint256", "name": "dx", "type": "uint256"},
                        ],
                        "name": "get_dy",
                        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                        "stateMutability": "view",
                        "type": "function",
                    }
                ]
                pool_addr = Web3.to_checksum_address(str(pool.get("address", "")))
                token_out = tokens[1] if tokens[0] == token_in else tokens[0]
                i = tokens.index(token_in)
                j = tokens.index(token_out)
                contract = w3.eth.contract(address=pool_addr, abi=curve_abi)
                out = contract.functions.get_dy(i, j, int(_dec(amount_in))).call()
                return str(int(out))

            if protocol == "BALANCER_WEIGHTED":
                vault = deployment_address("BALANCER_VAULT")
                vault_abi = [
                    {
                        "inputs": [
                            {"internalType": "uint8", "name": "kind", "type": "uint8"},
                            {
                                "components": [
                                    {"internalType": "bytes32", "name": "poolId", "type": "bytes32"},
                                    {"internalType": "uint256", "name": "assetInIndex", "type": "uint256"},
                                    {"internalType": "uint256", "name": "assetOutIndex", "type": "uint256"},
                                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                                    {"internalType": "bytes", "name": "userData", "type": "bytes"},
                                ],
                                "internalType": "struct IVault.BatchSwapStep[]",
                                "name": "swaps",
                                "type": "tuple[]",
                            },
                            {"internalType": "address[]", "name": "assets", "type": "address[]"},
                            {
                                "components": [
                                    {"internalType": "address", "name": "sender", "type": "address"},
                                    {"internalType": "bool", "name": "fromInternalBalance", "type": "bool"},
                                    {"internalType": "address payable", "name": "recipient", "type": "address"},
                                    {"internalType": "bool", "name": "toInternalBalance", "type": "bool"},
                                ],
                                "internalType": "struct IVault.FundManagement",
                                "name": "funds",
                                "type": "tuple",
                            },
                        ],
                        "name": "queryBatchSwap",
                        "outputs": [{"internalType": "int256[]", "name": "assetDeltas", "type": "int256[]"}],
                        "stateMutability": "nonpayable",
                        "type": "function",
                    }
                ]
                token_out = tokens[1] if tokens[0] == token_in else tokens[0]
                pool_id = str(pool.get("address", ""))
                assets = [Web3.to_checksum_address(token_in), Web3.to_checksum_address(token_out)]
                step = (bytes.fromhex(pool_id[2:]), 0, 1, int(_dec(amount_in)), b"")
                funds = (
                    Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
                    False,
                    Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
                    False,
                )
                contract = w3.eth.contract(address=Web3.to_checksum_address(vault), abi=vault_abi)
                deltas = contract.functions.queryBatchSwap(0, [step], assets, funds).call()
                return str(int(abs(deltas[1])))
        except Exception:
            pass

    reserves = state.get("reserves") or pool.get("reserves") or state.get("balances")
    if not reserves:
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

