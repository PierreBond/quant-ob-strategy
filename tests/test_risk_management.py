"""
Tests for risk management components.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestCircuitBreaker:
    """Circuit breaker state machine tests."""

    def test_initial_state_is_active(self):
        from trading_bot.utils.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        status = cb.get_status()
        assert status["state"] in ("active", "ACTIVE", "Active")

    def test_can_trade_initially(self):
        from trading_bot.utils.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        assert cb.can_trade() is True


class TestPositionSizer:
    """Kelly criterion position sizing tests."""

    def test_sizer_instantiates(self):
        from trading_bot.utils.position_sizing import PositionSizer
        ps = PositionSizer()
        assert ps is not None

    def test_get_sizer_factory(self):
        from trading_bot.utils.position_sizing import get_position_sizer
        ps = get_position_sizer()
        assert ps is not None


class TestRiskManager:
    """Integration tests for the unified risk manager."""

    def test_instantiation(self):
        from trading_bot.utils.risk_manager import RiskManager
        rm = RiskManager(capital=10000, use_mtf=False, use_funding=False, use_order_flow=False)
        assert rm is not None

    def test_trade_decision_structure(self):
        from trading_bot.utils.risk_manager import TradeDecision
        td = TradeDecision(
            can_trade=True,
            position_size_pct=0.02,
            position_size_usd=200,
            reasons=[],
            warnings=[],
            mtf_score=0.5,
            funding_bias="neutral",
        )
        assert td.can_trade is True
        assert td.position_size_usd == 200
