import telebot
import os
import threading
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from engine import C1Aggressor, SlippageSentinel, Web3PoolScanner
import logging
from execution_governance import get_governance_service, get_minimum_net_profit_usd

load_dotenv()
logger = logging.getLogger(__name__)
BOT_NAME = "/nexus"

# Initialize Bot
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# System State Control
class SystemState:
    def __init__(self):
        self.is_running = False
        self.stop_event = threading.Event()
        self.opportunities_found = 0
        self.scans_completed = 0
        self.last_scan_time = None
        self.engine_thread = None

state = SystemState()


@bot.message_handler(commands=['start', 'help'])
def handle_start(message):
    """Welcome message and command list"""
    help_text = """
🔱 <b>APEX_OMEGA - TITAN REBUILD V4</b>

<b>Available Commands:</b>
/boot_nexus - Initialize C1 Aggressor & start scanning
/shutdown - Stop the Nexus engine
/status - Check current system status
/pools - List all monitored pools
/config - View current configuration
/audit_start - Start performance audit (dry_run default)
/audit_stop - Stop active performance audit
/audit_status - View current governance metrics
/test_run - Trigger test orchestration job
/test_stop - Stop active test orchestration job
/latency_probe - Run one latency probe test job
/help - Show this message

<b>System Components:</b>
• <b>C1 Aggressor</b> - Atomic Displacement Calculator
• <b>Slippage Sentinel</b> - Variance Predictor
• <b>Web3 Multicall</b> - 12+ Pool Simultaneous Scanner

<i>Network: Polygon Mainnet</i>
    """
    bot.reply_to(message, help_text)


@bot.message_handler(commands=['boot_nexus'])
def handle_boot(message):
    """Initialize and start the Nexus scanning engine"""
    if state.is_running:
        bot.reply_to(message, "⚠️ <b>TITAN OMEGA:</b> Nexus is already active.\nUse /shutdown to stop first.")
        return

    bot.reply_to(message, """
🛰️ <b>TITAN OMEGA: Handshake Verified.</b>

<b>Initializing Systems:</b>
├─ C1 Aggressor: <code>ONLINE</code>
├─ Slippage Sentinel: <code>ONLINE</code>
├─ Web3 Multicall: <code>ARMED</code>
└─ Pool Scanner: <code>12 TARGETS LOCKED</code>

<i>Monitoring Polygon UniswapV3 pools...</i>
    """)
    
    state.is_running = True
    state.stop_event.clear()
    state.opportunities_found = 0
    state.scans_completed = 0
    
    # Start the engine in a background thread
    state.engine_thread = threading.Thread(target=nexus_loop, args=(message.chat.id,), daemon=True)
    state.engine_thread.start()


