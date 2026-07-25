/* eslint-disable @typescript-eslint/no-non-null-assertion */

/**
 * APEX Ω — Precision Pricing Engine
 *
 * Canonical responsibilities:
 *
 * 1. Resolve token decimals.
 * 2. Resolve oracle decimals.
 * 3. Normalize every oracle price into PRICE_SCALE.
 * 4. Convert token atomic units into USD fixed-point units.
 * 5. Convert USD values back into token atomic units.
 * 6. Derive TOKEN_A / TOKEN_B cross prices.
 * 7. Reject stale, invalid, incomplete, or divergent prices.
 * 8. Preserve integer precision throughout the execution pipeline.
 *
 * No JavaScript Number is used for monetary arithmetic.
 *
 * This is the reference implementation. The Python port in
 * omega_v5/pricing/precision_pricing.py is kept bit-for-bit equivalent
 * for pipeline compatibility.
 */

export type Address = `0x${string}`;

export const PRICE_DECIMALS = 18;
export const PRICE_SCALE = 10n ** BigInt(PRICE_DECIMALS);

export const BPS_DENOMINATOR = 10_000n;

export type OracleKind =
  | "CHAINLINK"
  | "DEX_TWAP"
  | "PROTOCOL_RATE"
  | "MANUAL_DISABLED";

export interface TokenMetadata {
  chainId: number;
  address: Address;
  symbol: string;
  decimals: number;
}

export interface OracleObservation {
  sourceId: string;
  sourceKind: OracleKind;

  /**
   * Oracle answer before normalization.
   *
   * Example:
   * 1 USDC = $1.00000000 from an 8-decimal feed
   * answer = 100_000_000
   */
  answer: bigint;

  /**
   * Number of decimal places used by `answer`.
   */
  answerDecimals: number;

  /**
   * Unix timestamp in seconds at which the source was updated.
   */
  updatedAt: bigint;

  /**
   * Chain block from which the observation was obtained.
   */
  observedAtBlock: bigint;

  /**
   * Optional source round identifier.
   */
  roundId?: bigint;

  /**
   * Optional completed-round identifier.
   */
  answeredInRound?: bigint;

  /**
   * Optional source confidence in basis points.
   * 10,000 = full configured confidence.
   */
  confidenceBps?: bigint;
}

export interface OracleSource {
  readonly id: string;
  readonly kind: OracleKind;

  /**
   * Returns the USD price for exactly one whole token.
   */
  readUsdPrice(
    token: TokenMetadata,
    context: PricingContext,
  ): Promise<OracleObservation>;
}

export interface PricingContext {
  chainId: number;
  currentBlock: bigint;
  currentTimestamp: bigint;
}

export interface TokenOraclePolicy {
  token: Address;

  /**
   * Maximum permitted age for any accepted observation.
   */
  maxAgeSeconds: bigint;

  /**
   * Maximum difference between the freshest observation block
   * and the current block.
   */
  maxBlockLag: bigint;

  /**
   * Minimum number of valid sources required.
   */
  minimumValidSources: number;

  /**
   * Maximum difference between accepted oracle observations.
   */
  maximumDeviationBps: bigint;

  /**
   * Minimum accepted source confidence.
   */
  minimumConfidenceBps: bigint;

  /**
   * Source identifiers in priority order.
   */
  sourceIds: string[];

  /**
   * Aggregation rule used after validation.
   */
  aggregation: "MEDIAN" | "CONSERVATIVE_LOW" | "CONSERVATIVE_HIGH";
}

export interface PriceResult {
  token: TokenMetadata;

  /**
   * USD price of one whole token, normalized to 18 decimals.
   */
  priceUsdX18: bigint;

  observedAtBlock: bigint;
  updatedAt: bigint;

  sourcesUsed: string[];

  /**
   * Maximum source-to-source deviation after validation.
   */
  sourceDeviationBps: bigint;

  /**
   * Minimum confidence among accepted sources.
   */
  confidenceBps: bigint;
}

export interface PricePair {
  base: TokenMetadata;
  quote: TokenMetadata;

  /**
   * Quote-token units per one base token, scaled to 1e18.
   *
   * Example:
   * WETH/USDC = 3,000 quote units per base unit
   * basePerQuoteX18 represents 3000e18.
   */
  quotePerBaseX18: bigint;

  baseUsdX18: bigint;
  quoteUsdX18: bigint;
}

