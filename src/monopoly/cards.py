"""Chance and Community Chest cards.

A :class:`Card` is a small, frozen value object with a name, an effect
discriminator (``effect_type``) and a free-form ``payload`` dict. The
engine never inspects card identities — it switches on ``effect_type`` and
reads the relevant payload keys, so adding a new card variant is a
one-file change in YAML once a new effect type is supported.

A :class:`Deck` wraps a list of cards plus a ``numpy`` random generator,
shuffles itself on construction (so the game's ``seed`` fully determines
the deck order), and exposes :meth:`draw` and :meth:`return_card` for the
top / bottom-of-deck rotation used by :class:`monopoly.game.Game`.

Effect types supported by the engine
------------------------------------

``move_to_position``
    Teleport to ``payload['position']``. If ``payload['pass_go']`` is true
    and the move crosses GO, the standard $200 salary is paid.
``move_to_nearest``
    Move clockwise to the nearest tile of ``payload['target_type']``
    (``"railroad"`` or ``"utility"``). If ``payload['pay_owner_double']``
    is true, the rent paid on landing is doubled.
``move_relative``
    Move by ``payload['offset']`` tiles. Negative values are allowed
    (``-3`` for "Go Back 3 Spaces"). No GO salary paid even if the
    relative move wraps.
``collect`` / ``pay``
    Bank pays / receives ``payload['amount']``.
``collect_from_each_player`` / ``pay_each_player``
    Each other still-solvent player gives / receives ``payload['amount']``.
``pay_per_house_and_hotel``
    The drawing player pays ``payload['per_house']`` per house and
    ``payload['per_hotel']`` per hotel they own (across all streets).
``go_to_jail``
    Standard jail send: position to jail, ``in_jail=True``, no GO salary.
``get_out_of_jail``
    Card stays with the player rather than rotating to the bottom of the
    deck. ``payload['deck']`` (``"chance"`` or ``"community_chest"``)
    records which deck owns it so it can be returned on use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(frozen=True)
class Card:
    """A single Chance or Community Chest card."""

    name: str
    effect_type: str
    payload: dict[str, Any] = field(default_factory=dict)


class Deck:
    """A shuffled deck of cards with top-draw / bottom-return semantics.

    Parameters
    ----------
    cards : list[Card]
        The full set of cards. The list is copied and shuffled in place
        using ``rng``, so the caller's list is left untouched.
    rng : numpy.random.Generator
        Source of randomness for the initial shuffle. Sharing the game's
        RNG keeps the deck order seed-deterministic alongside dice rolls.
    """

    def __init__(self, cards: list[Card], rng: np.random.Generator) -> None:
        self.cards: list[Card] = list(cards)
        self.rng: np.random.Generator = rng
        self.rng.shuffle(self.cards)

    def draw(self) -> Card:
        """Pop the top card off the deck."""
        return self.cards.pop(0)

    def return_card(self, card: Card) -> None:
        """Place ``card`` at the bottom of the deck."""
        self.cards.append(card)

    def __len__(self) -> int:
        return len(self.cards)


def load_cards(path: str | Path) -> list[Card]:
    """Load a list of cards from a YAML file.

    The file must contain a top-level ``cards`` key whose value is a list
    of ``{name, effect_type, payload?}`` mappings.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    out: list[Card] = []
    for item in data["cards"]:
        out.append(
            Card(
                name=item["name"],
                effect_type=item["effect_type"],
                payload=dict(item.get("payload") or {}),
            )
        )
    return out


def default_chance_path() -> Path:
    """Path to the bundled Chance deck YAML."""
    return Path(__file__).resolve().parents[2] / "data" / "chance_cards.yaml"


def default_community_chest_path() -> Path:
    """Path to the bundled Community Chest deck YAML."""
    return Path(__file__).resolve().parents[2] / "data" / "community_chest_cards.yaml"
