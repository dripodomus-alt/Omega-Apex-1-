import React, { useState } from 'react';
import { PoolInfo } from '../types';
import { CHAINLINK_FEEDS, FULL_CHAIN_137_METRICS } from '../data/mockEngineData';
import { MidTokenPoolRegistryStudio } from './MidTokenPoolRegistryStudio';
import {
  Server,
  ShieldCheck,
  Zap,
  Lock,
  Activity,
  Copy,
  Check,
  Network,
  Radio,
  RefreshCw,
  Search,
  CheckCircle2,
  Coins,
} from 'lucide-react';

interface ProtocolRegistryMatrixProps {
  pools: PoolInfo[];
}

interface RpcSourceConfig {
  id: string;
  name: string;
  type: 'PRIMARY_RPC' | 'HIGH_SPEED_WS' | 'MEV_BUNDLE_RELAY' | 'ORACLE_AGGREGATOR';
  endpoint: string;
  latencyMs: number;
  status: 'ACTIVE' | 'STANDBY' | 'OPTIMAL';
  isQuorumParticipant: boolean;
}

export const ProtocolRegistryMatrix: React.FC<ProtocolRegistryMatrixProps> = ({ pools }) => {
  const [activeSubTab, setActiveSubTab] = useState<'MID_TOKEN_STUDIO' | 'TOPOLOGY_MATRIX' | 'ORACLES'>('MID_TOKEN_STUDIO');
  const [copiedAddress, setCopiedAddress] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedProtocolFilter, setSelectedProtocolFilter] = useState('ALL');

  // Multi-Source RPC Configuration State
  const [activePrimarySourceId, setActivePrimarySourceId] = useState<string>('rpc_alchemy');
  const [isBatchSyncing, setIsBatchSyncing] = useState<boolean>(false);
  const [syncBatchNotification, setSyncBatchNotification] = useState<string | null>(null);

  const [rpcSources, setRpcSources] = useState<RpcSourceConfig[]>([
    {
      id: 'rpc_polygon_official',
      name: 'Polygon PoS Official Public RPC',
      type: 'PRIMARY_RPC',
      endpoint: 'https://polygon-rpc.com',
      latencyMs: 18.2,
      status: 'ACTIVE',
      isQuorumParticipant: true,
    },
    {
      id: 'rpc_alchemy',
      name: 'Alchemy High-Speed WSS Node',
      type: 'HIGH_SPEED_WS',
      endpoint: 'wss://polygon-mainnet.g.alchemy.com/v2/omega-v5-key',
      latencyMs: 4.1,
      status: 'OPTIMAL',
      isQuorumParticipant: true,
    },
    {
      id: 'rpc_quicknode',
      name: 'QuickNode Low-Latency Fallback',
      type: 'PRIMARY_RPC',
      endpoint: 'https://polygon-mainnet.discover.quiknode.pro/sub-ms',
      latencyMs: 8.5,
      status: 'STANDBY',
      isQuorumParticipant: true,
    },
    {
      id: 'rpc_fastlane_mev',
      name: 'FastLane / Private MEV Bundle Relay',
      type: 'MEV_BUNDLE_RELAY',
      endpoint: 'https://polygon-relay.fastlane.finance/v1/bundle',
      latencyMs: 2.3,
      status: 'OPTIMAL',
      isQuorumParticipant: false,
    },
    {
      id: 'oracle_chainlink_pyth',
      name: 'Chainlink + Pyth Hybrid Oracle Gateway',
      type: 'ORACLE_AGGREGATOR',
      endpoint: 'internal://oracle-router.polygon.137',
      latencyMs: 0.8,
      status: 'OPTIMAL',
      isQuorumParticipant: true,
    },
  ]);

  const fundingPools = pools.filter((p) => p.isFundingPool);
  const executionPools = pools.filter((p) => !p.isFundingPool);

  const filteredExecutionPools = executionPools.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.address.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.token0.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.token1.symbol.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesProtocol = selectedProtocolFilter === 'ALL' || p.protocol === selectedProtocolFilter;
    return matchesSearch && matchesProtocol;
  });

  const copyToClipboard = (addr: string) => {
    navigator.clipboard.writeText(addr);
    setCopiedAddress(addr);
    setTimeout(() => setCopiedAddress(null), 2000);
  };

  const handleBatchSyncOraclesAndPools = () => {
    setIsBatchSyncing(true);
    setSyncBatchNotification(null);

    setTimeout(() => {
      setRpcSources((prev) =>
        prev.map((s) => ({
          ...s,
          latencyMs: Number((Math.random() * 8 + 1.2).toFixed(1)),
        }))
      );
      setIsBatchSyncing(false);
      setSyncBatchNotification(
        `Batch Sync Complete: Refreshed state across ${pools.length} DEX pools, ${Object.keys(CHAINLINK_FEEDS).length} Chainlink oracles, and 5 multi-source RPC nodes!`
      );

      setTimeout(() => {
        setSyncBatchNotification(null);
      }, 5000);
    }, 1200);
  };

  const toggleQuorumParticipant = (id: string) => {
    setRpcSources((prev) =>
      prev.map((s) => (s.id === id ? { ...s, isQuorumParticipant: !s.isQuorumParticipant } : s))
    );
  };

  return (
    <div id="protocol-registry-matrix" className="space-y-6">
      {/* Sub-Tab Navigation Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-2.5 flex flex-wrap items-center gap-2 font-mono text-xs">
        <button
          onClick={() => setActiveSubTab('MID_TOKEN_STUDIO')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'MID_TOKEN_STUDIO'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 shadow-lg shadow-emerald-950/40'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          <Coins className="w-4 h-4 text-emerald-400" />
          <span>Base Assets &amp; Mid-Token Pool Registry</span>
          <span className="bg-emerald-950 text-emerald-300 border border-emerald-800 text-[9px] px-1.5 py-0.2 rounded font-mono">
            Raw Delta &amp; Units
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('TOPOLOGY_MATRIX')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'TOPOLOGY_MATRIX'
              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/50 shadow-lg shadow-purple-950/40'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          <Network className="w-4 h-4 text-purple-400" />
          <span>Polygon #137 Topology &amp; Multi-RPC Gateway</span>
        </button>

        <button
          onClick={() => setActiveSubTab('ORACLES')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeSubTab === 'ORACLES'
              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 shadow-lg shadow-amber-950/40'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          <Activity className="w-4 h-4 text-amber-400" />
          <span>Chainlink Price Feeds</span>
        </button>
      </div>

      {activeSubTab === 'MID_TOKEN_STUDIO' && (
        <MidTokenPoolRegistryStudio />
      )}

      {activeSubTab === 'TOPOLOGY_MATRIX' && (
        <>
          {/* Chain 2137b / #137 Mainnet Full Coverage Banner */}
          <div className="bg-gradient-to-r from-purple-950/80 via-slate-900 to-indigo-950/80 border border-purple-800/80 rounded-xl p-5 shadow-2xl space-y-4">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Network className="w-5 h-5 text-purple-400 animate-pulse" />
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                    Chain #137 / #2137b Polygon PoS Mainnet Network Topology Matrix
                  </h2>
                </div>
                <p className="text-xs text-slate-300 mt-1 max-w-3xl leading-relaxed font-mono">
                  Full-chain graph indexer indexing {FULL_CHAIN_137_METRICS.totalIndexedPools.toLocaleString()} pools and {FULL_CHAIN_137_METRICS.totalSwappableEdges.toLocaleString()} directed liquidity edges across 14 DEX protocols on Polygon PoS.
                </p>
              </div>

              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
                <div className="flex items-center gap-2 bg-emerald-950/90 border border-emerald-800 px-3.5 py-2 rounded-lg text-xs font-mono text-emerald-300 shrink-0">
                  <Lock className="w-4 h-4 text-emerald-400" />
                  <span>Self-Funding Shield &amp; Pot Isolation ACTIVE</span>
                </div>
                <div className="flex items-center gap-2 bg-indigo-950/90 border border-indigo-800 px-3.5 py-2 rounded-lg text-xs font-mono text-indigo-300 shrink-0">
                  <ShieldCheck className="w-4 h-4 text-indigo-400" />
                  <span>Registry Asset Verification Enforced</span>
                </div>
              </div>
            </div>

            {/* Full Chain Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-2 border-t border-purple-900/60 font-mono text-xs">
              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <div className="text-slate-400 text-[10px] uppercase">Chain ID</div>
                <div className="text-white font-bold mt-0.5 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-purple-400"></span>
                  #137 (0x89 / 2137b)
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <div className="text-slate-400 text-[10px] uppercase">Indexed DEX Pools</div>
                <div className="text-purple-300 font-bold mt-0.5">
                  {FULL_CHAIN_137_METRICS.totalIndexedPools.toLocaleString()} Pools
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <div className="text-slate-400 text-[10px] uppercase">Swappable Edges</div>
                <div className="text-cyan-300 font-bold mt-0.5">
                  {FULL_CHAIN_137_METRICS.totalSwappableEdges.toLocaleString()} Directed
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <div className="text-slate-400 text-[10px] uppercase">Tracked Chain TVL</div>
                <div className="text-emerald-400 font-bold mt-0.5">
                  ${(FULL_CHAIN_137_METRICS.totalTrackedTvlUSD / 1e6).toFixed(1)}M USD
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <div className="text-slate-400 text-[10px] uppercase">Protocols Covered</div>
                <div className="text-amber-300 font-bold mt-0.5">
                  {FULL_CHAIN_137_METRICS.indexedProtocolsCount} Major DEXes
                </div>
              </div>

              <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800">
                <div className="text-slate-400 text-[10px] uppercase">Graph Sweep Latency</div>
                <div className="text-emerald-300 font-bold mt-0.5">
                  {FULL_CHAIN_137_METRICS.avgFullGraphSweepMs} ms / cycle
                </div>
              </div>
            </div>

            {/* Active DEX Badges Bar */}
            <div className="pt-2 border-t border-purple-900/40 flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
              <span className="text-slate-400 font-semibold mr-1">Indexed Protocols:</span>
              {FULL_CHAIN_137_METRICS.activeDexes.map((dex) => (
                <span
                  key={dex}
                  className="px-2 py-0.5 bg-purple-950/80 border border-purple-800 text-purple-200 rounded"
                >
                  {dex}
                </span>
              ))}
            </div>
          </div>

          {/* Multi-Source RPC Nodes Gateway Configuration */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <Radio className="w-5 h-5 text-cyan-400" />
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                    Multi-Source RPC Nodes &amp; Oracle Data Feeds Gateway
                  </h3>
                </div>
                <p className="text-xs text-slate-400 mt-1 font-mono">
                  Configure primary RPC sources, WebSocket telemetry feeds, MEV bundle relays, and oracle quorums on Polygon PoS.
                </p>
              </div>

              <button
                onClick={handleBatchSyncOraclesAndPools}
                disabled={isBatchSyncing}
                className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-mono text-xs font-bold rounded-lg transition-all shadow-lg active:scale-95 disabled:opacity-50 shrink-0"
              >
                <RefreshCw className={`w-4 h-4 ${isBatchSyncing ? 'animate-spin text-purple-200' : 'text-purple-300'}`} />
                <span>
                  {isBatchSyncing ? 'Batch Syncing All Sources...' : `Batch Sync Oracles & Pools (${pools.length} Pools / ${Object.keys(CHAINLINK_FEEDS).length} Feeds)`}
                </span>
              </button>
            </div>

            {syncBatchNotification && (
              <div className="bg-emerald-950/80 border border-emerald-700/80 p-3 rounded-lg flex items-center gap-2 text-xs font-mono text-emerald-300 animate-fadeIn">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{syncBatchNotification}</span>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {rpcSources.map((source) => {
                const isPrimary = activePrimarySourceId === source.id;
                return (
                  <div
                    key={source.id}
                    className={`p-3.5 rounded-xl border transition-all ${
                      isPrimary
                        ? 'bg-cyan-950/40 border-cyan-700/80 shadow-lg shadow-cyan-950/30'
                        : 'bg-slate-950 border-slate-800/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wide px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-cyan-300">
                        {source.type.replace(/_/g, ' ')}
                      </span>
                      <div className="flex items-center gap-1.5 text-[10px] font-mono">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                        <span className="text-emerald-400 font-bold">{source.latencyMs} ms</span>
                      </div>
                    </div>

                    <div className="mt-2">
                      <div className="text-xs font-bold text-white font-mono flex items-center justify-between">
                        <span>{source.name}</span>
                        {isPrimary && (
                          <span className="text-[10px] text-cyan-400 font-mono font-bold bg-cyan-950 border border-cyan-800 px-1.5 py-0.5 rounded">
                            PRIMARY
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] font-mono text-slate-400 truncate mt-1 bg-slate-900/80 p-1.5 rounded border border-slate-800">
                        {source.endpoint}
                      </div>
                    </div>

                    <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between gap-2 text-[11px] font-mono">
                      <button
                        onClick={() => setActivePrimarySourceId(source.id)}
                        className={`px-2.5 py-1 rounded font-bold transition-all ${
                          isPrimary
                            ? 'bg-cyan-500 text-slate-950 shadow-sm'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                        }`}
                      >
                        {isPrimary ? 'Active Primary Source' : 'Set as Primary Source'}
                      </button>

                      <button
                        onClick={() => toggleQuorumParticipant(source.id)}
                        className={`px-2 py-1 rounded text-[10px] transition-all border ${
                          source.isQuorumParticipant
                            ? 'bg-purple-950 border-purple-800 text-purple-300 font-semibold'
                            : 'bg-slate-900 border-slate-800 text-slate-400'
                        }`}
                        title="Include in multi-RPC consensus quorum"
                      >
                        Quorum: {source.isQuorumParticipant ? 'ON' : 'OFF'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Funding / Flashloan Pool Registry */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                  Funding &amp; Flashloan Pool Registry (Separated Pot)
                </h3>
              </div>
              <span className="px-2.5 py-1 text-[11px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800 rounded-full font-semibold">
                {fundingPools.length} Isolated Funding Vaults
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                    <th className="p-3">Protocol / Vault</th>
                    <th className="p-3">Category</th>
                    <th className="p-3">Smart Contract Address</th>
                    <th className="p-3">Pair / Asset</th>
                    <th className="p-3">Available TVL</th>
                    <th className="p-3">Fee</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {fundingPools.map((pool) => (
                    <tr key={pool.id} className="hover:bg-slate-800/40">
                      <td className="p-3 font-semibold text-white flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                        {pool.name}
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 bg-indigo-950 text-indigo-300 rounded border border-indigo-800/60 text-[10px]">
                          {pool.category}
                        </span>
                      </td>
                      <td className="p-3 text-slate-300 font-mono text-[11px]">{pool.address}</td>
                      <td className="p-3 text-slate-200">
                        {pool.token0.symbol} / {pool.token1.symbol}
                      </td>
                      <td className="p-3 font-bold text-emerald-400">
                        ${(pool.reserve0USD + pool.reserve1USD).toLocaleString()}
                      </td>
                      <td className="p-3 text-slate-300">{pool.feeBps / 100}%</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 bg-emerald-950 text-emerald-300 rounded border border-emerald-800/60 text-[10px] font-bold">
                          {pool.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Swappable Execution Pool Registry */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-purple-400" />
                <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                  Swappable Execution Pool Registry (Polygon #137 Mainnet)
                </h3>
              </div>
              <span className="px-2.5 py-1 text-[11px] font-mono bg-purple-950 text-purple-300 border border-purple-800 rounded-full font-semibold shrink-0">
                {filteredExecutionPools.length} Active Swappable Pools
              </span>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-3 font-mono text-xs">
              <div className="relative w-full sm:w-72">
                <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Search pool, token, address..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-purple-500 text-xs"
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto">
                <span className="text-slate-400 text-[11px] shrink-0">Protocol:</span>
                {['ALL', 'V3_CLMM', 'QS_V2_CPMM', 'QS_V3_ALGEBRA', 'V2_CPMM', 'CURVE_STABLE'].map((proto) => (
                  <button
                    key={proto}
                    onClick={() => setSelectedProtocolFilter(proto)}
                    className={`px-2.5 py-1 rounded text-[11px] transition-all whitespace-nowrap ${
                      selectedProtocolFilter === proto
                        ? 'bg-purple-600 text-white font-bold'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-white'
                    }`}
                  >
                    {proto}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                    <th className="p-3">Pool Name</th>
                    <th className="p-3">Protocol Architecture</th>
                    <th className="p-3">Address</th>
                    <th className="p-3">Token Pair</th>
                    <th className="p-3">Combined Reserves</th>
                    <th className="p-3">Fee Bps</th>
                    <th className="p-3">V3 Virtualization</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredExecutionPools.map((pool) => (
                    <tr key={pool.id} className="hover:bg-slate-800/40">
                      <td className="p-3 font-semibold text-white">{pool.name}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 bg-purple-950 text-purple-300 rounded border border-purple-800/60 text-[10px]">
                          {pool.protocolArchitecture || pool.protocol}
                        </span>
                      </td>
                      <td className="p-3 text-slate-300 font-mono text-[11px]">{pool.address}</td>
                      <td className="p-3 text-slate-200">
                        {pool.token0.symbol} / {pool.token1.symbol}
                      </td>
                      <td className="p-3 font-bold text-white">
                        ${(pool.reserve0USD + pool.reserve1USD).toLocaleString()}
                      </td>
                      <td className="p-3 text-slate-300">{pool.feeBps} bps ({pool.feeBps / 100}%)</td>
                      <td className="p-3">
                        {pool.sqrtPriceX96 ? (
                          <span className="px-2 py-0.5 bg-cyan-950 text-cyan-300 rounded border border-cyan-800 text-[10px]">
                            sqrtPriceX96 Active
                          </span>
                        ) : (
                          <span className="text-slate-500 text-[10px]">Standard V2 CPMM</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {activeSubTab === 'ORACLES' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-amber-400" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                Chainlink Price Feed Oracles Matrix (Polygon PoS Mainnet)
              </h3>
            </div>
            <span className="px-2.5 py-1 text-[11px] font-mono bg-amber-950 text-amber-300 border border-amber-800 rounded-full font-semibold">
              {Object.keys(CHAINLINK_FEEDS).length} Indexed Feeds
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 bg-slate-950/60">
                  <th className="p-3">Asset Symbol</th>
                  <th className="p-3">Oracle Pair</th>
                  <th className="p-3">Chainlink Feed Contract Address</th>
                  <th className="p-3">Live Reference Price</th>
                  <th className="p-3">Heartbeat</th>
                  <th className="p-3">Deviation Threshold</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {Object.entries(CHAINLINK_FEEDS).map(([symbol, feed]) => (
                  <tr key={symbol} className="hover:bg-slate-800/40">
                    <td className="p-3 font-bold text-amber-300">{symbol}</td>
                    <td className="p-3 font-semibold text-white">{feed.pair}</td>
                    <td className="p-3 text-slate-300 font-mono text-[11px]">
                      <div className="flex items-center gap-2">
                        <span>{feed.address}</span>
                        <button
                          onClick={() => copyToClipboard(feed.address)}
                          className="text-slate-500 hover:text-slate-300 transition-colors"
                          title="Copy Oracle Address"
                        >
                          {copiedAddress === feed.address ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </td>
                    <td className="p-3 font-bold text-emerald-400">
                      ${feed.priceUSD < 1 ? feed.priceUSD.toFixed(4) : feed.priceUSD.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="p-3 text-slate-300">{feed.heartbeat}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 bg-amber-950 text-amber-300 rounded border border-amber-800/60 text-[10px]">
                        {feed.deviation}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
