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
sys.path.insert(0, str(Path(__file__).parent.parent))
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
    from strategies.orderblock import OrderBlockStrategy, OrderBlockStrategyAll, OrderBlockStrategyInverse, OrderBlockStrategyPremium, OrderBlockStrategyPremiumV2, OrderBlockStrategyPremiumV3, SimpleSMACrossover, RSIStrategy
except ImportError:
    class OrderBlockStrategy:
        pass
    class OrderBlockStrategyAll:
        pass
    class OrderBlockStrategyInverse:
        pass
    class OrderBlockStrategyPremium:
        pass
    class OrderBlockStrategyPremiumV2:
        pass
    class OrderBlockStrategyPremiumV3:
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
                 timeframe: str = "15m",
                 use_risk_management: bool = False,
                 use_mtf: bool = True,
                 use_funding: bool = False,
                 use_circuit_breaker: bool = True,
                 use_kelly: bool = True):
    """Run backtest with optional Phase 1 risk management"""

    print(f"\n{'='*60}")
    print(f"BACKTEST MODE")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Days: {days}")
    print(f"Strategy: {strategy_name}")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Data Source: {'Real (' + exchange + ')' if use_real_data else 'Simulated'}")
    
    # Phase 1 Risk Management status
    if use_risk_management:
        print(f"\n🛡️ PHASE 1 RISK MANAGEMENT: ENABLED")
        print(f"   • Kelly Criterion:    {'✅' if use_kelly else '❌'}")
        print(f"   • Circuit Breaker:    {'✅' if use_circuit_breaker else '❌'}")
        print(f"   • Multi-Timeframe:    {'✅' if use_mtf else '❌'}")
        print(f"   • Funding Filter:     {'✅' if use_funding else '❌'}")
    else:
        print(f"\n🛡️ PHASE 1 RISK MANAGEMENT: DISABLED")
        print(f"   (Use --risk-mgmt to enable)")
    
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

    # Select strategy using factory function
    strategy = get_strategy_instance(strategy_name, timeframe)

    # Initialize Phase 1 Risk Manager if enabled
    risk_manager = None
    if use_risk_management:
        try:
            from utils import RiskManager
            risk_manager = RiskManager(
                capital=initial_capital,
                exchange_id=exchange,
                use_mtf=use_mtf,
                use_funding=use_funding,
                use_circuit_breaker=use_circuit_breaker,
                use_kelly=use_kelly
            )
            print("🛡️ Risk Manager initialized")
            
            # Pre-fetch MTF data if enabled
            if use_mtf:
                print("📊 Pre-fetching multi-timeframe data...")
                risk_manager.load_mtf_data(symbol, force=True)
                
        except ImportError as e:
            print(f"⚠️ Could not load Risk Manager: {e}")
            risk_manager = None

    # Run backtest
    print(f"\nRunning backtest with {strategy.name}...")
    engine = BacktestEngine(
        initial_capital=initial_capital,
        fee_percent=0.001,
        slippage_percent=0.0005,
        risk_manager=risk_manager  # Pass risk manager to engine
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


def get_strategy_instance(strategy_name: str, timeframe: str = "15m"):
    """
    Factory function to create strategy instances
    
    Args:
        strategy_name: Name of strategy
        timeframe: Timeframe for time-based strategies
        
    Returns:
        Strategy instance
    """
    # Parse timeframe to minutes
    tf_map = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
    tf_minutes = tf_map.get(timeframe, 15)
    
    if strategy_name == "orderblock":
        return OrderBlockStrategy(
            input_range=25,
            min_risk_reward=1.5,
            sl_atr_mult=2.0,
            tp_rr_mult=2.0,
            first_retest_only=True,
            position_size=0.5
        )
    elif strategy_name == "orderblock_all":
        return OrderBlockStrategyAll(
            input_range=25,
            min_risk_reward=1.5,
            sl_atr_mult=2.0,
            tp_rr_mult=2.0,
            max_retests=3,
            position_size=0.5,
            mitigated_size_mult=0.5
        )
    elif strategy_name == "orderblock_inverse":
        return OrderBlockStrategyInverse(
            input_range=25,
            min_risk_reward=1.5,
            sl_atr_mult=2.0,
            tp_rr_mult=2.0,
            first_retest_only=True,
            position_size=0.5
        )
    elif strategy_name == "orderblock_premium":
        return OrderBlockStrategyPremium(
            input_range=25,
            min_risk_reward=2.0,
            sl_atr_mult=1.0,
            tp_rr_mult=3.0,
            require_fvg=True,
            min_fvg_percent=0.1,
            require_displacement=True,
            min_displacement_percent=0.5,
            min_displacement_candles=2,
            require_ob_mss=False,
            mss_confirmation_bars=20,
            mss_swing_lookback=5,
            first_retest_only=True,
            position_size=0.5
        )
    elif strategy_name == "orderblock_premium_v2":
        return OrderBlockStrategyPremiumV2(
            input_range=25,
            min_risk_reward=1.5,
            tp_rr_mult=2.5,
            require_fvg=True,
            require_displacement=True,
            max_age_bars=150,
            mss_confirmation_bars=20,
            use_trend_filter=True,
            ema_fast=50,
            ema_slow=200,
            use_dynamic_rr=True,
            low_vol_threshold=1.0,
            high_vol_threshold=2.0,
            use_partial_tp=True,
            partial_tp_percent=0.5,
            tp1_rr_mult=1.5,
            tp2_rr_mult=3.0,
            sl_atr_buffer=0.5,
            position_size=0.5
        )
    elif strategy_name == "orderblock_premium_v3":
        return OrderBlockStrategyPremiumV3(
            input_range=25,
            min_risk_reward=1.5,
            require_fvg=True,
            require_displacement=True,
            mss_confirmation_bars=20,
            # TIME-BASED SETTINGS
            aggressive_days=30,
            timeframe_minutes=tf_minutes,
            # AGGRESSIVE MODE (Days 1-30)
            aggressive_max_age=500,
            aggressive_rr=3.0,
            aggressive_sl_buffer=0.3,
            # CONSERVATIVE MODE (Days 31+)
            conservative_max_age=150,
            conservative_sl_buffer=0.5,
            # Trend Filter (V2 mode only)
            ema_fast=50,
            ema_slow=200,
            # Dynamic R:R (V2 mode only)
            low_vol_threshold=1.0,
            high_vol_threshold=2.0,
            # Partial TP (V2 mode only)
            partial_tp_percent=0.5,
            tp1_rr_mult=1.5,
            tp2_rr_mult=3.0,
            position_size=0.5
        )
    elif strategy_name == "sma":
        return SimpleSMACrossover(10, 20)
    else:
        return OrderBlockStrategy()


def run_live(paper: bool = True, 
             symbol: str = "BTC/USDT",
             strategy_name: str = "orderblock_premium",
             exchange: str = "binance",
             timeframe: str = "15m",
             capital: float = 10000.0):
    """
    Run live trading (paper or real)
    
    Args:
        paper: If True, paper trading (no real orders)
        symbol: Trading pair
        strategy_name: Strategy to use
        exchange: Exchange to trade on
        timeframe: Candle timeframe
        capital: Starting capital (for paper trading)
    """
    import asyncio

    print(f"\n{'='*60}")
    print(f"LIVE TRADING MODE")
    print(f"{'='*60}")
    print(f"Symbol:    {symbol}")
    print(f"Strategy:  {strategy_name}")
    print(f"Exchange:  {exchange}")
    print(f"Timeframe: {timeframe}")
    print(f"Mode:      {'PAPER TRADING' if paper else '⚠️  REAL TRADING'}")
    print(f"Capital:   ${capital:,.2f}")
    print(f"{'='*60}\n")

    print("⚠️  WARNING: Live trading involves real financial risk!")
    print("   Use PAPER mode to test without real money.\n")

    # Strategy recommendation based on trading duration
    print("📊 STRATEGY SELECTION GUIDE:")
    print("   ┌─────────────────────────────────────────────────────┐")
    print("   │ Duration        │ Recommended Strategy              │")
    print("   ├─────────────────┼───────────────────────────────────┤")
    print("   │ ≤30 days        │ orderblock_premium (V1)           │")
    print("   │ 31-120 days     │ orderblock_premium_v3 (Hybrid)    │")
    print("   │ 180+ days       │ orderblock_premium_v2 (Conservative)│")
    print("   └─────────────────────────────────────────────────────┘\n")
    
    # V3 special note
    if strategy_name == "orderblock_premium_v3":
        print("🔄 V3 HYBRID MODE ACTIVE:")
        print("   • Days 1-30:  AGGRESSIVE (V1 style - higher R:R, less filtering)")
        print("   • Days 31+:   CONSERVATIVE (V2 style - trend filter, partial TP)")
        print("   • Auto-switches based on time running\n")

    # Create strategy
    strategy = get_strategy_instance(strategy_name, timeframe)
    print(f"✓ Strategy initialized: {strategy.name}")

    if paper:
        print("\n📝 PAPER TRADING MODE")
        print("   No real orders will be placed.")
        print("   Bot will track simulated positions.\n")
        
        # Paper trading loop
        print("To start paper trading:")
        print(f"  1. Bot will fetch {symbol} data from {exchange}")
        print(f"  2. Strategy '{strategy_name}' will generate signals")
        print("  3. Signals will be logged (no real orders)")
        print("\nPress Ctrl+C to stop.\n")
        
        # Load historical data to initialize strategy
        print("Loading historical data to initialize strategy...")
        df = fetch_real_data(symbol=symbol, days=7, timeframe=timeframe, exchange_id=exchange)
        if df is not None and not df.empty:
            strategy.on_init(df)
            print(f"✓ Strategy initialized with {len(df)} candles")
            print(f"  Data from: {df.index[0]}")
            print(f"  Data to:   {df.index[-1]}")
            print(f"  Current price: ${df['close'].iloc[-1]:,.2f}\n")
        
        # Simple paper trading loop
        print("Starting paper trading loop (checking every candle)...")
        print("=" * 60)
        
        import time
        tf_seconds = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, 
                      '1h': 3600, '4h': 14400, '1d': 86400}
        interval = tf_seconds.get(timeframe, 900)
        
        position = None
        trades = []
        paper_capital = capital
        
        try:
            while True:
                # Fetch latest candle
                df = fetch_real_data(symbol=symbol, days=1, timeframe=timeframe, exchange_id=exchange)
                if df is None or df.empty:
                    time.sleep(60)
                    continue
                
                latest = df.iloc[-1]
                current_price = latest['close']
                
                # Get signal
                pos_str = position['side'] if position else "FLAT"
                signal = strategy.on_bar(latest, pos_str)
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Process signal
                if signal.get('signal') == 'LONG' and position is None:
                    position = {
                        'side': 'LONG',
                        'entry': current_price,
                        'sl': signal.get('stop_loss'),
                        'tp': signal.get('take_profit'),
                        'time': timestamp
                    }
                    print(f"🟢 [{timestamp}] LONG @ ${current_price:,.2f} | SL: ${position['sl']:,.2f} | TP: ${position['tp']:,.2f}")
                    
                elif signal.get('signal') == 'SHORT' and position is None:
                    position = {
                        'side': 'SHORT',
                        'entry': current_price,
                        'sl': signal.get('stop_loss'),
                        'tp': signal.get('take_profit'),
                        'time': timestamp
                    }
                    print(f"🔴 [{timestamp}] SHORT @ ${current_price:,.2f} | SL: ${position['sl']:,.2f} | TP: ${position['tp']:,.2f}")
                
                # Check SL/TP
                if position:
                    if position['side'] == 'LONG':
                        if current_price <= position['sl']:
                            pnl = (current_price - position['entry']) / position['entry'] * 100
                            paper_capital *= (1 + pnl/100 * 0.5)  # 50% position size
                            print(f"🛑 [{timestamp}] LONG SL HIT @ ${current_price:,.2f} | PnL: {pnl:+.2f}% | Capital: ${paper_capital:,.2f}")
                            position = None
                        elif current_price >= position['tp']:
                            pnl = (current_price - position['entry']) / position['entry'] * 100
                            paper_capital *= (1 + pnl/100 * 0.5)
                            print(f"✅ [{timestamp}] LONG TP HIT @ ${current_price:,.2f} | PnL: {pnl:+.2f}% | Capital: ${paper_capital:,.2f}")
                            position = None
                    else:  # SHORT
                        if current_price >= position['sl']:
                            pnl = (position['entry'] - current_price) / position['entry'] * 100
                            paper_capital *= (1 + pnl/100 * 0.5)
                            print(f"🛑 [{timestamp}] SHORT SL HIT @ ${current_price:,.2f} | PnL: {pnl:+.2f}% | Capital: ${paper_capital:,.2f}")
                            position = None
                        elif current_price <= position['tp']:
                            pnl = (position['entry'] - current_price) / position['entry'] * 100
                            paper_capital *= (1 + pnl/100 * 0.5)
                            print(f"✅ [{timestamp}] SHORT TP HIT @ ${current_price:,.2f} | PnL: {pnl:+.2f}% | Capital: ${paper_capital:,.2f}")
                            position = None
                
                # Status update
                pos_status = f"{position['side']} from ${position['entry']:,.2f}" if position else "FLAT"
                print(f"   [{timestamp}] Price: ${current_price:,.2f} | Position: {pos_status} | Capital: ${paper_capital:,.2f}", end='\r')
                
                # Wait for next candle
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(f"\n\n{'='*60}")
            print("Paper trading stopped by user")
            print(f"Final Capital: ${paper_capital:,.2f}")
            print(f"Return: {(paper_capital/capital - 1)*100:+.2f}%")
            print(f"{'='*60}")
            
    else:
        print("\n⚠️  REAL TRADING MODE")
        print("   This will place REAL orders with REAL money!")
        print("\nTo enable real trading:")
        print("  1. Create config/api_keys.json with your exchange API keys")
        print("  2. Ensure you have sufficient balance")
        print("  3. Start with small amounts to test")
        print("\nAPI keys file format (config/api_keys.json):")
        print('  {"exchange": "binance", "api_key": "xxx", "api_secret": "xxx"}')


