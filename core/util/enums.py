"""
core/util/enums.py

Centralised home for every IntEnum and IntFlag used anywhere in the project.

All format modules (itm.py, spl.py, are.py, cre.py, …) import their enums
from here.  Nothing else should define IntEnum / IntFlag constants — if a new
constant is needed, add it here.

Rationale
---------
Keeping enums in one place avoids the "which file was that in?" hunt across
dozens of format modules.  Enums are shared vocabulary, not file-format
implementation details.  They belong in core/util/ alongside the other
shared primitive types (ResRef, StrRef, IdsRef).

Import pattern for format files::

    from core.util.enums import ItemType, ItemFlag, AttackType   # etc.

Organisation
------------
Enums are grouped by the file format or domain they primarily describe,
with a clear header comment for each group.  Shared enums (used by multiple
formats, e.g. EffectTarget) appear in a dedicated "Shared / cross-format"
section.
"""

from __future__ import annotations

from enum import IntEnum, IntFlag
from typing import Dict


# ===========================================================================
# Resource registry (CHITIN.KEY / BIFF)
# ===========================================================================

class ResType(IntEnum):
    """
    Infinity Engine resource type codes.

    These are the uint16 values stored in both KEY resource entries and
    BIFF file entries to identify what kind of data a resource contains.
    """
    BMP    = 0x0001
    MVE    = 0x0002
    WAV    = 0x0004
    WFX    = 0x0005
    PLT    = 0x0006
    BAM    = 0x03E8
    WED    = 0x03E9
    CHU    = 0x03EA
    TIS    = 0x03EB
    MOS    = 0x03EC
    ITM    = 0x03ED
    SPL    = 0x03EE
    BCS    = 0x03EF
    IDS    = 0x03F0
    CRE    = 0x03F1
    ARE    = 0x03F2
    DLG    = 0x03F3
    TWO_DA = 0x03F4
    GAM    = 0x03F5
    STO    = 0x03F6
    WMP    = 0x03F7
    CHR    = 0x03F8
    BS     = 0x03F9
    VVC    = 0x03FB
    VEF    = 0x03FC
    PRO    = 0x03FD
    BIO    = 0x03FE
    WBM    = 0x03FF
    FNT    = 0x0400
    GUI    = 0x0402
    SQL    = 0x0403
    PVRZ   = 0x0404
    GLSL   = 0x0405
    MENU   = 0x0408
    LUA    = 0x0409
    TTF    = 0x040A
    PNG    = 0x040B
    BAH    = 0x044C
    INI    = 0x0802
    SRC    = 0x0803

    @classmethod
    def extension(cls, code: int) -> str:
        """Return a lowercase file extension for a resource type code."""
        _EXT: Dict[int, str] = {
            0x0001: "bmp",  0x0002: "mve",  0x0004: "wav",  0x0005: "wfx",
            0x0006: "plt",  0x03E8: "bam",  0x03E9: "wed",  0x03EA: "chu",
            0x03EB: "tis",  0x03EC: "mos",  0x03ED: "itm",  0x03EE: "spl",
            0x03EF: "bcs",  0x03F0: "ids",  0x03F1: "cre",  0x03F2: "are",
            0x03F3: "dlg",  0x03F4: "2da",  0x03F5: "gam",  0x03F6: "sto",
            0x03F7: "wmp",  0x03F8: "chr",  0x03F9: "bs",   0x03FB: "vvc",
            0x03FC: "vef",  0x03FD: "pro",  0x03FE: "bio",  0x03FF: "wbm",
            0x0400: "fnt",  0x0402: "gui",  0x0403: "sql",  0x0404: "pvrz",
            0x0405: "glsl", 0x0408: "menu", 0x0409: "lua",  0x040A: "ttf",
            0x040B: "png",  0x044C: "bah",  0x0802: "ini",  0x0803: "src",
        }
        return _EXT.get(code, f"res_{code:04x}")


# ===========================================================================
# Shared / cross-format  (used by ITM, SPL, CRE, …)
# ===========================================================================

class EffectTarget(IntEnum):
    """
    Feature-block / effect target type.

    Stored at offset 0x02 in a V1 feature block and offset 0x20 in a V2
    EFF body.  Identical layout used in ITM, SPL, and embedded CRE effects.
    """
    NONE                  = 0
    SELF                  = 1
    PRESET_TARGET         = 2
    PARTY                 = 3
    EVERYONE              = 4
    EVERYONE_EXCEPT_PARTY = 5
    ORIGINAL_CASTER       = 6
    EVERYONE_IN_AREA      = 7
    EVERYONE_EXCEPT_SELF  = 8
    ORIGINAL_CASTER_GROUP = 9


