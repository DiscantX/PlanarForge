from __future__ import annotations

import hashlib
import json
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Optional

from core.formats.cre import Alignment, Class, CreFile, Gender, Race
from core.formats.key_biff import KeyFile, ResType
from core.formats.mos import MosFile
from core.services.itm_catalog import ItmCatalog
from core.viewmodels.character_vm import CharacterVM, InventorySlotVM, StatVM
from game.installation import GameInstallation, InstallationFinder
from game.string_manager import StringManager


class CharacterService:
    """Cache-backed, read-only CRE -> CharacterVM service."""

    def __init__(
        self,
        *,
        cache_root: Path | str = ".cache",
        finder: Optional[InstallationFinder] = None,
        keyfile_cls: type[KeyFile] = KeyFile,
        string_manager_cls: type[StringManager] = StringManager,
        itm_catalog: Optional[ItmCatalog] = None,
        parser_file: Path | str = "core/formats/cre.py",
    ) -> None:
        self._cache_root = Path(cache_root)
        self._finder = finder or InstallationFinder()
        self._keyfile_cls = keyfile_cls
        self._string_manager_cls = string_manager_cls
        self._itm_catalog = itm_catalog or ItmCatalog(finder=self._finder)
        self._parser_file = Path(parser_file)

        self._selected_game: Optional[GameInstallation] = None
        self._key: Optional[KeyFile] = None
        self._manager: Optional[StringManager] = None
        self._character_index: list[tuple[str, str]] = []
        self._progress_callback: Optional[Callable[[str], None]] = None
        self._pvrz_cache: dict[int, object] = {}  # page_num -> PvrzFile (shared across all resources)

    def list_games(self) -> list[GameInstallation]:
        return self._finder.find_all()

    def set_progress_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """
        Set a callback to receive progress/status updates.
        
        Args:
            callback: Function that receives status messages during loading.
        """
        self._progress_callback = callback

    def select_game(self, game_id: str) -> None:
        inst = self._finder.find(game_id)
        if inst is None:
            raise ValueError(f"Game {game_id!r} not found.")
        self._selected_game = inst
        self._key = None
        self._manager = None
        self._character_index = []
        self._pvrz_cache.clear()  # Clear PVRZ cache when switching games
        self._itm_catalog.select_game(game_id)
        self._itm_catalog.load_index(force_rebuild=False)

    def load_index(self, force_rebuild: bool = False) -> None:
        """Load CRE picker index from cache or rebuild from KEY."""
        inst = self._require_selected_game()
        self._ensure_handles()

        chitin_mtime = inst.chitin_key.stat().st_mtime
        parser_hash = self._parser_hash()
        cache_path = self._cache_path(inst)

        entries: Optional[list[tuple[str, str]]] = None
        if not force_rebuild:
            entries = self._load_index(cache_path, chitin_mtime, parser_hash)
            # Accept existing cache files without strict metadata if they have valid entries.
            if entries is None:
                entries = self._load_index(cache_path, chitin_mtime=None, parser_hash=None)

        if entries is None:
            entries = self._build_index()
            self._save_index(entries, cache_path, chitin_mtime, parser_hash)

        self._character_index = entries

    def search_characters(self, query: str) -> list[tuple[str, str]]:
        if not self._character_index:
            self.load_index(force_rebuild=False)

        q = (query or "").strip().lower()
        if not q:
            return self._character_index

        return [
            (resref, name)
            for resref, name in self._character_index
            if q in resref.lower() or q in name.lower()
        ]

    def load_character(self, cre_resref: str) -> CharacterVM:
        vm, _payload = self.load_character_with_payload(cre_resref)
        return vm

    def load_character_with_payload(self, cre_resref: str) -> tuple[CharacterVM, dict]:
        self._ensure_handles()
        assert self._key is not None

        norm = (cre_resref or "").strip().upper()
        if not norm:
            raise ValueError("CRE ResRef is required.")

        entry = self._key.find(norm, ResType.CRE)
        if entry is None:
            raise ValueError(f"CRE {norm} not found.")

        raw = self._key.read_resource(entry, game_root=self._selected_game)
        self._report_progress(f"Loading {norm}...")
        cre = CreFile.from_bytes(raw)
        self._report_progress(f"Parsing {norm}...")
        h = cre.header

        display_name = self._resolve_strref_int(int(h.name)) or norm
        level = max(int(getattr(h, "level_1", 0)), int(getattr(h, "level_2", 0)), int(getattr(h, "level_3", 0)))

        stats = [
            StatVM("STR", str(int(getattr(h, "str", 0)))),
            StatVM("DEX", str(int(getattr(h, "dex", 0)))),
            StatVM("CON", str(int(getattr(h, "con", 0)))),
            StatVM("INT", str(int(getattr(h, "int", 0)))),
            StatVM("WIS", str(int(getattr(h, "wis", 0)))),
            StatVM("CHA", str(int(getattr(h, "cha", 0)))),
            StatVM("THAC0", str(int(getattr(h, "thac0", 0)))),
            StatVM("AC", str(int(getattr(h, "ac_effective", 0)))),
            StatVM("Attacks", str(int(getattr(h, "attacks", 0)))),
        ]

        inventory: list[InventorySlotVM] = []
        self._report_progress(f"Loading inventory for {norm}...")
        for slot_enum, idx in cre.slots.items():
            if idx == 0xFFFF or idx < 0 or idx >= len(cre.items):
                continue
            item = cre.items[idx]
            item_resref = str(item.resref).strip().upper()
            if not item_resref:
                continue
            item_name, icon = self._itm_catalog.load_item_name_and_icon_by_resref(item_resref)
            inventory.append(
                InventorySlotVM(
                    slot_name=str(getattr(slot_enum, "name", slot_enum)),
                    item_resref=item_resref,
                    item_name=item_name or item_resref,
                    icon=icon,
                )
            )

        vm = CharacterVM(
            resref=norm,
            display_name=display_name,
            race=self._enum_name(Race, int(getattr(h, "race", 0))),
            klass=self._enum_name(Class, int(getattr(h, "klass", 0))),
            gender=self._enum_name(Gender, int(getattr(h, "gender", 0))),
            alignment=self._enum_name(Alignment, int(getattr(h, "alignment", 0))),
            level=level,
            hp_current=int(getattr(h, "current_hp", 0)),
            hp_max=int(getattr(h, "max_hp", 0)),
            stats=stats,
            inventory=inventory,
        )
        self._report_progress(f"Serializing {norm}...")
        payload = cre.to_json()
        return vm, payload

    def load_icon_by_resref(self, resref: str) -> tuple[int, int, list[float]] | None:
        return self._itm_catalog.load_bam_icon_by_resref(resref)

    def load_mos_by_resref(self, resref: str) -> tuple[int, int, list[float]] | None:
        self._ensure_handles()
        assert self._key is not None
        norm = (resref or "").strip().upper()
        if not norm:
            return None
        try:
            entry = self._key.find(norm, ResType.MOS)
            if entry is None:
                return None
            raw = self._key.read_resource(entry, game_root=self._selected_game)
            mos = MosFile.from_bytes(raw)
            rgba_bytes = mos.to_rgba(
                pvrz_loader=self._make_pvrz_loader() if mos.is_pvrz else None
            )
            if rgba_bytes is None:
                return None
            rgba = [b / 255.0 for b in rgba_bytes]
            return mos.width, mos.height, rgba
        except Exception:
            return None

    def _make_pvrz_loader(self):
        """
        Return a callable(page_number) -> raw_pvrz_bytes | None.

        The MOS V2 decoder calls this to load each texture page on demand.
        We pass raw KEY bytes directly — PvrzFile.from_bytes handles
        zlib decompression and PVR3 header parsing internally.
        """
        key   = self._key
        game  = self._selected_game
        cache = self._pvrz_cache  # Use shared PVRZ cache

        def _load(page: int) -> bytes | None:
            if page in cache:
                return cache[page]
            resref = f"MOS{page:04d}"
            try:
                entry = key.find(resref, ResType.PVRZ)
                if entry is None:
                    cache[page] = None
                    return None
                raw = key.read_resource(entry, game_root=game)
                cache[page] = raw
                return raw
            except Exception:
                cache[page] = None
                return None

        return _load

    def load_bam_by_resref(
        self,
        resref: str,
        *,
        cycle: int = 0,
        frame: int = 0,
    ) -> tuple[int, int, list[float]] | None:
        """Load a BAM file and decode a specific cycle/frame to an RGBA texture tuple.

        Args:
            resref: BAM resource name.
            cycle:  Cycle index (from ButtonControl.anim_cycle).
            frame:  Frame index within the cycle (from ButtonControl.frame_unpressed).

        Falls back to decode_first_frame_rgba if cycle/frame resolution fails.
        """
        self._ensure_handles()
        if self._key is None:
            return None
        norm = (resref or "").strip().upper()
        if not norm:
            return None
        try:
            entry = self._key.find(norm, ResType.BAM)
            if entry is None:
                print(f"[BAM] {norm!r} not found in KEY")
                return None
            raw = self._key.read_resource(entry, game_root=self._selected_game)
            from core.formats.bam import decode_cycle_frame_rgba, decode_first_frame_rgba
            pvrz_loader = self._make_pvrz_loader_for_bam()
            try:
                result = decode_cycle_frame_rgba(raw, cycle=cycle, frame=frame, pvrz_loader=pvrz_loader)
                print(f"[BAM] {norm!r} cycle={cycle} frame={frame} decoded OK {result[0]}x{result[1]}")
                return result
            except Exception as e:
                print(f"[BAM] {norm!r} cycle={cycle} frame={frame} decode_cycle failed: {e}, trying first_frame")
                return decode_first_frame_rgba(raw, pvrz_loader=pvrz_loader)
        except Exception as e:
            print(f"[BAM] {norm!r} unexpected error: {e}")
            return None

    def load_chu_by_resref(self, resref: str) -> bytes | None:
        self._ensure_handles()
        if self._key is None:
            return None
        norm = (resref or "").strip().upper()
        if not norm:
            return None
        try:
            entry = self._key.find(norm, ResType.CHU)
            if entry is None:
                return None
            return self._key.read_resource(entry, game_root=self._selected_game)
        except Exception:
            return None

    def _build_index(self) -> list[tuple[str, str]]:
        assert self._key is not None
        rows: list[tuple[str, str]] = []
        for entry in self._key.iter_resources():
            try:
                if int(entry.res_type) != int(ResType.CRE):
                    continue
            except Exception:
                continue

            resref = str(entry.resref).strip().upper()
            if not resref:
                continue

            display_name = ""
            try:
                raw = self._key.read_resource(entry, game_root=self._selected_game)
                parsed = CreFile.from_bytes(raw)
                display_name = self._resolve_strref_int(int(parsed.header.name)).strip()
            except Exception:
                display_name = ""

            rows.append((resref, display_name or resref))
        rows.sort(key=lambda x: (x[1].lower(), x[0].lower()))
        return rows

    def _cache_path(self, inst: GameInstallation) -> Path:
        return self._cache_root / inst.game_id / "index" / "CRE_index.json"

    def _parser_hash(self) -> str:
        try:
            data = self._parser_file.read_bytes()
            return hashlib.md5(data).hexdigest()[:8]
        except OSError:
            return "unknown"

    def _save_index(self, entries: list[tuple[str, str]], path: Path, chitin_mtime: float, parser_hash: str) -> None:
        payload = {
            "chitin_mtime": chitin_mtime,
            "parser_hash": parser_hash,
            "entries": [
                {
                    "resref": resref,
                    "res_type": int(ResType.CRE),
                    "display_name": name,
                    "source": "biff",
                    "data": {},
                }
                for resref, name in entries
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_index(
        self,
        path: Path,
        chitin_mtime: Optional[float],
        parser_hash: Optional[str],
    ) -> Optional[list[tuple[str, str]]]:
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        if chitin_mtime is not None and raw.get("chitin_mtime") != chitin_mtime:
            return None
        if parser_hash is not None and raw.get("parser_hash") != parser_hash:
            return None

        rows: list[tuple[str, str]] = []
        for e in raw.get("entries", []):
            try:
                if int(e.get("res_type", -1)) != int(ResType.CRE):
                    continue
                resref = str(e["resref"]).strip().upper()
                if not resref:
                    continue
                name = str(e.get("display_name", "") or "").strip() or resref
                rows.append((resref, name))
            except Exception:
                continue
        rows.sort(key=lambda x: (x[1].lower(), x[0].lower()))
        return rows

    def _require_selected_game(self) -> GameInstallation:
        if self._selected_game is None:
            raise RuntimeError("No game selected.")
        return self._selected_game

    def _ensure_handles(self) -> None:
        if self._selected_game is None:
            raise RuntimeError("No game selected.")
        if self._key is None:
            self._key = self._keyfile_cls.open(self._selected_game.chitin_key)
        if self._manager is None:
            self._manager = self._string_manager_cls.from_installation(self._selected_game)

    def _resolve_strref_int(self, raw: int) -> str:
        if raw < 0 or raw == 0xFFFFFFFF:
            return ""
        try:
            assert self._manager is not None
            from core.util.strref import StrRef

            return self._manager.resolve(StrRef(raw)) or ""
        except Exception:
            return ""

    @staticmethod
    def _enum_name(enum_cls: type[IntEnum], value: int) -> str:
        try:
            return enum_cls(value).name.replace("_", " ").title()
        except Exception:
            return str(value)

    def _make_pvrz_loader_for_bam(self):
        """Return a callable that loads and caches PVRZ pages as PvrzFile objects."""
        from core.formats.pvrz import PvrzFile
        from core.formats.key_biff import ResType

        key = self._key
        game = self._selected_game
        cache = self._pvrz_cache  # Use shared PVRZ cache

        def loader(page: int):
            if page in cache:
                return cache[page]
            
            try:
                resref = f"MOS{page:04d}"
                entry = key.find(resref, ResType.PVRZ)
                if entry is None:
                    cache[page] = None
                    return None
                raw = key.read_resource(entry, game_root=game)
                try:
                    pvrz = PvrzFile.from_bytes(raw)
                    cache[page] = pvrz
                    return pvrz
                except Exception:
                    cache[page] = None
                    return None
            except Exception:
                cache[page] = None
                return None

        return loader

    def _report_progress(self, message: str) -> None:
        """Report progress to the callback if set."""
        if self._progress_callback:
            self._progress_callback(message)