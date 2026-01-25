# Quantitative Trading Strategy Bot

A Python-based algorithmic trading bot with Order Block detection strategies, real exchange data integration, and comprehensive backtesting capabilities.

---

## 🚀 Quick Start

```bash
# Activate virtual environment
.\.venv311\Scripts\Activate.ps1

# Run backtest with simulated data
python trading_bot/main.py --mode backtest --days 30 --strategy orderblock

# Run backtest with real Binance data
python trading_bot/main.py --mode backtest --days 30 --strategy orderblock --real-data

# Check latest order blocks on 1hr timeframe
python trading_bot/main.py --mode last_ob --timeframe 1h
```

---

## 📋 Table of Contents

- [Installation](#installation)
- [Available Modes](#available-modes)
- [Strategies](#strategies)
- [Command Reference](#command-reference)
- [Usage Examples](#usage-examples)
- [Data Sources](#data-sources)
- [Configuration](#configuration)

---

## 🔧 Installation

```bash
# Clone repository
git clone https://github.com/PierreBond/quant-trading-stretegy.git
cd quant-trading-stretegy

# Install dependencies
pip install -r requirements.txt
```

**Required Packages:**
- pandas
- numpy
- matplotlib
- ccxt (for exchange connectivity)
- aiohttp
- python-telegram-bot (optional, for notifications)

---

## 🎮 Available Modes

### 1. Backtest Mode
Run historical backtests on strategies with performance metrics.

```bash
python trading_bot/main.py --mode backtest [options]
```

### 2. Last Order Block Mode
Display the latest detected order blocks on any timeframe.

```bash
python trading_bot/main.py --mode last_ob [options]
```

### 3. Optimize Mode
Run parameter optimization to find best strategy settings.

```bash
python trading_bot/main.py --mode optimize [options]
```

### 4. Live Mode
Run live trading (paper or real - requires API keys).

```bash
python trading_bot/main.py --mode live [options]
```

---

## 📊 Strategies

### 1. **Order Block Strategy** (`orderblock`)
Classic Smart Money Concepts (SMC) order block detection and trading.

**Logic:**
- Detects Break of Structure (BOS)
- Creates bullish/bearish order blocks
- Enters on first retest only
- Removes OBs after mitigation

```bash
python trading_bot/main.py --strategy orderblock
```

### 2. **Order Block All** (`orderblock_all`)
Trades ALL order blocks including mitigated ones.

**Logic:**
- Trades both active AND mitigated OBs
- Multiple retests per OB (max: 3)
- Reduced position size for mitigated OBs (50%)
- Higher frequency trading

```bash
python trading_bot/main.py --strategy orderblock_all
```

### 3. **Order Block Inverse** (`orderblock_inverse`)
Contrarian strategy that inverts all signals.

**Logic:**
- SHORT on bullish OB retest (fade support)
- LONG on bearish OB retest (fade resistance)
- Best for ranging/choppy markets
- Targets OB failures

```bash
python trading_bot/main.py --strategy orderblock_inverse
```

### 4. **SMA Crossover** (`sma`)
Simple Moving Average crossover strategy (for testing).

```bash
python trading_bot/main.py --strategy sma
```

---

## 📖 Command Reference

### Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--mode` | choice | `backtest` | Mode: `backtest`, `last_ob`, `optimize`, `live` |
| `--symbol` | str | `BTC/USDT` | Trading pair (e.g., BTC/USDT, ETH/USDT) |
| `--days` | int | `60` | Number of days of historical data |
| `--strategy` | choice | `orderblock` | Strategy to use |
| `--capital` | float | `10000` | Initial capital for backtest |
| `--real-data` | flag | `False` | Use real exchange data instead of simulated |
| `--exchange` | choice | `binance` | Exchange: binance, bybit, okx, kucoin, coinbase |
| `--timeframe` | choice | `15m` | Candle timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d |
| `--paper` | flag | `False` | Use paper trading (live mode only) |
| `--live` | flag | `False` | Enable real trading (requires API keys) |

---

## 💡 Usage Examples

### Backtest Examples

**Basic backtest with simulated data:**
```bash
python trading_bot/main.py --mode backtest --days 30 --strategy orderblock
```

**Backtest with real Binance data (15min candles):**
```bash
python trading_bot/main.py --mode backtest --days 30 --strategy orderblock --real-data
```

**Backtest with 1hr timeframe:**
```bash
python trading_bot/main.py --mode backtest --days 60 --strategy orderblock --real-data --timeframe 1h
```

**Test inverse strategy on ETH:**
```bash
python trading_bot/main.py --mode backtest --symbol ETH/USDT --days 30 --strategy orderblock_inverse --real-data
```

**Higher frequency with orderblock_all:**
```bash
python trading_bot/main.py --mode backtest --days 90 --strategy orderblock_all --real-data --timeframe 15m
```

**Different exchange (Bybit):**
```bash
python trading_bot/main.py --mode backtest --days 30 --real-data --exchange bybit --timeframe 1h
```

**Custom capital:**
```bash
python trading_bot/main.py --mode backtest --days 30 --capital 5000 --real-data
```

### Order Block Detection Examples

**Check latest OBs on BTC 1hr:**
```bash
python trading_bot/main.py --mode last_ob --timeframe 1h --days 7
```

**Check ETH order blocks on 4hr:**
```bash
python trading_bot/main.py --mode last_ob --symbol ETH/USDT --timeframe 4h --days 14
```

**Different exchange:**
```bash
python trading_bot/main.py --mode last_ob --timeframe 1h --exchange bybit
```

### Optimization Examples

**Optimize strategy parameters:**
```bash
python trading_bot/main.py --mode optimize --days 60
```

**Optimize on specific symbol:**
```bash
python trading_bot/main.py --mode optimize --symbol ETH/USDT --days 90
```

### Live Trading Examples

**Paper trading (no real money):**
```bash
python trading_bot/main.py --mode live --paper
```

**Real trading (requires API keys):**
```bash
python trading_bot/main.py --mode live --live --symbol BTC/USDT
```

---

## 🌐 Data Sources

### Simulated Data (Default)
Random walk data generation for testing without exchange connectivity.

```bash
python trading_bot/main.py --mode backtest --days 30
```

### Real Exchange Data
Fetches historical OHLCV data from exchanges via CCXT (no API key required for public data).

```bash
python trading_bot/main.py --mode backtest --days 30 --real-data
```

**Supported Exchanges:**
- Binance (default)
- Bybit
- OKX
- KuCoin
- Coinbase

**Supported Timeframes:**
- 1m, 5m, 15m, 30m (short-term)
- 1h, 4h (medium-term)
- 1d (long-term)

---

## 📈 Output and Results

### Backtest Results

After each backtest, the bot generates:

**1. Console Output:**
- Trade-by-trade progress
- Performance metrics summary
- Win rate, profit factor, max drawdown

**2. Files Generated:**
```
results/
├── trades_YYYYMMDD_HHMMSS.csv      # Trade history
├── backtest_YYYYMMDD_HHMMSS.json   # Full results JSON
└── charts/
    └── backtest_YYYYMMDD_HHMMSS.png  # Equity curve chart
```

### Performance Metrics

| Metric | Description |
|--------|-------------|
| **Total Trades** | Number of completed trades |
| **Win Rate** | Percentage of winning trades |
| **Total PnL** | Net profit/loss in dollars |
| **Total Return** | Percentage return on capital |
| **Average Win** | Average winning trade (%) |
| **Average Loss** | Average losing trade (%) |
| **Profit Factor** | Gross profit / Gross loss |
| **Max Drawdown** | Largest peak-to-trough decline (%) |
| **Best/Worst Trade** | Single best and worst trades (%) |

### Order Block Information

When running backtests or `last_ob` mode, order blocks are displayed:

```
🟢 ============================================================
NEW BULLISH ORDER BLOCK DETECTED
============================================================
📍 Price Range:  $88,663.65 - $89,733.71
📏 OB Width:     $1,070.06 (1.21%)
💰 Current Price: $90,600.00
📊 Distance:     2.18% above OB
🕐 Created:      2026-01-23 17:00:00
📈 State:        ACTIVE
============================================================
```

---

## ⚙️ Configuration

### Strategy Parameters

Edit parameters in `main.py` or create custom strategy instances:

```python
# Order Block Strategy
strategy = OrderBlockStrategy(
    input_range=25,           # Swing detection range (bars)
    min_risk_reward=1.5,      # Minimum R:R ratio
    sl_atr_mult=2.0,          # Stop loss (ATR multiplier)
    tp_rr_mult=2.0,           # Take profit (R:R multiplier)
    first_retest_only=True,   # Only trade first retest
    position_size=0.5         # Position size (50% of capital)
)

# Order Block All Strategy
strategy = OrderBlockStrategyAll(
    max_retests=3,            # Max retests per OB
    mitigated_size_mult=0.5   # Size mult for mitigated OBs
)
```

### Backtest Engine Settings

```python
engine = BacktestEngine(
    initial_capital=10000,     # Starting capital
    fee_percent=0.001,         # Trading fee (0.1%)
    slippage_percent=0.0005,   # Slippage (0.05%)
    max_position_size=1.0      # Max position size (100%)
)
```

---

## 🔍 Order Block Detection Logic

The bot uses **Smart Money Concepts (SMC)** for OB identification:

### 1. Structure Tracking
- Tracks swing highs/lows within rolling window (default: 25 bars)
- Records last bullish and bearish candles

### 2. Bearish Order Block Creation
**Trigger:** Price breaks below structure low (swing low)  
**OB Placement:** Last bullish candle before the break  
**Logic:** Smart money placed sell orders in that candle

### 3. Bullish Order Block Creation
**Trigger:** Price breaks above a bearish OB top  
**OB Placement:** Last bearish candle before breakout  
**Mitigation:** Previous bearish OB is removed

### 4. Entry Signals
- **LONG:** Price retests bullish OB from above (touches top)
- **SHORT:** Price retests bearish OB from below (touches bottom)

---

## 🛡️ Risk Management

### Stop Loss Placement
- Placed beyond OB zone using ATR multiplier
- Default: 2.0 x ATR from OB boundary

### Take Profit Calculation
- Based on risk/reward ratio
- Default: 2.0 x risk distance

### Position Sizing
- Default: 50% of capital per trade
- Reduced to 25% for mitigated OBs (orderblock_all)

---

## 📞 Support & Contributing

**Issues:** [GitHub Issues](https://github.com/PierreBond/quant-trading-stretegy/issues)  
**Repository:** [GitHub](https://github.com/PierreBond/quant-trading-stretegy)

---

## ⚠️ Disclaimer

**This software is for educational purposes only. Trading cryptocurrencies involves substantial risk of loss. Past performance does not guarantee future results. Use at your own risk.**

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🎯 Quick Reference Card

```bash
# Backtest with real data (most common)
python trading_bot/main.py --mode backtest --days 30 --real-data

# Check latest order blocks
python trading_bot/main.py --mode last_ob --timeframe 1h

# Test inverse strategy
python trading_bot/main.py --mode backtest --strategy orderblock_inverse --real-data

# High frequency trading
python trading_bot/main.py --mode backtest --strategy orderblock_all --real-data

# Different symbols
python trading_bot/main.py --mode backtest --symbol ETH/USDT --real-data

# Optimize parameters
python trading_bot/main.py --mode optimize --days 60
```

---

**Last Updated:** January 25, 2026  
**Version:** 1.0.0