class EffectTiming(IntEnum):
    """
    Feature-block timing / duration mode.

    Stored at offset 0x08 in a V1 feature block.  Shared by ITM and SPL.
    """
    DURATION              = 0
    PERMANENT_UNSAVED     = 1
    WHILE_EQUIPPED        = 2
    DELAYED               = 3
    DELAYED_PERMANENT     = 4
    DELAYED_UNSAVED       = 5
    DURATION_AFTER_DEATH  = 6
    PERMANENT_AFTER_DEATH = 7
    INDEPENDENT           = 8
    PERMANENT_SAVED       = 9


# ===========================================================================
# ITM — Item format  (core/formats/itm.py)
# ===========================================================================

class ItemType(IntEnum):
    """
    Item category codes, stored at offset 0x1C in the ITM header.

    These map directly to the game's item-type system and control which
    equipment slots the item can occupy, what proficiency applies, and how
    the game treats the item in scripting.
    """
    BOOKS_MISC      = 0x0000
    MISCELLANEOUS   = 0x0000  # legacy alias
    AMULET          = 0x0001
    ARMOUR          = 0x0002
    BELT            = 0x0003
    BOOTS           = 0x0004
    ARROWS          = 0x0005
    BRACERS         = 0x0006
    HEADGEAR        = 0x0007
    KEYS            = 0x0008
    POTION          = 0x0009
    RING            = 0x000A
    SCROLLS         = 0x000B
    SHIELD          = 0x000C
    FOOD            = 0x000D
    BULLETS         = 0x000E
    BOW             = 0x000F
    DAGGER          = 0x0010
    MACE            = 0x0011
    SLING           = 0x0012
    SMALL_SWORD     = 0x0013
    LARGE_SWORD     = 0x0014
    HAMMER          = 0x0015
    MORNINGSTAR     = 0x0016
    FLAIL           = 0x0017
    DARTS           = 0x0018
    AXE             = 0x0019
    QUARTERSTAFF    = 0x001A
    CROSSBOW        = 0x001B
    HAND_TO_HAND    = 0x001C
    SPEAR           = 0x001D
    HALBERD         = 0x001E
    BOLTS           = 0x001F
    CLOAK           = 0x0020
    GOLD            = 0x0021
    GEM             = 0x0022
    WAND            = 0x0023
    CONTAINER       = 0x0024  # containers / eye / broken armor
    BOOKS2          = 0x0025  # books / broken shields / bracelets
    FAMILIAR        = 0x0026  # familiars / broken swords / earrings
    TATTOO          = 0x0027  # PST
    LENS            = 0x0028  # PST
    BUCKLER         = 0x0029  # bucklers / teeth
    CANDLE          = 0x002A
    UNKNOWN_2B      = 0x002B
    CLUB            = 0x002C  # IWD
    UNKNOWN_2D      = 0x002D
    UNKNOWN_2E      = 0x002E
    LARGE_SHIELD    = 0x002F  # IWD
    UNKNOWN_30      = 0x0030
    MEDIUM_SHIELD   = 0x0031  # IWD
    NOTES           = 0x0032
    UNKNOWN_33      = 0x0033
    UNKNOWN_34      = 0x0034
    SMALL_SHIELD    = 0x0035  # IWD
    UNKNOWN_36      = 0x0036
    TELESCOPE       = 0x0037  # IWD
    DRINK           = 0x0038  # IWD
    GREAT_SWORD     = 0x0039  # IWD
    CONTAINER2      = 0x003A
    FUR             = 0x003B
    LEATHER_ARMOUR  = 0x003C
    STUDDED_LEATHER = 0x003D
    CHAIN_MAIL      = 0x003E
    SPLINT_MAIL     = 0x003F
    HALF_PLATE      = 0x0040
    FULL_PLATE      = 0x0041
    HIDE_ARMOUR     = 0x0042
    ROBE            = 0x0043
    UNKNOWN_44      = 0x0044
    BASTARD_SWORD   = 0x0045
    SCARF           = 0x0046
    FOOD2           = 0x0047  # IWD2
    HAT             = 0x0048
    GAUNTLET        = 0x0049


    THROWING_AXE    = 0x0048
    CROSSBOW_BOLT   = 0x0049


