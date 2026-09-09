"""
MT5 Live Trader
===============
Live trading on MT5 (Exness trial account) using MT5Executor + MT5DataProvider.
Runs RegimeFilteredOB strategy with all filters (vol, OFI, trailing stop).
"""

import json
import time
from datetime import datetime
from typing import Dict, Optional, List
from pathlib import Path

import requests

from ..execution.mt5_executor import MT5Executor, TradeResult, Position, PositionStatus
from ..data.mt5_provider import MT5DataProvider
from ..config.settings import MT5Config, NotificationConfig


class MT5LiveTrader:
    """Live trading on MT5 using RegimeFilteredOB strategy."""

    def __init__(self,
                 executor: MT5Executor,
                 provider: MT5DataProvider,
                 strategy,
                 config: Dict = None):
        self.executor = executor
        self.provider = provider
        self.strategy = strategy
        self.config = config or {}

        self.symbol = executor.symbol
        self.position: Optional[Position] = None
        self.trades: List[Dict] = []
        self.trade_id = 0

        self.telegram_token = self.config.get('telegram_token', '')
        self.telegram_chat_id = self.config.get('telegram_chat_id', '')
        self.send_telegram = self.config.get('send_telegram', True)

        self.persistence_path = self.config.get('persistence_path', 'paper_trades.json')
        self.check_interval = self.config.get('check_interval', 3600)

        self._load_trades()

    def _load_trades(self):
        """Load trade history from JSON."""
        path = Path(self.persistence_path)
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.trades = data.get('trades', [])
                    self.trade_id = data.get('trade_id', 0)
            except (json.JSONDecodeError, KeyError):
                self.trades = []
                self.trade_id = 0

    def _save_trades(self):
        """Save trade history to JSON."""
        path = Path(self.persistence_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        total_pnl = sum(t.get('pnl', 0) for t in self.trades)
        wins = [t for t in self.trades if t.get('pnl', 0) > 0]
        losses = [t for t in self.trades if t.get('pnl', 0) <= 0]

        data = {
            'trades': self.trades,
            'trade_id': self.trade_id,
            'summary': {
                'total_trades': len(self.trades),
                'winning_trades': len(wins),
                'losing_trades': len(losses),
                'win_rate': len(wins) / max(len(self.trades), 1) * 100,
                'total_pnl': total_pnl,
            }
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def send_message(self, message: str):
        """Send notification to Telegram."""
        if not self.send_telegram or not self.telegram_token or not self.telegram_chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram error: {e}")

    def _position_side(self) -> str:
        """Get current position side as string."""
        if not self.position:
            return 'FLAT'
        return 'LONG' if self.position.side == PositionStatus.LONG else 'SHORT'

    def _open_position(self, signal: Dict) -> bool:
        """Open position based on strategy signal."""
        side = signal['signal']
        sl = signal.get('sl')
        tp = signal.get('tp')

        mt5_side = 'BUY' if side == 'LONG' else 'SELL'

        result = self.executor.create_order(
            side=mt5_side,
            order_type='MARKET',
            volume=0.01,
            sl=sl,
            tp=tp,
        )

        if not result.success:
            print(f"Order failed: {result.error}")
            self.send_message(f"❌ Order failed: {result.error}")
            return False

        self.position = self.executor.get_position_by_ticket(result.ticket)
        self.trade_id += 1

        trade = {
            'id': self.trade_id,
            'ticket': result.ticket,
            'side': side,
            'entry_price': result.fill_price,
            'entry_time': datetime.now().isoformat(),
            'sl': sl,
            'tp': tp,
            'volume': 0.01,
        }
        self.trades.append(trade)
        self._save_trades()

        msg = (
            f"🔔 <b>{side}</b> {self.symbol}\n"
            f"Entry: {result.fill_price:.2f}\n"
            f"SL: {sl:.2f}\n"
            f"TP: {tp:.2f}\n"
            f"Lot: 0.01\n"
            f"Ticket: {result.ticket}"
        )
        print(msg.replace('<b>', '').replace('</b>', ''))
        self.send_message(msg)
        return True

    def _close_position(self, reason: str = 'signal') -> bool:
        """Close current position."""
        if not self.position:
            return False

        result = self.executor.close_position(self.position.ticket)
        if not result.success:
            print(f"Close failed: {result.error}")
            return False

        exit_price = result.fill_price
        if self.position.side == PositionStatus.LONG:
            pnl = (exit_price - self.position.price_open) * self.position.volume
        else:
            pnl = (self.position.price_open - exit_price) * self.position.volume

        for trade in reversed(self.trades):
            if trade.get('ticket') == self.position.ticket and 'exit_price' not in trade:
                trade['exit_price'] = exit_price
                trade['exit_time'] = datetime.now().isoformat()
                trade['pnl'] = pnl
                trade['exit_reason'] = reason
                break

        self._save_trades()

        side = 'LONG' if self.position.side == PositionStatus.LONG else 'SHORT'
        emoji = '🟢' if pnl > 0 else '🔴'
        msg = (
            f"{emoji} <b>CLOSE {side}</b> {self.symbol}\n"
            f"Entry: {self.position.price_open:.2f}\n"
            f"Exit: {exit_price:.2f}\n"
            f"PnL: {pnl:+.2f}\n"
            f"Reason: {reason}"
        )
        print(msg.replace('<b>', '').replace('</b>', ''))
        self.send_message(msg)

        self.position = None
        return True

    def _update_position(self):
        """Check and update current position status."""
        if not self.position:
            return

        positions = self.executor.get_positions()
        if not positions:
            self._close_position(reason='sl_tp_hit')
            return

        found = False
        for pos in positions:
            if pos.ticket == self.position.ticket:
                self.position = pos
                found = True
                break

        if not found:
            self._close_position(reason='sl_tp_hit')

    def _send_daily_summary(self):
        """Send daily trade summary to Telegram."""
        today = datetime.now().date().isoformat()
        today_trades = [t for t in self.trades if t.get('entry_time', '').startswith(today)]

        if not today_trades:
            return

        total_pnl = sum(t.get('pnl', 0) for t in today_trades if 'pnl' in t)
        wins = len([t for t in today_trades if t.get('pnl', 0) > 0])
        losses = len([t for t in today_trades if t.get('pnl', 0) <= 0 and 'pnl' in t])

        account = self.executor.get_balance()

        msg = (
            f"📊 <b>Daily Summary</b> {today}\n"
            f"Trades: {len(today_trades)}\n"
            f"Wins: {wins} | Losses: {losses}\n"
            f"PnL: {total_pnl:+.2f}\n"
            f"Balance: {account:.2f}"
        )
        print(msg.replace('<b>', '').replace('</b>', ''))
        self.send_message(msg)

    def run(self):
        """Main trading loop."""
        print(f"\n{'='*60}")
        print(f"MT5 LIVE TRADER - {self.symbol}")
        print(f"{'='*60}")

        if not self.executor.connect():
            print("Failed to connect MT5 executor")
            return

        if not self.provider.connect():
            print("Failed to connect MT5 provider")
            return

        account = self.executor.get_balance()
        print(f"Balance: {account:.2f}")
        print(f"Check interval: {self.check_interval}s")
        print(f"Strategy: RegimeFilteredOB")
        print(f"{'='*60}\n")

        self.send_message(
            f"🚀 <b>MT5 Live Trader Started</b>\n"
            f"Symbol: {self.symbol}\n"
            f"Balance: {account:.2f}\n"
            f"Interval: {self.check_interval}s"
        )

        last_summary_hour = -1
        strategy_initialized = False

        while True:
            try:
                df = self.provider.fetch_recent(days=7)
                if df.empty:
                    print("No data, waiting...")
                    time.sleep(60)
                    continue

                if not strategy_initialized:
                    self.strategy.on_init(df)
                    strategy_initialized = True
                    print(f"Strategy initialized with {len(df)} bars")

                self._update_position()

                signal = self.strategy.on_bar(df, self._position_side())

                sig = signal.get('signal', 'FLAT')
                if sig in ('LONG', 'SHORT'):
                    if self.position:
                        if (sig == 'LONG' and self.position.side == PositionStatus.SHORT) or \
                           (sig == 'SHORT' and self.position.side == PositionStatus.LONG):
                            self._close_position(reason='reversal')
                            self._open_position(signal)
                        else:
                            pass
                    else:
                        self._open_position(signal)
                elif sig == 'FLAT' and self.position:
                    current_idx = len(df) - 1
                    current = df.iloc[current_idx]
                    atr = signal.get('atr', current['close'] * 0.02)

                    if self.position.side == PositionStatus.LONG:
                        trail_sl = current['close'] - atr * 0.5
                        if trail_sl > self.position.sl and trail_sl > self.position.price_open:
                            self.executor.modify_sl_tp(self.position.ticket, trail_sl, self.position.tp)
                            self.position = self.executor.get_position_by_ticket(self.position.ticket)
                    elif self.position.side == PositionStatus.SHORT:
                        trail_sl = current['close'] + atr * 0.5
                        if trail_sl < self.position.sl and trail_sl < self.position.price_open:
                            self.executor.modify_sl_tp(self.position.ticket, trail_sl, self.position.tp)
                            self.position = self.executor.get_position_by_ticket(self.position.ticket)

                current_hour = datetime.now().hour
                if current_hour == 0 and last_summary_hour != 0:
                    self._send_daily_summary()
                    last_summary_hour = 0

                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                print("\nStopping...")
                if self.position:
                    self._close_position(reason='shutdown')
                self.send_message("🛑 <b>MT5 Live Trader Stopped</b>")
                break
            except Exception as e:
                print(f"Error: {e}")
                self.send_message(f"⚠️ Error: {e}")
                time.sleep(60)
