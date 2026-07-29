export type PipelineStage = 'DISCOVERED' | 'RANKED' | 'SIMULATED' | 'PREPARED' | 'EXECUTED' | 'ACCOUNTED';

export type ProtocolType =
  | 'V2_CPMM'
  | 'V3_CLMM'
  | 'QS_V2_CPMM'
  | 'QS_V3_ALGEBRA'
  | 'BAL_WEIGHTED'
  | 'CURVE_STABLE'
  | 'AAVE_V3'
  | 'BALANCER_V3';

export type PoolCategory = 'SWAPPABLE_EXECUTION' | 'FUNDING_FLASHLOAN' | 'LIQUIDATION_TARGET';

export interface PoolInfo {
  id: string;
  name: string;
  protocol: ProtocolType;
  protocolArchitecture?: string;
  category: PoolCategory;
  address: string;
  token0: { symbol: string; decimals: number; address: string };
  token1: { symbol: string; decimals: number; address: string };
  feeBps: number;
  reserve0USD: number;
  reserve1USD: number;
  sqrtPriceX96?: string; // UniV3 / Algebra
  liquidity?: string;
  activeTick?: number;
  isFundingPool: boolean;
  status: 'ACTIVE' | 'DEPRECATED' | 'PAUSED';
}

export interface ArbitrageRoute {
  id: string;
  pathString: string;
  length: number;
  pools: PoolInfo[];
  expectedYieldUSD: number;
  vqcAlphaScore: number;
  vqcWinProbability: number;
  optimalInputUSD: number;
  optimalInputWei: string;
  grossProfitUSD: number;
  estimatedGasUSD: number;
  netProfitUSD: number;
  stage: PipelineStage;
  timestamp: string;
  txHash?: string;
  gasGwei?: number;
  slippageToleranceBps: number;
  isSelfFundingRisk: boolean;
  vqcAlphaHistory?: number[];
  notes?: string;
  transientTrace?: TransientAccountingTrace;
}

export interface VqcModelMetadata {
  version: string;
  accuracy: number;
  precision: number;
  recall: number;
  f1Score: number;
  circuitQubits: number;
  circuitLayers: number;
  ansatz: string;
  trainingSamples: number;
  lastRetrained: string;
  featureWeights: {
    virtualReserveRatio: number;
    pathLengthPenalty: number;
    poolFeeWeight: number;
    gasGweiDensity: number;
    bottleneckTvlRatio: number;
    crossChainSlippageVariance: number;
  };
}

export interface SimulationAuditLog {
  id: string;
  simulationId: string;
  routeId: string;
  pathString: string;
  optimalInputUSD: number;
  expectedGrossProfitUSD: number;
  netProfitUSD: number;
  status: 'SUCCESS' | 'REVERT_SLIPPAGE' | 'EXPIRED_BLOCK' | 'INSUFFICIENT_LIQUIDITY';
  gasUsedGwei: number;
  redisStreamKey: string;
  sqlSynced: boolean;
  timestamp: string;
}

export interface BenchmarkStep {
  id: number;
  title: string;
  command: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED';
  durationMs: number;
  output: string;
}

export interface BenchmarkReport {
  overallScore: number;
  rustEngineCompiled: boolean;
  redisConnected: boolean;
  sqlConnected: boolean;
  pipelineLatencyMs: number;
  maxThroughputRps: number;
  testedRoutes: number;
  validRoutes: number;
  steps: BenchmarkStep[];
}

export interface MathVariableMap {
  symbol: string;
  name: string;
  routeSourceKey: string;
  exampleVal: string;
  unit: string;
  description: string;
}

export interface MathEquation {
  id: string;
  title: string;
  category: 'V3_VIRTUALIZATION' | 'CPMM_DERIVATIVE' | 'APEX_SOLVER' | 'VQC_QUANTUM' | 'ISOLATION_PROOFS' | 'BELLMAN_FORD' | 'TRANSIENT_ACCOUNTING';
  latexFormula: string;
  plainFormula: string;
  summary: string;
  variableMap: MathVariableMap[];
  derivationSteps: string[];
}

export interface TransientLeg {
  legIndex: number;
  tokenIn: string;
  tokenOut: string;
  amountIn: number;
  amountOut: number;
  feeUSD: number;
  gasReserveUSD: number;
  tipUSD: number;
  riskReserveUSD: number;
  modelReserveUSD: number;
  residualUSD: number;
  passed: boolean;
}

export interface TransientAccountingTrace {
  routeId: string;
  borrowedToken: string;
  borrowedAmount: number;
  debtWithFee: number;
  legs: TransientLeg[];
  integrityHash: string;
  finalRepaymentPassed: boolean;
}

export interface LiveTradeLog {
  id: string;
  txHash: string;
  timestamp: string;
  type: 'HFT_ARBITRAGE' | 'AAVE_LIQUIDATION';
  contractAddress: string;
  assetPair: string;
  flashloanAmount: string;
  gasPaidGwei: number;
  netProfitUSD: number;
  blockNumber: number;
  status: 'CONFIRMED_ON_CHAIN' | 'PENDING_RELAY' | 'REVERTED_PROTECTED';
  mevRelay: string;
}

export interface MainnetConfig {
  rpcEndpoint: string;
  wsEndpoint: string;
  mevRelayUrl: string;
  executorAddress: string;
  liquidationContractAddress: string;
  balancerVaultAddress: string;
  multicallAddress: string;
  gasPriceStrategy: 'FAST' | 'INSTANT' | 'CUSTOM';
  customGwei: number;
  isConnected: boolean;
  latestBlock: number;
  isLiveProductionMode: boolean;
  activeNodeProvider?: 'ALCHEMY_PROD' | 'INFURA_ENTERPRISE' | 'QUICKNODE_DEDICATED' | 'PUBLIC_SHARED';
  productionRpcNode?: string;
  authApiKey?: string;
  realTxSigningEnabled?: boolean;
}