class ItemFlag(IntFlag):
    """
    Item header flags, stored as a dword at offset 0x18 in the ITM header.

    EE-only bits are marked; they are safe to read on non-EE files (they
    will simply be 0).
    """
    NONE               = 0x00000000
    UNSELLABLE         = 0x00000001  # critical item — cannot be sold
    TWO_HANDED         = 0x00000002
    DROPPABLE          = 0x00000004
    DISPLAYABLE        = 0x00000008
    CURSED             = 0x00000010
    NOT_COPYABLE       = 0x00000020  # cannot scribe to spellbook (scrolls)
    MAGICAL            = 0x00000040
    LEFT_HANDED        = 0x00000080
    SILVER             = 0x00000100  # interacts with opcode #120
    COLD_IRON          = 0x00000200  # interacts with opcode #120
    OFF_HANDED         = 0x00000400
    CONVERSABLE        = 0x00000800
    EE_FAKE_TWO_HANDED = 0x00001000  # EE only
    EE_FORBID_OFF_HAND = 0x00002000  # EE only


class ItemFlagEE(IntFlag):
    """
    ITM header flags for EE titles (BGEE/BG2EE/IWDEE/PSTEE).
    """
    NONE               = 0x00000000
    UNSELLABLE         = 0x00000001
    TWO_HANDED         = 0x00000002
    DROPPABLE          = 0x00000004
    DISPLAYABLE        = 0x00000008
    CURSED             = 0x00000010
    NOT_COPYABLE       = 0x00000020
    MAGICAL            = 0x00000040
    LEFT_HANDED        = 0x00000080
    SILVER             = 0x00000100
    COLD_IRON          = 0x00000200
    OFF_HANDED         = 0x00000400
    CONVERSABLE        = 0x00000800
    FAKE_TWO_HANDED    = 0x00001000
    FORBID_OFF_HAND    = 0x00002000
    ADAMANTINE         = 0x00008000  # BGEE
    CRIT_AVERSION_TOGGLE = 0x00020000  # EE/TobEx
    UNDISPELLABLE_MAGICAL_SLOT = 0x01000000  # EE/TobEx


class ItemFlagPSTEE(IntFlag):
    """
    ITM header flags for PSTEE (differs in a few EE-only bits).
    """
    NONE               = 0x00000000
    UNSELLABLE         = 0x00000001
    TWO_HANDED         = 0x00000002
    DROPPABLE          = 0x00000004
    DISPLAYABLE        = 0x00000008
    CURSED             = 0x00000010
    NOT_COPYABLE       = 0x00000020
    MAGICAL            = 0x00000040
    LEFT_HANDED        = 0x00000080
    SILVER             = 0x00000100
    COLD_IRON          = 0x00000200
    OFF_HANDED         = 0x00000400
    CONVERSABLE        = 0x00000800
    FAKE_TWO_HANDED    = 0x00001000
    FORBID_OFF_HAND    = 0x00002000
    USABLE_IN_INVENTORY = 0x00004000


class ItemUsabilityFlag(IntFlag):
    """
    ITM header usability bitmask (offset 0x1E, dword).

    Bits are set to EXCLUDE a class/align/race from using the item.
    """
    NONE                     = 0x00000000
    # Byte 1
    UNUSABLE_BY_CHAOTIC      = 0x00000001
    UNUSABLE_BY_EVIL         = 0x00000002
    UNUSABLE_BY_GOOD         = 0x00000004
    UNUSABLE_BY_NEUTRAL_GE   = 0x00000008  # neither good nor evil
    UNUSABLE_BY_LAWFUL       = 0x00000010
    UNUSABLE_BY_NEUTRAL_LC   = 0x00000020  # neither lawful nor chaotic
    UNUSABLE_BY_BARD         = 0x00000040
    UNUSABLE_BY_CLERIC       = 0x00000080
    # Byte 2
    UNUSABLE_BY_CLERIC_MAGE  = 0x00000100
    UNUSABLE_BY_CLERIC_THIEF = 0x00000200
    UNUSABLE_BY_CLERIC_RANGER = 0x00000400
    UNUSABLE_BY_FIGHTER      = 0x00000800
    UNUSABLE_BY_FIGHTER_DRUID = 0x00001000
    UNUSABLE_BY_FIGHTER_MAGE = 0x00002000
    UNUSABLE_BY_FIGHTER_CLERIC = 0x00004000
    UNUSABLE_BY_FIGHTER_MAGE_CLERIC = 0x00008000
    # Byte 3
    UNUSABLE_BY_FIGHTER_MAGE_THIEF = 0x00010000
    UNUSABLE_BY_FIGHTER_THIEF     = 0x00020000
    UNUSABLE_BY_MAGE              = 0x00040000
    UNUSABLE_BY_MAGE_THIEF        = 0x00080000
    UNUSABLE_BY_PALADIN           = 0x00100000
    UNUSABLE_BY_RANGER            = 0x00200000
    UNUSABLE_BY_THIEF             = 0x00400000
    UNUSABLE_BY_ELF               = 0x00800000
    # Byte 4
    UNUSABLE_BY_DWARF     = 0x01000000
    UNUSABLE_BY_HALF_ELF  = 0x02000000
    UNUSABLE_BY_HALFLING  = 0x04000000
    UNUSABLE_BY_HUMAN     = 0x08000000
    UNUSABLE_BY_GNOME     = 0x10000000
    UNUSABLE_BY_MONK      = 0x20000000
    UNUSABLE_BY_DRUID     = 0x40000000
    UNUSABLE_BY_HALF_ORC  = 0x80000000