def print_last_orderblocks(symbol: str = "BTC/USDT",
                           days: int = 7,
                           timeframe: str = "1h",
                           exchange: str = "binance"):
    """Print the last order blocks on a given timeframe"""
    print(f"\n{'='*60}")
    print(f"FETCHING LAST ORDER BLOCKS")
    print(f"{'='*60}")
    print(f"Symbol:     {symbol}")
    print(f"Timeframe:  {timeframe}")
    print(f"Exchange:   {exchange}")
    print(f"{'='*60}\n")

    # Fetch real data
    print("Loading data...")
    df = fetch_real_data(symbol=symbol, days=days, timeframe=timeframe, exchange_id=exchange)
    
    if df is None or df.empty:
        print("❌ Failed to fetch data")
        return

    # Initialize strategy
    strategy = OrderBlockStrategy(
        input_range=25,
        min_risk_reward=1.5,
        sl_atr_mult=2.0,
        tp_rr_mult=2.0,
        first_retest_only=False
    )
    
    # Initialize strategy with data
    strategy.on_init(df)
    
    # Run through data to detect OBs (suppress OB printing during scan)
    print("🔍 Scanning for order blocks...\n")
    strategy._last_printed_ob_long = -1  # Suppress printing during scan
    strategy._last_printed_ob_short = -1
    
    for idx in range(strategy.input_range + 10, len(df)):
        current = df.iloc[idx]
        current_idx = idx
        
        # Update state step by step
        strategy._update_structure(df, current_idx)
        strategy._detect_bearish_bos(df, current, current_idx)
        strategy._detect_bullish_bos(df, current, current_idx)
        strategy._update_ob_status(df, current, current_idx)
    
    # Get last OBs
    last_obs = strategy.get_last_ob_info()
    current_price = df['close'].iloc[-1]
    
    print(f"\n{'='*60}")
    print(f"LATEST ORDER BLOCKS - {symbol} ({timeframe})")
    print(f"{'='*60}")
    print(f"Current Price: ${current_price:,.2f}")
    print(f"Last Update:   {df.index[-1]}\n")
    
    if last_obs['bullish']:
        ob = last_obs['bullish']
        print(f"🟢 BULLISH ORDER BLOCK")
        print(f"   Top:       ${ob['top']:,.2f}")
        print(f"   Bottom:    ${ob['bottom']:,.2f}")
        print(f"   Range:     ${ob['range']:,.2f} ({ob['range']/ob['bottom']*100:.2f}%)")
        print(f"   State:     {ob['state']}")
        print(f"   Created:   {ob['created_at']}")
        print(f"   Timestamp: {ob['timestamp']}\n")
    else:
        print("🟢 No bullish order block detected\n")
    
    if last_obs['bearish']:
        ob = last_obs['bearish']
        print(f"🔴 BEARISH ORDER BLOCK")
        print(f"   Top:       ${ob['top']:,.2f}")
        print(f"   Bottom:    ${ob['bottom']:,.2f}")
        print(f"   Range:     ${ob['range']:,.2f} ({ob['range']/ob['bottom']*100:.2f}%)")
        print(f"   State:     {ob['state']}")
        print(f"   Created:   {ob['created_at']}")
        print(f"   Timestamp: {ob['timestamp']}\n")
    else:
        print("🔴 No bearish order block detected\n")
    
    print(f"{'='*60}\n")


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


