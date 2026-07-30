import asyncio
from web3 import Web3

async def run_hardcoded_diagnostic():
    HTTP_URL = 'https://polygon-bor-rpc.publicnode.com'
    WSS_URL = 'wss://polygon-bor-rpc.publicnode.com'

    print(f"--- Hardcoded Diagnostic Tool ---")

    # Test HTTP
    w3_http = Web3(Web3.HTTPProvider(HTTP_URL))
    http_connected = w3_http.is_connected()
    print(f"HTTP Connection ({HTTP_URL}): {http_connected}")
    if http_connected:
        print(f"Current Block (HTTP): {w3_http.eth.block_number}")

    # Test WSS
    print(f"\nWSS Connection ({WSS_URL}):")
    try:
        # Check for specific Web3 version provider naming
        if hasattr(Web3, 'LegacyWebSocketProvider'):
            provider = Web3.LegacyWebSocketProvider(WSS_URL)
        else:
            provider = Web3.WebsocketProvider(WSS_URL)

        w3_wss = Web3(provider)
        wss_connected = w3_wss.is_connected()
        print(f"WSS Connected: {wss_connected}")
        if wss_connected:
            print(f"Current Block (WSS): {w3_wss.eth.block_number}")
    except Exception as e:
        print(f"WSS Diagnostic Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_hardcoded_diagnostic())
