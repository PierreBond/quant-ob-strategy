# 🤖 Order Block Trading Bot

A Python trading bot implementing Smart Money Concepts (SMC) order block strategy, ported from PineScript.

## Features

- 📊 **Order Block Detection** - Identifies bullish and bearish order blocks
- 📈 **Break of Structure (BOS)** - Detects market structure changes
- 🔄 **OB Mitigation Tracking** - Monitors when order blocks are invalidated
- 📉 **Backtesting Engine** - Test strategies with realistic simulation
- 🚀 **Live Trading** - Execute trades via CCXT on exchanges
- 📱 **Telegram Alerts** - Get notified of signals and trades

## Project Structure

```
trading_bot/
├── config/
│   └── settings.py          # Configuration (capital, risk, API keys)
├── data/
│   └── market_data.py       # CCXT data fetching & caching
├── backtest/
│   └── engine.py            # Backtesting engine
├── strategies/
│   ├── base.py              # Base strategy class
│   └── orderblock.py        # Order block strategy (PineScript port)
├── execution/
│   └── live_trader.py       # Live trading execution
├── utils/
│   └── notifications.py     # Telegram alerts
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Installation

### 1. Clone and Install Dependencies

```bash
cd /workspace/trading_bot

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Settings

Edit `config/settings.py` with your preferences:

```python
# Trading settings
INITIAL_CAPITAL = 10000.0      # Starting capital
RISK_PER_TRADE = 0.02          # 2% risk per trade
TIMEFRAME = "15m"              # Candle timeframe
SYMBOL = "BTC/USDT"            # Trading pair

# Exchange settings
EXCHANGE = "binance"           # binance, coinbase, kraken
TESTNET = True                 # Use testnet (recommended for testing)
PAPER_TRADING = True           # Paper trading mode (no real money)
```

### 3. (Optional) Configure Telegram Alerts

```python
# In config/settings.py
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "your_bot_token_here"
TELEGRAM_CHAT_ID = "your_chat_id_here"
```

#### Getting Telegram Bot Token

1. Message @BotFather on Telegram
2. Send `/newbot` to create a new bot
3. Follow instructions to get your bot token
4. Start a conversation with your bot (send any message)
5. Get your chat ID from @userinfobot or add the bot to your group

## Usage

### Command Line Options

```bash
python main.py --help
```

| Argument | Options | Default | Description |
|----------|---------|---------|-------------|
| `--mode` | `backtest`, `live`, `optimize` | `backtest` | Operating mode |
| `--strategy` | See strategies table | `orderblock_premium` | Trading strategy |
| `--days` | 1-365+ | 30 | Backtest period (days from today) |
| `--capital` | Any positive number | 10000 | Starting capital ($) |
| `--timeframe` | `1m`, `5m`, `15m`, `1h`, `4h`, `1d` | `15m` | Candle timeframe |
| `--symbol` | e.g. `BTC/USDT` | `BTC/USDT` | Trading pair |
| `--exchange` | `binance`, `bybit`, `okx`, `kucoin`, `coinbase`, `kraken` | `binance` | Exchange |
| `--real-data` | flag | False | Use real market data (recommended) |
| `--live` | flag | False | Enable real trading (requires API keys) |

---

## 📊 Available Strategies

| Strategy | Command Value | Description | Best For |
|----------|--------------|-------------|----------|
| **Premium V1** | `orderblock_premium` | Aggressive, FVG+displacement, 3:1 R:R | ≤30 days |
| **Premium V2** | `orderblock_premium_v2` | Conservative, trend filter, dynamic R:R, partial TP | 90-180 days |
| **Premium V3** | `orderblock_premium_v3` | Hybrid: V1 for first 30d, then V2 | 60-120 days |
| **Basic** | `orderblock` | Simple order block strategy | Testing |
| **All OBs** | `orderblock_all` | Trades all order blocks | Testing |
| **Inverse** | `orderblock_inverse` | Opposite signals | Testing |

### Strategy Performance Summary (BTC/USDT 15m)

