"""Minimal Windows BMP reader for icon preview use-cases."""

from __future__ import annotations

import struct


class BmpDecodeError(ValueError):
    """Raised when BMP data cannot be decoded."""


def decode_bmp_rgba(raw: bytes) -> tuple[int, int, list[float]]:
    """Decode a BMP image into Dear PyGui RGBA texture data."""
    if len(raw) < 26:
        raise BmpDecodeError("BMP data is too small.")
    if raw[0:2] != b"BM":
        raise BmpDecodeError("Unsupported BMP signature.")

    pixel_offset = struct.unpack_from("<I", raw, 10)[0]
    dib_size = struct.unpack_from("<I", raw, 14)[0]
    if dib_size < 12:
        raise BmpDecodeError("Unsupported BMP DIB header size.")

    if dib_size == 12:
        # OS/2 BITMAPCOREHEADER
        width = struct.unpack_from("<H", raw, 18)[0]
        height_signed = struct.unpack_from("<H", raw, 20)[0]
        planes = struct.unpack_from("<H", raw, 22)[0]
        bpp = struct.unpack_from("<H", raw, 24)[0]
        compression = 0
        clr_used = 0
        palette_entry_size = 3
    else:
        # Windows BITMAPINFOHEADER and later variants
        if len(raw) < 54:
            raise BmpDecodeError("BMP data is too small for info header.")
        width = struct.unpack_from("<i", raw, 18)[0]
        height_signed = struct.unpack_from("<i", raw, 22)[0]
        planes = struct.unpack_from("<H", raw, 26)[0]
        bpp = struct.unpack_from("<H", raw, 28)[0]
        compression = struct.unpack_from("<I", raw, 30)[0]
        clr_used = struct.unpack_from("<I", raw, 46)[0]
        palette_entry_size = 4

    if planes != 1:
        raise BmpDecodeError("Invalid BMP planes value.")
    if width <= 0 or height_signed == 0:
        raise BmpDecodeError("Invalid BMP dimensions.")
    if compression not in (0, 1, 2, 3):
        raise BmpDecodeError(f"Unsupported BMP compression: {compression}.")

    top_down = height_signed < 0
    height = abs(height_signed)

    if bpp == 8 and compression in (0, 1):
        return _decode_8bpp(
            raw, width, height, top_down, pixel_offset, clr_used, dib_size, compression, palette_entry_size
        )
    if bpp == 4 and compression in (0, 2):
        return _decode_4bpp(
            raw, width, height, top_down, pixel_offset, clr_used, dib_size, compression, palette_entry_size
        )
    if bpp == 24 and compression == 0:
        return _decode_24bpp(raw, width, height, top_down, pixel_offset)
    if bpp == 32 and compression in (0, 3):
        return _decode_32bpp(raw, width, height, top_down, pixel_offset)

    raise BmpDecodeError(f"Unsupported BMP format: {bpp}bpp compression={compression}.")


