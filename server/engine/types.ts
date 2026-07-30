export interface DualPunchParams {
    p1Success: number;
    flashFeeBps: bigint;
    safetyBetaBps: bigint;
    gasCostWei: bigint;
    failureLossWei: bigint;
    minProfitWei: bigint;
    p1Min: number;
    minFlashloanWei: bigint;
}

export interface C2ExecutionConfig {
    targetContract: string;
    walletAddress: string;
    privateKey: string;
    anvilRpcUrl: string;
    mainnetRpcUrl: string;
    anvilActive: boolean;
}

export type ApexPayloadKind =
    | "FLASHLOAN_INTEGRATED_C1_PAYLOADS"
    | "FLASHLOAN_INTEGRATED_C2_PAYLOADS"
    | "FLASHLOAN_INTEGRATED_LIQUIDATIONS";

export interface FlashloanIntegratedLeg {
    dex: string;
    router: string;
    tokenIn: string;
    tokenOut: string;
    amountIn: string;
    minAmountOut: string;
    path: string;
}

export interface FlashloanIntegratedC1Payload {
    payloadKind: "FLASHLOAN_INTEGRATED_C1_PAYLOADS";
    canonicalName: "FLASHLOAN INTEGRATED C1 PAYLOADS";
    useCase: "Open a flashloan-funded C1 cycle, borrow capital, and execute the entry route before C2 settlement.";
    chainId: 137;
    executor: string;
    flashloanProvider: string;
    flashloanAsset: string;
    flashloanAmount: string;
    entryLegs: FlashloanIntegratedLeg[];
    c1StateCommitment: string;
    minC1Output: string;
    deadline: number;
}

export interface FlashloanIntegratedC2Payload {
    payloadKind: "FLASHLOAN_INTEGRATED_C2_PAYLOADS";
    canonicalName: "FLASHLOAN INTEGRATED C2 PAYLOADS";
    useCase: "React to landed C1 state, execute closing route legs, repay flashloan principal plus fee, and settle surplus.";
    chainId: 137;
    executor: string;
    flashloanProvider: string;
    repayAsset: string;
    repayAmount: string;
    c1StateCommitment: string;
    observedC1TxHash: string;
    exitLegs: FlashloanIntegratedLeg[];
    minSurplus: string;
    receiver: string;
    deadline: number;
}

export interface FlashloanIntegratedLiquidationPayload {
    payloadKind: "FLASHLOAN_INTEGRATED_LIQUIDATIONS";
    canonicalName: "FLASHLOAN INTEGRATED LIQUIDATIONS";
    useCase: "Use Balancer flashloan capital to repay unhealthy Aave V3 debt, seize collateral, unwind collateral, repay the flashloan, and settle liquidation surplus.";
    chainId: 137;
    executor: string;
    lendingPool: string;
    userToLiquidate: string;
    debtAsset: string;
    collateralAsset: string;
    debtToCover: string;
    flashloanProvider: string;
    flashloanAsset: string;
    flashloanAmount: string;
    minCollateralOut: string;
    minSurplus: string;
    receiver: string;
    deadline: number;
}

export type ApexExecutionPayload =
    | FlashloanIntegratedC1Payload
    | FlashloanIntegratedC2Payload
    | FlashloanIntegratedLiquidationPayload;