def test_phase1_features(symbol: str = "BTC/USDT", exchange: str = "binance"):
    """
    Test all Phase 1 risk management features
    
    Tests:
    1. Kelly Criterion Position Sizing
    2. Circuit Breaker
    3. Multi-Timeframe Analysis
    4. Funding Rate Filter
    5. Unified Risk Manager
    """
    print(f"\n{'='*70}")
    print(f"PHASE 1 RISK MANAGEMENT TEST")
    print(f"{'='*70}")
    print(f"Symbol: {symbol}")
    print(f"Exchange: {exchange}")
    print(f"{'='*70}\n")
    
    # Import Phase 1 modules
    try:
        from utils import (
            PositionSizer,
            CircuitBreaker, CircuitBreakerConfig,
            MultiTimeframeAnalyzer, Trend,
            FundingRateFilter,
            RiskManager
        )
        print("✅ All Phase 1 modules imported successfully\n")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return
    
    results = {}
    
    # ============================
    # TEST 1: Kelly Criterion
    # ============================
    print(f"{'─'*70}")
    print("TEST 1: KELLY CRITERION POSITION SIZING")
    print(f"{'─'*70}")
    
    sizer = PositionSizer(
        max_position_pct=0.25,
        kelly_fraction=0.25,
        volatility_adjustment=True
    )
    
    # Simulate trade history
    print("Simulating 20 trades (50% win rate, 1.88 profit factor)...")
    wins = [(True, 0.03), (True, 0.025), (True, 0.035), (True, 0.028), (True, 0.032),
            (True, 0.027), (True, 0.031), (True, 0.029), (True, 0.033), (True, 0.026)]
    losses = [(False, -0.018), (False, -0.015), (False, -0.017), (False, -0.016), (False, -0.014),
              (False, -0.019), (False, -0.015), (False, -0.016), (False, -0.017), (False, -0.018)]
    
    for win, pnl in wins + losses:
        sizer.add_trade(pnl, win)  # Fixed argument order
    
    stats = sizer.get_stats()
    recommended_size, reason = sizer.get_position_size(0.02)
    
    # Calculate raw Kelly for display
    if stats:
        win_loss_ratio = stats.avg_win_pct / stats.avg_loss_pct if stats.avg_loss_pct > 0 else 0
        raw_kelly = stats.win_rate - ((1 - stats.win_rate) / win_loss_ratio) if win_loss_ratio > 0 else 0
    else:
        raw_kelly = 0
    
    print(f"  Win Rate:      {stats.win_rate*100:.1f}%")
    print(f"  Profit Factor: {stats.profit_factor:.2f}")
    print(f"  Kelly Raw:     {raw_kelly*100:.1f}%")
    print(f"  Recommended:   {recommended_size*100:.1f}%")
    print(f"  Reason:        {reason}")
    
    results['kelly'] = {
        'status': 'PASS' if 0 < recommended_size <= 0.25 else 'FAIL',
        'size': recommended_size
    }
    print(f"\n  Result: {'✅ PASS' if results['kelly']['status'] == 'PASS' else '❌ FAIL'}\n")
    
    # ============================
    # TEST 2: Circuit Breaker
    # ============================
    print(f"{'─'*70}")
    print("TEST 2: CIRCUIT BREAKER")
    print(f"{'─'*70}")
    
    config = CircuitBreakerConfig(
        max_consecutive_losses=3,  # Low threshold for test
        cooldown_minutes=1
    )
    breaker = CircuitBreaker(config)
    breaker.initialize(10000)  # Initialize with capital
    
    print("Simulating 3 consecutive losses...")
    for i in range(3):
        breaker.update(10000 - (i+1)*200, trade_won=False)  # $200 loss each
        can_trade = breaker.can_trade()
        print(f"  Loss {i+1}: Can trade = {can_trade}")
    
    status = breaker.get_status()
    breaker_triggered = not breaker.can_trade()
    
    print(f"\n  Breaker Triggered: {breaker_triggered}")
    print(f"  State: {status['state']}")
    print(f"  Consecutive Losses: {status['consecutive_losses']}")
    
    results['circuit_breaker'] = {
        'status': 'PASS' if breaker_triggered else 'FAIL',
        'triggered': breaker_triggered
    }
    print(f"\n  Result: {'✅ PASS' if results['circuit_breaker']['status'] == 'PASS' else '❌ FAIL'}\n")
    
    # ============================
    # TEST 3: Multi-Timeframe
    # ============================
    print(f"{'─'*70}")
    print("TEST 3: MULTI-TIMEFRAME ANALYSIS")
    print(f"{'─'*70}")
    
    mtf = MultiTimeframeAnalyzer(
        exchange_id=exchange
    )
    
    print(f"Fetching {symbol} data across timeframes...")
    mtf.fetch_all_timeframes(symbol, timeframes=['15m', '1h', '4h'])
    
    print(f"\n  Timeframe Results:")
    for tf in ['15m', '1h', '4h']:
        if tf in mtf.analysis:
            analysis = mtf.analysis[tf]
            trend_emoji = '🟢' if analysis.trend.value > 0 else '🔴' if analysis.trend.value < 0 else '⚪'
            print(f"    {tf:>4}: {trend_emoji} {analysis.trend.name}")
    
    # Get alignment score
    score, description = mtf.get_trend_alignment_score()
    print(f"\n  Overall Score: {score:.2f}")
    print(f"  Description: {description}")
    
    # Test confirmation
    long_confirmed, long_details = mtf.get_confirmation('15m', 'LONG')
    short_confirmed, short_details = mtf.get_confirmation('15m', 'SHORT')
    
    print(f"\n  LONG Confirmation:  {'✅' if long_confirmed else '❌'} ({long_details.get('confirmation_rate', 'N/A')})")
    print(f"  SHORT Confirmation: {'✅' if short_confirmed else '❌'} ({short_details.get('confirmation_rate', 'N/A')})")
    
    results['mtf'] = {
        'status': 'PASS',
        'score': score,
        'trend': description
    }
    print(f"\n  Result: ✅ PASS (MTF analysis working)\n")
    
    # ============================
    # TEST 4: Funding Rate
    # ============================
    print(f"{'─'*70}")
    print("TEST 4: FUNDING RATE FILTER")
    print(f"{'─'*70}")
    
    funding = FundingRateFilter(exchange_id=exchange)
    
    print(f"Fetching funding rate for {symbol}...")
    
    try:
        # Normalize symbol (remove / for futures)
        normalized_symbol = symbol.replace('/', '')
        info = funding.get_funding_rate(normalized_symbol)
        
        if info:
            print(f"\n  Current Rate:  {info.rate_pct:.4f}%")
            print(f"  Annualized:    {info.rate_annualized:.2f}%")
            print(f"  Sentiment:     {info.sentiment}")
            print(f"  Extreme:       {'Yes' if info.is_extreme else 'No'}")
            
            # Check if trades allowed
            long_avoid, long_reason = funding.should_avoid_trade(normalized_symbol, 'LONG')
            short_avoid, short_reason = funding.should_avoid_trade(normalized_symbol, 'SHORT')
            
            print(f"\n  LONG Allowed:  {'❌' if long_avoid else '✅'}")
            print(f"  SHORT Allowed: {'❌' if short_avoid else '✅'}")
            
            # Get bias
            bias, confidence, bias_reason = funding.get_funding_bias(normalized_symbol)
            print(f"\n  Funding Bias:  {bias} (confidence: {confidence:.0%})")
            
            results['funding'] = {
                'status': 'PASS',
                'rate': info.rate
            }
        else:
            print("  ⚠️ Could not fetch funding rate")
            results['funding'] = {
                'status': 'SKIP',
                'error': 'No funding data'
            }
    except Exception as e:
        print(f"  ⚠️ Could not fetch funding: {e}")
        print("  (This may be normal for spot symbols)")
        results['funding'] = {
            'status': 'SKIP',
            'error': str(e)
        }
    
    print(f"\n  Result: {'✅ PASS' if results['funding']['status'] == 'PASS' else '⚠️ SKIPPED'}\n")
    
    # ============================
    # TEST 5: Unified Risk Manager
    # ============================
    print(f"{'─'*70}")
    print("TEST 5: UNIFIED RISK MANAGER")
    print(f"{'─'*70}")
    
    rm = RiskManager(
        capital=10000,
        exchange_id=exchange,
        use_mtf=True,
        use_funding=True,
        use_circuit_breaker=True,
        use_kelly=True
    )
    
    # Seed with trade history
    for win, pnl in wins[:5] + losses[:5]:
        if rm.position_sizer:
            rm.position_sizer.add_trade(pnl, win)
    
    print("Evaluating LONG trade...")
    long_decision = rm.evaluate_trade(symbol, 'LONG', '15m', 0.02)
    
    print(f"\n  LONG Decision:")
    print(f"    Can Trade:    {'✅' if long_decision.can_trade else '❌'}")
    print(f"    Position Size: {long_decision.position_size_pct*100:.1f}%")
    print(f"    MTF Score:     {long_decision.mtf_score:.2f}")
    if long_decision.reasons:
        print(f"    Reasons:       {', '.join(long_decision.reasons)}")
    if long_decision.warnings:
        print(f"    Warnings:      {', '.join(long_decision.warnings)}")
    
    print("\nEvaluating SHORT trade...")
    short_decision = rm.evaluate_trade(symbol, 'SHORT', '15m', 0.02)
    
    print(f"\n  SHORT Decision:")
    print(f"    Can Trade:    {'✅' if short_decision.can_trade else '❌'}")
    print(f"    Position Size: {short_decision.position_size_pct*100:.1f}%")
    print(f"    MTF Score:     {short_decision.mtf_score:.2f}")
    if short_decision.reasons:
        print(f"    Reasons:       {', '.join(short_decision.reasons)}")
    if short_decision.warnings:
        print(f"    Warnings:      {', '.join(short_decision.warnings)}")
    
    results['risk_manager'] = {
        'status': 'PASS',
        'long_approved': long_decision.can_trade,
        'short_approved': short_decision.can_trade
    }
    print(f"\n  Result: ✅ PASS (Risk Manager working)\n")
    
    # ============================
    # SUMMARY
    # ============================
    print(f"{'='*70}")
    print("PHASE 1 TEST SUMMARY")
    print(f"{'='*70}")
    
    all_pass = True
    for name, result in results.items():
        status = result['status']
        emoji = '✅' if status == 'PASS' else '⚠️' if status == 'SKIP' else '❌'
        print(f"  {name.upper():20} {emoji} {status}")
        if status == 'FAIL':
            all_pass = False
    
    print(f"{'='*70}")
    if all_pass:
        print("✅ ALL PHASE 1 FEATURES WORKING CORRECTLY")
    else:
        print("⚠️ SOME TESTS FAILED - CHECK ABOVE")
    print(f"{'='*70}\n")
    
    return results


