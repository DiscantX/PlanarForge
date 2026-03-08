"""
tests/formats/test_chu.py

Unit tests for the CHU (CHUI) parser.

Tests construct minimal but valid CHU binary payloads from scratch so no
game files are required.  The focus is on:

  - Header parsing (signature, version, counts, offsets)
  - Window entry parsing (geometry, background resref, control linkage)
  - Each control type (Button, Slider, TextEdit, TextArea, Label, Scrollbar)
  - Unknown control type degrades to UnknownControl gracefully
  - find_window() and find_control() lookup helpers
  - to_json() serialisation round-trip
  - SignatureMismatch on bad magic
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.formats.chu import (
    ChuFile, ChuError, ChuWindow,
    ControlType, ControlCommon,
    ButtonControl, SliderControl, TextEditControl,
    TextAreaControl, LabelControl, ScrollbarControl, UnknownControl,
    SIGNATURE, VERSION_V1,
    HEADER_SIZE, WINDOW_SIZE, CTL_TABLE_ENTRY, CONTROL_COMMON,
)
from core.util.binary import BinaryWriter, SignatureMismatch


# ---------------------------------------------------------------------------
# Binary builder helpers
# ---------------------------------------------------------------------------

def _resref(name: str) -> bytes:
    """Encode a ResRef as 8 bytes, null-padded."""
    return name.upper().encode("latin-1")[:8].ljust(8, b"\x00")


def _pack_common(
    control_id: int,
    x: int, y: int,
    width: int, height: int,
    ctrl_type: int,
) -> bytes:
    """14-byte common control prefix."""
    return struct.pack("<IHHHHBB", control_id, x, y, width, height, ctrl_type, 0)


def _pack_button(
    control_id: int = 1,
    x: int = 10, y: int = 20,
    width: int = 64, height: int = 32,
    bam: str = "MYBAM",
) -> bytes:
    common = _pack_common(control_id, x, y, width, height, 0)
    extra = (
        _resref(bam)          # BAM resref  8 bytes
        + struct.pack("BBBBBBBBBB",
                      3,   # anim_cycle
                      0,   # text_justify
                      0,   # frame_unpressed
                      0,   # anchor_x1
                      1,   # frame_pressed
                      0,   # anchor_x2
                      2,   # frame_selected
                      0,   # anchor_y1
                      3,   # frame_disabled
                      0)   # anchor_y2
    )
    return common + extra


def _pack_slider(
    control_id: int = 2,
    x: int = 0, y: int = 0,
    width: int = 100, height: int = 20,
) -> bytes:
    common = _pack_common(control_id, x, y, width, height, 2)
    extra = (
        _resref("SLDBG")      # background MOS  8 bytes
        + _resref("SLDKNOB")  # knob BAM        8 bytes
        + struct.pack("<HHHHHHHHHHHH",
                      1,   # cycle
                      0,   # frame_ungrabbed
                      1,   # frame_grabbed
                      5,   # knob_x
                      8,   # knob_y
                      10,  # jump_width
                      5,   # jump_count
                      0, 0, 0, 0, 0)  # unknowns (×4 → 4×uint16 = 8 bytes, but spec has 4)
    )
    return common + extra


def _pack_textarea(
    control_id: int = 5,
    x: int = 0, y: int = 0,
    width: int = 200, height: int = 100,
) -> bytes:
    common = _pack_common(control_id, x, y, width, height, 5)
    extra = (
        _resref("FONTINIT")   # initials font BAM  8 bytes
        + _resref("FONTMAIN")  # main font BAM      8 bytes
        + struct.pack("<IIII",
                      0xFF0000FF,   # text_colour  RGBA
                      0x00FF00FF,   # initials_colour
                      0x000000FF,   # background_colour
                      0xFFFFFFFF)   # scrollbar_id (none)
    )
    return common + extra


def _pack_label(
    control_id: int = 6,
    x: int = 5, y: int = 5,
    width: int = 80, height: int = 20,
    strref: int = 42,
) -> bytes:
    common = _pack_common(control_id, x, y, width, height, 6)
    extra = (
        struct.pack("<I", strref)  # initial strref  4 bytes
        + _resref("LABELFNT")      # font BAM        8 bytes
        + struct.pack("<IIH",
                      0xFFFFFFFF,  # text_colour
                      0x00000000,  # outline_colour
                      4)           # subtype
    )
    return common + extra


def _pack_scrollbar(
    control_id: int = 7,
    x: int = 0, y: int = 0,
    width: int = 16, height: int = 100,
    textarea_id: int = 0xFFFFFFFF,
) -> bytes:
    common = _pack_common(control_id, x, y, width, height, 7)
    extra = (
        _resref("SCRLBAM")         # BAM  8 bytes
        + struct.pack("<HHHHHHHI",
                      0,              # cycle
                      0, 1, 2, 3,     # up_unpressed, up_pressed, down_unpressed, down_pressed
                      4, 5,           # trough, slider
                      textarea_id)    # textarea control ID
    )
    return common + extra


def _build_chu(
    controls: list[bytes],
    window_x: int = 0,
    window_y: int = 0,
    window_w: int = 640,
    window_h: int = 480,
    bg_mos: str = "GUIBG",
) -> bytes:
    """
    Build a minimal valid CHU file with a single window containing the
    given list of pre-serialised control byte strings.
    """
    n_controls = len(controls)

    # Layout:
    #   0x00  Header (20 bytes)
    #   0x14  Window entries (28 bytes each)  — 1 window here
    #   0x30  Control table (8 bytes × n_controls)
    #   0x30 + 8*n  Control structs (variable)

    window_offset       = HEADER_SIZE                           # 0x14
    control_table_offset = window_offset + WINDOW_SIZE          # 0x30
    ctrl_structs_start  = control_table_offset + CTL_TABLE_ENTRY * n_controls

    # Compute each control's absolute offset
    ctrl_offsets: list[int] = []
    pos = ctrl_structs_start
    for raw in controls:
        ctrl_offsets.append(pos)
        pos += len(raw)

    # --- Header ---
    header = struct.pack(
        "<4s4sIII",
        SIGNATURE,
        VERSION_V1,
        1,                    # window count
        control_table_offset,
        window_offset,
    )

    # --- Window (28 bytes) ---
    window = struct.pack(
        "<HHHHHHHh8sHH",
        0,            # window_id
        0,            # unknown
        window_x,
        window_y,
        window_w,
        window_h,
        1 if bg_mos else 0,  # has_background flag
        n_controls,
        _resref(bg_mos),
        0,            # first_control_index
        0,            # unknown2
    )

    # --- Control table ---
    ctl_table = b""
    for i, raw in enumerate(controls):
        ctl_table += struct.pack("<II", ctrl_offsets[i], len(raw))

    return header + window + ctl_table + b"".join(controls)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChuSignature(unittest.TestCase):

    def test_bad_signature_raises(self):
        bad = b"NOPE" + VERSION_V1 + b"\x00" * 12
        with self.assertRaises((ChuError, SignatureMismatch)):
            ChuFile.from_bytes(bad)

    def test_bad_version_raises(self):
        bad = SIGNATURE + b"V2  " + b"\x00" * 12
        with self.assertRaises((ChuError, SignatureMismatch)):
            ChuFile.from_bytes(bad)


class TestChuHeader(unittest.TestCase):

    def test_empty_window_list(self):
        # A CHU with 0 windows should parse without error
        data = struct.pack("<4s4sIII", SIGNATURE, VERSION_V1, 0, HEADER_SIZE, HEADER_SIZE)
        chu = ChuFile.from_bytes(data)
        self.assertEqual(len(chu.windows), 0)


class TestChuWindow(unittest.TestCase):

    def _parse_single_window(self, **kwargs) -> ChuWindow:
        data = _build_chu([], **kwargs)
        chu = ChuFile.from_bytes(data)
        self.assertEqual(len(chu.windows), 1)
        return chu.windows[0]

    def test_window_geometry(self):
        win = self._parse_single_window(window_x=50, window_y=100, window_w=320, window_h=240)
        self.assertEqual(win.x, 50)
        self.assertEqual(win.y, 100)
        self.assertEqual(win.width, 320)
        self.assertEqual(win.height, 240)

    def test_window_background_mos(self):
        win = self._parse_single_window(bg_mos="GUIINV")
        self.assertEqual(win.background_mos, "GUIINV")
        self.assertTrue(win.has_background)

    def test_window_no_controls(self):
        win = self._parse_single_window()
        self.assertEqual(len(win.controls), 0)

    def test_find_window_exists(self):
        data = _build_chu([])
        chu = ChuFile.from_bytes(data)
        win = chu.find_window(0)
        self.assertIsNotNone(win)

    def test_find_window_missing(self):
        data = _build_chu([])
        chu = ChuFile.from_bytes(data)
        self.assertIsNone(chu.find_window(99))


class TestButtonControl(unittest.TestCase):

    def _get_button(self) -> ButtonControl:
        btn = _pack_button(control_id=10, x=5, y=15, width=64, height=32, bam="MYBTN")
        data = _build_chu([btn])
        chu = ChuFile.from_bytes(data)
        ctrl = chu.windows[0].controls[0]
        self.assertIsInstance(ctrl, ButtonControl)
        return ctrl  # type: ignore[return-value]

    def test_control_id(self):
        self.assertEqual(self._get_button().control_id, 10)

    def test_position(self):
        btn = self._get_button()
        self.assertEqual(btn.x, 5)
        self.assertEqual(btn.y, 15)

    def test_dimensions(self):
        btn = self._get_button()
        self.assertEqual(btn.width, 64)
        self.assertEqual(btn.height, 32)

    def test_bam_resref(self):
        self.assertEqual(self._get_button().bam_resref, "MYBTN")

    def test_type_enum(self):
        self.assertEqual(self._get_button().type, ControlType.BUTTON)

    def test_frame_indices(self):
        btn = self._get_button()
        self.assertEqual(btn.frame_pressed, 1)
        self.assertEqual(btn.frame_selected, 2)
        self.assertEqual(btn.frame_disabled, 3)

    def test_find_control(self):
        btn = _pack_button(control_id=42)
        data = _build_chu([btn])
        chu = ChuFile.from_bytes(data)
        found = chu.windows[0].find_control(42)
        self.assertIsNotNone(found)
        self.assertEqual(found.control_id, 42)

    def test_controls_of_type(self):
        btn = _pack_button(control_id=1)
        data = _build_chu([btn])
        chu = ChuFile.from_bytes(data)
        buttons = chu.windows[0].controls_of_type(ControlType.BUTTON)
        self.assertEqual(len(buttons), 1)


class TestSliderControl(unittest.TestCase):

    def _get_slider(self) -> SliderControl:
        raw = _pack_slider(control_id=20)
        data = _build_chu([raw])
        chu = ChuFile.from_bytes(data)
        ctrl = chu.windows[0].controls[0]
        self.assertIsInstance(ctrl, SliderControl)
        return ctrl  # type: ignore[return-value]

    def test_type_enum(self):
        self.assertEqual(self._get_slider().type, ControlType.SLIDER)

    def test_background_mos(self):
        self.assertEqual(self._get_slider().background_mos, "SLDBG")

    def test_knob_bam(self):
        self.assertEqual(self._get_slider().knob_bam, "SLDKNOB")

    def test_knob_offsets(self):
        s = self._get_slider()
        self.assertEqual(s.knob_x_offset, 5)
        self.assertEqual(s.knob_y_offset, 8)


class TestTextAreaControl(unittest.TestCase):

    def _get_textarea(self) -> TextAreaControl:
        raw = _pack_textarea(control_id=30)
        data = _build_chu([raw])
        chu = ChuFile.from_bytes(data)
        ctrl = chu.windows[0].controls[0]
        self.assertIsInstance(ctrl, TextAreaControl)
        return ctrl  # type: ignore[return-value]

    def test_type_enum(self):
        self.assertEqual(self._get_textarea().type, ControlType.TEXTAREA)

    def test_fonts(self):
        ta = self._get_textarea()
        self.assertEqual(ta.font_initials_bam, "FONTINIT")
        self.assertEqual(ta.font_main_bam, "FONTMAIN")

    def test_scrollbar_none(self):
        self.assertEqual(self._get_textarea().scrollbar_id, 0xFFFFFFFF)


class TestLabelControl(unittest.TestCase):

    def _get_label(self) -> LabelControl:
        raw = _pack_label(control_id=60, strref=1234)
        data = _build_chu([raw])
        chu = ChuFile.from_bytes(data)
        ctrl = chu.windows[0].controls[0]
        self.assertIsInstance(ctrl, LabelControl)
        return ctrl  # type: ignore[return-value]

    def test_type_enum(self):
        self.assertEqual(self._get_label().type, ControlType.LABEL)

    def test_strref(self):
        self.assertEqual(self._get_label().initial_strref, 1234)

    def test_font_bam(self):
        self.assertEqual(self._get_label().font_bam, "LABELFNT")


class TestScrollbarControl(unittest.TestCase):

    def _get_scrollbar(self) -> ScrollbarControl:
        raw = _pack_scrollbar(control_id=70, textarea_id=30)
        data = _build_chu([raw])
        chu = ChuFile.from_bytes(data)
        ctrl = chu.windows[0].controls[0]
        self.assertIsInstance(ctrl, ScrollbarControl)
        return ctrl  # type: ignore[return-value]

    def test_type_enum(self):
        self.assertEqual(self._get_scrollbar().type, ControlType.SCROLLBAR)

    def test_bam_resref(self):
        self.assertEqual(self._get_scrollbar().bam_resref, "SCRLBAM")

    def test_textarea_link(self):
        self.assertEqual(self._get_scrollbar().textarea_id, 30)


class TestUnknownControl(unittest.TestCase):

    def test_unknown_type_degrades_gracefully(self):
        # Build a control with type byte 99 (not in the spec)
        raw = _pack_common(99, 0, 0, 10, 10, 99) + b"\x00" * 10
        data = _build_chu([raw])
        chu = ChuFile.from_bytes(data)
        ctrl = chu.windows[0].controls[0]
        self.assertIsInstance(ctrl, UnknownControl)
        self.assertEqual(int(ctrl.type), 99)


class TestMultipleControls(unittest.TestCase):

    def test_multiple_controls_in_window(self):
        btn = _pack_button(control_id=1)
        lbl = _pack_label(control_id=2)
        scr = _pack_scrollbar(control_id=3)
        data = _build_chu([btn, lbl, scr])
        chu = ChuFile.from_bytes(data)
        win = chu.windows[0]
        self.assertEqual(len(win.controls), 3)
        self.assertEqual(win.controls[0].control_id, 1)
        self.assertEqual(win.controls[1].control_id, 2)
        self.assertEqual(win.controls[2].control_id, 3)

    def test_controls_of_type_filters_correctly(self):
        btn1 = _pack_button(control_id=1)
        btn2 = _pack_button(control_id=2)
        lbl  = _pack_label(control_id=3)
        data = _build_chu([btn1, btn2, lbl])
        chu = ChuFile.from_bytes(data)
        win = chu.windows[0]
        buttons = win.controls_of_type(ControlType.BUTTON)
        labels  = win.controls_of_type(ControlType.LABEL)
        self.assertEqual(len(buttons), 2)
        self.assertEqual(len(labels), 1)


class TestJsonSerialisation(unittest.TestCase):

    def test_window_to_json_keys(self):
        data = _build_chu([_pack_button()], bg_mos="GUIINV")
        chu = ChuFile.from_bytes(data)
        j = chu.windows[0].to_json()
        for key in ("window_id", "x", "y", "width", "height", "background_mos", "controls"):
            self.assertIn(key, j)

    def test_control_to_json_has_type_name(self):
        data = _build_chu([_pack_button()])
        chu = ChuFile.from_bytes(data)
        j = chu.windows[0].to_json()
        ctrl_json = j["controls"][0]
        self.assertEqual(ctrl_json["type"], "BUTTON")

    def test_full_to_json_is_serialisable(self):
        import json
        data = _build_chu([_pack_button(), _pack_label()])
        chu = ChuFile.from_bytes(data)
        # Should not raise
        text = chu.to_json_string()
        parsed = json.loads(text)
        self.assertIn("windows", parsed)


if __name__ == "__main__":
    unittest.main()
