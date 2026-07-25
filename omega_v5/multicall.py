# ==============================================================================
# multicall.py -- Utility for batching on-chain read calls.
#
# This module provides a helper to interact with a Multicall3-compatible
# contract, allowing multiple view calls to be bundled into a single RPC request.
# This is a critical optimization for reducing RPC load and improving data
# fetching performance.
# ==============================================================================

from typing import List, Dict, Any, Tuple
from web3 import Web3

# Standard Multicall3 address, deployed on most EVM chains.
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

# Minimal ABI needed for the 'aggregate3' function.
MULTICALL3_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bool", "name": "allowFailure", "type": "bool"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Call3[]",
                "name": "calls",
                "type": "tuple[]",
            }
        ],
        "name": "aggregate3",
        "outputs": [
            {
                "components": [
                    {"internalType": "bool", "name": "success", "type": "bool"},
                    {"internalType": "bytes", "name": "returnData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Result[]",
                "name": "returnData",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


def execute_multicall(w3: Web3, calls: List[Dict[str, Any]]) -> List[Tuple[bool, bytes]]:
    """
    Executes a batch of calls using the Multicall3 contract.

    Args:
        w3: The Web3 instance.
        calls: A list of call dictionaries, each with 'target', 'allowFailure', and 'callData'.

    Returns:
        A list of tuples, where each tuple is (success, returnData).
    """
    multicall_contract = w3.eth.contract(address=MULTICALL3_ADDRESS, abi=MULTICALL3_ABI)
    return multicall_contract.functions.aggregate3(calls).call()