| Period | V1 Return | V2 Return | V3 Return | 🏆 Best |
|--------|-----------|-----------|-----------|---------|
| 30 days | **+3.01%** | +1.67% | +2.98% | V1 |
| 60 days | +3.37% | +5.32% | **+5.61%** | V3 |
| 90 days | +14.34% | +15.86% | **+17.41%** | V3 |
| 180 days | +4.73% | **+12.16%** | +11.98% | V2 |
| 240 days | -3.53% | **+6.59%** | +5.77% | V2 |
| 365 days | -21.11% | **-10.40%** | -14.17% | V2 |

---

## 🧪 Backtesting Commands

### Basic Backtest
```bash
# Default: 30 days, Premium V1, BTC/USDT, 15m
python main.py --mode backtest --real-data
```

### Premium V1 (Aggressive) - Best for ≤30 days
```bash
# 30-day backtest
python main.py --mode backtest --days 30 --strategy orderblock_premium --real-data --exchange binance --timeframe 15m --symbol BTC/USDT

# 90-day backtest (peak performance ~+14%)
python main.py --mode backtest --days 90 --strategy orderblock_premium --real-data --exchange binance --timeframe 15m --symbol BTC/USDT
```

### Premium V2 (Conservative) - Best for 90-180 days
```bash
# 90-day backtest (~+16% return, 56% win rate)
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --exchange binance --timeframe 15m --symbol BTC/USDT

# 180-day backtest (~+12% return)
python main.py --mode backtest --days 180 --strategy orderblock_premium_v2 --real-data --exchange binance --timeframe 15m --symbol BTC/USDT

# 365-day backtest (shows strategy degradation)
python main.py --mode backtest --days 365 --strategy orderblock_premium_v2 --real-data --exchange binance --timeframe 15m --symbol BTC/USDT
```

### Premium V3 (Hybrid) - Best for 60-120 days
```bash
# 90-day backtest (best overall: +17.41%, PF 2.02)
python main.py --mode backtest --days 90 --strategy orderblock_premium_v3 --real-data --exchange binance --timeframe 15m --symbol BTC/USDT

# 120-day backtest
python main.py --mode backtest --days 120 --strategy orderblock_premium_v3 --real-data --exchange binance --timeframe 15m --symbol BTC/USDT
```

### Different Timeframes (⚠️ Not Recommended)
```bash
# 5-minute timeframe (too noisy, loses money)
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --timeframe 5m --symbol BTC/USDT

# 1-hour timeframe (too slow, loses money)
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --timeframe 1h --symbol BTC/USDT
```

### Different Exchanges
```bash
# Bybit
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --exchange bybit --timeframe 15m --symbol BTC/USDT

# OKX
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --exchange okx --timeframe 15m --symbol BTC/USDT

# Kraken
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --exchange kraken --timeframe 15m --symbol BTC/USDT
```

### Custom Capital
```bash
# Start with $5,000
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --capital 5000

# Start with $50,000
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --capital 50000
```

### Batch Testing (PowerShell)
```powershell
# Test all periods at once
@(30, 60, 90, 180, 365) | ForEach-Object { 
    Write-Host "===== $_ DAYS ====="; 
    python main.py --mode backtest --days $_ --strategy orderblock_premium_v2 --real-data 
}
```

---

## 🚀 Live Trading Commands

### Paper Trading (No Real Money)
```bash
# Paper trade with V3 (recommended)
python main.py --mode live --strategy orderblock_premium_v3 --exchange binance --timeframe 15m --symbol BTC/USDT

# Paper trade with V2
python main.py --mode live --strategy orderblock_premium_v2 --exchange binance --timeframe 15m --symbol BTC/USDT
```

### Real Trading (Requires API Keys)
```bash
# ⚠️ REAL MONEY - Use with caution!
python main.py --mode live --live --strategy orderblock_premium_v2 --exchange binance --timeframe 15m --symbol BTC/USDT
```

### Live Trading Setup Checklist
1. ✅ Configure API keys in `config/settings.py`
2. ✅ Set `PAPER_TRADING = False` for real trading
3. ✅ Set `TESTNET = False` for mainnet
4. ✅ Enable IP whitelist on exchange
5. ✅ Start with small capital to test

