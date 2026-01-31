"""
Funding Rate Filter for Futures Trading
Avoid trades when market is overleveraged in one direction

Features:
- Fetch funding rate from exchanges (Binance, Bybit)
- Identify overleveraged markets
- Filter trades based on funding sentiment
- Suggest trading bias based on funding
"""
import ccxt
from datetime import datetime
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class FundingInfo:
    """Funding rate information"""
    symbol: str
    rate: float                    # Current funding rate (e.g., 0.0001 = 0.01%)
    rate_pct: float                # Rate as percentage
    rate_annualized: float         # Annualized rate percentage
    next_funding_time: Optional[datetime]
    sentiment: str                 # 'overleveraged_longs', 'overleveraged_shorts', 'neutral'
    is_extreme: bool               # Is funding rate extreme?
    longs_pay: bool                # True if longs pay shorts


class FundingRateFilter:
    """
    Filter trades based on funding rate
    
    Key Concepts:
    - Positive funding = Longs pay shorts (market bullish, longs overleveraged)
    - Negative funding = Shorts pay longs (market bearish, shorts overleveraged)
    - Extreme funding often precedes reversals
    
    Trading Rules:
    - High positive funding → Avoid longs (fade the crowd)
    - High negative funding → Avoid shorts (fade the crowd)
    - Extreme funding → Potential mean reversion opportunity
    
    Usage:
        filter = FundingRateFilter()
        
        # Check if should avoid a LONG
        avoid, reason = filter.should_avoid_trade('BTC/USDT', 'LONG')
        if avoid:
            print(f"Skipping LONG: {reason}")
    """
    
    # Thresholds (per 8-hour funding period)
    EXTREME_THRESHOLD = 0.0005   # 0.05% per 8h = very high
    HIGH_THRESHOLD = 0.0003      # 0.03% per 8h = elevated
    NORMAL_RANGE = 0.0001        # 0.01% = typical
    
    def __init__(self, exchange_id: str = 'binance'):
        """
        Initialize funding rate filter
        
        Args:
            exchange_id: Exchange to use ('binance', 'bybit')
        """
        self.exchange_id = exchange_id
        self._init_exchange()
    
    def _init_exchange(self):
        """Initialize futures exchange connection"""
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future'  # Use futures/perpetual market
                }
            })
            self.exchange_available = True
        except Exception as e:
            print(f"⚠️ Could not initialize futures exchange: {e}")
            self.exchange = None
            self.exchange_available = False
    
    def get_funding_rate(self, symbol: str = 'BTC/USDT') -> Optional[FundingInfo]:
        """
        Get current funding rate for symbol
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
        
        Returns:
            FundingInfo object or None if error
        """
        if not self.exchange_available:
            return None
        
        try:
            rate = 0
            next_time = None
            
            if self.exchange_id == 'binance':
                # Binance Futures API
                symbol_formatted = symbol.replace('/', '')
                funding = self.exchange.fapiPublicGetPremiumIndex({
                    'symbol': symbol_formatted
                })
                rate = float(funding.get('lastFundingRate', 0))
                next_timestamp = funding.get('nextFundingTime')
                if next_timestamp:
                    next_time = datetime.fromtimestamp(int(next_timestamp) / 1000)
            
            elif self.exchange_id == 'bybit':
                # Bybit API
                symbol_formatted = symbol.replace('/', '')
                tickers = self.exchange.fetch_tickers()
                if symbol in tickers:
                    rate = float(tickers[symbol].get('info', {}).get('fundingRate', 0))
            
            else:
                # Generic method - may not work for all exchanges
                ticker = self.exchange.fetch_ticker(symbol)
                rate = float(ticker.get('info', {}).get('fundingRate', 0) or 0)
            
            # Calculate metrics
            rate_pct = rate * 100
            annualized = rate * 3 * 365 * 100  # 3 funding periods per day
            
            # Determine sentiment
            if rate > self.HIGH_THRESHOLD:
                sentiment = 'overleveraged_longs'
            elif rate < -self.HIGH_THRESHOLD:
                sentiment = 'overleveraged_shorts'
            else:
                sentiment = 'neutral'
            
            is_extreme = abs(rate) > self.EXTREME_THRESHOLD
            longs_pay = rate > 0
            
            return FundingInfo(
                symbol=symbol,
                rate=rate,
                rate_pct=rate_pct,
                rate_annualized=annualized,
                next_funding_time=next_time,
                sentiment=sentiment,
                is_extreme=is_extreme,
                longs_pay=longs_pay
            )
            
        except Exception as e:
            print(f"⚠️ Error fetching funding rate for {symbol}: {e}")
            return None
    
    def should_avoid_trade(
        self,
        symbol: str,
        direction: str,  # 'LONG' or 'SHORT'
        strict: bool = False
    ) -> Tuple[bool, str]:
        """
        Check if trade should be avoided based on funding
        
        Args:
            symbol: Trading pair
            direction: 'LONG' or 'SHORT'
            strict: If True, use HIGH threshold. If False, only EXTREME.
        
        Returns:
            (should_avoid: bool, reason: str)
        """
        funding = self.get_funding_rate(symbol)
        
        if funding is None:
            return False, "Could not fetch funding rate - proceeding with trade"
        
        threshold = self.HIGH_THRESHOLD if strict else self.EXTREME_THRESHOLD
        
        # High positive funding = avoid longs (longs are paying, overleveraged)
        if direction == 'LONG' and funding.rate > threshold:
            return True, (
                f"Funding {funding.rate_pct:.4f}% - longs overleveraged. "
                f"Annualized cost: {funding.rate_annualized:.1f}%"
            )
        
        # High negative funding = avoid shorts (shorts are paying, overleveraged)
        if direction == 'SHORT' and funding.rate < -threshold:
            return True, (
                f"Funding {funding.rate_pct:.4f}% - shorts overleveraged. "
                f"Annualized cost: {abs(funding.rate_annualized):.1f}%"
            )
        
        return False, f"Funding {funding.rate_pct:.4f}% - acceptable for {direction}"
    
    def get_funding_bias(self, symbol: str = 'BTC/USDT') -> Tuple[str, float, str]:
        """
        Get suggested trading bias based on funding (contrarian)
        
        Contrarian Logic:
        - Extreme positive funding → Bias SHORT (fade overleveraged longs)
        - Extreme negative funding → Bias LONG (fade overleveraged shorts)
        
        Returns:
            (bias: 'LONG'/'SHORT'/'NEUTRAL', confidence: 0-1, reason: str)
        """
        funding = self.get_funding_rate(symbol)
        
        if funding is None:
            return 'NEUTRAL', 0, "Could not fetch funding rate"
        
        rate = funding.rate
        
        # Extreme positive funding = fade longs (bias SHORT)
        if rate > self.EXTREME_THRESHOLD:
            confidence = min(abs(rate) / (self.EXTREME_THRESHOLD * 2), 1.0)
            return 'SHORT', confidence, (
                f"Extreme positive funding ({funding.rate_pct:.3f}%) - "
                f"longs overleveraged, contrarian bias SHORT"
            )
        
        # Extreme negative funding = fade shorts (bias LONG)
        if rate < -self.EXTREME_THRESHOLD:
            confidence = min(abs(rate) / (self.EXTREME_THRESHOLD * 2), 1.0)
            return 'LONG', confidence, (
                f"Extreme negative funding ({funding.rate_pct:.3f}%) - "
                f"shorts overleveraged, contrarian bias LONG"
            )
        
        # Moderate positive = slight short bias
        if rate > self.HIGH_THRESHOLD:
            confidence = 0.3
            return 'SHORT', confidence, f"Elevated positive funding ({funding.rate_pct:.3f}%)"
        
        # Moderate negative = slight long bias
        if rate < -self.HIGH_THRESHOLD:
            confidence = 0.3
            return 'LONG', confidence, f"Elevated negative funding ({funding.rate_pct:.3f}%)"
        
        return 'NEUTRAL', 0, f"Funding neutral ({funding.rate_pct:.4f}%)"
    
    def get_funding_cost(
        self,
        symbol: str,
        direction: str,
        position_size_usd: float,
        holding_hours: int = 24
    ) -> Tuple[float, str]:
        """
        Calculate expected funding cost for holding a position
        
        Args:
            symbol: Trading pair
            direction: 'LONG' or 'SHORT'
            position_size_usd: Position size in USD
            holding_hours: Expected holding time in hours
        
        Returns:
            (cost_usd: float, explanation: str)
        """
        funding = self.get_funding_rate(symbol)
        
        if funding is None:
            return 0, "Could not calculate - funding rate unavailable"
        
        # Funding is paid/received every 8 hours
        funding_periods = holding_hours / 8
        
        # Cost calculation depends on direction and funding sign
        if direction == 'LONG':
            if funding.longs_pay:
                # Longs pay when funding is positive
                cost = position_size_usd * funding.rate * funding_periods
                return cost, f"LONG pays ${cost:.2f} ({funding_periods:.1f} periods × {funding.rate_pct:.4f}%)"
            else:
                # Longs receive when funding is negative
                income = position_size_usd * abs(funding.rate) * funding_periods
                return -income, f"LONG receives ${income:.2f} ({funding_periods:.1f} periods × {abs(funding.rate_pct):.4f}%)"
        
        else:  # SHORT
            if not funding.longs_pay:
                # Shorts pay when funding is negative
                cost = position_size_usd * abs(funding.rate) * funding_periods
                return cost, f"SHORT pays ${cost:.2f} ({funding_periods:.1f} periods × {abs(funding.rate_pct):.4f}%)"
            else:
                # Shorts receive when funding is positive
                income = position_size_usd * funding.rate * funding_periods
                return -income, f"SHORT receives ${income:.2f} ({funding_periods:.1f} periods × {funding.rate_pct:.4f}%)"
    
    def print_funding_info(self, symbol: str = 'BTC/USDT'):
        """Print formatted funding rate information"""
        funding = self.get_funding_rate(symbol)
        
        if funding is None:
            print(f"❌ Could not fetch funding for {symbol}")
            return
        
        # Emoji based on rate
        if funding.is_extreme:
            emoji = "🔥" if funding.rate > 0 else "❄️"
        elif abs(funding.rate) > self.HIGH_THRESHOLD:
            emoji = "🟡"
        else:
            emoji = "🟢"
        
        extreme_warning = " ⚠️ EXTREME" if funding.is_extreme else ""
        
        print(f"\n{'='*55}")
        print(f"💰 FUNDING RATE: {symbol}")
        print(f"{'='*55}")
        print(f"Current Rate:     {emoji} {funding.rate_pct:+.4f}%{extreme_warning}")
        print(f"Annualized:       {funding.rate_annualized:+.1f}%")
        print(f"Who Pays:         {'Longs → Shorts' if funding.longs_pay else 'Shorts → Longs'}")
        print(f"Sentiment:        {funding.sentiment.upper().replace('_', ' ')}")
        
        if funding.next_funding_time:
            print(f"Next Funding:     {funding.next_funding_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get bias
        bias, confidence, reason = self.get_funding_bias(symbol)
        if confidence > 0:
            print(f"\n📊 Contrarian Bias: {bias} (confidence: {confidence:.0%})")
            print(f"   {reason}")
        
        # Example cost calculation
        cost, cost_reason = self.get_funding_cost(symbol, 'LONG', 10000, 24)
        print(f"\n💵 24h Funding Cost ($10k LONG): {cost_reason}")
        
        print(f"{'='*55}\n")


# Global instance
_funding_filter = None

def get_funding_filter(exchange_id: str = 'binance') -> FundingRateFilter:
    """Get or create global funding filter instance"""
    global _funding_filter
    if _funding_filter is None:
        _funding_filter = FundingRateFilter(exchange_id)
    return _funding_filter


if __name__ == "__main__":
    # Example usage
    print("Initializing Funding Rate Filter...")
    
    filter = FundingRateFilter(exchange_id='binance')
    
    # Print funding info for major pairs
    for symbol in ['BTC/USDT', 'ETH/USDT']:
        filter.print_funding_info(symbol)
    
    # Check if should avoid trades
    print("\n📋 Trade Checks:")
    print("-"*40)
    
    for symbol in ['BTC/USDT']:
        for direction in ['LONG', 'SHORT']:
            avoid, reason = filter.should_avoid_trade(symbol, direction)
            status = "❌ AVOID" if avoid else "✅ OK"
            print(f"{symbol} {direction}: {status}")
            print(f"   {reason}\n")
