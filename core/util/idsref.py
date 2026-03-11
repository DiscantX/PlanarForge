"""
core/util/idsref.py

The IdsRef type — a reference to an IDS table value.

An IdsRef pairs a raw integer (as stored in a binary resource) with the
name of the IDS file it should be resolved against.  Resolution is always
external: the caller supplies the IdsTable to look up the value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from core.formats.ids import IdsTable


_MAX_VALUE = 0xFFFFFFFF


class IdsRef:
    """
    Wrap a raw integer with the IDS file name it resolves against.

    ids_name is the IDS basename: uppercase, no extension, max 8 chars.
    """

    __slots__ = ("_value", "_ids_name")

    def __init__(self, value: int, ids_name: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"IdsRef value must be int, got {type(value).__name__!r}.")
        if value < 0 or value > _MAX_VALUE:
            raise ValueError(f"IdsRef value {value} is out of range (0-{_MAX_VALUE:#010x}).")

        ids_name = ids_name.strip()
        if ids_name:
            if "." in ids_name:
                raise ValueError("IdsRef ids_name must be a basename without extension.")
            ids_name = ids_name.upper()
            if len(ids_name) > 8:
                raise ValueError("IdsRef ids_name must be at most 8 characters.")
            for ch in ids_name:
                if not ("A" <= ch <= "Z" or "0" <= ch <= "9" or ch == "_"):
                    raise ValueError(
                        "IdsRef ids_name must contain only A-Z, 0-9, and '_' characters."
                    )

        self._value = value
        self._ids_name = ids_name

    # ------------------------------------------------------------------
    # Sentinel
    # ------------------------------------------------------------------

    @classmethod
    @property
    def NONE(cls) -> "IdsRef":
        """The canonical 'no value' sentinel (value=0, ids_name="")."""
        return cls(0, "")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def value(self) -> int:
        return self._value

    @property
    def ids_name(self) -> str:
        return self._ids_name

    # ------------------------------------------------------------------
    # Resolution / JSON
    # ------------------------------------------------------------------

    def resolve(self, table: "IdsTable") -> str:
        """Return the symbolic name for this value, or UNKNOWN(N)."""
        return table.resolve(self._value)

    def to_json(self) -> dict:
        return {"value": self._value, "ids": self._ids_name}

    @classmethod
    def from_json(cls, d: dict) -> "IdsRef":
        if not isinstance(d, dict):
            raise ValueError("IdsRef.from_json expects a dict.")
        if "value" not in d or "ids" not in d:
            raise ValueError("IdsRef JSON must contain 'value' and 'ids' keys.")
        return cls(int(d["value"]), str(d["ids"]))

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __int__(self) -> int:
        return self._value

    def __repr__(self) -> str:
        return f"IdsRef(value={self._value}, ids_name={self._ids_name!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IdsRef):
            return False
        return self._value == other._value and self._ids_name == other._ids_name
