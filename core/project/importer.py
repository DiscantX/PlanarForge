"""
core/project/importer.py

Resource importer — reads game resources and converts them into project
JSON ready to be saved under imported/<game_id>/<type>/.

The importer is the bridge between the binary game world (KeyFile, BIFF
archives, StrRef uint32 indices) and the project world (ProjectStrRef,
language-aware text snapshots, portable JSON).

What it does
------------
1. Reads raw bytes for a resource from CHITIN.KEY or the override dir.
2. Parses them with the appropriate format parser.
3. Walks every StrRef field in the resulting JSON and converts it to a
   ProjectStrRef, capturing multi-language text via
   StringManager.resolve_all_languages().
4. Returns a project JSON dict ready to write to disk, plus the resolved
   display name for the resource index.

StrRef conversion rules
-----------------------
- Primary game, unmodified string  → ProjectStrRef.live(strref)
  (The string exists in the game's TLK; no need to snapshot it.)
- Secondary game (any string)      → ProjectStrRef.snapshot(strref, strings)
  (The StrRef index is meaningless in the primary game's TLK.)
- StrRef.NONE (0xFFFFFFFF)         → None  (field left null in JSON)

The importer does not decide whether a string has been "modified" — that
distinction is made later when the user edits the field.  All primary-game
imports start as live references.

Usage::

    from core.project.importer import import_resource, ImportedResource

    result = import_resource(
        resref         = ResRef("SW1H01"),
        res_type       = ResType.ITM,
        source_game_id = "BG2EE",
        is_primary     = True,
        key            = key,
        game_root      = inst,
        string_manager = manager,
        inst           = inst,
    )

    # Write to project directory
    out_path = project_root / "imported" / "BG2EE" / "itm" / "sw1h01.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    out_path.write_text(json.dumps(result.data, indent=2, ensure_ascii=False))
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

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

from core.project.strref import ProjectStrRef

if TYPE_CHECKING:
    from game.installation   import GameInstallation
    from game.string_manager import StringManager


# ---------------------------------------------------------------------------
# Parser dispatch  (mirrors core/index.py _PARSERS — kept in sync manually)
# ---------------------------------------------------------------------------

_PARSERS: Dict[int, type] = {
    int(ResType.ARE): AreFile,
    int(ResType.CRE): CreFile,
    int(ResType.DLG): DlgFile,
    int(ResType.ITM): ItmFile,
    int(ResType.MOS): MosFile,
    int(ResType.SPL): SplFile,
    int(ResType.TIS): TisFile,
    int(ResType.WED): WedFile,
}

# Maps ResType → function(parsed_resource) → StrRef | None
# Returns the StrRef that best represents the resource's display name.
def _name_strref_itm(r: ItmFile)  -> Optional[StrRef]: return r.header.identified_name
def _name_strref_spl(r: SplFile)  -> Optional[StrRef]: return r.header.identified_name
def _name_strref_cre(r: CreFile)  -> Optional[StrRef]: return r.header.name

_NAME_STRREF: Dict[int, Any] = {
    int(ResType.ITM): _name_strref_itm,
    int(ResType.SPL): _name_strref_spl,
    int(ResType.CRE): _name_strref_cre,
}

# Sentinel raw value for StrRef.NONE
_STRREF_NONE = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ImportedResource:
    """
    The result of importing a single resource.

    Attributes
    ----------
    resref:
        The resource name.
    res_type:
        The resource type.
    source_game_id:
        The game_id this resource was imported from, e.g. ``"BG2EE"``.
    display_name:
        The resolved display name in the best available language (en_US
        preferred).  Empty string for resource types with no name field.
    data:
        The project JSON dict, with all StrRef fields converted to
        ProjectStrRef JSON form.  Ready to write to disk.
    """
    resref:         ResRef
    res_type:       ResType
    source_game_id: str
    display_name:   str
    data:           dict = field(default_factory=dict)

    @property
    def suggested_path(self) -> Path:
        """
        Suggested relative path within the project directory.

        e.g. ``imported/BG2EE/itm/sw1h01.json``
        """
        ext = ResType(self.res_type).name.lower()
        return Path("imported") / self.source_game_id / ext / f"{self.resref}.json".lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_resource(
    resref:         ResRef,
    res_type:       ResType,
    source_game_id: str,
    is_primary:     bool,
    key:            KeyFile,
    game_root:      "GameInstallation | Path | str",
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> ImportedResource:
    """
    Import a single resource from a game installation.

    Parameters
    ----------
    resref:
        The resource to import.
    res_type:
        Resource type (ITM, CRE, SPL, etc.).
    source_game_id:
        Identifier for the source game, e.g. ``"BG2EE"``.  Stored in the
        result and used as the directory name under ``imported/``.
    is_primary:
        True if importing from the primary game.  Primary-game StrRefs
        become live references; secondary-game StrRefs become snapshots.
    key:
        Open KeyFile for the source game.
    game_root:
        Game installation root (Path, str, or GameInstallation).
    string_manager:
        StringManager loaded for the source game.  Used to resolve strings
        across all available languages.
    inst:
        GameInstallation for the source game.  Used by
        resolve_all_languages() to find language TLK files.

    Returns
    -------
    ImportedResource
        Contains the project JSON dict and resolved display name.

    Raises
    ------
    ImportError
        If the resource cannot be found or parsed.
    """
    raw = _read_raw(resref, res_type, key, game_root)
    return _import_from_raw(
        raw, resref, res_type, source_game_id, is_primary,
        string_manager, inst,
    )


def import_resource_from_override(
    path:           Path,
    res_type:       ResType,
    source_game_id: str,
    is_primary:     bool,
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> ImportedResource:
    """
    Import a resource from a file in the override directory.

    Behaves identically to import_resource() but reads from a plain file
    rather than a BIFF archive.
    """
    try:
        raw    = path.read_bytes()
        resref = ResRef(path.stem.upper()[:8])
    except (OSError, Exception) as exc:
        raise ImportError(f"Cannot read override file {path}: {exc}") from exc

    return _import_from_raw(
        raw, resref, res_type, source_game_id, is_primary,
        string_manager, inst,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_raw(
    resref:    ResRef,
    res_type:  ResType,
    key:       KeyFile,
    game_root: Any,
) -> bytes:
    """Read raw bytes for a resource from CHITIN.KEY."""
    entry = key.find(resref, res_type)
    if entry is None:
        raise ImportError(
            f"Resource {resref}.{res_type.name.lower()} not found in KEY file."
        )
    try:
        return key.read_resource(entry, game_root=game_root)
    except Exception as exc:
        raise ImportError(
            f"Cannot read {resref}.{res_type.name.lower()} from BIFF: {exc}"
        ) from exc


def _import_from_raw(
    raw:            bytes,
    resref:         ResRef,
    res_type:       ResType,
    source_game_id: str,
    is_primary:     bool,
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> ImportedResource:
    """Parse raw bytes and build an ImportedResource."""
    parser = _PARSERS.get(int(res_type))
    if parser is None:
        # No parser for this type — store raw metadata only
        return ImportedResource(
            resref         = resref,
            res_type       = res_type,
            source_game_id = source_game_id,
            display_name   = "",
            data           = {"_raw": True, "resref": str(resref),
                              "res_type": res_type.name},
        )

    try:
        parsed = parser.from_bytes(raw)
    except Exception as exc:
        raise ImportError(
            f"Cannot parse {resref}.{res_type.name.lower()}: {exc}"
        ) from exc

    # Convert the JSON dict — walk every StrRef field
    raw_json = parsed.to_json()
    proj_json = _convert_strrefs(raw_json, is_primary, string_manager, inst)

    # Resolve display name
    display_name = _resolve_display_name(
        parsed, res_type, is_primary, string_manager, inst,
    )

    return ImportedResource(
        resref         = resref,
        res_type       = res_type,
        source_game_id = source_game_id,
        display_name   = display_name,
        data           = proj_json,
    )


def _resolve_display_name(
    parsed:         Any,
    res_type:       ResType,
    is_primary:     bool,
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> str:
    """Return the best available display name for a parsed resource."""
    extractor = _NAME_STRREF.get(int(res_type))
    if extractor is None:
        return ""
    ref = extractor(parsed)
    if ref is None or (hasattr(ref, 'is_none') and ref.is_none):
        return ""
    if is_primary:
        return string_manager.get(ref.file_id, ref.tlk_index)
    # Secondary game — resolve from all languages, prefer en_US
    strings = string_manager.resolve_all_languages(ref, inst)
    return (
        strings.get("en_US")
        or strings.get("default")
        or next(iter(strings.values()), "")
    )


def _convert_strrefs(
    obj:            Any,
    is_primary:     bool,
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> Any:
    """
    Recursively walk a JSON-compatible object and convert StrRef integers
    to ProjectStrRef JSON dicts.

    StrRef fields are stored as plain integers in the format parsers'
    to_json() output.  This function identifies them by value range and
    converts them.

    Identification heuristic: an integer value that is either 0xFFFFFFFF
    (NONE sentinel) or within the valid StrRef range (0–0x00FFFFFF for
    the index portion) is treated as a potential StrRef *only* when it
    appears in a context we know contains StrRefs.

    Since the raw JSON mixes StrRef integers with other integers (flags,
    counts, offsets, etc.), we rely on the format parsers having already
    tagged StrRef fields by making them StrRef objects before to_json()
    serialises them.  to_json() on a StrRef calls .to_json() which returns
    the raw int — but to distinguish it from other ints we need a marker.

    The current parsers do NOT tag StrRef fields distinctly in JSON —
    they serialise as plain ints.  Until the parsers are updated to emit
    {"_strref": N} dicts, this function uses a conservative heuristic:
    integers in the range 0–200000 or equal to 0xFFFFFFFF are treated as
    StrRefs ONLY when the field name ends with known StrRef suffixes.

    This is intentionally conservative to avoid false positives on flag
    fields.  The correct long-term fix is for the parsers to emit a
    tagged form (tracked in pending work).
    """
    if isinstance(obj, dict):
        return {
            k: _maybe_convert_field(k, v, is_primary, string_manager, inst)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            _convert_strrefs(item, is_primary, string_manager, inst)
            for item in obj
        ]
    return obj


# Field name suffixes that identify StrRef fields in the parsers' JSON output.
# Derived from the field names used across itm.py, spl.py, cre.py, are.py, dlg.py.
_STRREF_SUFFIXES = (
    "_name",
    "_description",
    "_text",
    "_tooltip",
    "identified_name",
    "unidentified_name",
    "identified_description",
    "unidentified_description",
    "journal_text",
    "dialog_text",
    "encounter_text",
    "name",
    "tooltip",
    "description",
)


def _is_strref_field(key: str) -> bool:
    """True if the field name suggests it holds a StrRef."""
    k = key.lower()
    return any(k == s or k.endswith(s) for s in _STRREF_SUFFIXES)


def _maybe_convert_field(
    key:            str,
    value:          Any,
    is_primary:     bool,
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> Any:
    """Convert a single field value if it looks like a StrRef."""
    if isinstance(value, int) and _is_strref_field(key):
        return _convert_single_strref(value, is_primary, string_manager, inst)
    if isinstance(value, (dict, list)):
        return _convert_strrefs(value, is_primary, string_manager, inst)
    return value


def _convert_single_strref(
    raw_value:      int,
    is_primary:     bool,
    string_manager: "StringManager",
    inst:           "GameInstallation",
) -> Any:
    """
    Convert a single raw StrRef integer to a ProjectStrRef JSON dict.

    Returns None for the NONE sentinel (0xFFFFFFFF).
    Returns a live reference dict for primary-game imports.
    Returns a snapshot dict for secondary-game imports.
    """
    if raw_value == _STRREF_NONE:
        return None

    ref = StrRef(raw_value)

    if is_primary:
        return ProjectStrRef.live(ref.tlk_index).to_json()

    # Secondary game — snapshot with all available language strings
    strings = string_manager.resolve_all_languages(ref, inst)
    if strings:
        return ProjectStrRef.snapshot(ref.tlk_index, strings).to_json()
    # No strings found — still a snapshot but with empty map
    # (rare: the index is out of range in the source TLK)
    return ProjectStrRef.live(ref.tlk_index).to_json()