class ItemUsabilityFlagEE(IntFlag):
    """
    ITM header usability bitmask for EE games.

    Same layout as ItemUsabilityFlag, but bit 0x40000000 applies to both
    Druids and Shamans in EE (per IESDP).
    """
    NONE                     = 0x00000000
    # Byte 1
    UNUSABLE_BY_CHAOTIC      = 0x00000001
    UNUSABLE_BY_EVIL         = 0x00000002
    UNUSABLE_BY_GOOD         = 0x00000004
    UNUSABLE_BY_NEUTRAL_GE   = 0x00000008
    UNUSABLE_BY_LAWFUL       = 0x00000010
    UNUSABLE_BY_NEUTRAL_LC   = 0x00000020
    UNUSABLE_BY_BARD         = 0x00000040
    UNUSABLE_BY_CLERIC       = 0x00000080
    # Byte 2
    UNUSABLE_BY_CLERIC_MAGE  = 0x00000100
    UNUSABLE_BY_CLERIC_THIEF = 0x00000200
    UNUSABLE_BY_CLERIC_RANGER = 0x00000400
    UNUSABLE_BY_FIGHTER      = 0x00000800
    UNUSABLE_BY_FIGHTER_DRUID = 0x00001000
    UNUSABLE_BY_FIGHTER_MAGE = 0x00002000
    UNUSABLE_BY_FIGHTER_CLERIC = 0x00004000
    UNUSABLE_BY_FIGHTER_MAGE_CLERIC = 0x00008000
    # Byte 3
    UNUSABLE_BY_FIGHTER_MAGE_THIEF = 0x00010000
    UNUSABLE_BY_FIGHTER_THIEF     = 0x00020000
    UNUSABLE_BY_MAGE              = 0x00040000
    UNUSABLE_BY_MAGE_THIEF        = 0x00080000
    UNUSABLE_BY_PALADIN           = 0x00100000
    UNUSABLE_BY_RANGER            = 0x00200000
    UNUSABLE_BY_THIEF             = 0x00400000
    UNUSABLE_BY_ELF               = 0x00800000
    # Byte 4
    UNUSABLE_BY_DWARF     = 0x01000000
    UNUSABLE_BY_HALF_ELF  = 0x02000000
    UNUSABLE_BY_HALFLING  = 0x04000000
    UNUSABLE_BY_HUMAN     = 0x08000000
    UNUSABLE_BY_GNOME     = 0x10000000
    UNUSABLE_BY_MONK      = 0x20000000
    UNUSABLE_BY_DRUID_SHAMAN = 0x40000000
    UNUSABLE_BY_HALF_ORC  = 0x80000000


