"""
Backtest Engine
================
Backtest trading strategies with realistic simulation
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Callable, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

try:
    from trading_bot.utils.trade_journal import TradeJournalSync
except ImportError:
    TradeJournalSync = None

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PositionSide(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    """Trading order"""
    timestamp: datetime
    side: PositionSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_time: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status.value,
            "filled_price": self.filled_price,
            "filled_time": self.filled_time.isoformat() if self.filled_time else None
        }


@dataclass
class Trade:
    """Completed trade"""
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    side: PositionSide
    quantity: float
    pnl: float
    pnl_percent: float
    duration: int  # bars
    entry_order: Order
    exit_reason: str  # "tp", "sl", "manual", "signal"
    entry_reason: str = "signal"  # reason for entry

    def to_dict(self) -> Dict:
        return {
            "entry_time": self.entry_time.isoformat(),
            "entry_price": self.entry_price,
            "exit_time": self.exit_time.isoformat(),
            "exit_price": self.exit_price,
            "side": self.side.value,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "duration": self.duration,
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason
        }


@dataclass
class BacktestResult:
    """Backtest results"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    avg_trade_duration: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": self.total_pnl,
            "total_pnl_percent": self.total_pnl_percent,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "avg_trade_duration": self.avg_trade_duration,
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": self.equity_curve
        }


class Strategy:
    """
    Base strategy class

    Implement these methods:
    - on_init(): Setup indicators, etc.
    - on_bar(df): Called each bar, return signals
    """

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name
        self.indicators = {}
        self.parameters = {}

    def on_init(self, df: pd.DataFrame):
        """Initialize strategy with data"""
        pass

    def on_bar(self, df: pd.DataFrame, position: PositionSide) -> Dict:
        """
        Generate signals for current bar

        Returns:
            Dict with keys: 'signal' (LONG/SHORT/FLAT), 'sl', 'tp', 'size'
        """
        return {
            'signal': 'FLAT',
            'sl': None,
            'tp': None,
            'size': 0.0
        }

    def set_parameters(self, **kwargs):
        """Set strategy parameters"""
        self.parameters.update(kwargs)


