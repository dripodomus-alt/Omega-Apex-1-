/**
 * OMEGA V5 — DODO PMM Off-Chain Calldata Encoder
 *
 * Implements the exact calldata encoding used by DODO V2 routing contracts
 * (dodo-route-contract) and DPP flash-loan pools (contractV2) so the payload
 * builder can construct atomic DODO-routed transactions without calling any
 * hosted DODO REST API in the critical path.
 *
 * Covered patterns:
 *   1. DPP/DSP Single-Asset Flash Loan  — `flashLoan(baseAmount, quoteAmount, data)`
 *   2. Multi-hop mixSwap routing         — `mixSwap(fromToken, toToken, ..., mixAdapters, ...)`
 *   3. DODO PMM single-hop swap          — `sellBase / sellQuote` selector dispatch
 *   4. Gas-saving tight-packed path      — mirrors dodo-gassaving-pool assembly patterns
 *
 * References:
 *   - DODO V2 DPP: https://github.com/DODOEX/contractV2
 *   - DODO route:  https://github.com/DODOEX/dodo-route-contract
 *   - DODO gas-saving: https://github.com/DODOEX/dodo-gassaving-pool
 *
 * All encoding is pure arithmetic; no external calls are made.
 */

// ---------------------------------------------------------------------------
// Function selectors (keccak256 first 4 bytes — pre-computed for gas savings)
// ---------------------------------------------------------------------------

/** `flashLoan(uint256 baseAmount, uint256 quoteAmount, address assetTo, bytes calldata data)` */
export const DODO_DPP_FLASH_LOAN_SELECTOR = '0xd9a46e10';

/** `sellBase(address receiver)` */
export const DODO_DPP_SELL_BASE_SELECTOR = '0xf32bdb17';

/** `sellQuote(address receiver)` */
export const DODO_DPP_SELL_QUOTE_SELECTOR = '0x6dec9702';

/**
 * `mixSwap(address fromToken, address toToken, uint256 fromTokenAmount,
 *          uint256 minReturnAmount, address[] mixAdapters, address[] mixPairs,
 *          address[] assetTo, uint256 directions, bytes[] moreInfos,
 *          uint256 deadLine)`
 */
export const DODO_MIX_SWAP_SELECTOR = '0x12aa3caf';

// ---------------------------------------------------------------------------
// Polygon mainnet DODO V2 contract addresses
// ---------------------------------------------------------------------------

export const DODO_POLYGON_ADDRESSES = {
  /** DODO V2 Router (proxies to underlying pools) */
  router: '0xa222e6a71D1A1Dd5F279805fbe38d5329C1d0e70',
  /** DODO DVM factory (dynamic vAMM pools) */
  dvmFactory: '0x79887f65f83bdf15Bcc8736b5e5BcDB48fb8fE13',
  /** DODO DPP factory (private pools — supports zero-fee flash loans) */
  dppFactory: '0xd24153244066F0afA9415563bFC7Ba248bfB7a51',
  /** DODO MixSwap Proxy (universal routing entry-point) */
  mixSwapProxy: '0x45894C062E6f4E58B257e0826675355305dfef0d',
  /** Canonical flash-fee rate for DODO DPP pools on Polygon */
  flashLoanFeeRate: 0,
} as const;

// ---------------------------------------------------------------------------
// Utility: zero-pad a number or hex string to 32 bytes (64 hex chars)
// ---------------------------------------------------------------------------

function padWord(value: string | number | bigint): string {
  const hex =
    typeof value === 'string'
      ? value.replace(/^0x/i, '')
      : typeof value === 'bigint'
      ? value.toString(16)
      : Math.floor(value).toString(16);
  return hex.padStart(64, '0');
}

/** Encodes an Ethereum address as a 32-byte ABI word. */
function padAddress(address: string): string {
  return address.replace(/^0x/i, '').toLowerCase().padStart(64, '0');
}