export class PricingError extends Error {
  constructor(
    public readonly code:
      | "TOKEN_NOT_REGISTERED"
      | "POLICY_NOT_REGISTERED"
      | "SOURCE_NOT_REGISTERED"
      | "INVALID_TOKEN_DECIMALS"
      | "INVALID_ORACLE_DECIMALS"
      | "NON_POSITIVE_ORACLE_PRICE"
      | "STALE_ORACLE_PRICE"
      | "ORACLE_BLOCK_LAG"
      | "INCOMPLETE_ORACLE_ROUND"
      | "LOW_ORACLE_CONFIDENCE"
      | "INSUFFICIENT_VALID_SOURCES"
      | "ORACLE_DEVIATION_EXCEEDED"
      | "DIVISION_BY_ZERO"
      | "NEGATIVE_VALUE"
      | "UNSAFE_DECIMAL_EXPONENT",
    message: string,
  ) {
    super(`${code}: ${message}`);
    this.name = "PricingError";
  }
}

export class PrecisionPricingEngine {
  private readonly tokens = new Map<string, TokenMetadata>();
  private readonly policies = new Map<string, TokenOraclePolicy>();
  private readonly sources = new Map<string, OracleSource>();

  constructor(
    tokens: TokenMetadata[],
    policies: TokenOraclePolicy[],
    sources: OracleSource[],
  ) {
    for (const token of tokens) {
      this.validateDecimals(token.decimals, "token");
      this.tokens.set(this.key(token.chainId, token.address), token);
    }

    for (const policy of policies) {
      this.policies.set(policy.token.toLowerCase(), policy);
    }

    for (const source of sources) {
      this.sources.set(source.id, source);
    }
  }

  getToken(chainId: number, address: Address): TokenMetadata {
    const token = this.tokens.get(this.key(chainId, address));

    if (!token) {
      throw new PricingError(
        "TOKEN_NOT_REGISTERED",
        `No metadata exists for ${chainId}:${address}`,
      );
    }

    return token;
  }

  /**
   * Resolves one token's USD price through the configured multi-oracle policy.
   */
  async getUsdPrice(
    tokenAddress: Address,
    context: PricingContext,
  ): Promise<PriceResult> {
    const token = this.getToken(context.chainId, tokenAddress);
    const policy = this.policies.get(tokenAddress.toLowerCase());

    if (!policy) {
      throw new PricingError(
        "POLICY_NOT_REGISTERED",
        `No oracle policy exists for ${token.symbol}`,
      );
    }

    const observations: OracleObservation[] = [];
    const failures: string[] = [];

    for (const sourceId of policy.sourceIds) {
      const source = this.sources.get(sourceId);

      if (!source) {
        failures.push(`${sourceId}:SOURCE_NOT_REGISTERED`);
        continue;
      }

      try {
        const observation = await source.readUsdPrice(token, context);
        this.validateObservation(observation, policy, context);
        observations.push(observation);
      } catch (error) {
        failures.push(
          `${sourceId}:${
            error instanceof Error ? error.message : String(error)
          }`,
        );
      }
    }

    if (observations.length < policy.minimumValidSources) {
      throw new PricingError(
        "INSUFFICIENT_VALID_SOURCES",
        [
          `${token.symbol} requires ${policy.minimumValidSources}`,
          `valid sources but received ${observations.length}.`,
          `Failures: ${failures.join(" | ")}`,
        ].join(" "),
      );
    }

    const normalized = observations.map((observation) => ({
      observation,
      priceUsdX18: scaleDecimals(
        observation.answer,
        observation.answerDecimals,
        PRICE_DECIMALS,
      ),
    }));

    const minimum = minBigInt(normalized.map((x) => x.priceUsdX18));
    const maximum = maxBigInt(normalized.map((x) => x.priceUsdX18));

    const deviationBps = calculateDeviationBps(minimum, maximum);

    if (deviationBps > policy.maximumDeviationBps) {
      throw new PricingError(
        "ORACLE_DEVIATION_EXCEEDED",
        `${token.symbol} source deviation ${deviationBps} bps exceeds ${
          policy.maximumDeviationBps
        } bps`,
      );
    }

    const selectedPrice = aggregatePrices(
      normalized.map((x) => x.priceUsdX18),
      policy.aggregation,
    );

    return {
      token,
      priceUsdX18: selectedPrice,
      observedAtBlock: minBigInt(
        observations.map((x) => x.observedAtBlock),
      ),
      updatedAt: minBigInt(observations.map((x) => x.updatedAt)),
      sourcesUsed: observations.map((x) => x.sourceId),
      sourceDeviationBps: deviationBps,
      confidenceBps: minBigInt(
        observations.map((x) => x.confidenceBps ?? BPS_DENOMINATOR),
      ),
    };
  }

