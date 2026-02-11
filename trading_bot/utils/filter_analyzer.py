"""
Risk Filter Analyzer
====================
Tracks and analyzes which filters are rejecting trades and why.
Provides detailed statistics and recommendations for threshold tuning.

Features:
- Track rejection reasons per filter
- Calculate rejection statistics
- Identify which filter blocks the most trades
- Suggest minimal threshold adjustments
- Generate detailed reports
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime
import json


@dataclass
class RejectionEvent:
    """Record of a single trade rejection"""
    timestamp: datetime
    symbol: str
    direction: str  # LONG or SHORT
    filter_name: str
    rejection_reason: str
    position_size_intended: float = 0.02
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'direction': self.direction,
            'filter': self.filter_name,
            'reason': self.rejection_reason,
            'position_size': self.position_size_intended
        }


class FilterAnalyzer:
    """
    Analyzes trade rejections across all risk management filters.
    
    Usage:
        analyzer = FilterAnalyzer()
        
        # After each trade rejection
        analyzer.log_rejection(
            symbol='BTC/USDT',
            direction='LONG',
            filter_name='MTF',
            reason='Bearish on higher timeframes'
        )
        
        # Get statistics
        stats = analyzer.get_statistics()
        analyzer.print_report()
    """
    
    def __init__(self):
        """Initialize filter analyzer"""
        self.rejections: List[RejectionEvent] = []
        self.filter_stats: Dict[str, Dict] = defaultdict(lambda: {
            'count': 0,
            'reasons': defaultdict(int),
            'symbols': defaultdict(int),
            'directions': {'LONG': 0, 'SHORT': 0}
        })
    
    def log_rejection(
        self,
        symbol: str,
        direction: str,
        filter_name: str,
        rejection_reason: str,
        position_size: float = 0.02
    ):
        """
        Log a trade rejection event
        
        Args:
            symbol: Trading pair
            direction: LONG or SHORT
            filter_name: Which filter rejected (Circuit, MTF, Funding, OrderFlow)
            rejection_reason: Detailed reason from filter
            position_size: Intended position size before rejection
        """
        event = RejectionEvent(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            filter_name=filter_name,
            rejection_reason=rejection_reason,
            position_size_intended=position_size
        )
        
        self.rejections.append(event)
        
        # Update statistics
        stats = self.filter_stats[filter_name]
        stats['count'] += 1
        stats['reasons'][rejection_reason] += 1
        stats['symbols'][symbol] += 1
        stats['directions'][direction] += 1
    
    def get_statistics(self) -> Dict:
        """Get comprehensive rejection statistics"""
        total_rejections = len(self.rejections)
        
        if total_rejections == 0:
            return {
                'total_rejections': 0,
                'filters': {}
            }
        
        # Calculate per-filter statistics
        filter_breakdown = {}
        for filter_name, stats in self.filter_stats.items():
            pct = (stats['count'] / total_rejections) * 100
            
            # Find most common reason
            top_reason = 'N/A'
            top_reason_count = 0
            if stats['reasons']:
                top_reason, top_reason_count = max(
                    stats['reasons'].items(),
                    key=lambda x: x[1]
                )
            
            filter_breakdown[filter_name] = {
                'count': stats['count'],
                'percentage': pct,
                'top_reason': top_reason,
                'top_reason_count': top_reason_count,
                'unique_reasons': len(stats['reasons']),
                'symbols_affected': dict(stats['symbols']),
                'long_rejections': stats['directions']['LONG'],
                'short_rejections': stats['directions']['SHORT'],
                'all_reasons': dict(stats['reasons'])
            }
        
        # Sort by rejection count
        sorted_filters = sorted(
            filter_breakdown.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )
        
        return {
            'total_rejections': total_rejections,
            'total_unique_symbols': len(set(r.symbol for r in self.rejections)),
            'rejection_rate': (total_rejections / max(1, total_rejections)) * 100,  # Will calculate from outside
            'filters_ranked': [name for name, _ in sorted_filters],
            'filters': dict(sorted_filters)
        }
    
    def get_blocklist_filter(self) -> Tuple[str, int, float]:
        """
        Get the filter that blocks the most trades
        
        Returns:
            (filter_name, rejection_count, percentage)
        """
        if not self.filter_stats:
            return 'None', 0, 0.0
        
        max_filter = max(
            self.filter_stats.items(),
            key=lambda x: x[1]['count']
        )
        
        total = sum(f['count'] for f in self.filter_stats.values())
        pct = (max_filter[1]['count'] / max(1, total)) * 100
        
        return max_filter[0], max_filter[1]['count'], pct
    
    def get_filter_impact(self, filter_name: str) -> Dict:
        """Get detailed impact analysis for a specific filter"""
        if filter_name not in self.filter_stats:
            return {'error': f'Filter {filter_name} has no rejections'}
        
        stats = self.filter_stats[filter_name]
        
        return {
            'filter': filter_name,
            'total_rejections': stats['count'],
            'rejection_reasons': dict(stats['reasons']),
            'symbols_blocked': dict(stats['symbols']),
            'long_vs_short': {
                'long': stats['directions']['LONG'],
                'short': stats['directions']['SHORT']
            },
            'most_common_reason': max(
                stats['reasons'].items(),
                key=lambda x: x[1],
                default=('N/A', 0)
            )[0]
        }
    
    def print_report(self):
        """Print detailed rejection analysis report"""
        stats = self.get_statistics()
        
        if stats['total_rejections'] == 0:
            print("\n✅ No rejections - all trades approved!")
            return
        
        print("\n" + "="*70)
        print("📊 FILTER REJECTION ANALYSIS")
        print("="*70)
        
        print(f"\nTotal Rejections: {stats['total_rejections']}")
        print(f"Unique Symbols: {stats['total_unique_symbols']}")
        
        print("\n" + "-"*70)
        print("Filter Ranking (by rejection count)")
        print("-"*70)
        
        for i, (filter_name, filter_stats) in enumerate(stats['filters'].items(), 1):
            print(f"\n{i}. {filter_name.upper()}")
            print(f"   Rejections: {filter_stats['count']} ({filter_stats['percentage']:.1f}%)")
            print(f"   Top Reason: {filter_stats['top_reason']}")
            print(f"   Top Reason Count: {filter_stats['top_reason_count']}")
            print(f"   Unique Reasons: {filter_stats['unique_reasons']}")
            print(f"   LONG rejections: {filter_stats['long_rejections']}")
            print(f"   SHORT rejections: {filter_stats['short_rejections']}")
            
            # Show top 3 symbols
            if filter_stats['symbols_affected']:
                top_symbols = sorted(
                    filter_stats['symbols_affected'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                print(f"   Most affected symbols:")
                for symbol, count in top_symbols:
                    print(f"      - {symbol}: {count}")
        
        print("\n" + "="*70)
    
    def get_recommendations(self) -> List[Dict]:
        """
        Suggest minimal threshold changes to improve performance
        
        Returns:
            List of recommendations with reasoning
        """
        recommendations = []
        stats = self.get_statistics()
        
        if stats['total_rejections'] == 0:
            return [{'note': 'No rejections detected - no changes needed'}]
        
        # Analyze each filter
        for filter_name, filter_stats in stats['filters'].items():
            pct = filter_stats['percentage']
            
            # MTF Filter Recommendations
            if filter_name == 'MTF' and pct > 40:
                recommendations.append({
                    'filter': 'Multi-Timeframe',
                    'issue': f'Blocking {pct:.1f}% of trades',
                    'current_setting': 'All higher TFs must confirm',
                    'recommendation': 'Reduce require_all_mtf from True to False',
                    'impact': 'Allow trades if any higher TF aligns (instead of all)',
                    'risk_change': 'Minimal - still requires some confirmation',
                    'estimated_increase': '15-25% more trades allowed'
                })
            
            # Funding Filter Recommendations
            elif filter_name == 'Funding' and pct > 30:
                recommendations.append({
                    'filter': 'Funding Rate',
                    'issue': f'Blocking {pct:.1f}% of trades',
                    'current_setting': 'strict=False (EXTREME threshold only)',
                    'recommendation': 'Disable strict mode completely',
                    'impact': 'Only filter extreme outliers (>0.05% funding)',
                    'risk_change': 'Minimal - only extreme edges are problematic',
                    'estimated_increase': '20-30% more trades allowed'
                })
            
            # Circuit Breaker Recommendations
            elif filter_name == 'Circuit' and pct > 20:
                most_common = filter_stats['top_reason']
                
                if 'consecutive' in most_common.lower():
                    recommendations.append({
                        'filter': 'Circuit Breaker',
                        'issue': f'Consecutive losses triggering {pct:.1f}% of blocks',
                        'current_setting': 'max_consecutive_losses = 5',
                        'recommendation': 'Increase to 6-7',
                        'impact': 'Allow one more loss streak before pausing',
                        'risk_change': 'Very low - rare edge case',
                        'estimated_increase': '5-10% more trades during drawdowns'
                    })
                
                elif 'daily' in most_common.lower():
                    recommendations.append({
                        'filter': 'Circuit Breaker',
                        'issue': f'Daily loss limit triggering {pct:.1f}% of blocks',
                        'current_setting': 'max_daily_loss_pct = 5%',
                        'recommendation': 'Increase to 6-7%',
                        'impact': 'Allow slightly larger daily losses',
                        'risk_change': 'Low - still protective',
                        'estimated_increase': '10-15% more trades on volatile days'
                    })
        
        return recommendations
    
    def export_rejections(self, filepath: str):
        """Export all rejection events to JSON"""
        data = {
            'export_time': datetime.now().isoformat(),
            'total_rejections': len(self.rejections),
            'rejections': [r.to_dict() for r in self.rejections],
            'statistics': self.get_statistics()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"\n✅ Exported {len(self.rejections)} rejection events to {filepath}")
    
    def clear(self):
        """Clear all recorded rejections"""
        self.rejections.clear()
        self.filter_stats.clear()


def print_config_thresholds():
    """Print all current risk configuration thresholds"""
    from .circuit_breaker import CircuitBreakerConfig
    from .risk_manager import RiskManager
    from .funding_rate import FundingRateFilter
    
    print("\n" + "="*70)
    print("⚙️ RISK MANAGER CONFIGURATION THRESHOLDS")
    print("="*70)
    
    # Circuit Breaker
    cb_config = CircuitBreakerConfig()
    print("\n🔌 CIRCUIT BREAKER")
    print("-" * 70)
    print(f"   Max Drawdown:           {cb_config.max_drawdown_pct:.1%}")
    print(f"   Warning Drawdown:       {cb_config.warning_drawdown_pct:.1%}")
    print(f"   Max Daily Loss:         {cb_config.max_daily_loss_pct:.1%}")
    print(f"   Max Consecutive Losses: {cb_config.max_consecutive_losses}")
    print(f"   Max Daily Trades:       {cb_config.max_daily_trades}")
    print(f"   Cooldown Minutes:       {cb_config.cooldown_minutes}")
    
    # Funding Rate
    print("\n💰 FUNDING RATE FILTER")
    print("-" * 70)
    print(f"   Extreme Threshold:      {FundingRateFilter.EXTREME_THRESHOLD:.5f} (0.05%)")
    print(f"   High Threshold:         {FundingRateFilter.HIGH_THRESHOLD:.5f} (0.03%)")
    print(f"   Normal Range:           {FundingRateFilter.NORMAL_RANGE:.5f} (0.01%)")
    print(f"   Strict Mode:            Uses HIGH threshold")
    print(f"   Normal Mode:            Uses EXTREME threshold")
    
    # Multi-Timeframe
    print("\n📈 MULTI-TIMEFRAME CONFIRMATION")
    print("-" * 70)
    print(f"   Fast EMA Period:        50 bars")
    print(f"   Slow EMA Period:        200 bars")
    print(f"   RSI Period:             14 bars")
    print(f"   ATR Period:             14 bars")
    print(f"   Confirmation Rule:      require_all_mtf=True (all higher TFs must align)")
    print(f"   Weak Alignment Warning: mtf_score < 0.3")
    
    # Position Sizing
    print("\n📊 POSITION SIZING (Kelly Criterion)")
    print("-" * 70)
    print(f"   Default Position Size:  2% of capital")
    print(f"   Kelly Fraction:         0.25 (conservative)")
    print(f"   Max Position Size:      5% of capital")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    # Example usage
    analyzer = FilterAnalyzer()
    
    # Simulate some rejections
    analyzer.log_rejection('BTC/USDT', 'LONG', 'MTF', 'Bearish on higher timeframes')
    analyzer.log_rejection('BTC/USDT', 'SHORT', 'Funding', 'Shorts overleveraged (funding -0.0004%)')
    analyzer.log_rejection('ETH/USDT', 'LONG', 'MTF', 'Bearish on higher timeframes')
    analyzer.log_rejection('BTC/USDT', 'SHORT', 'Circuit', 'paused')
    
    # Print report
    analyzer.print_report()
    
    # Get blocklist filter
    blocker, count, pct = analyzer.get_blocklist_filter()
    print(f"\n🚫 Most Blocking Filter: {blocker} ({count} rejections, {pct:.1f}%)")
    
    # Get recommendations
    print("\n📋 RECOMMENDATIONS:")
    for rec in analyzer.get_recommendations():
        if 'note' in rec:
            print(f"   {rec['note']}")
        else:
            print(f"\n   Filter: {rec['filter']}")
            print(f"   Issue: {rec['issue']}")
            print(f"   Recommendation: {rec['recommendation']}")
            print(f"   Impact: {rec['impact']}")
    
    # Print config thresholds
    print_config_thresholds()
