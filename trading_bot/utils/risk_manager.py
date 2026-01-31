"""
Unified Risk Manager
====================
Combines all Phase 1 risk management features:
- Kelly Criterion Position Sizing
- Circuit Breaker
- Multi-Timeframe Confirmation
- Funding Rate Filter

This is the main entry point for risk management in strategies.
"""
from typing import Tuple, Optional, Dict
from dataclasses import dataclass

from .position_sizing import PositionSizer, get_position_sizer
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, get_circuit_breaker
from .multi_timeframe import MultiTimeframeAnalyzer, get_mtf_analyzer
from .funding_rate import FundingRateFilter, get_funding_filter


@dataclass
class TradeDecision:
    """Result of trade evaluation"""
    can_trade: bool
    position_size_pct: float
    position_size_usd: float
    reasons: list
    warnings: list
    mtf_score: float
    funding_bias: str


class RiskManager:
    """
    Unified Risk Manager
    
    Evaluates trades through multiple risk filters:
    1. Circuit Breaker - Is trading allowed?
    2. Multi-Timeframe - Does higher TF confirm?
    3. Funding Rate - Is market overleveraged?
    4. Position Sizing - How much to risk?
    
    Usage:
        rm = RiskManager(capital=10000)
        
        # Before taking a trade
        decision = rm.evaluate_trade(
            symbol='BTC/USDT',
            direction='LONG',
            entry_timeframe='15m'
        )
        
        if decision.can_trade:
            size = decision.position_size_usd
            # Execute trade with size
        else:
            print(f"Trade rejected: {decision.reasons}")
    """
    
    def __init__(
        self,
        capital: float = 10000,
        exchange_id: str = 'binance',
        use_mtf: bool = True,
        use_funding: bool = True,
        use_circuit_breaker: bool = True,
        use_kelly: bool = True,
        strict_funding: bool = False,
        require_all_mtf: bool = False,
        circuit_breaker_config: CircuitBreakerConfig = None
    ):
        """
        Initialize Risk Manager
        
        Args:
            capital: Trading capital
            exchange_id: Exchange for data fetching
            use_mtf: Enable multi-timeframe confirmation
            use_funding: Enable funding rate filter
            use_circuit_breaker: Enable circuit breaker
            use_kelly: Enable Kelly position sizing
            strict_funding: Use stricter funding thresholds
            require_all_mtf: Require ALL higher TFs to confirm
            circuit_breaker_config: Custom circuit breaker config
        """
        self.capital = capital
        self.exchange_id = exchange_id
        
        # Feature flags
        self.use_mtf = use_mtf
        self.use_funding = use_funding
        self.use_circuit_breaker = use_circuit_breaker
        self.use_kelly = use_kelly
        self.strict_funding = strict_funding
        self.require_all_mtf = require_all_mtf
        
        # Initialize components
        self.position_sizer = PositionSizer() if use_kelly else None
        
        self.circuit_breaker = CircuitBreaker(circuit_breaker_config) if use_circuit_breaker else None
        if self.circuit_breaker:
            self.circuit_breaker.initialize(capital)
        
        self.mtf_analyzer = MultiTimeframeAnalyzer(exchange_id=exchange_id) if use_mtf else None
        self.funding_filter = FundingRateFilter(exchange_id=exchange_id) if use_funding else None
        
        # Track state
        self._mtf_data_loaded = False
        self._last_symbol = None
    
    def update_capital(self, new_capital: float, trade_won: bool = None):
        """
        Update capital after a trade
        
        Args:
            new_capital: New account balance
            trade_won: Whether the last trade was profitable
        """
        self.capital = new_capital
        
        if self.circuit_breaker:
            self.circuit_breaker.update(new_capital, trade_won)
        
        if self.position_sizer and trade_won is not None:
            # Record trade for Kelly calculation
            pnl_pct = ((new_capital - self.capital) / self.capital) * 100
            self.position_sizer.add_trade(pnl_pct, trade_won)
    
    def load_mtf_data(self, symbol: str, force: bool = False):
        """Load multi-timeframe data for a symbol"""
        if not self.use_mtf or self.mtf_analyzer is None:
            return
        
        # Only reload if symbol changed or forced
        if self._last_symbol == symbol and self._mtf_data_loaded and not force:
            return
        
        self.mtf_analyzer.fetch_all_timeframes(
            symbol,
            timeframes=['15m', '1h', '4h', '1d']
        )
        self._mtf_data_loaded = True
        self._last_symbol = symbol
    
    def evaluate_trade(
        self,
        symbol: str,
        direction: str,  # 'LONG' or 'SHORT'
        entry_timeframe: str = '15m',
        current_atr_pct: float = None
    ) -> TradeDecision:
        """
        Evaluate a potential trade through all risk filters
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            direction: Trade direction ('LONG' or 'SHORT')
            entry_timeframe: Timeframe for entry
            current_atr_pct: Current ATR as % of price (for volatility adjustment)
        
        Returns:
            TradeDecision with approval status and sizing
        """
        reasons = []
        warnings = []
        can_trade = True
        mtf_score = 0
        funding_bias = 'NEUTRAL'
        
        # 1. Check Circuit Breaker
        if self.use_circuit_breaker and self.circuit_breaker:
            if not self.circuit_breaker.can_trade():
                can_trade = False
                reasons.append(f"Circuit breaker: {self.circuit_breaker.state.value}")
        
        # 2. Check Multi-Timeframe Confirmation
        if self.use_mtf and self.mtf_analyzer and can_trade:
            # Load MTF data if needed
            self.load_mtf_data(symbol)
            
            if self._mtf_data_loaded:
                confirmed, details = self.mtf_analyzer.get_confirmation(
                    entry_timeframe,
                    direction,
                    require_all=self.require_all_mtf
                )
                
                mtf_score, _ = self.mtf_analyzer.get_trend_alignment_score()
                
                if not confirmed:
                    can_trade = False
                    reasons.append(f"MTF rejection: {details.get('confirmation_rate', '?')}")
                else:
                    # Add warning if alignment is weak
                    if abs(mtf_score) < 0.3:
                        warnings.append(f"Weak MTF alignment (score: {mtf_score:.2f})")
        
        # 3. Check Funding Rate
        if self.use_funding and self.funding_filter and can_trade:
            avoid, reason = self.funding_filter.should_avoid_trade(
                symbol, direction, strict=self.strict_funding
            )
            
            if avoid:
                can_trade = False
                reasons.append(f"Funding: {reason}")
            
            # Get funding bias
            bias, confidence, _ = self.funding_filter.get_funding_bias(symbol)
            funding_bias = bias
            
            # Warn if trading against funding bias
            if confidence > 0.5 and bias != direction and bias != 'NEUTRAL':
                warnings.append(f"Trading against funding bias ({bias})")
        
        # 4. Calculate Position Size
        position_size_pct = 0.02  # Default 2%
        
        if self.use_kelly and self.position_sizer:
            position_size_pct, sizing_reason = self.position_sizer.get_position_size(
                current_atr_pct
            )
        else:
            sizing_reason = "Default 2% risk"
        
        position_size_usd = self.capital * position_size_pct
        
        # If trade not allowed, set size to 0
        if not can_trade:
            position_size_pct = 0
            position_size_usd = 0
        
        return TradeDecision(
            can_trade=can_trade,
            position_size_pct=position_size_pct,
            position_size_usd=position_size_usd,
            reasons=reasons if reasons else [f"Approved: {sizing_reason}"],
            warnings=warnings,
            mtf_score=mtf_score,
            funding_bias=funding_bias
        )
    
    def print_status(self):
        """Print status of all risk management components"""
        print("\n" + "="*60)
        print("🛡️ RISK MANAGER STATUS")
        print("="*60)
        
        print(f"\n💰 Capital: ${self.capital:,.2f}")
        print(f"\nEnabled Features:")
        print(f"   Circuit Breaker: {'✅' if self.use_circuit_breaker else '❌'}")
        print(f"   Multi-Timeframe: {'✅' if self.use_mtf else '❌'}")
        print(f"   Funding Filter:  {'✅' if self.use_funding else '❌'}")
        print(f"   Kelly Sizing:    {'✅' if self.use_kelly else '❌'}")
        
        if self.circuit_breaker:
            print("\n--- Circuit Breaker ---")
            status = self.circuit_breaker.get_status()
            print(f"   State: {status['state']}")
            print(f"   Drawdown: {status['drawdown_pct']:.1%}")
            print(f"   Consecutive Losses: {status['consecutive_losses']}")
        
        if self.position_sizer:
            print("\n--- Position Sizing ---")
            size, reason = self.position_sizer.get_position_size()
            print(f"   Recommended: {size:.1%} (${self.capital * size:,.2f})")
            print(f"   Reason: {reason}")
        
        if self.mtf_analyzer and self._mtf_data_loaded:
            print("\n--- Multi-Timeframe ---")
            score, desc = self.mtf_analyzer.get_trend_alignment_score()
            print(f"   Alignment: {desc}")
            print(f"   Score: {score:+.2f}")
        
        print("\n" + "="*60)


