"""Strategy interface and built-in strategies."""

from monopoly.strategies.aggressive import AggressiveStrategy
from monopoly.strategies.base import JailAction, MortgageInheritance, Strategy
from monopoly.strategies.cautious import CautiousStrategy
from monopoly.strategies.random_aggressive import RandomAggressiveStrategy
from monopoly.strategies.random_strategy import RandomStrategy
from monopoly.strategies.targeted import TargetedStrategy

__all__ = [
    "AggressiveStrategy",
    "CautiousStrategy",
    "JailAction",
    "MortgageInheritance",
    "RandomAggressiveStrategy",
    "RandomStrategy",
    "Strategy",
    "TargetedStrategy",
]
