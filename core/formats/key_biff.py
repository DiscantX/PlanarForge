"""
core/formats/key_biff.py

CHITIN.KEY index reader and BIFF v1 archive reader for Infinity Engine games.

CHITIN.KEY is the master resource index found in every IE game installation.
It maps (ResRef, resource-type) pairs to a location inside one of the game's
BIFF archives.  BIFF files are the actual data containers — each one holds
hundreds of tightly-packed game resources (areas, creatures, items, etc.).

Supported games (all share the same KEY V1 / BIFF V1 format):
    Baldur's Gate 1 & 2, Icewind Dale 1 & 2, Planescape: Torment,
    Baldur's Gate: Enhanced Edition, BG2:EE, IWD:EE, PST:EE

IESDP references:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/key_v1.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/bif_v1.htm

Usage::

    from core.formats.key_biff import KeyFile, ResType

    key = KeyFile.open("/path/to/game/CHITIN.KEY")
    entry = key.find("AR0602", ResType.ARE)
    if entry:
        raw = key.read_resource(entry, game_root="/path/to/game")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Tuple, Union

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.resref import ResRef

if TYPE_CHECKING:
    # Imported only for type hints; avoids a circular dependency at runtime
    # since installation.py does not import key_biff.py.
    from core.installation import GameInstallation

# A game root can be supplied as a plain path or as a GameInstallation object.
GameRoot = Union[str, Path, "GameInstallation"]


def _resolve_game_root(game_root: "GameRoot") -> Path:
    """
    Normalise *game_root* to a :class:`Path`.

    Accepts a plain ``str`` or ``Path``, or a ``GameInstallation`` object
    (in which case its ``install_path`` attribute is used).  This lets
    callers pass whatever is most convenient without the low-level reader
    needing to know about the higher-level installation abstraction.
    """
    # Check by attribute rather than isinstance to avoid a hard import of
    # the installation module at runtime (keeps the dependency one-way).
    if hasattr(game_root, "install_path"):
        return Path(game_root.install_path)
    return Path(game_root)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class KeyFileError(Exception):
    """Raised when a KEY file cannot be parsed."""

class BiffError(Exception):
    """Raised when a BIFF file cannot be parsed."""


# ---------------------------------------------------------------------------
# Resource type registry
# ---------------------------------------------------------------------------

class ResType(IntEnum):
    """
    Infinity Engine resource type codes.

    These are the uint16 values stored in both KEY resource entries and
    BIFF file entries to identify what kind of data a resource contains.
    """
    BMP    = 0x0001
    MVE    = 0x0002
    WAV    = 0x0004
    WFX    = 0x0005
    PLT    = 0x0006
    BAM    = 0x03E8
    WED    = 0x03E9
    CHU    = 0x03EA
    TIS    = 0x03EB
    MOS    = 0x03EC
    ITM    = 0x03ED
    SPL    = 0x03EE
    BCS    = 0x03EF
    IDS    = 0x03F0
    CRE    = 0x03F1
    ARE    = 0x03F2
    DLG    = 0x03F3
    TWO_DA = 0x03F4
    GAM    = 0x03F5
    STO    = 0x03F6
    WMP    = 0x03F7
    CHR    = 0x03F8
    BS     = 0x03F9
    VVC    = 0x03FB
    VEF    = 0x03FC
    PRO    = 0x03FD
    BIO    = 0x03FE
    WBM    = 0x03FF
    FNT    = 0x0400
    GUI    = 0x0402
    SQL    = 0x0403
    PVRZ   = 0x0404
    GLSL   = 0x0405
    MENU   = 0x0408
    LUA    = 0x0409
    TTF    = 0x040A
    PNG    = 0x040B
    BAH    = 0x044C
    INI    = 0x0802
    SRC    = 0x0803

    @classmethod
    def extension(cls, code: int) -> str:
        """Return a lowercase file extension for a resource type code."""
        _EXT: Dict[int, str] = {
            0x0001: "bmp",  0x0002: "mve",  0x0004: "wav",  0x0005: "wfx",
            0x0006: "plt",  0x03E8: "bam",  0x03E9: "wed",  0x03EA: "chu",
            0x03EB: "tis",  0x03EC: "mos",  0x03ED: "itm",  0x03EE: "spl",
            0x03EF: "bcs",  0x03F0: "ids",  0x03F1: "cre",  0x03F2: "are",
            0x03F3: "dlg",  0x03F4: "2da",  0x03F5: "gam",  0x03F6: "sto",
            0x03F7: "wmp",  0x03F8: "chr",  0x03F9: "bs",   0x03FB: "vvc",
            0x03FC: "vef",  0x03FD: "pro",  0x03FE: "bio",  0x03FF: "wbm",
            0x0400: "fnt",  0x0402: "gui",  0x0403: "sql",  0x0404: "pvrz",
            0x0405: "glsl", 0x0408: "menu", 0x0409: "lua",  0x040A: "ttf",
            0x040B: "png",  0x044C: "bah",  0x0802: "ini",  0x0803: "src",
        }
        return _EXT.get(code, f"res_{code:04x}")


# ---------------------------------------------------------------------------
# KEY data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BiffEntry:
    """
    One row from the BIFF file table in CHITIN.KEY.

    Describes a single .bif archive: where it lives on disk and which
    CD/location flag applies (used by the original CD-ROM releases).
    """
    index:       int    # Zero-based position in the bif table
    filename:    str    # Relative path, e.g. "data\\AR0602.bif"
    file_length: int    # Uncompressed archive size in bytes (informational)
    location:    int    # Bitmask: bit 0 = data dir, bits 1-6 = CD1-6


@dataclass(frozen=True)
class ResourceEntry:
    """
    One row from the resource table in CHITIN.KEY.

    Identifies a single game resource by name and type, and encodes its
    location inside a BIFF archive via a packed 32-bit locator.

    Locator bit layout (from IESDP):
        bits 31-20  (12 bits)  BIFF index — which archive file
        bits 19-14  ( 6 bits)  tileset index — for TIS resources only
        bits 13- 0  (14 bits)  file index — position within the archive
    """
    resref:   ResRef  # Resource name, e.g. ResRef("AR0602")
    res_type: int     # ResType code, e.g. ResType.ARE
    locator:  int     # Packed 32-bit location descriptor

    @property
    def biff_index(self) -> int:
        """Index into the KeyFile's BiffEntry list."""
        return (self.locator >> 20) & 0xFFF

    @property
    def tileset_index(self) -> int:
        """Tileset slot within the BIFF; non-zero only for TIS resources."""
        return (self.locator >> 14) & 0x3F

    @property
    def file_index(self) -> int:
        """File slot within the BIFF archive."""
        return self.locator & 0x3FFF

    @property
    def extension(self) -> str:
        return ResType.extension(self.res_type)

    @property
    def filename(self) -> str:
        """Reconstructed filename, e.g. ``AR0602.are``."""
        return f"{self.resref}.{self.extension}"

    def __repr__(self) -> str:
        return (
            f"<ResourceEntry {self.resref!r}.{self.extension} "
            f"biff={self.biff_index} idx={self.file_index}>"
        )


