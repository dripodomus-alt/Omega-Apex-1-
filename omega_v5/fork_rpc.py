# ==============================================================================
# fork_rpc.py -- Prints the best available discovery RPC URL for forking.
#
# This script allows PowerShell scripts like `start_anvil_fork.ps1` to leverage
# the same dynamic RPC selection logic as the main Python application.
# ==============================================================================

import argparse
from . import rpc_layer

def main():
    # The rpc_layer module automatically selects the best URL upon import.
    # We just need to print the result to stdout for the calling script.
    print(rpc_layer.DISCOVERY_RPC_URL)

if __name__ == "__main__":
    main()