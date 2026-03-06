# PlanarForge — Design Reference

> **This file is the ground truth for this project.**
>
> Claude: Before making any structural decision — adding a module, changing an
> interface, choosing between approaches — read this file first using the view
> tool. Update it in the same response as the decision that warrants the change.
> Never update it speculatively or during summarisation. If a section is
> contradicted by a later decision, update it immediately rather than letting
> the contradiction stand.

---

## Project purpose

A mod editor for Infinity Engine games (Baldur's Gate, Icewind Dale,
Planescape: Torment and their Enhanced Editions). Reads game resources
directly from installed game files via CHITIN.KEY / BIFF archives.
Outputs mods in WeiDU-compatible format.

---

## Canonical project structure

This is the intended layout. Do not deviate from it without a recorded
decision below.

```
infinity_editor/
│
├── main.py                      # Entry point, launches Dear PyGui
│
├── core/                        # All non-UI logic
│   ├── __init__.py
│   │
│   ├── formats/                 # One module per IE file format
│   │   ├── __init__.py
│   │   ├── tlk.py               # String table parser
│   │   ├── key_biff.py          # CHITIN.KEY + BIFF archive reader
│   │   ├── are.py               # Area master file
│   │   ├── wed.py               # Tileset & wall polygons
│   │   ├── tis.py               # Tile graphics
│   │   ├── mos.py               # Minimap image
│   │   ├── cre.py               # Creature
│   │   ├── itm.py               # Item
│   │   ├── spl.py               # Spell
│   │   ├── dlg.py               # Dialog tree
│   │   ├── bcs.py               # Compiled script (NOT YET IMPLEMENTED)
│   │   └── baf.py               # Script source (NOT YET IMPLEMENTED)
│   │
│   ├── project/                 # Mod project management (NOT YET IMPLEMENTED)
│   │   ├── __init__.py
│   │   ├── project.py           # Project open/save/new, dirty tracking
│   │   ├── mod_structure.py     # WeiDU .tp2 generation
│   │   └── undo_redo.py         # Command pattern undo/redo stack
│   │
│   └── util/                    # Shared helpers
│       ├── __init__.py
│       ├── binary.py            # struct read/write helpers
│       └── resref.py            # ResRef type (8-char resource names)
│
├── core/
│   └── index.py                 # Resource index — search + resolve
│
├── core/index.py                # Resource index — build, search, resolve
│
├── game/                        # Game installation interface
│   │                            # NOTE: may be renamed/reorganised later
│   ├── __init__.py
│   ├── installation.py          # Locate game dir, read CHITIN.KEY
│   └── string_manager.py        # .tlk lookup with fallback + override
│
├── ui/                          # All Dear PyGui code (NOT YET IMPLEMENTED)
│   ├── __init__.py
│   ├── app.py
│   ├── panels/
│   │   ├── file_browser.py
│   │   ├── properties.py
│   │   └── log.py
│   ├── editors/
│   │   ├── area_editor.py
│   │   ├── creature_editor.py
│   │   ├── item_editor.py
│   │   ├── spell_editor.py
│   │   ├── dialog_editor.py
│   │   └── script_editor.py
│   └── widgets/
│       ├── resref_picker.py
│       ├── strref_picker.py
│       ├── flags_editor.py
│       └── viewport.py
│
├── tools/                       # External tool integration (NOT YET IMPLEMENTED)
│   ├── weidu.py
│   └── bin/
│
├── data/
│   ├── iesdp/
│   ├── game_defs/
│   │   ├── bg1.json
│   │   ├── bg2.json
│   │   ├── iwd.json
│   │   └── pst.json
│   └── icons/
│
├── tests/
│   ├── formats/
│   ├── fixtures/
│   └── project/
│
├── docs/
│   └── format_notes.md
│
├── requirements.txt
├── README.md
└── .gitignore
```

---

## Dependency rules

These are strict. Violating them creates circular imports or inappropriate
coupling.