def nexus_loop(chat_id):
    """Main scanning loop - runs in background thread"""
    rpc_url = os.getenv("POLYGON_RPC_URL", "")
    tolerance = float(os.getenv("MAX_SLIPPAGE_TOLERANCE", 0.03))
    min_profit = float(os.getenv("MIN_PROFIT_THRESHOLD", 0.005))
    force_multiplier = float(os.getenv("ATOMIC_FORCE_MULTIPLIER", 1.2))
    scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", 15))
    
    sentinel = SlippageSentinel(tolerance=tolerance)
    aggressor = C1Aggressor(sentinel, min_profit=min_profit, force_multiplier=force_multiplier)
    scanner = Web3PoolScanner(rpc_url)
    
    # Check Web3 connection
    if scanner.is_connected():
        bot.send_message(chat_id, f"🤖 <b>{BOT_NAME}</b>\n🌐 <b>WEB3 CONNECTION:</b> <code>ESTABLISHED</code>\n<i>Live pool data active</i>")
    else:
        bot.send_message(chat_id, f"🤖 <b>{BOT_NAME}</b>\n⚠️ <b>WEB3 CONNECTION:</b> <code>MOCK MODE</code>\n<i>Using simulated pool data (add valid RPC URL for live data)</i>")
    
    bot.send_message(chat_id, f"🤖 <b>{BOT_NAME}</b>\n🚀 <b>NEXUS ONLINE:</b> Scanning every {scan_interval}s...")
    
    while not state.stop_event.is_set():
        try:
            state.last_scan_time = datetime.now(timezone.utc)
            
            # Scan and analyze all pools
            results = aggressor.scan_and_analyze(scanner)
            state.scans_completed += 1
            
            # Filter validated opportunities
            validated = [r for r in results if r['status'] == 'VALIDATED']
            
            if validated:
                state.opportunities_found += len(validated)
                
                for opp in validated[:3]:  # Send top 3 opportunities
                    raw_flash_size = opp.get("flash_size_usd")
                    if raw_flash_size is None:
                        raw_flash_size = opp.get("force_required")
                    flash_size = float(raw_flash_size) if raw_flash_size is not None else 0.0
                    execution_gate = "C2 (Surgical)" if opp.get("status") == "VALIDATED" else "C1"
                    alert = f"""
🤖 <b>{BOT_NAME}</b>
🌑 <b>NEXUS: SURGICAL STRIKE</b>

[C1 - AGGRESSOR] | [C2 - SURGEON]
<b>Status:</b> Verified Execution
<b>Target Gate:</b> {execution_gate}

<b>Pool:</b> {opp['pool']}
<b>Address:</b> <code>{opp['address'][:10]}...{opp['address'][-6:]}</code>

📊 <b>Execution Parameters:</b>
├─ Min TVL: ${opp['liquidity']:,}
├─ Flash Size: ${flash_size:,.2f} (10% Scaling)
├─ Gap: {opp['gap']}%
└─ Volatility Index: {opp['volatility']}

💰 <b>Profit Projection:</b>
├─ Force Required: {opp['force_required']:,.4f}
├─ Gross Return: {opp['gross_return']:.6f}
├─ Slippage Loss: {opp['slippage_loss']:.6f}
├─ <b>Net Profit: {opp['predicted_profit']:.6f}</b>
└─ <b>ROI: {opp['profit_percentage']:.4f}%</b>

⚡ Slippage: {opp['slippage']:.6f} (Tolerance: {tolerance})
                    """
                    bot.send_message(chat_id, alert)
                    time.sleep(0.5)  # Rate limiting
            
            # Periodic status update every 10 scans
            if state.scans_completed % 10 == 0:
                bot.send_message(chat_id, f"🤖 <b>{BOT_NAME}</b>\n📡 <b>SCAN UPDATE:</b> {state.scans_completed} cycles | {state.opportunities_found} opportunities found")
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            bot.send_message(chat_id, f"🤖 <b>{BOT_NAME}</b>\n⚠️ <b>SCAN ERROR:</b> {str(e)[:100]}")
        
        state.stop_event.wait(scan_interval)
    
    bot.send_message(chat_id, f"🤖 <b>{BOT_NAME}</b>\n🔴 <b>NEXUS LOOP TERMINATED</b>")


@bot.message_handler(commands=['shutdown'])
def handle_shutdown(message):
    """Stop the Nexus engine"""
    if not state.is_running:
        bot.reply_to(message, "ℹ️ System is already offline.")
        return
    
    state.stop_event.set()
    state.is_running = False
    
    bot.reply_to(message, f"""
🛑 <b>SYSTEM SHUTDOWN INITIATED</b>

<b>Final Statistics:</b>
├─ Scans Completed: {state.scans_completed}
├─ Opportunities Found: {state.opportunities_found}
└─ Status: <code>OFFLINE</code>

<i>Use /boot_nexus to restart.</i>
    """)


@bot.message_handler(commands=['status'])
def handle_status(message):
    """Show current system status"""
    status_emoji = "🟢" if state.is_running else "🔴"
    last_scan = state.last_scan_time.strftime("%H:%M:%S UTC") if state.last_scan_time else "Never"
    
    rpc_url = os.getenv("POLYGON_RPC_URL", "")
    scanner = Web3PoolScanner(rpc_url)
    web3_status = "Connected" if scanner.is_connected() else "Mock Mode"
    
    governance = get_governance_service().get_metrics()
    gov_system = governance.get("system", {})
    status_text = f"""
📊 <b>APEX_OMEGA STATUS</b>

<b>Engine:</b> {status_emoji} {'ONLINE' if state.is_running else 'OFFLINE'}
<b>Web3:</b> {web3_status}
<b>Scans:</b> {state.scans_completed}
<b>Opportunities:</b> {state.opportunities_found}
<b>Last Scan:</b> {last_scan}

<b>Configuration:</b>
├─ Slippage Tolerance: {os.getenv('MAX_SLIPPAGE_TOLERANCE', '0.03')}
├─ Min Profit (policy): ${get_minimum_net_profit_usd():.2f} net after all costs
├─ Force Multiplier: {os.getenv('ATOMIC_FORCE_MULTIPLIER', '1.2')}
└─ Scan Interval: {os.getenv('SCAN_INTERVAL_SECONDS', '15')}s

<b>Governance:</b>
├─ Decisions: {gov_system.get('decisions_total', 0)}
├─ Accepted: {gov_system.get('accepted', 0)}
└─ Rejected: {gov_system.get('rejected', 0)}
    """
    bot.reply_to(message, status_text)


