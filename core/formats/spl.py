"""
core/formats/spl.py

Parser and writer for the Infinity Engine SPL (Spell) format.

Every arcane spell, divine spell, innate ability, and special power in the
game is an SPL file.  The format is structurally identical to ITM: a header
section followed by a flat array of extended headers (one per casting mode or
power level) and a flat array of feature blocks (effects).  Each extended
header references a slice of the feature block array for its own effects;
a second slice holds effects applied on equip/memorisation (used by innate
abilities and some special powers).

Supported versions:
    V1   — BG1, IWD1, PST
    V1.1 — BG2, BG2:EE, IWD:EE, PST:EE  (adds projectile field, same as ITM)

IESDP references:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/spl_v1.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/spl_v11.htm

File layout:
    0x0000  Header          (114 bytes V1 / 116 bytes V1.1)
    after header:
        N × ExtendedHeader  (40 bytes each)  ← note: 40, not 56 like ITM
        M × FeatureBlock    (48 bytes each)

Usage::

    from core.formats.spl import SplFile, SpellType, SpellSchool

    spl = SplFile.from_file("SPWI302.spl")          # Fireball
    print(spl.header.spell_level)                    # 3
    print(spl.header.school)                         # SpellSchool.EVOCATION

    # Add a secondary effect to the first casting mode
    from core.formats.spl import FeatureBlock
    spl.extended_headers[0].features.append(
        FeatureBlock(opcode=12, parameter2=5, timing_mode=0, duration=30)
    )
    spl.to_file("SPWI302_mod.spl")

    # JSON round-trip
    import json
    json.dump(spl.to_json(), open("SPWI302.json", "w"), indent=2)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import List, Optional

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.resref import ResRef


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE       = b"SPL "
VERSION_V1      = b"V1  "
VERSION_V11     = b"V1.1"

HEADER_SIZE_V1  = 114
HEADER_SIZE_V11 = 116
EXT_HEADER_SIZE = 40
FEATURE_BLOCK_SIZE = 48

STRREF_NONE = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SpellType(IntEnum):
    """Spell category (offset 0x1C in header)."""
    SPECIAL_ABILITY = 0x0000   # innate / special power
    WIZARD          = 0x0001
    CLERIC          = 0x0002
    PSIONIC         = 0x0003   # PST
    INNATE          = 0x0004   # also used for abilities granted by items
    BARD            = 0x0005


class SpellSchool(IntEnum):
    """Arcane school / divine sphere (offset 0x25 in header)."""
    NONE            = 0
    ABJURATION      = 1
    CONJURATION     = 2
    DIVINATION      = 3
    ENCHANTMENT     = 4
    ILLUSION        = 5
    EVOCATION       = 6
    NECROMANCY      = 7
    TRANSMUTATION   = 8   # Alteration
    GENERALIST      = 9
    DIVINATION2     = 10  # used inconsistently in some games
    # Divine spheres (IWD2 / some EE titles map these differently)
    ALL_SPHERES     = 0
    ANIMAL          = 20
    ASTRAL          = 21
    CHARM           = 22
    COMBAT          = 23
    CREATION        = 24
    ELEMENTAL       = 26
    HEALING         = 27
    NECROMANTIC     = 28
    PLANT           = 29
    PROTECTION      = 30
    SUMMONING       = 31
    SUN             = 32
    WEATHER         = 33


class SpellFlag(IntFlag):
    """Spell flag bits (offset 0x18 in header)."""
    NONE                    = 0x00000000
    FRIENDLY                = 0x00000002  # does not affect caster's faction
    NO_LOS_REQUIRED         = 0x00000004
    ALLOW_DEAD              = 0x00000010  # can target dead creatures
    IGNORE_WILD_SURGE       = 0x00000020
    IGNORE_DEAD_MAGIC       = 0x00000040  # unaffected by dead magic zones
    NOT_AFFECTED_BY_ANTIMAGIC = 0x00000080
    IGNORE_WILD_MAGIC_ZONE  = 0x00000100
    EE_HOSTILE              = 0x00000400  # EE: marks as hostile
    EE_NO_INVENTORY_FEEDBACK = 0x00000800


class UsabilityFlag(IntFlag):
    """
    Who cannot learn / use this spell (offset 0x1E in header).

    Set bits *exclude* that class from using the spell.  The mapping
    differs slightly between BG1/BG2/IWD; these are the BG2 values.
    """
    NONE            = 0x00000000
    CHAOTIC         = 0x00000001
    EVIL            = 0x00000002
    GOOD            = 0x00000004
    NEUTRAL_GE      = 0x00000008  # neither good nor evil
    LAWFUL          = 0x00000010
    NEUTRAL_LC      = 0x00000020  # neither lawful nor chaotic
    BARD            = 0x00000040
    CLERIC          = 0x00000080
    CLERIC_EVIL     = 0x00000100
    CLERIC_GOOD     = 0x00000200
    CLERIC_NEUTRAL  = 0x00000400
    DRUID           = 0x00000800
    FIGHTER         = 0x00001000
    MAGE            = 0x00002000
    PALADIN         = 0x00004000
    RANGER          = 0x00008000
    SHAMAN          = 0x00010000
    THIEF           = 0x00020000


class CastingAnimation(IntEnum):
    """Casting graphics selection (offset 0x28 in header)."""
    NONE        = 0x0000
    SPELL       = 0x0001
    DETECTION   = 0x0002
    MANUAL      = 0x0003  # no animation
    AREA_EFFECT = 0x0004


class TargetType(IntEnum):
    """Extended header target type (offset 0x04 in ext header)."""
    INVALID         = 0
    LIVING_ACTOR    = 1
    INVENTORY       = 2
    DEAD_ACTOR      = 3
    ANY_POINT       = 4
    SELF            = 5
    EX_SELF         = 6   # anyone except self
    LARGE_AOE       = 7


class EffectTarget(IntEnum):
    """Feature block target (offset 0x20 in feature block)."""
    NONE                    = 0
    SELF                    = 1
    PRESET_TARGET           = 2
    PARTY                   = 3
    EVERYONE                = 4
    EVERYONE_EXCEPT_PARTY   = 5
    ORIGINAL_CASTER         = 6
    EVERYONE_IN_AREA        = 7
    EVERYONE_EXCEPT_SELF    = 8
    ORIGINAL_CASTER_GROUP   = 9


class EffectTiming(IntEnum):
    """Feature block timing mode (offset 0x22 in feature block)."""
    DURATION            = 0
    PERMANENT_UNSAVED   = 1
    WHILE_EQUIPPED      = 2
    DELAYED             = 3
    DELAYED_PERMANENT   = 4
    DELAYED_UNSAVED     = 5
    DURATION_AFTER_DEATH = 6
    PERMANENT_AFTER_DEATH = 7
    INDEPENDENT         = 8
    PERMANENT_SAVED     = 9


# ---------------------------------------------------------------------------
# Feature block  (48 bytes)  — identical layout to itm.FeatureBlock
# ---------------------------------------------------------------------------

@dataclass
class FeatureBlock:
    """
    A single applied effect — one row in the feature block array.

    The binary layout is identical to the one in ``itm.py``; it is
    reproduced here so each format module remains self-contained and
    can be imported independently.
    """
    opcode:         int = 0       # uint16
    target:         int = 0       # uint8   — EffectTarget
    power:          int = 0       # uint8
    parameter1:     int = 0       # int32
    parameter2:     int = 0       # int32
    timing_mode:    int = 0       # uint8   — EffectTiming
    dispel_resist:  int = 0       # uint8
    duration:       int = 0       # uint32  — ticks (15/sec)
    probability1:   int = 100     # uint8
    probability2:   int = 0       # uint8
    resource:       str = ""      # ResRef
    dice_count:     int = 0       # int32
    dice_sides:     int = 0       # int32
    saving_throw:   int = 0       # uint32
    save_bonus:     int = 0       # int32
    special:        int = 0       # uint32

    # ------------------------------------------------------------------
    # Binary I/O
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader) -> "FeatureBlock":
        opcode        = r.read_uint16()
        target        = r.read_uint8()
        power         = r.read_uint8()
        parameter1    = r.read_int32()
        parameter2    = r.read_int32()
        timing_mode   = r.read_uint8()
        dispel_resist = r.read_uint8()
        r.skip(2)                           # padding
        duration      = r.read_uint32()
        probability1  = r.read_uint8()
        probability2  = r.read_uint8()
        r.skip(2)                           # padding
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

    def _write(self, w: BinaryWriter) -> None:
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

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

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
        return d

    @classmethod
    def from_json(cls, d: dict) -> "FeatureBlock":
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
        )


# ---------------------------------------------------------------------------
# Extended header  (40 bytes)
# ---------------------------------------------------------------------------

@dataclass
class ExtendedHeader:
    """
    One casting mode / power level entry.

    A standard wizard spell typically has one extended header for its
    normal casting.  A spell with multiple power tiers (e.g. a sequencer
    component) will have several.  Feature blocks for each header are kept
    in the global block array; *feature_offset* + *feature_count* index
    into that array.

    Note: SPL extended headers are 40 bytes, 16 bytes shorter than ITM's
    56-byte variety.  They have no alt-dice or alt-damage fields; damage
    dice live in feature blocks instead.
    """
    spell_level:      int = 0                  # uint16 — level of *this ability*
    target_type:      int = TargetType.INVALID # uint8
    target_count:     int = 1                  # uint8
    range:            int = 0                  # uint16 — in feet
    casting_time:     int = 0                  # uint16 — in ticks
    duration:         int = 0                  # uint16 — base duration in rounds
    dice_sides:       int = 0                  # uint8
    dice_count:       int = 0                  # uint8
    damage_bonus:     int = 0                  # int16
    damage_type:      int = 0                  # uint16
    feature_count:    int = 0                  # uint16
    feature_offset:   int = 0                  # uint16 — index into global array
    charges:          int = 0                  # uint16
    charge_depletion: int = 0                  # uint16
    projectile_type:  int = 0                  # uint16

    # Feature blocks belonging to this header (populated after full parse)
    features: List[FeatureBlock] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Binary I/O
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader) -> "ExtendedHeader":
        spell_level      = r.read_uint16()
        target_type      = r.read_uint8()
        target_count     = r.read_uint8()
        rng              = r.read_uint16()
        casting_time     = r.read_uint16()
        duration         = r.read_uint16()
        dice_sides       = r.read_uint8()
        dice_count       = r.read_uint8()
        damage_bonus     = r.read_int16()
        damage_type      = r.read_uint16()
        feature_count    = r.read_uint16()
        feature_offset   = r.read_uint16()
        charges          = r.read_uint16()
        charge_depletion = r.read_uint16()
        projectile_type  = r.read_uint16()
        return cls(
            spell_level=spell_level, target_type=target_type,
            target_count=target_count, range=rng,
            casting_time=casting_time, duration=duration,
            dice_sides=dice_sides, dice_count=dice_count,
            damage_bonus=damage_bonus, damage_type=damage_type,
            feature_count=feature_count, feature_offset=feature_offset,
            charges=charges, charge_depletion=charge_depletion,
            projectile_type=projectile_type,
        )

    def _write(self, w: BinaryWriter, feature_offset: int) -> None:
        w.write_uint16(self.spell_level)
        w.write_uint8(self.target_type)
        w.write_uint8(self.target_count)
        w.write_uint16(self.range)
        w.write_uint16(self.casting_time)
        w.write_uint16(self.duration)
        w.write_uint8(self.dice_sides)
        w.write_uint8(self.dice_count)
        w.write_int16(self.damage_bonus)
        w.write_uint16(self.damage_type)
        w.write_uint16(len(self.features))
        w.write_uint16(feature_offset)
        w.write_uint16(self.charges)
        w.write_uint16(self.charge_depletion)
        w.write_uint16(self.projectile_type)

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        d: dict = {
            "spell_level":  self.spell_level,
            "target_type":  self.target_type,
            "range":        self.range,
            "casting_time": self.casting_time,
        }
        if self.target_count != 1: d["target_count"]     = self.target_count
        if self.duration:          d["duration"]         = self.duration
        if self.dice_count:        d["dice_count"]       = self.dice_count
        if self.dice_sides:        d["dice_sides"]       = self.dice_sides
        if self.damage_bonus:      d["damage_bonus"]     = self.damage_bonus
        if self.damage_type:       d["damage_type"]      = self.damage_type
        if self.charges:           d["charges"]          = self.charges
        if self.charge_depletion:  d["charge_depletion"] = self.charge_depletion
        if self.projectile_type:   d["projectile_type"]  = self.projectile_type
        if self.features:
            d["features"] = [f.to_json() for f in self.features]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "ExtendedHeader":
        eh = cls(
            spell_level      = d.get("spell_level",      0),
            target_type      = d.get("target_type",      TargetType.INVALID),
            target_count     = d.get("target_count",     1),
            range            = d.get("range",            0),
            casting_time     = d.get("casting_time",     0),
            duration         = d.get("duration",         0),
            dice_sides       = d.get("dice_sides",       0),
            dice_count       = d.get("dice_count",       0),
            damage_bonus     = d.get("damage_bonus",     0),
            damage_type      = d.get("damage_type",      0),
            charges          = d.get("charges",          0),
            charge_depletion = d.get("charge_depletion", 0),
            projectile_type  = d.get("projectile_type",  0),
        )
        eh.features = [FeatureBlock.from_json(f) for f in d.get("features", [])]
        return eh


# ---------------------------------------------------------------------------
# Spell header  (114 / 116 bytes)
# ---------------------------------------------------------------------------

@dataclass
class SplHeader:
    """
    The top-level spell record.

    Contains identity (name/description strrefs), school, type, level,
    casting animation, and memorisation/learning restrictions.  Offset
    fields are managed automatically by :class:`SplFile` on write.
    """
    # Identity
    unidentified_name: int = STRREF_NONE   # StrRef — name before identification
    identified_name:   int = STRREF_NONE   # StrRef — true spell name
    casting_graphics:  str = ""            # ResRef — VEF/VVC casting animation
    flags:             int = SpellFlag.NONE
    spell_type:        int = SpellType.WIZARD
    usability:         int = 0             # uint32 — UsabilityFlag (exclusions)
    casting_anim:      int = CastingAnimation.SPELL  # uint16
    min_level:         int = 0             # uint16 — minimum caster level
    primary_type:      int = SpellSchool.NONE  # uint8 — school / sphere
    secondary_type:    int = 0             # uint8
    # Memorisation / learning
    unknown_28:        int = 0             # uint32 — unused / reserved
    unknown_2c:        int = 0             # uint32
    unknown_30:        int = 0             # uint32
    spell_level:       int = 0             # uint32 — spell circle (1–9)
    unidentified_desc: int = STRREF_NONE   # StrRef
    identified_desc:   int = STRREF_NONE   # StrRef
    memorisation_icon: str = ""            # ResRef — icon in spellbook
    first_level_cond:  int = 0             # uint16 — condition for first casting
    spell_icon:        str = ""            # ResRef — quick-slot icon

    # Offsets (managed by SplFile)
    ext_header_offset:   int = 0           # uint32
    ext_header_count:    int = 0           # uint16
    feature_offset:      int = 0           # uint32
    cast_feature_index:  int = 0           # uint16 — first casting effect
    cast_feature_count:  int = 0           # uint16

    # V1.1 only
    projectile_type:   int = 0             # uint16

    # ------------------------------------------------------------------
    # Binary I/O
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader, version: bytes) -> "SplHeader":
        unidentified_name  = r.read_uint32()
        identified_name    = r.read_uint32()
        casting_graphics   = r.read_resref()
        flags              = r.read_uint32()
        spell_type         = r.read_uint16()
        usability          = r.read_uint32()
        casting_anim       = r.read_uint16()
        min_level          = r.read_uint16()
        primary_type       = r.read_uint8()
        secondary_type     = r.read_uint8()
        unknown_28         = r.read_uint32()
        unknown_2c         = r.read_uint32()
        unknown_30         = r.read_uint32()
        spell_level        = r.read_uint32()
        unidentified_desc  = r.read_uint32()
        identified_desc    = r.read_uint32()
        memorisation_icon  = r.read_resref()
        first_level_cond   = r.read_uint16()
        spell_icon         = r.read_resref()
        ext_header_offset  = r.read_uint32()
        ext_header_count   = r.read_uint16()
        feature_offset     = r.read_uint32()
        cast_feature_index = r.read_uint16()
        cast_feature_count = r.read_uint16()

        projectile_type = 0
        if version == VERSION_V11:
            projectile_type = r.read_uint16()

        return cls(
            unidentified_name=unidentified_name,
            identified_name=identified_name,
            casting_graphics=casting_graphics,
            flags=flags, spell_type=spell_type, usability=usability,
            casting_anim=casting_anim, min_level=min_level,
            primary_type=primary_type, secondary_type=secondary_type,
            unknown_28=unknown_28, unknown_2c=unknown_2c, unknown_30=unknown_30,
            spell_level=spell_level,
            unidentified_desc=unidentified_desc, identified_desc=identified_desc,
            memorisation_icon=memorisation_icon,
            first_level_cond=first_level_cond, spell_icon=spell_icon,
            ext_header_offset=ext_header_offset,
            ext_header_count=ext_header_count,
            feature_offset=feature_offset,
            cast_feature_index=cast_feature_index,
            cast_feature_count=cast_feature_count,
            projectile_type=projectile_type,
        )

    def _write(self, w: BinaryWriter, version: bytes) -> None:
        w.write_uint32(self.unidentified_name)
        w.write_uint32(self.identified_name)
        w.write_resref(self.casting_graphics)
        w.write_uint32(self.flags)
        w.write_uint16(self.spell_type)
        w.write_uint32(self.usability)
        w.write_uint16(self.casting_anim)
        w.write_uint16(self.min_level)
        w.write_uint8(self.primary_type)
        w.write_uint8(self.secondary_type)
        w.write_uint32(self.unknown_28)
        w.write_uint32(self.unknown_2c)
        w.write_uint32(self.unknown_30)
        w.write_uint32(self.spell_level)
        w.write_uint32(self.unidentified_desc)
        w.write_uint32(self.identified_desc)
        w.write_resref(self.memorisation_icon)
        w.write_uint16(self.first_level_cond)
        w.write_resref(self.spell_icon)
        w.write_uint32(self.ext_header_offset)
        w.write_uint16(self.ext_header_count)
        w.write_uint32(self.feature_offset)
        w.write_uint16(self.cast_feature_index)
        w.write_uint16(self.cast_feature_count)
        if version == VERSION_V11:
            w.write_uint16(self.projectile_type)


# ---------------------------------------------------------------------------
# SplFile — top-level container
# ---------------------------------------------------------------------------

class SplFile:
    """
    A complete SPL resource: header, extended headers, and feature blocks.

    The three sections are exposed directly:

    ``header``
        A :class:`SplHeader` with identity, school, level, and restrictions.

    ``extended_headers``
        A list of :class:`ExtendedHeader` objects, one per casting mode.
        Each carries its own ``features`` list of :class:`FeatureBlock`.

    ``cast_features``
        A list of :class:`FeatureBlock` objects applied when the spell is
        cast (used for memorisation/innate-ability overhead effects).  Most
        spells leave this empty; effects live in extended header features.

    Usage::

        spl = SplFile.from_file("SPWI302.spl")     # Fireball

        eh = spl.extended_headers[0]
        print(f"Casting time: {eh.casting_time} ticks")
        print(f"Effects: {len(eh.features)}")

        # Bump the casting time of all modes by 1
        for eh in spl.extended_headers:
            eh.casting_time += 1

        spl.to_file("SPWI302_slow.spl")
    """

    def __init__(
        self,
        header:           SplHeader,
        extended_headers: List[ExtendedHeader],
        cast_features:    List[FeatureBlock],
        version:          bytes = VERSION_V1,
        source_path:      Optional[Path] = None,
    ) -> None:
        self.header           = header
        self.extended_headers = extended_headers
        self.cast_features    = cast_features
        self.version          = version
        self.source_path      = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "SplFile":
        """Parse a SPL resource from raw bytes."""
        r = BinaryReader(data)

        try:
            r.expect_signature(SIGNATURE)
            version = r.read_bytes(4)
            if version not in (VERSION_V1, VERSION_V11):
                raise ValueError(f"Unsupported SPL version {version!r}.")
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        header = SplHeader._read(r, version)

        # --- Extended headers ---
        r.seek(header.ext_header_offset)
        raw_ext_headers: List[ExtendedHeader] = []
        for _ in range(header.ext_header_count):
            raw_ext_headers.append(ExtendedHeader._read(r))

        # --- Feature block array ---
        # Determine how many blocks to read by finding the highest index
        # referenced by any header or by the cast_feature slice.
        max_index = header.cast_feature_index + header.cast_feature_count
        for eh in raw_ext_headers:
            max_index = max(max_index, eh.feature_offset + eh.feature_count)

        all_features: List[FeatureBlock] = []
        if max_index > 0:
            r.seek(header.feature_offset)
            for _ in range(max_index):
                all_features.append(FeatureBlock._read(r))

        # Attach ability features to their extended headers
        for eh in raw_ext_headers:
            eh.features = all_features[
                eh.feature_offset : eh.feature_offset + eh.feature_count
            ]

        cast_features = all_features[
            header.cast_feature_index :
            header.cast_feature_index + header.cast_feature_count
        ]

        return cls(header, raw_ext_headers, cast_features, version=version)

    @classmethod
    def from_file(cls, path: str | Path) -> "SplFile":
        """Read and parse a SPL file from disk."""
        path = Path(path)
        return cls.from_bytes(path.read_bytes())

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise the spell back to its binary representation."""
        version     = self.version
        header_size = HEADER_SIZE_V11 if version == VERSION_V11 else HEADER_SIZE_V1

        ext_header_offset     = header_size
        total_ext_size        = len(self.extended_headers) * EXT_HEADER_SIZE
        feature_offset        = ext_header_offset + total_ext_size
        ability_feature_count = sum(len(eh.features) for eh in self.extended_headers)
        cast_feature_index    = ability_feature_count

        w_ext  = BinaryWriter()
        w_feat = BinaryWriter()

        running_feat_offset = 0
        for eh in self.extended_headers:
            eh._write(w_ext, running_feat_offset)
            running_feat_offset += len(eh.features)

        for eh in self.extended_headers:
            for fb in eh.features:
                fb._write(w_feat)

        for fb in self.cast_features:
            fb._write(w_feat)

        # Update header offsets
        self.header.ext_header_offset  = ext_header_offset
        self.header.ext_header_count   = len(self.extended_headers)
        self.header.feature_offset     = feature_offset
        self.header.cast_feature_index = cast_feature_index
        self.header.cast_feature_count = len(self.cast_features)

        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(version)
        self.header._write(w, version)

        return w.to_bytes() + w_ext.to_bytes() + w_feat.to_bytes()

    def to_file(self, path: str | Path) -> None:
        """Write the spell to disk."""
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        h = self.header
        d: dict = {
            "format":  "spl",
            "version": _version_str(self.version),
            "header": {
                "unidentified_name": h.unidentified_name,
                "identified_name":   h.identified_name,
                "spell_type":        h.spell_type,
                "spell_level":       h.spell_level,
                "primary_type":      h.primary_type,
                "flags":             h.flags,
                "usability":         h.usability,
                "unidentified_desc": h.unidentified_desc,
                "identified_desc":   h.identified_desc,
            },
        }
        hd = d["header"]
        if h.casting_graphics:             hd["casting_graphics"]  = h.casting_graphics
        if h.casting_anim:                 hd["casting_anim"]      = h.casting_anim
        if h.min_level:                    hd["min_level"]         = h.min_level
        if h.secondary_type:               hd["secondary_type"]    = h.secondary_type
        if h.memorisation_icon:            hd["memorisation_icon"] = h.memorisation_icon
        if h.spell_icon:                   hd["spell_icon"]        = h.spell_icon
        if h.first_level_cond:             hd["first_level_cond"]  = h.first_level_cond
        if h.unknown_28:                   hd["unknown_28"]        = h.unknown_28
        if h.unknown_2c:                   hd["unknown_2c"]        = h.unknown_2c
        if h.unknown_30:                   hd["unknown_30"]        = h.unknown_30
        if self.version == VERSION_V11 and h.projectile_type:
            hd["projectile_type"] = h.projectile_type

        if self.extended_headers:
            d["extended_headers"] = [eh.to_json() for eh in self.extended_headers]
        if self.cast_features:
            d["cast_features"] = [f.to_json() for f in self.cast_features]

        return d

    @classmethod
    def from_json(cls, d: dict) -> "SplFile":
        """Deserialise from a JSON-compatible dict."""
        ver_str = d.get("version", "V1")
        version = VERSION_V11 if ver_str == "V1.1" else VERSION_V1

        hd = d.get("header", {})
        header = SplHeader(
            unidentified_name  = hd.get("unidentified_name",  STRREF_NONE),
            identified_name    = hd.get("identified_name",    STRREF_NONE),
            casting_graphics   = hd.get("casting_graphics",   ""),
            flags              = hd.get("flags",              SpellFlag.NONE),
            spell_type         = hd.get("spell_type",         SpellType.WIZARD),
            usability          = hd.get("usability",          0),
            casting_anim       = hd.get("casting_anim",       CastingAnimation.SPELL),
            min_level          = hd.get("min_level",          0),
            primary_type       = hd.get("primary_type",       SpellSchool.NONE),
            secondary_type     = hd.get("secondary_type",     0),
            unknown_28         = hd.get("unknown_28",         0),
            unknown_2c         = hd.get("unknown_2c",         0),
            unknown_30         = hd.get("unknown_30",         0),
            spell_level        = hd.get("spell_level",        0),
            unidentified_desc  = hd.get("unidentified_desc",  STRREF_NONE),
            identified_desc    = hd.get("identified_desc",    STRREF_NONE),
            memorisation_icon  = hd.get("memorisation_icon",  ""),
            first_level_cond   = hd.get("first_level_cond",   0),
            spell_icon         = hd.get("spell_icon",         ""),
            projectile_type    = hd.get("projectile_type",    0),
        )

        extended_headers = [
            ExtendedHeader.from_json(e) for e in d.get("extended_headers", [])
        ]
        cast_features = [
            FeatureBlock.from_json(f) for f in d.get("cast_features", [])
        ]

        return cls(header, extended_headers, cast_features, version=version)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "SplFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def add_cast_feature(self, fb: FeatureBlock) -> None:
        """Append an effect applied at cast time (on top of all modes)."""
        self.cast_features.append(fb)

    def add_extended_header(self, eh: ExtendedHeader) -> None:
        """Append a new casting mode."""
        self.extended_headers.append(eh)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<SplFile {src!r} "
            f"level={self.header.spell_level} "
            f"school={self.header.primary_type} "
            f"modes={len(self.extended_headers)} "
            f"cast_fx={len(self.cast_features)}>"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _version_str(version: bytes) -> str:
    """Return a human-readable version string from a raw version field."""
    return version.rstrip(b" ").decode("latin-1")