class ItemUsabilityFlagPST(IntFlag):
    """
    PST (ITM V1.1) usability bitmask (per IESDP ITM V1.1 table).
    """
    NONE                       = 0x00000000
    # Byte 1
    UNUSABLE_BY_CHAOTIC        = 0x00000001
    UNUSABLE_BY_EVIL           = 0x00000002
    UNUSABLE_BY_GOOD           = 0x00000004
    UNUSABLE_BY_NEUTRAL_GE     = 0x00000008
    UNUSABLE_BY_LAWFUL         = 0x00000010
    UNUSABLE_BY_NEUTRAL_LC     = 0x00000020
    UNUSABLE_BY_SENSATES       = 0x00000040
    UNUSABLE_BY_PRIEST         = 0x00000080
    # Byte 2
    UNUSABLE_BY_GODSMEN        = 0x00000100
    UNUSABLE_BY_ANARCHIST      = 0x00000200
    UNUSABLE_BY_CHAOSMEN       = 0x00000400
    UNUSABLE_BY_FIGHTER        = 0x00000800
    UNUSABLE_BY_NO_FACTION     = 0x00001000
    UNUSABLE_BY_FIGHTER_MAGE   = 0x00002000
    UNUSABLE_BY_DUSTMEN        = 0x00004000
    UNUSABLE_BY_MERCYKILLERS   = 0x00008000
    # Byte 3
    UNUSABLE_BY_INDEPS         = 0x00010000
    UNUSABLE_BY_FIGHTER_THIEF  = 0x00020000
    UNUSABLE_BY_MAGE           = 0x00040000
    UNUSABLE_BY_MAGE_THIEF     = 0x00080000
    UNUSABLE_BY_DAKKON         = 0x00100000
    UNUSABLE_BY_FALL_FROM_GRACE = 0x00200000
    UNUSABLE_BY_THIEF          = 0x00400000
    UNUSABLE_BY_VHAILOR        = 0x00800000
    # Byte 4
    UNUSABLE_BY_IGNUS          = 0x01000000
    UNUSABLE_BY_MORTE          = 0x02000000
    UNUSABLE_BY_NORDOM         = 0x04000000
    UNUSABLE_BY_UNKNOWN_3      = 0x08000000
    UNUSABLE_BY_ANNAH          = 0x10000000
    UNUSABLE_BY_UNKNOWN_5      = 0x20000000
    UNUSABLE_BY_NAMELESS_ONE   = 0x40000000
    UNUSABLE_BY_UNKNOWN_7      = 0x80000000


class AttackType(IntEnum):
    """
    Extended-header attack type, stored at offset 0x00 in each ext header.
    """
    NONE       = 0
    MELEE      = 1
    PROJECTILE = 2
    MAGIC      = 3
    LAUNCHER   = 4


class ItemTargetType(IntEnum):
    """
    Extended-header target type for items, stored at offset 0x05 in each
    ext header.  Describes what the ability can be used on.

    Named ItemTargetType to avoid collision with SpellTargetType.
    """
    INVALID      = 0
    LIVING_ACTOR = 1
    INVENTORY    = 2
    DEAD_ACTOR   = 3
    ANY_POINT    = 4
    SELF         = 5
    CRASH        = 6
    CASTER_EE    = 7  # EE only (self, ignores pause)


class ItemAbilityLocation(IntEnum):
    """
    ITM extended header ability location (offset 0x02).
    """
    NONE      = 0
    WEAPON    = 1
    SPELL     = 2
    EQUIPMENT = 3
    INNATE    = 4


class ItemDamageType(IntEnum):
    """
    ITM extended header damage type (offset 0x1C).

    See IESDP ITM v1 "Damage type" table.
    """
    NONE                      = 0
    PIERCING                  = 1
    CRUSHING                  = 2
    SLASHING                  = 3
    MISSILE                   = 4
    FIST                      = 5
    PIERCING_CRUSHING_BETTER  = 6
    PIERCING_SLASHING_BETTER  = 7
    CRUSHING_SLASHING_WORSE   = 8
    BLUNT_MISSILE             = 9


class ItemTargetTypePST(IntEnum):
    """
    PST ITM v1.1 target type table.
    """
    INVALID            = 0
    CREATURE           = 1
    CRASH_A            = 2
    CHARACTER_PORTRAIT = 3
    AREA               = 4
    SELF               = 5
    CRASH_B            = 6
    NONE_SELF_EE       = 7  # ignores pause


class ItemDamageTypePST(IntEnum):
    """
    PST ITM v1.1 damage types.
    """
    NONE            = 0
    PIERCING_MAGIC  = 1
    BLUNT           = 2
    SLASHING        = 3
    RANGED          = 4
    FISTS           = 5


class ItemAbilityFlag(IntFlag):
    """
    ITM extended header flags (offset 0x26, dword).

    IESDP lists byte-1 and byte-2 bit meanings. Only documented bits are named.
    """
    NONE                 = 0x00000000
    ADD_STRENGTH_BONUS   = 0x00000001  # byte1 bit0
    BREAKABLE            = 0x00000002  # byte1 bit1
    DAMAGE_STR_BONUS     = 0x00000004  # byte1 bit2
    THAC0_STR_BONUS      = 0x00000008  # byte1 bit3
    EE_BREAK_SANCTUARY   = 0x00000200  # byte2 bit1 (EE)
    HOSTILE              = 0x00000400  # byte2 bit2
    RECHARGES            = 0x00000800  # byte2 bit3


