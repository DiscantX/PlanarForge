"""
core/index.py

Resource index for fast search across all game resources.

The index is built once from a game installation (CHITIN.KEY + override
directory) and then maintained incrementally as resources are created,
modified, or deleted — either by the editor or by external file changes
detected by the watcher (core/watcher.py, not yet implemented).

Each entry stores:
    resref:       ResRef   — the resource name
    res_type:     ResType  — file type (ITM, CRE, SPL, etc.)
    display_name: str      — pre-resolved human-readable name (may be empty)
    source:       str      — "biff", "override", or "project"
    data:         dict     — full to_json() output for attribute search

Source priority (highest wins per resref+res_type):
    project > override > biff

Search
------
    index.search()                          — all entries
    index.search(query="sword")             — ResRef prefix OR any string in data
    index.search(res_type=ResType.ITM)      — by type
    index.search(filters={"base_weight": lambda w: w < 5})
    index.search(query="sword", res_type=ResType.ITM, filters={...})

Resolve
-------
    resource = index.resolve(entry, key, game_root)
    # returns the fully parsed XxxFile object

Update interface (used by editor and future watcher)
------------------------------------------------------
    index.add_or_update(resref, res_type, source, data, display_name="")
    index.remove(resref, res_type, source)

Override directory
------------------
Per IESDP, <install_root>/override/ is the general-purpose override folder
for resource types ITM, CRE, SPL, DLG, ARE, WED, etc.  Type-specific
folders (Characters, Portrait, Sounds, Scripts) are not indexed here as
they contain non-resource file types outside our scope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, TYPE_CHECKING

from core.formats.key_biff import KeyFile, ResType, ResourceEntry
from core.formats.are  import AreFile
from core.formats.cre  import CreFile
from core.formats.dlg  import DlgFile
from core.formats.itm  import ItmFile
from core.formats.mos  import MosFile
from core.formats.spl  import SplFile
from core.formats.tis  import TisFile
from core.formats.wed  import WedFile
from core.util.resref  import ResRef
from core.util.strref  import StrRef

if TYPE_CHECKING:
    from game.installation   import GameInstallation
    from game.string_manager import StringManager


# ---------------------------------------------------------------------------
# Source constants
# ---------------------------------------------------------------------------

SOURCE_BIFF     = "biff"
SOURCE_OVERRIDE = "override"
SOURCE_PROJECT  = "project"

_SOURCE_PRIORITY = {SOURCE_BIFF: 0, SOURCE_OVERRIDE: 1, SOURCE_PROJECT: 2}


# ---------------------------------------------------------------------------
# Parser dispatch table
# ---------------------------------------------------------------------------

# Maps ResType → parser class with a from_bytes() classmethod.
# Types not in this table are indexed by ResRef and type only (no data/name).
_PARSERS: Dict[int, type] = {
    int(ResType.ARE):  AreFile,
    int(ResType.CRE):  CreFile,
    int(ResType.DLG):  DlgFile,
    int(ResType.ITM):  ItmFile,
    int(ResType.MOS):  MosFile,
    int(ResType.SPL):  SplFile,
    int(ResType.TIS):  TisFile,
    int(ResType.WED):  WedFile,
}

# Maps ResType → function(parsed_resource, StringManager) → str.
# Returns the best human-readable name for a resource of that type.
# Types not in this table get an empty display_name.
def _name_itm(r: ItmFile,  sm: "StringManager") -> str: return sm.resolve(r.header.identified_name)
def _name_spl(r: SplFile,  sm: "StringManager") -> str: return sm.resolve(r.header.identified_name)
def _name_cre(r: CreFile,  sm: "StringManager") -> str: return sm.resolve(r.header.name)
def _name_are(r: AreFile,  sm: "StringManager") -> str: return str(r.header.wed_resref)
def _name_dlg(r: DlgFile,  sm: "StringManager") -> str: return ""   # identity is the ResRef

_NAME_EXTRACTORS: Dict[int, Callable] = {
    int(ResType.ITM): _name_itm,
    int(ResType.SPL): _name_spl,
    int(ResType.CRE): _name_cre,
    int(ResType.ARE): _name_are,
    int(ResType.DLG): _name_dlg,
}


# ---------------------------------------------------------------------------
# IndexEntry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndexEntry:
    """
    A single entry in the resource index.

    Attributes
    ----------
    resref:       Resource name.
    res_type:     Resource type code.
    display_name: Pre-resolved human-readable name, or empty string.
    source:       Where this entry came from: "biff", "override", "project".
    data:         Full to_json() output.  Use for attribute search and display.
                  Empty dict for resource types with no parser.
    """
    resref:       ResRef
    res_type:     ResType
    display_name: str
    source:       str
    data:         dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def extension(self) -> str:
        """File extension for this resource type, e.g. 'itm'."""
        try:
            return ResType(self.res_type).name.lower()
        except ValueError:
            return "???"


# ---------------------------------------------------------------------------
# ResourceIndex
# ---------------------------------------------------------------------------

class ResourceIndex:
    """
    Indexed view over all game resources, supporting fast multi-field search.

    Build once from a game installation, then maintain incrementally via
    add_or_update() and remove() as resources change.

    The index is keyed by (resref, res_type).  When the same resource exists
    in multiple sources, the highest-priority source wins:
        project > override > biff
    """

    def __init__(self) -> None:
        # Primary store: (resref_str, res_type_int) → IndexEntry
        self._entries: Dict[Tuple[str, int], IndexEntry] = {}
        # Shadow store for lower-priority duplicates:
        # (resref_str, res_type_int) → {source: IndexEntry}
        self._shadow:  Dict[Tuple[str, int], Dict[str, IndexEntry]] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        key:            KeyFile,
        game_root:      "GameInstallation | Path | str",
        string_manager: "StringManager",
        *,
        progress_cb:    Optional[Callable[[int, int, str], None]] = None,
    ) -> None:
        """
        Build the index from a game installation.

        Indexes all resources from CHITIN.KEY (source="biff") and then
        all files in the override directory (source="override").

        progress_cb, if provided, is called as (current, total, resref_str)
        after each resource is processed — useful for progress bars.
        """
        self._entries.clear()
        self._shadow.clear()

        all_entries = list(key.iter_resources())
        total = len(all_entries)

        for i, res_entry in enumerate(all_entries):
            self._index_key_entry(
                res_entry, key, game_root, string_manager, SOURCE_BIFF
            )
            if progress_cb:
                progress_cb(i + 1, total, str(res_entry.resref))

        # Index override directory on top
        override_dir = Path(getattr(game_root, "install_path", game_root)) / "override"
        if override_dir.is_dir():
            self._index_override_dir(override_dir, string_manager)

    def _index_key_entry(
        self,
        res_entry:      ResourceEntry,
        key:            KeyFile,
        game_root:      Any,
        string_manager: "StringManager",
        source:         str,
    ) -> None:
        """Parse one ResourceEntry from CHITIN.KEY and add it to the index."""
        try:
            raw = key.read_resource(res_entry, game_root=game_root)
        except Exception:
            return  # skip unreadable resources silently

        self._index_raw(
            resref       = res_entry.resref,
            res_type     = ResType(res_entry.res_type),
            source       = source,
            raw          = raw,
            string_manager = string_manager,
        )

    def _index_override_dir(
        self,
        override_dir:   Path,
        string_manager: "StringManager",
    ) -> None:
        """Index all recognised resource files in the override directory."""
        # Build extension → ResType map from _PARSERS keys
        ext_map: Dict[str, ResType] = {}
        for rt in ResType:
            ext_map[rt.name.lower()] = rt

        for path in override_dir.iterdir():
            if not path.is_file():
                continue
            ext = path.suffix.lstrip(".").lower()
            if ext not in ext_map:
                continue
            res_type = ext_map[ext]
            resref   = ResRef(path.stem.upper()[:8])
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            self._index_raw(
                resref         = resref,
                res_type       = res_type,
                source         = SOURCE_OVERRIDE,
                raw            = raw,
                string_manager = string_manager,
            )

    def _index_raw(
        self,
        resref:         ResRef,
        res_type:       ResType,
        source:         str,
        raw:            bytes,
        string_manager: "StringManager",
    ) -> None:
        """Parse raw bytes and add/update the index entry."""
        res_type_int = int(res_type)
        parser       = _PARSERS.get(res_type_int)
        data: dict   = {}
        display_name = ""

        if parser is not None:
            try:
                parsed       = parser.from_bytes(raw)
                data         = parsed.to_json()
                extractor    = _NAME_EXTRACTORS.get(res_type_int)
                if extractor is not None:
                    display_name = extractor(parsed, string_manager) or ""
            except Exception:
                pass  # malformed resource — index without data

        entry = IndexEntry(
            resref       = resref,
            res_type     = res_type,
            display_name = display_name,
            source       = source,
            data         = data,
        )
        self._store(entry)

    # ------------------------------------------------------------------
    # Update interface (editor + future watcher)
    # ------------------------------------------------------------------

    def add_or_update(
        self,
        resref:       ResRef,
        res_type:     ResType,
        source:       str,
        data:         dict,
        display_name: str = "",
    ) -> None:
        """
        Add or update a single index entry.

        If a higher-priority source already exists for this (resref, res_type),
        this entry is stored in the shadow but does not become the primary.
        If this source has higher priority, it becomes primary and the
        previous primary is demoted to shadow.
        """
        entry = IndexEntry(
            resref       = resref,
            res_type     = res_type,
            display_name = display_name,
            source       = source,
            data         = data,
        )
        self._store(entry)

    def add_or_update_from_json(
        self,
        resref:         ResRef,
        res_type:       ResType,
        source:         str,
        data:           dict,
        string_manager: "StringManager",
    ) -> None:
        """
        Add or update an entry from a JSON dict, resolving display_name.

        Convenience for the project layer, which stores resources as JSON.
        """
        res_type_int = int(res_type)
        display_name = ""
        parser       = _PARSERS.get(res_type_int)
        if parser is not None:
            try:
                parsed       = parser.from_json(data)
                extractor    = _NAME_EXTRACTORS.get(res_type_int)
                if extractor:
                    display_name = extractor(parsed, string_manager) or ""
            except Exception:
                pass
        self.add_or_update(resref, res_type, source, data, display_name)

    def remove(self, resref: ResRef, res_type: ResType, source: str) -> None:
        """
        Remove an entry for a specific source.

        If a lower-priority shadow entry exists, it is promoted to primary.
        """
        key = (str(resref), int(res_type))

        # Remove from shadow if present
        if key in self._shadow:
            self._shadow[key].pop(source, None)
            if not self._shadow[key]:
                del self._shadow[key]

        # Remove from primary and promote best shadow if any
        primary = self._entries.get(key)
        if primary is not None and primary.source == source:
            del self._entries[key]
            # Promote highest-priority shadow
            shadows = self._shadow.get(key, {})
            if shadows:
                best = max(shadows.values(),
                           key=lambda e: _SOURCE_PRIORITY.get(e.source, -1))
                self._entries[key] = best

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query:    str                              = "",
        res_type: Optional[ResType]               = None,
        filters:  Optional[Dict[str, Any]]        = None,
    ) -> List[IndexEntry]:
        """
        Search the index.

        Parameters
        ----------
        query:
            Case-insensitive string matched against:
            - ResRef (prefix match)
            - display_name (substring match)
            - Any string value anywhere in data (recursive substring match)
            Empty string matches everything.
        res_type:
            If given, only entries of this type are returned.
        filters:
            Dict of {field_name: value_or_predicate}.  Each key is looked
            up in the entry's data dict.  Value may be:
            - A plain value: matched with ==
            - A callable: called with the field value, must return True to match

        Returns entries in index order (build order).
        """
        q = query.strip().lower()
        results: List[IndexEntry] = []

        for entry in self._entries.values():
            if res_type is not None and entry.res_type != res_type:
                continue
            if q and not self._matches_query(entry, q):
                continue
            if filters and not self._matches_filters(entry, filters):
                continue
            results.append(entry)

        return results

    @staticmethod
    def _matches_query(entry: IndexEntry, q: str) -> bool:
        """True if q matches the entry's resref, display_name, or any data value."""
        if str(entry.resref).lower().startswith(q):
            return True
        if q in entry.display_name.lower():
            return True
        return ResourceIndex._search_dict(entry.data, q)

    @staticmethod
    def _search_dict(d: Any, q: str) -> bool:
        """Recursively search any string value in a nested dict/list."""
        if isinstance(d, str):
            return q in d.lower()
        if isinstance(d, dict):
            return any(ResourceIndex._search_dict(v, q) for v in d.values())
        if isinstance(d, list):
            return any(ResourceIndex._search_dict(v, q) for v in d)
        return False

    @staticmethod
    def _matches_filters(entry: IndexEntry, filters: Dict[str, Any]) -> bool:
        """True if all filters match against the entry's data dict."""
        for field_name, predicate in filters.items():
            value = entry.data.get(field_name)
            if value is None:
                return False
            if callable(predicate):
                if not predicate(value):
                    return False
            else:
                if value != predicate:
                    return False
        return True

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    def resolve(
        self,
        entry:     IndexEntry,
        key:       KeyFile,
        game_root: Any,
    ) -> Any:
        """
        Load and return the fully parsed resource for an IndexEntry.

        Uses the entry's source to determine where to read from:
        - "biff" / "override": reads via KeyFile or override directory
        - "project": reconstructs from entry.data via from_json()

        Returns None if the resource cannot be loaded.
        """
        res_type_int = int(entry.res_type)
        parser       = _PARSERS.get(res_type_int)
        if parser is None:
            return None

        try:
            if entry.source == SOURCE_PROJECT:
                return parser.from_json(entry.data)

            if entry.source == SOURCE_OVERRIDE:
                root = Path(getattr(game_root, "install_path", game_root))
                ext  = entry.extension
                path = root / "override" / f"{entry.resref}.{ext}"
                if path.is_file():
                    return parser.from_bytes(path.read_bytes())

            # biff (and override fallback)
            key_entry = key.find(entry.resref, entry.res_type)
            if key_entry is not None:
                raw = key.read_resource(key_entry, game_root=game_root)
                return parser.from_bytes(raw)

        except Exception:
            return None

        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[IndexEntry]:
        return iter(self._entries.values())

    def __contains__(self, item: Tuple[ResRef, ResType]) -> bool:
        resref, res_type = item
        return (str(resref), int(res_type)) in self._entries

    def count_by_type(self) -> Dict[ResType, int]:
        """Return a dict of {ResType: entry_count} for all indexed types."""
        counts: Dict[ResType, int] = {}
        for entry in self._entries.values():
            counts[entry.res_type] = counts.get(entry.res_type, 0) + 1
        return counts

    def __repr__(self) -> str:
        return f"ResourceIndex({len(self._entries)} entries)"

    # ------------------------------------------------------------------
    # Internal storage helpers
    # ------------------------------------------------------------------

    def _store(self, entry: IndexEntry) -> None:
        """
        Store an entry, respecting source priority.

        The highest-priority source becomes primary; others go to shadow.
        """
        key      = (str(entry.resref), int(entry.res_type))
        priority = _SOURCE_PRIORITY.get(entry.source, -1)

        existing = self._entries.get(key)
        if existing is None:
            # First entry for this key
            self._entries[key] = entry
            return

        existing_priority = _SOURCE_PRIORITY.get(existing.source, -1)

        if priority > existing_priority:
            # New entry wins — demote existing to shadow
            self._entries[key] = entry
            shadows = self._shadow.setdefault(key, {})
            shadows[existing.source] = existing
        else:
            # Existing wins — new entry goes to shadow
            shadows = self._shadow.setdefault(key, {})
            shadows[entry.source] = entry
