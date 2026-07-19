// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Minimal {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function approve(address spender, uint256 value) external returns (bool);
}

interface IUniswapV2PairMinimal {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32);
    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes calldata data) external;
}

interface IUniswapV3PoolMinimal {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function fee() external view returns (uint24);
    function swap(
        address recipient,
        bool zeroForOne,
        int256 amountSpecified,
        uint160 sqrtPriceLimitX96,
        bytes calldata data
    ) external returns (int256 amount0, int256 amount1);
}

interface IUniswapV3SwapCallback {
    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data)
        external;
}

interface IAlgebraPoolMinimal {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function globalState()
        external
        view
        returns (
            uint160 price,
            int24 tick,
            uint16 lastFee,
            uint8 pluginConfig,
            uint16 communityFee,
            bool unlocked
        );
    function swap(
        address recipient,
        bool zeroToOne,
        int256 amountRequired,
        uint160 limitSqrtPrice,
        bytes calldata data
    ) external returns (int256 amount0, int256 amount1);
}

interface IAlgebraSwapCallback {
    function algebraSwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data)
        external;
}

interface ICurvePoolMinimal {
    function coins(uint256 i) external view returns (address);
    function exchange(int128 i, int128 j, uint256 dx, uint256 minDy) external returns (uint256);
}

interface IBalancerVaultMinimal {
    enum SwapKind {
        GIVEN_IN,
        GIVEN_OUT
    }

    struct SingleSwap {
        bytes32 poolId;
        SwapKind kind;
        address assetIn;
        address assetOut;
        uint256 amount;
        bytes userData;
    }

    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address payable recipient;
        bool toInternalBalance;
    }

    function swap(
        SingleSwap calldata singleSwap,
        FundManagement calldata funds,
        uint256 limit,
        uint256 deadline
    ) external payable returns (uint256 amountCalculated);
}

interface IBalancerPoolMinimal {
    function getPoolId() external view returns (bytes32);
}