class ChargeBehavior(IntEnum):
    """
    Extended-header charge depletion behaviour, stored at offset 0x24 in
    each ext header.
    """
    DONT_VANISH    = 0
    EXPENDED       = 1
    EXPENDED_QUIET = 2  # expended without sound
    RECHARGE_DAILY = 3


# ===========================================================================
# SPL — Spell format  (core/formats/spl.py)
# ===========================================================================

class SpellType(IntEnum):
    """Spell type / school category, stored at offset 0x1C in the SPL header."""
    SPECIAL_ABILITY = 0x0000  # innate / special power
    WIZARD          = 0x0001
    CLERIC          = 0x0002
    PSIONIC         = 0x0003  # PST
    INNATE          = 0x0004  # also used for abilities granted by items
    BARD            = 0x0005


class SpellSchool(IntEnum):
    """
    Arcane school / divine sphere, stored at offset 0x25 in the SPL header.

    Values 20+ are divine spheres used in IWD2 and some EE titles.
    The overlap at 0 between NONE and ALL_SPHERES is intentional —
    both map to 0 in different contexts (arcane vs. divine).
    """
    NONE          = 0
    ABJURATION    = 1
    CONJURATION   = 2
    DIVINATION    = 3
    ENCHANTMENT   = 4
    ILLUSION      = 5
    EVOCATION     = 6
    NECROMANCY    = 7
    TRANSMUTATION = 8   # Alteration
    GENERALIST    = 9
    DIVINATION2   = 10  # used inconsistently in some games
    # Divine spheres
    ALL_SPHERES   = 0
    ANIMAL        = 20
    ASTRAL        = 21
    CHARM         = 22
    COMBAT        = 23
    CREATION      = 24
    ELEMENTAL     = 26
    HEALING       = 27
    NECROMANTIC   = 28
    PLANT         = 29
    PROTECTION    = 30
    SUMMONING     = 31
    SUN           = 32
    WEATHER       = 33


class SpellFlag(IntFlag):
    """Spell header flags, stored as a dword at offset 0x18 in the SPL header."""
    NONE                      = 0x00000000
    FRIENDLY                  = 0x00000002  # does not affect caster's faction
    NO_LOS_REQUIRED           = 0x00000004
    ALLOW_DEAD                = 0x00000010  # can target dead creatures
    IGNORE_WILD_SURGE         = 0x00000020
    IGNORE_DEAD_MAGIC         = 0x00000040  # unaffected by dead magic zones
    NOT_AFFECTED_BY_ANTIMAGIC = 0x00000080
    IGNORE_WILD_MAGIC_ZONE    = 0x00000100
    EE_HOSTILE                = 0x00000400  # EE: marks as hostile
    EE_NO_INVENTORY_FEEDBACK  = 0x00000800


class SpellUsabilityFlag(IntFlag):
    """
    Who cannot learn / use this spell, stored at offset 0x1E in the SPL header.

    Set bits *exclude* that class.  Mapping is BG2 values; differs slightly
    between BG1, BG2, and IWD.

    Named SpellUsabilityFlag to avoid collision with ItemUsabilityFlag
    (item usability bitmask field, which has a different layout).
    """
    NONE           = 0x00000000
    CHAOTIC        = 0x00000001
    EVIL           = 0x00000002
    GOOD           = 0x00000004
    NEUTRAL_GE     = 0x00000008  # neither good nor evil
    LAWFUL         = 0x00000010
    NEUTRAL_LC     = 0x00000020  # neither lawful nor chaotic
    BARD           = 0x00000040
    CLERIC         = 0x00000080
    CLERIC_EVIL    = 0x00000100
    CLERIC_GOOD    = 0x00000200
    CLERIC_NEUTRAL = 0x00000400
    DRUID          = 0x00000800
    FIGHTER        = 0x00001000
    MAGE           = 0x00002000
    PALADIN        = 0x00004000
    RANGER         = 0x00008000
    SHAMAN         = 0x00010000
    THIEF          = 0x00020000


class CastingAnimation(IntEnum):
    """
    Casting animation selection, stored at offset 0x28 in the SPL header.
    """
    NONE        = 0x0000
    SPELL       = 0x0001
    DETECTION   = 0x0002
    MANUAL      = 0x0003  # no animation
    AREA_EFFECT = 0x0004


class SpellTargetType(IntEnum):
    """
    Extended-header target type for spells, stored at offset 0x04 in each
    SPL ext header.

    Named SpellTargetType to avoid collision with ItemTargetType.
    """
    INVALID      = 0
    LIVING_ACTOR = 1
    INVENTORY    = 2
    DEAD_ACTOR   = 3
    ANY_POINT    = 4
    SELF         = 5
    EX_SELF      = 6  # anyone except self
    LARGE_AOE    = 7


