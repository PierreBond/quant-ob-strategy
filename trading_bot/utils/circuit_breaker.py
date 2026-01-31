"""
Circuit Breaker - Risk Management System
Automatically pauses trading when risk thresholds are breached

Features:
- Max drawdown protection (full stop)
- Daily loss limit (temporary pause)
- Consecutive loss protection
- Daily trade limit
- Automatic cooldown periods
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Callable
from enum import Enum
import json
from pathlib import Path


class BreakerState(Enum):
    """Circuit breaker states"""
    ACTIVE = "active"           # Trading allowed
    PAUSED = "paused"           # Temporarily paused (auto-resumes)
    STOPPED = "stopped"         # Fully stopped - manual reset required


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker thresholds"""
    max_drawdown_pct: float = 0.15          # 15% max drawdown → STOP
    max_daily_loss_pct: float = 0.05        # 5% max daily loss → PAUSE
    max_consecutive_losses: int = 5          # 5 losses in a row → PAUSE
    cooldown_minutes: int = 60               # 1 hour cooldown after pause
    max_daily_trades: int = 20               # Max trades per day → PAUSE
    warning_drawdown_pct: float = 0.10       # 10% drawdown → WARNING


@dataclass
class TradingSession:
    """Track current trading session"""
    start_time: datetime = field(default_factory=datetime.now)
    start_capital: float = 0
    peak_capital: float = 0
    current_capital: float = 0
    daily_start_capital: float = 0
    daily_pnl: float = 0
    consecutive_losses: int = 0
    daily_trades: int = 0
    total_trades: int = 0
    last_trade_time: Optional[datetime] = None
    last_trade_won: Optional[bool] = None