```
core/util/binary.py       — no project imports
core/util/resref.py       — no project imports
core/util/strref.py       — no project imports at runtime
                          — imports core/formats/tlk TYPE_CHECKING only
                            (for TlkFile type hint in resolve())

core/formats/*.py         — may import: core/util/binary, core/util/resref
                          — may NOT import: core/game/*, core/project/*, ui/*

game/installation.py      — may import: stdlib only
                          — may NOT import: core/formats/* (avoids circular deps)
                          — NOTE: package name (game/) is provisional and may change

game/string_manager.py    — may import: core/formats/tlk, core/util/strref
                          — imports core/formats/tlk at call time inside
                            from_installation() to avoid top-level circular deps
                          — imports game/installation TYPE_CHECKING only

core/formats/key_biff.py  — imports game/installation TYPE_CHECKING only
                            (for GameRoot type hint — not a runtime import)

core/index.py             — may import: core/formats/*, core/util/*,
                            game/string_manager, game/installation
                          — game/* imports are TYPE_CHECKING only

core/project/*            — may import: core/formats/*, core/game/*, core/util/*
                          — may NOT import: ui/*

ui/*                      — may import anything in core/
```

**The one-way rule:** `core/formats/` does not know about `core/game/`. The
`game_root` parameter in `key_biff.py` accepts a `GameInstallation` via duck
typing (`hasattr(game_root, "install_path")`), not via a runtime import.

---

## Module contracts

### core/util/binary.py
- `BinaryReader(data: bytes)` — wraps bytes, tracks position
- `BinaryWriter()` — accumulates bytes, returns via `to_bytes()`
- `SignatureMismatch(BinaryError)` — raised by `expect_signature()`
- All reads/writes are little-endian
- `read_resref()` returns an uppercased 8-char string (raw — not a ResRef object)
- `read_string(n)` strips trailing nulls and spaces

### core/util/resref.py
- `ResRef(value: str)` — validates and normalises on construction
- Truncates at first space or null byte before validation (handles raw binary
  padding — e.g. `'MONKTU 8'` → `'MONKTU'`)
- Allowed characters: `A-Z 0-9 _ - #`
  - `#` added for EE games (Beamdog internal resource convention)
  - If further characters are encountered in other games, add them here with
    a note of which game requires them
- Always stored uppercase; case-insensitive equality
- `ResRefError(ValueError)` on invalid input
- Empty string is a valid ResRef (represents "no resource")

### core/util/strref.py
- `StrRef(value: int | str)` — wraps a raw uint32 as stored on disk
- The uint32 encodes two fields (per IESDP):
  - Top 8 bits: file ID — `0x00` = `dialog.tlk`, `0x01` = `dialogf.tlk`
  - Low 24 bits: row index within that TLK file
- `StrRef.from_parts(file_id, tlk_index)` — construct from decoded parts
- `StrRef.NONE` — sentinel for "no string" (0xFFFFFFFF)
- `ref.raw` — full uint32 as stored on disk
- `ref.file_id` — top 8 bits (0 = male/default, 1 = female)
- `ref.tlk_index` — low 24 bits; the actual row to pass to `tlk.get()`
- `ref.is_female` — True if file_id == 1 (dialogf.tlk)
- `ref.is_none` — True if the NONE sentinel
- `str(ref)` returns the raw uint32 as decimal; `int(ref)` returns the raw uint32
- `bool(ref)` is False only for the NONE sentinel
- `ref.resolve(male_tlk, female_tlk=None) -> str` — selects the right TLK
  based on `is_female`; falls back to male_tlk if female_tlk not provided
- `ref.resolve_with(resolver: Callable[[int, int], str]) -> str` — resolver
  receives `(file_id, tlk_index)`; this is the interface string_manager implements
- `ref.to_json() -> int` — serialises the full raw uint32
- `StrRef.from_json(value: int | str) -> StrRef`
- `StrRefError(ValueError)` on invalid input
- No runtime project imports — `TlkFile` is TYPE_CHECKING only