abstract contract OmegaRouteSwapAdapter is IUniswapV3SwapCallback {
    error AdapterNotOwner();
    error AdapterNotExecutor();
    error AdapterBadAddress();
    error AdapterBadRoute();
    error AdapterBadPoolKind();
    error AdapterPoolKindUnset(address pool);
    error AdapterUnsupportedPool(address pool);
    error AdapterSlippageOrProfit();
    error AdapterCallbackSender();
    error AdapterCallbackToken();
    error AdapterTransferFailed();
    error AdapterAmountTooLarge();

    uint160 internal constant MIN_SQRT_RATIO_PLUS_ONE = 4_295_128_740;
    uint160 internal constant MAX_SQRT_RATIO_MINUS_ONE =
        1_461_446_703_485_210_103_287_273_052_203_988_822_378_723_970_341;

    address public immutable executor;
    address public immutable balancerVault;
    address public owner;

    enum RoutePoolKind {
        UNSET,
        V2_CPMM,
        V3_CLMM,
        ALGEBRA_CLMM,
        CURVE_STABLE,
        BALANCER_WEIGHTED
    }

    mapping(address => RoutePoolKind) public routePoolKind;
    bool public routePoolKindEnforced = true;

    address private _v3CallbackPool;
    address private _v3CallbackTokenIn;

    event RoutePoolKindConfigured(address indexed pool, RoutePoolKind kind);
    event RoutePoolKindEnforcementSet(bool enforced);
    event AdapterOwnershipTransferred(address indexed previousOwner, address indexed nextOwner);

    modifier onlyOwner() {
        if (msg.sender != owner) revert AdapterNotOwner();
        _;
    }

    modifier onlyExecutor() {
        if (msg.sender != executor) revert AdapterNotExecutor();
        _;
    }

    constructor(address executor_, address balancerVault_) {
        if (executor_ == address(0) || balancerVault_ == address(0)) revert AdapterBadAddress();
        executor = executor_;
        balancerVault = balancerVault_;
        owner = msg.sender;
    }

    function transferOwnership(address nextOwner) external onlyOwner {
        if (nextOwner == address(0)) revert AdapterBadAddress();
        emit AdapterOwnershipTransferred(owner, nextOwner);
        owner = nextOwner;
    }

    function setRoutePoolKindEnforced(bool enforced) external onlyOwner {
        routePoolKindEnforced = enforced;
        emit RoutePoolKindEnforcementSet(enforced);
    }

    function configureRoutePoolKinds(address[] calldata pools, RoutePoolKind[] calldata kinds)
        external
        onlyOwner
    {
        if (pools.length != kinds.length) revert AdapterBadRoute();
        for (uint256 i = 0; i < pools.length; ++i) {
            if (pools[i] == address(0)) revert AdapterBadAddress();
            if (uint8(kinds[i]) > uint8(RoutePoolKind.BALANCER_WEIGHTED)) {
                revert AdapterBadPoolKind();
            }
            routePoolKind[pools[i]] = kinds[i];
            emit RoutePoolKindConfigured(pools[i], kinds[i]);
        }
    }

    function recoverToken(address token, address to, uint256 amount) external onlyOwner {
        if (token == address(0) || to == address(0)) revert AdapterBadAddress();
        _safeTransfer(token, to, amount);
    }

    function _executeRoute(
        uint256 amountIn,
        address[] memory poolSequence,
        address[] memory tokenPath
    ) internal returns (uint256 amountOut) {
        if (poolSequence.length == 0 || tokenPath.length != poolSequence.length + 1) {
            revert AdapterBadRoute();
        }

        amountOut = amountIn;
        for (uint256 i = 0; i < poolSequence.length; ++i) {
            address pool = poolSequence[i];
            address tokenIn = tokenPath[i];
            address tokenOut = tokenPath[i + 1];
            if (pool == address(0) || tokenIn == address(0) || tokenOut == address(0)) {
                revert AdapterBadRoute();
            }
            if (tokenIn == tokenOut || amountOut == 0) revert AdapterBadRoute();

            RoutePoolKind kind = _effectiveRoutePoolKind(pool);
            if (kind == RoutePoolKind.BALANCER_WEIGHTED) {
                amountOut = _swapBalancer(pool, tokenIn, tokenOut, amountOut);
            } else if (kind == RoutePoolKind.CURVE_STABLE) {
                amountOut = _swapCurve(pool, tokenIn, tokenOut, amountOut);
            } else if (kind == RoutePoolKind.ALGEBRA_CLMM) {
                amountOut = _swapAlgebra(pool, tokenIn, tokenOut, amountOut);
            } else if (kind == RoutePoolKind.V3_CLMM) {
                amountOut = _swapV3(pool, tokenIn, tokenOut, amountOut);
            } else if (kind == RoutePoolKind.V2_CPMM) {
                amountOut = _swapV2(pool, tokenIn, tokenOut, amountOut);
            } else {
                revert AdapterUnsupportedPool(pool);
            }
        }
    }

    function _swapV2(address pool, address tokenIn, address tokenOut, uint256 amountIn)
        internal
        returns (uint256 amountOut)
    {
        IUniswapV2PairMinimal pair = IUniswapV2PairMinimal(pool);
        address token0 = pair.token0();
        address token1 = pair.token1();
        if (!((tokenIn == token0 && tokenOut == token1) || (tokenIn == token1 && tokenOut == token0))) {
            revert AdapterBadRoute();
        }

        (uint112 reserve0, uint112 reserve1,) = pair.getReserves();
        (uint256 reserveIn, uint256 reserveOut) =
            tokenIn == token0 ? (uint256(reserve0), uint256(reserve1)) : (uint256(reserve1), uint256(reserve0));
        if (reserveIn == 0 || reserveOut == 0) revert AdapterBadRoute();

        uint256 amountInWithFee = amountIn * 997;
        amountOut = (amountInWithFee * reserveOut) / ((reserveIn * 1000) + amountInWithFee);
        if (amountOut == 0) revert AdapterSlippageOrProfit();

        _safeTransfer(tokenIn, pool, amountIn);
        (uint256 amount0Out, uint256 amount1Out) =
            tokenIn == token0 ? (uint256(0), amountOut) : (amountOut, uint256(0));
        pair.swap(amount0Out, amount1Out, address(this), "");
    }

    function _swapV3(address pool, address tokenIn, address tokenOut, uint256 amountIn)
        internal
        returns (uint256 amountOut)
    {
        IUniswapV3PoolMinimal v3 = IUniswapV3PoolMinimal(pool);
        address token0 = v3.token0();
        address token1 = v3.token1();
        if (!((tokenIn == token0 && tokenOut == token1) || (tokenIn == token1 && tokenOut == token0))) {
            revert AdapterBadRoute();
        }

        bool zeroForOne = tokenIn == token0;
        uint256 balanceBefore = IERC20Minimal(tokenOut).balanceOf(address(this));
        if (amountIn > uint256(type(int256).max)) revert AdapterAmountTooLarge();
        _v3CallbackPool = pool;
        _v3CallbackTokenIn = tokenIn;
        v3.swap(
            address(this),
            zeroForOne,
            // forge-lint: disable-next-line(unsafe-typecast)
            int256(amountIn),
            zeroForOne ? MIN_SQRT_RATIO_PLUS_ONE : MAX_SQRT_RATIO_MINUS_ONE,
            abi.encode(tokenIn)
        );
        _v3CallbackPool = address(0);
        _v3CallbackTokenIn = address(0);
        amountOut = IERC20Minimal(tokenOut).balanceOf(address(this)) - balanceBefore;
        if (amountOut == 0) revert AdapterSlippageOrProfit();
    }

    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data)
        external
        override
    {
        if (msg.sender != _v3CallbackPool) revert AdapterCallbackSender();
        address tokenIn = abi.decode(data, (address));
        if (tokenIn != _v3CallbackTokenIn) revert AdapterCallbackToken();

        uint256 amountToPay;
        if (amount0Delta > 0) {
            // forge-lint: disable-next-line(unsafe-typecast)
            amountToPay = uint256(amount0Delta);
        } else if (amount1Delta > 0) {
            // forge-lint: disable-next-line(unsafe-typecast)
            amountToPay = uint256(amount1Delta);
        } else {
            revert AdapterBadRoute();
        }
        _safeTransfer(tokenIn, msg.sender, amountToPay);
    }

    function _swapAlgebra(address pool, address tokenIn, address tokenOut, uint256 amountIn)
        internal
        returns (uint256 amountOut)
    {
        IAlgebraPoolMinimal algebra = IAlgebraPoolMinimal(pool);
        address token0 = algebra.token0();
        address token1 = algebra.token1();
        if (!((tokenIn == token0 && tokenOut == token1) || (tokenIn == token1 && tokenOut == token0))) {
            revert AdapterBadRoute();
        }

        bool zeroToOne = tokenIn == token0;
        uint256 balanceBefore = IERC20Minimal(tokenOut).balanceOf(address(this));
        if (amountIn > uint256(type(int256).max)) revert AdapterAmountTooLarge();
        _v3CallbackPool = pool;
        _v3CallbackTokenIn = tokenIn;
        algebra.swap(
            address(this),
            zeroToOne,
            // forge-lint: disable-next-line(unsafe-typecast)
            int256(amountIn),
            zeroToOne ? MIN_SQRT_RATIO_PLUS_ONE : MAX_SQRT_RATIO_MINUS_ONE,
            abi.encode(tokenIn)
        );
        _v3CallbackPool = address(0);
        _v3CallbackTokenIn = address(0);
        amountOut = IERC20Minimal(tokenOut).balanceOf(address(this)) - balanceBefore;
        if (amountOut == 0) revert AdapterSlippageOrProfit();
    }

    function algebraSwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data)
        external
    {
        if (msg.sender != _v3CallbackPool) revert AdapterCallbackSender();
        address tokenIn = abi.decode(data, (address));
        if (tokenIn != _v3CallbackTokenIn) revert AdapterCallbackToken();

        uint256 amountToPay;
        if (amount0Delta > 0) {
            // forge-lint: disable-next-line(unsafe-typecast)
            amountToPay = uint256(amount0Delta);
        } else if (amount1Delta > 0) {
            // forge-lint: disable-next-line(unsafe-typecast)
            amountToPay = uint256(amount1Delta);
        } else {
            revert AdapterBadRoute();
        }
        _safeTransfer(tokenIn, msg.sender, amountToPay);
    }

    function _swapCurve(address pool, address tokenIn, address tokenOut, uint256 amountIn)
        internal
        returns (uint256 amountOut)
    {
        (int128 i, int128 j) = _curveIndices(pool, tokenIn, tokenOut);
        uint256 balanceBefore = IERC20Minimal(tokenOut).balanceOf(address(this));
        _safeApprove(tokenIn, pool, 0);
        _safeApprove(tokenIn, pool, amountIn);
        ICurvePoolMinimal(pool).exchange(i, j, amountIn, 0);
        amountOut = IERC20Minimal(tokenOut).balanceOf(address(this)) - balanceBefore;
        if (amountOut == 0) revert AdapterSlippageOrProfit();
    }

    function _curveIndices(address pool, address tokenIn, address tokenOut)
        internal
        view
        returns (int128 i, int128 j)
    {
        bool foundIn;
        bool foundOut;
        for (uint256 idx = 0; idx < 8; ++idx) {
            (bool ok, bytes memory data) =
                pool.staticcall(abi.encodeWithSelector(ICurvePoolMinimal.coins.selector, idx));
            if (!ok || data.length != 32) break;
            address coin = abi.decode(data, (address));
            if (coin == tokenIn) {
                i = _curveIndex(idx);
                foundIn = true;
            }
            if (coin == tokenOut) {
                j = _curveIndex(idx);
                foundOut = true;
            }
        }
        if (!foundIn || !foundOut || i == j) revert AdapterBadRoute();
    }

    function _curveIndex(uint256 idx) internal pure returns (int128) {
        if (idx >= 8) revert AdapterBadRoute();
        // Curve coin indexes scanned here are bounded to 0..7.
        // forge-lint: disable-next-line(unsafe-typecast)
        return int128(uint128(idx));
    }

    function _swapBalancer(address pool, address tokenIn, address tokenOut, uint256 amountIn)
        internal
        returns (uint256 amountOut)
    {
        bytes32 poolId = IBalancerPoolMinimal(pool).getPoolId();
        _safeApprove(tokenIn, balancerVault, 0);
        _safeApprove(tokenIn, balancerVault, amountIn);

        IBalancerVaultMinimal.SingleSwap memory singleSwap = IBalancerVaultMinimal.SingleSwap({
            poolId: poolId,
            kind: IBalancerVaultMinimal.SwapKind.GIVEN_IN,
            assetIn: tokenIn,
            assetOut: tokenOut,
            amount: amountIn,
            userData: ""
        });
        IBalancerVaultMinimal.FundManagement memory funds = IBalancerVaultMinimal.FundManagement({
            sender: address(this),
            fromInternalBalance: false,
            recipient: payable(address(this)),
            toInternalBalance: false
        });
        amountOut = IBalancerVaultMinimal(balancerVault).swap(
            singleSwap,
            funds,
            0,
            block.timestamp
        );
        if (amountOut == 0) revert AdapterSlippageOrProfit();
    }

    function _effectiveRoutePoolKind(address pool) internal view returns (RoutePoolKind kind) {
        kind = routePoolKind[pool];
        if (kind != RoutePoolKind.UNSET) return kind;
        if (routePoolKindEnforced) revert AdapterPoolKindUnset(pool);
        return _detectRoutePoolKind(pool);
    }

    function _detectRoutePoolKind(address pool) internal view returns (RoutePoolKind) {
        if (_hasGetPoolId(pool)) return RoutePoolKind.BALANCER_WEIGHTED;
        if (_hasCurveCoins(pool)) return RoutePoolKind.CURVE_STABLE;
        if (_hasAlgebraGlobalState(pool)) return RoutePoolKind.ALGEBRA_CLMM;
        if (_hasV3Fee(pool)) return RoutePoolKind.V3_CLMM;
        if (_hasPairTokens(pool)) return RoutePoolKind.V2_CPMM;
        return RoutePoolKind.UNSET;
    }

    function _hasGetPoolId(address target) internal view returns (bool) {
        (bool ok, bytes memory data) =
            target.staticcall(abi.encodeWithSelector(IBalancerPoolMinimal.getPoolId.selector));
        return ok && data.length == 32;
    }

    function _hasV3Fee(address target) internal view returns (bool) {
        (bool ok, bytes memory data) =
            target.staticcall(abi.encodeWithSelector(IUniswapV3PoolMinimal.fee.selector));
        return ok && data.length == 32;
    }

    function _hasAlgebraGlobalState(address target) internal view returns (bool) {
        (bool ok, bytes memory data) =
            target.staticcall(abi.encodeWithSelector(IAlgebraPoolMinimal.globalState.selector));
        return ok && data.length >= 192;
    }

    function _hasCurveCoins(address target) internal view returns (bool) {
        (bool ok0, bytes memory data0) =
            target.staticcall(abi.encodeWithSelector(ICurvePoolMinimal.coins.selector, 0));
        (bool ok1, bytes memory data1) =
            target.staticcall(abi.encodeWithSelector(ICurvePoolMinimal.coins.selector, 1));
        return ok0 && ok1 && data0.length == 32 && data1.length == 32;
    }

    function _hasPairTokens(address target) internal view returns (bool) {
        (bool ok0, bytes memory data0) =
            target.staticcall(abi.encodeWithSelector(IUniswapV2PairMinimal.token0.selector));
        (bool ok1, bytes memory data1) =
            target.staticcall(abi.encodeWithSelector(IUniswapV2PairMinimal.token1.selector));
        return ok0 && ok1 && data0.length == 32 && data1.length == 32;
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Minimal.transfer.selector, to, amount));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert AdapterTransferFailed();
    }

    function _safeApprove(address token, address spender, uint256 amount) internal {
        (bool ok, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Minimal.approve.selector, spender, amount));
        if (!ok || (data.length != 0 && !abi.decode(data, (bool)))) revert AdapterTransferFailed();
    }
}
