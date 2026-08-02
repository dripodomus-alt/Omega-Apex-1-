#!/usr/bin/env python3
# ==============================================================================
# contract_deployments.py -- researched Chain 137 protocol infrastructure.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, field

from web3 import Web3

from .config import _env


@dataclass(frozen=True)
class Deployment:
    name: str
    env_key: str
    address: str
    role: str
    source: str
    required_for_execution: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)


DEPLOYMENTS: tuple[Deployment, ...] = (
    Deployment("Multicall3", "MULTICALL3_ADDRESS", "0xcA11bde05977b3631167028862bE2a173976CA11", "read_batcher", "mds1/multicall3"),
    Deployment("UniswapV3Factory", "UNISWAP_V3_FACTORY", "0x1F98431c8aD98523631AE4a59f267346ea31F984", "factory", "Uniswap docs"),
    Deployment("UniswapV3Quoter", "UNISWAP_V3_QUOTER", "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6", "quoter", "Uniswap docs"),
    Deployment("UniswapV3QuoterV2", "UNISWAP_V3_QUOTER_V2", "0x61fFE014bA17989E743c5F6cB21bF9697530B21e", "quoter", "Uniswap docs"),
    Deployment("UniswapV3SwapRouter", "UNISWAP_V3_SWAP_ROUTER", "0xE592427A0AEce92De3Edee1F18E0157C05861564", "router", "Uniswap docs", aliases=("UNISWAP_V3_ROUTER",)),
    Deployment("UniswapV3SwapRouter02", "UNISWAP_V3_SWAP_ROUTER_02", "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45", "router", "Uniswap docs"),
    Deployment("UniswapUniversalRouter", "UNISWAP_UNIVERSAL_ROUTER", "0x1095692A6237d83C6a72F3F5eFEdb9A670C49223", "router", "Uniswap docs"),
    Deployment("UniswapPermit2", "PERMIT2_ADDRESS", "0x000000000022D473030F116dDEE9F6B43aC78BA3", "allowance", "Uniswap docs"),
    Deployment("UniswapTickLens", "UNISWAP_V3_TICK_LENS", "0xbfd8137f7d1516D3ea5cA83523914859ec47F573", "state_reader", "Uniswap docs"),
    Deployment("QuickSwapV2Router", "QUICKSWAP_V2_ROUTER", "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff", "router", "QuickSwap docs"),
    Deployment("QuickSwapV2Factory", "QUICKSWAP_V2_FACTORY", "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32", "factory", "QuickSwap docs"),
    Deployment("QuickSwapAlgebraFactory", "QUICKSWAP_ALGEBRA_FACTORY", "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28", "factory", "QuickSwap docs", aliases=("ALGEBRA_FACTORY",)),
    Deployment("QuickSwapAlgebraQuoter", "QUICKSWAP_ALGEBRA_QUOTER", "0xa15F0D7377B2A0C0c10db057f641beD21028FC89", "quoter", "QuickSwap docs", aliases=("ALGEBRA_QUOTER",)),
    Deployment("QuickSwapAlgebraRouter", "QUICKSWAP_ALGEBRA_ROUTER", "0xf5b509bB0909a69B1c207E495f687a596C168E12", "router", "QuickSwap docs", aliases=("ALGEBRA_ROUTER",)),
    Deployment("QuickSwapAlgebraMulticall", "QUICKSWAP_ALGEBRA_MULTICALL", "0x6ccb9426CeceE2903FbD97fd833fD1D31c100292", "read_batcher", "QuickSwap docs"),
    Deployment("UniswapV4PoolManager", "UNISWAP_V4_POOL_MANAGER", "0x67366782805870060151383F4BbFF9daB53e5cD6", "pool_manager", "Uniswap v4 deployments"),
    Deployment("UniswapV4PositionManager", "UNISWAP_V4_POSITION_MANAGER", "0x1Ec2eBf4F37E7363FDfe3551602425af0B3ceef9", "position_manager", "Uniswap v4 deployments"),
    Deployment("UniswapV4Quoter", "UNISWAP_V4_QUOTER", "0xb3d5c3dfc3a7aebff71895a7191796bffc2c81b9", "quoter", "Uniswap v4 deployments"),
    Deployment("UniswapV4StateView", "UNISWAP_V4_STATE_VIEW", "0x5Ea1bD7974c8A611cBAB0bDCAfCB1D9CC9b3BA5a", "state_reader", "Uniswap v4 deployments"),
    Deployment("UniswapV4UniversalRouter", "UNISWAP_V4_UNIVERSAL_ROUTER", "0x1095692A6237d83C6a72F3F5eFEdb9A670C49223", "router", "Uniswap v4 deployments"),
    Deployment("BalancerV2Vault", "BALANCER_VAULT", "0xBA12222222228d8Ba445958a75a0704d566BF2C8", "vault", "Balancer deployments"),
    Deployment("BalancerAuthorizer", "BALANCER_AUTHORIZER", "0xA331D84eC860Bf466b4CdCcFb4aC09a1B43F3aE6", "authorizer", "Balancer deployments"),
    Deployment("CurveAddressProvider", "CURVE_ADDRESS_PROVIDER", "0x5ffe7FB82894076ECB99A30D6A32e969e6e35E98", "registry", "Curve deployments"),
    Deployment("CurveMetaRegistry", "CURVE_META_REGISTRY", "0x296d2B5C23833A70D07c8fCBB97d846c1ff90DDD", "registry", "Curve deployments"),
    Deployment("CurveStableFactory", "CURVE_STABLE_FACTORY", "0x1764ee18e8B3ccA4787249Ceb249356192594585", "factory", "Curve deployments"),
    Deployment("CurveRouter", "CURVE_ROUTER", "0x0DCDED3545D565bA3B19E683431381007245d983", "router", "Curve deployments"),
    Deployment("CurveStableCalcZap", "CURVE_STABLE_CALC_ZAP", "0xCA8d0747B5573D69653C3aC22242e6341C36e4b4", "quoter", "Curve deployments"),
    Deployment("DODOV2Proxy", "DODO_V2_PROXY", "0x45894C062E6f4E58B257e0826675355305dfef0d", "router", "DODO docs"),
    Deployment("DODORouteProxy", "DODO_ROUTE_PROXY", "0x2fA4334cfD7c56a0E7Ca02BD81455205FcBDc5E9", "router", "DODO docs"),
    Deployment("DODODVMFactory", "DODO_DVM_FACTORY", "0x79887f65f83bdf15Bcc8736b5e5BcDB48fb8fE13", "factory", "DODO docs"),
    Deployment("DODODPPFactory", "DODO_DPP_FACTORY", "0xd24153244066F0afA9415563bFC7Ba248bfB7a51", "factory", "DODO docs"),
    Deployment("DODODSPFactory", "DODO_DSP_FACTORY", "0x43C49f8DD240e1545F147211Ec9f917376Ac1e87", "factory", "DODO docs"),
)


def resolved_deployments() -> dict[str, Deployment]:
    resolved: dict[str, Deployment] = {}
    for item in DEPLOYMENTS:
        override = _env(item.env_key)
        for alias in item.aliases:
            override = override or _env(alias)
        address = override if override and Web3.is_address(override) else item.address
        resolved[item.env_key] = Deployment(
            name=item.name,
            env_key=item.env_key,
            address=Web3.to_checksum_address(address),
            role=item.role,
            source=item.source,
            required_for_execution=item.required_for_execution,
            aliases=item.aliases,
        )
    return resolved


def deployment_address(env_key: str) -> str:
    item = resolved_deployments().get(env_key)
    return item.address if item else ""


def validate_deployment_bytecode(w3) -> list[tuple[Deployment, bool, str]]:
    results: list[tuple[Deployment, bool, str]] = []
    for item in resolved_deployments().values():
        try:
            code = w3.eth.get_code(Web3.to_checksum_address(item.address)).hex()
            ok = code not in ("", "0x")
            results.append((item, ok, "bytecode present" if ok else "no bytecode"))
        except Exception as exc:
            results.append((item, False, f"{type(exc).__name__}: {exc}"))
    return results
