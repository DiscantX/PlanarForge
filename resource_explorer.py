#!/usr/bin/env python3
"""
resource_explorer.py

Interactive CLI resource explorer for PlanarForge.

- Builds or loads a cached index for a selected game and resource type.
- Supports full listing by type (e.g. all ITM files).
- Supports text search, then interactive selection by ResRef for inspection.
- Pretty-prints parsed resource JSON to the terminal.

Usage examples
--------------
    python resource_explorer.py --list-games
    python resource_explorer.py --game BG2EE --type ITM --list-type ITM
    python resource_explorer.py "sword" --game BG2EE --type ITM
    python resource_explorer.py "potion" --type ITM --limit 50 --no-cache
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from collections import defaultdict

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from game.installation import InstallationFinder, GameInstallation
from game.string_manager import StringManager, StringManagerError
from core.formats.key_biff import KeyFile, ResType, BiffFile
from core.index import ResourceIndex, IndexEntry, SOURCE_BIFF


SAFE_TYPES = {ResType.ITM}
DEMO_OUTPUT = Path("demo_output")
EXIT_WORDS = {"exit", "quit", "q"}
CLEAR_WORDS = {"cls"}


def _clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _pick_game(finder: InstallationFinder, game_id: str | None) -> GameInstallation:
    games = finder.find_all()
    if not games:
        print("ERROR: No IE game installations found.")
        sys.exit(1)

    if game_id:
        inst = finder.find(game_id)
        if inst is None:
            print(f"ERROR: Game '{game_id}' not found. Available:")
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
        if raw.lower() in CLEAR_WORDS:
            _clear_screen()
            print("Installed IE games found:\n")
            for i, g in enumerate(games, 1):
                print(f"  [{i}]  {g.game_id:12s}  {g.display_name}")
                print(f"         {g.install_path}")
            print()
            continue
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
    import hashlib

    parser_files = {
        ResType.ITM: "core/formats/itm.py",
        ResType.SPL: "core/formats/spl.py",
        ResType.CRE: "core/formats/cre.py",
        ResType.DLG: "core/formats/dlg.py",
        ResType.ARE: "core/formats/are.py",
        ResType.WED: "core/formats/wed.py",
        ResType.TIS: "core/formats/tis.py",
        ResType.MOS: "core/formats/mos.py",
    }
    path = Path(_HERE) / parser_files.get(res_type, "core/index.py")
    try:
        data = path.read_bytes()
        return hashlib.md5(data).hexdigest()[:8]
    except OSError:
        return "unknown"


def _save_index(index: ResourceIndex, path: Path, chitin_mtime: float, parser_hash: str = "") -> None:
    entries = []
    for e in index:
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


def _load_index(path: Path, chitin_mtime: float, expected_hash: str = "") -> ResourceIndex | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if raw.get("chitin_mtime") != chitin_mtime:
        print("  (Cache outdated: CHITIN.KEY changed, rebuilding.)")
        return None
    if expected_hash and raw.get("parser_hash") != expected_hash:
        print("  (Cache outdated: parser changed, rebuilding.)")
        return None

    from core.util.resref import ResRef

    index = ResourceIndex()
    for e in raw.get("entries", []):
        try:
            index.add_or_update(
                resref=ResRef(e["resref"]),
                res_type=ResType(e["res_type"]),
                source=e["source"],
                data=e["data"],
                display_name=e["display_name"],
            )
        except Exception:
            pass
    return index


def _build_index_batched(entries_to_index: list, key: KeyFile, inst: GameInstallation, manager: StringManager) -> tuple[ResourceIndex, list[str]]:
    by_biff: dict[int, list] = defaultdict(list)
    for e in entries_to_index:
        by_biff[e.biff_index].append(e)

    index = ResourceIndex()
    errors: list[str] = []
    done = 0
    total = len(entries_to_index)

    for _, batch in sorted(by_biff.items()):
        try:
            biff_path = key.biff_path(batch[0], game_root=inst)
        except Exception as exc:
            for e in batch:
                errors.append(f"  PATH  {e.resref}: {exc}")
                done += 1
            continue

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
                    resref=res_entry.resref,
                    res_type=ResType(res_entry.res_type),
                    source=SOURCE_BIFF,
                    raw=raw,
                    string_manager=manager,
                )
            except Exception as exc:
                errors.append(f"  PARSE {res_entry.resref}: {exc}")

    return index, errors


def _progress(current: int, total: int, resref: str) -> None:
    pct = int(current / total * 100) if total else 0
    print(f"\r  Indexing... {current}/{total} ({pct}%)  {resref:<12}", end="", flush=True)


def _print_result_table(results: list[IndexEntry], limit: int) -> None:
    print(f"  {len(results)} result(s):\n")
    print(f"  {'ResRef':<12} {'Type':<6} Name")
    print(f"  {'-'*12} {'-'*6} {'-'*60}")
    for entry in results[:limit]:
        name = entry.display_name or "(no name)"
        print(f"  {str(entry.resref):<12} {entry.res_type.name:<6} {name}")
    if len(results) > limit:
        print(f"\n  ... and {len(results) - limit} more (--limit N to see more).")


def _prompt_pick_resref(results: list[IndexEntry]) -> IndexEntry | None:
    by_resref = {str(e.resref).upper(): e for e in results}
    print("\nInspect a resource by typing its ResRef (example: HSWORD).")
    print("Press Enter to skip.")

    while True:
        raw = input("ResRef to inspect: ").strip().upper()
        if raw.lower() in CLEAR_WORDS:
            _clear_screen()
            print("Inspect a resource by typing its ResRef (example: HSWORD).")
            print("Press Enter to skip.")
            continue
        if not raw:
            return None
        entry = by_resref.get(raw)
        if entry is not None:
            return entry
        print("  ResRef not in the current result set. Try again.")


def _inspect_entry(entry: IndexEntry, key: KeyFile, inst: GameInstallation, index: ResourceIndex) -> None:
    parsed = index.resolve(entry, key, inst)
    if parsed is None:
        print(f"\nERROR: Could not resolve {entry.resref}.{entry.res_type.name.lower()}.")
        return

    try:
        payload = parsed.to_json()
    except Exception as exc:
        print(f"\nERROR: Could not serialize {entry.resref}: {exc}")
        return

    print("\n" + "=" * 90)
    print(f"Resource: {entry.resref}.{entry.res_type.name.lower()}   Source: {entry.source}")
    print("=" * 90)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _handle_list_flow(index: ResourceIndex, res_type: ResType, limit: int, key: KeyFile, inst: GameInstallation) -> None:
    print(f"\nListing all resources of type {res_type.name}:\n")
    results = index.search(query="", res_type=res_type)
    _print_result_table(results, limit)
    picked = _prompt_pick_resref(results)
    if picked is not None:
        _inspect_entry(picked, key, inst, index)


def _handle_search_flow(index: ResourceIndex, res_type: ResType, query: str, limit: int, key: KeyFile, inst: GameInstallation) -> None:
    print(f"\nSearching for: {query!r}  (type={res_type.name})\n")
    results = index.search(query=query, res_type=res_type)
    if not results:
        print("  No results found.")
        return
    _print_result_table(results, limit)
    picked = _prompt_pick_resref(results)
    if picked is not None:
        _inspect_entry(picked, key, inst, index)


def _load_or_build_index(
    *,
    key: KeyFile,
    inst: GameInstallation,
    manager: StringManager,
    res_type: ResType,
    no_cache: bool,
) -> ResourceIndex:
    chitin_mtime = inst.chitin_key.stat().st_mtime
    cache = _cache_path(inst, res_type)
    index: ResourceIndex | None = None

    phash = _parser_hash(res_type)
    if not no_cache:
        index = _load_index(cache, chitin_mtime, phash)
        if index is not None:
            print(f"Index loaded from cache ({len(index)} entries): {cache}")

    if index is None:
        entries_to_index = [
            e
            for e in key.iter_resources()
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
            print(f"failed ({exc}) -- continuing without cache.")

    return index


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

    inst = _pick_game(finder, args.game)
    print(f"\nUsing: {inst.display_name}")
    print(f"       {inst.install_path}\n")

    print("Opening CHITIN.KEY ... ", end="", flush=True)
    try:
        key = KeyFile.open(inst.chitin_key)
    except Exception as exc:
        print(f"\nERROR: Cannot open CHITIN.KEY: {exc}")
        sys.exit(1)
    print(f"{key.num_resources} resources across {key.num_biff} BIFF archives.")

    print("Loading TLK ... ", end="", flush=True)
    try:
        manager = StringManager.from_installation(inst)
    except StringManagerError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    langs = StringManager.available_languages(inst)
    if langs:
        print(f"{manager.base_entry_count} strings, {len(langs)} language(s): {', '.join(langs)}")
    else:
        print(f"{manager.base_entry_count} strings (single-language install).")

    current_type = _parse_res_type(args.list_type or args.type)
    index_cache: dict[ResType, ResourceIndex] = {}

    def get_index(res_type: ResType) -> ResourceIndex:
        if res_type not in index_cache:
            if res_type not in SAFE_TYPES:
                print(f"WARNING: {res_type.name} is marked untested. Parse errors will be skipped.")
            index_cache[res_type] = _load_or_build_index(
                key=key,
                inst=inst,
                manager=manager,
                res_type=res_type,
                no_cache=args.no_cache,
            )
        return index_cache[res_type]

    # Initial one-shot action from CLI args (if provided), then continue in loop.
    if args.list_type:
        _handle_list_flow(get_index(current_type), current_type, args.limit, key, inst)
    elif args.query:
        _handle_search_flow(get_index(current_type), current_type, args.query, args.limit, key, inst)
    else:
        index = get_index(current_type)
        print(f"\nNo query supplied. Index contains {len(index)} entries for {current_type.name}.")

    print("\nInteractive mode.")
    print("Commands: <search text> | list | type <TYPE> | exit")

    while True:
        raw = input(f"[{current_type.name}] > ").strip()
        lowered = raw.lower()

        if lowered in CLEAR_WORDS:
            _clear_screen()
            print("Interactive mode.")
            print("Commands: <search text> | list | type <TYPE> | cls | exit")
            continue

        if lowered in EXIT_WORDS:
            print("Exiting.")
            return

        if not raw:
            continue

        if lowered == "list":
            _handle_list_flow(get_index(current_type), current_type, args.limit, key, inst)
            continue

        if lowered.startswith("type "):
            next_type_name = raw.split(None, 1)[1].strip() if len(raw.split(None, 1)) > 1 else ""
            if not next_type_name:
                print("  Usage: type <TYPE>   (example: type ITM)")
                continue
            current_type = _parse_res_type(next_type_name)
            index = get_index(current_type)
            print(f"  Switched type to {current_type.name}. Indexed entries: {len(index)}.")
            continue

        _handle_search_flow(get_index(current_type), current_type, raw, args.limit, key, inst)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PlanarForge CLI resource explorer.",
    )
    parser.add_argument("query", nargs="?", help="Search query (substring in name or any field).")
    parser.add_argument("--game", "-g", metavar="GAME_ID", help="Game ID (e.g. BG2EE). Prompted if omitted.")
    parser.add_argument("--type", "-t", metavar="TYPE", default="ITM", help="Resource type for search (default: ITM).")
    parser.add_argument("--list-type", metavar="TYPE", help="List all resources for this type (e.g. ITM).")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Max rows to display (default: 20).")
    parser.add_argument("--list-games", action="store_true", help="List detected installations and exit.")
    parser.add_argument("--no-cache", action="store_true", help="Force index rebuild even if cache exists.")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
