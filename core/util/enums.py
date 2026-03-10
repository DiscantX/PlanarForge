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
    MISCELLANEOUS   = 0x0000
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
    CONTAINER       = 0x0024  # eye / broken armour slot items
    BOOKS           = 0x0025
    FAMILIAR        = 0x0026
    TATTOO          = 0x0027  # PST
    LENS            = 0x0028  # PST
    BUCKLER         = 0x0029
    CANDLE          = 0x002A
    CLUB            = 0x002C
    LARGE_SHIELD    = 0x002F
    MEDIUM_SHIELD   = 0x0031
    NOTES           = 0x0033
    SMALL_SHIELD    = 0x0035
    TELESCOPE       = 0x0037
    DRINK           = 0x0038
    GREAT_SWORD     = 0x0039
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
    BASTARD_SWORD   = 0x0045
    SCARF           = 0x0046
    FOOD2           = 0x0047
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
    UNKNOWN_20         = 0x00000020
    MAGICAL            = 0x00000040
    LEFT_HANDED        = 0x00000080
    SILVER             = 0x00000100  # interacts with opcode #120
    COLD_IRON          = 0x00000200  # interacts with opcode #120
    OFF_HANDED         = 0x00000400
    CONVERSABLE        = 0x00000800
    EE_FAKE_TWO_HANDED = 0x00001000  # EE only
    EE_FORBID_OFF_HAND = 0x00002000  # EE only


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
    EX_SELF      = 6  # anyone except self
    LARGE_AOE    = 7


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
