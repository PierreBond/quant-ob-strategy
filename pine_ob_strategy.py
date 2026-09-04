from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from trading_bot.strategies.ob_core import OrderBlockStrategy, OrderBlock, OBState, PositionSide


class HTFOrderBlock:
    """Simple HTF OB for confirmation"""
    def __init__(self, high: float, low: float, ob_type: str):
        self.high = high
        self.low = low
        self.ob_type = ob_type


class HTFTrend:
    """HTF trend direction for confirmation"""
    def __init__(self, direction: int, timestamp: pd.Timestamp = None):
        self.direction = direction  # 1=bullish, -1=bearish, 0=neutral
        self.timestamp = timestamp


class RegimeFilteredOB(OrderBlockStrategy):
    def __init__(self,
                 name: str = "RegimeFilteredOB",
                 input_range: int = 25,
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 use_mitigated_blocks: bool = True,
                 first_retest_only: bool = False,
                 max_age_bars: int = 1000,
                 position_size: float = 0.5,
                 mitigated_size_mult: float = 0.5,
                 use_vol_filter: bool = True,
                 min_atr_pct: float = 0.8,
                 max_atr_pct: float = 2.5,
                 use_adx_filter: bool = True,
                 adx_period: int = 14,
                 adx_threshold: float = 25.0,
                 use_trailing_stop: bool = False,
                 trail_activate_atr: float = 1.5,
                 trail_distance_atr: float = 1.0,
                 use_ofi_filter: bool = False,
                 ofi_window: int = 10,
                 ofi_threshold: float = 0.0,
                 use_htf_ob: bool = False,
                 htf_ob_required: bool = True):

        super().__init__(
            name=name, input_range=input_range,
            min_risk_reward=min_risk_reward, sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult, use_mitigated_blocks=use_mitigated_blocks,
            first_retest_only=first_retest_only, max_age_bars=max_age_bars,
            position_size=position_size
        )
        self.mitigated_size_mult = mitigated_size_mult
        self.ob_retest_counts = {}
        self.use_vol_filter = use_vol_filter
        self.min_atr_pct = min_atr_pct
        self.max_atr_pct = max_atr_pct
        self.use_adx_filter = use_adx_filter
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.use_trailing_stop = use_trailing_stop
        self.trail_activate_atr = trail_activate_atr
        self.trail_distance_atr = trail_distance_atr
        self.use_ofi_filter = use_ofi_filter
        self.ofi_window = ofi_window
        self.ofi_threshold = ofi_threshold
        self.use_htf_ob = use_htf_ob
        self.htf_ob_required = htf_ob_required
        self.htf_obs: List[HTFOrderBlock] = []
        self.htf_trends: List[HTFTrend] = []

    def _init_state(self):
        super()._init_state()
        self.ob_retest_counts = {}

    def set_htf_obs(self, long_obs: List[HTFOrderBlock], short_obs: List[HTFOrderBlock]):
        """Set higher timeframe Order Blocks for confirmation"""
        self.htf_obs = long_obs + short_obs

    def set_htf_trends(self, trends: List[HTFTrend]):
        """Set higher timeframe trend directions for confirmation"""
        self.htf_trends = trends

    def _check_htf_ob(self, price: float, direction: str, timestamp: pd.Timestamp = None) -> bool:
        """Check if price is inside a higher timeframe OB zone or if HTF trend aligns"""
        if not self.use_htf_ob:
            return True

        # Check OB zones first
        for ob in self.htf_obs:
            if ob.ob_type == direction.lower() and ob.low <= price <= ob.high:
                return True

        # If no OB match and required, check trend alignment
        if self.htf_ob_required and self.htf_trends:
            for trend in reversed(self.htf_trends):
                if timestamp and trend.timestamp and trend.timestamp <= timestamp:
                    if direction == 'LONG' and trend.direction == 1:
                        return True
                    elif direction == 'SHORT' and trend.direction == -1:
                        return True
                    return False
            # No trend data available for this timestamp - allow trade
            return True

        return True

    def on_init(self, df: pd.DataFrame):
        df = df.copy()
        df['atr'] = self._calculate_atr(df, 14)
        df['atr_pct'] = (df['atr'] / df['close']) * 100

        if self.use_ofi_filter:
            hl_range = df['high'] - df['low']
            hl_range = hl_range.replace(0, np.nan)
            df['buy_vol'] = df['volume'] * (df['close'] - df['low']) / hl_range
            df['sell_vol'] = df['volume'] * (df['high'] - df['close']) / hl_range
            df['ofi'] = (df['buy_vol'] - df['sell_vol']).rolling(self.ofi_window).sum()
            df['ofi_momentum'] = df['ofi'].diff()
            df['ofi_accel'] = df['ofi_momentum'].diff()
            df['ofi_divergence'] = df['ofi'].rolling(20).mean() - df['close'].pct_change(20).rolling(20).mean()

        if self.use_adx_filter:
            high = df['high']; low = df['low']; close = df['close']
            plus_dm = high.diff()
            minus_dm = -low.diff()
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr14 = tr.ewm(span=self.adx_period, adjust=False).mean()
            plus_di = 100 * (plus_dm.ewm(span=self.adx_period, adjust=False).mean() / atr14)
            minus_di = 100 * (minus_dm.ewm(span=self.adx_period, adjust=False).mean() / atr14)
            dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
            df['adx'] = dx.ewm(span=self.adx_period, adjust=False).mean()
            df['plus_di'] = plus_di
            df['minus_di'] = minus_di
            df['trend_dir'] = np.where(plus_di > minus_di, 1, -1)

        self.data = df
        self.initialized = True
        self._init_state()

    def _update_ob_status(self, df, current, current_idx):
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value and current['close'] < ob.bottom:
                ob.state = OBState.MITIGATED.value
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value and current['close'] > ob.top:
                ob.state = OBState.MITIGATED.value
        self.long_obs = [ob for ob in self.long_obs
                         if self.ob_retest_counts.get(ob.index, 0) < 3]
        self.short_obs = [ob for ob in self.short_obs
                          if self.ob_retest_counts.get(ob.index, 0) < 3]

    def _check_filters(self, current):
        if self.use_vol_filter:
            atr_pct = current.get('atr_pct', 1.5)
            if pd.isna(atr_pct) or atr_pct < self.min_atr_pct or atr_pct > self.max_atr_pct:
                return False, 0
        if self.use_ofi_filter:
            ofi = current.get('ofi', 0)
            ofi_mom = current.get('ofi_momentum', 0)
            ofi_accel = current.get('ofi_accel', 0)
            if pd.isna(ofi):
                return True, 0
            ofi_signal = 0
            if ofi > self.ofi_threshold:
                ofi_signal = 1
            elif ofi < -self.ofi_threshold:
                ofi_signal = -1
            if ofi_mom > 0 and ofi_signal == 1:
                ofi_signal = 2
            elif ofi_mom < 0 and ofi_signal == -1:
                ofi_signal = -2
            return True, ofi_signal
        if self.use_adx_filter:
            adx = current.get('adx', 0)
            if pd.isna(adx) or adx < self.adx_threshold:
                return False, 0
            trend = current.get('trend_dir', 0)
            return True, int(trend)
        return True, 0

    def _check_entries(self, df, current, position):
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        ok, trend = self._check_filters(current)
        if not ok:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        current_idx = len(df) - 1
        atr = current.get('atr', current['close'] * 0.02)
        price = current['close']

        for ob in self.long_obs:
            if not self.use_mitigated_blocks and ob.state == OBState.MITIGATED.value:
                continue
            if current_idx - ob.index > self.max_age_bars:
                continue
            if trend == -1:
                continue
            if not self._check_htf_ob(price, 'LONG'):
                continue
            if current['low'] <= ob.top and current['high'] > ob.top:
                if self.ob_retest_counts.get(ob.index, 0) >= 3:
                    continue
                self.long_retest = True
                sl = ob.bottom - atr * self.sl_atr_mult
                rd = current['close'] - sl
                if rd <= 0: continue
                tp = current['close'] + rd * self.tp_rr_mult
                if (tp - current['close']) / rd < self.min_risk_reward: continue
                is_mit = ob.state == OBState.MITIGATED.value
                sz = self.position_size * (self.mitigated_size_mult if is_mit else 1.0)
                self.ob_retest_counts[ob.index] = self.ob_retest_counts.get(ob.index, 0) + 1
                return {'signal': 'LONG', 'sl': sl, 'tp': tp, 'size': sz,
                        'ob_index': ob.index, 'ob_type': 'bullish',
                        'ob_state': 'mitigated' if is_mit else 'active',
                        'retest_count': self.ob_retest_counts[ob.index],
                        'atr': atr}

        for ob in self.short_obs:
            if not self.use_mitigated_blocks and ob.state == OBState.MITIGATED.value:
                continue
            if current_idx - ob.index > self.max_age_bars:
                continue
            if trend == 1:
                continue
            if not self._check_htf_ob(price, 'SHORT'):
                continue
            if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                if self.ob_retest_counts.get(ob.index, 0) >= 3:
                    continue
                self.short_retest = True
                sl = ob.top + atr * self.sl_atr_mult
                rd = sl - current['close']
                if rd <= 0: continue
                tp = current['close'] - rd * self.tp_rr_mult
                if (current['close'] - tp) / rd < self.min_risk_reward: continue
                is_mit = ob.state == OBState.MITIGATED.value
                sz = self.position_size * (self.mitigated_size_mult if is_mit else 1.0)
                self.ob_retest_counts[ob.index] = self.ob_retest_counts.get(ob.index, 0) + 1
                return {'signal': 'SHORT', 'sl': sl, 'tp': tp, 'size': sz,
                        'ob_index': ob.index, 'ob_type': 'bearish',
                        'ob_state': 'mitigated' if is_mit else 'active',
                        'retest_count': self.ob_retest_counts[ob.index],
                        'atr': atr}

        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
