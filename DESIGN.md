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
│   │   ├── ids.py               # IDS file parser → IdsTable
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
│   ├── project/                 # Mod project management
│   │   ├── __init__.py
│   │   ├── project.py           # Project open/save/new, dirty tracking
│   │   ├── strref.py            # ProjectStrRef — three-variant string reference
│   │   ├── importer.py          # Import resources from game; snapshot strings
│   │   ├── mod_structure.py     # WeiDU .tp2 + .tra generation
│   │   └── undo_redo.py         # Command pattern undo/redo stack
│   │
│   ├── services/                # Runtime services over bundled or indexed data
│   │   ├── __init__.py
│   │   ├── character_service.py
│   │   ├── itm_catalog.py
│   │   └── opcode_registry.py   # Loads data/opcodes/*.json; resolves opcode → name/desc
│   │
│   └── index.py                 # Resource index — build, search, resolve
│   │
│   └── util/                    # Shared helpers and primitive types
│       ├── __init__.py
│       ├── binary.py            # struct read/write helpers
│       ├── enums.py             # All IntEnum / IntFlag definitions (centralised)
│       ├── resref.py            # ResRef type (8-char resource names)
│       ├── strref.py            # StrRef type (uint32 TLK reference)
│       └── idsref.py            # IdsRef type (integer + IDS file name)
│
├── game/                        # Game installation interface ONLY
│   │                            # Reserve for files that deal with game installations.
│   │                            # NOTE: installation.py → installation_manager.py (todo)
│   ├── __init__.py
│   ├── installation.py          # Locate game dir, read CHITIN.KEY
│   ├── string_manager.py        # .tlk lookup with fallback + override
│   └── ids_manager.py           # Lazy-loads IdsTable objects from installation on demand
│
├── ui/                          # All Dear PyGui code
│   ├── __init__.py
│   ├── app.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── titlebar.py
│   │   ├── editor_toolbar.py
│   │   ├── resource_browser_pane.py
│   │   └── progress_handler.py
│   ├── editors/
│   │   ├── __init__.py
│   │   ├── character_editor.py
│   │   └── item_editor.py
│   ├── skin/
│   │   └── infinity/
│   │       ├── __init__.py
│   │       ├── assets.py
│   │       ├── screen_panel.py
│   │       ├── components/
│   │       └── data/
│   │           └── manifest_default.json
│   └── widgets/
│       ├── resref_picker.py
│       ├── strref_picker.py
│       ├── flags_editor.py
│       └── viewport.py
│
├── tools/                       # Utility scripts and external tool integration
│   ├── resource_explorer.py     # Interactive CLI resource explorer (implemented)
│   ├── weidu.py                 # NOT YET IMPLEMENTED
│   └── bin/
│
├── data/
│   ├── iesdp/
│   ├── game_defs/
│   │   ├── bg1.json
│   │   ├── bg2.json
│   │   ├── iwd.json
│   │   └── pst.json
│   ├── opcodes/                 # Bundled opcode tables (int → name + description)
│   │   ├── bgee.json            # BGEE / BG2EE opcodes (~300 entries from IESDP)
│   │   ├── iwd.json             # IWD variant opcodes (where they differ)
│   │   └── pst.json             # PST variant opcodes (where they differ)
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
├── .cache/                      # Runtime caches (gitignored)
│   └── <GAME_ID>/
│       └── <TYPE>_index.json
│
├── requirements.txt
├── README.md
└── .gitignore
```

---

## Mod project on-disk layout

A mod project is a self-contained directory. The structure is:

```
<project_root>/
├── project.json                  # Metadata, game references, export settings
├── imported/
│   ├── <game_id>/                # e.g. BG2EE/, BG1EE/  (primary and secondary)
│   │   ├── itm/
│   │   │   └── sw1h01.json
│   │   └── cre/
│   │       └── guard01.json
│   └── ...
├── created/
│   ├── itm/
│   │   └── mymods01.json
│   └── cre/
│       └── myvillain.json
└── strings/
    ├── english/
    │   └── default.tra           # WeiDU translation file, maintained live
    ├── french/
    │   └── default.tra
    └── ...
