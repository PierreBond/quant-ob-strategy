# Telegram Trade Journal - Quick Reference

## Setup (One-Time)

```bash
# Interactive setup
python setup_telegram.py

# What you need:
# 1. Bot token from @BotFather
# 2. Chat ID from @userinfobot
# 3. Start your bot in Telegram
```

## Usage

```bash
# Run backtest with Telegram notifications (automatic)
python trading_bot/main.py --mode backtest --days 30 --real-data

# Check latest order blocks (with console output)
python trading_bot/main.py --mode last_ob --timeframe 1h
```

## Configuration File

**Location:** `trading_bot/config/telegram_config.json`

**Minimal Config:**
```json
{
  "bot_token": "1234567890:ABCdef...",
  "chat_id": "123456789",
  "enabled": true
}
```

**Full Config:**
```json
{
  "bot_token": "1234567890:ABCdef...",
  "chat_id": "123456789",
  "enabled": true,
  "parse_mode": "HTML",
  "notify_on_entry": true,
  "notify_on_exit": true,
  "notify_on_orderblock": false,
  "send_summary": true,
  "quiet_mode": false
}
```

## Quick Toggles

**Disable Telegram:**
```json
{"enabled": false}
```

**Summary Only:**
```json
{
  "enabled": true,
  "notify_on_entry": false,
  "notify_on_exit": false,
  "send_summary": true
}
```

**Silent Notifications:**
```json
{"quiet_mode": true}
```

## What Gets Sent

✓ **Entry Notifications** - Every trade entry with details  
✓ **Exit Notifications** - Every trade exit with P/L  
✓ **Session Summary** - Final stats at end  
✓ **Order Blocks** (optional) - OB detections  

## Files

- `setup_telegram.py` - Interactive setup script
- `trading_bot/config/telegram_config.json` - Configuration
- `trading_bot/utils/trade_journal.py` - Journal implementation
- `trading_bot/utils/notifications.py` - Telegram API wrapper
- `TELEGRAM_GUIDE.md` - Complete documentation

## Troubleshooting

**No messages?**
1. Check bot is started in Telegram
2. Verify `enabled: true` in config
3. Re-run `python setup_telegram.py`

**Wrong chat?**
- Update `chat_id` in config with correct ID from @userinfobot

**See:** [TELEGRAM_GUIDE.md](TELEGRAM_GUIDE.md) for full troubleshooting

## Integration

Telegram journaling is **automatically enabled** in backtests.  
Console output remains available for debugging.

To disable programmatically:
```python
engine = BacktestEngine(
    initial_capital=10000,
    enable_journal=False  # Disable Telegram
)
```

---

**Quick Start:** `python setup_telegram.py` → Run backtest → Get notifications!
