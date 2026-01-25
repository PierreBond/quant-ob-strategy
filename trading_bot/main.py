#!/usr/bin/env python3
"""
Trading Bot Main Entry Point
============================

Usage:
    python main.py --mode backtest --symbol BTC/USDT --days 30
    python main.py --mode live --paper
    python main.py --mode optimize
"""

import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np

# Import modules - handle both package and standalone imports
try:
    from config.settings import get_config, TradingConfig
except ImportError:
    TradingConfig = None
    def get_config(env="paper"):
        return {}

try:
    from data.market_data import DataManager, add_indicators
except ImportError:
    def DataManager():
        return None

    def add_indicators(df):
        return df

try:
    from backtest.engine import BacktestEngine, SMAStrategy
except ImportError:
    class BacktestEngine:
        def __init__(self, **kwargs):
            pass
        def run(self, *args, **kwargs):
            return None

    class SMAStrategy:
        pass

try:
    from strategies.orderblock import OrderBlockStrategy, OrderBlockStrategyAll, OrderBlockStrategyInverse, SimpleSMACrossover, RSIStrategy
except ImportError:
    class OrderBlockStrategy:
        pass
    class OrderBlockStrategyAll:
        pass
    class OrderBlockStrategyInverse:
        pass
    class SimpleSMACrossover:
        pass
    class RSIStrategy:
        pass


def generate_sample_data(days: int = 60, start_price: float = 90000) -> pd.DataFrame:
    """Generate sample OHLCV data for testing"""
    n_bars = days * 96  # 96 bars per day for 15min candles
    dates = pd.date_range(start='2025-01-01', periods=n_bars, freq='15min')

    np.random.seed(42)
    price = start_price
    prices = []
    volumes = []

    for i in range(n_bars):
        # Random walk with drift
        change = np.random.randn() * 150
        price = price + change
        prices.append(price)

        # Volume
        volume = 500 + np.random.rand() * 1000
        volumes.append(volume)

    df = pd.DataFrame({
        'open': prices,
        'high': [p + np.random.rand() * 100 for p in prices],
        'low': [p - np.random.rand() * 100 for p in prices],
        'close': prices,
        'volume': volumes
    }, index=dates)

    return df


def fetch_real_data(symbol: str = "BTC/USDT", 
                    days: int = 60, 
                    timeframe: str = "15m",
                    exchange_id: str = "binance") -> pd.DataFrame:
    """
    Fetch real OHLCV data from exchange using CCXT
    
    Args:
        symbol: Trading pair (e.g., "BTC/USDT")
        days: Number of days of historical data
        timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
        exchange_id: Exchange to fetch from (binance, bybit, etc.)
    
    Returns:
        DataFrame with OHLCV data
    """
    try:
        import ccxt
    except ImportError:
        print("Installing ccxt...")
        import subprocess
        subprocess.run(["pip", "install", "ccxt", "-q"])
        import ccxt
    
    print(f"Connecting to {exchange_id}...")
    
    # Initialize exchange
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({
        'enableRateLimit': True,
        'timeout': 30000,
    })
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    since = int(start_time.timestamp() * 1000)
    
    # Timeframe to milliseconds
    timeframe_ms = {
        '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000, '30m': 1800000,
        '1h': 3600000, '2h': 7200000, '4h': 14400000, '6h': 21600000, '12h': 43200000,
        '1d': 86400000, '1w': 604800000
    }
    
    all_candles = []
    current_since = since
    limit = 1000  # Max candles per request
    
    print(f"Fetching {symbol} {timeframe} data from {start_time.date()} to {end_time.date()}...")
    
    while current_since < int(end_time.timestamp() * 1000):
        try:
            candles = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=current_since,
                limit=limit
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            # Move to next batch
            last_timestamp = candles[-1][0]
            current_since = last_timestamp + timeframe_ms.get(timeframe, 900000)
            
            print(f"  Fetched {len(all_candles)} candles...", end='\r')
            
            # Rate limit
            import time
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            print(f"\nError fetching data: {e}")
            break
    
    print(f"\n✓ Fetched {len(all_candles)} candles from {exchange_id}")
    
    if not all_candles:
        print("No data fetched, falling back to sample data")
        return generate_sample_data(days)
    
    # Convert to DataFrame
    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    df = df.astype(float)
    
    # Remove duplicates and sort
    df = df[~df.index.duplicated(keep='first')]
    df.sort_index(inplace=True)
    
    return df


