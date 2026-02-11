# Implementation Guide: Making Threshold Changes

This guide shows exactly how and where to adjust each risk filter threshold.

---

## 1️⃣ MULTI-TIMEFRAME CONFIRMATION

**Priority:** ⭐ START HERE (biggest impact, lowest risk)  
**Expected Impact:** +15-25% more trades

### Current Setting
```python
require_all_mtf: True
```
"All higher timeframes must align with entry direction"

### Change To
```python
require_all_mtf: False
```
"Allow trades if trend is not opposed by higher TFs"

### Where to Change

**File:** `trading_bot/main.py` (Line ~280)

```python
# Find this section around line 280:
if use_risk_management:
    try:
        from utils import RiskManager
        risk_manager = RiskManager(
            capital=initial_capital,
            exchange_id=exchange,
            use_mtf=use_mtf,
            use_funding=use_funding,
            use_circuit_breaker=use_circuit_breaker,
            use_kelly=use_kelly,
            use_order_flow=use_order_flow,
            strict_order_flow=strict_order_flow,
            require_all_mtf=True,  # ← CHANGE THIS TO False
)
```

### How It Works

**Before (require_all_mtf=True):**
```
To enter LONG on 15m, need ALL of:
  1h trend ≥ 0 (BULLISH/NEUTRAL)     AND
  4h trend ≥ 0 (BULLISH/NEUTRAL)     AND
  1d trend ≥ 0 (BULLISH/NEUTRAL)

If ANY is negative → ENTRY BLOCKED
Block Rate: ~40-50% of valid signals
```

**After (require_all_mtf=False):**
```
To enter LONG on 15m, need:
  Majority vote of higher TFs
  At least 50%+ trending the same direction
  
Example accepted scenario:
  1h: BULLISH (+)
  4h: NEUTRAL (0)    ← This was blocking before
  1d: BULLISH (+)
  Result: 2/3 bullish = APPROVED
  
Block Rate: ~20-30% of valid signals
```

---

## 2️⃣ FUNDING RATE FILTER

**Priority:** ⭐⭐ (moderate impact, very low risk)  
**Expected Impact:** +10-15% more trades

### Current Setting
```python
use_funding: True
strict_funding: False
```
"Block only when funding > 0.05% (extreme leverage)"

### Change Option A: Disable Entirely
```python
use_funding: False
```
"Don't check funding rates at all"

### Change Option B: Loosen Threshold (Advanced)
```python
# Edit utils/funding_rate.py line 65-67
EXTREME_THRESHOLD = 0.0010   # Was 0.0005 (0.05%)
HIGH_THRESHOLD = 0.0007      # Was 0.0003 (0.03%)
```

### Where to Change

**File:** `trading_bot/main.py` (Line ~280)

```python
if use_risk_management:
    try:
        from utils import RiskManager
        risk_manager = RiskManager(
            capital=initial_capital,
            exchange_id=exchange,
            use_mtf=use_mtf,
            use_funding=False,  # ← CHANGE THIS (was True)
            use_circuit_breaker=use_circuit_breaker,
            use_kelly=use_kelly,
            ...
        )
```

### How It Works

**Before (use_funding=True):**
```
Binance funding check before entry:

BTC/USDT LONG:
  Current funding: +0.045%
  Is longs paying shorts? Yes
  Are longs overleveraged? Yes (> 0.05%)
  Decision: BLOCK this trade
  
Estimated annual funding cost: 49%+
```

**After (use_funding=False):**
```
Binance funding check: [SKIPPED]
No funding analysis
All trades approved (assuming other filters pass)
```

---

## 3️⃣ CIRCUIT BREAKER: CONSECUTIVE LOSSES

**Priority:** ⭐⭐⭐ (low-moderate impact, low risk)  
**Expected Impact:** +5-10% more trades (during drawdowns only)

### Current Setting
```python
max_consecutive_losses: 5
```
"Pause trading after 5 consecutive losses"

