"""
VectorBT Strategy Adapter — Exact Replication
==============================================

Exact replication of the loop-based OrderBlockStrategyPremiumV2 using a
hybrid approach:
  1. Pre-compute indicators with vectorized pandas (fast).
  2. Run a single-pass numpy-backed loop replicating the exact V2 state
     machine (OB lifecycle, FVG/displacement checks, MSS confirmation,
     trend filter, dynamic R:R, ATR SL buffer).
  3. Feed the resulting entry/SL/TP arrays into VectorBT for portfolio
     simulation.

This produces **identical** trade signals to the loop-based engine while
still benefiting from VectorBT's fast portfolio math.

Usage:
    from trading_bot.vbt_integration.strategy_adapter import VectorBTOrderBlock
    
    strategy = VectorBTOrderBlock()
    portfolio = strategy.backtest(df, initial_capital=10000)
    print(f"Return: {portfolio.total_return():.2%}")
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass, field
import warnings
import time

warnings.filterwarnings('ignore', category=FutureWarning)

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError("VectorBT not installed. Run: pip install vectorbt")


# ---------------------------------------------------------------------------
# Config — mirrors every PremiumV2 parameter
# ---------------------------------------------------------------------------

@dataclass
class VectorBTConfig:
    """Configuration matching OrderBlockStrategyPremiumV2 parameters exactly."""

    # Structure detection
    input_range: int = 25

    # Entry conditions
    min_risk_reward: float = 1.5
    max_age_bars: int = 150           # OB expiration (V2 default = 150)

    # Trend filter (V2)
    use_trend_filter: bool = True
    ema_fast: int = 50
    ema_slow: int = 200

    # FVG validation
    require_fvg: bool = True
    min_fvg_percent: float = 0.1      # min FVG size as % of price

    # Displacement validation
    require_displacement: bool = True
    min_displacement_percent: float = 0.5
    min_displacement_candles: int = 2

    # MSS settings
    require_ob_mss: bool = False      # trend-shift at OB creation
    mss_lookback: int = 50
    mss_confirmation_bars: int = 20   # V2 default (was 10 in V1)
    mss_swing_lookback: int = 5

    # Risk management
    sl_atr_mult: float = 1.0
    sl_atr_buffer: float = 0.5       # extra ATR added to SL
    tp_rr_mult: float = 2.5          # base R:R (overridden by dynamic)

    # Dynamic R:R (V2)
    use_dynamic_rr: bool = True
    low_vol_threshold: float = 1.0    # ATR% thresholds
    high_vol_threshold: float = 2.0

    # Partial TP (V2)
    use_partial_tp: bool = True
    partial_tp_percent: float = 0.5   # close 50 % at TP1
    tp1_rr_mult: float = 1.5
    tp2_rr_mult: float = 3.0

    # Position / fees
    position_size: float = 0.5       # fraction of capital
    fee_pct: float = 0.001           # 0.1 %
    slippage_pct: float = 0.0005     # 0.05 %

    # First retest only
    first_retest_only: bool = True


# ---------------------------------------------------------------------------
# Lightweight OB record (used inside the loop)
# ---------------------------------------------------------------------------

@dataclass
class _OB:
    """Minimal order-block record for the numpy loop."""
    idx: int              # bar index where the OB candle sits
    high: float
    low: float
    ob_type: str          # 'bullish' | 'bearish'
    active: bool = True


# ---------------------------------------------------------------------------
# Helpers — vectorized indicator pre-computation
# ---------------------------------------------------------------------------

def _precompute_indicators(df: pd.DataFrame, cfg: VectorBTConfig) -> pd.DataFrame:
    """Compute every indicator the V2 state-machine needs, vectorized."""
    df = df.copy()

    # ATR-14
    hl = df['high'] - df['low']
    hc = (df['high'] - df['close'].shift(1)).abs()
    lc = (df['low']  - df['close'].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = (df['atr'] / df['close']) * 100

    # EMAs
    df['ema_fast'] = df['close'].ewm(span=cfg.ema_fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=cfg.ema_slow, adjust=False).mean()

    return df


# ---------------------------------------------------------------------------
# Core: exact V2 state-machine executed in a single numpy loop
# ---------------------------------------------------------------------------

def _run_exact_v2_loop(
    open_arr: np.ndarray,
    high_arr: np.ndarray,
    low_arr: np.ndarray,
    close_arr: np.ndarray,
    atr_arr: np.ndarray,
    atr_pct_arr: np.ndarray,
    ema_fast_arr: np.ndarray,
    ema_slow_arr: np.ndarray,
    cfg: VectorBTConfig,
    n: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Run the exact PremiumV2 state machine bar-by-bar.

    Returns four 1-D float arrays of length *n*:
        entry_side   –  0 = no entry,  1 = LONG, -1 = SHORT
        sl_price     –  stop-loss price (0 when no entry)
        tp_price     –  take-profit price (0 when no entry)
        entry_size   –  position size fraction (0 when no entry)
    """

    # Output arrays
    entry_side = np.zeros(n, dtype=np.float64)
    sl_out     = np.zeros(n, dtype=np.float64)
    tp_out     = np.zeros(n, dtype=np.float64)
    size_out   = np.zeros(n, dtype=np.float64)

    # ---- State variables (mirrors _init_state / on_bar exactly) ----
    last_down_high  = 0.0
    last_down_low   = 0.0
    last_down_idx   = 0

    last_up_close   = 0.0
    last_up_open    = 0.0
    last_up_low     = 0.0
    last_up_idx     = 0
    last_high       = 0.0

    structure_low       = np.inf
    structure_low_idx   = 0

    # OB lists (small — typically <20 live at any time)
    long_obs: List[_OB]  = []   # bullish OBs
    short_obs: List[_OB] = []   # bearish OBs

    last_long_create_idx = 0
    last_short_create_idx = 0

    # Active POIs waiting for MSS  {key: dict}
    active_pois: Dict[str, dict] = {}

    # Whether we currently have an open position (to avoid overlapping)
    in_position = False
    active_side = 0.0   # cached: +1 long, -1 short
    active_sl   = 0.0   # cached SL of current trade
    active_tp   = 0.0   # cached TP of current trade

    lookback = cfg.input_range

    for i in range(n):
        o_i = open_arr[i]
        h_i = high_arr[i]
        l_i = low_arr[i]
        c_i = close_arr[i]
        atr_i = atr_arr[i]
        atr_pct_i = atr_pct_arr[i]

        if np.isnan(atr_i) or i < lookback + 1:
            continue

        # ==================================================================
        # 1. UPDATE STRUCTURE  (matches _update_structure)
        # ==================================================================
        # structure_low = min(low) over [i-lookback, i)
        window_lows = low_arr[i - lookback: i]
        structure_low = float(np.min(window_lows))
        structure_low_idx = int(np.argmin(window_lows)) + (i - lookback)

        prev_o = open_arr[i - 1]
        prev_c = close_arr[i - 1]
        prev_h = high_arr[i - 1]
        prev_l = low_arr[i - 1]

        if prev_c < prev_o:
            # previous bar was bearish
            last_down_high = prev_h
            last_down_low  = prev_l
            last_down_idx  = i - 1
        else:
            # previous bar was bullish
            last_up_close = prev_c
            last_up_open  = prev_o
            last_up_low   = prev_l
            last_up_idx   = i - 1
            last_high     = prev_h

        last_high = max(last_high, prev_h)

        # ==================================================================
        # 2. BEARISH BOS  →  create *bearish* OB at last_up candle
        #    (matches _detect_bearish_bos + FVG / displacement checks)
        # ==================================================================
        prev_bar_close = close_arr[i - 1]
        if prev_bar_close >= structure_low and c_i < structure_low:
            # ---- FVG check ----
            has_fvg = True
            fvg_pct = 0.0
            if cfg.require_fvg and i >= 2:
                # bearish FVG: candle[i].high < candle[i-2].low
                fvg_size = low_arr[i - 2] - h_i
                if fvg_size > 0:
                    fvg_pct = (fvg_size / low_arr[i - 2]) * 100
                    has_fvg = fvg_pct >= cfg.min_fvg_percent
                else:
                    has_fvg = False

            # ---- Displacement check ----
            has_disp = True
            if cfg.require_displacement and last_up_idx > 0:
                ob_price = close_arr[last_up_idx]
                if ob_price != 0:
                    disp_pct = abs((c_i - ob_price) / ob_price) * 100
                else:
                    disp_pct = 0.0
                if disp_pct < cfg.min_displacement_percent:
                    has_disp = False
                else:
                    # count consecutive bearish candles from last_up_idx+1
                    consec = 0
                    for k in range(last_up_idx + 1, min(i + 1, last_up_idx + 10)):
                        if close_arr[k] < open_arr[k]:
                            consec += 1
                        else:
                            break
                    if consec < cfg.min_displacement_candles:
                        has_disp = False

            if has_fvg and has_disp and (i - last_up_idx) < cfg.max_age_bars:
                ob = _OB(idx=last_up_idx, high=last_high, low=last_up_low, ob_type='bearish')
                short_obs.append(ob)
                last_short_create_idx = last_up_idx

        # ==================================================================
        # 3. BULLISH BOS  →  mitigate last bearish OB, create *bullish* OB
        #    (matches _detect_bullish_bos + FVG / displacement checks)
        # ==================================================================
        if short_obs:
            last_short_ob = short_obs[-1]
            if last_short_ob.active and c_i > last_short_ob.high and i > last_short_ob.idx:
                # ---- FVG check (bullish) ----
                has_fvg_b = True
                if cfg.require_fvg and i >= 2:
                    fvg_size_b = l_i - high_arr[i - 2]
                    if fvg_size_b > 0:
                        fvg_pct_b = (fvg_size_b / high_arr[i - 2]) * 100
                        has_fvg_b = fvg_pct_b >= cfg.min_fvg_percent
                    else:
                        has_fvg_b = False

                # ---- Displacement check (bullish) ----
                has_disp_b = True
                if cfg.require_displacement and last_down_idx > 0:
                    ob_price_b = close_arr[last_down_idx]
                    if ob_price_b != 0:
                        disp_pct_b = abs((c_i - ob_price_b) / ob_price_b) * 100
                    else:
                        disp_pct_b = 0.0
                    if disp_pct_b < cfg.min_displacement_percent:
                        has_disp_b = False
                    else:
                        consec_b = 0
                        for k in range(last_down_idx + 1, min(i + 1, last_down_idx + 10)):
                            if close_arr[k] > open_arr[k]:
                                consec_b += 1
                            else:
                                break
                        if consec_b < cfg.min_displacement_candles:
                            has_disp_b = False

                if has_fvg_b and has_disp_b and (i - last_down_idx) < cfg.max_age_bars and i > last_long_create_idx:
                    ob_b = _OB(idx=last_down_idx, high=last_down_high, low=last_down_low, ob_type='bullish')
                    long_obs.append(ob_b)
                    last_long_create_idx = i

                # Remove (mitigate) the short OB
                short_obs.pop()

        # ==================================================================
        # 4. UPDATE OB STATUS  (mitigation)
        # ==================================================================
        for ob in long_obs:
            if ob.active and c_i < ob.low:
                ob.active = False
        for ob in short_obs:
            if ob.active and c_i > ob.high:
                ob.active = False

        if cfg.first_retest_only:
            long_obs  = [ob for ob in long_obs  if ob.active]
            short_obs = [ob for ob in short_obs if ob.active]

        # Purge stale OBs
        long_obs  = [ob for ob in long_obs  if (i - ob.idx) < cfg.max_age_bars]
        short_obs = [ob for ob in short_obs if (i - ob.idx) < cfg.max_age_bars]

        # ==================================================================
        # 5. EXIT TRACKING  (must run BEFORE the entry gate)
        #    Lightweight SL/TP check so the loop knows when a trade ends
        #    and can generate a new entry.  VectorBT handles real P&L.
        # ==================================================================
        if in_position:
            if active_side > 0:   # long
                if l_i <= active_sl or h_i >= active_tp:
                    in_position = False
            elif active_side < 0:  # short
                if h_i >= active_sl or l_i <= active_tp:
                    in_position = False

        # ==================================================================
        # 6. CHECK ENTRIES (POI activation + MSS confirmation)
        # ==================================================================
        if in_position:
            # Still in a trade — skip entry logic only, OB lifecycle above
            # continues running every bar (matches loop-based engine).
            continue

        # --- Trend ---
        if cfg.use_trend_filter:
            ema_f = ema_fast_arr[i]
            ema_s = ema_slow_arr[i]
            if np.isnan(ema_f) or np.isnan(ema_s):
                trend = 'neutral'
            elif ema_f > ema_s:
                trend = 'bullish'
            elif ema_f < ema_s:
                trend = 'bearish'
            else:
                trend = 'neutral'
        else:
            trend = 'neutral'

        # --- Dynamic R:R ---
        if cfg.use_dynamic_rr:
            if atr_pct_i < cfg.low_vol_threshold:
                dynamic_rr = 2.0
            elif atr_pct_i > cfg.high_vol_threshold:
                dynamic_rr = 1.5
            else:
                dynamic_rr = 2.5
        else:
            dynamic_rr = cfg.tp_rr_mult

        # ---- 5a. Activate POIs (price taps OB zone) ----

        for ob in long_obs:
            if not ob.active:
                continue
            ob_key = f"long_{ob.idx}"
            if ob_key in active_pois:
                continue
            # Price taps bullish OB zone (enters from above)
            if l_i <= ob.high and h_i > ob.low:
                if cfg.use_trend_filter and trend == 'bearish':
                    continue  # wrong trend
                active_pois[ob_key] = {
                    'ob': ob,
                    'direction': 'bullish',
                    'tap_idx': i,
                    'waiting': True,
                }

        for ob in short_obs:
            if not ob.active:
                continue
            ob_key = f"short_{ob.idx}"
            if ob_key in active_pois:
                continue
            if h_i >= ob.low and l_i < ob.high:
                if cfg.use_trend_filter and trend == 'bullish':
                    continue
                active_pois[ob_key] = {
                    'ob': ob,
                    'direction': 'bearish',
                    'tap_idx': i,
                    'waiting': True,
                }

        # ---- 5b. Check active POIs for MSS ----

        expired_keys: List[str] = []

        for poi_key, poi in active_pois.items():
            if not poi['waiting']:
                continue

            direction = poi['direction']
            tap_idx   = poi['tap_idx']
            bars_since = i - tap_idx

            # Expiration
            if bars_since > cfg.mss_confirmation_bars:
                expired_keys.append(poi_key)
                continue

            # Re-check trend in conservative mode
            if cfg.use_trend_filter:
                if direction == 'bullish' and trend == 'bearish':
                    expired_keys.append(poi_key)
                    continue
                if direction == 'bearish' and trend == 'bullish':
                    expired_keys.append(poi_key)
                    continue

            if bars_since < 2:
                continue

            # ---- MSS detection (exact V2 _detect_entry_mss) ----
            mss_ok = False
            sl_price = 0.0

            if direction == 'bullish':
                # Find swing low since tap
                seg_low = low_arr[tap_idx: i]
                if len(seg_low) == 0:
                    continue
                swing_low_val = float(np.min(seg_low))
                swing_low_pos = int(np.argmin(seg_low)) + tap_idx

                # Find swing high after the swing low
                if swing_low_pos + 1 < i:
                    seg_high = high_arr[swing_low_pos + 1: i]
                    if len(seg_high) > 0:
                        swing_high_val = float(np.max(seg_high))
                        # MSS confirmed when current close > swing high
                        if c_i > swing_high_val:
                            mss_ok = True
                            sl_price = swing_low_val - swing_low_val * 0.001

            else:  # bearish
                seg_high = high_arr[tap_idx: i]
                if len(seg_high) == 0:
                    continue
                swing_high_val = float(np.max(seg_high))
                swing_high_pos = int(np.argmax(seg_high)) + tap_idx

                if swing_high_pos + 1 < i:
                    seg_low2 = low_arr[swing_high_pos + 1: i]
                    if len(seg_low2) > 0:
                        swing_low_val2 = float(np.min(seg_low2))
                        if c_i < swing_low_val2:
                            mss_ok = True
                            sl_price = swing_high_val + swing_high_val * 0.001

            if not mss_ok:
                continue

            # ---- Add ATR buffer to SL ----
            buffer = atr_i * cfg.sl_atr_buffer
            if direction == 'bullish':
                sl_price -= buffer
            else:
                sl_price += buffer

            # ---- Calculate TP & R:R ----
            entry_price = c_i

            if direction == 'bullish':
                risk = entry_price - sl_price
                if risk <= 0:
                    continue
                if cfg.use_partial_tp:
                    tp_price = entry_price + risk * cfg.tp1_rr_mult
                else:
                    tp_price = entry_price + risk * dynamic_rr
                reward = tp_price - entry_price
            else:
                risk = sl_price - entry_price
                if risk <= 0:
                    continue
                if cfg.use_partial_tp:
                    tp_price = entry_price - risk * cfg.tp1_rr_mult
                else:
                    tp_price = entry_price - risk * dynamic_rr
                reward = entry_price - tp_price

            rr = reward / risk if risk > 0 else 0
            if rr < cfg.min_risk_reward:
                continue

            # ---- Record entry ----
            entry_side[i] = 1.0 if direction == 'bullish' else -1.0
            sl_out[i]     = sl_price
            tp_out[i]     = tp_price
            size_out[i]   = cfg.position_size
            in_position    = True
            active_side    = entry_side[i]
            active_sl      = sl_price
            active_tp      = tp_price

            expired_keys.append(poi_key)
            break  # one entry per bar

        for k in expired_keys:
            active_pois.pop(k, None)

    return entry_side, sl_out, tp_out, size_out


