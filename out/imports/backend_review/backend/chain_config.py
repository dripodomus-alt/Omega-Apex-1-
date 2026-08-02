"""
APEX_OMEGA Multi-Chain Configuration
10 EVM chains — each runs isolated single-chain discovery + execution
Cross-DEX only within the same chain. No cross-chain arbitrage.
"""

from typing import Dict, List, Any

# ─────────────────────────────────────────────
#  MASTER CHAIN REGISTRY
# ─────────────────────────────────────────────
CHAINS: Dict[int, Dict[str, Any]] = {

    # ── 1. ETHEREUM ──────────────────────────
    1: {
        "name": "ethereum",
        "display": "Ethereum",
        "chain_id": 1,
        "native_symbol": "ETH",
        "wrapped_native": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "rpc_env_vars": ["ETH_RPC_URL", "ALCHEMY_ETH_HTTP", "INFURA_ETH_HTTP"],
        "public_rpcs": [
            "https://eth.llamarpc.com",
            "https://rpc.ankr.com/eth",
            "https://ethereum.publicnode.com",
        ],
        "block_time_s": 12,

        # Standard DEX factories (V2 / V3)
        "dex_factories": {
            "uniswap_v2":    {"address": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f", "type": 2, "fee_bps": 30},
            "uniswap_v3":    {"address": "0x1F98431c8aD98523631AE4a59f267346ea31F984", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "sushiswap_v2":  {"address": "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac", "type": 2, "fee_bps": 30},
            "sushiswap_v3":  {"address": "0xbACEB8eC6b9355Dfc0269C18bac9d6E2Bdc29C4F", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "pancakeswap_v3":{"address": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865", "type": 3, "fee_tiers": [100, 500, 2500, 10000]},
        },

        # Curve registry
        "curve": {
            "address_provider": "0x0000000022d53366457f9d5e68ec105046fc4383",
            "meta_registry":    "0xF98B45FA17a31b0F647FD4Fa0B5b9BD55ef4F16D",
            "factory_v2":       "0xB9fC157394Af804a3578134A6585C0dc9cc990d4",
            "enabled": True,
        },

        # Balancer
        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        # Token universe
        "tokens": {
            "WETH":  {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
            "WBTC":  {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
            "USDC":  {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
            "USDT":  {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
            "DAI":   {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
            "FRAX":  {"address": "0x853d955aCEf822Db058eb8505911ED77F175b99e", "decimals": 18},
            "LINK":  {"address": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "decimals": 18},
            "UNI":   {"address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "decimals": 18},
            "AAVE":  {"address": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", "decimals": 18},
            "CRV":   {"address": "0xD533a949740bb3306d119CC777fa900bA034cd52", "decimals": 18},
            "BAL":   {"address": "0xba100000625a3754423978a60c9317c58a424e3D", "decimals": 18},
            "LDO":   {"address": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32", "decimals": 18},
            "MKR":   {"address": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2", "decimals": 18},
            "SNX":   {"address": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F", "decimals": 18},
            "stETH": {"address": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84", "decimals": 18},
            "rETH":  {"address": "0xae78736Cd615f374D3085123A210448E74Fc6393", "decimals": 18},
            "LUSD":  {"address": "0x5f98805A4E8be255a32880FDeC7F6728C6568bA0", "decimals": 18},
            "crvUSD":{"address": "0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E", "decimals": 18},
            "SUSHI": {"address": "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2", "decimals": 18},
            "GRT":   {"address": "0xc944E90C64B2c07662A292be6244BDf05Cda44a7", "decimals": 18},
        },
        "priority_pairs": [
            ("WETH", "USDC"), ("WETH", "USDT"), ("WBTC", "WETH"),
            ("USDC", "USDT"), ("DAI", "USDC"), ("stETH", "WETH"),
            ("WETH", "DAI"), ("WBTC", "USDC"),
        ],
    },

    # ── 2. BNB CHAIN ─────────────────────────
    56: {
        "name": "bnb",
        "display": "BNB Chain",
        "chain_id": 56,
        "native_symbol": "BNB",
        "wrapped_native": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "rpc_env_vars": ["BNB_RPC_URL", "BNB_HTTP"],
        "public_rpcs": [
            "https://bsc-dataseed1.binance.org",
            "https://bsc-dataseed.bnbchain.org",
            "https://rpc.ankr.com/bsc",
            "https://bsc.publicnode.com",
        ],
        "block_time_s": 3,

        "dex_factories": {
            "pancakeswap_v2": {"address": "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73", "type": 2, "fee_bps": 25},
            "pancakeswap_v3": {"address": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865", "type": 3, "fee_tiers": [100, 500, 2500, 10000]},
            "biswap":         {"address": "0x858E3312ed3A876947EA49d572A7C42DE08af7EE", "type": 2, "fee_bps": 10},
            "apeswap":        {"address": "0x0841BD0B734E4F5853f0dD8d7Ea041c241fb0Da6", "type": 2, "fee_bps": 20},
            "thena_v1":       {"address": "0xAFD89d21BdB66d00817d4153E055830B1c2B3970", "type": 2, "fee_bps": 20},
            "thena_fusion":   {"address": "0x306F06C147f064A010530292A1EB6737c3e378e4", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        # Curve on BNB (limited deployment)
        "curve": {
            "address_provider": "0x0000000022d53366457f9d5e68ec105046fc4383",
            "meta_registry":    None,
            "factory_v2":       "0xd7E72f3615aa65b92A4DBdC211E296a35512988B",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WBNB":  {"address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "decimals": 18},
            "WETH":  {"address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "decimals": 18},
            "WBTC":  {"address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "decimals": 18},
            "USDT":  {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
            "USDC":  {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
            "BUSD":  {"address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "decimals": 18},
            "DAI":   {"address": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "decimals": 18},
            "CAKE":  {"address": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "decimals": 18},
            "XVS":   {"address": "0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63", "decimals": 18},
            "ALPACA":{"address": "0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F", "decimals": 18},
            "BSGG":  {"address": "0xEe814F5b2bF700D2e843Dc56835D28d095161dd9", "decimals": 18},
            "ADA":   {"address": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47", "decimals": 18},
            "DOT":   {"address": "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402", "decimals": 18},
            "LINK":  {"address": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD", "decimals": 18},
            "UNI":   {"address": "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1", "decimals": 18},
            "ANKR":  {"address": "0xf307910A4c7bbc79691fD374879B36359b8F5792", "decimals": 18},
            "TUSD":  {"address": "0x14016E85a25aeb13065688cAFB43044C2ef86784", "decimals": 18},
            "FRAX":  {"address": "0x90C97F71E18723b0Cf0dfa30ee176Ab653E89F40", "decimals": 18},
        },
        "priority_pairs": [
            ("WBNB", "USDT"), ("WBNB", "USDC"), ("WBNB", "BUSD"),
            ("WETH", "USDT"), ("WBTC", "USDT"), ("USDT", "USDC"),
            ("CAKE", "WBNB"), ("CAKE", "BUSD"),
        ],
    },

    # ── 3. POLYGON ───────────────────────────
    137: {
        "name": "polygon",
        "display": "Polygon",
        "chain_id": 137,
        "native_symbol": "MATIC",
        "wrapped_native": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "rpc_env_vars": [
            "GETBLOCK_HTTP1",
            "ALCHEMY_HTTP_1",
            "ALCHEMY_HTTP_2",
            "PRIVATE_RPC_URL",
            "POLYGON_RPC_URL",
            "POLYGON_HTTP",
            "INFURA_HTTP",
        ],
        "public_rpcs": [
            "https://polygon.drpc.org",
            "https://1rpc.io/matic",
            "https://polygon.llamarpc.com",
            "https://rpc.ankr.com/polygon",
        ],
        "block_time_s": 2,

        "dex_factories": {
            "quickswap_v2":  {"address": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32", "type": 2, "fee_bps": 30},
            "quickswap_v3":  {"address": "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "uniswap_v3":    {"address": "0x1F98431c8aD98523631AE4a59f267346ea31F984", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "sushiswap_v2":  {"address": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4", "type": 2, "fee_bps": 30},
            "sushiswap_v3":  {"address": "0x917933899c6a5F8E37F31E19f92CdBFF7e8FF0e2", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "apeswap":       {"address": "0xCf083Be4164828f00cAE704EC15a36D711491284", "type": 2, "fee_bps": 20},
            "dfyn":          {"address": "0xE7Fb3e833eFE5F9c441105EB65Ef8b261266423B", "type": 2, "fee_bps": 30},
            "retro":         {"address": "0x91e1B99072f238352f59e58de875691e20Dc19c1", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        "curve": {
            "address_provider": "0x094d12e5b541784701FD8d65F11fc0598FBC6332",
            "meta_registry":    "0x4AcE4a534D814539C8ec39a3B76D05c15a787cA1",
            "factory_v2":       "0x722272D36ef0Da72FF51c5A65Db7b870E2e8D4ee",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WMATIC": {"address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
            "WETH":   {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18},
            "WBTC":   {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "decimals": 8},
            "USDC":   {"address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", "decimals": 6},
            "USDCn":  {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
            "USDT":   {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
            "DAI":    {"address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", "decimals": 18},
            "FRAX":   {"address": "0x45c32fA6DF82ead1e2EF74d17b76547EDdFaFF89", "decimals": 18},
            "AAVE":   {"address": "0xD6DF932A45C0f255f85145f286eA0b292B21C90B", "decimals": 18},
            "CRV":    {"address": "0x172370d5Cd63279eFa6d502DAB29171933a610AF", "decimals": 18},
            "BAL":    {"address": "0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3", "decimals": 18},
            "SUSHI":  {"address": "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a", "decimals": 18},
            "LINK":   {"address": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39", "decimals": 18},
            "QUICK":  {"address": "0xB5C064F955D8e7F38fE0460C556a72987494eE17", "decimals": 18},
            "MAI":    {"address": "0xa3Fa99A148fA48D14Ed51d610c367C61876997F1", "decimals": 18},
            "stMATIC":{"address": "0x3A58a54C066FdC0f2D55FC9C89F0415C92eBf3C4", "decimals": 18},
            "MaticX": {"address": "0xfa68FB4628DFF1028CFEc22b4162FCcd0d45efb6", "decimals": 18},
            "GNS":    {"address": "0xE5417Af564e4bFDA1c483642db72007871397896", "decimals": 18},
            "SAND":   {"address": "0xBbba073C31bF03b8ACf7c28EF0738DeCF3695683", "decimals": 18},
            "GHST":   {"address": "0x385Eeac5cB85A38A9a07A70c73e0a3271CfB54A7", "decimals": 18},
        },
        "priority_pairs": [
            ("WMATIC", "USDC"), ("WETH", "USDC"), ("WBTC", "WETH"),
            ("USDC", "USDT"), ("WMATIC", "WETH"), ("DAI", "USDC"),
            ("stMATIC", "WMATIC"), ("MaticX", "WMATIC"),
        ],
    },

    # ── 4. ARBITRUM ──────────────────────────
    42161: {
        "name": "arbitrum",
        "display": "Arbitrum One",
        "chain_id": 42161,
        "native_symbol": "ETH",
        "wrapped_native": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "rpc_env_vars": ["ARB_RPC_URL", "ALCHEMY_ARB_HTTP"],
        "public_rpcs": [
            "https://arb1.arbitrum.io/rpc",
            "https://rpc.ankr.com/arbitrum",
            "https://arbitrum.llamarpc.com",
            "https://arbitrum.publicnode.com",
        ],
        "block_time_s": 0.25,

        "dex_factories": {
            "uniswap_v3":    {"address": "0x1F98431c8aD98523631AE4a59f267346ea31F984", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "sushiswap_v2":  {"address": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4", "type": 2, "fee_bps": 30},
            "sushiswap_v3":  {"address": "0x1af415a1EbA07a4986a52B6f2e7dE7003D82231e", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "camelot_v2":    {"address": "0x6EcCab422D763aC031210895C81787E87B43A652", "type": 2, "fee_bps": 30},
            "camelot_v3":    {"address": "0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35d", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "ramses_v2":     {"address": "0xAAA20D08e59F6561f272015f6aA2D7bD37728b8c", "type": 2, "fee_bps": 30},
            "zyberswap_v3":  {"address": "0x9C2ABD632771b433E5E7507BcaA41cA3b25D8544", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        "curve": {
            "address_provider": "0x0000000022d53366457f9d5e68ec105046fc4383",
            "meta_registry":    "0x445FE580eF8d70FF569aB36e80c647af338db351",
            "factory_v2":       "0xb17b674D9c5CB2e441F8e196a2f048A81355d031",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WETH":   {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
            "WBTC":   {"address": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "decimals": 8},
            "USDC":   {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
            "USDCe":  {"address": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8", "decimals": 6},
            "USDT":   {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
            "DAI":    {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
            "FRAX":   {"address": "0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F", "decimals": 18},
            "ARB":    {"address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "decimals": 18},
            "GMX":    {"address": "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a", "decimals": 18},
            "GLP":    {"address": "0x4277f8F2c384827B5273592FF7CeBd9f2C1ac258", "decimals": 18},
            "LINK":   {"address": "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4", "decimals": 18},
            "UNI":    {"address": "0xFa7F8980b0f1E64A2062791cc3b0871572f1F7f0", "decimals": 18},
            "SUSHI":  {"address": "0xd4d42F0b6DEF4CE0383636770eF773390d85c61A", "decimals": 18},
            "CRV":    {"address": "0x11cDb42B0EB46D95f990BeDD4695A6e3fA034978", "decimals": 18},
            "BAL":    {"address": "0x040d1EdC9569d4Bab2D15287Dc5A4F10F56a56B8", "decimals": 18},
            "AAVE":   {"address": "0xba5DdD1f9d7F570dc94a51479a000E3BCE967196", "decimals": 18},
            "PENDLE": {"address": "0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8", "decimals": 18},
            "MUX":    {"address": "0x8BB2Ac0DCF1E86550534cEE5E168C8b9aA3c88A2", "decimals": 18},
            "GRAIL":  {"address": "0x3d9907F9a368ad0a51Be60f7Da3b97cf940982D8", "decimals": 18},
        },
        "priority_pairs": [
            ("WETH", "USDC"), ("WBTC", "WETH"), ("USDC", "USDT"),
            ("WETH", "USDT"), ("ARB", "WETH"), ("GMX", "WETH"),
            ("WETH", "DAI"), ("WBTC", "USDC"),
        ],
    },

    # ── 5. OPTIMISM ──────────────────────────
    10: {
        "name": "optimism",
        "display": "Optimism",
        "chain_id": 10,
        "native_symbol": "ETH",
        "wrapped_native": "0x4200000000000000000000000000000000000006",
        "rpc_env_vars": ["OP_RPC_URL", "ALCHEMY_OP_HTTP"],
        "public_rpcs": [
            "https://mainnet.optimism.io",
            "https://rpc.ankr.com/optimism",
            "https://optimism.llamarpc.com",
            "https://optimism.publicnode.com",
        ],
        "block_time_s": 2,

        "dex_factories": {
            "uniswap_v3":    {"address": "0x1F98431c8aD98523631AE4a59f267346ea31F984", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "velodrome_v2":  {"address": "0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a", "type": 2, "fee_bps": 30},
            "velodrome_cl":  {"address": "0xCc0bDDB707055e04e497aB22a59c2aF4391cd12F", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "sushiswap_v3":  {"address": "0x9c6522117e2ed1fE5bdb72bb0eD5E3f2bdE7DBe0", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "beethovenx":    {"address": "0xBA12222222228d8Ba445958a75a0704d566BF2C8", "type": 5, "fee_tiers": []},
        },

        "curve": {
            "address_provider": "0x0000000022d53366457f9d5e68ec105046fc4383",
            "meta_registry":    "0x445FE580eF8d70FF569aB36e80c647af338db351",
            "factory_v2":       "0x2db0E83599a91b508Ac268a6197b8B14F5e72840",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WETH":  {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
            "WBTC":  {"address": "0x68f180fcCe6836688e9084f035309E29Bf0A2095", "decimals": 8},
            "USDC":  {"address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
            "USDCe": {"address": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607", "decimals": 6},
            "USDT":  {"address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "decimals": 6},
            "DAI":   {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
            "FRAX":  {"address": "0x2E3D870790dC77A83dd1d18184Acc7439A53f475", "decimals": 18},
            "OP":    {"address": "0x4200000000000000000000000000000000000042", "decimals": 18},
            "VELO":  {"address": "0x9560e827aF36c94D2Ac33a39bCE1Fe78631088Db", "decimals": 18},
            "LINK":  {"address": "0x350a791Bfc2C21F9Ed5d10980Dad2e2638ffa7f6", "decimals": 18},
            "SNX":   {"address": "0x8700dAec35aF8Ff88c16BdF0418774CB3D7599B4", "decimals": 18},
            "sUSD":  {"address": "0x8c6f28f2F1A3C87F0f938b96d27520d9751ec8d9", "decimals": 18},
            "PERP":  {"address": "0x9e1028F5F1D5eDE59748FFceE5532509976840E0", "decimals": 18},
            "LUSD":  {"address": "0xc40F949F8a4e094D1b49a23ea9241D289B7b2819", "decimals": 18},
            "AAVE":  {"address": "0x76FB31fb4af56892A25e32cFC43De717950c9278", "decimals": 18},
            "CRV":   {"address": "0x0994206dfE8De6Ec6920FF4D779B0d950605Fb53", "decimals": 18},
        },
        "priority_pairs": [
            ("WETH", "USDC"), ("WETH", "USDT"), ("WBTC", "WETH"),
            ("OP", "WETH"), ("VELO", "WETH"), ("USDC", "USDT"),
            ("WETH", "DAI"), ("sUSD", "USDC"),
        ],
    },

    # ── 6. BASE ──────────────────────────────
    8453: {
        "name": "base",
        "display": "Base",
        "chain_id": 8453,
        "native_symbol": "ETH",
        "wrapped_native": "0x4200000000000000000000000000000000000006",
        "rpc_env_vars": ["BASE_RPC_URL", "ALCHEMY_BASE_HTTP"],
        "public_rpcs": [
            "https://mainnet.base.org",
            "https://base.llamarpc.com",
            "https://rpc.ankr.com/base",
            "https://base.publicnode.com",
        ],
        "block_time_s": 2,

        "dex_factories": {
            "uniswap_v3":    {"address": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "aerodrome_v2":  {"address": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da", "type": 2, "fee_bps": 30},
            "aerodrome_cl":  {"address": "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "sushiswap_v3":  {"address": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "baseswap_v2":   {"address": "0xFDa619b6d20975be80A10332cD39b9a4b0FAa8BB", "type": 2, "fee_bps": 30},
            "alienbase_v3":  {"address": "0x0Fd83557b2be93617c9C1C1B6fd549401C74558C", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        "curve": {
            "address_provider": "0x5ffe7FB82894076ECB99A30D6A32e969e6e35E98",
            "meta_registry":    None,
            "factory_v2":       "0x3093f9B57A428F3EB6285a589cb35bEA6e78c336",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WETH":  {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
            "USDC":  {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
            "USDbC": {"address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "decimals": 6},
            "DAI":   {"address": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "decimals": 18},
            "USDT":  {"address": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", "decimals": 6},
            "AERO":  {"address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631", "decimals": 18},
            "CBETH": {"address": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22", "decimals": 18},
            "wstETH":{"address": "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452", "decimals": 18},
            "BRETT": {"address": "0x532f27101965dd16442E59d40670FaF5eBB142E4", "decimals": 18},
            "DEGEN": {"address": "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed", "decimals": 18},
            "TOSHI": {"address": "0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4", "decimals": 18},
            "WELL":  {"address": "0xA88594D404727625A9437C3f886C7643872296AE", "decimals": 18},
            "BALD":  {"address": "0x27D2DECb4bFC9C76F0309b8E88dec3a601Fe25a8", "decimals": 18},
            "RDNT":  {"address": "0xd722E55C1d9D9fA0021A5215Cbb904b92B3dC5d4", "decimals": 18},
        },
        "priority_pairs": [
            ("WETH", "USDC"), ("WETH", "USDbC"), ("CBETH", "WETH"),
            ("USDC", "USDbC"), ("AERO", "WETH"), ("wstETH", "WETH"),
            ("WETH", "DAI"),
        ],
    },

    # ── 7. AVALANCHE ─────────────────────────
    43114: {
        "name": "avalanche",
        "display": "Avalanche",
        "chain_id": 43114,
        "native_symbol": "AVAX",
        "wrapped_native": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
        "rpc_env_vars": ["AVAX_RPC_URL", "AVAX_HTTP"],
        "public_rpcs": [
            "https://api.avax.network/ext/bc/C/rpc",
            "https://rpc.ankr.com/avalanche",
            "https://avalanche.llamarpc.com",
            "https://avalanche.publicnode.com",
        ],
        "block_time_s": 2,

        "dex_factories": {
            "traderjoe_v2":  {"address": "0x9Ad6C38BE94206cA50bb0d90783181662f0Cfa10", "type": 2, "fee_bps": 30},
            "traderjoe_v21": {"address": "0x6E77932A92582f504FF6c4BdbCef7Da6c198aEEf", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "pangolin":      {"address": "0xefa94DE7a4656D787667C749f7E1223D71E9FD88", "type": 2, "fee_bps": 30},
            "uniswap_v3":    {"address": "0x740b1c1de25031C31FF4fC9A62f554A55cdC1baD", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "sushiswap_v2":  {"address": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4", "type": 2, "fee_bps": 30},
            "pharaoh_cl":    {"address": "0x420DD381b31aEf6683db6B902084cB0FFECe40Da", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        "curve": {
            "address_provider": "0x0000000022d53366457f9d5e68ec105046fc4383",
            "meta_registry":    "0x8474DdbE98F5aA3179B3B3F5942D724aFcdec9f6",
            "factory_v2":       "0xb17b674D9c5CB2e441F8e196a2f048A81355d031",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WAVAX": {"address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7", "decimals": 18},
            "WETH":  {"address": "0x49D5c2BdFfac6CE2BFdB6640F4F80f226bc10bAB", "decimals": 18},
            "WBTC":  {"address": "0x50b7545627a5162F82A992c33b87aDc75187B218", "decimals": 8},
            "USDC":  {"address": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", "decimals": 6},
            "USDCe": {"address": "0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664", "decimals": 6},
            "USDT":  {"address": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", "decimals": 6},
            "DAI":   {"address": "0xd586E7F844cEa2F87f50152665BCbc2C279D8d70", "decimals": 18},
            "GMX":   {"address": "0x62edc0692BD897D2295872a9FFCac5425011c661", "decimals": 18},
            "JOE":   {"address": "0x6e84a6216eA6dACC71eE8E6b0a5B7322EEbC0fDd", "decimals": 18},
            "PNG":   {"address": "0x60781C2586D68229fde47564546784ab3fACA982", "decimals": 18},
            "QI":    {"address": "0x8729438EB15e2C8B576fCc6AeCdA6A148776C0F5", "decimals": 18},
            "sAVAX": {"address": "0x2b2C81e08f1Af8835a78Bb2A90AE924ACE0eA4bE", "decimals": 18},
            "FRAX":  {"address": "0xD24C2Ad096400B6FBcd2ad8B24E7acBc21A1da64", "decimals": 18},
            "LINK":  {"address": "0x5947BB275c521040051D82396192181b413227A3", "decimals": 18},
            "AAVE":  {"address": "0x63a72806098Bd3D9520cC43356dD78afe5D386D9", "decimals": 18},
        },
        "priority_pairs": [
            ("WAVAX", "USDC"), ("WETH", "USDC"), ("WBTC", "WETH"),
            ("USDC", "USDT"), ("WAVAX", "WETH"), ("GMX", "WAVAX"),
            ("sAVAX", "WAVAX"), ("JOE", "WAVAX"),
        ],
    },

    # ── 8. FANTOM ────────────────────────────
    250: {
        "name": "fantom",
        "display": "Fantom",
        "chain_id": 250,
        "native_symbol": "FTM",
        "wrapped_native": "0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83",
        "rpc_env_vars": ["FTM_RPC_URL", "FTM_HTTP"],
        "public_rpcs": [
            "https://rpc.ftm.tools",
            "https://rpc.ankr.com/fantom",
            "https://fantom.llamarpc.com",
            "https://fantom.publicnode.com",
        ],
        "block_time_s": 1,

        "dex_factories": {
            "spookyswap_v2": {"address": "0x152eE697f2E276fA89E96742e9bB9aB1F2E61bE3", "type": 2, "fee_bps": 20},
            "spookyswap_v3": {"address": "0x7928a2c48754501f3a8064765ECaE541daE5c3E6", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "spiritswap":    {"address": "0xEF45d134b73241eDa7703fa787148D9C9F4950b0", "type": 2, "fee_bps": 30},
            "equalizer":     {"address": "0xc6366EFD0AF1d09171fe0EBF32c7943BB310832a", "type": 2, "fee_bps": 30},
            "equalizer_cl":  {"address": "0x7B18a3f862D0640A7f3c6B7a6Ea20C97DC4a33e5", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        "curve": {
            "address_provider": "0x0000000022d53366457f9d5e68ec105046fc4383",
            "meta_registry":    "0x0f854EA9F38ceA4B1c2FC79047E9D0134419D5d6",
            "factory_v2":       "0x686d67265703D1f124c45E33d47d794c566889Ba",
            "enabled": True,
        },

        "balancer": {
            "vault":   "0x20dd72Ed959b6147912C2e529F0a0C651c33c9ce",
            "queries": "0x81463936C35f62CA97DA3A5A38Cf2F2B0B94d0D7",
            "enabled": True,
        },

        "tokens": {
            "WFTM":  {"address": "0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83", "decimals": 18},
            "WETH":  {"address": "0x74b23882a30290451A17c44f4F05243b6b58C76d", "decimals": 18},
            "WBTC":  {"address": "0x321162Cd933E2Be498Cd2267a90534A804051b11", "decimals": 8},
            "USDC":  {"address": "0x04068DA6C83AFCFA0e13ba15A6696662335D5B75", "decimals": 6},
            "USDT":  {"address": "0x049d68029688eAbF473097a2fC38ef61633A3C7A", "decimals": 6},
            "DAI":   {"address": "0x8D11eC38a3EB5E956B052f67Da8Bdc9bef8Abf3E", "decimals": 18},
            "MIM":   {"address": "0x82f0B8B456c1A451378467398982d4834b6829c1", "decimals": 18},
            "BOO":   {"address": "0x841FAD6EAe12c286d1Fd18d1d525DFfA414Cd3c", "decimals": 18},
            "EQUAL": {"address": "0x3Fd3A0c85B70754eFc07aC9Ac0cbBDce664865A6", "decimals": 18},
            "CRV":   {"address": "0x1E4F97b9f9F913c46F1632781732927B9019C68b", "decimals": 18},
            "LQDR":  {"address": "0x10b620b2dbAC4Faa7D7FFD71Da486f5D44cd86f9", "decimals": 18},
            "FRAX":  {"address": "0xdc301622e621166BD8E82f2cA0A26c13Ad0BE355", "decimals": 18},
            "LINK":  {"address": "0xb3654dc3D10Ea7645f8319668E8F54d2574FBdC8", "decimals": 18},
        },
        "priority_pairs": [
            ("WFTM", "USDC"), ("WETH", "USDC"), ("WBTC", "WETH"),
            ("USDC", "USDT"), ("WFTM", "WETH"), ("BOO", "WFTM"),
            ("EQUAL", "WFTM"), ("MIM", "USDC"),
        ],
    },

    # ── 9. ZKSYNC ERA ────────────────────────
    324: {
        "name": "zksync",
        "display": "zkSync Era",
        "chain_id": 324,
        "native_symbol": "ETH",
        "wrapped_native": "0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91",
        "rpc_env_vars": ["ZKSYNC_RPC_URL"],
        "public_rpcs": [
            "https://mainnet.era.zksync.io",
            "https://rpc.ankr.com/zksync_era",
            "https://zksync.llamarpc.com",
            "https://zksync.publicnode.com",
        ],
        "block_time_s": 1,

        "dex_factories": {
            "syncswap_classic":   {"address": "0xf2DAd89f2788a8CD54625C60b55cD3d2D0ACa7Cb", "type": 2, "fee_bps": 30},
            "syncswap_stable":    {"address": "0x5b9f21d407F35b10CbfDDca17D5D84b129356ea3", "type": 2, "fee_bps": 1},
            "mute_io":            {"address": "0x40be1cBa6C5B47cDF9da7f963B6F761F4C60627D", "type": 2, "fee_bps": 30},
            "spacefi":            {"address": "0x78b3C724A2F663D11373C4a1978689271895256f", "type": 2, "fee_bps": 30},
            "zkswap_v3":          {"address": "0x3A44A3b263FB631cdbf25f339e2D29497511A81F", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "pancakeswap_v3":     {"address": "0x1BB72E0CbbEA93c08f535fc7856E0338D7F7a8aB", "type": 3, "fee_tiers": [100, 500, 2500, 10000]},
        },

        # Curve not deployed on zkSync Era mainnet
        "curve": {
            "enabled": False,
        },

        # Balancer uses different vault on zkSync
        "balancer": {
            "vault":   "0xBA1333333333a1BA1108E8412f11850A5C319bA9",
            "queries": None,
            "enabled": True,
        },

        "tokens": {
            "WETH":  {"address": "0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91", "decimals": 18},
            "USDC":  {"address": "0x3355df6D4c9C3035724Fd0e3914dE96A5a83aaf4", "decimals": 6},
            "USDT":  {"address": "0x493257fD37EDB34451f62EDf8D2a0C418852bA4C", "decimals": 6},
            "WBTC":  {"address": "0xBBeB516fb02a01611cBBE0453Fe3c580D7281011", "decimals": 8},
            "DAI":   {"address": "0x4B9eb6c0b6ea15176BBF62841C6B2A8a398cb656", "decimals": 18},
            "MUTE":  {"address": "0x0e97C7a0F8B2C9885C8ac9fC6136e829CbC21d42", "decimals": 18},
            "SPACE": {"address": "0x47260090cE5e83454d5f05A0AbbB2C953835f777", "decimals": 18},
            "LUSD":  {"address": "0x503234F203fC7Eb888b97BD30E0e35f8F8FBe20B", "decimals": 18},
            "FRAX":  {"address": "0x000000000000000000000000000000000000800A", "decimals": 18},
            "ZK":    {"address": "0x5A7d6b2F92C77FAD6CCaBd7EE0624E64907Eaf3E", "decimals": 18},
        },
        "priority_pairs": [
            ("WETH", "USDC"), ("WETH", "USDT"), ("WBTC", "WETH"),
            ("USDC", "USDT"), ("WETH", "DAI"),
        ],
    },

    # ── 10. LINEA ────────────────────────────
    59144: {
        "name": "linea",
        "display": "Linea",
        "chain_id": 59144,
        "native_symbol": "ETH",
        "wrapped_native": "0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f",
        "rpc_env_vars": ["LINEA_RPC_URL"],
        "public_rpcs": [
            "https://rpc.linea.build",
            "https://linea.drpc.org",
            "https://linea.decubate.com",
            "https://rpc.ankr.com/linea",
        ],
        "block_time_s": 2,

        "dex_factories": {
            "nile_v1":        {"address": "0xAAA16c016BF556fcD620328f0759252E29b2AB5E", "type": 2, "fee_bps": 30},
            "nile_cl":        {"address": "0xAAA78E8C4241990B4ce159E105dA08129345946A", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
            "linehub_v2":     {"address": "0x7f4e8427c1D29e09f4A3C59e18D6dbd96C04Ffb4", "type": 2, "fee_bps": 30},
            "pancakeswap_v3": {"address": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865", "type": 3, "fee_tiers": [100, 500, 2500, 10000]},
            "velocore_v2":    {"address": "0x85D84c774CF8e9fF85342684b0E795Df72A24908", "type": 2, "fee_bps": 30},
            "lynex_v1":       {"address": "0xBc7695Fd006E85be101a824e50ab20361e995962", "type": 2, "fee_bps": 30},
            "lynex_cl":       {"address": "0x622b2c98123D21650cB49f4863E324e56ae223F7", "type": 3, "fee_tiers": [100, 500, 3000, 10000]},
        },

        # Curve not yet widely deployed on Linea
        "curve": {
            "address_provider": "0x5ffe7FB82894076ECB99A30D6A32e969e6e35E98",
            "meta_registry":    None,
            "factory_v2":       None,
            "enabled": False,
        },

        "balancer": {
            "vault":   "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
            "queries": "0xE39B5e3B6D74016b2F6A9673D7d7493B6DF549d6",
            "enabled": True,
        },

        "tokens": {
            "WETH":   {"address": "0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f", "decimals": 18},
            "USDC":   {"address": "0x176211869cA2b568f2A7D4EE941E073a821EE1ff", "decimals": 6},
            "USDT":   {"address": "0xA219439258ca9da29E9Cc4cE5596924745e12B93", "decimals": 6},
            "DAI":    {"address": "0x4AF15ec2A0BD43Db75dd04E62FAA3B8EF36b00d5", "decimals": 18},
            "WBTC":   {"address": "0x3aAB2285ddcDdaD8edf438C1bAB47e1a9D05a9b4", "decimals": 8},
            "NILE":   {"address": "0xAAAac83751090C6ea42379626435f805DDF54DC8", "decimals": 18},
            "LVC":    {"address": "0xcc22F6AA610D1b2a0e89EF228079cB3e1831b1D1", "decimals": 18},
            "MATIC":  {"address": "0x265B25e22bcd7f10a5bD6E6410F10537Cc7567e8", "decimals": 18},
            "BUSD":   {"address": "0x7d43AABC515C356145049227CeE54B608342B0a8", "decimals": 18},
            "LYNX":   {"address": "0x1a51b19CE03dbE0Cb44C1528E34a7EDD7771E9Af", "decimals": 18},
        },
        "priority_pairs": [
            ("WETH", "USDC"), ("WETH", "USDT"), ("WBTC", "WETH"),
            ("USDC", "USDT"), ("WETH", "DAI"),
        ],
    },
}


# ─────────────────────────────────────────────
#  Helper functions
# ─────────────────────────────────────────────

def get_chain(chain_id: int) -> Dict[str, Any]:
    if chain_id not in CHAINS:
        raise ValueError(f"Chain {chain_id} not configured. Available: {list(CHAINS.keys())}")
    return CHAINS[chain_id]


def get_all_chain_ids() -> List[int]:
    return list(CHAINS.keys())


def get_chain_token_addresses(chain_id: int) -> List[str]:
    cfg = get_chain(chain_id)
    return [t["address"] for t in cfg["tokens"].values()]


def get_chain_token_info(chain_id: int, address: str) -> Dict:
    cfg = get_chain(chain_id)
    addr_lower = address.lower()
    for symbol, info in cfg["tokens"].items():
        if info["address"].lower() == addr_lower:
            return {"symbol": symbol, **info}
    return {}


def get_rpc_url(chain_id: int) -> str:
    """Return first available RPC URL for this chain from env vars or public list."""
    import os
    cfg = get_chain(chain_id)
    for var in cfg.get("rpc_env_vars", []):
        url = os.getenv(var, "").strip()
        if url and "YOUR_API_KEY" not in url:
            return url
    fallbacks = cfg.get("public_rpcs", [])
    if fallbacks:
        return fallbacks[0]
    raise RuntimeError(f"No RPC configured for chain {chain_id}")


CHAIN_NAMES = {cid: cfg["name"] for cid, cfg in CHAINS.items()}
ENABLED_CHAINS = get_all_chain_ids()
