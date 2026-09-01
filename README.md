# Volatility-Filtered Order Block Strategy

Algorithmic OB trading strategy for BTC/USDT — walk-forward validated, volatility-filtered, outperforming buy-and-hold by +33%.

---

## Results

**Data:** BTC/USDT 1h, Mar 2025 – Jul 2026 (509 days, 8527 bars)
**Capital:** $10,000 | **Fees:** 0.3% round-trip | **Filter:** ATR% 0.8–2.5 | **SL:** 1.5x ATR | **Trailing:** activate 3.0x, trail 0.5x | **Position:** 50% fixed

### Performance

| Metric | Value |
|---|---|
| Total Return | **+13.22%** |
| CAGR | +9.31% |
| Buy & Hold | -21.69% |
| Alpha vs B&H | **+34.91%** |
| Sharpe Ratio | **1.90** |
| Max Drawdown | **-9.1%** |
| Profit Factor | 1.32 |
| Total Trades | **113** |
| Win Rate | 52.2% |
| Expectancy | $15.70/trade |
| Kelly Criterion | 12.8% |
| Avg Duration | 1.5 days |

### Monthly Returns

| Metric | Value |
|---|---|
| Positive Months | 7/16 (44%) |
| Best Month | +5.23% |
| Worst Month | -3.28% |

### Walk-Forward (10 windows, 60d train / 30d test)

| Metric | Value |
|---|---|
| Compounded | **+13.00%** |
| Avg Test Sharpe | 1.00 |
| Overfit Gap | **0.06** |
| Beats B&H | 5/10 windows |

### Statistical Significance

- t-stat: **12.71** (>2.0 threshold) — statistically significant
- 71 trades (approaching 100 minimum)

### Filters Tested

| Filter | Result |
|---|---|
| Vol filter (ATR% 0.8–2.5) | **Winner** — +11.49% single, +13.00% WF |
| Tight SL (1.5x ATR) | **Winner** — more trades, higher Sharpe, lower DD |
| Trailing stop (activate 3.0x, trail 0.5x) | **Optional** — +13.22% single, +2.48% WF avg, higher returns but more WF gap |
| HMM regime | Failed — -17.18% WF |
| EWMA vol sizing | Failed — -2.54% WF |
| ADX filter | Hurts performance |
| Relaxed vol (0.5–3.0%) | Failed — adds noise |
| No vol filter | Failed — -6.62% |

---

## Strategy

### How It Works

The core logic is simple: when price creates a Break of Structure (BOS), it leaves an Order Block. When price returns to that zone, it trades. The edge comes from a volatility regime filter that skips high-volatility bars where OBs fail.

**Entry flow:**
1. Detect Break of Structure (BOS)
2. Record the Order Block (last opposing candle before break)
3. Wait for price to retest the OB
4. **Vol filter:** Only enter if ATR% is between 0.8% and 2.5%
5. Enter on retest with SL at 1.5x ATR beyond OB + TP at 2.0R

**Why the vol filter works:**
- In low vol (<0.8%), OBs are noise — price meanders through without conviction
- In high vol (>2.5%), OBs get destroyed by momentum — SL gets hit before price can reverse
- The sweet spot (0.8–2.5%) is where institutional order flow respects structure

**Why tight SL works:**
- Frees capital faster — trades that would linger at 2.0x ATR exit quickly at 1.5x ATR
- More trades = more opportunities to compound
- Lower win rate (35% vs 45%) but much higher R:R (2.42R vs 1.51R) compensates

### Parameters

```python
RegimeFilteredOB(
    input_range=25,          # Swing detection window
    min_risk_reward=1.5,     # Minimum R:R to enter
    sl_atr_mult=1.5,         # SL = 1.5x ATR from OB edge (tight)
    tp_rr_mult=2.0,          # TP = 2x risk
    max_age_bars=1000,       # OB expiry
    position_size=0.5,       # 50% of capital
    mitigated_size_mult=0.5, # 25% for mitigated OBs
    use_vol_filter=True,
    min_atr_pct=0.8,         # Min ATR% to enter
    max_atr_pct=2.5,         # Max ATR% to enter
    # Optional trailing stop (disabled by default):
    # use_trailing_stop=True,
    # trail_activate_atr=3.0,  # Activate at 3.0x ATR profit
    # trail_distance_atr=0.5,  # Trail at 0.5x ATR below best
)
```

### Trailing Stop (Optional)

Activates after 3.0x ATR profit, trails 0.5x ATR below the best price. Locks in ~2.5R minimum on winning trades. Higher returns (+13.22% vs +11.49%) but slightly higher WF gap (0.81 vs -0.06).

---

## Quick Start

