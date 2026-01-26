"""
Trade Journal Module
====================
Advanced trade journaling with Telegram notifications
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Any, List
from pathlib import Path
import json

from trading_bot.utils.notifications import (
    TelegramNotifier, 
    TelegramConfig, 
    TradeAlerts
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradeJournal:
    """
    Trade journal with detailed Telegram notifications
    """

    def __init__(self, config_path: str = None):
        """
        Initialize trade journal

        Args:
            config_path: Path to telegram_config.json
        """
        self.config_path = config_path or self._find_config()
        self.config = self._load_config()
        self.notifier = None
        self.alerts = None
        self.initialized = False
        self.trade_count = 0
        self.session_start = datetime.now()

    def _find_config(self) -> str:
        """Find telegram config file"""
        possible_paths = [
            "trading_bot/config/telegram_config.json",
            "config/telegram_config.json",
            "../config/telegram_config.json",
            "telegram_config.json"
        ]

        for path in possible_paths:
            if Path(path).exists():
                return path

        # Create default config
        default_path = "trading_bot/config/telegram_config.json"
        Path(default_path).parent.mkdir(parents=True, exist_ok=True)
        
        default_config = {
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "chat_id": "YOUR_CHAT_ID_HERE",
            "enabled": False,
            "parse_mode": "HTML"
        }
        
        with open(default_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        return default_path

    def _load_config(self) -> Dict:
        """Load Telegram configuration"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Validate required fields
            if config.get("bot_token") == "YOUR_BOT_TOKEN_HERE":
                logger.warning("⚠️  Telegram bot token not configured")
                config["enabled"] = False
            
            if config.get("chat_id") == "YOUR_CHAT_ID_HERE":
                logger.warning("⚠️  Telegram chat ID not configured")
                config["enabled"] = False
            
            return config
        
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            return {"enabled": False}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {"enabled": False}

    async def initialize(self):
        """Initialize Telegram bot"""
        if not self.config.get("enabled", False):
            logger.info("📝 Trade journaling to console only (Telegram disabled)")
            return

        telegram_config = TelegramConfig(
            bot_token=self.config["bot_token"],
            chat_id=self.config["chat_id"],
            enabled=True,
            parse_mode=self.config.get("parse_mode", "HTML")
        )

        self.notifier = TelegramNotifier(telegram_config)
        await self.notifier.initialize()
        
        self.alerts = TradeAlerts(self.notifier)
        self.initialized = True
        
        logger.info("✓ Trade journal with Telegram initialized")

    async def log_trade_entry(self, 
                              signal_type: str,
                              symbol: str,
                              price: float,
                              sl: float,
                              tp: float,
                              quantity: float,
                              capital: float,
                              entry_reason: str = "signal",
                              ob_info: Dict = None):
        """
        Log trade entry with detailed information

        Args:
            signal_type: LONG or SHORT
            symbol: Trading pair
            price: Entry price
            sl: Stop loss
            tp: Take profit
            quantity: Position size
            capital: Current capital
            entry_reason: Reason for entry
            ob_info: Order block information
        """
        self.trade_count += 1

        # Calculate metrics
        risk_amount = abs(price - sl) * quantity
        risk_percent = (risk_amount / capital) * 100
        reward_amount = abs(tp - price) * quantity
        
        if signal_type == "LONG":
            rr_ratio = (tp - price) / (price - sl) if price != sl else 0
        else:
            rr_ratio = (price - tp) / (sl - price) if sl != price else 0

        # Console output
        print("\n" + "="*60)
        print(f"{'🟢' if signal_type == 'LONG' else '🔴'} TRADE #{self.trade_count} - {signal_type} ENTRY")
        print("="*60)
        print(f"Symbol:        {symbol}")
        print(f"Entry Price:   ${price:,.4f}")
        print(f"Stop Loss:     ${sl:,.4f}")
        print(f"Take Profit:   ${tp:,.4f}")
        print(f"Quantity:      {quantity:.6f}")
        print(f"Position Size: ${price * quantity:,.2f}")
        print(f"Risk Amount:   ${risk_amount:,.2f} ({risk_percent:.2f}%)")
        print(f"Reward Amount: ${reward_amount:,.2f}")
        print(f"Risk/Reward:   1:{rr_ratio:.2f}")
        print(f"Capital:       ${capital:,.2f}")
        print(f"Reason:        {entry_reason}")
        
        if ob_info:
            print(f"\n📊 Order Block Info:")
            print(f"   Type:   {ob_info.get('type', 'N/A')}")
            print(f"   Range:  ${ob_info.get('bottom', 0):,.2f} - ${ob_info.get('top', 0):,.2f}")
            print(f"   State:  {ob_info.get('state', 'N/A')}")
        
        print(f"Time:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")

        # Send to Telegram
        if self.initialized and self.config.get("notify_on_entry", True):
            # Build detailed message
            emoji = "🟢" if signal_type == "LONG" else "🔴"
            
            text = f"""
{emoji} <b>TRADE #{self.trade_count} - {signal_type} ENTRY</b>

<b>📈 Position Details</b>
Symbol: {symbol}
Entry: ${price:,.4f}
Stop Loss: ${sl:,.4f} ({abs(price - sl) / price * 100:.2f}%)
Take Profit: ${tp:,.4f} ({abs(tp - price) / price * 100:.2f}%)

<b>💰 Risk Management</b>
Quantity: {quantity:.6f}
Position Size: ${price * quantity:,.2f}
Risk: ${risk_amount:,.2f} ({risk_percent:.2f}%)
Reward: ${reward_amount:,.2f}
R:R Ratio: 1:{rr_ratio:.2f}

<b>💼 Account</b>
Capital: ${capital:,.2f}
Reason: {entry_reason}
"""
            
            if ob_info:
                text += f"""
<b>📊 Order Block</b>
Type: {ob_info.get('type', 'N/A')}
Range: ${ob_info.get('bottom', 0):,.2f} - ${ob_info.get('top', 0):,.2f}
State: {ob_info.get('state', 'N/A')}
"""
            
            text += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            try:
                await self.notifier.send_message(
                    text, 
                    disable_notification=self.config.get("quiet_mode", False)
                )
            except Exception as e:
                logger.error(f"Failed to send entry notification: {e}")

    async def log_trade_exit(self,
                             signal_type: str,
                             symbol: str,
                             entry_price: float,
                             exit_price: float,
                             quantity: float,
                             pnl: float,
                             pnl_percent: float,
                             exit_reason: str,
                             duration_bars: int,
                             capital: float,
                             sl: float = None,
                             tp: float = None):
        """
        Log trade exit with comprehensive details

        Args:
            signal_type: LONG or SHORT
            symbol: Trading pair
            entry_price: Entry price
            exit_price: Exit price
            quantity: Position size
            pnl: Profit/Loss in dollars
            pnl_percent: Profit/Loss percentage
            exit_reason: Reason for exit (tp, sl, reversal, etc)
            duration_bars: Number of bars in trade
            capital: Current capital after trade
            sl: Stop loss level
            tp: Take profit level
        """
        # Determine outcome
        is_win = pnl > 0
        emoji = "✅" if is_win else "❌"
        outcome = "WIN" if is_win else "LOSS"

        # Console output
        print("\n" + "="*60)
        print(f"{emoji} TRADE #{self.trade_count} - {outcome}")
        print("="*60)
        print(f"Symbol:        {symbol}")
        print(f"Type:          {signal_type}")
        print(f"Entry Price:   ${entry_price:,.4f}")
        print(f"Exit Price:    ${exit_price:,.4f}")
        print(f"Quantity:      {quantity:.6f}")
        print(f"PnL:           {'$' if pnl >= 0 else '-$'}{abs(pnl):,.2f} ({pnl_percent:+.2f}%)")
        print(f"Exit Reason:   {exit_reason.upper()}")
        print(f"Duration:      {duration_bars} bars")
        print(f"New Capital:   ${capital:,.2f}")
        
        if sl and tp:
            print(f"Original SL:   ${sl:,.4f}")
            print(f"Original TP:   ${tp:,.4f}")
        
        print(f"Time:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60 + "\n")

        # Send to Telegram
        if self.initialized and self.config.get("notify_on_exit", True):
            pnl_emoji = "+" if pnl >= 0 else ""
            
            text = f"""
{emoji} <b>TRADE #{self.trade_count} - {outcome}</b>

<b>📊 Trade Summary</b>
Symbol: {symbol}
Type: {signal_type}
Entry: ${entry_price:,.4f}
Exit: ${exit_price:,.4f}
Quantity: {quantity:.6f}

<b>💵 Results</b>
PnL: {pnl_emoji}${pnl:,.2f} ({pnl_percent:+.2f}%)
Exit Reason: {exit_reason.upper()}
Duration: {duration_bars} bars

<b>💼 Account</b>
Capital: ${capital:,.2f}
"""
            
            if sl and tp:
                text += f"""
<b>🎯 Targets</b>
Stop Loss: ${sl:,.4f}
Take Profit: ${tp:,.4f}
"""
            
            text += f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            try:
                await self.notifier.send_message(
                    text,
                    disable_notification=self.config.get("quiet_mode", False)
                )
            except Exception as e:
                logger.error(f"Failed to send exit notification: {e}")

    async def send_session_summary(self, 
                                   total_trades: int,
                                   win_rate: float,
                                   total_pnl: float,
                                   total_return: float,
                                   initial_capital: float,
                                   final_capital: float,
                                   max_drawdown: float,
                                   profit_factor: float = None):
        """
        Send session summary

        Args:
            total_trades: Total number of trades
            win_rate: Win rate percentage
            total_pnl: Total PnL in dollars
            total_return: Total return percentage
            initial_capital: Starting capital
            final_capital: Ending capital
            max_drawdown: Maximum drawdown percentage
            profit_factor: Profit factor
        """
        if not self.initialized or not self.config.get("send_summary", True):
            return

        session_duration = datetime.now() - self.session_start
        emoji = "🎉" if total_pnl > 0 else "📉"

        text = f"""
{emoji} <b>TRADING SESSION SUMMARY</b>

<b>📊 Performance</b>
Total Trades: {total_trades}
Win Rate: {win_rate:.1f}%
Total PnL: ${total_pnl:+,.2f}
Total Return: {total_return:+.2f}%

<b>💼 Capital</b>
Initial: ${initial_capital:,.2f}
Final: ${final_capital:,.2f}
Max Drawdown: {max_drawdown:.2f}%
"""
        
        if profit_factor:
            text += f"Profit Factor: {profit_factor:.2f}\n"
        
        text += f"""
<b>⏱️ Session</b>
Duration: {session_duration}
Started: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}
Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        try:
            await self.notifier.send_message(text)
        except Exception as e:
            logger.error(f"Failed to send session summary: {e}")

    async def send_orderblock_detected(self, 
                                      ob_type: str,
                                      symbol: str,
                                      price_range: tuple,
                                      current_price: float,
                                      state: str):
        """
        Send order block detection notification

        Args:
            ob_type: bullish or bearish
            symbol: Trading pair
            price_range: (bottom, top) tuple
            current_price: Current price
            state: ACTIVE, MITIGATED, etc
        """
        if not self.initialized or not self.config.get("notify_on_orderblock", False):
            return

        emoji = "🟢" if ob_type == "bullish" else "🔴"
        bottom, top = price_range
        width = ((top - bottom) / bottom) * 100

        text = f"""
{emoji} <b>{ob_type.upper()} ORDER BLOCK DETECTED</b>

<b>Symbol:</b> {symbol}
<b>Range:</b> ${bottom:,.2f} - ${top:,.2f}
<b>Width:</b> {width:.2f}%
<b>Current Price:</b> ${current_price:,.2f}
<b>State:</b> {state}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        try:
            await self.notifier.send_message(
                text,
                disable_notification=True  # OBs are informational
            )
        except Exception as e:
            logger.error(f"Failed to send OB notification: {e}")

    async def shutdown(self):
        """Shutdown journal"""
        if self.notifier:
            await self.notifier.shutdown()


# ============================================================================
# SYNCHRONOUS WRAPPER (for backtest engine integration)
# ============================================================================

class TradeJournalSync:
    """
    Synchronous wrapper for TradeJournal (for non-async code)
    """

    def __init__(self, config_path: str = None):
        self.journal = TradeJournal(config_path)
        self.loop = None

    def initialize(self):
        """Initialize journal"""
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        self.loop.run_until_complete(self.journal.initialize())

    def log_trade_entry(self, **kwargs):
        """Log trade entry"""
        self.loop.run_until_complete(
            self.journal.log_trade_entry(**kwargs)
        )

    def log_trade_exit(self, **kwargs):
        """Log trade exit"""
        self.loop.run_until_complete(
            self.journal.log_trade_exit(**kwargs)
        )

    def send_session_summary(self, **kwargs):
        """Send session summary"""
        self.loop.run_until_complete(
            self.journal.send_session_summary(**kwargs)
        )

    def send_orderblock_detected(self, **kwargs):
        """Send OB notification"""
        self.loop.run_until_complete(
            self.journal.send_orderblock_detected(**kwargs)
        )

    def shutdown(self):
        """Shutdown journal"""
        self.loop.run_until_complete(self.journal.shutdown())