```

**imported/ vs created/:**
- `imported/` — resources pulled from a game installation. The source game
  is recorded in the subdirectory name. The same ResRef can exist under
  multiple game IDs without collision (e.g. BG1EE and BG2EE both have sw1h01).
  Importing and modifying an existing resource generates a `COPY_EXISTING` +
  patch block in the WeiDU output.
- `created/` — user-authored resources with no game original. Generates
  `ADD_ITEM` / `ADD_CREATURE` etc. in WeiDU output.

**project.json structure:**
```json
{
  "name": "My Total Conversion",
  "version": "0.1.0",
  "primary_game": "BG2EE",
  "secondary_games": ["BG1EE"],
  "author": "",
  "description": "",
  "export": {
    "tp2_name": "my_mod",
    "languages": ["en_US", "fr_FR", "de_DE"]
  }
}
```
`primary_game` and `secondary_games` use `GameInstallation.game_id` values.
`export.languages` controls which `.tra` files are generated; only languages
present in at least one resource's strings map are exported.

**strings/ directory:**
`.tra` files are maintained as a live working copy — updated whenever a
string is added or modified in any resource, not only at export time. One
subdirectory per language, matching WeiDU's conventional `.tra` layout.
The project does NOT maintain its own `dialog.tlk`. New strings become
`@N` WeiDU string references assigned at install time.

**Projects are self-contained and do not share files.**
Two projects that import the same resource each have their own copy under
their own `imported/` directory. The base game installation is shared
(read-only), but working copies are not.

---

## ProjectStrRef — three-variant string reference

`core/project/strref.py` — distinct from `core/util/strref.py` (which is a
binary format concern). `ProjectStrRef` is a project data concern.

Three variants, discriminated by which fields are populated:

```python
@dataclass
class ProjectStrRef:
    strref:  int | None        # original game index; None = project-authored
    strings: dict[str, str]    # language_code → text; empty = live reference