# ---------------------------------------------------------------------------
# KEY file
# ---------------------------------------------------------------------------

_KEY_SIG = b"KEY "
_KEY_VER = b"V1  "


class KeyFile:
    """
    Parses a CHITIN.KEY file and provides fast resource lookup.

    The KEY file is the entry point for reading any IE game resource.
    Open it once, then use :meth:`find` to locate resources and
    :meth:`read_resource` to extract their raw bytes from the archives.

    Usage::

        key = KeyFile.open("/path/to/game/CHITIN.KEY")

        entry = key.find("AR0602", ResType.ARE)
        if entry:
            raw = key.read_resource(entry, game_root="/path/to/game")  # or a GameInstallation

        # All dialogue files:
        for entry in key.find_all(ResType.DLG):
            print(entry.filename)
    """

    def __init__(
        self,
        biff_entries:     List[BiffEntry],
        resource_entries: List[ResourceEntry],
        source_path:      Optional[Path] = None,
    ) -> None:
        self._biff_entries     = biff_entries
        self._resource_entries = resource_entries
        self.source_path       = source_path

        # (resref_str, res_type_int) -> ResourceEntry  — O(1) lookup
        self._index: Dict[Tuple[str, int], ResourceEntry] = {
            (str(e.resref), e.res_type): e
            for e in resource_entries
        }

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path) -> "KeyFile":
        """Read and parse a CHITIN.KEY file from disk."""
        path = Path(path)
        data = path.read_bytes()
        return cls._parse(BinaryReader(data), source_path=path)

    @classmethod
    def from_bytes(cls, data: bytes) -> "KeyFile":
        """Parse a CHITIN.KEY from an in-memory buffer (useful for tests)."""
        return cls._parse(BinaryReader(data))

    @classmethod
    def _parse(cls, r: BinaryReader, source_path: Optional[Path] = None) -> "KeyFile":
        try:
            r.expect_signature(_KEY_SIG)
            r.expect_signature(_KEY_VER)
        except SignatureMismatch as exc:
            raise KeyFileError(str(exc)) from exc

        num_bif    = r.read_uint32()
        num_res    = r.read_uint32()
        bif_offset = r.read_uint32()
        res_offset = r.read_uint32()

        biff_entries     = cls._read_bif_entries(r, bif_offset, num_bif)
        resource_entries = cls._read_res_entries(r, res_offset, num_res)

        return cls(biff_entries, resource_entries, source_path=source_path)

    @staticmethod
    def _read_bif_entries(r: BinaryReader, offset: int, count: int) -> List[BiffEntry]:
        entries: List[BiffEntry] = []
        r.seek(offset)
        for i in range(count):
            file_length  = r.read_uint32()
            fname_offset = r.read_uint32()
            fname_len    = r.read_uint16()
            location     = r.read_uint16()

            filename = r.read_bytes_at(fname_offset, fname_len).rstrip(b"\x00").decode("latin-1")
            entries.append(BiffEntry(i, filename, file_length, location))
        return entries

    @staticmethod
    def _read_res_entries(r: BinaryReader, offset: int, count: int) -> List[ResourceEntry]:
        entries: List[ResourceEntry] = []
        r.seek(offset)
        for _ in range(count):
            resref_str = r.read_resref()   # 8 bytes, already uppercased by BinaryReader
            res_type   = r.read_uint16()
            locator    = r.read_uint32()
            entries.append(ResourceEntry(ResRef(resref_str), res_type, locator))
        return entries

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def find(self, resref: str | ResRef, res_type: int | ResType) -> Optional[ResourceEntry]:
        """
        Look up a resource by name and type.

        Returns the matching :class:`ResourceEntry`, or ``None`` if not found.

            entry = key.find("AR0602", ResType.ARE)
        """
        key = (str(ResRef(str(resref))), int(res_type))
        return self._index.get(key)

    def find_all(self, res_type: int | ResType) -> List[ResourceEntry]:
        """Return every resource of a given type, in KEY-file order."""
        t = int(res_type)
        return [e for e in self._resource_entries if e.res_type == t]

    def iter_resources(self) -> Iterator[ResourceEntry]:
        """Iterate over every resource entry in the KEY file."""
        return iter(self._resource_entries)

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------

    def biff_path(self, entry: ResourceEntry, game_root: GameRoot) -> Path:
        """
        Resolve the on-disk path for the BIFF archive that contains *entry*.

        KEY stores Windows-style relative paths (``data\\AR0602.bif``);
        this normalises separators for the current OS.
        """
        biff     = self._biff_entries[entry.biff_index]
        relative = Path(biff.filename.replace("\\", "/"))
        return _resolve_game_root(game_root) / relative

    def read_resource(self, entry: ResourceEntry, game_root: GameRoot) -> bytes:
        """
        Extract and return the raw bytes for *entry* from its BIFF archive.

        Opens the appropriate .bif file, reads the resource, and returns
        the bytes.  If you need to read many resources from the same archive,
        use :class:`BiffFile` directly to avoid repeated file opens.

            raw = key.read_resource(entry, game_root="/path/to/game")  # or a GameInstallation
        """
        biff_path = self.biff_path(entry, game_root)
        with BiffFile.open(biff_path) as biff:
            if entry.res_type == ResType.TIS:
                return biff.read_tileset_raw(entry.tileset_index)
            return biff.read(entry.file_index)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    @property
    def num_biff(self) -> int:
        return len(self._biff_entries)

    @property
    def num_resources(self) -> int:
        return len(self._resource_entries)

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return f"<KeyFile {src!r}: {self.num_biff} biffs, {self.num_resources} resources>"


