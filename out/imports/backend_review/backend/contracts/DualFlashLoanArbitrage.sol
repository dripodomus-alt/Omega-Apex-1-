// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

interface IBalancerVault {
    function flashLoan(
        address recipient,
        address[] memory tokens,
        uint256[] memory amounts,
        bytes memory userData
    ) external;
}

interface IFlashLoanRecipient {
    function receiveFlashLoan(
        address[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external;
}

interface IFlashLoanReceiver {
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

interface IAavePool {
    function flashLoan(
        address receiverAddress,
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata interestRateModes,
        address onBehalfOf,
        bytes calldata params,
        uint16 referralCode
    ) external;

    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
}

interface IUniswapV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    
    function exactInputSingle(ExactInputSingleParams calldata params) 
        external returns (uint256 amountOut);
}

/**
 * @title DualFlashLoanArbitrage
 * @notice Executes arbitrage using Balancer (0% fee) or Aave (0.09% fee) flash loans.
 *
 * Entry points (called by the executor wallet):
 *   initBalancerFlash(asset, amount, minProfit, deadline, params)
 *   initAaveFlash(asset, amount, minProfit, deadline, params)
 *
 * The `params` argument is abi.encode(address[] targets, bytes[] calldatas) —
 * a multicall-style list of (router, calldata) pairs that the contract executes
 * in sequence inside the flash-loan callback.
 *
 * This matches the Python InstitutionalExecutor ABI exactly, so the on-chain
 * contract and the off-chain payload builder stay in sync.
 */
contract DualFlashLoanArbitrage is Ownable, IFlashLoanRecipient, IFlashLoanReceiver {

    // Flash loan providers
    address public constant BALANCER_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address public constant AAVE_POOL = 0x794a61358D6845594F94dc1DB02A252b5b4814aD;

    // Routers
    address public constant UNISWAP_V3_ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
    address public constant QUICKSWAP_V2_ROUTER = 0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff;
    address public constant SUSHISWAP_ROUTER = 0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506;

    // Events
    event ArbitrageExecuted(
        address indexed token,
        uint256 profit,
        address provider,
        uint256 timestamp
    );

    event FlashLoanReceived(
        address indexed token,
        uint256 amount,
        address provider
    );

    constructor() Ownable(msg.sender) {}

    // =========================================================================
    // PUBLIC ENTRY POINTS  (ABI matches Python InstitutionalExecutor)
    // =========================================================================

    /**
     * @notice Initiate arbitrage via a Balancer flash loan (0% fee).
     * @param asset    Token to borrow.
     * @param amount   Amount to borrow (in token native units / wei).
     * @param minProfit Minimum profit required (in token native units).
     *                  Transaction reverts if profit < minProfit.
     * @param deadline  Unix timestamp after which the tx is invalid.
     * @param params    abi.encode(address[] targets, bytes[] calldatas) —
     *                  the sequence of router calls to execute.
     */
    function initBalancerFlash(
        address asset,
        uint256 amount,
        uint256 minProfit,
        uint256 deadline,
        bytes calldata params
    ) external onlyOwner {
        require(block.timestamp <= deadline, "Deadline exceeded");

        address[] memory tokens = new address[](1);
        tokens[0] = asset;

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;

        // Pack minProfit + deadline + params into userData for the callback
        bytes memory userData = abi.encode(minProfit, deadline, params);

        IBalancerVault(BALANCER_VAULT).flashLoan(
            address(this),
            tokens,
            amounts,
            userData
        );
    }

    /**
     * @notice Initiate arbitrage via an Aave V3 flash loan (0.09% fee).
     * @param asset    Token to borrow.
     * @param amount   Amount to borrow (in token native units / wei).
     * @param minProfit Minimum profit required (in token native units).
     * @param deadline  Unix timestamp after which the tx is invalid.
     * @param params    abi.encode(address[] targets, bytes[] calldatas).
     */
    function initAaveFlash(
        address asset,
        uint256 amount,
        uint256 minProfit,
        uint256 deadline,
        bytes calldata params
    ) external onlyOwner {
        _executeAaveArbitrage(asset, amount, minProfit, deadline, params);
    }

    /**
     * @notice Initiate arbitrage via an Aave V3 flash loan (0.09% fee).
     * @dev Backwards-compatible named entry point for executors that call
     *      executeAaveArbitrage directly. Aave calls executeOperation below.
     */
    function executeAaveArbitrage(
        address asset,
        uint256 amount,
        uint256 minProfit,
        uint256 deadline,
        bytes calldata params
    ) external onlyOwner {
        _executeAaveArbitrage(asset, amount, minProfit, deadline, params);
    }

    function _executeAaveArbitrage(
        address asset,
        uint256 amount,
        uint256 minProfit,
        uint256 deadline,
        bytes calldata params
    ) internal {
        require(block.timestamp <= deadline, "Deadline exceeded");

        address[] memory assets = new address[](1);
        assets[0] = asset;

        uint256[] memory amounts = new uint256[](1);
        amounts[0] = amount;

        uint256[] memory modes = new uint256[](1);
        modes[0] = 0; // No debt mode — reverts if not repaid within the tx

        bytes memory userData = abi.encode(minProfit, deadline, params);

        // Aave V3 flash-loan request. The Pool transfers funds, then invokes
        // executeOperation on this contract as the callback in the same tx.
        IAavePool(AAVE_POOL).flashLoan(
            address(this),
            assets,
            amounts,
            modes,
            address(this),
            userData,
            0
        );
    }

    // =========================================================================
    // FLASH LOAN CALLBACKS
    // =========================================================================

    /**
     * @notice Balancer callback — receives the loan, executes swaps, repays.
     */
    function receiveFlashLoan(
        address[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == BALANCER_VAULT, "Only Balancer Vault");

        emit FlashLoanReceived(tokens[0], amounts[0], BALANCER_VAULT);

        (uint256 minProfit, uint256 deadline, bytes memory params) =
            abi.decode(userData, (uint256, uint256, bytes));

        require(block.timestamp <= deadline, "Deadline exceeded");

        uint256 finalAmount = _executeMulticall(params);

        // Balancer fee is 0
        uint256 repayAmount = amounts[0] + feeAmounts[0];
        require(finalAmount >= repayAmount, "Insufficient output");
        uint256 profit = finalAmount - repayAmount;
        require(profit >= minProfit, "Profit too low");

        IERC20(tokens[0]).transfer(BALANCER_VAULT, repayAmount);
        IERC20(tokens[0]).transfer(owner(), profit);

        emit ArbitrageExecuted(tokens[0], profit, BALANCER_VAULT, block.timestamp);
    }

    /**
     * @notice Aave callback — receives the loan, executes swaps, repays.
     */
    function executeOperation(
        address[] calldata assets,
        uint256[] calldata amounts,
        uint256[] calldata premiums,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == AAVE_POOL, "Only Aave Pool");
        require(initiator == address(this), "Invalid initiator");

        emit FlashLoanReceived(assets[0], amounts[0], AAVE_POOL);

        (uint256 minProfit, uint256 deadline, bytes memory swapParams) =
            abi.decode(params, (uint256, uint256, bytes));

        require(block.timestamp <= deadline, "Deadline exceeded");

        uint256 finalAmount = _executeMulticall(swapParams);

        // Aave fee = amounts[0] * 0.0009
        uint256 repayAmount = amounts[0] + premiums[0];
        require(finalAmount >= repayAmount, "Insufficient output");
        uint256 profit = finalAmount - repayAmount;
        require(profit >= minProfit, "Profit too low");

        IERC20(assets[0]).approve(AAVE_POOL, repayAmount);
        IERC20(assets[0]).transfer(owner(), profit);

        emit ArbitrageExecuted(assets[0], profit, AAVE_POOL, block.timestamp);

        return true;
    }

    // =========================================================================
    // INTERNAL HELPERS
    // =========================================================================

    /**
     * @notice Execute a multicall sequence encoded as (address[] targets, bytes[] calldatas).
     * @return finalAmount Balance of the last tokenOut after all calls complete.
     *
     * The caller is responsible for encoding calldatas with the correct router
     * selectors and ABI-encoded parameters (swapExactTokensForTokens / exactInputSingle).
     */
    function _executeMulticall(bytes memory params) internal returns (uint256 finalAmount) {
        (address[] memory targets, bytes[] memory calldatas) =
            abi.decode(params, (address[], bytes[]));

        require(targets.length == calldatas.length, "Mismatched targets/calldatas");
        require(targets.length > 0, "No swap targets");

        for (uint256 i = 0; i < targets.length; i++) {
            (bool success, ) = targets[i].call(calldatas[i]);
            require(success, "Swap call failed");
        }

        // Return the contract's balance of the borrowed token (token0 of the first leg).
        // The profit check in the caller verifies this covers repayment + minProfit.
        // We decode the first calldata to extract tokenIn so we can query its balance.
        // Fallback: return 0 and let the repayment check catch any shortfall.
        finalAmount = _getResultBalance(targets, calldatas);
    }

    /**
     * @notice Read the post-swap balance of the output token of the last leg.
     *         Decodes the last calldata to find tokenOut for V2 or V3 swaps.
     */
    function _getResultBalance(
        address[] memory targets,
        bytes[] memory calldatas
    ) internal view returns (uint256) {
        // Attempt to decode the last calldata to find the output token.
        bytes memory lastCalldata = calldatas[calldatas.length - 1];
        if (lastCalldata.length < 4) return 0;

        bytes4 selector;
        assembly { selector := mload(add(lastCalldata, 32)) }

        // swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
        bytes4 v2Selector = bytes4(keccak256("swapExactTokensForTokens(uint256,uint256,address[],address,uint256)"));
        // exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))
        bytes4 v3Selector = bytes4(keccak256("exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))"));

        if (selector == v2Selector) {
            // Decode: skip selector (4 bytes), amountIn (32), amountOutMin (32),
            // then dynamic path array. tokenOut = path[path.length-1].
            (, , address[] memory path, , ) = abi.decode(
                _stripSelector(lastCalldata),
                (uint256, uint256, address[], address, uint256)
            );
            if (path.length > 0) {
                return IERC20(path[path.length - 1]).balanceOf(address(this));
            }
        } else if (selector == v3Selector) {
            // Decode the ExactInputSingleParams tuple: (tokenIn, tokenOut, fee, recipient, ...)
            (address tokenIn, address tokenOut, , , , , ,) = abi.decode(
                _stripSelector(lastCalldata),
                (address, address, uint24, address, uint256, uint256, uint256, uint160)
            );
            return IERC20(tokenOut).balanceOf(address(this));
        }

        return 0;
    }

    /// @dev Remove the 4-byte function selector from calldata for abi.decode.
    function _stripSelector(bytes memory data) internal pure returns (bytes memory) {
        bytes memory stripped = new bytes(data.length - 4);
        for (uint256 i = 4; i < data.length; i++) {
            stripped[i - 4] = data[i];
        }
        return stripped;
    }

    // =========================================================================
    // ADMIN
    // =========================================================================

    /**
     * @notice Emergency withdraw any ERC-20 stuck in the contract.
     */
    function withdraw(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        IERC20(token).transfer(owner(), balance);
    }

    /**
     * @notice Receive ETH (needed for gas refunds etc.)
     */
    receive() external payable {}
}
