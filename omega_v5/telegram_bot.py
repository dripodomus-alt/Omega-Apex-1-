#!/usr/bin/env python3
# ==============================================================================
# telegram_bot.py -- Telegram bot for Omega V5 remote control and monitoring.
# ==============================================================================

import os
import subprocess
import json
from decimal import Decimal
import telebot
from telebot import types

from .config import _env
from .runtime_control import get_runtime_state, set_runtime_mode
from .pnl_tracker import current_snapshot
from .profit_sweeper import sweep_profits


TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_IDS = [
    int(uid.strip()) for uid in _env("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if uid.strip()
]
PROFIT_RECEIVER_WALLET = _env("PROFIT_RECEIVER_WALLET")


if not TELEGRAM_BOT_TOKEN:
    print("TELEGRAM_BOT_TOKEN not set. Bot will not run.")
    bot = None
else:
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


def authorized_only(func):
    """Decorator to restrict access to authorized users."""
    def wrapper(message):
        if TELEGRAM_ALLOWED_USER_IDS and message.from_user.id not in TELEGRAM_ALLOWED_USER_IDS:
            bot.reply_to(message, "🚫 Access Denied. You are not authorized.")
            return
        return func(message)
    return wrapper


def _format_pnl(pnl_data: dict) -> str:
    """Formats PnL data for a readable Telegram message."""
    lines = []
    for book in ["dry_run", "live"]:
        lines.append(f"*{book.replace('_', ' ').title()} PnL*")
        c1 = pnl_data.get(book, {}).get("C1", {})
        c2 = pnl_data.get(book, {}).get("C2", {})
        comb = pnl_data.get(book, {}).get("combined", {})
        lines.append(f"  C1: `${Decimal(c1.get('display_pnl_usd', 0)):.2f}` ({c1.get('events', 0)} events)")
        lines.append(f"  C2: `${Decimal(c2.get('display_pnl_usd', 0)):.2f}` ({c2.get('events', 0)} events)")
        lines.append(f"  *Combined*: `${Decimal(comb.get('display_pnl_usd', 0)):.2f}`")
        lines.append("")
    return "\n".join(lines)


if bot:
    @bot.message_handler(commands=['start', 'help'])
    @authorized_only
    def send_welcome(message):
        help_text = (
            "Omega V5 Control Panel\n\n"
            "*Monitoring:*\n"
            "/status - Get runtime status\n/pnl - Get PnL summary\n/pm2 - Get PM2 process status\n\n"
            "*Control:*\n/mode - Change runtime mode\n/sweep - Sweep profits to receiver wallet\n\n"
            "*Strategies:*\n/arbitrage_on | /arbitrage_off\n/liquidation_on | /liquidation_off"
        )
        bot.reply_to(message, help_text, parse_mode="Markdown")

    @bot.message_handler(commands=['status'])
    @authorized_only
    def get_status(message):
        try:
            state = get_runtime_state()
            mode = state.get('mode', 'unknown')
            settings = state.get('settings', {})
            status_text = (
                f"*Omega V5 Status*\n"
                f"Mode: `{mode.upper()}`\n"
                f"Execute Top: `{settings.get('execute_top', 'N/A')}`\n"
                f"Canary Mode: `{'ON' if settings.get('canary_mode') else 'OFF'}`\n"
                f"Ticks: `{settings.get('ticks', 'N/A')}`\n"
                f"Principal: `${Decimal(settings.get('principal_usd', 0)):,}`"
            )
            bot.reply_to(message, status_text, parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"Error fetching status: {e}")

    @bot.message_handler(commands=['pnl'])
    @authorized_only
    def get_pnl(message):
        try:
            snapshot = current_snapshot()
            pnl_text = _format_pnl(snapshot)
            bot.reply_to(message, pnl_text, parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"Error fetching PnL: {e}")

    @bot.message_handler(commands=['mode'])
    @authorized_only
    def change_mode(message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("Live", callback_data='set_mode_live'),
            types.InlineKeyboardButton("Dry Run", callback_data='set_mode_dry_run'),
            types.InlineKeyboardButton("Canary", callback_data='set_mode_canary'),
            types.InlineKeyboardButton("Shadow", callback_data='set_mode_shadow'),
        )
        bot.send_message(message.chat.id, "Select new runtime mode:", reply_markup=markup)

    @bot.message_handler(commands=['sweep'])
    @authorized_only
    def sweep(message):
        if not PROFIT_RECEIVER_WALLET:
            bot.reply_to(message, "⚠️ PROFIT_RECEIVER_WALLET is not configured in .env file.")
            return
        try:
            bot.reply_to(message, "Sweeping profits...")
            result = sweep_profits(PROFIT_RECEIVER_WALLET)
            result_text = f"✅ *Profit Sweep Successful*\nTx Hash: `{result['tx_hash']}`\nAmount: {result['amount_swept']} ETH"
            bot.reply_to(message, result_text, parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Profit sweep failed: {e}")

    @bot.message_handler(commands=['pm2'])
    @authorized_only
    def pm2_status(message):
        """Gets the status of all pm2 managed processes."""
        try:
            result = subprocess.run(["pm2", "jlist"], check=True, capture_output=True, text=True)
            bot.reply_to(message, f"```\n{result.stdout}\n```", parse_mode="MarkdownV2")
            result = subprocess.run(["pm2", "jlist"], check=True, capture_output=True, text=True, encoding="utf-8")
            processes = json.loads(result.stdout)
            if not processes:
                bot.reply_to(message, "No PM2 processes found.")
                return

            lines = ["*PM2 Process Status*"]
            for proc in sorted(processes, key=lambda p: p.get("name", "")):
                name = proc.get("name", "N/A")
                status = proc.get("pm2_env", {}).get("status", "unknown")
                cpu = proc.get("monit", {}).get("cpu", 0)
                mem_bytes = proc.get("monit", {}).get("memory", 0)
                mem_mb = mem_bytes / (1024 * 1024)

                status_icon = "✅" if status == "online" else "❌" if status in ["stopped", "errored"] else "⚠️"
                lines.append(f"`{status_icon} {name:<28}`")
                lines.append(f"  `Status: {status}, CPU: {cpu}%, Mem: {mem_mb:.1f} MB`")

            bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            bot.reply_to(message, f"❌ Failed to get PM2 status. Is it installed and in PATH?\n`{e}`")
            bot.reply_to(message, f"❌ Failed to get PM2 status. Is it installed and in PATH?\n`{e}`", parse_mode="Markdown")

    def _toggle_strategy(strategy_name: str, action: str):
        """Helper to start/stop pm2 processes."""
        try:
            subprocess.run(["pm2", action, strategy_name], check=True, capture_output=True, text=True)
            return f"✅ Strategy *{strategy_name}* has been *{action.upper()}ED*."
        except subprocess.CalledProcessError as e:
            return f"❌ Failed to {action} *{strategy_name}*.\n`{e.stderr}`"

    @bot.message_handler(commands=['arbitrage_on'])
    @authorized_only
    def arbitrage_on(message):
        bot.reply_to(message, _toggle_strategy("omega-engine", "start"), parse_mode="Markdown")

    @bot.message_handler(commands=['arbitrage_off'])
    @authorized_only
    def arbitrage_off(message):
        bot.reply_to(message, _toggle_strategy("omega-engine", "stop"), parse_mode="Markdown")

    @bot.message_handler(commands=['liquidation_on'])
    @authorized_only
    def liquidation_on(message):
        bot.reply_to(message, _toggle_strategy("omega-liquidation-watcher", "start"), parse_mode="Markdown")

    @bot.message_handler(commands=['liquidation_off'])
    @authorized_only
    def liquidation_off(message):
        bot.reply_to(message, _toggle_strategy("omega-liquidation-watcher", "stop"), parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('set_mode_'))
    def callback_query(call):
        try:
            new_mode = call.data.replace('set_mode_', '')
            if call.from_user.id not in TELEGRAM_ALLOWED_USER_IDS:
                bot.answer_callback_query(call.id, "🚫 Access Denied")
                return

            set_runtime_mode(new_mode, actor=f"telegram_user_{call.from_user.id}")
            bot.answer_callback_query(call.id, f"Mode changed to {new_mode.upper()}")
            bot.send_message(call.message.chat.id, f"✅ Runtime mode set to *{new_mode.upper()}*.", parse_mode="Markdown")
        except Exception as e:
            bot.answer_callback_query(call.id, "Error changing mode")
            bot.send_message(call.message.chat.id, f"Failed to change mode: {e}")


def main():
    if not bot:
        print("Telegram bot is not configured. Exiting.")
        return
    if not TELEGRAM_ALLOWED_USER_IDS:
        print("WARNING: TELEGRAM_ALLOWED_USER_IDS is not set. The bot will only be accessible to the owner.")

    print("🤖 Telegram bot started...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()