  /**
   * Converts raw ERC-20 atomic units to USD fixed-point units.
   *
   * Result uses 18 USD decimals.
   */
  tokenAtomicToUsdX18(
    amountAtomic: bigint,
    token: TokenMetadata,
    priceUsdX18: bigint,
    rounding: Rounding = "DOWN",
  ): bigint {
    assertNonNegative(amountAtomic);
    assertPositive(priceUsdX18);

    const tokenScale = pow10(token.decimals);

    return mulDiv(
      amountAtomic,
      priceUsdX18,
      tokenScale,
      rounding,
    );
  }

  /**
   * Converts USD fixed-point value back into token atomic units.
   */
  usdX18ToTokenAtomic(
    usdValueX18: bigint,
    token: TokenMetadata,
    priceUsdX18: bigint,
    rounding: Rounding = "UP",
  ): bigint {
    assertNonNegative(usdValueX18);
    assertPositive(priceUsdX18);

    return mulDiv(
      usdValueX18,
      pow10(token.decimals),
      priceUsdX18,
      rounding,
    );
  }

  /**
   * Calculates the cross price:
   *
   * quote-token units required for one base token.
   */
  derivePairPrice(
    base: PriceResult,
    quote: PriceResult,
    rounding: Rounding = "DOWN",
  ): PricePair {
    assertPositive(quote.priceUsdX18);

    const quotePerBaseX18 = mulDiv(
      base.priceUsdX18,
      PRICE_SCALE,
      quote.priceUsdX18,
      rounding,
    );

    return {
      base: base.token,
      quote: quote.token,
      quotePerBaseX18,
      baseUsdX18: base.priceUsdX18,
      quoteUsdX18: quote.priceUsdX18,
    };
  }

  /**
   * Converts costs denominated in one token into another token.
   *
   * Used for:
   * gas token → flashloan token
   * relay token → flashloan token
   * profit token → USD
   */
  convertTokenAtomic(
    amountInAtomic: bigint,
    tokenIn: TokenMetadata,
    tokenInUsdX18: bigint,
    tokenOut: TokenMetadata,
    tokenOutUsdX18: bigint,
    rounding: Rounding = "UP",
  ): bigint {
    const usdValue = this.tokenAtomicToUsdX18(
      amountInAtomic,
      tokenIn,
      tokenInUsdX18,
      rounding,
    );

    return this.usdX18ToTokenAtomic(
      usdValue,
      tokenOut,
      tokenOutUsdX18,
      rounding,
    );
  }

  /**
   * Produces an executable venue price from actual leg amounts.
   *
   * amountIn / amountOut gives input-token units paid
   * per output-token unit received.
   */
  executablePriceX18(
    amountInAtomic: bigint,
    tokenIn: TokenMetadata,
    amountOutAtomic: bigint,
    tokenOut: TokenMetadata,
    rounding: Rounding = "UP",
  ): bigint {
    assertPositive(amountInAtomic);
    assertPositive(amountOutAtomic);

    const numerator =
      amountInAtomic *
      pow10(tokenOut.decimals) *
      PRICE_SCALE;

    const denominator =
      amountOutAtomic *
      pow10(tokenIn.decimals);

    return divide(numerator, denominator, rounding);
  }

  private validateObservation(
    observation: OracleObservation,
    policy: TokenOraclePolicy,
    context: PricingContext,
  ): void {
    this.validateDecimals(observation.answerDecimals, "oracle");

    if (observation.answer <= 0n) {
      throw new PricingError(
        "NON_POSITIVE_ORACLE_PRICE",
        `${observation.sourceId} returned ${observation.answer}`,
      );
    }

    if (
      observation.updatedAt <= 0n ||
      context.currentTimestamp < observation.updatedAt ||
      context.currentTimestamp - observation.updatedAt >
        policy.maxAgeSeconds
    ) {
      throw new PricingError(
        "STALE_ORACLE_PRICE",
        `${observation.sourceId} failed timestamp validation`,
      );
    }

    if (
      context.currentBlock < observation.observedAtBlock ||
      context.currentBlock - observation.observedAtBlock >
        policy.maxBlockLag
    ) {
      throw new PricingError(
        "ORACLE_BLOCK_LAG",
        `${observation.sourceId} exceeded block-lag policy`,
      );
    }

    if (
      observation.roundId !== undefined &&
      observation.answeredInRound !== undefined &&
      observation.answeredInRound < observation.roundId
    ) {
      throw new PricingError(
        "INCOMPLETE_ORACLE_ROUND",
        `${observation.sourceId} returned an incomplete round`,
      );
    }

    const confidence =
      observation.confidenceBps ?? BPS_DENOMINATOR;

    if (confidence < policy.minimumConfidenceBps) {
      throw new PricingError(
        "LOW_ORACLE_CONFIDENCE",
        `${observation.sourceId} confidence ${confidence} bps is below ${
          policy.minimumConfidenceBps
        } bps`,
      );
    }
  }

