"""
core/formats/tlk.py

Parser and writer for the Infinity Engine TLK (Talk Table) format.

The TLK file (always named dialog.tlk, and dialogf.tlk for the female
version in BG2) is the central string database for an IE game. Every
piece of human-readable text in the game - item names, descriptions,
dialog lines, journal entries - is stored here and referenced elsewhere
by a uint32 index called a StrRef.

IESDP Reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/tlk_v1.htm

File layout (V1, the only version):
    0x0000  char[4]     Signature        "TLK "
    0x0004  char[4]     Version          "V1  "
    0x0008  uint16      Language ID      (0 = English)
    0x000A  uint32      Entry count      number of string entries
    0x000E  uint32      Strings offset   byte offset to string data block

    Immediately following the header: entry_count x 26-byte Entry structs.
    At strings_offset: raw string bytes, referenced by entry offsets/lengths.

Entry struct (26 bytes each):
    0x00  uint16   Flags
    0x02  char[8]  Sound ResRef   (associated voice line, may be empty)
    0x0A  uint32   Volume variance  (unused in most games)
    0x0E  uint32   Pitch variance   (unused in most games)
    0x12  uint32   String offset    (relative to strings_offset in header)
    0x16  uint32   String length    (byte length; 0 = no string, use sound only)

Entry flags:
    0x00  No text or sound
    0x01  Has text
    0x02  Has sound
    0x04  Has sound (with pitch/volume data, older format)
    0x08  Has tags (token substitution e.g. <CHARNAME>)

Usage:
    from core.formats.tlk import TlkFile

    # Read
    tlk = TlkFile.from_file("dialog.tlk")
    print(tlk.get(42))          # "You must gather your party..."
    print(tlk.get(0xFFFFFFFF))  # "" (standard invalid strref sentinel)

    # Edit
    tlk.set_text(42, "You must gather your party before venturing forth.")

    # Add new entry (returns new strref index)
    new_ref = tlk.add("A brand new string for your mod.")

    # Write
    tlk.to_file("dialog.tlk")

    # JSON round-trip (for mod project storage)
    import json
    json.dump(tlk.to_json(), open("dialog.json", "w"), indent=2)
    tlk2 = TlkFile.from_json(json.load(open("dialog.json")))
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from core.util.binary import BinaryReader, BinaryWriter
from core.util.resref import ResRef


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE = b"TLK "
VERSION   = b"V1  "
HEADER_SIZE = 18        # bytes
ENTRY_SIZE  = 26        # bytes
STRREF_INVALID = 0xFFFFFFFF   # conventional "no string" sentinel

# Entry flag bits
FLAG_NONE       = 0x00
FLAG_HAS_TEXT   = 0x01
FLAG_HAS_SOUND  = 0x02
FLAG_HAS_TAGS   = 0x08


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TlkEntry:
    """
    A single string entry in the TLK table.

    Attributes:
        text:       The human-readable string. May be empty if the entry
                    only has an associated sound (flags & FLAG_HAS_SOUND).
        sound:      ResRef of the associated .WAV voice file. Empty string
                    means no sound.
        flags:      Raw flag bitfield from the file. Usually computed
                    automatically on write; you rarely need to set this
                    directly.
        volume_var: Volume variance (stored but ignored by most games).
        pitch_var:  Pitch variance (stored but ignored by most games).
    """
    text:       str = ""
    sound:      str = ""        # ResRef, 8 chars max
    flags:      int = FLAG_NONE
    volume_var: int = 0
    pitch_var:  int = 0

    def compute_flags(self) -> int:
        """Derive the correct flags value from the entry content."""
        f = FLAG_NONE
        if self.text:
            f |= FLAG_HAS_TEXT
        if self.sound:
            f |= FLAG_HAS_SOUND
        return f

    def to_json(self) -> dict:
        d = {"text": self.text}
        if self.sound:
            d["sound"] = self.sound
        if self.flags not in (FLAG_NONE, self.compute_flags()):
            d["flags"] = self.flags   # only persist non-standard flags
        if self.volume_var:
            d["volume_var"] = self.volume_var
        if self.pitch_var:
            d["pitch_var"] = self.pitch_var
        return d

    @classmethod
    def from_json(cls, d: dict) -> "TlkEntry":
        return cls(
            text       = d.get("text", ""),
            sound      = d.get("sound", ""),
            flags      = d.get("flags", FLAG_NONE),
            volume_var = d.get("volume_var", 0),
            pitch_var  = d.get("pitch_var", 0),
        )


# ---------------------------------------------------------------------------
# Main TLK file class
# ---------------------------------------------------------------------------

class TlkFile:
    """
    Represents a complete TLK string table.

    Entries are stored as a list; the list index is the StrRef value.
    Index 0 is always present in a valid TLK (it is the "invalid" entry
    in most games, containing an empty string).
    """

    def __init__(self, language_id: int = 0):
        self.language_id: int = language_id
        self._entries: list[TlkEntry] = []

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "TlkFile":
        """Parse a TLK file from raw bytes."""
        r = BinaryReader(data)

        # Header
        r.expect_signature(SIGNATURE)
        r.expect_signature(VERSION)
        language_id    = r.read_uint16()
        entry_count    = r.read_uint32()
        strings_offset = r.read_uint32()

        tlk = cls(language_id=language_id)

        # Read entry structs
        raw_entries = []
        for _ in range(entry_count):
            flags       = r.read_uint16()
            sound       = r.read_resref()
            volume_var  = r.read_uint32()
            pitch_var   = r.read_uint32()
            str_offset  = r.read_uint32()
            str_length  = r.read_uint32()
            raw_entries.append((flags, sound, volume_var, pitch_var, str_offset, str_length))

        # Read string data using offsets from the entry structs
        for flags, sound, volume_var, pitch_var, str_offset, str_length in raw_entries:
            if str_length > 0:
                raw_str = r.read_bytes_at(strings_offset + str_offset, str_length)
                text = raw_str.decode("latin-1", errors="replace")
            else:
                text = ""

            tlk._entries.append(TlkEntry(
                text       = text,
                sound      = sound,
                flags      = flags,
                volume_var = volume_var,
                pitch_var  = pitch_var,
            ))

        return tlk

    @classmethod
    def from_file(cls, path: str | Path) -> "TlkFile":
        """Read and parse a TLK file from disk."""
        data = Path(path).read_bytes()
        return cls.from_bytes(data)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise the TLK back to its binary representation."""
        w_header = BinaryWriter()
        w_entries = BinaryWriter()
        w_strings = BinaryWriter()

        # Build string block and entry structs in a single pass
        for entry in self._entries:
            encoded = entry.text.encode("latin-1", errors="replace") if entry.text else b""
            str_offset = w_strings.pos
            str_length = len(encoded)
            if encoded:
                w_strings.write_bytes(encoded)

            flags = entry.compute_flags()
            w_entries.write_uint16(flags)
            w_entries.write_resref(entry.sound)
            w_entries.write_uint32(entry.volume_var)
            w_entries.write_uint32(entry.pitch_var)
            w_entries.write_uint32(str_offset)
            w_entries.write_uint32(str_length)

        # Header
        entry_count    = len(self._entries)
        strings_offset = HEADER_SIZE + (entry_count * ENTRY_SIZE)

        w_header.write_bytes(SIGNATURE)
        w_header.write_bytes(VERSION)
        w_header.write_uint16(self.language_id)
        w_header.write_uint32(entry_count)
        w_header.write_uint32(strings_offset)

        return w_header.to_bytes() + w_entries.to_bytes() + w_strings.to_bytes()

    def to_file(self, path: str | Path) -> None:
        """Write the TLK to disk."""
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, strref: int) -> str:
        """
        Return the text for a StrRef index.

        Returns an empty string for the standard invalid sentinel
        (0xFFFFFFFF) and for out-of-range indices, matching game behaviour.
        """
        if strref == STRREF_INVALID or strref < 0 or strref >= len(self._entries):
            return ""
        return self._entries[strref].text

    def get_entry(self, strref: int) -> Optional[TlkEntry]:
        """Return the full TlkEntry for a StrRef, or None if out of range."""
        if strref == STRREF_INVALID or strref < 0 or strref >= len(self._entries):
            return None
        return self._entries[strref]

    def get_sound(self, strref: int) -> str:
        """Return the sound ResRef for a StrRef, or empty string."""
        entry = self.get_entry(strref)
        return entry.sound if entry else ""

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, strref: int) -> bool:
        return 0 <= strref < len(self._entries)

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------

    def set_text(self, strref: int, text: str) -> None:
        """Update the text of an existing entry."""
        if strref < 0 or strref >= len(self._entries):
            raise IndexError(f"StrRef {strref} is out of range (table has {len(self._entries)} entries)")
        self._entries[strref].text = text

    def set_sound(self, strref: int, sound_resref: str) -> None:
        """Update the sound ResRef of an existing entry."""
        if strref < 0 or strref >= len(self._entries):
            raise IndexError(f"StrRef {strref} is out of range")
        self._entries[strref].sound = sound_resref.upper()[:8]

    def add(self, text: str, sound: str = "") -> int:
        """
        Append a new string entry and return its StrRef index.

        This is how mods add new strings - append to the end of the table.
        The returned index is what you store in item/creature/dialog fields.
        """
        entry = TlkEntry(text=text, sound=sound.upper()[:8])
        self._entries.append(entry)
        return len(self._entries) - 1

    # ------------------------------------------------------------------
    # JSON round-trip (mod project format)
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """
        Serialise to a JSON-compatible dict.

        The format stores entries as a list; the list index is the StrRef.
        Entries with no text and no sound are stored as null to keep the
        file compact while preserving index alignment.
        """
        entries = []
        for e in self._entries:
            if not e.text and not e.sound:
                entries.append(None)
            else:
                entries.append(e.to_json())

        return {
            "format":      "tlk",
            "version":     "V1",
            "language_id": self.language_id,
            "entries":     entries,
        }

    @classmethod
    def from_json(cls, d: dict) -> "TlkFile":
        """Deserialise from a JSON-compatible dict."""
        tlk = cls(language_id=d.get("language_id", 0))
        for entry_data in d.get("entries", []):
            if entry_data is None:
                tlk._entries.append(TlkEntry())
            else:
                tlk._entries.append(TlkEntry.from_json(entry_data))
        return tlk

    @classmethod
    def from_json_file(cls, path: str | Path) -> "TlkFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def search(self, query: str, case_sensitive: bool = False) -> list[tuple[int, str]]:
        """
        Search all entries for a substring.

        Returns a list of (strref, text) tuples for all matching entries.
        Useful for the editor's string browser.
        """
        if not case_sensitive:
            query = query.lower()
        results = []
        for i, entry in enumerate(self._entries):
            text = entry.text if case_sensitive else entry.text.lower()
            if query in text:
                results.append((i, entry.text))
        return results

    def __repr__(self) -> str:
        return f"TlkFile(entries={len(self._entries)}, language_id={self.language_id})"
