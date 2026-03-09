"""
core/formats/mos.py

Parser and writer for the Infinity Engine MOS (Map Overview / Minimap) format.

MOS files store the pre-rendered minimap image shown in the area map screen.
Like TIS, two variants exist:
    MOS V1   — original palette-based format.  The image is divided into
               64×64 pixel blocks, each with its own 256-colour palette.
               Unlike TIS, MOS stores the block grid inline (no companion
               WED/TIS pairing).
    MOSC     — zlib-compressed V1 data (common in BG2; same structure after
               decompression).
    MOS V2   — Enhanced Edition PVRZ-based format.  Blocks reference external
               PVRZ texture pages (same as TIS V2).

Pixel decoding (optional):
    ``MosFile.to_rgba()`` converts palette-based MOS to a flat RGBA byte
    array without any external dependencies.
    ``MosFile.to_image()`` returns a ``PIL.Image`` if Pillow is installed.

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/mos_v1.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/mos_v2.htm

Usage::

    from core.formats.mos import MosFile

    mos = MosFile.from_file("AR0602.mos")
    print(mos.width, mos.height)     # pixel dimensions
    print(mos.cols, mos.rows)        # block grid size
    img = mos.to_image()             # PIL.Image or None
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.formats.pvrz import PvrzFile


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE_MOS  = b"MOS "
SIGNATURE_MOSC = b"MOSC"
VERSION_V1     = b"V1  "
VERSION_V2     = b"V2  "

BLOCK_SIZE     = 64          # pixels per block side
PALETTE_SIZE   = 1024        # 256 × 4 bytes BGRA
BLOCK_PIXELS   = BLOCK_SIZE * BLOCK_SIZE  # 4096

HEADER_SIZE_V1 = 24
HEADER_SIZE_V2 = 16


# ---------------------------------------------------------------------------
# Block types
# ---------------------------------------------------------------------------

@dataclass
class PaletteBlock:
    """One 64×64 palette-based block."""
    palette:    bytes = b"\x00" * 1024
    pixel_data: bytes = b"\x00" * 4096


@dataclass
class PvrzBlock:
    """One PVRZ-reference block (EE MOS V2).

    Actual EE on-disk format is 28 bytes per block:
      page(4)  src_x(4)  src_y(4)  width(4)  height(4)  dst_x(4)  dst_y(4)

    src_x/src_y are the source offset within the PVRZ page texture.
    dst_x/dst_y are the explicit pixel destination in the output image.
    """
    page:   int = 0
    x:      int = 0    # src_x — offset within PVRZ page
    y:      int = 0    # src_y — offset within PVRZ page
    width:  int = BLOCK_SIZE
    height: int = BLOCK_SIZE
    dst_x:  int = 0    # destination x in output image
    dst_y:  int = 0    # destination y in output image


# ---------------------------------------------------------------------------
# MosFile
# ---------------------------------------------------------------------------

class MosFile:
    """
    A complete MOS minimap image.

    For palette-based MOS (V1 / MOSC):
        ``blocks``  — List[:class:`PaletteBlock`] in row-major order
        ``is_pvrz`` — False

    For PVRZ-based MOS (V2):
        ``blocks``  — List[:class:`PvrzBlock`]
        ``is_pvrz`` — True

    Usage::

        mos = MosFile.from_file("AR0602.mos")
        print(f"{mos.width}×{mos.height}  {mos.cols}×{mos.rows} blocks")

        # Convert to RGBA bytes (palette MOS only, no Pillow needed)
        rgba = mos.to_rgba()

        # Or get a PIL Image
        img = mos.to_image()
        if img:
            img.save("AR0602_minimap.png")
    """

    def __init__(
        self,
        width:   int,
        height:  int,
        blocks:  List,          # List[PaletteBlock] or List[PvrzBlock]
        version: bytes = VERSION_V1,
        compressed: bool = False,
        source_path: Optional[Path] = None,
    ) -> None:
        self.width       = width
        self.height      = height
        self.blocks      = blocks
        self.version     = version
        self.compressed  = compressed
        self.source_path = source_path

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cols(self) -> int:
        """Number of block columns."""
        return (self.width + BLOCK_SIZE - 1) // BLOCK_SIZE

    @property
    def rows(self) -> int:
        """Number of block rows."""
        return (self.height + BLOCK_SIZE - 1) // BLOCK_SIZE

    @property
    def is_pvrz(self) -> bool:
        return self.version == VERSION_V2

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "MosFile":
        sig = data[:4]

        if sig == SIGNATURE_MOSC:
            # Decompress: MOSC header = sig(4) + ver(4) + decompressed_len(4)
            decomp_len = int.from_bytes(data[8:12], "little")
            data = zlib.decompress(data[12:])
            return cls._parse_v1(BinaryReader(data), compressed=True)

        r = BinaryReader(data)
        try:
            r.expect_signature(SIGNATURE_MOS)
            version = r.read_bytes(4)
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        if version == VERSION_V2:
            return cls._parse_v2(r)
        if version == VERSION_V1:
            return cls._parse_v1(r)
        raise ValueError(f"Unsupported MOS version {version!r}.")

    @classmethod
    def _parse_v1(cls, r: BinaryReader, compressed: bool = False) -> "MosFile":
        width       = r.read_uint16()
        height      = r.read_uint16()
        cols        = r.read_uint16()
        rows        = r.read_uint16()
        block_size  = r.read_uint32()  # always 5120
        data_offset = r.read_uint32()  # always 24

        block_count = cols * rows
        # Palette table: block_count × 1024 bytes, at data_offset
        # Pixel data:    block_count × 4096 bytes, after palettes
        palette_base = data_offset
        pixel_base   = palette_base + block_count * PALETTE_SIZE

        blocks: List[PaletteBlock] = []
        for i in range(block_count):
            pal_off = palette_base + i * PALETTE_SIZE
            pix_off = pixel_base   + i * BLOCK_PIXELS
            palette    = r.read_bytes_at(pal_off, PALETTE_SIZE)
            pixel_data = r.read_bytes_at(pix_off, BLOCK_PIXELS)
            blocks.append(PaletteBlock(palette=palette, pixel_data=pixel_data))

        return cls(width=width, height=height, blocks=blocks,
                   version=VERSION_V1, compressed=compressed)

    @classmethod
    def _parse_v2(cls, r: BinaryReader) -> "MosFile":
        width         = r.read_uint32()
        height        = r.read_uint32()
        block_count   = r.read_uint32()
        blocks_offset = r.read_uint32()

        r.seek(blocks_offset)
        blocks: List[PvrzBlock] = []
        for _ in range(block_count):
            # 28 bytes per block: page src_x src_y width height dst_x dst_y
            page  = r.read_uint32()
            src_x = r.read_uint32()
            src_y = r.read_uint32()
            w     = r.read_uint32()
            h     = r.read_uint32()
            dst_x = r.read_uint32()
            dst_y = r.read_uint32()
            blocks.append(PvrzBlock(
                page=page, x=src_x, y=src_y,
                width=w, height=h,
                dst_x=dst_x, dst_y=dst_y,
            ))

        return cls(width=width, height=height, blocks=blocks, version=VERSION_V2)

    @classmethod
    def from_file(cls, path: str | Path) -> "MosFile":
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Pixel decoding
    # ------------------------------------------------------------------

    def to_rgba(self, pvrz_loader: Optional[Callable[[int], object]] = None) -> Optional[bytes]:
        """
        Convert to a flat RGBA byte array (width×height×4 bytes).

        Works for palette MOS (V1/MOSC) without any external libraries.
        For PVRZ-based MOS (V2), requires a pvrz_loader callable that returns
        PvrzFile objects given a page number.

        Args:
            pvrz_loader: Optional callable(page_number) -> PvrzFile | None
                         Loader that returns a PvrzFile object for a given page number.
                         If None and MOS is PVRZ-based, returns None.

        Returns:
            RGBA byte array or None if decoding is not possible.
        """
        if self.is_pvrz:
            if pvrz_loader is None:
                return None
            return self._to_rgba_pvrz(pvrz_loader)
        else:
            return self._to_rgba_palette()

    def _to_rgba_palette(self) -> Optional[bytes]:
        """Convert palette-based MOS to RGBA."""
        out = bytearray(self.width * self.height * 4)

        for block_row in range(self.rows):
            for block_col in range(self.cols):
                block = self.blocks[block_row * self.cols + block_col]
                pal   = block.palette

                # Pixel dimensions of this block (last row/col may be partial)
                bw = min(BLOCK_SIZE, self.width  - block_col * BLOCK_SIZE)
                bh = min(BLOCK_SIZE, self.height - block_row * BLOCK_SIZE)

                origin_x = block_col * BLOCK_SIZE
                origin_y = block_row * BLOCK_SIZE

                for local_y in range(bh):
                    for local_x in range(bw):
                        idx = block.pixel_data[local_y * BLOCK_SIZE + local_x]
                        b = pal[idx * 4]
                        g = pal[idx * 4 + 1]
                        r = pal[idx * 4 + 2]
                        a = pal[idx * 4 + 3]
                        dst = ((origin_y + local_y) * self.width + (origin_x + local_x)) * 4
                        out[dst]   = r
                        out[dst+1] = g
                        out[dst+2] = b
                        out[dst+3] = a

        return bytes(out)

    def _to_rgba_pvrz(self, pvrz_loader: Callable[[int], object]) -> Optional[bytes]:
        """
        Convert PVRZ-based MOS to RGBA using external PVRZ texture pages.

        Each block record (28 bytes) contains:
          page, src_x, src_y, width, height, dst_x, dst_y

        src_x/src_y  — source offset within the PVRZ page texture
        dst_x/dst_y  — explicit pixel destination in the output image
        
        The pvrz_loader callable should return PvrzFile objects and handle caching.
        """
        try:
            out = bytearray(self.width * self.height * 4)
            blocks_decoded = 0

            for block in self.blocks:
                # Load PVRZ page via loader (which caches internally at CharacterService level)
                page_num = block.page
                try:
                    pvrz = pvrz_loader(page_num)
                except Exception as e:
                    print(f"[MOS PVRZ] Failed to load PVRZ page {page_num}: {e}")
                    pvrz = None

                if pvrz is None:
                    continue

                # Extract source rectangle from PVRZ page
                try:
                    region_rgba = pvrz.get_region_rgba(
                        block.x, block.y, block.width, block.height
                    )
                except Exception as e:
                    print(f"[MOS PVRZ] Failed to extract region from PVRZ page {page_num}: {e}")
                    region_rgba = None

                if region_rgba is None:
                    continue

                blocks_decoded += 1

                # Copy into output using the explicit destination coordinates
                dst_x = block.dst_x
                dst_y = block.dst_y
                for local_y in range(block.height):
                    oy = dst_y + local_y
                    if oy >= self.height:
                        break
                    row_w = min(block.width, self.width - dst_x)
                    if row_w <= 0:
                        continue
                    src_off = local_y * block.width * 4
                    dst_off = (oy * self.width + dst_x) * 4
                    out[dst_off: dst_off + row_w * 4] = region_rgba[src_off: src_off + row_w * 4]

            if blocks_decoded == 0:
                return None

            return bytes(out)

        except Exception:
            return None

    def to_image(self):
        """
        Return a ``PIL.Image`` (RGBA) of the full minimap.

        Returns ``None`` if Pillow is not installed or the format is PVRZ.
        """
        rgba = self.to_rgba()
        if rgba is None:
            return None
        try:
            from PIL import Image
            return Image.frombytes("RGBA", (self.width, self.height), rgba)
        except ImportError:
            return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self, compress: bool = False) -> bytes:
        """
        Serialise to binary.

        ``compress=True`` produces MOSC (zlib-compressed V1).  Has no effect
        for PVRZ (V2) MOS files.
        """
        if self.is_pvrz:
            return self._to_bytes_v2()
        raw = self._to_bytes_v1()
        if compress or self.compressed:
            compressed = zlib.compress(raw, level=6)
            header = SIGNATURE_MOSC + VERSION_V1
            header += len(raw).to_bytes(4, "little")
            return header + compressed
        return raw

    def _to_bytes_v1(self) -> bytes:
        cols = self.cols
        rows = self.rows
        w = BinaryWriter()
        w.write_bytes(SIGNATURE_MOS)
        w.write_bytes(VERSION_V1)
        w.write_uint16(self.width)
        w.write_uint16(self.height)
        w.write_uint16(cols)
        w.write_uint16(rows)
        w.write_uint32(PALETTE_SIZE + BLOCK_PIXELS)  # block_size = 5120
        w.write_uint32(HEADER_SIZE_V1)

        for block in self.blocks:
            if isinstance(block, PaletteBlock):
                w.write_bytes(block.palette[:PALETTE_SIZE].ljust(PALETTE_SIZE, b"\x00"))
            else:
                w.write_bytes(b"\x00" * PALETTE_SIZE)
        for block in self.blocks:
            if isinstance(block, PaletteBlock):
                w.write_bytes(block.pixel_data[:BLOCK_PIXELS].ljust(BLOCK_PIXELS, b"\x00"))
            else:
                w.write_bytes(b"\x00" * BLOCK_PIXELS)

        return w.to_bytes()

    def _to_bytes_v2(self) -> bytes:
        blocks_offset = HEADER_SIZE_V2
        w = BinaryWriter()
        w.write_bytes(SIGNATURE_MOS)
        w.write_bytes(VERSION_V2)
        w.write_uint32(self.width)
        w.write_uint32(self.height)
        w.write_uint32(len(self.blocks))
        w.write_uint32(blocks_offset)
        for block in self.blocks:
            if isinstance(block, PvrzBlock):
                w.write_uint32(block.page)
                w.write_uint32(block.x)
                w.write_uint32(block.y)
                w.write_uint32(block.width)
                w.write_uint32(block.height)
            else:
                w.write_bytes(b"\x00" * 20)
        return w.to_bytes()

    def to_file(self, path: str | Path, compress: bool = False) -> None:
        Path(path).write_bytes(self.to_bytes(compress=compress))

    # ------------------------------------------------------------------
    # JSON (metadata only; pixel data excluded)
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        d: dict = {
            "format":     "mos",
            "version":    self.version.rstrip(b" ").decode("latin-1"),
            "width":      self.width,
            "height":     self.height,
            "compressed": self.compressed,
            "is_pvrz":    self.is_pvrz,
        }
        if self.is_pvrz:
            d["blocks"] = [
                {"page": b.page, "x": b.x, "y": b.y,
                 "width": b.width, "height": b.height}
                for b in self.blocks
            ]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "MosFile":
        ver_str = d.get("version", "V1")
        version = VERSION_V2 if ver_str == "V2" else VERSION_V1
        width   = d.get("width", 0)
        height  = d.get("height", 0)
        blocks  = []
        if d.get("is_pvrz"):
            for b in d.get("blocks", []):
                blocks.append(PvrzBlock(page=b["page"], x=b["x"], y=b["y"],
                                        width=b.get("width", BLOCK_SIZE),
                                        height=b.get("height", BLOCK_SIZE)))
        return cls(width=width, height=height, blocks=blocks, version=version,
                   compressed=d.get("compressed", False))

    # ------------------------------------------------------------------
    # Convenience: blank MOS
    # ------------------------------------------------------------------

    @classmethod
    def blank(cls, width: int, height: int,
              color: Tuple[int,int,int] = (0,0,0)) -> "MosFile":
        """Create a new solid-colour palette MOS (V1) of the given pixel size."""
        r, g, b = color
        palette = bytearray(PALETTE_SIZE)
        palette[0] = b; palette[1] = g; palette[2] = r; palette[3] = 255
        for i in range(1, 256):
            palette[i*4+3] = 255
        palette = bytes(palette)
        pixels  = b"\x00" * BLOCK_PIXELS

        cols = (width  + BLOCK_SIZE - 1) // BLOCK_SIZE
        rows = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
        blocks = [PaletteBlock(palette=palette, pixel_data=pixels)
                  for _ in range(cols * rows)]
        return cls(width=width, height=height, blocks=blocks, version=VERSION_V1)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src  = self.source_path.name if self.source_path else "?"
        fmt  = "V2/PVRZ" if self.is_pvrz else ("MOSC" if self.compressed else "V1")
        return f"<MosFile {src!r} {self.width}×{self.height} px [{fmt}]>"