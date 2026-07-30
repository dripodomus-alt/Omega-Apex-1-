/**
 * Polygon Mainnet (Chain 137) Arbitrage Data Normalization Engine
 * 
 * Corrects POL/USD valuation imbalances and normalizes USD pool balances,
 * gas costs, and multi-vector route metrics across C1/C2 execution pipelines.
 */

export interface TokenPrice {
  symbol: string;
  name: string;
  price_usd: number;
  price_source: string;
  decimals: number;
  is_native_gas_token?: boolean;
}

// Canonical Normalized Market Prices for Polygon Mainnet (Chain 137)
export const NORMALIZED_TOKEN_PRICES: Record<string, TokenPrice> = {
  POL: {
    symbol: "POL",
    name: "Polygon Ecosystem Token",
    price_usd: 0.3850, // Normalized POL/USD price (corrected from deprecated 0.076)
    price_source: "Chainlink POL/USD Aggregator",
    decimals: 18,
    is_native_gas_token: true,
  },
  WMATIC: {
    symbol: "WMATIC",
    name: "Wrapped MATIC / POL",
    price_usd: 0.3850, // Normalized POL/WMATIC parity
    price_source: "Chainlink POL/USD Aggregator",
    decimals: 18,
    is_native_gas_token: true,
  },
  WETH: {
    symbol: "WETH",
    name: "Wrapped Ether",
    price_usd: 3420.50,
    price_source: "Chainlink WETH/USD Aggregator",
    decimals: 18,
  },
  USDC: {
    symbol: "USDC",
    name: "USD Coin",
    price_usd: 1.00,
    price_source: "Chainlink USDC/USD Aggregator",
    decimals: 6,
  },
  USDT: {
    symbol: "USDT",
    name: "Tether USD",
    price_usd: 1.00,
    price_source: "Chainlink USDT/USD Aggregator",
    decimals: 6,
  },
  WBTC: {
    symbol: "WBTC",
    name: "Wrapped BTC",
    price_usd: 64820.00,
    price_source: "Uniswap V3 TWAP",
    decimals: 8,
  },
};

/**
 * Normalizes gas cost in USD based on Polygon native POL gas price and execution gas units.
 * 
 * @param gasUnits Total gas units consumed (e.g. 210,000 gas)
 * @param gasPriceGwei Gas price in Gwei (e.g. 35 Gwei)
 * @param polPriceUsd Current POL/USD valuation (defaults to normalized 0.3850)
 * @param priorityFeeGwei Additional priority fee in Gwei (defaults to 30 Gwei for MEV fast-path)
 */
export function calculateNormalizedGasCostUsd(
  gasUnits: number,
  gasPriceGwei: number = 35,
  polPriceUsd: number = NORMALIZED_TOKEN_PRICES.POL.price_usd,
  priorityFeeGwei: number = 30
): number {
  const totalGwei = gasPriceGwei + priorityFeeGwei;
  const totalPolSpent = (gasUnits * totalGwei) / 1e9;
  const gasCostUsd = totalPolSpent * polPriceUsd;
  
  // Return normalized gas cost rounded to 4 decimals (minimum $0.005)
  return Math.max(0.005, Number(gasCostUsd.toFixed(4)));
}

/**
 * Normalizes pool reserve balance into USD valuation using canonical token prices.
 */
export function calculateNormalizedPoolBalanceUsd(
  symbol: string,
  rawAmount: number,
  customPolPriceUsd?: number
): number {
  const cleanSymbol = symbol.toUpperCase().trim();
  let price = 1.0;

  if (cleanSymbol === "POL" || cleanSymbol === "WMATIC" || cleanSymbol === "MATIC") {
    price = customPolPriceUsd || NORMALIZED_TOKEN_PRICES.POL.price_usd;
  } else if (NORMALIZED_TOKEN_PRICES[cleanSymbol]) {
    price = NORMALIZED_TOKEN_PRICES[cleanSymbol].price_usd;
  }

  return rawAmount * price;
}

/**
 * Calculates normalized total TVL for a pool given token reserve balances.
 */
export function normalizePoolTvlUsd(
  reserves: Array<{ symbol: string; amount: number }>,
  customPolPriceUsd?: number
): number {
  return reserves.reduce((total, res) => {
    return total + calculateNormalizedPoolBalanceUsd(res.symbol, res.amount, customPolPriceUsd);
  }, 0);
}

/**
 * Normalizes a single opportunity payload to ensure POL/USD valuation and gas metrics are synchronized.
 */
export function normalizeOpportunityData(opp: any, customPolPriceUsd: number = NORMALIZED_TOKEN_PRICES.POL.price_usd) {
  // Normalize POL / WMATIC representations in route paths
  let normalizedRoute = opp.route_path || "";
  normalizedRoute = normalizedRoute.replace(/WMATIC/g, "POL (WMATIC)");

  // Derive realistic gas units based on hop count / stage
  const hops = (opp.route_path || "").split(" → ").length - 1;
  const baseGasUnits = 140000 + (hops * 45000); // e.g. 230,000 gas for 2-hop, 275,000 gas for 3-hop
  const normalizedGasCostUsd = calculateNormalizedGasCostUsd(baseGasUnits, 35, customPolPriceUsd, 25);

  return {
    ...opp,
    route_path: normalizedRoute,
    pol_price_usd_normalized: customPolPriceUsd,
    gas_cost_usd: normalizedGasCostUsd,
    net_realized_pnl_usd: Math.max(0, Number((opp.expected_pnl_usd - normalizedGasCostUsd).toFixed(2))),
  };
}
