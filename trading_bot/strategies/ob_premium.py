"""
Order Block Premium Strategies
==============================
Premium (MSS Confirmation), V2 (Enhanced Win Rate), V3 (Time-Based Hybrid)
"""

from typing import Dict, List, Tuple
import pandas as pd

from .ob_core import (
    OrderBlockStrategy, OrderBlock, OBState, Strategy, PositionSide
)


# ============================================================================
# PREMIUM - MSS CONFIRMATION ENTRY
# ============================================================================

class OrderBlockStrategyPremium(OrderBlockStrategy):
    """
    Order Block Strategy - PREMIUM (MSS Confirmation Entry)

    STEP 1: TOP-DOWN ANALYSIS (OB Detection)
    STEP 2: WAIT FOR PRICE TO RETURN
    STEP 3: ENTRY CONFIRMATION (MSS)
    STEP 4: ENTRY EXECUTION
    """

    def __init__(self,
                 name: str = "OrderBlockStrategyPremium",
                 input_range: int = 25,
                 min_risk_reward: float = 2.0,
                 sl_atr_mult: float = 1.0,
                 tp_rr_mult: float = 3.0,
                 require_fvg: bool = True,
                 min_fvg_percent: float = 0.1,
                 require_displacement: bool = True,
                 min_displacement_percent: float = 0.5,
                 min_displacement_candles: int = 2,
                 require_ob_mss: bool = False,
                 mss_lookback: int = 50,
                 mss_confirmation_bars: int = 20,
                 mss_swing_lookback: int = 5,
                 first_retest_only: bool = True,
                 max_age_bars: int = 500,
                 position_size: float = 0.5):

        super().__init__(
            name=name, input_range=input_range,
            min_risk_reward=min_risk_reward, sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult, use_mitigated_blocks=False,
            first_retest_only=first_retest_only, max_age_bars=max_age_bars,
            position_size=position_size
        )

        self.require_fvg = require_fvg
        self.min_fvg_percent = min_fvg_percent
        self.require_displacement = require_displacement
        self.min_displacement_percent = min_displacement_percent
        self.min_displacement_candles = min_displacement_candles
        self.require_ob_mss = require_ob_mss
        self.mss_lookback = mss_lookback
        self.mss_confirmation_bars = mss_confirmation_bars
        self.mss_swing_lookback = mss_swing_lookback
        self.qualified_long_obs: List[OrderBlock] = []
        self.qualified_short_obs: List[OrderBlock] = []
        self.active_poi: Dict[int, Dict] = {}

    def _init_state(self):
        super()._init_state()
        self.qualified_long_obs = []
        self.qualified_short_obs = []
        self.prev_trend = None
        self.active_poi = {}

    # ----- FVG Detection -----

    def _detect_fvg(self, df: pd.DataFrame, current_idx: int, direction: str) -> Tuple[bool, float]:
        if current_idx < 3:
            return False, 0.0
        candle_1 = df.iloc[current_idx - 2]
        candle_3 = df.iloc[current_idx]
        if direction == 'bullish':
            fvg_size = candle_3['low'] - candle_1['high']
            if fvg_size > 0:
                fvg_percent = (fvg_size / candle_1['high']) * 100
                return fvg_percent >= self.min_fvg_percent, fvg_percent
        else:
            fvg_size = candle_1['low'] - candle_3['high']
            if fvg_size > 0:
                fvg_percent = (fvg_size / candle_1['low']) * 100
                return fvg_percent >= self.min_fvg_percent, fvg_percent
        return False, 0.0

    # ----- Displacement Detection -----

    def _detect_displacement(self, df: pd.DataFrame, ob_idx: int, current_idx: int, direction: str) -> Tuple[bool, float]:
        if current_idx <= ob_idx + 1:
            return False, 0.0
        ob_price = df.iloc[ob_idx]['close']
        current_price = df.iloc[current_idx]['close']
        if direction == 'bullish':
            displacement = ((current_price - ob_price) / ob_price) * 100
        else:
            displacement = ((ob_price - current_price) / ob_price) * 100
        if displacement < self.min_displacement_percent:
            return False, displacement
        consecutive_count = 0
        for i in range(ob_idx + 1, min(current_idx + 1, ob_idx + 10)):
            candle = df.iloc[i]
            body = candle['close'] - candle['open']
            if direction == 'bullish' and body > 0:
                consecutive_count += 1
            elif direction == 'bearish' and body < 0:
                consecutive_count += 1
            else:
                break
        if consecutive_count < self.min_displacement_candles:
            return False, displacement
        return True, displacement

    # ----- Trend MSS Detection -----

    def _detect_trend_mss(self, df: pd.DataFrame, current_idx: int, new_direction: str) -> bool:
        if current_idx < self.mss_lookback:
            return False
        lookback_data = df.iloc[current_idx - self.mss_lookback:current_idx]
        closes = lookback_data['close'].values
        mid = len(closes) // 2
        first_half_avg = closes[:mid].mean()
        second_half_avg = closes[mid:].mean()
        if second_half_avg > first_half_avg * 1.01:
            prev_trend = 'bullish'
        elif second_half_avg < first_half_avg * 0.99:
            prev_trend = 'bearish'
        else:
            prev_trend = 'neutral'
        if new_direction == 'bearish' and prev_trend == 'bullish':
            return True
        elif new_direction == 'bullish' and prev_trend == 'bearish':
            return True
        return False

    # ----- Swing High / Low helpers -----

    def _find_swing_high(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[float, int]:
        if start_idx >= end_idx or start_idx < 0:
            return 0.0, -1
        end_idx = min(end_idx, len(df))
        subset = df.iloc[start_idx:end_idx]
        if len(subset) == 0:
            return 0.0, -1
        max_idx = subset['high'].idxmax()
        if isinstance(max_idx, int):
            return subset.loc[max_idx, 'high'], max_idx
        else:
            pos = subset.index.get_loc(max_idx)
            return subset.iloc[pos]['high'], start_idx + pos

    def _find_swing_low(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[float, int]:
        if start_idx >= end_idx or start_idx < 0:
            return float('inf'), -1
        end_idx = min(end_idx, len(df))
        subset = df.iloc[start_idx:end_idx]
        if len(subset) == 0:
            return float('inf'), -1
        min_idx = subset['low'].idxmin()
        if isinstance(min_idx, int):
            return subset.loc[min_idx, 'low'], min_idx
        else:
            pos = subset.index.get_loc(min_idx)
            return subset.iloc[pos]['low'], start_idx + pos

    # ----- Entry MSS Detection -----

    def _detect_entry_mss(self, df: pd.DataFrame, current_idx: int, poi: Dict, direction: str) -> Tuple[bool, float]:
        tap_idx = poi['tap_index']
        bars_since_tap = current_idx - tap_idx
        if bars_since_tap < 2:
            return False, 0.0
        if bars_since_tap > self.mss_confirmation_bars:
            return False, 0.0
        current = df.iloc[current_idx]
        if direction == 'bullish':
            swing_low, swing_low_idx = self._find_swing_low(df, tap_idx, current_idx)
            if swing_low_idx == -1:
                return False, 0.0
            swing_high, swing_high_idx = self._find_swing_high(df, swing_low_idx, current_idx)
            if swing_high_idx == -1 or swing_high_idx <= swing_low_idx:
                return False, 0.0
            if current['close'] > swing_high:
                sl_price = swing_low - (swing_low * 0.001)
                return True, sl_price
        else:
            swing_high, swing_high_idx = self._find_swing_high(df, tap_idx, current_idx)
            if swing_high_idx == -1:
                return False, 0.0
            swing_low, swing_low_idx = self._find_swing_low(df, swing_high_idx, current_idx)
            if swing_low_idx == -1 or swing_low_idx <= swing_high_idx:
                return False, 0.0
            if current['close'] < swing_low:
                sl_price = swing_high + (swing_high * 0.001)
                return True, sl_price
        return False, 0.0

    # ----- BOS Detection overrides -----

    def _detect_bearish_bos(self, df: pd.DataFrame, current, current_idx: int):
        prev_close = df.iloc[current_idx - 1]['close']
        if prev_close >= self.structure_low and current['close'] < self.structure_low:
            has_fvg, fvg_percent = True, 0.0
            if self.require_fvg:
                has_fvg, fvg_percent = self._detect_fvg(df, current_idx, 'bearish')
            has_displacement, displacement_pct = True, 0.0
            if self.require_displacement:
                has_displacement, displacement_pct = self._detect_displacement(
                    df, self.last_up_index, current_idx, 'bearish')
            is_trend_mss = False
            if self.require_ob_mss:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bearish')
                if not is_trend_mss:
                    return
            else:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bearish')
            if has_fvg and has_displacement:
                if current_idx - self.last_up_index < self.max_age_bars:
                    ob = OrderBlock(
                        index=self.last_up_index,
                        timestamp=df.index[self.last_up_index],
                        high=self.last_high,
                        low=self.last_up_low,
                        close=df.iloc[self.last_up_index]['close'],
                        open=df.iloc[self.last_up_index]['open'],
                        ob_type='bearish',
                        created_at=current.name if hasattr(current, 'name') else df.index[current_idx]
                    )
                    self.short_obs.append(ob)
                    self.qualified_short_obs.append(ob)
                    self.last_short_index = self.last_up_index
                    self.bearish_alert = True
                    self._print_premium_ob_info(
                        ob, current['close'], df,
                        has_fvg, fvg_percent,
                        has_displacement, displacement_pct,
                        is_trend_mss)

    def _detect_bullish_bos(self, df: pd.DataFrame, current, current_idx: int):
        if not self.short_obs:
            return
        short_ob = self.short_obs[-1]
        if current['close'] > short_ob.top and current_idx > short_ob.index:
            has_fvg, fvg_percent = True, 0.0
            if self.require_fvg:
                has_fvg, fvg_percent = self._detect_fvg(df, current_idx, 'bullish')
            has_displacement, displacement_pct = True, 0.0
            if self.require_displacement:
                has_displacement, displacement_pct = self._detect_displacement(
                    df, self.last_down_index, current_idx, 'bullish')
            is_trend_mss = False
            if self.require_ob_mss:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bullish')
                if not is_trend_mss:
                    self.short_obs.pop()
                    return
            else:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bullish')
            self.bullish_alert = True
            if has_fvg and has_displacement:
                if current_idx - self.last_down_index < self.max_age_bars and current_idx > self.last_long_index:
                    ob = OrderBlock(
                        index=self.last_down_index,
                        timestamp=df.index[self.last_down_index],
                        high=self.last_down_high,
                        low=self.last_down_low,
                        close=df.iloc[self.last_down_index]['close'],
                        open=df.iloc[self.last_down_index]['open'],
                        ob_type='bullish',
                        created_at=current.name if hasattr(current, 'name') else df.index[current_idx]
                    )
                    self.long_obs.append(ob)
                    self.qualified_long_obs.append(ob)
                    self.last_long_index = current_idx
                    self._print_premium_ob_info(
                        ob, current['close'], df,
                        has_fvg, fvg_percent,
                        has_displacement, displacement_pct,
                        is_trend_mss)
            self.short_obs.pop()

    # ----- Entry logic with MSS confirmation -----

    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        current_idx = len(df) - 1
        atr = current.get('atr', current['close'] * 0.02)

        # STEP 1: POI activation
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"long_{ob.index}"
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bullish',
                        'tap_index': current_idx, 'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   Waiting for MSS confirmation...")

        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"short_{ob.index}"
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bearish',
                        'tap_index': current_idx, 'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
                    print(f"   Waiting for MSS confirmation...")

        # STEP 2: Check POIs for MSS
        expired_pois = []
        for poi_key, poi in self.active_poi.items():
            if not poi['waiting_mss']:
                continue
            direction = poi['direction']
            ob = poi['ob']
            bars_since_tap = current_idx - poi['tap_index']
            if bars_since_tap > self.mss_confirmation_bars:
                expired_pois.append(poi_key)
                print(f"\n⏰ POI EXPIRED - No MSS within {self.mss_confirmation_bars} bars")
                continue
            mss_confirmed, sl_price = self._detect_entry_mss(df, current_idx, poi, direction)
            if mss_confirmed:
                entry_price = current['close']
                if direction == 'bullish':
                    risk_distance = entry_price - sl_price
                    tp_price = entry_price + (risk_distance * self.tp_rr_mult)
                    reward = tp_price - entry_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        print(f"\n✅ {'='*60}")
                        print(f"🟢 LONG ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"📍 Entry:     ${entry_price:,.2f}")
                        print(f"🛑 Stop Loss: ${sl_price:,.2f} (MSS swing low)")
                        print(f"🎯 Target:    ${tp_price:,.2f} ({self.tp_rr_mult}x risk)")
                        print(f"📊 Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"📈 Reward:    ${reward:,.2f} ({reward/entry_price*100:.2f}%)")
                        print(f"⚖️  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        return {
                            'signal': 'LONG', 'sl': sl_price, 'tp': tp_price,
                            'size': self.position_size, 'ob_index': ob.index,
                            'ob_type': 'bullish', 'entry_type': 'mss_confirmation'
                        }
                else:
                    risk_distance = sl_price - entry_price
                    tp_price = entry_price - (risk_distance * self.tp_rr_mult)
                    reward = entry_price - tp_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        print(f"\n✅ {'='*60}")
                        print(f"🔴 SHORT ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"📍 Entry:     ${entry_price:,.2f}")
                        print(f"🛑 Stop Loss: ${sl_price:,.2f} (MSS swing high)")
                        print(f"🎯 Target:    ${tp_price:,.2f} ({self.tp_rr_mult}x risk)")
                        print(f"📊 Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"📈 Reward:    ${reward:,.2f} ({reward/entry_price*100:.2f}%)")
                        print(f"⚖️  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        return {
                            'signal': 'SHORT', 'sl': sl_price, 'tp': tp_price,
                            'size': self.position_size, 'ob_index': ob.index,
                            'ob_type': 'bearish', 'entry_type': 'mss_confirmation'
                        }
        for poi_key in expired_pois:
            del self.active_poi[poi_key]
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

    def _print_premium_ob_info(self, ob: OrderBlock, current_price: float, df: pd.DataFrame,
                               has_fvg: bool, fvg_percent: float,
                               has_displacement: bool, displacement_pct: float,
                               is_trend_mss: bool):
        ob_id = id(ob)
        if ob.ob_type == 'bullish':
            if self._last_printed_ob_long == ob_id:
                return
            self._last_printed_ob_long = ob_id
        else:
            if self._last_printed_ob_short == ob_id:
                return
            self._last_printed_ob_short = ob_id
        emoji = "🟢" if ob.ob_type == "bullish" else "🔴"
        quality = "⭐⭐⭐ PREMIUM POI" if is_trend_mss else "⭐⭐ HIGH QUALITY POI"
        ob_range = ob.top - ob.bottom
        print(f"\n{emoji} {'='*60}")
        print(f"{quality} - {ob.ob_type.upper()} ORDER BLOCK")
        print(f"{'='*60}")
        print(f"📍 OB Zone:        ${ob.bottom:,.2f} - ${ob.top:,.2f}")
        print(f"📏 OB Width:       ${ob_range:,.2f} ({ob_range/ob.bottom*100:.2f}%)")
        print(f"💰 Current Price:  ${current_price:,.2f}")
        print(f"")
        print(f"✅ QUALITY CHECKS:")
        print(f"   📊 FVG/Imbalance:    {'YES' if has_fvg else 'NO'} ({fvg_percent:.2f}%)")
        print(f"   🚀 Displacement:     {'YES' if has_displacement else 'NO'} ({displacement_pct:.2f}%)")
        print(f"   🔄 Trend Reversal:   {'YES' if is_trend_mss else 'NO'}")
        print(f"")
        print(f"⏳ WAITING: Price to tap OB zone for entry")
        print(f"📋 ENTRY:   Will confirm with MSS on tap")
        print(f"🕐 Created: {ob.created_at}")
        print(f"{'='*60}\n")

    def get_stats(self) -> Dict:
        return {
            'total_long_obs': len(self.long_obs),
            'total_short_obs': len(self.short_obs),
            'qualified_long_obs': len(self.qualified_long_obs),
            'qualified_short_obs': len(self.qualified_short_obs),
            'active_pois': len(self.active_poi),
            'require_fvg': self.require_fvg,
            'require_displacement': self.require_displacement,
            'require_ob_mss': self.require_ob_mss,
            'mss_confirmation_bars': self.mss_confirmation_bars
        }


# ============================================================================
# PREMIUM V2 - ENHANCED VERSION WITH HIGHER WIN RATE
# ============================================================================

class OrderBlockStrategyPremiumV2(OrderBlockStrategyPremium):
    """
    Premium V2 - Enhanced Win Rate Version

    Improvements: Trend filter (EMA50/200), faster OB expiration,
    longer MSS window, dynamic R:R, partial TP, ATR SL buffer,
    volatility-based sizing.
    """

    def __init__(self,
                 name: str = "OrderBlockStrategyPremiumV2",
                 input_range: int = 25,
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 1.0,
                 tp_rr_mult: float = 2.5,
                 require_fvg: bool = True,
                 min_fvg_percent: float = 0.1,
                 require_displacement: bool = True,
                 min_displacement_percent: float = 0.5,
                 min_displacement_candles: int = 2,
                 require_ob_mss: bool = False,
                 mss_lookback: int = 50,
                 mss_confirmation_bars: int = 20,
                 mss_swing_lookback: int = 5,
                 first_retest_only: bool = True,
                 max_age_bars: int = 50,
                 use_trend_filter: bool = True,
                 ema_fast: int = 50,
                 ema_slow: int = 200,
                 use_longterm_filter: bool = True,
                 longterm_period: int = 1000,
                 use_partial_tp: bool = True,
                 partial_tp_percent: float = 0.5,
                 tp1_rr_mult: float = 1.5,
                 tp2_rr_mult: float = 3.0,
                 use_dynamic_rr: bool = True,
                 low_vol_threshold: float = 1.0,
                 high_vol_threshold: float = 2.0,
                  sl_atr_buffer: float = 0.5,
                  position_size: float = 0.5):

        super().__init__(
            name=name, input_range=input_range,
            min_risk_reward=min_risk_reward, sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult, require_fvg=require_fvg,
            min_fvg_percent=min_fvg_percent,
            require_displacement=require_displacement,
            min_displacement_percent=min_displacement_percent,
            min_displacement_candles=min_displacement_candles,
            require_ob_mss=require_ob_mss, mss_lookback=mss_lookback,
            mss_confirmation_bars=mss_confirmation_bars,
            mss_swing_lookback=mss_swing_lookback,
            first_retest_only=first_retest_only,
            max_age_bars=max_age_bars, position_size=position_size
        )

        self.use_trend_filter = use_trend_filter
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.use_longterm_filter = use_longterm_filter
        self.longterm_period = longterm_period
        self.use_partial_tp = use_partial_tp
        self.partial_tp_percent = partial_tp_percent
        self.tp1_rr_mult = tp1_rr_mult
        self.tp2_rr_mult = tp2_rr_mult
        self.use_dynamic_rr = use_dynamic_rr
        self.low_vol_threshold = low_vol_threshold
        self.high_vol_threshold = high_vol_threshold
        self.sl_atr_buffer = sl_atr_buffer
        self.current_trend = 'neutral'
        self.market_regime = 'neutral'
        self.partial_positions = {}

    def on_init(self, df: pd.DataFrame):
        super().on_init(df)
        if self.use_trend_filter:
            self.data['ema_fast'] = self.data['close'].ewm(span=self.ema_fast, adjust=False).mean()
            self.data['ema_slow'] = self.data['close'].ewm(span=self.ema_slow, adjust=False).mean()
            self.data['trend'] = 'neutral'
            self.data.loc[self.data['ema_fast'] > self.data['ema_slow'], 'trend'] = 'bullish'
            self.data.loc[self.data['ema_fast'] < self.data['ema_slow'], 'trend'] = 'bearish'
        if self.use_longterm_filter:
            self.data['longterm_ema'] = self.data['close'].ewm(span=self.longterm_period, adjust=False).mean()
        self.data['atr_pct'] = (self.data['atr'] / self.data['close']) * 100
        print(f"\n{'='*60}")
        print(f"🚀 PREMIUM V2 STRATEGY INITIALIZED")
        print(f"{'='*60}")
        print(f"✅ Trend Filter: {'ON (EMA' + str(self.ema_fast) + '/EMA' + str(self.ema_slow) + ')' if self.use_trend_filter else 'OFF'}")
        print(f"✅ Long-term Regime: {'ON (EMA' + str(self.longterm_period) + ')' if self.use_longterm_filter else 'OFF'}")
        print(f"✅ Dynamic R:R: {'ON' if self.use_dynamic_rr else 'OFF'}")
        print(f"✅ Partial TP: {'ON (' + str(int(self.partial_tp_percent*100)) + '% at ' + str(self.tp1_rr_mult) + 'x)' if self.use_partial_tp else 'OFF'}")
        print(f"✅ Max OB Age: {self.max_age_bars} bars")
        print(f"✅ MSS Window: {self.mss_confirmation_bars} bars")
        print(f"✅ SL ATR Buffer: {self.sl_atr_buffer}x ATR")
        print(f"{'='*60}\n")

    def _get_current_trend(self, df: pd.DataFrame) -> str:
        if not self.use_trend_filter:
            return 'neutral'
        current = df.iloc[-1]
        if 'ema_fast' in current and 'ema_slow' in current:
            if current['ema_fast'] > current['ema_slow']:
                return 'bullish'
            elif current['ema_fast'] < current['ema_slow']:
                return 'bearish'
        return 'neutral'

    def _get_market_regime(self, df: pd.DataFrame) -> str:
        if not self.use_longterm_filter:
            return 'neutral'
        current = df.iloc[-1]
        if 'longterm_ema' in current:
            if current['close'] > current['longterm_ema']:
                return 'bullish'
            elif current['close'] < current['longterm_ema']:
                return 'bearish'
        return 'neutral'

    def _get_dynamic_rr(self, df: pd.DataFrame) -> float:
        if not self.use_dynamic_rr:
            return self.tp_rr_mult
        current = df.iloc[-1]
        atr_pct = current.get('atr_pct', 1.5)
        if atr_pct < self.low_vol_threshold:
            return 2.0
        elif atr_pct > self.high_vol_threshold:
            return 1.5
        else:
            return 2.5

    def _get_sl_with_buffer(self, base_sl: float, direction: str, atr: float) -> float:
        buffer = atr * self.sl_atr_buffer
        if direction == 'bullish':
            return base_sl - buffer
        else:
            return base_sl + buffer

    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        current_idx = len(df) - 1
        atr = current.get('atr', current['close'] * 0.02)
        trend = self._get_current_trend(df)
        self.current_trend = trend
        regime = self._get_market_regime(df)
        self.market_regime = regime


        dynamic_rr = self._get_dynamic_rr(df)

        # POI activation — blocked by trend filter AND long-term regime
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"long_{ob.index}"
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    if self.use_trend_filter and trend == 'bearish':
                        continue
                    if self.use_longterm_filter and regime == 'bearish':
                        continue
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bullish',
                        'tap_index': current_idx, 'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   📈 Trend: {trend.upper()} | Regime: {regime.upper()} | Dynamic R:R: {dynamic_rr}:1")

        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"short_{ob.index}"
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    if self.use_trend_filter and trend == 'bullish':
                        continue
                    if self.use_longterm_filter and regime == 'bullish':
                        continue
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bearish',
                        'tap_index': current_idx, 'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
                    print(f"   📉 Trend: {trend.upper()} | Regime: {regime.upper()} | Dynamic R:R: {dynamic_rr}:1")

        # MSS confirmation
        expired_pois = []
        for poi_key, poi in self.active_poi.items():
            if not poi['waiting_mss']:
                continue
            direction = poi['direction']
            ob = poi['ob']
            bars_since_tap = current_idx - poi['tap_index']
            if bars_since_tap > self.mss_confirmation_bars:
                expired_pois.append(poi_key)
                print(f"\n⏰ POI EXPIRED - No MSS within {self.mss_confirmation_bars} bars")
                continue
            if self.use_trend_filter:
                if direction == 'bullish' and trend == 'bearish':
                    expired_pois.append(poi_key)
                    print(f"\n❌ POI INVALIDATED - Trend shifted to bearish")
                    continue
                elif direction == 'bearish' and trend == 'bullish':
                    expired_pois.append(poi_key)
                    print(f"\n❌ POI INVALIDATED - Trend shifted to bullish")
                    continue
            if self.use_longterm_filter:
                if direction == 'bullish' and regime == 'bearish':
                    expired_pois.append(poi_key)
                    print(f"\n❌ POI INVALIDATED - Regime shifted to bearish")
                    continue
                elif direction == 'bearish' and regime == 'bullish':
                    expired_pois.append(poi_key)
                    print(f"\n❌ POI INVALIDATED - Regime shifted to bullish")
                    continue
            mss_confirmed, base_sl = self._detect_entry_mss(df, current_idx, poi, direction)
            if mss_confirmed:
                entry_price = current['close']
                sl_price = self._get_sl_with_buffer(base_sl, direction, atr)
                if direction == 'bullish':
                    risk_distance = entry_price - sl_price
                    tp_price = entry_price + (risk_distance * dynamic_rr)
                    tp1_price = entry_price + (risk_distance * self.tp1_rr_mult) if self.use_partial_tp else None
                    reward = tp_price - entry_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        print(f"\n✅ {'='*60}")
                        print(f"🟢 PREMIUM V2 - LONG ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"📈 TREND:     {trend.upper()}")
                        print(f"📍 Entry:     ${entry_price:,.2f}")
                        print(f"🛑 Stop Loss: ${sl_price:,.2f} (swing + {self.sl_atr_buffer}x ATR buffer)")
                        if self.use_partial_tp:
                            print(f"🎯 TP1:       ${tp1_price:,.2f} ({self.tp1_rr_mult}x) - Close {int(self.partial_tp_percent*100)}%")
                            print(f"🎯 TP2:       ${tp_price:,.2f} ({dynamic_rr}x) - Close remaining")
                        else:
                            print(f"🎯 Target:    ${tp_price:,.2f} ({dynamic_rr}x risk)")
                        print(f"📊 Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"⚖️  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        return {
                            'signal': 'LONG', 'sl': sl_price,
                            'tp': tp1_price if self.use_partial_tp else tp_price,
                            'tp2': tp_price if self.use_partial_tp else None,
                            'size': self.position_size, 'ob_index': ob.index,
                            'ob_type': 'bullish', 'entry_type': 'premium_v2_mss',
                            'trend': trend, 'dynamic_rr': dynamic_rr,
                            'partial_tp': self.use_partial_tp
                        }
                else:
                    risk_distance = sl_price - entry_price
                    tp_price = entry_price - (risk_distance * dynamic_rr)
                    tp1_price = entry_price - (risk_distance * self.tp1_rr_mult) if self.use_partial_tp else None
                    reward = entry_price - tp_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        print(f"\n✅ {'='*60}")
                        print(f"🔴 PREMIUM V2 - SHORT ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"📉 TREND:     {trend.upper()}")
                        print(f"📍 Entry:     ${entry_price:,.2f}")
                        print(f"🛑 Stop Loss: ${sl_price:,.2f} (swing + {self.sl_atr_buffer}x ATR buffer)")
                        if self.use_partial_tp:
                            print(f"🎯 TP1:       ${tp1_price:,.2f} ({self.tp1_rr_mult}x) - Close {int(self.partial_tp_percent*100)}%")
                            print(f"🎯 TP2:       ${tp_price:,.2f} ({dynamic_rr}x) - Close remaining")
                        else:
                            print(f"🎯 Target:    ${tp_price:,.2f} ({dynamic_rr}x risk)")
                        print(f"📊 Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"⚖️  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        return {
                            'signal': 'SHORT', 'sl': sl_price,
                            'tp': tp1_price if self.use_partial_tp else tp_price,
                            'tp2': tp_price if self.use_partial_tp else None,
                            'size': self.position_size, 'ob_index': ob.index,
                            'ob_type': 'bearish', 'entry_type': 'premium_v2_mss',
                            'trend': trend, 'dynamic_rr': dynamic_rr,
                            'partial_tp': self.use_partial_tp
                        }
        for poi_key in expired_pois:
            del self.active_poi[poi_key]
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

    def get_stats(self) -> Dict:
        base_stats = super().get_stats()
        base_stats.update({
            'version': 'V2',
            'use_trend_filter': self.use_trend_filter,
            'ema_fast': self.ema_fast, 'ema_slow': self.ema_slow,
            'use_dynamic_rr': self.use_dynamic_rr,
            'use_partial_tp': self.use_partial_tp,
            'current_trend': self.current_trend,
            'sl_atr_buffer': self.sl_atr_buffer
        })
        return base_stats


# ============================================================================
# PREMIUM V3 - TIME-BASED HYBRID (V1 for 30 days, V2 after)
# ============================================================================

class OrderBlockStrategyPremiumV3(OrderBlockStrategyPremiumV2):
    """
    Premium V3 - Time-Based Hybrid

    FIRST 30 DAYS: Aggressive (V1 logic, no filters, 3:1 R:R)
    AFTER 30 DAYS: Conservative (V2 logic, trend filter, dynamic R:R, partial TP)
    """

    def __init__(self,
                 name: str = "OrderBlockStrategyPremiumV3",
                 input_range: int = 25,
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 1.0,
                 tp_rr_mult: float = 3.0,
                 require_fvg: bool = True,
                 min_fvg_percent: float = 0.1,
                 require_displacement: bool = True,
                 min_displacement_percent: float = 0.5,
                 min_displacement_candles: int = 2,
                 require_ob_mss: bool = False,
                 mss_lookback: int = 50,
                 mss_confirmation_bars: int = 20,
                 mss_swing_lookback: int = 5,
                 first_retest_only: bool = True,
                 aggressive_days: int = 30,
                 timeframe_minutes: int = 15,
                 aggressive_max_age: int = 500,
                 aggressive_rr: float = 3.0,
                 aggressive_sl_buffer: float = 0.3,
                 conservative_max_age: int = 150,
                 conservative_sl_buffer: float = 0.5,
                 ema_fast: int = 50,
                 ema_slow: int = 200,
                 low_vol_threshold: float = 1.0,
                 high_vol_threshold: float = 2.0,
                 partial_tp_percent: float = 0.5,
                  tp1_rr_mult: float = 1.5,
                  tp2_rr_mult: float = 3.0,
                  position_size: float = 0.5):

        super().__init__(
            name=name, input_range=input_range,
            min_risk_reward=min_risk_reward, sl_atr_mult=sl_atr_mult,
            tp_rr_mult=aggressive_rr, require_fvg=require_fvg,
            min_fvg_percent=min_fvg_percent,
            require_displacement=require_displacement,
            min_displacement_percent=min_displacement_percent,
            min_displacement_candles=min_displacement_candles,
            require_ob_mss=require_ob_mss, mss_lookback=mss_lookback,
            mss_confirmation_bars=mss_confirmation_bars,
            mss_swing_lookback=mss_swing_lookback,
            first_retest_only=first_retest_only,
            max_age_bars=aggressive_max_age,
            use_trend_filter=False, ema_fast=ema_fast, ema_slow=ema_slow,
            use_partial_tp=False, partial_tp_percent=partial_tp_percent,
            tp1_rr_mult=tp1_rr_mult, tp2_rr_mult=tp2_rr_mult,
            use_dynamic_rr=False,
            low_vol_threshold=low_vol_threshold,
            high_vol_threshold=high_vol_threshold,
            sl_atr_buffer=aggressive_sl_buffer,
            position_size=position_size
        )

        self.aggressive_days = aggressive_days
        self.timeframe_minutes = timeframe_minutes
        self.bars_per_day = (24 * 60) // timeframe_minutes
        self.aggressive_bars = aggressive_days * self.bars_per_day
        self.aggressive_max_age = aggressive_max_age
        self.aggressive_rr = aggressive_rr
        self.aggressive_sl_buffer = aggressive_sl_buffer
        self.conservative_max_age = conservative_max_age
        self.conservative_sl_buffer = conservative_sl_buffer
        self.start_bar_index = 0
        self.current_mode = 'aggressive'
        self.mode_switched = False
        self.total_trades = 0
        self.mode_stats = {
            'aggressive': {'trades': 0, 'wins': 0},
            'conservative': {'trades': 0, 'wins': 0}
        }

    def _get_current_mode(self, current_idx: int) -> str:
        bars_elapsed = current_idx - self.start_bar_index
        if bars_elapsed < self.aggressive_bars:
            return 'aggressive'
        return 'conservative'

    def _get_days_elapsed(self, current_idx: int) -> float:
        bars_elapsed = current_idx - self.start_bar_index
        return bars_elapsed / self.bars_per_day

    def _update_mode_settings(self, current_idx: int):
        old_mode = self.current_mode
        self.current_mode = self._get_current_mode(current_idx)
        days_elapsed = self._get_days_elapsed(current_idx)
        if old_mode != self.current_mode and not self.mode_switched:
            self.mode_switched = True
            print(f"\n{'🔄'*30}")
            print(f"🚀 MODE TRANSITION at Day {days_elapsed:.1f}")
            print(f"   🔥 AGGRESSIVE → 🛡️ CONSERVATIVE")
            print(f"{'🔄'*30}\n")
        if self.current_mode == 'aggressive':
            self.max_age_bars = self.aggressive_max_age
            self.tp_rr_mult = self.aggressive_rr
            self.sl_atr_buffer = self.aggressive_sl_buffer
            self.use_trend_filter = False
            self.use_partial_tp = False
            self.use_dynamic_rr = False
        else:
            self.max_age_bars = self.conservative_max_age
            self.sl_atr_buffer = self.conservative_sl_buffer
            self.use_trend_filter = True
            self.use_partial_tp = True
            self.use_dynamic_rr = True

    def on_init(self, df: pd.DataFrame):
        super().on_init(df)
        self.start_bar_index = 0
        self.current_mode = 'aggressive'
        self.mode_switched = False
        print(f"\n{'='*60}")
        print(f"🚀 PREMIUM V3 TIME-BASED STRATEGY INITIALIZED")
        print(f"{'='*60}")
        print(f"⏱️ Switch at: Day {self.aggressive_days} ({self.aggressive_bars} bars)")
        print(f"🔥 AGGRESSIVE (Days 1-{self.aggressive_days}): No filter, {self.aggressive_rr}:1 R:R")
        print(f"🛡️ CONSERVATIVE (Days {self.aggressive_days+1}+): Trend filter, dynamic R:R, partial TP")
        print(f"{'='*60}\n")

    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        current_idx = len(df) - 1
        self._update_mode_settings(current_idx)
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        atr = current.get('atr', current['close'] * 0.02)
        atr_pct = current.get('atr_pct', (atr / current['close']) * 100)
        days_elapsed = self._get_days_elapsed(current_idx)
        trend = self._get_current_trend(df)
        self.current_trend = trend
        dynamic_rr = self.aggressive_rr if self.current_mode == 'aggressive' else self._get_dynamic_rr(df)

        # POI activation
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"long_{ob.index}"
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    if self.current_mode == 'conservative' and self.use_trend_filter and trend == 'bearish':
                        continue
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bullish',
                        'tap_index': current_idx, 'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    mode_emoji = "🔥" if self.current_mode == 'aggressive' else "🛡️"
                    print(f"\n📍 POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   {mode_emoji} Mode: {self.current_mode.upper()} | Day {days_elapsed:.1f} | R:R: {dynamic_rr}:1")

        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"short_{ob.index}"
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    if self.current_mode == 'conservative' and self.use_trend_filter and trend == 'bullish':
                        continue
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bearish',
                        'tap_index': current_idx, 'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    mode_emoji = "🔥" if self.current_mode == 'aggressive' else "🛡️"
                    print(f"\n📍 POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
                    print(f"   {mode_emoji} Mode: {self.current_mode.upper()} | Day {days_elapsed:.1f} | R:R: {dynamic_rr}:1")

        # MSS confirmation
        expired_pois = []
        for poi_key, poi in self.active_poi.items():
            if not poi['waiting_mss']:
                continue
            direction = poi['direction']
            ob = poi['ob']
            bars_since_tap = current_idx - poi['tap_index']
            if bars_since_tap > self.mss_confirmation_bars:
                expired_pois.append(poi_key)
                continue
            if self.current_mode == 'conservative' and self.use_trend_filter:
                if direction == 'bullish' and trend == 'bearish':
                    expired_pois.append(poi_key)
                    continue
                elif direction == 'bearish' and trend == 'bullish':
                    expired_pois.append(poi_key)
                    continue
            mss_confirmed, base_sl = self._detect_entry_mss(df, current_idx, poi, direction)
            if mss_confirmed:
                entry_price = current['close']
                sl_price = self._get_sl_with_buffer(base_sl, direction, atr)
                if direction == 'bullish':
                    risk_distance = entry_price - sl_price
                    tp_price = entry_price + (risk_distance * dynamic_rr)
                    tp1_price = None
                    if self.current_mode == 'conservative' and self.use_partial_tp:
                        tp1_price = entry_price + (risk_distance * self.tp1_rr_mult)
                    reward = tp_price - entry_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        self.total_trades += 1
                        self.mode_stats[self.current_mode]['trades'] += 1
                        mode_emoji = "🔥" if self.current_mode == 'aggressive' else "🛡️"
                        mode_name = "AGGRESSIVE (V1)" if self.current_mode == 'aggressive' else "CONSERVATIVE (V2)"
                        print(f"\n✅ {'='*60}")
                        print(f"🟢 PREMIUM V3 - LONG ENTRY [{mode_emoji} {mode_name}]")
                        print(f"{'='*60}")
                        print(f"📊 Trade #{self.total_trades} | Day {days_elapsed:.1f}")
                        print(f"📍 Entry: ${entry_price:,.2f} | SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f}")
                        print(f"⚖️  R:R: 1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        return {
                            'signal': 'LONG', 'sl': sl_price,
                            'tp': tp1_price if tp1_price else tp_price,
                            'tp2': tp_price if tp1_price else None,
                            'size': self.position_size, 'ob_index': ob.index,
                            'ob_type': 'bullish',
                            'entry_type': f'premium_v3_{self.current_mode}',
                            'trend': trend, 'mode': self.current_mode,
                            'day': days_elapsed, 'dynamic_rr': dynamic_rr
                        }
                else:
                    risk_distance = sl_price - entry_price
                    tp_price = entry_price - (risk_distance * dynamic_rr)
                    tp1_price = None
                    if self.current_mode == 'conservative' and self.use_partial_tp:
                        tp1_price = entry_price - (risk_distance * self.tp1_rr_mult)
                    reward = entry_price - tp_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        self.total_trades += 1
                        self.mode_stats[self.current_mode]['trades'] += 1
                        mode_emoji = "🔥" if self.current_mode == 'aggressive' else "🛡️"
                        mode_name = "AGGRESSIVE (V1)" if self.current_mode == 'aggressive' else "CONSERVATIVE (V2)"
                        print(f"\n✅ {'='*60}")
                        print(f"🔴 PREMIUM V3 - SHORT ENTRY [{mode_emoji} {mode_name}]")
                        print(f"{'='*60}")
                        print(f"📊 Trade #{self.total_trades} | Day {days_elapsed:.1f}")
                        print(f"📍 Entry: ${entry_price:,.2f} | SL: ${sl_price:,.2f} | TP: ${tp_price:,.2f}")
                        print(f"⚖️  R:R: 1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        return {
                            'signal': 'SHORT', 'sl': sl_price,
                            'tp': tp1_price if tp1_price else tp_price,
                            'tp2': tp_price if tp1_price else None,
                            'size': self.position_size, 'ob_index': ob.index,
                            'ob_type': 'bearish',
                            'entry_type': f'premium_v3_{self.current_mode}',
                            'trend': trend, 'mode': self.current_mode,
                            'day': days_elapsed, 'dynamic_rr': dynamic_rr
                        }
        for poi_key in expired_pois:
            del self.active_poi[poi_key]
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

    def get_stats(self) -> Dict:
        base_stats = super().get_stats()
        base_stats.update({
            'version': 'V3_TimeBased',
            'total_trades': self.total_trades,
            'current_mode': self.current_mode,
            'mode_stats': self.mode_stats,
            'aggressive_days': self.aggressive_days,
            'mode_switched': self.mode_switched
        })
        return base_stats
