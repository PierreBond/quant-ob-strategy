# 📚 Filter Analysis Documentation Index

Quick navigation for all risk filter analysis resources.

---

## 📍 Start Here

**Read this first (5 minutes):**
- [README_FILTER_ANALYSIS.md](README_FILTER_ANALYSIS.md) - Complete summary of what was delivered

---

## 📖 Main Documentation

| Document | Time | Purpose | Best For |
|----------|------|---------|----------|
| **FILTER_ANALYZER_QUICKSTART.md** | 5 min | Quick reference, running analysis, reading output | Getting started, understanding basics |
| **RISK_FILTER_ANALYSIS.md** | 20 min | Deep dive into each filter, how they work | Understanding filter logic |
| **THRESHOLD_ADJUSTMENT_GUIDE.md** | 15 min | Step-by-step instructions for making changes | Actually making modifications |
| **FILTER_ANALYSIS_EXAMPLES.md** | 15 min | Real example outputs, decision trees | Seeing what output looks like |
| **IMPLEMENTATION_COMPLETE.md** | 10 min | Technical summary of what was implemented | Understanding code changes |

---

## 🚀 Common Workflows

### "I want to understand my filter rate"
1. Read: [FILTER_ANALYZER_QUICKSTART.md](FILTER_ANALYZER_QUICKSTART.md) 
2. Run: `python trading_bot/main.py --mode backtest --days 90 --strategy orderblock_premium_v2 --real-data --risk-mgmt`
3. Check output section: `📊 FILTER REJECTION BREAKDOWN`

### "I want to improve my trade approval rate"
1. Read: [RISK_FILTER_ANALYSIS.md](RISK_FILTER_ANALYSIS.md) (section: "MINIMAL THRESHOLD ADJUSTMENTS")
2. Follow: [THRESHOLD_ADJUSTMENT_GUIDE.md](THRESHOLD_ADJUSTMENT_GUIDE.md) (section: "IMPLEMENTATION STEPS")
3. Test: Run backtest and verify improvements

### "I don't understand the output"
1. Check: [FILTER_ANALYSIS_EXAMPLES.md](FILTER_ANALYSIS_EXAMPLES.md) (section: "Example 1: High Filter Rate")
2. Compare with your own output
3. Use decision tree in same document