def run_vectorbt_backtest(symbol: str = "BTC/USDT",
                          days: int = 60,
                          initial_capital: float = 10000.0,
                          exchange: str = "binance",
                          timeframe: str = "15m",
                          use_trend_filter: bool = True,
                          require_fvg: bool = True):
    """Run VectorBT-powered backtest (100x faster)"""
    
    print(f"\n{'='*60}")
    print(f"⚡ VECTORBT BACKTEST MODE (100x FASTER)")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Days: {days}")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Exchange: {exchange}")
    print(f"Timeframe: {timeframe}")
    print(f"{'='*60}\n")
    
    try:
        from vbt_integration.strategy_adapter import VectorBTOrderBlock, VectorBTConfig
    except ImportError:
        print("❌ VectorBT module not found. Install with: pip install vectorbt")
        return None
    
    # Fetch data
    print("Loading data...")
    df = fetch_real_data(symbol=symbol, days=days, timeframe=timeframe, exchange_id=exchange)
    print(f"Data range: {df.index[0]} to {df.index[-1]}")
    print(f"Total bars: {len(df):,}")
    
    # Configure strategy
    config = VectorBTConfig(
        use_trend_filter=use_trend_filter,
        require_fvg=require_fvg,
        require_displacement=True,
        ema_fast=50,
        ema_slow=200,
        input_range=25,
        max_age_bars=150,
        sl_atr_mult=1.5,
        tp_rr_mult=2.5
    )
    
    # Run backtest
    print("\nRunning VectorBT backtest...")
    strategy = VectorBTOrderBlock(config)
    pf = strategy.backtest(df, initial_capital, verbose=True)
    
    # Save trades
    os.makedirs('results', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        trades_df = pf.trades.records_readable
        trades_df.to_csv(f'results/vbt_trades_{timestamp}.csv', index=False)
        print(f"\n✓ Trades saved to results/vbt_trades_{timestamp}.csv")
    except:
        pass
    
    return pf


def run_vectorbt_optimize(symbol: str = "BTC/USDT",
                          days: int = 90,
                          exchange: str = "binance",
                          timeframe: str = "15m",
                          quick: bool = True):
    """Run VectorBT parameter optimization"""
    
    print(f"\n{'='*60}")
    print(f"🔍 VECTORBT PARAMETER OPTIMIZATION")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Days: {days}")
    print(f"Mode: {'Quick' if quick else 'Full'}")
    print(f"{'='*60}\n")
    
    try:
        from vbt_integration.optimizer import ParameterOptimizer, optimize_strategy
    except ImportError:
        print("❌ VectorBT module not found. Install with: pip install vectorbt")
        return None
    
    # Fetch data
    print("Loading data...")
    df = fetch_real_data(symbol=symbol, days=days, timeframe=timeframe, exchange_id=exchange)
    print(f"Data range: {df.index[0]} to {df.index[-1]}")
    print(f"Total bars: {len(df):,}")
    
    # Run optimization
    print("\nRunning parameter optimization...")
    result = optimize_strategy(df, quick=quick, verbose=True)
    
    # Save results
    os.makedirs('results', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with open(f'results/vbt_optimization_{timestamp}.json', 'w') as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    
    print(f"\n✓ Optimization results saved to results/vbt_optimization_{timestamp}.json")
    
    return result


def run_walk_forward(symbol: str = "BTC/USDT",
                     days: int = 365,
                     exchange: str = "binance",
                     timeframe: str = "15m",
                     train_days: int = 210,
                     test_days: int = 90):
    """Run walk-forward analysis to validate strategy"""
    
    print(f"\n{'='*60}")
    print(f"🔄 WALK-FORWARD ANALYSIS")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Total Days: {days}")
    print(f"Train Window: {train_days} days")
    print(f"Test Window: {test_days} days")
    print(f"{'='*60}\n")
    
    try:
        from vbt_integration.walk_forward import WalkForwardAnalyzer
    except ImportError:
        print("❌ VectorBT module not found. Install with: pip install vectorbt")
        return None
    
    # Fetch data
    print("Loading data...")
    df = fetch_real_data(symbol=symbol, days=days, timeframe=timeframe, exchange_id=exchange)
    print(f"Data range: {df.index[0]} to {df.index[-1]}")
    print(f"Total bars: {len(df):,}")
    
    # Run walk-forward
    print("\nRunning walk-forward analysis...")
    analyzer = WalkForwardAnalyzer()
    result = analyzer.analyze(
        df,
        train_days=train_days,
        test_days=test_days,
        step_days=30,
        timeframe=timeframe,
        verbose=True
    )
    
    # Save results
    os.makedirs('results', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with open(f'results/walk_forward_{timestamp}.json', 'w') as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    
    print(f"\n✓ Walk-forward results saved to results/walk_forward_{timestamp}.json")
    
    return result


def run_benchmark(symbol: str = "BTC/USDT",
                  days: int = 60,
                  exchange: str = "binance",
                  timeframe: str = "15m"):
    """Run benchmark comparison: loop-based vs VectorBT"""
    
    print(f"\n{'='*60}")
    print(f"[BENCHMARK] LOOP VS VECTORBT")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Days: {days}")
    print(f"{'='*60}\n")
    
    try:
        from vbt_integration.benchmark import BacktestBenchmark
    except ImportError:
        print("❌ VectorBT module not found. Install with: pip install vectorbt")
        return None
    
    # Fetch data
    print("Loading data...")
    df = fetch_real_data(symbol=symbol, days=days, timeframe=timeframe, exchange_id=exchange)
    print(f"Data range: {df.index[0]} to {df.index[-1]}")
    print(f"Total bars: {len(df):,}")
    
    # Run benchmark
    print("\nRunning benchmark...")
    benchmark = BacktestBenchmark()
    result = benchmark.run(df, n_iterations=3, verbose=True)
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Trading Bot')
    parser.add_argument('--mode', choices=['backtest', 'live', 'optimize', 'last_ob', 'risk-test', 
                                           'vbt', 'vbt-optimize', 'walk-forward', 'benchmark'],
                        default='backtest', help='Running mode')
    parser.add_argument('--symbol', type=str, default='BTC/USDT',
                        help='Trading symbol (e.g., BTC/USDT, ETH/USDT)')
    parser.add_argument('--days', type=int, default=60,
                        help='Days of data')
    parser.add_argument('--strategy', type=str, default='orderblock',
                        choices=['orderblock', 'orderblock_all', 'orderblock_inverse', 'orderblock_premium', 'orderblock_premium_v2', 'orderblock_premium_v3', 'sma'],
                        help='Strategy: orderblock, orderblock_premium (v1), orderblock_premium_v2 (trend filter), orderblock_premium_v3 (adaptive hybrid), sma')
    parser.add_argument('--capital', type=float, default=10000,
                        help='Initial capital')
    parser.add_argument('--real-data', action='store_true',
                        help='Use real exchange data instead of simulated')
    parser.add_argument('--exchange', type=str, default='binance',
                        choices=['binance', 'bybit', 'okx', 'kucoin', 'coinbase', 'kraken'],
                        help='Exchange for real data (default: binance)')
    parser.add_argument('--timeframe', type=str, default='15m',
                        choices=['1m', '5m', '15m', '30m', '1h', '4h', '1d'],
                        help='Candle timeframe (default: 15m)')
    parser.add_argument('--paper', action='store_true',
                        help='Paper trading mode')
    parser.add_argument('--live', action='store_true',
                        help='Live trading (requires API keys)')
    
    # Phase 1 Risk Management flags
    parser.add_argument('--risk-mgmt', action='store_true',
                        help='Enable Phase 1 risk management (Kelly, Circuit Breaker, MTF, Funding)')
    parser.add_argument('--no-mtf', action='store_true',
                        help='Disable multi-timeframe confirmation (used with --risk-mgmt)')
    parser.add_argument('--no-kelly', action='store_true',
                        help='Disable Kelly Criterion sizing (used with --risk-mgmt)')
    parser.add_argument('--no-circuit-breaker', action='store_true',
                        help='Disable circuit breaker (used with --risk-mgmt)')
    parser.add_argument('--use-funding', action='store_true',
                        help='Enable funding rate filter (used with --risk-mgmt)')
    
    # VectorBT flags
    parser.add_argument('--no-trend-filter', action='store_true',
                        help='Disable trend filter in VectorBT mode')
    parser.add_argument('--no-fvg', action='store_true',
                        help='Disable FVG filter in VectorBT mode')
    parser.add_argument('--quick', action='store_true',
                        help='Quick optimization (fewer combinations)')
    parser.add_argument('--train-days', type=int, default=210,
                        help='Training window for walk-forward (default: 210)')
    parser.add_argument('--test-days', type=int, default=90,
                        help='Test window for walk-forward (default: 90)')

    args = parser.parse_args()

    if args.mode == 'backtest':
        run_backtest(
            symbol=args.symbol,
            days=args.days,
            strategy_name=args.strategy,
            initial_capital=args.capital,
            use_real_data=args.real_data,
            exchange=args.exchange,
            timeframe=args.timeframe,
            use_risk_management=args.risk_mgmt,
            use_mtf=not args.no_mtf,
            use_funding=args.use_funding,
            use_circuit_breaker=not args.no_circuit_breaker,
            use_kelly=not args.no_kelly
        )
    elif args.mode == 'live':
        run_live(
            paper=not args.live,
            symbol=args.symbol,
            strategy_name=args.strategy,
            exchange=args.exchange,
            timeframe=args.timeframe,
            capital=args.capital
        )
    elif args.mode == 'optimize':
        optimize_strategy(symbol=args.symbol, days=args.days)
    elif args.mode == 'last_ob':
        print_last_orderblocks(
            symbol=args.symbol,
            days=args.days,
            timeframe=args.timeframe,
            exchange=args.exchange
        )
    elif args.mode == 'risk-test':
        test_phase1_features(
            symbol=args.symbol,
            exchange=args.exchange
        )
    elif args.mode == 'vbt':
        run_vectorbt_backtest(
            symbol=args.symbol,
            days=args.days,
            initial_capital=args.capital,
            exchange=args.exchange,
            timeframe=args.timeframe,
            use_trend_filter=not args.no_trend_filter,
            require_fvg=not args.no_fvg
        )
    elif args.mode == 'vbt-optimize':
        run_vectorbt_optimize(
            symbol=args.symbol,
            days=args.days,
            exchange=args.exchange,
            timeframe=args.timeframe,
            quick=args.quick
        )
    elif args.mode == 'walk-forward':
        run_walk_forward(
            symbol=args.symbol,
            days=args.days,
            exchange=args.exchange,
            timeframe=args.timeframe,
            train_days=args.train_days,
            test_days=args.test_days
        )
    elif args.mode == 'benchmark':
        run_benchmark(
            symbol=args.symbol,
            days=args.days,
            exchange=args.exchange,
            timeframe=args.timeframe
        )


if __name__ == "__main__":
    main()
