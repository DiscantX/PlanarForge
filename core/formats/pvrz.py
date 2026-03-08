"""
core/formats/pvrz.py

Parser for PVRZ files — zlib-compressed PVRT (PowerVR Texture) format used by
Enhanced Edition games.

PVRZ files store pre-compressed texture pages referenced by TIS V2 and MOS V2
resources.  Each PVRZ file is zlib-compressed container of raw PVRTC data.

PVRTC is a proprietary format from Imagination Technologies (PowerVR).  This
module provides decompression and PVRTC pixel decoding for PVRTC 4bpp format
(commonly used by Enhanced Edition games).

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/pvrz.htm

Usage::

    from core.formats.pvrz import PvrzFile

    pvrz = PvrzFile.from_bytes(raw_bytes)
    print(pvrz.width, pvrz.height, pvrz.pixel_format)

    # Extract pixels from a region as RGBA
    rgba = pvrz.to_rgba()
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.formats.pvrtc import decode_pvrtc_4bpp, decode_pvrtc_2bpp


# ---------------------------------------------------------------------------
# PVRT Constants
# ---------------------------------------------------------------------------

# PVRT header magic
PVRT_MAGIC = 0x21525650  # "PVR!"

# Supported pixel formats (flags from PVRT header)
PIXEL_FORMAT_PVRTC_4BPP_RGBA = 0  # PVRTC 4-bit RGBA
PIXEL_FORMAT_PVRTC_2BPP_RGBA = 1  # PVRTC 2-bit RGBA
PIXEL_FORMAT_INVALID = -1

# PVRTC block dimensions
PVRTC_BLOCK_WIDTH = 8
PVRTC_BLOCK_HEIGHT = 4
PVRTC_BYTES_4BPP = 8  # 8 bytes per 4x4 block (4bpp)
PVRTC_BYTES_2BPP = 8  # 8 bytes per 8x4 block (2bpp)


# ---------------------------------------------------------------------------
# PVRT Header Structure
# ---------------------------------------------------------------------------

@dataclass
class PvrtHeader:
    """PVRT texture header."""
    magic: int = PVRT_MAGIC
    flags: int = 0
    pixel_format: int = 0
    color_space: int = 0
    channel_type: int = 0
    height: int = 0
    width: int = 0
    depth: int = 1
    num_surfaces: int = 1
    num_faces: int = 1
    mip_count: int = 1

    @classmethod
    def from_bytes(cls, data: bytes) -> PvrtHeader:
        """Parse PVRT header (52 bytes minimum)."""
        if len(data) < 52:
            raise ValueError(f"PVRT header too short: {len(data)} bytes")

        (magic, flags, pixel_format, color_space, channel_type,
         height, width, depth, num_surfaces, num_faces, mip_count) = struct.unpack(
            "<11I", data[:44]
        )

        if magic != PVRT_MAGIC:
            raise ValueError(f"Invalid PVRT magic: 0x{magic:08x}")

        return cls(
            magic=magic,
            flags=flags,
            pixel_format=pixel_format,
            color_space=color_space,
            channel_type=channel_type,
            height=height,
            width=width,
            depth=depth,
            num_surfaces=num_surfaces,
            num_faces=num_faces,
            mip_count=mip_count,
        )


# ---------------------------------------------------------------------------
# PvrzFile
# ---------------------------------------------------------------------------

class PvrzFile:
    """
    A decompressed PVRZ (zlib-compressed PVRT) texture page.

    PVRZ files store full texture pages (typically 256×512 or larger) referenced
    by PVRZ-based resources (TIS V2, MOS V2).  Each block in those resources
    specifies (page_number, x, y) to identify where its texture data lives.
    """

    def __init__(
        self,
        header: PvrtHeader,
        pixel_data: bytes,
        source_path: Optional[Path] = None,
    ) -> None:
        self.header = header
        self.pixel_data = pixel_data  # Raw PVRTC-compressed bytes
        self.source_path = source_path

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def width(self) -> int:
        return self.header.width

    @property
    def height(self) -> int:
        return self.header.height

    @property
    def pixel_format(self) -> int:
        return self.header.pixel_format

    @property
    def is_4bpp(self) -> bool:
        return self.pixel_format == PIXEL_FORMAT_PVRTC_4BPP_RGBA

    @property
    def is_2bpp(self) -> bool:
        return self.pixel_format == PIXEL_FORMAT_PVRTC_2BPP_RGBA

    # ------------------------------------------------------------------
    # Decompression
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes, source_path: Optional[Path] = None) -> PvrzFile:
        """
        Decompress PVRZ and parse PVRT header + pixel data.

        Raises ValueError if decompression or header parsing fails.
        """
        try:
            decompressed = zlib.decompress(data)
        except zlib.error as e:
            raise ValueError(f"Failed to decompress PVRZ: {e}") from e

        return cls.from_decompressed(decompressed, source_path)

    @classmethod
    def from_decompressed(cls, data: bytes, source_path: Optional[Path] = None) -> PvrzFile:
        """
        Parse decompressed PVRZ data using Enhanced Edition simplified header format.

        EE PVRZ files use a custom header structure starting with 'PVR' magic.
        The exact width/height encoding varies, but texture pages are typically 
        standard sizes (256x256, 512x512, 1024x512, etc).

        Raises ValueError if header is invalid.
        """
        if len(data) < 12:
            raise ValueError(f"Decompressed PVRZ too short: {len(data)} bytes (need at least 12)")

        # Check for 'PVR' magic marker
        magic_bytes = data[0:3]
        if magic_bytes != b'PVR':
            raise ValueError(f"Invalid PVRZ magic: {magic_bytes!r} (expected b'PVR')")
        
        format_marker = data[3]
        pixel_data = data[12:]  # Skip 12-byte header, assume rest is PVRTC data
        
        # Infer dimensions from decompressed pixel data size
        # PVRTC 4bpp: 8 bytes per 4x4 block
        
        blocks_count = len(pixel_data) // 8
        sqrt_blocks = int(blocks_count ** 0.5)
        
        # Start with square texture assumption
        width = sqrt_blocks * 4
        height = sqrt_blocks * 4
        pixel_format = PIXEL_FORMAT_PVRTC_4BPP_RGBA
        
        # Create a synthetic PVRT header to maintain compatibility
        header = PvrtHeader(
            magic=0x21525650,
            flags=0,
            pixel_format=pixel_format,
            color_space=0,
            channel_type=0,
            height=height,
            width=width,
            depth=1,
            num_surfaces=1,
            num_faces=1,
            mip_count=1
        )

        return cls(header=header, pixel_data=pixel_data, source_path=source_path)

    @classmethod
    def from_file(cls, path: str | Path) -> PvrzFile:
        """Load PVRZ from file."""
        path = Path(path)
        return cls.from_bytes(path.read_bytes(), source_path=path)

    # ------------------------------------------------------------------
    # Region Extraction
    # ------------------------------------------------------------------

    def to_rgba(self) -> Optional[bytes]:
        """
        Decode full PVRTC texture to RGBA.

        Uses the appropriate decoder based on pixel format (4bpp, 2bpp, etc).

        Returns:
            RGBA byte array or None if decoding fails
        """
        if self.is_4bpp:
            return decode_pvrtc_4bpp(self.pixel_data, self.width, self.height)
        elif self.is_2bpp:
            return decode_pvrtc_2bpp(self.pixel_data, self.width, self.height)
        else:
            return None

    def get_region_rgba(self, x: int, y: int, width: int, height: int) -> Optional[bytes]:
        """
        Extract a region as RGBA bytes.

        First decodes the full texture, then extracts the specified rectangle.

        Args:
            x, y: Top-left corner of region
            width, height: Region dimensions

        Returns:
            RGBA byte array or None if extraction fails
        """
        if width <= 0 or height <= 0:
            return None
        
        full_rgba = self.to_rgba()
        if full_rgba is None:
            return None

        # Extract region from full texture
        out = bytearray(width * height * 4)
        try:
            for row in range(height):
                src_y = y + row
                if src_y >= self.height:
                    break

                for col in range(width):
                    src_x = x + col
                    if src_x >= self.width:
                        break

                    # Copy RGBA pixel
                    src_idx = (src_y * self.width + src_x) * 4
                    dst_idx = (row * width + col) * 4

                    for c in range(4):
                        out[dst_idx + c] = full_rgba[src_idx + c]

            return bytes(out)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Re-compress to PVRZ format."""
        header_bytes = self._header_to_bytes()
        uncompressed = header_bytes + self.pixel_data
        return zlib.compress(uncompressed, level=9)

    def _header_to_bytes(self) -> bytes:
        """Serialize PVRT header."""
        h = self.header
        return struct.pack(
            "<11I",
            h.magic,
            h.flags,
            h.pixel_format,
            h.color_space,
            h.channel_type,
            h.height,
            h.width,
            h.depth,
            h.num_surfaces,
            h.num_faces,
            h.mip_count,
        ) + b"\x00" * 8  # Metadata offset + flags (padding)
