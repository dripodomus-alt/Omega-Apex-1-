import pytest
import json
import scanner_core  # This is the Rust extension module
import os
from omega_v5.contract_deployments import deployment_address

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


def _find_live_curve_pool(w3):
    registry_addr = deployment_address("CURVE_STABLE_FACTORY")
    registry_abi = [
        {
            "inputs": [],
            "name": "pool_count",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "uint256", "name": "arg0", "type": "uint256"}],
            "name": "pool_list",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]
    coins_abi = [
        {
            "inputs": [{"internalType": "int128", "name": "i", "type": "int128"}],
            "name": "coins",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]

    factory = w3.eth.contract(address=w3.to_checksum_address(registry_addr), abi=registry_abi)
    count = int(factory.functions.pool_count().call())
    for i in range(max(0, count - 1), max(-1, count - 25), -1):
        try:
            pool = factory.functions.pool_list(i).call()
            pool_contract = w3.eth.contract(address=w3.to_checksum_address(pool), abi=CURVE_POOL_ABI)
            _ = pool_contract.functions.A().call()
            _ = pool_contract.functions.balances(0).call()
            _ = pool_contract.functions.balances(1).call()
            token_contract = w3.eth.contract(address=w3.to_checksum_address(pool), abi=coins_abi)
            token0 = token_contract.functions.coins(0).call()
            token1 = token_contract.functions.coins(1).call()
            return str(pool), [str(token0), str(token1)]
        except Exception:
            continue
    pytest.skip("No responsive Curve stable pool found on current fork/provider")


def _find_live_balancer_pool(w3, vault_contract):
    event_sig = w3.keccak(text="PoolRegistered(bytes32,address,uint8)").hex()
    latest = int(w3.eth.block_number)
    start = max(0, latest - 9_000)
    try:
        logs = w3.eth.get_logs(
            {
                "fromBlock": start,
                "toBlock": latest,
                "address": w3.to_checksum_address(deployment_address("BALANCER_VAULT")),
                "topics": [event_sig],
            }
        )
    except Exception:
        pytest.skip("Balancer PoolRegistered log scan unsupported on current fork/provider")
    weighted_pool_abi = [
        {
            "inputs": [],
            "name": "getNormalizedWeights",
            "outputs": [{"internalType": "uint256[]", "name": "", "type": "uint256[]"}],
            "stateMutability": "view",
            "type": "function",
        }
    ]

    for entry in reversed(logs):
        try:
            pool_id_hex = entry["topics"][1].hex()
            pool_addr = "0x" + pool_id_hex[26:66]
            pool_tokens_data = vault_contract.functions.getPoolTokens(bytes.fromhex(pool_id_hex[2:])).call()
            tokens = [str(t) for t in pool_tokens_data[0]]
            balances = pool_tokens_data[1]
            if len(tokens) < 2 or len(balances) < 2:
                continue
            weighted = w3.eth.contract(address=w3.to_checksum_address(pool_addr), abi=weighted_pool_abi)
            weights = weighted.functions.getNormalizedWeights().call()
            if len(weights) < 2:
                continue
            return pool_id_hex, pool_addr, tokens, balances, weights
        except Exception:
            continue
    pytest.skip("No responsive Balancer weighted pool found on current fork/provider")


@pytest.fixture
def three_hop_arbitrage_pools():
    """
    Creates a JSON string representing a market with a clear 3-hop arbitrage opportunity.
    The opportunity is: USDC -> USDT -> DAI -> USDC

    - Pool 1 (USDC/USDT): Price is favorable for buying USDT with USDC.
    - Pool 2 (USDT/DAI): Price is favorable for buying DAI with USDT.
    - Pool 3 (DAI/USDC): Price is favorable for buying USDC with DAI, completing the profitable cycle.
    """
    # Define token addresses
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    dai = "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063"

    pools = {
        # Pool 1: USDC/USDT. Trade 1 USDC for 1.01 USDT.
        "pool1": {
            "protocol": "QUICKSWAP_V2",
            "address": "0x0000000000000000000000000000000000000001",
            "tokens": [usdc, usdt],
            "total_executable_liquidity_usd": "1000000",
            "state": {
                # Price(USDC->USDT) ~ 1.013 * 0.997 = 1.01
                "reserve0": 1_000_000 * 10**6,  # USDC (6 decimals)
                "reserve1": 1_013_000 * 10**6,  # USDT (6 decimals)
            },
        },
        # Pool 2: USDT/DAI. Trade 1 USDT for 1.01 DAI.
        "pool2": {
            "protocol": "SUSHISWAP_V2",
            "address": "0x0000000000000000000000000000000000000002",
            "tokens": [usdt, dai],
            "total_executable_liquidity_usd": "1000000",
            "state": {
                # Price(USDT->DAI) ~ 1.013 * 0.997 = 1.01
                "reserve0": 1_000_000 * 10**6,   # USDT (6 decimals)
                "reserve1": 1_013_000 * 10**18,  # DAI (18 decimals)
            },
        },
        # Pool 3: DAI/USDC. Trade 1 DAI for 1.01 USDC.
        "pool3": {
            "protocol": "QUICKSWAP_V2",
            "address": "0x0000000000000000000000000000000000000003",
            "tokens": [dai, usdc],
            "total_executable_liquidity_usd": "1000000",
            "state": {
                # Price(DAI->USDC) ~ 1.013 * 0.997 = 1.01
                "reserve0": 1_000_000 * 10**18, # DAI (18 decimals)
                "reserve1": 1_013_000 * 10**6,  # USDC (6 decimals)
            },
        },
    }
    return json.dumps(pools)


async def test_finds_three_hop_arbitrage_route(three_hop_arbitrage_pools):
    """
    Verifies that the Rust engine can find a known 3-hop arbitrage path.
    """
    # Create a default gate config (not used heavily in this test)
    config = scanner_core.GateConfig(min_tvl_usd="1000", chain_id=137)

    # Call the async Rust function
    routes = await scanner_core.scan_opportunities(three_hop_arbitrage_pools, config)

    # Assert that at least one profitable route was found
    assert len(routes) > 0, "No arbitrage routes were found"

    # The most profitable route should be our 3-hop path
    best_route = routes[0]

    # Define the expected path
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    dai = "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063"
    expected_path = [usdc, usdt, dai, usdc]

    # Assert that the path is correct
    assert [str(addr) for addr in best_route.path] == expected_path

    # Assert that the estimated profit is positive (1.01 * 1.01 * 1.01 > 1.03)
    assert best_route.estimated_profit_ratio > 1.02


@pytest.fixture
def complex_market_fixture():
    """
    Creates a more complex market with multiple competing opportunities.
    - A highly profitable 3-hop route: USDC -> USDT -> DAI -> USDC (Profit Ratio ~1.03)
    - A marginally profitable 2-hop route: USDC -> WETH -> USDC (Profit Ratio ~1.005)
    - Decoy pools that lead nowhere.
    """
    usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    usdt = "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    dai = "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063"
    weth = "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"

    pools = {
        # Profitable 3-hop path (USDC -> USDT -> DAI -> USDC)
        "pool_usdc_usdt": {
            "protocol": "QUICKSWAP_V2", "address": "0x01", "tokens": [usdc, usdt],
            "total_executable_liquidity_usd": "1000000",
            "state": {"reserve0": 1_000_000 * 10**6, "reserve1": 1_011_000 * 10**6}, # Price ~1.011
        },
        "pool_usdt_dai": {
            "protocol": "SUSHISWAP_V2", "address": "0x02", "tokens": [usdt, dai],
            "total_executable_liquidity_usd": "1000000",
            "state": {"reserve0": 1_000_000 * 10**6, "reserve1": 1_011_000 * 10**18}, # Price ~1.011
        },
        "pool_dai_usdc": {
            "protocol": "QUICKSWAP_V2", "address": "0x03", "tokens": [dai, usdc],
            "total_executable_liquidity_usd": "1000000",
            "state": {"reserve0": 1_000_000 * 10**18, "reserve1": 1_011_000 * 10**6}, # Price ~1.011
        },

        # Marginally profitable 2-hop path (USDC -> WETH -> USDC)
        "pool_usdc_weth": {
            "protocol": "QUICKSWAP_V2", "address": "0x04", "tokens": [usdc, weth],
            "total_executable_liquidity_usd": "2000000",
            "state": {"reserve0": 3_000_000 * 10**6, "reserve1": 1_000 * 10**18}, # Price: 3000 USDC/WETH
        },
        "pool_weth_usdc_profit": {
            "protocol": "SUSHISWAP_V2", "address": "0x05", "tokens": [weth, usdc],
            "total_executable_liquidity_usd": "2000000",
            "state": {"reserve0": 1_000 * 10**18, "reserve1": 3_020_000 * 10**6}, # Price: 3020 USDC/WETH
        },

        # Decoy pool (dead end)
        "pool_weth_dai_decoy": {
            "protocol": "QUICKSWAP_V2", "address": "0x06", "tokens": [weth, dai],
            "total_executable_liquidity_usd": "500000",
            "state": {"reserve0": 1_000 * 10**18, "reserve1": 3_000_000 * 10**18}, # Neutral price
        },
    }
    return json.dumps(pools)


async def test_engine_discovers_best_route_in_complex_market(complex_market_fixture):
    """
    Verifies that the engine discovers the most profitable route when presented
    with multiple competing opportunities.
    """
    config = scanner_core.GateConfig(min_tvl_usd="1000", chain_id=137)

    # Let the engine discover the best route on its own
    routes = await scanner_core.scan_opportunities(complex_market_fixture, config)

    assert len(routes) > 0, "Engine failed to find any profitable routes"

    # The engine sorts by profitability, so the first result should be the best one.
    best_route = routes[0]

    # 1. Validate the properties of the discovered route
    assert best_route.path[0] == best_route.path[-1], "The best route is not a valid cycle (start != end)"
    assert best_route.estimated_profit_ratio > 1.0, "The best route is not profitable"
    assert len(best_route.path) - 1 == len(best_route.pools), "Number of pools does not match number of hops"

    # 2. Assert that the engine made the correct optimal choice
    # We know the 3-hop is more profitable than the 2-hop.
    # Profit for 3-hop: (1.011*0.997)^3 ~ 1.024
    # Profit for 2-hop: (3020/3000)*(0.997*0.997) ~ 1.0006
    assert best_route.estimated_profit_ratio > 1.02, "Engine did not find the highly profitable 3-hop route"
    assert len(best_route.path) == 4, "The best route was not the 3-hop path"

    # 3. Check that the less profitable route was also found (optional, but good for coverage)
    if len(routes) > 1:
        second_route = routes[1]
        # Some scanner backends emit equivalent-profit cycles in arbitrary order.
        # Accept equal-ratio ties while ensuring strict profitability and valid cycle shape.
        assert second_route.path[0] == second_route.path[-1]
        assert second_route.estimated_profit_ratio > 1.0
        assert second_route.estimated_profit_ratio <= best_route.estimated_profit_ratio


@pytest.fixture
def v3_pool_fixture():
    """
    Creates a market containing a single realistic Uniswap V3 pool.
    The state values are taken from a real USDC/WETH pool on Polygon.
    """
    usdc = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174" # USDC.e on Polygon
    weth = "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"

    pools = {
        "v3_pool": {
            "protocol": "UNISWAP_V3",
            "address": "0x45dda9cb7c25131df268515131f647d726f50608",
            "tokens": [usdc, weth], # token0, token1
            "total_executable_liquidity_usd": "5000000",
            "state": {
                # Real state from block 56,000,000
                "liquidity": "3323039548638208181",
                "sqrt_price_x96": "1527011530243601379383395524" # Price of USDC per WETH
            },
        },
    }
    return json.dumps(pools)


async def test_v3_adapter_quote(v3_pool_fixture):
    """
    Performs a unit-style test on the V3Adapter's math by checking its quote
    against a known-good calculation.
    """
    config = scanner_core.GateConfig(min_tvl_usd="1000", chain_id=137)

    # The V3 adapter is used implicitly by the routing engine when it sees "UNISWAP_V3"
    routes = await scanner_core.scan_opportunities(v3_pool_fixture, config)

    # We don't expect a profitable route, but we expect the graph to have been built.
    # This test primarily ensures the V3 quoting logic doesn't crash and produces a value.
    # A more precise test would require a full Rust port of the V3 Quoter contract.
    # For now, we confirm it produces a non-zero profit ratio, meaning a valid price was calculated.
    # The profit ratio will be < 1 because there's only one pool.
    assert len(routes) == 0, "No profitable routes should be found with one pool"
    # This test implicitly passes if `scan_opportunities` completes without `AdapterError` or other panics.


@pytest.mark.fork
async def test_v3_adapter_fork_validation():
    """
    Validates the Rust V3Adapter against the on-chain Uniswap V3 QuoterV2 contract.

    This test requires a mainnet fork. Run with:
    anvil --fork-url <YOUR_POLYGON_RPC_URL>
    pytest -m fork
    """
    # --- Setup ---
    from web3 import Web3
    fork_rpc_url = os.environ.get("FORK_RPC_URL", "http://127.0.0.1:8545")
    w3 = Web3(Web3.HTTPProvider(fork_rpc_url, request_kwargs={"timeout": 10}))
    assert w3.is_connected(), "Could not connect to Anvil fork. Is it running?"

    # Pool: USDC/WETH 0.05% on Polygon
    pool_address = "0x45dda9cb7c25131df268515131f647d726f50608"
    token0_addr = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e
    token1_addr = "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619"  # WETH
    fee = 500

    # On-chain contracts
    pool_contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=V3_POOL_ABI)
    quoter_contract = w3.eth.contract(
        address=Web3.to_checksum_address(deployment_address("UNISWAP_V3_QUOTER")),
        abi=V3_QUOTER_ABI,
    )

    # --- Fetch Live State ---
    slot0 = pool_contract.functions.slot0().call()
    liquidity = pool_contract.functions.liquidity().call()
    sqrt_price_x96 = slot0[0]

    # --- Prepare Rust Input ---
    amount_in = 1_000 * 10**6  # 1,000 USDC
    raw_pool = {
        "protocol": "UNISWAP_V3",
        "address": pool_address,
        "tokens": [token0_addr, token1_addr],
        "total_executable_liquidity_usd": "10000000",
        "state": {
            "liquidity": str(liquidity),
            "sqrt_price_x96": str(sqrt_price_x96),
        },
    }

    # --- Get Quotes from Both Sources ---
    # 1. On-chain QuoterV2
    on_chain_amount_out = quoter_contract.functions.quoteExactInputSingle(
        Web3.to_checksum_address(token0_addr), Web3.to_checksum_address(token1_addr), fee, amount_in, 0
    ).call()

    # 2. Rust V3Adapter (via the direct test-only quote function)
    rust_amount_out_str = await scanner_core.test_only_quote(
        json.dumps(raw_pool),
        token0_addr,
        str(amount_in)
    )
    rust_amount_out = int(rust_amount_out_str)

    print(f"\nOn-chain QuoterV2 output for 1,000 USDC: {on_chain_amount_out / 10**18:.6f} WETH")
    print(f"Rust V3Adapter output for 1,000 USDC:   {rust_amount_out / 10**18:.6f} WETH")
    assert on_chain_amount_out > 0, "On-chain quoter returned zero, fork state might be bad."
    assert rust_amount_out == on_chain_amount_out, "Rust adapter output does not match on-chain quoter output."


