# Trading Bot Configuration
# =========================
# Edit these settings for your environment
# API keys are loaded from environment variables (see .env.example)

import os
from enum import Enum
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

# ============================================================================
# EXCHANGE SETTINGS
# ============================================================================

EXCHANGE = "binance"  # binance, coinbase, kraken, etc.
SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"  # 1m, 5m, 15m, 1h, 4h, 1d

api_key = os.environ.get("BINANCE_API_KEY", "")
api_secret = os.environ.get("BINANCE_API_SECRET", "")

# Sandbox/Test mode (recommended for testing)
TESTNET = True
PAPER_TRADING = True  # No real money - for testing

# ============================================================================
# TRADING PARAMETERS
# ============================================================================

@dataclass
class TradingConfig:
    """Core trading parameters"""
    # Position sizing
    INITIAL_CAPITAL: float = 10000.0
    RISK_PER_TRADE: float = 0.01  # 1% risk per trade
    MAX_POSITIONS: int = 3

    # Order settings
    ORDER_TYPE = "market"  # market, limit
    LEVERAGE = 1.0  # 1x = spot, 2x = 2x margin, etc.

    # SL/TP
    DEFAULT_SL_PERCENT: float = 2.0
    DEFAULT_TP_PERCENT: float = 4.0
    TRAILING_SL: bool = False
    TRAILING_SL_PERCENT: float = 1.0

    # Session
    SESSION_NAME: str = "default"
    LOG_LEVEL: str = "INFO"

# ============================================================================
# ORDER BLOCK SETTINGS
# ============================================================================

@dataclass
class OrderBlockConfig:
    """Order block detection parameters"""
    MIN_OB_BODY_SIZE: float = 0.3  # % of candle range
    IMPULSE_LOOKBACK: int = 5  # candles to check for impulse
    MIN_IMPULSE_LENGTH: int = 3  # consecutive candles
    OB_TOLERANCE: float = 0.001  # 0.1% price tolerance

    # Confluence filters
    USE_FIBONACCI: bool = True
    USE_FVG: bool = True
    USE_LIQUIDITY: bool = True
    USE_MARKET_STRUCTURE: bool = True

    # Timeframe filter (trade only on HTF aligned signals)
    HTF_MULTIPLIER: int = 4  # Check HTF (e.g., 1h for 15m trades)

# ============================================================================
# RISK MANAGEMENT
# ============================================================================

@dataclass
class RiskConfig:
    """Risk management parameters"""
    MAX_DAILY_LOSS: float = 0.05  # 5% max daily loss
    MAX_DRAWDOWN: float = 0.10    # 10% max drawdown
    MAX_TRADES_PER_DAY: int = 10
    MIN_RISK_REWARD: float = 1.5  # Minimum 1:1.5 R:R

    # Cooldown
    COOLDOWN_AFTER_LOSS: int = 2  # Skip N candles after loss
    COOLDOWN_AFTER_WIN: int = 0

# ============================================================================
# NOTIFICATIONS
# ============================================================================

@dataclass
class NotificationConfig:
    """Notification settings"""
    TELEGRAM_ENABLED = bool(os.environ.get("TELEGRAM_TOKEN", ""))
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    EMAIL_ENABLED: bool = False
    EMAIL_SMTP_SERVER: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    EMAIL_TO: Optional[str] = None

# ============================================================================
# DATA SETTINGS
# ============================================================================

@dataclass
class DataConfig:
    """Data feed settings"""
    DATA_SOURCE = "exchange"  # exchange, csv, parquet
    DATA_DIR = "data"
    CACHE_ENABLED = True
    CACHE_DIR = "cache"

    # Historical data
    START_DATE: Optional[str] = None  # "2025-01-01"
    END_DATE: Optional[str] = None    # "2026-01-24"

    # Live data
    HEARTBEAT_INTERVAL: int = 5  # seconds
    RECONNECT_DELAY: int = 5

# ============================================================================
# EXPORT SETTINGS
# ============================================================================

@dataclass
class ExportConfig:
    """Export and reporting settings"""
    EXPORT_TRADES = True
    EXPORT_DIR = "exports"
    EXPORT_FORMAT = "csv"  # csv, json, parquet

    SAVE_CHARTS = True
    CHARTS_DIR = "charts"

    GENERATE_REPORT = True
    REPORT_DIR = "reports"

# ============================================================================
# CONFIG FACTORY
# ============================================================================

def get_config(env: str = "paper") -> dict:
    """
    Get configuration for specific environment

    Args:
        env: 'paper', 'live', 'backtest'
    """
    base_config = {
        "trading": TradingConfig(),
        "order_block": OrderBlockConfig(),
        "risk": RiskConfig(),
        "notifications": NotificationConfig(),
        "data": DataConfig(),
        "export": ExportConfig(),
    }

    if env == "live":
        base_config["trading"].PAPER_TRADING = False
        base_config["trading"].TESTNET = False
    elif env == "backtest":
        base_config["data"].START_DATE = "2025-01-01"
        base_config["data"].END_DATE = "2026-01-24"

    return base_config


# Environment selector
ENV = "paper"  # Change to 'live' for real trading (careful!)

CONFIG = get_config(ENV)
