"""Minimal Infinity Engine BAM/BAMC reader for icon display use-cases."""

from __future__ import annotations

import struct
import zlib


class BamDecodeError(ValueError):
    """Raised when BAM data cannot be decoded."""


def decode_first_frame_rgba(raw: bytes) -> tuple[int, int, list[float]]:
    """Decode a representative BAM/BAMC frame into Dear PyGui RGBA texture data.

    Uses the first non-empty frame if available; otherwise falls back to frame 0.
    """
    data = _decompress_bamc_if_needed(raw)
    if len(data) < 24:
        raise BamDecodeError("BAM data is too small.")

    sig = data[0:4]
    ver = data[4:8]
    if sig != b"BAM " or ver != b"V1  ":
        raise BamDecodeError(f"Unsupported BAM signature/version: {sig!r} {ver!r}")

    frame_count = struct.unpack_from("<H", data, 0x08)[0]
    if frame_count < 1:
        raise BamDecodeError("BAM contains no frames.")

    rle_marker = data[0x0B]
    frame_entries_off = struct.unpack_from("<I", data, 0x0C)[0]
    palette_off = struct.unpack_from("<I", data, 0x10)[0]

    palette = _read_palette(data, palette_off)
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
    rgba = _indices_to_rgba(pixels, palette, transparent_idx)
    return width, height, rgba


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

    frame_data_off = frame_data_field & 0x7FFFFFFF
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
        if expected_size and len(decompressed) != expected_size:
            # Keep permissive behavior, but reject clearly broken payload.
            if len(decompressed) < expected_size:
                raise BamDecodeError("BAMC decompressed payload is shorter than declared size.")
        return decompressed
    return raw


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
        a = 0.0 if idx == transparent_idx else 1.0
        rgba.extend((r / 255.0, g / 255.0, b / 255.0, a))
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
