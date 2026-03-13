"""core/formats/wmp.py

Parser for the Infinity Engine WMAP (World Map) file format.

A WMAP file describes the top-level world map structure: background image,
area icon positions, travel links between areas, and — critically for the
editor — the human-readable caption StrRef and tooltip StrRef for each area
that appears on the world map.

Structure:
    File header  (16 bytes)
      └─ N × Worldmap entry  (184 bytes each)
              └─ M × Area entry     (240 bytes each, absolute offsets)
              └─ L × Area link      (216 bytes each, absolute offsets)

The primary use case is resolving ARE resrefs to display names:

    wmp = WmpFile.from_file("WORLDMAP.WMP")
    names = wmp.area_name_map()      # {"AR0014": StrRef(12345), ...}

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/wmap_v1.htm

Applies to: BG1, BG1:TotS, BG2, BG2:ToB, PST, IWD, IWD:HoW, IWD:TotL,
            IWD2, BGEE
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.resref import ResRef
from core.util.strref import StrRef


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE    = b"WMAP"
VERSION_V1   = b"V1.0"

_WORLDMAP_ENTRY_SIZE = 184   # 0xB8
_AREA_ENTRY_SIZE     = 240   # 0xF0
_AREA_LINK_SIZE      = 216   # 0xD8


# ---------------------------------------------------------------------------
# Area Link  (0xD8 = 216 bytes)
# ---------------------------------------------------------------------------

@dataclass
class WmpAreaLink:
    """One directional travel link between two worldmap areas."""

    dest_area_index:       int          # index into the parent worldmap's area list
    entry_point:           str          # 32-char entrance name in the destination area
    travel_time:           int          # travel time / 4 (game hours)
    default_entry:         int          # bitmask: N/E/S/W side of dest area
    random_encounter_1:    ResRef = field(default_factory=lambda: ResRef(""))
    random_encounter_2:    ResRef = field(default_factory=lambda: ResRef(""))
    random_encounter_3:    ResRef = field(default_factory=lambda: ResRef(""))
    random_encounter_4:    ResRef = field(default_factory=lambda: ResRef(""))
    random_encounter_5:    ResRef = field(default_factory=lambda: ResRef(""))
    random_encounter_prob: int = 0

    # ── Binary ──────────────────────────────────────────────────────────────

    @classmethod
    def _read(cls, r: BinaryReader) -> "WmpAreaLink":
        dest_area_index       = r.read_uint32()
        entry_point           = r.read_string(32)
        travel_time           = r.read_uint32()
        default_entry         = r.read_uint32()
        random_encounter_1    = ResRef(r.read_resref())
        random_encounter_2    = ResRef(r.read_resref())
        random_encounter_3    = ResRef(r.read_resref())
        random_encounter_4    = ResRef(r.read_resref())
        random_encounter_5    = ResRef(r.read_resref())
        random_encounter_prob = r.read_uint32()
        r.skip(128)   # unused padding

        return cls(
            dest_area_index=dest_area_index,
            entry_point=entry_point,
            travel_time=travel_time,
            default_entry=default_entry,
            random_encounter_1=random_encounter_1,
            random_encounter_2=random_encounter_2,
            random_encounter_3=random_encounter_3,
            random_encounter_4=random_encounter_4,
            random_encounter_5=random_encounter_5,
            random_encounter_prob=random_encounter_prob,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint32(self.dest_area_index)
        w.write_string(self.entry_point, 32)
        w.write_uint32(self.travel_time)
        w.write_uint32(self.default_entry)
        w.write_resref(str(self.random_encounter_1))
        w.write_resref(str(self.random_encounter_2))
        w.write_resref(str(self.random_encounter_3))
        w.write_resref(str(self.random_encounter_4))
        w.write_resref(str(self.random_encounter_5))
        w.write_uint32(self.random_encounter_prob)
        w.write_bytes(bytes(128))

    # ── JSON ────────────────────────────────────────────────────────────────

    def to_json(self) -> dict:
        d: dict = {
            "dest_area_index": self.dest_area_index,
            "entry_point":     self.entry_point,
            "travel_time":     self.travel_time,
            "default_entry":   self.default_entry,
        }
        for i, enc in enumerate(
            (
                self.random_encounter_1,
                self.random_encounter_2,
                self.random_encounter_3,
                self.random_encounter_4,
                self.random_encounter_5,
            ),
            start=1,
        ):
            if str(enc):
                d[f"random_encounter_{i}"] = str(enc)
        if self.random_encounter_prob:
            d["random_encounter_prob"] = self.random_encounter_prob
        return d

    @classmethod
    def from_json(cls, d: dict) -> "WmpAreaLink":
        return cls(
            dest_area_index=d.get("dest_area_index", 0),
            entry_point=d.get("entry_point", ""),
            travel_time=d.get("travel_time", 0),
            default_entry=d.get("default_entry", 0),
            random_encounter_1=ResRef(d.get("random_encounter_1", "")),
            random_encounter_2=ResRef(d.get("random_encounter_2", "")),
            random_encounter_3=ResRef(d.get("random_encounter_3", "")),
            random_encounter_4=ResRef(d.get("random_encounter_4", "")),
            random_encounter_5=ResRef(d.get("random_encounter_5", "")),
            random_encounter_prob=d.get("random_encounter_prob", 0),
        )


# ---------------------------------------------------------------------------
# Area Entry  (0xF0 = 240 bytes)
# ---------------------------------------------------------------------------

@dataclass
class WmpAreaEntry:
    """One area icon entry in the world map."""

    area_resref:  ResRef        # the ARE file this entry refers to
    area_name_short: ResRef     # short area name (resref to a 2DA / script name)
    area_name_long:  str        # 32-char internal/script name
    status_flags: int           # visibility/reachable bitmask
    bam_sequence: int           # BAM cycle index for the map icon
    x:            int           # pixel X on the worldmap
    y:            int           # pixel Y on the worldmap
    caption:      StrRef        # display name shown in UI (strref)
    tooltip:      StrRef        # tooltip text (strref)
    loading_mos:  ResRef        # loading screen MOS

    # Link arrays resolved after all entries are loaded
    links_north:  List[WmpAreaLink] = field(default_factory=list)
    links_west:   List[WmpAreaLink] = field(default_factory=list)
    links_south:  List[WmpAreaLink] = field(default_factory=list)
    links_east:   List[WmpAreaLink] = field(default_factory=list)

    # Raw link table indices/counts stored for round-trip write
    _link_idx_n:  int = 0
    _link_cnt_n:  int = 0
    _link_idx_w:  int = 0
    _link_cnt_w:  int = 0
    _link_idx_s:  int = 0
    _link_cnt_s:  int = 0
    _link_idx_e:  int = 0
    _link_cnt_e:  int = 0

    # ── Binary ──────────────────────────────────────────────────────────────

    @classmethod
    def _read(cls, r: BinaryReader) -> "WmpAreaEntry":
        area_resref      = ResRef(r.read_resref())
        area_name_short  = ResRef(r.read_resref())
        area_name_long   = r.read_string(32)
        status_flags     = r.read_uint32()
        bam_sequence     = r.read_uint32()
        x                = r.read_uint32()
        y                = r.read_uint32()
        caption          = StrRef(r.read_uint32())
        tooltip          = StrRef(r.read_uint32())
        loading_mos      = ResRef(r.read_resref())
        link_idx_n       = r.read_uint32()
        link_cnt_n       = r.read_uint32()
        link_idx_w       = r.read_uint32()
        link_cnt_w       = r.read_uint32()
        link_idx_s       = r.read_uint32()
        link_cnt_s       = r.read_uint32()
        link_idx_e       = r.read_uint32()
        link_cnt_e       = r.read_uint32()
        r.skip(128)      # unused padding

        entry = cls(
            area_resref=area_resref,
            area_name_short=area_name_short,
            area_name_long=area_name_long,
            status_flags=status_flags,
            bam_sequence=bam_sequence,
            x=x,
            y=y,
            caption=caption,
            tooltip=tooltip,
            loading_mos=loading_mos,
        )
        entry._link_idx_n = link_idx_n
        entry._link_cnt_n = link_cnt_n
        entry._link_idx_w = link_idx_w
        entry._link_cnt_w = link_cnt_w
        entry._link_idx_s = link_idx_s
        entry._link_cnt_s = link_cnt_s
        entry._link_idx_e = link_idx_e
        entry._link_cnt_e = link_cnt_e
        return entry

    def _write(self, w: BinaryWriter) -> None:
        w.write_resref(str(self.area_resref))
        w.write_resref(str(self.area_name_short))
        w.write_string(self.area_name_long, 32)
        w.write_uint32(self.status_flags)
        w.write_uint32(self.bam_sequence)
        w.write_uint32(self.x)
        w.write_uint32(self.y)
        w.write_uint32(int(self.caption))
        w.write_uint32(int(self.tooltip))
        w.write_resref(str(self.loading_mos))
        w.write_uint32(self._link_idx_n)
        w.write_uint32(self._link_cnt_n)
        w.write_uint32(self._link_idx_w)
        w.write_uint32(self._link_cnt_w)
        w.write_uint32(self._link_idx_s)
        w.write_uint32(self._link_cnt_s)
        w.write_uint32(self._link_idx_e)
        w.write_uint32(self._link_cnt_e)
        w.write_bytes(bytes(128))

    # ── JSON ────────────────────────────────────────────────────────────────

    def to_json(self) -> dict:
        d: dict = {
            "area_resref":     str(self.area_resref),
            "area_name_short": str(self.area_name_short),
            "area_name_long":  self.area_name_long,
            "status_flags":    self.status_flags,
            "bam_sequence":    self.bam_sequence,
            "x":               self.x,
            "y":               self.y,
            "caption":         self.caption.to_json(),
            "tooltip":         self.tooltip.to_json(),
        }
        if str(self.loading_mos):
            d["loading_mos"] = str(self.loading_mos)
        for direction, links in (
            ("links_north", self.links_north),
            ("links_west",  self.links_west),
            ("links_south", self.links_south),
            ("links_east",  self.links_east),
        ):
            if links:
                d[direction] = [lk.to_json() for lk in links]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "WmpAreaEntry":
        entry = cls(
            area_resref=ResRef(d.get("area_resref", "")),
            area_name_short=ResRef(d.get("area_name_short", "")),
            area_name_long=d.get("area_name_long", ""),
            status_flags=d.get("status_flags", 0),
            bam_sequence=d.get("bam_sequence", 0),
            x=d.get("x", 0),
            y=d.get("y", 0),
            caption=StrRef.from_json(d.get("caption", 0xFFFFFFFF)),
            tooltip=StrRef.from_json(d.get("tooltip", 0xFFFFFFFF)),
            loading_mos=ResRef(d.get("loading_mos", "")),
        )
        entry.links_north = [WmpAreaLink.from_json(lk) for lk in d.get("links_north", [])]
        entry.links_west  = [WmpAreaLink.from_json(lk) for lk in d.get("links_west",  [])]
        entry.links_south = [WmpAreaLink.from_json(lk) for lk in d.get("links_south", [])]
        entry.links_east  = [WmpAreaLink.from_json(lk) for lk in d.get("links_east",  [])]
        return entry


# ---------------------------------------------------------------------------
# Worldmap Entry  (0xB8 = 184 bytes)
# ---------------------------------------------------------------------------

@dataclass
class WmpWorldmapEntry:
    """One worldmap panel (most games have exactly one)."""

    background_mos: ResRef
    width:          int
    height:         int
    map_number:     int
    name:           StrRef      # strref for the worldmap panel name
    start_x:        int
    start_y:        int
    map_icons_bam:  ResRef
    flags:          int         # BGEE colour-icons flag

    areas: List[WmpAreaEntry] = field(default_factory=list)

    # Raw area/link offsets for round-trip write
    _area_offset: int = 0
    _link_offset: int = 0

    # ── Binary ──────────────────────────────────────────────────────────────

    @classmethod
    def _read_header(cls, r: BinaryReader) -> "WmpWorldmapEntry":
        """Read the fixed 184-byte worldmap entry header (no areas yet)."""
        background_mos = ResRef(r.read_resref())
        width          = r.read_uint32()
        height         = r.read_uint32()
        map_number     = r.read_uint32()
        name           = StrRef(r.read_uint32())
        start_x        = r.read_uint32()
        start_y        = r.read_uint32()
        area_count     = r.read_uint32()
        area_offset    = r.read_uint32()
        link_offset    = r.read_uint32()
        link_count     = r.read_uint32()  # noqa: F841 (needed to consume bytes)
        map_icons_bam  = ResRef(r.read_resref())
        flags          = r.read_uint32()
        r.skip(124)    # unused padding

        entry = cls(
            background_mos=background_mos,
            width=width,
            height=height,
            map_number=map_number,
            name=name,
            start_x=start_x,
            start_y=start_y,
            map_icons_bam=map_icons_bam,
            flags=flags,
        )
        entry._area_offset = area_offset
        entry._area_count  = area_count   # type: ignore[attr-defined]
        entry._link_offset = link_offset
        return entry

    def _write_header(self, w: BinaryWriter, area_offset: int, link_offset: int) -> None:
        w.write_resref(str(self.background_mos))
        w.write_uint32(self.width)
        w.write_uint32(self.height)
        w.write_uint32(self.map_number)
        w.write_uint32(int(self.name))
        w.write_uint32(self.start_x)
        w.write_uint32(self.start_y)
        w.write_uint32(len(self.areas))
        w.write_uint32(area_offset)
        link_count = sum(
            len(a.links_north) + len(a.links_west) + len(a.links_south) + len(a.links_east)
            for a in self.areas
        )
        # link_offset written before link_count in the format
        w.write_uint32(link_offset)
        w.write_uint32(link_count)
        w.write_resref(str(self.map_icons_bam))
        w.write_uint32(self.flags)
        w.write_bytes(bytes(124))

    # ── JSON ────────────────────────────────────────────────────────────────

    def to_json(self) -> dict:
        return {
            "background_mos": str(self.background_mos),
            "width":          self.width,
            "height":         self.height,
            "map_number":     self.map_number,
            "name":           self.name.to_json(),
            "start_x":        self.start_x,
            "start_y":        self.start_y,
            "map_icons_bam":  str(self.map_icons_bam),
            "flags":          self.flags,
            "areas":          [a.to_json() for a in self.areas],
        }

    @classmethod
    def from_json(cls, d: dict) -> "WmpWorldmapEntry":
        entry = cls(
            background_mos=ResRef(d.get("background_mos", "")),
            width=d.get("width", 0),
            height=d.get("height", 0),
            map_number=d.get("map_number", 0),
            name=StrRef.from_json(d.get("name", 0xFFFFFFFF)),
            start_x=d.get("start_x", 0),
            start_y=d.get("start_y", 0),
            map_icons_bam=ResRef(d.get("map_icons_bam", "")),
            flags=d.get("flags", 0),
        )
        entry.areas = [WmpAreaEntry.from_json(a) for a in d.get("areas", [])]
        return entry


# ---------------------------------------------------------------------------
# WmpFile  (top-level container)
# ---------------------------------------------------------------------------

class WmpFile:
    """
    Parsed WMAP (World Map) file.

    Most games ship a single WORLDMAP.WMP containing one worldmap entry with
    all overworld areas.  BG2:ToB and BGEE may reference multiple worldmap
    panels.

    Usage::

        wmp = WmpFile.from_file("WORLDMAP.WMP")

        # Quick lookup: ARE resref → caption StrRef
        names = wmp.area_name_map()
        # e.g. {"AR0014": StrRef(12345), "AR0016": StrRef(12346), ...}

        # Resolve via StringManager
        from game.string_manager import StringManager
        manager = StringManager.from_installation(inst)
        for resref, strref in names.items():
            print(resref, manager.resolve(strref))
    """

    def __init__(self, worldmaps: List[WmpWorldmapEntry], source_path: Optional[Path] = None) -> None:
        self.worldmaps   = worldmaps
        self.source_path = source_path

    # ── Construction ────────────────────────────────────────────────────────

    @classmethod
    def from_bytes(cls, data: bytes) -> "WmpFile":
        r = BinaryReader(data)

        # Header
        try:
            sig = r.read_bytes(4)
            if sig != SIGNATURE:
                raise SignatureMismatch(f"Expected WMAP signature, got {sig!r}")
            ver = r.read_bytes(4)
            if ver != VERSION_V1:
                raise SignatureMismatch(f"Unsupported WMAP version {ver!r}")
        except SignatureMismatch:
            raise

        wm_count  = r.read_uint32()
        wm_offset = r.read_uint32()

        # Read worldmap entry headers
        worldmaps: List[WmpWorldmapEntry] = []
        for i in range(wm_count):
            r.seek(wm_offset + i * _WORLDMAP_ENTRY_SIZE)
            wm = WmpWorldmapEntry._read_header(r)
            worldmaps.append(wm)

        # For each worldmap, read its area entries and link entries
        for wm in worldmaps:
            area_count: int = getattr(wm, "_area_count", 0)

            # All link entries for this worldmap are stored in one flat array
            # beginning at wm._link_offset; areas reference slices by index+count.
            # Collect all links first, then slice into each area.
            all_links: List[WmpAreaLink] = []
            # We need to know the total link count — derive from the last area's
            # index+count after reading areas, so read areas first (no links yet).
            raw_areas: List[WmpAreaEntry] = []
            for j in range(area_count):
                r.seek(wm._area_offset + j * _AREA_ENTRY_SIZE)
                raw_areas.append(WmpAreaEntry._read(r))

            # Determine total link count
            if raw_areas:
                # Max of (index + count) across all directions and all areas
                max_link_end = 0
                for a in raw_areas:
                    for idx, cnt in (
                        (a._link_idx_n, a._link_cnt_n),
                        (a._link_idx_w, a._link_cnt_w),
                        (a._link_idx_s, a._link_cnt_s),
                        (a._link_idx_e, a._link_cnt_e),
                    ):
                        max_link_end = max(max_link_end, idx + cnt)
                r.seek(wm._link_offset)
                for _ in range(max_link_end):
                    all_links.append(WmpAreaLink._read(r))

            # Resolve link slices into each area entry
            for a in raw_areas:
                a.links_north = all_links[a._link_idx_n : a._link_idx_n + a._link_cnt_n]
                a.links_west  = all_links[a._link_idx_w : a._link_idx_w + a._link_cnt_w]
                a.links_south = all_links[a._link_idx_s : a._link_idx_s + a._link_cnt_s]
                a.links_east  = all_links[a._link_idx_e : a._link_idx_e + a._link_cnt_e]

            wm.areas = raw_areas

        return cls(worldmaps)

    @classmethod
    def from_file(cls, path: str | Path) -> "WmpFile":
        path = Path(path)
        inst = cls.from_bytes(path.read_bytes())
        inst.source_path = path
        return inst

    # ── Serialisation ───────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        w = BinaryWriter()

        # File header
        w.write_bytes(SIGNATURE)
        w.write_bytes(VERSION_V1)
        w.write_uint32(len(self.worldmaps))
        wm_offset = 16  # header is always 16 bytes
        w.write_uint32(wm_offset)

        # We need absolute offsets for areas and links.
        # Worldmap headers come first, then area entries, then link entries.
        wm_headers_size = len(self.worldmaps) * _WORLDMAP_ENTRY_SIZE

        # Calculate per-worldmap area offsets (area blocks packed after all headers)
        area_offsets: List[int] = []
        link_offsets: List[int] = []
        cursor = wm_offset + wm_headers_size
        for wm in self.worldmaps:
            area_offsets.append(cursor)
            cursor += len(wm.areas) * _AREA_ENTRY_SIZE
        # Link blocks follow all area blocks
        for i, wm in enumerate(self.worldmaps):
            link_offsets.append(cursor)
            total_links = sum(
                len(a.links_north) + len(a.links_west) + len(a.links_south) + len(a.links_east)
                for a in wm.areas
            )
            cursor += total_links * _AREA_LINK_SIZE

        # Write worldmap headers
        for i, wm in enumerate(self.worldmaps):
            wm._write_header(w, area_offsets[i], link_offsets[i])

        # Write area entries and update link indices
        for i, wm in enumerate(self.worldmaps):
            link_cursor = 0
            for a in wm.areas:
                a._link_idx_n = link_cursor;  a._link_cnt_n = len(a.links_north); link_cursor += a._link_cnt_n
                a._link_idx_w = link_cursor;  a._link_cnt_w = len(a.links_west);  link_cursor += a._link_cnt_w
                a._link_idx_s = link_cursor;  a._link_cnt_s = len(a.links_south); link_cursor += a._link_cnt_s
                a._link_idx_e = link_cursor;  a._link_cnt_e = len(a.links_east);  link_cursor += a._link_cnt_e
                a._write(w)

        # Write link entries
        for wm in self.worldmaps:
            for a in wm.areas:
                for lk in (*a.links_north, *a.links_west, *a.links_south, *a.links_east):
                    lk._write(w)

        return w.get_bytes()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # ── JSON ────────────────────────────────────────────────────────────────

    def to_json(self) -> dict:
        return {
            "signature":  "WMAP",
            "version":    "V1.0",
            "worldmaps":  [wm.to_json() for wm in self.worldmaps],
        }

    def to_json_file(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls, d: dict) -> "WmpFile":
        worldmaps = [WmpWorldmapEntry.from_json(wm) for wm in d.get("worldmaps", [])]
        return cls(worldmaps)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "WmpFile":
        path = Path(path)
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))

    # ── Convenience ─────────────────────────────────────────────────────────

    def area_name_map(self) -> Dict[str, StrRef]:
        """
        Return a mapping of ARE resref (uppercase) → caption StrRef.

        Only areas whose caption StrRef is valid (not 0xFFFFFFFF) are
        included.  Areas not present in the worldmap (dungeons, interiors)
        will simply not appear in this dict.

            names = wmp.area_name_map()
            strref = names.get("AR0014")   # StrRef(12345) or None
        """
        result: Dict[str, StrRef] = {}
        for wm in self.worldmaps:
            for area in wm.areas:
                resref = str(area.area_resref).upper()
                if resref and not area.caption.is_none:
                    result[resref] = area.caption
        return result

    def area_tooltip_map(self) -> Dict[str, StrRef]:
        """Return a mapping of ARE resref → tooltip StrRef (same caveat as area_name_map)."""
        result: Dict[str, StrRef] = {}
        for wm in self.worldmaps:
            for area in wm.areas:
                resref = str(area.area_resref).upper()
                if resref and not area.tooltip.is_none:
                    result[resref] = area.tooltip
        return result

    def __repr__(self) -> str:
        total_areas = sum(len(wm.areas) for wm in self.worldmaps)
        src = self.source_path.name if self.source_path else "?"
        return f"<WmpFile {src!r} worldmaps={len(self.worldmaps)} areas={total_areas}>"