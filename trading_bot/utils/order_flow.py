"""
Order Flow Analysis Module (Phase 2)
=====================================
Analyze market microstructure data beyond OHLCV candles:
- Cumulative Volume Delta (CVD): Buy vs sell pressure
- Open Interest tracking: Leverage sentiment
- Large Trade Detection: Whale/institutional activity

Features:
- Real-time and historical data via CCXT + Binance REST API
- Configurable thresholds for signal generation
- Integration with RiskManager for trade filtering
- Caching to minimize API calls
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import ccxt
except ImportError:
    ccxt = None

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


# ==============================================================================
# Data Classes
# ==============================================================================

class OrderFlowBias(Enum):
    """Overall order flow bias"""
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


@dataclass
class CVDData:
    """Cumulative Volume Delta data"""
    cvd_value: float              # Current CVD value
    cvd_change_pct: float         # CVD change over lookback (%)
    buy_volume: float             # Total buy volume
    sell_volume: float            # Total sell volume
    volume_ratio: float           # buy_volume / sell_volume
    delta_trend: str              # 'rising', 'falling', 'flat'
    divergence: Optional[str]     # 'bullish_div', 'bearish_div', None
    timestamp: Optional[datetime] = None

    def __repr__(self):
        return (
            f"CVD({self.cvd_value:+,.2f} | Δ{self.cvd_change_pct:+.1f}% | "
            f"Buy/Sell={self.volume_ratio:.2f} | {self.delta_trend}"
            f"{' | ' + self.divergence if self.divergence else ''})"
        )


@dataclass
class OpenInterestData:
    """Open Interest data"""
    current_oi: float             # Current open interest (contracts)
    current_oi_value: float       # Current OI in USD
    oi_change_pct: float          # OI change over lookback (%)
    oi_trend: str                 # 'rising', 'falling', 'flat'
    price_oi_signal: str          # 'trend_strong', 'trend_weak', 'reversal_likely', 'neutral'
    is_extreme: bool              # Unusually high OI change
    timestamp: Optional[datetime] = None

    def __repr__(self):
        return (
            f"OI(${self.current_oi_value:,.0f} | Δ{self.oi_change_pct:+.1f}% | "
            f"{self.oi_trend} | Signal: {self.price_oi_signal})"
        )


@dataclass
class LargeTradeData:
    """Large trade detection data"""
    whale_buy_count: int          # Number of large buy trades
    whale_sell_count: int         # Number of large sell trades
    whale_buy_volume: float       # Total large buy volume
    whale_sell_volume: float      # Total large sell volume
    whale_ratio: float            # whale_buy_volume / whale_sell_volume
    whale_bias: str               # 'buying', 'selling', 'neutral'
    largest_trade: float          # Largest single trade size
    avg_large_trade: float        # Average large trade size
    alert_level: str              # 'normal', 'elevated', 'extreme'
    timestamp: Optional[datetime] = None

    def __repr__(self):
        total = self.whale_buy_count + self.whale_sell_count
        return (
            f"Whales({total} trades | Buy/Sell={self.whale_ratio:.2f} | "
            f"Bias: {self.whale_bias} | Alert: {self.alert_level})"
        )


@dataclass
class OrderFlowSignal:
    """Combined order flow signal"""
    bias: OrderFlowBias           # Overall bias
    confidence: float             # 0-1 confidence score
    cvd: Optional[CVDData]
    open_interest: Optional[OpenInterestData]
    large_trades: Optional[LargeTradeData]
    should_avoid_long: bool       # True if order flow is bearish
    should_avoid_short: bool      # True if order flow is bullish
    reasons: List[str]            # Reasons for the signal
    warnings: List[str]           # Warnings
    timestamp: datetime = field(default_factory=datetime.now)

    def __repr__(self):
        return (
            f"OrderFlow({self.bias.value} | Conf={self.confidence:.0%} | "
            f"Avoid LONG={'❌' if self.should_avoid_long else '✅'} | "
            f"Avoid SHORT={'❌' if self.should_avoid_short else '✅'})"
        )


# ==============================================================================
# Order Flow Analyzer
# ==============================================================================

class OrderFlowAnalyzer:
    """
    Analyzes order flow data to provide trade bias and filtering.

    Components:
    1. CVD (Cumulative Volume Delta)
       - Tracks buy vs sell pressure from trade tape
       - Detects bullish/bearish divergences with price

    2. Open Interest
       - Monitors futures leverage
       - Detects overleverage and liquidation risk

    3. Large Trade Detection
       - Identifies whale/institutional activity
       - Detects accumulation/distribution

    Usage:
        analyzer = OrderFlowAnalyzer(exchange_id='binance')

        # Get full analysis
        signal = analyzer.get_order_flow_signal('BTC/USDT')

        if signal.should_avoid_long:
            print("Order flow bearish, skip LONG")

        # Or check individual components
        cvd = analyzer.get_cvd('BTC/USDT')
        oi = analyzer.get_open_interest('BTC/USDT')
        whales = analyzer.detect_large_trades('BTC/USDT')
    """

    # === Configuration Defaults ===
    DEFAULT_CVD_LOOKBACK = 500       # Number of recent trades for CVD
    DEFAULT_OI_LOOKBACK_HOURS = 24   # Hours of OI history
    DEFAULT_WHALE_THRESHOLD_BTC = 1.0  # BTC threshold for "large trade"
    DEFAULT_WHALE_THRESHOLD_USD = 50000  # USD threshold for "large trade"

    # CVD thresholds
    CVD_STRONG_THRESHOLD = 0.15      # 15% CVD change = strong signal
    CVD_MODERATE_THRESHOLD = 0.05    # 5% CVD change = moderate signal

    # OI thresholds
    OI_EXTREME_CHANGE_PCT = 10.0     # 10% OI change = extreme
    OI_SIGNIFICANT_CHANGE_PCT = 5.0  # 5% OI change = significant

    # Large trade thresholds
    WHALE_ALERT_COUNT = 5            # 5+ whale trades = elevated
    WHALE_EXTREME_COUNT = 15         # 15+ whale trades = extreme

    def __init__(
        self,
        exchange_id: str = 'binance',
        cvd_lookback: int = None,
        whale_threshold_usd: float = None,
        oi_lookback_hours: int = None,
        cache_ttl_seconds: int = 60,
    ):
        """
        Initialize Order Flow Analyzer.

        Args:
            exchange_id: Exchange for data ('binance', 'bybit')
            cvd_lookback: Number of recent trades for CVD calculation
            whale_threshold_usd: USD threshold for large trade detection
            oi_lookback_hours: Hours of OI history to analyze
            cache_ttl_seconds: Cache lifetime to reduce API calls
        """
        self.exchange_id = exchange_id
        self.cvd_lookback = cvd_lookback or self.DEFAULT_CVD_LOOKBACK
        self.whale_threshold_usd = whale_threshold_usd or self.DEFAULT_WHALE_THRESHOLD_USD
        self.oi_lookback_hours = oi_lookback_hours or self.DEFAULT_OI_LOOKBACK_HOURS
        self.cache_ttl = cache_ttl_seconds

        # Initialize exchange
        self._exchange = None
        self._exchange_available = False
        self._init_exchange()

        # Cache
        self._cache: Dict[str, Tuple[datetime, Any]] = {}

    def _init_exchange(self):
        """Initialize exchange connection"""
        if ccxt is None:
            logger.warning("ccxt not installed, order flow analysis unavailable")
            return

        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self._exchange = exchange_class({
                'enableRateLimit': True,
                'timeout': 30000,
                'options': {
                    'defaultType': 'future'  # Use futures for OI data
                }
            })
            self._exchange_available = True
            logger.info(f"OrderFlow: Connected to {self.exchange_id} futures")
        except Exception as e:
            logger.warning(f"OrderFlow: Could not init exchange: {e}")
            self._exchange_available = False

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self._cache:
            cached_time, value = self._cache[key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl:
                return value
        return None

    def _set_cached(self, key: str, value: Any):
        """Store value in cache"""
        self._cache[key] = (datetime.now(), value)

    # ==========================================================================
    # 1. CUMULATIVE VOLUME DELTA (CVD)
    # ==========================================================================

    def _fetch_recent_trades(self, symbol: str, limit: int = None) -> Optional[pd.DataFrame]:
        """
        Fetch recent trades from exchange.

        Returns DataFrame with columns: timestamp, price, amount, side, cost
        """
        limit = limit or self.cvd_lookback
        cache_key = f"trades_{symbol}_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not self._exchange_available:
            return None

        try:
            # Try spot exchange for trades (more liquid)
            spot_exchange_class = getattr(ccxt, self.exchange_id)
            spot_exchange = spot_exchange_class({
                'enableRateLimit': True,
                'timeout': 30000,
            })
            raw_trades = spot_exchange.fetch_trades(symbol, limit=limit)

            if not raw_trades:
                return None

            trades_data = []
            for t in raw_trades:
                trades_data.append({
                    'timestamp': pd.to_datetime(t['timestamp'], unit='ms'),
                    'price': float(t['price']),
                    'amount': float(t['amount']),
                    'side': t['side'],  # 'buy' or 'sell'
                    'cost': float(t.get('cost', t['price'] * t['amount']))
                })

            df = pd.DataFrame(trades_data)
            self._set_cached(cache_key, df)
            return df

        except Exception as e:
            logger.warning(f"OrderFlow: Failed to fetch trades for {symbol}: {e}")
            return None

    def get_cvd(self, symbol: str = 'BTC/USDT', price_series: pd.Series = None) -> Optional[CVDData]:
        """
        Calculate Cumulative Volume Delta.

        CVD = Running sum of (buy volume - sell volume)
        - Rising CVD + Rising Price → Strong trend (buyers in control)
        - Falling CVD + Rising Price → Bearish divergence (weakness)
        - Rising CVD + Falling Price → Bullish divergence (accumulation)
        - Falling CVD + Falling Price → Strong downtrend (sellers in control)

        Args:
            symbol: Trading pair
            price_series: Optional price data for divergence detection

        Returns:
            CVDData with analysis results
        """
        cache_key = f"cvd_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        trades_df = self._fetch_recent_trades(symbol)
        if trades_df is None or trades_df.empty:
            return None

        # Calculate volume delta per trade
        trades_df['volume_delta'] = trades_df.apply(
            lambda x: x['amount'] if x['side'] == 'buy' else -x['amount'],
            axis=1
        )

        # Cumulative sum
        trades_df['cvd'] = trades_df['volume_delta'].cumsum()

        # Metrics
        buy_mask = trades_df['side'] == 'buy'
        sell_mask = trades_df['side'] == 'sell'

        buy_volume = trades_df.loc[buy_mask, 'amount'].sum()
        sell_volume = trades_df.loc[sell_mask, 'amount'].sum()
        volume_ratio = buy_volume / sell_volume if sell_volume > 0 else float('inf')

        # CVD value and change
        cvd_value = trades_df['cvd'].iloc[-1]
        lookback_idx = max(0, len(trades_df) - min(100, len(trades_df)))
        cvd_start = trades_df['cvd'].iloc[lookback_idx]
        total_volume = buy_volume + sell_volume
        cvd_change_pct = ((cvd_value - cvd_start) / total_volume * 100) if total_volume > 0 else 0

        # CVD trend (using recent slope)
        recent_cvd = trades_df['cvd'].tail(50)
        if len(recent_cvd) >= 10:
            slope = np.polyfit(range(len(recent_cvd)), recent_cvd.values, 1)[0]
            avg_vol = trades_df['amount'].mean()
            normalized_slope = slope / avg_vol if avg_vol > 0 else 0
            if normalized_slope > 0.05:
                delta_trend = 'rising'
            elif normalized_slope < -0.05:
                delta_trend = 'falling'
            else:
                delta_trend = 'flat'
        else:
            delta_trend = 'flat'

        # Divergence detection
        divergence = None
        if price_series is not None and len(price_series) >= 10:
            recent_prices = price_series.tail(50)
            price_change = (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]

            if price_change > 0.005 and delta_trend == 'falling':
                divergence = 'bearish_div'  # Price up but CVD falling
            elif price_change < -0.005 and delta_trend == 'rising':
                divergence = 'bullish_div'  # Price down but CVD rising

        result = CVDData(
            cvd_value=cvd_value,
            cvd_change_pct=cvd_change_pct,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            volume_ratio=volume_ratio,
            delta_trend=delta_trend,
            divergence=divergence,
            timestamp=datetime.now()
        )

        self._set_cached(cache_key, result)
        return result

    # ==========================================================================
    # 2. OPEN INTEREST TRACKING
    # ==========================================================================

    def _fetch_open_interest(self, symbol: str) -> Optional[Dict]:
        """
        Fetch current open interest from Binance Futures API.

        Returns dict with oi, oi_value, timestamp
        """
        cache_key = f"oi_current_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if requests is None:
            logger.warning("requests not installed, OI unavailable")
            return None

        try:
            # Binance Futures API - Open Interest
            binance_symbol = symbol.replace('/', '').replace('-', '')
            url = f"https://fapi.binance.com/fapi/v1/openInterest"
            params = {'symbol': binance_symbol}

            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            oi = float(data.get('openInterest', 0))

            # Get mark price for USD value
            price_url = f"https://fapi.binance.com/fapi/v1/ticker/price"
            price_resp = requests.get(price_url, params={'symbol': binance_symbol}, timeout=10)
            price_data = price_resp.json()
            mark_price = float(price_data.get('price', 0))

            result = {
                'oi': oi,
                'oi_value': oi * mark_price,
                'mark_price': mark_price,
                'timestamp': datetime.now()
            }

            self._set_cached(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"OrderFlow: Failed to fetch OI for {symbol}: {e}")
            return None

    def _fetch_oi_history(self, symbol: str, period: str = '5m', limit: int = 100) -> Optional[pd.DataFrame]:
        """
        Fetch historical open interest from Binance Futures.

        Args:
            symbol: Trading pair
            period: Kline interval (5m, 15m, 30m, 1h, 4h, 1d)
            limit: Number of data points

        Returns:
            DataFrame with timestamp, oi, oi_value columns
        """
        cache_key = f"oi_hist_{symbol}_{period}_{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if requests is None:
            return None

        try:
            binance_symbol = symbol.replace('/', '').replace('-', '')
            url = "https://fapi.binance.com/futures/data/openInterestHist"
            params = {
                'symbol': binance_symbol,
                'period': period,
                'limit': limit
            }

            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                return None

            records = []
            for d in data:
                records.append({
                    'timestamp': pd.to_datetime(d['timestamp'], unit='ms'),
                    'oi': float(d['sumOpenInterest']),
                    'oi_value': float(d['sumOpenInterestValue'])
                })

            df = pd.DataFrame(records)
            self._set_cached(cache_key, df)
            return df

        except Exception as e:
            logger.warning(f"OrderFlow: Failed to fetch OI history for {symbol}: {e}")
            return None

    def get_open_interest(
        self,
        symbol: str = 'BTC/USDT',
        price_series: pd.Series = None
    ) -> Optional[OpenInterestData]:
        """
        Analyze Open Interest data.

        OI + Price Interpretation:
        - Rising OI + Rising Price   → Strong uptrend (new longs entering)
        - Rising OI + Falling Price  → Strong downtrend (new shorts entering)
        - Falling OI + Rising Price  → Short squeeze / weak rally
        - Falling OI + Falling Price → Long liquidation / weak decline

        Args:
            symbol: Trading pair
            price_series: Optional recent price data

        Returns:
            OpenInterestData with analysis
        """
        cache_key = f"oi_analysis_{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Fetch current OI
        current = self._fetch_open_interest(symbol)
        if current is None:
            return None

        # Fetch OI history
        oi_hist = self._fetch_oi_history(symbol, period='5m', limit=100)

        oi_change_pct = 0.0
        oi_trend = 'flat'
        is_extreme = False

        if oi_hist is not None and len(oi_hist) >= 5:
            # Calculate OI change
            oi_start = oi_hist['oi_value'].iloc[0]
            oi_end = oi_hist['oi_value'].iloc[-1]
            oi_change_pct = ((oi_end - oi_start) / oi_start * 100) if oi_start > 0 else 0

            # OI trend
            recent_oi = oi_hist['oi_value'].tail(20)
            if len(recent_oi) >= 5:
                slope = np.polyfit(range(len(recent_oi)), recent_oi.values, 1)[0]
                avg_oi = recent_oi.mean()
                normalized = slope / avg_oi if avg_oi > 0 else 0
                if normalized > 0.001:
                    oi_trend = 'rising'
                elif normalized < -0.001:
                    oi_trend = 'falling'
                else:
                    oi_trend = 'flat'

            is_extreme = abs(oi_change_pct) > self.OI_EXTREME_CHANGE_PCT

        # Price-OI signal interpretation
        price_oi_signal = 'neutral'
        if price_series is not None and len(price_series) >= 5:
            price_change = (price_series.iloc[-1] - price_series.iloc[-20 if len(price_series) >= 20 else 0])
            price_up = price_change > 0

            if oi_trend == 'rising' and price_up:
                price_oi_signal = 'trend_strong'       # New money confirms trend
            elif oi_trend == 'rising' and not price_up:
                price_oi_signal = 'trend_strong'       # New shorts entering
            elif oi_trend == 'falling' and price_up:
                price_oi_signal = 'trend_weak'         # Short squeeze, not sustainable
            elif oi_trend == 'falling' and not price_up:
                price_oi_signal = 'reversal_likely'    # Closing positions, trend exhaustion

        result = OpenInterestData(
            current_oi=current['oi'],
            current_oi_value=current['oi_value'],
            oi_change_pct=oi_change_pct,
            oi_trend=oi_trend,
            price_oi_signal=price_oi_signal,
            is_extreme=is_extreme,
            timestamp=datetime.now()
        )

        self._set_cached(cache_key, result)
        return result

    # ==========================================================================
    # 3. LARGE TRADE DETECTION
    # ==========================================================================

    def detect_large_trades(
        self,
        symbol: str = 'BTC/USDT',
        threshold_usd: float = None
    ) -> Optional[LargeTradeData]:
        """
        Detect whale/institutional trades.

        Identifies unusually large trades that may signal:
        - Institutional accumulation (many large buys)
        - Distribution/dumping (many large sells)
        - Market manipulation attempts

        Args:
            symbol: Trading pair
            threshold_usd: USD threshold for "whale trade" (default: 50000)

        Returns:
            LargeTradeData with detection results
        """
        threshold = threshold_usd or self.whale_threshold_usd
        cache_key = f"whales_{symbol}_{threshold}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Fetch recent trades (more for whale detection)
        trades_df = self._fetch_recent_trades(symbol, limit=1000)
        if trades_df is None or trades_df.empty:
            return None

        # Identify large trades
        large_mask = trades_df['cost'] >= threshold
        large_trades = trades_df[large_mask]

        if large_trades.empty:
            result = LargeTradeData(
                whale_buy_count=0,
                whale_sell_count=0,
                whale_buy_volume=0,
                whale_sell_volume=0,
                whale_ratio=1.0,
                whale_bias='neutral',
                largest_trade=0,
                avg_large_trade=0,
                alert_level='normal',
                timestamp=datetime.now()
            )
            self._set_cached(cache_key, result)
            return result

        # Separate buys and sells
        whale_buys = large_trades[large_trades['side'] == 'buy']
        whale_sells = large_trades[large_trades['side'] == 'sell']

        whale_buy_count = len(whale_buys)
        whale_sell_count = len(whale_sells)
        whale_buy_volume = whale_buys['cost'].sum() if not whale_buys.empty else 0
        whale_sell_volume = whale_sells['cost'].sum() if not whale_sells.empty else 0

        # Volume ratio
        whale_ratio = whale_buy_volume / whale_sell_volume if whale_sell_volume > 0 else (
            float('inf') if whale_buy_volume > 0 else 1.0
        )

        # Bias determination
        total_whale = whale_buy_count + whale_sell_count
        if total_whale == 0:
            whale_bias = 'neutral'
        elif whale_ratio > 1.5:
            whale_bias = 'buying'
        elif whale_ratio < 0.67:
            whale_bias = 'selling'
        else:
            whale_bias = 'neutral'

        # Alert level
        if total_whale >= self.WHALE_EXTREME_COUNT:
            alert_level = 'extreme'
        elif total_whale >= self.WHALE_ALERT_COUNT:
            alert_level = 'elevated'
        else:
            alert_level = 'normal'

        # Trade stats
        largest_trade = large_trades['cost'].max()
        avg_large_trade = large_trades['cost'].mean()

        result = LargeTradeData(
            whale_buy_count=whale_buy_count,
            whale_sell_count=whale_sell_count,
            whale_buy_volume=whale_buy_volume,
            whale_sell_volume=whale_sell_volume,
            whale_ratio=whale_ratio,
            whale_bias=whale_bias,
            largest_trade=largest_trade,
            avg_large_trade=avg_large_trade,
            alert_level=alert_level,
            timestamp=datetime.now()
        )

        self._set_cached(cache_key, result)
        return result

    # ==========================================================================
    # COMBINED SIGNAL
    # ==========================================================================

    def get_order_flow_signal(
        self,
        symbol: str = 'BTC/USDT',
        direction: str = 'LONG',
        price_series: pd.Series = None,
        use_cvd: bool = True,
        use_oi: bool = True,
        use_large_trades: bool = True,
        strict: bool = False
    ) -> OrderFlowSignal:
        """
        Get combined order flow signal with bias and confidence.

        Combines CVD, OI, and Large Trade data into a single actionable signal.

        Args:
            symbol: Trading pair
            direction: Intended trade direction ('LONG' or 'SHORT')
            price_series: Recent price data for divergence/OI analysis
            use_cvd: Enable CVD analysis
            use_oi: Enable Open Interest analysis
            use_large_trades: Enable whale detection
            strict: If True, any negative signal blocks the trade

        Returns:
            OrderFlowSignal with combined analysis
        """
        reasons = []
        warnings = []
        scores = []  # -1 (bearish) to +1 (bullish) per component

        cvd_data = None
        oi_data = None
        large_trade_data = None

        # 1. CVD Analysis
        if use_cvd:
            cvd_data = self.get_cvd(symbol, price_series)
            if cvd_data is not None:
                # Score based on CVD trend and ratio
                if cvd_data.delta_trend == 'rising':
                    cvd_score = min(0.5 + abs(cvd_data.cvd_change_pct) / 20, 1.0)
                elif cvd_data.delta_trend == 'falling':
                    cvd_score = max(-0.5 - abs(cvd_data.cvd_change_pct) / 20, -1.0)
                else:
                    cvd_score = 0.0

                # Boost/penalize based on volume ratio
                if cvd_data.volume_ratio > 1.2:
                    cvd_score = min(cvd_score + 0.2, 1.0)
                elif cvd_data.volume_ratio < 0.8:
                    cvd_score = max(cvd_score - 0.2, -1.0)

                scores.append(('cvd', cvd_score, 0.4))  # 40% weight

                # Divergence signals
                if cvd_data.divergence == 'bearish_div':
                    warnings.append("⚠️ Bearish CVD divergence (price up, CVD down)")
                    scores.append(('cvd_div', -0.5, 0.15))
                elif cvd_data.divergence == 'bullish_div':
                    warnings.append("💡 Bullish CVD divergence (price down, CVD up)")
                    scores.append(('cvd_div', 0.5, 0.15))

                reasons.append(
                    f"CVD: {cvd_data.delta_trend} (Δ{cvd_data.cvd_change_pct:+.1f}%, "
                    f"Buy/Sell={cvd_data.volume_ratio:.2f})"
                )
            else:
                reasons.append("CVD: Data unavailable")

        # 2. Open Interest Analysis
        if use_oi:
            oi_data = self.get_open_interest(symbol, price_series)
            if oi_data is not None:
                # Score based on OI signal
                oi_score = 0.0
                if oi_data.price_oi_signal == 'trend_strong':
                    oi_score = 0.3 if oi_data.oi_trend == 'rising' else -0.3
                elif oi_data.price_oi_signal == 'trend_weak':
                    oi_score = -0.2  # Weak moves don't sustain
                elif oi_data.price_oi_signal == 'reversal_likely':
                    oi_score = 0.2  # May reverse, contrarian signal

                if oi_data.is_extreme:
                    warnings.append(
                        f"⚠️ Extreme OI change ({oi_data.oi_change_pct:+.1f}%) - "
                        f"liquidation cascade risk"
                    )
                    # Extreme OI = higher risk
                    oi_score *= 0.5

                scores.append(('oi', oi_score, 0.3))  # 30% weight

                reasons.append(
                    f"OI: {oi_data.oi_trend} (Δ{oi_data.oi_change_pct:+.1f}%, "
                    f"Signal: {oi_data.price_oi_signal})"
                )
            else:
                reasons.append("OI: Data unavailable")

        # 3. Large Trade Detection
        if use_large_trades:
            large_trade_data = self.detect_large_trades(symbol)
            if large_trade_data is not None:
                total_whales = large_trade_data.whale_buy_count + large_trade_data.whale_sell_count

                if total_whales > 0:
                    # Score based on whale bias
                    whale_score = 0.0
                    if large_trade_data.whale_bias == 'buying':
                        whale_score = min(0.3 + (large_trade_data.whale_ratio - 1.0) * 0.2, 1.0)
                    elif large_trade_data.whale_bias == 'selling':
                        safe_ratio = max(large_trade_data.whale_ratio, 0.01)  # Avoid div by zero
                        whale_score = max(-0.3 - (1.0 / safe_ratio - 1.0) * 0.2, -1.0)

                    scores.append(('whales', whale_score, 0.3))  # 30% weight

                    if large_trade_data.alert_level != 'normal':
                        warnings.append(
                            f"🐋 Whale alert ({large_trade_data.alert_level}): "
                            f"{total_whales} large trades, bias={large_trade_data.whale_bias}"
                        )

                    reasons.append(
                        f"Whales: {total_whales} trades ({large_trade_data.whale_bias}, "
                        f"ratio={large_trade_data.whale_ratio:.2f})"
                    )
                else:
                    reasons.append("Whales: No large trades detected")
            else:
                reasons.append("Whales: Data unavailable")

        # === COMBINE SCORES ===
        if scores:
            total_weight = sum(w for _, _, w in scores)
            weighted_score = sum(s * w for _, s, w in scores) / total_weight if total_weight > 0 else 0
        else:
            weighted_score = 0.0

        # Determine bias
        if weighted_score > 0.4:
            bias = OrderFlowBias.STRONG_BULLISH
        elif weighted_score > 0.15:
            bias = OrderFlowBias.BULLISH
        elif weighted_score < -0.4:
            bias = OrderFlowBias.STRONG_BEARISH
        elif weighted_score < -0.15:
            bias = OrderFlowBias.BEARISH
        else:
            bias = OrderFlowBias.NEUTRAL

        # Confidence = how strongly components agree
        confidence = min(abs(weighted_score) * 2, 1.0)

        # Should avoid signals
        should_avoid_long = False
        should_avoid_short = False

        if strict:
            should_avoid_long = bias in (OrderFlowBias.BEARISH, OrderFlowBias.STRONG_BEARISH)
            should_avoid_short = bias in (OrderFlowBias.BULLISH, OrderFlowBias.STRONG_BULLISH)
        else:
            # Only block on strong signals
            should_avoid_long = bias == OrderFlowBias.STRONG_BEARISH
            should_avoid_short = bias == OrderFlowBias.STRONG_BULLISH

        return OrderFlowSignal(
            bias=bias,
            confidence=confidence,
            cvd=cvd_data,
            open_interest=oi_data,
            large_trades=large_trade_data,
            should_avoid_long=should_avoid_long,
            should_avoid_short=should_avoid_short,
            reasons=reasons,
            warnings=warnings,
            timestamp=datetime.now()
        )

    # ==========================================================================
    # TRADE FILTERING (for RiskManager integration)
    # ==========================================================================

    def should_avoid_trade(
        self,
        symbol: str,
        direction: str,
        price_series: pd.Series = None,
        strict: bool = False
    ) -> Tuple[bool, str]:
        """
        Check if a trade should be avoided based on order flow.

        Simple interface matching FundingRateFilter.should_avoid_trade().

        Args:
            symbol: Trading pair
            direction: 'LONG' or 'SHORT'
            price_series: Recent price data
            strict: Use stricter thresholds

        Returns:
            Tuple of (should_avoid: bool, reason: str)
        """
        signal = self.get_order_flow_signal(
            symbol=symbol,
            direction=direction,
            price_series=price_series,
            strict=strict
        )

        if direction.upper() == 'LONG' and signal.should_avoid_long:
            reason = (
                f"Order flow bearish ({signal.bias.value}, "
                f"confidence={signal.confidence:.0%})"
            )
            return True, reason

        if direction.upper() == 'SHORT' and signal.should_avoid_short:
            reason = (
                f"Order flow bullish ({signal.bias.value}, "
                f"confidence={signal.confidence:.0%})"
            )
            return True, reason

        return False, ""

    def get_bias(self, symbol: str = 'BTC/USDT') -> Tuple[str, float]:
        """
        Get simple bias and confidence.

        Returns:
            Tuple of (bias: str, confidence: float)
        """
        signal = self.get_order_flow_signal(symbol)
        bias_map = {
            OrderFlowBias.STRONG_BULLISH: 'LONG',
            OrderFlowBias.BULLISH: 'LONG',
            OrderFlowBias.NEUTRAL: 'NEUTRAL',
            OrderFlowBias.BEARISH: 'SHORT',
            OrderFlowBias.STRONG_BEARISH: 'SHORT',
        }
        return bias_map.get(signal.bias, 'NEUTRAL'), signal.confidence

    # ==========================================================================
    # PRINTING & DISPLAY
    # ==========================================================================

    def print_analysis(self, symbol: str = 'BTC/USDT', price_series: pd.Series = None):
        """Print full order flow analysis to console"""
        signal = self.get_order_flow_signal(symbol, price_series=price_series)

        bias_emoji = {
            OrderFlowBias.STRONG_BULLISH: "🟢🟢",
            OrderFlowBias.BULLISH: "🟢",
            OrderFlowBias.NEUTRAL: "⚪",
            OrderFlowBias.BEARISH: "🔴",
            OrderFlowBias.STRONG_BEARISH: "🔴🔴",
        }

        print(f"\n{'═'*60}")
        print(f"📊 ORDER FLOW ANALYSIS: {symbol}")
        print(f"{'═'*60}")

        # CVD
        if signal.cvd:
            c = signal.cvd
            print(f"\n🔄 CUMULATIVE VOLUME DELTA (CVD)")
            print(f"   CVD Value:     {c.cvd_value:+,.4f}")
            print(f"   CVD Change:    {c.cvd_change_pct:+.2f}%")
            print(f"   Buy Volume:    {c.buy_volume:,.4f}")
            print(f"   Sell Volume:   {c.sell_volume:,.4f}")
            print(f"   Buy/Sell:      {c.volume_ratio:.3f}")
            print(f"   Trend:         {c.delta_trend.upper()}")
            if c.divergence:
                div_name = 'BULLISH' if c.divergence == 'bullish_div' else 'BEARISH'
                print(f"   Divergence:    ⚠️ {div_name}")

        # Open Interest
        if signal.open_interest:
            o = signal.open_interest
            print(f"\n📈 OPEN INTEREST")
            print(f"   Current OI:    {o.current_oi:,.2f} contracts")
            print(f"   OI Value:      ${o.current_oi_value:,.0f}")
            print(f"   OI Change:     {o.oi_change_pct:+.2f}%")
            print(f"   OI Trend:      {o.oi_trend.upper()}")
            print(f"   Price Signal:  {o.price_oi_signal.upper()}")
            if o.is_extreme:
                print(f"   ⚠️ EXTREME OI CHANGE!")

        # Large Trades
        if signal.large_trades:
            l = signal.large_trades
            total = l.whale_buy_count + l.whale_sell_count
            if total > 0:
                print(f"\n🐋 LARGE TRADES (>${self.whale_threshold_usd:,.0f})")
                print(f"   Whale Buys:    {l.whale_buy_count} (${l.whale_buy_volume:,.0f})")
                print(f"   Whale Sells:   {l.whale_sell_count} (${l.whale_sell_volume:,.0f})")
                print(f"   Buy/Sell:      {l.whale_ratio:.2f}" if l.whale_ratio != float('inf') else "   Buy/Sell:      ∞ (buys only)")
                print(f"   Whale Bias:    {l.whale_bias.upper()}")
                print(f"   Largest:       ${l.largest_trade:,.0f}")
                print(f"   Alert Level:   {l.alert_level.upper()}")
            else:
                print(f"\n🐋 LARGE TRADES: None detected")

        # Combined signal
        print(f"\n{'═'*60}")
        emoji = bias_emoji.get(signal.bias, '⚪')
        print(f"OVERALL BIAS: {emoji} {signal.bias.value} "
              f"(confidence: {signal.confidence:.0%})")
        print(f"{'═'*60}")

        print(f"\n   Trade Decision:")
        print(f"   LONG:  {'❌ Avoid' if signal.should_avoid_long else '✅ OK'}")
        print(f"   SHORT: {'❌ Avoid' if signal.should_avoid_short else '✅ OK'}")

        if signal.warnings:
            print(f"\n   Warnings:")
            for w in signal.warnings:
                print(f"      {w}")

        print(f"\n{'═'*60}")

        return signal


# ==============================================================================
# Factory/Global Instance
# ==============================================================================

_order_flow_analyzer = None


def get_order_flow_analyzer(
    exchange_id: str = 'binance',
    **kwargs
) -> OrderFlowAnalyzer:
    """Get or create global order flow analyzer instance"""
    global _order_flow_analyzer
    if _order_flow_analyzer is None:
        _order_flow_analyzer = OrderFlowAnalyzer(exchange_id=exchange_id, **kwargs)
    return _order_flow_analyzer


# ==============================================================================
# STANDALONE TEST
# ==============================================================================

if __name__ == "__main__":
    print("📊 Testing Order Flow Analyzer...\n")

    analyzer = OrderFlowAnalyzer(exchange_id='binance')

    # Full analysis
    signal = analyzer.print_analysis('BTC/USDT')

    # Simple check
    avoid, reason = analyzer.should_avoid_trade('BTC/USDT', 'LONG')
    print(f"\nShould avoid LONG? {'YES: ' + reason if avoid else 'NO'}")

    avoid, reason = analyzer.should_avoid_trade('BTC/USDT', 'SHORT')
    print(f"Should avoid SHORT? {'YES: ' + reason if avoid else 'NO'}")

    # Bias
    bias, conf = analyzer.get_bias('BTC/USDT')
    print(f"\nBias: {bias} (confidence: {conf:.0%})")