class CircuitBreaker:
    """
    Risk management circuit breaker
    
    Monitors trading activity and automatically pauses/stops
    when risk thresholds are breached.
    
    Usage:
        breaker = CircuitBreaker()
        breaker.initialize(capital=10000)
        
        # Before each trade
        if breaker.can_trade():
            # execute trade
            pass
        
        # After each trade
        breaker.update(new_capital, trade_won=True)
    """
    
    def __init__(
        self,
        config: CircuitBreakerConfig = None,
        on_pause: Optional[Callable] = None,
        on_stop: Optional[Callable] = None,
        on_warning: Optional[Callable] = None
    ):
        """
        Initialize circuit breaker
        
        Args:
            config: Configuration thresholds
            on_pause: Callback when trading is paused
            on_stop: Callback when trading is stopped
            on_warning: Callback for warnings
        """
        self.config = config or CircuitBreakerConfig()
        self.state = BreakerState.ACTIVE
        self.session = TradingSession()
        self.pause_until: Optional[datetime] = None
        self.breach_history: List[dict] = []
        
        # Callbacks
        self.on_pause = on_pause
        self.on_stop = on_stop
        self.on_warning = on_warning
    
    def initialize(self, capital: float):
        """
        Initialize or reset session with starting capital
        
        Args:
            capital: Starting capital amount
        """
        now = datetime.now()
        self.session = TradingSession(
            start_time=now,
            start_capital=capital,
            peak_capital=capital,
            current_capital=capital,
            daily_start_capital=capital
        )
        self.state = BreakerState.ACTIVE
        self.pause_until = None
        print(f"🔌 Circuit Breaker initialized: ${capital:,.2f}")
        print(f"   Max Drawdown: {self.config.max_drawdown_pct:.0%}")
        print(f"   Max Daily Loss: {self.config.max_daily_loss_pct:.0%}")
        print(f"   Max Consecutive Losses: {self.config.max_consecutive_losses}")
    
    def _check_new_day(self):
        """Check if it's a new trading day and reset daily counters"""
        now = datetime.now()
        if self.session.start_time.date() < now.date():
            # New day - reset daily counters
            self.session.daily_start_capital = self.session.current_capital
            self.session.daily_pnl = 0
            self.session.daily_trades = 0
            self.session.start_time = now
            
            # Resume from daily pause (but not from STOP)
            if self.state == BreakerState.PAUSED:
                self.state = BreakerState.ACTIVE
                self.pause_until = None
                print("📅 New trading day - circuit breaker reset")
    
    def update(
        self,
        current_capital: float,
        trade_won: Optional[bool] = None
    ) -> bool:
        """
        Update circuit breaker with latest capital
        
        Args:
            current_capital: Current account value
            trade_won: True if last trade won, False if lost, None if no trade
        
        Returns:
            True if trading is still allowed, False if breaker tripped
        """
        self._check_new_day()
        
        old_capital = self.session.current_capital
        self.session.current_capital = current_capital
        self.session.peak_capital = max(self.session.peak_capital, current_capital)
        
        # Update daily PnL
        self.session.daily_pnl = current_capital - self.session.daily_start_capital
        
        # Update trade stats
        if trade_won is not None:
            self.session.daily_trades += 1
            self.session.total_trades += 1
            self.session.last_trade_time = datetime.now()
            self.session.last_trade_won = trade_won
            
            if trade_won:
                self.session.consecutive_losses = 0
            else:
                self.session.consecutive_losses += 1
        
        # Check all thresholds
        return self._check_thresholds()
    
    def _check_thresholds(self) -> bool:
        """Check all circuit breaker thresholds"""
        
        # Check if in cooldown
        if self.pause_until and datetime.now() < self.pause_until:
            remaining = (self.pause_until - datetime.now()).seconds // 60
            return False
        
        # Reset from pause if cooldown expired
        if self.state == BreakerState.PAUSED and self.pause_until:
            if datetime.now() >= self.pause_until:
                self.state = BreakerState.ACTIVE
                self.pause_until = None
                print("✅ Circuit breaker cooldown complete. Trading resumed.")
        
        # Check if stopped (requires manual reset)
        if self.state == BreakerState.STOPPED:
            return False
        
        # Check drawdown (STOP)
        if self._check_drawdown():
            return False
        
        # Check daily loss (PAUSE)
        if self._check_daily_loss():
            return False
        
        # Check consecutive losses (PAUSE)
        if self._check_consecutive_losses():
            return False
        
        # Check daily trade limit (PAUSE)
        if self._check_daily_trades():
            return False
        
        return True
    
    def _get_drawdown(self) -> float:
        """Calculate current drawdown percentage"""
        if self.session.peak_capital == 0:
            return 0
        return (self.session.peak_capital - self.session.current_capital) / self.session.peak_capital
    
    def _check_drawdown(self) -> bool:
        """Check if max drawdown exceeded"""
        drawdown = self._get_drawdown()
        
        # Warning at warning threshold
        if drawdown >= self.config.warning_drawdown_pct and drawdown < self.config.max_drawdown_pct:
            if self.on_warning:
                self.on_warning(f"Drawdown warning: {drawdown:.1%}")
            print(f"⚠️ DRAWDOWN WARNING: {drawdown:.1%} (max: {self.config.max_drawdown_pct:.0%})")
        
        # Stop at max threshold
        if drawdown >= self.config.max_drawdown_pct:
            self._trigger_stop(
                reason="MAX_DRAWDOWN",
                message=f"Drawdown {drawdown:.1%} exceeded {self.config.max_drawdown_pct:.0%} threshold"
            )
            return True
        
        return False
    
    def _check_daily_loss(self) -> bool:
        """Check if max daily loss exceeded"""
        if self.session.daily_start_capital == 0:
            return False
        
        daily_loss_pct = -self.session.daily_pnl / self.session.daily_start_capital
        
        if daily_loss_pct >= self.config.max_daily_loss_pct:
            self._trigger_pause(
                reason="DAILY_LOSS",
                message=f"Daily loss {daily_loss_pct:.1%} exceeded {self.config.max_daily_loss_pct:.0%}"
            )
            return True
        
        return False
    
    def _check_consecutive_losses(self) -> bool:
        """Check if max consecutive losses exceeded"""
        if self.session.consecutive_losses >= self.config.max_consecutive_losses:
            self._trigger_pause(
                reason="CONSECUTIVE_LOSSES",
                message=f"{self.session.consecutive_losses} consecutive losses"
            )
            return True
        return False
    
    def _check_daily_trades(self) -> bool:
        """Check if max daily trades exceeded"""
        if self.session.daily_trades >= self.config.max_daily_trades:
            self._trigger_pause(
                reason="DAILY_TRADE_LIMIT",
                message=f"Reached {self.config.max_daily_trades} daily trades"
            )
            return True
        return False
    
    def _trigger_pause(self, reason: str, message: str):
        """Trigger temporary pause"""
        self.state = BreakerState.PAUSED
        self.pause_until = datetime.now() + timedelta(minutes=self.config.cooldown_minutes)
        
        self.breach_history.append({
            'time': datetime.now().isoformat(),
            'reason': reason,
            'message': message,
            'action': 'PAUSE',
            'capital': self.session.current_capital,
            'drawdown': self._get_drawdown()
        })
        
        print(f"\n⏸️ CIRCUIT BREAKER PAUSED")
        print(f"   Reason: {message}")
        print(f"   Cooldown: {self.config.cooldown_minutes} minutes")
        print(f"   Resume at: {self.pause_until.strftime('%H:%M:%S')}\n")
        
        if self.on_pause:
            self.on_pause(message)
    
    def _trigger_stop(self, reason: str, message: str):
        """Trigger full stop - requires manual reset"""
        self.state = BreakerState.STOPPED
        
        self.breach_history.append({
            'time': datetime.now().isoformat(),
            'reason': reason,
            'message': message,
            'action': 'STOP',
            'capital': self.session.current_capital,
            'drawdown': self._get_drawdown()
        })
        
        print(f"\n🛑 CIRCUIT BREAKER STOPPED")
        print(f"   Reason: {message}")
        print(f"   Peak Capital: ${self.session.peak_capital:,.2f}")
        print(f"   Current Capital: ${self.session.current_capital:,.2f}")
        print(f"   Loss: ${self.session.peak_capital - self.session.current_capital:,.2f}")
        print(f"   Action: Manual reset required - call circuit_breaker.reset()\n")
        
        if self.on_stop:
            self.on_stop(message)
    
    def can_trade(self) -> bool:
        """Check if trading is currently allowed"""
        self._check_new_day()
        return self._check_thresholds()
    
    def reset(self, new_capital: Optional[float] = None):
        """
        Manual reset of circuit breaker
        
        Args:
            new_capital: New starting capital (or use current)
        """
        capital = new_capital or self.session.current_capital
        self.initialize(capital)
        print(f"🔄 Circuit breaker manually reset with ${capital:,.2f}")
    
    def get_status(self) -> dict:
        """Get current circuit breaker status"""
        drawdown = self._get_drawdown()
        daily_loss_pct = 0
        if self.session.daily_start_capital > 0:
            daily_loss_pct = -self.session.daily_pnl / self.session.daily_start_capital
        
        return {
            'state': self.state.value,
            'can_trade': self.state == BreakerState.ACTIVE,
            'current_capital': self.session.current_capital,
            'peak_capital': self.session.peak_capital,
            'drawdown_pct': drawdown,
            'drawdown_remaining': self.config.max_drawdown_pct - drawdown,
            'daily_pnl': self.session.daily_pnl,
            'daily_loss_pct': daily_loss_pct,
            'consecutive_losses': self.session.consecutive_losses,
            'daily_trades': self.session.daily_trades,
            'total_trades': self.session.total_trades,
            'pause_until': self.pause_until.isoformat() if self.pause_until else None,
            'thresholds': {
                'max_drawdown': self.config.max_drawdown_pct,
                'max_daily_loss': self.config.max_daily_loss_pct,
                'max_consecutive_losses': self.config.max_consecutive_losses,
                'max_daily_trades': self.config.max_daily_trades
            },
            'breach_count': len(self.breach_history)
        }
    
    def print_status(self):
        """Print formatted circuit breaker status"""
        status = self.get_status()
        
        state_emoji = {
            'active': '🟢',
            'paused': '🟡',
            'stopped': '🔴'
        }
        
        print("\n" + "="*50)
        print("🔌 CIRCUIT BREAKER STATUS")
        print("="*50)
        print(f"State:            {state_emoji.get(status['state'], '⚪')} {status['state'].upper()}")
        print(f"Current Capital:  ${status['current_capital']:,.2f}")
        print(f"Peak Capital:     ${status['peak_capital']:,.2f}")
        print(f"Drawdown:         {status['drawdown_pct']:.1%} / {self.config.max_drawdown_pct:.0%}")
        print(f"Daily P&L:        ${status['daily_pnl']:+,.2f} ({status['daily_loss_pct']:+.1%})")
        print(f"Consecutive L:    {status['consecutive_losses']} / {self.config.max_consecutive_losses}")
        print(f"Daily Trades:     {status['daily_trades']} / {self.config.max_daily_trades}")
        
        if status['pause_until']:
            print(f"Resume At:        {status['pause_until']}")
        
        print("="*50 + "\n")
    
    def save_state(self, filepath: str = 'circuit_breaker_state.json'):
        """Save circuit breaker state to file"""
        state = self.get_status()
        state['breach_history'] = self.breach_history
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def load_state(self, filepath: str = 'circuit_breaker_state.json') -> bool:
        """Load circuit breaker state from file"""
        path = Path(filepath)
        if not path.exists():
            return False
        
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            self.session.current_capital = state.get('current_capital', 10000)
            self.session.peak_capital = state.get('peak_capital', 10000)
            self.breach_history = state.get('breach_history', [])
            
            state_str = state.get('state', 'active')
            self.state = BreakerState(state_str)
            
            return True
        except Exception as e:
            print(f"Error loading circuit breaker state: {e}")
            return False


# Global instance
_circuit_breaker = None

def get_circuit_breaker(config: CircuitBreakerConfig = None) -> CircuitBreaker:
    """Get or create global circuit breaker instance"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(config)
    return _circuit_breaker


if __name__ == "__main__":
    # Example usage
    config = CircuitBreakerConfig(
        max_drawdown_pct=0.15,
        max_daily_loss_pct=0.05,
        max_consecutive_losses=5,
        cooldown_minutes=60
    )
    
    breaker = CircuitBreaker(config)
    breaker.initialize(capital=10000)
    
    # Simulate trading
    print("\n📊 Simulating trades...\n")
    
    trades = [
        (10200, True),   # Win
        (10150, False),  # Loss
        (10050, False),  # Loss
        (9900, False),   # Loss
        (9750, False),   # Loss
        (9600, False),   # Loss - consecutive limit hit
    ]
    
    for i, (capital, won) in enumerate(trades):
        print(f"Trade {i+1}: Capital=${capital:,.2f}, Won={won}")
        can_continue = breaker.update(capital, trade_won=won)
        
        if not can_continue:
            print("❌ Trading halted by circuit breaker!")
            break
    
    # Print final status
    breaker.print_status()
