export type ChainId = 137;

export type InvariantFamily =
  | 'V2_CPMM'
  | 'V3_CLMM'
  | 'ALGEBRA_CLMM'
  | 'CURVE_STABLE'
  | 'BALANCER_WEIGHTED'
  | 'BALANCER_STABLE'
  | 'BALANCER_COMPOSABLE'
  | 'DODO_PMM';

export type QuoteBasis = 'EXACT_IN';
export type MarketSource = 'LIVE_RPC' | 'LIVE_SCANNER' | 'SIMULATION';

export interface AssetRef {
  address: string;
  symbol?: string;
  decimals: number;
}

export interface ExecutableVenueQuote {
  schemaVersion: 'apex.market.quote.v1';
  chainId: ChainId;

  venue: string;
  protocol: string;
  invariantFamily: InvariantFamily;

  factoryOrRegistry?: string;
  destinationId: string;
  poolId: string;

  baseAsset: AssetRef;
  quoteAsset: AssetRef;

  quoteBasis: QuoteBasis;
  amountInRaw: string;

  /** quote-asset units per one base asset, fixed point 1e18 */
  buyPriceX18: string;
  sellPriceX18: string;

  /** pool-native TVL in USD, fixed point 1e18 */
  tvlUsdX18: string;

  feeBps: number;
  executable: boolean;

  blockNumber: number;
  observedAtMs: number;
  stateHash?: string;
}

export interface MarketEngineConfig {
  chainId: ChainId;
  minPoolTvlUsdX18: bigint;
  stateTtlBlocks: number;
  minRawSpreadBps: bigint;
  latestBlock: number;
  maxCandidates?: number;
}

export type QuoteRejectReason =
  | 'WRONG_CHAIN'
  | 'NOT_EXECUTABLE'
  | 'TVL_BELOW_GATE'
  | 'STALE_STATE'
  | 'INVALID_PRICE'
  | 'INVALID_AMOUNT'
  | 'INVALID_DESTINATION'
  | 'INVALID_POOL'
  | 'INVALID_ASSET'
  | 'INVALID_FEE';

export interface QuoteRejection {
  reason: QuoteRejectReason;
  destinationId?: string;
  poolId?: string;
  detail: string;
}

export interface RankedRouteCandidate {
  schemaVersion: 'apex.market.candidate.v1';
  comparableKey: string;

  buy: ExecutableVenueQuote;
  sell: ExecutableVenueQuote;

  buyPriceX18: string;
  sellPriceX18: string;
  rawSpreadX18: string;
  rawSpreadBps: string;

  buyBlock: number;
  sellBlock: number;

  candidateHash: string;
  rank: number;
}

export interface MarketEngineResult {
  schemaVersion: 'apex.market.snapshot.v1';
  source: MarketSource;

  generatedAtMs: number;
  latestBlock: number;

  inputRows: number;
  eligibleRows: number;
  rejectedRows: QuoteRejection[];

  comparableMarkets: number;
  candidateCount: number;

  candidates: RankedRouteCandidate[];
}

export interface MarketIntakeEnvelope {
  schemaVersion: 'apex.market.intake.v1';
  source: MarketSource;
  latestBlock: number;
  observedAtMs: number;
  quotes: ExecutableVenueQuote[];
}
