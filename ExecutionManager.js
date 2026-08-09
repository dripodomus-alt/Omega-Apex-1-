import { ethers } from 'ethers';

const APEX_VM_EXECUTION_ABI = [
  'function globalNonce() view returns (uint256)',
  'function executeC1(uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external',
  'function executeC2(bytes32 c1InternalId, uint8 flashloanSource, address flashloanAsset, uint256 flashloanAmount, tuple(address profitAsset,uint256 minNetProfit,uint256 nonce,bytes32 merkleRoot,bytes32[] proof,tuple(address venue,address tokenIn,address tokenOut,uint256 amountIn,uint256 minAmountOut,uint256 callValue,bytes payload)[] steps) context) external',
];

const LIQUIDATION_EXECUTOR_ABI = [
  'function executeLiquidation((address collateralAsset,address debtAsset,address user,uint256 debtToCover,uint256 minProfitBps,uint8 swapProtocol,uint24 swapFee,uint256 minDebtAmountOut,address curvePool,uint256 maxSlippageBps) liquidation) external',
];

const POLYGON_CHAIN_ID = 137n;
const DEFAULT_CONFIRM_TIMEOUT_MS = 90_000;
const DEFAULT_CONFIRMATIONS = 1;

function normalizePrivateKey(privateKey) {
  if (!privateKey) return '';
  const trimmed = String(privateKey).trim();
  if (/^0x[a-fA-F0-9]{64}$/.test(trimmed)) return trimmed;
  if (/^[a-fA-F0-9]{64}$/.test(trimmed)) return `0x${trimmed}`;
  return '';
}

function isAddress(value) {
  return typeof value === 'string' && ethers.isAddress(value);
}

function toBigNumberish(value, label) {
  if (typeof value === 'bigint') return value;
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) return BigInt(Math.floor(value));
  if (typeof value === 'string' && value.trim()) return BigInt(value);
  throw new Error(`${label} is required and must be a non-negative integer value.`);
}

function normalizeContext(context) {
  if (!context || typeof context !== 'object') {
    throw new Error('VM context is required.');
  }
  const steps = Array.isArray(context.steps) ? context.steps : [];
  if (steps.length === 0) {
    throw new Error('VM context.steps must be a non-empty array.');
  }
  return {
    profitAsset: context.profitAsset,
    minNetProfit: toBigNumberish(context.minNetProfit ?? 0, 'context.minNetProfit'),
    nonce: toBigNumberish(context.nonce ?? 0, 'context.nonce'),
    merkleRoot: context.merkleRoot || ethers.ZeroHash,
    proof: Array.isArray(context.proof) ? context.proof : [],
    steps: steps.map((step, index) => ({
      venue: step.venue,
      tokenIn: step.tokenIn,
      tokenOut: step.tokenOut,
      amountIn: toBigNumberish(step.amountIn ?? 0, `context.steps[${index}].amountIn`),
      minAmountOut: toBigNumberish(step.minAmountOut ?? 0, `context.steps[${index}].minAmountOut`),
      callValue: toBigNumberish(step.callValue ?? 0, `context.steps[${index}].callValue`),
      payload: step.payload || '0x',
    })),
  };
}

function normalizeLiquidation(liquidation) {
  if (!liquidation || typeof liquidation !== 'object') {
    throw new Error('Liquidation payload is required.');
  }
  return {
    collateralAsset: liquidation.collateralAsset,
    debtAsset: liquidation.debtAsset,
    user: liquidation.user,
    debtToCover: toBigNumberish(liquidation.debtToCover, 'liquidation.debtToCover'),
    minProfitBps: toBigNumberish(liquidation.minProfitBps ?? 0, 'liquidation.minProfitBps'),
    swapProtocol: Number(liquidation.swapProtocol ?? 1),
    swapFee: Number(liquidation.swapFee ?? 500),
    minDebtAmountOut: toBigNumberish(liquidation.minDebtAmountOut, 'liquidation.minDebtAmountOut'),
    curvePool: liquidation.curvePool || ethers.ZeroAddress,
    maxSlippageBps: toBigNumberish(liquidation.maxSlippageBps ?? 50, 'liquidation.maxSlippageBps'),
  };
}

function assertAddress(value, label) {
  if (!isAddress(value)) throw new Error(`${label} must be a valid address.`);
  return ethers.getAddress(value);
}

function maskRpcUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname ? '/...' : ''}`;
  } catch {
    return url ? 'configured' : 'missing';
  }
}

export class DeFiExecutorManager {
  constructor(rpcUrl, privateKey, enableLive = false) {
    this.rpcUrl = rpcUrl;
    this.privateKey = normalizePrivateKey(privateKey);
    this.enableLive = Boolean(enableLive);
    this.dryRun = true;
    this.provider = null;
    this.wallet = null;
    this.vmInterface = new ethers.Interface(APEX_VM_EXECUTION_ABI);
    this.liquidationInterface = new ethers.Interface(LIQUIDATION_EXECUTOR_ABI);
  }

  setDryRun(value) {
    this.dryRun = Boolean(value);
    return this.dryRun;
  }

  isDryRun() {
    return this.dryRun === true;
  }

  setRpcUrl(url) {
    this.rpcUrl = url;
    this.provider = null;
    this.wallet = null;
    return url;
  }

  hasSigner() {
    return Boolean(this.privateKey);
  }

  isArmed() {
    return this.enableLive && this.hasSigner() && !this.dryRun;
  }

  _getProvider() {
    if (!this.rpcUrl || !/^https?:\/\//i.test(this.rpcUrl)) {
      throw new Error('EXECUTOR_RPC_UNAVAILABLE: a valid HTTP RPC URL is required.');
    }
    if (!this.provider) {
      this.provider = new ethers.JsonRpcProvider(this.rpcUrl, Number(POLYGON_CHAIN_ID), { staticNetwork: true });
    }
    return this.provider;
  }

  _getWallet() {
    if (!this.privateKey) {
      throw new Error('EXECUTOR_SIGNER_MISSING: EXECUTOR_PRIVATE_KEY or BOT_PRIVATE_KEY is required for live broadcast.');
    }
    if (!this.wallet) {
      this.wallet = new ethers.Wallet(this.privateKey, this._getProvider());
    }
    return this.wallet;
  }

  getWalletAddress() {
    if (!this.privateKey) return ethers.ZeroAddress;
    try {
      return new ethers.Wallet(this.privateKey).address;
    } catch {
      return ethers.ZeroAddress;
    }
  }

  async initialize() {
    return this.getHealth();
  }

  async getHealth() {
    let chainId = null;
    let signerAddress = this.getWalletAddress();
    try {
      const network = await this._getProvider().getNetwork();
      chainId = Number(network.chainId);
    } catch {
      chainId = null;
    }
    return {
      ok: chainId === Number(POLYGON_CHAIN_ID),
      enabled: this.enableLive,
      rpcUrl: maskRpcUrl(this.rpcUrl),
      dryRun: this.dryRun,
      signerLoaded: this.hasSigner(),
      signerAddress,
      chainId,
      armed: this.isArmed(),
    };
  }

  async getStatus() {
    return this.getHealth();
  }

  _buildDryRunEnvelope(kind, payload) {
    return {
      ok: true,
      success: true,
      error: null,
      kind,
      payload,
      simulated: true,
      dryRun: true,
      hash: null,
      hashLink: null,
      rpcUrl: maskRpcUrl(this.rpcUrl),
      wallet: this.getWalletAddress(),
      timestamp: new Date().toISOString(),
      message: `${kind} payload validated in dry-run mode; no signature or chain submission occurred.`,
      settlement: {
        required: false,
        status: 'NOT_SUBMITTED',
      },
    };
  }

  async _assertLiveReady() {
    if (!this.enableLive) throw new Error('LIVE_EXECUTION_DISABLED: server was not initialized for live execution.');
    if (this.dryRun) throw new Error('LIVE_EXECUTION_BLOCKED: executor is in dry-run mode.');
    const provider = this._getProvider();
    const wallet = this._getWallet();
    const network = await provider.getNetwork();
    if (network.chainId !== POLYGON_CHAIN_ID) {
      throw new Error(`CHAIN_ID_MISMATCH: expected 137, got ${network.chainId.toString()}.`);
    }
    return { provider, wallet };
  }

  async _sendContractCall({ kind, targetContract, data, value = 0n, payload }) {
    const normalizedTarget = assertAddress(targetContract, `${kind} targetContract`);

    if (this.dryRun || !this.enableLive) {
      return this._buildDryRunEnvelope(kind, { targetContract: normalizedTarget, ...payload });
    }

    const { provider, wallet } = await this._assertLiveReady();
    const feeData = await provider.getFeeData();
    const nonce = await provider.getTransactionCount(wallet.address, 'pending');
    const request = {
      to: normalizedTarget,
      data,
      value,
      nonce,
      chainId: Number(POLYGON_CHAIN_ID),
      type: 2,
      maxFeePerGas: feeData.maxFeePerGas ?? undefined,
      maxPriorityFeePerGas: feeData.maxPriorityFeePerGas ?? undefined,
    };

    let estimatedGas;
    try {
      estimatedGas = await provider.estimateGas({ ...request, from: wallet.address });
    } catch (error) {
      throw new Error(`PRE_FLIGHT_ESTIMATE_REVERTED: ${error?.shortMessage || error?.message || String(error)}`);
    }
    request.gasLimit = estimatedGas + (estimatedGas / 5n);

    try {
      await provider.call({ ...request, from: wallet.address });
    } catch (error) {
      throw new Error(`PRE_FLIGHT_ETH_CALL_REVERTED: ${error?.shortMessage || error?.message || String(error)}`);
    }

    const response = await wallet.sendTransaction(request);
    return {
      ok: true,
      success: true,
      error: null,
      kind,
      payload: { targetContract: normalizedTarget, ...payload },
      simulated: false,
      dryRun: false,
      hash: response.hash,
      hashLink: `https://polygonscan.com/tx/${response.hash}`,
      nonce: response.nonce,
      gasLimit: request.gasLimit.toString(),
      maxFeePerGas: request.maxFeePerGas?.toString() || null,
      maxPriorityFeePerGas: request.maxPriorityFeePerGas?.toString() || null,
      rpcUrl: maskRpcUrl(this.rpcUrl),
      wallet: wallet.address,
      timestamp: new Date().toISOString(),
      message: `${kind} transaction submitted to Polygon; P&L remains locked until receipt verification.`,
      settlement: {
        required: true,
        status: 'PENDING_RECEIPT_VERIFICATION',
        verifyEndpoint: '/api/execution/verify-hash',
      },
    };
  }

  async executeOpportunity(route = null) {
    if (!route?.targetContract || !route?.data) {
      return this._buildDryRunEnvelope('EXECUTE_OPPORTUNITY', {
        routeId: route?.id || 'unknown',
        stage: route?.stage || 'PREPARED',
        netProfitUSD: route?.netProfitUSD || 0,
        reason: 'GENERIC_ROUTE_BROADCAST_REQUIRES_EXPLICIT_TARGET_AND_CALLDATA',
      });
    }
    return this._sendContractCall({
      kind: 'EXECUTE_OPPORTUNITY',
      targetContract: route.targetContract,
      data: route.data,
      value: toBigNumberish(route.value ?? 0, 'route.value'),
      payload: { routeId: route.id || 'unknown' },
    });
  }

  async broadcastFlashloanIntegratedC1Payload(targetContract, flashloanSource, flashloanAsset, flashloanAmount, context) {
    const normalizedFlashloanAsset = assertAddress(flashloanAsset, 'C1 flashloanAsset');
    const normalizedContext = normalizeContext(context);
    assertAddress(normalizedContext.profitAsset, 'C1 context.profitAsset');
    normalizedContext.steps.forEach((step, index) => {
      assertAddress(step.venue, `C1 context.steps[${index}].venue`);
      assertAddress(step.tokenIn, `C1 context.steps[${index}].tokenIn`);
      assertAddress(step.tokenOut, `C1 context.steps[${index}].tokenOut`);
    });
    const amount = toBigNumberish(flashloanAmount, 'C1 flashloanAmount');
    const source = Number(flashloanSource);
    const data = this.vmInterface.encodeFunctionData('executeC1', [source, normalizedFlashloanAsset, amount, normalizedContext]);
    return this._sendContractCall({
      kind: 'C1',
      targetContract,
      data,
      payload: { flashloanSource: source, flashloanAsset: normalizedFlashloanAsset, flashloanAmount: amount.toString(), context: normalizedContext },
    });
  }

  async broadcastFlashloanIntegratedC2Payload(targetContract, c1InternalId, flashloanSource, flashloanAsset, flashloanAmount, context) {
    if (!ethers.isHexString(c1InternalId, 32)) {
      throw new Error('C2 c1InternalId must be bytes32.');
    }
    const normalizedFlashloanAsset = assertAddress(flashloanAsset, 'C2 flashloanAsset');
    const normalizedContext = normalizeContext(context);
    assertAddress(normalizedContext.profitAsset, 'C2 context.profitAsset');
    normalizedContext.steps.forEach((step, index) => {
      assertAddress(step.venue, `C2 context.steps[${index}].venue`);
      assertAddress(step.tokenIn, `C2 context.steps[${index}].tokenIn`);
      assertAddress(step.tokenOut, `C2 context.steps[${index}].tokenOut`);
    });
    const amount = toBigNumberish(flashloanAmount, 'C2 flashloanAmount');
    const source = Number(flashloanSource);
    const data = this.vmInterface.encodeFunctionData('executeC2', [c1InternalId, source, normalizedFlashloanAsset, amount, normalizedContext]);
    return this._sendContractCall({
      kind: 'C2',
      targetContract,
      data,
      payload: { c1InternalId, flashloanSource: source, flashloanAsset: normalizedFlashloanAsset, flashloanAmount: amount.toString(), context: normalizedContext },
    });
  }

  async broadcastFlashloanIntegratedLiquidation(targetContract, liquidation) {
    const normalizedLiquidation = normalizeLiquidation(liquidation);
    assertAddress(normalizedLiquidation.collateralAsset, 'liquidation.collateralAsset');
    assertAddress(normalizedLiquidation.debtAsset, 'liquidation.debtAsset');
    assertAddress(normalizedLiquidation.user, 'liquidation.user');
    assertAddress(normalizedLiquidation.curvePool, 'liquidation.curvePool');
    const data = this.liquidationInterface.encodeFunctionData('executeLiquidation', [normalizedLiquidation]);
    return this._sendContractCall({
      kind: 'LIQUIDATION',
      targetContract,
      data,
      payload: { liquidation: normalizedLiquidation },
    });
  }
}