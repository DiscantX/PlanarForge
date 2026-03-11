"""
game/ids_manager.py

Lazy-loading IDS table manager for a game installation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from core.formats.ids import IdsFile, IdsTable
from core.formats.key_biff import KeyFile
from core.util.enums import ResType
from game.installation import GameInstallation


class IdsManager:
    """
    Lazy-loads IdsTable objects from the game installation on demand.

    Searches the override directory first, then CHITIN.KEY.
    """

    def __init__(self, installation: GameInstallation) -> None:
        self._installation = installation
        self._cache: Dict[str, IdsTable] = {}
        self._key: Optional[KeyFile] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, ids_name: str) -> IdsTable:
        name = _normalize_name(ids_name)
        if name in self._cache:
            return self._cache[name]

        table = self._load_from_override(name)
        if table is None:
            table = self._load_from_key(name)

        self._cache[name] = table
        return table

    def preload(self, *ids_names: str) -> None:
        for name in ids_names:
            self.get(name)

    def clear_cache(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key_file(self) -> KeyFile:
        if self._key is None:
            self._key = KeyFile.open(self._installation.chitin_key)
        return self._key

    def _load_from_override(self, name: str) -> Optional[IdsTable]:
        override_dir = self._installation.install_path / "override"
        if not override_dir.exists():
            return None

        candidate = override_dir / f"{name}.ids"
        if not candidate.exists():
            # Case-insensitive fallback.
            matches = [p for p in override_dir.glob("*.ids") if p.stem.upper() == name]
            if not matches:
                return None
            candidate = matches[0]

        table = IdsFile.from_file(candidate)
        if table.name != name:
            table = IdsTable(name, table.entries)
        return table

    def _load_from_key(self, name: str) -> IdsTable:
        key = self._key_file()
        entry = key.find(name, ResType.IDS)
        if entry is None:
            raise FileNotFoundError(f"IDS resource {name}.IDS not found in CHITIN.KEY.")
        raw = key.read_resource(entry, self._installation)
        return IdsFile.from_bytes(raw, name=name)


def _normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("ids_name must be non-empty.")
    if "." in name:
        name = name.split(".", 1)[0]
    name = name.upper()
    if len(name) > 8:
        raise ValueError("ids_name must be at most 8 characters.")
    return name
