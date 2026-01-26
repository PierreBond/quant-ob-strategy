"""
Telegram Bot Setup Script
==========================
Interactive setup for Telegram trade journaling
"""

import json
import sys
import os
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def print_header():
    """Print setup header"""
    print("\n" + "="*70)
    print("TELEGRAM TRADE JOURNAL SETUP")
    print("="*70)
    print("\nThis script will help you configure Telegram notifications")
    print("for your trading bot.\n")


def print_instructions():
    """Print setup instructions"""
    print("SETUP INSTRUCTIONS:")
    print("-" * 70)
    print("\n1. CREATE A TELEGRAM BOT:")
    print("   - Open Telegram and search for @BotFather")
    print("   - Send /newbot command")
    print("   - Follow instructions to create your bot")
    print("   - Copy the bot token (looks like: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)")
    
    print("\n2. GET YOUR CHAT ID:")
    print("   - Search for @userinfobot in Telegram")
    print("   - Start a chat and it will show your ID")
    print("   - Or search for @RawDataBot and forward any message")
    print("   - Your chat ID is a number (e.g., 123456789)")
    
    print("\nThat's it! Trade notifications will appear directly in your Telegram.")
    print("No need to start the bot - messages will show up automatically.\n")
    print("-" * 70)


def load_from_env():
    """Load credentials from .env file"""
    bot_token = os.getenv("telegram_token")
    chat_id = os.getenv("chat_id")
    
    if bot_token and chat_id:
        print("\n✅ Successfully loaded credentials from .env file!")
    
    return bot_token, chat_id


def get_input(prompt: str, default: str = None) -> str:
    """Get user input with optional default"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input
            print("This field is required. Please try again.")


def validate_bot_token(token: str) -> bool:
    """Validate bot token format"""
    parts = token.split(":")
    if len(parts) != 2:
        return False
    
    try:
        int(parts[0])
        return len(parts[1]) > 20
    except ValueError:
        return False


def validate_chat_id(chat_id: str) -> bool:
    """Validate chat ID format"""
    try:
        int(chat_id)
        return True
    except ValueError:
        return False


def test_connection(bot_token: str, chat_id: str) -> bool:
    """Test Telegram connection"""
    print("\nTesting connection...")
    
    try:
        import asyncio
        from trading_bot.utils.notifications import create_telegram_notifier
        
        async def test():
            notifier = create_telegram_notifier(
                bot_token=bot_token,
                chat_id=chat_id,
                enabled=True
            )
            
            await notifier.initialize()
            
            success = await notifier.send_message(
                "<b>✅ Connection Successful!</b>\n\n"
                "Your trading bot is now configured!\n\n"
                "Trade notifications will appear here automatically when you run backtests.\n\n"
                "Setup complete! 🎉"
            )
            
            await notifier.shutdown()
            return success
        
        result = asyncio.run(test())
        
        if result:
            print("✅ [SUCCESS] Connection successful! Test message sent to Telegram.")
            return True
        else:
            print("❌ [ERROR] Connection failed. Please check your credentials.")
            return False
    
    except Exception as e:
        print(f"❌ [ERROR] Error testing connection: {e}")
        return False


def main():
    """Main setup function"""
    print_header()
    
    # Try to load from .env
    env_bot_token, env_chat_id = load_from_env()
    
    if env_bot_token and env_chat_id:
        print("✓ Found credentials in .env file:")
        print(f"  Bot Token: {env_bot_token[:20]}...")
        print(f"  Chat ID: {env_chat_id}")
        
        use_env = get_input("\nUse these credentials? (y/n)", "y").lower() == 'y'
        
        if use_env:
            bot_token = env_bot_token
            chat_id = env_chat_id
            
            # Validate
            if not validate_bot_token(bot_token):
                print("❌ Invalid bot token in .env file")
                return
            if not validate_chat_id(chat_id):
                print("❌ Invalid chat ID in .env file")
                return
        else:
            print_instructions()
            # Manual entry (existing code below)
            bot_token = None
            chat_id = None
    else:
        print("\n⚠️  No credentials found in .env file")
        print_instructions()
        bot_token = None
        chat_id = None
    
    # Load existing config if it exists
    config_path = Path("trading_bot/config/telegram_config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    existing_config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                existing_config = json.load(f)
            print("\n✓ Found existing configuration\n")
        except:
            pass
    
    # Get credentials if not from .env
    if not bot_token:
        print("\n" + "="*70)
        print("CONFIGURATION")
        print("="*70 + "\n")
        
        # Get bot token
        while True:
            bot_token = get_input("Enter your bot token", 
                                 existing_config.get("bot_token", ""))
            
            if validate_bot_token(bot_token):
                break
            else:
                print("❌ Invalid bot token format. Should be: 1234567890:ABCdefGHI...")
        
        # Get chat ID
        while True:
            chat_id = get_input("Enter your chat ID",
                               existing_config.get("chat_id", ""))
            
            if validate_chat_id(chat_id):
                break
            else:
                print("❌ Invalid chat ID. Should be a number like: 123456789")
    
    # Get preferences
    print("\n📋 Notification Preferences:")
    
    notify_entry = get_input("Send notifications on trade entry? (y/n)", "y").lower() == 'y'
    notify_exit = get_input("Send notifications on trade exit? (y/n)", "y").lower() == 'y'
    notify_ob = get_input("Send notifications when order blocks detected? (y/n)", "n").lower() == 'y'
    send_summary = get_input("Send session summary at end? (y/n)", "y").lower() == 'y'
    quiet_mode = get_input("Quiet mode (no notification sound)? (y/n)", "n").lower() == 'y'
    
    # Build config
    config = {
        "bot_token": bot_token,
        "chat_id": chat_id,
        "enabled": True,
        "parse_mode": "HTML",
        "notify_on_entry": notify_entry,
        "notify_on_exit": notify_exit,
        "notify_on_orderblock": notify_ob,
        "send_summary": send_summary,
        "quiet_mode": quiet_mode
    }
    
    # Test connection
    print()
    test_now = get_input("Test connection now? (y/n)", "y").lower() == 'y'
    
    if test_now:
        if test_connection(bot_token, chat_id):
            # Save config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            print("\n" + "="*70)
            print("✅ [SUCCESS] SETUP COMPLETE!")
            print("="*70)
            print(f"\nConfiguration saved to: {config_path}")
            print("\n📱 Trade notifications will appear in your Telegram app automatically!")
            print("   Just run a backtest and check your Telegram for messages.")
            print("\n💡 TIP: Edit telegram_config.json anytime to change settings")
            print("="*70 + "\n")
        else:
            save_anyway = get_input("\nSave configuration anyway? (y/n)", "n").lower() == 'y'
            if save_anyway:
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                print(f"\n[INFO] Configuration saved to: {config_path}")
                print("[WARNING] Please verify your credentials and test again")
    else:
        # Save without testing
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print("\n[INFO] Configuration saved (not tested)")
        print("[WARNING] Make sure to test before running live trading!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Setup cancelled by user")
    except Exception as e:
        print(f"\n\n[ERROR] Setup error: {e}")