@bot.message_handler(commands=['pools'])
def handle_pools(message):
    """List all monitored pools"""
    from engine import POLYGON_POOLS
    
    pools_text = "🏊 <b>MONITORED POOLS (Polygon UniswapV3)</b>\n\n"
    for i, (name, address) in enumerate(POLYGON_POOLS.items(), 1):
        pools_text += f"{i}. <b>{name}</b>\n   <code>{address[:20]}...</code>\n"
    
    pools_text += f"\n<i>Total: {len(POLYGON_POOLS)} pools</i>"
    bot.reply_to(message, pools_text)


@bot.message_handler(commands=['config'])
def handle_config(message):
    """Show current configuration"""
    config_text = f"""
⚙️ <b>CURRENT CONFIGURATION</b>

<b>Network:</b> Polygon Mainnet
<b>RPC:</b> {'Configured' if 'YOUR_API_KEY' not in os.getenv('POLYGON_RPC_URL', 'YOUR_API_KEY') else 'Not Set'}

<b>C1 Aggressor Settings:</b>
├─ MIN_NET_PROFIT_USD (policy): {get_minimum_net_profit_usd():.2f}
├─ MAX_SLIPPAGE_TOLERANCE: {os.getenv('MAX_SLIPPAGE_TOLERANCE', '0.03')}
├─ ATOMIC_FORCE_MULTIPLIER: {os.getenv('ATOMIC_FORCE_MULTIPLIER', '1.2')}
└─ SCAN_INTERVAL_SECONDS: {os.getenv('SCAN_INTERVAL_SECONDS', '15')}

<i>Edit .env file to modify settings.</i>
    """
    bot.reply_to(message, config_text)


@bot.message_handler(commands=['audit_start'])
def handle_audit_start(message):
    args = message.text.split()
    mode = args[1] if len(args) > 1 else "dry_run"
    result = get_governance_service().start_audit_run(mode=mode, profile={"interval_sec": 2})
    bot.reply_to(
        message,
        f"🧪 <b>AUDIT RUNNER:</b> {result.get('status','unknown').upper()}\n"
        f"Mode: <code>{mode}</code>\n"
        f"Run ID: <code>{result.get('run', {}).get('run_id', 'n/a')}</code>"
    )


@bot.message_handler(commands=['audit_stop'])
def handle_audit_stop(message):
    result = get_governance_service().stop_audit_run()
    bot.reply_to(message, f"🛑 <b>AUDIT RUNNER:</b> {result.get('status', 'unknown').upper()}")


@bot.message_handler(commands=['audit_status'])
def handle_audit_status(message):
    metrics = get_governance_service().get_metrics()
    latency = metrics.get("latency", {})
    system = metrics.get("system", {})
    run_state = metrics.get("audit_run", {})
    bot.reply_to(
        message,
        "📈 <b>GOVERNANCE METRICS</b>\n\n"
        f"Policy floor: <b>${get_minimum_net_profit_usd():.2f}</b>\n"
        f"Run active: <code>{run_state.get('active', False)}</code>\n"
        f"Mode: <code>{run_state.get('mode', 'n/a')}</code>\n"
        f"Decisions: {system.get('decisions_total', 0)} "
        f"(✅ {system.get('accepted', 0)} / ❌ {system.get('rejected', 0)})\n"
        f"Latency avg/p95: {latency.get('avg_ms', 0):.2f}ms / {latency.get('p95_ms', 0):.2f}ms"
    )


@bot.message_handler(commands=['test_run'])
def handle_test_run(message):
    args = message.text.split()
    kind = args[1] if len(args) > 1 else "full_suite"
    component = args[2] if len(args) > 2 else None
    result = get_governance_service().start_test_job(kind=kind, component=component, scheduled_interval_sec=0)
    bot.reply_to(
        message,
        f"🧰 <b>TEST ORCHESTRATION:</b> {result.get('status', 'unknown').upper()}\n"
        f"Kind: <code>{kind}</code>\n"
        f"Component: <code>{component or 'default'}</code>"
    )


@bot.message_handler(commands=['test_stop'])
def handle_test_stop(message):
    result = get_governance_service().stop_test_job()
    bot.reply_to(message, f"🛑 <b>TEST ORCHESTRATION:</b> {result.get('status', 'unknown').upper()}")


@bot.message_handler(commands=['latency_probe'])
def handle_latency_probe(message):
    result = get_governance_service().start_test_job(kind="latency_probe", scheduled_interval_sec=0)
    bot.reply_to(
        message,
        f"⏱️ <b>LATENCY PROBE:</b> {result.get('status', 'unknown').upper()}\n"
        "Use /audit_status to view updated latency metrics."
    )


def start_bot():
    """Start the Telegram bot"""
    logger.info("Starting APEX_OMEGA Bot Interface...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    print("APEX_OMEGA Bot Interface Active...")
    start_bot()
