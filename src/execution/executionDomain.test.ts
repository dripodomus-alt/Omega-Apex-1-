import { describe, expect, it } from 'vitest';
import type {
  ApprovedExecutionEnvelope,
  ApprovedTransactionEnvelope,
  C1MathResult,
  C2MathResult,
  LiquidationMathResult,
  StateProvenance,
} from './types';
import { dispatchApprovedExecution } from './dispatcher';
import { assertC1Transition } from './lanes/c1/stateMachine';
import { planC1 } from './lanes/c1/planner';
import { confirmC1Receipt } from './lanes/c1/receipt';
import { buildPostC1Snapshot } from './lanes/c2/postState';
import { decideC2 } from './lanes/c2/decision';
import { discoverLiquidationOpportunity } from './lanes/liquidation/discovery';
import { evaluateLiquidation } from './lanes/liquidation/math';
import { LaneNonceManager } from './nonce/laneNonceManager';
import { StateLockManager } from './locks/stateLockManager';
import { validateBundleIsolation } from './bundles/bundlePolicy';
import { runExecutionGate } from './gates/executionGate';
import { buildContinuousC1CyclePlan } from './cycles/c1CyclePolicy';
import type { RankedRouteCandidate } from '../engine/market/types';

const state: StateProvenance = {
  chainId: 137,
  blockNumber: 100,
  blockHash: '0xblock',
  stateHash: '0xstate-a',
  observedAtMs: 1,
};

const candidate: RankedRouteCandidate = {
  schemaVersion: 'apex.market.candidate.v1',
  comparableKey: 'USDC.e/WMATIC',
  buy: {
    schemaVersion: 'apex.market.quote.v1',
    chainId: 137,
    venue: 'SushiSwap V2',
    protocol: 'SUSHI_V2',
    invariantFamily: 'V2_CPMM',
    destinationId: 'sushi',
    poolId: '0xsell',
    baseAsset: { address: '0xbase', decimals: 6, symbol: 'USDC.e' },
    quoteAsset: { address: '0xmid', decimals: 18, symbol: 'WMATIC' },
    quoteBasis: 'EXACT_IN',
    amountInRaw: '1000000000',
    buyPriceX18: '76000000000000000',
    sellPriceX18: '77000000000000000',
    tvlUsdX18: '1000000000000000000000000',
    feeBps: 30,
    executable: true,
    blockNumber: 100,
    observedAtMs: 1,
  },
  sell: {
    schemaVersion: 'apex.market.quote.v1',
    chainId: 137,
    venue: 'QuickSwap V2',
    protocol: 'QUICKSWAP_V2',
    invariantFamily: 'V2_CPMM',
    destinationId: 'quick',
    poolId: '0xbuy',
    baseAsset: { address: '0xbase', decimals: 6, symbol: 'USDC.e' },
    quoteAsset: { address: '0xmid', decimals: 18, symbol: 'WMATIC' },
    quoteBasis: 'EXACT_IN',
    amountInRaw: '1000000000',
    buyPriceX18: '76000000000000000',
    sellPriceX18: '77000000000000000',
    tvlUsdX18: '1000000000000000000000000',
    feeBps: 30,
    executable: true,
    blockNumber: 100,
    observedAtMs: 1,
  },
  buyPriceX18: '76000000000000000',
  sellPriceX18: '77000000000000000',
  rawSpreadX18: '1000000000000000',
  rawSpreadBps: '131',
  buyBlock: 100,
  sellBlock: 100,
  candidateHash: '0xcandidate',
  rank: 1,
};

function c1Math(overrides: Partial<C1MathResult> = {}): C1MathResult {
  return {
    executionType: 'C1_ARBITRAGE',
    state,
    routeHash: '0xroute',
    simulationHash: '0xsim',
    calldataHash: '0xcalldata',
    optimalInputRaw: '1000000000',
    expectedNetProfitUsd: 12.5,
    gasCostUsd: 0.1,
    flashFeeUsd: 0.09,
    slippageBps: 10,
    candidate,
    leg1ExpectedOutputRaw: '13100000000000000000000',
    leg2ExpectedOutputRaw: '1012500000',
    ...overrides,
  };
}

