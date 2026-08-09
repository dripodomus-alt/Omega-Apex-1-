import { ethers } from 'ethers';
import { buildPayloadForRoute } from './payloadBuilder';
import type { ArbitrageRoute } from '../types';

/** Canonical ABI definitions for the generic route executor payload builder. */
export const OMEGA_EXECUTOR_ABI = [
  'function executeArbitrage(address[] calldata path, uint256 inputAmount, uint256 minProfitUSD, bytes calldata flashloanData) external returns (uint256 netProfit)',
  'function executeFlashLoanArbitrage(address tokenIn, uint256 amountIn, address[] calldata routePools, bytes calldata callData) external returns (uint256 profit)',
  'function executeAaveLiquidation(address userToLiquidate, address collateralAsset, address debtAsset, uint256 debtToCover, bool receiveAToken) external returns (uint256 profitUSD)',
  'function owner() view returns (address)',
  'function executeMultiHopSwap(tuple(address target, bytes callData, uint256 value)[] calls)',
  'function profitReceiver() view returns (address)',
  'function isAuthorizedRelayer(address relayer) view returns (bool)',
  'function getNonce(address user) view returns (uint256)',
  'event ArbitrageExecuted(bytes32 indexed routeHash, uint256 inputAmount, uint256 netProfitUSD, uint256 gasPaidGwei)',
  'event LiquidationExecuted(address indexed borrower, address indexed collateralAsset, uint256 profitUSD)',
];

export interface LiveEthersTxBroadcastResult {
  success: boolean;
  txHash: string;
  blockNumber?: number;
  gasUsedGwei?: number;
  effectiveGasPriceGwei?: number;
  nonce?: number;
  rpcNodeUsed: string;
  relayProtocol: string;
  preFlightSimulationPassed: boolean;
  revertReason?: string;
  polygonscanUrl: string;
  confirmationLogs: string[];
  settlement?: {
    required: boolean;
    status: string;
    verifyEndpoint?: string;
  };
}

export interface BroadcastTransactionPayload {
  /** The full arbitrage route, which is the source of truth for simulation and broadcast. */
  route?: ArbitrageRoute;
  /** Legacy UI fields are typed for compatibility only; live execution still requires route. */
  routeId?: string;
  pathAddresses?: string[];
  inputAmountUSD?: number;
  expectedProfitUSD?: number;
  relayProtocol?: 'FASTLANE' | 'FLASHBOTS' | 'BUILDER_0X69' | 'EDEN' | 'PUBLIC_RPC';
  customMaxFeeGwei?: number;
}

function failureResult(payload: BroadcastTransactionPayload, reason: string, logs: string[] = []): LiveEthersTxBroadcastResult {
  return {
    success: false,
    txHash: ethers.ZeroHash,
    rpcNodeUsed: 'server-side-execution-bridge',
    relayProtocol: payload.relayProtocol || 'FASTLANE',
    preFlightSimulationPassed: false,
    revertReason: reason,
    polygonscanUrl: 'https://polygonscan.com/',
    confirmationLogs: logs.length ? logs : [`[BROADCAST BLOCKED] ${reason}`],
    settlement: { required: false, status: 'NOT_SUBMITTED' },
  };
}

function apiBase(): string {
  const configured = import.meta.env.VITE_APEX_API_BASE as string | undefined;
  return (configured?.trim() || '').replace(/\/+$/, '');
}

async function readJson(response: Response): Promise<any> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

/**
 * Pre-flight simulation for a route through the server-side execution bridge.
 *
 * The browser may build calldata for transparency, but private-key signing is
 * intentionally never performed in the client bundle.
 */
