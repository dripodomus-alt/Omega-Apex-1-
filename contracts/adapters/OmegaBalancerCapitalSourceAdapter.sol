// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {OmegaRouteSwapAdapter, IERC20Minimal} from "./OmegaRouteSwapAdapter.sol";

interface IBalancerFlashVaultMinimal {
    function flashLoan(
        address recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;
}

interface IBalancerFlashLoanRecipientMinimal {
    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external;
}

contract OmegaBalancerCapitalSourceAdapter is
    OmegaRouteSwapAdapter,
    IBalancerFlashLoanRecipientMinimal
{
    error BalancerCallbackSender();
    error BalancerCallbackState();
    error BalancerCallbackAsset();

    struct ActiveRoute {
        address asset;
        uint256 amount;
        uint256 minProfit;
        bytes32 stateHash;
        bool active;
    }

    ActiveRoute private _active;
    uint256 private _lastProfit;

    constructor(address executor_, address balancerVault_)
        OmegaRouteSwapAdapter(executor_, balancerVault_)
    {}

    function executeAtomic(
        address asset,
        uint256 amount,
        address[] calldata poolSequence,
        address[] calldata tokenPath,
        uint256 minProfit,
        bytes32 stateHash
    ) external onlyExecutor returns (uint256 profit) {
        if (_active.active) revert BalancerCallbackState();
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

        address[] memory tokens = new address[](1);
        tokens[0] = asset;
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;

        IBalancerFlashVaultMinimal(balancerVault).flashLoan(
            address(this),
            tokens,
            amounts,
            abi.encode(poolSequence, tokenPath, minProfit, stateHash)
        );

        profit = _lastProfit;
        delete _active;
        _lastProfit = 0;
    }

    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external override {
        if (msg.sender != balancerVault) revert BalancerCallbackSender();
        if (!_active.active || tokens.length != 1 || amounts.length != 1 || feeAmounts.length != 1) {
            revert BalancerCallbackState();
        }
        if (tokens[0] != _active.asset || amounts[0] != _active.amount) revert BalancerCallbackAsset();

        (
            address[] memory poolSequence,
            address[] memory tokenPath,
            uint256 minProfit,
            bytes32 stateHash
        ) = abi.decode(userData, (address[], address[], uint256, bytes32));
        if (stateHash != _active.stateHash || minProfit != _active.minProfit) {
            revert BalancerCallbackState();
        }

        uint256 finalAmount = _executeRoute(amounts[0], poolSequence, tokenPath);
        uint256 repayment = amounts[0] + feeAmounts[0];
        if (finalAmount < repayment + minProfit) revert AdapterSlippageOrProfit();

        uint256 profit = finalAmount - repayment;
        _safeTransfer(tokens[0], executor, profit);
        _safeTransfer(tokens[0], balancerVault, repayment);
        _lastProfit = profit;
    }
}