def _decode_8bpp(
    raw: bytes,
    width: int,
    height: int,
    top_down: bool,
    pixel_offset: int,
    clr_used: int,
    dib_size: int,
    compression: int,
    palette_entry_size: int,
) -> tuple[int, int, list[float]]:
    palette_count = clr_used if clr_used else 256
    pal_off = 14 + dib_size
    palette = _read_palette(raw, pal_off, palette_count, palette_entry_size)

    if compression == 1:
        indices = _decode_rle8_indices(raw, pixel_offset, width, height)
    else:
        row_stride = ((width + 3) // 4) * 4
        data_needed = row_stride * height
        if pixel_offset + data_needed > len(raw):
            raise BmpDecodeError("BMP pixel data is out of bounds.")
        indices: list[int] = [0] * (width * height)
        for y in range(height):
            src_y = y if top_down else (height - 1 - y)
            row_start = pixel_offset + src_y * row_stride
            dst_off = y * width
            for x in range(width):
                indices[dst_off + x] = raw[row_start + x]

    return _indices_to_rgba(indices, palette, width, height)


def _decode_4bpp(
    raw: bytes,
    width: int,
    height: int,
    top_down: bool,
    pixel_offset: int,
    clr_used: int,
    dib_size: int,
    compression: int,
    palette_entry_size: int,
) -> tuple[int, int, list[float]]:
    palette_count = clr_used if clr_used else 16
    pal_off = 14 + dib_size
    palette = _read_palette(raw, pal_off, palette_count, palette_entry_size)

    if compression == 2:
        indices = _decode_rle4_indices(raw, pixel_offset, width, height)
    else:
        row_stride = (((width + 1) // 2 + 3) // 4) * 4
        data_needed = row_stride * height
        if pixel_offset + data_needed > len(raw):
            raise BmpDecodeError("BMP pixel data is out of bounds.")
        indices: list[int] = [0] * (width * height)
        for y in range(height):
            src_y = y if top_down else (height - 1 - y)
            row_start = pixel_offset + src_y * row_stride
            dst_off = y * width
            x = 0
            while x < width:
                b = raw[row_start + (x // 2)]
                hi = (b >> 4) & 0x0F
                lo = b & 0x0F
                indices[dst_off + x] = hi
                x += 1
                if x < width:
                    indices[dst_off + x] = lo
                    x += 1
    return _indices_to_rgba(indices, palette, width, height)


def _read_palette(raw: bytes, pal_off: int, palette_count: int, entry_size: int) -> list[tuple[int, int, int]]:
    pal_size = palette_count * entry_size
    if pal_off + pal_size > len(raw):
        raise BmpDecodeError("BMP palette is out of bounds.")
    palette: list[tuple[int, int, int]] = []
    for i in range(palette_count):
        off = pal_off + i * entry_size
        if entry_size == 3:
            b, g, r = struct.unpack_from("<BBB", raw, off)
        else:
            b, g, r, _ = struct.unpack_from("<BBBB", raw, off)
        palette.append((r, g, b))
    return palette


def _decode_rle8_indices(raw: bytes, offset: int, width: int, height: int) -> list[int]:
    indices: list[int] = [0] * (width * height)
    x = 0
    y = height - 1  # RLE8 is typically bottom-up
    i = offset

    while i < len(raw) and y >= 0:
        count = raw[i]
        i += 1
        if i >= len(raw):
            break
        val = raw[i]
        i += 1

        if count > 0:
            for _ in range(count):
                if 0 <= x < width and 0 <= y < height:
                    indices[y * width + x] = val
                x += 1
            continue

        # Escape sequence
        if val == 0:  # EOL
            x = 0
            y -= 1
            continue
        if val == 1:  # EOB
            break
        if val == 2:  # Delta
            if i + 1 >= len(raw):
                break
            dx = raw[i]
            dy = raw[i + 1]
            i += 2
            x += dx
            y -= dy
            continue

        # Absolute mode: val = number of literal bytes
        n = val
        if i + n > len(raw):
            break
        for k in range(n):
            if 0 <= x < width and 0 <= y < height:
                indices[y * width + x] = raw[i + k]
            x += 1
        i += n
        # Align to word boundary
        if n & 1:
            i += 1

    return indices


def _decode_rle4_indices(raw: bytes, offset: int, width: int, height: int) -> list[int]:
    indices: list[int] = [0] * (width * height)
    x = 0
    y = height - 1
    i = offset

    while i < len(raw) and y >= 0:
        count = raw[i]
        i += 1
        if i >= len(raw):
            break
        val = raw[i]
        i += 1

        if count > 0:
            hi = (val >> 4) & 0x0F
            lo = val & 0x0F
            for n in range(count):
                px = hi if (n % 2 == 0) else lo
                if 0 <= x < width and 0 <= y < height:
                    indices[y * width + x] = px
                x += 1
            continue

        if val == 0:  # EOL
            x = 0
            y -= 1
            continue
        if val == 1:  # EOB
            break
        if val == 2:  # Delta
            if i + 1 >= len(raw):
                break
            dx = raw[i]
            dy = raw[i + 1]
            i += 2
            x += dx
            y -= dy
            continue

        # Absolute mode: val = number of pixels (nibbles)
        n = val
        byte_count = (n + 1) // 2
        if i + byte_count > len(raw):
            break
        for p in range(n):
            b = raw[i + (p // 2)]
            px = ((b >> 4) & 0x0F) if (p % 2 == 0) else (b & 0x0F)
            if 0 <= x < width and 0 <= y < height:
                indices[y * width + x] = px
            x += 1
        i += byte_count
        # Absolute mode aligns to 16-bit word boundary.
        if byte_count & 1:
            i += 1

    return indices


def _indices_to_rgba(
    indices: list[int],
    palette: list[tuple[int, int, int]],
    width: int,
    height: int,
) -> tuple[int, int, list[float]]:
    rgba: list[float] = []
    for idx in indices:
        if idx >= len(palette):
            rgba.extend((0.0, 0.0, 0.0, 0.0))
            continue
        r, g, b = palette[idx]
        if r == 0 and g == 255 and b == 0:
            rgba.extend((0.0, 0.0, 0.0, 0.0))
        else:
            rgba.extend((r / 255.0, g / 255.0, b / 255.0, 1.0))
    return width, height, rgba


def _decode_24bpp(
    raw: bytes,
    width: int,
    height: int,
    top_down: bool,
    pixel_offset: int,
) -> tuple[int, int, list[float]]:
    row_stride = ((width * 3 + 3) // 4) * 4
    data_needed = row_stride * height
    if pixel_offset + data_needed > len(raw):
        raise BmpDecodeError("BMP pixel data is out of bounds.")

    rgba: list[float] = []
    for y in range(height):
        src_y = y if top_down else (height - 1 - y)
        row_start = pixel_offset + src_y * row_stride
        for x in range(width):
            px = row_start + x * 3
            b, g, r = struct.unpack_from("<BBB", raw, px)
            if r == 0 and g == 255 and b == 0:
                rgba.extend((0.0, 0.0, 0.0, 0.0))
            else:
                rgba.extend((r / 255.0, g / 255.0, b / 255.0, 1.0))
    return width, height, rgba


def _decode_32bpp(
    raw: bytes,
    width: int,
    height: int,
    top_down: bool,
    pixel_offset: int,
) -> tuple[int, int, list[float]]:
    row_stride = width * 4
    data_needed = row_stride * height
    if pixel_offset + data_needed > len(raw):
        raise BmpDecodeError("BMP pixel data is out of bounds.")

    rgba: list[float] = []
    for y in range(height):
        src_y = y if top_down else (height - 1 - y)
        row_start = pixel_offset + src_y * row_stride
        for x in range(width):
            px = row_start + x * 4
            b, g, r, a = struct.unpack_from("<BBBB", raw, px)
            if r == 0 and g == 255 and b == 0:
                rgba.extend((0.0, 0.0, 0.0, 0.0))
            else:
                if a == 0 and (r != 0 or g != 0 or b != 0):
                    a = 255
                rgba.extend((r / 255.0, g / 255.0, b / 255.0, a / 255.0))
    return width, height, rgba
