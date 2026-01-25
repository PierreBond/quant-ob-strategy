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

### Backtesting

```bash
# Basic backtest with sample data
python main.py --mode backtest --days 30

# Backtest with custom capital
python main.py --mode backtest --days 60 --capital 5000

# Test different strategies
python main.py --mode backtest --strategy sma --days 30
```

### Live Trading

```bash
# Paper trading (recommended for testing)
python main.py --mode live --paper

# Live trading (requires API keys)
python main.py --mode live
```

### Parameter Optimization

```bash
# Find best parameters
python main.py --mode optimize --days 30
```

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
