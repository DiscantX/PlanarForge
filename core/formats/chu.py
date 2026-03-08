"""
core/formats/chu.py

Parser for the Infinity Engine CHU (CHUI) format.

CHU files describe the layout of GUI screens — which panels exist, where
they are positioned, and what controls (buttons, sliders, text areas, etc.)
they contain.  The actual graphics for a screen are stored separately in
MOS (background) and BAM (control art) files; CHU just provides the geometry
and wiring.

Supported versions:
    V1   — BG1, BG1:TotS, BG2, BG2:ToB, PST, IWD, IWD:HoW, IWD:TotL, IWD2

Overall structure:
    Header          (20 bytes)
    Window entries  (28 bytes each, at header.window_offset)
    Control table   (8 bytes per entry, at header.control_table_offset)
    Control structs (variable length, offsets stored in control table)

The control table is a flat array of (offset, length) pairs covering ALL
controls across ALL windows.  Each window records the index of its first
control and a count; controls for a window are contiguous in this table.

Control types:
    0  Button / toggle button / pixmap
    2  Slider
    3  TextEdit field
    5  TextArea
    6  Label
    7  Scrollbar

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/chu_v1.htm

Usage::

    from core.formats.chu import ChuFile, ControlType

    chu = ChuFile.from_file("GUIINV.chu")
    for window in chu.windows:
        print(f"Window {window.window_id}: {window.width}x{window.height} "
              f"at ({window.x}, {window.y}), bg={window.background_mos!r}")
        for ctrl in window.controls:
            print(f"  Control {ctrl.control_id} type={ctrl.type.name} "
                  f"at ({ctrl.x}, {ctrl.y}) {ctrl.width}x{ctrl.height}")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import List, Optional, Union

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE       = b"CHUI"
VERSION_V1      = b"V1  "

HEADER_SIZE     = 20
WINDOW_SIZE     = 28    # 0x001c bytes per window entry
CTL_TABLE_ENTRY = 8     # 4 (offset) + 4 (length) per control table entry
CONTROL_COMMON  = 14    # bytes shared by every control type


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ControlType(IntEnum):
    """Known CHU control type codes (byte at offset 0x000c in common section)."""
    BUTTON   = 0
    SLIDER   = 2
    TEXTEDIT = 3
    TEXTAREA = 5
    LABEL    = 6
    SCROLLBAR = 7

    @classmethod
    def _missing_(cls, value: object) -> "ControlType":  # type: ignore[override]
        # Return a synthetic member rather than raising, so unknown controls
        # degrade gracefully — the raw type byte is still accessible on the
        # dataclass.
        pseudo = int.__new__(cls, value)  # type: ignore[arg-type]
        pseudo._name_ = f"UNKNOWN_{value}"
        pseudo._value_ = value
        return pseudo


# ---------------------------------------------------------------------------
# Control dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ControlCommon:
    """Fields shared by every control type (14 bytes)."""
    control_id: int         # uint32
    x:          int         # uint16 — relative to containing window
    y:          int         # uint16 — relative to containing window
    width:      int         # uint16
    height:     int         # uint16
    type:       ControlType # byte
    _unknown:   int = 0     # byte — reserved


@dataclass
class ButtonControl(ControlCommon):
    """Type 0 — Button / toggle button / pixmap."""
    bam_resref:     str = ""  # 8-byte BAM resource
    anim_cycle:     int = 0   # byte
    text_justify:   int = 0   # byte (flags)
    frame_unpressed: int = 0  # byte
    anchor_x1:      int = 0   # byte
    frame_pressed:  int = 0   # byte
    anchor_x2:      int = 0   # byte
    frame_selected: int = 0   # byte
    anchor_y1:      int = 0   # byte
    frame_disabled: int = 0   # byte
    anchor_y2:      int = 0   # byte


@dataclass
class SliderControl(ControlCommon):
    """Type 2 — Slider."""
    background_mos: str = ""   # 8-byte MOS resource
    knob_bam:       str = ""   # 8-byte BAM resource
    cycle:          int = 0    # uint16
    frame_ungrabbed: int = 0   # uint16
    frame_grabbed:  int = 0    # uint16
    knob_x_offset:  int = 0    # uint16
    knob_y_offset:  int = 0    # uint16
    knob_jump_width: int = 0   # uint16
    knob_jump_count: int = 0   # uint16
    _unknown1:      int = 0    # uint16
    _unknown2:      int = 0    # uint16
    _unknown3:      int = 0    # uint16
    _unknown4:      int = 0    # uint16


@dataclass
class TextEditControl(ControlCommon):
    """Type 3 — TextEdit field."""
    background1_mos: str = ""  # 8-byte MOS
    background2_mos: str = ""  # 8-byte MOS
    background3_mos: str = ""  # 8-byte MOS
    cursor_bam:      str = ""  # 8-byte BAM
    caret_cycle:     int = 0   # uint16
    caret_frame:     int = 0   # uint16
    caret_x:         int = 0   # uint16
    caret_y:         int = 0   # uint16
    scrollbar_id:    int = 0xFFFFFFFF  # uint32 (0xFFFFFFFF = none)
    font_bam:        str = ""  # 8-byte BAM
    _unknown:        int = 0   # uint16
    initial_text:    str = ""  # 32-byte ASCII
    max_length:      int = 0   # uint16
    text_case:       int = 0   # uint32 (0=sentence, 1=upper, 2=lower)


@dataclass
class TextAreaControl(ControlCommon):
    """Type 5 — TextArea."""
    font_initials_bam: str = ""  # 8-byte BAM
    font_main_bam:     str = ""  # 8-byte BAM
    text_colour:       int = 0   # uint32 RGBA
    initials_colour:   int = 0   # uint32 RGBA
    background_colour: int = 0   # uint32 RGBA
    scrollbar_id:      int = 0xFFFFFFFF  # uint32 (0xFFFFFFFF = none)


@dataclass
class LabelControl(ControlCommon):
    """Type 6 — Label."""
    initial_strref: int = 0     # uint32 StrRef
    font_bam:       str = ""    # 8-byte BAM
    text_colour:    int = 0     # uint32 RGBA
    outline_colour: int = 0     # uint32 RGBA
    subtype:        int = 0     # uint16 (justification flags)


@dataclass
class ScrollbarControl(ControlCommon):
    """Type 7 — Scrollbar."""
    bam_resref:          str = ""  # 8-byte BAM
    cycle:               int = 0   # uint16
    frame_up_unpressed:  int = 0   # uint16
    frame_up_pressed:    int = 0   # uint16
    frame_down_unpressed: int = 0  # uint16
    frame_down_pressed:  int = 0   # uint16
    frame_trough:        int = 0   # uint16
    frame_slider:        int = 0   # uint16
    textarea_id:         int = 0xFFFFFFFF  # uint32 (0xFFFFFFFF = none)


@dataclass
class UnknownControl(ControlCommon):
    """Placeholder for control types not yet defined in the spec."""
    raw_bytes: bytes = b""


# Union type for all control variants
AnyControl = Union[
    ButtonControl, SliderControl, TextEditControl,
    TextAreaControl, LabelControl, ScrollbarControl, UnknownControl,
]


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

@dataclass
class ChuWindow:
    """One UI panel / window within a CHU file."""
    window_id:      int          # uint16
    _unknown:       int          # uint16
    x:              int          # uint16 — screen position
    y:              int          # uint16 — screen position
    width:          int          # uint16
    height:         int          # uint16
    has_background: bool         # uint16 flag: 1 = background MOS present
    control_count:  int          # uint16
    background_mos: str          # 8-byte ResRef (may be empty string)
    first_control_index: int     # uint16 — index into the flat control table
    _unknown2:      int          # uint16
    controls:       List[AnyControl] = field(default_factory=list)

    def find_control(self, control_id: int) -> Optional[AnyControl]:
        """Return the first control with the given ID, or None."""
        for ctrl in self.controls:
            if ctrl.control_id == control_id:
                return ctrl
        return None

    def controls_of_type(self, control_type: ControlType) -> List[AnyControl]:
        """Return all controls of a given type."""
        return [c for c in self.controls if c.type == control_type]

    def to_json(self) -> dict:
        return {
            "window_id":      self.window_id,
            "x":              self.x,
            "y":              self.y,
            "width":          self.width,
            "height":         self.height,
            "has_background": self.has_background,
            "background_mos": self.background_mos,
            "controls":       [_control_to_json(c) for c in self.controls],
        }


# ---------------------------------------------------------------------------
# ChuFile
# ---------------------------------------------------------------------------

class ChuFile:
    """
    A parsed CHU (CHUI) file.

    Attributes:
        windows: Ordered list of all UI windows in the file.
    """

    def __init__(self, windows: List[ChuWindow]) -> None:
        self.windows = windows

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> "ChuFile":
        """Parse a CHU file from disk."""
        data = Path(path).read_bytes()
        return cls.from_bytes(data)

    @classmethod
    def from_bytes(cls, data: bytes) -> "ChuFile":
        """Parse a CHU file from an in-memory buffer."""
        r = BinaryReader(data)
        return cls._parse(r)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def find_window(self, window_id: int) -> Optional[ChuWindow]:
        """Return the first window with the given ID, or None."""
        for w in self.windows:
            if w.window_id == window_id:
                return w
        return None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        return {"windows": [w.to_json() for w in self.windows]}

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_json(), ensure_ascii=False, indent=indent)

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @classmethod
    def _parse(cls, r: BinaryReader) -> "ChuFile":
        # --- Header ---
        try:
            r.expect_signature(SIGNATURE)
            r.expect_signature(VERSION_V1)
        except SignatureMismatch as exc:
            raise ChuError(str(exc)) from exc

        window_count         = r.read_uint32()  # 0x0008
        control_table_offset = r.read_uint32()  # 0x000c
        window_offset        = r.read_uint32()  # 0x0010

        # --- Read control table (flat array of offset+length pairs) ---
        # We read this first so window parsing can immediately dereference
        # control pointers.
        control_table = cls._read_control_table(r, control_table_offset, r.size)

        # --- Read windows ---
        windows = cls._read_windows(r, window_offset, window_count, control_table)

        return cls(windows)

    @staticmethod
    def _read_control_table(
        r: BinaryReader,
        offset: int,
        file_size: int,
    ) -> List[tuple[int, int]]:
        """
        Read the flat control table from the given offset.

        Returns a list of (ctrl_offset, ctrl_length) tuples.  We read until
        we hit the first entry whose offset would exceed the file, or until
        we have enough entries to cover all windows (determined later during
        window parsing).  In practice the file size is the only bound we
        have without a total control count in the header.
        """
        entries: List[tuple[int, int]] = []
        r.seek(offset)
        # We don't know the total count from the header alone; read until
        # offset points past the file or we hit clearly invalid data.
        # In practice control structs are contiguous and start immediately
        # after the table, so we read until the first offset reaches a
        # control struct region or the file ends.
        while r.remaining >= CTL_TABLE_ENTRY:
            ctrl_offset = r.read_uint32()
            ctrl_length = r.read_uint32()
            if ctrl_offset == 0 and ctrl_length == 0:
                break
            if ctrl_offset >= file_size:
                break
            entries.append((ctrl_offset, ctrl_length))
        return entries

    @staticmethod
    def _read_windows(
        r: BinaryReader,
        offset: int,
        count: int,
        control_table: List[tuple[int, int]],
    ) -> List[ChuWindow]:
        windows: List[ChuWindow] = []
        r.seek(offset)
        for _ in range(count):
            win = ChuFile._read_window(r, control_table)
            windows.append(win)
        return windows

    @staticmethod
    def _read_window(
        r: BinaryReader,
        control_table: List[tuple[int, int]],
    ) -> ChuWindow:
        window_id       = r.read_uint16()   # 0x0000
        unk             = r.read_uint16()   # 0x0002
        x               = r.read_uint16()   # 0x0004
        y               = r.read_uint16()   # 0x0006
        width           = r.read_uint16()   # 0x0008
        height          = r.read_uint16()   # 0x000a
        bg_flag         = r.read_uint16()   # 0x000c
        ctrl_count      = r.read_uint16()   # 0x000e
        background_mos  = r.read_resref()   # 0x0010  (8 bytes)
        first_ctrl_idx  = r.read_uint16()   # 0x0018
        unk2            = r.read_uint16()   # 0x001a

        win = ChuWindow(
            window_id=window_id,
            _unknown=unk,
            x=x,
            y=y,
            width=width,
            height=height,
            has_background=bool(bg_flag),
            control_count=ctrl_count,
            background_mos=background_mos,
            first_control_index=first_ctrl_idx,
            _unknown2=unk2,
        )

        # Resolve controls via the control table
        save_pos = r.pos
        for i in range(ctrl_count):
            table_idx = first_ctrl_idx + i
            if table_idx >= len(control_table):
                break
            ctrl_offset, ctrl_length = control_table[table_idx]
            ctrl = ChuFile._read_control(r, ctrl_offset, ctrl_length)
            win.controls.append(ctrl)
        r.seek(save_pos)  # restore — caller drives sequential window reading

        return win

    @staticmethod
    def _read_common(r: BinaryReader) -> ControlCommon:
        control_id = r.read_uint32()  # 0x0000
        x          = r.read_uint16()  # 0x0004
        y          = r.read_uint16()  # 0x0006
        width      = r.read_uint16()  # 0x0008
        height     = r.read_uint16()  # 0x000a
        type_byte  = r.read_uint8()   # 0x000c
        unknown    = r.read_uint8()   # 0x000d
        return ControlCommon(
            control_id=control_id,
            x=x, y=y,
            width=width, height=height,
            type=ControlType(type_byte),
            _unknown=unknown,
        )

    @staticmethod
    def _read_control(r: BinaryReader, offset: int, length: int) -> AnyControl:
        r.seek(offset)
        common = ChuFile._read_common(r)
        ctrl_type = common.type

        try:
            if ctrl_type == ControlType.BUTTON:
                return ChuFile._read_button(r, common)
            if ctrl_type == ControlType.SLIDER:
                return ChuFile._read_slider(r, common)
            if ctrl_type == ControlType.TEXTEDIT:
                return ChuFile._read_textedit(r, common)
            if ctrl_type == ControlType.TEXTAREA:
                return ChuFile._read_textarea(r, common)
            if ctrl_type == ControlType.LABEL:
                return ChuFile._read_label(r, common)
            if ctrl_type == ControlType.SCROLLBAR:
                return ChuFile._read_scrollbar(r, common)
        except Exception:
            # On any parse error within a specific control, fall through to
            # UnknownControl so one bad control doesn't abort the whole file.
            pass

        # Unknown or unreadable control — preserve raw bytes for inspection
        r.seek(offset)
        raw = r.read_bytes(min(length, r.remaining))
        return UnknownControl(
            control_id=common.control_id,
            x=common.x, y=common.y,
            width=common.width, height=common.height,
            type=common.type,
            _unknown=common._unknown,
            raw_bytes=raw,
        )

    # ------------------------------------------------------------------
    # Per-type readers  (r is positioned just after common section)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_button(r: BinaryReader, c: ControlCommon) -> ButtonControl:
        # 0x000e onwards
        bam_resref      = r.read_resref()   # 8 bytes
        anim_cycle      = r.read_uint8()
        text_justify    = r.read_uint8()
        frame_unpressed = r.read_uint8()
        anchor_x1       = r.read_uint8()
        frame_pressed   = r.read_uint8()
        anchor_x2       = r.read_uint8()
        frame_selected  = r.read_uint8()
        anchor_y1       = r.read_uint8()
        frame_disabled  = r.read_uint8()
        anchor_y2       = r.read_uint8()
        return ButtonControl(
            control_id=c.control_id, x=c.x, y=c.y,
            width=c.width, height=c.height, type=c.type, _unknown=c._unknown,
            bam_resref=bam_resref, anim_cycle=anim_cycle,
            text_justify=text_justify,
            frame_unpressed=frame_unpressed, anchor_x1=anchor_x1,
            frame_pressed=frame_pressed, anchor_x2=anchor_x2,
            frame_selected=frame_selected, anchor_y1=anchor_y1,
            frame_disabled=frame_disabled, anchor_y2=anchor_y2,
        )

    @staticmethod
    def _read_slider(r: BinaryReader, c: ControlCommon) -> SliderControl:
        background_mos  = r.read_resref()   # 8 bytes
        knob_bam        = r.read_resref()   # 8 bytes
        cycle           = r.read_uint16()
        frame_ungrabbed = r.read_uint16()
        frame_grabbed   = r.read_uint16()
        knob_x          = r.read_uint16()
        knob_y          = r.read_uint16()
        jump_width      = r.read_uint16()
        jump_count      = r.read_uint16()
        unk1            = r.read_uint16()
        unk2            = r.read_uint16()
        unk3            = r.read_uint16()
        unk4            = r.read_uint16()
        return SliderControl(
            control_id=c.control_id, x=c.x, y=c.y,
            width=c.width, height=c.height, type=c.type, _unknown=c._unknown,
            background_mos=background_mos, knob_bam=knob_bam,
            cycle=cycle, frame_ungrabbed=frame_ungrabbed,
            frame_grabbed=frame_grabbed,
            knob_x_offset=knob_x, knob_y_offset=knob_y,
            knob_jump_width=jump_width, knob_jump_count=jump_count,
            _unknown1=unk1, _unknown2=unk2, _unknown3=unk3, _unknown4=unk4,
        )

    @staticmethod
    def _read_textedit(r: BinaryReader, c: ControlCommon) -> TextEditControl:
        bg1         = r.read_resref()   # 8 bytes
        bg2         = r.read_resref()   # 8 bytes
        bg3         = r.read_resref()   # 8 bytes
        cursor_bam  = r.read_resref()   # 8 bytes
        caret_cycle = r.read_uint16()
        caret_frame = r.read_uint16()
        caret_x     = r.read_uint16()
        caret_y     = r.read_uint16()
        scrollbar   = r.read_uint32()
        font_bam    = r.read_resref()   # 8 bytes
        unk         = r.read_uint16()
        init_text   = r.read_string(32)
        max_len     = r.read_uint16()
        text_case   = r.read_uint32()
        return TextEditControl(
            control_id=c.control_id, x=c.x, y=c.y,
            width=c.width, height=c.height, type=c.type,
            background1_mos=bg1, background2_mos=bg2, background3_mos=bg3,
            cursor_bam=cursor_bam, caret_cycle=caret_cycle,
            caret_frame=caret_frame, caret_x=caret_x, caret_y=caret_y,
            scrollbar_id=scrollbar, font_bam=font_bam,
            initial_text=init_text, max_length=max_len, text_case=text_case,
        )

    @staticmethod
    def _read_textarea(r: BinaryReader, c: ControlCommon) -> TextAreaControl:
        font_init  = r.read_resref()   # 8 bytes
        font_main  = r.read_resref()   # 8 bytes
        text_col   = r.read_uint32()
        init_col   = r.read_uint32()
        bg_col     = r.read_uint32()
        scrollbar  = r.read_uint32()
        return TextAreaControl(
            control_id=c.control_id, x=c.x, y=c.y,
            width=c.width, height=c.height, type=c.type, _unknown=c._unknown,
            font_initials_bam=font_init, font_main_bam=font_main,
            text_colour=text_col, initials_colour=init_col,
            background_colour=bg_col, scrollbar_id=scrollbar,
        )

    @staticmethod
    def _read_label(r: BinaryReader, c: ControlCommon) -> LabelControl:
        strref      = r.read_uint32()
        font_bam    = r.read_resref()   # 8 bytes
        text_col    = r.read_uint32()
        outline_col = r.read_uint32()
        subtype     = r.read_uint16()
        return LabelControl(
            control_id=c.control_id, x=c.x, y=c.y,
            width=c.width, height=c.height, type=c.type, _unknown=c._unknown,
            initial_strref=strref, font_bam=font_bam,
            text_colour=text_col, outline_colour=outline_col,
            subtype=subtype,
        )

    @staticmethod
    def _read_scrollbar(r: BinaryReader, c: ControlCommon) -> ScrollbarControl:
        bam         = r.read_resref()   # 8 bytes
        cycle       = r.read_uint16()
        fr_up_up    = r.read_uint16()
        fr_up_dn    = r.read_uint16()
        fr_dn_up    = r.read_uint16()
        fr_dn_dn    = r.read_uint16()
        fr_trough   = r.read_uint16()
        fr_slider   = r.read_uint16()
        textarea_id = r.read_uint32()
        return ScrollbarControl(
            control_id=c.control_id, x=c.x, y=c.y,
            width=c.width, height=c.height, type=c.type, _unknown=c._unknown,
            bam_resref=bam, cycle=cycle,
            frame_up_unpressed=fr_up_up, frame_up_pressed=fr_up_dn,
            frame_down_unpressed=fr_dn_up, frame_down_pressed=fr_dn_dn,
            frame_trough=fr_trough, frame_slider=fr_slider,
            textarea_id=textarea_id,
        )


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ChuError(Exception):
    """Raised when a CHU file cannot be parsed."""


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _control_to_json(ctrl: AnyControl) -> dict:
    """Convert any control to a plain JSON-serialisable dict."""
    base = {
        "control_id": ctrl.control_id,
        "type":       ctrl.type.name,
        "type_value": int(ctrl.type),
        "x":          ctrl.x,
        "y":          ctrl.y,
        "width":      ctrl.width,
        "height":     ctrl.height,
    }
    if isinstance(ctrl, ButtonControl):
        base.update({
            "bam_resref":      ctrl.bam_resref,
            "anim_cycle":      ctrl.anim_cycle,
            "text_justify":    ctrl.text_justify,
            "frame_unpressed": ctrl.frame_unpressed,
            "frame_pressed":   ctrl.frame_pressed,
            "frame_selected":  ctrl.frame_selected,
            "frame_disabled":  ctrl.frame_disabled,
        })
    elif isinstance(ctrl, SliderControl):
        base.update({
            "background_mos":  ctrl.background_mos,
            "knob_bam":        ctrl.knob_bam,
            "cycle":           ctrl.cycle,
            "knob_x_offset":   ctrl.knob_x_offset,
            "knob_y_offset":   ctrl.knob_y_offset,
        })
    elif isinstance(ctrl, TextEditControl):
        base.update({
            "font_bam":    ctrl.font_bam,
            "max_length":  ctrl.max_length,
            "text_case":   ctrl.text_case,
            "initial_text": ctrl.initial_text,
        })
    elif isinstance(ctrl, TextAreaControl):
        base.update({
            "font_initials_bam": ctrl.font_initials_bam,
            "font_main_bam":     ctrl.font_main_bam,
            "scrollbar_id":      ctrl.scrollbar_id,
        })
    elif isinstance(ctrl, LabelControl):
        base.update({
            "initial_strref": ctrl.initial_strref,
            "font_bam":       ctrl.font_bam,
            "subtype":        ctrl.subtype,
        })
    elif isinstance(ctrl, ScrollbarControl):
        base.update({
            "bam_resref":   ctrl.bam_resref,
            "textarea_id":  ctrl.textarea_id,
        })
    elif isinstance(ctrl, UnknownControl):
        base["raw_bytes_hex"] = ctrl.raw_bytes.hex()
    return base
