# Release Notes — v2.7

## What's New

### Correlation Filter (NEW)
- Skip trades when BTC-ETH correlation > 0.9
- Filters noise regimes where both assets move together without conviction
- **Result:** +43.32% return (vs +35.97% baseline), PF 2.21 (vs 1.85), WR 67.7% (vs 63.6%)

### Walk-Forward Validated
- 13-window expanding walk-forward: +30.73% compounded
- 8/12 positive windows (vs 6/12 baseline)
- Max DD: 3.7% (vs 4.7% baseline)

## Filters Tested This Release

| Filter | Result |
|---|---|
| Correlation filter (skip >0.9) | **Winner** — +7.35% return, +4.1% WR, +0.36 PF |
| Kelly criterion sizing | Failed — worse returns across all configs |
| Time-of-day filter | Hurts — loses too many good trades |
| Dynamic OFI threshold | Hurts — fixed threshold is better |

## Updated Stats

| Metric | v2.6 | v2.7 |
|---|---|---|
| Total Return | +35.97% | **+43.32%** |
| Profit Factor | 1.85 | **2.21** |
| Win Rate | 63.6% | **67.7%** |
| Max Drawdown | -7.6% | **-7.0%** |
| Alpha vs B&H | +57.66% | **+65.01%** |

## Files Changed

- `pine_ob_strategy.py` — Added correlation filter, removed Kelly criterion
- `trading_bot/backtest/engine.py` — Removed Kelly PnL tracking
- `README.md` — Updated to v2.7 with correlation filter results

## Breaking Changes

- Removed `use_kelly`, `kelly_fraction`, `kelly_lookback` parameters
- Added `use_corr_filter`, `corr_threshold`, `eth_df` parameters

## Upgrade

```python
# v2.6
strategy = RegimeFilteredOB(
    use_ofi_filter=True, ofi_window=6, ofi_threshold=150,
    use_trailing_stop=True, trail_activate_atr=3.0, trail_distance_atr=0.5,
)

# v2.7
strategy = RegimeFilteredOB(
    use_ofi_filter=True, ofi_window=6, ofi_threshold=150,
    use_corr_filter=True, corr_threshold=0.9, eth_df=eth_data,
    use_trailing_stop=True, trail_activate_atr=3.0, trail_distance_atr=0.5,
)
```
