"""
Order Block Strategy - Re-export Module
========================================
Backward-compatible module that re-exports all strategy classes
from their new focused modules.

Module Structure:
- ob_core.py      → OBState, OrderBlock, OrderBlockStrategy (base)
- ob_variants.py  → OrderBlockStrategyAll, OrderBlockStrategyInverse
- ob_premium.py   → Premium, PremiumV2, PremiumV3
- benchmarks.py   → SimpleSMACrossover, RSIStrategy
"""

# Core types & base strategy
from .ob_core import (
    OBState,
    OrderBlock,
    OrderBlockStrategy,
)

# Variant strategies
from .ob_variants import (
    OrderBlockStrategyAll,
    OrderBlockStrategyInverse,
)

# Premium strategies
from .ob_premium import (
    OrderBlockStrategyPremium,
    OrderBlockStrategyPremiumV2,
    OrderBlockStrategyPremiumV3,
)

# Benchmark strategies
from .benchmarks import (
    SimpleSMACrossover,
    RSIStrategy,
)

__all__ = [
    # Types
    'OBState',
    'OrderBlock',
    # Strategies
    'OrderBlockStrategy',
    'OrderBlockStrategyAll',
    'OrderBlockStrategyInverse',
    'OrderBlockStrategyPremium',
    'OrderBlockStrategyPremiumV2',
    'OrderBlockStrategyPremiumV3',
    'SimpleSMACrossover',
    'RSIStrategy',
]
