# Filter Analysis Example Output & Interpretation Guide

This document shows what you'll see after running a backtest with `--risk-mgmt` enabled.

---

## 📊 Example 1: High Filter Rate (Too Restrictive)

### Actual Terminal Output
```
Testing BTC/USDT with OrderBlock Premium V2 Strategy...
Fetching 90 days of historical data...

Backtest Results
══════════════════════════════════════════════════════════════════════════════
📊 PERFORMANCE METRICS
──────────────────────────────────────────────────────────────────────────────
Strategies Tested            orderblock_premium_v2
Fund Size                    $10,000.00
Analysis Period              90 days

Open Positions               0
Trades Completed             20
Winning Trades              11 (55.0%)
Losing Trades               9 (45.0%)
Win Rate                     55.0%

Gross P&L                    +$1,385.83
Return                       +13.86% (+$0.14 per trade avg)
Average Win                  +2.42%
Average Loss                 -1.74%
Best Trade                   +6.48%
Worst Trade                  -3.44%
Profit Factor                 1.54

Max Drawdown                 14.3%
Average Trade Duration       102.0 bars
──────────────────────────────────────────────────────────────────────────────

Final Capital                $11,385.83
Initial Capital              $10,000.00

──────────────────────────────────────────────────────────────────────────────
🛡️ PHASE 1 RISK MANAGEMENT
──────────────────────────────────────────────────────────────────────────────
Signals Evaluated            500
Trades Allowed               20
Trades Filtered              480        ← ⚠️ VERY HIGH!
Filter Rate                  96.0%      ← ⚠️ WAY TOO STRICT!

Circuit Breaker State        active

──────────────────────────────────────────────────────────────────────────────
📊 FILTER REJECTION BREAKDOWN
──────────────────────────────────────────────────────────────────────────────

Most Blocking Filter: Multi-Timeframe (285 rejections, 59.4%)

Top Rejection Reasons:
   • MTF rejection: 25%: 215 (44.8%)
   • MTF rejection: 50%: 70 (14.6%)
   • Funding 0.08% - longs overleveraged: 155 (32.3%)
   • Circuit breaker: paused: 50 (10.4%)

══════════════════════════════════════════════════════════════════════════════
📊 DETAILED FILTER ANALYSIS
══════════════════════════════════════════════════════════════════════════════

1. MULTI-TIMEFRAME
   Rejections: 285 (59.4%)
   Top Reason: MTF rejection: 25% (only 1 of 3 higher TFs agree)
   Top Reason Count: 215
   Unique Reasons: 2
   LONG rejections: 160
   SHORT rejections: 125
   Most affected symbols:
      - BTC/USDT: 285

2. FUNDING RATE
   Rejections: 155 (32.3%)
   Top Reason: Longs overleveraged (funding 0.08%)
   Top Reason Count: 155
   Unique Reasons: 1
   LONG rejections: 155
   SHORT rejections: 0
   Most affected symbols:
      - BTC/USDT: 155

3. CIRCUIT BREAKER
   Rejections: 50 (10.4%)
   Top Reason: Paused (consecutive losses)
   Top Reason Count: 50
   Unique Reasons: 1
   LONG rejections: 25
   SHORT rejections: 25
   Most affected symbols:
      - BTC/USDT: 50

══════════════════════════════════════════════════════════════════════════════
💡 RECOMMENDATIONS TO RESTORE PERFORMANCE
══════════════════════════════════════════════════════════════════════════════

1. MULTI-TIMEFRAME
   ❌ Issue: Blocking 59.4% of trades
   Current: require_all_mtf = True (all higher TFs must align)
   ✅ Suggestion: Change to require_all_mtf = False
   Impact: Allow trades if higher TF trend not opposed
   Risk Change: Very Low - still requires alignment, just more flexible
   Estimated Result: 15-25% more trades allowed

2. FUNDING RATE
   ❌ Issue: Blocking 32.3% of trades
   Current: use_funding = True, strict_funding = False (blocks at 0.05%+)
   ✅ Suggestion: Disable funding filter entirely (use_funding = False)
   Impact: Skip funding rate analysis. Only extreme edges dangerous
   Risk Change: Very Low - funding extremes (>0.1%) rare
   Estimated Result: 20-30% more trades allowed

3. CIRCUIT BREAKER
   ❌ Issue: Blocking 10.4% of trades
   Current: max_consecutive_losses = 5
   ✅ Suggestion: Increase to max_consecutive_losses = 6
   Impact: Allow one more consecutive loss before pausing
   Risk Change: Low - rare scenario, already protected by other filters
   Estimated Result: 5-10% more trades during drawdowns

══════════════════════════════════════════════════════════════════════════════

✓ Results saved to results/
  - trades_20260211_160011.csv
  - backtest_20260211_160011.json
  - filter_analysis_20260211_160011.json
  - charts/backtest_20260211_160011.png
```

### How to Read This Example

