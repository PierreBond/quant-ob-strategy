# Quick Start: Using the Filter Analyzer

## What Changed?

We've added detailed logging and analysis of which risk filters are blocking trades. Now, after each backtest, you'll see:

```
📊 FILTER REJECTION BREAKDOWN
────────────────────────────────────────────────

Most Blocking Filter: Multi-Timeframe (47.3%)

Top Rejection Reasons:
   • MTF rejection: 50%: 165 (42.1%)
   • Funding 0.065% - longs overleveraged: 95 (24.2%)
   • Circuit breaker: paused: 73 (18.6%)

📊 Filter Rejection Report
────────────────────────────
1. MULTI-TIMEFRAME
   Rejections: 165 (42.1%)
   Top Reason: 50% of higher TFs confirm
   LONG rejections: 92
   SHORT rejections: 73

2. FUNDING RATE
   Rejections: 95 (24.2%)
   Top Reason: Longs overleveraged
   Most affected: BTC/USDT (95)

3. CIRCUIT BREAKER
   Rejections: 73 (18.6%)
   Top Reason: Consecutive losses (5)
   LONG rejections: 35
   SHORT rejections: 38

💡 RECOMMENDATIONS TO RESTORE PERFORMANCE
────────────────────────────────────────────────

1. MULTI-TIMEFRAME
   Issue: Blocking 42.1% of trades
   Current: All higher TFs must have mtf_score align
   ✅ Suggestion: Relax to require_all_mtf=False
   Impact: Allow trades if any higher TF aligns
   Risk: Very low - still requires some confirmation
   Result: 15-25% more trades allowed
```

---

## New Files Created

### 1. **FilterAnalyzer** (`utils/filter_analyzer.py`)
- Tracks each trade rejection with detailed reasons
- Calculates statistics per filter
- Identifies which filter blocks most trades
- Suggests minimal threshold adjustments

### 2. **Enhanced Logging** (in `backtest/engine.py`)
- Now logs rejection reasons from RiskManager
- Categorizes by filter type
- Exports detailed JSON for analysis

### 3. **Analysis Output** (in `results/`)
- `filter_analysis_{timestamp}.json` - Complete rejection log
- Shows every rejection reason in detail
- Enables deep-dive analysis

---

## Running Your First Analysis

```bash
# Run a backtest with risk management enabled
python trading_bot/main.py --mode backtest --days 90 \
  --strategy orderblock_premium_v2 \
  --real-data \
  --risk-mgmt
```

Watch for this section in the output:
```
────────────────────────────────────────────────
📊 FILTER REJECTION BREAKDOWN
────────────────────────────────────────────────
```

---

## Reading the Output

### **Section 1: Most Blocking Filter**
```
Most Blocking Filter: Multi-Timeframe (47.3%)
```
This tells you which filter is rejecting the most trades. Start here for optimization.

### **Section 2: Top Rejection Reasons**
```
Top Rejection Reasons:
   • MTF rejection: 50%: 165 (42.1%)
   • Funding 0.065% - longs overleveraged: 95 (24.2%)
```
Shows the specific reasons why trades were rejected.

### **Section 3: Recommendations**
```
1. MULTI-TIMEFRAME
   Issue: Blocking 42.1% of trades
   ✅ Suggestion: Relax to require_all_mtf=False
   Result: 15-25% more trades allowed
```
Ready-to-implement recommendations with expected impact.

---

## Key Metrics to Watch

| Metric | Interpretation |
|--------|-----------------|
| **Filter Rate** | % of signals rejected (higher = stricter) |
| **Most Blocking Filter** | Start optimization here |
| **Top Reason %** | How much of rejections are due to each reason |
| **Long vs Short** | Whether one direction is more affected |

---

## Configuration thresholds at a glance:

```
CIRCUIT BREAKER
   Max Drawdown:           15.0%    (STOP)
   Max Daily Loss:          5.0%    (PAUSE)
   Max Consecutive Losses:  5        (PAUSE)
   Max Daily Trades:       20        (PAUSE)
   Cooldown:            60 min

MULTI-TIMEFRAME
   require_all_mtf:     True (ALL higher TFs must align)
   Fast EMA:             50 bars
   Slow EMA:            200 bars

FUNDING RATE
   Extreme Threshold:    0.05%  (rarely blocks)
   High Threshold:       0.03%  (with strict mode)
   Current Mode:         Normal

POSITION SIZING
   Default:               2.0%
   Kelly Fraction:        0.25
   Max Size:              5.0%
```

---

## Making a Change

Example: Relax MTF confirmation

```python
# In main.py or your config:
risk_manager = RiskManager(
    capital=initial_capital,
    exchange_id=exchange,
    use_mtf=True,
    use_funding=use_funding,
    use_circuit_breaker=use_circuit_breaker,
    use_kelly=use_kelly,
    require_all_mtf=False,  # ← CHANGE THIS (was True)
)
```

Then run backtest again and compare:
- Does filter rate decrease? ✓
- Does win rate stay stable or improve? ✓
- Is drawdown still controlled? ✓

---

## Interpreting Results After Change

**Before:**
```
Signals Evaluated: 500
Trades Allowed:    150 (30%)
Filter Rate:       70%
Win Rate:          60%
Return:            +1.2%
```

**After (with require_all_mtf=False):**
```
Signals Evaluated: 500
Trades Allowed:    180 (+30😊 20)   ← More trades!
Filter Rate:       64% (-6%)        ← Less filtering
Win Rate:          62% (+2%)        ← Still profitable!
Return:            +2.1% (+0.9%)    ← Better results!
```

→ This change was successful! Every metric improved.

---

## Troubleshooting

**Q: Why do I see "No rejections detected"?**
A: Either:
1. Risk management is disabled (`--risk-mgmt` not used)
2. All signals were approved (rare)
3. The analyzer isn't initialized (check logs)

**Q: Which change should I make first?**
A: Always start with **Option 1: require_all_mtf=False**
- Lowest risk
- Biggest impact (can unlock 20-25% more trades)
- Easy to revert if needed

**Q: Can I make multiple changes at once?**
A: Not recommended. Change one, test, measure, then try the next.

**Q: What if my filter rate is already low (< 20%)?**
A: You have a healthy configuration! Only fine-tune if performance is insufficient.

---

## Advanced: Analyzing the JSON Output

After backtest, check `results/filter_analysis_{timestamp}.json`:

```json
{
  "total_rejections": 350,
  "total_unique_symbols": 3,
  "filters_ranked": ["MTF", "Funding", "Circuit"],
  "filters": {
    "Multi-Timeframe": {
      "count": 165,
      "percentage": 47.1,
      "top_reason": "MTF rejection: 50%",
      "unique_reasons": 4,
      "long_rejections": 92,
      "short_rejections": 73
    }
  }
}
```

This lets you:
- Export to spreadsheet for trend analysis
- Monitor filter performance over time
- Debug specific rejection scenarios

---

## Summary

| Step | Action |
|------|--------|
| 1 | Run backtest with `--risk-mgmt` |
| 2 | Read filter rejection breakdown |
| 3 | Identify most blocking filter |
| 4 | Try recommended change |
| 5 | Compare results |
| 6 | If improved, keep change; else revert |
| 7 | Try next recommendation |

That's it! Simple and methodical.

