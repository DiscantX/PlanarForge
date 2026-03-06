"""
core/util/strref.py

The StrRef type — a TLK string table reference.

A StrRef is a uint32 stored in IE binary files.  Its bits encode two things:

    Bits 31-24  (top 8)   — file ID: which TLK file to look in
    Bits 23-0   (low 24)  — tlk_index: the row within that file

    File IDs:
        0x00  dialog.tlk   — male protagonist / default
        0x01  dialogf.tlk  — female protagonist
        All other values are reserved / unused in practice.

The sentinel value 0xFFFFFFFF means "no string" — the field is absent or
unused.  StrRef.NONE is the canonical way to express this.

Source: IESDP Notes and Conventions
    "strref — A reference into the 'TLK' resource. Stored as a 32-bit
    number (though the top 8 bits refer to an internal file Id, e.g.
    0x01 refers to dialogf.tlk)."

A StrRef does NOT hold a reference to any TLK file.  Resolution is always
explicit and external — the caller supplies the appropriate TLK(s).  The
primary resolution path in the editor goes through string_manager, which
knows which language and gender variant are active.  The resolve() method
is provided as a low-level convenience for when you have TLK files directly
to hand.

Examples::

    from core.util.strref import StrRef

    ref = StrRef(12345)
    print(ref)              # "12345"   (raw uint32 as decimal)
    print(ref.tlk_index)    # 12345     (low 24 bits — actual row in TLK)
    print(ref.file_id)      # 0         (0 = dialog.tlk)
    print(ref.is_female)    # False
    print(ref.is_none)      # False

    female_ref = StrRef(0x01002345)
    print(female_ref.is_female)   # True
    print(female_ref.tlk_index)   # 0x2345

    none = StrRef.NONE
    print(none.is_none)     # True

    # Low-level resolution with explicit TLK files:
    text = ref.resolve(male_tlk)
    text = ref.resolve(male_tlk, female_tlk)   # picks dialogf.tlk if is_female

    # Preferred path in the editor:
    text = string_manager.resolve(ref)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    # Imported only for type hints; strref.py has no runtime project imports.
    from core.formats.tlk import TlkFile


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NONE_VALUE:     int = 0xFFFFFFFF
_MAX_VALUE:      int = 0xFFFFFFFF   # uint32 ceiling

_FILE_ID_MASK:   int = 0xFF000000
_TLK_INDEX_MASK: int = 0x00FFFFFF
_FILE_ID_SHIFT:  int = 24

FILE_ID_MALE:   int = 0x00   # dialog.tlk  — male protagonist / default
FILE_ID_FEMALE: int = 0x01   # dialogf.tlk — female protagonist


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class StrRefError(ValueError):
    """Raised when a StrRef value is out of range or malformed."""


# ---------------------------------------------------------------------------
# StrRef
# ---------------------------------------------------------------------------

class StrRef:
    """
    A validated Infinity Engine TLK string reference.

    Wraps a raw uint32 as stored on disk.  The top 8 bits encode which TLK
    file to consult (0 = dialog.tlk, 1 = dialogf.tlk); the low 24 bits are
    the row index within that file.

    The sentinel 0xFFFFFFFF (StrRef.NONE) means "no string assigned".

    StrRef is decoupled from any TLK file — it is a stable, language-agnostic
    identifier.  Use resolve() for direct TLK access, or string_manager in
    the editor for automatic language and gender handling.
    """

    __slots__ = ("_raw",)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, value: int | str) -> None:
        """
        Construct a StrRef from a raw uint32 or a decimal string.

        The value is the full 32-bit integer as stored on disk — file ID
        bits included.  Use from_parts() to construct from a (file_id, index)
        pair explicitly.

        Raises StrRefError if the value is outside the uint32 range.
        """
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError:
                raise StrRefError(
                    f"StrRef value {value!r} cannot be interpreted as an integer."
                )
        if not isinstance(value, int) or isinstance(value, bool):
            raise StrRefError(
                f"StrRef requires an int or digit string, got {type(value).__name__!r}."
            )
        if value < 0 or value > _MAX_VALUE:
            raise StrRefError(
                f"StrRef value {value} is out of range (0-{_MAX_VALUE:#010x})."
            )
        self._raw = value

    @classmethod
    def from_parts(cls, file_id: int, tlk_index: int) -> "StrRef":
        """
        Construct from an explicit file ID and TLK row index.

            ref = StrRef.from_parts(FILE_ID_FEMALE, 0x2345)
            # equivalent to StrRef(0x01002345)
        """
        if file_id < 0 or file_id > 0xFF:
            raise StrRefError(f"file_id {file_id} is out of range (0-255).")
        if tlk_index < 0 or tlk_index > _TLK_INDEX_MASK:
            raise StrRefError(
                f"tlk_index {tlk_index} is out of range (0-{_TLK_INDEX_MASK:#08x})."
            )
        return cls((file_id << _FILE_ID_SHIFT) | tlk_index)

    # ------------------------------------------------------------------
    # Sentinel
    # ------------------------------------------------------------------

    @classmethod
    @property
    def NONE(cls) -> "StrRef":
        """The canonical 'no string' sentinel (0xFFFFFFFF)."""
        return cls(_NONE_VALUE)

    # ------------------------------------------------------------------
    # Properties — raw value
    # ------------------------------------------------------------------

    @property
    def raw(self) -> int:
        """The full raw uint32 as stored on disk (file ID bits + index)."""
        return self._raw

    @property
    def is_none(self) -> bool:
        """True if this is the 'no string' sentinel (0xFFFFFFFF)."""
        return self._raw == _NONE_VALUE

    # ------------------------------------------------------------------
    # Properties — decoded
    # ------------------------------------------------------------------

    @property
    def file_id(self) -> int:
        """
        The TLK file selector encoded in the top 8 bits.

            0 = dialog.tlk   (male / default)
            1 = dialogf.tlk  (female protagonist)
        """
        return (self._raw & _FILE_ID_MASK) >> _FILE_ID_SHIFT

    @property
    def tlk_index(self) -> int:
        """
        The row index within the TLK file (low 24 bits).

        This is the value to pass to tlk.get().
        """
        return self._raw & _TLK_INDEX_MASK

    @property
    def is_female(self) -> bool:
        """True if this strref points into dialogf.tlk (file_id == 1)."""
        return self.file_id == FILE_ID_FEMALE

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(
        self,
        male_tlk:   "TlkFile",
        female_tlk: "Optional[TlkFile]" = None,
    ) -> str:
        """
        Look up the string in the appropriate TLK file.

        Selects dialogf.tlk when is_female is True and female_tlk is
        provided; falls back to male_tlk otherwise.  Returns an empty
        string for the NONE sentinel.

        In the editor, prefer string_manager.resolve(ref) which manages
        language and gender context automatically.
        """
        if self.is_none:
            return ""
        tlk = (female_tlk
               if (self.is_female and female_tlk is not None)
               else male_tlk)
        return tlk.get(self.tlk_index)

    def resolve_with(self, resolver: Callable[[int, int], str]) -> str:
        """
        Resolve using a callable (file_id, tlk_index) -> str.

        This is the interface string_manager implements — it receives both
        the file ID and the index so it can select the appropriate TLK.

        Returns an empty string for the NONE sentinel.
        """
        if self.is_none:
            return ""
        return resolver(self.file_id, self.tlk_index)

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        """Return the raw uint32 as a decimal string — e.g. '12345'."""
        return str(self._raw)

    def __repr__(self) -> str:
        if self.is_none:
            return "StrRef.NONE"
        if self.file_id == 0:
            return f"StrRef({self._raw})"
        return f"StrRef(file_id={self.file_id}, tlk_index={self.tlk_index:#x})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StrRef):
            return self._raw == other._raw
        if isinstance(other, int):
            return self._raw == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._raw)

    def __bool__(self) -> bool:
        """False if this is the NONE sentinel, True otherwise."""
        return not self.is_none

    def __int__(self) -> int:
        """Return the raw uint32 — used when writing back to binary."""
        return self._raw

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> int:
        """
        Serialise to a plain integer for JSON storage.

        The full raw uint32 is stored (file ID bits included) so the
        round-trip is exact and the value is unambiguously a TLK reference.
        """
        return self._raw

    @classmethod
    def from_json(cls, value: int | str) -> "StrRef":
        """Deserialise from a JSON value (int or decimal string)."""
        return cls(value)