  private validateDecimals(
    decimals: number,
    type: "token" | "oracle",
  ): void {
    if (!Number.isInteger(decimals) || decimals < 0 || decimals > 36) {
      throw new PricingError(
        type === "token"
          ? "INVALID_TOKEN_DECIMALS"
          : "INVALID_ORACLE_DECIMALS",
        `${type} decimals ${decimals} are unsupported`,
      );
    }
  }

  private key(chainId: number, address: Address): string {
    return `${chainId}:${address.toLowerCase()}`;
  }
}

export type Rounding = "DOWN" | "UP" | "NEAREST";

/**
 * Scales an integer from one decimal precision to another.
 */
export function scaleDecimals(
  value: bigint,
  fromDecimals: number,
  toDecimals: number,
  rounding: Rounding = "DOWN",
): bigint {
  assertNonNegative(value);

  if (fromDecimals === toDecimals) {
    return value;
  }

  if (fromDecimals < toDecimals) {
    return value * pow10(toDecimals - fromDecimals);
  }

  return divide(
    value,
    pow10(fromDecimals - toDecimals),
    rounding,
  );
}

/**
 * Full-precision multiply-then-divide helper.
 *
 * JavaScript bigint does not overflow at uint256 boundaries, but downstream
 * Solidity implementations must use a full-precision mulDiv implementation.
 */
export function mulDiv(
  x: bigint,
  y: bigint,
  denominator: bigint,
  rounding: Rounding = "DOWN",
): bigint {
  if (denominator === 0n) {
    throw new PricingError(
      "DIVISION_BY_ZERO",
      "mulDiv denominator is zero",
    );
  }

  return divide(x * y, denominator, rounding);
}

export function divide(
  numerator: bigint,
  denominator: bigint,
  rounding: Rounding,
): bigint {
  if (denominator === 0n) {
    throw new PricingError(
      "DIVISION_BY_ZERO",
      "Division denominator is zero",
    );
  }

  const quotient = numerator / denominator;
  const remainder = numerator % denominator;

  if (remainder === 0n || rounding === "DOWN") {
    return quotient;
  }

  if (rounding === "UP") {
    return quotient + 1n;
  }

  return remainder * 2n >= denominator
    ? quotient + 1n
    : quotient;
}

export function calculateDeviationBps(
  minimum: bigint,
  maximum: bigint,
): bigint {
  assertPositive(minimum);

  return mulDiv(
    maximum - minimum,
    BPS_DENOMINATOR,
    minimum,
    "UP",
  );
}

export function aggregatePrices(
  prices: bigint[],
  mode: TokenOraclePolicy["aggregation"],
): bigint {
  if (prices.length === 0) {
    throw new PricingError(
      "INSUFFICIENT_VALID_SOURCES",
      "No prices were supplied for aggregation",
    );
  }

  const sorted = [...prices].sort((a, b) =>
    a < b ? -1 : a > b ? 1 : 0,
  );

  if (mode === "CONSERVATIVE_LOW") {
    return sorted[0];
  }

  if (mode === "CONSERVATIVE_HIGH") {
    return sorted[sorted.length - 1];
  }

  const middle = Math.floor(sorted.length / 2);

  if (sorted.length % 2 === 1) {
    return sorted[middle];
  }

  return (sorted[middle - 1] + sorted[middle]) / 2n;
}

export function pow10(decimals: number): bigint {
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 36) {
    throw new PricingError(
      "UNSAFE_DECIMAL_EXPONENT",
      `Unsupported decimal exponent ${decimals}`,
    );
  }

  return 10n ** BigInt(decimals);
}

function assertPositive(value: bigint): void {
  if (value <= 0n) {
    throw new PricingError(
      "NON_POSITIVE_ORACLE_PRICE",
      `Expected positive value; received ${value}`,
    );
  }
}

function assertNonNegative(value: bigint): void {
  if (value < 0n) {
    throw new PricingError(
      "NEGATIVE_VALUE",
      `Expected non-negative value; received ${value}`,
    );
  }
}

function minBigInt(values: bigint[]): bigint {
  if (values.length === 0) {
    throw new PricingError(
      "INSUFFICIENT_VALID_SOURCES",
      "Cannot determine minimum of an empty collection",
    );
  }

  return values.reduce((minimum, value) =>
    value < minimum ? value : minimum,
  );
}

function maxBigInt(values: bigint[]): bigint {
  if (values.length === 0) {
    throw new PricingError(
      "INSUFFICIENT_VALID_SOURCES",
      "Cannot determine maximum of an empty collection",
    );
  }

  return values.reduce((maximum, value) =>
    value > maximum ? value : maximum,
  );
}
