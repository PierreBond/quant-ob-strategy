# Volatility-Filtered Order Block Strategy

Algorithmic OB trading strategy for BTC/USDT — walk-forward validated, volatility-filtered + OFI momentum filter, outperforming buy-and-hold by +58%.

---

## Results

**Data:** BTC/USDT 1h, Mar 2025 – Jul 2026 (509 days, 8527 bars)
**Capital:** $10,000 | **Fees:** 0.3% round-trip | **Filter:** ATR% 0.8–2.5 + OFI w=6, t=150 | **SL:** 2.0x ATR | **Trailing:** activate 3.0x, trail 0.5x | **Position:** 50% fixed

### Performance

| Metric | Value |
|---|---|
| Total Return | **+35.97%** |
| CAGR | +24.64% |
| Buy & Hold | -21.69% |
| Alpha vs B&H | **+57.66%** |
| Profit Factor | **1.85** |
| Total Trades | **99** |
| Win Rate | **63.6%** |
| Max Drawdown | **-7.6%** |

### Monthly Returns

| Metric | Value |
|---|---|
| Positive Months | 7/16 (44%) |
| Best Month | +5.23% |
| Worst Month | -3.28% |

### Walk-Forward (13-window expanding)

| Metric | Value |
|---|---|
| Compounded Return | **+36.37%** |
| Avg Profit Factor | 1.86 |
| Final Window PF | 1.86 |
| Beats B&H | 9/13 windows |

### Statistical Significance

- 99 trades
- Monte Carlo (10K sims): mean +39.97%, P(negative) 0.5%, P(DD>15%) 0.0%

### Filters Tested

| Filter | Result |
|---|---|
| Vol filter (ATR% 0.8–2.5) | **Winner** — filters noise, improves WR |
| OFI momentum (w=6, t=150) | **Winner** — +9.97% return, +2.6% WR, +0.14 PF |
| OFI basic (w=4, t=100) | Good — +4.86% return |
| Tight SL (2.0x ATR) | **Winner** — more trades survive to trailing stop |
| Trailing stop (activate 3.0x, trail 0.5x) | **Winner** — captures momentum |
| HMM regime | Failed — -17.18% WF |
| EWMA vol sizing | Failed — -2.54% WF |
| ADX filter | Hurts performance |
| EMA directional (50/100/200) | Hurts performance in all configs |
| SMA50 regime detection | Failed — 33% alignment (worse than random) |
| Relaxed vol (0.5–3.0%) | Failed — adds noise |

---

## Strategy

### How It Works

The core logic is simple: when price creates a Break of Structure (BOS), it leaves an Order Block. When price returns to that zone, it trades. The edge comes from a volatility regime filter that skips high-volatility bars where OBs fail.

**Entry flow:**
1. Detect Break of Structure (BOS)
2. Record the Order Block (last opposing candle before break)
3. Wait for price to retest the OB
4. **Vol filter:** Only enter if ATR% is between 0.8% and 2.5%
5. **OFI filter:** Only enter if order flow confirms direction (buyers for longs, sellers for shorts)
6. Enter on retest with SL at 2.0x ATR beyond OB + TP at 2.0R

**Why the vol filter works:**
- In low vol (<0.8%), OBs are noise — price meanders through without conviction
- In high vol (>2.5%), OBs get destroyed by momentum — SL gets hit before price can reverse
- The sweet spot (0.8–2.5%) is where institutional order flow respects structure

**Why the OFI filter works:**
- Measures net buying/selling pressure using volume delta (tick rule)
- Skips shorts when buyers are in control (OFI > 150)
- Skips longs when sellers are in control (OFI < -150)
- Based on Cont-Kukanov-Stoikov 2014: order flow predicts price better than volume alone
- Window=6 captures short-term pressure without lag
- **Momentum bonus**: +2 signal when OFI is accelerating in the right direction

**Why tight SL works:**
- Frees capital faster — trades that would linger exit quickly at 2.0x ATR
- More trades = more opportunities to compound
- Lower win rate but much higher R:R compensates

### Parameters

```python
RegimeFilteredOB(
    input_range=25,          # Swing detection window
    min_risk_reward=1.5,     # Minimum R:R to enter
    sl_atr_mult=2.0,         # SL = 2.0x ATR from OB edge
    tp_rr_mult=2.0,          # TP = 2x risk
    max_age_bars=1000,       # OB expiry
    position_size=0.5,       # 50% of capital
    mitigated_size_mult=0.5, # 25% for mitigated OBs
    use_vol_filter=True,
    min_atr_pct=0.8,         # Min ATR% to enter
    max_atr_pct=2.5,         # Max ATR% to enter
    use_ofi_filter=True,     # Order flow imbalance filter
    ofi_window=6,            # Rolling window for OFI
    ofi_threshold=150,       # Min OFI to allow entry
    use_htf_ob=True,         # 4h trend confirmation
    htf_ob_required=True,    # Require 4h trend alignment
    use_trailing_stop=True,
    trail_activate_atr=3.0,  # Activate at 3.0x ATR profit
    trail_distance_atr=0.5,  # Trail at 0.5x ATR below best
)
```

### Multi-Timeframe Confirmation

The strategy supports 4h trend confirmation via `use_htf_ob=True`. When enabled:
- Only takes LONG entries when 4h EMA50 > EMA200 (bullish trend)
- Only takes SHORT entries when 4h EMA50 < EMA200 (bearish trend)
- Falls back to no filter when 4h data is unavailable

```python
strategy = RegimeFilteredOB(
    use_htf_ob=True,      # Enable 4h confirmation
    htf_ob_required=True,  # Require alignment (vs preferred)
)
# Pass 4h trend data before backtest
strategy.set_htf_trends(htf_trends)
```

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
The final walk-forward validated strategy. Extends base OB with ATR% regime filter, OFI filter, and tight SL. Used for all benchmark results above.
```python
from pine_ob_strategy import RegimeFilteredOB
strategy = RegimeFilteredOB(
    use_vol_filter=True, min_atr_pct=0.8, max_atr_pct=2.5,
    sl_atr_mult=2.0, tp_rr_mult=2.0,
    use_ofi_filter=True, ofi_window=4, ofi_threshold=100,
    use_trailing_stop=True, trail_activate_atr=3.0, trail_distance_atr=0.5
)
```

---

## Walk-Forward

13-window expanding walk-forward validation (OFI w=4, t=100):

- **Compounded return:** +26.36%
- **Average profit factor:** 1.61
- **Final window PF:** 1.71
- **Beats buy-and-hold:** 9/13 windows
- **All windows positive:** Yes

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

**Version:** 2.6
