"""
tests/formats/test_tlk.py

Unit tests for the TLK parser.

These tests construct synthetic TLK binary data to verify parsing
correctness without requiring actual copyrighted game files.
The round-trip tests (binary -> model -> binary) are the most
important: they confirm the writer produces byte-identical output
to what was read.
"""

import struct
import sys
import unittest
from pathlib import Path

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.formats.tlk import (
    TlkFile, TlkEntry,
    SIGNATURE, VERSION, HEADER_SIZE, ENTRY_SIZE,
    FLAG_HAS_TEXT, FLAG_HAS_SOUND, STRREF_INVALID,
)
from core.util.binary import BinaryWriter, SignatureMismatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_tlk_bytes(entries: list[dict], language_id: int = 0) -> bytes:
    """
    Build a minimal but valid TLK binary for testing.

    Each entry dict may have keys: text (str), sound (str), flags (int).
    """
    entry_count    = len(entries)
    strings_offset = HEADER_SIZE + (entry_count * ENTRY_SIZE)

    # Build string block
    string_parts  = []
    string_offset = 0
    entry_structs = []

    for e in entries:
        text    = e.get("text", "")
        sound   = e.get("sound", "").upper().ljust(8, "\x00")[:8]
        flags   = e.get("flags", 0)
        encoded = text.encode("latin-1") if text else b""

        entry_structs.append((flags, sound, string_offset, len(encoded)))
        string_parts.append(encoded)
        string_offset += len(encoded)

    # Header
    w = BinaryWriter()
    w.write_bytes(SIGNATURE)
    w.write_bytes(VERSION)
    w.write_uint16(language_id)
    w.write_uint32(entry_count)
    w.write_uint32(strings_offset)

    # Entry structs
    for flags, sound, str_off, str_len in entry_structs:
        w.write_uint16(flags)
        w.write_bytes(sound.encode("latin-1").ljust(8, b"\x00")[:8])
        w.write_uint32(0)   # volume_var
        w.write_uint32(0)   # pitch_var
        w.write_uint32(str_off)
        w.write_uint32(str_len)

    # String block
    for part in string_parts:
        w.write_bytes(part)

    return w.to_bytes()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTlkParsing(unittest.TestCase):

    def test_parse_empty_table(self):
        data = build_tlk_bytes([])
        tlk = TlkFile.from_bytes(data)
        self.assertEqual(len(tlk), 0)

    def test_parse_single_entry(self):
        data = build_tlk_bytes([{"text": "Hello, world!", "flags": FLAG_HAS_TEXT}])
        tlk = TlkFile.from_bytes(data)
        self.assertEqual(len(tlk), 1)
        self.assertEqual(tlk.get(0), "Hello, world!")

    def test_parse_multiple_entries(self):
        entries = [
            {"text": "You must gather your party.", "flags": FLAG_HAS_TEXT},
            {"text": "I am iron man.",              "flags": FLAG_HAS_TEXT},
            {"text": "",                            "flags": 0},
        ]
        data = build_tlk_bytes(entries)
        tlk = TlkFile.from_bytes(data)
        self.assertEqual(len(tlk), 3)
        self.assertEqual(tlk.get(0), "You must gather your party.")
        self.assertEqual(tlk.get(1), "I am iron man.")
        self.assertEqual(tlk.get(2), "")

    def test_invalid_strref_returns_empty(self):
        data = build_tlk_bytes([{"text": "Only entry", "flags": FLAG_HAS_TEXT}])
        tlk = TlkFile.from_bytes(data)
        self.assertEqual(tlk.get(STRREF_INVALID), "")
        self.assertEqual(tlk.get(999),            "")
        self.assertEqual(tlk.get(-1),             "")

    def test_sound_resref_parsed(self):
        entries = [{"text": "Spoken line", "sound": "GORION01", "flags": FLAG_HAS_TEXT | FLAG_HAS_SOUND}]
        data = build_tlk_bytes(entries)
        tlk = TlkFile.from_bytes(data)
        self.assertEqual(tlk.get_sound(0), "GORION01")

    def test_bad_signature_raises(self):
        data = b"BAD " + b"V1  " + b"\x00" * 100
        with self.assertRaises(SignatureMismatch):
            TlkFile.from_bytes(data)

    def test_language_id_preserved(self):
        data = build_tlk_bytes([], language_id=3)
        tlk = TlkFile.from_bytes(data)
        self.assertEqual(tlk.language_id, 3)