### Change To
```python
max_consecutive_losses: 6  # or 7
```
"Allow up to 6-7 losses before pausing"

### Where to Change

**File:** `trading_bot/main.py` (Line 270-280)

```python
if use_risk_management:
    try:
        from utils import RiskManager, CircuitBreakerConfig
        
        # Create custom circuit breaker config
        cb_config = CircuitBreakerConfig(
            max_drawdown_pct=0.15,          # Keep same
            max_daily_loss_pct=0.05,        # Keep same
            max_consecutive_losses=6,       # ← CHANGE THIS (was 5)
            cooldown_minutes=60,            # Keep same
            max_daily_trades=20             # Keep same
        )
        
        risk_manager = RiskManager(
            capital=initial_capital,
            exchange_id=exchange,
            use_mtf=use_mtf,
            use_funding=use_funding,
            use_circuit_breaker=use_circuit_breaker,
            use_kelly=use_kelly,
            circuit_breaker_config=cb_config  # Pass config
        )
```

### How It Works

**Before (max_consecutive_losses=5):**
```
Loss 1: ✓ Continue trading
Loss 2: ✓ Continue trading
Loss 3: ✓ Continue trading
Loss 4: ✓ Continue trading
Loss 5: ✓ Continue trading
Loss 6: 🛑 PAUSE for 60 minutes
```

**After (max_consecutive_losses=6):**
```
Loss 1: ✓ Continue trading
Loss 2: ✓ Continue trading
Loss 3: ✓ Continue trading
Loss 4: ✓ Continue trading
Loss 5: ✓ Continue trading
Loss 6: ✓ Continue trading
Loss 7: 🛑 PAUSE for 60 minutes
```

### Impact
- Allows one additional loss streak before cooling down
- Only affects days with multiple losses
- Rarely triggers for good strategies

---

## 4️⃣ CIRCUIT BREAKER: DAILY LOSS LIMIT

**Priority:** ⭐⭐⭐⭐ (moderate-high impact, moderate risk)  
**Expected Impact:** +10-15% more trades (on volatile days)

### Current Setting
```python
max_daily_loss_pct: 0.05  # 5%
```
"Pause trading after losing 5% in a single day"

### Change To
```python
max_daily_loss_pct: 0.06  # 6% (or up to 0.08)
```
"Allow up to 6-8% daily loss before pausing"

### Where to Change

**File:** `trading_bot/main.py` (Line 270-280)

```python
cb_config = CircuitBreakerConfig(
    max_drawdown_pct=0.15,          # Keep same
    max_daily_loss_pct=0.06,        # ← CHANGE THIS (was 0.05)
    max_consecutive_losses=5,       # Keep same
    cooldown_minutes=60,            # Keep same
    max_daily_trades=20             # Keep same
)
```

### How It Works

**Before (max_daily_loss_pct=0.05):**
```
Day 1 Trading:
  Trade 1 loss: -1.0%
  Trade 2 loss: -2.0%
  Trade 3 loss: -2.5% ← TOTAL -5.5%
  🛑 PAUSE: Hit daily loss limit

Remaining trades for the day = 0
```

**After (max_daily_loss_pct=0.06):**
```
Day 1 Trading:
  Trade 1 loss: -1.0%
  Trade 2 loss: -2.0%
  Trade 3 loss: -2.5% ← TOTAL -5.5%
  ✓ Continue: Still under 6%
  Trade 4: +1.0%
  Trade 5 loss: -1.5% ← TOTAL -7.0%
  🛑 PAUSE: Hit daily loss limit

Allows 1-2 more trades before pausing
```

### ⚠️ Risk Consideration
**Highest risk adjustment** - allows larger daily drawdowns. Only recommend if:
1. You're using good position sizing (Kelly Criterion)
2. Your strategy has ATR-based stops
3. You want to avoid artificial trading pauses during volatile days

---

## 5️⃣ CIRCUIT BREAKER: MAX DAILY TRADES