# ===========================================================================
# ARE — Area format  (core/formats/are.py)
# ===========================================================================

class AreaFlag(IntFlag):
    """Area header flags, stored at offset 0x08 in the ARE header."""
    NONE           = 0x0000
    SAVE_FORBIDDEN = 0x0001
    TUTORIAL       = 0x0004
    DEAD_MAGIC     = 0x0008
    DREAM          = 0x0010
    DREAM2         = 0x0020


class AreaType(IntFlag):
    """Area type bitmask, stored at offset 0x54 in the ARE header."""
    NONE      = 0x0000
    OUTDOOR   = 0x0001
    DAY_NIGHT = 0x0002
    WEATHER   = 0x0004
    CITY      = 0x0008
    FOREST    = 0x0010
    DUNGEON   = 0x0020
    EXTENDED  = 0x0040
    CAN_REST  = 0x0080


class ActorFlag(IntFlag):
    """Actor placement flags within an ARE file."""
    NONE            = 0x0000
    CRE_IN_BIFF     = 0x0001  # creature data is in BIFF, not embedded
    DEAD            = 0x0002
    NO_PERM_DEATH   = 0x0008
    ALLY            = 0x0010
    ENEMY           = 0x0020
    INANIMATE       = 0x0040
    NO_TURN_UNDEAD  = 0x0080


class RegionType(IntEnum):
    """Type of an interactive region (trigger) in an ARE file."""
    PROXIMITY  = 0
    INFO_POINT = 1
    TRAVEL     = 2


class ContainerType(IntEnum):
    """Container type stored in ARE container records."""
    BAG        = 0
    CHEST      = 1
    DRAWER     = 2
    PILE       = 3
    TABLE      = 4
    SHELF      = 5
    ALTAR      = 6
    NONVISIBLE = 7
    WATER      = 8
    BARREL     = 9
    CRATE      = 10


class DoorFlag(IntFlag):
    """Door state flags stored in ARE door records."""
    NONE         = 0x0000
    OPEN         = 0x0001
    LOCKED       = 0x0002
    RESET        = 0x0004
    DETECTABLE   = 0x0008
    BROKEN       = 0x0010
    CANT_CLOSE   = 0x0020
    LINKED       = 0x0040
    SECRET       = 0x0080
    FOUND        = 0x0100
    TRANSPARENT  = 0x0200
    TRIGGER_OPEN = 0x0400


class SpawnFlag(IntFlag):
    """Spawn point flags stored in ARE spawn records."""
    NONE       = 0x0000
    ENABLED    = 0x0001
    CONTINUOUS = 0x0008


# ===========================================================================
# CRE — Creature format  (core/formats/cre.py)
# ===========================================================================

class Gender(IntEnum):
    """
    Creature gender, stored at offset 0x275 in the CRE V1 header
    (GENDER.IDS).  These are the standard BG/IWD values.
    """
    MALE    = 1
    FEMALE  = 2
    NEITHER = 3
    BOTH    = 4


class Race(IntEnum):
    """
    Creature race, stored at offset 0x272 in the CRE V1 header (RACE.IDS).
    These are the standard BG/IWD values.  PST uses a different table.
    """
    HUMAN    = 1
    ELF      = 2
    HALF_ELF = 3
    DWARF    = 4
    HALFLING = 5
    GNOME    = 6
    HALF_ORC = 7


class Class(IntEnum):
    """
    Creature class, stored at offset 0x273 in the CRE V1 header
    (CLASS.IDS).  Multi-class combinations are single values.
    """
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
    SORCERER            = 19  # shares value with SHAMAN in some games


class Alignment(IntEnum):
    """
    Creature alignment, stored at offset 0x27F in the CRE V1 header
    (ALIGNMEN.IDS).  High nibble = law/chaos axis, low nibble = good/evil.
    """
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
    """
    Creature header flags, stored as a dword at offset 0x0008 in the CRE
    header.
    """
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