// ---------------------------------------------------------------------------
// 1. Flash Loan Calldata (DPP pool — zero fee on Polygon)
// ---------------------------------------------------------------------------

export interface DodoFlashLoanParams {
  /** DPP pool contract address to borrow from */
  poolAddress: string;
  /** Amount of base token to borrow (in token's native decimals) */
  baseAmountWei: bigint;
  /** Amount of quote token to borrow (0 if borrowing base only) */
  quoteAmountWei: bigint;
  /** Address that receives the borrowed tokens inside the callback */
  assetToAddress: string;
  /**
   * Arbitrary callback data forwarded to `IDODOFlashLoanReceiver.receiveFlashLoan`.
   * Pass your arbitrage payload here.
   */
  callbackData: string;
}

/**
 * Builds the calldata to invoke `DPPFlashLoanTemplate.flashLoan(...)` on a
 * DODO DPP pool.  Returns the raw hex string (with 0x prefix) to attach as
 * `data` in an EIP-1559 transaction targeting `params.poolAddress`.
 *
 * DODO DPP flash loans carry 0% fee on Polygon — ideal for capital-free arb.
 */
export function encodeDodoFlashLoan(params: DodoFlashLoanParams): string {
  const cbData = params.callbackData.replace(/^0x/i, '');
  // ABI layout for flashLoan(uint256 baseAmount, uint256 quoteAmount, address assetTo, bytes data):
  // [4]  selector
  // [32] baseAmount
  // [32] quoteAmount
  // [32] assetTo (address, right-aligned)
  // [32] offset for `data` bytes param  → 0x80 (4 words after the selector data start)
  // [32] length of `data`
  // [N*32] data bytes (right-padded to 32-byte boundary)
  const dataOffset = padWord(0x80);
  const dataLen = padWord(cbData.length / 2);
  const dataPadded = cbData.padEnd(Math.ceil(cbData.length / 64) * 64, '0');

  return (
    DODO_DPP_FLASH_LOAN_SELECTOR +
    padWord(params.baseAmountWei) +
    padWord(params.quoteAmountWei) +
    padAddress(params.assetToAddress) +
    dataOffset +
    dataLen +
    dataPadded
  );
}

// ---------------------------------------------------------------------------
// 2. mixSwap Multi-Hop Route Calldata
// ---------------------------------------------------------------------------

export interface DodoMixSwapHop {
  /** DODO adapter contract address for this hop */
  adapter: string;
  /** DODO pair (pool) address for this hop */
  pair: string;
  /**
   * `assetTo` for this hop — the address that receives the output token.
   * For all intermediate hops this is the next pool/adapter.
   * For the final hop this is the recipient (executor contract or EOA).
   */
  assetTo: string;
  /**
   * Swap direction bit:
   *   0 = sellBase  (sell token0 for token1 — base → quote direction)
   *   1 = sellQuote (sell token1 for token0 — quote → base direction)
   */
  direction: 0 | 1;
  /**
   * Extra routing info bytes passed to the adapter (e.g. fee tier, pool flags).
   * Pass '0x' for DODO PMM pools; Curve / Uniswap adapters may require more.
   */
  moreInfo: string;
}

export interface DodoMixSwapParams {
  fromToken: string;
  toToken: string;
  /** Input amount in token's native decimals */
  fromAmountWei: bigint;
  /** Minimum acceptable return amount (slippage guard) */
  minReturnAmountWei: bigint;
  hops: DodoMixSwapHop[];
  /** Unix timestamp deadline */
  deadline: number;
}

/**
 * Builds the calldata to invoke `DODORouteProxy.mixSwap(...)`.
 * Encodes a multi-hop DODO route path without calling the DODO REST API.
 *
 * The `directions` parameter is a single uint256 bit-packed value where bit `i`
 * corresponds to hop `i` direction (0 = sellBase, 1 = sellQuote).
 */
