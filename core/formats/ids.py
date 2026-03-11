"""
core/formats/ids.py

Parser for Infinity Engine IDS (symbol table) files.

IDS files map integer values to symbolic names (e.g. RACE.IDS).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IdsTable:
    """
    Resolved lookup table for one IDS file.

    name is the IDS basename (uppercase, no extension).
    """
    name: str
    entries: Dict[int, str]

    def resolve(self, value: int) -> str:
        return self.entries.get(value, f"UNKNOWN({value})")

    def to_json(self) -> dict:
        # JSON keys must be strings; preserve numeric values in the key.
        return {
            "name": self.name,
            "entries": {str(k): v for k, v in self.entries.items()},
        }

    @classmethod
    def from_json(cls, d: dict) -> "IdsTable":
        if not isinstance(d, dict):
            raise ValueError("IdsTable.from_json expects a dict.")
        name = str(d.get("name", ""))
        raw_entries = d.get("entries", {})
        if not isinstance(raw_entries, dict):
            raise ValueError("IdsTable 'entries' must be a dict.")
        entries: Dict[int, str] = {}
        for k, v in raw_entries.items():
            entries[int(k, 0)] = str(v)
        return cls(_normalize_name(name), entries)


# ---------------------------------------------------------------------------
# IDS parser
# ---------------------------------------------------------------------------

class IdsFile:
    """Parser for IDS text/encrypted files."""

    @classmethod
    def from_bytes(cls, data: bytes, name: str | None = None) -> IdsTable:
        text = _decode_ids(data)
        entries = _parse_ids_text(text)
        if name is None:
            name = ""
        return IdsTable(_normalize_name(name), entries)

    @classmethod
    def from_file(cls, path: str | Path) -> IdsTable:
        path = Path(path)
        data = path.read_bytes()
        return cls.from_bytes(data, name=path.stem)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    if "." in name:
        name = name.split(".", 1)[0]
    return name.upper()


def _decode_ids(data: bytes) -> str:
    # IDS files may be XOR-encoded; detect by header.
    if _looks_like_ids(data):
        return data.decode("latin-1", errors="replace")
    decoded = bytes(b ^ 0xFF for b in data)
    if _looks_like_ids(decoded):
        return decoded.decode("latin-1", errors="replace")
    # Fall back to raw decode if header is missing.
    return data.decode("latin-1", errors="replace")


def _looks_like_ids(data: bytes) -> bool:
    if len(data) < 3:
        return False
    return data.startswith(b"IDS") or data.startswith(b"IDS ") or data.startswith(b"IDS V")


def _parse_ids_text(text: str) -> Dict[int, str]:
    lines = text.splitlines()

    # Consume header lines if present (IDS / IDS V1.0 and optional count).
    idx = 0
    if idx < len(lines) and lines[idx].strip().upper().startswith("IDS"):
        idx += 1
    if idx < len(lines) and lines[idx].strip().isdigit():
        idx += 1

    entries: Dict[int, str] = {}
    for line in lines[idx:]:
        stripped = _strip_comments(line).strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            value = int(parts[0], 0)
        except ValueError:
            continue
        name = parts[1]
        if value not in entries:
            entries[value] = name
    return entries


def _strip_comments(line: str) -> str:
    for marker in ("//", "#", ";"):
        if marker in line:
            line = line.split(marker, 1)[0]
    return line
