"""
Canonical executor contract registry.

This module is the single source of truth for deployed executor contracts,
strategy function signatures, ABI fragments, ownership expectations, and
startup validation.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from web3 import Web3

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
UNDEPLOYED_MARKERS = {"", "NOT_DEPLOYED", ZERO_ADDRESS}
POLYGON_RPC_ENV_VARS = ("GETBLOCK_HTTP1", "ALCHEMY_HTTP_1", "PRIVATE_RPC_URL", "POLYGON_RPC_URL")
POLYGON_WSS_ENV_VARS = ("WSS_PROVIDER", "GETBLOCK_WSS1", "ALCHEMY_WSS")
EXECUTOR_WALLET_ENV_VARS = (
    "EXECUTOR_WALLET",
    "DEPLOYER_WALLET",
    "TREASURY_WALLET",
    "BOT_PROFIT_RECEIVER",
)
C1_EXECUTOR_ADDRESS_ENV_VARS = ("C1_CONTRACT_ADDRESS", "C1_ARB_EXECUTOR_ADDRESS", "C1_TARGET")
C2_EXECUTOR_ADDRESS_ENV_VARS = (
    "C2_CONTRACT_ADDRESS",
    "C2_ARB_EXECUTOR_ADDRESS",
    "C2_TARGET",
    "C2_ULTIMATE_TARGET",
)
LIQUIDATION_EXECUTOR_ADDRESS_ENV_VARS = ("LIQUIDATION_EXECUTOR_ADDRESS",)
DEFAULT_C1_EXECUTOR_ADDRESS = "0xe0cDe0255e1aFdcf0938Bed2A4329094b12b2642"
DEFAULT_C2_EXECUTOR_ADDRESS = "0x31B591B984981Fb73BA111b08CeeF93AF150Dc22"
DEFAULT_LIQUIDATION_EXECUTOR_ADDRESS = "0xE41F15f340F8eFa17f9129e44F82A9C0ee9F8D94"
INVALID_RPC_URL_MARKERS = ("YOUR_API_KEY",)


@dataclass(frozen=True)
class ChainConfig:
    key: str
    name: str
    chain_id: int
    rpc_env_vars: Sequence[str]


@dataclass(frozen=True)
class ExecutorContractConfig:
    strategy: str
    chain: str
    address: Optional[str]
    abi_identifier: str
    abi: List[Dict[str, Any]]
    function_signatures: Mapping[str, str]
    owner_address: Optional[str]
    required_permissions: Sequence[str]
    deployment_status: str
    deployment_block: Optional[int]
    address_env_vars: Sequence[str] = field(default_factory=tuple)
    owner_env_var: Optional[str] = None

    @property
    def chain_id(self) -> int:
        return SUPPORTED_CHAINS[self.chain].chain_id

    @property
    def deployed(self) -> bool:
        return self.deployment_status.lower() == "deployed" and bool(self.address)

    def checksum_address(self) -> Optional[str]:
        if not self.address or self.address in UNDEPLOYED_MARKERS:
            return None
        try:
            return Web3.to_checksum_address(self.address)
        except ValueError:
            return None


INSTITUTIONAL_EXECUTOR_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "minProfit", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "params", "type": "bytes"},
        ],
        "name": "initAaveFlash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "minProfit", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "params", "type": "bytes"},
        ],
        "name": "initBalancerFlash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "token", "type": "address"},
            {"name": "router", "type": "address"},
        ],
        "name": "approveRouter",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ULTIMATE_ARBITRAGE_EXECUTOR_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "minProfit", "type": "uint256"},
            {"name": "proof", "type": "bytes32[]"},
            {"name": "params", "type": "bytes"},
        ],
        "name": "initAaveFlash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "minProfit", "type": "uint256"},
            {"name": "proof", "type": "bytes32[]"},
            {"name": "params", "type": "bytes"},
        ],
        "name": "executeArbitrage",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {"inputs": [], "name": "owner", "outputs": [{"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "merkleRoot", "outputs": [{"name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "globalVaultMode", "outputs": [{"name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "newRoot", "type": "bytes32"}], "name": "updateRoot", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "r", "type": "bytes32"}], "name": "updateMerkleRoot", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
]

LIQUIDATION_EXECUTOR_ABI: List[Dict[str, Any]] = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "collateralAsset", "type": "address"},
                    {"name": "debtAsset", "type": "address"},
                    {"name": "user", "type": "address"},
                    {"name": "debtToCover", "type": "uint256"},
                    {"name": "minProfitBps", "type": "uint256"},
                    {"name": "swapProtocol", "type": "uint8"},
                    {"name": "swapFee", "type": "uint24"},
                    {"name": "maxSlippageBps", "type": "uint256"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "executeLiquidation",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "token", "type": "address"}, {"name": "to", "type": "address"}],
        "name": "withdrawAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {"inputs": [], "name": "owner", "outputs": [{"name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "user", "type": "address"},
            {"indexed": True, "name": "collateralAsset", "type": "address"},
            {"indexed": True, "name": "debtAsset", "type": "address"},
            {"indexed": False, "name": "debtCovered", "type": "uint256"},
            {"indexed": False, "name": "collateralReceived", "type": "uint256"},
            {"indexed": False, "name": "profitUsd", "type": "uint256"},
        ],
        "name": "LiquidationExecuted",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "tokenIn", "type": "address"},
            {"indexed": True, "name": "tokenOut", "type": "address"},
            {"indexed": False, "name": "amountIn", "type": "uint256"},
            {"indexed": False, "name": "amountOut", "type": "uint256"},
            {"indexed": False, "name": "protocol", "type": "uint8"},
        ],
        "name": "SwapExecuted",
        "type": "event",
    },
]

SUPPORTED_CHAINS: Mapping[str, ChainConfig] = {
    "polygon": ChainConfig(
        key="polygon",
        name="Polygon",
        chain_id=137,
        rpc_env_vars=POLYGON_RPC_ENV_VARS,
    )
}

DEX_ROUTERS: Mapping[str, Mapping[str, str]] = {
    "polygon": {
        "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "quickswap_v2": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        "quickswap_v3": "0xf5b509bB0909a69B1c207E495f687a596C168E12",
        "sushiswap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
    }
}


def _env_address(env_vars: Sequence[str], default: Optional[str]) -> Optional[str]:
    for env_var in env_vars:
        value = os.getenv(env_var, "").strip()
        if value:
            return None if value in UNDEPLOYED_MARKERS else value
    return default


def _env_owner(env_var: str) -> Optional[str]:
    value = os.getenv(env_var, "").strip()
    if value and value not in UNDEPLOYED_MARKERS:
        return value
    return None


def get_executor_registry() -> Dict[str, ExecutorContractConfig]:
    c1_address = _env_address(C1_EXECUTOR_ADDRESS_ENV_VARS, DEFAULT_C1_EXECUTOR_ADDRESS)
    c2_address = _env_address(C2_EXECUTOR_ADDRESS_ENV_VARS, DEFAULT_C2_EXECUTOR_ADDRESS)
    liquidation_address = _env_address(
        LIQUIDATION_EXECUTOR_ADDRESS_ENV_VARS,
        DEFAULT_LIQUIDATION_EXECUTOR_ADDRESS,
    )

    return {
        "institutional_arbitrage": ExecutorContractConfig(
            strategy="institutional_arbitrage",
            chain="polygon",
            address=c1_address,
            abi_identifier="inline:institutional_executor:v1",
            abi=INSTITUTIONAL_EXECUTOR_ABI,
            function_signatures={
                "aave_flash": "initAaveFlash(address,uint256,uint256,uint256,bytes)",
                "balancer_flash": "initBalancerFlash(address,uint256,uint256,uint256,bytes)",
                "approve_router": "approveRouter(address,address)",
                "owner": "owner()",
            },
            owner_address=_env_owner("C1_OWNER_ADDRESS"),
            required_permissions=("owner",),
            deployment_status="deployed" if c1_address else "not_deployed",
            deployment_block=_int_env("C1_DEPLOYMENT_BLOCK"),
            address_env_vars=C1_EXECUTOR_ADDRESS_ENV_VARS,
            owner_env_var="C1_OWNER_ADDRESS",
        ),
        "ultimate_arbitrage": ExecutorContractConfig(
            strategy="ultimate_arbitrage",
            chain="polygon",
            address=c2_address,
            abi_identifier="inline:ultimate_arbitrage_executor:v1",
            abi=ULTIMATE_ARBITRAGE_EXECUTOR_ABI,
            function_signatures={
                "aave_flash": "initAaveFlash(address,uint256,uint256,bytes32[],bytes)",
                "execute_arbitrage": "executeArbitrage(address,uint256,uint256,bytes32[],bytes)",
                "update_root": "updateRoot(bytes32)",
                "update_merkle_root": "updateMerkleRoot(bytes32)",
                "owner": "owner()",
            },
            owner_address=_env_owner("C2_OWNER_ADDRESS"),
            required_permissions=("owner", "merkle_root_updater"),
            deployment_status="deployed" if c2_address else "not_deployed",
            deployment_block=_int_env("C2_DEPLOYMENT_BLOCK"),
            address_env_vars=C2_EXECUTOR_ADDRESS_ENV_VARS,
            owner_env_var="C2_OWNER_ADDRESS",
        ),
        "liquidation": ExecutorContractConfig(
            strategy="liquidation",
            chain="polygon",
            address=liquidation_address,
            abi_identifier="inline:liquidation_executor:v1",
            abi=LIQUIDATION_EXECUTOR_ABI,
            function_signatures={
                "execute_liquidation": "executeLiquidation((address,address,address,uint256,uint256,uint8,uint24,uint256))",
                "withdraw_all": "withdrawAll(address,address)",
                "owner": "owner()",
            },
            owner_address=_env_owner("LIQUIDATION_EXECUTOR_OWNER"),
            required_permissions=("owner",),
            deployment_status="deployed" if liquidation_address else "not_deployed",
            deployment_block=_int_env("LIQUIDATION_EXECUTOR_DEPLOYMENT_BLOCK"),
            address_env_vars=LIQUIDATION_EXECUTOR_ADDRESS_ENV_VARS,
            owner_env_var="LIQUIDATION_EXECUTOR_OWNER",
        ),
    }


def _int_env(name: str) -> Optional[int]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def get_executor_config(strategy: str) -> ExecutorContractConfig:
    registry = get_executor_registry()
    if strategy not in registry:
        raise KeyError(f"Unsupported executor strategy: {strategy}")
    return registry[strategy]


def get_active_executor_address(strategy: str) -> Optional[str]:
    return get_executor_config(strategy).checksum_address()


def get_executor_abi(strategy: str) -> List[Dict[str, Any]]:
    return get_executor_config(strategy).abi


def get_chain_config(chain: str = "polygon") -> ChainConfig:
    if chain not in SUPPORTED_CHAINS:
        raise KeyError(f"Unsupported chain: {chain}")
    return SUPPORTED_CHAINS[chain]


def get_rpc_url(chain: str = "polygon") -> str:
    for env_var in get_chain_config(chain).rpc_env_vars:
        value = os.getenv(env_var, "").strip()
        if value and not any(marker in value for marker in INVALID_RPC_URL_MARKERS):
            return value
    return ""


def get_wss_url(chain: str = "polygon") -> str:
    if chain != "polygon":
        return ""
    for env_var in POLYGON_WSS_ENV_VARS:
        value = os.getenv(env_var, "").strip()
        if value:
            return value
    return ""


def get_configured_executor_wallet(w3: Optional[Web3] = None) -> Optional[str]:
    private_key = os.getenv("PRIVATE_KEY", "").strip()
    if private_key and w3 is not None:
        return w3.eth.account.from_key(private_key).address
    wallet = _env_address(EXECUTOR_WALLET_ENV_VARS, None)
    if wallet:
        return Web3.to_checksum_address(wallet)
    return None


def abi_function_names(abi: Sequence[Mapping[str, Any]]) -> set[str]:
    return {item.get("name", "") for item in abi if item.get("type") == "function"}


def required_abi_function_names(config: ExecutorContractConfig) -> set[str]:
    return {signature.split("(", 1)[0] for signature in config.function_signatures.values()}


def validate_executor_registry(
    w3: Web3,
    executor_wallet: Optional[str] = None,
    strategies: Optional[Iterable[str]] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """Validate active deployed executor configs against the connected chain."""
    registry = get_executor_registry()
    strategy_names = list(strategies) if strategies else list(registry.keys())
    results: Dict[str, Any] = {}
    errors: List[str] = []

    actual_chain_id: Optional[int]
    try:
        actual_chain_id = int(w3.eth.chain_id)
    except Exception as exc:
        actual_chain_id = None
        errors.append(f"chain_id lookup failed: {exc}")

    if executor_wallet is None:
        executor_wallet = get_configured_executor_wallet(w3)
    executor_wallet_checksum = Web3.to_checksum_address(executor_wallet) if executor_wallet else None

    for strategy in strategy_names:
        config = registry[strategy]
        checks: Dict[str, Any] = {
            "strategy": strategy,
            "chain": config.chain,
            "configured_chain_id": config.chain_id,
            "actual_chain_id": actual_chain_id,
            "address": config.checksum_address(),
            "abi_identifier": config.abi_identifier,
            "deployment_status": config.deployment_status,
            "deployment_block": config.deployment_block,
            "required_permissions": list(config.required_permissions),
            "ok": True,
            "errors": [],
        }

        missing_functions = sorted(required_abi_function_names(config) - abi_function_names(config.abi))
        checks["abi_functions_present"] = not missing_functions
        checks["missing_abi_functions"] = missing_functions
        if missing_functions:
            checks["errors"].append(f"ABI missing functions: {', '.join(missing_functions)}")

        if actual_chain_id is not None and actual_chain_id != config.chain_id:
            checks["errors"].append(f"chain ID mismatch: expected {config.chain_id}, got {actual_chain_id}")

        address = config.checksum_address()
        if config.deployed:
            if not address:
                checks["errors"].append("deployed registry entry has no active address")
            else:
                try:
                    bytecode = w3.eth.get_code(address)
                    checks["bytecode_exists"] = bool(bytecode and bytecode != b"\x00")
                    checks["bytecode_size"] = len(bytecode)
                    if not checks["bytecode_exists"]:
                        checks["errors"].append("deployed bytecode is empty")
                except Exception as exc:
                    checks["bytecode_exists"] = False
                    checks["errors"].append(f"bytecode lookup failed: {exc}")

                contract = w3.eth.contract(address=address, abi=config.abi)
                try:
                    onchain_owner = contract.functions.owner().call()
                    checks["onchain_owner"] = Web3.to_checksum_address(onchain_owner)
                    expected_owner = config.owner_address
                    if expected_owner:
                        checks["expected_owner"] = Web3.to_checksum_address(expected_owner)
                        if checks["onchain_owner"] != checks["expected_owner"]:
                            checks["errors"].append("configured owner does not match on-chain owner")
                    if executor_wallet_checksum:
                        checks["executor_wallet"] = executor_wallet_checksum
                        checks["wallet_authorized"] = checks["onchain_owner"] == executor_wallet_checksum
                        if not checks["wallet_authorized"]:
                            checks["errors"].append("configured executor wallet is not authorized as owner")
                    else:
                        checks["wallet_authorized"] = False
                        checks["errors"].append("no executor wallet configured")
                except Exception as exc:
                    checks["wallet_authorized"] = False
                    checks["errors"].append(f"owner authorization check failed: {exc}")
        else:
            checks["bytecode_exists"] = False
            checks["wallet_authorized"] = False

        checks["ok"] = not checks["errors"]
        results[strategy] = checks
        errors.extend(f"{strategy}: {error}" for error in checks["errors"])

    summary = {"ok": not errors, "errors": errors, "results": results}
    if strict and errors:
        raise RuntimeError("Executor registry validation failed: " + "; ".join(errors))
    return summary