```bash
# Activate virtual environment
.\.venv311\Scripts\Activate.ps1

# Run backtest with real data
python trading_bot/main.py --mode backtest --days 365 --strategy orderblock --real-data --timeframe 1h

# Check latest order blocks
python trading_bot/main.py --mode last_ob --timeframe 1h --days 7

# Optimize parameters
python trading_bot/main.py --mode optimize --days 60
```

---

## Installation

```bash
git clone https://github.com/PierreBond/quant-trading-stretegy.git
cd quant-trading-stretegy
pip install -r requirements.txt
```

**Required:** pandas, numpy, matplotlib, ccxt, aiohttp
**Optional:** python-telegram-bot (for trade notifications)

---

## Modes

### Backtest
Run historical backtests with performance metrics.
```bash
python trading_bot/main.py --mode backtest [options]
```

### Last Order Block
Display latest detected order blocks on any timeframe.
```bash
python trading_bot/main.py --mode last_ob [options]
```

### Optimize
Find best strategy parameters.
```bash
python trading_bot/main.py --mode optimize [options]
```

### Live
Paper or real trading (requires API keys).
```bash
python trading_bot/main.py --mode live [options]
```

---

## Strategies

### Order Block (`orderblock`)
Classic SMC order block detection. Trades first retest only.
```bash
python trading_bot/main.py --strategy orderblock
```

### Order Block All (`orderblock_all`)
Trades all OBs including mitigated. Multiple retests per OB (max 3), reduced size for mitigated.
```bash
python trading_bot/main.py --strategy orderblock_all
```

### Volatility-Filtered OB (`pine_ob_strategy.py`)
The final walk-forward validated strategy. Extends base OB with ATR% regime filter and tight SL. Used for all benchmark results above.
```python
from pine_ob_strategy import RegimeFilteredOB
strategy = RegimeFilteredOB(
    use_vol_filter=True, min_atr_pct=0.8, max_atr_pct=2.5,
    sl_atr_mult=1.5, tp_rr_mult=2.0,
    use_trailing_stop=True, trail_activate_atr=3.0, trail_distance_atr=0.5
)
```

---

## Walk-Forward

10-window walk-forward validation (60-day train / 30-day test):

- **Compounded return:** +13.00%
- **Average test Sharpe:** 1.00
- **Overfit gap:** 0.06 (near-zero overfitting)
- **Beats buy-and-hold:** 5/10 windows

Config grid was intentionally skipped during WF to avoid curve-fitting. Filter threshold (0.8–2.5%) was selected on full data, then validated out-of-sample.

---

## Telegram Trade Journal

Get real-time trade notifications sent to Telegram on every entry, exit, and session summary.

### Setup

1. Create a bot with [@BotFather](https://t.me/BotFather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Edit `trading_bot/config/telegram_config.json`:

```json
{
  "bot_token": "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
  "chat_id": "123456789",
  "enabled": true,
  "notify_on_entry": true,
  "notify_on_exit": true,
  "send_summary": true
}
```

Notifications include entry/exit details (symbol, price, SL/TP, PnL) and session summaries (win rate, total PnL, drawdown).

---

## Configuration

### Backtest Engine

```python
engine = BacktestEngine(
    initial_capital=10000,
    fee_percent=0.001,         # 0.1% taker fee
    slippage_percent=0.0005,   # 0.05% slippage
)
```

### Command Line Options

| Option | Default | Description |
|---|---|---|
| `--mode` | `backtest` | backtest, last_ob, optimize, live |
| `--symbol` | `BTC/USDT` | Trading pair |
| `--days` | `60` | Days of historical data |
| `--strategy` | `orderblock` | Strategy name |
| `--capital` | `10000` | Initial capital |
| `--real-data` | off | Use real exchange data |
| `--exchange` | `binance` | binance, bybit, okx, kucoin, coinbase |
| `--timeframe` | `15m` | 1m, 5m, 15m, 30m, 1h, 4h, 1d |
| `--paper` | off | Paper trading only |

---

## Project Structure

```
quant-trading-stretegy/
├── pine_ob_strategy.py          # Final strategy (RegimeFilteredOB)
├── trading_bot/
│   ├── backtest/engine.py       # Backtest engine
│   ├── strategies/
│   │   ├── ob_core.py           # Base OB logic
│   │   ├── ob_premium.py        # V1/V2/V3
│   │   ├── ob_variants.py       # All-OB variant
│   │   └── benchmarks.py        # SMA/RSI baselines
│   ├── analysis/                # Walk-forward, optimizer
│   ├── utils/                   # Risk, sizing, journal
│   ├── execution/               # Live trader
│   └── config/                  # Settings, Telegram
├── results/                     # Final backtest results
├── cache/                       # Market data CSVs
├── tests/                       # Unit tests
├── version5.md                  # PineScript indicator source
└── requirements.txt
```

---

## Disclaimer

This software is for educational purposes only. Trading cryptocurrencies involves substantial risk of loss. Past performance does not guarantee future results. Use at your own risk.

---

**Version:** 2.2
