#!/usr/bin/env python3
"""
demo_search.py

Full working demonstration of PlanarForge search and import.

Finds an installed IE game, builds a resource index over ITM files
(or a type you specify), searches by string query, and optionally imports
the first matching resource to demo_output/ as a project JSON file.

The index is cached to demo_output/<game_id>_<type>_index.json and reused
on subsequent runs.  Delete the cache file to force a rebuild.

Usage
-----
    python demo_search.py "sword"
    python demo_search.py "sword" --type ITM
    python demo_search.py "leather" --game BG2EE
    python demo_search.py "potion" --import-first
    python demo_search.py "hold" --type SPL --game IWDEE
    python demo_search.py --list-games
    python demo_search.py "sword" --no-cache   # force index rebuild

Run from the project root (infinity_editor/).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from game.installation   import InstallationFinder, GameInstallation
from game.string_manager import StringManager, StringManagerError
from core.formats.key_biff import KeyFile, ResType, BiffFile
from core.index import ResourceIndex, IndexEntry, SOURCE_BIFF


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_TYPES  = {ResType.ITM}
_RISKY_TYPES = {ResType.CRE, ResType.SPL, ResType.DLG, ResType.ARE,
                ResType.WED, ResType.TIS, ResType.MOS}

DEMO_OUTPUT = Path("demo_output")


def _pick_game(finder: InstallationFinder, game_id: str | None) -> GameInstallation:
    games = finder.find_all()
    if not games:
        print("ERROR: No IE game installations found.")
        sys.exit(1)

    if game_id:
        inst = finder.find(game_id)
        if inst is None:
            print(f"ERROR: Game '{game_id}' not found.  Available:")
            for g in games:
                print(f"  {g.game_id:12s}  {g.display_name}")
            sys.exit(1)
        return inst

    print("Installed IE games found:\n")
    for i, g in enumerate(games, 1):
        print(f"  [{i}]  {g.game_id:12s}  {g.display_name}")
        print(f"         {g.install_path}")
    print()

    while True:
        raw = input(f"Pick a game [1-{len(games)}]: ").strip()
        try:
            choice = int(raw)
            if 1 <= choice <= len(games):
                return games[choice - 1]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(games)}.")


def _parse_res_type(name: str) -> ResType:
    try:
        return ResType[name.upper()]
    except KeyError:
        print(f"ERROR: Unknown resource type '{name}'.")
        sys.exit(1)


def _safe_res_type(code: int) -> bool:
    try:
        ResType(code)
        return True
    except ValueError:
        return False


def _cache_path(inst: GameInstallation, res_type: ResType) -> Path:
    return DEMO_OUTPUT / f"{inst.game_id}_{res_type.name}_index.json"


def _parser_hash(res_type: ResType) -> str:
    """
    Return a short hash of the parser module for this res_type.

    Cache is invalidated automatically when the parser source changes,
    not just when CHITIN.KEY changes.
    """
    import hashlib
    _PARSER_FILES = {
        ResType.ITM: "core/formats/itm.py",
        ResType.SPL: "core/formats/spl.py",
        ResType.CRE: "core/formats/cre.py",
        ResType.DLG: "core/formats/dlg.py",
        ResType.ARE: "core/formats/are.py",
    }
    path = Path(_HERE) / _PARSER_FILES.get(res_type, "core/index.py")
    try:
        data = path.read_bytes()
        return hashlib.md5(data).hexdigest()[:8]
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Index serialisation (simple — just what we need for the demo)
# ---------------------------------------------------------------------------

def _save_index(index: ResourceIndex, path: Path, chitin_mtime: float, parser_hash: str = "") -> None:
    """Serialise index to JSON for caching."""
    entries = []
    for e in index:
        entries.append({
            "resref":        str(e.resref),
            "res_type":      int(e.res_type),
            "display_name":  e.display_name,
            "source":        e.source,
            "data":          e.data,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"chitin_mtime": chitin_mtime,
                    "parser_hash":  parser_hash,
                    "entries":      entries},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_index(path: Path, chitin_mtime: float, expected_hash: str = "") -> ResourceIndex | None:
    """Load cached index if it exists and chitin.key hasn't changed."""
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if raw.get("chitin_mtime") != chitin_mtime:
        print("  (Cache outdated — CHITIN.KEY has changed, rebuilding.)")
        return None
    if expected_hash and raw.get("parser_hash") != expected_hash:
        print("  (Cache outdated — parser has changed, rebuilding.)")
        return None

    from core.util.resref import ResRef
    index = ResourceIndex()
    for e in raw["entries"]:
        try:
            index.add_or_update(
                resref       = ResRef(e["resref"]),
                res_type     = ResType(e["res_type"]),
                source       = e["source"],
                data         = e["data"],
                display_name = e["display_name"],
            )
        except Exception:
            pass
    return index


