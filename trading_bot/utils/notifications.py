"""
Telegram Notifications Module
=============================
Send trade alerts and notifications via Telegram Bot
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass
import json

# Telegram bot library
try:
    import telegram
    from telegram import Update
    from telegram.ext import Application, CommandHandler, CallbackContext
except ImportError:
    print("Installing python-telegram-bot...")
    import subprocess
    subprocess.run(["pip", "install", "python-telegram-bot", "-q"], capture_output=True)
    import telegram
    from telegram import Update
    from telegram.ext import Application, CommandHandler, CallbackContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    bot_token: str
    chat_id: str
    enabled: bool = True
    parse_mode: str = "HTML"  # HTML, Markdown, None


class TelegramNotifier:
    """
    Telegram notification handler for trading alerts
    """

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.application = None
        self.bot = None

    async def initialize(self):
        """Initialize the Telegram bot"""
        if not self.config.enabled:
            logger.info("Telegram notifications disabled")
            return

        try:
            self.application = Application.builder().token(self.config.bot_token).build()
            self.bot = self.application.bot
            await self.bot.initialize()
            logger.info("✓ Telegram bot initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.config.enabled = False

    async def send_message(self, text: str, disable_notification: bool = False) -> bool:
        """
        Send a message to the configured chat

        Args:
            text: Message text (supports HTML if parse_mode='HTML')
            disable_notification: Send without sound

        Returns:
            True if sent successfully
        """
        if not self.config.enabled:
            return False

        try:
            await self.bot.send_message(
                chat_id=self.config.chat_id,
                text=text,
                parse_mode=self.config.parse_mode,
                disable_notification=disable_notification
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def shutdown(self):
        """Shutdown the Telegram bot"""
        if self.application:
            await self.application.shutdown()


class TradeAlerts:
    """
    Pre-formatted trade alerts for Telegram
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier

    async def alert_entry(self,
                          signal_type: str,
                          symbol: str,
                          price: float,
                          sl: float,
                          tp: float,
                          ob_type: str = None,
                          ob_index: int = None) -> bool:
        """
        Send entry signal alert

        Args:
            signal_type: LONG or SHORT
            symbol: Trading pair (e.g., BTC/USDT)
            price: Entry price
            sl: Stop loss price
            tp: Take profit price
            ob_type: Order block type (bullish/bearish)
            ob_index: Order block index
        """
        emoji = "🟢" if signal_type == "LONG" else "🔴"
        direction = "LONG" if signal_type == "LONG" else "SHORT"

        rr = (tp - price) / (price - sl) if signal_type == "LONG" else (price - tp) / (sl - price)
        rr_str = f"{rr:.2f}"

        text = f"""
{emoji} <b>{direction} ENTRY</b>

<b>Symbol:</b> {symbol}
<b>Price:</b> ${price:,.2f}
<b>SL:</b> ${sl:,.2f}
<b>TP:</b> ${tp:,.2f}
<b>Risk/Reward:</b> 1:{rr_str}
"""
        if ob_type:
            text += f"<b>OB Type:</b> {ob_type}\n"

        text += f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return await self.notifier.send_message(text)

    async def alert_exit(self,
                         signal_type: str,
                         symbol: str,
                         entry_price: float,
                         exit_price: float,
                         pnl_percent: float,
                         reason: str,
                         sl: float = None,
                         tp: float = None) -> bool:
        """
        Send exit signal alert

        Args:
            signal_type: LONG or SHORT
            symbol: Trading pair
            entry_price: Entry price
            exit_price: Exit price
            pnl_percent: Profit/loss percentage
            reason: Exit reason (tp, sl, manual, reversal)
            sl: Original stop loss
            tp: Original take profit
        """
        emoji = "✅" if pnl_percent > 0 else "❌"
        pnl_emoji = "+" if pnl_percent > 0 else ""

        text = f"""
{emoji} <b>POSITION CLOSED</b>

<b>Symbol:</b> {symbol}
<b>Type:</b> {signal_type}
<b>Entry:</b> ${entry_price:,.2f}
<b>Exit:</b> ${exit_price:,.2f}
<b>PnL:</b> {pnl_emoji}{pnl_percent:.2f}%
<b>Reason:</b> {reason.upper()}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return await self.notifier.send_message(text)

    async def alert_bos(self,
                        symbol: str,
                        bos_type: str,
                        price: float) -> bool:
        """
        Send Break of Structure alert

        Args:
            symbol: Trading pair
            bos_type: BULLISH or BEARISH
            price: Break price
        """
        emoji = "🟢" if bos_type == "BULLISH" else "🔴"
        text = f"""
{emoji} <b>{bos_type} BOS</b>

