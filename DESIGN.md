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
├── game/                        # Game installation interface
│   │                            # NOTE: may be renamed/reorganised later
│   ├── __init__.py
│   ├── installation.py          # Locate game dir, read CHITIN.KEY
│   └── string_manager.py        # .tlk lookup with fallback + override (NOT YET IMPLEMENTED)
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

core/formats/key_biff.py  — imports game/installation TYPE_CHECKING only
                            (for GameRoot type hint — not a runtime import)

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
- `StrRef(value: int | str)` — wraps a uint32 TLK index
- `StrRef.NONE` — sentinel for "no string" (0xFFFFFFFF)
- `str(ref)` returns the raw index as a decimal string — e.g. `"12345"`
- `int(ref)` returns the raw index
- `bool(ref)` is False only for the NONE sentinel
- `ref.is_none` — True if the NONE sentinel
- `ref.resolve(tlk: TlkFile) -> str` — low-level resolution against a specific TLK;
  returns `""` for NONE. Prefer `string_manager.resolve(ref)` in editor code.
- `ref.resolve_with(resolver: Callable[[int], str]) -> str` — resolution via
  any callable; useful for testing and for wrapping string_manager
- `ref.to_json() -> int` — serialises as integer (not string)
- `StrRef.from_json(value: int | str) -> StrRef` — accepts both for robustness
- `StrRefError(ValueError)` on invalid input
- StrRef has no reference to any TLK file — it is a stable, language-agnostic
  identifier. Resolution context (language, gender) is the caller's concern.

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
4. `core/game/string_manager.py` — TLK lookup with override support
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

