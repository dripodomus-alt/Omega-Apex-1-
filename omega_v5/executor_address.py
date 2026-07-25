# ==============================================================================
# executor_address.py -- Prints the canonical executor contract address.
#
# This allows PowerShell scripts to use the same configuration resolution
# logic as the Python application, ensuring consistency.
# ==============================================================================
from .config import EXECUTOR_CONTRACT

if __name__ == "__main__":
    print(EXECUTOR_CONTRACT)