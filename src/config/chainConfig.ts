// Extracted and Active Polygon Mainnet #137 Production Execution Targets & Binding Config

export const POLYGON_CHAIN_CONFIG = {
  chainId: 137,
  chainName: 'Polygon PoS (Mainnet #137)',
  runtimeMode: 'LIVE_TRADING_MAINNET',

  // Executor Bot & Wallet Binding
  botAddress: '0x9Bd51a2f18bd687d83B4A7cc9e661E4a58Fcef95',
  profitReceiverAddress: '0xAd93CCE6b616d08973472345Fa42A0b34F52d713',
  executorWallet: '0x9Bd51a2f18bd687d83B4A7cc9e661E4a58Fcef95',
  userMainnetWallet: '0x9Bd51a2f18bd687d83B4A7cc9e661E4a58Fcef95',

  // Max Opportunity Staging & Discovery Controls
  enableMaxOpportunityStaging: true,
  maxPoolDiscoveryAllAssets: true,
  discoverableIsExecutableUponGating: true,

  // Contract Targets (Pinned)
  c1ArbExecutorAddress: '0x409ece3Fd71DFBd8f692B600f36A89301cb37346',
  c2ArbExecutorAddress: '0x409ece3Fd71DFBd8f692B600f36A89301cb37346',
  hftDefaultTarget: '0x409ece3Fd71DFBd8f692B600f36A89301cb37346',
  merkleDefaultTarget: '0x409ece3Fd71DFBd8f692B600f36A89301cb37346',
  liquidationExecutorAddress: '0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951',

  // Protocol Infrastructure
  uniswapV3Quoter: '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
  uniswapV3Router: '0xE592427A0AEce92De3Edee1F18E0157C05861564',
  algebraFactory: '0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28',
  algebraQuoter: '0xa15F0D7377B2A0C0c10db057f641beD21028FC89',
  algebraRouter: '0xf5b509bB0909a69B1c207E495f687a596C168E12',
  balancerVaultAddress: '0xBA12222222228d8Ba445958a75a0704d566BF2C8',
  // Single vault address provides dual V2/V3 compatibility for flashloan capital
  curveAddressProvider: '0x0000000022D53366457F9d5E68Ec105046FC4383',

  // Custom Omega Adapters
  aaveV3CapitalAdapter: '0x766346f18B7646f6044F88Dfc903D92D9AbF70e1',
  balancerVaultCapitalAdapter: '0xBFB563CB388E4cdB34C2Db3cEfcb35D7Ce48a9DE',
  aaveV3LiquidationAdapter: '0xd145d1eF1cF8F891A5b369D76532ae0fFbF10ce3',

  // RPC Endpoints & Multi-Lane Architecture
  rpcEndpoints: {
    primaryAlchemyHttp: 'https://polygon-mainnet.g.alchemy.com/v2/alch_1ZM_Z5UwNe9UghW0V0czR',
    primaryAlchemyWss: 'wss://polygon-mainnet.g.alchemy.com/v2/alch_1ZM_Z5UwNe9UghW0V0czR',
    drpcLoadBalancedHttp: 'https://lb.drpc.live/polygon/Avauizx6-kfknfhxCHj4Li331ds_f94R8a7RijtBrJVX',
    drpcLoadBalancedWss: 'wss://lb.drpc.live/polygon/Avauizx6-kfknfhxCHj4Li331ds_f94R8a7RijtBrJVX',
    chainstackHttp: 'https://polygon-mainnet.core.chainstack.com/0b8f83de9048afe7f5c60bb78d746daf',
    getBlockHttp: 'https://shared.us-east-1.getblock.io/f6d98a8bece041d5bb38e2c7fdcd475e',
    getBlockWss: 'wss://shared.us-east-1.getblock.io/dcadb5871aac49e6888f20ffc0c43127',
    infuraWritableHttp: 'https://polygon-mainnet.infura.io/v3/ed05b301f1a949f59bfbc1c128910937',
    infuraWritableWss: 'wss://polygon-mainnet.infura.io/ws/v3/ed05b301f1a949f59bfbc1c128910937',
    polygonScanApiKey: 'DPT5XK9NDVMMIXZKRK1JIRYX7ACKU17H91',
    moralisApiKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',
  },

  // Gas Station & FastLane Relayer
  polygonGasStationUrl: 'https://gasstation.polygon.technology/v2',
  flashbotsRelayUrl: 'https://relay-polygon.flashbots.net',
  titanMevUsWest: 'https://us.rpc.titanbuilder.xyz',
};

/** Current POL/USD spot price used for USD-denominated balance display. */
export const POL_PRICE_USD = 0.073;

/**
 * Maximum allowed per-leg accounting residual (ε_allowed) for the off-chain
 * transient storage conservation check.  Any leg whose |ε_j| exceeds this
 * threshold is flagged as TRANSIENT_LEG_ACCOUNTING_MISMATCH.
 * Units: USD
 */
export const TRANSIENT_EPSILON_USD_MAX = 0.01;
