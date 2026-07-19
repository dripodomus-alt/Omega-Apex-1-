// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface ILiquidationAdapter {
    function executeLiquidation(
        address borrower,
        address collateralAsset,
        address debtAsset,
        uint256 debtToCover,
        address[] calldata exitPoolSequence,
        address[] calldata exitTokenPath,
        uint256 minProfit,
        bytes32 stateHash
    ) external returns (uint256 profit);
}

interface IERC20Recoverable {
    function transfer(address to, uint256 value) external returns (bool);
}

/// @title OmegaLiquidationExecutor
/// @notice Guarded C1/C2 execution boundary for scanner-produced Aave liquidation packets.
contract OmegaLiquidationExecutor {
    error NotOwner();
    error NotKeeper();
    error Paused();
    error Reentrant();
    error BadAddress();
    error BadRoute();
    error BadRisk();
    error Expired();
    error GasTooHigh();
    error NonceUsed(bytes32 nonce);
    error AdapterUnset();
    error ProfitTooLow(uint256 profit, uint256 minProfit);
    error TransferFailed();

    struct LiquidationParams {
        address borrower;
        address collateralAsset;
        address debtAsset;
        uint256 debtToCover;
        address[] exitPoolSequence;
        address[] exitTokenPath;
        uint256 minProfit;
        uint256 maxFeePerGas;
        uint256 deadlineBlock;
        bytes32 nonce;
        bytes32 stateHash;
    }

    address public owner;
    address public pendingOwner;
    address public liquidationAdapter;
    bool public paused;
    bool private _entered;

    uint256 public minProfitWei;
    uint256 public maxDebtToCover;
    uint256 public maxFeePerGas;
    uint256 public maxExitPools;

    mapping(address => bool) public keeper;
    mapping(bytes32 => bool) public usedNonce;

    event OwnershipTransferStarted(address indexed previousOwner, address indexed pendingOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event KeeperSet(address indexed keeper, bool allowed);
    event PausedSet(bool paused);
    event LiquidationAdapterSet(address indexed adapter);
    event RiskLimitsSet(
        uint256 minProfitWei,
        uint256 maxDebtToCover,
        uint256 maxFeePerGas,
        uint256 maxExitPools
    );
    event LiquidationExecuted(
        bytes32 indexed executionId,
        address indexed borrower,
        address indexed debtAsset,
        address collateralAsset,
        uint256 debtToCover,
        uint256 profit,
        bytes32 nonce,
        bytes32 stateHash
    );
    event LiquidationC2Decision(
        bytes32 indexed parentExecutionId,
        bytes32 indexed executionId,
        uint8 action,
        uint256 profit,
        bytes32 nonce
    );
    event TokenRecovered(address indexed token, address indexed to, uint256 amount);

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyKeeper() {
        if (msg.sender != owner && !keeper[msg.sender]) revert NotKeeper();
        _;
    }

    modifier whenNotPaused() {
        if (paused) revert Paused();
        _;
    }

    modifier nonReentrant() {
        if (_entered) revert Reentrant();
        _entered = true;
        _;
        _entered = false;
    }

    constructor(address owner_, address liquidationAdapter_) {
        if (owner_ == address(0)) revert BadAddress();
        owner = owner_;
        keeper[owner_] = true;
        maxExitPools = 4;
        maxFeePerGas = 250 gwei;
        if (liquidationAdapter_ != address(0)) {
            liquidationAdapter = liquidationAdapter_;
            emit LiquidationAdapterSet(liquidationAdapter_);
        }
        emit OwnershipTransferred(address(0), owner_);
        emit KeeperSet(owner_, true);
        emit RiskLimitsSet(minProfitWei, maxDebtToCover, maxFeePerGas, maxExitPools);
    }

    function transferOwnership(address nextOwner) external onlyOwner {
        if (nextOwner == address(0)) revert BadAddress();
        pendingOwner = nextOwner;
        emit OwnershipTransferStarted(owner, nextOwner);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotOwner();
        address previous = owner;
        owner = pendingOwner;
        pendingOwner = address(0);
        keeper[owner] = true;
        emit OwnershipTransferred(previous, owner);
        emit KeeperSet(owner, true);
    }

    function setKeeper(address keeper_, bool allowed) external onlyOwner {
        if (keeper_ == address(0)) revert BadAddress();
        keeper[keeper_] = allowed;
        emit KeeperSet(keeper_, allowed);
    }

    function setPaused(bool paused_) external onlyOwner {
        paused = paused_;
        emit PausedSet(paused_);
    }

    function setLiquidationAdapter(address adapter_) external onlyOwner {
        if (adapter_ == address(0)) revert BadAddress();
        liquidationAdapter = adapter_;
        emit LiquidationAdapterSet(adapter_);
    }

    function setRiskLimits(
        uint256 minProfitWei_,
        uint256 maxDebtToCover_,
        uint256 maxFeePerGas_,
        uint256 maxExitPools_
    ) external onlyOwner {
        if (maxExitPools_ == 0 || maxExitPools_ > 8) revert BadRisk();
        minProfitWei = minProfitWei_;
        maxDebtToCover = maxDebtToCover_;
        maxFeePerGas = maxFeePerGas_;
        maxExitPools = maxExitPools_;
        emit RiskLimitsSet(minProfitWei_, maxDebtToCover_, maxFeePerGas_, maxExitPools_);
    }

    function executeLiquidation(LiquidationParams calldata params)
        external
        onlyKeeper
        whenNotPaused
        nonReentrant
        returns (bytes32 executionId, uint256 profit)
    {
        (executionId, profit) = _execute(params);
        emit LiquidationExecuted(
            executionId,
            params.borrower,
            params.debtAsset,
            params.collateralAsset,
            params.debtToCover,
            profit,
            params.nonce,
            params.stateHash
        );
    }

    function executeLiquidationC2(
        bytes32 parentExecutionId,
        uint8 action,
        LiquidationParams calldata params
    ) external onlyKeeper whenNotPaused nonReentrant returns (bytes32 executionId, uint256 profit) {
        if (action == 0) {
            executionId = keccak256(abi.encode(parentExecutionId, action, params.nonce, block.number));
            emit LiquidationC2Decision(parentExecutionId, executionId, action, 0, params.nonce);
            return (executionId, 0);
        }
        (executionId, profit) = _execute(params);
        emit LiquidationC2Decision(parentExecutionId, executionId, action, profit, params.nonce);
    }

    function recoverToken(address token, address to, uint256 amount) external onlyOwner {
        if (token == address(0) || to == address(0)) revert BadAddress();
        (bool ok, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Recoverable.transfer.selector, to, amount));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert TransferFailed();
        emit TokenRecovered(token, to, amount);
    }

    function _execute(LiquidationParams calldata params)
        private
        returns (bytes32 executionId, uint256 profit)
    {
        _validate(params);
        usedNonce[params.nonce] = true;
        profit = ILiquidationAdapter(liquidationAdapter).executeLiquidation(
            params.borrower,
            params.collateralAsset,
            params.debtAsset,
            params.debtToCover,
            params.exitPoolSequence,
            params.exitTokenPath,
            params.minProfit,
            params.stateHash
        );
        if (profit < params.minProfit || profit < minProfitWei) {
            revert ProfitTooLow(profit, params.minProfit > minProfitWei ? params.minProfit : minProfitWei);
        }
        executionId = keccak256(
            abi.encode(
                block.chainid,
                address(this),
                params.borrower,
                params.collateralAsset,
                params.debtAsset,
                params.debtToCover,
                params.nonce,
                params.stateHash
            )
        );
    }

    function _validate(LiquidationParams calldata params) private view {
        if (liquidationAdapter == address(0)) revert AdapterUnset();
        if (
            params.borrower == address(0) || params.collateralAsset == address(0)
                || params.debtAsset == address(0)
        ) {
            revert BadAddress();
        }
        if (params.debtToCover == 0 || params.nonce == bytes32(0)) revert BadRisk();
        if (maxDebtToCover != 0 && params.debtToCover > maxDebtToCover) revert BadRisk();
        if (params.deadlineBlock < block.number) revert Expired();
        if (params.maxFeePerGas == 0 || tx.gasprice > params.maxFeePerGas) revert GasTooHigh();
        if (maxFeePerGas != 0 && tx.gasprice > maxFeePerGas) revert GasTooHigh();
        if (usedNonce[params.nonce]) revert NonceUsed(params.nonce);

        if (params.collateralAsset == params.debtAsset) {
            if (params.exitPoolSequence.length != 0 || params.exitTokenPath.length != 0) {
                revert BadRoute();
            }
            return;
        }
        if (
            params.exitPoolSequence.length == 0
                || params.exitPoolSequence.length > maxExitPools
                || params.exitTokenPath.length != params.exitPoolSequence.length + 1
                || params.exitTokenPath[0] != params.collateralAsset
                || params.exitTokenPath[params.exitTokenPath.length - 1] != params.debtAsset
        ) {
            revert BadRoute();
        }
        for (uint256 i = 0; i < params.exitPoolSequence.length; ++i) {
            if (params.exitPoolSequence[i] == address(0)) revert BadRoute();
            if (params.exitTokenPath[i] == address(0) || params.exitTokenPath[i + 1] == address(0)) {
                revert BadRoute();
            }
        }
    }
}
