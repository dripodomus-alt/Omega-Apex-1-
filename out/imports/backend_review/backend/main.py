#!/usr/bin/env python3
"""
APEX_OMEGA: TITAN REBUILD V4
Main Orchestrator - Entry point for the system
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


def verify_environment():
    """Verify all required environment variables are set"""
    required_vars = ['TELEGRAM_BOT_TOKEN']
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing required environment variables: {missing}")
        return False
    
    # Verify token format
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    if 'AAHPE' not in token:
        logger.warning("Token may be invalid (expected format not detected)")
    
    return True


def print_banner():
    """Print startup banner"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║      █████╗ ██████╗ ███████╗██╗  ██╗     ██████╗ ███╗   ███╗ ║
║     ██╔══██╗██╔══██╗██╔════╝╚██╗██╔╝    ██╔═══██╗████╗ ████║ ║
║     ███████║██████╔╝█████╗   ╚███╔╝     ██║   ██║██╔████╔██║ ║
║     ██╔══██║██╔═══╝ ██╔══╝   ██╔██╗     ██║   ██║██║╚██╔╝██║ ║
║     ██║  ██║██║     ███████╗██╔╝ ██╗    ╚██████╔╝██║ ╚═╝ ██║ ║
║     ╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝     ╚═════╝ ╚═╝     ╚═╝ ║
║                                                              ║
║                    TITAN REBUILD V4                          ║
║             Atomic Displacement Engine                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def start_rebuild():
    """
    Main entry point for the APEX_OMEGA System Rebuild.
    Verifies environment and starts the Telegram Listener.
    """
    print_banner()
    print("--- APEX_OMEGA: TITAN REBUILD V4 ---")
    print()
    
    # Verify environment
    if not verify_environment():
        print("ERROR: Environment verification failed")
        sys.exit(1)
    
    # Display token status
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    print(f"✓ Token Verified: {token[:15]}...{token[-5:]}")
    
    # Display RPC status
    rpc_url = os.getenv('POLYGON_RPC_URL', '')
    if 'YOUR_API_KEY' in rpc_url:
        print("⚠ RPC URL: Not configured (using mock mode)")
    else:
        print("✓ RPC URL: Configured")
    
    print()
    print("Components:")
    print("  • C1 Aggressor: Ready")
    print("  • Slippage Sentinel: Ready")
    print("  • Web3 Multicall Scanner: Ready")
    print("  • Pool Targets: 12 Polygon UniswapV3 pools")
    print()
    print("Status: Awaiting /boot_nexus command via Telegram...")
    print()
    
    try:
        from bot_handler import start_bot
        start_bot()
    except KeyboardInterrupt:
        print("\n\nShutdown requested by user.")
    except Exception as e:
        logger.error(f"CRITICAL SYSTEM ERROR: {e}")
        raise


if __name__ == "__main__":
    start_rebuild()