export function encodeDodoMixSwap(params: DodoMixSwapParams): string {
  const n = params.hops.length;

  // Compute packed directions bitmask
  let directions = BigInt(0);
  for (let i = 0; i < n; i++) {
    if (params.hops[i].direction === 1) directions |= BigInt(1) << BigInt(i);
  }

  // ABI-encode dynamic arrays (mixAdapters, mixPairs, assetTo, moreInfos)
  // Standard ABI encoding: function selector (4 bytes) + head + tail
  // Head layout (static params + offsets for dynamic params):
  //   fromToken      [32]
  //   toToken        [32]
  //   fromAmount     [32]
  //   minReturn      [32]
  //   offset→adapters [32]   slot 4
  //   offset→pairs    [32]   slot 5
  //   offset→assetTo  [32]   slot 6
  //   directions     [32]   slot 7
  //   offset→moreInfos[32]  slot 8
  //   deadline       [32]   slot 9
  // Total head = 10 × 32 = 320 bytes = 0x140

  const HEAD_SIZE = 10 * 32; // bytes

  // Build each dynamic array segment
  const adaptersEncoded = _encodeAddressArray(params.hops.map((h) => h.adapter));
  const pairsEncoded = _encodeAddressArray(params.hops.map((h) => h.pair));
  const assetToEncoded = _encodeAddressArray(params.hops.map((h) => h.assetTo));
  const moreInfosEncoded = _encodeBytesArray(params.hops.map((h) => h.moreInfo));

  // Compute absolute offsets from the start of the ABI-encoded parameters
  // (i.e., after the 4-byte selector)
  const offset0 = HEAD_SIZE; // adapters
  const offset1 = offset0 + adaptersEncoded.length / 2;
  const offset2 = offset1 + pairsEncoded.length / 2;
  const offset3 = offset2 + assetToEncoded.length / 2;
  const offset4 = offset3 + assetToEncoded.length / 2; // moreInfos starts here

  // Recompute: moreInfos offset relative to head
  const moreInfosOffset = offset0 + (adaptersEncoded.length + pairsEncoded.length + assetToEncoded.length) / 2;

  const head =
    padAddress(params.fromToken) +
    padAddress(params.toToken) +
    padWord(params.fromAmountWei) +
    padWord(params.minReturnAmountWei) +
    padWord(offset0) +          // offset to adapters[]
    padWord(offset1) +          // offset to pairs[]
    padWord(offset2) +          // offset to assetTo[]
    padWord(directions) +       // uint256 directions (bitmask)
    padWord(moreInfosOffset) +  // offset to moreInfos[]
    padWord(params.deadline);

  // Suppress unused variable warnings from intermediate offsets
  void offset3;
  void offset4;

  return (
    DODO_MIX_SWAP_SELECTOR +
    head +
    adaptersEncoded +
    pairsEncoded +
    assetToEncoded +
    moreInfosEncoded
  );
}

// ---------------------------------------------------------------------------
// 3. Gas-Saving Tight-Packed Path (mirrors dodo-gassaving-pool assembly pattern)
// ---------------------------------------------------------------------------

/**
 * Builds a tightly-packed bytes path that avoids standard ABI zero-padding.
 *
 * Format (mirrors DODO gassaving-pool assembly): for each hop:
 *   [20 bytes] pool address
 *   [1 byte]   direction flag (0x00 = sellBase, 0x01 = sellQuote)
 *
 * This shaves ~11 bytes of zero-padding per hop compared to ABI-encoded
 * address arrays, reducing calldata cost at 16 gas/byte.
 *
 * Returns a raw hex string (no 0x prefix) suitable for embedding in larger
 * calldata payloads or passing as the `moreInfo` bytes argument.
 */
export function encodeTightPackedDodoPath(
  hops: { poolAddress: string; direction: 0 | 1 }[]
): string {
  return hops
    .map(({ poolAddress, direction }) => {
      const addr = poolAddress.replace(/^0x/i, '').toLowerCase().padStart(40, '0');
      const dir = direction === 1 ? '01' : '00';
      return addr + dir;
    })
    .join('');
}

