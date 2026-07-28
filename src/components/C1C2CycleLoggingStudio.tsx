import React, { useState, useEffect } from 'react';
import {
  Layers,
  Zap,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Database,
  Terminal,
  ShieldCheck,
  RefreshCw,
  Play,
  Pause,
  ArrowRight,
  TrendingUp,
  Cpu,
  Lock,
  ExternalLink,
  Copy,
  Check,
  Sliders,
} from 'lucide-react';
import { POLYGON_CHAIN_CONFIG } from '../config/chainConfig';

export interface OpportunityRecord {
  opportunity_id: string;
  chain_id: number;
  discovered_block: number;
  discovered_block_hash: string;
  detected_at_ms: number;
  config_version: number;
  config_hash: string;
  borrow_asset: string;
  borrow_symbol: string;
  buy_venue: string;
  buy_pool: string;
  sell_venue: string;
  sell_pool: string;
  buy_family: string;
  sell_family: string;
  buy_leg_price: number;
  sell_leg_price: number;
  raw_spread_usd: number;
  raw_spread_bps: number;
  state_hash: string;
  route_hash: string;
  opportunity_status: 'DISCOVERED' | 'C1_PENDING' | 'C1_SETTLED' | 'C2_PENDING' | 'CLOSED_PROFITABLE' | 'CLOSED_C1_FAILED' | 'CLOSED_C1_ONLY_PROFITABLE' | 'STALE_EXPIRED';
  c1_cycle_id: string | null;
  c2_cycle_id: string | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface C1CycleRecord {
  c1_cycle_id: string;
  opportunity_id: string;
  cycle_type: 'C1';
  cycle_index: number;
  chain_id: number;
  discovery_block: number;
  execution_anchor_block: number;
  expires_at_block: number;
  borrow_asset: string;
  borrow_amount_raw: string;
  borrow_amount_usd: number;
  route_hash: string;
  state_hash: string;
  config_hash: string;
  expected_gross_usd: number;
  expected_net_usd: number;
  min_net_usd: number;
  gas_estimate_usd: number;
  flash_fee_usd: number;
  risk_buffer_usd: number;
  mev_buffer_usd: number;
  simulation_status: 'PASSED' | 'FAILED' | 'SKIPPED';
  payload_status: 'BUILT' | 'FAILED';
  submission_status: 'SUBMITTED_PRIVATE' | 'SUBMITTED_PUBLIC' | 'CONFIRMED' | 'REVERTED' | 'EXPIRED';
  settlement_status: 'SETTLED' | 'FAILED' | 'PENDING';
  tx_hash: string | null;
  submitted_block: number | null;
  confirmed_block: number | null;
  realized_gross_usd: number | null;
  realized_net_usd: number | null;
  realized_gas_usd: number | null;
  realized_profit_raw: string | null;
  reject_reason: string | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface C2CycleRecord {
  c2_cycle_id: string;
  opportunity_id: string;
  parent_c1_cycle_id: string;
  cycle_type: 'C2';
  cycle_index: number;
  c1_tx_hash: string;
  c1_confirmed_block: number;
  c2_window_start_block: number;
  c2_window_end_block: number;
  c2_eval_block: number;
  post_c1_state_hash: string;
  pre_c2_route_hash: string | null;
  c2_route_hash: string | null;
  c2_decision: 'MIRROR' | 'REVERSE' | 'DO_NOTHING' | 'EXPIRED' | 'CANCELLED';
  mirror_expected_net_usd: number;
  reverse_expected_net_usd: number;
  selected_expected_net_usd: number;
  borrow_asset: string | null;
  borrow_amount_raw: string | null;
  borrow_amount_usd: number | null;
  gas_estimate_usd: number | null;
  flash_fee_usd: number | null;
  risk_buffer_usd: number | null;
  mev_buffer_usd: number | null;
  simulation_status: 'PASSED' | 'FAILED' | 'SKIPPED_NO_PROFITABLE_BRANCH' | 'NOT_STARTED';
  payload_status: 'BUILT' | 'NOT_BUILT';
  submission_status: 'SUBMITTED_PRIVATE' | 'NOT_SUBMITTED' | 'CONFIRMED' | 'CANCELLED' | 'EXPIRED';
  settlement_status: 'SETTLED' | 'NOOP' | 'EXPIRED' | 'CANCELLED' | 'PENDING';
  tx_hash: string | null;
  submitted_block: number | null;
  confirmed_block: number | null;
  realized_gross_usd: number | null;
  realized_net_usd: number | null;
  realized_gas_usd: number | null;
  realized_profit_raw: string | null;
  reject_reason: string | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface CycleEventRecord {
  event_id: string;
  opportunity_id: string;
  cycle_id: string;
  cycle_type: 'DISCOVERY' | 'C1' | 'C2' | 'LIQUIDATION';
  event_type: string;
  event_status: string;
  block_number: number;
  tx_hash: string | null;
  state_hash: string | null;
  route_hash: string | null;
  config_hash: string;
  message: string;
  created_at_ms: number;
}

export const C1C2CycleLoggingStudio: React.FC = () => {
  // Current Polygon Block Height
  const [currentBlock, setCurrentBlock] = useState<number>(90213722);
  const [autoEngineActive, setAutoEngineActive] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'TIMELINE' | 'OPPORTUNITIES' | 'C1_CYCLES' | 'C2_CYCLES' | 'EVENTS' | 'JSON_STATE'>('TIMELINE');
  const [selectedOppId, setSelectedOppId] = useState<string>('opp_137_90213722_a91f');
  const [copyStatus, setCopySuccess] = useState<string | null>(null);

  // Initial State Hydration based on User Specification Example
  const [opportunities, setOpportunities] = useState<OpportunityRecord[]>([
    {
      opportunity_id: 'opp_137_90213722_a91f',
      chain_id: 137,
      discovered_block: 90213722,
      discovered_block_hash: '0x3d82a17f918bc28f110c',
      detected_at_ms: Date.now() - 12000,
      config_version: 44,
      config_hash: '0xconfig44',
      borrow_asset: 'USDC',
      borrow_symbol: 'USDC',
      buy_venue: 'QuickSwapV2',
      buy_pool: '0xadbF1854e5883eB8aa7BAf50705338739e558E5b',
      sell_venue: 'UniswapV3',
      sell_pool: '0x0a6c4588b7D8Bd22cF120283B1FFf953420c45F3',
      buy_family: 'V2_CPMM',
      sell_family: 'V3_CLMM',
      buy_leg_price: 2574.12,
      sell_leg_price: 2577.89,
      raw_spread_usd: 3.77,
      raw_spread_bps: 14.645,
      state_hash: '0xstate_pre_c1',
      route_hash: '0xroute_c1',
      opportunity_status: 'CLOSED_PROFITABLE',
      c1_cycle_id: 'c1_opp_137_90213722_a91f',
      c2_cycle_id: 'c2_opp_137_90213722_a91f',
      created_at_ms: Date.now() - 12000,
      updated_at_ms: Date.now() - 2000,
    },
    {
      opportunity_id: 'opp_137_90213720_b34c',
      chain_id: 137,
      discovered_block: 90213716,
      discovered_block_hash: '0x88f2910c22fa10298a',
      detected_at_ms: Date.now() - 35000,
      config_version: 44,
      config_hash: '0xconfig44',
      borrow_asset: 'WMATIC',
      borrow_symbol: 'WMATIC',
      buy_venue: 'Sushiswap',
      buy_pool: '0xc4e595acDD7d12feC385E5dA5D43160e8A0bAC0E',
      sell_venue: 'UniswapV3',
      sell_pool: '0x33C4F0043E2e988b3c2e9C77e2C670eFe709Bfe3',
      buy_family: 'V2_CPMM',
      sell_family: 'V3_CLMM',
      buy_leg_price: 0.584,
      sell_leg_price: 0.591,
      raw_spread_usd: 12.4,
      raw_spread_bps: 11.9,
      state_hash: '0xstate_stale_91',
      route_hash: '0xroute_stale_91',
      opportunity_status: 'STALE_EXPIRED',
      c1_cycle_id: 'c1_opp_137_90213720_b34c',
      c2_cycle_id: null,
      created_at_ms: Date.now() - 35000,
      updated_at_ms: Date.now() - 28000,
    },
  ]);

  const [c1Cycles, setC1Cycles] = useState<C1CycleRecord[]>([
    {
      c1_cycle_id: 'c1_opp_137_90213722_a91f',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_type: 'C1',
      cycle_index: 1,
      chain_id: 137,
      discovery_block: 90213722,
      execution_anchor_block: 90213723,
      expires_at_block: 90213726, // discovery_block + 4
      borrow_asset: 'USDC',
      borrow_amount_raw: '10000000000',
      borrow_amount_usd: 10000.0,
      route_hash: '0xroute_c1',
      state_hash: '0xstate_pre_c1',
      config_hash: '0xconfig44',
      expected_gross_usd: 18.92,
      expected_net_usd: 8.57,
      min_net_usd: 5.0,
      gas_estimate_usd: 2.85,
      flash_fee_usd: 5.0,
      risk_buffer_usd: 1.5,
      mev_buffer_usd: 1.0,
      simulation_status: 'PASSED',
      payload_status: 'BUILT',
      submission_status: 'CONFIRMED',
      settlement_status: 'SETTLED',
      tx_hash: '0x8f2a1738c119280a982f1b402e8d901a88c3f592d11019e01',
      submitted_block: 90213723,
      confirmed_block: 90213723,
      realized_gross_usd: 17.41,
      realized_net_usd: 7.99,
      realized_gas_usd: 2.92,
      realized_profit_raw: '7990000',
      reject_reason: null,
      created_at_ms: Date.now() - 11000,
      updated_at_ms: Date.now() - 9000,
    },
    {
      c1_cycle_id: 'c1_opp_137_90213720_b34c',
      opportunity_id: 'opp_137_90213720_b34c',
      cycle_type: 'C1',
      cycle_index: 1,
      chain_id: 137,
      discovery_block: 90213716,
      execution_anchor_block: 90213717,
      expires_at_block: 90213720, // discovery + 4 = stale
      borrow_asset: 'WMATIC',
      borrow_amount_raw: '25000000000000000000000',
      borrow_amount_usd: 14750.0,
      route_hash: '0xroute_stale_91',
      state_hash: '0xstate_stale_91',
      config_hash: '0xconfig44',
      expected_gross_usd: 14.1,
      expected_net_usd: 6.2,
      min_net_usd: 4.0,
      gas_estimate_usd: 2.9,
      flash_fee_usd: 3.5,
      risk_buffer_usd: 1.0,
      mev_buffer_usd: 0.5,
      simulation_status: 'PASSED',
      payload_status: 'BUILT',
      submission_status: 'EXPIRED',
      settlement_status: 'FAILED',
      tx_hash: null,
      submitted_block: null,
      confirmed_block: null,
      realized_gross_usd: null,
      realized_net_usd: null,
      realized_gas_usd: null,
      realized_profit_raw: null,
      reject_reason: 'OPPORTUNITY_STALE_EXPIRED_AFTER_4_BLOCKS',
      created_at_ms: Date.now() - 34000,
      updated_at_ms: Date.now() - 28000,
    },
  ]);

  const [c2Cycles, setC2Cycles] = useState<C2CycleRecord[]>([
    {
      c2_cycle_id: 'c2_opp_137_90213722_a91f',
      opportunity_id: 'opp_137_90213722_a91f',
      parent_c1_cycle_id: 'c1_opp_137_90213722_a91f',
      cycle_type: 'C2',
      cycle_index: 2,
      c1_tx_hash: '0x8f2a1738c119280a982f1b402e8d901a88c3f592d11019e01',
      c1_confirmed_block: 90213723,
      c2_window_start_block: 90213724,
      c2_window_end_block: 90213728, // 4 blocks window
      c2_eval_block: 90213724,
      post_c1_state_hash: '0xstate_post_c1',
      pre_c2_route_hash: '0xroute_c1',
      c2_route_hash: '0xroute_c2_reverse',
      c2_decision: 'REVERSE',
      mirror_expected_net_usd: -1.42,
      reverse_expected_net_usd: 6.36,
      selected_expected_net_usd: 6.36,
      borrow_asset: 'USDC',
      borrow_amount_raw: '7000000000',
      borrow_amount_usd: 7000.0,
      gas_estimate_usd: 2.61,
      flash_fee_usd: 3.5,
      risk_buffer_usd: 1.5,
      mev_buffer_usd: 1.0,
      simulation_status: 'PASSED',
      payload_status: 'BUILT',
      submission_status: 'CONFIRMED',
      settlement_status: 'SETTLED',
      tx_hash: '0x71ba910c28371900a8412ef1099281a8c91',
      submitted_block: 90213724,
      confirmed_block: 90213724,
      realized_gross_usd: 12.92,
      realized_net_usd: 5.68,
      realized_gas_usd: 2.74,
      realized_profit_raw: '5680000',
      reject_reason: null,
      created_at_ms: Date.now() - 8000,
      updated_at_ms: Date.now() - 2000,
    },
  ]);

  const [cycleEvents, setCycleEvents] = useState<CycleEventRecord[]>([
    {
      event_id: 'evt_001',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'opp_137_90213722_a91f',
      cycle_type: 'DISCOVERY',
      event_type: 'DISCOVERED',
      event_status: 'SUCCESS',
      block_number: 90213722,
      tx_hash: null,
      state_hash: '0xstate_pre_c1',
      route_hash: '0xroute_c1',
      config_hash: '0xconfig44',
      message: 'Bellman-Ford positive cycle identified across QuickSwap V2 & Uniswap V3',
      created_at_ms: Date.now() - 12000,
    },
    {
      event_id: 'evt_002',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c1_opp_137_90213722_a91f',
      cycle_type: 'C1',
      event_type: 'PRICE_EDGE_VALIDATED',
      event_status: 'SUCCESS',
      block_number: 90213722,
      tx_hash: null,
      state_hash: '0xstate_pre_c1',
      route_hash: '0xroute_c1',
      config_hash: '0xconfig44',
      message: 'Spread: 14.64 bps ($3.77 raw). Optimal sizing calculus: $10,000 borrow.',
      created_at_ms: Date.now() - 11800,
    },
    {
      event_id: 'evt_003',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c1_opp_137_90213722_a91f',
      cycle_type: 'C1',
      event_type: 'SIM_PASSED',
      event_status: 'SUCCESS',
      block_number: 90213722,
      tx_hash: null,
      state_hash: '0xstate_pre_c1',
      route_hash: '0xroute_c1',
      config_hash: '0xconfig44',
      message: 'eth_call simulation passed. Gas: 184,200 units ($2.85). Expected Net: +$8.57',
      created_at_ms: Date.now() - 11000,
    },
    {
      event_id: 'evt_004',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c1_opp_137_90213722_a91f',
      cycle_type: 'C1',
      event_type: 'SUBMITTED_PRIVATE',
      event_status: 'SUCCESS',
      block_number: 90213723,
      tx_hash: '0x8f2a1738c119280a982f1b402e8d901a88c3f592d11019e01',
      state_hash: '0xstate_pre_c1',
      route_hash: '0xroute_c1',
      config_hash: '0xconfig44',
      message: 'Broadcasted signed EIP-1559 payload to FastLane Relay https://rpc.fastlane.xyz',
      created_at_ms: Date.now() - 10000,
    },
    {
      event_id: 'evt_005',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c1_opp_137_90213722_a91f',
      cycle_type: 'C1',
      event_type: 'CONFIRMED',
      event_status: 'SETTLED',
      block_number: 90213723,
      tx_hash: '0x8f2a1738c119280a982f1b402e8d901a88c3f592d11019e01',
      state_hash: '0xstate_pre_c1',
      route_hash: '0xroute_c1',
      config_hash: '0xconfig44',
      message: 'C1 Mined in Block #90213723. Realized Net Yield: +$7.99',
      created_at_ms: Date.now() - 9000,
    },
    {
      event_id: 'evt_006',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c2_opp_137_90213722_a91f',
      cycle_type: 'C2',
      event_type: 'C2_WINDOW_OPENED',
      event_status: 'ACTIVE',
      block_number: 90213724,
      tx_hash: null,
      state_hash: '0xstate_post_c1',
      route_hash: '0xroute_c1',
      config_hash: '0xconfig44',
      message: 'C1 Confirmation triggered C2 window. Valid Blocks: #90213724 to #90213728',
      created_at_ms: Date.now() - 8500,
    },
    {
      event_id: 'evt_007',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c2_opp_137_90213722_a91f',
      cycle_type: 'C2',
      event_type: 'C2_REVERSE_EVALUATED',
      event_status: 'SUCCESS',
      block_number: 90213724,
      tx_hash: null,
      state_hash: '0xstate_post_c1',
      route_hash: '0xroute_c2_reverse',
      config_hash: '0xconfig44',
      message: 'C2 Evaluation: MIRROR=-$1.42, REVERSE=+$6.36. Selected REVERSE strategy.',
      created_at_ms: Date.now() - 8000,
    },
    {
      event_id: 'evt_008',
      opportunity_id: 'opp_137_90213722_a91f',
      cycle_id: 'c2_opp_137_90213722_a91f',
      cycle_type: 'C2',
      event_type: 'CONFIRMED',
      event_status: 'SETTLED',
      block_number: 90213724,
      tx_hash: '0x71ba910c28371900a8412ef1099281a8c91',
      state_hash: '0xstate_post_c1',
      route_hash: '0xroute_c2_reverse',
      config_hash: '0xconfig44',
      message: 'C2 Mined in Block #90213724. Realized Net Yield: +$5.68. Combined Total: +$13.67',
      created_at_ms: Date.now() - 2000,
    },
  ]);

  // Block Clock & Automated Execution Engine
  useEffect(() => {
    let interval: any = null;
    if (autoEngineActive) {
      interval = setInterval(() => {
        setCurrentBlock((prevBlock) => {
          const nextBlock = prevBlock + 1;

          // Process Block Parity and Staleness Check (Rule: Stale after 4 blocks if not executed)
          setOpportunities((prevOpps) =>
            prevOpps.map((opp) => {
              if (
                opp.opportunity_status === 'C1_PENDING' ||
                opp.opportunity_status === 'DISCOVERED'
              ) {
                if (nextBlock > opp.discovered_block + 4) {
                  // Mark as Stale Expired
                  return {
                    ...opp,
                    opportunity_status: 'STALE_EXPIRED',
                    updated_at_ms: Date.now(),
                  };
                }
              }
              return opp;
            })
          );

          // Randomly trigger a NEW high-yield C1 opportunity bound to the current block every ~4-5 blocks
          if (Math.random() > 0.65) {
            const oppHash = Math.random().toString(36).substring(2, 6);
            const newOppId = `opp_137_${nextBlock}_${oppHash}`;
            const c1Id = `c1_${newOppId}`;
            const c2Id = `c2_${newOppId}`;

            const assets = ['USDC', 'WMATIC', 'WETH', 'USDT', 'DAI'];
            const chosenAsset = assets[Math.floor(Math.random() * assets.length)];
            const grossC1 = Number((18.0 + Math.random() * 25.0).toFixed(2));
            const gasC1 = Number((2.2 + Math.random() * 0.8).toFixed(2));
            const netC1 = Number((grossC1 - gasC1 - 5.0).toFixed(2));

            const newOpp: OpportunityRecord = {
              opportunity_id: newOppId,
              chain_id: 137,
              discovered_block: nextBlock,
              discovered_block_hash: `0x${Math.random().toString(16).substring(2, 12)}`,
              detected_at_ms: Date.now(),
              config_version: 44,
              config_hash: '0xconfig44',
              borrow_asset: chosenAsset,
              borrow_symbol: chosenAsset,
              buy_venue: 'QuickSwap V3',
              buy_pool: POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress,
              sell_venue: 'Uniswap V3',
              sell_pool: '0x0a6c4588b7D8Bd22cF120283B1FFf953420c45F3',
              buy_family: 'V3_CLMM',
              sell_family: 'V3_CLMM',
              buy_leg_price: 1.002,
              sell_leg_price: 1.006,
              raw_spread_usd: Number((grossC1 * 0.8).toFixed(2)),
              raw_spread_bps: Number((12.5 + Math.random() * 8.0).toFixed(2)),
              state_hash: `0xstate_${oppHash}`,
              route_hash: `0xroute_c1_${oppHash}`,
              opportunity_status: 'C1_PENDING',
              c1_cycle_id: c1Id,
              c2_cycle_id: null,
              created_at_ms: Date.now(),
              updated_at_ms: Date.now(),
            };

            const newC1: C1CycleRecord = {
              c1_cycle_id: c1Id,
              opportunity_id: newOppId,
              cycle_type: 'C1',
              cycle_index: 1,
              chain_id: 137,
              discovery_block: nextBlock,
              execution_anchor_block: nextBlock + 1,
              expires_at_block: nextBlock + 4, // 4-block staleness law
              borrow_asset: chosenAsset,
              borrow_amount_raw: '50000000000',
              borrow_amount_usd: 50000.0,
              route_hash: `0xroute_c1_${oppHash}`,
              state_hash: `0xstate_${oppHash}`,
              config_hash: '0xconfig44',
              expected_gross_usd: grossC1,
              expected_net_usd: netC1,
              min_net_usd: 5.0,
              gas_estimate_usd: gasC1,
              flash_fee_usd: 5.0,
              risk_buffer_usd: 1.5,
              mev_buffer_usd: 1.0,
              simulation_status: 'PASSED',
              payload_status: 'BUILT',
              submission_status: 'SUBMITTED_PRIVATE',
              settlement_status: 'PENDING',
              tx_hash: `0x${Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join('')}`,
              submitted_block: nextBlock,
              confirmed_block: nextBlock,
              realized_gross_usd: grossC1 - 0.5,
              realized_net_usd: netC1 - 0.4,
              realized_gas_usd: gasC1,
              realized_profit_raw: `${Math.round((netC1 - 0.4) * 1e6)}`,
              reject_reason: null,
              created_at_ms: Date.now(),
              updated_at_ms: Date.now(),
            };

            // Automated Settlement Simulation in 1 block
            setTimeout(() => {
              // Mark C1 Settled
              setC1Cycles((prev) =>
                prev.map((c) => (c.c1_cycle_id === c1Id ? { ...c, submission_status: 'CONFIRMED', settlement_status: 'SETTLED' } : c))
              );

              // C2 LAW: C2 is ONLY generated via C1 activation
              const c2Gross = Number((11.0 + Math.random() * 12.0).toFixed(2));
              const c2Gas = 2.4;
              const c2Net = Number((c2Gross - c2Gas - 3.5).toFixed(2));

              const newC2: C2CycleRecord = {
                c2_cycle_id: c2Id,
                opportunity_id: newOppId,
                parent_c1_cycle_id: c1Id,
                cycle_type: 'C2',
                cycle_index: 2,
                c1_tx_hash: newC1.tx_hash!,
                c1_confirmed_block: nextBlock,
                c2_window_start_block: nextBlock + 1,
                c2_window_end_block: nextBlock + 5,
                c2_eval_block: nextBlock + 1,
                post_c1_state_hash: `0xpost_c1_${oppHash}`,
                pre_c2_route_hash: `0xroute_c1_${oppHash}`,
                c2_route_hash: `0xroute_c2_reverse_${oppHash}`,
                c2_decision: Math.random() > 0.2 ? 'REVERSE' : 'MIRROR',
                mirror_expected_net_usd: -0.85,
                reverse_expected_net_usd: c2Net,
                selected_expected_net_usd: c2Net,
                borrow_asset: chosenAsset,
                borrow_amount_raw: '30000000000',
                borrow_amount_usd: 30000.0,
                gas_estimate_usd: c2Gas,
                flash_fee_usd: 3.5,
                risk_buffer_usd: 1.0,
                mev_buffer_usd: 0.8,
                simulation_status: 'PASSED',
                payload_status: 'BUILT',
                submission_status: 'CONFIRMED',
                settlement_status: 'SETTLED',
                tx_hash: `0x${Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join('')}`,
                submitted_block: nextBlock + 1,
                confirmed_block: nextBlock + 1,
                realized_gross_usd: c2Gross,
                realized_net_usd: c2Net,
                realized_gas_usd: c2Gas,
                realized_profit_raw: `${Math.round(c2Net * 1e6)}`,
                reject_reason: null,
                created_at_ms: Date.now(),
                updated_at_ms: Date.now(),
              };

              setC2Cycles((prev) => [newC2, ...prev]);

              setOpportunities((prev) =>
                prev.map((o) =>
                  o.opportunity_id === newOppId
                    ? { ...o, opportunity_status: 'CLOSED_PROFITABLE', c2_cycle_id: c2Id }
                    : o
                )
              );

              // Add Events
              const evt1: CycleEventRecord = {
                event_id: `evt_${Date.now()}_1`,
                opportunity_id: newOppId,
                cycle_id: c1Id,
                cycle_type: 'C1',
                event_type: 'CONFIRMED',
                event_status: 'SETTLED',
                block_number: nextBlock,
                tx_hash: newC1.tx_hash,
                state_hash: newC1.state_hash,
                route_hash: newC1.route_hash,
                config_hash: '0xconfig44',
                message: `C1 Flash Loan Confirmed on Chain 137. Realized Net: +$${newC1.realized_net_usd}`,
                created_at_ms: Date.now(),
              };

              const evt2: CycleEventRecord = {
                event_id: `evt_${Date.now()}_2`,
                opportunity_id: newOppId,
                cycle_id: c2Id,
                cycle_type: 'C2',
                event_type: 'C2_REVERSE_EVALUATED',
                event_status: 'SUCCESS',
                block_number: nextBlock + 1,
                tx_hash: newC2.tx_hash,
                state_hash: newC2.post_c1_state_hash,
                route_hash: newC2.c2_route_hash,
                config_hash: '0xconfig44',
                message: `C2 Decision: REVERSE. Confirmed on Chain 137. Realized Net: +$${c2Net}. Combined: +$${(newC1.realized_net_usd! + c2Net).toFixed(2)}`,
                created_at_ms: Date.now() + 500,
              };

              setCycleEvents((prev) => [evt2, evt1, ...prev]);
            }, 1800);

            setOpportunities((prev) => [newOpp, ...prev]);
            setC1Cycles((prev) => [newC1, ...prev]);
            setSelectedOppId(newOppId);
          }

          return nextBlock;
        });
      }, 2500);
    }
    return () => clearInterval(interval);
  }, [autoEngineActive]);

  // Selected Opportunity Detail Object
  const selectedOpp = opportunities.find((o) => o.opportunity_id === selectedOppId) || opportunities[0];
  const selectedC1 = c1Cycles.find((c) => c.opportunity_id === selectedOpp?.opportunity_id);
  const selectedC2 = c2Cycles.find((c) => c.opportunity_id === selectedOpp?.opportunity_id);
  const selectedEvents = cycleEvents.filter((e) => e.opportunity_id === selectedOpp?.opportunity_id);

  const c1Net = selectedC1?.realized_net_usd || selectedC1?.expected_net_usd || 0;
  const c2Net = selectedC2?.realized_net_usd || selectedC2?.selected_expected_net_usd || 0;
  const combinedNet = Number((c1Net + c2Net).toFixed(2));

  // Copy Helper
  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopySuccess(label);
    setTimeout(() => setCopySuccess(null), 2000);
  };

  return (
    <div className="bg-slate-950 text-slate-100 min-h-screen p-4 md:p-6 font-mono space-y-6">
      {/* Studio Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="bg-emerald-500/20 text-emerald-300 text-[10px] font-bold px-2.5 py-0.5 rounded border border-emerald-500/30 uppercase tracking-widest flex items-center gap-1">
              <Zap className="w-3 h-3 text-emerald-400" /> C1 × C2 Logging Engine
            </span>
            <span className="bg-cyan-500/20 text-cyan-300 text-[10px] font-bold px-2 py-0.5 rounded border border-cyan-500/30 uppercase font-mono">
              Polygon #137
            </span>
            <span className="bg-purple-500/20 text-purple-300 text-[10px] font-bold px-2 py-0.5 rounded border border-purple-500/30 uppercase font-mono">
              4-Block Parity Enforcement
            </span>
          </div>
          <h1 className="text-xl md:text-2xl font-black text-white tracking-tight flex items-center gap-2">
            <span>Deterministic C1 × C2 Execution Lifecycle</span>
          </h1>
          <p className="text-xs text-slate-400 max-w-3xl">
            C2 is strictly conditional upon C1 confirmation. All payload parameters and cycle state data are anchored to block parity and automatically expire after <span className="text-amber-400 font-bold">4 blocks (~8 seconds)</span> if unexecuted.
          </p>
        </div>

        {/* Live Controls & Block Clock */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="bg-slate-950 px-4 py-2 rounded-xl border border-slate-800 flex items-center gap-3">
            <div className="flex flex-col">
              <span className="text-[9px] uppercase font-bold text-slate-400">Current Polygon Block</span>
              <span className="text-sm font-black font-mono text-cyan-400 animate-pulse">#{currentBlock}</span>
            </div>
            <RefreshCw className={`w-4 h-4 text-cyan-400 ${autoEngineActive ? 'animate-spin' : ''}`} />
          </div>

          <button
            onClick={() => setAutoEngineActive(!autoEngineActive)}
            className={`px-4 py-2.5 rounded-xl font-bold text-xs flex items-center gap-2 transition-all shadow-lg ${
              autoEngineActive
                ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20'
                : 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-600/20'
            }`}
          >
            {autoEngineActive ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current" />}
            <span>{autoEngineActive ? 'AUTOMATED BOT RUNNING' : 'ENGINE PAUSED'}</span>
          </button>
        </div>
      </div>

      {/* Target Executors & Active Contracts Hud */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-bold flex justify-between">
            <span>C1 Arbitrage Executor</span>
            <span className="text-emerald-400">Deployed</span>
          </div>
          <div className="text-xs font-mono font-bold text-emerald-300 truncate">
            {POLYGON_CHAIN_CONFIG.c1ArbExecutorAddress}
          </div>
          <div className="text-[9px] text-slate-500">Flash Loan & Route Swaps</div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-bold flex justify-between">
            <span>Liquidation Executor</span>
            <span className="text-emerald-400">Deployed</span>
          </div>
          <div className="text-xs font-mono font-bold text-emerald-300 truncate">
            {POLYGON_CHAIN_CONFIG.liquidationExecutorAddress}
          </div>
          <div className="text-[9px] text-slate-500">Aave V3 Health Factor Sentinel</div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-bold flex justify-between">
            <span>FastLane Private MEV Relay</span>
            <span className="text-cyan-400">Connected</span>
          </div>
          <div className="text-xs font-mono font-bold text-cyan-300 truncate">
            https://rpc.fastlane.xyz
          </div>
          <div className="text-[9px] text-slate-500">Frontrun & Revert Protected</div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl space-y-1">
          <div className="text-[10px] text-slate-400 uppercase font-bold flex justify-between">
            <span>Block Staleness Rule</span>
            <span className="text-amber-400 font-bold">Max 4 Blocks</span>
          </div>
          <div className="text-xs font-mono font-bold text-amber-300">
            Expires: block_disc + 4
          </div>
          <div className="text-[9px] text-slate-500">Unmined payloads drop after ~8s</div>
        </div>
      </div>

      {/* Main Studio Interactive Views */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Side: Opportunities Master List */}
        <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl">
          <div className="flex justify-between items-center border-b border-slate-800 pb-2">
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span>Opportunities Stream ({opportunities.length})</span>
            </h2>
            <span className="text-[10px] text-slate-400 uppercase">Canonical Hash IDs</span>
          </div>

          <div className="space-y-2 max-h-[580px] overflow-y-auto pr-1 no-scrollbar">
            {opportunities.map((opp) => {
              const isSelected = opp.opportunity_id === selectedOppId;
              const blocksLeft = Math.max(0, opp.discovered_block + 4 - currentBlock);
              const isExpired = opp.opportunity_status === 'STALE_EXPIRED' || (blocksLeft === 0 && opp.opportunity_status === 'C1_PENDING');

              return (
                <div
                  key={opp.opportunity_id}
                  onClick={() => setSelectedOppId(opp.opportunity_id)}
                  className={`p-3 rounded-xl border cursor-pointer transition-all space-y-2 ${
                    isSelected
                      ? 'bg-emerald-950/40 border-emerald-500/80 shadow-lg shadow-emerald-500/5'
                      : 'bg-slate-950/60 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-mono font-bold text-emerald-300 truncate max-w-[170px]">
                      {opp.opportunity_id}
                    </span>
                    <span
                      className={`text-[9px] font-bold px-2 py-0.5 rounded border uppercase ${
                        opp.opportunity_status === 'CLOSED_PROFITABLE'
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                          : opp.opportunity_status === 'STALE_EXPIRED' || isExpired
                          ? 'bg-red-500/20 text-red-300 border-red-500/40'
                          : 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse'
                      }`}
                    >
                      {isExpired ? 'STALE_EXPIRED' : opp.opportunity_status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-400 font-mono bg-slate-900/60 p-2 rounded-lg border border-slate-800/80">
                    <div>
                      <span className="text-slate-500 block">Buy Venue:</span>
                      <span className="text-slate-200 font-bold">{opp.buy_venue}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Sell Venue:</span>
                      <span className="text-slate-200 font-bold">{opp.sell_venue}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Borrow Asset:</span>
                      <span className="text-cyan-300 font-bold">{opp.borrow_asset}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Block Anchor:</span>
                      <span className="text-purple-300 font-bold">#{opp.discovered_block}</span>
                    </div>
                  </div>

                  <div className="flex justify-between items-center text-[10px]">
                    <div className="flex items-center gap-1 text-slate-400">
                      <Clock className="w-3 h-3 text-amber-400" />
                      <span>
                        Block Age:{' '}
                        <strong className={blocksLeft === 0 ? 'text-red-400' : 'text-amber-300'}>
                          {blocksLeft > 0 ? `${blocksLeft} blks left` : 'EXPIRED'}
                        </strong>
                      </span>
                    </div>

                    <div className="flex items-center gap-1 font-bold text-emerald-400">
                      <span>Spread: +${opp.raw_spread_usd}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Side: Selected Opportunity Inspector & State Machine */}
        <div className="lg:col-span-8 space-y-4">
          {/* Navigation Tabs for Inspector */}
          <div className="bg-slate-900 border border-slate-800 p-2 rounded-xl flex items-center justify-between overflow-x-auto no-scrollbar gap-2">
            <div className="flex items-center gap-1">
              <button
                onClick={() => setActiveTab('TIMELINE')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  activeTab === 'TIMELINE' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Activity className="w-3.5 h-3.5" />
                <span>Cycle Timeline</span>
              </button>

              <button
                onClick={() => setActiveTab('C1_CYCLES')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  activeTab === 'C1_CYCLES' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Zap className="w-3.5 h-3.5" />
                <span>C1 Log Record</span>
              </button>

              <button
                onClick={() => setActiveTab('C2_CYCLES')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  activeTab === 'C2_CYCLES' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'text-slate-400 hover:text-white'
                }`}
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>C2 Log Record</span>
              </button>

              <button
                onClick={() => setActiveTab('EVENTS')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  activeTab === 'EVENTS' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>Event Stream ({selectedEvents.length})</span>
              </button>

              <button
                onClick={() => setActiveTab('JSON_STATE')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  activeTab === 'JSON_STATE' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Database className="w-3.5 h-3.5" />
                <span>Machine State (JSON)</span>
              </button>
            </div>

            <button
              onClick={() => handleCopy(JSON.stringify(selectedOpp, null, 2), 'opp_json')}
              className="text-[10px] text-cyan-300 hover:text-cyan-100 flex items-center gap-1 bg-slate-800 px-2.5 py-1 rounded border border-slate-700"
            >
              {copyStatus === 'opp_json' ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span>{copyStatus === 'opp_json' ? 'Copied' : 'Copy Data'}</span>
            </button>
          </div>

          {/* Selected Opportunity Header Summary Box */}
          {selectedOpp && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl">
              <div className="flex flex-col md:flex-row justify-between md:items-center gap-2 border-b border-slate-800 pb-3">
                <div>
                  <div className="text-[10px] text-slate-400 uppercase font-bold">Active Opportunity Container</div>
                  <div className="text-sm font-black font-mono text-emerald-300">{selectedOpp.opportunity_id}</div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">C1 Net Yield</div>
                    <div className="text-xs font-bold text-emerald-400">+${c1Net.toFixed(2)}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] text-slate-400 uppercase font-bold">C2 Reaction Yield</div>
                    <div className="text-xs font-bold text-cyan-400">+${c2Net.toFixed(2)}</div>
                  </div>
                  <div className="bg-emerald-950/80 border border-emerald-500/50 p-2 rounded-xl text-right">
                    <div className="text-[9px] text-emerald-300 font-bold uppercase">Combined Realized PnL</div>
                    <div className="text-sm font-black text-emerald-400">+${combinedNet.toFixed(2)}</div>
                  </div>
                </div>
              </div>

              {/* C1 x C2 Execution Law Indicator */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                  <div className="flex justify-between text-[10px] font-bold uppercase">
                    <span className="text-slate-400">C1 Cycle Status</span>
                    <span className="text-emerald-400">{selectedC1?.settlement_status || 'PENDING'}</span>
                  </div>
                  <div className="text-slate-200 font-mono text-[11px] truncate">
                    Hash: {selectedC1?.tx_hash ? selectedC1.tx_hash.substring(0, 18) + '...' : 'Not broadcast'}
                  </div>
                  <div className="text-[9px] text-slate-500">
                    Anchor Block: #{selectedC1?.execution_anchor_block || selectedOpp.discovered_block}
                  </div>
                </div>

                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                  <div className="flex justify-between text-[10px] font-bold uppercase">
                    <span className="text-slate-400">C2 Conditional Law</span>
                    <span className={selectedC2 ? 'text-cyan-400' : 'text-slate-500'}>
                      {selectedC2 ? `ACTIVATED (${selectedC2.c2_decision})` : 'WAITING FOR C1'}
                    </span>
                  </div>
                  <div className="text-slate-200 font-mono text-[11px] truncate">
                    Parent C1: {selectedC1?.c1_cycle_id || 'N/A'}
                  </div>
                  <div className="text-[9px] text-slate-500">
                    Window: #{selectedC2?.c2_window_start_block || selectedOpp.discovered_block + 1} - #{selectedC2?.c2_window_end_block || selectedOpp.discovered_block + 5}
                  </div>
                </div>

                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 space-y-1">
                  <div className="flex justify-between text-[10px] font-bold uppercase">
                    <span className="text-slate-400">Parity Expiration</span>
                    <span className="text-amber-400 font-bold">
                      {Math.max(0, selectedOpp.discovered_block + 4 - currentBlock)} Blocks Remaining
                    </span>
                  </div>
                  <div className="w-full bg-slate-900 rounded-full h-2 mt-1.5 overflow-hidden">
                    <div
                      className="bg-amber-400 h-2 transition-all duration-500"
                      style={{
                        width: `${Math.min(100, Math.max(0, ((selectedOpp.discovered_block + 4 - currentBlock) / 4) * 100))}%`,
                      }}
                    />
                  </div>
                  <div className="text-[9px] text-slate-500 flex justify-between">
                    <span>Disc: #{selectedOpp.discovered_block}</span>
                    <span>Max: #{selectedOpp.discovered_block + 4}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB CONTENT: Timeline */}
          {activeTab === 'TIMELINE' && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-xl">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <Sliders className="w-4 h-4 text-emerald-400" />
                <span>Deterministic Execution Pipeline Timeline</span>
              </h3>

              <div className="relative border-l-2 border-slate-800 pl-6 space-y-6 my-2">
                {/* Discovery Step */}
                <div className="relative space-y-1">
                  <div className="absolute -left-[31px] top-0 bg-emerald-500 text-slate-950 rounded-full p-1 border-2 border-slate-900">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-white uppercase">[Block #{selectedOpp?.discovered_block}] DISCOVERY LOG</span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(selectedOpp?.detected_at_ms || Date.now()).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Discovered positive Bellman-Ford spread ({selectedOpp?.raw_spread_bps} bps) on Polygon Mainnet.
                    Config Hash: <code className="text-cyan-300">{selectedOpp?.config_hash}</code>.
                  </p>
                </div>

                {/* C1 Execution Step */}
                <div className="relative space-y-1">
                  <div className={`absolute -left-[31px] top-0 rounded-full p-1 border-2 border-slate-900 ${
                    selectedC1?.settlement_status === 'SETTLED' ? 'bg-emerald-500 text-slate-950' : 'bg-amber-500 text-slate-950'
                  }`}>
                    <Zap className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-white uppercase">
                      [Block #{selectedC1?.execution_anchor_block || selectedOpp?.discovered_block}] C1 CYCLE EXECUTION
                    </span>
                    <span className="text-[10px] text-emerald-400 font-bold">
                      {selectedC1?.settlement_status || 'PENDING'}
                    </span>
                  </div>
                  <div className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Route Hash:</span>
                      <span className="font-mono text-cyan-300">{selectedC1?.route_hash}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Borrow Flash Loan:</span>
                      <span className="font-mono text-slate-200">${selectedC1?.borrow_amount_usd.toLocaleString()} {selectedC1?.borrow_asset}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Private FastLane Hash:</span>
                      <a
                        href={`https://polygonscan.com/tx/${selectedC1?.tx_hash}`}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-cyan-400 underline truncate max-w-[240px] flex items-center gap-1"
                      >
                        <span>{selectedC1?.tx_hash?.substring(0, 16)}...</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                    <div className="flex justify-between pt-1 border-t border-slate-800 text-emerald-400 font-bold">
                      <span>C1 Realized Net Yield:</span>
                      <span>+${selectedC1?.realized_net_usd || 0} USD</span>
                    </div>
                  </div>
                </div>

                {/* C2 Reaction Step */}
                <div className="relative space-y-1">
                  <div className={`absolute -left-[31px] top-0 rounded-full p-1 border-2 border-slate-900 ${
                    selectedC2?.settlement_status === 'SETTLED' ? 'bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-400'
                  }`}>
                    <RefreshCw className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-white uppercase">
                      [Block #{selectedC2?.c2_eval_block || selectedOpp?.discovered_block + 1}] C2 POST-C1 REACTION
                    </span>
                    <span className="text-[10px] text-cyan-400 font-bold">
                      {selectedC2 ? `DECISION: ${selectedC2.c2_decision}` : 'WAITING FOR C1 SETTLEMENT'}
                    </span>
                  </div>

                  {selectedC2 ? (
                    <div className="bg-slate-950 p-3 rounded-xl border border-slate-800/80 text-xs space-y-1">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Post-C1 State Reloaded:</span>
                        <span className="font-mono text-purple-300">{selectedC2.post_c1_state_hash}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Branch Evaluation:</span>
                        <span className="font-mono text-slate-300">MIRROR: ${selectedC2.mirror_expected_net_usd} | REVERSE: +${selectedC2.reverse_expected_net_usd}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">C2 FastLane Hash:</span>
                        <a
                          href={`https://polygonscan.com/tx/${selectedC2.tx_hash}`}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-cyan-400 underline truncate max-w-[240px] flex items-center gap-1"
                        >
                          <span>{selectedC2.tx_hash?.substring(0, 16)}...</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                      <div className="flex justify-between pt-1 border-t border-slate-800 text-cyan-400 font-bold">
                        <span>C2 Realized Net Yield:</span>
                        <span>+${selectedC2.realized_net_usd || 0} USD</span>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/50 text-xs text-slate-500 italic">
                      C2 execution window opens automatically upon confirmed C1 block inclusion. If C1 fails, C2 is marked CANCELLED.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB CONTENT: C1 Cycle Record */}
          {activeTab === 'C1_CYCLES' && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">c1_cycles Table Row Record</h3>
              {selectedC1 ? (
                <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-[11px] text-emerald-300 font-mono overflow-x-auto leading-relaxed">
                  {JSON.stringify(selectedC1, null, 2)}
                </pre>
              ) : (
                <div className="text-slate-500 text-xs italic">No C1 Record found for this opportunity.</div>
              )}
            </div>
          )}

          {/* TAB CONTENT: C2 Cycle Record */}
          {activeTab === 'C2_CYCLES' && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">c2_cycles Table Row Record</h3>
              {selectedC2 ? (
                <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-[11px] text-cyan-300 font-mono overflow-x-auto leading-relaxed">
                  {JSON.stringify(selectedC2, null, 2)}
                </pre>
              ) : (
                <div className="text-slate-500 text-xs italic">No C2 Reaction Record generated yet (C1 must settle first).</div>
              )}
            </div>
          )}

          {/* TAB CONTENT: Event Stream */}
          {activeTab === 'EVENTS' && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl max-h-[500px] overflow-y-auto no-scrollbar">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">cycle_events Database Audit Trail</h3>
              <div className="space-y-2">
                {selectedEvents.map((evt) => (
                  <div key={evt.event_id} className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs space-y-1">
                    <div className="flex justify-between items-center text-[10px]">
                      <span className="font-bold text-cyan-400 uppercase">[{evt.cycle_type}] {evt.event_type}</span>
                      <span className="text-purple-300 font-mono">Block #{evt.block_number}</span>
                    </div>
                    <p className="text-slate-200">{evt.message}</p>
                    <div className="text-[9px] text-slate-500 font-mono flex justify-between">
                      <span>Event ID: {evt.event_id}</span>
                      <span>{new Date(evt.created_at_ms).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB CONTENT: Machine State JSON */}
          {activeTab === 'JSON_STATE' && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 shadow-xl">
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">Dashboard Machine State Export</h3>
              <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800 text-[11px] text-emerald-300 font-mono overflow-x-auto leading-relaxed">
                {JSON.stringify(
                  {
                    opportunity_id: selectedOpp?.opportunity_id,
                    status: selectedOpp?.opportunity_status,
                    blocks: {
                      discovered: selectedOpp?.discovered_block,
                      c1_submitted: selectedC1?.submitted_block,
                      c1_confirmed: selectedC1?.confirmed_block,
                      c2_window_start: selectedC2?.c2_window_start_block,
                      c2_window_end: selectedC2?.c2_window_end_block,
                      c2_submitted: selectedC2?.submitted_block,
                      c2_confirmed: selectedC2?.confirmed_block,
                    },
                    c1: selectedC1,
                    c2: selectedC2,
                    pnl: {
                      c1_realized_net_usd: c1Net,
                      c2_realized_net_usd: c2Net,
                      combined_realized_net_usd: combinedNet,
                    },
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