---

## 📈 Parameter Optimization

```bash
# Find best parameters for V2
python main.py --mode optimize --days 90 --strategy orderblock_premium_v2

# Optimize with custom capital
python main.py --mode optimize --days 60 --capital 5000
```

---

## 📱 Telegram Notifications

Enable Telegram alerts in `config/settings.py`:

```python
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "your_bot_token_here"
TELEGRAM_CHAT_ID = "your_chat_id_here"
```

Notifications include:
- 🟢 Trade entry signals
- 🔴 Trade exit signals
- 💰 Profit/loss updates
- ⚠️ Drawdown warnings

---

## ⚡ Quick Start Examples

### Beginner: Test the Strategy
```bash
# 1. Run a 30-day backtest to see how it works
python main.py --mode backtest --days 30 --strategy orderblock_premium_v2 --real-data

# 2. View results in results/ folder
```

### Intermediate: Compare Strategies
```bash
# Compare V1, V2, V3 over 90 days
python main.py --mode backtest --days 90 --strategy orderblock_premium --real-data
python main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data
python main.py --mode backtest --days 90 --strategy orderblock_premium_v3 --real-data
```

### Advanced: Start Paper Trading
```bash
# Paper trade with best strategy (V3 for ~90 days)
python main.py --mode live --strategy orderblock_premium_v3 --exchange binance --timeframe 15m --symbol BTC/USDT
```

---

## 📋 Output Files

All backtest results are saved to:

| File | Location | Contents |
|------|----------|----------|
| Trade log | `results/trades_YYYYMMDD_HHMMSS.csv` | All trades with entry/exit prices |
| Summary | `results/backtest_YYYYMMDD_HHMMSS.json` | Performance metrics |
| Chart | `charts/backtest_YYYYMMDD_HHMMSS.png` | Equity curve visualization |
| Strategy summary | `results/premium_strategy_summary.json` | All strategy comparisons |

---

## 🛡️ Phase 1: Risk Management Features

Advanced risk management tools to improve capital preservation and trade quality.

### Features Overview

| Feature | Module | Purpose |
|---------|--------|---------|
| **Kelly Criterion** | `utils/position_sizing.py` | Optimal position sizing based on win rate & profit factor |
| **Circuit Breaker** | `utils/circuit_breaker.py` | Auto-pause trading on drawdown/loss limits |
| **Multi-Timeframe** | `utils/multi_timeframe.py` | Confirm trades with higher TF trend |
| **Funding Rate** | `utils/funding_rate.py` | Filter trades based on futures funding |
| **Risk Manager** | `utils/risk_manager.py` | Unified manager combining all features |

### Test All Risk Features

```bash
# Test all Phase 1 risk management features
python main.py --mode risk-test --symbol BTC/USDT --exchange binance
```

**Expected Output:**
```
✅ All Phase 1 modules imported successfully

TEST 1: KELLY CRITERION POSITION SIZING
  Win Rate: 50.0%, Profit Factor: 1.79 → Recommended: 5.5%
  ✅ PASS

TEST 2: CIRCUIT BREAKER
  3 consecutive losses → PAUSED (1 min cooldown)
  ✅ PASS

TEST 3: MULTI-TIMEFRAME ANALYSIS
  15m: STRONG_BEARISH, 1h: STRONG_BEARISH, 4h: STRONG_BEARISH
  LONG: ❌ (0/2), SHORT: ✅ (2/2)
  ✅ PASS

TEST 4: FUNDING RATE FILTER
  Current: 0.0023%, Annualized: 2.49%, Sentiment: neutral
  ✅ PASS

TEST 5: UNIFIED RISK MANAGER
  LONG: ❌ (MTF rejection), SHORT: ✅ (2.0% size)
  ✅ PASS
```

### Using Risk Manager in Strategy

