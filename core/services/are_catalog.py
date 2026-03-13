"""core/services/are_catalog.py

Read-only ARE (Area) catalog for UI consumers.

Mirrors the ItmCatalog pattern exactly: discovers game installations, indexes
all ARE resources from CHITIN.KEY, caches per-game JSON indices to .cache/,
and provides per-entry raw-JSON load.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional

from core.formats.are import AreFile
from core.formats.key_biff import KeyFile
from core.formats.wmp import WmpFile
from core.util.enums import ResType
from core.index import IndexEntry, ResourceIndex, SOURCE_BIFF
from core.util.resref import ResRef
from game.installation import GameInstallation, InstallationFinder
from game.string_manager import StringManager


class AreCatalog:
    """Cache-backed, read-only ARE catalog for UI consumers."""

    def __init__(
        self,
        *,
        cache_root: Path | str = ".cache",
        finder: Optional[InstallationFinder] = None,
        keyfile_cls: type[KeyFile] = KeyFile,
        string_manager_cls: type[StringManager] = StringManager,
        are_parser_cls: type[AreFile] = AreFile,
        index_cls: type[ResourceIndex] = ResourceIndex,
        parser_file: Path | str = "core/formats/are.py",
    ) -> None:
        self._cache_root = Path(cache_root)
        self._finder = finder or InstallationFinder()
        self._keyfile_cls = keyfile_cls
        self._string_manager_cls = string_manager_cls
        self._are_parser_cls = are_parser_cls
        self._index_cls = index_cls
        self._parser_file = Path(parser_file)

        self._selected_game: Optional[GameInstallation] = None
        self._key: Optional[KeyFile] = None
        self._manager: Optional[StringManager] = None
        self._index: Optional[ResourceIndex] = None
        self._area_names: dict[str, str] = {}   # resref.upper() → resolved caption
        self._progress_callback: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Game management
    # ------------------------------------------------------------------

    def list_games(self) -> list[GameInstallation]:
        return self._finder.find_all()

    def select_game(self, game_id: str) -> None:
        inst = self._finder.find(game_id)
        if inst is None:
            raise ValueError(f"Game {game_id!r} not found.")
        self._selected_game = inst
        self._key = None
        self._manager = None
        self._index = None
        self._area_names = {}

    def set_progress_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        self._progress_callback = callback

    def _report_progress(self, msg: str) -> None:
        if self._progress_callback:
            self._progress_callback(msg)

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def load_index(self, force_rebuild: bool = False) -> None:
        """Load cached ARE index or build from CHITIN.KEY."""
        inst = self._require_selected_game()
        self._ensure_runtime_handles()

        chitin_mtime = inst.chitin_key.stat().st_mtime
        parser_hash = self._parser_hash()
        cache_path = self._cache_path(inst)

        if not force_rebuild:
            cached = self._load_index(cache_path, chitin_mtime, parser_hash)
            if cached is not None:
                self._index = cached
                return

        self._report_progress("Building ARE index...")
        self._index = self._build_index()

        try:
            self._save_index(self._index, cache_path, chitin_mtime, parser_hash)
        except Exception:
            pass

    def search(self, query: str = "") -> list[IndexEntry]:
        if self._index is None:
            return []
        q = query.strip().upper()
        results = []
        for entry in self._index:
            if int(entry.res_type) != int(ResType.ARE):
                continue
            if not q:
                results.append(entry)
                continue
            resref = str(entry.resref).upper()
            display = (entry.display_name or "").upper()
            if q in resref or q in display:
                results.append(entry)
        return results

    def load_entry_data(self, entry: IndexEntry) -> dict[str, Any]:
        """Return cached JSON payload for an index entry."""
        if int(entry.res_type) != int(ResType.ARE):
            raise ValueError("Entry is not an ARE resource.")
        return entry.data or {}

    def load_are_raw(self, resref: str) -> dict[str, Any]:
        """Load and parse an ARE directly from the KEY archive, returning JSON dict."""
        self._ensure_runtime_handles()
        assert self._key is not None
        assert self._selected_game is not None

        self._report_progress(f"Loading {resref}...")
        key_entry = self._key.find(resref, ResType.ARE)
        if key_entry is None:
            raise FileNotFoundError(f"ARE {resref!r} not found in KEY.")
        raw = self._key.read_resource(key_entry, game_root=self._selected_game)
        self._report_progress(f"Parsing {resref}...")
        parsed = self._are_parser_cls.from_bytes(raw)
        return parsed.to_json()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_selected_game(self) -> GameInstallation:
        if self._selected_game is None:
            raise RuntimeError("No game selected.")
        return self._selected_game

    def _ensure_runtime_handles(self) -> None:
        inst = self._require_selected_game()
        if self._key is None:
            self._key = self._keyfile_cls.open(inst.chitin_key)
        if self._manager is None:
            self._manager = self._string_manager_cls.from_installation(inst)
        if not self._area_names:
            self._area_names = self._load_area_names()

    def _load_area_names(self) -> dict[str, str]:
        """Build a resref → resolved caption string map from WORLDMAP.WMP."""
        assert self._key is not None
        assert self._manager is not None
        assert self._selected_game is not None
        names: dict[str, str] = {}
        try:
            wmp_entry = self._key.find("WORLDMAP", ResType.WMP)
            if wmp_entry is None:
                return names
            raw = self._key.read_resource(wmp_entry, game_root=self._selected_game)
            wmp = WmpFile.from_bytes(raw)
            for resref_str, strref in wmp.area_name_map().items():
                text = self._manager.resolve(strref)
                if text:
                    names[resref_str.upper()] = text
        except Exception:
            pass
        return names

    def _build_index(self) -> ResourceIndex:
        assert self._key is not None
        assert self._selected_game is not None

        index = self._index_cls()
        are_entries = self._key.find_all(ResType.ARE)
        total = len(are_entries)

        for i, entry in enumerate(are_entries):
            if i % 50 == 0:
                self._report_progress(f"Indexing ARE {i}/{total}...")
            try:
                raw = self._key.read_resource(entry, game_root=self._selected_game)
                parsed = self._are_parser_cls.from_bytes(raw)
                data = parsed.to_json()
            except Exception:
                continue

            wed = ""
            try:
                wed = str(data.get("header", {}).get("wed_resref", ""))
            except Exception:
                pass

            resref_upper = str(entry.resref).upper()
            display_name = self._area_names.get(resref_upper) or wed

            index.add_or_update(
                resref=ResRef(str(entry.resref)),
                res_type=ResType.ARE,
                source=SOURCE_BIFF,
                data=data,
                display_name=display_name,
            )

        return index

    def _cache_path(self, inst: GameInstallation) -> Path:
        return self._cache_root / inst.game_id / "index" / "ARE_index.json"

    def _parser_hash(self) -> str:
        try:
            return hashlib.md5(self._parser_file.read_bytes()).hexdigest()[:8]
        except OSError:
            return "unknown"

    def _save_index(
        self,
        index: ResourceIndex,
        path: Path,
        chitin_mtime: float,
        parser_hash: str,
    ) -> None:
        entries: list[dict[str, Any]] = []
        for e in index:
            if int(e.res_type) != int(ResType.ARE):
                continue
            entries.append(
                {
                    "resref": str(e.resref),
                    "res_type": int(e.res_type),
                    "display_name": e.display_name,
                    "source": e.source,
                    "data": e.data,
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "chitin_mtime": chitin_mtime,
                    "parser_hash": parser_hash,
                    "entries": entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_index(
        self,
        path: Path,
        chitin_mtime: float,
        parser_hash: str,
    ) -> Optional[ResourceIndex]:
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if raw.get("chitin_mtime") != chitin_mtime:
            return None
        if raw.get("parser_hash") != parser_hash:
            return None

        index = self._index_cls()
        for e in raw.get("entries", []):
            try:
                index.add_or_update(
                    resref=ResRef(e["resref"]),
                    res_type=ResType(e["res_type"]),
                    source=e["source"],
                    data=e["data"],
                    display_name=e.get("display_name", ""),
                )
            except Exception:
                continue
        return index