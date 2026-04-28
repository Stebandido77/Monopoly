"""Static Monopoly board: tiles plus indexes by color group and tile type.

The board geometry, prices, and rents are loaded from a YAML file (see
``data/board.yaml``). The :class:`Tile` dataclass is frozen — ownership and
buildings are tracked elsewhere (currently in :class:`monopoly.game.Game`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Tile:
    """A static space on the Monopoly board.

    Parameters
    ----------
    position : int
        Index 0..39 starting at GO and proceeding clockwise.
    name : str
        Display name (e.g. ``"Boardwalk"``).
    type : str
        One of: ``street``, ``railroad``, ``utility``, ``tax``, ``chance``,
        ``community_chest``, ``go``, ``jail``, ``free_parking``, ``go_to_jail``.
    color_group : str or None
        Color group identifier for streets (``brown``, ``light_blue``,
        ``pink``, ``orange``, ``red``, ``yellow``, ``green``, ``dark_blue``).
        ``None`` for non-streets.
    price : int or None
        Purchase price for streets, railroads, and utilities.
    rent : tuple of int or None
        For streets: ``(base, 1h, 2h, 3h, 4h, hotel)`` of length 6.
        For railroads: ``(1_owned, 2_owned, 3_owned, 4_owned)`` of length 4.
        ``None`` otherwise. Base street rent is doubled by the rules engine
        when the owner holds the full color group with no buildings.
    house_cost : int or None
        Cost per house (and per hotel, after returning the four houses).
        ``None`` for non-streets.
    mortgage_value : int or None
        Cash received on mortgaging. ``None`` for non-properties.
    rent_multipliers : tuple of int or None
        For utilities only: ``(1_owned, 2_owned)`` multipliers applied to
        the dice roll on landing.
    tax_amount : int or None
        Fixed amount paid on tax tiles.
    """

    position: int
    name: str
    type: str
    color_group: str | None = None
    price: int | None = None
    rent: tuple[int, ...] | None = None
    house_cost: int | None = None
    mortgage_value: int | None = None
    rent_multipliers: tuple[int, ...] | None = None
    tax_amount: int | None = None

    @property
    def is_property(self) -> bool:
        """Whether this tile can be owned by a player."""
        return self.type in {"street", "railroad", "utility"}


@dataclass(frozen=True)
class BankConfig:
    """Static bank parameters loaded from ``data/board.yaml``."""

    starting_money: int
    go_salary: int
    jail_fine: int
    total_houses: int
    total_hotels: int


class Board:
    """Static Monopoly board: tiles plus precomputed indexes.

    Use :meth:`from_yaml` to load from an arbitrary path or :meth:`default`
    to load the bundled standard US board (``data/board.yaml`` at the repo
    root).

    Attributes
    ----------
    tiles : list[Tile]
        The 40 tiles in board order.
    bank : BankConfig
        Bank-level parameters (starting cash, GO salary, jail fine, house
        and hotel inventories).
    color_groups : dict[str, list[Tile]]
        Color group name -> list of street tiles in that group.
    tiles_by_type : dict[str, list[Tile]]
        Tile type name -> list of tiles of that type.
    """

    def __init__(self, tiles: list[Tile], bank: BankConfig) -> None:
        self.tiles: list[Tile] = list(tiles)
        self.bank: BankConfig = bank
        self.color_groups: dict[str, list[Tile]] = {}
        self.tiles_by_type: dict[str, list[Tile]] = {}
        for tile in self.tiles:
            self.tiles_by_type.setdefault(tile.type, []).append(tile)
            if tile.type == "street" and tile.color_group is not None:
                self.color_groups.setdefault(tile.color_group, []).append(tile)

    def __len__(self) -> int:
        return len(self.tiles)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Board:
        """Load a board from a YAML file.

        The file must contain a top-level ``spaces`` list (40 entries) and
        a ``bank`` mapping. See ``data/board.yaml`` for the canonical schema.
        """
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        tiles = [_tile_from_dict(s) for s in data["spaces"]]
        bank = BankConfig(**data["bank"])
        return cls(tiles, bank)

    @classmethod
    def default(cls) -> Board:
        """Load the bundled standard US board (``<repo>/data/board.yaml``)."""
        path = Path(__file__).resolve().parents[2] / "data" / "board.yaml"
        return cls.from_yaml(path)


def _tile_from_dict(d: dict[str, Any]) -> Tile:
    return Tile(
        position=d["position"],
        name=d["name"],
        type=d["type"],
        color_group=d.get("color_group"),
        price=d.get("price"),
        rent=tuple(d["rent"]) if "rent" in d else None,
        house_cost=d.get("house_cost"),
        mortgage_value=d.get("mortgage_value"),
        rent_multipliers=tuple(d["rent_multipliers"]) if "rent_multipliers" in d else None,
        tax_amount=d.get("tax_amount"),
    )