# ---------------------------------------------------------------------------
# Batched index build (groups resources by BIFF to avoid re-opening files)
# ---------------------------------------------------------------------------

def _build_index_batched(
    entries_to_index: list,
    key:              KeyFile,
    inst:             GameInstallation,
    manager:          StringManager,
) -> tuple[ResourceIndex, list[str]]:
    """
    Build a ResourceIndex by batching reads per BIFF archive.

    The naive approach opens and closes each .bif file once per resource.
    BG2EE has ~2867 items spread across many BIFFs — batching by BIFF file
    reduces file opens from ~2867 to ~191, dramatically improving speed.
    """
    from core.util.resref import ResRef as _ResRef

    # Group entries by biff_index
    by_biff: dict[int, list] = defaultdict(list)
    for e in entries_to_index:
        by_biff[e.biff_index].append(e)

    index  = ResourceIndex()
    errors = []
    done   = 0
    total  = len(entries_to_index)

    for biff_idx, batch in sorted(by_biff.items()):
        # Resolve path for this BIFF
        try:
            biff_path = key.biff_path(batch[0], game_root=inst)
        except Exception as exc:
            for e in batch:
                errors.append(f"  PATH  {e.resref}: {exc}")
                done += 1
            continue

        # Open BIFF once for the whole batch
        try:
            biff = BiffFile.open(biff_path)
        except Exception as exc:
            for e in batch:
                errors.append(f"  OPEN  {e.resref} ({biff_path.name}): {exc}")
                done += 1
            _progress(done, total, "")
            continue

        for res_entry in batch:
            done += 1
            _progress(done, total, str(res_entry.resref))
            try:
                if res_entry.res_type == int(ResType.TIS):
                    raw = biff.read_tileset_raw(res_entry.tileset_index)
                else:
                    raw = biff.read(res_entry.file_index)
            except Exception as exc:
                errors.append(f"  READ  {res_entry.resref}: {exc}")
                continue

            try:
                index._index_raw(
                    resref         = res_entry.resref,
                    res_type       = ResType(res_entry.res_type),
                    source         = SOURCE_BIFF,
                    raw            = raw,
                    string_manager = manager,
                )
            except Exception as exc:
                errors.append(f"  PARSE {res_entry.resref}: {exc}")

    return index, errors


