"""Minimal Infinity Engine BAM/BAMC reader for icon display use-cases.

Supports:
  - BAM V1  (palette-based, classic games + EE)
  - BAMC    (zlib-compressed BAM V1)
  - BAM V2  (PVRZ texture-page-based, Enhanced Edition only)
"""

from __future__ import annotations

import struct
import zlib
from typing import Callable, Optional


class BamDecodeError(ValueError):
    """Raised when BAM data cannot be decoded."""


# Callback type: given a PVRZ page number returns a PvrzFile (with get_region_rgba) or None.
PvrzLoader = Callable[[int], Optional[object]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decode_first_frame_rgba(
    raw: bytes,
    *,
    pvrz_loader: Optional[PvrzLoader] = None,
) -> tuple[int, int, list[float]]:
    """Decode a representative frame into Dear PyGui RGBA texture data.

    For V1/BAMC: uses the first non-transparent frame.
    For V2: decodes cycle 0, frame 0.
    pvrz_loader is required for BAM V2.
    """
    data = _decompress_bamc_if_needed(raw)
    _check_size(data, 24)

    sig, ver = data[0:4], data[4:8]
    if sig == b"BAM " and ver == b"V2  ":
        return _decode_v2_cycle_frame(data, cycle=0, frame=0, pvrz_loader=pvrz_loader)

    if sig != b"BAM " or ver != b"V1  ":
        raise BamDecodeError(f"Unsupported BAM signature/version: {sig!r} {ver!r}")

    frame_count       = struct.unpack_from("<H", data, 0x08)[0]
    if frame_count < 1:
        raise BamDecodeError("BAM contains no frames.")

    rle_marker        = data[0x0B]
    frame_entries_off = struct.unpack_from("<I", data, 0x0C)[0]
    palette_off       = struct.unpack_from("<I", data, 0x10)[0]

    palette         = _read_palette(data, palette_off)
    transparent_idx = _transparent_index(palette)

    best: tuple[int, int, list[int]] | None = None
    for frame_index in range(frame_count):
        width, height, pixels = _decode_frame_indices(
            data=data,
            frame_entries_off=frame_entries_off,
            frame_index=frame_index,
            rle_marker=rle_marker,
        )
        if best is None:
            best = (width, height, pixels)
        if any(px != transparent_idx for px in pixels):
            best = (width, height, pixels)
            break

    if best is None:
        raise BamDecodeError("No decodable BAM frames found.")

    width, height, pixels = best
    return width, height, _indices_to_rgba(pixels, palette, transparent_idx)


def decode_cycle_frame_rgba(
    raw: bytes,
    *,
    cycle: int = 0,
    frame: int = 0,
    pvrz_loader: Optional[PvrzLoader] = None,
) -> tuple[int, int, list[float]]:
    """Decode a specific cycle/frame from a BAM V1, BAMC, or BAM V2 file.

    BAM V1 header:
      0x08  frame_count        uint16
      0x0A  cycle_count        uint16
      0x0B  rle_marker         uint8
      0x0C  frame_entries_off  uint32  (12 bytes/entry)
      0x10  palette_off        uint32
      0x14  cycle_entries_off  uint32  (4 bytes/entry: count uint16 + first_lookup uint16)
      Lookup table follows cycle entries: one uint16/slot -> global frame index.

    BAM V2 header (EE only):
      0x08  frame_count        uint32
      0x0C  cycle_count        uint32
      0x10  data_block_count   uint32
      0x14  frame_entries_off  uint32  (12 bytes/entry)
      0x18  cycle_entries_off  uint32  (4 bytes/entry: count uint16 + first_frame uint16)
      0x1C  data_blocks_off    uint32  (28 bytes/entry)

    pvrz_loader is required for BAM V2 files.
    """
    data = _decompress_bamc_if_needed(raw)
    _check_size(data, 24)

    sig, ver = data[0:4], data[4:8]
    if sig == b"BAM " and ver == b"V2  ":
        return _decode_v2_cycle_frame(data, cycle=cycle, frame=frame, pvrz_loader=pvrz_loader)

    if sig != b"BAM " or ver != b"V1  ":
        raise BamDecodeError(f"Unsupported BAM signature/version: {sig!r} {ver!r}")

    # --- BAM V1 ---
    frame_count       = struct.unpack_from("<H", data, 0x08)[0]
    cycle_count       = struct.unpack_from("<H", data, 0x0A)[0]
    rle_marker        = data[0x0B]
    frame_entries_off = struct.unpack_from("<I", data, 0x0C)[0]
    palette_off       = struct.unpack_from("<I", data, 0x10)[0]
    cycle_entries_off = struct.unpack_from("<I", data, 0x14)[0]

    if cycle_count == 0 or cycle >= cycle_count:
        raise BamDecodeError(f"Cycle {cycle} out of range (cycle_count={cycle_count})")

    frames_in_cycle, first_lookup = struct.unpack_from(
        "<HH", data, cycle_entries_off + cycle * 4
    )
    if frames_in_cycle == 0 or frame >= frames_in_cycle:
        raise BamDecodeError(
            f"Frame {frame} out of range in cycle {cycle} (frames_in_cycle={frames_in_cycle})"
        )

    lookup_table_off = cycle_entries_off + cycle_count * 4
    global_frame_idx = struct.unpack_from(
        "<H", data, lookup_table_off + (first_lookup + frame) * 2
    )[0]

    if global_frame_idx >= frame_count:
        raise BamDecodeError(
            f"global_frame_idx={global_frame_idx} out of range (frame_count={frame_count})"
        )

    palette         = _read_palette(data, palette_off)
    transparent_idx = _transparent_index(palette)
    width, height, pixels = _decode_frame_indices(
        data=data,
        frame_entries_off=frame_entries_off,
        frame_index=global_frame_idx,
        rle_marker=rle_marker,
    )
    return width, height, _indices_to_rgba(pixels, palette, transparent_idx)


# ---------------------------------------------------------------------------
# BAM V2 internal decoder
# ---------------------------------------------------------------------------

def _decode_v2_cycle_frame(
    data: bytes,
    *,
    cycle: int,
    frame: int,
    pvrz_loader: Optional[PvrzLoader],
) -> tuple[int, int, list[float]]:
    """Decode one frame from already-decompressed BAM V2 data.

    Frame entry (12 bytes):
      0x00 width       uint16
      0x02 height      uint16
      0x04 cx          int16   (centre X, ignored)
      0x06 cy          int16   (centre Y, ignored)
      0x08 block_start uint16
      0x0A block_count uint16

    Data block (28 bytes):
      0x00 pvrz_page  uint32
      0x04 src_x      uint32
      0x08 src_y      uint32
      0x0C src_width  uint32
      0x10 src_height uint32
      0x14 tgt_x      uint32
      0x18 tgt_y      uint32
    """
    if pvrz_loader is None:
        raise BamDecodeError("BAM V2 requires a pvrz_loader but none was provided")

    _check_size(data, 0x20)

    frame_count       = struct.unpack_from("<I", data, 0x08)[0]
    cycle_count       = struct.unpack_from("<I", data, 0x0C)[0]
    frame_entries_off = struct.unpack_from("<I", data, 0x14)[0]
    cycle_entries_off = struct.unpack_from("<I", data, 0x18)[0]
    data_blocks_off   = struct.unpack_from("<I", data, 0x1C)[0]

    if cycle >= cycle_count:
        raise BamDecodeError(f"V2 cycle {cycle} out of range (count={cycle_count})")

    frames_in_cycle, first_frame_idx = struct.unpack_from(
        "<HH", data, cycle_entries_off + cycle * 4
    )
    if frame >= frames_in_cycle:
        raise BamDecodeError(
            f"V2 frame {frame} out of range in cycle {cycle} (count={frames_in_cycle})"
        )

    global_frame_idx = first_frame_idx + frame
    if global_frame_idx >= frame_count:
        raise BamDecodeError(f"V2 global_frame_idx={global_frame_idx} out of range")

    frame_off = frame_entries_off + global_frame_idx * 12
    width, height, _cx, _cy, block_start, block_count = struct.unpack_from(
        "<HHhhHH", data, frame_off
    )
    if width < 1 or height < 1:
        raise BamDecodeError(f"V2 frame has invalid dimensions {width}x{height}")

    # RGBA byte canvas, initially transparent
    canvas = bytearray(width * height * 4)

    for b in range(block_count):
        block_off = data_blocks_off + (block_start + b) * 28
        pvrz_page, src_x, src_y, src_w, src_h, tgt_x, tgt_y = struct.unpack_from(
            "<IIIIIII", data, block_off
        )

        pvrz = pvrz_loader(pvrz_page)
        if pvrz is None:
            continue

        region = pvrz.get_region_rgba(src_x, src_y, src_w, src_h)
        if region is None:
            continue

        # Blit the region onto the canvas at (tgt_x, tgt_y)
        for row in range(src_h):
            dy = tgt_y + row
            if dy >= height:
                break
            src_row_off = row * src_w * 4
            dst_row_off = dy * width * 4
            for col in range(src_w):
                dx = tgt_x + col
                if dx >= width:
                    break
                so = src_row_off + col * 4
                do = dst_row_off + dx * 4
                canvas[do:do + 4] = region[so:so + 4]

    return width, height, [v / 255.0 for v in canvas]


# ---------------------------------------------------------------------------
# BAM V1 helpers
# ---------------------------------------------------------------------------

def _decode_frame_indices(
    *,
    data: bytes,
    frame_entries_off: int,
    frame_index: int,
    rle_marker: int,
) -> tuple[int, int, list[int]]:
    frame_entry_size = 12
    frame_off = frame_entries_off + (frame_index * frame_entry_size)
    if frame_off + frame_entry_size > len(data):
        raise BamDecodeError("Frame table offset is out of bounds.")

    width, height, _cx, _cy, frame_data_field = struct.unpack_from("<HHhhI", data, frame_off)
    if width < 1 or height < 1:
        raise BamDecodeError("Invalid BAM frame dimensions.")

    frame_data_off  = frame_data_field & 0x7FFFFFFF
    is_uncompressed = bool(frame_data_field & 0x80000000)
    pixels = _read_frame_pixels(
        data=data,
        offset=frame_data_off,
        width=width,
        height=height,
        rle_marker=rle_marker,
        is_uncompressed=is_uncompressed,
    )
    return width, height, pixels


def _decompress_bamc_if_needed(raw: bytes) -> bytes:
    if len(raw) >= 4 and raw[0:4] == b"BAMC":
        if len(raw) < 12:
            raise BamDecodeError("BAMC data is too small.")
        expected_size = struct.unpack_from("<I", raw, 0x08)[0]
        try:
            decompressed = zlib.decompress(raw[12:])
        except zlib.error as exc:
            raise BamDecodeError(f"BAMC zlib decompression failed: {exc}") from exc
        if expected_size and len(decompressed) < expected_size:
            raise BamDecodeError("BAMC decompressed payload is shorter than declared size.")
        return decompressed
    return raw


def _check_size(data: bytes, minimum: int) -> None:
    if len(data) < minimum:
        raise BamDecodeError(f"BAM data too small: {len(data)} < {minimum}")


def _read_palette(data: bytes, palette_off: int) -> list[tuple[int, int, int, int]]:
    palette_bytes = 256 * 4
    if palette_off + palette_bytes > len(data):
        raise BamDecodeError("BAM palette offset is out of bounds.")
    palette: list[tuple[int, int, int, int]] = []
    for i in range(256):
        b, g, r, a = struct.unpack_from("<BBBB", data, palette_off + i * 4)
        palette.append((b, g, r, a))
    return palette


def _transparent_index(palette: list[tuple[int, int, int, int]]) -> int:
    for i, (b, g, r, _a) in enumerate(palette):
        if r == 0 and g == 255 and b == 0:
            return i
    return 0


def _indices_to_rgba(
    pixels: list[int],
    palette: list[tuple[int, int, int, int]],
    transparent_idx: int,
) -> list[float]:
    rgba: list[float] = []
    for idx in pixels:
        b, g, r, _ = palette[idx]
        if idx == transparent_idx:
            rgba.extend((0.0, 0.0, 0.0, 0.0))   # zero out RGB on transparent pixels
        else:
            rgba.extend((r / 255.0, g / 255.0, b / 255.0, 1.0))
    return rgba


def _read_frame_pixels(
    *,
    data: bytes,
    offset: int,
    width: int,
    height: int,
    rle_marker: int,
    is_uncompressed: bool,
) -> list[int]:
    pixel_count = width * height
    if offset >= len(data):
        raise BamDecodeError("Frame data offset is out of bounds.")

    if is_uncompressed:
        end = offset + pixel_count
        if end > len(data):
            raise BamDecodeError("Uncompressed frame overruns BAM payload.")
        return list(data[offset:end])

    out: list[int] = []
    i = offset
    while len(out) < pixel_count:
        if i >= len(data):
            raise BamDecodeError("Compressed frame ended early.")
        b = data[i]
        i += 1
        if b != rle_marker:
            out.append(b)
            continue
        if i >= len(data):
            raise BamDecodeError("Compressed frame RLE marker without run length.")
        run = data[i] + 1
        i += 1
        out.extend([rle_marker] * run)

    return out[:pixel_count]