export async function simulateArbitrageOnChain(
  route: ArbitrageRoute,
): Promise<{ success: boolean; simulationData: string; estimatedGasUnits: bigint; errorReason?: string }> {
  try {
    const builtPayload = await buildPayloadForRoute(route);
    const response = await fetch(`${apiBase()}/api/execution/route-broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        dryRunOnly: true,
        routeId: route.id,
        expectedProfitUSD: route.netProfitUSD,
        targetContract: builtPayload.to,
        data: builtPayload.data,
        value: builtPayload.value.toString(),
      }),
    });
    const data = await readJson(response);
    if (!response.ok || data?.success === false) {
      throw new Error(data?.error || data?.message || `Simulation bridge failed: ${response.status}`);
    }
    return {
      success: true,
      simulationData: data?.hash || '0x',
      estimatedGasUnits: data?.gasLimit ? BigInt(data.gasLimit) : 0n,
    };
  } catch (error) {
    return {
      success: false,
      simulationData: '0x',
      estimatedGasUnits: 0n,
      errorReason: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Execute and broadcast via the server-side signer.
 *
 * This function is client-safe: it does not read private keys or instantiate a
 * signing wallet in the browser. The server owns live-mode gating, pre-flight
 * simulation, signing, transaction submission, and pending settlement tracking.
 */
export async function broadcastEthersOnChainTransaction(
  payload: BroadcastTransactionPayload,
): Promise<LiveEthersTxBroadcastResult> {
  const route = payload.route;
  if (!route) {
    return failureResult(payload, 'Canonical ArbitrageRoute is required. Legacy path-only payloads are simulation-only and cannot be broadcast.');
  }

  const confirmationLogs = [
    '[CLIENT BRIDGE] Building executable calldata from canonical route.',
    '[CLIENT BRIDGE] Private key handling delegated to server-side execution bridge.',
  ];

  try {
    const builtPayload = await buildPayloadForRoute(route);
    confirmationLogs.push(`[PAYLOAD] ${builtPayload.description}`);

    const response = await fetch(`${apiBase()}/api/execution/route-broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        routeId: route.id,
        pathString: route.pathString,
        expectedProfitUSD: payload.expectedProfitUSD ?? route.netProfitUSD,
        relayProtocol: payload.relayProtocol || 'FASTLANE',
        customMaxFeeGwei: payload.customMaxFeeGwei,
        targetContract: builtPayload.to,
        data: builtPayload.data,
        value: builtPayload.value.toString(),
      }),
    });
    const data = await readJson(response);
    if (!response.ok || data?.success === false) {
      const reason = data?.error || data?.message || `Execution bridge rejected payload: HTTP ${response.status}`;
      return failureResult(payload, reason, [...confirmationLogs, `[SERVER REJECTED] ${reason}`]);
    }

    const txHash = data.hash || data.txHash || ethers.ZeroHash;
    return {
      success: Boolean(data.success),
      txHash,
      blockNumber: data.blockNumber,
      nonce: data.nonce,
      rpcNodeUsed: data.rpcUrl || data.rpcNodeUsed || 'server-side-execution-bridge',
      relayProtocol: data.relayProtocol || payload.relayProtocol || 'FASTLANE',
      preFlightSimulationPassed: true,
      polygonscanUrl: data.hashLink || (txHash !== ethers.ZeroHash ? `https://polygonscan.com/tx/${txHash}` : 'https://polygonscan.com/'),
      confirmationLogs: [...confirmationLogs, ...(Array.isArray(data.logs) ? data.logs : []), data.message || '[SERVER ACCEPTED] Payload processed.'].filter(Boolean),
      settlement: data.settlement,
    };
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return failureResult(payload, reason, [...confirmationLogs, `[CLIENT BRIDGE ERROR] ${reason}`]);
  }
}

/** Liquidation broadcast requires a complete server-side liquidation payload. */
export async function broadcastAaveLiquidationViaEthers(
  borrowerAddress: string,
  collateralAsset: string,
  debtAsset: string,
  debtToCoverUSD: number,
): Promise<LiveEthersTxBroadcastResult> {
  return failureResult(
    { routeId: 'AAVE-LIQUIDATION', relayProtocol: 'FASTLANE' },
    `Use /api/liquidations/execute with raw debtToCover and minDebtAmountOut. Received summary request for ${borrowerAddress}/${collateralAsset}/${debtAsset}/$${debtToCoverUSD}.`,
  );
}