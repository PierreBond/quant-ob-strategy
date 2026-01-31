"""
Kelly Criterion and Advanced Position Sizing
Calculates optimal position sizes based on historical performance
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
import json
from pathlib import Path


@dataclass
class TradeStats:
    """Statistics from historical trades"""
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    total_trades: int
    profit_factor: float


class PositionSizer:
    """
    Advanced position sizing with Kelly Criterion
    
    Kelly Formula: f* = W - (1-W)/R
    Where:
        f* = fraction of capital to bet
        W = win probability
        R = win/loss ratio (avg_win / avg_loss)
    """
    
    def __init__(
        self,
        max_position_pct: float = 0.25,      # Never risk more than 25%
        kelly_fraction: float = 0.5,          # Use half-Kelly for safety
        min_trades_for_kelly: int = 20,       # Need 20+ trades for reliable stats
        default_size_pct: float = 0.02,       # Default 2% risk
        min_size_pct: float = 0.01,           # Minimum 1%
        volatility_adjustment: bool = True     # Adjust for volatility
    ):
        self.max_position_pct = max_position_pct
        self.kelly_fraction = kelly_fraction
        self.min_trades_for_kelly = min_trades_for_kelly
        self.default_size_pct = default_size_pct
        self.min_size_pct = min_size_pct
        self.volatility_adjustment = volatility_adjustment
        
        self.trade_history: List[dict] = []
        self.avg_atr_pct: float = 0.02  # Default 2% ATR
        
    def add_trade(self, pnl_pct: float, won: bool):
        """
        Record a completed trade
        
        Args:
            pnl_pct: Profit/loss as percentage (e.g., 2.5 for +2.5%)
            won: True if trade was profitable
        """
        self.trade_history.append({
            'pnl_pct': pnl_pct,
            'won': won
        })
    
    def load_trades_from_results(self, results_dir: str = 'results') -> int:
        """
        Load historical trades from backtest results
        
        Returns:
            Number of trades loaded
        """
        results_path = Path(results_dir)
        if not results_path.exists():
            return 0
        
        trades_loaded = 0
        
        # Load from JSON backtest results
        for json_file in results_path.glob('backtest_*.json'):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    
                if 'trades' in data:
                    for trade in data['trades']:
                        pnl_pct = trade.get('pnl_pct', 0)
                        won = pnl_pct > 0
                        self.add_trade(pnl_pct, won)
                        trades_loaded += 1
            except Exception as e:
                continue
        
        return trades_loaded
    
    def get_stats(self) -> Optional[TradeStats]:
        """Calculate trading statistics from history"""
        if len(self.trade_history) < 5:
            return None
        
        wins = [t for t in self.trade_history if t['won']]
        losses = [t for t in self.trade_history if not t['won']]
        
        if not wins or not losses:
            return None
        
        avg_win = np.mean([t['pnl_pct'] for t in wins])
        avg_loss = abs(np.mean([t['pnl_pct'] for t in losses]))
        
        total_wins = sum(t['pnl_pct'] for t in wins)
        total_losses = abs(sum(t['pnl_pct'] for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        return TradeStats(
            win_rate=len(wins) / len(self.trade_history),
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            total_trades=len(self.trade_history),
            profit_factor=profit_factor
        )
    
    def kelly_criterion(self, stats: TradeStats) -> float:
        """
        Calculate Kelly Criterion optimal bet size
        
        Formula: f* = W - (1-W)/R
        """
        if stats.avg_loss_pct == 0:
            return self.default_size_pct
        
        win_loss_ratio = stats.avg_win_pct / stats.avg_loss_pct
        kelly = stats.win_rate - ((1 - stats.win_rate) / win_loss_ratio)
        
        # Apply fractional Kelly (safer - reduces variance)
        kelly *= self.kelly_fraction
        
        # Clamp to valid range
        return max(self.min_size_pct, min(kelly, self.max_position_pct))
    
    def volatility_adjusted_size(
        self,
        base_size: float,
        current_atr_pct: float
    ) -> float:
        """
        Adjust position size based on current volatility
        
        Higher volatility = smaller position
        Lower volatility = larger position (up to 1.5x)
        """
        if not self.volatility_adjustment or current_atr_pct == 0:
            return base_size
        
        # Calculate volatility ratio
        vol_ratio = self.avg_atr_pct / current_atr_pct
        
        # Clamp adjustment (0.5x to 1.5x)
        vol_ratio = max(0.5, min(vol_ratio, 1.5))
        
        adjusted = base_size * vol_ratio
        return max(self.min_size_pct, min(adjusted, self.max_position_pct))
    
    def update_avg_atr(self, atr_pct: float, alpha: float = 0.1):
        """Update rolling average ATR with exponential smoothing"""
        if self.avg_atr_pct == 0:
            self.avg_atr_pct = atr_pct
        else:
            self.avg_atr_pct = alpha * atr_pct + (1 - alpha) * self.avg_atr_pct
    
    def get_position_size(
        self,
        current_atr_pct: Optional[float] = None
    ) -> Tuple[float, str]:
        """
        Get recommended position size as fraction of capital
        
        Args:
            current_atr_pct: Current ATR as % of price (for volatility adjustment)
        
        Returns:
            (size: float, reason: str)
        """
        stats = self.get_stats()
        
        # Not enough data - use conservative default
        if stats is None or stats.total_trades < self.min_trades_for_kelly:
            size = self.default_size_pct
            reason = f"Default size (need {self.min_trades_for_kelly}+ trades for Kelly)"
            
            # Still apply volatility adjustment if available
            if current_atr_pct and self.volatility_adjustment:
                size = self.volatility_adjusted_size(size, current_atr_pct)
                reason += f" + vol adj"
            
            return size, reason
        
        # Calculate Kelly size
        kelly_size = self.kelly_criterion(stats)
        
        # Check if Kelly suggests no edge
        if kelly_size <= 0:
            return self.min_size_pct, f"Kelly negative (WR={stats.win_rate:.1%}) - using minimum"
        
        # Apply volatility adjustment
        if current_atr_pct and self.volatility_adjustment:
            final_size = self.volatility_adjusted_size(kelly_size, current_atr_pct)
            reason = (f"Kelly={kelly_size:.1%} × vol_adj → {final_size:.1%} "
                     f"(WR={stats.win_rate:.1%}, PF={stats.profit_factor:.2f})")
        else:
            final_size = kelly_size
            reason = f"Kelly={final_size:.1%} (WR={stats.win_rate:.1%}, PF={stats.profit_factor:.2f})"
        
        return final_size, reason
    
    def get_dollar_size(
        self,
        capital: float,
        current_atr_pct: Optional[float] = None
    ) -> Tuple[float, str]:
        """
        Get position size in dollars
        
        Returns:
            (dollar_amount: float, reason: str)
        """
        pct_size, reason = self.get_position_size(current_atr_pct)
        dollar_size = capital * pct_size
        return dollar_size, reason
    
    def print_status(self):
        """Print current position sizing status"""
        stats = self.get_stats()
        
        print("\n" + "="*50)
        print("📊 POSITION SIZING STATUS (Kelly Criterion)")
        print("="*50)
        
        if stats:
            print(f"Total Trades:     {stats.total_trades}")
            print(f"Win Rate:         {stats.win_rate:.1%}")
            print(f"Avg Win:          {stats.avg_win_pct:+.2f}%")
            print(f"Avg Loss:         {stats.avg_loss_pct:-.2f}%")
            print(f"Profit Factor:    {stats.profit_factor:.2f}")
            
            kelly = self.kelly_criterion(stats)
            print(f"\nKelly Optimal:    {kelly:.1%}")
            print(f"Half-Kelly:       {kelly * self.kelly_fraction:.1%}")
        else:
            print(f"Trades recorded:  {len(self.trade_history)}")
            print(f"Need {self.min_trades_for_kelly}+ trades for Kelly calculation")
        
        size, reason = self.get_position_size()
        print(f"\nRecommended Size: {size:.1%}")
        print(f"Reason: {reason}")
        print("="*50 + "\n")


# Global instance for easy access
_position_sizer = None

def get_position_sizer() -> PositionSizer:
    """Get or create global position sizer instance"""
    global _position_sizer
    if _position_sizer is None:
        _position_sizer = PositionSizer()
    return _position_sizer


if __name__ == "__main__":
    # Example usage
    sizer = PositionSizer(
        max_position_pct=0.25,
        kelly_fraction=0.5,
        min_trades_for_kelly=20
    )
    
    # Simulate historical trades (45% win rate, 2:1 R:R)
    import random
    random.seed(42)
    
    for _ in range(50):
        won = random.random() < 0.45
        if won:
            pnl = random.uniform(1.5, 3.5)  # Win 1.5-3.5%
        else:
            pnl = random.uniform(-1.5, -0.8)  # Lose 0.8-1.5%
        sizer.add_trade(pnl, won)
    
    # Print status
    sizer.print_status()
    
    # Get size for $10,000 account
    dollar_size, reason = sizer.get_dollar_size(10000, current_atr_pct=0.025)
    print(f"For $10,000 account: ${dollar_size:,.2f}")
    print(f"Reason: {reason}")
