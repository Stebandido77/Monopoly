"""Tests for the Player dataclass."""

from __future__ import annotations

from monopoly.player import Player


def test_default_state_matches_hasbro_rules():
    p = Player(name="Alice")
    assert p.name == "Alice"
    assert p.position == 0
    assert p.cash == 1500
    assert p.properties == []
    assert p.in_jail is False
    assert p.jail_turns == 0
    assert p.doubles_streak == 0


def test_property_lists_are_independent_per_player():
    """A mutable default would be a bug — each player needs its own list."""
    p1 = Player(name="A")
    p2 = Player(name="B")
    p1.properties.append("dummy")  # type: ignore[arg-type]
    assert p2.properties == []


def test_custom_initialization_accepts_overrides():
    p = Player(name="Bob", cash=2000, position=10, jail_turns=2)
    assert p.cash == 2000
    assert p.position == 10
    assert p.jail_turns == 2
