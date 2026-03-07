"""
core/formats/cre.py

Parser and writer for the Infinity Engine CRE (Creature) format.

Every NPC, monster, and summon in the game is a CRE file.  The format
encodes identity, stats, resistances, skills, proficiencies, known spells,
memorised spells, inventory, equipment slots, and active effects.

Supported versions:
    V1   — BG1, IWD1
    V1.2 — Planescape: Torment  (significantly different header layout)
    V9   — BG2, BG2:EE, IWD:EE  (larger header, EFF V2.0 effect blocks)

Effect storage:
    V1 / V1.2  use inline 48-byte effect blocks (same layout as ITM/SPL).
    V9         uses 104-byte EFF V2.0 structs; both are parsed into the
               unified :class:`EffectBlock` type.  The extra 56 bytes are
               preserved verbatim in ``raw_extra`` for lossless round-trips.

Item slots:
    Exposed as :class:`SlotIndex` (V1/V9) or :class:`PstSlotIndex` (V1.2),
    both mapping slot names to indices in the ``slots`` dict.

IESDP references:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/cre_v1.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/cre_v12.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/cre_v9.htm

Usage::

    from core.formats.cre import CreFile, CreFileV12, SlotIndex, PstSlotIndex

    cre = CreFile.from_file("GORION.cre")       # auto-dispatches on version
    print(cre.header.max_hp)
    print(cre.item_in_slot(SlotIndex.WEAPON1))

    pst = CreFile.from_file("MORTE.cre")        # returns CreFileV12
    assert isinstance(pst, CreFileV12)
    print(pst.header.lore)
    print(pst.item_in_slot(PstSlotIndex.TATTOO1))
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.resref import ResRef
from core.util.strref import StrRef, StrRefError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE        = b"CRE "
VERSION_V1       = b"V1.0"
VERSION_V12      = b"V1.2"
VERSION_V9       = b"V9.0"

HEADER_SIZE_V1   = 0x2D4   # 724  bytes  (BG2 V1.0 full header)
HEADER_SIZE_V12  = 0x378   # 888  bytes
HEADER_SIZE_V9   = 0x33C   # 828  bytes

KNOWN_SPELL_SIZE      = 12
MEMORISE_INFO_SIZE    = 16
MEMORISED_SPELL_SIZE  = 12
ITEM_SIZE             = 20
EFFECT_V1_SIZE        = 48
EFFECT_V2_SIZE        = 104

SLOT_COUNT     = 40   # V1 / V9  (BG1/BG2/BGEE: 40 slots per IESDP)
SLOT_COUNT_V12 = 46   # PST



# ---------------------------------------------------------------------------
# Enumerations — shared
# ---------------------------------------------------------------------------

class Gender(IntEnum):
    MALE    = 1
    FEMALE  = 2
    NEITHER = 3
    BOTH    = 4


class Race(IntEnum):
    HUMAN    = 1
    ELF      = 2
    HALF_ELF = 3
    DWARF    = 4
    HALFLING = 5
    GNOME    = 6
    HALF_ORC = 7


class Class(IntEnum):
    MAGE                = 1
    FIGHTER             = 2
    CLERIC              = 3
    THIEF               = 4
    BARD                = 5
    PALADIN             = 6
    FIGHTER_MAGE        = 7
    FIGHTER_CLERIC      = 8
    FIGHTER_THIEF       = 9
    FIGHTER_MAGE_THIEF  = 10
    DRUID               = 11
    RANGER              = 12
    MAGE_THIEF          = 13
    CLERIC_MAGE         = 14
    CLERIC_THIEF        = 15
    FIGHTER_DRUID       = 16
    FIGHTER_MAGE_CLERIC = 17
    CLERIC_RANGER       = 18
    SHAMAN              = 19
    SORCERER            = 19


class Alignment(IntEnum):
    LAWFUL_GOOD     = 0x11
    NEUTRAL_GOOD    = 0x21
    CHAOTIC_GOOD    = 0x31
    LAWFUL_NEUTRAL  = 0x12
    TRUE_NEUTRAL    = 0x22
    CHAOTIC_NEUTRAL = 0x32
    LAWFUL_EVIL     = 0x13
    NEUTRAL_EVIL    = 0x23
    CHAOTIC_EVIL    = 0x33


class CreFlag(IntFlag):
    NONE               = 0x00000000
    DMG_ON_DEATH       = 0x00000001
    NO_CORPSE          = 0x00000002
    PERMANENT_CORPSE   = 0x00000004
    ORIG_CLASS_FIGHTER = 0x00000008
    ORIG_CLASS_MAGE    = 0x00000010
    ORIG_CLASS_CLERIC  = 0x00000020
    ORIG_CLASS_THIEF   = 0x00000040
    ORIG_CLASS_DRUID   = 0x00000080
    ORIG_CLASS_RANGER  = 0x00000100
    FALLEN_PALADIN     = 0x00000200
    FALLEN_RANGER      = 0x00000400
    EXPORTABLE         = 0x00000800
    HIDE_INJURY_STATUS = 0x00001000
    QUEST_CRITICAL     = 0x00004000
    ACTIVATED          = 0x00008000
    EE_BEEN_IN_PARTY   = 0x00010000


# ---------------------------------------------------------------------------
# Item slot enums
# ---------------------------------------------------------------------------

class SlotIndex(IntEnum):
    """Equipment slot indices for V1 (BG1/IWD) and V9 (BG2/EE) creatures."""
    HELMET       = 0
    ARMOUR       = 1
    SHIELD       = 2
    GLOVES       = 3
    RING_LEFT    = 4
    RING_RIGHT   = 5
    AMULET       = 6
    BELT         = 7
    BOOTS        = 8
    WEAPON1      = 9
    WEAPON2      = 10
    WEAPON3      = 11
    WEAPON4      = 12
    QUIVER1      = 13
    QUIVER2      = 14
    QUIVER3      = 15
    CLOAK        = 16
    QUICK_ITEM1  = 17
    QUICK_ITEM2  = 18
    QUICK_ITEM3  = 19
    INVENTORY_0  = 20
    INVENTORY_1  = 21
    INVENTORY_2  = 22
    INVENTORY_3  = 23
    INVENTORY_4  = 24
    INVENTORY_5  = 25
    INVENTORY_6  = 26
    INVENTORY_7  = 27
    INVENTORY_8  = 28
    INVENTORY_9  = 29
    INVENTORY_10 = 30
    INVENTORY_11 = 31
    INVENTORY_12 = 32
    INVENTORY_13 = 33
    INVENTORY_14 = 34
    INVENTORY_15 = 35
    MAGIC_WEAPON    = 36
    WEAPON_SELECTED = 37   # index of active weapon (0–3), not a real slot


class PstSlotIndex(IntEnum):
    """
    Equipment slot indices for V1.2 (Planescape: Torment) creatures.

    PST has a significantly different slot layout:
    - No shield slot (PST is mostly fist/weapon only)
    - Only 2 weapon slots
    - Adds Tattoo and Lens slots unique to Sigil's item system
    - Larger inventory (20 slots)
    """
    HELMET       = 0
    ARMOUR       = 1
    # slot 2 unused (no shield)
    GLOVES       = 3
    RING_LEFT    = 4
    RING_RIGHT   = 5
    AMULET       = 6
    BELT         = 7
    BOOTS        = 8
    WEAPON1      = 9
    WEAPON2      = 10
    # slots 11-12 unused (no weapon 3/4)
    QUIVER1      = 13
    QUIVER2      = 14
    QUIVER3      = 15
    CLOAK        = 16
    QUICK_ITEM1  = 17
    QUICK_ITEM2  = 18
    QUICK_ITEM3  = 19
    INVENTORY_0  = 20
    INVENTORY_1  = 21
    INVENTORY_2  = 22
    INVENTORY_3  = 23
    INVENTORY_4  = 24
    INVENTORY_5  = 25
    INVENTORY_6  = 26
    INVENTORY_7  = 27
    INVENTORY_8  = 28
    INVENTORY_9  = 29
    INVENTORY_10 = 30
    INVENTORY_11 = 31
    INVENTORY_12 = 32
    INVENTORY_13 = 33
    INVENTORY_14 = 34
    INVENTORY_15 = 35
    INVENTORY_16 = 36
    INVENTORY_17 = 37
    INVENTORY_18 = 38
    INVENTORY_19 = 39
    TATTOO1      = 40   # PST-specific
    TATTOO2      = 41   # PST-specific
    LENS         = 42   # PST-specific (eyeball slot)
    MAGIC_WEAPON    = 43
    WEAPON_SELECTED = 44
    # slot 45: unused padding


# ---------------------------------------------------------------------------
# Effect block  (48-byte V1 core + optional 56-byte V2 tail)
# ---------------------------------------------------------------------------

@dataclass
class EffectBlock:
    """
    A single active effect on a creature.

    The 48-byte core is identical to ITM/SPL feature blocks.  For V9
    creatures, the engine stores 104-byte EFF V2.0 structs; the extra
    56 bytes are kept verbatim in ``raw_extra`` for lossless round-trips.
    Callers that only need the common fields can ignore ``raw_extra``.
    """
    opcode:        int   = 0
    target:        int   = 0
    power:         int   = 0
    parameter1:    int   = 0
    parameter2:    int   = 0
    timing_mode:   int   = 0
    dispel_resist: int   = 0
    duration:      int   = 0
    probability1:  int   = 100
    probability2:  int   = 0
    resource:      str   = ""
    dice_count:    int   = 0
    dice_sides:    int   = 0
    saving_throw:  int   = 0
    save_bonus:    int   = 0
    special:       int   = 0
    raw_extra:     bytes = b""   # 56 bytes for V2, empty for V1/V1.2

    @classmethod
    def _read_v1(cls, r: BinaryReader) -> "EffectBlock":
        opcode        = r.read_uint16()
        target        = r.read_uint8()
        power         = r.read_uint8()
        parameter1    = r.read_int32()
        parameter2    = r.read_int32()
        timing_mode   = r.read_uint8()
        dispel_resist = r.read_uint8()
        r.skip(2)
        duration      = r.read_uint32()
        probability1  = r.read_uint8()
        probability2  = r.read_uint8()
        r.skip(2)
        resource      = r.read_resref()
        dice_count    = r.read_int32()
        dice_sides    = r.read_int32()
        saving_throw  = r.read_uint32()
        save_bonus    = r.read_int32()
        special       = r.read_uint32()
        return cls(
            opcode=opcode, target=target, power=power,
            parameter1=parameter1, parameter2=parameter2,
            timing_mode=timing_mode, dispel_resist=dispel_resist,
            duration=duration, probability1=probability1,
            probability2=probability2, resource=resource,
            dice_count=dice_count, dice_sides=dice_sides,
            saving_throw=saving_throw, save_bonus=save_bonus,
            special=special,
        )

    @classmethod
    def _read_v2(cls, r: BinaryReader) -> "EffectBlock":
        base = cls._read_v1(r)
        base.raw_extra = r.read_bytes(56)
        return base

    def _write_v1(self, w: BinaryWriter) -> None:
        w.write_uint16(self.opcode)
        w.write_uint8(self.target)
        w.write_uint8(self.power)
        w.write_int32(self.parameter1)
        w.write_int32(self.parameter2)
        w.write_uint8(self.timing_mode)
        w.write_uint8(self.dispel_resist)
        w.write_padding(2)
        w.write_uint32(self.duration)
        w.write_uint8(self.probability1)
        w.write_uint8(self.probability2)
        w.write_padding(2)
        w.write_resref(self.resource)
        w.write_int32(self.dice_count)
        w.write_int32(self.dice_sides)
        w.write_uint32(self.saving_throw)
        w.write_int32(self.save_bonus)
        w.write_uint32(self.special)

    def _write_v2(self, w: BinaryWriter) -> None:
        self._write_v1(w)
        tail = self.raw_extra[:56].ljust(56, b"\x00")
        w.write_bytes(tail)

    def to_json(self) -> dict:
        d: dict = {"opcode": self.opcode}
        if self.target:              d["target"]        = self.target
        if self.power:               d["power"]         = self.power
        if self.parameter1:          d["parameter1"]    = self.parameter1
        if self.parameter2:          d["parameter2"]    = self.parameter2
        if self.timing_mode:         d["timing_mode"]   = self.timing_mode
        if self.dispel_resist:       d["dispel_resist"] = self.dispel_resist
        if self.duration:            d["duration"]      = self.duration
        if self.probability1 != 100: d["probability1"]  = self.probability1
        if self.probability2:        d["probability2"]  = self.probability2
        if self.resource:            d["resource"]      = self.resource
        if self.dice_count:          d["dice_count"]    = self.dice_count
        if self.dice_sides:          d["dice_sides"]    = self.dice_sides
        if self.saving_throw:        d["saving_throw"]  = self.saving_throw
        if self.save_bonus:          d["save_bonus"]    = self.save_bonus
        if self.special:             d["special"]       = self.special
        if self.raw_extra:           d["raw_extra"]     = self.raw_extra.hex()
        return d

    @classmethod
    def from_json(cls, d: dict) -> "EffectBlock":
        raw_extra_hex = d.get("raw_extra", "")
        return cls(
            opcode        = d.get("opcode", 0),
            target        = d.get("target", 0),
            power         = d.get("power", 0),
            parameter1    = d.get("parameter1", 0),
            parameter2    = d.get("parameter2", 0),
            timing_mode   = d.get("timing_mode", 0),
            dispel_resist = d.get("dispel_resist", 0),
            duration      = d.get("duration", 0),
            probability1  = d.get("probability1", 100),
            probability2  = d.get("probability2", 0),
            resource      = d.get("resource", ""),
            dice_count    = d.get("dice_count", 0),
            dice_sides    = d.get("dice_sides", 0),
            saving_throw  = d.get("saving_throw", 0),
            save_bonus    = d.get("save_bonus", 0),
            special       = d.get("special", 0),
            raw_extra     = bytes.fromhex(raw_extra_hex) if raw_extra_hex else b"",
        )


# ---------------------------------------------------------------------------
# Known / memorised spell records  (shared across all versions)
# ---------------------------------------------------------------------------

@dataclass
class KnownSpell:
    """A spell the creature knows and may memorise."""
    resref:     str = ""
    level:      int = 0
    spell_type: int = 0   # 0=wizard 1=cleric 2=innate

    @classmethod
    def _read(cls, r: BinaryReader) -> "KnownSpell":
        return cls(resref=r.read_resref(), level=r.read_uint16(),
                   spell_type=r.read_uint16())

    def _write(self, w: BinaryWriter) -> None:
        w.write_resref(self.resref)
        w.write_uint16(self.level)
        w.write_uint16(self.spell_type)

    def to_json(self) -> dict:
        return {"resref": self.resref, "level": self.level,
                "spell_type": self.spell_type}

    @classmethod
    def from_json(cls, d: dict) -> "KnownSpell":
        return cls(resref=d.get("resref",""), level=d.get("level",0),
                   spell_type=d.get("spell_type",0))


@dataclass
class MemoriseInfo:
    """Spell memorisation slot entry — 16 bytes per IESDP CRE V1.0.

    Offset  Size  Field
    0x0000    2   Spell level (0-based, i.e. level-1)
    0x0002    2   Number of spells memorisable
    0x0004    2   Number of spells memorisable (after effects)
    0x0006    2   Spell type: 0=Priest, 1=Wizard, 2=Innate
    0x0008    4   Index into memorised-spells array (first entry for this slot)
    0x000C    4   Count of memorised-spell entries for this slot
    """
    level:           int = 0
    num_memor:       int = 0   # spells memorisable (base)
    num_memor2:      int = 0   # spells memorisable (after effects)
    spell_type:      int = 0   # 0=Priest, 1=Wizard, 2=Innate
    first_spell_idx: int = 0   # index into memorised spells array
    spell_count:     int = 0   # entries in memorised spells array for this slot

    @classmethod
    def _read(cls, r: BinaryReader) -> "MemoriseInfo":
        level           = r.read_uint16()
        num_memor       = r.read_uint16()
        num_memor2      = r.read_uint16()
        spell_type      = r.read_uint16()
        first_spell_idx = r.read_uint32()
        spell_count     = r.read_uint32()
        return cls(level=level, num_memor=num_memor, num_memor2=num_memor2,
                   spell_type=spell_type, first_spell_idx=first_spell_idx,
                   spell_count=spell_count)

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint16(self.level)
        w.write_uint16(self.num_memor)
        w.write_uint16(self.num_memor2)
        w.write_uint16(self.spell_type)
        w.write_uint32(self.first_spell_idx)
        w.write_uint32(self.spell_count)

    def to_json(self) -> dict:
        d: dict = {"level": self.level, "num_memor": self.num_memor,
                   "num_memor2": self.num_memor2, "spell_type": self.spell_type}
        if self.first_spell_idx: d["first_spell_idx"] = self.first_spell_idx
        if self.spell_count:     d["spell_count"]     = self.spell_count
        return d

    @classmethod
    def from_json(cls, d: dict) -> "MemoriseInfo":
        return cls(level=d.get("level", 0), num_memor=d.get("num_memor", 0),
                   num_memor2=d.get("num_memor2", 0),
                   spell_type=d.get("spell_type", 0),
                   first_spell_idx=d.get("first_spell_idx", 0),
                   spell_count=d.get("spell_count", 0))


@dataclass
class MemorisedSpell:
    """A spell currently memorised (ready to cast)."""
    resref:    str = ""
    memorised: int = 1   # 1=available, 0=already cast today

    @classmethod
    def _read(cls, r: BinaryReader) -> "MemorisedSpell":
        return cls(resref=r.read_resref(), memorised=r.read_uint32())

    def _write(self, w: BinaryWriter) -> None:
        w.write_resref(self.resref)
        w.write_uint32(self.memorised)

    def to_json(self) -> dict:
        d: dict = {"resref": self.resref}
        if not self.memorised:
            d["memorised"] = 0
        return d

    @classmethod
    def from_json(cls, d: dict) -> "MemorisedSpell":
        return cls(resref=d.get("resref",""), memorised=d.get("memorised",1))


# ---------------------------------------------------------------------------
# Inventory item  (20 bytes, shared across all versions)
# ---------------------------------------------------------------------------

@dataclass
class CreItem:
    """An item in the creature's inventory or equipment."""
    resref:   str = ""
    flags:    int = 0
    charges1: int = 0
    charges2: int = 0
    charges3: int = 0
    unknown: bytes = b"\x00\x00\x00\x00"   # 4 bytes at offset 16 (often 0x02000000)

    FLAG_IDENTIFIED  = 0x0001
    FLAG_UNSTEALABLE = 0x0002
    FLAG_STOLEN      = 0x0004
    FLAG_UNDROPPABLE = 0x0008

    @classmethod
    def _read(cls, r: BinaryReader) -> "CreItem":
        resref   = r.read_resref()
        flags    = r.read_uint16()
        charges1 = r.read_uint16()
        charges2 = r.read_uint16()
        charges3 = r.read_uint16()
        unknown  = r.read_bytes(4)
        return cls(resref=resref, flags=flags,
                   charges1=charges1, charges2=charges2, charges3=charges3,
                   unknown=unknown)

    def _write(self, w: BinaryWriter) -> None:
        w.write_resref(self.resref)
        w.write_uint16(self.flags)
        w.write_uint16(self.charges1)
        w.write_uint16(self.charges2)
        w.write_uint16(self.charges3)
        w.write_bytes(self.unknown[:4].ljust(4, b"\x00"))

    def to_json(self) -> dict:
        d: dict = {"resref": self.resref}
        if self.flags:    d["flags"]    = self.flags
        if self.charges1: d["charges1"] = self.charges1
        if self.charges2: d["charges2"] = self.charges2
        if self.charges3: d["charges3"] = self.charges3
        return d

    @classmethod
    def from_json(cls, d: dict) -> "CreItem":
        return cls(resref=d.get("resref",""), flags=d.get("flags",0),
                   charges1=d.get("charges1",0), charges2=d.get("charges2",0),
                   charges3=d.get("charges3",0))


