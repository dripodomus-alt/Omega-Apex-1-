/**
 * OMEGA V5 — Universal Protocol Adapter Framework
 *
 * Defines a standardized interface for interacting with any DEX protocol. Each
 * adapter is responsible for generating the precise, gas-optimized calldata
 * required for a swap on its specific protocol. This modular pattern allows the
 * execution engine to be completely protocol-agnostic.
 *
 * The `PayloadBuilder` consumes these adapters to construct the final transaction
 * payload for the on-chain `OmegaExecutor` contract.
 *
 * Core Principles:
 *   - Extensibility: New protocols can be added by implementing the IProtocolAdapter interface.
 *   - Gas Optimization: Adapters are responsible for generating the most efficient calldata.
 *   - Separation of Concerns: Adapters handle protocol-specifics; the core engine handles orchestration.
 */

import type { PoolInfo } from '../types';
import {
  DODO_POLYGON_ADDRESSES,
  encodeTightPackedDodoPath,
  DodoMixSwapHop,
} from './dodoCalldata';
import { ethers } from 'ethers';

/**
 * Represents the protocol-specific data needed for a single swap (hop) in a route.
 * This is the output of an adapter's `encodeCall` method.
 */
export interface AdapterCall {
  /** The target contract address for this specific swap (e.g., a DODO pool or a Uniswap router). */
  target: string;
  /** The raw calldata for the swap function on the target contract. */
  callData: string;
  /** The value (in ETH/MATIC) to be sent with this call, usually 0 for token swaps. */
  value: bigint;
}

/**
 * The standard interface for all protocol adapters.
 */
export interface IProtocolAdapter {
  /** A unique identifier for the protocol (e.g., 'DODO_V2', 'UNISWAP_V3'). */
  protocol: string;

  /**
   * Encodes the calldata for a single swap operation.
   * @param pool The pool information for the swap.
   * @param amountIn The amount of the input token (in wei).
   * @param recipient The address that will receive the output tokens.
   * @param amountOutMinimum The minimum amount of output tokens expected (in wei) for slippage protection.
   * @returns An AdapterCall object with the target and calldata.
   */
  encodeCall(pool: PoolInfo, amountIn: bigint, recipient: string, amountOutMinimum: bigint): AdapterCall;
}

/**
 * World-Class Implementation for DODO V2 PMM Pools.
 *
 * This adapter generates tightly-packed calldata for DODO's gas-saving router,
 * which is more efficient than standard ABI encoding for multi-hop routes.
 */
export class DodoV2Adapter implements IProtocolAdapter {
  public readonly protocol = 'DODO_V2';

  /**
   * Encodes a DODO V2 swap using the gas-saving tight-packed path format.
   * The `OmegaExecutor` contract will then use this packed path.
   *
   * @param pool The DODO pool to swap through.
   * @param amountIn The input amount (wei).
   * @param recipient The final recipient of the output tokens.
   * @returns An AdapterCall targeting the DODO gas-saving router.
   */
  encodeCall(pool: PoolInfo, amountIn: bigint, recipient: string, amountOutMinimum: bigint): AdapterCall {
    // DODO's tight-packed path requires knowing if we are selling the base token (token0)
    // or the quote token (token1). This is determined by which token is the input.
    // Direction: 0 = sellBase (token0 -> token1), 1 = sellQuote (token1 -> token0)
    const direction = pool.token0.address.toLowerCase() === pool.tokenInAddress?.toLowerCase() ? 0 : 1;

    const hop: DodoMixSwapHop = {
      adapter: DODO_POLYGON_ADDRESSES.mixSwapProxy,
      pair: pool.address,
      assetTo: recipient,
      direction,
      moreInfo: '0x',
    };

    // The `encodeTightPackedDodoPath` function creates the most gas-efficient
    // representation for a DODO route.
    const packedPath = encodeTightPackedDodoPath([
      { poolAddress: hop.pair, direction: hop.direction },
    ]);

    // The on-chain executor will expect this packed format.
    // For this example, we'll assume a function `executeDodoPackedSwap(bytes path, uint256 amountIn)`
    // on our OmegaExecutor contract. We'll add amountOutMinimum to it.
    const executorInterface = new ethers.Interface(['function executeDodoPackedSwap(bytes path, uint256 amountIn, uint256 amountOutMinimum)']);
    const callData = executorInterface.encodeFunctionData('executeDodoPackedSwap', [
      '0x' + packedPath,
      amountIn,
      amountOutMinimum, // Pass amountOutMinimum to the executor
    ]);

    return {
      target: DODO_POLYGON_ADDRESSES.router, // The main DODO router
      callData,
      value: 0n,
    };
  }
}

/**
 * World-Class Implementation for Uniswap V3 Single-Hop Swaps.
 *
 * This adapter generates calldata for the `exactInputSingle` function on the
 * Uniswap V3 router, which is the standard for single-pool swaps.
 */
export class UniswapV3Adapter implements IProtocolAdapter {
  public readonly protocol = 'UNISWAP_V3';

  // Per Uniswap docs, the V3 router address on Polygon
  public readonly routerAddress = '0xE592427A0AEce92De3Edee1F18E0157C05861564';

  encodeCall(pool: PoolInfo, amountIn: bigint, recipient: string, amountOutMinimum: bigint): AdapterCall {
    const uniswapRouterInterface = new ethers.Interface([
      'function exactInputSingle(tuple(address tokenIn, address tokenOut, uint24 fee, address recipient, uint256 deadline, uint256 amountIn, uint256 amountOutMinimum, uint160 sqrtPriceLimitX96) params) external payable returns (uint256 amountOut)',
    ]);

    const params = {
      tokenIn: pool.tokenInAddress!,
      tokenOut: pool.tokenOutAddress!,
      fee: pool.feeBps * 10, // e.g., 30 bps -> 3000 fee tier
      recipient: recipient,
      deadline: Math.floor(Date.now() / 1000) + 60 * 20, // 20 minutes from now
      amountIn: amountIn,
      amountOutMinimum: amountOutMinimum, // Now we enforce the minimum
      sqrtPriceLimitX96: 0n,
    };

    const callData = uniswapRouterInterface.encodeFunctionData('exactInputSingle', [params]);

    return {
      target: this.routerAddress,
      callData,
      value: 0n,
    };
  }
}

/** A simple factory to get an adapter instance by protocol name. */
export function getAdapter(protocol: string): IProtocolAdapter {
  switch (protocol) {
    case 'DODO_V2':
    case 'DODO_V2_PMM':
      return new DodoV2Adapter();
    case 'V3_CLMM': // Map the generic V3 protocol name to our specific adapter
    case 'UNISWAP_V3':
      return new UniswapV3Adapter();
    default:
      throw new Error(`[AdapterFactory] No adapter found for protocol: ${protocol}`);
  }
}