class SlotIndex(IntEnum):
    """
    Equipment slot indices for V1.0 (BG1/IWD) and V9.0 (BG2/EE) creatures.
    The slots array in a CRE file has SLOT_COUNT (40) entries; each entry
    is an index into the items array, or 0xFFFF for empty.
    """
    HELMET          = 0
    ARMOUR          = 1
    SHIELD          = 2
    GLOVES          = 3
    RING_LEFT       = 4
    RING_RIGHT      = 5
    AMULET          = 6
    BELT            = 7
    BOOTS           = 8
    WEAPON1         = 9
    WEAPON2         = 10
    WEAPON3         = 11
    WEAPON4         = 12
    QUIVER1         = 13
    QUIVER2         = 14
    QUIVER3         = 15
    CLOAK           = 16
    QUICK_ITEM1     = 17
    QUICK_ITEM2     = 18
    QUICK_ITEM3     = 19
    INVENTORY_0     = 20
    INVENTORY_1     = 21
    INVENTORY_2     = 22
    INVENTORY_3     = 23
    INVENTORY_4     = 24
    INVENTORY_5     = 25
    INVENTORY_6     = 26
    INVENTORY_7     = 27
    INVENTORY_8     = 28
    INVENTORY_9     = 29
    INVENTORY_10    = 30
    INVENTORY_11    = 31
    INVENTORY_12    = 32
    INVENTORY_13    = 33
    INVENTORY_14    = 34
    INVENTORY_15    = 35
    MAGIC_WEAPON    = 36
    WEAPON_SELECTED = 37  # index of active weapon (0–3), not a real slot


class PstSlotIndex(IntEnum):
    """
    Equipment slot indices for V1.2 (Planescape: Torment) creatures.
    PST has 48 slots with a different layout to the BG/IWD slot table.
    """
    HELMET             = 0   # Right Earring / Lens / Helmet
    ARMOUR             = 1   # Chest
    TATTOO_LEFT        = 2
    HAND               = 3
    RING_LEFT          = 4
    RING_RIGHT         = 5
    EYEBALL            = 6   # Left Earring / Eyeball
    TATTOO_RIGHT_LOWER = 7
    BOOTS              = 8
    WEAPON1            = 9
    WEAPON2            = 10
    WEAPON3            = 11
    WEAPON4            = 12
    QUIVER1            = 13
    QUIVER2            = 14
    QUIVER3            = 15
    QUIVER4            = 16
    QUIVER5            = 17
    QUIVER6            = 18
    TATTOO_RIGHT_UPPER = 19
    QUICK_ITEM1        = 20
    QUICK_ITEM2        = 21
    QUICK_ITEM3        = 22
    QUICK_ITEM4        = 23
    QUICK_ITEM5        = 24
    INVENTORY_0        = 25
    INVENTORY_1        = 26
    INVENTORY_2        = 27
    INVENTORY_3        = 28
    INVENTORY_4        = 29
    INVENTORY_5        = 30
    INVENTORY_6        = 31
    INVENTORY_7        = 32
    INVENTORY_8        = 33
    INVENTORY_9        = 34
    INVENTORY_10       = 35
    INVENTORY_11       = 36
    INVENTORY_12       = 37
    INVENTORY_13       = 38
    INVENTORY_14       = 39
    INVENTORY_15       = 40
    INVENTORY_16       = 41
    INVENTORY_17       = 42
    INVENTORY_18       = 43
    INVENTORY_19       = 44
    MAGIC_WEAPON       = 45
    WEAPON_SELECTED    = 46
    # slot 47: selected weapon ability (engine read-only, not named)


# ===========================================================================
# DLG
# ===========================================================================

class TransitionFlag(IntFlag):
    NONE              = 0x00
    HAS_TEXT          = 0x01   # transition has a player-response StrRef
    HAS_TRIGGER       = 0x02   # transition has a condition string
    HAS_ACTION        = 0x04   # transition has an action string
    TERMINATES        = 0x08   # conversation ends here (no next state)
    JOURNAL_ENTRY     = 0x10   # transition writes a journal entry
    INTERRUPT         = 0x20   # interrupts current dialogue
    ADD_JOURNAL       = 0x40   # add quest journal entry
    REMOVE_JOURNAL    = 0x80   # remove quest journal entry
    SOLVED_JOURNAL    = 0x100  # mark journal entry as solved


# ===========================================================================
# CHU
# ===========================================================================

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


# ===========================================================================
# WED
# ===========================================================================

class TilemapFlag(IntFlag):
    NONE            = 0x00
    EXTENDED_NIGHT  = 0x01   # cell has an alternate night tile
    DRAW_OVERLAPPED = 0x02   # tile drawn on top of adjacent tiles


class PolygonFlag(IntFlag):
    NONE        = 0x00
    SHADE_WALL  = 0x01   # blocks LOS
    HOVERING    = 0x02   # polygon hovers above ground
    COVER_PCS   = 0x04   # covers player characters
    COVER_ANIMS = 0x08   # covers animations
    IMPASSABLE  = 0x10   # blocks movement