# ---------------------------------------------------------------------------
# CRE header  — V1 / V9
# ---------------------------------------------------------------------------

@dataclass
class CreHeader:
    """
    Header for CRE V1.0 creatures (BG1, BG2, BGEE).

    Layout verified against IESDP.  All field offsets are absolute from
    the start of the file (including the 8-byte signature/version prefix).
    """
    # -- Identity --
    name:               StrRef   = StrRef(0xFFFFFFFF)
    tooltip:            StrRef   = StrRef(0xFFFFFFFF)
    flags:              int   = CreFlag.NONE
    xp_value:           int   = 0
    xp:                 int   = 0
    gold:               int   = 0
    status_flags:       int   = 0
    current_hp:         int   = 1
    max_hp:             int   = 1
    animation_id:       int   = 0
    metal_color:        int   = 0
    minor_color:        int   = 0
    major_color:        int   = 0
    skin_color:         int   = 0
    leather_color:      int   = 0
    armor_color:        int   = 0
    hair_color:         int   = 0
    eff_version:        int   = 0   # 0=inline V1, 1=EFF V2.0
    small_portrait:     str   = ""
    large_portrait:     str   = ""
    reputation:         int   = 10
    hide_in_shadows:    int   = 0

    # -- AC --
    ac_base:            int   = 10
    ac_effective:       int   = 10   # effective AC (natural + modifiers combined)
    ac_crush:           int   = 0
    ac_missile:         int   = 0
    ac_pierce:          int   = 0
    ac_slash:           int   = 0

    # -- Combat --
    thac0:              int   = 20
    attacks:            int   = 1
    save_death:         int   = 20
    save_wands:         int   = 20
    save_poly:          int   = 20
    save_breath:        int   = 20
    save_spells:        int   = 20

    # -- Resistances --
    resist_fire:        int   = 0
    resist_cold:        int   = 0
    resist_electricity: int   = 0
    resist_acid:        int   = 0
    resist_magic:       int   = 0
    resist_magic_fire:  int   = 0
    resist_magic_cold:  int   = 0
    resist_slash:       int   = 0
    resist_crush:       int   = 0
    resist_pierce:      int   = 0
    resist_missile:     int   = 0

    # -- Skills --
    detect_illusions:   int   = 0
    set_traps:          int   = 0
    lore:               int   = 0
    lock_picking:       int   = 0
    move_silently:      int   = 0
    find_traps:         int   = 0
    pick_pockets:       int   = 0
    fatigue:            int   = 0
    intoxication:       int   = 0
    luck:               int   = 0

    # -- Proficiencies --
    large_sword_prof:   int   = 0
    small_sword_prof:   int   = 0
    bow_prof:           int   = 0
    spear_prof:         int   = 0
    blunt_prof:         int   = 0
    spiked_prof:        int   = 0
    axe_prof:           int   = 0
    missile_prof:       int   = 0
    unknown_profs:      bytes = b"\x00" * 12   # 0x0076..0x0081 (12 bytes)

    # -- Tracking --
    turn_undead_level:  int   = 0              # 0x0082
    tracking:           int   = 0              # 0x0083
    tracking_target:    bytes = b"\x00" * 32   # 0x0084: 32-byte char array

    # -- Sound / voice --
    soundset:           List[StrRef] = field(default_factory=lambda: [StrRef(0xFFFFFFFF)] * 100)  # 0x00A4: 100 × uint32 strrefs

    # -- Character --
    level_1:            int   = 0
    level_2:            int   = 0
    level_3:            int   = 0
    sex:                int   = Gender.MALE
    str:                int   = 9
    str_extra:          int   = 0
    int:                int   = 9
    wis:                int   = 9
    dex:                int   = 9
    con:                int   = 9
    cha:                int   = 9
    morale:             int   = 10
    morale_break:       int   = 5
    racial_enemy:       int   = 0
    morale_recovery:    int   = 0
    kit:                int   = 0
    override_script:    str   = ""
    class_script:       str   = ""
    race_script:        str   = ""
    general_script:     str   = ""
    default_script:     str   = ""
    enemy:              int   = 0
    general:            int   = 0
    race:               int   = Race.HUMAN
    klass:              int   = Class.FIGHTER
    specific:           int   = 0
    gender:             int   = Gender.MALE
    object_refs:        bytes = b"\x00" * 5
    alignment:          int   = Alignment.TRUE_NEUTRAL
    global_actor_enum:  int   = 0
    local_actor_enum:   int   = 0
    death_variable:     str   = ""

    # -- Offsets (managed by CreFile.to_bytes) --
    known_spells_offset:     int = 0
    known_spells_count:      int = 0
    memorise_info_offset:    int = 0
    memorise_info_count:     int = 0
    memorised_spells_offset: int = 0
    memorised_spells_count:  int = 0
    item_slots_offset:       int = 0
    items_offset:            int = 0
    items_count:             int = 0
    effects_offset:          int = 0
    effects_count:           int = 0
    dialog:                  str = ""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader) -> "CreHeader":
        """Read a V1.0 header from *r* (positioned after sig+ver)."""
        raw = r.read_bytes(HEADER_SIZE_V1 - 8)
        return cls._parse_fields(BinaryReader(raw))

    @classmethod
    def _read_common_prefix(cls, r: BinaryReader) -> dict:
        """Read the 616 bytes of fields shared by V1.0 and V9.0 (0x0008..0x026F).

        Returns a dict of kwargs suitable for passing to either header constructor.
        Both versions are identical in this region.
        """
        return dict(
            name                = StrRef(r.read_uint32()),
            tooltip             = StrRef(r.read_uint32()),
            flags               = r.read_uint32(),
            xp_value            = r.read_uint32(),
            xp                  = r.read_uint32(),
            gold                = r.read_uint32(),
            status_flags        = r.read_uint32(),
            current_hp          = r.read_uint16(),
            max_hp              = r.read_uint16(),
            animation_id        = r.read_uint32(),
            metal_color         = r.read_uint8(),
            minor_color         = r.read_uint8(),
            major_color         = r.read_uint8(),
            skin_color          = r.read_uint8(),
            leather_color       = r.read_uint8(),
            armor_color         = r.read_uint8(),
            hair_color          = r.read_uint8(),
            eff_version         = r.read_uint8(),
            small_portrait      = r.read_resref(),
            large_portrait      = r.read_resref(),
            reputation          = r.read_int8(),
            hide_in_shadows     = r.read_uint8(),
            ac_base             = r.read_int16(),
            ac_effective        = r.read_int16(),
            ac_crush            = r.read_int16(),
            ac_missile          = r.read_int16(),
            ac_pierce           = r.read_int16(),
            ac_slash            = r.read_int16(),
            thac0               = r.read_int8(),
            attacks             = r.read_uint8(),
            save_death          = r.read_int8(),
            save_wands          = r.read_int8(),
            save_poly           = r.read_int8(),
            save_breath         = r.read_int8(),
            save_spells         = r.read_int8(),
            resist_fire         = r.read_int8(),
            resist_cold         = r.read_int8(),
            resist_electricity  = r.read_int8(),
            resist_acid         = r.read_int8(),
            resist_magic        = r.read_int8(),
            resist_magic_fire   = r.read_int8(),
            resist_magic_cold   = r.read_int8(),
            resist_slash        = r.read_int8(),
            resist_crush        = r.read_int8(),
            resist_pierce       = r.read_int8(),
            resist_missile      = r.read_int8(),
            detect_illusions    = r.read_uint8(),
            set_traps           = r.read_uint8(),
            lore                = r.read_uint8(),
            lock_picking        = r.read_uint8(),
            move_silently       = r.read_uint8(),
            find_traps          = r.read_uint8(),
            pick_pockets        = r.read_uint8(),
            fatigue             = r.read_uint8(),
            intoxication        = r.read_uint8(),
            luck                = r.read_int8(),
            # -- proficiencies 0x006E..0x0081 --
            large_sword_prof    = r.read_uint8(),
            small_sword_prof    = r.read_uint8(),
            bow_prof            = r.read_uint8(),
            spear_prof          = r.read_uint8(),
            blunt_prof          = r.read_uint8(),
            spiked_prof         = r.read_uint8(),
            axe_prof            = r.read_uint8(),
            missile_prof        = r.read_uint8(),
            unknown_profs       = r.read_bytes(12),   # 0x0076..0x0081
            # -- 0x0082..0x0083 --
            turn_undead_level   = r.read_uint8(),
            tracking            = r.read_uint8(),
            # -- 0x0084..0x00A3: tracking target (32-byte char array) --
            tracking_target     = r.read_bytes(32),
            # -- 0x00A4..0x0233: soundset (100 × uint32 strrefs) --
            soundset            = [StrRef(r.read_uint32()) for _ in range(100)],
            # -- 0x0234..0x026F: levels, stats, kit, scripts --
            level_1             = r.read_uint8(),
            level_2             = r.read_uint8(),
            level_3             = r.read_uint8(),
            sex                 = r.read_uint8(),
            str                 = r.read_uint8(),
            str_extra           = r.read_uint8(),
            int                 = r.read_uint8(),
            wis                 = r.read_uint8(),
            dex                 = r.read_uint8(),
            con                 = r.read_uint8(),
            cha                 = r.read_uint8(),
            morale              = r.read_uint8(),
            morale_break        = r.read_uint8(),
            racial_enemy        = r.read_uint8(),
            morale_recovery     = r.read_uint16(),
            kit                 = r.read_uint32(),
            override_script     = r.read_resref(),
            class_script        = r.read_resref(),
            race_script         = r.read_resref(),
            general_script      = r.read_resref(),
            default_script      = r.read_resref(),
            # common prefix ends at 0x0270 — caller reads the version-specific tail
        )

    @classmethod
    def _parse_fields(cls, r: BinaryReader) -> "CreHeader":
        kw = cls._read_common_prefix(r)
        # -- V1.0 tail: 0x0270..0x02D3 (shared object identity + offsets) --
        kw.update(
            enemy               = r.read_uint8(),
            general             = r.read_uint8(),
            race                = r.read_uint8(),
            klass               = r.read_uint8(),
            specific            = r.read_uint8(),
            gender              = r.read_uint8(),
            object_refs         = r.read_bytes(5),
            alignment           = r.read_uint8(),
            global_actor_enum   = r.read_uint16(),
            local_actor_enum    = r.read_uint16(),
            death_variable      = r.read_string(32),
            known_spells_offset     = r.read_uint32(),
            known_spells_count      = r.read_uint32(),
            memorise_info_offset    = r.read_uint32(),
            memorise_info_count     = r.read_uint32(),
            memorised_spells_offset = r.read_uint32(),
            memorised_spells_count  = r.read_uint32(),
            item_slots_offset       = r.read_uint32(),
            items_offset            = r.read_uint32(),
            items_count             = r.read_uint32(),
            effects_offset          = r.read_uint32(),
            effects_count           = r.read_uint32(),
            dialog                  = r.read_resref(),
        )
        return cls(**kw)


    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _write_common_prefix(self, w: BinaryWriter) -> None:
        """Write the 616-byte common prefix shared by V1.0 and V9.0 (0x0008..0x026F)."""
        w.write_uint32(int(self.name))
        w.write_uint32(int(self.tooltip))
        w.write_uint32(self.flags)
        w.write_uint32(self.xp_value)
        w.write_uint32(self.xp)
        w.write_uint32(self.gold)
        w.write_uint32(self.status_flags)
        w.write_uint16(self.current_hp)
        w.write_uint16(self.max_hp)
        w.write_uint32(self.animation_id)
        w.write_uint8(self.metal_color)
        w.write_uint8(self.minor_color)
        w.write_uint8(self.major_color)
        w.write_uint8(self.skin_color)
        w.write_uint8(self.leather_color)
        w.write_uint8(self.armor_color)
        w.write_uint8(self.hair_color)
        w.write_uint8(self.eff_version)
        w.write_resref(self.small_portrait)
        w.write_resref(self.large_portrait)
        w.write_int8(self.reputation)
        w.write_uint8(self.hide_in_shadows)
        w.write_int16(self.ac_base)
        w.write_int16(self.ac_effective)
        w.write_int16(self.ac_crush)
        w.write_int16(self.ac_missile)
        w.write_int16(self.ac_pierce)
        w.write_int16(self.ac_slash)
        w.write_int8(self.thac0)
        w.write_uint8(self.attacks)
        w.write_int8(self.save_death)
        w.write_int8(self.save_wands)
        w.write_int8(self.save_poly)
        w.write_int8(self.save_breath)
        w.write_int8(self.save_spells)
        w.write_int8(self.resist_fire)
        w.write_int8(self.resist_cold)
        w.write_int8(self.resist_electricity)
        w.write_int8(self.resist_acid)
        w.write_int8(self.resist_magic)
        w.write_int8(self.resist_magic_fire)
        w.write_int8(self.resist_magic_cold)
        w.write_int8(self.resist_slash)
        w.write_int8(self.resist_crush)
        w.write_int8(self.resist_pierce)
        w.write_int8(self.resist_missile)
        w.write_uint8(self.detect_illusions)
        w.write_uint8(self.set_traps)
        w.write_uint8(self.lore)
        w.write_uint8(self.lock_picking)
        w.write_uint8(self.move_silently)
        w.write_uint8(self.find_traps)
        w.write_uint8(self.pick_pockets)
        w.write_uint8(self.fatigue)
        w.write_uint8(self.intoxication)
        w.write_int8(self.luck)
        w.write_uint8(self.large_sword_prof)
        w.write_uint8(self.small_sword_prof)
        w.write_uint8(self.bow_prof)
        w.write_uint8(self.spear_prof)
        w.write_uint8(self.blunt_prof)
        w.write_uint8(self.spiked_prof)
        w.write_uint8(self.axe_prof)
        w.write_uint8(self.missile_prof)
        w.write_bytes(self.unknown_profs[:12].ljust(12, b"\x00"))  # 0x0076..0x0081
        w.write_uint8(self.turn_undead_level)                       # 0x0082
        w.write_uint8(self.tracking)                                # 0x0083
        w.write_bytes(self.tracking_target[:32].ljust(32, b"\x00")) # 0x0084: 32-byte char array
        for s in (self.soundset + [StrRef(0xFFFFFFFF)] * 100)[:100]:  # 0x00A4: 100 × uint32 strrefs
            w.write_uint32(int(s))
        w.write_uint8(self.level_1)
        w.write_uint8(self.level_2)
        w.write_uint8(self.level_3)
        w.write_uint8(self.sex)
        w.write_uint8(self.str)
        w.write_uint8(self.str_extra)
        w.write_uint8(self.int)
        w.write_uint8(self.wis)
        w.write_uint8(self.dex)
        w.write_uint8(self.con)
        w.write_uint8(self.cha)
        w.write_uint8(self.morale)
        w.write_uint8(self.morale_break)
        w.write_uint8(self.racial_enemy)
        w.write_uint16(self.morale_recovery)
        w.write_uint32(self.kit)
        w.write_resref(self.override_script)
        w.write_resref(self.class_script)
        w.write_resref(self.race_script)
        w.write_resref(self.general_script)
        w.write_resref(self.default_script)
        # common prefix ends at 0x0270

    def _write_shared_tail(self, w: BinaryWriter) -> None:
        """Write the shared object-identity + offsets tail (present in both V1.0 and V9.0)."""
        w.write_uint8(self.enemy)
        w.write_uint8(self.general)
        w.write_uint8(self.race)
        w.write_uint8(self.klass)
        w.write_uint8(self.specific)
        w.write_uint8(self.gender)
        w.write_bytes(self.object_refs[:5].ljust(5, b"\x00"))
        w.write_uint8(self.alignment)
        w.write_uint16(self.global_actor_enum)
        w.write_uint16(self.local_actor_enum)
        dv = self.death_variable.encode("latin-1", errors="replace")[:32].ljust(32, b"\x00")
        w.write_bytes(dv)
        w.write_uint32(self.known_spells_offset)
        w.write_uint32(self.known_spells_count)
        w.write_uint32(self.memorise_info_offset)
        w.write_uint32(self.memorise_info_count)
        w.write_uint32(self.memorised_spells_offset)
        w.write_uint32(self.memorised_spells_count)
        w.write_uint32(self.item_slots_offset)
        w.write_uint32(self.items_offset)
        w.write_uint32(self.items_count)
        w.write_uint32(self.effects_offset)
        w.write_uint32(self.effects_count)
        w.write_resref(self.dialog)

    def _write(self, w: BinaryWriter) -> None:
        """Write the complete V1.0 header (724 bytes, not including sig+ver)."""
        self._write_common_prefix(w)
        self._write_shared_tail(w)
        w.write_uint8(self.leather_color)
        w.write_uint8(self.armor_color)
        w.write_uint8(self.hair_color)
        w.write_uint8(self.eff_version)


