import sys, builtins, logging, os, json
sys.stdout = type(sys.stdout)(sys.stdout.buffer, encoding='utf-8')
sys.stderr = type(sys.stderr)(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, '.')
import pandas as pd, numpy as np
from trading_bot.backtest.engine import BacktestEngine
from pine_ob_strategy import RegimeFilteredOB

logging.disable(logging.CRITICAL)
os.environ['TELEGRAM_TOKEN'] = ''
os.environ['TELEGRAM_CHAT_ID'] = ''
_orig = builtins.print
builtins.print = lambda *a, **kw: None

c = 'cache'; frames = []
for f in sorted(os.listdir(c)):
    if f.startswith('BTCUSDT_1h') and f.endswith('.csv'):
        df = pd.read_csv(os.path.join(c, f), index_col='timestamp', parse_dates=True).astype(float)
        frames.append(df)
df = pd.concat(frames).sort_index()
df = df[~df.index.duplicated(keep='first')]
print(f"Data: {df.index[0]} to {df.index[-1]}, {len(df)} bars", file=sys.stderr)

DATA_START = pd.Timestamp('2025-03-01')
windows = [
    ("W0",  "2025-05-31", "2025-06-01", "2025-06-30", True),
    ("W1",  "2025-06-30", "2025-10-01", "2025-10-31", True),
    ("W2",  "2025-10-31", "2025-11-01", "2025-11-30", True),
    ("W3",  "2025-11-30", "2025-12-01", "2025-12-31", False),
    ("W4",  "2025-12-31", "2026-01-01", "2026-01-31", False),
    ("W5",  "2026-01-31", "2026-02-01", "2026-02-28", False),
    ("W6",  "2026-02-28", "2026-03-01", "2026-03-31", False),
    ("W7",  "2026-03-31", "2026-04-01", "2026-04-30", False),
    ("W8a", "2026-04-30", "2026-05-01", "2026-05-31", False),
    ("W8b", "2026-05-31", "2026-06-01", "2026-06-30", False),
    ("W8c", "2026-06-30", "2026-07-01", "2026-07-10", False),
]

def make_strategy(sl_mult, position_size=0.5):
    return RegimeFilteredOB(
        input_range=25, min_risk_reward=1.5, sl_atr_mult=sl_mult, tp_rr_mult=2.0,
        max_age_bars=1000, position_size=position_size, mitigated_size_mult=0.5,
        use_vol_filter=True, min_atr_pct=0.8, max_atr_pct=2.5, use_adx_filter=False,
        use_trailing_stop=True, trail_activate_atr=3.0, trail_distance_atr=0.5,
    )

def make_engine():
    return BacktestEngine(
        initial_capital=10000, fee_percent=0.001, slippage_percent=0.0005,
        enable_journal=False, use_trailing_stop=True,
        trail_activate_atr=3.0, trail_distance_atr=0.5,
    )

configs = [("SL=1.5x", 1.5), ("SL=2.0x", 2.0)]

