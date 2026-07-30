import assert from "node:assert/strict";
import {
  enforceExecutionInvariants,
  InvariantViolationError,
  type QuotedRouteStep,
} from "../server/engine/executionInvariants.js";

const costs = {
  flashloanFeeRaw: 0n,
  gasCostInAssetRaw: 0n,
  relayTipInAssetRaw: 0n,
  executorCostInAssetRaw: 0n,
  riskBufferInAssetRaw: 0n,
};

const tokenA = "0x00000000000000000000000000000000000000aa";
const tokenB = "0x00000000000000000000000000000000000000bb";
const tokenC = "0x00000000000000000000000000000000000000cc";
const chainId = 137;
const poolOne = "0x0000000000000000000000000000000000000001";
const poolTwo = "0x0000000000000000000000000000000000000002";
const poolThree = "0x0000000000000000000000000000000000000003";

function poolKey(poolAddress: string) {
  return `${chainId}:${poolAddress.toLowerCase()}`;
}

function profitableTwoLeg(poolBuy: string, poolSell: string): QuotedRouteStep[] {
  return [
    {
      venueId: `UNISWAPV3:${poolBuy}:A->B:fee500`,
      poolKey: poolKey(poolBuy),
      tokenIn: tokenA,
      tokenOut: tokenB,
      amountIn: 1_000n,
      amountOut: 1_100n,
    },
    {
      venueId: `UNISWAPV3:${poolSell}:B->A:fee500`,
      poolKey: poolKey(poolSell),
      tokenIn: tokenB,
      tokenOut: tokenA,
      amountIn: 1_100n,
      amountOut: 1_200n,
    },
  ];
}

function profitableThreeLegWithDuplicatePool(): QuotedRouteStep[] {
  return [
    {
      venueId: `UNISWAPV3:${poolOne}:A->B:fee500`,
      poolKey: poolKey(poolOne),
      tokenIn: tokenA,
      tokenOut: tokenB,
      amountIn: 1_000n,
      amountOut: 1_100n,
    },
    {
      venueId: `QUICKSWAPV3:${poolTwo}:B->C:fee500`,
      poolKey: poolKey(poolTwo),
      tokenIn: tokenB,
      tokenOut: tokenC,
      amountIn: 1_100n,
      amountOut: 1_150n,
    },
    {
      venueId: `UNISWAPV3:${poolOne}:C->A:fee500`,
      poolKey: poolKey(poolOne),
      tokenIn: tokenC,
      tokenOut: tokenA,
      amountIn: 1_150n,
      amountOut: 1_250n,
    },
  ];
}

enforceExecutionInvariants(profitableTwoLeg(poolOne, poolTwo), costs);
enforceExecutionInvariants([
  ...profitableTwoLeg(poolOne, poolTwo).slice(0, 1),
  {
    venueId: `QUICKSWAPV3:${poolTwo}:B->C:fee500`,
    poolKey: poolKey(poolTwo),
    tokenIn: tokenB,
    tokenOut: tokenC,
    amountIn: 1_100n,
    amountOut: 1_150n,
  },
  {
    venueId: `UNISWAPV3:${poolThree}:C->A:fee500`,
    poolKey: poolKey(poolThree),
    tokenIn: tokenC,
    tokenOut: tokenA,
    amountIn: 1_150n,
    amountOut: 1_250n,
  },
], costs);

assert.throws(
  () => enforceExecutionInvariants(profitableTwoLeg(poolOne, poolOne), costs),
  (error) => error instanceof InvariantViolationError && error.invariant === "VENUE_EXCLUSIVITY",
);

assert.throws(
  () => enforceExecutionInvariants(profitableThreeLegWithDuplicatePool(), costs),
  (error) => error instanceof InvariantViolationError && error.invariant === "VENUE_EXCLUSIVITY",
);

console.log("INVARIANT_TEST|venue_exclusivity=PASS|canonicalPoolKey=chainId:poolAddress|same_protocol_different_pool_allowed=true|same_pool_rejected=true|multi_hop_duplicate_pool_rejected=true");