class BacktestEngine:
    """
    Backtesting engine with realistic simulation
    """

    def __init__(self,
                 initial_capital: float = 10000.0,
                 fee_percent: float = 0.001,  # 0.1% fee
                 slippage_percent: float = 0.0005,  # 0.05% slippage
                 max_position_size: float = 1.0,  # 100% of capital
                 enable_journal: bool = True):  # Enable trade journaling
        self.initial_capital = initial_capital
        self.fee_percent = fee_percent
        self.slippage_percent = slippage_percent
        self.max_position_size = max_position_size
        self.enable_journal = enable_journal

        self.capital = initial_capital
        self.position: PositionSide = PositionSide.FLAT
        self.position_quantity = 0.0
        self.entry_price = 0.0
        self.entry_time = None
        self.entry_bar_idx = 0  # Track bar index for duration calculation
        self.journal = None  # Trade journal instance
        self.entry_order = None

        self.trades: List[Trade] = []
        self.orders: List[Order] = []
        self.equity_curve = []
        self.current_bar_idx = 0

    def run(self,
            df: pd.DataFrame,
            strategy: Strategy,
            verbose: bool = True) -> BacktestResult:
        """
        Run backtest

        Args:
            df: DataFrame with OHLCV data
            strategy: Strategy instance
            verbose: Print progress

        Returns:
            BacktestResult with performance metrics
        """
        # Initialize trade journal
        if self.enable_journal and TradeJournalSync:
            try:
                self.journal = TradeJournalSync()
                self.journal.initialize()
                self.current_symbol = getattr(df, 'symbol', 'BTC/USDT')
                logger.info("✓ Trade journal enabled")
            except Exception as e:
                logger.warning(f"Trade journal initialization failed: {e}")
                self.journal = None
        
        # Initialize
        self.capital = self.initial_capital
        self.position = PositionSide.FLAT
        self.trades = []
        self.orders = []
        self.equity_curve = []
        self.current_bar_idx = 0

        # Initialize strategy
        df = df.copy()
        strategy.on_init(df)

        if verbose:
            print(f"\n{'='*60}")
            print(f"BACKTEST: {strategy.name}")
            print(f"{'='*60}")
            print(f"Period: {df.index[0]} to {df.index[-1]}")
            print(f"Bars: {len(df)}")
            print(f"Initial Capital: ${self.initial_capital:,.2f}")
            print(f"{'='*60}\n")

        # Main loop
        for i, (timestamp, row) in enumerate(df.iterrows()):
            self.current_bar_idx = i

            # Get signal from strategy
            signal = strategy.on_bar(df.iloc[:i+1], self.position)

            # Process signals
            self._process_signal(signal, row)

            # Check SL/TP
            if self.position != PositionSide.FLAT:
                self._check_sl_tp(row)

            # Record equity
            self._record_equity(timestamp, row)

            # Progress update
            if verbose and (i + 1) % 100 == 0:
                print(f"Progress: {i+1}/{len(df)} bars | "
                      f"Capital: ${self.capital:,.2f} | "
                      f"Position: {self.position.value}")

        # Close any open position at end
        if self.position != PositionSide.FLAT:
            last_row = df.iloc[-1]
            self._close_position(last_row, "end_of_data")

        # Calculate results
        result = self._calculate_results()

        if verbose:
            self._print_results(result)
        
        # Send session summary to journal
        if self.journal:
            try:
                self.journal.send_session_summary(
                    total_trades=result.total_trades,
                    win_rate=result.win_rate,
                    total_pnl=result.total_pnl,
                    total_return=result.total_pnl_percent,
                    initial_capital=self.initial_capital,
                    final_capital=self.capital,
                    max_drawdown=result.max_drawdown,
                    profit_factor=result.profit_factor
                )
                self.journal.shutdown()
            except Exception as e:
                logger.error(f"Failed to send journal summary: {e}")

        return result

    def _process_signal(self, signal: Dict, row: pd.Series):
        """Process trading signal"""
        signal_type = signal.get('signal', 'FLAT').upper()

        # Skip if no change
        if signal_type == 'FLAT':
            return

        # Check if already in position
        if self.position != PositionSide.FLAT:
            # Check if trying to reverse
            if (self.position == PositionSide.LONG and signal_type == 'SHORT') or \
               (self.position == PositionSide.SHORT and signal_type == 'LONG'):
                self._close_position(row, "reversal")
            return

        # Calculate position size
        size = signal.get('size', self.max_position_size)
        size = min(size, self.max_position_size)

        # Calculate quantity
        quantity = (self.capital * size) / row['close']

        # Apply slippage
        if signal_type == 'LONG':
            entry_price = row['close'] * (1 + self.slippage_percent)
        else:
            entry_price = row['close'] * (1 - self.slippage_percent)

        # Create order
        order = Order(
            timestamp=row.name if isinstance(row.name, datetime) else datetime.now(),
            side=PositionSide.LONG if signal_type == 'LONG' else PositionSide.SHORT,
            order_type=OrderType.MARKET,
            quantity=quantity,
            stop_loss=signal.get('sl'),
            take_profit=signal.get('tp')
        )
        order.status = OrderStatus.FILLED
        order.filled_price = entry_price
        order.filled_time = row.name if isinstance(row.name, datetime) else datetime.now()

        self.orders.append(order)

        # Open position
        self._open_position(order, row)

    def _open_position(self, order: Order, row: pd.Series):
        """Open a position"""
        # Apply fee
        fee = order.quantity * order.filled_price * self.fee_percent
        self.capital -= fee

        self.position = order.side
        self.position_quantity = order.quantity
        self.entry_price = order.filled_price
        self.entry_time = order.filled_time
        self.entry_bar_idx = self.current_bar_idx  # Store bar index for duration
        self.entry_order = order
        
        # Log trade entry to journal
        if self.journal:
            try:
                symbol = getattr(self, 'current_symbol', 'BTC/USDT')
                self.journal.log_trade_entry(
                    signal_type=order.side.value,
                    symbol=symbol,
                    price=order.filled_price,
                    sl=order.stop_loss if order.stop_loss else 0,
                    tp=order.take_profit if order.take_profit else 0,
                    quantity=order.quantity,
                    capital=self.capital + fee,  # Capital before fee
                    entry_reason="signal"
                )
            except Exception as e:
                logger.error(f"Failed to log trade entry: {e}")

    def _close_position(self, row: pd.Series, reason: str):
        """Close current position"""
        if self.position == PositionSide.FLAT:
            return

        # Calculate exit price with slippage
        if self.position == PositionSide.LONG:
            exit_price = row['close'] * (1 - self.slippage_percent)
        else:
            exit_price = row['close'] * (1 + self.slippage_percent)

        # Calculate PnL
        if self.position == PositionSide.LONG:
            pnl = (exit_price - self.entry_price) * self.position_quantity
        else:
            pnl = (self.entry_price - exit_price) * self.position_quantity

        pnl_percent = pnl / (self.entry_price * self.position_quantity) * 100

        # Apply fee
        fee = self.position_quantity * exit_price * self.fee_percent
        pnl -= fee
        self.capital += pnl

        # Create trade
        trade = Trade(
            entry_time=self.entry_time,
            entry_price=self.entry_price,
            exit_time=row.name if isinstance(row.name, datetime) else datetime.now(),
            exit_price=exit_price,
            side=self.position,
            quantity=self.position_quantity,
            pnl=pnl,
            pnl_percent=pnl_percent,
            duration=self.current_bar_idx - self.entry_bar_idx,
            entry_order=self.entry_order,
            exit_reason=reason,
            entry_reason="signal"
        )

        self.trades.append(trade)
        
        # Log trade exit to journal
        if self.journal:
            try:
                symbol = getattr(self, 'current_symbol', 'BTC/USDT')
                self.journal.log_trade_exit(
                    signal_type=self.position.value,
                    symbol=symbol,
                    entry_price=self.entry_price,
                    exit_price=exit_price,
                    quantity=self.position_quantity,
                    pnl=pnl,
                    pnl_percent=pnl_percent,
                    exit_reason=reason,
                    duration_bars=trade.duration,
                    capital=self.capital,
                    sl=self.entry_order.stop_loss if self.entry_order else None,
                    tp=self.entry_order.take_profit if self.entry_order else None
                )
            except Exception as e:
                logger.error(f"Failed to log trade exit: {e}")

        # Reset position
        self.position = PositionSide.FLAT
        self.position_quantity = 0.0
        self.entry_price = 0.0
        self.entry_time = None
        self.entry_bar_idx = 0
        self.entry_order = None

    def _check_sl_tp(self, row: pd.Series):
        """Check stop loss and take profit"""
        if self.position == PositionSide.FLAT:
            return

        sl = self.entry_order.stop_loss
        tp = self.entry_order.take_profit

        if self.position == PositionSide.LONG:
            if sl and row['low'] <= sl:
                self._close_position(row, "sl")
            elif tp and row['high'] >= tp:
                self._close_position(row, "tp")
        else:  # SHORT
            if sl and row['high'] >= sl:
                self._close_position(row, "sl")
            elif tp and row['low'] <= tp:
                self._close_position(row, "tp")

    def _record_equity(self, timestamp: datetime, row: pd.Series):
        """Record equity for equity curve"""
        # Calculate current equity
        if self.position == PositionSide.FLAT:
            equity = self.capital
        elif self.position == PositionSide.LONG:
            unrealized = (row['close'] - self.entry_price) * self.position_quantity
            equity = self.capital + unrealized
        else:  # SHORT
            unrealized = (self.entry_price - row['close']) * self.position_quantity
            equity = self.capital + unrealized

        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': equity,
            'position': self.position.value
        })

    def _calculate_results(self) -> BacktestResult:
        """Calculate backtest metrics"""
        if not self.trades:
            return BacktestResult()

        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]

        # Calculate drawdown
        equity = [e['equity'] for e in self.equity_curve]
        peak = equity[0]
        max_dd = 0
        for e in equity:
            if e > peak:
                peak = e
            dd = (peak - e) / peak * 100
            if dd > max_dd:
                max_dd = dd

        result = BacktestResult(
            total_trades=len(self.trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / len(self.trades) * 100 if self.trades else 0,
            total_pnl=self.capital - self.initial_capital,
            total_pnl_percent=(self.capital / self.initial_capital - 1) * 100,
            avg_win=sum([t.pnl_percent for t in wins]) / len(wins) if wins else 0,
            avg_loss=sum([t.pnl_percent for t in losses]) / len(losses) if losses else 0,
            best_trade=max([t.pnl_percent for t in self.trades]) if self.trades else 0,
            worst_trade=min([t.pnl_percent for t in self.trades]) if self.trades else 0,
            profit_factor=abs(sum([t.pnl for t in wins]) / sum([t.pnl for t in losses])) if losses else float('inf'),
            max_drawdown=max_dd,
            avg_trade_duration=sum([t.duration for t in self.trades]) / len(self.trades) if self.trades else 0,
            trades=self.trades,
            equity_curve=self.equity_curve
        )

        return result

    def _print_results(self, result: BacktestResult):
        """Print backtest results"""
        print(f"\n{'='*60}")
        print("BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"\n{'Metric':<25} {'Value':>15}")
        print("-" * 42)
        print(f"{'Total Trades':<25} {result.total_trades:>15}")
        print(f"{'Win Rate':<25} {result.win_rate:>14.1f}%")
        print(f"{'Winning Trades':<25} {result.winning_trades:>15}")
        print(f"{'Losing Trades':<25} {result.losing_trades:>15}")
        print(f"{'Total PnL':<25} ${result.total_pnl:>14,.2f}")
        print(f"{'Total Return':<25} {result.total_pnl_percent:>14.2f}%")
        print(f"{'Average Win':<25} +{result.avg_win:>14.2f}%")
        print(f"{'Average Loss':<25} {result.avg_loss:>14.2f}%")
        print(f"{'Best Trade':<25} +{result.best_trade:>14.2f}%")
        print(f"{'Worst Trade':<25} {result.worst_trade:>14.2f}%")
        print(f"{'Profit Factor':<25} {result.profit_factor:>15.2f}")
        print(f"{'Max Drawdown':<25} {result.max_drawdown:>14.2f}%")
        print(f"{'Avg Duration (bars)':<25} {result.avg_trade_duration:>15.1f}")
        print(f"\n{'Final Capital':<25} ${self.capital:>14,.2f}")
        print(f"{'Initial Capital':<25} ${self.initial_capital:>14,.2f}")
        print(f"{'='*60}\n")

    def plot_results(self, result: BacktestResult, save_path: str = None):
        """Plot equity curve and trade markers"""
        fig, axes = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})

        # Get data
        equity_df = pd.DataFrame(result.equity_curve)
        trades_df = pd.DataFrame([t.to_dict() for t in result.trades]) if result.trades else pd.DataFrame()

        # Handle empty equity curve
        if equity_df.empty or 'equity' not in equity_df.columns:
            ax1 = axes[0]
            ax1.axhline(y=self.initial_capital, color='gray', linestyle='--', alpha=0.5)
            ax1.set_title(f'No Trades - Initial Capital: ${self.initial_capital:,.2f}', fontsize=12)
            ax1.set_ylabel('Equity ($)', fontsize=10)
            ax1.grid(True, alpha=0.3)
            
            ax2 = axes[1]
            ax2.set_title('Drawdown', fontsize=10)
            ax2.set_ylabel('DD (%)', fontsize=10)
            ax2.set_xlabel('Bar', fontsize=10)
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            if save_path:
                plt.savefig(save_path, dpi=150, bbox_inches='tight')
                print(f"Chart saved to: {save_path}")
            return fig

        # Price chart
        ax1 = axes[0]
        # This would need price data - simplified for now
        ax1.plot(range(len(equity_df)), equity_df['equity'], 'b-', linewidth=1.5)
        ax1.axhline(y=self.initial_capital, color='gray', linestyle='--', alpha=0.5)

        # Mark trades
        for trade in result.trades:
            color = 'green' if trade.pnl > 0 else 'red'
            marker = '^' if trade.side == PositionSide.LONG else 'v'
            ax1.scatter(trade.entry_time, equity_df.iloc[trade.entry_time]['equity']
                        if hasattr(trade.entry_time, '__index__') else 0,
                        marker=marker, s=100, color=color, zorder=5)

        ax1.set_title(f'Equity Curve - {result.total_trades} Trades | '
                      f'Win Rate: {result.win_rate:.1f}% | '
                      f'Return: {result.total_pnl_percent:.1f}%', fontsize=12)
        ax1.set_ylabel('Equity ($)', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.legend(['Equity', 'Initial'], loc='upper left')

        # Drawdown chart
        ax2 = axes[1]
        equity_vals = equity_df['equity'].values
        peak = np.maximum.accumulate(equity_vals)
        drawdown = (peak - equity_vals) / peak * 100
        ax2.fill_between(range(len(drawdown)), 0, drawdown, alpha=0.3, color='red')
        ax2.set_title('Drawdown', fontsize=10)
        ax2.set_ylabel('DD (%)', fontsize=10)
        ax2.set_xlabel('Bar', fontsize=10)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Chart saved to: {save_path}")

        return fig


# ============================================================================
# STRATEGY TEMPLATES
# ============================================================================

class SMAStrategy(Strategy):
    """Simple SMA crossover strategy"""

    def __init__(self, fast_period: int = 10, slow_period: int = 20):
        super().__init__(f"SMA_{fast_period}_{slow_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_init(self, df: pd.DataFrame):
        df['sma_fast'] = df['close'].rolling(self.fast_period).mean()
        df['sma_slow'] = df['close'].rolling(self.slow_period).mean()

    def on_bar(self, df: pd.DataFrame, position: PositionSide) -> Dict:
        current = df.iloc[-1]
        previous = df.iloc[-2] if len(df) > 1 else current

        # Crossover
        if position == PositionSide.FLAT:
            if previous['sma_fast'] <= previous['sma_slow'] and current['sma_fast'] > current['sma_slow']:
                return {
                    'signal': 'LONG',
                    'sl': current['close'] - (current['close'] - current['low']) * 2,
                    'tp': current['close'] * 1.02,
                    'size': 1.0
                }
        else:
            if previous['sma_fast'] >= previous['sma_slow'] and current['sma_fast'] < current['sma_slow']:
                return {
                    'signal': 'SHORT',
                    'sl': current['close'] + (current['high'] - current['close']) * 2,
                    'tp': current['close'] * 0.98,
                    'size': 1.0
                }

        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Create sample data
    dates = pd.date_range(start='2025-01-01', periods=500, freq='15min')
    import numpy as np

    np.random.seed(42)
    price = 90000
    prices = [price]
    for i in range(499):
        price = price + np.random.randn() * 100
        prices.append(price)

    df = pd.DataFrame({
        'open': prices,
        'high': [p + np.random.rand() * 50 for p in prices],
        'low': [p - np.random.rand() * 50 for p in prices],
        'close': prices,
        'volume': np.random.rand(500) * 1000
    }, index=dates)

    # Run backtest
    strategy = SMAStrategy(10, 20)
    engine = BacktestEngine(initial_capital=10000)
    result = engine.run(df, strategy)

    # Plot
    engine.plot_results(result, save_path='/workspace/charts/backtest_result.png')