# ---------------------------------------------------------------------------
# BIFF v1 archive
# ---------------------------------------------------------------------------

_BIFF_SIG = b"BIFF"
_BIFF_VER = b"V1  "


@dataclass(frozen=True)
class _FileEntry:
    locator:  int
    offset:   int
    size:     int
    res_type: int


@dataclass(frozen=True)
class _TileEntry:
    locator:   int
    offset:    int
    num_tiles: int
    tile_size: int
    res_type:  int


class BiffFile:
    """
    Reader for a single BIFF (BIF) v1 archive.

    Most callers should use :meth:`KeyFile.read_resource` rather than
    opening a BiffFile directly.  Use this class when you need to read
    multiple resources from the same archive efficiently, or want
    fine-grained access to individual tiles.

    BiffFile supports the context manager protocol::

        with BiffFile.open("/path/to/data/AR0602.bif") as biff:
            raw = biff.read(file_index=0)
    """

    def __init__(
        self,
        file_entries: List[_FileEntry],
        tile_entries: List[_TileEntry],
        data:         bytes,
        source_path:  Optional[Path] = None,
    ) -> None:
        self._file_entries = file_entries
        self._tile_entries = tile_entries
        self._data         = data
        self.source_path   = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path) -> "BiffFile":
        """Read and parse a BIFF archive from disk."""
        path = Path(path)
        data = path.read_bytes()
        return cls._parse(BinaryReader(data), data, source_path=path)

    @classmethod
    def from_bytes(cls, data: bytes) -> "BiffFile":
        """Parse a BIFF archive from an in-memory buffer (useful for tests)."""
        return cls._parse(BinaryReader(data), data)

    @classmethod
    def _parse(
        cls,
        r:           BinaryReader,
        raw:         bytes,
        source_path: Optional[Path] = None,
    ) -> "BiffFile":
        try:
            r.expect_signature(_BIFF_SIG)
            r.expect_signature(_BIFF_VER)
        except SignatureMismatch as exc:
            raise BiffError(str(exc)) from exc

        num_file    = r.read_uint32()
        num_tile    = r.read_uint32()
        file_offset = r.read_uint32()

        file_entries = cls._read_file_entries(r, file_offset, num_file)
        tile_entries = cls._read_tile_entries(r, num_tile)

        return cls(file_entries, tile_entries, raw, source_path=source_path)

    @staticmethod
    def _read_file_entries(r: BinaryReader, offset: int, count: int) -> List[_FileEntry]:
        entries: List[_FileEntry] = []
        r.seek(offset)
        for _ in range(count):
            locator  = r.read_uint32()
            off      = r.read_uint32()
            size     = r.read_uint32()
            res_type = r.read_uint16()
            r.skip(2)  # unknown / padding
            entries.append(_FileEntry(locator, off, size, res_type))
        return entries

    @staticmethod
    def _read_tile_entries(r: BinaryReader, count: int) -> List[_TileEntry]:
        entries: List[_TileEntry] = []
        for _ in range(count):
            locator   = r.read_uint32()
            offset    = r.read_uint32()
            num_tiles = r.read_uint32()
            tile_size = r.read_uint32()
            res_type  = r.read_uint16()
            r.skip(2)  # unknown / padding
            entries.append(_TileEntry(locator, offset, num_tiles, tile_size, res_type))
        return entries

    # ------------------------------------------------------------------
    # Data access — regular resources
    # ------------------------------------------------------------------

    def read(self, file_index: int) -> bytes:
        """
        Return the raw bytes for a regular (non-tileset) resource.

        *file_index* is ``ResourceEntry.file_index`` — the lower 14 bits
        of the KEY locator.
        """
        entry = self._file_entry_by_index(file_index)
        return self._data[entry.offset : entry.offset + entry.size]

    # ------------------------------------------------------------------
    # Data access — TIS tileset resources
    # ------------------------------------------------------------------

    def read_tile(self, tileset_index: int, tile_number: int) -> bytes:
        """
        Return the raw bytes for a single tile from a TIS tileset.

        *tileset_index* is ``ResourceEntry.tileset_index`` (bits 19-14
        of the KEY locator).  *tile_number* is zero-based.
        """
        entry = self._tile_entry_by_index(tileset_index)
        if tile_number >= entry.num_tiles:
            raise IndexError(
                f"Tile {tile_number} out of range "
                f"(tileset {tileset_index} has {entry.num_tiles} tiles)."
            )
        offset = entry.offset + tile_number * entry.tile_size
        return self._data[offset : offset + entry.tile_size]

    def read_all_tiles(self, tileset_index: int) -> List[bytes]:
        """Return every tile in a tileset as a list of raw byte blobs."""
        entry = self._tile_entry_by_index(tileset_index)
        tiles: List[bytes] = []
        for i in range(entry.num_tiles):
            offset = entry.offset + i * entry.tile_size
            tiles.append(self._data[offset : offset + entry.tile_size])
        return tiles

    def read_tileset_raw(self, tileset_index: int) -> bytes:
        """
        Return the entire tileset as a single contiguous bytes object.

        Used by :meth:`KeyFile.read_resource` for TIS entries so that
        all resource types return a single blob consistently.
        """
        entry = self._tile_entry_by_index(tileset_index)
        total = entry.num_tiles * entry.tile_size
        return self._data[entry.offset : entry.offset + total]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _file_entry_by_index(self, file_index: int) -> _FileEntry:
        # Entries are almost always stored in order; try direct lookup first.
        if file_index < len(self._file_entries):
            e = self._file_entries[file_index]
            if (e.locator & 0x3FFF) == file_index:
                return e
        for e in self._file_entries:
            if (e.locator & 0x3FFF) == file_index:
                return e
        raise BiffError(f"No file entry with index {file_index} in {self!r}.")

    def _tile_entry_by_index(self, tileset_index: int) -> _TileEntry:
        if tileset_index < len(self._tile_entries):
            e = self._tile_entries[tileset_index]
            if ((e.locator >> 14) & 0x3F) == tileset_index:
                return e
        for e in self._tile_entries:
            if ((e.locator >> 14) & 0x3F) == tileset_index:
                return e
        raise BiffError(f"No tileset entry with index {tileset_index} in {self!r}.")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "BiffFile":
        return self

    def __exit__(self, *_) -> None:
        pass  # Data is held in memory; nothing to release.

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    @property
    def num_files(self) -> int:
        return len(self._file_entries)

    @property
    def num_tilesets(self) -> int:
        return len(self._tile_entries)

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<BiffFile {src!r}: "
            f"{self.num_files} files, {self.num_tilesets} tilesets>"
        )


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------

def extract_resources(
    key:        KeyFile,
    res_type:   int | ResType,
    game_root:  str | Path,
    output_dir: str | Path,
    *,
    overwrite:  bool = False,
) -> List[Path]:
    """
    Extract every resource of *res_type* from the game archives to *output_dir*.

    Creates *output_dir* if it does not exist.  Skips files that already exist
    unless *overwrite* is ``True``.  Returns the list of written (or skipped) paths.

        written = extract_resources(key, ResType.DLG, "/game", "/out/dlg")
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for entry in key.find_all(res_type):
        dest = output_dir / entry.filename
        if dest.exists() and not overwrite:
            written.append(dest)
            continue
        raw = key.read_resource(entry, game_root)
        dest.write_bytes(raw)
        written.append(dest)

    return written