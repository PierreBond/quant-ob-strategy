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
                 max_age_bars: int = 150,
                 use_trend_filter: bool = True,
                 ema_fast: int = 50,
                 ema_slow: int = 200,
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
        self.use_partial_tp = use_partial_tp
        self.partial_tp_percent = partial_tp_percent
        self.tp1_rr_mult = tp1_rr_mult
        self.tp2_rr_mult = tp2_rr_mult
        self.use_dynamic_rr = use_dynamic_rr
        self.low_vol_threshold = low_vol_threshold
        self.high_vol_threshold = high_vol_threshold
        self.sl_atr_buffer = sl_atr_buffer
        self.current_trend = 'neutral'
        self.partial_positions = {}

    def on_init(self, df: pd.DataFrame):
        super().on_init(df)
        if self.use_trend_filter:
            self.data['ema_fast'] = self.data['close'].ewm(span=self.ema_fast, adjust=False).mean()
            self.data['ema_slow'] = self.data['close'].ewm(span=self.ema_slow, adjust=False).mean()
            self.data['trend'] = 'neutral'
            self.data.loc[self.data['ema_fast'] > self.data['ema_slow'], 'trend'] = 'bullish'
            self.data.loc[self.data['ema_fast'] < self.data['ema_slow'], 'trend'] = 'bearish'
        self.data['atr_pct'] = (self.data['atr'] / self.data['close']) * 100
        print(f"\n{'='*60}")
        print(f"🚀 PREMIUM V2 STRATEGY INITIALIZED")
        print(f"{'='*60}")
        print(f"✅ Trend Filter: {'ON (EMA' + str(self.ema_fast) + '/EMA' + str(self.ema_slow) + ')' if self.use_trend_filter else 'OFF'}")
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
        dynamic_rr = self._get_dynamic_rr(df)

        # POI activation
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"long_{ob.index}"
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    if self.use_trend_filter and trend == 'bearish':
                        continue
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bullish',
                        'tap_index': current_idx, 'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   📈 Trend: {trend.upper()} | Dynamic R:R: {dynamic_rr}:1")

        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            ob_key = f"short_{ob.index}"
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    if self.use_trend_filter and trend == 'bullish':
                        continue
                    self.active_poi[ob_key] = {
                        'ob': ob, 'direction': 'bearish',
                        'tap_index': current_idx, 'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    print(f"\n📍 POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
                    print(f"   📉 Trend: {trend.upper()} | Dynamic R:R: {dynamic_rr}:1")

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

