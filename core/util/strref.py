"""
core/util/strref.py

The StrRef type — a TLK string table reference.

A StrRef is a uint32 index into a .tlk string table.  It is the
computer-readable, language-agnostic identity of a piece of in-game text.
The same StrRef resolves to different human-readable strings depending on
which language's TLK file is consulted, and potentially different strings
for male vs female characters.

A StrRef does NOT hold a reference to any TLK file.  Resolution is always
explicit and external — the caller supplies the appropriate TLK.  The
primary resolution path in the editor goes through string_manager, which
knows which language and gender variant are active.  The resolve() method
is provided as a low-level escape hatch for when you have a specific TLK
directly to hand.

The sentinel value 0xFFFFFFFF means "no string" — the field is absent or
unused.  StrRef.NONE is the canonical way to express this.

Examples::

    from core.util.strref import StrRef

    ref = StrRef(12345)
    print(ref)             # "12345"
    print(ref.index)       # 12345
    print(ref.is_none)     # False

    none = StrRef.NONE
    print(none.is_none)    # True

    # Resolution requires a TLK — StrRef does not resolve itself
    text = ref.resolve(tlk)          # "Leather Armour"
    text = string_manager.resolve(ref)  # preferred path in the editor
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    # Imported only for type hints so that strref.py stays dependency-free
    # at runtime.  TlkFile lives in core/formats/tlk.py.
    from core.formats.tlk import TlkFile


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NONE_VALUE: int = 0xFFFFFFFF
_MAX_VALUE:  int = 0xFFFFFFFF   # uint32 ceiling


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class StrRefError(ValueError):
    """Raised when a StrRef value is out of range."""


# ---------------------------------------------------------------------------
# StrRef
# ---------------------------------------------------------------------------

class StrRef:
    """
    A validated TLK string table reference.

    Wraps a uint32 index.  The sentinel value 0xFFFFFFFF (StrRef.NONE)
    means "no string assigned".  All other values are potentially valid
    indices into a TLK file.

    StrRef is intentionally decoupled from any TLK file.  It is a stable,
    language-agnostic identifier.  Use resolve() to obtain the human-readable
    text for a specific TLK, or string_manager.resolve() for the editor's
    active language context.
    """

    __slots__ = ("_index",)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, value: int | str) -> None:
        """
        Construct a StrRef from an integer index or a string digit.

        Accepts an int directly, or a str containing a decimal integer
        (for convenience when reading from JSON or user input).

        Raises StrRefError if the value is out of the uint32 range or
        cannot be interpreted as an integer.
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
                f"StrRef value {value} is out of range (0–{_MAX_VALUE})."
            )
        self._index = value

    # ------------------------------------------------------------------
    # Sentinel
    # ------------------------------------------------------------------

    @classmethod
    @property
    def NONE(cls) -> "StrRef":
        """The canonical 'no string' sentinel (0xFFFFFFFF)."""
        return cls(_NONE_VALUE)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def index(self) -> int:
        """The raw uint32 TLK index."""
        return self._index

    @property
    def is_none(self) -> bool:
        """True if this StrRef is the 'no string' sentinel (0xFFFFFFFF)."""
        return self._index == _NONE_VALUE

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, tlk: "TlkFile") -> str:
        """
        Look up and return the string this StrRef points to in *tlk*.

        This is a low-level escape hatch for when you have a specific TLK
        directly to hand.  In the editor, prefer string_manager.resolve(ref)
        which handles language and gender selection automatically.

        Returns an empty string if this StrRef is the NONE sentinel.
        Delegates to tlk.get() — see TlkFile for behaviour on missing indices.
        """
        if self.is_none:
            return ""
        return tlk.get(self._index)

    def resolve_with(self, resolver: Callable[[int], str]) -> str:
        """
        Resolve using a callable that accepts a TLK index and returns a string.

        Useful when the resolution context is not a TlkFile directly — for
        example, a lambda wrapping string_manager, or a test stub.

        Returns an empty string if this StrRef is the NONE sentinel.
        """
        if self.is_none:
            return ""
        return resolver(self._index)

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        """Return the raw index as a decimal string — e.g. '12345'."""
        return str(self._index)

    def __repr__(self) -> str:
        return f"StrRef({self._index})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, StrRef):
            return self._index == other._index
        if isinstance(other, int):
            return self._index == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._index)

    def __bool__(self) -> bool:
        """False if this is the NONE sentinel, True otherwise."""
        return not self.is_none

    def __int__(self) -> int:
        """Allow int(strref) to return the raw index."""
        return self._index

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> int:
        """
        Serialise to a plain integer for JSON storage.

        Stored as int rather than string so it is unambiguously a TLK
        index in the JSON output and round-trips without parsing.
        """
        return self._index

    @classmethod
    def from_json(cls, value: int | str) -> "StrRef":
        """
        Deserialise from a JSON value.

        Accepts both int and string representations for robustness.
        """
        return cls(value)
