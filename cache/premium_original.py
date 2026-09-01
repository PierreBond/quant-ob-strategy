class OrderBlockStrategyPremium(OrderBlockStrategy):
    """
    Order Block Strategy - PREMIUM (MSS Confirmation Entry)
    
    This strategy follows institutional trading methodology:
    
    STEP 1: TOP-DOWN ANALYSIS (OB Detection)
    - Identify valid OBs on higher timeframe with BOS + FVG + Displacement
    - Mark these as Point of Interest (POI)
    
    STEP 2: WAIT FOR PRICE TO RETURN
    - Wait for price to retrace back to the OB zone
    - Don't enter immediately - wait for confirmation
    
    STEP 3: ENTRY CONFIRMATION (MSS)
    - Once price taps OB, look for Market Structure Shift
    - Bullish MSS: Break of lower high (in uptrend setup)
    - Bearish MSS: Break of higher low (in downtrend setup)
    
    STEP 4: ENTRY EXECUTION
    - Entry: After MSS confirmation
    - Stop Loss: Below/above the MSS swing point (tighter SL)
    - Take Profit: Target at least 3x risk
    
    Benefits:
    - Much higher win rate due to confirmation
    - Tighter stop losses = better risk/reward
    - Fewer false entries
    - Aligns with institutional Smart Money Concepts
    """
    
    def __init__(self,
                 name: str = "OrderBlockStrategyPremium",
                 # Structure Settings
                 input_range: int = 25,
                 # Trading Settings
                 min_risk_reward: float = 2.0,  # Higher RR for premium setups
                 sl_atr_mult: float = 1.0,      # Tighter SL (based on MSS swing)
                 tp_rr_mult: float = 3.0,       # At least 3x risk
                 # FVG Settings
                 require_fvg: bool = True,       # Must have FVG for valid OB
                 min_fvg_percent: float = 0.1,   # Min FVG size (0.1% of price)
                 # Displacement Settings
                 require_displacement: bool = True,
                 min_displacement_percent: float = 0.5,  # Min 0.5% move
                 min_displacement_candles: int = 2,      # Min consecutive candles
                 # MSS Settings
                 require_ob_mss: bool = False,    # OB must cause trend shift
                 mss_lookback: int = 50,          # Bars to check for OB trend
                 # Entry Confirmation Settings
                 mss_confirmation_bars: int = 10,  # Bars to wait for MSS after OB tap
                 mss_swing_lookback: int = 5,      # Bars to find swing for MSS
                 # Filter Settings
                 first_retest_only: bool = True,
                 max_age_bars: int = 500,        # OBs expire faster
                 # Position Settings
                 position_size: float = 0.5):
        
        super().__init__(
            name=name,
            input_range=input_range,
            min_risk_reward=min_risk_reward,
            sl_atr_mult=sl_atr_mult,
            tp_rr_mult=tp_rr_mult,
            use_mitigated_blocks=False,
            first_retest_only=first_retest_only,
            max_age_bars=max_age_bars,
            position_size=position_size
        )
        
        # FVG Settings
        self.require_fvg = require_fvg
        self.min_fvg_percent = min_fvg_percent
        
        # Displacement Settings
        self.require_displacement = require_displacement
        self.min_displacement_percent = min_displacement_percent
        self.min_displacement_candles = min_displacement_candles
        
        # MSS Settings (for OB creation)
        self.require_ob_mss = require_ob_mss
        self.mss_lookback = mss_lookback
        
        # Entry Confirmation Settings
        self.mss_confirmation_bars = mss_confirmation_bars
        self.mss_swing_lookback = mss_swing_lookback
        
        # Track qualified OBs
        self.qualified_long_obs: List[OrderBlock] = []
        self.qualified_short_obs: List[OrderBlock] = []
        
        # Track POI (Point of Interest) state
        self.active_poi: Dict[int, Dict] = {}  # ob_index -> poi_state
    
    def _init_state(self):
        """Initialize state variables"""
        super()._init_state()
        self.qualified_long_obs = []
        self.qualified_short_obs = []
        self.prev_trend = None
        self.active_poi = {}
    
    def _detect_fvg(self, df: pd.DataFrame, current_idx: int, direction: str) -> Tuple[bool, float]:
        """
        Detect Fair Value Gap (FVG) / Imbalance
        
        Bullish FVG: Gap between candle[i-2].high and candle[i].low
        Bearish FVG: Gap between candle[i-2].low and candle[i].high
        
        Returns: (has_fvg, fvg_size_percent)
        """
        if current_idx < 3:
            return False, 0.0
        
        candle_1 = df.iloc[current_idx - 2]  # First candle
        candle_3 = df.iloc[current_idx]       # Third candle (current)
        
        if direction == 'bullish':
            # Bullish FVG: candle_3.low > candle_1.high (gap up)
            fvg_size = candle_3['low'] - candle_1['high']
            if fvg_size > 0:
                fvg_percent = (fvg_size / candle_1['high']) * 100
                return fvg_percent >= self.min_fvg_percent, fvg_percent
        else:
            # Bearish FVG: candle_3.high < candle_1.low (gap down)
            fvg_size = candle_1['low'] - candle_3['high']
            if fvg_size > 0:
                fvg_percent = (fvg_size / candle_1['low']) * 100
                return fvg_percent >= self.min_fvg_percent, fvg_percent
        
        return False, 0.0
    
    def _detect_displacement(self, df: pd.DataFrame, ob_idx: int, current_idx: int, direction: str) -> Tuple[bool, float]:
        """
        Detect price displacement (strong momentum move)
        
        Checks:
        1. Total price movement from OB
        2. Number of consecutive same-direction candles
        
        Returns: (has_displacement, displacement_percent)
        """
        if current_idx <= ob_idx + 1:
            return False, 0.0
        
        ob_price = df.iloc[ob_idx]['close']
        current_price = df.iloc[current_idx]['close']
        
        # Calculate total displacement
        if direction == 'bullish':
            displacement = ((current_price - ob_price) / ob_price) * 100
        else:
            displacement = ((ob_price - current_price) / ob_price) * 100
        
        # Check if displacement meets minimum
        if displacement < self.min_displacement_percent:
            return False, displacement
        
        # Count consecutive same-direction candles
        consecutive_count = 0
        for i in range(ob_idx + 1, min(current_idx + 1, ob_idx + 10)):
            candle = df.iloc[i]
            body = candle['close'] - candle['open']
            
            if direction == 'bullish' and body > 0:
                consecutive_count += 1
            elif direction == 'bearish' and body < 0:
                consecutive_count += 1
            else:
                break  # Sequence broken
        
        # Check minimum consecutive candles
        if consecutive_count < self.min_displacement_candles:
            return False, displacement
        
        return True, displacement
    
    def _detect_trend_mss(self, df: pd.DataFrame, current_idx: int, new_direction: str) -> bool:
        """
        Detect Market Structure Shift for OB creation (trend reversal)
        
        MSS occurs when:
        - Previous trend was bullish ‘Â∆ now bearish BOS
        - Previous trend was bearish ‘Â∆ now bullish BOS
        
        Returns: True if this is a market structure shift
        """
        if current_idx < self.mss_lookback:
            return False
        
        # Determine previous trend using highs and lows
        lookback_data = df.iloc[current_idx - self.mss_lookback:current_idx]
        closes = lookback_data['close'].values
        
        # Simple trend detection: compare first half avg to second half avg
        mid = len(closes) // 2
        first_half_avg = closes[:mid].mean()
        second_half_avg = closes[mid:].mean()
        
        if second_half_avg > first_half_avg * 1.01:  # 1% threshold
            prev_trend = 'bullish'
        elif second_half_avg < first_half_avg * 0.99:
            prev_trend = 'bearish'
        else:
            prev_trend = 'neutral'
        
        # MSS occurs when new direction opposes previous trend
        if new_direction == 'bearish' and prev_trend == 'bullish':
            return True  # Bullish to bearish shift
        elif new_direction == 'bullish' and prev_trend == 'bearish':
            return True  # Bearish to bullish shift
        
        return False
    
    def _find_swing_high(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[float, int]:
        """Find the highest swing high in range"""
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
            # Handle datetime index
            pos = subset.index.get_loc(max_idx)
            return subset.iloc[pos]['high'], start_idx + pos
    
    def _find_swing_low(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Tuple[float, int]:
        """Find the lowest swing low in range"""
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
            # Handle datetime index
            pos = subset.index.get_loc(min_idx)
            return subset.iloc[pos]['low'], start_idx + pos
    
    def _detect_entry_mss(self, df: pd.DataFrame, current_idx: int, poi: Dict, direction: str) -> Tuple[bool, float]:
        """
        Detect Market Structure Shift for entry confirmation
        
        After price taps OB:
        - For LONG: Look for break of lower high (bullish MSS)
        - For SHORT: Look for break of higher low (bearish MSS)
        
        Returns: (mss_confirmed, sl_price)
        """
        tap_idx = poi['tap_index']
        bars_since_tap = current_idx - tap_idx
        
        if bars_since_tap < 2:
            return False, 0.0
        
        if bars_since_tap > self.mss_confirmation_bars:
            # Too many bars without MSS - invalidate POI
            return False, 0.0
        
        current = df.iloc[current_idx]
        
        if direction == 'bullish':
            # For bullish entry: need break of lower high
            # Find the swing low since tap (this will be our SL reference)
            swing_low, swing_low_idx = self._find_swing_low(df, tap_idx, current_idx)
            
            if swing_low_idx == -1:
                return False, 0.0
            
            # Find swing high after the swing low
            swing_high, swing_high_idx = self._find_swing_high(df, swing_low_idx, current_idx)
            
            if swing_high_idx == -1 or swing_high_idx <= swing_low_idx:
                return False, 0.0
            
            # MSS confirmed when price breaks above the swing high
            if current['close'] > swing_high:
                # SL below the swing low
                sl_price = swing_low - (swing_low * 0.001)  # Small buffer
                return True, sl_price
                
        else:  # bearish
            # For bearish entry: need break of higher low
            # Find the swing high since tap (this will be our SL reference)
            swing_high, swing_high_idx = self._find_swing_high(df, tap_idx, current_idx)
            
            if swing_high_idx == -1:
                return False, 0.0
            
            # Find swing low after the swing high
            swing_low, swing_low_idx = self._find_swing_low(df, swing_high_idx, current_idx)
            
            if swing_low_idx == -1 or swing_low_idx <= swing_high_idx:
                return False, 0.0
            
            # MSS confirmed when price breaks below the swing low
            if current['close'] < swing_low:
                # SL above the swing high
                sl_price = swing_high + (swing_high * 0.001)  # Small buffer
                return True, sl_price
        
        return False, 0.0
    
    def _detect_bearish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bearish BOS with FVG and displacement validation - creates POI"""
        prev_close = df.iloc[current_idx - 1]['close']
        
        if prev_close >= self.structure_low and current['close'] < self.structure_low:
            # Basic BOS detected - now validate quality
            
            # Check for FVG
            has_fvg, fvg_percent = True, 0.0
            if self.require_fvg:
                has_fvg, fvg_percent = self._detect_fvg(df, current_idx, 'bearish')
            
            # Check for displacement
            has_displacement, displacement_pct = True, 0.0
            if self.require_displacement:
                has_displacement, displacement_pct = self._detect_displacement(
                    df, self.last_up_index, current_idx, 'bearish'
                )
            
            # Check for trend MSS (optional)
            is_trend_mss = False
            if self.require_ob_mss:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bearish')
                if not is_trend_mss:
                    return  # Skip if trend MSS required but not detected
            else:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bearish')
            
            # Only create OB if all conditions met
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
                    
                    # Add to qualified list
                    self.short_obs.append(ob)
                    self.qualified_short_obs.append(ob)
                    self.last_short_index = self.last_up_index
                    self.bearish_alert = True
                    
                    # Print premium OB info
                    self._print_premium_ob_info(
                        ob, current['close'], df, 
                        has_fvg, fvg_percent,
                        has_displacement, displacement_pct,
                        is_trend_mss
                    )
    
    def _detect_bullish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bullish BOS with FVG and displacement validation - creates POI"""
        if not self.short_obs:
            return
        
        short_ob = self.short_obs[-1]
        
        if current['close'] > short_ob.top and current_idx > short_ob.index:
            # Basic BOS detected - now validate quality
            
            # Check for FVG
            has_fvg, fvg_percent = True, 0.0
            if self.require_fvg:
                has_fvg, fvg_percent = self._detect_fvg(df, current_idx, 'bullish')
            
            # Check for displacement
            has_displacement, displacement_pct = True, 0.0
            if self.require_displacement:
                has_displacement, displacement_pct = self._detect_displacement(
                    df, self.last_down_index, current_idx, 'bullish'
                )
            
            # Check for trend MSS (optional)
            is_trend_mss = False
            if self.require_ob_mss:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bullish')
                if not is_trend_mss:
                    self.short_obs.pop()
                    return
            else:
                is_trend_mss = self._detect_trend_mss(df, current_idx, 'bullish')
            
            self.bullish_alert = True
            
            # Only create OB if all conditions met
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
                    
                    # Add to qualified list
                    self.long_obs.append(ob)
                    self.qualified_long_obs.append(ob)
                    self.last_long_index = current_idx
                    
                    # Print premium OB info
                    self._print_premium_ob_info(
                        ob, current['close'], df,
                        has_fvg, fvg_percent,
                        has_displacement, displacement_pct,
                        is_trend_mss
                    )
            
            # Remove mitigated short OB
            self.short_obs.pop()
    
    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """
        Check for entry signals with MSS confirmation
        
        Entry Logic:
        1. Price must tap into OB zone (POI activation)
        2. Wait for MSS confirmation
        3. Entry after MSS with SL at swing point
        4. TP at least 3x risk
        """
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
        
        current_idx = len(df) - 1
        atr = current.get('atr', current['close'] * 0.02)
        
        # =====================================================================
        # STEP 1: Check for POI activation (price taps OB)
        # =====================================================================
        
        # Check bullish OBs for tap
        for ob in self.long_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            
            ob_key = f"long_{ob.index}"
            
            # Price taps OB zone (enters from above)
            if current['low'] <= ob.top and current['high'] > ob.bottom:
                if ob_key not in self.active_poi:
                    # Activate POI - don't enter yet, wait for MSS
                    self.active_poi[ob_key] = {
                        'ob': ob,
                        'direction': 'bullish',
                        'tap_index': current_idx,
                        'tap_price': current['low'],
                        'waiting_mss': True
                    }
                    print(f"\n≠ÉÙÏ POI ACTIVATED - Bullish OB tapped at ${current['low']:,.2f}")
                    print(f"   Waiting for MSS confirmation...")
        
        # Check bearish OBs for tap
        for ob in self.short_obs:
            if ob.state != OBState.ACTIVE.value:
                continue
            
            ob_key = f"short_{ob.index}"
            
            # Price taps OB zone (enters from below)
            if current['high'] >= ob.bottom and current['low'] < ob.top:
                if ob_key not in self.active_poi:
                    # Activate POI - don't enter yet, wait for MSS
                    self.active_poi[ob_key] = {
                        'ob': ob,
                        'direction': 'bearish',
                        'tap_index': current_idx,
                        'tap_price': current['high'],
                        'waiting_mss': True
                    }
                    print(f"\n≠ÉÙÏ POI ACTIVATED - Bearish OB tapped at ${current['high']:,.2f}")
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
            
            # Check if POI expired (too many bars without MSS)
            if bars_since_tap > self.mss_confirmation_bars:
                expired_pois.append(poi_key)
                print(f"\n‘≈¶ POI EXPIRED - No MSS within {self.mss_confirmation_bars} bars")
                continue
            
            # Check for MSS confirmation
            mss_confirmed, sl_price = self._detect_entry_mss(df, current_idx, poi, direction)
            
            if mss_confirmed:
                # =====================================================================
                # STEP 3: ENTRY EXECUTION
                # =====================================================================
                
                entry_price = current['close']
                
                if direction == 'bullish':
                    # LONG entry
                    risk_distance = entry_price - sl_price
                    tp_price = entry_price + (risk_distance * self.tp_rr_mult)
                    
                    # Verify R:R
                    reward = tp_price - entry_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        
                        print(f"\n‘£‡ {'='*60}")
                        print(f"≠ÉÉÛ LONG ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"≠ÉÙÏ Entry:     ${entry_price:,.2f}")
                        print(f"≠É¯Ê Stop Loss: ${sl_price:,.2f} (MSS swing low)")
                        print(f"≠Éƒª Target:    ${tp_price:,.2f} ({self.tp_rr_mult}x risk)")
                        print(f"≠ÉÙË Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"≠ÉÙÍ Reward:    ${reward:,.2f} ({reward/entry_price*100:.2f}%)")
                        print(f"‘‹˚¥©≈  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        
                        return {
                            'signal': 'LONG',
                            'sl': sl_price,
                            'tp': tp_price,
                            'size': self.position_size,
                            'ob_index': ob.index,
                            'ob_type': 'bullish',
                            'entry_type': 'mss_confirmation'
                        }
                
                else:  # bearish
                    # SHORT entry
                    risk_distance = sl_price - entry_price
                    tp_price = entry_price - (risk_distance * self.tp_rr_mult)
                    
                    # Verify R:R
                    reward = entry_price - tp_price
                    rr = reward / risk_distance if risk_distance > 0 else 0
                    
                    if rr >= self.min_risk_reward:
                        expired_pois.append(poi_key)
                        
                        print(f"\n‘£‡ {'='*60}")
                        print(f"≠Éˆ¶ SHORT ENTRY - MSS CONFIRMED!")
                        print(f"{'='*60}")
                        print(f"≠ÉÙÏ Entry:     ${entry_price:,.2f}")
                        print(f"≠É¯Ê Stop Loss: ${sl_price:,.2f} (MSS swing high)")
                        print(f"≠Éƒª Target:    ${tp_price:,.2f} ({self.tp_rr_mult}x risk)")
                        print(f"≠ÉÙË Risk:      ${risk_distance:,.2f} ({risk_distance/entry_price*100:.2f}%)")
                        print(f"≠ÉÙÍ Reward:    ${reward:,.2f} ({reward/entry_price*100:.2f}%)")
                        print(f"‘‹˚¥©≈  R:R:       1:{rr:.1f}")
                        print(f"{'='*60}\n")
                        
                        return {
                            'signal': 'SHORT',
                            'sl': sl_price,
                            'tp': tp_price,
                            'size': self.position_size,
                            'ob_index': ob.index,
                            'ob_type': 'bearish',
                            'entry_type': 'mss_confirmation'
                        }
        
        # Clean up expired POIs
        for poi_key in expired_pois:
            del self.active_poi[poi_key]
        
        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}
    
    def _print_premium_ob_info(self, ob: OrderBlock, current_price: float, df: pd.DataFrame,
                               has_fvg: bool, fvg_percent: float,
                               has_displacement: bool, displacement_pct: float,
                               is_trend_mss: bool):
        """Print premium order block information with quality metrics"""
        ob_id = id(ob)
        
        if ob.ob_type == 'bullish':
            if self._last_printed_ob_long == ob_id:
                return
            self._last_printed_ob_long = ob_id
        else:
            if self._last_printed_ob_short == ob_id:
                return
            self._last_printed_ob_short = ob_id
        
        emoji = "≠ÉÉÛ" if ob.ob_type == "bullish" else "≠Éˆ¶"
        quality = "‘°…‘°…‘°… PREMIUM POI" if is_trend_mss else "‘°…‘°… HIGH QUALITY POI"
        ob_range = ob.top - ob.bottom
        
        print(f"\n{emoji} {'='*60}")
        print(f"{quality} - {ob.ob_type.upper()} ORDER BLOCK")
        print(f"{'='*60}")
        print(f"≠ÉÙÏ OB Zone:        ${ob.bottom:,.2f} - ${ob.top:,.2f}")
        print(f"≠ÉÙ≈ OB Width:       ${ob_range:,.2f} ({ob_range/ob.bottom*100:.2f}%)")
        print(f"≠É∆¶ Current Price:  ${current_price:,.2f}")
        print(f"")
        print(f"‘£‡ QUALITY CHECKS:")
        print(f"   ≠ÉÙË FVG/Imbalance:    {'YES' if has_fvg else 'NO'} ({fvg_percent:.2f}%)")
        print(f"   ≠É‹« Displacement:     {'YES' if has_displacement else 'NO'} ({displacement_pct:.2f}%)")
        print(f"   ≠Éˆ‰ Trend Reversal:   {'YES' if is_trend_mss else 'NO'}")
        print(f"")
        print(f"‘≈¶ WAITING: Price to tap OB zone for entry")
        print(f"≠ÉÙÔ ENTRY:   Will confirm with MSS on tap")
        print(f"≠ÉÚ… Created: {ob.created_at}")
        print(f"{'='*60}\n")
    
    def get_stats(self) -> Dict:
        """Get strategy statistics including quality metrics"""
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