function approvedC1(overrides: Partial<ApprovedExecutionEnvelope> = {}): ApprovedExecutionEnvelope {
  const math = c1Math();
  return {
    schemaVersion: 'apex.execution.approved.v1',
    identity: {
      executionId: 'c1-1',
      executionType: 'C1_ARBITRAGE',
      candidateHash: candidate.candidateHash,
      routeHash: math.routeHash,
    },
    mode: 'DRY_RUN',
    math,
    resources: [
      { kind: 'ROUTE', id: math.routeHash },
      { kind: 'POOL', id: candidate.buy.poolId },
      { kind: 'POOL', id: candidate.sell.poolId },
    ],
    nonceOwner: 'c1_lane',
    createdAtMs: 1,
    ...overrides,
  };
}

function txFor(envelope: ApprovedExecutionEnvelope): ApprovedTransactionEnvelope {
  return {
    schemaVersion: 'apex.execution.tx.v1',
    identity: envelope.identity,
    mode: envelope.mode,
    to: '0x409ece3Fd71DFBd8f692B600f36A89301cb37346',
    data: '0x12345678',
    valueRaw: '0',
    nonce: 7,
    stateHash: envelope.math.state.stateHash,
    simulationHash: envelope.math.simulationHash,
    calldataHash: envelope.math.calldataHash ?? '0xcalldata',
    expectedNetProfitUsd: envelope.math.expectedNetProfitUsd,
    createdAtMs: 1,
  };
}


function confirmedCommit(envelope: ApprovedExecutionEnvelope) {
  return confirmC1Receipt(planC1(envelope).opportunity, {
    txHash: `0xtx-${envelope.identity.executionId}`,
    blockNumber: 101,
    status: 1,
    gasUsed: 100n,
    effectiveGasPrice: 2n,
  });
}

function c2MathFromCommit(
  commit: ReturnType<typeof confirmedCommit>,
  postState: ReturnType<typeof buildPostC1Snapshot>,
  overrides: Partial<C2MathResult> = {},
): C2MathResult {
  return {
    ...c1Math({ state: postState }),
    executionType: 'C2_ARBITRAGE',
    parentC1Id: commit.identity.executionId,
    parentC1Block: commit.confirmedBlock,
    sequence: 1,
    precedingExecutionId: commit.identity.executionId,
    precedingExecutionBlock: commit.confirmedBlock,
    postStateHash: postState.stateHash,
    action: 'REVERSE',
    expiryBlock: commit.confirmedBlock + 2,
    ...overrides,
  };
}

function approvedC1ForCycle(index: number): ApprovedExecutionEnvelope {
  const routeHash = `0xroute-${index}`;
  const math = c1Math({
    routeHash,
    simulationHash: `0xsim-${index}`,
    calldataHash: `0xcalldata-${index}`,
    expectedNetProfitUsd: 10 + index,
  });
  return approvedC1({
    identity: {
      executionId: `c1-${index}`,
      executionType: 'C1_ARBITRAGE',
      candidateHash: `0xcandidate-${index}`,
      routeHash,
    },
    math,
    resources: [
      { kind: 'ROUTE', id: routeHash },
      { kind: 'POOL', id: `0xbuy-${index}` },
      { kind: 'POOL', id: `0xsell-${index}` },
    ],
  });
}