# Global instance
_risk_manager = None

def get_risk_manager(
    capital: float = 10000,
    exchange_id: str = 'binance',
    **kwargs
) -> RiskManager:
    """Get or create global risk manager instance"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager(capital=capital, exchange_id=exchange_id, **kwargs)
    return _risk_manager


if __name__ == "__main__":
    # Example usage
    print("🛡️ Testing Risk Manager...\n")
    
    rm = RiskManager(
        capital=10000,
        exchange_id='binance',
        use_mtf=True,
        use_funding=True,
        use_circuit_breaker=True,
        use_kelly=True
    )
    
    # Evaluate a potential trade
    print("Evaluating BTC/USDT LONG on 15m...")
    decision = rm.evaluate_trade(
        symbol='BTC/USDT',
        direction='LONG',
        entry_timeframe='15m'
    )
    
    print(f"\n📋 Trade Decision:")
    print(f"   Can Trade: {'✅' if decision.can_trade else '❌'}")
    print(f"   Position Size: {decision.position_size_pct:.1%} (${decision.position_size_usd:,.2f})")
    print(f"   MTF Score: {decision.mtf_score:+.2f}")
    print(f"   Funding Bias: {decision.funding_bias}")
    
    if decision.reasons:
        print(f"\n   Reasons:")
        for r in decision.reasons:
            print(f"      - {r}")
    
    if decision.warnings:
        print(f"\n   Warnings:")
        for w in decision.warnings:
            print(f"      ⚠️ {w}")
    
    # Print full status
    rm.print_status()
