"""
Trading Bot Package
===================
Modular trading bot framework

Usage:
    from trading_bot import BacktestEngine, OrderBlockStrategy, DataManager

    # Backtest
    engine = BacktestEngine(initial_capital=10000)
    df = dm.fetch_recent(days=30)
    strategy = OrderBlockStrategy()
    result = engine.run(df, strategy)

    # Live trading
    from trading_bot import ExchangeExecutor, LiveTrader
    executor = ExchangeExecutor('binance', testnet=True)
    trader = LiveTrader(executor, initial_capital=10000)
"""

from .config.settings import CONFIG, TradingConfig, OrderBlockConfig, RiskConfig

__all__ = [
    'CONFIG',
    'TradingConfig',
    'OrderBlockConfig',
    'RiskConfig'
]
