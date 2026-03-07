"""
core/util/binary.py

Low-level binary read/write helpers used by every IE file format parser.

All Infinity Engine formats are little-endian. Structs are tightly packed
with no padding unless explicitly noted in IESDP.

Usage:
    from core.util.binary import BinaryReader, BinaryWriter

    with open("dialog.tlk", "rb") as f:
        reader = BinaryReader(f.read())

    sig = reader.read_bytes(4)
    count = reader.read_uint32()
    text = reader.read_string(32)
"""

import struct
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BinaryError(Exception):
    """Raised when binary data cannot be read or written correctly."""


class SignatureMismatch(BinaryError):
    """Raised when a file signature does not match the expected value."""


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class BinaryReader:
    """
    Wraps a bytes object and provides typed, offset-tracked reads.

    All multi-byte values are read as little-endian unless a specific
    struct format string is passed directly.
    """

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    # ------------------------------------------------------------------
    # Position control
    # ------------------------------------------------------------------

    @property
    def pos(self) -> int:
        """Current read position."""
        return self._pos

    @property
    def size(self) -> int:
        """Total size of the underlying data."""
        return len(self._data)

    @property
    def remaining(self) -> int:
        """Number of bytes left from the current position."""
        return self.size - self._pos

    def seek(self, offset: int) -> None:
        """Move to an absolute byte offset."""
        if offset < 0 or offset > self.size:
            raise BinaryError(
                f"Seek to {offset:#x} is out of range (file size {self.size:#x})"
            )
        self._pos = offset

    def skip(self, count: int) -> None:
        """Advance position by count bytes."""
        self.seek(self._pos + count)

    # ------------------------------------------------------------------
    # Raw reads
    # ------------------------------------------------------------------

    def read_bytes(self, count: int) -> bytes:
        """Read raw bytes and advance position."""
        end = self._pos + count
        if end > self.size:
            raise BinaryError(
                f"Read of {count} bytes at {self._pos:#x} exceeds file size {self.size:#x}"
            )
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def read_bytes_at(self, offset: int, count: int) -> bytes:
        """Read raw bytes from an absolute offset without moving position."""
        end = offset + count
        if end > self.size:
            raise BinaryError(
                f"Read of {count} bytes at {offset:#x} exceeds file size {self.size:#x}"
            )
        return self._data[offset:end]

    # ------------------------------------------------------------------
    # Typed reads (little-endian)
    # ------------------------------------------------------------------

    def _unpack(self, fmt: str, size: int) -> Any:
        chunk = self.read_bytes(size)
        return struct.unpack_from(fmt, chunk)[0]

    def read_int8(self)   -> int: return self._unpack("<b", 1)
    def read_uint8(self)  -> int: return self._unpack("<B", 1)
    def read_int16(self)  -> int: return self._unpack("<h", 2)
    def read_uint16(self) -> int: return self._unpack("<H", 2)
    def read_int32(self)  -> int: return self._unpack("<i", 4)
    def read_uint32(self) -> int: return self._unpack("<I", 4)

    def read_string(self, length: int, encoding: str = "latin-1") -> str:
        """
        Read a fixed-length null-padded string.

        IE strings are fixed-width byte fields, null-padded to fill the
        field. Trailing nulls and spaces are stripped. latin-1 is used
        because many IE files predate Unicode.
        """
        raw = self.read_bytes(length)
        return raw.rstrip(b"\x00").decode(encoding, errors="replace").rstrip()

    def read_resref(self) -> str:
        """
        Read an 8-byte resource reference.

        ResRefs are the Infinity Engine's resource name type: exactly 8
        bytes on disk, null-terminated (not just null-padded).  Bytes
        after the first null are padding and must be ignored — some
        Bioware/Black Isle tools leave non-zero garbage in the padding
        area which would otherwise appear as extra characters.

        Returns the ResRef as an uppercase str with no extension.
        """
        raw = self.read_bytes(8)
        # All-0xFF is the IE sentinel for "no resref" — treat as empty.
        if raw == b"\xff" * 8:
            return ""
        # Truncate at first null byte — bytes beyond it are padding.
        null_pos = raw.find(b"\x00")
        if null_pos >= 0:
            raw = raw[:null_pos]
        decoded = raw.decode("latin-1").upper()
        # Truncate at first character that can't appear in a ResRef.
        # Some tools leave non-null garbage bytes after the name; the IE
        # engine stops reading at the first non-valid byte just as it would
        # at a null.  Valid chars: A-Z, 0-9, underscore, hyphen, hash.
        result = []
        for ch in decoded:
            if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-#":
                result.append(ch)
            else:
                break
        return "".join(result)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def expect_signature(self, expected: bytes) -> None:
        """
        Read len(expected) bytes and raise SignatureMismatch if they differ.

        Used at the start of every parser to validate the file type.

            reader.expect_signature(b"TLK ")
            reader.expect_signature(b"V1  ")
        """
        actual = self.read_bytes(len(expected))
        if actual != expected:
            raise SignatureMismatch(
                f"Expected signature {expected!r}, got {actual!r} "
                f"at offset {self._pos - len(expected):#x}"
            )

    def peek_bytes(self, count: int) -> bytes:
        """Read bytes without advancing position."""
        return self._data[self._pos: self._pos + count]


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class BinaryWriter:
    """
    Builds a bytes object by appending typed values.

    Usage:
        writer = BinaryWriter()
        writer.write_bytes(b"TLK ")
        writer.write_bytes(b"V1  ")
        writer.write_uint32(entry_count)
        raw = writer.to_bytes()
    """

    def __init__(self):
        self._buf: list[bytes] = []

    def to_bytes(self) -> bytes:
        """Return the accumulated buffer as a single bytes object."""
        return b"".join(self._buf)

    @property
    def pos(self) -> int:
        """Current write position (total bytes written so far)."""
        return sum(len(b) for b in self._buf)

    # ------------------------------------------------------------------
    # Raw writes
    # ------------------------------------------------------------------

    def write_bytes(self, data: bytes) -> None:
        self._buf.append(data)

    # ------------------------------------------------------------------
    # Typed writes (little-endian)
    # ------------------------------------------------------------------

    def _pack(self, fmt: str, value: Any) -> None:
        self._buf.append(struct.pack(fmt, value))

    def write_int8(self,   v: int) -> None: self._pack("<b", v)
    def write_uint8(self,  v: int) -> None: self._pack("<B", v)
    def write_int16(self,  v: int) -> None: self._pack("<h", v)
    def write_uint16(self, v: int) -> None: self._pack("<H", v)
    def write_int32(self,  v: int) -> None: self._pack("<i", v)
    def write_uint32(self, v: int) -> None: self._pack("<I", v)

    def write_string(self, value: str, length: int, encoding: str = "latin-1") -> None:
        """
        Write a fixed-length null-padded string field.

        If value is longer than length it is truncated. Remaining bytes
        are padded with null bytes.
        """
        encoded = value.encode(encoding, errors="replace")
        encoded = encoded[:length]
        padded  = encoded.ljust(length, b"\x00")
        self._buf.append(padded)

    def write_resref(self, value: str) -> None:
        """Write an 8-byte ResRef field, uppercased and null-padded."""
        self.write_string(value.upper(), 8)

    def write_padding(self, count: int) -> None:
        """Write count null bytes (for reserved/unused fields)."""
        self._buf.append(b"\x00" * count)