# ---------------------------------------------------------------------------
# CRE header  — V9.0  (IWD, IWD:HoW, IWD:TotL)
# ---------------------------------------------------------------------------

@dataclass
class CreHeaderV9(CreHeader):
    """
    Header for CRE V9.0 creatures (IWD, IWD:HoW, IWD:TotL).

    V9.0 shares the common prefix (0x0008–0x026F) with V1.0 exactly, but
    differs in the proficiency names at 0x006E–0x0081 and diverges entirely
    after the five script resrefs at 0x0270, inserting 104 bytes of
    IWD-specific fields before the shared object-identity / offset tail.

    Proficiency fields at 0x006E–0x0081 (stored in parent slots):
      large_sword_prof  → large swords
      small_sword_prof  → small swords
      bow_prof          → bows
      spear_prof        → spears
      blunt_prof        → axes        (NOTE: different from V1.0's blunt)
      spiked_prof       → missile     (NOTE: different from V1.0's spiked)
      axe_prof          → great swords
      missile_prof      → daggers
      unknown_profs[0]  → halberds
      unknown_profs[1]  → maces
      unknown_profs[2]  → flails
      unknown_profs[3]  → hammers
      unknown_profs[4]  → clubs
      unknown_profs[5]  → quarterstaves
      unknown_profs[6]  → crossbows
      unknown_profs[7..11] → unknown
    """

    # -- V9-specific block (0x0270..0x02D7) --
    visible:              int   = 1
    set_dead_var:         int   = 0     # set _DEAD variable on death
    set_kill_cnt:         int   = 0     # set KILL_<script>_CNT on death
    unknown_0273:         int   = 0
    internal_vars:        bytes = b"\x00" * 10   # 5 × word
    secondary_death_var:  bytes = b"\x00" * 32   # char array
    tertiary_death_var:   bytes = b"\x00" * 32   # char array
    save_location_flag:   int   = 0
    saved_x:              int   = 0
    saved_y:              int   = 0
    saved_orientation:    int   = 0
    unknown_02c6:         bytes = b"\x00" * 18

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader) -> "CreHeaderV9":
        """Read a V9.0 header from *r* (positioned after sig+ver)."""
        raw = r.read_bytes(HEADER_SIZE_V9 - 8)
        return cls._parse_fields(BinaryReader(raw))

    @classmethod
    def _parse_fields(cls, r: BinaryReader) -> "CreHeaderV9":
        kw = CreHeader._read_common_prefix(r)   # 0x0008..0x026F (616 bytes)

        # -- V9-specific block: 0x0270..0x02D7 (104 bytes) --
        kw.update(
            visible             = r.read_uint8(),
            set_dead_var        = r.read_uint8(),
            set_kill_cnt        = r.read_uint8(),
            unknown_0273        = r.read_uint8(),
            internal_vars       = r.read_bytes(10),
            secondary_death_var = r.read_bytes(32),
            tertiary_death_var  = r.read_bytes(32),
            save_location_flag  = r.read_uint16(),
            saved_x             = r.read_uint16(),
            saved_y             = r.read_uint16(),
            saved_orientation   = r.read_uint16(),
            unknown_02c6        = r.read_bytes(18),
        )

        # -- Shared tail: 0x02D8..0x033B --
        kw.update(
            enemy               = r.read_uint8(),
            general             = r.read_uint8(),
            race                = r.read_uint8(),
            klass               = r.read_uint8(),
            specific            = r.read_uint8(),
            gender              = r.read_uint8(),
            object_refs         = r.read_bytes(5),
            alignment           = r.read_uint8(),
            global_actor_enum   = r.read_uint16(),
            local_actor_enum    = r.read_uint16(),
            death_variable      = r.read_string(32),
            known_spells_offset     = r.read_uint32(),
            known_spells_count      = r.read_uint32(),
            memorise_info_offset    = r.read_uint32(),
            memorise_info_count     = r.read_uint32(),
            memorised_spells_offset = r.read_uint32(),
            memorised_spells_count  = r.read_uint32(),
            item_slots_offset       = r.read_uint32(),
            items_offset            = r.read_uint32(),
            items_count             = r.read_uint32(),
            effects_offset          = r.read_uint32(),
            effects_count           = r.read_uint32(),
            dialog                  = r.read_resref(),
        )
        return cls(**kw)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _write(self, w: BinaryWriter) -> None:
        """Write the complete V9.0 header (820 bytes, not including sig+ver)."""
        self._write_common_prefix(w)            # 0x0008..0x026F

        # -- V9-specific block: 0x0270..0x02D7 --
        w.write_uint8(self.visible)
        w.write_uint8(self.set_dead_var)
        w.write_uint8(self.set_kill_cnt)
        w.write_uint8(self.unknown_0273)
        w.write_bytes(self.internal_vars[:10].ljust(10, b"\x00"))
        w.write_bytes(self.secondary_death_var[:32].ljust(32, b"\x00"))
        w.write_bytes(self.tertiary_death_var[:32].ljust(32, b"\x00"))
        w.write_uint16(self.save_location_flag)
        w.write_uint16(self.saved_x)
        w.write_uint16(self.saved_y)
        w.write_uint16(self.saved_orientation)
        w.write_bytes(self.unknown_02c6[:18].ljust(18, b"\x00"))

        self._write_shared_tail(w)              # 0x02D8..0x033B