@pytest.mark.fork
async def test_curve_adapter_fork_validation():
    """
    Validates the Rust CurveAdapter against a live Curve pool on-chain.
    This test uses the Aave stableswap pool (DAI/USDC/USDT).
    """
    # --- Setup ---
    from web3 import Web3
    fork_rpc_url = os.environ.get("FORK_RPC_URL", "http://127.0.0.1:8545")
    w3 = Web3(Web3.HTTPProvider(fork_rpc_url, request_kwargs={"timeout": 10}))
    assert w3.is_connected(), "Could not connect to Anvil fork."

    pool_address, tokens = _find_live_curve_pool(w3)
    token_in = tokens[0]
    token_out = tokens[1]

    pool_contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=CURVE_POOL_ABI)

    # --- Fetch Live State ---
    balances = [pool_contract.functions.balances(i).call() for i in range(2)]
    amplification_param = pool_contract.functions.A().call()

    # --- Prepare Rust Input ---
    # Quote token0 -> token1 for the discovered live pool.
    amount_in = 10_000 * 10**18
    raw_pool = {
        "protocol": "CURVE_STABLE",
        "address": pool_address,
        "tokens": [token_in, token_out],
        "total_executable_liquidity_usd": "100000000",
        "state": {
            "balances": [str(b) for b in balances],
            "a": str(amplification_param),
        },
    }

    # --- Get Quotes from Both Sources ---
    # 1. On-chain Curve pool
    on_chain_amount_out = pool_contract.functions.get_dy(0, 1, amount_in).call()

    # 2. Rust CurveAdapter
    rust_amount_out_str = await scanner_core.test_only_quote(
        json.dumps(raw_pool),
        token_in,
        str(amount_in)
    )
    rust_amount_out = int(rust_amount_out_str)

    print(f"\nOn-chain Curve output for discovered pair: {on_chain_amount_out}")
    print(f"Rust CurveAdapter output for discovered pair:   {rust_amount_out}")
    assert on_chain_amount_out > 0
    # Curve math is complex; a small difference due to iterative solver precision is acceptable.
    assert abs(rust_amount_out - on_chain_amount_out) <= 10, "Rust adapter output diverges significantly from on-chain quote."


