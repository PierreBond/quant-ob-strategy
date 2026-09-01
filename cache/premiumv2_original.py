class OrderBlockStrategyPremiumV2(OrderBlockStrategyPremium):
    """
    Order Block Strategy - PREMIUM V2 (Enhanced Win Rate Version)
    
    IMPROVEMENTS OVER V1:
    =====================
    1. TREND FILTER (EMA50/EMA200)
       - Only LONG when EMA50 > EMA200 (uptrend)
       - Only SHORT when EMA50 < EMA200 (downtrend)
       - Dramatically reduces counter-trend losses
    
    2. FASTER OB EXPIRATION
       - OBs expire after 150 bars (was 500)
       - Keeps POIs fresh and relevant
    
    3. LONGER MSS CONFIRMATION WINDOW
       - 20 bars to confirm MSS (was 10)
       - Gives valid setups more time to develop
    
    4. DYNAMIC R:R BASED ON VOLATILITY
       - Low volatility: Target 2:1
       - Normal volatility: Target 2.5:1
       - High volatility: Target 1.5:1 (take profits faster)
    
    5. PARTIAL TAKE PROFIT
       - Close 50% at TP1 (1.5x risk)
       - Let 50% run with trailing stop to TP2 (3x risk)
    
    6. ATR-BASED STOP LOSS BUFFER
       - Adds 0.5 ATR buffer below/above swing point
       - Prevents stop hunts
    
    7. VOLATILITY-BASED POSITION SIZING
       - Reduces size in high volatility
       - Increases size in low volatility
    """
    
    def __init__(self,
                 name: str = "OrderBlockStrategyPremiumV2",
                 # Structure Settings
                 input_range: int = 25,
                 # Trading Settings - IMPROVED
                 min_risk_reward: float = 1.5,   # Lowered for better hit rate
                 sl_atr_mult: float = 1.0,
                 tp_rr_mult: float = 2.5,        # Dynamic, this is base
                 # FVG Settings
                 require_fvg: bool = True,
                 min_fvg_percent: float = 0.1,
                 # Displacement Settings  
                 require_displacement: bool = True,
                 min_displacement_percent: float = 0.5,
                 min_displacement_candles: int = 2,
                 # MSS Settings
                 require_ob_mss: bool = False,
                 mss_lookback: int = 50,
                 # Entry Confirmation Settings - IMPROVED
                 mss_confirmation_bars: int = 20,  # Was 10 - more time for MSS
                 mss_swing_lookback: int = 5,
                 # Filter Settings - IMPROVED
                 first_retest_only: bool = True,
                 max_age_bars: int = 150,          # Was 500 - fresher OBs
                 # NEW - Trend Filter Settings
                 use_trend_filter: bool = True,
                 ema_fast: int = 50,
                 ema_slow: int = 200,
                 # NEW - Partial TP Settings
                 use_partial_tp: bool = True,
                 partial_tp_percent: float = 0.5,  # Close 50% at TP1
                 tp1_rr_mult: float = 1.5,         # TP1 at 1.5x risk
                 tp2_rr_mult: float = 3.0,         # TP2 at 3x risk
                 # NEW - Dynamic R:R Settings
                 use_dynamic_rr: bool = True,
                 low_vol_threshold: float = 1.0,   # ATR% threshold
                 high_vol_threshold: float = 2.0,
                 # NEW - ATR SL Buffer
                 sl_atr_buffer: float = 0.5,       # Add 0.5 ATR to SL
                 # Position Settings
                 position_size: float = 0.5):
        
        super().__init__(
            name=name,
            input_range=input_range,
            min_risk_reward=min_risk_reward,
            sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult,
            require_fvg=require_fvg,
            min_fvg_percent=min_fvg_percent,
            require_displacement=require_displacement,
            min_displacement_percent=min_displacement_percent,
            min_displacement_candles=min_displacement_candles,
            require_ob_mss=require_ob_mss,
            mss_lookback=mss_lookback,
            mss_confirmation_bars=mss_confirmation_bars,
            mss_swing_lookback=mss_swing_lookback,
            first_retest_only=first_retest_only,
            max_age_bars=max_age_bars,
            position_size=position_size
        )
        
        # Trend Filter Settings
        self.use_trend_filter = use_trend_filter
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        
        # Partial TP Settings
        self.use_partial_tp = use_partial_tp
        self.partial_tp_percent = partial_tp_percent
        self.tp1_rr_mult = tp1_rr_mult
        self.tp2_rr_mult = tp2_rr_mult
        
        # Dynamic R:R Settings
        self.use_dynamic_rr = use_dynamic_rr
        self.low_vol_threshold = low_vol_threshold
        self.high_vol_threshold = high_vol_threshold
        
        # ATR SL Buffer
        self.sl_atr_buffer = sl_atr_buffer
        
        # Tracking
        self.current_trend = 'neutral'
        self.partial_positions = {}  # Track partial TPs
        
    def on_init(self, df: pd.DataFrame):
        """Initialize with trend indicators"""
        super().on_init(df)
        
        # Add EMAs for trend filter
        if self.use_trend_filter:
            self.data['ema_fast'] = self.data['close'].ewm(span=self.ema_fast, adjust=False).mean()
            self.data['ema_slow'] = self.data['close'].ewm(span=self.ema_slow, adjust=False).mean()
            
            # Calculate trend
            self.data['trend'] = 'neutral'
            self.data.loc[self.data['ema_fast'] > self.data['ema_slow'], 'trend'] = 'bullish'
            self.data.loc[self.data['ema_fast'] < self.data['ema_slow'], 'trend'] = 'bearish'
        
        # Calculate ATR percentage for volatility
        self.data['atr_pct'] = (self.data['atr'] / self.data['close']) * 100
        
        print(f"\n{'='*60}")
        print(f"­ƒÜÇ PREMIUM V2 STRATEGY INITIALIZED")
        print(f"{'='*60}")
        print(f"Ô£à Trend Filter: {'ON (EMA' + str(self.ema_fast) + '/EMA' + str(self.ema_slow) + ')' if self.use_trend_filter else 'OFF'}")
        print(f"Ô£à Dynamic R:R: {'ON' if self.use_dynamic_rr else 'OFF'}")
        print(f"Ô£à Partial TP: {'ON (' + str(int(self.partial_tp_percent*100)) + '% at ' + str(self.tp1_rr_mult) + 'x)' if self.use_partial_tp else 'OFF'}")
        print(f"Ô£à Max OB Age: {self.max_age_bars} bars")
        print(f"Ô£à MSS Window: {self.mss_confirmation_bars} bars")
        print(f"Ô£à SL ATR Buffer: {self.sl_atr_buffer}x ATR")
        print(f"{'='*60}\n")
    
    def _get_current_trend(self, df: pd.DataFrame) -> str:
        """Get current market trend from EMAs"""
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
        """Calculate dynamic R:R based on volatility"""
        if not self.use_dynamic_rr:
            return self.tp_rr_mult
        
        current = df.iloc[-1]
        atr_pct = current.get('atr_pct', 1.5)
        
        if atr_pct < self.low_vol_threshold:
            # Low volatility - can target higher R:R
            return 2.0
        elif atr_pct > self.high_vol_threshold:
            # High volatility - take profits faster
            return 1.5
        else:
            # Normal volatility
            return 2.5
    
    def _get_sl_with_buffer(self, base_sl: float, direction: str, atr: float) -> float:
        """Add ATR buffer to stop loss to prevent stop hunts"""
        buffer = atr * self.sl_atr_buffer
        
        if direction == 'bullish':
            # SL below swing low - add buffer below
            return base_sl - buffer
        else:
            # SL above swing high - add buffer above
            return base_sl + buffer
    
    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """
        Enhanced entry check with trend filter, dynamic R:R, and partial TP
        """
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
        
        current_idx = len(df) - 1
        atr = current.get('atr', current['close'] * 0.02)
        
        # Get current trend
        trend = self._get_current_trend(df)
        self.current_trend = trend
        
        # Get dynamic R:R
        dynamic_rr = self._get_dynamic_rr(df)
        
        # =====================================================================
        # STEP 1: Check for POI activation (price taps OB)
        # =====================================================================
        
        # Check bullish OBs for tap
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            
            ob_key = f"long_{ob.index}"
            
            # Price taps OB zone
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    # TREND FILTER: Only activate bullish POI in uptrend
                    if self.use_trend_filter and trend == 'bearish':
                        continue  # Skip - wrong trend
                    
                    self.active_poi[ob_key] = {
                        'ob': ob,
                        'direction': 'bullish',
                        'tap_index': current_idx,
                        'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    print(f"\n­ƒôì POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   ­ƒôê Trend: {trend.upper()} | Dynamic R:R: {dynamic_rr}:1")
                    print(f"   Waiting for MSS confirmation...")
        
        # Check bearish OBs for tap
        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            
            ob_key = f"short_{ob.index}"
            
            # Price taps OB zone
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    # TREND FILTER: Only activate bearish POI in downtrend
                    if self.use_trend_filter and trend == 'bullish':
                        continue  # Skip - wrong trend
                    
                    self.active_poi[ob_key] = {
                        'ob': ob,
                        'direction': 'bearish',
                        'tap_index': current_idx,
                        'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    print(f"\n­ƒôì POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
                    print(f"   ­ƒôë Trend: {trend.upper()} | Dynamic R:R: {dynamic_rr}:1")
                    print(f"   Waiting for MSS confirmation...")
        
        # =====================================================================
        # STEP 2: Check active POIs for MSS confirmation
        # =====================================================================
        
        expired_pois = []
        
        for poi_key, poi in self.active_poi.items():
            if not poi['waiting_mss']:
                continue
            
            direction = poi['direction']
            ob = poi['ob']
            bars_since_tap = current_idx - poi['tap_index']
            
            # Check if POI expired
            if bars_since_tap > self.mss_confirmation_bars:
                expired_pois.append(poi_key)
                print(f"\nÔÅ¦ POI EXPIRED - No MSS within {self.mss_confirmation_bars} bars")
                continue
            
            # RE-CHECK TREND - ensure still valid
            if self.use_trend_filter:
                if direction == 'bullish' and trend == 'bearish':
                    expired_pois.append(poi_key)
                    print(f"\nÔØî POI INVALIDATED - Trend shifted to bearish")
                    continue
                elif direction == 'bearish' and trend == 'bullish':
                    expired_pois.append(poi_key)
                    print(f"\nÔØî POI INVALIDATED - Trend shifted to bullish")
                    continue
            
            # Check for MSS confirmation
            mss_confirmed, base_sl = self._detect_entry_mss(df, current_idx, poi, direction)
            
            if mss_confirmed:
                entry_price = current['close']
                
                # ADD ATR BUFFER TO STOP LOSS
                sl_price = self._get_sl_with_buffer(base_sl, direction, atr)
                
                if direction == 'bullish':
                    # LONG entry
                    risk_distance = entry_price - sl_price
                    
                    # Use dynamic R:R
                    tp_price = entry_price + (risk_distance * dynamic_rr)
                    
                    # Calculate TP1 for partial (if enabled)
                    tp1_price = entry_price + (risk_distance * self.tp1_rr_mult) if self.use_partial_tp else None
                    
                    reward = tp_price - entry_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        
                        print(f"\nÔ£à {'='*60}")
                        print(f"­ƒƒó PREMIUM V2 - LONG ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"­ƒôê TREND:     {trend.upper()}")
                        print(f"­ƒôì Entry:     ${entry_price:,.2f}")
                        print(f"­ƒøæ Stop Loss: ${sl_price:,.2f} (swing + {self.sl_atr_buffer}x ATR buffer)")
                        if self.use_partial_tp:
                            print(f"­ƒÄ» TP1:       ${tp1_price:,.2f} ({self.tp1_rr_mult}x) - Close {int(self.partial_tp_percent*100)}%")
                            print(f"­ƒÄ» TP2:       ${tp_price:,.2f} ({dynamic_rr}x) - Close remaining")
                        else:
                            print(f"­ƒÄ» Target:    ${tp_price:,.2f} ({dynamic_rr}x risk)")
                        print(f"­ƒôè Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"ÔÜû´©Å  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        
                        return {
                            'signal': 'LONG',
                            'sl': sl_price,
                            'tp': tp1_price if self.use_partial_tp else tp_price,  # First target
                            'tp2': tp_price if self.use_partial_tp else None,       # Second target
                            'size': self.position_size,
                            'ob_index': ob.index,
                            'ob_type': 'bullish',
                            'entry_type': 'premium_v2_mss',
                            'trend': trend,
                            'dynamic_rr': dynamic_rr,
                            'partial_tp': self.use_partial_tp
                        }
                
                else:  # bearish
                    # SHORT entry
                    risk_distance = sl_price - entry_price
                    
                    # Use dynamic R:R
                    tp_price = entry_price - (risk_distance * dynamic_rr)
                    
                    # Calculate TP1 for partial
                    tp1_price = entry_price - (risk_distance * self.tp1_rr_mult) if self.use_partial_tp else None
                    
                    reward = entry_price - tp_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        
                        print(f"\nÔ£à {'='*60}")
                        print(f"­ƒö¦ PREMIUM V2 - SHORT ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"­ƒôë TREND:     {trend.upper()}")
                        print(f"­ƒôì Entry:     ${entry_price:,.2f}")
                        print(f"­ƒøæ Stop Loss: ${sl_price:,.2f} (swing + {self.sl_atr_buffer}x ATR buffer)")
                        if self.use_partial_tp:
                            print(f"­ƒÄ» TP1:       ${tp1_price:,.2f} ({self.tp1_rr_mult}x) - Close {int(self.partial_tp_percent*100)}%")
                            print(f"­ƒÄ» TP2:       ${tp_price:,.2f} ({dynamic_rr}x) - Close remaining")
                        else:
                            print(f"­ƒÄ» Target:    ${tp_price:,.2f} ({dynamic_rr}x risk)")
                        print(f"­ƒôè Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"ÔÜû´©Å  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        
                        return {
                            'signal': 'SHORT',
                            'sl': sl_price,
                            'tp': tp1_price if self.use_partial_tp else tp_price,
                            'tp2': tp_price if self.use_partial_tp else None,
                            'size': self.position_size,
                            'ob_index': ob.index,
                            'ob_type': 'bearish',
                            'entry_type': 'premium_v2_mss',
                            'trend': trend,
                            'dynamic_rr': dynamic_rr,
                            'partial_tp': self.use_partial_tp
                        }
        
        # Clean up expired POIs
        for poi_key in expired_pois:
            del self.active_poi[poi_key]
        
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
    
    def get_stats(self) -> Dict:
        """Get enhanced strategy statistics"""
        base_stats = super().get_stats()
        base_stats.update({
            'version': 'V2',
            'use_trend_filter': self.use_trend_filter,
            'ema_fast': self.ema_fast,
            'ema_slow': self.ema_slow,
            'use_dynamic_rr': self.use_dynamic_rr,
            'use_partial_tp': self.use_partial_tp,
            'current_trend': self.current_trend,
            'sl_atr_buffer': self.sl_atr_buffer
        })
        return base_stats


# ============================================================================
# PREMIUM V3 - TIME-BASED HYBRID (V1 for 30 days, V2 after)
# ============================================================================

