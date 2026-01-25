"""
Live Trading Execution Module
=============================
Execute trades on exchanges in real-time
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json

# CCXT for exchange connectivity
try:
    import ccxt
except ImportError:
    print("Installing ccxt...")
    import subprocess
    subprocess.run(["pip", "install", "ccxt", "-q"])
    import ccxt

from ..data.market_data import DataManager, OHLCV
from ..backtest.engine import PositionSide, Order, OrderStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class PositionStatus(Enum):
    NONE = "none"
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Current position"""
    side: PositionStatus
    quantity: float
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0

    def to_dict(self) -> Dict:
        return {
            'side': self.side.value,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat(),
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'unrealized_pnl': self.unrealized_pnl
        }


@dataclass
class TradeRequest:
    """Trade request from strategy"""
    signal: str  # LONG, SHORT, FLAT
    size: float  # 0-1 (percentage of capital)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    reduce_only: bool = False


@dataclass
class TradeResult:
    """Result of trade execution"""
    success: bool
    order_id: Optional[str]
    fill_price: Optional[float]
    quantity: Optional[float]
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ExchangeExecutor:
    """
    Execute orders on exchange
    """

    def __init__(self,
                 exchange_id: str,
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None,
                 testnet: bool = True,
                 symbol: str = "BTC/USDT"):
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.testnet = testnet

        # Initialize exchange
        exchange_class = getattr(ccxt, exchange_id)

        kwargs = {
            'enableRateLimit': True,
            'timeout': 30000,
        }

        if api_key and api_secret:
            kwargs['apiKey'] = api_key
            kwargs['secret'] = api_secret

        self.exchange = exchange_class(kwargs)

        # Set sandbox/testnet
        if testnet:
            if hasattr(self.exchange, 'set_sandbox_mode'):
                self.exchange.set_sandbox_mode(True)

        # Get precision
        self.market = self.exchange.market(self.symbol)
        self.precision = self.market['precision']
        self.min_amount = self.market['limits']['amount']['min']
        self.min_cost = self.market['limits']['cost']['min']

    def get_balance(self, currency: str = "USDT") -> float:
        """Get available balance"""
        try:
            balance = self.exchange.fetch_balance()
            return balance['free'].get(currency, 0.0)
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    def get_current_price(self) -> float:
        """Get current ticker price"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Error fetching price: {e}")
            return 0.0

    def create_order(self,
                     side: OrderSide,
                     order_type: OrderType,
                     amount: float,
                     price: Optional[float] = None,
                     params: Optional[Dict] = None) -> Dict:
        """
        Create order on exchange

        Args:
            side: BUY or SELL
            order_type: Order type
            amount: Amount to trade
            price: Limit price (optional)
            params: Additional parameters

        Returns:
            Exchange order response
        """
        try:
            order = self.exchange.create_order(
                symbol=self.symbol,
                type=order_type.value,
                side=side.value,
                amount=amount,
                price=price,
                params=params or {}
            )
            logger.info(f"Order created: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            self.exchange.cancel_order(order_id, self.symbol)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    def get_order_status(self, order_id: str) -> Dict:
        """Get order status"""
        try:
            return self.exchange.fetch_order(order_id, self.symbol)
        except Exception as e:
            logger.error(f"Error fetching order: {e}")
            return {}

    def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        try:
            return self.exchange.fetch_open_orders(self.symbol)
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []

    def get_positions(self) -> List[Dict]:
        """Get open positions (for margin trading)"""
        try:
            if hasattr(self.exchange, 'fetch_positions'):
                return self.exchange.fetch_positions([self.symbol])
            return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []


class LiveTrader:
    """
    Live trading bot with risk management
    """

    def __init__(self,
                 executor: ExchangeExecutor,
                 initial_capital: float = 10000.0,
                 risk_per_trade: float = 0.02,  # 2% per trade
                 max_daily_loss: float = 0.05,   # 5% max daily loss
                 max_positions: int = 3):
        self.executor = executor
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_positions = max_positions

        # State
        self.position: Optional[Position] = None
        self.capital = initial_capital
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.day_start = datetime.now().date()
        self.daily_loss_limit = initial_capital * max_daily_loss

        # Callbacks
        self.on_signal: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

        # Running state
        self.running = False
        self.tasks = []

    def calculate_position_size(self,
                                 entry_price: float,
                                 stop_loss: float,
                                 risk_percent: float = None) -> float:
        """
        Calculate position size based on risk

        Args:
            entry_price: Planned entry price
            stop_loss: Stop loss price
            risk_percent: Risk % of capital (default: self.risk_per_trade)

        Returns:
            Position size in base currency
        """
        risk_percent = risk_percent or self.risk_per_trade

        # Calculate risk amount
        risk_amount = self.capital * risk_percent

        # Calculate stop loss distance
        if entry_price > stop_loss:  # Long
            sl_distance = entry_price - stop_loss
        else:  # Short
            sl_distance = stop_loss - entry_price

        if sl_distance == 0:
            return 0.0

        # Calculate quantity
        quantity = risk_amount / sl_distance

        # Round to precision
        if 'amount' in self.executor.precision:
            precision = self.executor.precision['amount']
            quantity = round(quantity / precision) * precision

        # Check minimum
        quantity = max(quantity, self.executor.min_amount)

        return quantity

    def execute_signal(self, signal: Dict) -> TradeResult:
        """
        Execute trading signal

        Args:
            signal: Signal dict with 'signal', 'sl', 'tp', 'size'

        Returns:
            TradeResult
        """
        signal_type = signal.get('signal', 'FLAT').upper()

        # Check daily loss limit
        if self.daily_pnl <= -self.daily_loss_limit:
            logger.warning("Daily loss limit reached. No more trades.")
            return TradeResult(
                success=False,
                order_id=None,
                fill_price=None,
                quantity=None,
                error="Daily loss limit reached"
            )

        # Check max positions
        if self.position is not None and self.trades_today >= self.max_positions:
            logger.warning("Max trades today reached.")
            return TradeResult(
                success=False,
                order_id=None,
                fill_price=None,
                quantity=None,
                error="Max trades today reached"
            )

        # Close existing position if signal is opposite
        if self.position is not None:
            if (self.position.side == PositionStatus.LONG and signal_type == 'SHORT') or \
               (self.position.side == PositionStatus.SHORT and signal_type == 'LONG'):
                self.close_position("reversal")

        # Process new signal
        if signal_type == 'FLAT':
            return TradeResult(success=True, order_id=None, fill_price=None, quantity=None)

        if signal_type == 'LONG':
            return self._open_long(signal)
        elif signal_type == 'SHORT':
            return self._open_short(signal)

        return TradeResult(success=False, order_id=None, fill_price=None, quantity=None)

    def _open_long(self, signal: Dict) -> TradeResult:
        """Open long position"""
        if self.position is not None:
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error="Already in position")

        current_price = self.executor.get_current_price()
        sl = signal.get('stop_loss', current_price * 0.98)
        tp = signal.get('take_profit', current_price * 1.04)
        size = signal.get('size', 0.5)  # Default 50% of risk amount

        # Calculate quantity
        risk_amount = self.capital * self.risk_per_trade * size
        sl_distance = current_price - sl
        if sl_distance <= 0:
            sl = current_price * 0.98
            sl_distance = current_price * 0.02

        quantity = risk_amount / sl_distance

        # Round to precision
        if 'amount' in self.executor.precision:
            precision = self.executor.precision['amount']
            quantity = round(quantity / precision) * precision

        if quantity < self.executor.min_amount:
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error="Amount too small")

        try:
            # Create order
            order = self.executor.create_order(
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=quantity
            )

            # Set SL/TP
            if sl or tp:
                self._set_sl_tp(quantity, sl, tp)

            # Update position
            self.position = Position(
                side=PositionStatus.LONG,
                quantity=quantity,
                entry_price=current_price,
                entry_time=datetime.now(),
                stop_loss=sl,
                take_profit=tp
            )

            self.trades_today += 1

            logger.info(f"Opened LONG: {quantity} @ {current_price}")

            if self.on_trade:
                self.on_trade({
                    'action': 'open_long',
                    'quantity': quantity,
                    'price': current_price,
                    'sl': sl,
                    'tp': tp
                })

            return TradeResult(
                success=True,
                order_id=order['id'],
                fill_price=current_price,
                quantity=quantity
            )

        except Exception as e:
            if self.on_error:
                self.on_error(e)
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error=str(e))

    def _open_short(self, signal: Dict) -> TradeResult:
        """Open short position"""
        if self.position is not None:
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error="Already in position")

        current_price = self.executor.get_current_price()
        sl = signal.get('stop_loss', current_price * 1.02)
        tp = signal.get('take_profit', current_price * 0.96)
        size = signal.get('size', 0.5)

        # Calculate quantity
        risk_amount = self.capital * self.risk_per_trade * size
        sl_distance = sl - current_price
        if sl_distance <= 0:
            sl = current_price * 1.02
            sl_distance = current_price * 0.02

        quantity = risk_amount / sl_distance

        # Round to precision
        if 'amount' in self.executor.precision:
            precision = self.executor.precision['amount']
            quantity = round(quantity / precision) * precision

        if quantity < self.executor.min_amount:
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error="Amount too small")

        try:
            order = self.executor.create_order(
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=quantity
            )

            self.position = Position(
                side=PositionStatus.SHORT,
                quantity=quantity,
                entry_price=current_price,
                entry_time=datetime.now(),
                stop_loss=sl,
                take_profit=tp
            )

            self.trades_today += 1

            logger.info(f"Opened SHORT: {quantity} @ {current_price}")

            if self.on_trade:
                self.on_trade({
                    'action': 'open_short',
                    'quantity': quantity,
                    'price': current_price,
                    'sl': sl,
                    'tp': tp
                })

            return TradeResult(
                success=True,
                order_id=order['id'],
                fill_price=current_price,
                quantity=quantity
            )

        except Exception as e:
            if self.on_error:
                self.on_error(e)
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error=str(e))

    def close_position(self, reason: str = "manual") -> TradeResult:
        """Close current position"""
        if self.position is None:
            return TradeResult(success=True, order_id=None, fill_price=None, quantity=None)

        current_price = self.executor.get_current_price()

        try:
            side = OrderSide.SELL if self.position.side == PositionStatus.LONG else OrderSide.BUY

            order = self.executor.create_order(
                side=side,
                order_type=OrderType.MARKET,
                amount=self.position.quantity
            )

            # Calculate PnL
            if self.position.side == PositionStatus.LONG:
                pnl = (current_price - self.position.entry_price) * self.position.quantity
            else:
                pnl = (self.position.entry_price - current_price) * self.position.quantity

            self.capital += pnl
            self.daily_pnl += pnl

            logger.info(f"Closed position ({reason}): PnL = ${pnl:.2f}")

            if self.on_trade:
                self.on_trade({
                    'action': 'close',
                    'reason': reason,
                    'pnl': pnl,
                    'price': current_price
                })

            closed_position = self.position
            self.position = None

            return TradeResult(
                success=True,
                order_id=order['id'],
                fill_price=current_price,
                quantity=closed_position.quantity
            )

        except Exception as e:
            if self.on_error:
                self.on_error(e)
            return TradeResult(success=False, order_id=None, fill_price=None, quantity=None, error=str(e))

    def _set_sl_tp(self, quantity: float, sl: float, tp: Optional[float]):
        """Set stop loss and take profit orders"""
        try:
            # Create OCO order (One Cancels Other)
            if self.position and self.position.side == PositionStatus.LONG:
                # For long: SL below, TP above
                if sl:
                    self.executor.create_order(
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP_LOSS,
                        amount=quantity,
                        price=sl,
                        params={'triggerPrice': sl}
                    )
                if tp:
                    self.executor.create_order(
                        side=OrderSide.SELL,
                        order_type=OrderType.TAKE_PROFIT,
                        amount=quantity,
                        price=tp,
                        params={'triggerPrice': tp}
                    )
            else:
                # For short: SL above, TP below
                if sl:
                    self.executor.create_order(
                        side=OrderSide.BUY,
                        order_type=OrderType.STOP_LOSS,
                        amount=quantity,
                        price=sl,
                        params={'triggerPrice': sl}
                    )
                if tp:
                    self.executor.create_order(
                        side=OrderSide.BUY,
                        order_type=OrderType.TAKE_PROFIT,
                        amount=quantity,
                        price=tp,
                        params={'triggerPrice': tp}
                    )
        except Exception as e:
            logger.warning(f"Could not set SL/TP: {e}")

    def update_position(self):
        """Update position (check SL/TP)"""
        if self.position is None:
            return

        current_price = self.executor.get_current_price()

        # Update unrealized PnL
        if self.position.side == PositionStatus.LONG:
            self.position.unrealized_pnl = (
                (current_price - self.position.entry_price) * self.position.quantity
            )
        else:
            self.position.unrealized_pnl = (
                (self.position.entry_price - current_price) * self.position.quantity
            )

        # Check SL
        if self.position.stop_loss:
            if self.position.side == PositionStatus.LONG and current_price <= self.position.stop_loss:
                self.close_position("sl")
            elif self.position.side == PositionStatus.SHORT and current_price >= self.position.stop_loss:
                self.close_position("sl")

        # Check TP
        if self.position.take_profit:
            if self.position.side == PositionStatus.LONG and current_price >= self.position.take_profit:
                self.close_position("tp")
            elif self.position.side == PositionStatus.SHORT and current_price <= self.position.take_profit:
                self.close_position("tp")

    def get_status(self) -> Dict:
        """Get current trader status"""
        return {
            'capital': self.capital,
            'position': self.position.to_dict() if self.position else None,
            'daily_pnl': self.daily_pnl,
            'trades_today': self.trades_today,
            'running': self.running
        }

    async def run(self, strategy, interval: int = 15):
        """
        Main trading loop

        Args:
            strategy: Strategy instance
            interval: Seconds between checks
        """
        self.running = True
        logger.info("Starting live trading...")

        # Initialize data
        dm = DataManager()
        dm.connect()
        df = dm.fetch_recent(days=7)
        strategy.on_init(df)

        while self.running:
            try:
                # Fetch latest data
                latest = dm.get_latest_candle()
                if not latest.empty:
                    # Generate signal
                    position_str = self.position.side.value if self.position else "FLAT"
                    signal = strategy.on_bar(latest, position_str)

                    # Execute signal
                    if signal.get('signal') != 'FLAT':
                        result = self.execute_signal(signal)

                        if self.on_signal:
                            self.on_signal(signal, result)

                # Update position (check SL/TP)
                self.update_position()

                # Wait
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                if self.on_error:
                    self.on_error(e)
                await asyncio.sleep(5)

    def stop(self):
        """Stop trading"""
        self.running = False
        logger.info("Stopping live trading...")
