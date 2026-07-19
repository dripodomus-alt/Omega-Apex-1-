// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {OmegaRouteSwapAdapter, IERC20Minimal} from "./OmegaRouteSwapAdapter.sol";

interface IAaveV3PoolLiquidationMinimal {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;

    function liquidationCall(
        address collateralAsset,
        address debtAsset,
        address user,
        uint256 debtToCover,
        bool receiveAToken
    ) external;
}

interface IAaveV3LiquidationFlashReceiverMinimal {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

contract OmegaAaveV3LiquidationAdapter is
    OmegaRouteSwapAdapter,
    IAaveV3LiquidationFlashReceiverMinimal
{
    error LiquidationCallbackSender();
    error LiquidationCallbackState();
    error LiquidationCallbackAsset();
    error LiquidationBadParams();

    address public immutable aavePool;

    struct ActiveLiquidation {
        address borrower;
        address collateralAsset;
        address debtAsset;
        uint256 debtToCover;
        uint256 minProfit;
        bytes32 stateHash;
        bool active;
    }

    struct CallbackParams {
        address borrower;
        address collateralAsset;
        address debtAsset;
        address[] exitPoolSequence;
        address[] exitTokenPath;
        uint256 minProfit;
        bytes32 stateHash;
    }

    ActiveLiquidation private _active;
    uint256 private _lastProfit;

    constructor(address executor_, address balancerVault_, address aavePool_)
        OmegaRouteSwapAdapter(executor_, balancerVault_)
    {
        if (aavePool_ == address(0)) revert AdapterBadAddress();
        aavePool = aavePool_;
    }

    function executeLiquidation(
        address borrower,
        address collateralAsset,
        address debtAsset,
        uint256 debtToCover,
        address[] calldata exitPoolSequence,
        address[] calldata exitTokenPath,
        uint256 minProfit,
        bytes32 stateHash
    ) external onlyExecutor returns (uint256 profit) {
        if (_active.active) revert LiquidationCallbackState();
        if (
            borrower == address(0) || collateralAsset == address(0) || debtAsset == address(0)
                || debtToCover == 0
        ) {
            revert LiquidationBadParams();
        }
        if (collateralAsset != debtAsset) {
            if (exitTokenPath.length < 2 || exitTokenPath[0] != collateralAsset) {
                revert AdapterBadRoute();
            }
            if (exitTokenPath[exitTokenPath.length - 1] != debtAsset) revert AdapterBadRoute();
            if (exitPoolSequence.length + 1 != exitTokenPath.length) revert AdapterBadRoute();
        }

        _active = ActiveLiquidation({
            borrower: borrower,
            collateralAsset: collateralAsset,
            debtAsset: debtAsset,
            debtToCover: debtToCover,
            minProfit: minProfit,
            stateHash: stateHash,
            active: true
        });
        _lastProfit = 0;

        IAaveV3PoolLiquidationMinimal(aavePool).flashLoanSimple(
            address(this),
            debtAsset,
            debtToCover,
            abi.encode(borrower, collateralAsset, debtAsset, exitPoolSequence, exitTokenPath, minProfit, stateHash),
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
        if (msg.sender != aavePool) revert LiquidationCallbackSender();
        if (initiator != address(this)) revert LiquidationCallbackSender();
        if (!_active.active || asset != _active.debtAsset || amount != _active.debtToCover) {
            revert LiquidationCallbackAsset();
        }

        CallbackParams memory decoded = _decodeCallback(params);
        _executeLiquidationCallback(amount, premium, decoded);
        return true;
    }

    function _decodeCallback(bytes calldata params) private pure returns (CallbackParams memory decoded) {
        (
            decoded.borrower,
            decoded.collateralAsset,
            decoded.debtAsset,
            decoded.exitPoolSequence,
            decoded.exitTokenPath,
            decoded.minProfit,
            decoded.stateHash
        ) = abi.decode(params, (address, address, address, address[], address[], uint256, bytes32));
    }

    function _executeLiquidationCallback(
        uint256 amount,
        uint256 premium,
        CallbackParams memory decoded
    ) private {
        if (
            decoded.borrower != _active.borrower || decoded.collateralAsset != _active.collateralAsset
                || decoded.debtAsset != _active.debtAsset || decoded.minProfit != _active.minProfit
                || decoded.stateHash != _active.stateHash
        ) {
            revert LiquidationCallbackState();
        }

        uint256 collateralBefore = IERC20Minimal(decoded.collateralAsset).balanceOf(address(this));
        _safeApprove(decoded.debtAsset, aavePool, 0);
        _safeApprove(decoded.debtAsset, aavePool, amount);
        IAaveV3PoolLiquidationMinimal(aavePool).liquidationCall(
            decoded.collateralAsset,
            decoded.debtAsset,
            decoded.borrower,
            amount,
            false
        );
        uint256 seized = IERC20Minimal(decoded.collateralAsset).balanceOf(address(this)) - collateralBefore;
        if (seized == 0) revert AdapterSlippageOrProfit();

        uint256 finalDebtAsset = decoded.collateralAsset == decoded.debtAsset
            ? seized
            : _executeRoute(seized, decoded.exitPoolSequence, decoded.exitTokenPath);

        uint256 repayment = amount + premium;
        if (finalDebtAsset < repayment + decoded.minProfit) revert AdapterSlippageOrProfit();

        uint256 profit = finalDebtAsset - repayment;
        _safeTransfer(decoded.debtAsset, executor, profit);
        _safeApprove(decoded.debtAsset, aavePool, 0);
        _safeApprove(decoded.debtAsset, aavePool, repayment);
        _lastProfit = profit;
    }
}