all_results = {}
for cfg_label, sl_mult in configs:
    results = []
    train_sharpes = []
    for wname, train_end, test_start, test_end, is_gap in windows:
        train_df = df[(df.index >= DATA_START) & (df.index <= pd.Timestamp(train_end))]
        test_df = df[(df.index >= pd.Timestamp(test_start)) & (df.index <= pd.Timestamp(test_end))]
        if len(train_df) < 100 or len(test_df) < 20:
            results.append({'name': wname, 'skip': True}); continue

        s = make_strategy(sl_mult)
        e = make_engine()
        r = e.run(train_df, s, verbose=False)
        train_sh = r.sharpe_ratio if r.sharpe_ratio else 0
        train_sharpes.append(train_sh)

        s2 = make_strategy(sl_mult)
        e2 = make_engine()
        r2 = e2.run(test_df, s2, verbose=False)
        test_sh = r2.sharpe_ratio if r2.sharpe_ratio else 0
        bh = (test_df['close'].iloc[-1] / test_df['close'].iloc[0] - 1) * 100 if len(test_df) > 1 else 0
        wins = [t for t in r2.trades if t.pnl > 0]
        losses = [t for t in r2.trades if t.pnl <= 0]
        avg_w = np.mean([t.pnl for t in wins]) if wins else 0
        avg_l = np.mean([t.pnl for t in losses]) if losses else 0

        results.append({
            'name': wname, 'is_gap': is_gap,
            'test_return': round(r2.total_pnl_percent, 2),
            'test_sharpe': round(test_sh, 2),
            'test_trades': r2.total_trades,
            'test_wr': round(len(wins) / max(r2.total_trades, 1) * 100, 1),
            'test_pf': round(r2.profit_factor, 2),
            'test_dd': round(r2.max_drawdown, 1),
            'bh_test': round(bh, 2),
            'beats_bh': bool(r2.total_pnl_percent > bh),
            'sl_exits': sum(1 for t in r2.trades if t.exit_reason == 'sl'),
            'tp_exits': sum(1 for t in r2.trades if t.exit_reason == 'tp'),
            'avg_win': round(avg_w, 2),
            'avg_loss': round(avg_l, 2),
            'win_loss_r': round(abs(avg_w / avg_l), 2) if avg_l != 0 else 0,
        })

    builtins.print = _orig
    valid = [r for r in results if not r.get('skip')]

    compound = 1.0
    for r in valid: compound *= (1 + r['test_return'] / 100)
    compound_pct = (compound - 1) * 100

    no_w8c = [r for r in valid if r['name'] != 'W8c']
    compound_no_w8c = 1.0
    for r in no_w8c: compound_no_w8c *= (1 + r['test_return'] / 100)

    contiguous = [r for r in valid if not r['is_gap'] and r['name'] != 'W8c']
    compound_cont = 1.0
    for r in contiguous: compound_cont *= (1 + r['test_return'] / 100)

    pos = sum(1 for r in valid if r['test_return'] > 0)
    beats = sum(1 for r in valid if r['beats_bh'])
    avg_sh = np.mean([r['test_sharpe'] for r in valid])
    avg_ret = np.mean([r['test_return'] for r in valid])
    avg_pf = np.mean([r['test_pf'] for r in valid if r['test_pf'] < 100])
    total_sl = sum(r['sl_exits'] for r in valid)
    total_tp = sum(r['tp_exits'] for r in valid)
    total_trades = sum(r['test_trades'] for r in valid)

    all_results[cfg_label] = {
        'windows': valid,
        'compound': round(compound_pct, 2),
        'compound_no_w8c': round((compound_no_w8c - 1) * 100, 2),
        'compound_cont': round((compound_cont - 1) * 100, 2),
        'pos': pos, 'beats': beats, 'total': len(valid),
        'avg_sharpe': round(avg_sh, 2),
        'avg_return': round(avg_ret, 2),
        'avg_pf': round(avg_pf, 2),
        'total_sl': total_sl, 'total_tp': total_tp, 'total_trades': total_trades,
    }

    print(f'\n{"="*95}')
    print(f'{cfg_label} — Walk-Forward Results')
    print(f'{"="*95}')
    print(f'{"Win":<5} {"Ret%":<9} {"Shrp":<7} {"DD%":<7} {"PF":<6} {"WR%":<7} {"Trd":<5} {"SL":<4} {"TP":<4} {"BH%":<9} {"B>BH":<5}')
    print('-'*95)
    for r in valid:
        flag = 'Y' if r['beats_bh'] else 'N'
        gap_f = '*' if r['is_gap'] else ' '
        print(f'{r["name"]:<5} {r["test_return"]:+<9.2f} {r["test_sharpe"]:<7.2f} {r["test_dd"]:<7.1f} {r["test_pf"]:<6.2f} {r["test_wr"]:<7.1f} {r["test_trades"]:<5} {r["sl_exits"]:<4} {r["tp_exits"]:<4} {r["bh_test"]:+<9.2f} {flag:<5} {gap_f}')

    print(f'\nCompounded (all):       {compound_pct:+.2f}%')
    print(f'Compounded (no W8c):    {(compound_no_w8c-1)*100:+.2f}%')
    print(f'Compounded (contiguous):{(compound_cont-1)*100:+.2f}%')
    print(f'Positive: {pos}/{len(valid)}  Beats B&H: {beats}/{len(valid)}')
    print(f'Avg Sharpe: {avg_sh:.2f}  Avg PF: {avg_pf:.2f}  SL exits: {total_sl}/{total_trades} ({total_sl/max(total_trades,1)*100:.0f}%)')
    builtins.print = lambda *a, **kw: None

builtins.print = _orig

# === Comparison ===
print(f'\n{"="*95}')
print(f'COMPARISON: SL=1.5x vs SL=2.0x')
print(f'{"="*95}')
print(f'{"Metric":<25} {"SL=1.5x":<15} {"SL=2.0x":<15} {"Delta":<10}')
print('-'*95)
for key, label in [
    ('compound', 'Compounded (all)'),
    ('compound_no_w8c', 'Compounded (no W8c)'),
    ('compound_cont', 'Compounded (contiguous)'),
    ('avg_sharpe', 'Avg Test Sharpe'),
    ('avg_pf', 'Avg Profit Factor'),
    ('avg_return', 'Avg Test Return'),
    ('total_sl', 'Total SL exits'),
    ('total_tp', 'Total TP exits'),
]:
    v1 = all_results['SL=1.5x'][key]
    v2 = all_results['SL=2.0x'][key]
    delta = v2 - v1
    sign = '+' if delta > 0 else ''
    print(f'{label:<25} {v1:<15} {v2:<15} {sign}{delta}')
