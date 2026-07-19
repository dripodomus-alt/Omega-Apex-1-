// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {OmegaRouteSwapAdapter, IERC20Minimal} from "./OmegaRouteSwapAdapter.sol";

interface IBalancerV3VaultMinimal {
    function unlock(bytes calldata data) external returns (bytes memory result);
    function sendTo(IERC20Minimal token, address to, uint256 amount) external;
    function settle(IERC20Minimal token, uint256 amountHint) external returns (uint256 credit);
}

contract OmegaBalancerV3CapitalSourceAdapter is OmegaRouteSwapAdapter {
    error BalancerV3CallbackSender();
    error BalancerV3CallbackState();
    error BalancerV3CallbackAsset();

    struct ActiveRoute {
        address asset;
        uint256 amount;
        uint256 minProfit;
        bytes32 stateHash;
        bool active;
    }

    ActiveRoute private _active;
    uint256 private _lastProfit;

    constructor(address executor_, address balancerV3Vault_)
        OmegaRouteSwapAdapter(executor_, balancerV3Vault_)
    {}

    function executeAtomic(
        address asset,
        uint256 amount,
        address[] calldata poolSequence,
        address[] calldata tokenPath,
        uint256 minProfit,
        bytes32 stateHash
    ) external onlyExecutor returns (uint256 profit) {
        if (_active.active) revert BalancerV3CallbackState();
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

        IBalancerV3VaultMinimal(balancerVault).unlock(
            abi.encodeWithSelector(
                this.receiveUnlocked.selector,
                abi.encode(poolSequence, tokenPath, minProfit, stateHash)
            )
        );

        profit = _lastProfit;
        delete _active;
        _lastProfit = 0;
    }

    function receiveUnlocked(bytes calldata userData) external {
        if (msg.sender != balancerVault) revert BalancerV3CallbackSender();
        if (!_active.active) revert BalancerV3CallbackState();

        (
            address[] memory poolSequence,
            address[] memory tokenPath,
            uint256 minProfit,
            bytes32 stateHash
        ) = abi.decode(userData, (address[], address[], uint256, bytes32));
        if (stateHash != _active.stateHash || minProfit != _active.minProfit) {
            revert BalancerV3CallbackState();
        }
        if (tokenPath.length < 2 || tokenPath[0] != _active.asset) {
            revert BalancerV3CallbackAsset();
        }

        IERC20Minimal loanToken = IERC20Minimal(_active.asset);
        IBalancerV3VaultMinimal(balancerVault).sendTo(loanToken, address(this), _active.amount);

        uint256 finalAmount = _executeRoute(_active.amount, poolSequence, tokenPath);
        uint256 repayment = _active.amount;
        if (finalAmount < repayment + minProfit) revert AdapterSlippageOrProfit();

        uint256 profit = finalAmount - repayment;
        _safeTransfer(_active.asset, balancerVault, repayment);
        IBalancerV3VaultMinimal(balancerVault).settle(loanToken, repayment);
        _safeTransfer(_active.asset, executor, profit);
        _lastProfit = profit;
    }
}
