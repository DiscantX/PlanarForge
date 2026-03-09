"""
core/formats/itm.py

Parser and writer for the Infinity Engine ITM (Item) format.

Every weapon, armour, potion, scroll, ring, and miscellaneous object in
the game is an ITM file.  Each file describes the item's stats, flags,
usability restrictions, and a list of *extended headers* (one per attack
mode or ability) each of which carries its own list of *feature blocks*
(applied effects).  A second top-level list of feature blocks covers
equipping effects that are active while the item is worn.

Supported versions:
    V1   — BG1, IWD1, PST
    V1.1 — BG2, BG2:EE, IWD:EE, PST:EE  (adds projectile field)

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/itm_v1.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/itm_v11.htm

File layout:
    0x0000  Header          (114 bytes V1 / 116 bytes V1.1)
    after header:
        N × ExtendedHeader  (56 bytes each)
        M × FeatureBlock    (48 bytes each, equipping effects)
    Extended header feature blocks are stored in the global feature block
    array; each ExtendedHeader records an offset + count into that array.

Usage::

    from core.formats.itm import ItmFile

    itm = ItmFile.from_file("MISC75.itm")
    print(itm.header.name_identified)   # StrRef for identified name
    print(itm.header.item_type)         # ItemType enum value

    # Write back (round-trip)
    itm.to_file("MISC75_copy.itm")

    # JSON round-trip
    import json
    json.dump(itm.to_json(), open("MISC75.json", "w"), indent=2)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import List, Optional

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.resref import ResRef
from core.util.strref import StrRef, StrRefError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE = b"ITM "
VERSION_V1  = b"V1  "
VERSION_V11 = b"V1.1"

HEADER_SIZE_V1  = 114
HEADER_SIZE_V11 = 116
EXT_HEADER_SIZE = 56
FEATURE_BLOCK_SIZE = 48



# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ItemType(IntEnum):
    """Item category codes (offset 0x1C in header)."""
    MISCELLANEOUS     = 0x0000
    AMULET            = 0x0001
    ARMOUR            = 0x0002
    BELT              = 0x0003
    BOOTS             = 0x0004
    ARROWS            = 0x0005
    BRACERS           = 0x0006
    HEADGEAR          = 0x0007
    KEYS              = 0x0008
    POTION            = 0x0009
    RING              = 0x000A
    SCROLLS           = 0x000B
    SHIELD            = 0x000C
    FOOD              = 0x000D
    BULLETS           = 0x000E
    BOW               = 0x000F
    DAGGER            = 0x0010
    MACE              = 0x0011
    SLING             = 0x0012
    SMALL_SWORD       = 0x0013
    LARGE_SWORD       = 0x0014
    HAMMER            = 0x0015
    MORNINGSTAR       = 0x0016
    FLAIL             = 0x0017
    DARTS             = 0x0018
    AXE               = 0x0019
    QUARTERSTAFF      = 0x001A
    CROSSBOW          = 0x001B
    HAND_TO_HAND      = 0x001C
    SPEAR             = 0x001D
    HALBERD           = 0x001E
    BOLTS             = 0x001F
    CLOAK             = 0x0020
    GOLD              = 0x0021
    GEM               = 0x0022
    WAND              = 0x0023
    CONTAINER         = 0x0024  # eye / broken armour slot items
    BOOKS             = 0x0025
    FAMILIAR          = 0x0026
    TATTOO            = 0x0027  # PST
    LENS              = 0x0028  # PST
    BUCKLER           = 0x0029
    CANDLE            = 0x002A
    CLUB              = 0x002C
    LARGE_SHIELD      = 0x002F
    MEDIUM_SHIELD     = 0x0031
    NOTES             = 0x0033
    SMALL_SHIELD      = 0x0035
    TELESCOPE         = 0x0037
    DRINK             = 0x0038
    GREAT_SWORD       = 0x0039
    CONTAINER2        = 0x003A
    FUR               = 0x003B
    LEATHER_ARMOUR    = 0x003C
    STUDDED_LEATHER   = 0x003D
    CHAIN_MAIL        = 0x003E
    SPLINT_MAIL       = 0x003F
    HALF_PLATE        = 0x0040
    FULL_PLATE        = 0x0041
    HIDE_ARMOUR       = 0x0042
    ROBE              = 0x0043
    BASTARD_SWORD     = 0x0045
    SCARF             = 0x0046
    FOOD2             = 0x0047
    THROWING_AXE      = 0x0048
    CROSSBOW_BOLT     = 0x0049


class ItemFlag(IntFlag):
    """Item flag bits (offset 0x18 in header)."""
    NONE                = 0x00000000
    UNSELLABLE          = 0x00000001  # critical item, cannot be sold
    TWO_HANDED          = 0x00000002
    DROPPABLE           = 0x00000004
    DISPLAYABLE         = 0x00000008
    CURSED              = 0x00000010
    UNKNOWN_20          = 0x00000020
    MAGICAL             = 0x00000040
    LEFT_HANDED         = 0x00000080
    SILVER              = 0x00000100
    COLD_IRON           = 0x00000200
    OFF_HANDED          = 0x00000400
    CONVERSABLE         = 0x00000800
    EE_FAKE_TWO_HANDED  = 0x00001000  # EE only
    EE_FORBID_OFF_HAND  = 0x00002000  # EE only


class AttackType(IntEnum):
    """Extended header attack type (offset 0x08 in ext header)."""
    NONE        = 0
    MELEE       = 1
    RANGED      = 2
    MAGICAL     = 3
    LAUNCHER    = 4


class TargetType(IntEnum):
    """Extended header target type (offset 0x0C in ext header)."""
    INVALID         = 0
    LIVING_ACTOR    = 1
    INVENTORY       = 2
    DEAD_ACTOR      = 3
    ANY_POINT       = 4
    SELF            = 5
    EX_SELF         = 6  # anyone except self
    LARGE_AOE       = 7


class EffectTarget(IntEnum):
    """Feature block target type (offset 0x02 in feature block)."""
    NONE            = 0
    SELF            = 1
    PRESET_TARGET   = 2
    PARTY           = 3
    EVERYONE        = 4
    EVERYONE_EXCEPT_PARTY = 5
    ORIGINAL_CASTER = 6
    EVERYONE_IN_AREA = 7
    EVERYONE_EXCEPT_SELF = 8
    ORIGINAL_CASTER_GROUP = 9


class EffectTiming(IntEnum):
    """Feature block timing mode (offset 0x0C in feature block)."""
    DURATION             = 0
    PERMANENT            = 1
    WHILE_EQUIPPED       = 2
    DELAYED_DURATION     = 3
    DELAYED              = 4
    DELAYED_TRANSFORMS   = 5
    DURATION_2           = 6
    PERMANENT_2          = 7
    PERMANENT_UNSAVED    = 8
    PERMANENT_AFTER_DEATH = 9
    TRIGGER              = 10


# ---------------------------------------------------------------------------
# Feature block  (48 bytes)
# ---------------------------------------------------------------------------

@dataclass
class FeatureBlock:
    """
    A single applied effect — one row in the feature block array.

    Feature blocks are the fundamental unit of "something happens to
    something": damage, stat bonuses, visual effects, script triggers, etc.
    Both extended headers (ability effects) and the equipping effect list
    use the same 48-byte structure.
    """
    opcode:         int = 0       # uint16 0x00 — Opcode number
    target:         int = 0       # uint8  0x02 — Target type
    power:          int = 0       # uint8  0x03 — Power
    parameter1:     int = 0       # int32  0x04 — Parameter 1
    parameter2:     int = 0       # int32  0x08 — Parameter 2
    timing_mode:    int = 0       # uint8  0x0C — Timing mode
    resistance:     int = 0       # uint8  0x0D — Resistance
    duration:       int = 0       # uint32 0x0E — Duration
    probability1:   int = 100     # uint8  0x12 — Probability 1
    probability2:   int = 0       # uint8  0x13 — Probability 2
    resource:       ResRef = ResRef("")   # resref 0x14 — Resource
    dice_thrown:     int = 0       # int32  0x1C — Dice thrown
    dice_sides:     int = 0       # int32  0x20 — Dice sides
    saving_throw:   int = 0       # uint32 0x24 — Saving throw type
    save_bonus:     int = 0       # int32  0x28 — Saving throw bonus
    special:        int = 0       # uint32 0x2C — Special

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
        resistance    = r.read_uint8()
        duration      = r.read_uint32()
        probability1  = r.read_uint8()
        probability2  = r.read_uint8()
        resource      = ResRef(r.read_resref())
        dice_thrown    = r.read_int32()
        dice_sides    = r.read_int32()
        saving_throw  = r.read_uint32()
        save_bonus    = r.read_int32()
        special       = r.read_uint32()
        return cls(
            opcode=opcode, target=target, power=power,
            parameter1=parameter1, parameter2=parameter2,
            timing_mode=timing_mode, resistance=resistance,
            duration=duration, probability1=probability1,
            probability2=probability2, resource=resource,
            dice_thrown=dice_thrown, dice_sides=dice_sides,
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
        w.write_uint8(self.resistance)
        w.write_uint32(self.duration)
        w.write_uint8(self.probability1)
        w.write_uint8(self.probability2)
        w.write_resref(str(self.resource))
        w.write_int32(self.dice_thrown)
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
        if self.resistance:          d["resistance"]    = self.resistance
        if self.duration:            d["duration"]      = self.duration
        if self.probability1 != 100: d["probability1"]  = self.probability1
        if self.probability2:        d["probability2"]  = self.probability2
        if self.resource:            d["resource"]      = self.resource.to_json()
        if self.dice_thrown:          d["dice_thrown"]    = self.dice_thrown
        if self.dice_sides:          d["dice_sides"]    = self.dice_sides
        if self.saving_throw:        d["saving_throw"]  = self.saving_throw
        if self.save_bonus:          d["save_bonus"]    = self.save_bonus
        if self.special:             d["special"]       = self.special
        return d

    @classmethod
    def from_json(cls, d: dict) -> "FeatureBlock":
        return cls(
            opcode        = d.get("opcode",       0),
            target        = d.get("target",       0),
            power         = d.get("power",        0),
            parameter1    = d.get("parameter1",   0),
            parameter2    = d.get("parameter2",   0),
            timing_mode   = d.get("timing_mode",  0),
            resistance    = d.get("resistance",   0),
            duration      = d.get("duration",     0),
            probability1  = d.get("probability1", 100),
            probability2  = d.get("probability2", 0),
            resource      = ResRef.from_json(d.get("resource", "")),
            dice_thrown    = d.get("dice_thrown",   0),
            dice_sides    = d.get("dice_sides",   0),
            saving_throw  = d.get("saving_throw", 0),
            save_bonus    = d.get("save_bonus",   0),
            special       = d.get("special",      0),
        )


# ---------------------------------------------------------------------------
# Extended header  (56 bytes)
# ---------------------------------------------------------------------------

@dataclass
class ExtendedHeader:
    """
    One attack mode / item ability.

    A sword typically has one melee extended header.  A bow might have one
    ranged header.  A wand of fire with multiple charges could have two or
    three headers (e.g. Agannazar's Scorcher vs Fireball).  The feature
    blocks for each header are stored in the global feature block array;
    this struct records the slice via *feature_offset* + *feature_count*.
    """
    # IESDP V1/V1.1 Extended Header layout (56 bytes total).
    # Offsets are relative to the start of the extended header struct.
    attack_type:       int = AttackType.NONE    # uint8  0x00 — Attack type
    id_req:            int = 0                  # uint8  0x01 — ID Req.
    location:          int = 0                  # uint8  0x02 — Location
    alt_dice_sides:    int = 0                  # uint8  0x03 — Alternate dice sides
    use_icon:          ResRef = ResRef("")       # resref 0x04 — Use icon (BAM)
    target_type:       int = TargetType.INVALID # uint8  0x0C — Target type
    target_count:      int = 0                  # uint8  0x0D — Target count
    range:             int = 0                  # uint16 0x0E — Range
    projectile_type:     int = 0                  # uint8  0x10 — Projectile type (0=None,1=Arrow,2=Bolt,3=Bullet)
    alt_dice_thrown:    int = 0                  # uint8  0x11 — Alternative dice thrown
    speed:             int = 0                  # uint8  0x12 — Speed
    alt_damage_bonus:  int = 0                  # int8   0x13 — Alternative damage bonus
    thac0_bonus:       int = 0                  # int16  0x14 — THAC0 bonus
    dice_sides:        int = 0                  # uint8  0x16 — Dice sides
    primary_type:      int = 0                  # uint8  0x17 — Primary type
    dice_thrown:        int = 0                  # uint8  0x18 — Dice thrown
    secondary_type:    int = 0                  # uint8  0x19 — Secondary type
    damage_bonus:      int = 0                  # int16  0x1A — Damage bonus
    damage_type:       int = 0                  # uint16 0x1C — Damage type
    feature_count:     int = 0                  # uint16 0x1E — Count of feature blocks
    feature_offset:    int = 0                  # uint16 0x20 — Index into feature blocks
    charges:           int = 0                  # uint16 0x22 — Charges
    charge_depletion:  int = 0                  # uint16 0x24 — Charge depletion behaviour
    flags:             int = 0                  # uint32 0x26 — Flags
    projectile_anim:   int = 0                  # uint16 0x2A — Projectile animation
    melee_anim:        List[int] = field(default_factory=lambda: [0, 0, 0])  # 3×uint16 0x2C–0x31
    unused_0x32:      int = 0                  # uint16 0x32 — Unused (IESDP V1/V1.1)
    unused_0x34:      int = 0                  # uint16 0x34 — Unused (IESDP V1/V1.1)
    unused_0x36:      int = 0                  # uint16 0x36 — Unused (IESDP V1/V1.1)

    # Feature blocks belonging to this header (populated after full parse)
    features: List[FeatureBlock] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Binary I/O
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader) -> "ExtendedHeader":
        # IESDP V1/V1.1 offsets (struct-relative):
        attack_type      = r.read_uint8()          # 0x00
        id_req           = r.read_uint8()          # 0x01
        location         = r.read_uint8()          # 0x02
        alt_dice_sides   = r.read_uint8()          # 0x03
        use_icon         = ResRef(r.read_resref()) # 0x04–0x0B
        target_type      = r.read_uint8()          # 0x0C
        target_count     = r.read_uint8()          # 0x0D
        rng              = r.read_uint16()         # 0x0E–0x0F
        projectile_type    = r.read_uint8()          # 0x10 — Projectile type
        alt_dice_thrown   = r.read_uint8()          # 0x11 — Alternative dice thrown
        speed            = r.read_uint8()          # 0x12 — Speed
        alt_damage_bonus = r.read_int8()           # 0x13 — Alternative damage bonus
        thac0_bonus      = r.read_int16()          # 0x14–0x15 — THAC0 bonus
        dice_sides       = r.read_uint8()          # 0x16
        primary_type     = r.read_uint8()          # 0x17
        dice_thrown       = r.read_uint8()          # 0x18 — Dice thrown
        secondary_type   = r.read_uint8()          # 0x19
        damage_bonus     = r.read_int16()          # 0x1A–0x1B
        damage_type      = r.read_uint16()         # 0x1C–0x1D
        feature_count    = r.read_uint16()         # 0x1E–0x1F
        feature_offset   = r.read_uint16()         # 0x20–0x21
        charges          = r.read_uint16()         # 0x22–0x23
        charge_depletion = r.read_uint16()         # 0x24–0x25
        flags            = r.read_uint32()         # 0x26–0x29
        projectile_anim  = r.read_uint16()         # 0x2A–0x2B
        melee_anim       = [r.read_uint16() for _ in range(3)]  # 0x2C–0x31
        unused_0x32     = r.read_uint16()         # 0x32–0x33
        unused_0x34     = r.read_uint16()         # 0x34–0x35
        unused_0x36     = r.read_uint16()         # 0x36–0x37
        return cls(
            attack_type=attack_type, id_req=id_req, location=location,
            alt_dice_sides=alt_dice_sides, use_icon=use_icon,
            target_type=target_type, target_count=target_count,
            range=rng, projectile_type=projectile_type,
            alt_dice_thrown=alt_dice_thrown, speed=speed,
            alt_damage_bonus=alt_damage_bonus, thac0_bonus=thac0_bonus,
            dice_sides=dice_sides, primary_type=primary_type,
            dice_thrown=dice_thrown, secondary_type=secondary_type,
            damage_bonus=damage_bonus, damage_type=damage_type,
            feature_count=feature_count, feature_offset=feature_offset,
            charges=charges, charge_depletion=charge_depletion,
            flags=flags, projectile_anim=projectile_anim,
            melee_anim=melee_anim,
            unused_0x32=unused_0x32,
            unused_0x34=unused_0x34,
            unused_0x36=unused_0x36,
        )

    def _write(self, w: BinaryWriter, feature_offset: int) -> None:
        """Write the 56-byte struct.  *feature_offset* is the global index."""
        w.write_uint8(self.attack_type)           # 0x00
        w.write_uint8(self.id_req)                # 0x01
        w.write_uint8(self.location)              # 0x02
        w.write_uint8(self.alt_dice_sides)        # 0x03
        w.write_resref(str(self.use_icon))        # 0x04–0x0B
        w.write_uint8(self.target_type)           # 0x0C
        w.write_uint8(self.target_count)          # 0x0D
        w.write_uint16(self.range)                # 0x0E–0x0F
        w.write_uint8(self.projectile_type)         # 0x10
        w.write_uint8(self.alt_dice_thrown)        # 0x11
        w.write_uint8(self.speed)                 # 0x12
        w.write_int8(self.alt_damage_bonus)       # 0x13
        w.write_int16(self.thac0_bonus)           # 0x14–0x15
        w.write_uint8(self.dice_sides)            # 0x16
        w.write_uint8(self.primary_type)          # 0x17
        w.write_uint8(self.dice_thrown)            # 0x18
        w.write_uint8(self.secondary_type)        # 0x19
        w.write_int16(self.damage_bonus)          # 0x1A–0x1B
        w.write_uint16(self.damage_type)          # 0x1C–0x1D
        w.write_uint16(len(self.features))        # 0x1E–0x1F
        w.write_uint16(feature_offset)            # 0x20–0x21
        w.write_uint16(self.charges)              # 0x22–0x23
        w.write_uint16(self.charge_depletion)     # 0x24–0x25
        w.write_uint32(self.flags)                # 0x26–0x29
        w.write_uint16(self.projectile_anim)      # 0x2A–0x2B
        for v in (self.melee_anim + [0, 0, 0])[:3]:
            w.write_uint16(v)                     # 0x2C–0x31
        w.write_uint16(self.unused_0x32)         # 0x32–0x33
        w.write_uint16(self.unused_0x34)         # 0x34–0x35
        w.write_uint16(self.unused_0x36)         # 0x36–0x37

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        d: dict = {
            "attack_type":  self.attack_type,
            "target_type":  self.target_type,
            "range":        self.range,
            "charges":      self.charges,
        }
        if self.use_icon:           d["use_icon"]          = self.use_icon.to_json()
        if self.id_req:             d["id_req"]            = self.id_req
        if self.location:           d["location"]          = self.location
        if self.target_count:       d["target_count"]      = self.target_count
        if self.projectile_type:      d["projectile_type"]     = self.projectile_type
        if self.alt_dice_thrown:     d["alt_dice_thrown"]    = self.alt_dice_thrown
        if self.alt_dice_sides:     d["alt_dice_sides"]    = self.alt_dice_sides
        if self.speed:              d["speed"]             = self.speed
        if self.alt_damage_bonus:   d["alt_damage_bonus"]  = self.alt_damage_bonus
        if self.thac0_bonus:        d["thac0_bonus"]       = self.thac0_bonus
        if self.dice_thrown:         d["dice_thrown"]        = self.dice_thrown
        if self.dice_sides:         d["dice_sides"]        = self.dice_sides
        if self.damage_bonus:       d["damage_bonus"]      = self.damage_bonus
        if self.damage_type:        d["damage_type"]       = self.damage_type
        if self.primary_type:       d["primary_type"]      = self.primary_type
        if self.secondary_type:     d["secondary_type"]    = self.secondary_type
        if self.charge_depletion:   d["charge_depletion"]  = self.charge_depletion
        if self.flags:              d["flags"]             = self.flags
        if self.projectile_anim:    d["projectile_anim"]   = self.projectile_anim
        if any(self.melee_anim):    d["melee_anim"]        = self.melee_anim
        if self.unused_0x32:       d["unused_0x32"]      = self.unused_0x32
        if self.unused_0x34:       d["unused_0x34"]      = self.unused_0x34
        if self.unused_0x36:       d["unused_0x36"]      = self.unused_0x36
        if self.feature_offset:     d["feature_offset"]    = self.feature_offset
        if self.features:
            d["features"] = [f.to_json() for f in self.features]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "ExtendedHeader":
        eh = cls(
            attack_type      = d.get("attack_type",      AttackType.NONE),
            id_req           = d.get("id_req",           0),
            location         = d.get("location",         0),
            alt_dice_sides   = d.get("alt_dice_sides",   0),
            use_icon         = ResRef.from_json(d.get("use_icon", "")),
            target_type      = d.get("target_type",      TargetType.INVALID),
            target_count     = d.get("target_count",     0),
            range            = d.get("range",            0),
            projectile_type    = d.get("projectile_type",    0),
            alt_dice_thrown   = d.get("alt_dice_thrown",   0),
            speed            = d.get("speed",            0),
            alt_damage_bonus = d.get("alt_damage_bonus", 0),
            thac0_bonus      = d.get("thac0_bonus",      0),
            dice_sides       = d.get("dice_sides",       0),
            primary_type     = d.get("primary_type",     0),
            dice_thrown       = d.get("dice_thrown",       0),
            secondary_type   = d.get("secondary_type",   0),
            damage_bonus     = d.get("damage_bonus",     0),
            damage_type      = d.get("damage_type",      0),
            charges          = d.get("charges",          0),
            charge_depletion = d.get("charge_depletion", 0),
            flags            = d.get("flags",            0),
            projectile_anim  = d.get("projectile_anim",  0),
            melee_anim       = d.get("melee_anim",       [0, 0, 0]),
            unused_0x32     = d.get("unused_0x32",     0),
            unused_0x34     = d.get("unused_0x34",     0),
            unused_0x36     = d.get("unused_0x36",     0),
            feature_offset  = d.get("feature_offset",  0),
        )
        eh.features = [FeatureBlock.from_json(f) for f in d.get("features", [])]
        return eh


# ---------------------------------------------------------------------------
# Item header  (114 / 116 bytes)
# ---------------------------------------------------------------------------

@dataclass
class ItmHeader:
    """
    The top-level item record.

    Contains identity, stats, usability flags, and the offsets/counts that
    locate extended headers and feature blocks within the file.  Offset
    fields (*ext_header_offset*, etc.) are managed automatically by
    :class:`ItmFile` on write; you do not need to set them manually.
    """
    # Identity
    unidentified_name:  StrRef = StrRef(0xFFFFFFFF)   # StrRef
    identified_name:    StrRef = StrRef(0xFFFFFFFF)   # StrRef
    replacement_item:   ResRef = ResRef("")      # ResRef — item replaced when depleted
    flags:              int = ItemFlag.DROPPABLE
    item_type:          int = ItemType.MISCELLANEOUS
    usability:          int = 0             # uint32 — usability bitmask (who can use)
    animation:          str = "  "         # char[2] — item animation code

    # Level / school requirements
    min_level:          int = 0             # uint16
    min_strength:       int = 0             # uint16
    min_strength_bonus: int = 0             # uint8
    kit_usability_1:    int = 0             # uint8
    min_intelligence:   int = 0             # uint8
    kit_usability_2:    int = 0             # uint8
    min_dexterity:      int = 0             # uint8
    kit_usability_3:    int = 0             # uint8
    min_wisdom:         int = 0             # uint8
    kit_usability_4:    int = 0             # uint8
    min_constitution:   int = 0             # uint8
    weapon_proficiency: int = 0             # uint8
    min_charisma:       int = 0             # uint16

    # Economy
    base_value:         int = 0             # uint32 — price in gold pieces
    max_stack:          int = 1             # uint16
    item_icon:          ResRef = ResRef("")      # ResRef — inventory BAM
    lore_required:      int = 0             # uint16 — lore to identify
    ground_icon:        ResRef = ResRef("")      # ResRef — dropped-on-ground BAM
    base_weight:        int = 0             # int32  — in tenths of a pound
    unidentified_desc:  StrRef = StrRef(0xFFFFFFFF)   # StrRef
    identified_desc:    StrRef = StrRef(0xFFFFFFFF)   # StrRef
    description_icon:   ResRef = ResRef("")      # ResRef
    enchantment:        int = 0             # int32  — "+N" enchantment level

    # Offsets (managed by ItmFile, stored here for completeness)
    ext_header_offset:  int = 0             # uint32
    ext_header_count:   int = 0             # uint16
    feature_offset:     int = 0             # uint32
    equip_feature_index: int = 0            # uint16 — index of first equip effect
    equip_feature_count: int = 0            # uint16

    # V1.1 only
    projectile_type:    int = 0             # uint16  (0 in V1 files)

    # ------------------------------------------------------------------
    # Binary I/O
    # ------------------------------------------------------------------

    @classmethod
    def _read(cls, r: BinaryReader, version: bytes) -> "ItmHeader":
        unidentified_name   = StrRef(r.read_uint32())
        identified_name     = StrRef(r.read_uint32())
        replacement_item    = ResRef(r.read_resref())
        flags               = r.read_uint32()
        item_type           = r.read_uint16()
        usability           = r.read_uint32()
        animation           = r.read_bytes(2).decode("latin-1")
        min_level           = r.read_uint16()
        min_strength        = r.read_uint16()
        min_strength_bonus  = r.read_uint8()
        kit_usability_1     = r.read_uint8()
        min_intelligence    = r.read_uint8()
        kit_usability_2     = r.read_uint8()
        min_dexterity       = r.read_uint8()
        kit_usability_3     = r.read_uint8()
        min_wisdom          = r.read_uint8()
        kit_usability_4     = r.read_uint8()
        min_constitution    = r.read_uint8()
        weapon_proficiency  = r.read_uint8()
        min_charisma        = r.read_uint16()
        base_value          = r.read_uint32()
        max_stack           = r.read_uint16()
        item_icon           = ResRef(r.read_resref())
        lore_required       = r.read_uint16()
        ground_icon         = ResRef(r.read_resref())
        base_weight         = r.read_int32()
        unidentified_desc   = StrRef(r.read_uint32())
        identified_desc     = StrRef(r.read_uint32())
        description_icon    = ResRef(r.read_resref())
        enchantment         = r.read_int32()
        ext_header_offset   = r.read_uint32()
        ext_header_count    = r.read_uint16()
        feature_offset      = r.read_uint32()
        equip_feature_index = r.read_uint16()
        equip_feature_count = r.read_uint16()

        projectile_type = 0
        if version == VERSION_V11:
            projectile_type = r.read_uint16()

        return cls(
            unidentified_name=unidentified_name,
            identified_name=identified_name,
            replacement_item=replacement_item,
            flags=flags, item_type=item_type, usability=usability,
            animation=animation, min_level=min_level,
            min_strength=min_strength, min_strength_bonus=min_strength_bonus,
            kit_usability_1=kit_usability_1, min_intelligence=min_intelligence,
            kit_usability_2=kit_usability_2, min_dexterity=min_dexterity,
            kit_usability_3=kit_usability_3, min_wisdom=min_wisdom,
            kit_usability_4=kit_usability_4, min_constitution=min_constitution,
            weapon_proficiency=weapon_proficiency, min_charisma=min_charisma,
            base_value=base_value, max_stack=max_stack, item_icon=item_icon,
            lore_required=lore_required, ground_icon=ground_icon,
            base_weight=base_weight, unidentified_desc=unidentified_desc,
            identified_desc=identified_desc, description_icon=description_icon,
            enchantment=enchantment, ext_header_offset=ext_header_offset,
            ext_header_count=ext_header_count, feature_offset=feature_offset,
            equip_feature_index=equip_feature_index,
            equip_feature_count=equip_feature_count,
            projectile_type=projectile_type,
        )

    def _write(self, w: BinaryWriter, version: bytes) -> None:
        w.write_uint32(int(self.unidentified_name))
        w.write_uint32(int(self.identified_name))
        w.write_resref(str(self.replacement_item))
        w.write_uint32(self.flags)
        w.write_uint16(self.item_type)
        w.write_uint32(self.usability)
        anim = self.animation.encode("latin-1")[:2].ljust(2, b" ")
        w.write_bytes(anim)
        w.write_uint16(self.min_level)
        w.write_uint16(self.min_strength)
        w.write_uint8(self.min_strength_bonus)
        w.write_uint8(self.kit_usability_1)
        w.write_uint8(self.min_intelligence)
        w.write_uint8(self.kit_usability_2)
        w.write_uint8(self.min_dexterity)
        w.write_uint8(self.kit_usability_3)
        w.write_uint8(self.min_wisdom)
        w.write_uint8(self.kit_usability_4)
        w.write_uint8(self.min_constitution)
        w.write_uint8(self.weapon_proficiency)
        w.write_uint16(self.min_charisma)
        w.write_uint32(self.base_value)
        w.write_uint16(self.max_stack)
        w.write_resref(str(self.item_icon))
        w.write_uint16(self.lore_required)
        w.write_resref(str(self.ground_icon))
        w.write_int32(self.base_weight)
        w.write_uint32(int(self.unidentified_desc))
        w.write_uint32(int(self.identified_desc))
        w.write_resref(str(self.description_icon))
        w.write_int32(self.enchantment)
        w.write_uint32(self.ext_header_offset)
        w.write_uint16(self.ext_header_count)
        w.write_uint32(self.feature_offset)
        w.write_uint16(self.equip_feature_index)
        w.write_uint16(self.equip_feature_count)
        if version == VERSION_V11:
            w.write_uint16(self.projectile_type)


# ---------------------------------------------------------------------------
# ItmFile — top-level container
# ---------------------------------------------------------------------------

class ItmFile:
    """
    A complete ITM resource: header, extended headers, and feature blocks.

    Feature block storage
    ~~~~~~~~~~~~~~~~~~~~~
    The binary format stores all feature blocks as a **single flat array**.
    Both the extended headers (ability effects) and the equip effects index
    into this array independently via (index, count) pairs.  The two sets
    may overlap, be discontiguous, or share blocks — and the array may
    contain unreferenced trailing blocks written by Bioware's tools.

    This class preserves the flat array verbatim in ``feature_blocks``.
    Do not reorder or deduplicate it; the indices stored in the headers
    must remain valid.

    Convenience accessors
    ~~~~~~~~~~~~~~~~~~~~~
    ``itm.equip_features``
        Read-only view: the slice of ``feature_blocks`` referenced by the
        equip_feature_index / equip_feature_count header fields.

    ``eh.features``  (on each :class:`ExtendedHeader`)
        Read-only view: the slice of ``feature_blocks`` for that ability.

    Modifying feature blocks
    ~~~~~~~~~~~~~~~~~~~~~~~~
    Append to ``feature_blocks`` directly and update the relevant index
    fields on the header or extended header::

        idx = len(itm.feature_blocks)
        itm.feature_blocks.append(FeatureBlock(opcode=74, parameter2=1,
                                                timing_mode=2))
        itm.header.equip_feature_index = idx
        itm.header.equip_feature_count += 1

    Usage::

        itm = ItmFile.from_file("SW1H01.itm")
        eh = itm.extended_headers[0]
        print(eh.dice_thrown, "d", eh.dice_sides, "+", eh.damage_bonus)
        for fb in itm.equip_features:
            print("equip fx:", fb.opcode)
    """

    def __init__(
        self,
        header:           ItmHeader,
        extended_headers: List[ExtendedHeader],
        feature_blocks:   List[FeatureBlock],
        version:          bytes = VERSION_V1,
        source_path:      Optional[Path] = None,
    ) -> None:
        self.header           = header
        self.extended_headers = extended_headers
        # Flat feature block pool — preserves original file layout exactly.
        self.feature_blocks   = feature_blocks
        self.version          = version
        self.source_path      = source_path

    # ------------------------------------------------------------------
    # Convenience views (read-only slices into feature_blocks)
    # ------------------------------------------------------------------

    @property
    def equip_features(self) -> List[FeatureBlock]:
        """Feature blocks active while the item is equipped."""
        idx = self.header.equip_feature_index
        cnt = self.header.equip_feature_count
        return self.feature_blocks[idx : idx + cnt]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "ItmFile":
        """Parse an ITM resource from raw bytes."""
        r = BinaryReader(data)

        try:
            r.expect_signature(SIGNATURE)
            version = r.read_bytes(4)
            if version not in (VERSION_V1, VERSION_V11):
                raise ValueError(f"Unsupported ITM version {version!r}.")
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        header = ItmHeader._read(r, version)

        # --- Extended headers ---
        r.seek(header.ext_header_offset)
        ext_headers: List[ExtendedHeader] = []
        for _ in range(header.ext_header_count):
            ext_headers.append(ExtendedHeader._read(r))

        # --- Feature block flat array ---
        # Read every feature block from feature_offset to EOF.
        # The count is determined by file size — Bioware tools sometimes write
        # more blocks than strictly referenced, and we must preserve them all
        # for a lossless round-trip.
        feature_blocks: List[FeatureBlock] = []
        if header.feature_offset < len(data):
            r.seek(header.feature_offset)
            remaining = len(data) - header.feature_offset
            block_count = remaining // FEATURE_BLOCK_SIZE
            for _ in range(block_count):
                feature_blocks.append(FeatureBlock._read(r))

        # Attach the ability-feature view to each extended header.
        # eh.feature_offset and eh.feature_count index into feature_blocks.
        for eh in ext_headers:
            eh.features = feature_blocks[
                eh.feature_offset : eh.feature_offset + eh.feature_count
            ]

        return cls(header, ext_headers, feature_blocks, version=version)

    @classmethod
    def from_file(cls, path: str | Path) -> "ItmFile":
        """Read and parse an ITM file from disk."""
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Serialise the item back to its binary representation."""
        version     = self.version
        header_size = HEADER_SIZE_V11 if version == VERSION_V11 else HEADER_SIZE_V1

        # Offsets: extended headers start immediately after the file header;
        # feature blocks start immediately after the extended headers.
        ext_header_offset = header_size
        feature_offset    = ext_header_offset + len(self.extended_headers) * EXT_HEADER_SIZE

        # Patch header offset fields.
        # equip_feature_index and equip_feature_count are NOT recomputed here —
        # they must preserve whatever the original (or caller) set them to,
        # because the flat feature_blocks array is written verbatim.
        self.header.ext_header_offset = ext_header_offset
        self.header.ext_header_count  = len(self.extended_headers)
        self.header.feature_offset    = feature_offset
        # equip_feature_index / equip_feature_count: left as-is on round-trip.
        # When building from scratch call itm.header.equip_feature_index etc. directly.

        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(version)
        self.header._write(w, version)

        # Extended headers — each writes its own feature_offset index
        for eh in self.extended_headers:
            eh._write(w, eh.feature_offset)

        # Flat feature block pool — written verbatim
        for fb in self.feature_blocks:
            fb._write(w)

        return w.to_bytes()

    def to_file(self, path: str | Path) -> None:
        """Write the item to disk."""
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        h = self.header
        d: dict = {
            "format":  "itm",
            "version": version_str(self.version),
            "header": {
                "unidentified_name":    h.unidentified_name.to_json(),
                "identified_name":      h.identified_name.to_json(),
                "item_type":            h.item_type,
                "flags":                h.flags,
                "usability":            h.usability,
                "base_value":           h.base_value,
                "base_weight":          h.base_weight,
                "max_stack":            h.max_stack,
                "lore_required":        h.lore_required,
                "enchantment":          h.enchantment,
                "unidentified_desc":    h.unidentified_desc.to_json(),
                "identified_desc":      h.identified_desc.to_json(),
                "equip_feature_index":  h.equip_feature_index,
                "equip_feature_count":  h.equip_feature_count,
            },
        }
        hd = d["header"]
        if h.replacement_item:   hd["replacement_item"]   = h.replacement_item.to_json()
        if h.animation.strip():  hd["animation"]          = h.animation
        if h.item_icon:          hd["item_icon"]          = h.item_icon.to_json()
        if h.ground_icon:        hd["ground_icon"]        = h.ground_icon.to_json()
        if h.description_icon:   hd["description_icon"]   = h.description_icon.to_json()
        if h.min_level:          hd["min_level"]          = h.min_level
        if h.min_strength:       hd["min_strength"]       = h.min_strength
        if h.min_strength_bonus: hd["min_strength_bonus"] = h.min_strength_bonus
        if h.min_intelligence:   hd["min_intelligence"]   = h.min_intelligence
        if h.min_dexterity:      hd["min_dexterity"]      = h.min_dexterity
        if h.min_wisdom:         hd["min_wisdom"]         = h.min_wisdom
        if h.min_constitution:   hd["min_constitution"]   = h.min_constitution
        if h.min_charisma:       hd["min_charisma"]       = h.min_charisma
        if h.weapon_proficiency: hd["weapon_proficiency"] = h.weapon_proficiency
        if h.kit_usability_1:    hd["kit_usability_1"]    = h.kit_usability_1
        if h.kit_usability_2:    hd["kit_usability_2"]    = h.kit_usability_2
        if h.kit_usability_3:    hd["kit_usability_3"]    = h.kit_usability_3
        if h.kit_usability_4:    hd["kit_usability_4"]    = h.kit_usability_4
        if self.version == VERSION_V11 and h.projectile_type:
            hd["projectile_type"] = h.projectile_type

        if self.extended_headers:
            d["extended_headers"] = [eh.to_json() for eh in self.extended_headers]
        if self.feature_blocks:
            d["feature_blocks"] = [fb.to_json() for fb in self.feature_blocks]

        return d

    @classmethod
    def from_json(cls, d: dict) -> "ItmFile":
        """Deserialise from a JSON-compatible dict."""
        ver_str = d.get("version", "V1")
        version = VERSION_V11 if ver_str == "V1.1" else VERSION_V1

        hd = d.get("header", {})
        header = ItmHeader(
            unidentified_name=StrRef.from_json(hd.get("unidentified_name", 0xFFFFFFFF)),
            identified_name=StrRef.from_json(hd.get("identified_name", 0xFFFFFFFF)),
            replacement_item    = ResRef.from_json(hd.get("replacement_item",   "")),
            flags               = hd.get("flags",              ItemFlag.DROPPABLE),
            item_type           = hd.get("item_type",          ItemType.MISCELLANEOUS),
            usability           = hd.get("usability",          0),
            animation           = hd.get("animation",          "  "),
            min_level           = hd.get("min_level",          0),
            min_strength        = hd.get("min_strength",       0),
            min_strength_bonus  = hd.get("min_strength_bonus", 0),
            kit_usability_1     = hd.get("kit_usability_1",    0),
            min_intelligence    = hd.get("min_intelligence",   0),
            kit_usability_2     = hd.get("kit_usability_2",    0),
            min_dexterity       = hd.get("min_dexterity",      0),
            kit_usability_3     = hd.get("kit_usability_3",    0),
            min_wisdom          = hd.get("min_wisdom",         0),
            kit_usability_4     = hd.get("kit_usability_4",    0),
            min_constitution    = hd.get("min_constitution",   0),
            weapon_proficiency  = hd.get("weapon_proficiency", 0),
            min_charisma        = hd.get("min_charisma",       0),
            base_value          = hd.get("base_value",         0),
            max_stack           = hd.get("max_stack",          1),
            item_icon           = ResRef.from_json(hd.get("item_icon",          "")),
            lore_required       = hd.get("lore_required",      0),
            ground_icon         = ResRef.from_json(hd.get("ground_icon",        "")),
            base_weight         = hd.get("base_weight",        0),
            unidentified_desc=StrRef.from_json(hd.get("unidentified_desc", 0xFFFFFFFF)),
            identified_desc=StrRef.from_json(hd.get("identified_desc", 0xFFFFFFFF)),
            description_icon    = ResRef.from_json(hd.get("description_icon",   "")),
            enchantment         = hd.get("enchantment",        0),
            equip_feature_index = hd.get("equip_feature_index", 0),
            equip_feature_count = hd.get("equip_feature_count", 0),
            projectile_type     = hd.get("projectile_type",    0),
        )

        ext_headers = [
            ExtendedHeader.from_json(e) for e in d.get("extended_headers", [])
        ]
        feature_blocks = [
            FeatureBlock.from_json(f) for f in d.get("feature_blocks", [])
        ]
        # Reattach feature views to extended headers.
        # If the extended header JSON had an embedded "features" list (the normal
        # case), eh.features is already populated by ExtendedHeader.from_json.
        # Only use the flat feature_blocks slice when the embedded list was absent.
        for eh in ext_headers:
            if not eh.features and feature_blocks:
                eh.features = feature_blocks[
                    eh.feature_offset : eh.feature_offset + eh.feature_count
                ]

        return cls(header, ext_headers, feature_blocks, version=version)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "ItmFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Convenience helpers for building items from scratch
    # ------------------------------------------------------------------

    def append_equip_feature(self, fb: FeatureBlock) -> int:
        """
        Append *fb* to the feature pool and extend the equip feature range.

        The equip features must already form a contiguous block at the end
        of ``feature_blocks`` (or be empty).  Returns the new block's index.

        For items built from scratch call this after all ability features
        have been added so equip features land at the end of the pool.
        """
        # If no equip features yet, set the index to current pool end
        if self.header.equip_feature_count == 0:
            self.header.equip_feature_index = len(self.feature_blocks)
        self.feature_blocks.append(fb)
        self.header.equip_feature_count += 1
        return len(self.feature_blocks) - 1

    def append_ability_feature(self, eh_index: int, fb: FeatureBlock) -> int:
        """
        Append *fb* to the feature pool and extend the given extended
        header's feature range.  Returns the new block's index.

        Extended header features must be the last thing added before
        equip features, and each header's features must be contiguous.
        """
        eh = self.extended_headers[eh_index]
        if eh.feature_count == 0:
            eh.feature_offset = len(self.feature_blocks)
        self.feature_blocks.append(fb)
        eh.feature_count += 1
        eh.features = self.feature_blocks[
            eh.feature_offset : eh.feature_offset + eh.feature_count
        ]
        return len(self.feature_blocks) - 1

    def add_extended_header(self, eh: ExtendedHeader) -> None:
        """Append a new attack mode / item ability."""
        self.extended_headers.append(eh)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<ItmFile {src!r} "
            f"type={self.header.item_type:#06x} "
            f"abilities={len(self.extended_headers)} "
            f"equip_fx={self.header.equip_feature_count} "
            f"total_blocks={len(self.feature_blocks)}>"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def version_str(version: bytes) -> str:
    """Return a human-readable version string from a raw version field."""
    return version.rstrip(b" ").decode("latin-1")