```python
from utils import RiskManager

# Initialize with your capital
rm = RiskManager(
    capital=10000,
    exchange_id='binance',
    use_mtf=True,           # Multi-timeframe confirmation
    use_funding=True,       # Funding rate filter
    use_circuit_breaker=True,  # Auto-pause on losses
    use_kelly=True          # Kelly position sizing
)

# Before taking any trade
decision = rm.evaluate_trade(
    symbol='BTC/USDT',
    direction='LONG',      # or 'SHORT'
    entry_timeframe='15m'
)

if decision.can_trade:
    print(f"✅ Trade approved: {decision.position_size_pct:.1%} position")
    # Execute trade with decision.position_size_pct
else:
    print(f"❌ Trade rejected: {decision.reasons}")

# After trade closes, update the manager
rm.update_capital(new_balance, trade_won=True)
```

### Individual Components

#### Kelly Criterion (Position Sizing)
```python
from utils import PositionSizer

sizer = PositionSizer(
    max_position_pct=0.25,    # Max 25% per trade
    kelly_fraction=0.25,      # Use 1/4 Kelly (conservative)
    min_trades_for_kelly=20   # Need 20+ trades for Kelly
)

# Record trades to build history
sizer.add_trade(pnl_pct=0.03, won=True)   # 3% win
sizer.add_trade(pnl_pct=-0.02, won=False) # 2% loss

# Get recommended size
size, reason = sizer.get_position_size(current_atr_pct=0.02)
print(f"Recommended: {size:.1%} - {reason}")
```

#### Circuit Breaker (Auto-Pause)
```python
from utils import CircuitBreaker, CircuitBreakerConfig

config = CircuitBreakerConfig(
    max_drawdown_pct=0.15,      # 15% max drawdown → STOP
    max_daily_loss_pct=0.05,    # 5% daily loss → PAUSE
    max_consecutive_losses=5,    # 5 losses → PAUSE
    cooldown_minutes=60          # 1 hour cooldown
)

breaker = CircuitBreaker(config)
breaker.initialize(capital=10000)

# After each trade
breaker.update(current_capital=9500, trade_won=False)

# Before next trade
if breaker.can_trade():
    # Execute trade
    pass
else:
    print(f"Trading paused: {breaker.get_status()['state']}")
```

#### Multi-Timeframe Analysis
```python
from utils import MultiTimeframeAnalyzer

mtf = MultiTimeframeAnalyzer(exchange_id='binance')

# Fetch data for multiple timeframes
mtf.fetch_all_timeframes('BTC/USDT', timeframes=['15m', '1h', '4h', '1d'])

# Check if higher TFs confirm your trade
confirmed, details = mtf.get_confirmation('15m', 'LONG')
if confirmed:
    print(f"LONG confirmed by {details['confirmation_rate']} higher TFs")
else:
    print("LONG rejected - higher TFs don't confirm")

# Get overall trend score (-1 to +1)
score, description = mtf.get_trend_alignment_score()
print(f"Trend: {description} (score: {score:+.2f})")
```

#### Funding Rate Filter
```python
from utils import FundingRateFilter

funding = FundingRateFilter(exchange_id='binance')

# Check funding for a symbol
info = funding.get_funding_rate('BTCUSDT')
print(f"Funding: {info.rate_pct:.4f}% ({info.sentiment})")

# Check if trade should be avoided
avoid, reason = funding.should_avoid_trade('BTCUSDT', 'LONG')
if avoid:
    print(f"Skip LONG: {reason}")

# Get contrarian bias
bias, confidence, reason = funding.get_funding_bias('BTCUSDT')
print(f"Funding bias: {bias} (confidence: {confidence:.0%})")
```

### Risk Management Thresholds

| Metric | Default | Action |
|--------|---------|--------|
| Max Drawdown | 15% | **STOP** trading (manual reset) |
| Daily Loss | 5% | **PAUSE** (4hr cooldown) |
| Consecutive Losses | 5 | **PAUSE** (1hr cooldown) |
| MTF Alignment | 50% | Reject if < 50% TFs confirm |
| Extreme Funding | ±0.05% | Warn/avoid overleveraged side |

---

## ⚠️ Important Recommendations

