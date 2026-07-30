import React from "react";
import { ChevronRight, ShieldCheck, Target, Zap } from "lucide-react";

const payloadStructures = [
  {
    canonicalName: "FLASHLOAN INTEGRATED C1 PAYLOADS",
    purpose: "Borrow flashloan capital and execute the opening C1 route against pre-state pricing.",
    useCase: "Entry payload for a C1 arbitrage cycle where capital is borrowed, routed, and committed for C2 settlement.",
    requiredFields: [
      "payloadKind",
      "chainId",
      "executor",
      "flashloanProvider",
      "flashloanAsset",
      "flashloanAmount",
      "entryLegs",
      "c1StateCommitment",
      "minC1Output",
      "deadline",
    ],
    sample: {
      payloadKind: "FLASHLOAN_INTEGRATED_C1_PAYLOADS",
      canonicalName: "FLASHLOAN INTEGRATED C1 PAYLOADS",
      chainId: 137,
      executor: "0xC1Executor...",
      flashloanProvider: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
      flashloanAsset: "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
      flashloanAmount: "1000000000",
      entryLegs: [
        {
          dex: "UniswapV3",
          router: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
          tokenIn: "USDC.e",
          tokenOut: "WETH",
          amountIn: "1000000000",
          minAmountOut: "284690000000000000",
          path: "USDC.e/WETH/500",
        },
      ],
      c1StateCommitment: "0x<pre_state_hash>",
      minC1Output: "284690000000000000",
      deadline: 0,
    },
  },
  {
    canonicalName: "FLASHLOAN INTEGRATED C2 PAYLOADS",
    purpose: "Consume landed C1 state, close the route, repay flashloan principal plus fee, and settle surplus.",
    useCase: "Reactive C2 payload generated only after C1 state is known and repayment math is bounded.",
    requiredFields: [
      "payloadKind",
      "chainId",
      "executor",
      "flashloanProvider",
      "repayAsset",
      "repayAmount",
      "c1StateCommitment",
      "observedC1TxHash",
      "exitLegs",
      "minSurplus",
      "receiver",
      "deadline",
    ],
    sample: {
      payloadKind: "FLASHLOAN_INTEGRATED_C2_PAYLOADS",
      canonicalName: "FLASHLOAN INTEGRATED C2 PAYLOADS",
      chainId: 137,
      executor: "0xC2Executor...",
      flashloanProvider: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
      repayAsset: "USDC.e",
      repayAmount: "1000500000",
      c1StateCommitment: "0x<pre_state_hash>",
      observedC1TxHash: "0x<c1_tx_hash>",
      exitLegs: [
        {
          dex: "QuickSwapV2",
          router: "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
          tokenIn: "WETH",
          tokenOut: "USDC.e",
          amountIn: "284690000000000000",
          minAmountOut: "1010000000",
          path: "WETH/USDC.e",
        },
      ],
      minSurplus: "9500000",
      receiver: "0xProfitReceiver...",
      deadline: 0,
    },
  },
  {
    canonicalName: "FLASHLOAN INTEGRATED LIQUIDATIONS",
    purpose: "Borrow Balancer flashloan capital to repay unhealthy Aave V3 debt, seize collateral, unwind, repay the flashloan, and retain liquidation bonus.",
    useCase: "Balancer flashloan integrated liquidation gated by Aave V3 health factor, close factor, collateral value, swap output, flashloan repayment, gas, and min surplus.",
    requiredFields: [
      "payloadKind",
      "chainId",
      "executor",
      "lendingPool",
      "userToLiquidate",
      "debtAsset",
      "collateralAsset",
      "debtToCover",
      "flashloanProvider",
      "flashloanAsset",
      "flashloanAmount",
      "minCollateralOut",
      "minSurplus",
      "receiver",
      "deadline",
    ],
    sample: {
      payloadKind: "FLASHLOAN_INTEGRATED_LIQUIDATIONS",
      canonicalName: "FLASHLOAN INTEGRATED LIQUIDATIONS",
      chainId: 137,
      executor: "0xLiquidationExecutor...",
      lendingPool: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
      userToLiquidate: "0xBorrower...",
      debtAsset: "USDC.e",
      collateralAsset: "WETH",
      debtToCover: "1000000000",
      flashloanProvider: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
      flashloanAsset: "USDC.e",
      flashloanAmount: "1000000000",
      minCollateralOut: "285000000000000000",
      minSurplus: "15000000",
      receiver: "0xProfitReceiver...",
      deadline: 0,
    },
  },
];

export default function MainnetPayloadSchema() {
  return (
    <div className="border border-[#1e2025] bg-[#0d0e12] rounded-md p-4 font-mono text-[10px] text-gray-300 max-h-64 overflow-y-auto scrollbar-thin glass-specular glass-inset">
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-[#1e2025]">
        <h3 className="text-cyan-400 font-bold uppercase flex items-center gap-2">
          <Target className="w-4 h-4 text-emerald-400" />
          Canonical Payload Structures
        </h3>
        <span className="text-[9px] bg-emerald-900/30 text-emerald-300 px-2 py-0.5 rounded-sm uppercase tracking-widest border border-emerald-500/20">
          3 Registered
        </span>
      </div>

      <div className="mb-4 p-3 bg-[#0a0b0e] border border-[#1e2025] rounded-sm overflow-x-auto">
        <div className="flex items-center gap-3 whitespace-nowrap text-[10px]">
          <span className="px-3 py-1.5 bg-cyan-900/30 border border-cyan-700/50 rounded-sm text-cyan-300">
            FLASHLOAN INTEGRATED C1 PAYLOADS
          </span>
          <ChevronRight className="w-3 h-3 text-gray-600 shrink-0" />
          <span className="px-3 py-1.5 bg-purple-900/30 border border-purple-700/50 rounded-sm text-purple-300">
            FLASHLOAN INTEGRATED C2 PAYLOADS
          </span>
          <ChevronRight className="w-3 h-3 text-gray-600 shrink-0" />
          <span className="px-3 py-1.5 bg-red-900/30 border border-red-700/50 rounded-sm text-red-300">
            FLASHLOAN INTEGRATED LIQUIDATIONS
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {payloadStructures.map((structure) => (
          <section key={structure.canonicalName} className="border border-[#1e2025] bg-black/30 rounded-sm p-3">
            <div className="flex items-center gap-2 mb-2">
              {structure.canonicalName === "FLASHLOAN INTEGRATED LIQUIDATIONS" ? (
                <ShieldCheck className="w-3.5 h-3.5 text-red-300" />
              ) : (
                <Zap className="w-3.5 h-3.5 text-cyan-300" />
              )}
              <h4 className="text-white uppercase font-bold tracking-wider">{structure.canonicalName}</h4>
            </div>
            <p className="text-gray-400 leading-relaxed mb-2">{structure.purpose}</p>
            <p className="text-gray-500 leading-relaxed mb-3">{structure.useCase}</p>
            <div className="text-gray-500 uppercase tracking-wider mb-1">Required Fields</div>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {structure.requiredFields.map((field) => (
                <span key={field} className="px-1.5 py-0.5 border border-[#1e2025] bg-[#07080a] text-gray-300 rounded-sm">
                  {field}
                </span>
              ))}
            </div>
            <pre className="bg-black/50 p-3 rounded-sm overflow-auto border border-[#1e2025] max-h-36 scrollbar-thin">
              <code className="text-[10px] leading-relaxed text-indigo-300">
                {JSON.stringify(structure.sample, null, 2)}
              </code>
            </pre>
          </section>
        ))}
      </div>
    </div>
  );
}