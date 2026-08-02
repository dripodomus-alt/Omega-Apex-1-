"""
Polygon Token Universe - 32 Most Important Tokens
Includes native, bridge, wrapped, and pegged tokens
"""

# 32-Token Universe on Polygon
POLYGON_TOKEN_UNIVERSE = {
    # Native & Wrapped
    "WMATIC": {
        "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "decimals": 18,
        "type": "wrapped_native"
    },
    "MATIC": {
        "address": "0x0000000000000000000000000000000000001010",  # Native MATIC
        "decimals": 18,
        "type": "native"
    },
    
    # Major Wrapped Assets
    "WETH": {
        "address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "decimals": 18,
        "type": "bridge_wrapped"
    },
    "WBTC": {
        "address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "decimals": 8,
        "type": "bridge_wrapped"
    },
    
    # Stablecoins - USD Pegged
    "USDC": {
        "address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # Bridged USDC.e
        "decimals": 6,
        "type": "stablecoin_bridge"
    },
    "USDC.e": {
        "address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "decimals": 6,
        "type": "stablecoin_bridge"
    },
    "USDT": {
        "address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "decimals": 6,
        "type": "stablecoin_bridge"
    },
    "DAI": {
        "address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "decimals": 18,
        "type": "stablecoin_bridge"
    },
    "USDD": {
        "address": "0xFFA4D863C96e743A2e1513824EA006B8D0353C57",
        "decimals": 18,
        "type": "stablecoin"
    },
    "TUSD": {
        "address": "0x2e1AD108fF1D8C782fcBbB89AAd783aC49586756",
        "decimals": 18,
        "type": "stablecoin"
    },
    "FRAX": {
        "address": "0x45c32fA6DF82ead1e2EF74d17b76547EDdFaFF89",
        "decimals": 18,
        "type": "stablecoin"
    },
    "MAI": {
        "address": "0xa3Fa99A148fA48D14Ed51d610c367C61876997F1",
        "decimals": 18,
        "type": "stablecoin_native"
    },
    
    # DeFi Blue Chips
    "AAVE": {
        "address": "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
        "decimals": 18,
        "type": "defi"
    },
    "CRV": {
        "address": "0x172370d5Cd63279eFa6d502DAB29171933a610AF",
        "decimals": 18,
        "type": "defi"
    },
    "SUSHI": {
        "address": "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",
        "decimals": 18,
        "type": "defi"
    },
    "BAL": {
        "address": "0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3",
        "decimals": 18,
        "type": "defi"
    },
    "QUICK": {
        "address": "0x831753DD7087CaC61aB5644b308642cc1c33Dc13",
        "decimals": 18,
        "type": "defi_native"
    },
    
    # Layer 1 Bridges
    "LINK": {
        "address": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
        "decimals": 18,
        "type": "bridge"
    },
    "UNI": {
        "address": "0xb33EaAd8d922B1083446DC23f610c2567fB5180f",
        "decimals": 18,
        "type": "bridge"
    },
    "GRT": {
        "address": "0x5fe2B58c13d5388fE21e21B7f15D0e3b7f4c2A0e",
        "decimals": 18,
        "type": "bridge"
    },
    "SNX": {
        "address": "0x50B728D8D964fd00C2d0AAD81718b71311feF68a",
        "decimals": 18,
        "type": "bridge"
    },
    
    # Gaming & Metaverse
    "SAND": {
        "address": "0xBbba073C31bF03b8ACf7c28EF0738DeCF3695683",
        "decimals": 18,
        "type": "gaming"
    },
    "MANA": {
        "address": "0xA1c57f48F0Deb89f569dFbE6E2B7f46D33606fD4",
        "decimals": 18,
        "type": "gaming"
    },
    "GHST": {
        "address": "0x385Eeac5cB85A38A9a07A70c73e0a3271CfB54A7",
        "decimals": 18,
        "type": "gaming_native"
    },
    
    # Liquid Staking Derivatives
    "stMATIC": {
        "address": "0x3A58a54C066FdC0f2D55FC9C89F0415C92eBf3C4",
        "decimals": 18,
        "type": "liquid_staking"
    },
    "MaticX": {
        "address": "0xfa68FB4628DFF1028CFEc22b4162FCcd0d45efb6",
        "decimals": 18,
        "type": "liquid_staking"
    },
    
    # Alternative L1 Bridges
    "AVAX": {
        "address": "0x2C89bbc92BD86F8075d1DEcc58C7F4E0107f286b",
        "decimals": 18,
        "type": "bridge"
    },
    "BNB": {
        "address": "0x3BA4c387f786bFEE076A58914F5Bd38d668B42c3",
        "decimals": 18,
        "type": "bridge"
    },
    
    # Yield-bearing stablecoins
    "agEUR": {
        "address": "0xE0B52e49357Fd4DAf2c15e02058DCE6BC0057db4",
        "decimals": 18,
        "type": "stablecoin_euro"
    },
    
    # Polygon Native Projects
    "RNDR": {
        "address": "0x61299774020dA444Af134c82fa83E3810b309991",
        "decimals": 18,
        "type": "polygon_native"
    },
    
    # Bridged Bitcoin variants
    "renBTC": {
        "address": "0xDBf31dF14B66535aF65AaC99C32e9eA844e14501",
        "decimals": 8,
        "type": "bridge_wrapped"
    },
    
    # Additional important tokens to reach 32
    "FXS": {
        "address": "0x1a3acf6D19267E2d3e7f898f42803e90C9219062",
        "decimals": 18,
        "type": "defi"
    },
    "ANKR": {
        "address": "0x101A023270368c0D50BFfb62780F4aFd4ea79C35",
        "decimals": 18,
        "type": "defi"
    }
}

# Get list of token addresses for pool scanning
def get_token_addresses():
    """Return list of all token addresses"""
    return [token["address"] for token in POLYGON_TOKEN_UNIVERSE.values()]

# Get token info by address
def get_token_info(address: str):
    """Get token info by address"""
    address_lower = address.lower()
    for symbol, info in POLYGON_TOKEN_UNIVERSE.items():
        if info["address"].lower() == address_lower:
            return {"symbol": symbol, **info}
    return None

# Get tokens by type
def get_tokens_by_type(token_type: str):
    """Get all tokens of a specific type"""
    return {
        symbol: info 
        for symbol, info in POLYGON_TOKEN_UNIVERSE.items() 
        if info["type"] == token_type
    }

# Common trading pairs (for prioritization)
PRIORITY_PAIRS = [
    ("WMATIC", "USDC"),
    ("WETH", "USDC"),
    ("WBTC", "WETH"),
    ("USDC", "USDT"),
    ("WMATIC", "WETH"),
    ("DAI", "USDC"),
    ("LINK", "WETH"),
    ("AAVE", "WETH"),
    ("MATIC", "USDC"),
    ("stMATIC", "WMATIC"),
]