| Rule | Explanation |
|------|-------------|
| **Only use 15m timeframe** | 5m too noisy, 1h too slow |
| **Only trade BTC/USDT** | Strategy fails on ETH, Gold |
| **Reset every 90-120 days** | Strategy degrades over time |
| **Use V3 for 60-120 days** | Best overall returns |
| **Use V2 for 120+ days** | Most conservative |
| **Never run 365 days straight** | All strategies lose money |

## Strategy Parameters

### OrderBlockStrategy

```python
from strategies.orderblock import OrderBlockStrategy

strategy = OrderBlockStrategy(
    input_range=25,          # Swing detection range (candles)
    min_risk_reward=1.5,     # Minimum risk/reward ratio
    sl_atr_mult=2.0,         # SL = OB edge ± ATR × multiplier
    tp_rr_mult=2.0,          # TP = distance × RR multiplier
    first_retest_only=True,  # Only trade first retest
    position_size=0.5        # Position size (0-1)
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_range` | 25 | Range for swing high/low detection |
| `min_risk_reward` | 1.5 | Minimum R:R ratio required for trade |
| `sl_atr_mult` | 2.0 | Stop loss distance in ATR multiples |
| `tp_rr_mult` | 2.0 | Take profit distance (× distance to SL) |
| `first_retest_only` | True | Only trade first OB retest |
| `position_size` | 0.5 | % of capital per trade (0.5 = 50%) |

### Custom Strategy Example

```python
from strategies.base import Strategy

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__("MyStrategy")

    def on_init(self, df):
        """Initialize with indicators"""
        df['sma'] = df['close'].rolling(20).mean()

    def on_bar(self, df, position):
        """Generate signals"""
        current = df.iloc[-1]
        prev = df.iloc[-2]

        if position == "FLAT":
            # Golden cross
            if prev['close'] <= prev['sma'] and current['close'] > current['sma']:
                return {
                    'signal': 'LONG',
                    'sl': current['close'] * 0.98,
                    'tp': current['close'] * 1.04,
                    'size': 0.5
                }
        else:
            # Death cross
            if prev['close'] >= prev['sma'] and current['close'] < current['sma']:
                return {'signal': 'FLAT'}

        return {'signal': 'FLAT'}
```

## API Keys Setup

### Binance

1. Go to [Binance API Management](https://www.binance.com/en/usercenter/settings/api-management)
2. Create a new API key
3. Enable "Read" and "Spot Trading" permissions
4. If using testnet, get keys from [Binance Testnet](https://testnet.binance.vision)

```python
# In config/settings.py or pass directly
api_key = "your_api_key"
api_secret = "your_api_secret"
```

### Coinbase

1. Go to [Coinbase API Access](https://www.coinbase.com/settings/api-access)
2. Create new API key with trading permissions

### Kraken

1. Go to [Kraken API Settings](https://www.kraken.com/u/settings/api)
2. Generate API key with trading/query permissions

## Telegram Commands

When bot is running with Telegram enabled:

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/status` | Show current position |
| `/pnl` | Show daily P&L |
| `/open` | Show open positions |
| `/last_signal` | Show last trade signal |

## Risk Warning

⚠️ **IMPORTANT**: Trading involves substantial risk of loss.

- Never trade with money you can't afford to lose
- Always use stop losses
- Start with paper trading to test strategies
- Past performance does not guarantee future results
- The bot is provided as-is without warranty

## Troubleshooting

### Common Issues

**"Module not found" errors**
```bash
pip install -r requirements.txt
```

**"Binance API unavailable"**
- Check your IP is not geo-restricted
- Use a VPN if needed
- Try testnet first

**Telegram not working**
- Verify bot token is correct
- Ensure bot was started with /start
- Check chat ID is correct

### Logging

Logs are printed to console with configurable verbosity:

```python
import logging
logging.basicConfig(level=logging.DEBUG)  # Full debug output
```

## License

MIT License - Use at your own risk.

## Contributing

Pull requests welcome! Please open an issue first for major changes.

---

**Disclaimer**: This software is for educational purposes only. It is not financial advice. Use at your own risk.