class TestTlkEditing(unittest.TestCase):

    def _make_tlk(self) -> TlkFile:
        data = build_tlk_bytes([
            {"text": "Original text", "flags": FLAG_HAS_TEXT},
            {"text": "Second entry",  "flags": FLAG_HAS_TEXT},
        ])
        return TlkFile.from_bytes(data)

    def test_set_text(self):
        tlk = self._make_tlk()
        tlk.set_text(0, "Modified text")
        self.assertEqual(tlk.get(0), "Modified text")

    def test_add_entry_returns_correct_index(self):
        tlk = self._make_tlk()
        idx = tlk.add("Brand new string")
        self.assertEqual(idx, 2)
        self.assertEqual(tlk.get(2), "Brand new string")

    def test_add_entry_with_sound(self):
        tlk = self._make_tlk()
        idx = tlk.add("Voiced line", sound="NEWVOICE")
        self.assertEqual(tlk.get_sound(idx), "NEWVOICE")

    def test_set_text_out_of_range(self):
        tlk = self._make_tlk()
        with self.assertRaises(IndexError):
            tlk.set_text(999, "Should fail")

    def test_search_finds_match(self):
        tlk = self._make_tlk()
        results = tlk.search("Original")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 0)

    def test_search_case_insensitive(self):
        tlk = self._make_tlk()
        results = tlk.search("original")
        self.assertEqual(len(results), 1)

    def test_search_no_match(self):
        tlk = self._make_tlk()
        results = tlk.search("xyzzy")
        self.assertEqual(results, [])


class TestTlkRoundTrip(unittest.TestCase):
    """
    The most important tests: verify binary -> model -> binary produces
    identical bytes. Any deviation means the writer has a bug that would
    corrupt game files.
    """

    def _round_trip(self, entries: list[dict]) -> tuple[bytes, bytes]:
        original = build_tlk_bytes(entries)
        tlk      = TlkFile.from_bytes(original)
        rebuilt  = tlk.to_bytes()
        return original, rebuilt

    def test_empty_round_trip(self):
        original, rebuilt = self._round_trip([])
        self.assertEqual(original, rebuilt)

    def test_single_entry_round_trip(self):
        original, rebuilt = self._round_trip([
            {"text": "Test string", "flags": FLAG_HAS_TEXT}
        ])
        self.assertEqual(original, rebuilt)

    def test_multi_entry_round_trip(self):
        entries = [
            {"text": "First",  "flags": FLAG_HAS_TEXT},
            {"text": "Second", "flags": FLAG_HAS_TEXT},
            {"text": "",       "flags": 0},
            {"text": "Fourth", "flags": FLAG_HAS_TEXT},
        ]
        original, rebuilt = self._round_trip(entries)
        self.assertEqual(original, rebuilt)


class TestTlkJsonRoundTrip(unittest.TestCase):

    def test_json_round_trip(self):
        data = build_tlk_bytes([
            {"text": "Hello",        "flags": FLAG_HAS_TEXT},
            {"text": "Voiced entry", "sound": "VOICE001", "flags": FLAG_HAS_TEXT | FLAG_HAS_SOUND},
        ])
        tlk      = TlkFile.from_bytes(data)
        as_json  = tlk.to_json()
        tlk2     = TlkFile.from_json(as_json)

        self.assertEqual(tlk.get(0), tlk2.get(0))
        self.assertEqual(tlk.get(1), tlk2.get(1))
        self.assertEqual(tlk.get_sound(1), tlk2.get_sound(1))
        self.assertEqual(tlk.language_id, tlk2.language_id)

    def test_json_null_entries_preserved(self):
        """Empty entries must remain as null in JSON to keep index alignment."""
        data = build_tlk_bytes([
            {"text": "Entry 0", "flags": FLAG_HAS_TEXT},
            {"text": "",        "flags": 0},               # gap entry
            {"text": "Entry 2", "flags": FLAG_HAS_TEXT},
        ])
        tlk     = TlkFile.from_bytes(data)
        as_json = tlk.to_json()

        self.assertIsNone(as_json["entries"][1])           # gap must be null
        self.assertEqual(as_json["entries"][2]["text"], "Entry 2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