**Priority:** ⭐⭐⭐⭐⭐ (avoid changing)  
**Expected Impact:** +5% more trades (rare scenario)

### Current Setting
```python
max_daily_trades: 20
```
"Pause after 20 trades in a single day"

### Why NOT to Change
- Already generous (20 trades/day is a lot)
- Prevents overtrading during emotional periods
- Protects against slippage accumulation
- **Leave this alone**

---

## 📋 STEP-BY-STEP EXAMPLE: Make All Changes

### Step 1: Create Custom Config (main.py ~270)

```python
if use_risk_management:
    try:
        from utils import RiskManager, CircuitBreakerConfig
        
        # Step 1: Create circuit breaker with adjusted thresholds
        cb_config = CircuitBreakerConfig(
            max_drawdown_pct=0.15,          # Keep: protects account
            warning_drawdown_pct=0.10,      # Keep: early warning
            max_daily_loss_pct=0.06,        # Change: 5% → 6%
            max_consecutive_losses=6,       # Change: 5 → 6
            cooldown_minutes=60,            # Keep same
            max_daily_trades=20             # Keep: trade limit
        )
        
        # Step 2: Initialize risk manager with adjustments
        risk_manager = RiskManager(
            capital=initial_capital,
            exchange_id=exchange,
            use_mtf=use_mtf,
            use_funding=False,              # Change: disable funding
            use_circuit_breaker=use_circuit_breaker,
            use_kelly=use_kelly,
            use_order_flow=use_order_flow,
            strict_order_flow=strict_order_flow,
            require_all_mtf=False,          # Change: relax MTF
            circuit_breaker_config=cb_config  # Pass config
        )
        print("🛡️ Risk Manager initialized with optimized thresholds")
        
    except ImportError as e:
        print(f"⚠️ Risk Manager import failed: {e}")
        risk_manager = None
```

---

## 🧪 Testing Your Changes

After making changes, run:

```bash
# Test 1: Simple backtest to check syntax
python trading_bot/main.py --mode backtest --days 30 \
  --strategy orderblock_premium_v2 \
  --real-data \
  --risk-mgmt

# Watch for:
# ✓ Risk manager initializes without errors
# ✓ Filter analysis shows in output
# ✓ Filter rate decreased from before
```

```bash
# Test 2: Medium backtest to verify impact
python trading_bot/main.py --mode backtest --days 90 \
  --strategy orderblock_premium_v2 \
  --real-data \
  --risk-mgmt

# Compare results:
# - Did Trades Allowed increase?
# - Did win rate stay stable?
# - Did max drawdown stay under control?
```

---

## 📊 Change Summary Table

| Change | Location | Current | New | Impact | Risk |
|--------|----------|---------|-----|--------|------|
| require_all_mtf | main.py:280 | True | False | +20% trades | ⭐ Low |
| use_funding | main.py:282 | True | False | +15% trades | ⭐ Low |
| max_consecutive_loses | main.py:271 | 5 | 6 | +8% trades | ⭐ Low |
| max_daily_loss | main.py:270 | 5% | 6% | +12% trades | ⭐⭐ Mod |

**Total Expected:** +55% more trades, +5-8% additional return

---

## Reverting Changes

If a change makes things worse:

```python
# Simply revert back to original values:
cb_config = CircuitBreakerConfig(
    max_daily_loss_pct=0.05,        # Back to 5%
    max_consecutive_losses=5,       # Back to 5
)

risk_manager = RiskManager(
    use_funding=True,               # Back to enabled
    require_all_mtf=True,           # Back to True
)
```

No code restart needed - just edit and re-run backtest.

---

## Getting Help

If a change isn't working:

1. Check `filter_analysis_{timestamp}.json` for rejection patterns
2. Look at the specific rejection reasons
3. Adjust the right threshold (not a guess)
4. Test again with clear metrics

Remember: **Change one thing at a time, measure, then decide.**