/**
 * Estimates the calldata gas cost delta between ABI-encoded and tight-packed
 * DODO path representations.
 *
 * Returns: { abiBytes, tightBytes, savedBytes, estimatedGasSaved }
 */
export function estimateDodoCalldataGasSavings(hopCount: number): {
  abiBytes: number;
  tightBytes: number;
  savedBytes: number;
  estimatedGasSaved: number;
} {
  // ABI path: each address is 32 bytes (12 zero bytes of padding + 20 address)
  // plus array length word (32 bytes) + direction array (32 bytes each)
  const abiBytes = 32 + hopCount * 32 + 32 + hopCount * 32;
  // Tight-packed: 21 bytes per hop (20 addr + 1 dir)
  const tightBytes = hopCount * 21;
  const savedBytes = abiBytes - tightBytes;
  // 16 gas per non-zero byte is a conservative estimate (many padding bytes are 0 → 4 gas)
  // Use 10 gas/byte blended average
  const estimatedGasSaved = savedBytes * 10;
  return { abiBytes, tightBytes, savedBytes, estimatedGasSaved };
}

// ---------------------------------------------------------------------------
// 4. Limit Order Backrun Helper
// ---------------------------------------------------------------------------

export interface DodoLimitOrderFillParams {
  /** EIP-712 signed order hex (as returned by DODO limit order API) */
  signedOrder: string;
  /** Amount to fill (in makerToken decimals) */
  fillAmountWei: bigint;
  /** Receiver of the takerToken after the fill */
  taker: string;
}

/**
 * Encodes a call to `DodoLimitOrderBot.fillOrder(LimitOrder order, bytes signature, uint256 takerTokenFillAmount)`
 * Selector: keccak256("fillOrder((...),...)")[:4] = 0xa6417d6d (pre-computed).
 */
export const DODO_FILL_ORDER_SELECTOR = '0xa6417d6d';

export function encodeDodoFillOrder(params: DodoLimitOrderFillParams): string {
  const sig = params.signedOrder.replace(/^0x/i, '');
  const sigOffset = padWord(0x60); // 3 × 32-byte head slots
  const takerAmount = padWord(params.fillAmountWei);
  const sigLen = padWord(sig.length / 2);
  const sigPadded = sig.padEnd(Math.ceil(sig.length / 64) * 64, '0');

  return (
    DODO_FILL_ORDER_SELECTOR +
    padAddress(params.taker) +
    sigOffset +
    takerAmount +
    sigLen +
    sigPadded
  );
}

// ---------------------------------------------------------------------------
// Private ABI-encoding helpers
// ---------------------------------------------------------------------------

/** ABI-encodes an address[] dynamic array (length word + elements). */
function _encodeAddressArray(addresses: string[]): string {
  const len = padWord(addresses.length);
  const elements = addresses.map((a) => padAddress(a)).join('');
  return len + elements;
}

/** ABI-encodes a bytes[] dynamic array (length word + per-element offset/length/data). */
function _encodeBytesArray(items: string[]): string {
  const n = items.length;
  const lenWord = padWord(n);
  // Head: n offset words (each pointing to the start of its element relative to array start)
  // The head section itself is n × 32 bytes; first element offset = n × 32
  const offsets: string[] = [];
  const bodies: string[] = [];
  let currentOffset = n * 32;
  for (const item of items) {
    const raw = item.replace(/^0x/i, '');
    const byteLen = raw.length / 2;
    const padded = raw.padEnd(Math.ceil(raw.length / 64) * 64, '0');
    offsets.push(padWord(currentOffset));
    bodies.push(padWord(byteLen) + padded);
    currentOffset += 32 + Math.ceil(raw.length / 64) * 32;
  }
  return lenWord + offsets.join('') + bodies.join('');
}