<b>Symbol:</b> {symbol}
<b>Price:</b> ${price:,.2f}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return await self.notifier.send_message(text)

    async def alert_status(self,
                           symbol: str,
                           position: str,
                           current_price: float,
                           unrealized_pnl: float) -> bool:
        """
        Send position status update

        Args:
            symbol: Trading pair
            position: Position status (LONG, SHORT, FLAT)
            current_price: Current price
            unrealized_pnl: Unrealized PnL percentage
        """
        if position == "FLAT":
            text = f"""
📊 <b>POSITION STATUS</b>

<b>Symbol:</b> {symbol}
<b>Position:</b> FLAT
<b>Price:</b> ${current_price:,.2f}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        else:
            emoji = "🟢" if unrealized_pnl >= 0 else "🔴"
            pnl_emoji = "+" if unrealized_pnl >= 0 else ""
            text = f"""
📊 <b>POSITION STATUS</b>

{emoji} <b>{position}</b>

<b>Symbol:</b> {symbol}
<b>Price:</b> ${current_price:,.2f}
<b>Unrealized PnL:</b> {pnl_emoji}{unrealized_pnl:.2f}%
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return await self.notifier.send_message(text)


# ============================================================================
# SIMPLE BOT HANDLERS (for /start, /status, /pnl commands)
# ============================================================================

class TradingBotHandlers:
    """
    Command handlers for the trading bot
    """

    def __init__(self, trader, alerts: TradeAlerts):
        self.trader = trader
        self.alerts = alerts

    async def start_handler(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 <b>Trading Bot Started</b>\n\n"
            "Commands:\n"
            "/status - Current position\n"
            "/pnl - Today's P&L\n"
            "/open - Open positions\n"
            "/last_signal - Last signal\n\n"
            "Use /trade to toggle auto-trading",
            parse_mode="HTML"
        )

    async def status_handler(self, update: Update, context: CallbackContext):
        """Handle /status command"""
        status = self.trader.get_status()
        position = status.get('position')

        if not position:
            await update.message.reply_text(
                "📊 <b>No active position</b>",
                parse_mode="HTML"
            )
            return

        await update.message.reply_text(
            f"📊 <b>Position Open</b>\n\n"
            f"Type: {position.get('side', 'N/A')}\n"
            f"Size: {position.get('quantity', 0):.4f}\n"
            f"Entry: ${position.get('entry_price', 0):,.2f}\n"
            f"Unrealized PnL: ${position.get('unrealized_pnl', 0):,.2f}",
            parse_mode="HTML"
        )

    async def pnl_handler(self, update: Update, context: CallbackContext):
        """Handle /pnl command"""
        status = self.trader.get_status()
        daily_pnl = status.get('daily_pnl', 0)

        emoji = "🟢" if daily_pnl >= 0 else "🔴"
        sign = "+" if daily_pnl >= 0 else ""

        await update.message.reply_text(
            f"📈 <b>Daily P&L</b>\n\n"
            f"{emoji} <b>{sign}${daily_pnl:,.2f}</b>",
            parse_mode="HTML"
        )

    def register_handlers(self, application: telegram.ext.Application):
        """Register command handlers"""
        application.add_handler(CommandHandler("start", self.start_handler))
        application.add_handler(CommandHandler("status", self.status_handler))
        application.add_handler(CommandHandler("pnl", self.pnl_handler))


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_telegram_notifier(bot_token: str, chat_id: str, enabled: bool = True) -> TelegramNotifier:
    """Create a configured Telegram notifier"""
    config = TelegramConfig(
        bot_token=bot_token,
        chat_id=chat_id,
        enabled=enabled
    )
    return TelegramNotifier(config)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Example: Send a test message
    import asyncio

    async def test():
        notifier = create_telegram_notifier(
            bot_token="YOUR_BOT_TOKEN",
            chat_id="YOUR_CHAT_ID",
            enabled=True
        )

        await notifier.initialize()

        # Send test message
        success = await notifier.send_message(
            "🧪 <b>Test Message</b>\n\nBot is running!"
        )

        if success:
            print("✓ Test message sent!")

        await notifier.shutdown()

    asyncio.run(test())
