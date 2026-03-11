from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from core.formats.bam import decode_first_frame_rgba
from core.formats.bmp import decode_bmp_rgba
from core.formats.itm import ItmFile
from core.formats.key_biff import KeyFile
from core.util.enums import ResType
from core.index import IndexEntry, ResourceIndex, SOURCE_BIFF
from core.util.resref import ResRef
from core.util.strref import StrRef
from core.services.opcode_registry import OpcodeRegistry
from game.ids_manager import IdsManager
from game.installation import GameInstallation, InstallationFinder
from game.string_manager import StringManager


class ItmCatalog:
    """Cache-backed, read-only ITM catalog for UI consumers."""

    def __init__(
        self,
        *,
        cache_root: Path | str = ".cache",
        finder: Optional[InstallationFinder] = None,
        keyfile_cls: type[KeyFile] = KeyFile,
        string_manager_cls: type[StringManager] = StringManager,
        ids_manager_cls: type[IdsManager] = IdsManager,
        item_parser_cls: type[ItmFile] = ItmFile,
        index_cls: type[ResourceIndex] = ResourceIndex,
        parser_file: Path | str = "core/formats/itm.py",
    ) -> None:
        self._cache_root = Path(cache_root)
        self._finder = finder or InstallationFinder()
        self._keyfile_cls = keyfile_cls
        self._string_manager_cls = string_manager_cls
        self._ids_manager_cls = ids_manager_cls
        self._item_parser_cls = item_parser_cls
        self._index_cls = index_cls
        self._parser_file = Path(parser_file)

        self._selected_game: Optional[GameInstallation] = None
        self._key: Optional[KeyFile] = None
        self._manager: Optional[StringManager] = None
        self._ids_manager: Optional[IdsManager] = None
        self._index: Optional[ResourceIndex] = None

    def list_games(self) -> list[GameInstallation]:
        """Return all discoverable installations."""
        return self._finder.find_all()

    def select_game(self, game_id: str) -> None:
        """Select a game by ID and reset loaded resources."""
        inst = self._finder.find(game_id)
        if inst is None:
            raise ValueError(f"Game {game_id!r} not found.")
        self._selected_game = inst
        self._key = None
        self._manager = None
        self._ids_manager = None
        self._index = None

    def load_index(self, force_rebuild: bool = False) -> None:
        """Load cached ITM index or build it from CHITIN.KEY."""
        inst = self._require_selected_game()
        self._ensure_runtime_handles()

        chitin_mtime = inst.chitin_key.stat().st_mtime
        cache_path = self._cache_path(inst)
        parser_hash = self._parser_hash()

        index: Optional[ResourceIndex] = None
        if not force_rebuild:
            index = self._load_index(cache_path, chitin_mtime, parser_hash)

        if index is None:
            index = self._build_index()
            self._save_index(index, cache_path, chitin_mtime, parser_hash)

        self._index = index

    def search_items(self, query: str) -> list[IndexEntry]:
        """Deep-search indexed ITMs by ResRef, name, and JSON text."""
        if self._index is None:
            self.load_index(force_rebuild=False)
        assert self._index is not None

        q = query.strip().lower()
        if not q:
            return self._index.search(res_type=ResType.ITM)

        results: list[IndexEntry] = []
        for entry in self._index.search(res_type=ResType.ITM):
            if q in str(entry.resref).lower():
                results.append(entry)
                continue
            if q in (entry.display_name or "").lower():
                results.append(entry)
                continue
            payload = json.dumps(entry.data, ensure_ascii=False, sort_keys=True).lower()
            if q in payload:
                results.append(entry)
        return results

    def load_item(self, entry: IndexEntry) -> dict:
        """Return parsed JSON data for a selected ITM entry."""
        if int(entry.res_type) != int(ResType.ITM):
            raise ValueError("Entry is not an ITM resource.")
        return entry.data or {}

    def load_item_icon(self, entry: IndexEntry) -> tuple[int, int, list[float]] | None:
        """Load first-frame inventory BAM icon for an ITM entry, if available."""
        if int(entry.res_type) != int(ResType.ITM):
            return None
        self._ensure_runtime_handles()
        assert self._key is not None

        header = (entry.data or {}).get("header", {})
        if not isinstance(header, dict):
            return None
        icon_resref = self._normalize_resrefish(header.get("item_icon", ""))
        if not icon_resref:
            return None

        try:
            key_entry = self._key.find(icon_resref, ResType.BAM)
            if key_entry is None:
                return None
            raw = self._key.read_resource(key_entry, game_root=self._selected_game)
            return decode_first_frame_rgba(raw)
        except Exception:
            return None

    def load_item_name_and_icon_by_resref(self, itm_resref: Any) -> tuple[str, tuple[int, int, list[float]] | None]:
        """Resolve ITM name and inventory icon by ITM ResRef."""
        self._ensure_runtime_handles()
        assert self._key is not None
        assert self._manager is not None

        resref = self._normalize_resrefish(itm_resref)
        if not resref:
            return "", None
        try:
            itm_entry = self._key.find(resref, ResType.ITM)
            if itm_entry is None:
                return "", None
            raw_itm = self._key.read_resource(itm_entry, game_root=self._selected_game)
            parsed = self._item_parser_cls.from_bytes(raw_itm)

            icon_resref = self._normalize_resrefish(getattr(parsed.header, "item_icon", ""))
            icon = self.load_bam_icon_by_resref(icon_resref) if icon_resref else None

            name = ""
            for raw_strref in (parsed.header.identified_name, parsed.header.unidentified_name):
                try:
                    from core.util.strref import StrRef

                    value = int(raw_strref)
                    if value == 0xFFFFFFFF:
                        continue
                    name = self._manager.resolve(StrRef(value)) or ""
                except Exception:
                    name = ""
                if name:
                    break
            return name, icon
        except Exception:
            return "", None

    def load_item_icon_by_itm_resref(self, itm_resref: Any) -> tuple[int, int, list[float]] | None:
        """Resolve an ITM ResRef and return its inventory icon preview."""
        _name, icon = self.load_item_name_and_icon_by_resref(itm_resref)
        return icon

    def load_bam_icon_by_resref(self, bam_resref: Any) -> tuple[int, int, list[float]] | None:
        """Load first-frame BAM/BMP icon texture by resref."""
        icon, _status = self.load_bam_icon_by_resref_with_status(bam_resref)
        return icon

    def load_bam_icon_by_resref_with_status(
        self, bam_resref: Any
    ) -> tuple[tuple[int, int, list[float]] | None, str]:
        """Load first-frame BAM/BMP icon texture by resref with diagnostic status."""
        self._ensure_runtime_handles()
        assert self._key is not None

        raw = self._normalize_resrefish(bam_resref)
        if not raw:
            return None, "empty resref"

        # Accept values like "FOO.BAM"/"FOO.BMP" and probe common IE naming variants.
        base = raw
        if base.endswith(".BAM") or base.endswith(".BMP"):
            base = base[:-4]
        candidates: list[str] = [base]
        if base.startswith("C") and len(base) > 1:
            candidates.append(base[1:])
        else:
            candidates.append(f"C{base}")
        candidates.append(f"#{base}")
        # ResRef semantics are max 8 chars; include a strict-8 fallback.
        if len(base) > 8:
            candidates.append(base[:8])

        seen: set[str] = set()
        notes: list[str] = []
        for resref in candidates:
            if not resref or resref in seen:
                continue
            seen.add(resref)
            # Prefer BAM; fallback to BMP for installs/resources that use BMP icons.
            for res_type, label, decoder in (
                (ResType.BAM, "BAM", decode_first_frame_rgba),
                (ResType.BMP, "BMP", decode_bmp_rgba),
            ):
                try:
                    key_entry = self._key.find(resref, res_type)
                except Exception as exc:
                    notes.append(f"{label}:{resref} find-error={type(exc).__name__}")
                    continue
                if key_entry is None:
                    continue

                try:
                    payload = self._key.read_resource(key_entry, game_root=self._selected_game)
                except Exception as exc:
                    notes.append(f"{label}:{resref} read-error={type(exc).__name__}")
                    continue
                try:
                    return decoder(payload), f"{label}:{resref}"
                except Exception as exc:
                    notes.append(f"{label}:{resref} decode-error={type(exc).__name__}")

        if notes:
            return None, notes[0]
        return None, "not found in BAM/BMP"

    @staticmethod
    def _normalize_resrefish(value: Any) -> str:
        """Convert common ResRef representations to normalized uppercase text."""
        if isinstance(value, ResRef):
            return str(value).strip().upper()
        if isinstance(value, str):
            return value.strip().upper()
        if isinstance(value, dict):
            for key in ("resref", "value", "name", "id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip().upper()
        return ""

    def resolve_strref(self, raw_value: int) -> str:
        """Resolve a raw StrRef uint32 to localized text."""
        if not isinstance(raw_value, int):
            return ""
        self._ensure_runtime_handles()
        assert self._manager is not None
        try:
            ref = StrRef(raw_value)
        except Exception:
            return ""
        return self._manager.resolve(ref) or ""

    def resolve_ids(self, ids_name: str, raw_value: int) -> str:
        """Resolve a raw IDS value to its symbolic name."""
        if not isinstance(raw_value, int):
            return ""
        self._ensure_runtime_handles()
        assert self._ids_manager is not None
        try:
            table = self._ids_manager.get(ids_name)
        except Exception:
            return ""
        return table.resolve(raw_value)

    def resolve_opcode(self, opcode: int) -> tuple[str, str]:
        """Resolve an opcode value to (name, description) using bundled tables."""
        if not isinstance(opcode, int):
            return "", ""
        game_id = ""
        if self._selected_game is not None:
            game_id = self._selected_game.game_id
        registry = OpcodeRegistry.for_game(game_id)
        entry = registry.resolve(opcode)
        return entry.name, entry.description

    def resolve_kit_usability_mask(self, raw_value: int, *, bit_offset: int = 0) -> str:
        """
        Resolve a kit usability bitmask (KITLIST.2DA) to kit names.

        Returns a " | "-joined list of kit names, or "" if unresolved.
        """
        if not isinstance(raw_value, int) or raw_value == 0:
            return ""
        self._ensure_runtime_handles()
        inst = self._require_selected_game()
        assert self._key is not None
        # Prefer 2DA kitlist from override or BIFF.
        try:
            entry = self._key.find("KITLIST", ResType.TWO_DA)
            if entry is None:
                return ""
            raw = self._key.read_resource(entry, game_root=inst)
        except Exception:
            return ""

        try:
            text = raw.decode("latin-1", errors="replace")
            table = _parse_2da(text)
        except Exception:
            return ""

        kits: list[str] = []
        for idx, row in enumerate(table.get("rows", [])):
            kit_name = row.get("KITNAME") or row.get("KIT") or row.get("LOWER") or row.get("NAME")
            if not kit_name:
                continue
            bit_index = idx - bit_offset
            if bit_index < 0 or bit_index >= 8:
                continue
            if raw_value & (1 << bit_index):
                label = str(kit_name)
                # Many KITLIST.2DA entries store a STRREF in KITNAME.
                try:
                    ref = int(label)
                    if ref >= 0:
                        resolved = self.resolve_strref(ref)
                        if resolved:
                            label = resolved
                except Exception:
                    pass
                kits.append(label)
        return " | ".join(kits)

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
        if self._ids_manager is None:
            self._ids_manager = self._ids_manager_cls(inst)

    def _build_index(self) -> ResourceIndex:
        assert self._key is not None
        assert self._manager is not None

        index = self._index_cls()
        for entry in self._key.iter_resources():
            try:
                if int(entry.res_type) != int(ResType.ITM):
                    continue
            except Exception:
                continue

            try:
                raw = self._key.read_resource(entry, game_root=self._selected_game)
                parsed = self._item_parser_cls.from_bytes(raw)
                data = parsed.to_json()
            except Exception:
                continue

            display_name = ""
            try:
                display_name = self._manager.resolve(parsed.header.identified_name) or ""
            except Exception:
                pass

            try:
                resref = entry.resref if isinstance(entry.resref, ResRef) else ResRef(str(entry.resref))
                index.add_or_update(
                    resref=resref,
                    res_type=ResType.ITM,
                    source=SOURCE_BIFF,
                    data=data,
                    display_name=display_name,
                )
            except Exception:
                continue

        return index

    def _cache_path(self, inst: GameInstallation) -> Path:
        return self._cache_root / inst.game_id / "index" / "ITM_index.json"

    def _parser_hash(self) -> str:
        try:
            data = self._parser_file.read_bytes()
            return hashlib.md5(data).hexdigest()[:8]
        except OSError:
            return "unknown"


    def _save_index(self, index: ResourceIndex, path: Path, chitin_mtime: float, parser_hash: str) -> None:
        entries: list[dict[str, Any]] = []
        for e in index.search(res_type=ResType.ITM):
            entries.append(
                {
                    "resref": str(e.resref),
                    "res_type": int(e.res_type),
                    "display_name": e.display_name,
                    "source": e.source,
                    "data": e.data,
                }
            )

        payload = {
            "chitin_mtime": chitin_mtime,
            "parser_hash": parser_hash,
            "entries": entries,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_index(self, path: Path, chitin_mtime: float, parser_hash: str) -> Optional[ResourceIndex]:
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


def _parse_2da(text: str) -> dict:
    """
    Minimal 2DA parser sufficient for KITLIST.2DA.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {"columns": [], "rows": []}

    idx = 0
    if lines[idx].upper().startswith("2DA"):
        idx += 1
    if idx < len(lines) and lines[idx].upper().startswith("V"):
        idx += 1

    # Default value line (ignored)
    if idx < len(lines):
        idx += 1

    if idx >= len(lines):
        return {"columns": [], "rows": []}

    headers = lines[idx].split()
    idx += 1

    rows: list[dict] = []
    for line in lines[idx:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        row_id = parts[0]
        values = parts[1:]
        row = {"_row_id": row_id}
        for i, col in enumerate(headers):
            if i < len(values):
                row[col] = values[i]
        rows.append(row)

    return {"columns": headers, "rows": rows}
