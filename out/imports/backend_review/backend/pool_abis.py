"""
ABIs for Web3 Pool Data Fetching
UniswapV2, UniswapV3, and Balancer Vault
"""

# UniswapV2 Pair ABI - getReserves, token0, token1, fee
UNISWAP_V2_PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# UniswapV3 Pool ABI - slot0, liquidity, token0, token1, fee
UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "tickSpacing",
        "outputs": [{"internalType": "int24", "name": "", "type": "int24"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Balancer V2 Vault ABI - getPoolTokens
BALANCER_VAULT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "poolId", "type": "bytes32"}],
        "name": "getPoolTokens",
        "outputs": [
            {"internalType": "address[]", "name": "tokens", "type": "address[]"},
            {"internalType": "uint256[]", "name": "balances", "type": "uint256[]"},
            {"internalType": "uint256", "name": "lastChangeBlock", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Balancer V2 Pool ABI - getPoolId, getNormalizedWeights
BALANCER_POOL_ABI = [
    {
        "inputs": [],
        "name": "getPoolId",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getNormalizedWeights",
        "outputs": [{"internalType": "uint256[]", "name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getSwapFeePercentage",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 ABI for decimals
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Balancer Vault Address on Polygon
BALANCER_VAULT_ADDRESS = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
