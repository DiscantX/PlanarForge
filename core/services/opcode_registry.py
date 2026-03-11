from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class OpcodeEntry:
    value: int
    name: str
    description: str


class OpcodeRegistry:
    """
    Loads bundled opcode tables from data/opcodes/<game_id>.json.
    """

    _cache: ClassVar[dict[str, "OpcodeRegistry"]] = {}

    def __init__(self, *, entries: dict[int, OpcodeEntry]) -> None:
        self._entries = entries

    @classmethod
    def for_game(cls, game_id: str) -> "OpcodeRegistry":
        key = (game_id or "").strip().lower()
        if key in {"bgee", "bg2ee", "bg1ee", "bg2"}:
            key = "bgee"
        elif key in {"iwd", "iwdee", "iwd1", "iwd2"}:
            key = "iwd"
        elif key in {"pst", "pstee"}:
            key = "pst"
        else:
            key = "bgee"

        cached = cls._cache.get(key)
        if cached is not None:
            return cached

        registry = cls._load_from_file(key)
        cls._cache[key] = registry
        return registry

    def resolve(self, opcode: int) -> OpcodeEntry:
        entry = self._entries.get(opcode)
        if entry is not None:
            return entry
        return OpcodeEntry(opcode, f"Opcode {opcode}", "")

    @classmethod
    def _load_from_file(cls, key: str) -> "OpcodeRegistry":
        root = Path(__file__).resolve().parents[2]
        path = root / "data" / "opcodes" / f"{key}.json"
        if not path.is_file():
            return cls(entries={})
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return cls(entries={})

        entries: dict[int, OpcodeEntry] = {}
        for raw in payload.get("opcodes", []):
            try:
                value = int(raw.get("value"))
                name = str(raw.get("name", "")).strip()
                description = str(raw.get("description", "")).strip()
            except Exception:
                continue
            if value not in entries:
                entries[value] = OpcodeEntry(value, name, description)
        return cls(entries=entries)