### core/formats/ — all parsers
All format modules follow this contract without exception:

- `XxxFile.from_bytes(data: bytes) -> XxxFile` — parse from raw bytes
- `XxxFile.from_file(path) -> XxxFile` — read file then parse
- `XxxFile.to_bytes() -> bytes` — serialise back to binary
- `XxxFile.to_file(path)` — serialise and write
- `XxxFile.to_json() -> dict` — serialise to JSON-safe dict
- `XxxFile.from_json(d: dict) -> XxxFile` — deserialise from dict
- Frozen dataclasses for all data-holding types
- Latin-1 encoding for all strings
- StrRef fields use `StrRef.NONE` (0xFFFFFFFF) for absent string references
  (replaces the old bare `STRREF_NONE = 0xFFFFFFFF` integer constant)
- `0xFFFF` sentinel for absent item slot references

### game/installation.py  (path is provisional — may be renamed)
- `InstallationFinder` — lazy-scanning, cached after first call
  - `find_all() -> List[GameInstallation]`
  - `find(game_id: str) -> Optional[GameInstallation]`
  - `find_chitin(game_id: str) -> Optional[Path]`
  - `rescan()` — clears cache, forces fresh scan on next access
- `GameInstallation` — frozen dataclass: `game_id, display_name, install_path,
  chitin_key, source`
  - `from_path(game_id, path, source="manual")` — safe constructor, returns
    None if no chitin.key found
- Discovery order (first match wins per game_id): Steam → GOG → Beamdog →
  classic registry
- All registry access is guarded by `sys.platform == "win32"` so the module
  loads on Linux/macOS
- Steam discovery parses `libraryfolders.vdf` to find all library roots, not
  just the default Steam path

### game/string_manager.py
- `StringManager(base_male, base_female=None, mod_male=None, mod_female=None)`
  — direct constructor; takes `TlkFile` objects
- `StringManager.from_installation(inst, language="en_US")` — locates and
  loads TLKs from a `GameInstallation`; detects original vs EE layout
  automatically (EE: `lang/<code>/dialog.tlk`; original: `dialog.tlk` in root)
- `manager.resolve(ref: StrRef) -> str` — primary resolution method
- `manager.get(file_id: int, tlk_index: int) -> str` — callable interface
  for `StrRef.resolve_with(manager.get)`
- `manager.set_mod_tlk(male_tlk, female_tlk=None)` — load project override layer
- `manager.clear_mod_tlk()` — remove override, fall back to base game only
- `manager.has_mod` — True if a mod override is loaded
- `manager.available_languages(inst) -> List[str]` — EE language codes available
- Resolution order for female strref: mod_female → mod_male → base_female → base_male
- Resolution order for male strref:   mod_male → base_male
- Returns `""` for NONE sentinel or missing indices
- `TlkFile` contract required: `get(index: int) -> str`, `contains(index: int) -> bool`

### game/string_manager.py
- `StringManager(base_male, base_female=None, mod_male=None, mod_female=None)`
  — all args are `TlkFile` objects; only `base_male` is required
- `StringManager.from_installation(inst, language="en_US") -> StringManager`
  — detects EE vs original layout by presence of `lang/` directory;
    `language` is ignored for original games
- `StringManager.available_languages(inst) -> List[str]`
  — returns sorted language codes for EE games; empty list for originals
- `manager.get(file_id, tlk_index) -> str`
  — primary resolution callable; matches `StrRef.resolve_with()` signature
  — priority chain: female → `mod_female → mod_male → base_female → base_male`;
    male → `mod_male → base_male`; skips empty entries and falls through
- `manager.get_entry(file_id, tlk_index) -> TlkEntry | None`
  — same chain as get(), returns full TlkEntry (text + sound + flags)
- `manager.resolve(ref: StrRef) -> str`
  — convenience wrapper: `ref.resolve_with(manager.get)`
