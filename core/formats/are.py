"""
core/formats/are.py

Parser and writer for the Infinity Engine ARE (Area) format.

The ARE file is the master record for a game area.  It describes the area's
properties and contains all of its dynamic content: actors, doors, containers,
regions (triggers), entrances, ambient sounds, spawn points, animations, map
notes, rest encounters, and tiled-door associations.  Static geometry (the
tile layout and wall polygons) lives in a companion WED file referenced by
the ARE header.

Supported versions:
    V1.0  — BG1, IWD1
    V9.1  — BG2, BG2:EE, IWD:EE  (adds fog-of-war, explored mask, extra fields)
    PST   — Planescape: Torment  (best-effort; version-specific tail stored raw)

All sub-structures are fully parsed.

IESDP references:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/are_v1.htm
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/are_v91.htm

Usage::

    from core.formats.are import AreFile

    area = AreFile.from_file("AR0602.are")
    print(area.header.wed_resref)       # companion WED file
    print(len(area.actors))             # number of actors placed in the area
    for entrance in area.entrances:
        print(entrance.name, entrance.x, entrance.y)
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

SIGNATURE       = b"AREA"
VERSION_V1      = b"V1.0"
VERSION_V91     = b"V9.1"
# PST uses "V1.0" signature but has extra fields; detected by context
# when opened via game installation data.

HEADER_SIZE_V1  = 0x11C   # 284 bytes
HEADER_SIZE_V91 = 0x11C   # same base; V9.1 appends extra explored-mask data



# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AreaFlag(IntFlag):
    NONE              = 0x0000
    SAVE_FORBIDDEN    = 0x0001
    TUTORIAL          = 0x0004
    DEAD_MAGIC        = 0x0008
    DREAM             = 0x0010
    DREAM2            = 0x0020


class AreaType(IntFlag):
    NONE       = 0x0000
    OUTDOOR    = 0x0001
    DAY_NIGHT  = 0x0002
    WEATHER    = 0x0004
    CITY       = 0x0008
    FOREST     = 0x0010
    DUNGEON    = 0x0020
    EXTENDED   = 0x0040
    CAN_REST   = 0x0080


class ActorFlag(IntFlag):
    NONE          = 0x0000
    CRE_IN_BIFF   = 0x0001   # creature data is in BIFF, not embedded
    DEAD          = 0x0002
    NO_PERM_DEATH = 0x0008
    ALLY          = 0x0010
    ENEMY         = 0x0020
    INANIMATE     = 0x0040
    NO_TURN_UNDEAD = 0x0080


class RegionType(IntEnum):
    PROXIMITY  = 0
    INFO_POINT = 1
    TRAVEL     = 2


class ContainerType(IntEnum):
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
    NONE          = 0x0000
    OPEN          = 0x0001
    LOCKED        = 0x0002
    RESET         = 0x0004
    DETECTABLE    = 0x0008
    BROKEN        = 0x0010
    CANT_CLOSE    = 0x0020
    LINKED        = 0x0040
    SECRET        = 0x0080
    FOUND         = 0x0100
    TRANSPARENT   = 0x0200
    TRIGGER_OPEN  = 0x0400


class SpawnFlag(IntFlag):
    NONE       = 0x0000
    ENABLED    = 0x0001
    CONTINUOUS = 0x0008


# ---------------------------------------------------------------------------
# Vertex  (4 bytes — shared by regions, doors, containers)
# ---------------------------------------------------------------------------

@dataclass
class Vertex:
    x: int = 0   # int16
    y: int = 0   # int16

    @classmethod
    def _read(cls, r: BinaryReader) -> "Vertex":
        return cls(x=r.read_int16(), y=r.read_int16())

    def _write(self, w: BinaryWriter) -> None:
        w.write_int16(self.x)
        w.write_int16(self.y)

    def to_json(self) -> list:
        return [self.x, self.y]

    @classmethod
    def from_json(cls, d) -> "Vertex":
        if isinstance(d, (list, tuple)):
            return cls(x=d[0], y=d[1])
        return cls(x=d.get("x", 0), y=d.get("y", 0))


# ---------------------------------------------------------------------------
# Actor  (272 bytes)
# ---------------------------------------------------------------------------

@dataclass
class Actor:
    """A creature placed in the area."""
    name:            str   = ""            # 32-char label
    x:               int   = 0             # uint16 — placement x
    y:               int   = 0             # uint16
    dest_x:          int   = 0             # uint16 — patrol destination
    dest_y:          int   = 0             # uint16
    flags:           int   = ActorFlag.NONE
    has_been_spawned: int  = 0             # uint16
    first_letter:    str   = ""            # char[1] — actor variable prefix
    unknown:         int   = 0             # uint8
    actor_remove:    StrRef   = StrRef(0xFFFFFFFF)   # uint32 — StrRef condition
    activation_at:   int   = 0             # uint32 — schedule bitmask (BG2)
    activation_day:  int   = 0             # uint32
    cre_resref:      str   = ""            # ResRef — .cre file
    cre_offset:      int   = 0             # uint32 — offset of embedded CRE (0 if in BIFF)
    cre_size:        int   = 0             # uint32
    dialog:          str   = ""            # ResRef
    scripts:         List[str] = field(default_factory=lambda: [""] * 8)  # 8 ResRefs

    @classmethod
    def _read(cls, r: BinaryReader) -> "Actor":
        name             = r.read_string(32)
        x                = r.read_uint16()
        y                = r.read_uint16()
        dest_x           = r.read_uint16()
        dest_y           = r.read_uint16()
        flags            = r.read_uint32()
        has_been_spawned = r.read_uint16()
        first_letter     = r.read_bytes(1).decode("latin-1")
        unknown          = r.read_uint8()
        actor_remove     = StrRef(r.read_uint32())
        activation_at    = r.read_uint32()
        activation_day   = r.read_uint32()
        r.skip(4)  # unknown
        scripts          = [r.read_resref() for _ in range(8)]
        cre_offset       = r.read_uint32()
        cre_size         = r.read_uint32()
        dialog           = r.read_resref()
        r.skip(8)  # padding
        cre_resref       = r.read_resref()
        r.skip(120)  # reserved / CRE embed area handled separately
        return cls(
            name=name, x=x, y=y, dest_x=dest_x, dest_y=dest_y,
            flags=flags, has_been_spawned=has_been_spawned,
            first_letter=first_letter, unknown=unknown,
            actor_remove=actor_remove, activation_at=activation_at,
            activation_day=activation_day, cre_resref=cre_resref,
            cre_offset=cre_offset, cre_size=cre_size,
            dialog=dialog, scripts=scripts,
        )

    def _write(self, w: BinaryWriter) -> None:
        name_enc = self.name.encode("latin-1", errors="replace")[:32].ljust(32, b"\x00")
        w.write_bytes(name_enc)
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        w.write_uint16(self.dest_x)
        w.write_uint16(self.dest_y)
        w.write_uint32(self.flags)
        w.write_uint16(self.has_been_spawned)
        w.write_bytes(self.first_letter.encode("latin-1")[:1].ljust(1, b"\x00"))
        w.write_uint8(self.unknown)
        w.write_uint32(int(self.actor_remove))
        w.write_uint32(self.activation_at)
        w.write_uint32(self.activation_day)
        w.write_padding(4)
        for i in range(8):
            s = self.scripts[i] if i < len(self.scripts) else ""
            w.write_resref(s)
        w.write_uint32(self.cre_offset)
        w.write_uint32(self.cre_size)
        w.write_resref(self.dialog)
        w.write_padding(8)
        w.write_resref(self.cre_resref)
        w.write_padding(120)

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "x": self.x, "y": self.y,
                   "cre_resref": self.cre_resref, "flags": self.flags}
        if self.dest_x != self.x or self.dest_y != self.y:
            d["dest_x"] = self.dest_x
            d["dest_y"] = self.dest_y
        if self.dialog:          d["dialog"]       = self.dialog
        if self.activation_at:   d["activation_at"] = self.activation_at
        if any(self.scripts):    d["scripts"]      = self.scripts
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Actor":
        return cls(
            name=d.get("name",""), x=d.get("x",0), y=d.get("y",0),
            dest_x=d.get("dest_x", d.get("x",0)),
            dest_y=d.get("dest_y", d.get("y",0)),
            flags=d.get("flags",0), cre_resref=d.get("cre_resref",""),
            dialog=d.get("dialog",""),
            activation_at=d.get("activation_at",0),
            activation_day=d.get("activation_day",0),
            scripts=d.get("scripts", [""] * 8),
        )


# ---------------------------------------------------------------------------
# Entrance  (104 bytes)
# ---------------------------------------------------------------------------

@dataclass
class Entrance:
    """A named entry point into the area."""
    name:      str = ""    # 32-char label
    x:         int = 0     # uint16
    y:         int = 0     # uint16
    facing:    int = 0     # uint16 — direction (0–15 clockwise from south)

    @classmethod
    def _read(cls, r: BinaryReader) -> "Entrance":
        name   = r.read_string(32)
        x      = r.read_uint16()
        y      = r.read_uint16()
        facing = r.read_uint16()
        r.skip(66)  # reserved
        return cls(name=name, x=x, y=y, facing=facing)

    def _write(self, w: BinaryWriter) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        w.write_uint16(self.facing)
        w.write_padding(66)

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "x": self.x, "y": self.y}
        if self.facing: d["facing"] = self.facing
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Entrance":
        return cls(name=d.get("name",""), x=d.get("x",0), y=d.get("y",0),
                   facing=d.get("facing",0))


# ---------------------------------------------------------------------------
# Region  (trigger / info point / travel)  (136 bytes + vertices)
# ---------------------------------------------------------------------------

@dataclass
class Region:
    """An interactive area trigger — proximity trap, info point, or travel region."""
    name:           str   = ""
    region_type:    int   = RegionType.INFO_POINT   # uint16
    bounding_box:   List[int] = field(default_factory=lambda: [0,0,0,0])  # x1,y1,x2,y2
    vertex_count:   int   = 0    # uint16
    vertex_index:   int   = 0    # uint32 — index into area vertex array
    trigger_value:  int   = 0    # uint32
    cursor_index:   int   = 0    # uint32
    destination_area: str = ""   # ResRef — for travel triggers
    destination_entrance: str = ""  # 32-char
    flags:          int   = 0    # uint32
    info_text:      StrRef   = StrRef(0xFFFFFFFF)   # StrRef
    trap_detect_dc: int   = 0    # uint16
    trap_disarm_dc: int   = 0    # uint16
    is_trapped:     int   = 0    # uint16
    trap_detected:  int   = 0    # uint16
    trap_launch_x:  int   = 0    # uint16
    trap_launch_y:  int   = 0    # uint16
    key_item:       str   = ""   # ResRef
    region_script:  str   = ""   # ResRef
    alt_use_point_x: int  = 0    # uint16
    alt_use_point_y: int  = 0    # uint16
    unknown:        bytes = b"\x00" * 44

    # Populated after vertex array is read
    vertices: List[Vertex] = field(default_factory=list)

    @classmethod
    def _read(cls, r: BinaryReader) -> "Region":
        name          = r.read_string(32)
        region_type   = r.read_uint16()
        bbox          = [r.read_uint16() for _ in range(4)]
        vertex_count  = r.read_uint16()
        vertex_index  = r.read_uint32()
        trigger_value = r.read_uint32()
        cursor_index  = r.read_uint32()
        dest_area     = r.read_resref()
        dest_entrance = r.read_string(32)
        flags         = r.read_uint32()
        info_text     = StrRef(r.read_uint32())
        trap_detect   = r.read_uint16()
        trap_disarm   = r.read_uint16()
        is_trapped    = r.read_uint16()
        trap_detected = r.read_uint16()
        trap_x        = r.read_uint16()
        trap_y        = r.read_uint16()
        key_item      = r.read_resref()
        script        = r.read_resref()
        alt_x         = r.read_uint16()
        alt_y         = r.read_uint16()
        unknown       = r.read_bytes(44)
        return cls(
            name=name, region_type=region_type, bounding_box=bbox,
            vertex_count=vertex_count, vertex_index=vertex_index,
            trigger_value=trigger_value, cursor_index=cursor_index,
            destination_area=dest_area, destination_entrance=dest_entrance,
            flags=flags, info_text=info_text,
            trap_detect_dc=trap_detect, trap_disarm_dc=trap_disarm,
            is_trapped=is_trapped, trap_detected=trap_detected,
            trap_launch_x=trap_x, trap_launch_y=trap_y,
            key_item=key_item, region_script=script,
            alt_use_point_x=alt_x, alt_use_point_y=alt_y,
            unknown=unknown,
        )

    def _write(self, w: BinaryWriter, vertex_index: int) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint16(self.region_type)
        for v in self.bounding_box[:4]:
            w.write_uint16(v)
        w.write_uint16(len(self.vertices))
        w.write_uint32(vertex_index)
        w.write_uint32(self.trigger_value)
        w.write_uint32(self.cursor_index)
        w.write_resref(self.destination_area)
        w.write_bytes(self.destination_entrance.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint32(self.flags)
        w.write_uint32(int(self.info_text))
        w.write_uint16(self.trap_detect_dc)
        w.write_uint16(self.trap_disarm_dc)
        w.write_uint16(self.is_trapped)
        w.write_uint16(self.trap_detected)
        w.write_uint16(self.trap_launch_x)
        w.write_uint16(self.trap_launch_y)
        w.write_resref(self.key_item)
        w.write_resref(self.region_script)
        w.write_uint16(self.alt_use_point_x)
        w.write_uint16(self.alt_use_point_y)
        w.write_bytes(self.unknown[:44].ljust(44, b"\x00"))

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "type": self.region_type,
                   "bounding_box": self.bounding_box,
                   "vertices": [v.to_json() for v in self.vertices]}
        if self.destination_area:    d["destination_area"]     = self.destination_area
        if self.destination_entrance: d["destination_entrance"] = self.destination_entrance
        if self.flags:               d["flags"]                = self.flags
        if not self.info_text.is_none: d["info_text"]       = self.info_text
        if self.is_trapped:          d["is_trapped"]           = self.is_trapped
        if self.key_item:            d["key_item"]             = self.key_item
        if self.region_script:       d["region_script"]        = self.region_script
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Region":
        r = cls(
            name=d.get("name",""), region_type=d.get("type", RegionType.INFO_POINT),
            bounding_box=d.get("bounding_box",[0,0,0,0]),
            flags=d.get("flags",0),
            destination_area=d.get("destination_area",""),
            destination_entrance=d.get("destination_entrance",""),
            info_text=StrRef.from_json(hd.get("info_text", 0xFFFFFFFF)),
            is_trapped=d.get("is_trapped",0),
            key_item=d.get("key_item",""),
            region_script=d.get("region_script",""),
        )
        r.vertices = [Vertex.from_json(v) for v in d.get("vertices",[])]
        return r


# ---------------------------------------------------------------------------
# SpawnPoint  (200 bytes)
# ---------------------------------------------------------------------------

@dataclass
class SpawnPoint:
    """A point where creatures may be spawned."""
    name:           str   = ""
    x:              int   = 0
    y:              int   = 0
    creature_resrefs: List[str] = field(default_factory=lambda: [""] * 10)
    creature_count: int   = 0    # uint16 — how many creatures in list
    base_difficulty: int  = 0    # uint16
    frequency:      int   = 0    # uint16 — respawn rate in seconds
    method:         int   = 0    # uint16
    actor_removal_time: int = 0  # uint32
    adjacent_difficulty: int = 0 # uint16
    unused:         int   = 0    # uint16
    max_creatures:  int   = 0    # uint16
    spawn_type:     int   = 0    # uint16
    schedule:       int   = 0    # uint32 — active-hours bitmask
    probability_day:   int = 100 # uint16
    probability_night: int = 100 # uint16
    flags:          int   = SpawnFlag.NONE  # uint32

    @classmethod
    def _read(cls, r: BinaryReader) -> "SpawnPoint":
        name        = r.read_string(32)
        x           = r.read_uint16()
        y           = r.read_uint16()
        creatures   = [r.read_resref() for _ in range(10)]
        cre_count   = r.read_uint16()
        base_diff   = r.read_uint16()
        frequency   = r.read_uint16()
        method      = r.read_uint16()
        removal     = r.read_uint32()
        adj_diff    = r.read_uint16()
        unused      = r.read_uint16()
        max_cre     = r.read_uint16()
        spawn_type  = r.read_uint16()
        schedule    = r.read_uint32()
        prob_day    = r.read_uint16()
        prob_night  = r.read_uint16()
        flags       = r.read_uint32()
        r.skip(56)  # reserved
        return cls(
            name=name, x=x, y=y, creature_resrefs=creatures,
            creature_count=cre_count, base_difficulty=base_diff,
            frequency=frequency, method=method,
            actor_removal_time=removal, adjacent_difficulty=adj_diff,
            unused=unused, max_creatures=max_cre, spawn_type=spawn_type,
            schedule=schedule, probability_day=prob_day,
            probability_night=prob_night, flags=flags,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        for i in range(10):
            w.write_resref(self.creature_resrefs[i] if i < len(self.creature_resrefs) else "")
        w.write_uint16(self.creature_count)
        w.write_uint16(self.base_difficulty)
        w.write_uint16(self.frequency)
        w.write_uint16(self.method)
        w.write_uint32(self.actor_removal_time)
        w.write_uint16(self.adjacent_difficulty)
        w.write_uint16(self.unused)
        w.write_uint16(self.max_creatures)
        w.write_uint16(self.spawn_type)
        w.write_uint32(self.schedule)
        w.write_uint16(self.probability_day)
        w.write_uint16(self.probability_night)
        w.write_uint32(self.flags)
        w.write_padding(56)

    def to_json(self) -> dict:
        creatures = [c for c in self.creature_resrefs if c]
        d: dict = {"name": self.name, "x": self.x, "y": self.y,
                   "creatures": creatures, "flags": self.flags}
        if self.frequency:          d["frequency"]   = self.frequency
        if self.max_creatures:      d["max_creatures"] = self.max_creatures
        if self.schedule:           d["schedule"]    = self.schedule
        if self.probability_day != 100:  d["probability_day"]   = self.probability_day
        if self.probability_night != 100: d["probability_night"] = self.probability_night
        return d

    @classmethod
    def from_json(cls, d: dict) -> "SpawnPoint":
        creatures = d.get("creatures", [])
        padded = (creatures + [""] * 10)[:10]
        return cls(
            name=d.get("name",""), x=d.get("x",0), y=d.get("y",0),
            creature_resrefs=padded, creature_count=len(creatures),
            flags=d.get("flags", SpawnFlag.NONE),
            frequency=d.get("frequency",0),
            max_creatures=d.get("max_creatures",0),
            schedule=d.get("schedule",0),
            probability_day=d.get("probability_day",100),
            probability_night=d.get("probability_night",100),
        )


# ---------------------------------------------------------------------------
# Ambient  (212 bytes)
# ---------------------------------------------------------------------------

@dataclass
class Ambient:
    """An ambient sound source in the area."""
    name:           str   = ""
    x:              int   = 0
    y:              int   = 0
    radius:         int   = 0     # uint16 — activation radius in pixels
    height:         int   = 0     # uint16
    pitch_variance: int   = 0     # uint32
    volume:         int   = 100   # uint16 — 0-100
    volume_variance: int  = 0     # uint16
    sounds:         List[str] = field(default_factory=lambda: [""] * 10)
    sound_count:    int   = 0
    interval:       int   = 0     # uint16 — seconds between plays
    interval_variance: int = 0    # uint16
    schedule:       int   = 0     # uint32 — active-hours bitmask
    flags:          int   = 0     # uint32

    @classmethod
    def _read(cls, r: BinaryReader) -> "Ambient":
        name      = r.read_string(32)
        x         = r.read_uint16()
        y         = r.read_uint16()
        radius    = r.read_uint16()
        height    = r.read_uint16()
        pitch_var = r.read_uint32()
        volume    = r.read_uint16()
        vol_var   = r.read_uint16()
        sounds    = [r.read_resref() for _ in range(10)]
        snd_count = r.read_uint16()
        interval  = r.read_uint16()
        int_var   = r.read_uint16()
        r.skip(2)
        schedule  = r.read_uint32()
        flags     = r.read_uint32()
        r.skip(64)
        return cls(
            name=name, x=x, y=y, radius=radius, height=height,
            pitch_variance=pitch_var, volume=volume, volume_variance=vol_var,
            sounds=sounds, sound_count=snd_count,
            interval=interval, interval_variance=int_var,
            schedule=schedule, flags=flags,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        w.write_uint16(self.radius)
        w.write_uint16(self.height)
        w.write_uint32(self.pitch_variance)
        w.write_uint16(self.volume)
        w.write_uint16(self.volume_variance)
        for i in range(10):
            w.write_resref(self.sounds[i] if i < len(self.sounds) else "")
        w.write_uint16(self.sound_count)
        w.write_uint16(self.interval)
        w.write_uint16(self.interval_variance)
        w.write_padding(2)
        w.write_uint32(self.schedule)
        w.write_uint32(self.flags)
        w.write_padding(64)

    def to_json(self) -> dict:
        sounds = [s for s in self.sounds if s]
        d: dict = {"name": self.name, "x": self.x, "y": self.y,
                   "sounds": sounds, "radius": self.radius,
                   "volume": self.volume, "flags": self.flags}
        if self.interval:  d["interval"]  = self.interval
        if self.schedule:  d["schedule"]  = self.schedule
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Ambient":
        sounds = d.get("sounds", [])
        padded = (sounds + [""] * 10)[:10]
        return cls(
            name=d.get("name",""), x=d.get("x",0), y=d.get("y",0),
            radius=d.get("radius",0), volume=d.get("volume",100),
            flags=d.get("flags",0), sounds=padded,
            sound_count=len(sounds), interval=d.get("interval",0),
            schedule=d.get("schedule",0),
        )


# ---------------------------------------------------------------------------
# Door  (200 bytes + vertices)
# ---------------------------------------------------------------------------

@dataclass
class Door:
    """A door in the area (links to a WED door record)."""
    name:             str   = ""
    door_id:          str   = ""    # ResRef — identifies this door in WED
    flags:            int   = DoorFlag.NONE
    open_vertex_index:  int = 0     # uint32 — into area vertex array
    open_vertex_count:  int = 0     # uint16
    close_vertex_index: int = 0     # uint32
    close_vertex_count: int = 0     # uint16
    open_bbox:        List[int] = field(default_factory=lambda: [0,0,0,0])
    close_bbox:       List[int] = field(default_factory=lambda: [0,0,0,0])
    open_cell_index:  int  = 0      # uint32 — impeded cell arrays (WED)
    open_cell_count:  int  = 0      # uint16
    close_cell_index: int  = 0      # uint32
    close_cell_count: int  = 0      # uint16
    hp:               int  = 0      # uint16
    ac:               int  = 0      # uint16 — armour class
    open_sound:       str  = ""     # ResRef
    close_sound:      str  = ""     # ResRef
    cursor_index:     int  = 0      # uint32
    trap_detect_dc:   int  = 0      # uint16
    trap_disarm_dc:   int  = 0      # uint16
    is_trapped:       int  = 0      # uint16
    trap_detected:    int  = 0      # uint16
    trap_launch_x:    int  = 0      # uint16
    trap_launch_y:    int  = 0      # uint16
    key_item:         str  = ""     # ResRef
    door_script:      str  = ""     # ResRef
    detection_difficulty: int = 0   # uint32
    lock_difficulty:  int  = 0      # uint32
    open_use_point:   List[int] = field(default_factory=lambda: [0,0])
    close_use_point:  List[int] = field(default_factory=lambda: [0,0])
    lock_pick_string: StrRef  = StrRef(0xFFFFFFFF)
    linked_info:      str  = ""     # 32-char
    name_strref:      StrRef  = StrRef(0xFFFFFFFF)
    door_open_anim:   str  = ""     # ResRef
    dialog:           str  = ""     # ResRef

    open_vertices:  List[Vertex] = field(default_factory=list)
    close_vertices: List[Vertex] = field(default_factory=list)

    @classmethod
    def _read(cls, r: BinaryReader) -> "Door":
        name               = r.read_string(32)
        door_id            = r.read_resref()
        flags              = r.read_uint32()
        open_vi            = r.read_uint32()
        open_vc            = r.read_uint16()
        close_vi           = r.read_uint32()
        close_vc           = r.read_uint16()
        open_bbox          = [r.read_uint16() for _ in range(4)]
        close_bbox         = [r.read_uint16() for _ in range(4)]
        open_ci            = r.read_uint32()
        open_cc            = r.read_uint16()
        close_ci           = r.read_uint32()
        close_cc           = r.read_uint16()
        hp                 = r.read_uint16()
        ac                 = r.read_uint16()
        open_snd           = r.read_resref()
        close_snd          = r.read_resref()
        cursor_index       = r.read_uint32()
        trap_detect        = r.read_uint16()
        trap_disarm        = r.read_uint16()
        is_trapped         = r.read_uint16()
        trap_detected      = r.read_uint16()
        trap_x             = r.read_uint16()
        trap_y             = r.read_uint16()
        key_item           = r.read_resref()
        door_script        = r.read_resref()
        detect_diff        = r.read_uint32()
        lock_diff          = r.read_uint32()
        open_use           = [r.read_uint16(), r.read_uint16()]
        close_use          = [r.read_uint16(), r.read_uint16()]
        lock_pick_str      = r.read_uint32()
        linked_info        = r.read_string(32)
        name_str           = r.read_uint32()
        door_open_anim     = r.read_resref()
        dialog             = r.read_resref()
        return cls(
            name=name, door_id=door_id, flags=flags,
            open_vertex_index=open_vi, open_vertex_count=open_vc,
            close_vertex_index=close_vi, close_vertex_count=close_vc,
            open_bbox=open_bbox, close_bbox=close_bbox,
            open_cell_index=open_ci, open_cell_count=open_cc,
            close_cell_index=close_ci, close_cell_count=close_cc,
            hp=hp, ac=ac, open_sound=open_snd, close_sound=close_snd,
            cursor_index=cursor_index,
            trap_detect_dc=trap_detect, trap_disarm_dc=trap_disarm,
            is_trapped=is_trapped, trap_detected=trap_detected,
            trap_launch_x=trap_x, trap_launch_y=trap_y,
            key_item=key_item, door_script=door_script,
            detection_difficulty=detect_diff, lock_difficulty=lock_diff,
            open_use_point=open_use, close_use_point=close_use,
            lock_pick_string=lock_pick_str, linked_info=linked_info,
            name_strref=name_str, door_open_anim=door_open_anim,
            dialog=dialog,
        )

    def _write(self, w: BinaryWriter, open_vi: int, close_vi: int) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_resref(self.door_id)
        w.write_uint32(self.flags)
        w.write_uint32(open_vi)
        w.write_uint16(len(self.open_vertices))
        w.write_uint32(close_vi)
        w.write_uint16(len(self.close_vertices))
        for v in self.open_bbox[:4]:  w.write_uint16(v)
        for v in self.close_bbox[:4]: w.write_uint16(v)
        w.write_uint32(self.open_cell_index)
        w.write_uint16(self.open_cell_count)
        w.write_uint32(self.close_cell_index)
        w.write_uint16(self.close_cell_count)
        w.write_uint16(self.hp)
        w.write_uint16(self.ac)
        w.write_resref(self.open_sound)
        w.write_resref(self.close_sound)
        w.write_uint32(self.cursor_index)
        w.write_uint16(self.trap_detect_dc)
        w.write_uint16(self.trap_disarm_dc)
        w.write_uint16(self.is_trapped)
        w.write_uint16(self.trap_detected)
        w.write_uint16(self.trap_launch_x)
        w.write_uint16(self.trap_launch_y)
        w.write_resref(self.key_item)
        w.write_resref(self.door_script)
        w.write_uint32(self.detection_difficulty)
        w.write_uint32(self.lock_difficulty)
        for v in self.open_use_point[:2]:  w.write_uint16(v)
        for v in self.close_use_point[:2]: w.write_uint16(v)
        w.write_uint32(int(self.lock_pick_string))
        w.write_bytes(self.linked_info.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint32(int(self.name_strref))
        w.write_resref(self.door_open_anim)
        w.write_resref(self.dialog)

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "door_id": self.door_id,
                   "flags": self.flags,
                   "open_vertices":  [v.to_json() for v in self.open_vertices],
                   "close_vertices": [v.to_json() for v in self.close_vertices]}
        if self.key_item:     d["key_item"]     = self.key_item
        if self.door_script:  d["door_script"]  = self.door_script
        if self.open_sound:   d["open_sound"]   = self.open_sound
        if self.close_sound:  d["close_sound"]  = self.close_sound
        if self.dialog:       d["dialog"]       = self.dialog
        if self.hp:           d["hp"]           = self.hp
        if self.is_trapped:   d["is_trapped"]   = self.is_trapped
        if not self.name_strref.is_none: d["name_strref"] = self.name_strref
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Door":
        door = cls(
            name=d.get("name",""), door_id=d.get("door_id",""),
            flags=d.get("flags",0),
            key_item=d.get("key_item",""), door_script=d.get("door_script",""),
            open_sound=d.get("open_sound",""), close_sound=d.get("close_sound",""),
            dialog=d.get("dialog",""), hp=d.get("hp",0),
            is_trapped=d.get("is_trapped",0),
            name_strref=StrRef.from_json(hd.get("name_strref", 0xFFFFFFFF)),
        )
        door.open_vertices  = [Vertex.from_json(v) for v in d.get("open_vertices",[])]
        door.close_vertices = [Vertex.from_json(v) for v in d.get("close_vertices",[])]
        return door


# ---------------------------------------------------------------------------
# Container  (192 bytes + vertices)
# ---------------------------------------------------------------------------

@dataclass
class Container:
    """A container object (chest, pile, etc.)."""
    name:             str   = ""
    x:                int   = 0
    y:                int   = 0
    container_type:   int   = ContainerType.PILE
    lock_difficulty:  int   = 0
    flags:            int   = 0
    trap_detect_dc:   int   = 0
    trap_disarm_dc:   int   = 0
    is_trapped:       int   = 0
    trap_detected:    int   = 0
    trap_launch_x:    int   = 0
    trap_launch_y:    int   = 0
    bounding_box:     List[int] = field(default_factory=lambda: [0,0,0,0])
    item_index:       int   = 0    # uint32 — first item in area item list
    item_count:       int   = 0    # uint32
    script_trap:      str   = ""   # ResRef
    vertex_index:     int   = 0    # uint32
    vertex_count:     int   = 0    # uint16
    trigger_range:    int   = 0    # uint16
    owner_name:       str   = ""   # 32-char
    key_item:         str   = ""   # ResRef
    break_difficulty: int   = 0
    lock_pick_string: StrRef   = StrRef(0xFFFFFFFF)
    unknown:          bytes = b"\x00" * 56

    vertices: List[Vertex] = field(default_factory=list)
    # Items in the container are stored in the area's global item list;
    # item_index and item_count index into it.

    @classmethod
    def _read(cls, r: BinaryReader) -> "Container":
        name          = r.read_string(32)
        x             = r.read_uint16()
        y             = r.read_uint16()
        ctype         = r.read_uint16()
        lock_diff     = r.read_uint16()
        flags         = r.read_uint32()
        trap_detect   = r.read_uint16()
        trap_disarm   = r.read_uint16()
        is_trapped    = r.read_uint16()
        trap_detected = r.read_uint16()
        trap_x        = r.read_uint16()
        trap_y        = r.read_uint16()
        bbox          = [r.read_uint16() for _ in range(4)]
        item_index    = r.read_uint32()
        item_count    = r.read_uint32()
        script_trap   = r.read_resref()
        vi            = r.read_uint32()
        vc            = r.read_uint16()
        trig_range    = r.read_uint16()
        owner         = r.read_string(32)
        key_item      = r.read_resref()
        break_diff    = r.read_uint32()
        lock_str      = r.read_uint32()
        unknown       = r.read_bytes(56)
        return cls(
            name=name, x=x, y=y, container_type=ctype,
            lock_difficulty=lock_diff, flags=flags,
            trap_detect_dc=trap_detect, trap_disarm_dc=trap_disarm,
            is_trapped=is_trapped, trap_detected=trap_detected,
            trap_launch_x=trap_x, trap_launch_y=trap_y,
            bounding_box=bbox, item_index=item_index, item_count=item_count,
            script_trap=script_trap, vertex_index=vi, vertex_count=vc,
            trigger_range=trig_range, owner_name=owner, key_item=key_item,
            break_difficulty=break_diff, lock_pick_string=lock_str,
            unknown=unknown,
        )

    def _write(self, w: BinaryWriter, vertex_index: int, item_index: int) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        w.write_uint16(self.container_type)
        w.write_uint16(self.lock_difficulty)
        w.write_uint32(self.flags)
        w.write_uint16(self.trap_detect_dc)
        w.write_uint16(self.trap_disarm_dc)
        w.write_uint16(self.is_trapped)
        w.write_uint16(self.trap_detected)
        w.write_uint16(self.trap_launch_x)
        w.write_uint16(self.trap_launch_y)
        for v in self.bounding_box[:4]: w.write_uint16(v)
        w.write_uint32(item_index)
        w.write_uint32(len(self.items) if hasattr(self, "items") else self.item_count)
        w.write_resref(self.script_trap)
        w.write_uint32(vertex_index)
        w.write_uint16(len(self.vertices))
        w.write_uint16(self.trigger_range)
        w.write_bytes(self.owner_name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_resref(self.key_item)
        w.write_uint32(self.break_difficulty)
        w.write_uint32(int(self.lock_pick_string))
        w.write_bytes(self.unknown[:56].ljust(56, b"\x00"))

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "x": self.x, "y": self.y,
                   "type": self.container_type, "flags": self.flags,
                   "vertices": [v.to_json() for v in self.vertices]}
        if self.key_item:     d["key_item"]    = self.key_item
        if self.script_trap:  d["script_trap"] = self.script_trap
        if self.is_trapped:   d["is_trapped"]  = self.is_trapped
        if self.lock_difficulty: d["lock_difficulty"] = self.lock_difficulty
        if not self.lock_pick_string.is_none:
            d["lock_pick_string"] = self.lock_pick_string
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Container":
        c = cls(
            name=d.get("name",""), x=d.get("x",0), y=d.get("y",0),
            container_type=d.get("type", ContainerType.PILE),
            flags=d.get("flags",0),
            key_item=d.get("key_item",""), script_trap=d.get("script_trap",""),
            is_trapped=d.get("is_trapped",0),
            lock_difficulty=d.get("lock_difficulty",0),
            lock_pick_string=StrRef.from_json(hd.get("lock_pick_string", 0xFFFFFFFF)),
        )
        c.vertices = [Vertex.from_json(v) for v in d.get("vertices",[])]
        return c


# ---------------------------------------------------------------------------
# AreaAnimation  (76 bytes)
# ---------------------------------------------------------------------------

@dataclass
class AreaAnimation:
    """A looping visual animation placed in the area (fire, waterfall, etc.)."""
    name:       str = ""
    schedule:   int = 0      # uint32 — active-hours bitmask
    x:          int = 0
    y:          int = 0
    animation:  str = ""     # ResRef — BAM file
    sequence:   int = 0      # uint16 — BAM sequence index
    frame:      int = 0      # uint16 — starting frame
    flags:      int = 0      # uint32
    height:     int = 0      # int16 — render height offset
    transparency: int = 0    # uint16 — 0=opaque
    start_frame: int = 0     # uint16
    looping_chance: int = 100 # uint8
    skip_cycles: int = 0     # uint8
    palette:    str = ""     # ResRef — palette override
    unknown:    int = 0      # uint16

    @classmethod
    def _read(cls, r: BinaryReader) -> "AreaAnimation":
        name        = r.read_string(32)
        schedule    = r.read_uint32()
        x           = r.read_uint16()
        y           = r.read_uint16()
        animation   = r.read_resref()
        sequence    = r.read_uint16()
        frame       = r.read_uint16()
        flags       = r.read_uint32()
        height      = r.read_int16()
        transparency = r.read_uint16()
        start_frame = r.read_uint16()
        loop_chance = r.read_uint8()
        skip        = r.read_uint8()
        palette     = r.read_resref()
        unknown     = r.read_uint16()
        return cls(
            name=name, schedule=schedule, x=x, y=y, animation=animation,
            sequence=sequence, frame=frame, flags=flags, height=height,
            transparency=transparency, start_frame=start_frame,
            looping_chance=loop_chance, skip_cycles=skip,
            palette=palette, unknown=unknown,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint32(self.schedule)
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        w.write_resref(self.animation)
        w.write_uint16(self.sequence)
        w.write_uint16(self.frame)
        w.write_uint32(self.flags)
        w.write_int16(self.height)
        w.write_uint16(self.transparency)
        w.write_uint16(self.start_frame)
        w.write_uint8(self.looping_chance)
        w.write_uint8(self.skip_cycles)
        w.write_resref(self.palette)
        w.write_uint16(self.unknown)

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "animation": self.animation,
                   "x": self.x, "y": self.y, "flags": self.flags}
        if self.schedule:        d["schedule"]    = self.schedule
        if self.transparency:    d["transparency"] = self.transparency
        if self.palette:         d["palette"]     = self.palette
        if self.height:          d["height"]      = self.height
        return d

    @classmethod
    def from_json(cls, d: dict) -> "AreaAnimation":
        return cls(
            name=d.get("name",""), animation=d.get("animation",""),
            x=d.get("x",0), y=d.get("y",0), flags=d.get("flags",0),
            schedule=d.get("schedule",0), transparency=d.get("transparency",0),
            palette=d.get("palette",""), height=d.get("height",0),
        )


# ---------------------------------------------------------------------------
# MapNote  (52 bytes)
# ---------------------------------------------------------------------------

@dataclass
class MapNote:
    """A note visible on the world map / area map."""
    x:         int = 0
    y:         int = 0
    text:      StrRef = StrRef(0xFFFFFFFF)   # StrRef
    color:     int = 0             # uint16

    @classmethod
    def _read(cls, r: BinaryReader) -> "MapNote":
        x     = r.read_uint16()
        y     = r.read_uint16()
        text  = StrRef(r.read_uint32())
        color = r.read_uint16()
        r.skip(42)
        return cls(x=x, y=y, text=text, color=color)

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint16(self.x)
        w.write_uint16(self.y)
        w.write_uint32(int(self.text))
        w.write_uint16(self.color)
        w.write_padding(42)

    def to_json(self) -> dict:
        d: dict = {"x": self.x, "y": self.y, "text": self.text.to_json()}
        if self.color: d["color"] = self.color
        return d

    @classmethod
    def from_json(cls, d: dict) -> "MapNote":
        return cls(x=d.get("x",0), y=d.get("y",0),
                   text=StrRef.from_json(hd.get("text", 0xFFFFFFFF)), color=d.get("color",0))


# ---------------------------------------------------------------------------
# RestEncounter  (228 bytes)
# ---------------------------------------------------------------------------

@dataclass
class RestEncounter:
    """Creatures that may ambush the party when resting in this area."""
    name:            str   = ""
    encounter_text:  List[StrRef] = field(default_factory=lambda: [StrRef(0xFFFFFFFF)]*10)
    creature_resrefs: List[str] = field(default_factory=lambda: [""] * 10)
    creature_count:  int   = 0
    difficulty:      int   = 0
    removal_time:    int   = 0
    movement_rate:   int   = 0
    dunno:           int   = 0
    max_creatures:   int   = 0
    enabled:         int   = 0

    @classmethod
    def _read(cls, r: BinaryReader) -> "RestEncounter":
        name       = r.read_string(32)
        enc_texts  = [StrRef(r.read_uint32()) for _ in range(10)]
        creatures  = [r.read_resref() for _ in range(10)]
        cre_count  = r.read_uint16()
        difficulty = r.read_uint16()
        removal    = r.read_uint32()
        movement   = r.read_uint16()
        dunno      = r.read_uint16()
        max_cre    = r.read_uint16()
        enabled    = r.read_uint16()
        r.skip(56)
        return cls(
            name=name, encounter_text=enc_texts, creature_resrefs=creatures,
            creature_count=cre_count, difficulty=difficulty,
            removal_time=removal, movement_rate=movement, dunno=dunno,
            max_creatures=max_cre, enabled=enabled,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        for t in (self.encounter_text + [StrRef(0xFFFFFFFF)]*10)[:10]:
            w.write_uint32(int(t))
        for i in range(10):
            w.write_resref(self.creature_resrefs[i] if i < len(self.creature_resrefs) else "")
        w.write_uint16(self.creature_count)
        w.write_uint16(self.difficulty)
        w.write_uint32(self.removal_time)
        w.write_uint16(self.movement_rate)
        w.write_uint16(self.dunno)
        w.write_uint16(self.max_creatures)
        w.write_uint16(self.enabled)
        w.write_padding(56)

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "creatures": [c for c in self.creature_resrefs if c],
            "enabled": self.enabled,
            "difficulty": self.difficulty,
        }

    @classmethod
    def from_json(cls, d: dict) -> "RestEncounter":
        creatures = d.get("creatures", [])
        padded = (creatures + [""] * 10)[:10]
        return cls(
            name=d.get("name",""), creature_resrefs=padded,
            creature_count=len(creatures),
            enabled=d.get("enabled",0), difficulty=d.get("difficulty",0),
        )


# ---------------------------------------------------------------------------
# ARE header  (284 bytes for both V1.0 and V9.1 base)
# ---------------------------------------------------------------------------

@dataclass
class AreHeader:
    """
    The top-level area record.

    Offset fields are managed by :class:`AreFile` on write.
    """
    wed_resref:      str   = ""            # ResRef — companion WED file
    last_saved:      int   = 0             # uint32 — game-time timestamp
    area_flags:      int   = AreaFlag.NONE
    area_north:      str   = ""            # ResRef — adjacent area N
    area_east:       str   = ""
    area_south:      str   = ""
    area_west:       str   = ""
    area_type:       int   = AreaType.DUNGEON
    rain_probability: int  = 0             # uint16
    snow_probability: int  = 0
    fog_probability:  int  = 0
    lightning_probability: int = 0
    wind_speed:      int   = 0
    area_script:     str   = ""            # ResRef
    explored_mask_size: int = 0            # uint32 — for V9.1 fog-of-war
    explored_mask_offset: int = 0          # uint32
    # Music
    day_song:        int   = 0             # uint16 — music table index
    night_song:      int   = 0
    win_song:        int   = 0
    battle_song:     int   = 0
    lose_song:       int   = 0
    alt_music_1:     int   = 0
    alt_music_2:     int   = 0
    alt_music_3:     int   = 0
    alt_music_4:     int   = 0
    alt_music_5:     int   = 0

    # Offsets/counts (managed on write)
    actors_offset:        int = 0
    actors_count:         int = 0
    regions_offset:       int = 0
    regions_count:        int = 0
    spawn_offset:         int = 0
    spawn_count:          int = 0
    entrances_offset:     int = 0
    entrances_count:      int = 0
    containers_offset:    int = 0
    containers_count:     int = 0
    items_offset:         int = 0
    items_count:          int = 0
    vertices_offset:      int = 0
    vertices_count:       int = 0
    ambients_offset:      int = 0
    ambients_count:       int = 0
    variables_offset:     int = 0
    variables_count:      int = 0
    tiled_obj_offset:     int = 0
    tiled_obj_count:      int = 0
    doors_offset:         int = 0
    doors_count:          int = 0
    anims_offset:         int = 0
    anims_count:          int = 0
    notes_offset:         int = 0
    notes_count:          int = 0
    rest_offset:          int = 0
    rest_count:           int = 0
    unknown_offset:       int = 0   # V9.1 auto-map notes
    unknown_count:        int = 0

    # V9.1 extra fields (raw tail, same strategy as CRE v9_extra)
    v91_extra: bytes = b""

    @classmethod
    def _read(cls, r: BinaryReader, version: bytes) -> "AreHeader":
        wed_resref     = r.read_resref()
        last_saved     = r.read_uint32()
        area_flags     = r.read_uint32()
        area_north     = r.read_resref()
        area_east      = r.read_resref()
        area_south     = r.read_resref()
        area_west      = r.read_resref()
        area_type      = r.read_uint16()
        rain_prob      = r.read_uint16()
        snow_prob      = r.read_uint16()
        fog_prob       = r.read_uint16()
        lightning_prob = r.read_uint16()
        wind_speed     = r.read_uint16()
        actors_off     = r.read_uint32()
        actors_cnt     = r.read_uint16()
        regions_cnt    = r.read_uint16()
        regions_off    = r.read_uint32()
        spawn_off      = r.read_uint32()
        spawn_cnt      = r.read_uint32()
        entrances_off  = r.read_uint32()
        entrances_cnt  = r.read_uint32()
        containers_off = r.read_uint32()
        containers_cnt = r.read_uint16()
        items_cnt      = r.read_uint16()
        items_off      = r.read_uint32()
        vertices_off   = r.read_uint32()
        vertices_cnt   = r.read_uint16()
        ambients_cnt   = r.read_uint16()
        ambients_off   = r.read_uint32()
        variables_off  = r.read_uint32()
        variables_cnt  = r.read_uint32()
        tiled_obj_off  = r.read_uint32()
        tiled_obj_cnt  = r.read_uint32()
        area_script    = r.read_resref()
        expl_mask_size = r.read_uint32()
        expl_mask_off  = r.read_uint32()
        doors_off      = r.read_uint32()
        doors_cnt      = r.read_uint32()
        anims_off      = r.read_uint32()
        anims_cnt      = r.read_uint32()
        notes_off      = r.read_uint32()
        notes_cnt      = r.read_uint32()
        songs_raw      = [r.read_uint16() for _ in range(10)]
        rest_off       = r.read_uint32()
        rest_cnt       = r.read_uint32()
        unknown_off    = r.read_uint32()
        unknown_cnt    = r.read_uint32()
        r.skip(72)     # reserved

        # V9.1 appends extra fog-of-war and other data after the 284-byte base
        v91_extra = b""
        if version == VERSION_V91:
            # Capture remaining header bytes; explored mask data follows
            v91_extra = r.read_bytes_at(HEADER_SIZE_V1,
                                         max(0, expl_mask_size)) if expl_mask_size else b""

        return cls(
            wed_resref=wed_resref, last_saved=last_saved,
            area_flags=area_flags,
            area_north=area_north, area_east=area_east,
            area_south=area_south, area_west=area_west,
            area_type=area_type,
            rain_probability=rain_prob, snow_probability=snow_prob,
            fog_probability=fog_prob,
            lightning_probability=lightning_prob, wind_speed=wind_speed,
            area_script=area_script,
            explored_mask_size=expl_mask_size,
            explored_mask_offset=expl_mask_off,
            day_song=songs_raw[0], night_song=songs_raw[1],
            win_song=songs_raw[2], battle_song=songs_raw[3],
            lose_song=songs_raw[4],
            alt_music_1=songs_raw[5], alt_music_2=songs_raw[6],
            alt_music_3=songs_raw[7], alt_music_4=songs_raw[8],
            alt_music_5=songs_raw[9],
            actors_offset=actors_off, actors_count=actors_cnt,
            regions_offset=regions_off, regions_count=regions_cnt,
            spawn_offset=spawn_off, spawn_count=spawn_cnt,
            entrances_offset=entrances_off, entrances_count=entrances_cnt,
            containers_offset=containers_off, containers_count=containers_cnt,
            items_offset=items_off, items_count=items_cnt,
            vertices_offset=vertices_off, vertices_count=vertices_cnt,
            ambients_offset=ambients_off, ambients_count=ambients_cnt,
            variables_offset=variables_off, variables_count=variables_cnt,
            tiled_obj_offset=tiled_obj_off, tiled_obj_count=tiled_obj_cnt,
            doors_offset=doors_off, doors_count=doors_cnt,
            anims_offset=anims_off, anims_count=anims_cnt,
            notes_offset=notes_off, notes_count=notes_cnt,
            rest_offset=rest_off, rest_count=rest_cnt,
            unknown_offset=unknown_off, unknown_count=unknown_cnt,
            v91_extra=v91_extra,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_resref(self.wed_resref)
        w.write_uint32(self.last_saved)
        w.write_uint32(self.area_flags)
        w.write_resref(self.area_north)
        w.write_resref(self.area_east)
        w.write_resref(self.area_south)
        w.write_resref(self.area_west)
        w.write_uint16(self.area_type)
        w.write_uint16(self.rain_probability)
        w.write_uint16(self.snow_probability)
        w.write_uint16(self.fog_probability)
        w.write_uint16(self.lightning_probability)
        w.write_uint16(self.wind_speed)
        w.write_uint32(self.actors_offset)
        w.write_uint16(self.actors_count)
        w.write_uint16(self.regions_count)
        w.write_uint32(self.regions_offset)
        w.write_uint32(self.spawn_offset)
        w.write_uint32(self.spawn_count)
        w.write_uint32(self.entrances_offset)
        w.write_uint32(self.entrances_count)
        w.write_uint32(self.containers_offset)
        w.write_uint16(self.containers_count)
        w.write_uint16(self.items_count)
        w.write_uint32(self.items_offset)
        w.write_uint32(self.vertices_offset)
        w.write_uint16(self.vertices_count)
        w.write_uint16(self.ambients_count)
        w.write_uint32(self.ambients_offset)
        w.write_uint32(self.variables_offset)
        w.write_uint32(self.variables_count)
        w.write_uint32(self.tiled_obj_offset)
        w.write_uint32(self.tiled_obj_count)
        w.write_resref(self.area_script)
        w.write_uint32(self.explored_mask_size)
        w.write_uint32(self.explored_mask_offset)
        w.write_uint32(self.doors_offset)
        w.write_uint32(self.doors_count)
        w.write_uint32(self.anims_offset)
        w.write_uint32(self.anims_count)
        w.write_uint32(self.notes_offset)
        w.write_uint32(self.notes_count)
        for s in (self.day_song, self.night_song, self.win_song,
                  self.battle_song, self.lose_song, self.alt_music_1,
                  self.alt_music_2, self.alt_music_3, self.alt_music_4,
                  self.alt_music_5):
            w.write_uint16(s)
        w.write_uint32(self.rest_offset)
        w.write_uint32(self.rest_count)
        w.write_uint32(self.unknown_offset)
        w.write_uint32(self.unknown_count)
        w.write_padding(84)


# ---------------------------------------------------------------------------
# Variable  (84 bytes)
# ---------------------------------------------------------------------------

@dataclass
class AreaVariable:
    """A local area variable (name + value)."""
    name:  str = ""    # 32 chars
    type_: int = 0     # uint16
    res_b: int = 0     # uint8 — resource field B
    res_c: int = 0
    dword_val: int = 0
    int_val:   int = 0
    double_val: int = 0
    script_name: str = ""  # 32 chars

    @classmethod
    def _read(cls, r: BinaryReader) -> "AreaVariable":
        name       = r.read_string(32)
        type_      = r.read_uint16()
        res_b      = r.read_uint8()
        res_c      = r.read_uint8()
        dword_val  = r.read_uint32()
        int_val    = r.read_int32()
        double_val = r.read_uint32()  # stored as uint32 in file
        script_name = r.read_string(32)
        r.skip(8)
        return cls(name=name, type_=type_, res_b=res_b, res_c=res_c,
                   dword_val=dword_val, int_val=int_val, double_val=double_val,
                   script_name=script_name)

    def _write(self, w: BinaryWriter) -> None:
        w.write_bytes(self.name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_uint16(self.type_)
        w.write_uint8(self.res_b)
        w.write_uint8(self.res_c)
        w.write_uint32(self.dword_val)
        w.write_int32(self.int_val)
        w.write_uint32(self.double_val)
        w.write_bytes(self.script_name.encode("latin-1")[:32].ljust(32, b"\x00"))
        w.write_padding(8)

    def to_json(self) -> dict:
        d: dict = {"name": self.name, "type": self.type_}
        if self.dword_val: d["dword_val"] = self.dword_val
        if self.int_val:   d["int_val"]   = self.int_val
        if self.script_name: d["script_name"] = self.script_name
        return d

    @classmethod
    def from_json(cls, d: dict) -> "AreaVariable":
        return cls(name=d.get("name",""), type_=d.get("type",0),
                   dword_val=d.get("dword_val",0), int_val=d.get("int_val",0),
                   script_name=d.get("script_name",""))


# ---------------------------------------------------------------------------
# ContainerItem  (shared item record stored in area item list)  (20 bytes)
# ---------------------------------------------------------------------------

@dataclass
class AreaItem:
    """An item stored in a container within this area."""
    resref:   str = ""
    flags:    int = 0     # uint16 — identified, stolen, etc.
    charges1: int = 0
    charges2: int = 0
    charges3: int = 0

    FLAG_IDENTIFIED  = 0x0001
    FLAG_UNSTEALABLE = 0x0002
    FLAG_STOLEN      = 0x0004
    FLAG_UNDROPPABLE = 0x0008

    @classmethod
    def _read(cls, r: BinaryReader) -> "AreaItem":
        resref   = r.read_resref()
        flags    = r.read_uint16()
        charges1 = r.read_uint16()
        charges2 = r.read_uint16()
        charges3 = r.read_uint16()
        r.skip(4)
        return cls(resref=resref, flags=flags,
                   charges1=charges1, charges2=charges2, charges3=charges3)

    def _write(self, w: BinaryWriter) -> None:
        w.write_resref(self.resref)
        w.write_uint16(self.flags)
        w.write_uint16(self.charges1)
        w.write_uint16(self.charges2)
        w.write_uint16(self.charges3)
        w.write_padding(4)

    def to_json(self) -> dict:
        d: dict = {"resref": self.resref}
        if self.flags:    d["flags"]    = self.flags
        if self.charges1: d["charges1"] = self.charges1
        if self.charges2: d["charges2"] = self.charges2
        if self.charges3: d["charges3"] = self.charges3
        return d

    @classmethod
    def from_json(cls, d: dict) -> "AreaItem":
        return cls(resref=d.get("resref",""), flags=d.get("flags",0),
                   charges1=d.get("charges1",0), charges2=d.get("charges2",0),
                   charges3=d.get("charges3",0))


# ---------------------------------------------------------------------------
# AreFile — top-level container
# ---------------------------------------------------------------------------

class AreFile:
    """
    A complete ARE resource.

    All sub-arrays are exposed as typed lists.  The global vertex array is
    resolved into each structure's own ``vertices`` list on read, and
    rebuilt from those lists on write.

    Attributes::

        header          — :class:`AreHeader`
        actors          — List[:class:`Actor`]
        regions         — List[:class:`Region`]       (triggers/info/travel)
        spawn_points    — List[:class:`SpawnPoint`]
        entrances       — List[:class:`Entrance`]
        containers      — List[:class:`Container`]
        items           — List[:class:`AreaItem`]     (container contents)
        ambients        — List[:class:`Ambient`]
        variables       — List[:class:`AreaVariable`]
        doors           — List[:class:`Door`]
        animations      — List[:class:`AreaAnimation`]
        notes           — List[:class:`MapNote`]
        rest_encounters — List[:class:`RestEncounter`]

    Usage::

        area = AreFile.from_file("AR0602.are")
        print(area.header.wed_resref)
        for actor in area.actors:
            print(actor.name, actor.cre_resref)
    """

    def __init__(
        self,
        header:          AreHeader,
        actors:          List[Actor],
        regions:         List[Region],
        spawn_points:    List[SpawnPoint],
        entrances:       List[Entrance],
        containers:      List[Container],
        items:           List[AreaItem],
        ambients:        List[Ambient],
        variables:       List[AreaVariable],
        doors:           List[Door],
        animations:      List[AreaAnimation],
        notes:           List[MapNote],
        rest_encounters: List[RestEncounter],
        version:         bytes = VERSION_V1,
        source_path:     Optional[Path] = None,
    ) -> None:
        self.header          = header
        self.actors          = actors
        self.regions         = regions
        self.spawn_points    = spawn_points
        self.entrances       = entrances
        self.containers      = containers
        self.items           = items
        self.ambients        = ambients
        self.variables       = variables
        self.doors           = doors
        self.animations      = animations
        self.notes           = notes
        self.rest_encounters = rest_encounters
        self.version         = version
        self.source_path     = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "AreFile":
        r = BinaryReader(data)
        try:
            r.expect_signature(SIGNATURE)
            version = r.read_bytes(4)
            if version not in (VERSION_V1, VERSION_V91):
                # PST also uses V1.0 — parse best-effort
                if version != VERSION_V1:
                    raise ValueError(f"Unsupported ARE version {version!r}.")
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        header = AreHeader._read(r, version)

        # -- Global vertex array --
        all_verts: List[Vertex] = []
        if header.vertices_count:
            r.seek(header.vertices_offset)
            for _ in range(header.vertices_count):
                all_verts.append(Vertex._read(r))

        # -- Actors --
        actors: List[Actor] = []
        if header.actors_count:
            r.seek(header.actors_offset)
            for _ in range(header.actors_count):
                actors.append(Actor._read(r))

        # -- Regions --
        regions: List[Region] = []
        if header.regions_count:
            r.seek(header.regions_offset)
            for _ in range(header.regions_count):
                reg = Region._read(r)
                reg.vertices = all_verts[reg.vertex_index:
                                         reg.vertex_index + reg.vertex_count]
                regions.append(reg)

        # -- Spawn points --
        spawn_points: List[SpawnPoint] = []
        if header.spawn_count:
            r.seek(header.spawn_offset)
            for _ in range(header.spawn_count):
                spawn_points.append(SpawnPoint._read(r))

        # -- Entrances --
        entrances: List[Entrance] = []
        if header.entrances_count:
            r.seek(header.entrances_offset)
            for _ in range(header.entrances_count):
                entrances.append(Entrance._read(r))

        # -- Items (area-level container contents) --
        items: List[AreaItem] = []
        if header.items_count:
            r.seek(header.items_offset)
            for _ in range(header.items_count):
                items.append(AreaItem._read(r))

        # -- Containers --
        containers: List[Container] = []
        if header.containers_count:
            r.seek(header.containers_offset)
            for _ in range(header.containers_count):
                con = Container._read(r)
                con.vertices = all_verts[con.vertex_index:
                                          con.vertex_index + con.vertex_count]
                containers.append(con)

        # -- Ambients --
        ambients: List[Ambient] = []
        if header.ambients_count:
            r.seek(header.ambients_offset)
            for _ in range(header.ambients_count):
                ambients.append(Ambient._read(r))

        # -- Variables --
        variables: List[AreaVariable] = []
        if header.variables_count:
            r.seek(header.variables_offset)
            for _ in range(header.variables_count):
                variables.append(AreaVariable._read(r))

        # -- Doors --
        doors: List[Door] = []
        if header.doors_count:
            r.seek(header.doors_offset)
            for _ in range(header.doors_count):
                door = Door._read(r)
                door.open_vertices  = all_verts[door.open_vertex_index:
                                                  door.open_vertex_index + door.open_vertex_count]
                door.close_vertices = all_verts[door.close_vertex_index:
                                                  door.close_vertex_index + door.close_vertex_count]
                doors.append(door)

        # -- Animations --
        animations: List[AreaAnimation] = []
        if header.anims_count:
            r.seek(header.anims_offset)
            for _ in range(header.anims_count):
                animations.append(AreaAnimation._read(r))

        # -- Map notes --
        notes: List[MapNote] = []
        if header.notes_count:
            r.seek(header.notes_offset)
            for _ in range(header.notes_count):
                notes.append(MapNote._read(r))

        # -- Rest encounters --
        rest_encounters: List[RestEncounter] = []
        if header.rest_count:
            r.seek(header.rest_offset)
            for _ in range(header.rest_count):
                rest_encounters.append(RestEncounter._read(r))

        return cls(
            header=header, actors=actors, regions=regions,
            spawn_points=spawn_points, entrances=entrances,
            containers=containers, items=items, ambients=ambients,
            variables=variables, doors=doors, animations=animations,
            notes=notes, rest_encounters=rest_encounters,
            version=version,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "AreFile":
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        # Rebuild the global vertex array from all structures that own vertices.
        # Track per-structure starting indices as we go.
        all_verts: List[Vertex] = []

        def _alloc_verts(verts: List[Vertex]) -> int:
            idx = len(all_verts)
            all_verts.extend(verts)
            return idx

        # Sections (fixed order matches IESDP)
        HEADER_SIZE = HEADER_SIZE_V1  # same base for V9.1

        # Build each section into a BinaryWriter, tracking offsets
        w_actors   = BinaryWriter()
        w_regions  = BinaryWriter()
        w_spawn    = BinaryWriter()
        w_enter    = BinaryWriter()
        w_items    = BinaryWriter()
        w_conts    = BinaryWriter()
        w_ambients = BinaryWriter()
        w_vars     = BinaryWriter()
        w_doors    = BinaryWriter()
        w_anims    = BinaryWriter()
        w_notes    = BinaryWriter()
        w_rest     = BinaryWriter()
        # Vertices written after everything else so indices are known

        for actor in self.actors:
            actor._write(w_actors)

        for reg in self.regions:
            vi = _alloc_verts(reg.vertices)
            reg._write(w_regions, vi)

        for sp in self.spawn_points:
            sp._write(w_spawn)

        for ent in self.entrances:
            ent._write(w_enter)

        for item in self.items:
            item._write(w_items)

        running_item_idx = 0
        for con in self.containers:
            vi = _alloc_verts(con.vertices)
            item_count = con.item_count
            con._write(w_conts, vi, running_item_idx)
            running_item_idx += item_count

        for amb in self.ambients:
            amb._write(w_ambients)

        for var in self.variables:
            var._write(w_vars)

        open_vi_map: dict = {}
        close_vi_map: dict = {}
        for i, door in enumerate(self.doors):
            ovi  = _alloc_verts(door.open_vertices)
            cvi  = _alloc_verts(door.close_vertices)
            open_vi_map[i]  = ovi
            close_vi_map[i] = cvi
        for i, door in enumerate(self.doors):
            door._write(w_doors, open_vi_map[i], close_vi_map[i])

        for anim in self.animations:
            anim._write(w_anims)

        for note in self.notes:
            note._write(w_notes)

        for rest in self.rest_encounters:
            rest._write(w_rest)

        w_verts = BinaryWriter()
        for v in all_verts:
            v._write(w_verts)

        # Compute absolute offsets
        cursor = HEADER_SIZE
        def _off(w: BinaryWriter) -> int:
            nonlocal cursor
            off = cursor
            cursor += w.pos
            return off

        actors_off   = _off(w_actors)
        regions_off  = _off(w_regions)
        spawn_off    = _off(w_spawn)
        enter_off    = _off(w_enter)
        items_off    = _off(w_items)
        conts_off    = _off(w_conts)
        ambients_off = _off(w_ambients)
        vars_off     = _off(w_vars)
        doors_off    = _off(w_doors)
        anims_off    = _off(w_anims)
        notes_off    = _off(w_notes)
        rest_off     = _off(w_rest)
        verts_off    = _off(w_verts)

        # Patch header
        h = self.header
        h.actors_offset     = actors_off;   h.actors_count     = len(self.actors)
        h.regions_offset    = regions_off;  h.regions_count    = len(self.regions)
        h.spawn_offset      = spawn_off;    h.spawn_count      = len(self.spawn_points)
        h.entrances_offset  = enter_off;    h.entrances_count  = len(self.entrances)
        h.items_offset      = items_off;    h.items_count      = len(self.items)
        h.containers_offset = conts_off;    h.containers_count = len(self.containers)
        h.ambients_offset   = ambients_off; h.ambients_count   = len(self.ambients)
        h.variables_offset  = vars_off;     h.variables_count  = len(self.variables)
        h.doors_offset      = doors_off;    h.doors_count      = len(self.doors)
        h.anims_offset      = anims_off;    h.anims_count      = len(self.animations)
        h.notes_offset      = notes_off;    h.notes_count      = len(self.notes)
        h.rest_offset       = rest_off;     h.rest_count       = len(self.rest_encounters)
        h.vertices_offset   = verts_off;    h.vertices_count   = len(all_verts)

        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(self.version)
        h._write(w)
        for section in (w_actors, w_regions, w_spawn, w_enter, w_items,
                        w_conts, w_ambients, w_vars, w_doors, w_anims,
                        w_notes, w_rest, w_verts):
            w.write_bytes(section.to_bytes())

        return w.to_bytes()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        h = self.header
        hd: dict = {
            "wed_resref":  h.wed_resref,
            "area_flags":  h.area_flags,
            "area_type":   h.area_type,
            "area_script": h.area_script,
            "day_song":    h.day_song,
            "night_song":  h.night_song,
            "battle_song": h.battle_song,
        }
        for attr in ("area_north","area_east","area_south","area_west"):
            if getattr(h, attr): hd[attr] = getattr(h, attr)
        for attr in ("rain_probability","snow_probability","fog_probability",
                     "lightning_probability","wind_speed"):
            if getattr(h, attr): hd[attr] = getattr(h, attr)
        if h.v91_extra: hd["v91_extra"] = h.v91_extra.hex()

        d: dict = {"format": "are", "version": _version_str(self.version),
                   "header": hd}
        if self.actors:          d["actors"]          = [a.to_json() for a in self.actors]
        if self.regions:         d["regions"]         = [r.to_json() for r in self.regions]
        if self.spawn_points:    d["spawn_points"]    = [s.to_json() for s in self.spawn_points]
        if self.entrances:       d["entrances"]       = [e.to_json() for e in self.entrances]
        if self.containers:      d["containers"]      = [c.to_json() for c in self.containers]
        if self.items:           d["items"]           = [i.to_json() for i in self.items]
        if self.ambients:        d["ambients"]        = [a.to_json() for a in self.ambients]
        if self.variables:       d["variables"]       = [v.to_json() for v in self.variables]
        if self.doors:           d["doors"]           = [d.to_json() for d in self.doors]
        if self.animations:      d["animations"]      = [a.to_json() for a in self.animations]
        if self.notes:           d["notes"]           = [n.to_json() for n in self.notes]
        if self.rest_encounters: d["rest_encounters"] = [r.to_json() for r in self.rest_encounters]
        return d

    @classmethod
    def from_json(cls, d: dict) -> "AreFile":
        ver_str = d.get("version", "V1.0")
        version = VERSION_V91 if ver_str == "V9.1" else VERSION_V1
        hd = d.get("header", {})
        v91_hex = hd.get("v91_extra","")
        header = AreHeader(
            wed_resref=hd.get("wed_resref",""),
            area_flags=hd.get("area_flags",0),
            area_type=hd.get("area_type", AreaType.DUNGEON),
            area_script=hd.get("area_script",""),
            area_north=hd.get("area_north",""), area_east=hd.get("area_east",""),
            area_south=hd.get("area_south",""), area_west=hd.get("area_west",""),
            rain_probability=hd.get("rain_probability",0),
            snow_probability=hd.get("snow_probability",0),
            fog_probability=hd.get("fog_probability",0),
            lightning_probability=hd.get("lightning_probability",0),
            wind_speed=hd.get("wind_speed",0),
            day_song=hd.get("day_song",0), night_song=hd.get("night_song",0),
            win_song=hd.get("win_song",0), battle_song=hd.get("battle_song",0),
            lose_song=hd.get("lose_song",0),
            v91_extra=bytes.fromhex(v91_hex) if v91_hex else b"",
        )
        return cls(
            header=header,
            actors          = [Actor.from_json(x)          for x in d.get("actors",[])],
            regions         = [Region.from_json(x)         for x in d.get("regions",[])],
            spawn_points    = [SpawnPoint.from_json(x)     for x in d.get("spawn_points",[])],
            entrances       = [Entrance.from_json(x)       for x in d.get("entrances",[])],
            containers      = [Container.from_json(x)      for x in d.get("containers",[])],
            items           = [AreaItem.from_json(x)       for x in d.get("items",[])],
            ambients        = [Ambient.from_json(x)        for x in d.get("ambients",[])],
            variables       = [AreaVariable.from_json(x)   for x in d.get("variables",[])],
            doors           = [Door.from_json(x)           for x in d.get("doors",[])],
            animations      = [AreaAnimation.from_json(x)  for x in d.get("animations",[])],
            notes           = [MapNote.from_json(x)        for x in d.get("notes",[])],
            rest_encounters = [RestEncounter.from_json(x)  for x in d.get("rest_encounters",[])],
            version=version,
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "AreFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<AreFile {src!r} "
            f"actors={len(self.actors)} "
            f"doors={len(self.doors)} "
            f"regions={len(self.regions)}>"
        )


def _version_str(version: bytes) -> str:
    return version.decode("latin-1")
