import type { C1Commit, C1Opportunity, C1Receipt } from './types';

export function confirmC1Receipt(opportunity: C1Opportunity, receipt: C1Receipt): C1Commit {
  if (receipt.status !== 1) {
    throw new Error('[C1_RECEIPT] receipt failed');
  }
  if (receipt.blockNumber < opportunity.preState.blockNumber) {
    throw new Error('[C1_RECEIPT] confirmation block precedes pre-state');
  }
  return {
    identity: opportunity.identity,
    confirmedBlock: receipt.blockNumber,
    txHash: receipt.txHash,
    preStateHash: opportunity.preState.stateHash,
    routeHash: opportunity.math.routeHash,
    receipt,
  };
}
