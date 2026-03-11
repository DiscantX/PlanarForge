#!/usr/bin/env python3
"""Verify that resources can be read and parsed for one or more types/games.

Outputs JSON failure lists with entries containing:
- game_id
- resref
- type
- stage (read|parse)
- error_type
- error
- locator details (biff_index, file_index, tileset_index)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from game.installation import InstallationFinder, GameInstallation
from core.formats.key_biff import KeyFile
from core.util.enums import ResType
from core.formats.are import AreFile
from core.formats.cre import CreFile
from core.formats.dlg import DlgFile
from core.formats.itm import ItmFile
from core.formats.mos import MosFile
from core.formats.spl import SplFile
from core.formats.tis import TisFile
from core.formats.wed import WedFile


PARSERS: dict[ResType, type] = {
    ResType.ARE: AreFile,
    ResType.CRE: CreFile,
    ResType.DLG: DlgFile,
    ResType.ITM: ItmFile,
    ResType.MOS: MosFile,
    ResType.SPL: SplFile,
    ResType.TIS: TisFile,
    ResType.WED: WedFile,
}


def parse_types(type_name: str) -> list[ResType]:
    if type_name.upper() == "ALL":
        return sorted(PARSERS.keys(), key=lambda rt: rt.name)
    try:
        return [ResType[type_name.upper()]]
    except KeyError:
        known = ", ".join(sorted(rt.name for rt in PARSERS))
        raise SystemExit(f"Unknown type '{type_name}'. Supported types: {known}, ALL")


def pick_game(finder: InstallationFinder, game_id: str | None) -> GameInstallation:
    games = finder.find_all()
    if not games:
        raise SystemExit("No IE game installations found.")

    if game_id:
        inst = finder.find(game_id)
        if inst is None:
            available = ", ".join(g.game_id for g in games)
            raise SystemExit(f"Game '{game_id}' not found. Available: {available}")
        return inst

    print("Installed IE games:\n")
    for i, g in enumerate(games, 1):
        print(f"  [{i}] {g.game_id:12s} {g.display_name}")
        print(f"      {g.install_path}")
    print()

    while True:
        raw = input(f"Pick a game [1-{len(games)}]: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(games):
                return games[idx - 1]
        except ValueError:
            pass
        print(f"Please enter a number between 1 and {len(games)}.")


def pick_games(finder: InstallationFinder, game_id: str | None, all_games: bool) -> list[GameInstallation]:
    games = finder.find_all()
    if not games:
        raise SystemExit("No IE game installations found.")
    if all_games:
        return games
    return [pick_game(finder, game_id)]


def default_output_path(inst: GameInstallation, type_label: str) -> Path:
    return Path(".cache") / inst.game_id / "verification" / f"{type_label}_verify_failures.json"


def verify_one_type(inst: GameInstallation, key: KeyFile, res_type: ResType) -> tuple[list[dict], int]:
    parser = PARSERS.get(res_type)
    if parser is None:
        return [], 0

    entries = key.find_all(res_type)
    total = len(entries)
    print(f"Verifying {total} resources of type {res_type.name} ...")

    failures: list[dict] = []
    for i, entry in enumerate(entries, 1):
        if i % 200 == 0 or i == total:
            pct = int(i / total * 100) if total else 100
            print(f"\r  Progress [{res_type.name}]: {i}/{total} ({pct}%)", end="", flush=True)

        try:
            raw = key.read_resource(entry, game_root=inst)
        except Exception as exc:
            failures.append(
                {
                    "game_id": inst.game_id,
                    "resref": str(entry.resref),
                    "type": res_type.name,
                    "stage": "read",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "biff_index": entry.biff_index,
                    "file_index": entry.file_index,
                    "tileset_index": entry.tileset_index,
                }
            )
            continue

        try:
            parser.from_bytes(raw)
        except Exception as exc:
            failures.append(
                {
                    "game_id": inst.game_id,
                    "resref": str(entry.resref),
                    "type": res_type.name,
                    "stage": "parse",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "biff_index": entry.biff_index,
                    "file_index": entry.file_index,
                    "tileset_index": entry.tileset_index,
                }
            )

    print()
    return failures, total


def run(args: argparse.Namespace) -> int:
    finder = InstallationFinder()
    if args.type.upper() == "ALL" and args.output:
        raise SystemExit("Cannot use --output with --type ALL (multiple output files are produced).")
    if args.all_games and args.output:
        raise SystemExit("Cannot use --output with --all-games (would overwrite per-game outputs).")

    selected_types = parse_types(args.type)
    selected_games = pick_games(finder, args.game, args.all_games)

    for inst in selected_games:
        print(f"\nUsing game: {inst.game_id} - {inst.display_name}")
        print("Opening CHITIN.KEY ... ", end="", flush=True)
        try:
            key = KeyFile.open(inst.chitin_key)
        except Exception as exc:
            print("failed.")
            print(f"  ERROR opening KEY for {inst.game_id}: {type(exc).__name__}: {exc}")
            for res_type in selected_types:
                failures = [
                    {
                        "game_id": inst.game_id,
                        "resref": "",
                        "type": res_type.name,
                        "stage": "key_open",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "chitin_key": str(inst.chitin_key),
                    }
                ]
                out_path = Path(args.output) if args.output else default_output_path(inst, res_type.name)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"JSON output: {out_path}")
            continue
        print(f"{key.num_resources} resources across {key.num_biff} BIFF archives.")

        game_total_checked = 0
        game_total_failures = 0
        for res_type in selected_types:
            failures, checked = verify_one_type(inst, key, res_type)
            game_total_checked += checked
            game_total_failures += len(failures)

            out_path = Path(args.output) if args.output else default_output_path(inst, res_type.name)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(failures, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Done [{res_type.name}]. Total checked: {checked}")
            print(f"Failures: {len(failures)}")
            print(f"JSON output: {out_path}")

        if len(selected_types) > 1:
            print(f"Game summary: checked={game_total_checked}, failures={game_total_failures}")

    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify readability/parsability across one or more resource types.")
    parser.add_argument("--game", "-g", metavar="GAME_ID", help="Game ID (e.g. BG2EE). Prompted if omitted.")
    parser.add_argument("--all-games", action="store_true", help="Run verification for all detected games.")
    parser.add_argument("--type", "-t", required=True, metavar="TYPE", help="Resource type (e.g. CRE, SPL, WED) or ALL.")
    parser.add_argument("--output", "-o", metavar="PATH", help="Output JSON path override (single output file target).")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