```

| Variant | `strref` | `strings` | When used |
|---------|----------|-----------|-----------|
| Live reference | set | empty | Unmodified import; resolved at display time |
| Imported snapshot | set | populated | Cross-game import or user-modified string |
| Project-authored | None | populated | New string with no game original |

**Display:** `resolve(language, string_manager)` — returns inline string if
available, falls back to `string_manager` for live references.

**Export:** live references emit the raw integer strref (string exists in game
TLK, no need to ship it); snapshots and authored strings emit `@N` WeiDU
placeholders (N assigned during export pass from `.tra` file).

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

### core/util/idsref.py
- `IdsRef(value: int, ids_name: str)` — wraps a raw integer with the name of
  the IDS file it resolves against
- `ids_name` is the IDS basename: uppercase, no extension, max 8 chars
  (e.g. `"WPROF"`, `"EA"`, `"RACE"`, `"PROJECTL"`)
- `ref.value` — the raw integer stored on disk
- `ref.ids_name` — the IDS file to resolve against
- `ref.resolve(table: IdsTable) -> str` — returns the symbolic name, or
  `"UNKNOWN(N)"` if the value is not in the table
- `ref.to_json() -> dict` — serialises as `{"value": N, "ids": "NAME"}`
- `IdsRef.from_json(d: dict) -> IdsRef`
- `IdsRef.NONE` — sentinel for "no value" where appropriate (value=0, ids_name="")
- No runtime project imports; `IdsTable` is TYPE_CHECKING only

### core/util/enums.py
- Single centralised module for **all** `IntEnum` and `IntFlag` definitions
  used anywhere in the project
- Covers format-specific enums (previously scattered across `itm.py`, `spl.py`,
  `are.py`, `cre.py`) and any future additions
- Rationale: one location is easier to find than hunting across dozens of format
  files; enums are not file formats and do not belong in `core/formats/`
- All format modules import their enums from here:
  `from core.util.enums import ItemType, ItemFlag, AttackType, ...`
- Standard import line for format files that use enums:
  `from core.util.enums import <EnumName>, ...`

### core/formats/ids.py
- `IdsTable` — resolved lookup table for one IDS file
  - `IdsTable(name: str, entries: dict[int, str])` — constructed from parsed data
  - `table.name` — IDS basename (e.g. `"WPROF"`)
  - `table.resolve(value: int) -> str` — returns symbolic name or `"UNKNOWN(N)"`
  - `table.entries` — the raw `dict[int, str]` mapping
  - `table.to_json() -> dict` — serialises for caching
  - `IdsTable.from_json(d: dict) -> IdsTable`
- `IdsFile` — parser for `.ids` binary/text files
  - `IdsFile.from_bytes(data: bytes) -> IdsTable` — parses and returns table
  - `IdsFile.from_file(path) -> IdsTable`
  - Handles both plain-text and encrypted IDS files
  - Header lines (IDS / IDS V1.0 + entry count) are consumed but not validated
    strictly (count line is often wrong per IESDP)

### core/formats/ — all parsers
All format modules follow this contract without exception:

- `XxxFile.from_bytes(data: bytes) -> XxxFile` — parse from raw bytes
- `XxxFile.from_file(path) -> XxxFile` — read file and delegate to `from_bytes()`
- `XxxFile.to_bytes() -> bytes` — serialise back to binary
- `XxxFile.to_file(path) -> None` — write binary to file
- `XxxFile.to_json() -> dict` — serialise to JSON-compatible dict
- `XxxFile.from_json(d: dict) -> XxxFile` — deserialise from dict

All format modules must have explicit imports for every symbol used from `core.util`:

```python
from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.enums  import <EnumName>, ...      # whatever enums the module uses
from core.util.idsref import IdsRef
from core.util.resref import ResRef
from core.util.strref import StrRef, StrRefError
```

Omit only what the file genuinely does not use.

### core/services/opcode_registry.py
- Loads bundled opcode tables from `data/opcodes/<game_id>.json` at first access
- Does NOT depend on a game installation — data is shipped with the editor
- `OpcodeRegistry.for_game(game_id: str) -> OpcodeRegistry` — factory; caches
  per game_id
- `registry.resolve(opcode: int) -> OpcodeEntry` — returns name + description;
  falls back to `OpcodeEntry(opcode, f"Opcode {opcode}", "")` for unknown values
- `OpcodeEntry(value: int, name: str, description: str)` — frozen dataclass
- JSON format: `{"opcodes": [{"value": N, "name": "...", "description": "..."}, ...]}`
- Supported game_ids map to files: `"bgee"` / `"bg2ee"` → `bgee.json`,
  `"iwd"` / `"iwdee"` → `iwd.json`, `"pst"` / `"pstee"` → `pst.json`

### game/ids_manager.py
- Lazy-loads `IdsTable` objects from the game installation on demand
- Depends on `game/installation.py` — lives in `game/` for this reason
- `IdsManager(installation: GameInstallation)` — construction does not load anything
- `manager.get(ids_name: str) -> IdsTable` — load on first access, cache thereafter;
  searches override dir first, then CHITIN.KEY (matching engine override priority)
- `manager.preload(*ids_names: str) -> None` — load multiple tables eagerly
- `manager.clear_cache() -> None` — force reload on next access (e.g. after game switch)
- `ids_name` is the uppercase basename without extension, e.g. `"WPROF"`, `"EA"`

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
- `manager.resolve_all_languages(ref: StrRef, inst: GameInstallation) -> dict[str, str]`
  — resolves StrRef against every installed language; used at import time only.
    EE games: iterates `lang/*/dialog.tlk`; original games: `{"default": text}`.
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

### core/project/strref.py  (ProjectStrRef)
- `ProjectStrRef(strref: int | None, strings: dict[str, str])`
- Three variants: live reference, imported snapshot, project-authored
  (see "ProjectStrRef — three-variant string reference" section above)
- `is_live` — `strref` set, `strings` empty
- `is_snapshot` — `strref` set, `strings` populated
- `is_authored` — `strref` is None
- `resolve(language: str, string_manager) -> str`
  — returns `strings[language]` if available, else `strings["en_US"]` as
    fallback, else resolves live via `string_manager`
- `to_json() -> dict` — one of the three JSON forms above
- `ProjectStrRef.from_json(d: dict) -> ProjectStrRef`
- `to_weidu_ref(assigned_index: int | None) -> str`
  — live → `str(strref)`; snapshot/authored → `@{assigned_index}`

### core/project/importer.py
- `import_resource(resref, res_type, source_game, key, game_root, string_manager) -> dict`
  — reads resource, parses it, converts all StrRef fields to ProjectStrRef,
    returns JSON dict ready to write to `imported/<game_id>/<type>/`
- Snapshot vs live decision: secondary game → always snapshot;
  primary game → live (unless string is modified later)

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

1. Implement CRE V2.2 (IWD2) parser — completely different header, not started
2. Convert `cre.py` `soundset` from `bytes` to `List[StrRef]` — V1.0 and V9.0
3. Vet and fix `itm.py` — ResRef fields contain garbage bytes (see decisions log)
4. **IdsRef / enum migration** (new — see decisions log):
   a. `core/util/enums.py` — migrate all existing enums here; update imports
   b. `core/util/idsref.py` — new IdsRef type
   c. `core/formats/ids.py` — IDS file parser
   d. `game/ids_manager.py` — lazy-loading IDS manager
   e. Wire IdsRef into format files (itm, spl, cre, are) field by field
   f. `data/opcodes/*.json` — populate bundled opcode tables from IESDP
   g. `core/services/opcode_registry.py` — opcode resolution service
5. ResRef migration — apply ResRef type to all format parser fields across all parsers
6. Vet remaining parsers against real game files: `spl.py`, `dlg.py`, `are.py`, `wed.py`, `mos.py`, `tis.py`
7. `core/project/project.py` — Project open/save/new, dirty tracking, path management
8. `core/project/mod_structure.py` — WeiDU .tp2 + .tra generation
9. `core/project/undo_redo.py` — command pattern
10. `core/watcher.py` — filesystem watcher (watchdog)
11. UI layer (Dear PyGui)
12. Unit tests for all modules

Completed (removed from list):
- CRE V1.2 (PST) parser fixes — done (turn_undead_level, tracking_target, soundset)
- `StringManager.resolve_all_languages()` — done
- `core/project/strref.py` ProjectStrRef — done
- `core/project/importer.py` — done

---

## UI architecture

### Layered composition with semantic naming

```
ui/
├── core/                        # Reusable, generic UI components
│   ├── __init__.py
│   ├── titlebar.py              # CustomTitleBarController — frameless window chrome
│   ├── editor_toolbar.py        # EditorToolbar — game selector, status, buttons
│   ├── resource_browser_pane.py # ResourceBrowserPane — searchable left panel
│   └── progress_handler.py      # EditorProgressHandler — progress forwarding
│
├── editors/                     # Concrete editor implementations
│   ├── __init__.py
│   ├── character_editor.py      # CharacterEditorPanel
│   └── item_editor.py           # ItemEditorPanel
│
├── skin/
│   └── infinity/
│       ├── assets.py            # InfinitySkinAssets — icon loader, CHU layout
│       ├── screen_panel.py      # InfinityScreenPanel — game screen renderer
│       ├── components/
│       └── data/
│           └── manifest_default.json   # Active config file (not a template)
│
└── app.py                       # Application root, viewport, routing
```

**Key design principles:**
- Semantic naming: `EditorToolbar`, `ResourceBrowserPane`, `CharacterEditorPanel`
  — what the component IS, not where it sits
- Composition over inheritance: each editor owns an `EditorToolbar` and
  `ResourceBrowserPane`; editors are stateful, core components are stateless
- DPG tag-based item management: every DPG item gets a prefixed tag
  `"{tag_prefix}_{suffix}"` to prevent collisions
- Non-code data files belong in `skin/infinity/data/`

**Adding new editor types:**
1. Create `ui/editors/my_editor.py` with class `MyEditorPanel`
2. Implement `__init__`, `set_size()`, `handle_mouse_event()`, `_search(query)`
3. Compose `EditorToolbar` and `ResourceBrowserPane` as needed
4. Export from `ui/editors/__init__.py`
5. Instantiate in `ui/app.py` and add to `ui_state` dict
6. Add routing case to `on_global_search_changed()`

**Progress tracking pattern for new editors:**
```python
from ui.core import EditorProgressHandler
# In __init__:
self._progress_handler = EditorProgressHandler(self._set_status)
service.set_progress_callback(self._progress_handler.on_progress)
```

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
The standard import block for a format file that uses all util modules is:

    from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
    from core.util.enums  import <EnumName>, ...
    from core.util.idsref import IdsRef
    from core.util.resref import ResRef
    from core.util.strref import StrRef, StrRefError

Omit only what the file genuinely does not use.

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

**2026-03 — Mod project structure and ProjectStrRef design**
Projects are self-contained directories; no shared files between projects.
Resources are split between `imported/<game_id>/<type>/` (pulled from a game
installation) and `created/<type>/` (user-authored). Same ResRef can exist
under multiple game IDs without collision. The distinction drives WeiDU output:
imported → COPY_EXISTING + patch; created → ADD_ITEM/ADD_CREATURE etc.

StrRef fields in project JSON use `ProjectStrRef` (core/project/strref.py),
distinct from the binary-format `StrRef` (core/util/strref.py). Three variants:
live reference (strref only), imported snapshot (strref + strings map),
project-authored (strings map only). Live references resolve at display time;
others carry inline text. At export, live → raw integer; others → @N WeiDU ref.

**2026-03 — string_manager.resolve() isinstance → duck typing**
The `isinstance(ref, StrRef)` check in `resolve()` and `resolve_all_languages()`
failed silently when the StrRef class was imported under a different module path
(e.g. `strref` vs `core.util.strref`). Replaced with `hasattr` checks for
`file_id`, `tlk_index`, and `is_none`.

**2026-03 — demo_search.py renamed to resource_explorer.py, moved to tools/**
The demo script was upgraded to a full interactive CLI explorer with a REPL loop,
structured `where` query syntax, `open <RESREF>` inspection, runtime type switching,
and `cls` screen clear. Cache moved from `demo_output/` to `.cache/<game_id>/`.
Script lives at `tools/resource_explorer.py`; `_ROOT` set to `parent.parent` so
imports resolve from the project root.

**2026-03 — Added PVRZ support for Enhanced Edition MOS V2 backgrounds**
The error "MOS 'INVENTOR': not found or is PVRZ (no RGBA decode)" was caused by
MOS V2 (PVRZ-based) files used in Enhanced Edition games. Implemented full PVRTC
support via `core/formats/pvrtc.py` (PVRTC 4bpp decoder) and extended
`core/formats/pvrz.py`. `MosFile.to_rgba()` accepts optional `pvrz_loader`
callable for V2 support. `CharacterService.load_mos_by_resref()` creates a PVRZ
loader and handles decoding.

**2026-03 — PVRZ decoding performance: two-level caching**
Initial implementation decoded entire PVRZ textures on every region extract.
Fixed with two-level caching: (1) `PvrzFile` internal `_rgba_cache` — first
region extract triggers full decode, subsequent calls reuse it; (2)
`CharacterService` shared `_pvrz_cache` dict by page number — `PvrzFile` objects
cached after first load, cleared on game selection change. Unified
`_make_pvrz_loader()` used by both BAM V2 and MOS V2 decoders.

**2026-03 — BAM/BMP transparent pixel RGB must be zeroed (pre-multiplied alpha)**
BAM V1 and BMP icons use a green colour key (R=0, G=255, B=0) for transparency.
When decoded, transparent pixels must be emitted as `(0.0, 0.0, 0.0, 0.0)` —
not `(0.0, 1.0, 0.0, 0.0)`. DearPyGui uses bilinear interpolation when a texture
is drawn at non-native size; retaining green RGB in transparent pixels bleeds
green into adjacent edges. Affected: `bam.py` `_indices_to_rgba()`,
`bmp.py` `_indices_to_rgba()`, `_decode_24bpp()`, `_decode_32bpp()`. In
`_decode_32bpp`, the colour-key zero-out must run before the `a==0,
non-zero RGB → force a=255` workaround.

**2026-03 — EditorProgressHandler reusable progress tracking**
Created `ui/core/progress_handler.py` as a lightweight component for all editors
to report progress during long operations. Editors instantiate with
`EditorProgressHandler(toolbar.set_status)`; services call `_report_progress()`;
messages appear as blue text on the toolbar. Same pattern works for all editor
types. Optional `AsyncLoader` (`ui/util/async_loader.py`) available for CPU-bound
ops needing background threading.

**2026-03 — UI architecture restructuring: layered composition with semantic naming**
Original UI had duplicate toolbars and browser panes per editor. Restructured to:
`ui/core/` (reusable components), `ui/editors/` (concrete implementations),
`ui/skin/` (visual theme). Semantic naming (`EditorToolbar`, `ResourceBrowserPane`)
over structural naming (`LeftPanel`, `Screen1`). Composition over inheritance —
editors own core components via constructor, not subclassing.

**2026-03 — IdsRef as a distinct type for IDS-backed fields**
All integer fields that are defined by an IDS file (weapon proficiency, EA,
race, class, alignment, gender, projectile, damage type, etc.) are stored as
`IdsRef(value, ids_name)` rather than bare `int`. This mirrors the `StrRef`
design: the reference carries enough information to be resolved without
consulting the schema. `ids_name` is the uppercase IDS basename without
extension (e.g. `"WPROF"`, `"EA"`). The IDS name is NOT encoded in the binary
value (unlike StrRef's file_id bits) — it is structural knowledge from IESDP,
stored explicitly on the `IdsRef` instance. Serialises as
`{"value": N, "ids": "NAME"}`. Resolution is always external — the caller
supplies an `IdsTable` from `IdsManager`.

**2026-03 — All enums centralised in core/util/enums.py**
All `IntEnum` and `IntFlag` definitions are kept in a single module
`core/util/enums.py` rather than scattered across format files. Rationale:
one location is easier to find and maintain than hunting across dozens of files.
Enums are not file formats; they belong in `core/util/` alongside other
primitive shared types. Format files (`itm.py`, `spl.py`, `are.py`, `cre.py`,
etc.) import enums from `core.util.enums`.

**2026-03 — Opcode resolution via bundled JSON, served by core/services/**
Opcodes are not stored in an IDS file and are not sourced from the game
installation — they are documented by IESDP and ship with the editor.
Bundled tables live in `data/opcodes/` (one JSON file per game variant).
Resolution is provided by `core/services/opcode_registry.py`, which lives in
`core/services/` because it is a runtime service over bundled data with no
installation dependency. `game/` is reserved for modules that require a game
installation; `core/services/` is the correct home for editor-bundled data
services. `OpcodeRegistry.for_game(game_id)` is the entry point.

**2026-03 — game/ reserved for installation-dependent modules only**
`game/` contains only modules that directly interact with a game installation
(locating files, reading CHITIN.KEY, loading TLK/IDS files). Modules that
serve bundled editor data (opcodes, static reference tables) belong in
`core/services/` instead. Future todo: rename `installation.py` to
`installation_manager.py` for clarity.

**2026-03 — ITM IDS/enum/StrRef resolution wired into structured view**
The ITM structured table now resolves IDS-backed fields (via `IdsRef`), enums,
and StrRefs at display time. This includes header weapon proficiencies (WPROF),
projectile animations (PROJECTL), header flags/usability (game-specific enum
variants), extended header fields (attack type, target type, location, damage
type, ability flags), feature block target/timing enums, and feature block
parameter1 as StrRef text. Usability flags are displayed as "Unusable by" with
kit usability fields labeled "Unusable by kit (1/4..4/4)" and resolved via
KITLIST.2DA. Animation codes and melee animation labels are displayed to match
NearInfinity naming.

**2026-03 — IDS/enum data sources and resolution services**
Implemented `IdsRef`, IDS parsing (`core/formats/ids.py`), and a lazy
installation-backed IDS manager (`game/ids_manager.py`). Resolution in the UI
uses `ItmCatalog.resolve_ids()` to avoid coupling formats to the game install.
Enum definitions are centralized in `core/util/enums.py` with per-game variants
for ITM header flags/usability and target/damage type differences.

**2026-03 — Opcode registry from bundled IESDP tables**
Added bundled opcode tables under `data/opcodes/` (BG(2)EE, IWD, PST variants)
and an `OpcodeRegistry` service under `core/services/`. ITM feature block opcode
values resolve through `ItmCatalog.resolve_opcode()` to a name/description pair
using the bundled data (not installation files).

**2026-03 — DPG table quirks**
DPG table column widths return 0 until the table has been rendered in a visible frame. get_item_rect_size and get_item_width on column tags always return 0 at construction time, even for tables inside default_open=True tree nodes. Deferring to the next frame (via set_frame_callback) does not help — the layout pass hasn't run yet. The correct pattern for text wrap in a 3-column table (fixed Field, fixed Value, stretch Resolved) is to compute wrap widths synchronously at build time from the known max_field and max_value pixel sizes (obtained via dpg.get_text_size on the label strings before the table is created) and _right_width. Store those values alongside the wrap-target list in _wrap_tables so that subsequent resize and tree-open refreshes can fall back to the same calculation when measurement still returns zero (e.g. collapsed nodes). Do not attempt a retry loop with a blind third-o-of-panel fallback — it fires too late and produces the wrong width.