### "I want to make just one change"
1. Start with: `require_all_mtf = False` (lowest risk, biggest impact)
2. Location: [THRESHOLD_ADJUSTMENT_GUIDE.md](THRESHOLD_ADJUSTMENT_GUIDE.md#1️⃣-multi-timeframe-confirmation)
3. Follow exact steps in that section

### "I want to understand why my trade was rejected"
1. Read: [RISK_FILTER_ANALYSIS.md](RISK_FILTER_ANALYSIS.md) (relevant filter section)
2. Example: If "MTF rejection: 50%" → [RISK_FILTER_ANALYSIS.md#2-multi-timeframe-mtf-confirmation](RISK_FILTER_ANALYSIS.md#2-multi-timeframe-mtf-confirmation)
3. Cross-reference rejection reasons in your JSON output

---

## 🔍 Quick Dictionary

### Filter Names & What They Do

**Circuit Breaker** 
- File: [RISK_FILTER_ANALYSIS.md#1-circuit-breaker](RISK_FILTER_ANALYSIS.md#1-circuit-breaker)
- Purpose: Hard stop when risk limits exceeded
- Key Thresholds: 15% drawdown, 5% daily loss, 5 consecutive losses

**Multi-Timeframe (MTF)**
- File: [RISK_FILTER_ANALYSIS.md#2-multi-timeframe-mtf-confirmation](RISK_FILTER_ANALYSIS.md#2-multi-timeframe-mtf-confirmation)
- Purpose: Confirm entry across multiple timeframes
- Key Threshold: require_all_mtf (True = all must align, False = flexible)

**Funding Rate**
- File: [RISK_FILTER_ANALYSIS.md#3-funding-rate-filter](RISK_FILTER_ANALYSIS.md#3-funding-rate-filter)
- Purpose: Avoid overleveraged markets
- Key Threshold: 0.05% EXTREME, 0.03% HIGH

**Position Sizing**
- File: [RISK_FILTER_ANALYSIS.md#4-position-sizing-kelly-criterion](RISK_FILTER_ANALYSIS.md#4-position-sizing-kelly-criterion)
- Purpose: Size positions based on expectancy
- Key Threshold: 2% default, 5% max

### Key Concepts

**Filter Rate**
- Definition: % of valid signals rejected by filters
- Location: Output section "PHASE 1 RISK MANAGEMENT"
- Ideal Range: 30-50%
- Warning: > 70% means too restrictive

**Rejection Reason**
- Definition: Why a specific trade was rejected
- Format: "[Filter Name] [specific reason]"
- Example: "MTF rejection: 50%" or "Funding 0.065% - longs overleveraged"
- Found: [FILTER_ANALYSIS_EXAMPLES.md#section-2-analyzing-specific-rejection-patterns](FILTER_ANALYSIS_EXAMPLES.md#-example-3-analyzing-specific-rejection-patterns)

**Blocklist Filter**
- Definition: Which filter rejects the most trades
- Usually: Multi-Timeframe confirmation (35-40%)
- Location: "Most Blocking Filter: [name] (xyz%)"
- Action: This is where to optimize first

---

## 🛠️ Implementation Steps (Quick Reference)

### Step 1: Run Analysis
```bash
python trading_bot/main.py --mode backtest --days 90 \
  --strategy orderblock_premium_v2 \
  --real-data \
  --risk-mgmt
```
**Reference:** [FILTER_ANALYZER_QUICKSTART.md#running-your-first-analysis](FILTER_ANALYZER_QUICKSTART.md#running-your-first-analysis)

### Step 2: Read Breakdown
Look for:
```
Most Blocking Filter: Multi-Timeframe (X.X%)
Top Rejection Reasons: [list]
```
**Reference:** [FILTER_ANALYSIS_EXAMPLES.md#how-to-read-this-example](FILTER_ANALYSIS_EXAMPLES.md#how-to-read-this-example)

### Step 3: Check Recommendations
```
💡 RECOMMENDATIONS TO RESTORE PERFORMANCE
────────────────────────────────────────────────
1. MULTI-TIMEFRAME
   ✅ Suggestion: Relax to require_all_mtf=False
```
**Reference:** [RISK_FILTER_ANALYSIS.md#minimal-recommended-changes-to-restore-performance](RISK_FILTER_ANALYSIS.md#minimal-recommended-changes-to-restore-performance)

### Step 4: Make Change
Edit `main.py` line ~280:
```python
require_all_mtf=False,  # was True
```
**Reference:** [THRESHOLD_ADJUSTMENT_GUIDE.md#1️⃣-multi-timeframe-confirmation](THRESHOLD_ADJUSTMENT_GUIDE.md#1️⃣-multi-timeframe-confirmation)

### Step 5: Test
Run backtest again and compare:
- Filter rate (should decrease)
- Trades allowed (should increase)
- Win rate (should stay stable)
**Reference:** [FILTER_ANALYSIS_EXAMPLES.md#example-2-after-making-changes](FILTER_ANALYSIS_EXAMPLES.md#example-2-after-making-changes)

---

## 📊 File Types

### Generated After Each Backtest
- `trades_{timestamp}.csv` - All trade details
- `backtest_{timestamp}.json` - Performance metrics
- **`filter_analysis_{timestamp}.json`** ← NEW! Rejection details
- `charts/backtest_{timestamp}.png` - Equity curve

**To analyze filter_analysis JSON:**
[FILTER_ANALYSIS_EXAMPLES.md#advanced-analyzing-the-json-output](FILTER_ANALYSIS_EXAMPLES.md#advanced-analyzing-the-json-output)

---

## ⚠️ Important Warnings

### Don't Change These
[RISK_FILTER_ANALYSIS.md#what-not-to-change-risk-protections](RISK_FILTER_ANALYSIS.md#what-not-to-change-risk-protections)
- max_drawdown_pct = 15%
- warning_drawdown_pct = 10%
- Kelly fraction = 0.25

### Watch for These Red Flags
[FILTER_ANALYSIS_EXAMPLES.md#🚨-red-flags-problems-to-watch](FILTER_ANALYSIS_EXAMPLES.md#🚨-red-flags-problems-to-watch)
- Win rate drops below 45%
- Max drawdown exceeds 15%
- Profit factor < 1.0

---

## 🎓 Learning Path

**Complete Beginner** (no filter knowledge):
1. Read: [README_FILTER_ANALYSIS.md](README_FILTER_ANALYSIS.md)
2. Read: [FILTER_ANALYZER_QUICKSTART.md](FILTER_ANALYZER_QUICKSTART.md)
3. Run: Backtest with `--risk-mgmt`
4. Compare your output to: [FILTER_ANALYSIS_EXAMPLES.md](FILTER_ANALYSIS_EXAMPLES.md)

**Intermediate** (want to understand deeply):
1. Read: [RISK_FILTER_ANALYSIS.md](RISK_FILTER_ANALYSIS.md) (all sections)
2. Understand: Each filter's logic and thresholds
3. Review: [FILTER_ANALYSIS_EXAMPLES.md](FILTER_ANALYSIS_EXAMPLES.md) (decision trees)

**Advanced** (want to optimize):
1. Understand: All four filters
2. Follow: [THRESHOLD_ADJUSTMENT_GUIDE.md](THRESHOLD_ADJUSTMENT_GUIDE.md) (implementation)
3. Systematically test changes
4. Document improvements

---

## 🤔 FAQ Navigation

**Q: Which filter is blocking my trades?**
A: Check output "Most Blocking Filter: XXX" 
See: [FILTER_ANALYSIS_EXAMPLES.md#how-to-read-this-example](FILTER_ANALYSIS_EXAMPLES.md#how-to-read-this-example)

**Q: Is 70% filter rate normal?**
A: No, too high. Means very restrictive. 
See: [RISK_FILTER_ANALYSIS.md#which-filter-blocks-the-most-trades](RISK_FILTER_ANALYSIS.md#which-filter-blocks-the-most-trades)

**Q: What should I change first?**
A: Always `require_all_mtf=False`
See: [RISK_FILTER_ANALYSIS.md#option-1-reduce-mtf-strictness-recommended](RISK_FILTER_ANALYSIS.md#option-1-reduce-mtf-strictness-recommended)

**Q: Is it safe to make changes?**
A: Yes if you change one at a time and test
See: [THRESHOLD_ADJUSTMENT_GUIDE.md#🧪-testing-your-changes](THRESHOLD_ADJUSTMENT_GUIDE.md#🧪-testing-your-changes)

**Q: Can I revert a change?**
A: Yes, instantly. Just change the value back
See: [THRESHOLD_ADJUSTMENT_GUIDE.md#reverting-changes](THRESHOLD_ADJUSTMENT_GUIDE.md#reverting-changes)

---

## 🔗 Code File References

### New Files Created
- `trading_bot/utils/filter_analyzer.py` - FilterAnalyzer class (391 lines)
- `RISK_FILTER_ANALYSIS.md` - Full technical documentation
- `FILTER_ANALYZER_QUICKSTART.md` - Quick start guide
- `THRESHOLD_ADJUSTMENT_GUIDE.md` - Implementation guide
- `FILTER_ANALYSIS_EXAMPLES.md` - Example outputs
- `IMPLEMENTATION_COMPLETE.md` - Change summary
- `README_FILTER_ANALYSIS.md` - Delivery summary
- `INDEX.md` - This file

### Modified Files
- `trading_bot/backtest/engine.py` - Added FilterAnalyzer logging
- `trading_bot/main.py` - Call filter analysis after backtest
- `trading_bot/utils/__init__.py` - Export filter analyzer classes

---

## 📞 Getting Help

1. **Quick answer:** Check [FILTER_ANALYZER_QUICKSTART.md](FILTER_ANALYZER_QUICKSTART.md)
2. **Understanding:** Check [RISK_FILTER_ANALYSIS.md](RISK_FILTER_ANALYSIS.md)
3. **Implementation:** Check [THRESHOLD_ADJUSTMENT_GUIDE.md](THRESHOLD_ADJUSTMENT_GUIDE.md)
4. **Examples:** Check [FILTER_ANALYSIS_EXAMPLES.md](FILTER_ANALYSIS_EXAMPLES.md)
5. **Everything:** Check [README_FILTER_ANALYSIS.md](README_FILTER_ANALYSIS.md)

---

## ✅ Checklist: Ready to Use

- [x] Backtest engine enhanced with FilterAnalyzer
- [x] Rejection logging implemented
- [x] Filter analysis report prints automatically
- [x] JSON export working
- [x] All documentation written
- [x] Examples provided
- [x] Step-by-step guides created
- [x] This index created

**You're ready to use the filter analysis system!**

Start with: [FILTER_ANALYZER_QUICKSTART.md](FILTER_ANALYZER_QUICKSTART.md)