- `manager.set_mod_tlk(male_tlk, female_tlk=None)` — load mod override layer
- `manager.clear_mod_tlk()` — remove mod override layer
- `manager.has_mod_tlk -> bool`
- Imports: `core/formats/tlk`, `core/util/strref`; `game/installation` TYPE_CHECKING only

### core/index.py
- `IndexEntry(resref, res_type, display_name, source, data)` — frozen dataclass
  - `source`: `"biff"`, `"override"`, or `"project"`
  - `data`: full `to_json()` output for attribute search
  - `display_name`: pre-resolved human-readable name (empty if resource has no name)
- `ResourceIndex` — the index itself
  - `build(key, game_root, string_manager, progress_cb=None)` — build from scratch;
    indexes CHITIN.KEY (source="biff") then override dir (source="override")
  - `add_or_update(resref, res_type, source, data, display_name="")` — incremental update
  - `add_or_update_from_json(resref, res_type, source, data, string_manager)` — resolves
    display_name from parsed JSON before storing
  - `remove(resref, res_type, source)` — removes entry; promotes shadow if available
  - `search(query="", res_type=None, filters=None) -> List[IndexEntry]`
    - `query`: case-insensitive ResRef prefix OR substring in display_name OR any string
      value anywhere in `data` (recursive)
    - `res_type`: filter by ResType
    - `filters`: `dict[field_name, value | Callable]` — exact match or predicate
  - `resolve(entry, key, game_root) -> XxxFile | None` — load full parsed resource;
    dispatches by source (project→from_json, override→file read, biff→CHITIN.KEY)
  - `count_by_type() -> dict[ResType, int]`
  - `__len__`, `__iter__`, `__contains__`
- Source priority: project (2) > override (1) > biff (0)
  - Lower-priority duplicates stored in shadow; promoted on remove()
- `_PARSERS` dict — ResType → parser class (shared by build and resolve)
- `_NAME_EXTRACTORS` dict — ResType → `(parsed, string_manager) -> str`
- Override dir: `<install_root>/override/` only (type-specific folders
  Characters/Portrait/Sounds/Scripts are not indexed — see IESDP override docs)

### core/formats/key_biff.py
- `KeyFile.open(path)` — parses CHITIN.KEY
- `KeyFile.find(resref, res_type) -> Optional[ResourceEntry]`
- `KeyFile.find_all(res_type) -> List[ResourceEntry]`
- `KeyFile.read_resource(entry, game_root) -> bytes`
  - `game_root` accepts `str | Path | GameInstallation` via `_resolve_game_root()`
- `BiffFile` — direct BIFF archive reader, supports context manager
- `ResType` — IntEnum of all resource type codes

---

## CRE format — version status

This is complex enough to warrant its own section.

| Version | Games | Class | Status |
|---------|-------|-------|--------|
| V1.0 | BG1, BG2, BGEE, BG2EE | `CreHeader` | ✅ Complete, verified against IESDP |
| V9.0 | IWD, IWD:HoW, IWD:TotL | `CreHeaderV9(CreHeader)` | ✅ Complete, verified against IESDP |
| V1.2 | Planescape: Torment | `CreHeaderV12` | ❌ Known bugs — pending fix |
| V2.2 | IWD2 | not implemented | ❌ Not started |

**V1.0 / V9.0 shared prefix:** Both versions are byte-identical from
`0x0008` to `0x026F`. `_read_common_prefix()` and `_write_common_prefix()`
handle this shared region. They diverge at `0x0270`.

**V9.0 unique block:** `0x0270–0x02D7` (104 bytes) contains IWD-specific
fields (`visible`, `set_dead_var`, `secondary_death_var`, etc.). The shared
object-identity / offset tail resumes at `0x02D8`.

**V1.2 known bugs (to fix):**
- `tracking_target` read as uint32 + skip(3) instead of 32-byte char array
- `soundset` read as 25 strrefs instead of correct size
- `turn_undead_level` missing entirely

