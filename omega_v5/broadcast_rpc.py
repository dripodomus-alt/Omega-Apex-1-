# ==============================================================================
# broadcast_rpc.py -- Prints the best available broadcast RPC URL.
#
# This allows PowerShell scripts to leverage the same dynamic RPC selection
# logic as the main Python application for submitting transactions.
# ==============================================================================
from . import rpc_layer

if __name__ == "__main__":
    # The rpc_layer module automatically selects the best URL upon import.
    print(rpc_layer.BROADCAST_RPC_URL)