def run_backtest(symbol: str = "BTC/USDT",
                 days: int = 60,
                 strategy_name: str = "orderblock",
                 initial_capital: float = 10000.0,
                 use_real_data: bool = False,
                 exchange: str = "binance",
                 timeframe: str = "15m"):
    """Run backtest"""

    print(f"\n{'='*60}")
    print(f"BACKTEST MODE")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Days: {days}")
    print(f"Strategy: {strategy_name}")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Data Source: {'Real (' + exchange + ')' if use_real_data else 'Simulated'}")
    print(f"{'='*60}\n")

    # Create directories
    os.makedirs('cache', exist_ok=True)
    os.makedirs('results', exist_ok=True)
    os.makedirs('charts', exist_ok=True)

    # Load data
    print("Loading data...")
    if use_real_data:
        df = fetch_real_data(symbol=symbol, days=days, timeframe=timeframe, exchange_id=exchange)
        print(f"Data range: {df.index[0]} to {df.index[-1]}")
        print(f"Price range: ${df['low'].min():,.2f} - ${df['high'].max():,.2f}")
    else:
        df = generate_sample_data(days)
        print(f"✓ Generated {len(df)} candles (sample data)")
        print(f"Data range: {df.index[0]} to {df.index[-1]}")
        print(f"Price range: ${df['low'].min():,.0f} - ${df['high'].max():,.0f}")

    # Select strategy
    if strategy_name == "orderblock":
        strategy = OrderBlockStrategy(
            input_range=25,
            min_risk_reward=1.5,
            sl_atr_mult=2.0,
            tp_rr_mult=2.0,
            first_retest_only=True,
            position_size=0.5
        )
    elif strategy_name == "orderblock_all":
        strategy = OrderBlockStrategyAll(
            input_range=25,
            min_risk_reward=1.5,
            sl_atr_mult=2.0,
            tp_rr_mult=2.0,
            max_retests=3,  # Trade each OB up to 3 times
            position_size=0.5,
            mitigated_size_mult=0.5  # Half size for mitigated OBs
        )
    elif strategy_name == "orderblock_inverse":
        strategy = OrderBlockStrategyInverse(
            input_range=25,
            min_risk_reward=1.5,
            sl_atr_mult=2.0,
            tp_rr_mult=2.0,
            first_retest_only=True,
            position_size=0.5
        )
    elif strategy_name == "sma":
        strategy = SimpleSMACrossover(10, 20)
    else:
        strategy = OrderBlockStrategy()

    # Run backtest
    print(f"\nRunning backtest with {strategy.name}...")
    engine = BacktestEngine(
        initial_capital=initial_capital,
        fee_percent=0.001,
        slippage_percent=0.0005
    )

    result = engine.run(df, strategy, verbose=True)

    # Save results
    os.makedirs('results', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save trades to CSV
    trades_df = pd.DataFrame([t.to_dict() for t in result.trades])
    trades_df.to_csv(f'results/trades_{timestamp}.csv', index=False)

    # Save results to JSON
    with open(f'results/backtest_{timestamp}.json', 'w') as f:
        json.dump(result.to_dict(), f, indent=2, default=str)

    # Plot results
    os.makedirs('charts', exist_ok=True)
    engine.plot_results(result, save_path=f'charts/backtest_{timestamp}.png')

    print(f"\n✓ Results saved to results/")
    print(f"  - trades_{timestamp}.csv")
    print(f"  - backtest_{timestamp}.json")
    print(f"  - charts/backtest_{timestamp}.png")

    return result


def run_live(paper: bool = True, symbol: str = "BTC/USDT"):
    """Run live trading (paper or real)"""

    print(f"\n{'='*60}")
    print(f"LIVE TRADING MODE")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Mode: {'PAPER TRADING' if paper else 'REAL TRADING'}")
    print(f"{'='*60}\n")

    print("⚠️  WARNING: Live trading involves real financial risk!")
    print("   Use PAPER mode to test without real money.\n")

    if paper:
        print("Paper trading enabled - no real money at risk")
        print("\nTo enable live trading:")
        print("  1. Set PAPER_TRADING = False in config/settings.py")
        print("  2. Add your API keys below")
        print("  3. Run with --live flag\n")

    # This would be the live trading setup
    print("Live trading setup requires:")
    print("  - Exchange API keys (for real trading)")
    print("  - Telegram token (for notifications)")
    print("  - Running bot with: python main.py --mode live")


def optimize_strategy(symbol: str = "BTC/USDT", days: int = 60):
    """Optimize strategy parameters"""

    print(f"\n{'='*60}")
    print(f"STRATEGY OPTIMIZATION")
    print(f"{'='*60}")

    # Load data
    print("Loading data...")
    df = generate_sample_data(days)
    print(f"✓ Generated {len(df)} candles")

    # Grid search
    print("\nRunning parameter optimization...")
    results = []

    for rr in [1.5, 2.0, 2.5, 3.0]:
        for sl_mult in [1.5, 2.0, 2.5, 3.0]:
            strategy = OrderBlockStrategy(
                min_risk_reward=rr,
                sl_atr_mult=sl_mult
            )

            engine = BacktestEngine(initial_capital=10000)
            result = engine.run(df, strategy, verbose=False)

            results.append({
                'rr': rr,
                'sl_mult': sl_mult,
                'win_rate': result.win_rate,
                'total_pnl': result.total_pnl,
                'profit_factor': result.profit_factor,
                'max_drawdown': result.max_drawdown
            })

    # Sort by profit factor
    results.sort(key=lambda x: x['profit_factor'], reverse=True)

    print("\nTop 5 Parameter Sets:")
    print(f"{'RR':<6} {'SL':<6} {'Win%':<8} {'PnL':<12} {'PF':<8} {'DD%':<8}")
    print("-" * 60)
    for r in results[:5]:
        print(f"{r['rr']:<6} {r['sl_mult']:<6} {r['win_rate']:<8.1f} "
              f"${r['total_pnl']:<10,.0f} {r['profit_factor']:<8.2f} {r['max_drawdown']:<8.2f}")

    return results


def main():
    parser = argparse.ArgumentParser(description='Trading Bot')
    parser.add_argument('--mode', choices=['backtest', 'live', 'optimize'],
                        default='backtest', help='Running mode')
    parser.add_argument('--symbol', type=str, default='BTC/USDT',
                        help='Trading symbol (e.g., BTC/USDT, ETH/USDT)')
    parser.add_argument('--days', type=int, default=60,
                        help='Days of data')
    parser.add_argument('--strategy', type=str, default='orderblock',
                        choices=['orderblock', 'orderblock_all', 'orderblock_inverse', 'sma'],
                        help='Strategy: orderblock, orderblock_all (mitigated), orderblock_inverse (contrarian), sma')
    parser.add_argument('--capital', type=float, default=10000,
                        help='Initial capital')
    parser.add_argument('--real-data', action='store_true',
                        help='Use real exchange data instead of simulated')
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'bybit', 'okx', 'kucoin', 'coinbase'],
                        help='Exchange for real data (default: binance)')
    parser.add_argument('--timeframe', type=str, default='15m',
                        choices=['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
                        help='Candle timeframe (default: 15m)')
    parser.add_argument('--paper', action='store_true',
                        help='Paper trading mode')
    parser.add_argument('--live', action='store_true',
                        help='Live trading (requires API keys)')

    args = parser.parse_args()

    if args.mode == 'backtest':
        run_backtest(
            symbol=args.symbol,
            days=args.days,
            strategy_name=args.strategy,
            initial_capital=args.capital,
            use_real_data=args.real_data,
            exchange=args.exchange,
            timeframe=args.timeframe
        )
    elif args.mode == 'live':
        run_live(paper=not args.live, symbol=args.symbol)
    elif args.mode == 'optimize':
        optimize_strategy(symbol=args.symbol, days=args.days)


if __name__ == "__main__":
    main()