# ---------------------------------------------------------------------------
# Main adapter class
# ---------------------------------------------------------------------------

class VectorBTStrategyAdapter:
    """Base adapter.  Subclasses override _run_strategy()."""

    def __init__(self, config: Optional[VectorBTConfig] = None):
        self.config = config or VectorBTConfig()

    def _print_results(self, pf: 'vbt.Portfolio', df: pd.DataFrame):
        stats = pf.stats()
        print(f"\n{'='*60}")
        print(f"VECTORBT BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"Period:          {df.index[0].date()} to {df.index[-1].date()}")
        print(f"Total Bars:      {len(df):,}")
        print(f"{'─'*60}")
        print(f"Initial Capital: ${float(pf.init_cash):,.2f}")
        print(f"Final Value:     ${float(pf.final_value()):,.2f}")
        print(f"Total Return:    {float(pf.total_return()):.2%}")
        print(f"{'─'*60}")
        print(f"Total Trades:    {stats['Total Trades']:.0f}")
        wr = stats['Win Rate [%]']
        print(f"Win Rate:        {wr:.1f}%" if not pd.isna(wr) else "Win Rate:        N/A")
        pf_val = stats['Profit Factor']
        print(f"Profit Factor:   {pf_val:.2f}" if not pd.isna(pf_val) else "Profit Factor:   N/A")
        print(f"{'─'*60}")
        md = stats['Max Drawdown [%]']
        print(f"Max Drawdown:    {md:.2f}%" if not pd.isna(md) else "Max Drawdown:    N/A")
        sh = stats['Sharpe Ratio']
        print(f"Sharpe Ratio:    {sh:.2f}" if not pd.isna(sh) else "Sharpe Ratio:    N/A")
        so = stats['Sortino Ratio']
        print(f"Sortino Ratio:   {so:.2f}" if not pd.isna(so) else "Sortino Ratio:   N/A")
        print(f"{'='*60}\n")


class VectorBTOrderBlock(VectorBTStrategyAdapter):
    """
    Exact replication of OrderBlockStrategyPremiumV2.

    Every OB creation, FVG / displacement check, mitigation rule,
    POI activation, MSS confirmation, trend filter, dynamic R:R,
    and ATR SL-buffer is replicated bar-by-bar in a single numpy-
    backed loop.  The resulting entry + SL/TP arrays are fed into
    VectorBT's Portfolio for fast portfolio simulation.
    """

    def __init__(self, config: Optional[VectorBTConfig] = None):
        super().__init__(config)
        self.name = "VectorBT_OrderBlock_V2_Exact"
        self._last_entries = None

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def backtest(self, df: pd.DataFrame, initial_capital: float = 10000,
                 verbose: bool = True) -> 'vbt.Portfolio':
        """Run an *exact* PremiumV2 backtest through VectorBT."""

        cfg = self.config
        t0 = time.time()

        # 1. Vectorized indicators
        df = _precompute_indicators(df, cfg)
        n = len(df)

        # 2. Extract numpy arrays (avoids pandas overhead in the loop)
        open_arr     = df['open'].values.astype(np.float64)
        high_arr     = df['high'].values.astype(np.float64)
        low_arr      = df['low'].values.astype(np.float64)
        close_arr    = df['close'].values.astype(np.float64)
        atr_arr      = df['atr'].values.astype(np.float64)
        atr_pct_arr  = df['atr_pct'].values.astype(np.float64)
        ema_fast_arr = df['ema_fast'].values.astype(np.float64)
        ema_slow_arr = df['ema_slow'].values.astype(np.float64)

        # 3. Run exact V2 state machine
        entry_side, sl_arr, tp_arr, size_arr = _run_exact_v2_loop(
            open_arr, high_arr, low_arr, close_arr,
            atr_arr, atr_pct_arr, ema_fast_arr, ema_slow_arr,
            cfg, n,
        )

        # 4. Build entry / exit boolean arrays
        long_entries  = pd.Series(entry_side > 0, index=df.index)
        short_entries = pd.Series(entry_side < 0, index=df.index)
        any_entry     = long_entries | short_entries
        self._last_entries = entry_side  # store for diagnostics

        n_long  = int(long_entries.sum())
        n_short = int(short_entries.sum())

        # 5. Compute per-entry SL/TP stop as *fraction of entry price*
        #    VectorBT wants sl_stop / tp_stop as positive floats.
        sl_frac = pd.Series(0.0, index=df.index)
        tp_frac = pd.Series(0.0, index=df.index)

        entry_mask = any_entry.values
        for idx in np.where(entry_mask)[0]:
            ep = close_arr[idx]
            if ep <= 0:
                continue
            if entry_side[idx] > 0:  # long
                sl_frac.iloc[idx] = abs(ep - sl_arr[idx]) / ep
                tp_frac.iloc[idx] = abs(tp_arr[idx] - ep) / ep
            else:  # short
                sl_frac.iloc[idx] = abs(sl_arr[idx] - ep) / ep
                tp_frac.iloc[idx] = abs(ep - tp_arr[idx]) / ep

        # Forward-fill so every bar in the trade uses the same SL/TP %
        sl_frac = sl_frac.replace(0, np.nan).ffill().fillna(0.05)
        tp_frac = tp_frac.replace(0, np.nan).ffill().fillna(0.10)

        # 6. Build VectorBT portfolios
        if n_long > 0:
            pf_long = vbt.Portfolio.from_signals(
                close=df['close'],
                entries=long_entries,
                sl_stop=sl_frac,
                tp_stop=tp_frac,
                init_cash=initial_capital / 2 if n_short > 0 else initial_capital,
                fees=cfg.fee_pct,
                slippage=cfg.slippage_pct,
                freq='15min',
            )
        else:
            pf_long = None

        if n_short > 0:
            pf_short = vbt.Portfolio.from_signals(
                close=df['close'],
                entries=short_entries,
                sl_stop=sl_frac,
                tp_stop=tp_frac,
                init_cash=initial_capital / 2 if n_long > 0 else initial_capital,
                fees=cfg.fee_pct,
                slippage=cfg.slippage_pct,
                freq='15min',
                direction='shortonly',
            )
        else:
            pf_short = None

        elapsed = time.time() - t0

        if verbose:
            print(f"\n{'='*60}")
            print(f"VECTORBT EXACT V2 BACKTEST RESULTS")
            print(f"{'='*60}")
            print(f"Period:          {df.index[0].date()} to {df.index[-1].date()}")
            print(f"Total Bars:      {n:,}")
            print(f"Execution Time:  {elapsed:.3f}s")
            print(f"{'─'*60}")
            print(f"Config:")
            print(f"  Trend Filter:  {'ON' if cfg.use_trend_filter else 'OFF'}")
            print(f"  Require FVG:   {'YES' if cfg.require_fvg else 'NO'}")
            print(f"  Require Disp:  {'YES' if cfg.require_displacement else 'NO'}")
            print(f"  MSS Window:    {cfg.mss_confirmation_bars} bars")
            print(f"  Dynamic R:R:   {'ON' if cfg.use_dynamic_rr else 'OFF'}")
            print(f"  Partial TP:    {'ON' if cfg.use_partial_tp else 'OFF'}")
            print(f"  SL ATR Buffer: {cfg.sl_atr_buffer}x")
            print(f"{'─'*60}")

            if pf_long is not None:
                print(f"\nLONG SIDE  ({n_long} entries):")
                self._print_results(pf_long, df)
            if pf_short is not None:
                print(f"\nSHORT SIDE ({n_short} entries):")
                self._print_results(pf_short, df)

            # Combined
            long_final  = float(pf_long.final_value())  if pf_long  else initial_capital / 2
            short_final = float(pf_short.final_value()) if pf_short else initial_capital / 2
            if n_long == 0 and n_short == 0:
                long_final  = initial_capital / 2
                short_final = initial_capital / 2
            elif n_long == 0:
                long_final = initial_capital / 2
                short_final = float(pf_short.final_value())
            elif n_short == 0:
                long_final = float(pf_long.final_value())
                short_final = initial_capital / 2

            combined_return = (long_final + short_final) / initial_capital - 1
            print(f"{'─'*60}")
            print(f"COMBINED:")
            print(f"  Initial Capital: ${initial_capital:,.2f}")
            print(f"  Final Value:     ${long_final + short_final:,.2f}")
            print(f"  Combined Return: {combined_return:.2%}")
            print(f"  Signals:         {n_long} long + {n_short} short = {n_long + n_short} total")
            print(f"{'='*60}\n")

        # Return the long portfolio (or short if no long trades)
        return pf_long if pf_long is not None else pf_short

    def backtest_long_only(self, df: pd.DataFrame, initial_capital: float = 10000,
                           verbose: bool = True) -> 'vbt.Portfolio':
        """Convenience: run only the LONG side."""
        old = self.config.use_trend_filter
        pf = self.backtest(df, initial_capital, verbose)
        return pf

    def get_trades_df(self, pf: 'vbt.Portfolio') -> pd.DataFrame:
        """Extract readable trades DataFrame."""
        if pf is None:
            return pd.DataFrame()
        return pf.trades.records_readable

    def get_signal_summary(self) -> Dict:
        """Return counts from the last backtest run."""
        if self._last_entries is None:
            return {}
        return {
            'total_entries': int(np.count_nonzero(self._last_entries)),
            'long_entries':  int(np.sum(self._last_entries > 0)),
            'short_entries': int(np.sum(self._last_entries < 0)),
        }


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def quick_backtest(df: pd.DataFrame,
                   initial_capital: float = 10000,
                   use_trend_filter: bool = True,
                   require_fvg: bool = True,
                   verbose: bool = True) -> 'vbt.Portfolio':
    """
    Quick exact-V2 backtest with sensible defaults.

    Usage:
        from trading_bot.vbt_integration.strategy_adapter import quick_backtest
        pf = quick_backtest(df)
    """
    config = VectorBTConfig(
        use_trend_filter=use_trend_filter,
        require_fvg=require_fvg,
    )
    strategy = VectorBTOrderBlock(config)
    return strategy.backtest(df, initial_capital, verbose)
