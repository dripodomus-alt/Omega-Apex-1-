import "dotenv/config";
import { ethers } from "ethers";
import { buildV2SwapCalldata, quoteV2Cpmm } from "../server/engine/routeAdapters.js";

const USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
const TOKENS = [
  { symbol: "USDC", address: USDC, decimals: 6 },
  { symbol: "WETH", address: "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", decimals: 18 },
  { symbol: "WMATIC", address: "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", decimals: 18 },
  { symbol: "WBTC", address: "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", decimals: 8 },
  { symbol: "USDT", address: "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", decimals: 6 },
  { symbol: "DAI", address: "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", decimals: 18 },
];
const VENUES = [
  { name: "QuickSwapV2", factory: "0x5757371414417b8c6caad45baef941abc7d3ab32", router: "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff", feeBps: 30n },
  { name: "SushiSwapV2", factory: "0xc35DADB65012eC5796536bD9864eD8773aBc74C4", router: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506", feeBps: 30n },
];

const FACTORY_ABI = ["function getPair(address,address) view returns (address)"];
const PAIR_ABI = [
  "function token0() view returns (address)",
  "function token1() view returns (address)",
  "function getReserves() view returns (uint112 reserve0,uint112 reserve1,uint32 blockTimestampLast)",
];

type Token = typeof TOKENS[number];
type Venue = typeof VENUES[number];
type PairState = {
  venue: Venue;
  pair: string;
  token0: string;
  token1: string;
  reserve0: bigint;
  reserve1: bigint;
};

function rpcUrl() {
  return process.env.POLYGON_RPC_URL || process.env.POLYGON_RPC || process.env.RPC_URL || "https://polygon-bor-rpc.publicnode.com";
}

function reserveSide(pair: PairState, tokenIn: string, tokenOut: string) {
  if (pair.token0.toLowerCase() === tokenIn.toLowerCase() && pair.token1.toLowerCase() === tokenOut.toLowerCase()) {
    return { reserveIn: pair.reserve0, reserveOut: pair.reserve1 };
  }
  if (pair.token1.toLowerCase() === tokenIn.toLowerCase() && pair.token0.toLowerCase() === tokenOut.toLowerCase()) {
    return { reserveIn: pair.reserve1, reserveOut: pair.reserve0 };
  }
  throw new Error("PAIR_TOKEN_MISMATCH");
}

function rawToFloat(raw: bigint, decimals: number) {
  return Number(ethers.formatUnits(raw, decimals));
}

function floatToUsdcRaw(value: number) {
  if (!Number.isFinite(value) || value <= 0) return 0n;
  return BigInt(Math.floor(value * 1e6));
}

function routeTokenPaths(maxHops: number) {
  const intermediates = TOKENS.filter((token) => token.symbol !== "USDC");
  const paths: Token[][] = [];
  const walk = (prefix: Token[], depth: number) => {
    if (depth === 0) {
      paths.push([TOKENS[0], ...prefix, TOKENS[0]]);
      return;
    }
    for (const token of intermediates) {
      if (prefix.some((item) => item.symbol === token.symbol)) continue;
      walk([...prefix, token], depth - 1);
    }
  };
  for (let hops = 2; hops <= maxHops; hops += 1) {
    walk([], hops - 1);
  }
  return paths;
}

function venueCombos(hops: number): Venue[][] {
  let combos: Venue[][] = [[]];
  for (let i = 0; i < hops; i += 1) {
    combos = combos.flatMap((combo) => VENUES.map((venue) => [...combo, venue]));
  }
  return combos;
}

async function loadPairs(provider: ethers.JsonRpcProvider) {
  const cache = new Map<string, PairState | null>();
  async function getPair(venue: Venue, tokenA: Token, tokenB: Token) {
    const key = `${venue.name}:${tokenA.symbol}:${tokenB.symbol}`;
    const reverseKey = `${venue.name}:${tokenB.symbol}:${tokenA.symbol}`;
    if (cache.has(key)) return cache.get(key);
    if (cache.has(reverseKey)) return cache.get(reverseKey);
    const factory = new ethers.Contract(venue.factory, FACTORY_ABI, provider);
    const pair = await factory.getPair(tokenA.address, tokenB.address);
    if (pair === ethers.ZeroAddress || await provider.getCode(pair) === "0x") {
      cache.set(key, null);
      return null;
    }
    const pairContract = new ethers.Contract(pair, PAIR_ABI, provider);
    const [token0, token1, reserves] = await Promise.all([
      pairContract.token0(),
      pairContract.token1(),
      pairContract.getReserves(),
    ]);
    const state = {
      venue,
      pair,
      token0: ethers.getAddress(token0),
      token1: ethers.getAddress(token1),
      reserve0: reserves.reserve0 as bigint,
      reserve1: reserves.reserve1 as bigint,
    };
    cache.set(key, state);
    return state;
  }
  return { getPair, cache };
}

async function main() {
  const maxHopsArg = process.argv.find((arg) => arg.startsWith("--max-hops="));
  const maxHops = Math.max(2, Math.min(4, Number(maxHopsArg?.split("=")[1] || process.env.MAX_ROUTE_HOPS || 4)));
  const minRouteTlvUsd = Number(process.env.MIN_ROUTE_TLV_USD || "10000");
  const requireCrossDex = process.env.ALLOW_SINGLE_VENUE_ROUTES !== "true";
  const provider = new ethers.JsonRpcProvider(rpcUrl(), 137, { staticNetwork: true });
  const { getPair, cache } = await loadPairs(provider);

  const priceUsdc = new Map<string, number>([["USDC", 1]]);
  for (const token of TOKENS.filter((item) => item.symbol !== "USDC")) {
    for (const venue of VENUES) {
      const pair = await getPair(venue, TOKENS[0], token);
      if (!pair) continue;
      const usdcSide = reserveSide(pair, USDC, token.address);
      const usdcReserve = rawToFloat(usdcSide.reserveIn, 6);
      const tokenReserve = rawToFloat(usdcSide.reserveOut, token.decimals);
      if (usdcReserve > 0 && tokenReserve > 0) {
        priceUsdc.set(token.symbol, usdcReserve / tokenReserve);
        break;
      }
    }
  }

  const candidates: any[] = [];
  let evaluated = 0;
  let skippedMissingPair = 0;
  let rejectedRepeatedPool = 0;
  let rejectedSingleVenue = 0;
  let rejectedTlv = 0;
  for (const path of routeTokenPaths(maxHops)) {
    const hops = path.length - 1;
    for (const venues of venueCombos(hops)) {
      const pairs: PairState[] = [];
      let missing = false;
      for (let i = 0; i < hops; i += 1) {
        const pair = await getPair(venues[i], path[i], path[i + 1]);
        if (!pair) {
          missing = true;
          break;
        }
        pairs.push(pair);
      }
      if (missing) {
        skippedMissingPair += 1;
        continue;
      }
      if (new Set(pairs.map((pair) => pair.pair.toLowerCase())).size !== pairs.length) {
        rejectedRepeatedPool += 1;
        continue;
      }
      if (requireCrossDex && new Set(venues.map((venue) => venue.name)).size < 2) {
        rejectedSingleVenue += 1;
        continue;
      }

      const tvls = pairs.map((pair) => {
        const token0 = TOKENS.find((token) => token.address.toLowerCase() === pair.token0.toLowerCase());
        const token1 = TOKENS.find((token) => token.address.toLowerCase() === pair.token1.toLowerCase());
        if (!token0 || !token1) return 0;
        const p0 = priceUsdc.get(token0.symbol);
        const p1 = priceUsdc.get(token1.symbol);
        if (!p0 || !p1) return 0;
        return (rawToFloat(pair.reserve0, token0.decimals) * p0) + (rawToFloat(pair.reserve1, token1.decimals) * p1);
      }).filter((value) => value > 0);
      if (tvls.length !== pairs.length) continue;
      if (Math.min(...tvls) < minRouteTlvUsd) {
        rejectedTlv += 1;
        continue;
      }
      const amountIn = floatToUsdcRaw(Math.min(...tvls) * 0.15);
      if (amountIn <= 0n) continue;

      let amount = amountIn;
      let ok = true;
      for (let i = 0; i < hops; i += 1) {
        const side = reserveSide(pairs[i], path[i].address, path[i + 1].address);
        amount = quoteV2Cpmm(amount, side.reserveIn, side.reserveOut, Number(pairs[i].venue.feeBps));
        if (amount <= 0n) {
          ok = false;
          break;
        }
      }
      if (!ok) continue;
      evaluated += 1;
      const profitRaw = amount - amountIn;
      candidates.push({
        path: path.map((token) => token.symbol).join("->"),
        venues: venues.map((venue) => venue.name).join("->"),
        hops,
        amountInRaw: amountIn.toString(),
        amountInUsdc: ethers.formatUnits(amountIn, 6),
        amountOutRaw: amount.toString(),
        amountOutUsdc: ethers.formatUnits(amount, 6),
        grossProfitRaw: profitRaw.toString(),
        grossProfitUsdc: ethers.formatUnits(profitRaw, 6),
        profitableBeforeGas: profitRaw > 0n,
        lowestPoolTvlUsdc: Math.min(...tvls),
        sizingRule: "15_PERCENT_OF_LOWEST_ROUTE_POOL_TVL",
        adapterIds: pairs.map(() => "UNISWAP_V2_SWAP_EXACT_TOKENS_FOR_TOKENS"),
        invariantTypes: pairs.map(() => "V2_CPMM"),
        calldataPreviewSelectors: pairs.map((pair, idx) => buildV2SwapCalldata(
          1n,
          1n,
          [path[idx].address, path[idx + 1].address],
          USDC,
          Math.floor(Date.now() / 1000) + 300,
        ).slice(0, 10)),
        pairs: pairs.map((pair) => ({ venue: pair.venue.name, pair: pair.pair })),
      });
    }
  }
  candidates.sort((a, b) => Number(BigInt(b.grossProfitRaw) - BigInt(a.grossProfitRaw)));

  console.log(`DYNAMIC_ROUTE_AUDIT|chainId=137|maxHops=${maxHops}|tokenCount=${TOKENS.length}|venueCount=${VENUES.length}|pairCache=${cache.size}|evaluated=${evaluated}|skippedMissingPair=${skippedMissingPair}|rejectedRepeatedPool=${rejectedRepeatedPool}|rejectedSingleVenue=${rejectedSingleVenue}|rejectedTlv=${rejectedTlv}|minRouteTlvUsd=${minRouteTlvUsd}|requireCrossDex=${requireCrossDex}|profitable=${candidates.filter((item) => item.profitableBeforeGas).length}|pnlUpdated=false`);
  console.log(`TOKEN_PRICE_MAP|${JSON.stringify(Object.fromEntries(priceUsdc.entries()))}`);
  for (const candidate of candidates.slice(0, 20)) {
    console.log(`ROUTE_CANDIDATE|path=${candidate.path}|venues=${candidate.venues}|hops=${candidate.hops}|amountIn=${candidate.amountInUsdc}|amountOut=${candidate.amountOutUsdc}|grossProfit=${candidate.grossProfitUsdc}|profitableBeforeGas=${candidate.profitableBeforeGas}|lowestPoolTvlUsdc=${candidate.lowestPoolTvlUsdc.toFixed(2)}|pnlUpdated=false`);
  }
}

main().catch((error) => {
  console.error(`DYNAMIC_ROUTE_AUDIT_FAILED|${error?.message || error}`);
  process.exit(1);
});
