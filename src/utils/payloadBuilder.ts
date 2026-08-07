/**
 * OMEGA V5 — Universal Transaction Payload Builder
 *
 * This engine consumes an `ArbitrageRoute` and the `AdapterFramework` to construct
 * with on-chain slippage protection,
 * the final, executable calldata for the on-chain `OmegaExecutor` contract.
 *
 * It translates a high-level route definition into a low-level, gas-optimized
 * transaction payload, ready for submission by the `ethersBroadcaster`.
 */

import { ethers } from 'ethers';
import { getAmountOut } from './pricing'; // Assumes a new helper for price simulation
import type { ArbitrageRoute } from '../types';
import { getAdapter, AdapterCall } from './adapters';
import { OMEGA_EXECUTOR_ABI } from './ethersBroadcaster';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';

export interface BuiltPayload {
  /** The address of the contract to call (our OmegaExecutor). */
  to: string;
  /** The encoded function call and arguments. */
  data: string;
  /** The ETH/MATIC value to send with the transaction (usually 0). */
  value: bigint;
  /** A human-readable description of the action. */
  description: string;
}

/**
 * Builds the final transaction payload for a given arbitrage route.
 *
 * This implementation demonstrates a multi-call pattern where the executor
 * contract would have a function like `execute(AdapterCall[] calls)`.
 *
 * @param route The arbitrage route to execute.
 * @returns A `BuiltPayload` object ready for signing and broadcasting.
 */
export async function buildPayloadForRoute(route: ArbitrageRoute): Promise<BuiltPayload> {
  if (!route.pools || route.pools.length === 0) {
    throw new Error('[PayloadBuilder] Route must contain at least one pool.');
  }

  const executorInterface = new ethers.Interface(OMEGA_EXECUTOR_ABI);
  const executorAddress = POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress;

  const adapterCalls: AdapterCall[] = [];
  let currentAmountIn = BigInt(route.optimalInputWei);
  let currentTokenIn = route.pools[0].token0.address; // Assume route starts with token0 of first pool

  for (let i = 0; i < route.pools.length; i++) {
    const pool = route.pools[i];
    const isLastHop = i === route.pools.length - 1;

    // Determine tokenOut for the current hop
    const tokenOut = pool.token0.address.toLowerCase() === currentTokenIn.toLowerCase()
      ? pool.token1.address
      : pool.token0.address;

    // The recipient of this hop's output is the next pool's address, or the final profit receiver
    const recipient = isLastHop
      ? POLYGON_CHAIN_CONFIG.profitReceiverAddress
      : route.pools[i + 1].address;

    // Simulate the output of this hop to calculate amountOutMinimum and to use as input for the next hop.
    const { amountOut: expectedAmountOut } = await getAmountOut(pool, currentAmountIn);

    // Calculate the minimum amount out based on the route's slippage tolerance.
    const slippageTolerance = BigInt(route.slippageToleranceBps);
    const amountOutMinimum = expectedAmountOut - (expectedAmountOut * slippageTolerance / 10000n);

    // The amount for the first hop is the route's optimal input. For subsequent hops,
    // the on-chain executor contract will handle the amount forwarding, so we pass 0.
    const amountInForCall = i === 0 ? currentAmountIn : 0n;

    const adapter = getAdapter(pool.protocol);
    pool.tokenInAddress = currentTokenIn;
    pool.tokenOutAddress = tokenOut;
    const adapterCall = adapter.encodeCall(
      pool,
      amountInForCall,
      recipient,
      amountOutMinimum // Pass the calculated minimum to the adapter
    );
    adapterCalls.push(adapterCall);

    // The output of this hop is the input for the next
    currentTokenIn = tokenOut;
    currentAmountIn = expectedAmountOut; // Use simulated output for next hop's input
  }

  // For multi-hop, we use our own executor's multicall function
  const data = executorInterface.encodeFunctionData('executeMultiHopSwap', [adapterCalls]);

  return {
    to: executorAddress,
    data,
    value: 0n,
    description: `Execute ${route.pools.length}-hop swap: ${route.pathString}`,
  };
}