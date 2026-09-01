class OrderBlockStrategy(Strategy):
    """
    Order Block Strategy - Ported from PineScript

    Trading Logic (matching PineScript):
    1. Track structure: swing highs/lows within inputRange
    2. Bearish BOS: Price crosses below structure low ÔåÆ Create Bearish OB
    3. Bullish BOS: Price breaks above Bearish OB top ÔåÆ Mitigate Bearish OB,
       Create Bullish OB
    4. Bearish OB Mitigation: Price goes below Bullish OB bottom ÔåÆ Remove OB
    5. Bullish OB Mitigation: Price goes above Bullish OB top ÔåÆ Remove OB

    Entry Signals:
    - LONG when price re-tests Bullish OB (with validation)
    - SHORT when price re-tests Bearish OB (with validation)
    """

    def __init__(self,
                 name: str = "OrderBlockStrategy",
                 # Structure Settings (matching PineScript)
                 input_range: int = 25,  # Candle range for swing detection
                 # Trading Settings
                 min_risk_reward: float = 1.5,
                 sl_atr_mult: float = 2.0,
                 tp_rr_mult: float = 2.0,
                 # Filter Settings
                 use_mitigated_blocks: bool = False,  # Show mitigated blocks
                 first_retest_only: bool = True,  # Only trade first retest
                 max_age_bars: int = 1000,  # Max bars since OB formation
                 # Position Settings
                 position_size: float = 0.5):  # 50% of capital per trade
        super().__init__(name=name)

        # Structure Settings
        self.input_range = input_range

        # Trading Settings
        self.min_risk_reward = min_risk_reward
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr_mult = tp_rr_mult

        # Filter Settings
        self.use_mitigated_blocks = use_mitigated_blocks
        self.first_retest_only = first_retest_only
        self.max_age_bars = max_age_bars

        # Position Settings
        self.position_size = position_size

    def on_init(self, df: pd.DataFrame):
        """Initialize strategy with data - calculate all needed values"""
        df = df.copy()

        # Calculate ATR for SL/TP
        df['atr'] = self._calculate_atr(df, 14)

        # Track last up/down candles (for OB placement)
        df['last_down_high'] = 0.0
        df['last_down_index'] = 0
        df['last_down_low'] = 0.0

        df['last_up_close'] = 0.0
        df['last_up_index'] = 0
        df['last_up_low'] = 0.0
        df['last_up_open'] = 0.0
        df['last_high'] = 0.0

        # Track current structure values
        df['structure_low'] = 0.0
        df['structure_low_index'] = 0

        # OB tracking columns
        df['long_ob_top'] = 0.0
        df['long_ob_bottom'] = 0.0
        df['long_ob_index'] = 0
        df['long_ob_state'] = 0  # 0=active, 1=mitigated

        df['short_ob_top'] = 0.0
        df['short_ob_bottom'] = 0.0
        df['short_ob_index'] = 0
        df['short_ob_state'] = 0

        # Signals
        df['bullish_signal'] = False
        df['bearish_signal'] = False
        df['long_retest'] = False
        df['short_retest'] = False

        # Store in strategy
        self.data = df
        self.initialized = True

        # Initialize state tracking
        self._init_state()

    def _init_state(self):
        """Initialize state variables for OB tracking"""
        # Last up/down tracking
        self.last_down_high = 0.0
        self.last_down_index = 0
        self.last_down_low = 0.0

        self.last_up_close = 0.0
        self.last_up_index = 0
        self.last_up_open = 0.0
        self.last_up_low = 0.0
        self.last_high = 0.0

        # Structure tracking
        self.structure_low = float('inf')
        self.structure_low_index = 0

        # OB tracking
        self.long_obs: List[OrderBlock] = []
        self.short_obs: List[OrderBlock] = []

        # Last OB indices (to prevent duplication)
        self.last_long_index = 0
        self.last_short_index = 0

        # Signals
        self.bullish_alert = False
        self.bearish_alert = False
        self.long_retest = False
        self.short_retest = False
        
        # Track last printed OB to avoid duplicates
        self._last_printed_ob_long = None
        self._last_printed_ob_short = None

    def on_bar(self, df: pd.DataFrame, position: PositionSide = None) -> Dict:
        """Generate trading signal for current bar"""
        if len(df) < self.input_range + 10:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        current = df.iloc[-1]
        current_idx = len(df) - 1

        # Update state step by step
        self._update_structure(df, current_idx)
        self._detect_bearish_bos(df, current, current_idx)
        self._detect_bullish_bos(df, current, current_idx)
        self._update_ob_status(df, current, current_idx)

        # Reset candle signals
        self.long_retest = False
        self.short_retest = False

        # Check for entry signals
        return self._check_entries(df, current, position)

    def _update_structure(self, df: pd.DataFrame, current_idx: int):
        """Update structure low and track swing points"""
        lookback = self.input_range

        if current_idx < lookback + 1:
            return

        # Get structure low (lowest low in range)
        self.structure_low = df['low'].iloc[current_idx - lookback:current_idx].min()
        self.structure_low_index = df['low'].iloc[current_idx - lookback:current_idx].idxmin()

        if isinstance(self.structure_low_index, datetime):
            self.structure_low_index = df.index.get_loc(self.structure_low_index)
        else:
            # Already an index
            pass

        # Update last up/down candles
        last_row = df.iloc[current_idx - 1]

        if last_row['close'] < last_row['open']:
            # Bearish candle
            self.last_down_high = last_row['high']
            self.last_down_index = current_idx - 1
            self.last_down_low = last_row['low']
        else:
            # Bullish candle
            self.last_up_close = last_row['close']
            self.last_up_index = current_idx - 1
            self.last_up_open = last_row['open']
            self.last_up_low = last_row['low']
            self.last_high = last_row['high']

        # Update last high/low for accurate OB placement
        self.last_high = max(self.last_high, last_row['high'])
        self.last_low = min(self.last_down_low if self.last_down_low else float('inf'),
                           last_row['low']) if self.last_down_low else last_row['low']

    def _detect_bearish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bearish break of structure - creates Bearish OB"""
        # Bearish BOS: price crosses below structure low
        prev_close = df.iloc[current_idx - 1]['close']

        if prev_close >= self.structure_low and current['close'] < self.structure_low:
            # Check timing (prevent duplicates)
            if current_idx - self.last_up_index < self.max_age_bars:
                # Create bearish order block
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
                self.last_short_index = self.last_up_index
                self.bearish_alert = True
                
                # Print OB info
                self._print_ob_info(ob, current['close'], df)

    def _detect_bullish_bos(self, df: pd.DataFrame, current, current_idx: int):
        """Detect bullish break of structure - mitigates Bearish OB, creates Bullish OB"""
        if not self.short_obs:
            return

        # Check most recent short OB
        short_ob = self.short_obs[-1]

        # Bullish BOS: price breaks above Bearish OB top
        if current['close'] > short_ob.top and current_idx > short_ob.index:
            # Mitigate/remove short OB
            self.bullish_alert = True

            # Check timing and create Bullish OB
            if current_idx - self.last_down_index < self.max_age_bars and current_idx > self.last_long_index:
                # Create bullish order block
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
                self.last_long_index = current_idx

                # Print OB info
                self._print_ob_info(ob, current['close'], df)

                # Remove mitigated short OB
                self.short_obs.pop()

    def _print_ob_info(self, ob: OrderBlock, current_price: float, df: pd.DataFrame):
        """Print order block information"""
        ob_id = id(ob)
        
        # Check if we already printed this OB
        if ob.ob_type == 'bullish':
            if self._last_printed_ob_long == ob_id:
                return
            self._last_printed_ob_long = ob_id
        else:
            if self._last_printed_ob_short == ob_id:
                return
            self._last_printed_ob_short = ob_id
        
        emoji = "­ƒƒó" if ob.ob_type == "bullish" else "­ƒö¦"
        ob_range = ob.top - ob.bottom
        
        try:
            if ob.ob_type == "bullish":
                distance_pct = ((current_price - ob.bottom) / ob.bottom * 100) if ob.bottom != 0 else 0
            else:
                distance_pct = ((ob.top - current_price) / current_price * 100) if current_price != 0 else 0
                
            width_pct = (ob_range/ob.bottom*100) if ob.bottom != 0 else 0
        except ZeroDivisionError:
            distance_pct = 0
            width_pct = 0

        print(f"\n{emoji} {'='*60}")
        print(f"NEW {ob.ob_type.upper()} ORDER BLOCK DETECTED")
        print(f"{'='*60}")
        print(f"­ƒôì Price Range:  ${ob.bottom:,.2f} - ${ob.top:,.2f}")
        print(f"­ƒôÅ OB Width:     ${ob_range:,.2f} ({width_pct:.2f}%)")
        print(f"­ƒÆ¦ Current Price: ${current_price:,.2f}")
        print(f"­ƒôè Distance:     {distance_pct:.2f}% {'above' if ob.ob_type == 'bullish' else 'below'} OB")
        print(f"­ƒòÉ Created:      {ob.created_at}")
        print(f"­ƒôê State:        {OBState(ob.state).name}")
        print(f"{'='*60}\n")
    
    def get_last_ob_info(self) -> Dict[str, Any]:
        """Get information about the last order blocks"""
        result = {
            'bullish': None,
            'bearish': None
        }
        
        if self.long_obs:
            ob = self.long_obs[-1]
            result['bullish'] = {
                'top': ob.top,
                'bottom': ob.bottom,
                'range': ob.top - ob.bottom,
                'created_at': ob.created_at,
                'state': OBState(ob.state).name,
                'timestamp': ob.timestamp
            }
        
        if self.short_obs:
            ob = self.short_obs[-1]
            result['bearish'] = {
                'top': ob.top,
                'bottom': ob.bottom,
                'range': ob.top - ob.bottom,
                'created_at': ob.created_at,
                'state': OBState(ob.state).name,
                'timestamp': ob.timestamp
            }
        
        return result

    def _update_ob_status(self, df: pd.DataFrame, current, current_idx: int):
        """Update OB status (mitigation checks)"""
        # Check Long OB mitigation
        for i, ob in enumerate(self.long_obs):
            if ob.state == OBState.ACTIVE.value:
                # Long OB mitigated when price goes below bottom
                if current['close'] < ob.bottom:
                    ob.state = OBState.MITIGATED.value
                    if self.first_retest_only:
                        self.long_obs.pop(i)

        # Check Short OB mitigation
        for i, ob in enumerate(self.short_obs):
            if ob.state == OBState.ACTIVE.value:
                # Short OB mitigated when price goes above top
                if current['close'] > ob.top:
                    ob.state = OBState.MITIGATED.value
                    if self.first_retest_only:
                        self.short_obs.pop(i)

    def _check_entries(self, df: pd.DataFrame, current, position) -> Dict:
        """Check for entry signals"""
        if PositionSide and position and position != PositionSide.FLAT:
            return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

        atr = current.get('atr', current['close'] * 0.02)

        # Check Long OB retest
        for ob in self.long_obs:
            if ob.state == OBState.ACTIVE.value:
                # Price enters OB zone
                if current['low'] <= ob.top and current['high'] > ob.top:
                    self.long_retest = True

                    # Generate LONG signal
                    sl_price = ob.bottom - atr * self.sl_atr_mult
                    risk_distance = current['close'] - sl_price
                    tp_price = current['close'] + risk_distance * self.tp_rr_mult
                    reward_distance = tp_price - current['close']

                    # Check risk/reward
                    rr = reward_distance / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue

                    return {
                        'signal': 'LONG',
                        'sl': sl_price,
                        'tp': tp_price,
                        'size': self.position_size,
                        'ob_index': ob.index,
                        'ob_type': 'bullish'
                    }

        # Check Short OB retest
        for ob in self.short_obs:
            if ob.state == OBState.ACTIVE.value:
                # Price enters OB zone
                if current['high'] >= ob.bottom and current['low'] < ob.bottom:
                    self.short_retest = True

                    # Generate SHORT signal
                    sl_price = ob.top + atr * self.sl_atr_mult
                    risk_distance = sl_price - current['close']
                    tp_price = current['close'] - risk_distance * self.tp_rr_mult
                    reward_distance = current['close'] - tp_price

                    # Check risk/reward
                    rr = reward_distance / risk_distance if risk_distance > 0 else 0
                    if rr < self.min_risk_reward:
                        continue

                    return {
                        'signal': 'SHORT',
                        'sl': sl_price,
                        'tp': tp_price,
                        'size': self.position_size,
                        'ob_index': ob.index,
                        'ob_type': 'bearish'
                    }

        return {'signal': 'FLAT', 'sl': None, 'tp': None, 'size': 0.0}

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate ATR"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def get_ob_zones(self) -> Dict:
        """Get current OB zones for visualization"""
        long_zones = [(ob.index, ob.top, ob.bottom, ob.ob_type, ob.state)
                      for ob in self.long_obs if ob.state == OBState.ACTIVE.value or self.use_mitigated_blocks]
        short_zones = [(ob.index, ob.top, ob.bottom, ob.ob_type, ob.state)
                       for ob in self.short_obs if ob.state == OBState.ACTIVE.value or self.use_mitigated_blocks]

        return {
            'long_zones': long_zones,
            'short_zones': short_zones,
            'structure_low': (self.structure_low_index, self.structure_low)
        }


# ============================================================================
# ORDER BLOCK STRATEGY - TRADE ALL (INCLUDING MITIGATED)
# ============================================================================

