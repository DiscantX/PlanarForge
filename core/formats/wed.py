"""
core/formats/wed.py

Parser and writer for the Infinity Engine WED (World Editor Data) format.

The WED file describes the static geometry of an area: its tile overlays,
the tilemap that selects and positions tiles from the companion TIS file,
and the wall polygon mesh used for line-of-sight and pathfinding.

One WED file corresponds to one ARE file (same resref, different extension).
The engine renders the area background by reading overlay tilemaps; blocks
line-of-sight using the wall polygons; and uses the polygon table to mark
areas as impassable.

Structure:
    Header
        N × Overlay          (one per visual layer; overlay 0 is the base)
            Each overlay has:
                W×H tilemap entries   (one per tile cell)
                lookup table          (maps tilemap indices to TIS tile numbers)
        M × Door             (door records linking WED geometry to ARE doors)
        P × Polygon          (wall / LOS polygons)
            Each polygon has K vertices
        polygon index table  (per-tile-cell index into polygon array)

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/wed_v1.3.htm

Usage::

    from core.formats.wed import WedFile

    wed = WedFile.from_file("AR0602.wed")
    print(wed.header.width, wed.header.height)  # area dimensions in tiles
    overlay = wed.overlays[0]
    cell = overlay.tilemap[0]                   # first tile cell
    print(cell.primary_tile_index)              # TIS tile number
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.enums import PolygonFlag, TilemapFlag


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE    = b"WED "
VERSION      = b"V1.3"

HEADER_SIZE       = 32
OVERLAY_HDR_SIZE  = 24
TILEMAP_ENTRY_SIZE = 10
DOOR_SIZE         = 16
POLYGON_HDR_SIZE  = 18


# ---------------------------------------------------------------------------
# TilemapEntry  (10 bytes)
# ---------------------------------------------------------------------------

@dataclass
class TilemapEntry:
    """
    One tile cell in an overlay's tilemap.

    ``primary_tile_index`` indexes the overlay's lookup table, which in turn
    gives the TIS tile number.  ``secondary_tile_index`` is used for the
    alternate night-mode tile when ``flags & EXTENDED_NIGHT``.
    ``overlay_mask`` is a bitmask of which upper overlays (1-7) are visible
    in this cell.
    """
    primary_tile_index:   int = 0    # uint16 — index into tile lookup table
    secondary_tile_index: int = 0    # uint16 — alternate tile (night / special)
    overlay_mask:         int = 0    # uint8  — bits 0-7 for overlays 1-7
    flags:                int = 0    # TilemapFlag (uint8)
    unknown:              int = 0    # uint16 — unused

    @classmethod
    def _read(cls, r: BinaryReader) -> "TilemapEntry":
        pti  = r.read_uint16()
        sti  = r.read_uint16()
        mask = r.read_uint8()
        flags = r.read_uint8()
        unk  = r.read_uint16()
        r.skip(2)  # additional padding in some files
        return cls(primary_tile_index=pti, secondary_tile_index=sti,
                   overlay_mask=mask, flags=flags, unknown=unk)

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint16(self.primary_tile_index)
        w.write_uint16(self.secondary_tile_index)
        w.write_uint8(self.overlay_mask)
        w.write_uint8(self.flags)
        w.write_uint16(self.unknown)
        w.write_padding(2)

    def to_json(self) -> dict:
        d: dict = {"pti": self.primary_tile_index}
        if self.secondary_tile_index: d["sti"]  = self.secondary_tile_index
        if self.overlay_mask:         d["mask"] = self.overlay_mask
        if self.flags:                d["flags"] = self.flags
        return d

    @classmethod
    def from_json(cls, d: dict) -> "TilemapEntry":
        return cls(
            primary_tile_index   = d.get("pti", 0),
            secondary_tile_index = d.get("sti", 0),
            overlay_mask         = d.get("mask", 0),
            flags                = d.get("flags", 0),
        )


# ---------------------------------------------------------------------------
# Overlay  (header 24 bytes + tilemap + lookup table)
# ---------------------------------------------------------------------------

@dataclass
class Overlay:
    """
    One visual layer in the area.

    Overlay 0 is the base floor layer, always present.  Overlays 1-7 are
    optional upper layers (water, lava, etc.) drawn on top of overlay 0.

    ``tilemap``       — W×H :class:`TilemapEntry` objects (row-major)
    ``tile_lookup``   — flat list of TIS tile indices referenced by tilemap
    """
    width:        int  = 0      # uint16 — in tiles
    height:       int  = 0      # uint16
    tis_resref:   str  = ""     # ResRef — companion TIS file
    num_unique_tiles: int = 0   # uint16
    movement_type:    int = 0   # uint16
    tilemap_offset:   int = 0   # uint32
    lookup_offset:    int = 0   # uint32

    tilemap:     List[TilemapEntry] = field(default_factory=list)
    tile_lookup: List[int]          = field(default_factory=list)  # uint16 each

    @classmethod
    def _read_header(cls, r: BinaryReader) -> "Overlay":
        width       = r.read_uint16()
        height      = r.read_uint16()
        tis_resref  = r.read_resref()
        num_unique  = r.read_uint16()
        mov_type    = r.read_uint16()
        tm_off      = r.read_uint32()
        lk_off      = r.read_uint32()
        return cls(width=width, height=height, tis_resref=tis_resref,
                   num_unique_tiles=num_unique, movement_type=mov_type,
                   tilemap_offset=tm_off, lookup_offset=lk_off)

    def _read_data(self, r: BinaryReader) -> None:
        """Read tilemap and lookup table using stored offsets."""
        cell_count = self.width * self.height
        r.seek(self.tilemap_offset)
        self.tilemap = [TilemapEntry._read(r) for _ in range(cell_count)]

        r.seek(self.lookup_offset)
        self.tile_lookup = [r.read_uint16() for _ in range(self.num_unique_tiles)]

    def _write_header(self, w: BinaryWriter,
                      tilemap_offset: int, lookup_offset: int) -> None:
        w.write_uint16(self.width)
        w.write_uint16(self.height)
        w.write_resref(self.tis_resref)
        w.write_uint16(len(self.tile_lookup))
        w.write_uint16(self.movement_type)
        w.write_uint32(tilemap_offset)
        w.write_uint32(lookup_offset)

    def to_json(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "tis_resref": self.tis_resref,
            "movement_type": self.movement_type,
            "tilemap":     [t.to_json() for t in self.tilemap],
            "tile_lookup": self.tile_lookup,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Overlay":
        ov = cls(
            width=d.get("width",0), height=d.get("height",0),
            tis_resref=d.get("tis_resref",""),
            movement_type=d.get("movement_type",0),
        )
        ov.tilemap     = [TilemapEntry.from_json(t) for t in d.get("tilemap",[])]
        ov.tile_lookup = d.get("tile_lookup",[])
        return ov


# ---------------------------------------------------------------------------
# WedDoor  (16 bytes + tile cell index list)
# ---------------------------------------------------------------------------

@dataclass
class WedDoor:
    """
    A door record in the WED, linking a named door to its tile cells.

    When the door opens or closes, the engine swaps the TIS tile indices
    in the associated cells.  ``cell_indices`` lists which tilemap cells
    (by flat index into overlay 0's tilemap) belong to this door.
    """
    name:              str   = ""    # ResRef — matches ARE door resref
    open_:             int   = 0     # uint16 — 0=closed, 1=open
    cell_index_first:  int   = 0     # uint16 — first index in the cell list
    cell_count:        int   = 0     # uint16 — number of cells
    polygon_open_first:  int = 0     # uint16
    polygon_open_count:  int = 0     # uint16
    polygon_close_first: int = 0     # uint16
    polygon_close_count: int = 0     # uint16

    cell_indices: List[int] = field(default_factory=list)  # uint16 each

    @classmethod
    def _read(cls, r: BinaryReader) -> "WedDoor":
        name        = r.read_resref()
        open_       = r.read_uint16()
        cell_first  = r.read_uint16()
        cell_count  = r.read_uint16()
        poly_of     = r.read_uint16()
        poly_oc     = r.read_uint16()
        poly_cf     = r.read_uint16()
        poly_cc     = r.read_uint16()
        return cls(
            name=name, open_=open_,
            cell_index_first=cell_first, cell_count=cell_count,
            polygon_open_first=poly_of, polygon_open_count=poly_oc,
            polygon_close_first=poly_cf, polygon_close_count=poly_cc,
        )

    def _write(self, w: BinaryWriter, cell_index_first: int) -> None:
        w.write_resref(self.name)
        w.write_uint16(self.open_)
        w.write_uint16(cell_index_first)
        w.write_uint16(len(self.cell_indices))
        w.write_uint16(self.polygon_open_first)
        w.write_uint16(self.polygon_open_count)
        w.write_uint16(self.polygon_close_first)
        w.write_uint16(self.polygon_close_count)

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "open": self.open_,
                   "cell_indices": self.cell_indices}
        if self.polygon_open_count:
            d["polygon_open"]  = [self.polygon_open_first,  self.polygon_open_count]
        if self.polygon_close_count:
            d["polygon_close"] = [self.polygon_close_first, self.polygon_close_count]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "WedDoor":
        door = cls(name=d.get("name",""), open_=d.get("open",0))
        door.cell_indices = d.get("cell_indices",[])
        pol_o = d.get("polygon_open", [0,0])
        pol_c = d.get("polygon_close",[0,0])
        door.polygon_open_first  = pol_o[0]
        door.polygon_open_count  = pol_o[1]
        door.polygon_close_first = pol_c[0]
        door.polygon_close_count = pol_c[1]
        return door


# ---------------------------------------------------------------------------
# Polygon vertex  (4 bytes)
# ---------------------------------------------------------------------------

@dataclass
class PolygonVertex:
    x: int = 0   # int16
    y: int = 0   # int16

    @classmethod
    def _read(cls, r: BinaryReader) -> "PolygonVertex":
        return cls(x=r.read_int16(), y=r.read_int16())

    def _write(self, w: BinaryWriter) -> None:
        w.write_int16(self.x)
        w.write_int16(self.y)

    def to_json(self) -> list:
        return [self.x, self.y]

    @classmethod
    def from_json(cls, d) -> "PolygonVertex":
        if isinstance(d, (list, tuple)):
            return cls(x=d[0], y=d[1])
        return cls(x=d.get("x",0), y=d.get("y",0))


# ---------------------------------------------------------------------------
# Polygon  (18-byte header + N vertices)
# ---------------------------------------------------------------------------

@dataclass
class Polygon:
    """
    A convex wall / LOS polygon.

    ``vertices`` are stored globally in the WED; each polygon references a
    contiguous slice.  After parsing, vertices are resolved into the
    polygon's own list for convenience.
    """
    vertex_index: int  = 0    # uint32 — first vertex in global array
    vertex_count: int  = 0    # uint32
    flags:        int  = PolygonFlag.NONE  # uint8
    unknown:      int  = 0    # uint8
    bounding_box: List[int] = field(default_factory=lambda: [0,0,0,0])  # x1,y1,x2,y2  (int16 each)

    vertices: List[PolygonVertex] = field(default_factory=list)

    @classmethod
    def _read(cls, r: BinaryReader) -> "Polygon":
        vi    = r.read_uint32()
        vc    = r.read_uint32()
        flags = r.read_uint8()
        unk   = r.read_uint8()
        bbox  = [r.read_int16() for _ in range(4)]
        return cls(vertex_index=vi, vertex_count=vc, flags=flags,
                   unknown=unk, bounding_box=bbox)

    def _write(self, w: BinaryWriter, vertex_index: int) -> None:
        w.write_uint32(vertex_index)
        w.write_uint32(len(self.vertices))
        w.write_uint8(self.flags)
        w.write_uint8(self.unknown)
        for v in self.bounding_box[:4]:
            w.write_int16(v)

    def to_json(self) -> dict:
        return {
            "flags":        self.flags,
            "bounding_box": self.bounding_box,
            "vertices":     [v.to_json() for v in self.vertices],
        }

    @classmethod
    def from_json(cls, d: dict) -> "Polygon":
        p = cls(flags=d.get("flags",0),
                bounding_box=d.get("bounding_box",[0,0,0,0]))
        p.vertices = [PolygonVertex.from_json(v) for v in d.get("vertices",[])]
        return p


# ---------------------------------------------------------------------------
# WED header  (32 bytes)
# ---------------------------------------------------------------------------

@dataclass
class WedHeader:
    overlay_count:       int = 0   # uint32
    door_count:          int = 0   # uint32
    overlay_offset:      int = 0   # uint32
    secondary_offset:    int = 0   # uint32 — second group of overlays (unused in most areas)
    door_offset:         int = 0   # uint32
    door_tile_cell_offset: int = 0 # uint32 — door cell index table

    @classmethod
    def _read(cls, r: BinaryReader) -> "WedHeader":
        ov_cnt  = r.read_uint32()
        d_cnt   = r.read_uint32()
        ov_off  = r.read_uint32()
        sec_off = r.read_uint32()
        d_off   = r.read_uint32()
        dtc_off = r.read_uint32()
        return cls(overlay_count=ov_cnt, door_count=d_cnt,
                   overlay_offset=ov_off, secondary_offset=sec_off,
                   door_offset=d_off, door_tile_cell_offset=dtc_off)

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint32(self.overlay_count)
        w.write_uint32(self.door_count)
        w.write_uint32(self.overlay_offset)
        w.write_uint32(self.secondary_offset)
        w.write_uint32(self.door_offset)
        w.write_uint32(self.door_tile_cell_offset)


# ---------------------------------------------------------------------------
# WedFile — top-level container
# ---------------------------------------------------------------------------

class WedFile:
    """
    A complete WED resource.

    Attributes::

        header     — :class:`WedHeader`
        overlays   — List[:class:`Overlay`]   (overlays[0] is the base layer)
        doors      — List[:class:`WedDoor`]
        polygons   — List[:class:`Polygon`]   (wall / LOS polygons)
        poly_index — List[int]               (per-tile-cell polygon index, uint16)

    Usage::

        wed = WedFile.from_file("AR0602.wed")
        base = wed.overlays[0]
        print(f"{base.width}×{base.height} tiles, TIS: {base.tis_resref}")

        # Get the polygon flags for cell (3, 5)
        cell_flat = 5 * base.width + 3
        poly_idx  = wed.poly_index[cell_flat]
        if poly_idx != 0xFFFF:
            print(wed.polygons[poly_idx].flags)
    """

    def __init__(
        self,
        header:     WedHeader,
        overlays:   List[Overlay],
        doors:      List[WedDoor],
        polygons:   List[Polygon],
        poly_index: List[int],
        source_path: Optional[Path] = None,
    ) -> None:
        self.header     = header
        self.overlays   = overlays
        self.doors      = doors
        self.polygons   = polygons
        self.poly_index = poly_index
        self.source_path = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "WedFile":
        r = BinaryReader(data)
        try:
            r.expect_signature(SIGNATURE)
            r.expect_signature(VERSION)
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        header = WedHeader._read(r)

        # -- Overlay headers --
        r.seek(header.overlay_offset)
        overlays: List[Overlay] = []
        for _ in range(header.overlay_count):
            overlays.append(Overlay._read_header(r))

        # -- Overlay data (tilemap + lookup) --
        for ov in overlays:
            ov._read_data(r)

        # -- Wall polygons --
        # The polygon array and vertex array offsets are embedded in the
        # overlay 0 tilemap; we discover them by scanning for the polygon
        # count at a known offset relative to the second overlay block start.
        # Standard layout: polygon headers follow the last overlay's lookup,
        # then the vertex array, then the polygon index table.
        # We use overlay[0]'s cell count to find the poly index table offset.
        polygons: List[Polygon] = []
        poly_index: List[int]   = []

        if overlays:
            base = overlays[0]
            cell_count = base.width * base.height

            # Polygon index table sits immediately after the tilemap.
            # Its offset = tilemap_offset + cell_count * TILEMAP_ENTRY_SIZE
            poly_idx_off = base.tilemap_offset + cell_count * TILEMAP_ENTRY_SIZE
            r.seek(poly_idx_off)
            poly_index = [r.read_uint16() for _ in range(cell_count)]

            # Polygon count is stored as a uint32 right after the overlay
            # header block + tilemap data.  Derive via known geometry:
            # polygon headers follow the door cell index table.
            # We read the polygon count from the WED polygon header section.
            # Convention: polygon header offset = door_tile_cell_offset + cell table size.
            # We calculate the door cell table size from the door records.

            # Read doors first so we know the cell table size
            r.seek(header.door_offset)
            raw_doors: List[WedDoor] = []
            for _ in range(header.door_count):
                raw_doors.append(WedDoor._read(r))

            # Read door cell index table
            r.seek(header.door_tile_cell_offset)
            for door in raw_doors:
                door.cell_indices = [r.read_uint16()
                                     for _ in range(door.cell_count)]

            # Polygon section starts after door cell table
            total_door_cells = sum(d.cell_count for d in raw_doors)
            poly_hdr_off = header.door_tile_cell_offset + total_door_cells * 2

            # Read polygon count (uint32 at poly_hdr_off - 4, written by WED tools)
            # More reliable: read it from the header field if present.
            # WED V1.3 stores polygon count implicitly; we read until we can't.
            # We use the polygon index table max value as an upper bound.
            if poly_index:
                valid_indices = [i for i in poly_index if i != 0xFFFF]
                max_poly = max(valid_indices) + 1 if valid_indices else 0
            else:
                max_poly = 0

            if max_poly > 0:
                r.seek(poly_hdr_off)
                # WED stores: uint32 polygon_count, then N polygon headers,
                # then uint32 vertex_count, then vertices.
                poly_count_stored = r.read_uint32()
                poly_count = max(max_poly, poly_count_stored)

                for _ in range(poly_count):
                    polygons.append(Polygon._read(r))

                # Read global vertex array
                vert_count_stored = r.read_uint32()
                all_verts = [PolygonVertex._read(r) for _ in range(vert_count_stored)]

                # Resolve vertices into each polygon
                for poly in polygons:
                    poly.vertices = all_verts[
                        poly.vertex_index : poly.vertex_index + poly.vertex_count
                    ]

            return cls(header, overlays, raw_doors, polygons, poly_index)

        return cls(header, overlays, [], polygons, poly_index)

    @classmethod
    def from_file(cls, path: str | Path) -> "WedFile":
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        # Layout order:
        #   Header (32)
        #   Overlay headers (N × 24)
        #   Overlay 0 tilemap + other overlay tilemaps
        #   Overlay lookup tables
        #   Poly index table (cell_count × uint16)
        #   Door headers (M × 16)
        #   Door cell index table
        #   uint32 polygon_count
        #   Polygon headers (P × 18)
        #   uint32 vertex_count
        #   Vertices (V × 4)

        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(VERSION)

        if not self.overlays:
            self.header._write(w)
            return w.to_bytes()

        base = self.overlays[0]
        cell_count = base.width * base.height

        # We'll write sections into sub-writers then assemble
        w_ov_hdrs = BinaryWriter()  # overlay headers placeholder
        w_tilemaps = BinaryWriter()
        w_lookups  = BinaryWriter()
        w_poly_idx = BinaryWriter()
        w_door_hdrs = BinaryWriter()
        w_door_cells = BinaryWriter()
        w_polys = BinaryWriter()
        w_verts = BinaryWriter()

        # Tilemaps and lookups per overlay
        tilemap_offsets = []
        lookup_offsets  = []
        ov_hdr_base = HEADER_SIZE  # overlays start right after header

        # We'll compute absolute offsets after sizing all sections
        # First pass: measure sizes
        total_tilemap = sum(ov.width * ov.height * TILEMAP_ENTRY_SIZE
                            for ov in self.overlays)
        total_lookup  = sum(len(ov.tile_lookup) * 2 for ov in self.overlays)

        ov_hdrs_size    = len(self.overlays) * OVERLAY_HDR_SIZE
        tilemaps_start  = ov_hdr_base + ov_hdrs_size
        lookups_start   = tilemaps_start + total_tilemap
        poly_idx_start  = lookups_start  + total_lookup

        door_hdrs_start = poly_idx_start + cell_count * 2
        total_door_cells = sum(len(d.cell_indices) for d in self.doors)
        door_cells_start = door_hdrs_start + len(self.doors) * DOOR_SIZE
        poly_section_start = door_cells_start + total_door_cells * 2

        # Assign overlay offsets
        tm_cursor = tilemaps_start
        lk_cursor = lookups_start
        for ov in self.overlays:
            tilemap_offsets.append(tm_cursor)
            tm_cursor += ov.width * ov.height * TILEMAP_ENTRY_SIZE
            lookup_offsets.append(lk_cursor)
            lk_cursor += len(ov.tile_lookup) * 2

        # Write overlay headers
        for i, ov in enumerate(self.overlays):
            ov._write_header(w_ov_hdrs, tilemap_offsets[i], lookup_offsets[i])

        # Write tilemaps + lookups
        for ov in self.overlays:
            for te in ov.tilemap:
                te._write(w_tilemaps)
        for ov in self.overlays:
            for ti in ov.tile_lookup:
                w_lookups.write_uint16(ti)

        # Poly index table
        for pi in self.poly_index:
            w_poly_idx.write_uint16(pi)

        # Door headers + cell tables
        cell_cursor = door_cells_start
        cell_offsets = []
        for door in self.doors:
            cell_offsets.append(cell_cursor)
            cell_cursor += len(door.cell_indices) * 2

        for i, door in enumerate(self.doors):
            # cell_index_first is a relative index into the door cell table
            rel = (cell_offsets[i] - door_cells_start) // 2
            door._write(w_door_hdrs, rel)
        for door in self.doors:
            for ci in door.cell_indices:
                w_door_cells.write_uint16(ci)

        # Polygon section: count + headers + vert_count + vertices
        all_poly_verts: List[PolygonVertex] = []
        poly_vi_map: List[int] = []
        for poly in self.polygons:
            poly_vi_map.append(len(all_poly_verts))
            all_poly_verts.extend(poly.vertices)

        w_polys.write_uint32(len(self.polygons))
        for i, poly in enumerate(self.polygons):
            poly._write(w_polys, poly_vi_map[i])
        w_polys.write_uint32(len(all_poly_verts))
        for pv in all_poly_verts:
            pv._write(w_polys)

        # Patch header
        self.header.overlay_count          = len(self.overlays)
        self.header.door_count             = len(self.doors)
        self.header.overlay_offset         = ov_hdr_base
        self.header.secondary_offset       = tilemaps_start  # convention
        self.header.door_offset            = door_hdrs_start
        self.header.door_tile_cell_offset  = door_cells_start

        w.write_bytes(b"\x00" * HEADER_SIZE)  # placeholder; rewrite below
        body = (w_ov_hdrs.to_bytes() + w_tilemaps.to_bytes() + w_lookups.to_bytes()
                + w_poly_idx.to_bytes() + w_door_hdrs.to_bytes()
                + w_door_cells.to_bytes() + w_polys.to_bytes())

        # Rebuild with correct header
        w2 = BinaryWriter()
        w2.write_bytes(SIGNATURE)
        w2.write_bytes(VERSION)
        self.header._write(w2)
        w2.write_bytes(body)
        return w2.to_bytes()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "format":     "wed",
            "version":    "V1.3",
            "overlays":   [ov.to_json() for ov in self.overlays],
            "doors":      [d.to_json()  for d  in self.doors],
            "polygons":   [p.to_json()  for p  in self.polygons],
            "poly_index": self.poly_index,
        }

    @classmethod
    def from_json(cls, d: dict) -> "WedFile":
        overlays   = [Overlay.from_json(o)   for o in d.get("overlays",[])]
        doors      = [WedDoor.from_json(x)   for x in d.get("doors",[])]
        polygons   = [Polygon.from_json(p)   for p in d.get("polygons",[])]
        poly_index = d.get("poly_index", [])
        return cls(WedHeader(), overlays, doors, polygons, poly_index)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "WedFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        base = self.overlays[0] if self.overlays else None
        dims = f"{base.width}×{base.height}" if base else "?"
        return (
            f"<WedFile {src!r} {dims} tiles "
            f"overlays={len(self.overlays)} "
            f"polygons={len(self.polygons)}>"
        )
