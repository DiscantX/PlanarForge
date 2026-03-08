from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StatVM:
    label: str
    value: str


@dataclass(frozen=True)
class InventorySlotVM:
    slot_name: str
    item_resref: str
    item_name: str
    icon: tuple[int, int, list[float]] | None = None


@dataclass(frozen=True)
class CharacterVM:
    resref: str
    display_name: str
    race: str
    klass: str
    gender: str
    alignment: str
    level: int
    hp_current: int
    hp_max: int
    stats: list[StatVM] = field(default_factory=list)
    inventory: list[InventorySlotVM] = field(default_factory=list)
