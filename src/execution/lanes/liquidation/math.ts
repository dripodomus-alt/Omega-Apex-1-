import type { LiquidationMathResult } from '../../types';
import type { LiquidationOpportunity } from './types';

export interface LiquidationCostInputs {
  debtToCoverRaw: bigint;
  expectedUnwindOutRaw: bigint;
  flashFeeRaw: bigint;
  gasCostRaw: bigint;
  routeHash: string;
  simulationHash: string;
}

export function evaluateLiquidation(
  opportunity: LiquidationOpportunity,
  costs: LiquidationCostInputs,
): LiquidationMathResult {
  const bonus = BigInt(opportunity.borrower.liquidationBonusBps);
  const expectedCollateralSeizedRaw = costs.debtToCoverRaw + (costs.debtToCoverRaw * bonus) / 10_000n;
  const netRaw = costs.expectedUnwindOutRaw - costs.debtToCoverRaw - costs.flashFeeRaw - costs.gasCostRaw;
  return {
    executionType: 'LIQUIDATION',
    state: opportunity.borrower.state,
    routeHash: costs.routeHash,
    simulationHash: costs.simulationHash,
    optimalInputRaw: costs.debtToCoverRaw.toString(),
    expectedNetProfitUsd: Number(netRaw) / 1e6,
    gasCostUsd: Number(costs.gasCostRaw) / 1e6,
    flashFeeUsd: Number(costs.flashFeeRaw) / 1e6,
    slippageBps: 0,
    borrower: opportunity.borrower.borrower,
    debtAsset: opportunity.borrower.debtAsset,
    collateralAsset: opportunity.borrower.collateralAsset,
    debtToCoverRaw: costs.debtToCoverRaw.toString(),
    expectedCollateralSeizedRaw: expectedCollateralSeizedRaw.toString(),
    liquidationBonusBps: opportunity.borrower.liquidationBonusBps,
    unwindRouteHash: costs.routeHash,
  };
}
