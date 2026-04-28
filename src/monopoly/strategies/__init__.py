"""Strategy interface and built-in baseline strategies."""

from monopoly.strategies.base import JailAction, Strategy
from monopoly.strategies.random_strategy import RandomStrategy

__all__ = ["JailAction", "RandomStrategy", "Strategy"]