**V2.2 (IWD2):** Completely different header layout. No implementation yet.
Do not allow V2.2 files to fall through to the V1.0 parser — they must raise
`ValueError("Unsupported CRE version")`.

---

## IESDP is the ground truth

For all binary format decisions, IESDP is authoritative:
https://gibberlings3.github.io/iesdp/file_formats/ie_formats/

Do not guess field sizes or offsets. Fetch the relevant IESDP page and verify
before implementing. The history of this project includes multiple bugs caused
by assuming field sizes without checking (e.g. `unknown_profs` was 104 bytes
instead of 12, `soundset` was 32 bytes instead of 400, `SLOT_COUNT` was 38
instead of 40).

---

## Pending work

In priority order:

1. Fix CRE V1.2 (PST) parser — three known field-size bugs listed above
2. Implement CRE V2.2 (IWD2) parser
3. `core/resources.py` — `load_resource(entry, raw) -> XxxFile` dispatcher
   that maps ResType to the correct parser class. Lives in `core/` not
   `core/formats/` to avoid circular imports (it imports from all format
   modules). Decision pending on: what to return for unknown types (raise,
   return raw bytes, or return None).
5. `core/project/` — mod project management layer
6. UI layer (Dear PyGui)

---

## Decisions log

Significant decisions, with rationale. Append; never delete.

**2026-03 — ResRef character set**
Added `#` to allowed characters after encountering `DW#FPPLO` in BG2EE's
CHITIN.KEY. This is a Beamdog convention for EE internal resources. If
further games require additional characters (IWD2 uses `%` in some resrefs),
add them to `_VALID_PATTERN` in `resref.py` with a note here.

**2026-03 — ResRef space/null truncation**
`ResRef.__init__` truncates at the first space or null before validation.
Raw binary resref fields are 8 bytes and may contain trailing spaces or nulls
as padding, or leftover bytes after a shorter name. `'MONKTU 8'` is a real
example from BG2EE. Truncating at the first space is the correct behaviour.

**2026-03 — key_biff game_root duck typing**
`KeyFile.read_resource()` and `biff_path()` accept `str | Path |
GameInstallation` via `_resolve_game_root()`. Uses `hasattr(game_root,
"install_path")` rather than `isinstance` to avoid importing
`core/game/installation.py` at runtime from `core/formats/key_biff.py`,
which would violate the dependency rules above.

**2026-03 — InstallationFinder lazy cache**
`InstallationFinder` scans lazily on first access and caches the result.
`rescan()` clears the cache. This is appropriate for an editor that starts
once and runs for a session. If the tool ever becomes a library called
repeatedly in a script, callers should be aware of this.

**2026-03 — CRE bg2_extra hypothesis rejected**
An earlier hypothesis that BG2 had a 302-byte extra block not present in BG1
was wrong. The discrepancy was caused by five accumulated field-size bugs in
the V1.0 parser. The corrected sizes are: `unknown_profs` = 12 bytes,
`turn_undead_level` = 1 byte (was missing), `tracking_target` = 32-byte char
array (was uint32), `soundset` = 400 bytes (100 strrefs), `SLOT_COUNT` = 40.

**2026-03 — DESIGN.md as ground truth**
This file was created as the single authoritative reference for architectural
decisions. Claude must read it before making structural decisions and update
it in the same response as any decision that changes the architecture.

**2026-03 — game/ package location is provisional**
`installation.py` currently lives at `game/installation.py`, not
`core/game/installation.py` as the original design specified. The discrepancy
is known and will be resolved when the project structure is reorganised. Do
not assume either path is final until a decision is recorded here.

**2026-03 — all files require vetting and unit tests**
Every module in this project is to be reviewed and unit-tested before being
considered complete. Files produced in this session are first drafts. In
particular, `binary.py`'s `read_resref()` strips trailing spaces via
`read_string()` before the value reaches `ResRef`, meaning the space-
truncation fix in `ResRef.__init__` is partially redundant for the binary
reading path. Both will be reviewed when `binary.py` is vetted.