def _progress(current: int, total: int, resref: str) -> None:
    pct = int(current / total * 100) if total else 0
    print(f"\r  Indexing... {current}/{total} ({pct}%)  {resref:<12}", end="", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:

    finder = InstallationFinder()

    if args.list_games:
        games = finder.find_all()
        if not games:
            print("No IE game installations found.")
        else:
            print(f"{'Game ID':<14} {'Display Name':<40} Install Path")
            print("-" * 90)
            for g in games:
                print(f"{g.game_id:<14} {g.display_name:<40} {g.install_path}")
        return

    inst = _pick_game(finder, getattr(args, 'game', None))
    print(f"\nUsing: {inst.display_name}")
    print(f"       {inst.install_path}\n")

    # ── Open CHITIN.KEY ───────────────────────────────────────────────────
    print(f"Opening CHITIN.KEY ... ", end="", flush=True)
    try:
        key = KeyFile.open(inst.chitin_key)
    except Exception as exc:
        print(f"\nERROR: Cannot open CHITIN.KEY: {exc}")
        sys.exit(1)
    print(f"{key.num_resources} resources across {key.num_biff} BIFF archives.")

    # ── Load StringManager ────────────────────────────────────────────────
    print(f"Loading TLK ... ", end="", flush=True)
    try:
        manager = StringManager.from_installation(inst)
    except StringManagerError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
    langs = StringManager.available_languages(inst)
    if langs:
        print(f"{manager.base_entry_count} strings, "
              f"{len(langs)} language(s): {', '.join(langs)}")
    else:
        print(f"{manager.base_entry_count} strings (single-language install).")

    # ── Decide type(s) ───────────────────────────────────────────────────
    res_type = _parse_res_type(args.type)
    if res_type not in _SAFE_TYPES:
        print(f"WARNING: {res_type.name} is untested. Parse errors will be skipped.")

    # ── Load or build index ───────────────────────────────────────────────
    chitin_mtime = inst.chitin_key.stat().st_mtime
    cache        = _cache_path(inst, res_type)
    index        = None

    phash = _parser_hash(res_type)
    if not args.no_cache:
        index = _load_index(cache, chitin_mtime, phash)
        if index is not None:
            print(f"Index loaded from cache ({len(index)} entries): {cache}")

    if index is None:
        entries_to_index = [
            e for e in key.iter_resources()
            if _safe_res_type(e.res_type)
            if ResType(e.res_type) == res_type
        ]
        total = len(entries_to_index)
        print(f"Building index for: {res_type.name}  ({total} resources)")

        t0 = time.time()
        index, errors = _build_index_batched(entries_to_index, key, inst, manager)
        elapsed = time.time() - t0
        print(f"\r  Indexed {len(index)} entries in {elapsed:.1f}s.{' ' * 30}")

        if errors:
            print(f"\n  {len(errors)} error(s) during indexing:")
            for e in errors[:10]:
                print(f"    {e}")
            if len(errors) > 10:
                print(f"    ... and {len(errors) - 10} more.")

        print(f"  Saving cache to {cache} ... ", end="", flush=True)
        try:
            _save_index(index, cache, chitin_mtime, phash)
            print("done.")
        except Exception as exc:
            print(f"failed ({exc}) — continuing without cache.")

    # ── Search ────────────────────────────────────────────────────────────
    if not args.query:
        print(f"\nNo query supplied.  Index contains {len(index)} entries.")
        print(f'Example: python demo_search.py "sword" --game {inst.game_id}')
        return

    query = args.query
    print(f"\nSearching for: {query!r}  (type={res_type.name})\n")

    results = index.search(query=query, res_type=res_type)

    if not results:
        print("  No results found.")
        return

    print(f"  {len(results)} result(s):\n")
    print(f"  {'ResRef':<12} {'Type':<6} Name")
    print(f"  {'-'*12} {'-'*6} {'-'*50}")
    for entry in results[:args.limit]:
        name = entry.display_name or "(no name)"
        print(f"  {str(entry.resref):<12} {entry.res_type.name:<6} {name}")
    if len(results) > args.limit:
        print(f"\n  ... and {len(results) - args.limit} more  (--limit N to see more).")

    # ── Optional import ───────────────────────────────────────────────────
    if args.import_first and results:
        _do_import(results[0], key, inst, manager)


def _do_import(
    entry:   IndexEntry,
    key:     KeyFile,
    inst:    GameInstallation,
    manager: StringManager,
) -> None:
    from core.project.importer import import_resource

    print(f"\nImporting {entry.resref}.{entry.res_type.name.lower()} ...")
    try:
        result = import_resource(
            resref         = entry.resref,
            res_type       = entry.res_type,
            source_game_id = inst.game_id,
            is_primary     = True,
            key            = key,
            game_root      = inst,
            string_manager = manager,
            inst           = inst,
        )
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return

    out_file = DEMO_OUTPUT / result.suggested_path
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(result.data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Written to:   {out_file}")
    print(f"  Display name: {result.display_name}\n")

    lines = json.dumps(result.data, indent=2, ensure_ascii=False).splitlines()
    print("  JSON preview (first 40 lines):")
    for line in lines[:40]:
        print(f"    {line}")
    if len(lines) > 40:
        print(f"    ... ({len(lines) - 40} more lines)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PlanarForge demo — search game resources by string.",
    )
    parser.add_argument("query", nargs="?",
                        help="Search query (substring in name or any field).")
    parser.add_argument("--game", "-g", metavar="GAME_ID",
                        help="Game ID (e.g. BG2EE). Prompted if omitted.")
    parser.add_argument("--type", "-t", metavar="TYPE", default="ITM",
                        help="Resource type (default: ITM).")
    parser.add_argument("--import-first", "-i", action="store_true",
                        help="Import first result to demo_output/.")
    parser.add_argument("--limit", "-n", type=int, default=20,
                        help="Max results to display (default: 20).")
    parser.add_argument("--list-games", action="store_true",
                        help="List detected installations and exit.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force index rebuild even if cache exists.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
