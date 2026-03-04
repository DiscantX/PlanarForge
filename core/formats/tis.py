"""
core/formats/tis.py

Parser and writer for the Infinity Engine TIS (Tileset) format.

A TIS file stores the tile graphics for one area overlay.  Each tile is a
fixed 64×64 pixel block stored as a palette + raw pixel data.  The companion
WED file's tilemap selects which TIS tiles to draw in which cells.

Two storage formats exist:
    Palette-based  — the original format; each tile has a 256-colour palette
                     (256 × 4 bytes BGRA) followed by 64×64 = 4096 raw
                     palette-index bytes.  Total: 1024 + 4096 = 5120 bytes/tile.
    PVRZ-based     — Enhanced Edition format; tiles reference PVRZ compressed
                     texture pages.  Each tile record is 12 bytes
                     (page, x, y offsets).  Pixel data lives in external PVRZ
                     files and is not decoded here.

Pixel decoding:
    Optional.  If Pillow is installed, ``TisFile.decode_tile(index)`` returns
    a ``PIL.Image`` in RGBA mode.  Without Pillow the raw palette + pixel
    bytes are still accessible via ``TisFile.tile_data(index)``.

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/tis_v1.htm

Usage::

    from core.formats.tis import TisFile

    tis = TisFile.from_file("AR0602.tis")
    print(tis.tile_count, tis.tile_size)  # e.g. 9344, 5120

    raw = tis.tile_data(0)                # 5120 bytes for palette tile
    # optional decode:
    img = tis.decode_tile(0)              # PIL.Image or None if no Pillow
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE = b"TIS "
VERSION   = b"V1  "

PALETTE_TILE_SIZE = 5120    # 1024 palette + 4096 pixel indices
PVRZ_TILE_SIZE    = 12      # page(4) + x(4) + y(4)
TILE_WIDTH        = 64
TILE_HEIGHT       = 64

HEADER_SIZE = 24


# ---------------------------------------------------------------------------
# Tile data structures
# ---------------------------------------------------------------------------

@dataclass
class PaletteTile:
    """
    A palette-based tile (original IE format).

    ``palette``     — 256 × 4 bytes in BGRA order (1024 bytes total)
    ``pixel_data``  — 64×64 palette-index bytes (4096 bytes, row-major)
    """
    palette:    bytes = b"\x00" * 1024
    pixel_data: bytes = b"\x00" * 4096

    def to_rgba(self) -> bytes:
        """
        Convert to a flat 64×64 RGBA byte array.

        Requires no external libraries.  Returns bytes of length 4096×4.
        Colour index 0 is treated as fully transparent (alpha=0) when the
        palette entry has alpha=0; otherwise the palette alpha is used.
        """
        pal = self.palette
        out = bytearray(TILE_WIDTH * TILE_HEIGHT * 4)
        for i, idx in enumerate(self.pixel_data):
            b = pal[idx * 4]
            g = pal[idx * 4 + 1]
            r = pal[idx * 4 + 2]
            a = pal[idx * 4 + 3]
            out[i*4]   = r
            out[i*4+1] = g
            out[i*4+2] = b
            out[i*4+3] = a
        return bytes(out)


@dataclass
class PvrzTile:
    """
    A PVRZ-based tile (Enhanced Edition format).

    References a compressed texture page; pixel data is not stored inline.
    ``page``  — PVRZ file index (MOS0000.pvrz, MOS0001.pvrz, …)
    ``x``, ``y`` — top-left pixel offset within the PVRZ page
    """
    page: int = 0
    x:    int = 0
    y:    int = 0


# ---------------------------------------------------------------------------
# TisFile
# ---------------------------------------------------------------------------

class TisFile:
    """
    A complete TIS tileset resource.

    Palette tiles are exposed as :class:`PaletteTile` objects; PVRZ tiles
    as :class:`PvrzTile` objects.  Use :attr:`is_pvrz` to distinguish.

    Raw tile bytes are always accessible via :meth:`tile_data`.  Optional
    RGBA decoding is available via :meth:`decode_tile` (palette tiles only;
    requires Pillow for image conversion, but ``to_rgba()`` works without it).

    Usage::

        tis = TisFile.from_file("AR0602.tis")
        if not tis.is_pvrz:
            rgba = tis.tiles[0].to_rgba()   # 16384 bytes, RGBA row-major
    """

    def __init__(
        self,
        tiles:       List,          # List[PaletteTile] or List[PvrzTile]
        source_path: Optional[Path] = None,
    ) -> None:
        self.tiles       = tiles
        self.source_path = source_path

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tile_count(self) -> int:
        return len(self.tiles)

    @property
    def is_pvrz(self) -> bool:
        return bool(self.tiles) and isinstance(self.tiles[0], PvrzTile)

    @property
    def tile_size(self) -> int:
        return PVRZ_TILE_SIZE if self.is_pvrz else PALETTE_TILE_SIZE

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "TisFile":
        r = BinaryReader(data)
        try:
            r.expect_signature(SIGNATURE)
            r.expect_signature(VERSION)
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        tile_count = r.read_uint32()
        tile_size  = r.read_uint32()
        header_size = r.read_uint32()  # should be 24
        tile_dim    = r.read_uint32()  # should be 64

        is_pvrz = (tile_size == PVRZ_TILE_SIZE)

        r.seek(header_size)
        tiles = []
        if is_pvrz:
            for _ in range(tile_count):
                page = r.read_uint32()
                x    = r.read_uint32()
                y    = r.read_uint32()
                tiles.append(PvrzTile(page=page, x=x, y=y))
        else:
            for _ in range(tile_count):
                palette    = r.read_bytes(1024)
                pixel_data = r.read_bytes(4096)
                tiles.append(PaletteTile(palette=palette, pixel_data=pixel_data))

        return cls(tiles)

    @classmethod
    def from_file(cls, path: str | Path) -> "TisFile":
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Tile access
    # ------------------------------------------------------------------

    def tile_data(self, index: int) -> bytes:
        """
        Return the raw bytes for tile *index*.

        For palette tiles: 5120 bytes (1024 palette + 4096 pixels).
        For PVRZ tiles:    12 bytes   (page + x + y as uint32s).
        """
        tile = self.tiles[index]
        if isinstance(tile, PaletteTile):
            return tile.palette + tile.pixel_data
        # PVRZ
        import struct
        return struct.pack("<III", tile.page, tile.x, tile.y)

    def decode_tile(self, index: int):
        """
        Decode tile *index* to a ``PIL.Image`` (RGBA, 64×64).

        Returns ``None`` if:
        - Pillow is not installed
        - The file uses PVRZ format (pixel data is in external files)

        For palette tiles this works without Pillow via :meth:`PaletteTile.to_rgba`.
        """
        tile = self.tiles[index]
        if not isinstance(tile, PaletteTile):
            return None
        rgba = tile.to_rgba()
        try:
            from PIL import Image
            return Image.frombytes("RGBA", (TILE_WIDTH, TILE_HEIGHT), rgba)
        except ImportError:
            return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(VERSION)
        w.write_uint32(len(self.tiles))
        w.write_uint32(self.tile_size)
        w.write_uint32(HEADER_SIZE)
        w.write_uint32(TILE_WIDTH)

        for tile in self.tiles:
            if isinstance(tile, PaletteTile):
                w.write_bytes(tile.palette[:1024].ljust(1024, b"\x00"))
                w.write_bytes(tile.pixel_data[:4096].ljust(4096, b"\x00"))
            else:
                import struct
                w.write_bytes(struct.pack("<III", tile.page, tile.x, tile.y))

        return w.to_bytes()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON  (metadata only — pixel data excluded for size)
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """
        Serialise metadata to JSON.

        Pixel data is not included; use :meth:`to_file` to persist tiles.
        PVRZ tile page/offset references are included.
        """
        d: dict = {
            "format":     "tis",
            "tile_count": self.tile_count,
            "is_pvrz":    self.is_pvrz,
        }
        if self.is_pvrz:
            d["tiles"] = [{"page": t.page, "x": t.x, "y": t.y}
                          for t in self.tiles]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "TisFile":
        """Restore PVRZ metadata; palette tiles cannot be round-tripped via JSON."""
        tiles = []
        if d.get("is_pvrz"):
            for t in d.get("tiles", []):
                tiles.append(PvrzTile(page=t["page"], x=t["x"], y=t["y"]))
        return cls(tiles)

    # ------------------------------------------------------------------
    # Convenience: create a new blank palette-based TIS
    # ------------------------------------------------------------------

    @classmethod
    def blank(cls, tile_count: int, fill_color: Tuple[int,int,int] = (0, 0, 0)) -> "TisFile":
        """
        Create a new TIS file with *tile_count* solid-colour tiles.

        Useful as a starting point when building a new area from scratch.
        ``fill_color`` is an (R, G, B) tuple.
        """
        r, g, b = fill_color
        # Palette: colour 0 = fill colour, rest = black, all opaque
        palette = bytearray(1024)
        palette[0] = b
        palette[1] = g
        palette[2] = r
        palette[3] = 255
        for i in range(1, 256):
            palette[i*4+3] = 255
        palette = bytes(palette)
        pixel_data = b"\x00" * 4096  # all pixels use colour 0
        tiles = [PaletteTile(palette=palette, pixel_data=pixel_data)
                 for _ in range(tile_count)]
        return cls(tiles)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        fmt = "PVRZ" if self.is_pvrz else "palette"
        return f"<TisFile {src!r} {self.tile_count} tiles ({fmt})>"