# ---------------------------------------------------------------------------
# PST V1.2 header
# ---------------------------------------------------------------------------

@dataclass
class CreHeaderV12:
    """
    Header for V1.2 (Planescape: Torment) creatures.

    PST deviates significantly from V1:
    - Primary stats include **Lore** in place of the BG Wisdom role; a
      separate ``current_lore`` tracks the creature's current lore value.
    - No kit field; no HLA combat feats.
    - Fewer script slots (override + default only — no class/race/general).
    - Larger soundset (more voice entries).
    - Morality/faction fields differ in meaning.
    - Different colour layout (more granular, 10 colour slots).
    - Overlay data for PST's unique mortuary / tattoo-display system.
    """

    # -- Identity --
    name:               StrRef   = StrRef(0xFFFFFFFF)
    tooltip:            StrRef   = StrRef(0xFFFFFFFF)
    flags:              int   = CreFlag.NONE
    xp_value:           int   = 0
    xp:                 int   = 0
    gold:               int   = 0
    status_flags:       int   = 0
    current_hp:         int   = 1
    max_hp:             int   = 1
    animation_id:       int   = 0

    # PST has 10 named colour slots
    color1:             int   = 0
    color2:             int   = 0
    color3:             int   = 0
    color4:             int   = 0
    color5:             int   = 0
    color6:             int   = 0
    color7:             int   = 0

    eff_version:        int   = 0
    small_portrait:     str   = ""
    large_portrait:     str   = ""
    reputation:         int   = 10
    hide_in_shadows:    int   = 0

    # -- AC --
    ac_base:            int   = 10
    ac_crush:           int   = 0
    ac_missile:         int   = 0
    ac_pierce:          int   = 0
    ac_slash:           int   = 0

    # -- Combat --
    thac0:              int   = 20
    attacks:            int   = 1
    save_death:         int   = 20
    save_wands:         int   = 20
    save_poly:          int   = 20
    save_breath:        int   = 20
    save_spells:        int   = 20

    # -- Resistances --
    resist_fire:        int   = 0
    resist_cold:        int   = 0
    resist_electricity: int   = 0
    resist_acid:        int   = 0
    resist_magic:       int   = 0
    resist_magic_fire:  int   = 0
    resist_magic_cold:  int   = 0
    resist_slash:       int   = 0
    resist_crush:       int   = 0
    resist_pierce:      int   = 0
    resist_missile:     int   = 0

    # -- Skills --
    detect_illusions:   int   = 0
    set_traps:          int   = 0
    lore:               int   = 0          # PST: primary stat (like WIS in BG)
    lock_picking:       int   = 0
    move_silently:      int   = 0
    find_traps:         int   = 0
    pick_pockets:       int   = 0
    fatigue:            int   = 0
    intoxication:       int   = 0
    luck:               int   = 0
    # PST-specific proficiencies (fist / edged / hammer / axe / club / misc)
    fist_prof:          int   = 0
    edged_prof:         int   = 0
    hammer_prof:        int   = 0
    axe_prof:           int   = 0
    club_prof:          int   = 0
    misc_prof:          int   = 0
    unknown_profs:      bytes = b"\x00" * 10  # 10 additional prof bytes in PST

    # -- Tracking --
    tracking:           int   = 0
    tracking_target:    StrRef = StrRef(0xFFFFFFFF)

    soundset:           List[StrRef] = field(default_factory=lambda: [StrRef(0xFFFFFFFF)] * 25)  # 25 × uint32 strrefs

    # -- Character --
    level_1:            int   = 0
    level_2:            int   = 0
    level_3:            int   = 0
    sex:                int   = Gender.MALE
    str:                int   = 9
    str_extra:          int   = 0
    int:                int   = 9
    wis:                int   = 9   # still present; used differently in PST
    dex:                int   = 9
    con:                int   = 9
    cha:                int   = 9
    current_lore:       int   = 0   # PST-specific: current lore points
    morale:             int   = 10
    morale_break:       int   = 5
    racial_enemy:       int   = 0
    morale_recovery:    int   = 0

    # PST has no kit field; uses faction/team instead
    faction:            int   = 0
    team:               int   = 0

    override_script:    str   = ""   # PST only has override + default
    default_script:     str   = ""
    enemy:              int   = 0
    general:            int   = 0
    race:               int   = Race.HUMAN
    klass:              int   = Class.FIGHTER
    specific:           int   = 0
    gender:             int   = Gender.MALE
    object_refs:        bytes = b"\x00" * 5
    alignment:          int   = Alignment.TRUE_NEUTRAL
    global_actor_enum:  int   = 0
    local_actor_enum:   int   = 0
    death_variable:     str   = ""

    # -- PST overlay system --
    # 7 × uint32 overlay resref indices + 7 × uint32 overlay flags
    # stored as raw bytes to avoid 14 more fields for rarely-edited data
    overlay_data:       bytes = b"\x00" * 56

    # -- Offsets (managed by CreFileV12.to_bytes) --
    known_spells_offset:     int = 0
    known_spells_count:      int = 0
    memorise_info_offset:    int = 0
    memorise_info_count:     int = 0
    memorised_spells_offset: int = 0
    memorised_spells_count:  int = 0
    item_slots_offset:       int = 0
    items_offset:            int = 0
    items_count:             int = 0
    effects_offset:          int = 0
    effects_count:           int = 0
    dialog:                  str = ""

    # -- Remaining unknown / internal V1.2 fields --
    v12_tail: bytes = b""   # bytes from end of named fields to HEADER_SIZE_V12

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader) -> "CreHeaderV12":
        name            = StrRef(r.read_uint32())
        tooltip         = StrRef(r.read_uint32())
        flags           = r.read_uint32()
        xp_value        = r.read_uint32()
        xp              = r.read_uint32()
        gold            = r.read_uint32()
        status_flags    = r.read_uint32()
        current_hp      = r.read_uint16()
        max_hp          = r.read_uint16()
        animation_id    = r.read_uint32()
        # 7 colour bytes + 3 padding
        color1          = r.read_uint8()
        color2          = r.read_uint8()
        color3          = r.read_uint8()
        color4          = r.read_uint8()
        color5          = r.read_uint8()
        color6          = r.read_uint8()
        color7          = r.read_uint8()
        eff_version     = r.read_uint8()
        small_portrait  = r.read_resref()
        large_portrait  = r.read_resref()
        reputation      = r.read_int8()
        hide_in_shadows = r.read_uint8()
        ac_base         = r.read_int16()
        ac_crush        = r.read_int16()
        ac_missile      = r.read_int16()
        ac_pierce       = r.read_int16()
        ac_slash        = r.read_int16()
        thac0           = r.read_int8()
        attacks         = r.read_uint8()
        save_death      = r.read_int8()
        save_wands      = r.read_int8()
        save_poly       = r.read_int8()
        save_breath     = r.read_int8()
        save_spells     = r.read_int8()
        resist_fire         = r.read_int8()
        resist_cold         = r.read_int8()
        resist_electricity  = r.read_int8()
        resist_acid         = r.read_int8()
        resist_magic        = r.read_int8()
        resist_magic_fire   = r.read_int8()
        resist_magic_cold   = r.read_int8()
        resist_slash        = r.read_int8()
        resist_crush        = r.read_int8()
        resist_pierce       = r.read_int8()
        resist_missile      = r.read_int8()
        detect_illusions    = r.read_uint8()
        set_traps           = r.read_uint8()
        lore                = r.read_uint8()
        lock_picking        = r.read_uint8()
        move_silently       = r.read_uint8()
        find_traps          = r.read_uint8()
        pick_pockets        = r.read_uint8()
        fatigue             = r.read_uint8()
        intoxication        = r.read_uint8()
        luck                = r.read_int8()
        fist_prof           = r.read_uint8()
        edged_prof          = r.read_uint8()
        hammer_prof         = r.read_uint8()
        axe_prof            = r.read_uint8()
        club_prof           = r.read_uint8()
        misc_prof           = r.read_uint8()
        unknown_profs       = r.read_bytes(10)
        tracking            = r.read_uint8()
        r.skip(3)
        tracking_target     = r.read_uint32()
        soundset            = [StrRef(r.read_uint32()) for _ in range(25)]
        level_1             = r.read_uint8()
        level_2             = r.read_uint8()
        level_3             = r.read_uint8()
        sex                 = r.read_uint8()
        str_                = r.read_uint8()
        str_extra           = r.read_uint8()
        int_                = r.read_uint8()
        wis                 = r.read_uint8()
        dex                 = r.read_uint8()
        con                 = r.read_uint8()
        cha                 = r.read_uint8()
        current_lore        = r.read_uint8()
        morale              = r.read_uint8()
        morale_break        = r.read_uint8()
        racial_enemy        = r.read_uint8()
        morale_recovery     = r.read_uint16()
        faction             = r.read_uint8()
        team                = r.read_uint8()
        override_script     = r.read_resref()
        default_script      = r.read_resref()
        enemy               = r.read_uint8()
        general             = r.read_uint8()
        race                = r.read_uint8()
        klass               = r.read_uint8()
        specific            = r.read_uint8()
        gender              = r.read_uint8()
        object_refs         = r.read_bytes(5)
        alignment           = r.read_uint8()
        global_actor_enum   = r.read_uint16()
        local_actor_enum    = r.read_uint16()
        death_variable      = r.read_string(32)
        overlay_data        = r.read_bytes(56)
        known_spells_offset     = r.read_uint32()
        known_spells_count      = r.read_uint32()
        memorise_info_offset    = r.read_uint32()
        memorise_info_count     = r.read_uint32()
        memorised_spells_offset = r.read_uint32()
        memorised_spells_count  = r.read_uint32()
        item_slots_offset       = r.read_uint32()
        items_offset            = r.read_uint32()
        items_count             = r.read_uint32()
        effects_offset          = r.read_uint32()
        effects_count           = r.read_uint32()
        dialog                  = r.read_resref()

        # Capture any remaining header bytes up to HEADER_SIZE_V12
        consumed = r.pos - 8   # subtract sig+ver already read by caller
        tail_len = HEADER_SIZE_V12 - consumed
        v12_tail = r.read_bytes(tail_len) if tail_len > 0 else b""

        return cls(
            name=name, tooltip=tooltip, flags=flags,
            xp_value=xp_value, xp=xp, gold=gold,
            status_flags=status_flags, current_hp=current_hp, max_hp=max_hp,
            animation_id=animation_id,
            color1=color1, color2=color2, color3=color3, color4=color4,
            color5=color5, color6=color6, color7=color7,
            eff_version=eff_version,
            small_portrait=small_portrait, large_portrait=large_portrait,
            reputation=reputation, hide_in_shadows=hide_in_shadows,
            ac_base=ac_base, ac_crush=ac_crush, ac_missile=ac_missile,
            ac_pierce=ac_pierce, ac_slash=ac_slash,
            thac0=thac0, attacks=attacks,
            save_death=save_death, save_wands=save_wands, save_poly=save_poly,
            save_breath=save_breath, save_spells=save_spells,
            resist_fire=resist_fire, resist_cold=resist_cold,
            resist_electricity=resist_electricity, resist_acid=resist_acid,
            resist_magic=resist_magic, resist_magic_fire=resist_magic_fire,
            resist_magic_cold=resist_magic_cold, resist_slash=resist_slash,
            resist_crush=resist_crush, resist_pierce=resist_pierce,
            resist_missile=resist_missile,
            detect_illusions=detect_illusions, set_traps=set_traps,
            lore=lore, lock_picking=lock_picking, move_silently=move_silently,
            find_traps=find_traps, pick_pockets=pick_pockets,
            fatigue=fatigue, intoxication=intoxication, luck=luck,
            fist_prof=fist_prof, edged_prof=edged_prof, hammer_prof=hammer_prof,
            axe_prof=axe_prof, club_prof=club_prof, misc_prof=misc_prof,
            unknown_profs=unknown_profs,
            turn_undead_level=turn_undead_level, tracking=tracking,
            tracking_target=tracking_target,
            soundset=soundset,
            level_1=level_1, level_2=level_2, level_3=level_3,
            sex=sex, str=str_, str_extra=str_extra,
            int=int_, wis=wis, dex=dex, con=con, cha=cha,
            current_lore=current_lore,
            morale=morale, morale_break=morale_break,
            racial_enemy=racial_enemy, morale_recovery=morale_recovery,
            faction=faction, team=team,
            override_script=override_script, default_script=default_script,
            enemy=enemy, general=general, race=race, klass=klass,
            specific=specific, gender=gender,
            object_refs=object_refs, alignment=alignment,
            global_actor_enum=global_actor_enum, local_actor_enum=local_actor_enum,
            death_variable=death_variable,
            overlay_data=overlay_data,
            known_spells_offset=known_spells_offset,
            known_spells_count=known_spells_count,
            memorise_info_offset=memorise_info_offset,
            memorise_info_count=memorise_info_count,
            memorised_spells_offset=memorised_spells_offset,
            memorised_spells_count=memorised_spells_count,
            item_slots_offset=item_slots_offset,
            items_offset=items_offset, items_count=items_count,
            effects_offset=effects_offset, effects_count=effects_count,
            dialog=dialog,
            v12_tail=v12_tail,
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint32(int(self.name))
        w.write_uint32(int(self.tooltip))
        w.write_uint32(self.flags)
        w.write_uint32(self.xp_value)
        w.write_uint32(self.xp)
        w.write_uint32(self.gold)
        w.write_uint32(self.status_flags)
        w.write_uint16(self.current_hp)
        w.write_uint16(self.max_hp)
        w.write_uint32(self.animation_id)
        w.write_uint8(self.color1)
        w.write_uint8(self.color2)
        w.write_uint8(self.color3)
        w.write_uint8(self.color4)
        w.write_uint8(self.color5)
        w.write_uint8(self.color6)
        w.write_uint8(self.color7)
        w.write_uint8(self.eff_version)
        w.write_resref(self.small_portrait)
        w.write_resref(self.large_portrait)
        w.write_int8(self.reputation)
        w.write_uint8(self.hide_in_shadows)
        w.write_int16(self.ac_base)
        w.write_int16(self.ac_crush)
        w.write_int16(self.ac_missile)
        w.write_int16(self.ac_pierce)
        w.write_int16(self.ac_slash)
        w.write_int8(self.thac0)
        w.write_uint8(self.attacks)
        w.write_int8(self.save_death)
        w.write_int8(self.save_wands)
        w.write_int8(self.save_poly)
        w.write_int8(self.save_breath)
        w.write_int8(self.save_spells)
        w.write_int8(self.resist_fire)
        w.write_int8(self.resist_cold)
        w.write_int8(self.resist_electricity)
        w.write_int8(self.resist_acid)
        w.write_int8(self.resist_magic)
        w.write_int8(self.resist_magic_fire)
        w.write_int8(self.resist_magic_cold)
        w.write_int8(self.resist_slash)
        w.write_int8(self.resist_crush)
        w.write_int8(self.resist_pierce)
        w.write_int8(self.resist_missile)
        w.write_uint8(self.detect_illusions)
        w.write_uint8(self.set_traps)
        w.write_uint8(self.lore)
        w.write_uint8(self.lock_picking)
        w.write_uint8(self.move_silently)
        w.write_uint8(self.find_traps)
        w.write_uint8(self.pick_pockets)
        w.write_uint8(self.fatigue)
        w.write_uint8(self.intoxication)
        w.write_int8(self.luck)
        w.write_uint8(self.fist_prof)
        w.write_uint8(self.edged_prof)
        w.write_uint8(self.hammer_prof)
        w.write_uint8(self.axe_prof)
        w.write_uint8(self.club_prof)
        w.write_uint8(self.misc_prof)
        w.write_bytes(self.unknown_profs[:10].ljust(10, b"\x00"))
        w.write_uint8(self.tracking)
        w.write_padding(3)
        w.write_uint32(self.tracking_target)
        for s in (self.soundset + [StrRef(0xFFFFFFFF)] * 25)[:25]:  # 25 × uint32 strrefs
            w.write_uint32(int(s))
        w.write_uint8(self.level_1)
        w.write_uint8(self.level_2)
        w.write_uint8(self.level_3)
        w.write_uint8(self.sex)
        w.write_uint8(self.str)
        w.write_uint8(self.str_extra)
        w.write_uint8(self.int)
        w.write_uint8(self.wis)
        w.write_uint8(self.dex)
        w.write_uint8(self.con)
        w.write_uint8(self.cha)
        w.write_uint8(self.current_lore)
        w.write_uint8(self.morale)
        w.write_uint8(self.morale_break)
        w.write_uint8(self.racial_enemy)
        w.write_uint16(self.morale_recovery)
        w.write_uint8(self.faction)
        w.write_uint8(self.team)
        w.write_resref(self.override_script)
        w.write_resref(self.default_script)
        w.write_uint8(self.enemy)
        w.write_uint8(self.general)
        w.write_uint8(self.race)
        w.write_uint8(self.klass)
        w.write_uint8(self.specific)
        w.write_uint8(self.gender)
        w.write_bytes(self.object_refs[:5].ljust(5, b"\x00"))
        w.write_uint8(self.alignment)
        w.write_uint16(self.global_actor_enum)
        w.write_uint16(self.local_actor_enum)
        dv = self.death_variable.encode("latin-1", errors="replace")[:32].ljust(32, b"\x00")
        w.write_bytes(dv)
        w.write_bytes(self.overlay_data[:56].ljust(56, b"\x00"))
        w.write_uint32(self.known_spells_offset)
        w.write_uint32(self.known_spells_count)
        w.write_uint32(self.memorise_info_offset)
        w.write_uint32(self.memorise_info_count)
        w.write_uint32(self.memorised_spells_offset)
        w.write_uint32(self.memorised_spells_count)
        w.write_uint32(self.item_slots_offset)
        w.write_uint32(self.items_offset)
        w.write_uint32(self.items_count)
        w.write_uint32(self.effects_offset)
        w.write_uint32(self.effects_count)
        w.write_resref(self.dialog)
        # Tail
        tail_space = HEADER_SIZE_V12 - w.pos + 8  # +8 for sig+ver written outside
        if tail_space > 0:
            tail = self.v12_tail[:tail_space].ljust(tail_space, b"\x00")
            w.write_bytes(tail)


# ---------------------------------------------------------------------------
# Shared sub-array I/O helper
# ---------------------------------------------------------------------------

def _read_subarrays(
    r: BinaryReader,
    header,
    slot_count: int,
    use_v2_effects: bool,
):
    """Read all CRE sub-arrays given a parsed header and slot count.

    Offset/count fields may be ``0xFFFFFFFF`` when a creature has no data
    for that sub-array (e.g. a non-spellcasting guard has no spell slots).
    These are treated as empty lists.
    """
    ABSENT = 0xFFFFFFFF

    known_spells: List[KnownSpell] = []
    if header.known_spells_count and header.known_spells_count != ABSENT \
            and header.known_spells_offset != ABSENT:
        r.seek(header.known_spells_offset)
        for _ in range(header.known_spells_count):
            known_spells.append(KnownSpell._read(r))

    memorise_info: List[MemoriseInfo] = []
    if header.memorise_info_count and header.memorise_info_count != ABSENT \
            and header.memorise_info_offset != ABSENT:
        r.seek(header.memorise_info_offset)
        for _ in range(header.memorise_info_count):
            memorise_info.append(MemoriseInfo._read(r))

    memorised_spells: List[MemorisedSpell] = []
    if header.memorised_spells_count and header.memorised_spells_count != ABSENT \
            and header.memorised_spells_offset != ABSENT:
        r.seek(header.memorised_spells_offset)
        for _ in range(header.memorised_spells_count):
            memorised_spells.append(MemorisedSpell._read(r))

    raw_slots = [0xFFFF] * slot_count
    if header.item_slots_offset != ABSENT:
        r.seek(header.item_slots_offset)
        raw_slots = [r.read_uint16() for _ in range(slot_count)]

    items: List[CreItem] = []
    if header.items_count and header.items_count != ABSENT \
            and header.items_offset != ABSENT:
        r.seek(header.items_offset)
        for _ in range(header.items_count):
            items.append(CreItem._read(r))

    effects: List[EffectBlock] = []
    if header.effects_count and header.effects_count != ABSENT \
            and header.effects_offset != ABSENT:
        r.seek(header.effects_offset)
        for _ in range(header.effects_count):
            if use_v2_effects:
                effects.append(EffectBlock._read_v2(r))
            else:
                effects.append(EffectBlock._read_v1(r))

    # Capture any trailing bytes after the slot array (e.g. 4-byte tool-written tail).
    tail = b""
    if header.item_slots_offset != ABSENT:
        expected_end = header.item_slots_offset + slot_count * 2
        if expected_end < r.size:
            r.seek(expected_end)
            tail = r.read_bytes(r.size - expected_end)

    return known_spells, memorise_info, memorised_spells, raw_slots, items, effects, tail


def _write_subarrays(
    header,
    slot_enum,
    slot_count: int,
    known_spells: List[KnownSpell],
    memorise_info: List[MemoriseInfo],
    memorised_spells: List[MemorisedSpell],
    slots: Dict,
    items: List[CreItem],
    effects: List[EffectBlock],
    use_v2_effects: bool,
    header_size: int,
) -> bytes:
    """Build all sub-array bytes and patch header offset fields."""
    w_known   = BinaryWriter()
    w_meminfo = BinaryWriter()
    w_memspl  = BinaryWriter()
    w_slots   = BinaryWriter()
    w_items   = BinaryWriter()
    w_effects = BinaryWriter()

    for ks in known_spells:   ks._write(w_known)
    for mi in memorise_info:  mi._write(w_meminfo)
    for ms in memorised_spells: ms._write(w_memspl)

    for i in range(slot_count):
        try:
            val = slots.get(slot_enum(i), 0xFFFF)
        except ValueError:
            val = 0xFFFF
        w_slots.write_uint16(val)

    for item in items:   item._write(w_items)
    for eff in effects:
        if use_v2_effects:
            eff._write_v2(w_effects)
        else:
            eff._write_v1(w_effects)

    known_off   = header_size
    meminfo_off = known_off   + w_known.pos
    memspl_off  = meminfo_off + w_meminfo.pos
    items_off   = memspl_off  + w_memspl.pos
    slots_off   = items_off   + w_items.pos
    effects_off = slots_off   + slot_count * 2

    header.known_spells_offset      = known_off
    header.known_spells_count       = len(known_spells)
    header.memorise_info_offset     = meminfo_off
    header.memorise_info_count      = len(memorise_info)
    header.memorised_spells_offset  = memspl_off
    header.memorised_spells_count   = len(memorised_spells)
    header.item_slots_offset        = slots_off
    header.items_offset             = items_off
    header.items_count              = len(items)
    header.effects_offset           = effects_off if effects else items_off
    header.effects_count            = len(effects)

    return (w_known.to_bytes() + w_meminfo.to_bytes() + w_memspl.to_bytes()
            + w_items.to_bytes() + w_slots.to_bytes() + w_effects.to_bytes())


# ---------------------------------------------------------------------------
# CreFile  (V1 / V9)
# ---------------------------------------------------------------------------

class CreFile:
    """
    A complete V1 or V9 creature resource.

    :meth:`from_file` and :meth:`from_bytes` auto-detect the version and
    return a :class:`CreFileV12` instance for PST files, so you can call
    ``CreFile.from_file(path)`` unconditionally and use ``isinstance``
    checks where version-specific behaviour is needed.

    Attributes:
        header           — :class:`CreHeader`
        known_spells     — List[:class:`KnownSpell`]
        memorise_info    — List[:class:`MemoriseInfo`]
        memorised_spells — List[:class:`MemorisedSpell`]
        items            — List[:class:`CreItem`]
        slots            — Dict[:class:`SlotIndex`, int]  (0xFFFF = empty)
        effects          — List[:class:`EffectBlock`]
    """

    def __init__(
        self,
        header:           CreHeader,
        known_spells:     List[KnownSpell],
        memorise_info:    List[MemoriseInfo],
        memorised_spells: List[MemorisedSpell],
        items:            List[CreItem],
        slots:            Dict[SlotIndex, int],
        effects:          List[EffectBlock],
        version:          bytes = VERSION_V1,
        source_path:      Optional[Path] = None,
    ) -> None:
        self.header           = header
        self.known_spells     = known_spells
        self.memorise_info    = memorise_info
        self.memorised_spells = memorised_spells
        self.items            = items
        self.slots            = slots
        self.effects          = effects
        self.version          = version
        self.source_path      = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "CreFile":
        """
        Parse a CRE resource from raw bytes.

        Returns a :class:`CreFileV12` for PST V1.2 files.
        """
        r = BinaryReader(data)
        try:
            r.expect_signature(SIGNATURE)
            version = r.read_bytes(4)
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        if version == VERSION_V12:
            return CreFileV12._from_reader(r, data)
        if version not in (VERSION_V1, VERSION_V9):
            raise ValueError(f"Unsupported CRE version {version!r}.")

        if version == VERSION_V9:
            header = CreHeaderV9._read(r)
            hdr_size = HEADER_SIZE_V9
        else:
            header = CreHeader._read(r)
            hdr_size = HEADER_SIZE_V1
        use_v2 = (header.eff_version == 1)

        known_spells, memorise_info, memorised_spells, raw_slots, items, effects, tail = (
            _read_subarrays(r, header, SLOT_COUNT, use_v2)
        )

        slots: Dict[SlotIndex, int] = {}
        for slot in SlotIndex:
            if slot.value < SLOT_COUNT:
                slots[slot] = raw_slots[slot.value]

        cre = cls(header, known_spells, memorise_info, memorised_spells,
                   items, slots, effects, version=version)
        cre._subarray_tail = tail
        return cre

    @classmethod
    def from_file(cls, path: str | Path) -> "CreFile":
        """Read and parse a CRE file from disk."""
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        version    = self.version
        use_v2     = (self.header.eff_version == 1)
        hdr_size   = HEADER_SIZE_V9 if version == VERSION_V9 else HEADER_SIZE_V1

        sub_bytes = _write_subarrays(
            self.header, SlotIndex, SLOT_COUNT,
            self.known_spells, self.memorise_info, self.memorised_spells,
            self.slots, self.items, self.effects, use_v2, hdr_size,
        )

        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(version)
        self.header._write(w)
        w.write_bytes(sub_bytes)
        tail = getattr(self, '_subarray_tail', b"")
        if tail:
            w.write_bytes(tail)
        return w.to_bytes()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        h = self.header
        hd: dict = {
            "name": h.name.to_json(), "tooltip": h.tooltip.to_json(), "flags": h.flags,
            "xp_value": h.xp_value, "current_hp": h.current_hp,
            "max_hp": h.max_hp, "animation_id": h.animation_id,
            "race": h.race, "klass": h.klass, "gender": h.gender,
            "alignment": h.alignment,
            "level_1": h.level_1, "str": h.str, "int": h.int,
            "wis": h.wis, "dex": h.dex, "con": h.con, "cha": h.cha,
            "thac0": h.thac0, "ac_base": h.ac_base, "ac_effective": h.ac_effective,
            "attacks": h.attacks,
            "dialog": h.dialog,
        }
        # Sparse optional fields
        for attr, default in (
            ("xp",0),("gold",0),("level_2",0),("level_3",0),("str_extra",0),
            ("kit",0),("reputation",10),("status_flags",0),("morale",10),
            ("morale_break",5),("morale_recovery",0),("racial_enemy",0),
            ("lore",0),("hide_in_shadows",0),("death_variable",""),
            ("small_portrait",""),("large_portrait",""),
            ("save_death",20),("save_wands",20),("save_poly",20),
            ("save_breath",20),("save_spells",20),
            ("ac_crush",0),("ac_missile",0),("ac_pierce",0),("ac_slash",0),
            ("resist_fire",0),("resist_cold",0),("resist_electricity",0),
            ("resist_acid",0),("resist_magic",0),("resist_slash",0),
            ("resist_crush",0),("resist_pierce",0),("resist_missile",0),
        ):
            v = getattr(h, attr)
            if v != default:
                hd[attr] = v
        for attr in ("override_script","class_script","race_script",
                     "general_script","default_script"):
            if getattr(h, attr): hd[attr] = getattr(h, attr)
        for attr in ("metal_color","minor_color","major_color","skin_color",
                     "leather_color","armor_color","hair_color"):
            if getattr(h, attr): hd[attr] = getattr(h, attr)
        _NONE_SOUNDSET = [StrRef(0xFFFFFFFF)] * 100
        if h.soundset != _NONE_SOUNDSET:
            hd["soundset"] = [s.to_json() for s in h.soundset]
        # V9-specific fields
        if isinstance(h, CreHeaderV9):
            if h.visible != 1:
                hd["visible"] = h.visible
            for attr in ("set_dead_var", "set_kill_cnt", "save_location_flag",
                         "saved_x", "saved_y", "saved_orientation"):
                v = getattr(h, attr)
                if v: hd[attr] = v
            if h.secondary_death_var != b"\x00" * 32:
                hd["secondary_death_var"] = h.secondary_death_var.rstrip(b"\x00").decode("latin-1", errors="replace")
            if h.tertiary_death_var != b"\x00" * 32:
                hd["tertiary_death_var"] = h.tertiary_death_var.rstrip(b"\x00").decode("latin-1", errors="replace")

        slot_dict = {s.name: i for s, i in self.slots.items() if i != 0xFFFF}
        d: dict = {"format": "cre", "version": _version_str(self.version),
                   "header": hd}
        if slot_dict:           d["slots"]            = slot_dict
        if self.items:          d["items"]            = [i.to_json() for i in self.items]
        if self.known_spells:   d["known_spells"]     = [k.to_json() for k in self.known_spells]
        if self.memorise_info:  d["memorise_info"]    = [m.to_json() for m in self.memorise_info]
        if self.memorised_spells: d["memorised_spells"] = [m.to_json() for m in self.memorised_spells]
        if self.effects:        d["effects"]          = [e.to_json() for e in self.effects]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "CreFile":
        ver_str = d.get("version", "V1.0")
        if ver_str == "V1.2":
            return CreFileV12.from_json(d)
        version = VERSION_V9 if ver_str == "V9.0" else VERSION_V1
        hd = d.get("header", {})
        _raw_soundset = hd.get("soundset", None)
        if isinstance(_raw_soundset, list):
            _soundset = [StrRef.from_json(v) for v in _raw_soundset]
            # Pad/truncate to exactly 100
            _soundset = (_soundset + [StrRef(0xFFFFFFFF)] * 100)[:100]
        else:
            _soundset = [StrRef(0xFFFFFFFF)] * 100

        # Fields shared by both V1.0 and V9.0
        common = dict(
            name=StrRef.from_json(hd.get("name", 0xFFFFFFFF)), tooltip=StrRef.from_json(hd.get("tooltip", 0xFFFFFFFF)),
            flags=hd.get("flags", 0), xp_value=hd.get("xp_value", 0),
            xp=hd.get("xp", 0), gold=hd.get("gold", 0),
            status_flags=hd.get("status_flags", 0),
            current_hp=hd.get("current_hp", 1), max_hp=hd.get("max_hp", 1),
            animation_id=hd.get("animation_id", 0),
            metal_color=hd.get("metal_color", 0), minor_color=hd.get("minor_color", 0),
            major_color=hd.get("major_color", 0), skin_color=hd.get("skin_color", 0),
            leather_color=hd.get("leather_color", 0), armor_color=hd.get("armor_color", 0),
            hair_color=hd.get("hair_color", 0),
            eff_version=hd.get("eff_version", 0),
            small_portrait=hd.get("small_portrait", ""),
            large_portrait=hd.get("large_portrait", ""),
            reputation=hd.get("reputation", 10),
            hide_in_shadows=hd.get("hide_in_shadows", 0),
            ac_base=hd.get("ac_base", 10), ac_effective=hd.get("ac_effective", 10),
            ac_crush=hd.get("ac_crush", 0),
            ac_missile=hd.get("ac_missile", 0), ac_pierce=hd.get("ac_pierce", 0),
            ac_slash=hd.get("ac_slash", 0),
            thac0=hd.get("thac0", 20), attacks=hd.get("attacks", 1),
            save_death=hd.get("save_death", 20), save_wands=hd.get("save_wands", 20),
            save_poly=hd.get("save_poly", 20), save_breath=hd.get("save_breath", 20),
            save_spells=hd.get("save_spells", 20),
            resist_fire=hd.get("resist_fire", 0), resist_cold=hd.get("resist_cold", 0),
            resist_electricity=hd.get("resist_electricity", 0),
            resist_acid=hd.get("resist_acid", 0), resist_magic=hd.get("resist_magic", 0),
            resist_magic_fire=hd.get("resist_magic_fire", 0),
            resist_magic_cold=hd.get("resist_magic_cold", 0),
            resist_slash=hd.get("resist_slash", 0), resist_crush=hd.get("resist_crush", 0),
            resist_pierce=hd.get("resist_pierce", 0), resist_missile=hd.get("resist_missile", 0),
            detect_illusions=hd.get("detect_illusions", 0),
            set_traps=hd.get("set_traps", 0), lore=hd.get("lore", 0),
            lock_picking=hd.get("lock_picking", 0),
            move_silently=hd.get("move_silently", 0),
            find_traps=hd.get("find_traps", 0), pick_pockets=hd.get("pick_pockets", 0),
            fatigue=hd.get("fatigue", 0), intoxication=hd.get("intoxication", 0),
            luck=hd.get("luck", 0),
            large_sword_prof=hd.get("large_sword_prof", 0),
            small_sword_prof=hd.get("small_sword_prof", 0),
            bow_prof=hd.get("bow_prof", 0), spear_prof=hd.get("spear_prof", 0),
            blunt_prof=hd.get("blunt_prof", 0), spiked_prof=hd.get("spiked_prof", 0),
            axe_prof=hd.get("axe_prof", 0), missile_prof=hd.get("missile_prof", 0),
            unknown_profs=bytes.fromhex(hd["unknown_profs"]) if hd.get("unknown_profs") else b"\x00"*12,
            turn_undead_level=hd.get("turn_undead_level", 0),
            tracking=hd.get("tracking", 0),
            tracking_target=bytes.fromhex(hd["tracking_target"]) if hd.get("tracking_target") else b"\x00"*32,
            soundset=_soundset,
            level_1=hd.get("level_1", 0), level_2=hd.get("level_2", 0),
            level_3=hd.get("level_3", 0), sex=hd.get("sex", Gender.MALE),
            str=hd.get("str", 9), str_extra=hd.get("str_extra", 0),
            int=hd.get("int", 9), wis=hd.get("wis", 9),
            dex=hd.get("dex", 9), con=hd.get("con", 9), cha=hd.get("cha", 9),
            morale=hd.get("morale", 10), morale_break=hd.get("morale_break", 5),
            racial_enemy=hd.get("racial_enemy", 0),
            morale_recovery=hd.get("morale_recovery", 0),
            kit=hd.get("kit", 0),
            override_script=hd.get("override_script", ""),
            class_script=hd.get("class_script", ""),
            race_script=hd.get("race_script", ""),
            general_script=hd.get("general_script", ""),
            default_script=hd.get("default_script", ""),
            enemy=hd.get("enemy", 0), general=hd.get("general", 0),
            race=hd.get("race", Race.HUMAN), klass=hd.get("klass", Class.FIGHTER),
            specific=hd.get("specific", 0), gender=hd.get("gender", Gender.MALE),
            object_refs=bytes.fromhex(hd["object_refs"]) if hd.get("object_refs") else b"\x00"*5,
            alignment=hd.get("alignment", Alignment.TRUE_NEUTRAL),
            global_actor_enum=hd.get("global_actor_enum", 0),
            local_actor_enum=hd.get("local_actor_enum", 0),
            death_variable=hd.get("death_variable", ""),
            dialog=hd.get("dialog", ""),
        )

        if version == VERSION_V9:
            def _dv(key: str) -> bytes:
                v = hd.get(key, "")
                return v.encode("latin-1", errors="replace")[:32].ljust(32, b"\x00") if v else b"\x00"*32
            header: CreHeader = CreHeaderV9(
                **common,
                visible=hd.get("visible", 1),
                set_dead_var=hd.get("set_dead_var", 0),
                set_kill_cnt=hd.get("set_kill_cnt", 0),
                unknown_0273=hd.get("unknown_0273", 0),
                internal_vars=bytes.fromhex(hd["internal_vars"]) if hd.get("internal_vars") else b"\x00"*10,
                secondary_death_var=_dv("secondary_death_var"),
                tertiary_death_var=_dv("tertiary_death_var"),
                save_location_flag=hd.get("save_location_flag", 0),
                saved_x=hd.get("saved_x", 0),
                saved_y=hd.get("saved_y", 0),
                saved_orientation=hd.get("saved_orientation", 0),
                unknown_02c6=bytes.fromhex(hd["unknown_02c6"]) if hd.get("unknown_02c6") else b"\x00"*18,
            )
        else:
            header = CreHeader(**common)
        slots: Dict[SlotIndex, int] = {s: 0xFFFF for s in SlotIndex}
        for name, idx in d.get("slots", {}).items():
            try: slots[SlotIndex[name]] = idx
            except KeyError: pass
        return cls(
            header,
            [KnownSpell.from_json(k) for k in d.get("known_spells", [])],
            [MemoriseInfo.from_json(m) for m in d.get("memorise_info", [])],
            [MemorisedSpell.from_json(m) for m in d.get("memorised_spells", [])],
            [CreItem.from_json(i) for i in d.get("items", [])],
            slots,
            [EffectBlock.from_json(e) for e in d.get("effects", [])],
            version=version,
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "CreFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def item_in_slot(self, slot: SlotIndex) -> Optional[CreItem]:
        """Return the :class:`CreItem` in *slot*, or ``None`` if empty."""
        idx = self.slots.get(slot, 0xFFFF)
        if idx == 0xFFFF or idx >= len(self.items):
            return None
        return self.items[idx]

    def equip_item(self, slot: SlotIndex, resref: str,
                   flags: int = CreItem.FLAG_IDENTIFIED) -> int:
        """Append *resref* to items and assign it to *slot*. Returns item index."""
        item = CreItem(resref=resref, flags=flags)
        self.items.append(item)
        idx = len(self.items) - 1
        self.slots[slot] = idx
        return idx

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<CreFile {src!r} v={_version_str(self.version)} "
            f"hp={self.header.current_hp}/{self.header.max_hp} "
            f"items={len(self.items)} effects={len(self.effects)}>"
        )


# ---------------------------------------------------------------------------
# CreFileV12  (PST V1.2)
# ---------------------------------------------------------------------------

class CreFileV12(CreFile):
    """
    A Planescape: Torment V1.2 creature resource.

    Shares the same sub-array structure as :class:`CreFile` but uses
    :class:`CreHeaderV12` and :class:`PstSlotIndex` for the 46-slot
    PST equipment layout.

    The ``header`` attribute is a :class:`CreHeaderV12` instance.
    The ``slots`` dict is keyed by :class:`PstSlotIndex`.

    Additional PST-specific header fields exposed directly:
    - ``header.lore``          — primary lore stat (replaces BG Wisdom role)
    - ``header.current_lore``  — current lore points
    - ``header.faction``       — PST faction
    - ``header.team``          — PST team
    - ``header.color1``–``color7`` — PST colour slots
    - ``header.overlay_data``  — raw 56-byte tattoo overlay block
    - ``header.soundset``      — 100-byte extended soundset (25 strrefs)
    """

    def __init__(
        self,
        header:           CreHeaderV12,
        known_spells:     List[KnownSpell],
        memorise_info:    List[MemoriseInfo],
        memorised_spells: List[MemorisedSpell],
        items:            List[CreItem],
        slots:            Dict[PstSlotIndex, int],
        effects:          List[EffectBlock],
        source_path:      Optional[Path] = None,
    ) -> None:
        # Call grandparent __init__ directly to avoid CreFile's type hints
        self.header           = header
        self.known_spells     = known_spells
        self.memorise_info    = memorise_info
        self.memorised_spells = memorised_spells
        self.items            = items
        self.slots            = slots
        self.effects          = effects
        self.version          = VERSION_V12
        self.source_path      = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def _from_reader(cls, r: BinaryReader, data: bytes) -> "CreFileV12":
        """Called by CreFile.from_bytes after the version tag is consumed."""
        header = CreHeaderV12._read(r)

        known_spells, memorise_info, memorised_spells, raw_slots, items, effects = (
            _read_subarrays(BinaryReader(data[8:]), header, SLOT_COUNT_V12,
                            use_v2_effects=False)
        )
        # The sub-array reader needs absolute offsets, so re-read from full data
        r2 = BinaryReader(data)
        r2.skip(8)  # sig + ver
        known_spells, memorise_info, memorised_spells, raw_slots, items, effects = (
            _read_subarrays(r2, header, SLOT_COUNT_V12, use_v2_effects=False)
        )

        slots: Dict[PstSlotIndex, int] = {}
        for slot in PstSlotIndex:
            if slot.value < SLOT_COUNT_V12:
                slots[slot] = raw_slots[slot.value]

        return cls(header, known_spells, memorise_info, memorised_spells,
                   items, slots, effects)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        sub_bytes = _write_subarrays(
            self.header, PstSlotIndex, SLOT_COUNT_V12,
            self.known_spells, self.memorise_info, self.memorised_spells,
            self.slots, self.items, self.effects,
            use_v2_effects=False,
            header_size=HEADER_SIZE_V12,
        )
        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(VERSION_V12)
        self.header._write(w)
        w.write_bytes(sub_bytes)
        return w.to_bytes()

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        h = self.header
        hd: dict = {
            "name": h.name.to_json(), "tooltip": h.tooltip.to_json(), "flags": h.flags,
            "xp_value": h.xp_value, "current_hp": h.current_hp,
            "max_hp": h.max_hp, "animation_id": h.animation_id,
            "race": h.race, "klass": h.klass, "gender": h.gender,
            "alignment": h.alignment,
            "level_1": h.level_1, "str": h.str, "int": h.int,
            "wis": h.wis, "dex": h.dex, "con": h.con, "cha": h.cha,
            "lore": h.lore, "current_lore": h.current_lore,
            "thac0": h.thac0, "ac_base": h.ac_base, "attacks": h.attacks,
            "dialog": h.dialog,
        }
        for attr, default in (
            ("xp",0),("gold",0),("level_2",0),("level_3",0),("str_extra",0),
            ("faction",0),("team",0),("reputation",10),("status_flags",0),
            ("morale",10),("morale_break",5),("morale_recovery",0),
            ("racial_enemy",0),("hide_in_shadows",0),("death_variable",""),
            ("small_portrait",""),("large_portrait",""),
            ("save_death",20),("save_wands",20),("save_poly",20),
            ("save_breath",20),("save_spells",20),
        ):
            v = getattr(h, attr)
            if v != default: hd[attr] = v
        for attr in ("override_script","default_script"):
            if getattr(h, attr): hd[attr] = getattr(h, attr)
        for i in range(1, 8):
            v = getattr(h, f"color{i}")
            if v: hd[f"color{i}"] = v
        _NONE_SOUNDSET_V12 = [StrRef(0xFFFFFFFF)] * 25
        if h.soundset != _NONE_SOUNDSET_V12:
            hd["soundset"] = [s.to_json() for s in h.soundset]
        if any(h.overlay_data):
            hd["overlay_data"] = h.overlay_data.hex()
        if h.v12_tail:
            hd["v12_tail"] = h.v12_tail.hex()

        slot_dict = {s.name: i for s, i in self.slots.items() if i != 0xFFFF}
        d: dict = {"format": "cre", "version": "V1.2", "header": hd}
        if slot_dict:           d["slots"]            = slot_dict
        if self.items:          d["items"]            = [i.to_json() for i in self.items]
        if self.known_spells:   d["known_spells"]     = [k.to_json() for k in self.known_spells]
        if self.memorise_info:  d["memorise_info"]    = [m.to_json() for m in self.memorise_info]
        if self.memorised_spells: d["memorised_spells"] = [m.to_json() for m in self.memorised_spells]
        if self.effects:        d["effects"]          = [e.to_json() for e in self.effects]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "CreFileV12":
        hd = d.get("header", {})
        _raw_soundset_v12 = hd.get("soundset", None)
        if isinstance(_raw_soundset_v12, list):
            _soundset_v12 = [StrRef.from_json(v) for v in _raw_soundset_v12]
            _soundset_v12 = (_soundset_v12 + [StrRef(0xFFFFFFFF)] * 25)[:25]
        else:
            _soundset_v12 = [StrRef(0xFFFFFFFF)] * 25
        overlay_hex   = hd.get("overlay_data", "")
        v12_tail_hex  = hd.get("v12_tail", "")
        header = CreHeaderV12(
            name=StrRef.from_json(hd.get("name", 0xFFFFFFFF)), tooltip=StrRef.from_json(hd.get("tooltip", 0xFFFFFFFF)),
            flags=hd.get("flags", 0), xp_value=hd.get("xp_value", 0),
            xp=hd.get("xp", 0), gold=hd.get("gold", 0),
            status_flags=hd.get("status_flags", 0),
            current_hp=hd.get("current_hp", 1), max_hp=hd.get("max_hp", 1),
            animation_id=hd.get("animation_id", 0),
            color1=hd.get("color1",0), color2=hd.get("color2",0),
            color3=hd.get("color3",0), color4=hd.get("color4",0),
            color5=hd.get("color5",0), color6=hd.get("color6",0),
            color7=hd.get("color7",0),
            small_portrait=hd.get("small_portrait",""),
            large_portrait=hd.get("large_portrait",""),
            reputation=hd.get("reputation",10),
            hide_in_shadows=hd.get("hide_in_shadows",0),
            ac_base=hd.get("ac_base",10), ac_crush=hd.get("ac_crush",0),
            ac_missile=hd.get("ac_missile",0), ac_pierce=hd.get("ac_pierce",0),
            ac_slash=hd.get("ac_slash",0),
            thac0=hd.get("thac0",20), attacks=hd.get("attacks",1),
            save_death=hd.get("save_death",20), save_wands=hd.get("save_wands",20),
            save_poly=hd.get("save_poly",20), save_breath=hd.get("save_breath",20),
            save_spells=hd.get("save_spells",20),
            resist_fire=hd.get("resist_fire",0), resist_cold=hd.get("resist_cold",0),
            resist_electricity=hd.get("resist_electricity",0),
            resist_acid=hd.get("resist_acid",0), resist_magic=hd.get("resist_magic",0),
            resist_magic_fire=hd.get("resist_magic_fire",0),
            resist_magic_cold=hd.get("resist_magic_cold",0),
            resist_slash=hd.get("resist_slash",0), resist_crush=hd.get("resist_crush",0),
            resist_pierce=hd.get("resist_pierce",0), resist_missile=hd.get("resist_missile",0),
            detect_illusions=hd.get("detect_illusions",0),
            set_traps=hd.get("set_traps",0), lore=hd.get("lore",0),
            lock_picking=hd.get("lock_picking",0),
            move_silently=hd.get("move_silently",0),
            find_traps=hd.get("find_traps",0), pick_pockets=hd.get("pick_pockets",0),
            fatigue=hd.get("fatigue",0), intoxication=hd.get("intoxication",0),
            luck=hd.get("luck",0),
            fist_prof=hd.get("fist_prof",0), edged_prof=hd.get("edged_prof",0),
            hammer_prof=hd.get("hammer_prof",0), axe_prof=hd.get("axe_prof",0),
            club_prof=hd.get("club_prof",0), misc_prof=hd.get("misc_prof",0),
            tracking=hd.get("tracking",0),
            tracking_target=StrRef.from_json(hd.get("tracking_target", 0xFFFFFFFF)),
            soundset=_soundset_v12,
            level_1=hd.get("level_1",0), level_2=hd.get("level_2",0),
            level_3=hd.get("level_3",0), sex=hd.get("sex",Gender.MALE),
            str=hd.get("str",9), str_extra=hd.get("str_extra",0),
            int=hd.get("int",9), wis=hd.get("wis",9),
            dex=hd.get("dex",9), con=hd.get("con",9), cha=hd.get("cha",9),
            current_lore=hd.get("current_lore",0),
            morale=hd.get("morale",10), morale_break=hd.get("morale_break",5),
            racial_enemy=hd.get("racial_enemy",0),
            morale_recovery=hd.get("morale_recovery",0),
            faction=hd.get("faction",0), team=hd.get("team",0),
            override_script=hd.get("override_script",""),
            default_script=hd.get("default_script",""),
            enemy=hd.get("enemy",0), general=hd.get("general",0),
            race=hd.get("race",Race.HUMAN), klass=hd.get("klass",Class.FIGHTER),
            specific=hd.get("specific",0), gender=hd.get("gender",Gender.MALE),
            alignment=hd.get("alignment",Alignment.TRUE_NEUTRAL),
            global_actor_enum=hd.get("global_actor_enum",0),
            local_actor_enum=hd.get("local_actor_enum",0),
            death_variable=hd.get("death_variable",""),
            overlay_data=bytes.fromhex(overlay_hex) if overlay_hex else b"\x00"*56,
            dialog=hd.get("dialog",""),
            v12_tail=bytes.fromhex(v12_tail_hex) if v12_tail_hex else b"",
        )
        slots: Dict[PstSlotIndex, int] = {s: 0xFFFF for s in PstSlotIndex}
        for name, idx in d.get("slots", {}).items():
            try: slots[PstSlotIndex[name]] = idx
            except KeyError: pass
        return cls(
            header,
            [KnownSpell.from_json(k) for k in d.get("known_spells", [])],
            [MemoriseInfo.from_json(m) for m in d.get("memorise_info", [])],
            [MemorisedSpell.from_json(m) for m in d.get("memorised_spells", [])],
            [CreItem.from_json(i) for i in d.get("items", [])],
            slots,
            [EffectBlock.from_json(e) for e in d.get("effects", [])],
        )

    # ------------------------------------------------------------------
    # Convenience  (PST-specific)
    # ------------------------------------------------------------------

    def item_in_slot(self, slot: PstSlotIndex) -> Optional[CreItem]:
        idx = self.slots.get(slot, 0xFFFF)
        if idx == 0xFFFF or idx >= len(self.items):
            return None
        return self.items[idx]

    def equip_item(self, slot: PstSlotIndex, resref: str,
                   flags: int = CreItem.FLAG_IDENTIFIED) -> int:
        item = CreItem(resref=resref, flags=flags)
        self.items.append(item)
        idx = len(self.items) - 1
        self.slots[slot] = idx
        return idx

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<CreFileV12 {src!r} "
            f"hp={self.header.current_hp}/{self.header.max_hp} "
            f"items={len(self.items)} effects={len(self.effects)}>"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _version_str(version: bytes) -> str:
    return version.rstrip(b" ").decode("latin-1")