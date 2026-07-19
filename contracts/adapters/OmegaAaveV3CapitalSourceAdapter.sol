// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {OmegaRouteSwapAdapter} from "./OmegaRouteSwapAdapter.sol";

interface IAaveV3PoolMinimal {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IAaveV3FlashLoanSimpleReceiverMinimal {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

contract OmegaAaveV3CapitalSourceAdapter is
    OmegaRouteSwapAdapter,
    IAaveV3FlashLoanSimpleReceiverMinimal
{
    error AaveCallbackSender();
    error AaveCallbackState();
    error AaveCallbackAsset();

    address public immutable aavePool;

    struct ActiveRoute {
        address asset;
        uint256 amount;
        uint256 minProfit;
        bytes32 stateHash;
        bool active;
    }

    ActiveRoute private _active;
    uint256 private _lastProfit;

    constructor(address executor_, address balancerVault_, address aavePool_)
        OmegaRouteSwapAdapter(executor_, balancerVault_)
    {
        if (aavePool_ == address(0)) revert AdapterBadAddress();
        aavePool = aavePool_;
    }

    function executeAtomic(
        address asset,
        uint256 amount,
        address[] calldata poolSequence,
        address[] calldata tokenPath,
        uint256 minProfit,
        bytes32 stateHash
    ) external onlyExecutor returns (uint256 profit) {
        if (_active.active) revert AaveCallbackState();
        if (asset == address(0) || amount == 0 || tokenPath.length < 2 || tokenPath[0] != asset) {
            revert AdapterBadRoute();
        }

        _active = ActiveRoute({
            asset: asset,
            amount: amount,
            minProfit: minProfit,
            stateHash: stateHash,
            active: true
        });
        _lastProfit = 0;

        IAaveV3PoolMinimal(aavePool).flashLoanSimple(
            address(this),
            asset,
            amount,
            abi.encode(poolSequence, tokenPath, minProfit, stateHash),
            0
        );

        profit = _lastProfit;
        delete _active;
        _lastProfit = 0;
    }

    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        if (msg.sender != aavePool) revert AaveCallbackSender();
        if (initiator != address(this)) revert AaveCallbackSender();
        if (!_active.active || asset != _active.asset || amount != _active.amount) {
            revert AaveCallbackAsset();
        }

        (
            address[] memory poolSequence,
            address[] memory tokenPath,
            uint256 minProfit,
            bytes32 stateHash
        ) = abi.decode(params, (address[], address[], uint256, bytes32));
        if (stateHash != _active.stateHash || minProfit != _active.minProfit) {
            revert AaveCallbackState();
        }

        uint256 finalAmount = _executeRoute(amount, poolSequence, tokenPath);
        uint256 repayment = amount + premium;
        if (finalAmount < repayment + minProfit) revert AdapterSlippageOrProfit();

        uint256 profit = finalAmount - repayment;
        _safeTransfer(asset, executor, profit);
        _safeApprove(asset, aavePool, 0);
        _safeApprove(asset, aavePool, repayment);
        _lastProfit = profit;
        return true;
    }
}
