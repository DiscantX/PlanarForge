"""
core/util/resref.py

The ResRef type - the Infinity Engine's universal resource name.

A ResRef is a string of up to 8 characters identifying a game resource.
It has no file extension (the type is implied by context or stored
separately as a uint16 resource type code). It is always stored
uppercased and null-padded to exactly 8 bytes on disk.

Examples:
    "AR0602"    - an area file (AR0602.ARE)
    "GORION"    - a creature (GORION.CRE)
    "MISC75"    - an item (MISC75.ITM)

Usage:
    from core.util.resref import ResRef

    r = ResRef("ar0602")
    print(r)          # AR0602
    print(r.is_empty) # False

    empty = ResRef("")
    print(empty.is_empty)  # True
"""

import re

_VALID_PATTERN = re.compile(r'^[A-Z0-9_\-]{0,8}$')

MAX_LENGTH = 8


class ResRefError(ValueError):
    """Raised when a ResRef string is invalid."""


class ResRef:
    """
    A validated, normalised Infinity Engine resource reference.

    ResRefs are case-insensitive on disk (always stored uppercase).
    This class normalises on construction so comparisons are reliable.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str):
        normalised = value.strip().upper()
        if len(normalised) > MAX_LENGTH:
            raise ResRefError(
                f"ResRef '{value}' is {len(normalised)} characters; maximum is {MAX_LENGTH}"
            )
        if normalised and not _VALID_PATTERN.match(normalised):
            raise ResRefError(
                f"ResRef '{value}' contains invalid characters. "
                f"Allowed: A-Z, 0-9, underscore, hyphen"
            )
        self._value = normalised

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def value(self) -> str:
        return self._value

    @property
    def is_empty(self) -> bool:
        """True if this ResRef is blank (references nothing)."""
        return self._value == ""

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __str__(self)  -> str:  return self._value
    def __repr__(self) -> str:  return f"ResRef({self._value!r})"
    def __eq__(self, other) -> bool:
        if isinstance(other, ResRef):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other.strip().upper()
        return NotImplemented
    def __hash__(self) -> int:  return hash(self._value)
    def __bool__(self) -> bool: return not self.is_empty

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialise to a plain string for JSON storage."""
        return self._value

    @classmethod
    def from_json(cls, value: str) -> "ResRef":
        return cls(value)