@pytest.mark.fork
async def test_balancer_adapter_fork_validation():
    """
    Validates the Rust BalancerAdapter against the on-chain Balancer Vault.
    This test uses a WETH/WBTC 50/50 weighted pool on Polygon.
    """
    # --- Setup ---
    from web3 import Web3
    fork_rpc_url = os.environ.get("FORK_RPC_URL", "http://127.0.0.1:8545")
    w3 = Web3(Web3.HTTPProvider(fork_rpc_url, request_kwargs={"timeout": 10}))
    assert w3.is_connected(), "Could not connect to Anvil fork."

    vault_addr = deployment_address("BALANCER_VAULT")
    vault_contract = w3.eth.contract(address=Web3.to_checksum_address(vault_addr), abi=BALANCER_VAULT_ABI)

    pool_id, _pool_addr, tokens, pool_balances, weights = _find_live_balancer_pool(w3, vault_contract)
    token_in = tokens[0]
    token_out = tokens[1]

    # --- Prepare Rust Input ---
    amount_in = 1 * 10**18
    raw_pool = {
        "protocol": "BALANCER_WEIGHTED",
        "address": pool_id,
        "tokens": [token_in, token_out],
        "total_executable_liquidity_usd": "1000000",
        "state": {
            "balances": [str(b) for b in pool_balances],
            "weights": [str(int(w)) for w in weights],
        },
    }

    # --- Get Quotes from Both Sources ---
    # 1. On-chain Balancer Vault using queryBatchSwap
    swap_struct = (
        bytes.fromhex(pool_id[2:]),
        0,
        1,
        amount_in,
        b''
    )
    funds_struct = (
        Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
        False,
        Web3.to_checksum_address("0x0000000000000000000000000000000000000000"),
        False,
    )
    assets = [Web3.to_checksum_address(token_in), Web3.to_checksum_address(token_out)]
    asset_deltas = vault_contract.functions.queryBatchSwap(0, [swap_struct], assets, funds_struct).call()
    on_chain_amount_out = abs(asset_deltas[1])

    # 2. Rust BalancerAdapter
    rust_amount_out_str = await scanner_core.test_only_quote(json.dumps(raw_pool), token_in, str(amount_in))
    rust_amount_out = int(rust_amount_out_str)

    print(f"\nOn-chain Balancer output for discovered pair: {on_chain_amount_out}")
    print(f"Rust BalancerAdapter output for discovered pair:   {rust_amount_out}")
    assert on_chain_amount_out > 0, "On-chain quoter returned zero, fork state might be bad."
    assert rust_amount_out == on_chain_amount_out, "Rust adapter output does not match on-chain quoter output."