function approvedC2FromC1(
  c1: ApprovedExecutionEnvelope,
  sequence: number,
  precedingBlock: number,
  stateBlock: number,
): ApprovedExecutionEnvelope {
  const math: C2MathResult = {
    ...c1.math,
    executionType: 'C2_ARBITRAGE',
    parentC1Id: c1.identity.executionId,
    parentC1Block: precedingBlock,
    sequence,
    precedingExecutionId: sequence === 1 ? c1.identity.executionId : `c2-${sequence - 1}`,
    precedingExecutionBlock: precedingBlock,
    postStateHash: `0xpost-${sequence}`,
    action: 'MIRROR',
    expiryBlock: precedingBlock + 2,
    state: { ...c1.math.state, blockNumber: stateBlock, stateHash: `0xpost-${sequence}` },
  } as C2MathResult;
  return {
    ...c1,
    identity: {
      executionId: `c2-${sequence}`,
      executionType: 'C2_ARBITRAGE',
      candidateHash: `0xc2-${sequence}`,
      routeHash: `0xroute-c2-${sequence}`,
    },
    math,
    nonceOwner: 'c2_lane',
  };
}

describe('three-lane execution domain', () => {
  it('dispatches approved C1 into the C1 lane only', () => {
    const result = dispatchApprovedExecution(approvedC1());
    expect(result).toMatchObject({ accepted: true, lane: 'C1', status: 'C1_LOCKED' });
  });

  it('rejects backward C1 transitions', () => {
    expect(() => assertC1Transition('C1_BUILT', 'C1_LOCKED')).toThrow('[C1_STATE]');
  });

  it('rejects C1 plans that reuse the same buy and sell pool', () => {
    const bad = approvedC1({
      math: c1Math({
        candidate: {
          ...candidate,
          sell: { ...candidate.sell, poolId: candidate.buy.poolId },
        },
      }),
    });
    expect(() => planC1(bad)).toThrow('distinct executable buy/sell pools');
  });

  it('requires C2 to reference a confirmed parent C1 and fresh post-state', () => {
    const envelope = approvedC1();
    const plan = planC1(envelope);
    const commit = confirmC1Receipt(plan.opportunity, {
      txHash: '0xtx',
      blockNumber: 101,
      status: 1,
      gasUsed: 100n,
      effectiveGasPrice: 2n,
    });
    const postState = buildPostC1Snapshot(commit, {
      ...state,
      blockNumber: 102,
      stateHash: '0xstate-b',
    });
    const math: C2MathResult = {
      ...c1Math({ state: postState }),
      executionType: 'C2_ARBITRAGE',
      parentC1Id: commit.identity.executionId,
      parentC1Block: commit.confirmedBlock,
      sequence: 1,
      precedingExecutionId: commit.identity.executionId,
      precedingExecutionBlock: commit.confirmedBlock,
      postStateHash: postState.stateHash,
      action: 'REVERSE',
      expiryBlock: 106,
    };
    const decision = decideC2(commit, postState, math);
    expect(decision.action).toBe('REVERSE');
  });

  it('discovers liquidation eligibility without requiring a comparable DEX pair', () => {
    const opportunity = discoverLiquidationOpportunity({
      borrower: '0xborrower',
      healthFactorX18: 900000000000000000n,
      debtAsset: '0xdebt',
      collateralAsset: '0xcollateral',
      totalDebtBaseRaw: 1000n,
      collateralRaw: 2000n,
      closeFactorBps: 5000,
      liquidationBonusBps: 750,
      state,
    });
    expect(opportunity?.maxDebtToCoverRaw).toBe(500n);
  });

  it('evaluates liquidation net from debt cover, flash fee, gas, and unwind output', () => {
    const opportunity = discoverLiquidationOpportunity({
      borrower: '0xborrower',
      healthFactorX18: 900000000000000000n,
      debtAsset: '0xdebt',
      collateralAsset: '0xcollateral',
      totalDebtBaseRaw: 1000n,
      collateralRaw: 2000n,
      closeFactorBps: 5000,
      liquidationBonusBps: 750,
      state,
    });
    expect(opportunity).not.toBeNull();
    const math = evaluateLiquidation(opportunity!, {
      debtToCoverRaw: 500n,
      expectedUnwindOutRaw: 620n,
      flashFeeRaw: 1n,
      gasCostRaw: 2n,
      routeHash: '0xunwind',
      simulationHash: '0xliq-sim',
    });
    expect(math.expectedCollateralSeizedRaw).toBe('537');
    expect(math.expectedNetProfitUsd).toBeGreaterThan(0);
  });

  it('prevents nonce and mutable-state collisions across lanes', () => {
    const manager = new LaneNonceManager(11);
    const locks = new StateLockManager();
    const c1 = approvedC1();
    const first = manager.reserve(c1);
    locks.acquire(c1);
    expect(first).toMatchObject({ lane: 'c1_lane', nonce: 11 });
    expect(() => locks.acquire(approvedC1({ identity: { ...c1.identity, executionId: 'c1-2' } }))).toThrow('conflicting');
  });

  it('rejects parent C1 plus child C2 in one bundle', () => {
    const c1 = approvedC1();
    const c2Math: C2MathResult = {
      ...c1Math(),
      executionType: 'C2_ARBITRAGE',
      parentC1Id: c1.identity.executionId,
      parentC1Block: 101,
      sequence: 1,
      precedingExecutionId: c1.identity.executionId,
      precedingExecutionBlock: 101,
      postStateHash: '0xstate-b',
      action: 'MIRROR',
      expiryBlock: 106,
    };
    const c2: ApprovedExecutionEnvelope = {
      ...c1,
      identity: {
        executionId: 'c2-1',
        executionType: 'C2_ARBITRAGE',
        candidateHash: '0xc2',
        routeHash: '0xroute-c2',
      },
      math: c2Math,
      nonceOwner: 'c2_lane',
    };
    expect(validateBundleIsolation([c1, c2])).toMatchObject({ ok: false });
  });

  it('final gate rejects state drift before live submit', () => {
    const envelope = approvedC1();
    const nonce = new LaneNonceManager(1).reserve(envelope);
    const gate = runExecutionGate({
      envelope,
      transaction: txFor(envelope),
      currentState: { ...state, stateHash: '0xdrift' },
      nonce,
      simulationPassed: true,
    });
    expect(gate.passed).toBe(false);
    expect(gate.reasons).toContain('STATE_HASH_DRIFT');
  });
  it('requires at least 10 executable C1 lanes per cycle', () => {
    const nine = Array.from({ length: 9 }, (_, index) => approvedC1ForCycle(index));
    expect(() => buildContinuousC1CyclePlan('cycle-underfilled', nine)).toThrow(
      'requires at least 10 executable C1 lanes',
    );
  });

  it('keeps C2 work queued without blocking the next C1 cycle', () => {
    const tenC1 = Array.from({ length: 10 }, (_, index) => approvedC1ForCycle(index));
    const c2 = approvedC2FromC1(tenC1[0], 1, 101, 102);
    const cycle = buildContinuousC1CyclePlan('cycle-ready', [...tenC1, c2]);
    expect(cycle.c1Lanes).toHaveLength(10);
    expect(cycle.nonBlockingC2Queue).toHaveLength(1);
  });

  it('expires C2 after the fifth child execution for one parent C1', () => {
    const envelope = approvedC1();
    const commit = confirmedCommit(envelope);
    const postState = buildPostC1Snapshot(commit, {
      ...state,
      blockNumber: 102,
      stateHash: '0xstate-b',
    });
    const math = c2MathFromCommit(commit, postState, {
      sequence: 6,
      precedingExecutionId: 'c2-5',
      precedingExecutionBlock: 101,
    });
    expect(decideC2(commit, postState, math).action).toBe('EXPIRE');
  });

  it('expires C2 when it is more than 2 blocks after the preceding execution', () => {
    const envelope = approvedC1();
    const commit = confirmedCommit(envelope);
    const postState = buildPostC1Snapshot(commit, {
      ...state,
      blockNumber: 104,
      stateHash: '0xstate-b',
    });
    const math = c2MathFromCommit(commit, postState, {
      sequence: 1,
      precedingExecutionBlock: 101,
    });
    expect(decideC2(commit, postState, math)).toMatchObject({ action: 'EXPIRE', expiryBlock: 103 });
  });
});