1. **Key Metrics:**
   - 500 valid signals generated
   - 20 trades actually executed (4% approval rate)
   - 480 trades rejected by risk filters (96% filter rate)
   - ⚠️ This is **WAY too strict** - you're missing 96% of your opportunities!

2. **Filter Breakdown:**
   - Multi-Timeframe: 59% of rejections (285 trades)
   - Funding Rate: 32% of rejections (155 trades)
   - Circuit Breaker: 10% of rejections (50 trades)
   - **MTF is the clear bottleneck**

3. **Most Common Rejection:**
   - "MTF rejection: 25%" = Only 1 out of 3 higher timeframes align
   - Example: You want LONG on 15m, but:
     - 1h: BULLISH ✓
     - 4h: NEUTRAL ✗ (doesn't confirm)
     - 1d: BULLISH ✓
     - Result: 2/3 agree but NOT 3/3 → REJECTED

4. **Recommendations:**
   - Start with Option 1: `require_all_mtf = False`
   - Expected impact: +20% more trades
   - Very low risk (still requires confirmation, just more flexible)

---

## 📊 Example 2: After Making Changes

### Same Backtest After Adjustment

```bash
# What you changed in main.py:
require_all_mtf = False        # Was True
use_funding = False            # Was True
max_consecutive_losses = 6     # Was 5
```

### New Results

```
══════════════════════════════════════════════════════════════════════════════
🛡️ PHASE 1 RISK MANAGEMENT
──────────────────────────────────────────────────────────────────────────────
Signals Evaluated            500
Trades Allowed               85
Trades Filtered              415
Filter Rate                  83.0%      ← Improved from 96%!

══════════════════════════════════════────────────────────────────────────────
📊 FILTER REJECTION BREAKDOWN
────────────────────────────────────────────────────────────────────────────

Most Blocking Filter: Multi-Timeframe (245 rejections, 59.0%)

Top Rejection Reasons:
   • MTF rejection still strict but different threshold: 180 (43.4%)
   • Circuit breaker: paused: 50 (12.0%)
   (Funding filter removed entirely)

════════════════════════════════════════════════════════════════════════════════
📊 BACKTEST RESULTS COMPARISON
════════════════════════════════════════════════════════════════════════════════

                    BEFORE      AFTER       CHANGE
Signals Evaluated   500         500         (same)
Trades Allowed      20          85          +325% ✓
Trades Filtered     480         415         -65
Filter Rate         96.0%       83.0%       -13% ✓

Trades Completed    20          85          +325% ✓
Win Rate            55.0%       57.1%       +2.1% ✓
Profit Factor       1.54        1.68        +9.1% ✓
Max Drawdown        14.3%       14.8%       -0.5% (acceptable)
Return              +13.86%     +34.2%      +20.34% ✓✓✓

════════════════════════════════════════════════════════════════════════════════
```

### Analysis of Improvement

**What Happened:**
1. ✅ Trades allowed increased by 325% (20 → 85)
2. ✅ Win rate improved 55% → 57% (stayed healthy)
3. ✅ Total return increased 14% → 34% (+20 percentage points!)
4. ✅ Profit factor improved 1.54 → 1.68
5. ⚠️ Drawdown increased slightly 14.3% → 14.8% (still under 15% limit)

**Conclusion:**
- All three changes were successful
- Risk slightly increased but still within circuit breaker limits
- Performance gained far outweighs the risk

---

## 📊 Example 3: Analyzing Specific Rejection Patterns

### When MTF is the Problem

**Scenario:** You see high rejection with `"MTF rejection: 25%"`

This means only 25% of your higher timeframes align with your signal.

**Example:**
```
You want LONG entry on 15m candle

Higher Timeframe Analysis:
  1h:   BEARISH ✗ (trend = -1)
  4h:   NEUTRAL ✓ (trend = 0)
  1d:   NEUTRAL ✓ (trend = 0)
  
Alignment: 1 out of 3 = 33%
Result: REJECTED (need 100% with require_all_mtf=True)

If require_all_mtf=False:
Result: APPROVED (33% is not opposed, just not confirmed)
```

**Fix:** `require_all_mtf = False`

---

### When Funding is the Problem

**Scenario:** You see high rejection with `"Funding 0.065% - longs overleveraged"`

This means the market is crowded with leveraged LONG positions.

**What it means:**
```
Current Funding Rate: +0.065% per 8 hours
Interpretation: Longs are paying shorts 0.065%
Annualized: 0.065% × 3 × 365 = ~71% annual cost
Risk: Market is top-heavy with long positions

This strongly correlates with reversals
So RiskManager blocks LONG entries until funding normalizes
```

**Fix Option A:** `use_funding = False` (ignore funding entirely)  
**Fix Option B:** `strict_funding = True` (be even stricter)

---

### When Circuit Breaker Pauses Trading

**Scenario:** You see `"Circuit breaker: paused"`

This means you hit a temporary limit:

```
Daily Loss Limit Triggered:
- Current daily P&L: -5.2%
- Limit: 5.0%
- Action: 60-minute cooldown before trading resumes

This is intentional! It prevents emotional trading during drawdowns.
```

**Why it exists:**
- Protect against overtrading during bad days
- Prevent revenge trading (dangerous behavior)
- Give time to reassess

**Fixes:**
1. Increase limit: `max_daily_loss_pct = 0.06` (6%)
2. Or just accept and wait (recommended)

---

## 📈 Expected Improvement Path

### Stage 1: Baseline (No Changes)
```
Filter Rate: 70-96% (most signals rejected)
Trades Allowed: 20-30% of signals
Performance: Baseline
Problem: Missing most opportunities
```

### Stage 2: Relax MTF (require_all_mtf=False)
```
Filter Rate: 55-75%
Trades Allowed: 35-50% of signals ← +20% improvement
Performance: +2-4% additional return
Problem: Still missing opportunities
Recommendation: IMPLEMENT - low risk, good reward
```

### Stage 3: Disable Funding (use_funding=False)
```
Filter Rate: 40-55%
Trades Allowed: 50-70% of signals ← +30% improvement
Performance: +3-6% additional return  
Problem: Slightly less risk control on extremes
Recommendation: IMPLEMENT - acceptable tradeoff
```

### Stage 4: Loosen Circuit Breaker (max_consecutive_losses=6)
```
Filter Rate: 35-50%
Trades Allowed: 55-75% of signals ← +35% improvement
Performance: +4-7% additional return
Problem: Allow more losses in a row
Recommendation: TEST - review drawdown behavior
```

---

## 🎯 Decision Tree (What to Change)

```
┌─ Is filter rate > 80%?
│  └─ YES → Check filter breakdown
│     └─ Is MTF blocking > 50%?
│        └─ YES → Change require_all_mtf=False FIRST
│        └─ NO → Is Funding blocking > 30%?
│           └─ YES → Change use_funding=False NEXT
│        
└─ Is filter rate 50-80%?
   └─ Probably acceptable, minor tweaks only
   └─ Check if performance is satisfactory
      └─ YES → Leave it alone
      └─ NO → Make one small change, test again

┌─ After each change:
└─ Run backtest again (90 days minimum)
   └─ Did win rate stay stable? (55%+ is good)
   └─ Did return improve? (>0 is good)
   └─ Did drawdown stay under 15%? (must be YES)
   └─ If all YES → Keep change
   └─ If any NO → Revert and try different change
```

---

## 📋 Checklist: Did the Change Work?

After making a threshold adjustment, verify ALL of these:

```
✓ EXECUTION
  □ Code compiled without errors
  □ Backtest ran to completion
  □ Filter analysis printed
  □ JSON export completed without errors

✓ FILTER METRICS
  □ Filter rate decreased (not increased)
  □ Number of trades allowed increased
  □ No new rejection reasons appeared

✓ PERFORMANCE
  □ Win rate stayed the same or improved
  □ Profit factor stayed the same or improved
  □ Max drawdown stayed under 15% limit
  □ Total return increased

✓ RISK CONTROL
  □ Circuit breaker still working
  □ No new warnings in output
  □ Daily loss limit still respected
  □ Consecutive loss tracking still active

IF ALL CHECKED: Keep the change! ✓
IF ANY UNCHECKED: Revert and try different adjustment
```

---

## 🚨 Red Flags (Problems to Watch)

| Red Flag | What It Means | Action |
|----------|---------------|--------|
| Win rate drops below 45% | More losing trades | Revert change |
| Profit factor < 1.0 | Losing more than winning | Revert change |
| Max drawdown > 15% | Circuit breaker limit breached | Revert change |
| New rejections appear | Filter logic changed | Check code |
| Trades allowed = 0 | Something is broken | Debug and revert |

---

## 💾 Saving Your Analysis

After each backtest, archive your findings:

```
✓ Keep the JSON file: filter_analysis_{timestamp}.json
✓ Save backtest CSV: trades_{timestamp}.csv
✓ Screenshot the output if something notable happened
✓ Create a simple log:
    Date: 2026-02-11
    Strategy: orderblock_premium_v2
    Changes: require_all_mtf=False
    Filter Rate Before: 96% → After: 83%
    Win Rate Before: 55% → After: 57%
    Return Before: +14% → After: +34%
    Status: ✓ SUCCESSFUL, KEEPING CHANGES
```

This lets you track what worked and why.

---

## Summary

The filter analysis gives you everything you need to optimize your trading:

1. **Identifies the problem** - Which filter blocks most trades
2. **Explains the reason** - Why it's rejecting trades
3. **Suggests the fix** - What to change and why
4. **Quantifies the impact** - How much improvement to expect
5. **Assesses the risk** - Whether it's worth the change

Use it systematically, one change at a time, and you'll quickly optimize your setup for maximum performance within acceptable risk limits.

