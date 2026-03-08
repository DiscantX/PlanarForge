"""
ui/skin/infinity/chu_layout.py

Maps Infinity Engine equipment slot names to pixel rects derived from a
parsed ChuFile.  This is the bridge between the CHU format parser and the
DearPyGui rendering layer.

Typical usage::

    from core.formats.chu import ChuFile
    from ui.skin.infinity.chu_layout import ChuLayout, GameScreenDef

    # Load a per-game screen definition (JSON or hardcoded)
    screen_def = GameScreenDef.bg2ee_inventory()

    # Parse the CHU from the game's KEY/BIFF archive
    chu = ChuFile.from_bytes(raw_chu_bytes)

    # Build the layout — resolves control IDs to rects
    layout = ChuLayout.from_chu(chu, screen_def)

    # Use it: each slot returns (x, y, w, h) relative to the panel origin
    rect = layout.slot_rect("HELMET")   # or None if not present
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.formats.chu import ChuFile, ButtonControl, ControlType


# ---------------------------------------------------------------------------
# SlotRect — a resolved pixel bounding box
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlotRect:
    """Pixel bounding box for one equipment/inventory slot."""
    x:      int   # relative to the window (MOS background) origin
    y:      int
    width:  int
    height: int

    @property
    def pmin(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def pmax(self) -> tuple[int, int]:
        return (self.x + self.width, self.y + self.height)

    @property
    def centre(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


# ---------------------------------------------------------------------------
# ScreenControlMap — per-game declarative wiring
# ---------------------------------------------------------------------------

@dataclass
class ScreenControlMap:
    """
    Declarative mapping for one game screen (e.g. GUIINV).

    Attributes:
        chu_resref:     ResRef of the CHU file to load (e.g. "GUIINV").
        window_id:      Which window inside the CHU holds the slots (int).
        slot_control_ids: Dict mapping canonical slot name → CHU control ID.
        fallback_slot_size: (w, h) used when constructing a fallback grid if
                            no CHU is available.
    """
    chu_resref:         str
    window_id:          int
    slot_control_ids:   dict[str, int]
    fallback_slot_size: tuple[int, int] = (64, 40)

    def to_json(self) -> dict:
        return {
            "chu_resref":         self.chu_resref,
            "window_id":          self.window_id,
            "slot_control_ids":   self.slot_control_ids,
            "fallback_slot_size": list(self.fallback_slot_size),
        }

    @classmethod
    def from_json(cls, d: dict) -> "ScreenControlMap":
        fss = d.get("fallback_slot_size", [64, 40])
        return cls(
            chu_resref=str(d["chu_resref"]),
            window_id=int(d["window_id"]),
            slot_control_ids={str(k): int(v) for k, v in d.get("slot_control_ids", {}).items()},
            fallback_slot_size=(int(fss[0]), int(fss[1])),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "ScreenControlMap":
        p = Path(path)
        return cls.from_json(json.loads(p.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------
    # Built-in per-game definitions
    # ------------------------------------------------------------------

    @classmethod
    def bg2ee_inventory(cls) -> "ScreenControlMap":
        """
        BG:EE / BG2:EE inventory screen (GUIINV, window 2, bg=INVENTOR, 864x710).

        Control IDs and positions verified directly from GUIINV.chu.

        Layout overview (paperdoll at x=306,y=172):
          y= 97: weapon slots (11-14) + cloak (62)
          y=137: quiver slots (15-17)
          y=154: quick item 3 (63, right side)
          y=243: helmet(1), armour(2), shield(3), gloves(4)  — left 4-wide row
          y=244: amulet (26, right of paperdoll)
          y=301: belt (22, centre-left), quick item 1 (23, far right)
          y=347: boots(5), ring_left(6), ring_right(7)       — left 3-wide row
          y=361: quick item 2 (24), ring extras (25,21)
          y=478-640: far-right 2x4 quick item grid (68-75)
          y=571/626: 8x2 inventory grid (30-45)
        """
        return cls(
            chu_resref="GUIINV",
            window_id=2,
            slot_control_ids={
                # Body slots (y=97, left-to-right)
                "ARMOR":       11,
                "GLOVES":       12,
                "HELMET":       13,
                "AMULET":       14,
                "COLOR":         62,   # top-right, same row
                # Quiver/ammo row (y=137)
                "QUIVER1":       15,
                "QUIVER2":       16,
                "QUIVER3":       17,
                # Body slots — left 4-wide row (y=243)
                "WEAPON1":         1,
                "WEAPON2":         2,
                "WEAPON3":         3,
                "WEAPON4":         4,
                # Right of paperdoll (y=244)
                "SHIELD":        26,
                # Belt / misc (y=301)
                "RING_LEFT":          22,   # x=217, centre-left
                # Right-side slot at y=301
                "RING_RIGHT":  23,   # x=461,y=301  
                # Body slots — left 3-wide row (y=347)
                "QUICK_ITEM1":          5,
                "QUICK_ITEM2":      6,
                "QUICK_ITEM3":     7,
                # Below-portrait cluster (y=361)
                "CLOAK":   24,   # x=282
                "BOOTS":   25,   # x=338
                "BELT":   21,   # x=393
                # Right panel (y=154, right side)
                "EMPTY":  63,   # x=464,y=154
                # Far-right quick item 2x4 grid
                "GROUND1":   68,   # x=722,y=478
                "GROUND2":   69,   # x=777,y=478
                "GROUND3":   70,   # x=722,y=532
                "GROUND4":   71,   # x=777,y=532
                "GROUND5":   72,   # x=722,y=586
                "GROUND6":   73,   # x=777,y=586
                "GROUND7":  74,   # x=722,y=640
                "GROUND8":  75,   # x=777,y=640
                # Inventory grid row 1 (y=571, left-to-right)
                "INVENTORY_0":   30,
                "INVENTORY_1":   32,
                "INVENTORY_2":   34,
                "INVENTORY_3":   36,
                "INVENTORY_4":   38,
                "INVENTORY_5":   40,
                "INVENTORY_6":   42,
                "INVENTORY_7":   44,
                # Inventory grid row 2 (y=626)
                "INVENTORY_8":   31,
                "INVENTORY_9":   33,
                "INVENTORY_10":  35,
                "INVENTORY_11":  37,
                "INVENTORY_12":  39,
                "INVENTORY_13":  41,
                "INVENTORY_14":  43,
                "INVENTORY_15":  45,
            },
        )
    @classmethod
    def bg1ee_inventory(cls) -> "ScreenControlMap":
        """BG1:EE inventory screen — same CHU structure as BG2:EE."""
        m = cls.bg2ee_inventory()
        return cls(
            chu_resref="GUIINV",
            window_id=m.window_id,
            slot_control_ids=m.slot_control_ids,
            fallback_slot_size=m.fallback_slot_size,
        )

    @classmethod
    def iwd_inventory(cls) -> "ScreenControlMap":
        """IWD inventory screen — GUIINV, same slot layout as BG."""
        m = cls.bg2ee_inventory()
        return cls(
            chu_resref="GUIINV",
            window_id=m.window_id,
            slot_control_ids=m.slot_control_ids,
        )

    @classmethod
    def pst_inventory(cls) -> "ScreenControlMap":
        """
        PST inventory screen (GUIINV, window 0).

        PST uses a different slot set — tattoos replace some slots.
        Control IDs are approximate; override via JSON if actual IDs differ.
        """
        return cls(
            chu_resref="GUIINV",
            window_id=0,
            slot_control_ids={
                "HELMET":              2,
                "ARMOUR":              3,
                "HAND":                4,
                "RING_LEFT":           5,
                "RING_RIGHT":          6,
                "EYEBALL":             7,
                "TATTOO_LEFT":         8,
                "TATTOO_RIGHT_LOWER":  9,
                "TATTOO_RIGHT_UPPER":  10,
                "BOOTS":               11,
                "WEAPON1":             12,
                "WEAPON2":             13,
                "WEAPON3":             14,
                "WEAPON4":             15,
                "QUIVER1":             16,
                "QUIVER2":             17,
                "QUIVER3":             18,
                "QUICK_ITEM1":         19,
                "QUICK_ITEM2":         20,
                "QUICK_ITEM3":         21,
                "QUICK_ITEM4":         22,
                "QUICK_ITEM5":         23,
                **{f"INVENTORY_{i}": 24 + i for i in range(20)},
            },
        )

    @classmethod
    def for_game(cls, game_id: str) -> "ScreenControlMap":
        """
        Return the inventory screen map for the given game ID.

        Falls back to the BG2EE definition if the game is unknown, so
        the panel still renders something useful rather than crashing.
        """
        game_id = game_id.upper()
        factories = {
            "BG2EE":  cls.bg2ee_inventory,
            "BG2":    cls.bg2ee_inventory,
            "BG1EE":  cls.bg1ee_inventory,
            "BG1":    cls.bg1ee_inventory,
            "BGEE":   cls.bg1ee_inventory,
            "IWDEE":  cls.iwd_inventory,
            "IWD":    cls.iwd_inventory,
            "PST":    cls.pst_inventory,
            "PSTEE":  cls.pst_inventory,
        }
        factory = factories.get(game_id, cls.bg2ee_inventory)
        return factory()


# ---------------------------------------------------------------------------
# ChuLayout — resolved slot rects
# ---------------------------------------------------------------------------

class ChuLayout:
    """
    A resolved set of slot rects for one game screen, derived from a ChuFile.

    Attributes:
        background_mos: ResRef of the MOS background for the window (may be "").
        window_x, window_y: Screen position of the window (for compositing).
        window_width, window_height: Pixel dimensions of the window.
        slots: Dict mapping slot name → SlotRect (window-relative coords).
    """

    def __init__(
        self,
        *,
        background_mos: str,
        window_x: int,
        window_y: int,
        window_width: int,
        window_height: int,
        slots: dict[str, SlotRect],
    ) -> None:
        self.background_mos  = background_mos
        self.window_x        = window_x
        self.window_y        = window_y
        self.window_width    = window_width
        self.window_height   = window_height
        self.slots           = slots

    # ------------------------------------------------------------------
    # Factory: build from a parsed ChuFile + ScreenControlMap
    # ------------------------------------------------------------------

    @classmethod
    def from_chu(cls, chu: ChuFile, screen_def: ScreenControlMap) -> "ChuLayout":
        """
        Resolve slot rects by looking up control IDs in the CHU window.

        Controls that are not found in the window are silently omitted from
        the slot dict — the rendering layer handles missing slots gracefully.
        """
        window = chu.find_window(screen_def.window_id)
        if window is None:
            # Fall back to an empty layout if the window ID doesn't exist.
            return cls._empty(screen_def)

        slots: dict[str, SlotRect] = {}
        for slot_name, ctrl_id in screen_def.slot_control_ids.items():
            ctrl = window.find_control(ctrl_id)
            if ctrl is None:
                continue
            slots[slot_name] = SlotRect(
                x=ctrl.x,
                y=ctrl.y,
                width=ctrl.width,
                height=ctrl.height,
            )

        return cls(
            background_mos=window.background_mos,
            window_x=window.x,
            window_y=window.y,
            window_width=window.width,
            window_height=window.height,
            slots=slots,
        )

    @classmethod
    def make_fallback(
        cls,
        screen_def: ScreenControlMap,
        *,
        cols: int = 4,
        padding: int = 6,
    ) -> "ChuLayout":
        """
        Build a synthetic grid layout when no CHU data is available.

        Slots are laid out left-to-right, top-to-bottom in rows of *cols*.
        Equipment slots come first (fixed positions), inventory slots fill
        a grid below them.
        """
        sw, sh = screen_def.fallback_slot_size
        step_x = sw + padding
        step_y = sh + padding

        # Separate equipment from inventory
        EQUIP_ORDER = [
            "HELMET", "AMULET", "ARMOUR", "CLOAK",
            "RING_LEFT", "RING_RIGHT", "BELT", "BOOTS",
            "GLOVES", "SHIELD",
            "WEAPON1", "WEAPON2", "WEAPON3", "WEAPON4",
            "QUIVER1", "QUIVER2", "QUIVER3",
            "QUICK_ITEM1", "QUICK_ITEM2", "QUICK_ITEM3",
            # PST extras
            "HAND", "EYEBALL", "TATTOO_LEFT",
            "TATTOO_RIGHT_LOWER", "TATTOO_RIGHT_UPPER",
            "QUICK_ITEM4", "QUICK_ITEM5",
        ]
        inventory_names = [n for n in screen_def.slot_control_ids if n.startswith("INVENTORY_")]
        equip_names = [n for n in EQUIP_ORDER if n in screen_def.slot_control_ids]

        slots: dict[str, SlotRect] = {}
        col = row = 0

        def _place(name: str) -> None:
            nonlocal col, row
            slots[name] = SlotRect(
                x=padding + col * step_x,
                y=padding + row * step_y,
                width=sw,
                height=sh,
            )
            col += 1
            if col >= cols:
                col = 0
                row += 1

        for name in equip_names:
            _place(name)

        # New row boundary before inventory
        if col != 0:
            col = 0
            row += 1

        for name in sorted(inventory_names, key=lambda n: int(n.split("_")[1])):
            _place(name)

        total_w = cols * step_x + padding
        total_h = (row + 1) * step_y + padding

        return cls(
            background_mos="",
            window_x=0,
            window_y=0,
            window_width=total_w,
            window_height=total_h,
            slots=slots,
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def slot_rect(self, slot_name: str) -> Optional[SlotRect]:
        """Return the rect for the named slot, or None if not in the layout."""
        return self.slots.get(slot_name)

    def slot_names(self) -> list[str]:
        return list(self.slots.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _empty(cls, screen_def: ScreenControlMap) -> "ChuLayout":
        return cls(
            background_mos="",
            window_x=0, window_y=0,
            window_width=640, window_height=480,
            slots={},
        )