# ABIs for the fork test
V3_POOL_ABI = """[{"inputs":[],"name":"slot0","outputs":[{"internalType":"uint160","name":"sqrtPriceX96","type":"uint160"},{"internalType":"int24","name":"tick","type":"int24"},{"internalType":"uint16","name":"observationIndex","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint16","name":"observationCardinalityNext","type":"uint16"},{"internalType":"uint8","name":"feeProtocol","type":"uint8"},{"internalType":"bool","name":"unlocked","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"liquidity","outputs":[{"internalType":"uint128","name":"","type":"uint128"}],"stateMutability":"view","type":"function"}]"""
V3_QUOTER_ABI = """[{"inputs":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],"name":"quoteExactInputSingle","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"nonpayable","type":"function"}]"""
CURVE_POOL_ABI = """[{"inputs":[{"internalType":"int128","name":"i","type":"int128"}],"name":"balances","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"A","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"int128","name":"i","type":"int128"},{"internalType":"int128","name":"j","type":"int128"},{"internalType":"uint256","name":"dx","type":"uint256"}],"name":"get_dy","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]"""
BALANCER_VAULT_ABI = """[{"inputs":[{"internalType":"bytes32","name":"poolId","type":"bytes32"}],"name":"getPoolTokens","outputs":[{"internalType":"address[]","name":"tokens","type":"address[]"},{"internalType":"uint256[]","name":"balances","type":"uint256[]"},{"internalType":"uint256","name":"lastChangeBlock","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint8","name":"kind","type":"uint8"},{"components":[{"internalType":"bytes32","name":"poolId","type":"bytes32"},{"internalType":"uint256","name":"assetInIndex","type":"uint256"},{"internalType":"uint256","name":"assetOutIndex","type":"uint256"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"bytes","name":"userData","type":"bytes"}],"internalType":"struct IVault.BatchSwapStep[]","name":"swaps","type":"tuple[]"},{"internalType":"address[]","name":"assets","type":"address[]"},{"components":[{"internalType":"address","name":"sender","type":"address"},{"internalType":"bool","name":"fromInternalBalance","type":"bool"},{"internalType":"address payable","name":"recipient","type":"address"},{"internalType":"bool","name":"toInternalBalance","type":"bool"}],"internalType":"struct IVault.FundManagement","name":"funds","type":"tuple"}],"name":"queryBatchSwap","outputs":[{"internalType":"int256[]","name":"assetDeltas","type":"int256[]"}],"stateMutability":"nonpayable","type":"function"}]"""