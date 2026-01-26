# 📱 Telegram Trade Journal - Complete Guide

## Overview

The Telegram Trade Journal automatically sends detailed trade notifications to your Telegram account, providing real-time visibility into your trading bot's performance. Every entry, exit, and session summary is beautifully formatted and sent instantly.

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Create Your Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the prompts:
   - Choose a name (e.g., "My Trading Bot")
   - Choose a username (e.g., "mytrading_bot")
4. **Copy the bot token** (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Get Your Chat ID

**Option A: Using @userinfobot**
1. Search for `@userinfobot` in Telegram
2. Start a chat
3. It will reply with your ID (e.g., `123456789`)

**Option B: Using @RawDataBot**
1. Search for `@RawDataBot`
2. Forward any message to it
3. Look for `"id": 123456789` in the response

### Step 3: Run Setup Script

```bash
python setup_telegram.py
```

Follow the interactive prompts:
- Enter your bot token
- Enter your chat ID
- Choose notification preferences
- Test the connection

### Step 4: Start Your Bot

1. Go to your bot in Telegram (search for the username you created)
2. Click **START** or send `/start`
3. This allows the bot to send you messages

### Step 5: Run a Backtest

```bash
python trading_bot/main.py --mode backtest --days 7 --real-data
```

You should start receiving trade notifications in Telegram! 🎉

---

## 📋 What You'll Receive

### 1. Trade Entry Notifications

Sent whenever your bot enters a new trade.

**Example:**
```
🟢 TRADE #3 - LONG ENTRY

📈 Position Details
Symbol: BTC/USDT
Entry: $86,450.00
Stop Loss: $84,200.00 (2.60%)
Take Profit: $91,000.00 (5.26%)

💰 Risk Management
Quantity: 0.115
Position Size: $9,941.75
Risk: $258.75 (2.60%)
Reward: $523.25
R:R Ratio: 1:2.02

💼 Account
Capital: $10,058.25
Reason: signal

📊 Order Block
Type: bullish
Range: $86,000.00 - $86,500.00
State: ACTIVE

🕐 2026-01-26 14:23:15
```

**Includes:**
- Position type (LONG/SHORT)
- Entry price and targets (SL/TP)
- Position size and quantity
- Risk/reward metrics
- Order block information
- Current capital
- Timestamp

### 2. Trade Exit Notifications

Sent when your bot closes a position.

**Winning Trade:**
```
✅ TRADE #3 - WIN

📊 Trade Summary
Symbol: BTC/USDT
Type: LONG
Entry: $86,450.00
Exit: $91,000.00
Quantity: 0.115

💵 Results
PnL: +$523.25 (+5.26%)
Exit Reason: TP
Duration: 47 bars

💼 Account
Capital: $10,581.50

🎯 Targets
Stop Loss: $84,200.00
Take Profit: $91,000.00

🕐 2026-01-26 18:45:30
```

**Losing Trade:**
```
❌ TRADE #4 - LOSS

📊 Trade Summary
Symbol: BTC/USDT
Type: SHORT
Entry: $90,500.00
Exit: $92,000.00
Quantity: 0.110

💵 Results
PnL: -$165.00 (-1.66%)
Exit Reason: SL
Duration: 12 bars

💼 Account
Capital: $10,416.50

🕐 2026-01-26 19:12:15
```

**Includes:**
- Win/Loss status
- Entry and exit prices
- Profit/Loss ($ and %)
- Exit reason (TP, SL, reversal, end_of_data)
- Trade duration (number of bars)
- Updated capital
- Original targets

### 3. Session Summary

Sent automatically at the end of each backtest.

**Example:**
```
🎉 TRADING SESSION SUMMARY

📊 Performance
Total Trades: 42
Win Rate: 57.1%
Total PnL: +$2,456.78
Total Return: +24.57%

💼 Capital
Initial: $10,000.00
Final: $12,456.78
Max Drawdown: 8.23%
Profit Factor: 1.89

⏱️ Session
Duration: 0:05:43
Started: 2026-01-26 14:00:00
Ended: 2026-01-26 14:05:43
```

**Includes:**
- Total trades and win rate
- Total PnL ($ and %)
- Capital progression
- Max drawdown
- Profit factor
- Session duration

### 4. Order Block Detection (Optional)

If enabled, you'll receive notifications when order blocks are detected.

```
🟢 BULLISH ORDER BLOCK DETECTED

Symbol: BTC/USDT
Range: $85,500.00 - $86,200.00
Width: 0.82%
Current Price: $88,450.00
State: ACTIVE

🕐 2026-01-26 13:15:00
```

---

## ⚙️ Configuration

### Option 1: Using the Setup Script (Recommended)

```bash
python setup_telegram.py
```

Interactive prompts will guide you through:
- Bot token entry
- Chat ID entry
- Notification preferences
- Connection testing

### Option 2: Manual Configuration

Edit `trading_bot/config/telegram_config.json`:

```json
{
  "bot_token": "YOUR_BOT_TOKEN_HERE",
  "chat_id": "YOUR_CHAT_ID_HERE",
  "enabled": true,
  "parse_mode": "HTML",
  "notify_on_entry": true,
  "notify_on_exit": true,
  "notify_on_orderblock": false,
  "send_summary": true,
  "quiet_mode": false
}
```

### Configuration Options Explained

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `bot_token` | string | Your bot token from @BotFather | Required |
| `chat_id` | string | Your Telegram user ID | Required |
| `enabled` | boolean | Master switch for Telegram notifications | `true` |
| `parse_mode` | string | Message formatting (`HTML`, `Markdown`, or `None`) | `HTML` |
| `notify_on_entry` | boolean | Send notification when entering trades | `true` |
| `notify_on_exit` | boolean | Send notification when exiting trades | `true` |
| `notify_on_orderblock` | boolean | Send notification when order blocks detected | `false` |
| `send_summary` | boolean | Send session summary at end of backtest | `true` |
| `quiet_mode` | boolean | Disable notification sound | `false` |

### Notification Presets

**Verbose Mode** (everything):
```json
{
  "enabled": true,
  "notify_on_entry": true,
  "notify_on_exit": true,
  "notify_on_orderblock": true,
  "send_summary": true,
  "quiet_mode": false
}
```

**Essential Mode** (entries and exits only):
```json
{
  "enabled": true,
  "notify_on_entry": true,
  "notify_on_exit": true,
  "notify_on_orderblock": false,
  "send_summary": true,
  "quiet_mode": false
}
```

**Summary Only** (minimal):
```json
{
  "enabled": true,
  "notify_on_entry": false,
  "notify_on_exit": false,
  "notify_on_orderblock": false,
  "send_summary": true,
  "quiet_mode": true
}
```

**Silent Mode** (no sound):
```json
{
  "enabled": true,
  "notify_on_entry": true,
  "notify_on_exit": true,
  "notify_on_orderblock": false,
  "send_summary": true,
  "quiet_mode": true
}
```

**Disabled** (console only):
```json
{
  "enabled": false
}
```

---

## 🧪 Testing

### Test Your Configuration

```bash
python setup_telegram.py
```

The script will send a test message to verify your setup.

### Manual Test

```python
import asyncio
from trading_bot.utils.notifications import create_telegram_notifier

async def test():
    notifier = create_telegram_notifier(
        bot_token="YOUR_BOT_TOKEN",
        chat_id="YOUR_CHAT_ID",
        enabled=True
    )
    
    await notifier.initialize()
    await notifier.send_message("🧪 <b>Test successful!</b>")
    await notifier.shutdown()

asyncio.run(test())
```

---

## 🔧 Troubleshooting

### Problem: No notifications received

**Check:**
1. ✅ Did you click START on your bot in Telegram?
2. ✅ Is `enabled: true` in the config?
3. ✅ Is the bot token correct?
4. ✅ Is the chat ID correct?

**Solution:**
```bash
python setup_telegram.py
# Re-run setup and test connection
```

### Problem: "Bot was blocked by the user"

**Cause:** You blocked the bot or never started it.

**Solution:**
1. Search for your bot in Telegram
2. Unblock it (if blocked)
3. Click START
4. Run backtest again

### Problem: "Unauthorized" error

**Cause:** Invalid bot token.

**Solution:**
1. Go to @BotFather
2. Send `/mybots`
3. Select your bot → API Token
4. Copy the token
5. Update `telegram_config.json`

### Problem: Messages sent to wrong person

**Cause:** Incorrect chat ID.

**Solution:**
1. Get your correct chat ID from @userinfobot
2. Update `chat_id` in `telegram_config.json`
3. Test again

### Problem: "Telegram notifications disabled" message

**Cause:** Config file has `enabled: false` or credentials are placeholder values.

**Solution:**
```bash
python setup_telegram.py
# Run interactive setup
```

### Problem: Messages not formatted correctly

**Cause:** Wrong parse_mode.

**Solution:**
Change `parse_mode` in config:
- `"HTML"` - Recommended (supports <b>, <i>, etc.)
- `"Markdown"` - Alternative format
- `null` - Plain text only

---

## 📊 Console Output

Even with Telegram enabled, trades are **also logged to the console** for debugging:

```
============================================================
🟢 TRADE #1 - LONG ENTRY
============================================================
Symbol:        BTC/USDT
Entry Price:   $86,450.0000
Stop Loss:     $84,200.0000
Take Profit:   $91,000.0000
Quantity:      0.115000
Position Size: $9,941.75
Risk Amount:   $258.75 (2.60%)
Reward Amount: $523.25
Risk/Reward:   1:2.02
Capital:       $10,058.25
Reason:        signal

📊 Order Block Info:
   Type:   bullish
   Range:  $86,000.00 - $86,500.00
   State:  ACTIVE

Time:          2026-01-26 14:23:15
============================================================
```

**To disable console output:** Edit `trading_bot/main.py` and set `verbose=False` in backtest call.

---

## 🔒 Security Best Practices

### 1. Keep Your Token Secret

❌ **DON'T:** Commit `telegram_config.json` to public repositories
✅ **DO:** Add it to `.gitignore`

```bash
# Add to .gitignore
echo "trading_bot/config/telegram_config.json" >> .gitignore
```

### 2. Use Environment Variables (Advanced)

Instead of hardcoding in config:

```python
import os
import json

config = {
    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
    "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
    "enabled": True
}

with open("telegram_config.json", "w") as f:
    json.dump(config, f)
```

Set environment variables:
```bash
# Windows PowerShell
$env:TELEGRAM_BOT_TOKEN="1234567890:ABCdef..."
$env:TELEGRAM_CHAT_ID="123456789"

# Linux/Mac
export TELEGRAM_BOT_TOKEN="1234567890:ABCdef..."
export TELEGRAM_CHAT_ID="123456789"
```

### 3. Revoke Compromised Tokens

If your token is exposed:
1. Go to @BotFather
2. Send `/mybots`
3. Select your bot → Revoke Token
4. Get new token and update config

---

## 💡 Tips & Tricks

### Multiple Bots for Different Strategies

Create separate bots for different strategies:

```json
// config/telegram_orderblock.json
{"bot_token": "...", "chat_id": "..."}

// config/telegram_sma.json
{"bot_token": "...", "chat_id": "..."}
```

Load specific config:
```python
journal = TradeJournalSync("config/telegram_orderblock.json")
```

### Group Chats

To send notifications to a group:
1. Add your bot to the group
2. Make it an admin
3. Get group chat ID (use @RawDataBot)
4. Use group ID in `chat_id` (starts with `-`)

### Reduce Notification Spam

For high-frequency strategies, use:
```json
{
  "notify_on_entry": false,
  "notify_on_exit": false,
  "send_summary": true
}
```

You'll only get the final summary!

### Custom Emoji

Edit `trade_journal.py` to customize emojis:
```python
emoji = "🚀" if signal_type == "LONG" else "💥"  # Instead of 🟢/🔴
```

---

## 🌟 Advanced Usage

### Programmatic Notifications

Send custom messages from your strategy:

```python
from trading_bot.utils.trade_journal import TradeJournalSync

journal = TradeJournalSync()
journal.initialize()

# In your strategy
journal.send_orderblock_detected(
    ob_type="bullish",
    symbol="BTC/USDT",
    price_range=(85000, 86000),
    current_price=88000,
    state="ACTIVE"
)
```

### Integration with Live Trading

```python
# In your live trading loop
if new_trade_opened:
    journal.log_trade_entry(
        signal_type="LONG",
        symbol="BTC/USDT",
        price=current_price,
        sl=stop_loss,
        tp=take_profit,
        quantity=position_size,
        capital=account_balance
    )
```

---

## 📞 Support

**Issues:** [GitHub Issues](https://github.com/PierreBond/quant-trading-stretegy/issues)  
**Telegram API Docs:** https://core.telegram.org/bots/api  
**BotFather Help:** Send `/help` to @BotFather

---

## 🎯 Quick Reference

```bash
# Setup Telegram
python setup_telegram.py

# Run backtest with Telegram notifications
python trading_bot/main.py --mode backtest --days 30 --real-data

# Disable Telegram (set in config)
"enabled": false

# Test connection
python setup_telegram.py  # Choose test option
```

---

**Last Updated:** January 26, 2026  
**Version:** 1.0.0
