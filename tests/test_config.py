"""
Tests for configuration and settings.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestSettings:
    """Verify settings load from environment variables."""

    def test_api_key_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("BINANCE_API_KEY", "test_key_123")
        monkeypatch.setenv("BINANCE_API_SECRET", "test_secret_456")

        # Force reimport to pick up new env
        if "trading_bot.config.settings" in sys.modules:
            del sys.modules["trading_bot.config.settings"]

        from trading_bot.config.settings import api_key, api_secret
        assert api_key == "test_key_123"
        assert api_secret == "test_secret_456"

    def test_api_key_defaults_empty(self, monkeypatch):
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

        if "trading_bot.config.settings" in sys.modules:
            del sys.modules["trading_bot.config.settings"]

        from trading_bot.config.settings import api_key, api_secret
        assert api_key == ""
        assert api_secret == ""

    def test_telegram_disabled_without_env(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

        if "trading_bot.config.settings" in sys.modules:
            del sys.modules["trading_bot.config.settings"]

        from trading_bot.config.settings import NotificationConfig
        cfg = NotificationConfig()
        assert cfg.TELEGRAM_TOKEN == ""

    def test_get_config_returns_dict(self):
        from trading_bot.config.settings import get_config
        cfg = get_config("paper")
        assert "trading" in cfg
        assert "risk" in cfg
        assert "order_block" in cfg

    def test_trading_config_defaults(self):
        from trading_bot.config.settings import TradingConfig
        tc = TradingConfig()
        assert tc.INITIAL_CAPITAL == 10000.0
        assert tc.RISK_PER_TRADE == 0.01
        assert tc.MAX_POSITIONS == 3