**2026-03 — StrRef as a distinct type**
TLK string indices are stored as `StrRef` objects, not bare `int`. A `StrRef`
is a stable, language-agnostic uint32 identifier. It does not hold a reference
to any TLK file. `str(ref)` returns the raw index as a decimal string;
`ref.resolve(tlk)` returns the human-readable text for a specific TLK.
The primary resolution path in the editor is `string_manager.resolve(ref)`,
which handles language and gender selection. `StrRef` imports `TlkFile` under
`TYPE_CHECKING` only, keeping it dependency-free at runtime.

**2026-03 — All format files must explicitly import from core.util**
Every file in `core/formats/` must have explicit imports for every symbol
it uses from `core/util/`. Do not assume these are available implicitly.
The standard import block for a format file that uses all three util modules is:

    from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
    from core.util.resref import ResRef
    from core.util.strref import StrRef, StrRefError

Omit only what the file genuinely does not use. This was a recurring silent
error: `cre.py` was missing `binary` and `resref` imports across multiple
sessions because the project owner was correcting it locally without flagging it.

**2026-03 — StrRef encodes file ID in top 8 bits (IESDP ground truth)**
The IESDP Notes and Conventions page confirms that a strref uint32 encodes
the TLK file selector in the top 8 bits (0x00 = dialog.tlk, 0x01 =
dialogf.tlk) and the row index in the low 24 bits. This is not a convention
imposed by the editor — it is how the IE engine reads strref fields on disk.
StrRef exposes `file_id`, `tlk_index`, and `is_female` as decoded properties.
`resolve_with()` now passes `(file_id, tlk_index)` to the resolver callable
so string_manager can select the right TLK without re-decoding the raw value.

**2026-03 — StringManager layered resolution design**
Holds up to four TLKs: base_male, base_female, mod_male, mod_female.
Resolution checks mod layer first, then base layer, with female variants
checked before male variants at each layer (mirroring engine fallback).
Override TLKs support the use case of reading both original game strings
and project-modified strings, with project strings taking priority.
`from_installation()` auto-detects original (root-level TLK) vs EE
(lang/<code>/ subdirectory) layout. `TlkFile` is imported at call time
inside `from_installation()` rather than at module level to avoid
circular import issues before tlk.py is fully integrated.

**2026-03 — StringManager design: layered resolution with mod override**
`StringManager` holds up to four TlkFiles (base_male, base_female, mod_male,
mod_female). Resolution priority for female strrefs: mod_female → mod_male →
base_female → base_male. For male: mod_male → base_male. Each step is skipped
if the TLK is not loaded or the index is not present. This mirrors the engine
fallback behaviour and supports the use case of reading original game strings
alongside mod-modified strings without merging them.

`from_installation()` detects original vs EE layout by checking for a `lang/`
subdirectory. The `language` parameter is only used for EE games.

TOH/TOT override file support (IWD/BG2 talk table override format) is deferred.

**2026-03 — ResourceIndex design: JSON-backed, source-layered, shadow store**
`core/index.py` builds once from CHITIN.KEY + override dir, then is maintained
incrementally. Each (resref, res_type) key stores the highest-priority source as
primary; lower-priority duplicates go to a shadow store and are promoted on remove().
The `data` field holds the full `to_json()` output so search can match any attribute
(weight, flags, tooltip, etc.) without re-parsing. `_PARSERS` and `_NAME_EXTRACTORS`
are the single place where ResType → parser/name mappings are defined; resolve() reuses
_PARSERS rather than having a separate dispatcher. Override directory indexed as
`<install_root>/override/` only — per IESDP, this covers all general resource types.

**2026-03 — Dependency policy on non-stdlib libraries**
Standard library preferred. Non-standard libraries permitted case-by-case; must be
well-maintained. Approved so far: `watchdog` (for core/watcher.py, not yet implemented).

