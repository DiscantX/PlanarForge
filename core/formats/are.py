"""
core/formats/are.py  — ARE V1.0 parser.  M1-M4 complete.
Milestones: [M1] Header [M2] Actors+Regions [M3] SpawnPoints+Entrances+Containers+Items
            [M4] Ambients+Variables+Doors  [M5] Animations+AutomapNotes+TiledObjects+
                 ProjectileTraps+SongEntries+RestInterruptions  [M6] round-trip tests
"""
import struct, math
from typing import List, Optional, Tuple

ARE_SIGNATURE  = b'AREA'
ARE_VERSION_10 = b'V1.0'

HEADER_SIZE            = 0x011C
ACTOR_SIZE             = 0x0110
REGION_SIZE            = 0x00C4
SPAWN_POINT_SIZE       = 0x00C8
ENTRANCE_SIZE          = 0x0068
CONTAINER_SIZE         = 0x00C0
ITEM_SIZE              = 0x0014
AMBIENT_SIZE           = 0x00D4
VARIABLE_SIZE          = 0x0054
DOOR_SIZE              = 0x00C8
ANIMATION_SIZE         = 0x004C
AUTOMAP_NOTE_SIZE      = 0x0034
AUTOMAP_NOTE_PST_SIZE  = 0x0214
TILED_OBJECT_SIZE      = 0x006C
PROJECTILE_TRAP_SIZE   = 0x001C
SONG_ENTRIES_SIZE      = 0x0090
REST_INTERRUPTION_SIZE = 0x00E4
VERTEX_SIZE            = 4

def _resref(b): return b.rstrip(b'\x00').decode('latin-1')
def _resref_encode(s): return s.encode('latin-1')[:8].ljust(8, b'\x00')
def _str32(b): return b.rstrip(b'\x00').decode('latin-1')
def _str32_encode(s): return s.encode('latin-1')[:32].ljust(32, b'\x00')
def _strn_encode(s, n): return s.encode('latin-1')[:n].ljust(n, b'\x00')
def _sparse(d): return {k: v for k, v in d.items() if v not in (0, '', None, [])}
def _verts_from_pool(pool, first, count):
    out = []
    for i in range(count):
        off = (first + i) * VERTEX_SIZE
        if off + VERTEX_SIZE <= len(pool):
            out.append(list(struct.unpack_from('<HH', pool, off)))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
class AreHeader:
    __slots__ = [
        'signature','version','area_wed','last_saved','area_flags',
        'north_resref','north_flags','east_resref','east_flags',
        'south_resref','south_flags','west_resref','west_flags',
        'area_type','rain_probability','snow_probability','fog_probability',
        'lightning_probability','wind_speed',
        'actors_offset','actors_count','regions_count','regions_offset',
        'spawn_points_offset','spawn_points_count',
        'entrances_offset','entrances_count',
        'containers_offset','containers_count','items_count','items_offset',
        'vertices_offset','vertices_count','ambients_count','ambients_offset',
        'variables_offset','variables_count',
        'tiled_object_flags_offset','tiled_object_flags_count',
        'area_script','explored_bitmask_size','explored_bitmask_offset',
        'doors_count','doors_offset','animations_count','animations_offset',
        'tiled_objects_count','tiled_objects_offset',
        'song_entries_offset','rest_interruptions_offset',
        'field_c4','field_c8','field_cc','projectile_traps_count',
        'rest_movie_day','rest_movie_night','unused_e4',
    ]

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= HEADER_SIZE
        h = cls.__new__(cls)
        h.signature = data[0x00:0x04]; h.version = data[0x04:0x08]
        assert h.signature == ARE_SIGNATURE
        h.area_wed = _resref(data[0x08:0x10])
        h.last_saved = struct.unpack_from('<I', data, 0x10)[0]
        h.area_flags = struct.unpack_from('<I', data, 0x14)[0]
        h.north_resref = _resref(data[0x18:0x20]); h.north_flags = struct.unpack_from('<I', data, 0x20)[0]
        h.east_resref  = _resref(data[0x24:0x2c]); h.east_flags  = struct.unpack_from('<I', data, 0x2c)[0]
        h.south_resref = _resref(data[0x30:0x38]); h.south_flags = struct.unpack_from('<I', data, 0x38)[0]
        h.west_resref  = _resref(data[0x3c:0x44]); h.west_flags  = struct.unpack_from('<I', data, 0x44)[0]
        h.area_type             = struct.unpack_from('<H', data, 0x48)[0]
        h.rain_probability      = struct.unpack_from('<H', data, 0x4a)[0]
        h.snow_probability      = struct.unpack_from('<H', data, 0x4c)[0]
        h.fog_probability       = struct.unpack_from('<H', data, 0x4e)[0]
        h.lightning_probability = struct.unpack_from('<H', data, 0x50)[0]
        h.wind_speed            = struct.unpack_from('<H', data, 0x52)[0]
        h.actors_offset  = struct.unpack_from('<I', data, 0x54)[0]
        h.actors_count   = struct.unpack_from('<H', data, 0x58)[0]
        h.regions_count  = struct.unpack_from('<H', data, 0x5a)[0]
        h.regions_offset = struct.unpack_from('<I', data, 0x5c)[0]
        h.spawn_points_offset = struct.unpack_from('<I', data, 0x60)[0]
        h.spawn_points_count  = struct.unpack_from('<I', data, 0x64)[0]
        h.entrances_offset = struct.unpack_from('<I', data, 0x68)[0]
        h.entrances_count  = struct.unpack_from('<I', data, 0x6c)[0]
        h.containers_offset = struct.unpack_from('<I', data, 0x70)[0]
        h.containers_count  = struct.unpack_from('<H', data, 0x74)[0]
        h.items_count       = struct.unpack_from('<H', data, 0x76)[0]
        h.items_offset      = struct.unpack_from('<I', data, 0x78)[0]
        h.vertices_offset = struct.unpack_from('<I', data, 0x7c)[0]
        h.vertices_count  = struct.unpack_from('<H', data, 0x80)[0]
        h.ambients_count  = struct.unpack_from('<H', data, 0x82)[0]
        h.ambients_offset = struct.unpack_from('<I', data, 0x84)[0]
        h.variables_offset = struct.unpack_from('<I', data, 0x88)[0]
        h.variables_count  = struct.unpack_from('<I', data, 0x8c)[0]
        h.tiled_object_flags_offset = struct.unpack_from('<H', data, 0x90)[0]
        h.tiled_object_flags_count  = struct.unpack_from('<H', data, 0x92)[0]
        h.area_script = _resref(data[0x94:0x9c])
        h.explored_bitmask_size   = struct.unpack_from('<I', data, 0x9c)[0]
        h.explored_bitmask_offset = struct.unpack_from('<I', data, 0xa0)[0]
        h.doors_count  = struct.unpack_from('<I', data, 0xa4)[0]
        h.doors_offset = struct.unpack_from('<I', data, 0xa8)[0]
        h.animations_count  = struct.unpack_from('<I', data, 0xac)[0]
        h.animations_offset = struct.unpack_from('<I', data, 0xb0)[0]
        h.tiled_objects_count  = struct.unpack_from('<I', data, 0xb4)[0]
        h.tiled_objects_offset = struct.unpack_from('<I', data, 0xb8)[0]
        h.song_entries_offset       = struct.unpack_from('<I', data, 0xbc)[0]
        h.rest_interruptions_offset = struct.unpack_from('<I', data, 0xc0)[0]
        h.field_c4 = struct.unpack_from('<I', data, 0xc4)[0]
        h.field_c8 = struct.unpack_from('<I', data, 0xc8)[0]
        h.field_cc = struct.unpack_from('<I', data, 0xcc)[0]
        h.projectile_traps_count = struct.unpack_from('<I', data, 0xd0)[0]
        h.rest_movie_day   = _resref(data[0xd4:0xdc])
        h.rest_movie_night = _resref(data[0xdc:0xe4])
        h.unused_e4        = bytes(data[0xe4:0x11c])
        return h

    def to_bytes(self):
        buf = bytearray(HEADER_SIZE)
        buf[0x00:0x04] = self.signature; buf[0x04:0x08] = self.version
        buf[0x08:0x10] = _resref_encode(self.area_wed)
        struct.pack_into('<I', buf, 0x10, self.last_saved)
        struct.pack_into('<I', buf, 0x14, self.area_flags)
        buf[0x18:0x20] = _resref_encode(self.north_resref); struct.pack_into('<I', buf, 0x20, self.north_flags)
        buf[0x24:0x2c] = _resref_encode(self.east_resref);  struct.pack_into('<I', buf, 0x2c, self.east_flags)
        buf[0x30:0x38] = _resref_encode(self.south_resref); struct.pack_into('<I', buf, 0x38, self.south_flags)
        buf[0x3c:0x44] = _resref_encode(self.west_resref);  struct.pack_into('<I', buf, 0x44, self.west_flags)
        struct.pack_into('<H', buf, 0x48, self.area_type)
        struct.pack_into('<H', buf, 0x4a, self.rain_probability)
        struct.pack_into('<H', buf, 0x4c, self.snow_probability)
        struct.pack_into('<H', buf, 0x4e, self.fog_probability)
        struct.pack_into('<H', buf, 0x50, self.lightning_probability)
        struct.pack_into('<H', buf, 0x52, self.wind_speed)
        struct.pack_into('<I', buf, 0x54, self.actors_offset)
        struct.pack_into('<H', buf, 0x58, self.actors_count)
        struct.pack_into('<H', buf, 0x5a, self.regions_count)
        struct.pack_into('<I', buf, 0x5c, self.regions_offset)
        struct.pack_into('<I', buf, 0x60, self.spawn_points_offset)
        struct.pack_into('<I', buf, 0x64, self.spawn_points_count)
        struct.pack_into('<I', buf, 0x68, self.entrances_offset)
        struct.pack_into('<I', buf, 0x6c, self.entrances_count)
        struct.pack_into('<I', buf, 0x70, self.containers_offset)
        struct.pack_into('<H', buf, 0x74, self.containers_count)
        struct.pack_into('<H', buf, 0x76, self.items_count)
        struct.pack_into('<I', buf, 0x78, self.items_offset)
        struct.pack_into('<I', buf, 0x7c, self.vertices_offset)
        struct.pack_into('<H', buf, 0x80, self.vertices_count)
        struct.pack_into('<H', buf, 0x82, self.ambients_count)
        struct.pack_into('<I', buf, 0x84, self.ambients_offset)
        struct.pack_into('<I', buf, 0x88, self.variables_offset)
        struct.pack_into('<I', buf, 0x8c, self.variables_count)
        struct.pack_into('<H', buf, 0x90, self.tiled_object_flags_offset)
        struct.pack_into('<H', buf, 0x92, self.tiled_object_flags_count)
        buf[0x94:0x9c] = _resref_encode(self.area_script)
        struct.pack_into('<I', buf, 0x9c, self.explored_bitmask_size)
        struct.pack_into('<I', buf, 0xa0, self.explored_bitmask_offset)
        struct.pack_into('<I', buf, 0xa4, self.doors_count)
        struct.pack_into('<I', buf, 0xa8, self.doors_offset)
        struct.pack_into('<I', buf, 0xac, self.animations_count)
        struct.pack_into('<I', buf, 0xb0, self.animations_offset)
        struct.pack_into('<I', buf, 0xb4, self.tiled_objects_count)
        struct.pack_into('<I', buf, 0xb8, self.tiled_objects_offset)
        struct.pack_into('<I', buf, 0xbc, self.song_entries_offset)
        struct.pack_into('<I', buf, 0xc0, self.rest_interruptions_offset)
        struct.pack_into('<I', buf, 0xc4, self.field_c4)
        struct.pack_into('<I', buf, 0xc8, self.field_c8)
        struct.pack_into('<I', buf, 0xcc, self.field_cc)
        struct.pack_into('<I', buf, 0xd0, self.projectile_traps_count)
        buf[0xd4:0xdc] = _resref_encode(self.rest_movie_day)
        buf[0xdc:0xe4] = _resref_encode(self.rest_movie_night)
        buf[0xe4:0x11c] = self.unused_e4[:56]
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'area_wed': self.area_wed, 'last_saved': self.last_saved, 'area_flags': self.area_flags,
            'north_resref': self.north_resref, 'north_flags': self.north_flags,
            'east_resref':  self.east_resref,  'east_flags':  self.east_flags,
            'south_resref': self.south_resref, 'south_flags': self.south_flags,
            'west_resref':  self.west_resref,  'west_flags':  self.west_flags,
            'area_type': self.area_type,
            'rain_probability': self.rain_probability, 'snow_probability': self.snow_probability,
            'fog_probability': self.fog_probability, 'lightning_probability': self.lightning_probability,
            'wind_speed': self.wind_speed, 'area_script': self.area_script,
            'field_c4': self.field_c4, 'field_c8': self.field_c8, 'field_cc': self.field_cc,
            'projectile_traps_count': self.projectile_traps_count,
            'rest_movie_day': self.rest_movie_day, 'rest_movie_night': self.rest_movie_night,
        })

    @classmethod
    def from_json(cls, d, offsets):
        h = cls.__new__(cls)
        h.signature = ARE_SIGNATURE; h.version = ARE_VERSION_10
        h.area_wed = d.get('area_wed',''); h.last_saved = d.get('last_saved',0); h.area_flags = d.get('area_flags',0)
        h.north_resref=d.get('north_resref',''); h.north_flags=d.get('north_flags',0)
        h.east_resref =d.get('east_resref', ''); h.east_flags =d.get('east_flags', 0)
        h.south_resref=d.get('south_resref',''); h.south_flags=d.get('south_flags',0)
        h.west_resref =d.get('west_resref', ''); h.west_flags =d.get('west_flags', 0)
        h.area_type=d.get('area_type',0); h.rain_probability=d.get('rain_probability',0)
        h.snow_probability=d.get('snow_probability',0); h.fog_probability=d.get('fog_probability',0)
        h.lightning_probability=d.get('lightning_probability',0); h.wind_speed=d.get('wind_speed',0)
        h.area_script=d.get('area_script','')
        h.field_c4=d.get('field_c4',0); h.field_c8=d.get('field_c8',0); h.field_cc=d.get('field_cc',0)
        h.projectile_traps_count=d.get('projectile_traps_count',0)
        h.rest_movie_day=d.get('rest_movie_day',''); h.rest_movie_night=d.get('rest_movie_night','')
        h.unused_e4=bytes(56)
        for k,v in offsets.items(): setattr(h, k, v)
        return h


# ─────────────────────────────────────────────────────────────────────────────
# Actors
# ─────────────────────────────────────────────────────────────────────────────
class AreActor:
    """272 bytes. flags bit 0 INVERTED: clear = embedded CRE present."""
    __slots__ = [
        'name','current_x','current_y','destination_x','destination_y',
        'flags','has_been_spawned','first_letter_cre','unused_2f',
        'actor_animation','actor_orientation','unused_36','removal_timer',
        'movement_restriction_distance','movement_restriction_distance_to_object',
        'appearance_schedule','num_times_talked_to',
        'dialog','script_override','script_general','script_class',
        'script_race','script_default','script_specific',
        'cre_file','cre_offset','cre_size','unused_90','embedded_cre',
    ]

    @classmethod
    def from_bytes(cls, data, file_data=None):
        assert len(data) >= ACTOR_SIZE
        a = cls.__new__(cls)
        a.name=_str32(data[0x00:0x20]); a.current_x=struct.unpack_from('<H',data,0x20)[0]; a.current_y=struct.unpack_from('<H',data,0x22)[0]
        a.destination_x=struct.unpack_from('<H',data,0x24)[0]; a.destination_y=struct.unpack_from('<H',data,0x26)[0]
        a.flags=struct.unpack_from('<I',data,0x28)[0]; a.has_been_spawned=struct.unpack_from('<H',data,0x2c)[0]
        a.first_letter_cre=data[0x2e]; a.unused_2f=data[0x2f]
        a.actor_animation=struct.unpack_from('<I',data,0x30)[0]; a.actor_orientation=struct.unpack_from('<H',data,0x34)[0]
        a.unused_36=struct.unpack_from('<H',data,0x36)[0]; a.removal_timer=struct.unpack_from('<I',data,0x38)[0]
        a.movement_restriction_distance=struct.unpack_from('<H',data,0x3c)[0]
        a.movement_restriction_distance_to_object=struct.unpack_from('<H',data,0x3e)[0]
        a.appearance_schedule=struct.unpack_from('<I',data,0x40)[0]; a.num_times_talked_to=struct.unpack_from('<I',data,0x44)[0]
        a.dialog=_resref(data[0x48:0x50]); a.script_override=_resref(data[0x50:0x58])
        a.script_general=_resref(data[0x58:0x60]); a.script_class=_resref(data[0x60:0x68])
        a.script_race=_resref(data[0x68:0x70]); a.script_default=_resref(data[0x70:0x78])
        a.script_specific=_resref(data[0x78:0x80]); a.cre_file=_resref(data[0x80:0x88])
        a.cre_offset=struct.unpack_from('<I',data,0x88)[0]; a.cre_size=struct.unpack_from('<I',data,0x8c)[0]
        a.unused_90=bytes(data[0x90:0x110])
        cre_attached = not (a.flags & 0x01)
        a.embedded_cre = bytes(file_data[a.cre_offset:a.cre_offset+a.cre_size]) if (cre_attached and a.cre_size>0 and file_data) else None
        return a

    def to_bytes(self, embedded_cre_offset=0):
        buf = bytearray(ACTOR_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.current_x); struct.pack_into('<H',buf,0x22,self.current_y)
        struct.pack_into('<H',buf,0x24,self.destination_x); struct.pack_into('<H',buf,0x26,self.destination_y)
        struct.pack_into('<I',buf,0x28,self.flags); struct.pack_into('<H',buf,0x2c,self.has_been_spawned)
        buf[0x2e]=self.first_letter_cre; buf[0x2f]=self.unused_2f
        struct.pack_into('<I',buf,0x30,self.actor_animation); struct.pack_into('<H',buf,0x34,self.actor_orientation)
        struct.pack_into('<H',buf,0x36,self.unused_36); struct.pack_into('<I',buf,0x38,self.removal_timer)
        struct.pack_into('<H',buf,0x3c,self.movement_restriction_distance)
        struct.pack_into('<H',buf,0x3e,self.movement_restriction_distance_to_object)
        struct.pack_into('<I',buf,0x40,self.appearance_schedule); struct.pack_into('<I',buf,0x44,self.num_times_talked_to)
        buf[0x48:0x50]=_resref_encode(self.dialog); buf[0x50:0x58]=_resref_encode(self.script_override)
        buf[0x58:0x60]=_resref_encode(self.script_general); buf[0x60:0x68]=_resref_encode(self.script_class)
        buf[0x68:0x70]=_resref_encode(self.script_race); buf[0x70:0x78]=_resref_encode(self.script_default)
        buf[0x78:0x80]=_resref_encode(self.script_specific); buf[0x80:0x88]=_resref_encode(self.cre_file)
        if self.embedded_cre:
            struct.pack_into('<I',buf,0x88,embedded_cre_offset); struct.pack_into('<I',buf,0x8c,len(self.embedded_cre))
        else:
            struct.pack_into('<I',buf,0x88,self.cre_offset); struct.pack_into('<I',buf,0x8c,self.cre_size)
        buf[0x90:0x110]=self.unused_90
        return bytes(buf)

    def to_json(self):
        d={'name':self.name,'current_x':self.current_x,'current_y':self.current_y,
           'destination_x':self.destination_x,'destination_y':self.destination_y,
           'flags':self.flags,'has_been_spawned':self.has_been_spawned,'first_letter_cre':self.first_letter_cre,
           'actor_animation':self.actor_animation,'actor_orientation':self.actor_orientation,
           'removal_timer':self.removal_timer,
           'movement_restriction_distance':self.movement_restriction_distance,
           'movement_restriction_distance_to_object':self.movement_restriction_distance_to_object,
           'appearance_schedule':self.appearance_schedule,'num_times_talked_to':self.num_times_talked_to,
           'dialog':self.dialog,'script_override':self.script_override,'script_general':self.script_general,
           'script_class':self.script_class,'script_race':self.script_race,'script_default':self.script_default,
           'script_specific':self.script_specific,'cre_file':self.cre_file}
        if self.embedded_cre: d['embedded_cre']=self.embedded_cre.hex()
        return _sparse(d)

    @classmethod
    def from_json(cls, d):
        a=cls.__new__(cls)
        a.name=d.get('name',''); a.current_x=d.get('current_x',0); a.current_y=d.get('current_y',0)
        a.destination_x=d.get('destination_x',0); a.destination_y=d.get('destination_y',0)
        a.flags=d.get('flags',0); a.has_been_spawned=d.get('has_been_spawned',0)
        a.first_letter_cre=d.get('first_letter_cre',0); a.unused_2f=0
        a.actor_animation=d.get('actor_animation',0); a.actor_orientation=d.get('actor_orientation',0); a.unused_36=0
        a.removal_timer=d.get('removal_timer',0xFFFFFFFF)
        a.movement_restriction_distance=d.get('movement_restriction_distance',0)
        a.movement_restriction_distance_to_object=d.get('movement_restriction_distance_to_object',0)
        a.appearance_schedule=d.get('appearance_schedule',0); a.num_times_talked_to=d.get('num_times_talked_to',0)
        a.dialog=d.get('dialog',''); a.script_override=d.get('script_override','')
        a.script_general=d.get('script_general',''); a.script_class=d.get('script_class','')
        a.script_race=d.get('script_race',''); a.script_default=d.get('script_default','')
        a.script_specific=d.get('script_specific',''); a.cre_file=d.get('cre_file','')
        a.cre_offset=0; a.cre_size=0; a.unused_90=bytes(128)
        raw=d.get('embedded_cre'); a.embedded_cre=bytes.fromhex(raw) if raw else None
        return a


# ─────────────────────────────────────────────────────────────────────────────
# Regions
# ─────────────────────────────────────────────────────────────────────────────
class AreRegion:
    """196 bytes. Vertices inlined. PST fields always parsed."""
    __slots__=['name','region_type','bounding_box','trigger_value','cursor_index',
               'destination_area','entrance_name','flags','information_text',
               'trap_detection_difficulty','trap_removal_difficulty',
               'is_trapped','trap_detected','trap_launch_x','trap_launch_y',
               'key_item','region_script','alt_use_point_x','alt_use_point_y',
               'unknown_88','unknown_8c','sound','talk_location_x','talk_location_y',
               'speaker_name','dialog_file','vertices']

    @classmethod
    def from_bytes(cls, data, vertex_pool, first_vi):
        assert len(data) >= REGION_SIZE
        r=cls.__new__(cls)
        r.name=_str32(data[0x00:0x20]); r.region_type=struct.unpack_from('<H',data,0x20)[0]
        r.bounding_box=list(struct.unpack_from('<4H',data,0x22))
        vc=struct.unpack_from('<H',data,0x2a)[0]
        r.trigger_value=struct.unpack_from('<I',data,0x30)[0]; r.cursor_index=struct.unpack_from('<I',data,0x34)[0]
        r.destination_area=_resref(data[0x38:0x40]); r.entrance_name=_str32(data[0x40:0x60])
        r.flags=struct.unpack_from('<I',data,0x60)[0]; r.information_text=struct.unpack_from('<I',data,0x64)[0]
        r.trap_detection_difficulty=struct.unpack_from('<H',data,0x68)[0]
        r.trap_removal_difficulty=struct.unpack_from('<H',data,0x6a)[0]
        r.is_trapped=struct.unpack_from('<H',data,0x6c)[0]; r.trap_detected=struct.unpack_from('<H',data,0x6e)[0]
        r.trap_launch_x=struct.unpack_from('<H',data,0x70)[0]; r.trap_launch_y=struct.unpack_from('<H',data,0x72)[0]
        r.key_item=_resref(data[0x74:0x7c]); r.region_script=_resref(data[0x7c:0x84])
        r.alt_use_point_x=struct.unpack_from('<H',data,0x84)[0]; r.alt_use_point_y=struct.unpack_from('<H',data,0x86)[0]
        r.unknown_88=struct.unpack_from('<I',data,0x88)[0]; r.unknown_8c=bytes(data[0x8c:0xac])
        r.sound=_resref(data[0xac:0xb4]); r.talk_location_x=struct.unpack_from('<H',data,0xb4)[0]
        r.talk_location_y=struct.unpack_from('<H',data,0xb6)[0]; r.speaker_name=struct.unpack_from('<I',data,0xb8)[0]
        r.dialog_file=_resref(data[0xbc:0xc4])
        r.vertices=_verts_from_pool(vertex_pool,first_vi,vc)
        return r

    def to_bytes(self, first_vi):
        buf=bytearray(REGION_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name); struct.pack_into('<H',buf,0x20,self.region_type)
        struct.pack_into('<4H',buf,0x22,*self.bounding_box)
        struct.pack_into('<H',buf,0x2a,len(self.vertices)); struct.pack_into('<I',buf,0x2c,first_vi)
        struct.pack_into('<I',buf,0x30,self.trigger_value); struct.pack_into('<I',buf,0x34,self.cursor_index)
        buf[0x38:0x40]=_resref_encode(self.destination_area); buf[0x40:0x60]=_str32_encode(self.entrance_name)
        struct.pack_into('<I',buf,0x60,self.flags); struct.pack_into('<I',buf,0x64,self.information_text)
        struct.pack_into('<H',buf,0x68,self.trap_detection_difficulty); struct.pack_into('<H',buf,0x6a,self.trap_removal_difficulty)
        struct.pack_into('<H',buf,0x6c,self.is_trapped); struct.pack_into('<H',buf,0x6e,self.trap_detected)
        struct.pack_into('<H',buf,0x70,self.trap_launch_x); struct.pack_into('<H',buf,0x72,self.trap_launch_y)
        buf[0x74:0x7c]=_resref_encode(self.key_item); buf[0x7c:0x84]=_resref_encode(self.region_script)
        struct.pack_into('<H',buf,0x84,self.alt_use_point_x); struct.pack_into('<H',buf,0x86,self.alt_use_point_y)
        struct.pack_into('<I',buf,0x88,self.unknown_88); buf[0x8c:0xac]=self.unknown_8c[:32]
        buf[0xac:0xb4]=_resref_encode(self.sound)
        struct.pack_into('<H',buf,0xb4,self.talk_location_x); struct.pack_into('<H',buf,0xb6,self.talk_location_y)
        struct.pack_into('<I',buf,0xb8,self.speaker_name); buf[0xbc:0xc4]=_resref_encode(self.dialog_file)
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'region_type':self.region_type,'bounding_box':self.bounding_box,
            'trigger_value':self.trigger_value,'cursor_index':self.cursor_index,
            'destination_area':self.destination_area,'entrance_name':self.entrance_name,
            'flags':self.flags,'information_text':self.information_text,
            'trap_detection_difficulty':self.trap_detection_difficulty,
            'trap_removal_difficulty':self.trap_removal_difficulty,
            'is_trapped':self.is_trapped,'trap_detected':self.trap_detected,
            'trap_launch_x':self.trap_launch_x,'trap_launch_y':self.trap_launch_y,
            'key_item':self.key_item,'region_script':self.region_script,
            'alt_use_point_x':self.alt_use_point_x,'alt_use_point_y':self.alt_use_point_y,
            'unknown_88':self.unknown_88,
            'unknown_8c':self.unknown_8c.hex() if any(self.unknown_8c) else None,
            'sound':self.sound,'talk_location_x':self.talk_location_x,'talk_location_y':self.talk_location_y,
            'speaker_name':self.speaker_name,'dialog_file':self.dialog_file,'vertices':self.vertices})

    @classmethod
    def from_json(cls, d):
        r=cls.__new__(cls)
        r.name=d.get('name',''); r.region_type=d.get('region_type',0)
        r.bounding_box=d.get('bounding_box',[0,0,0,0])
        r.trigger_value=d.get('trigger_value',0); r.cursor_index=d.get('cursor_index',0)
        r.destination_area=d.get('destination_area',''); r.entrance_name=d.get('entrance_name','')
        r.flags=d.get('flags',0); r.information_text=d.get('information_text',0)
        r.trap_detection_difficulty=d.get('trap_detection_difficulty',0)
        r.trap_removal_difficulty=d.get('trap_removal_difficulty',0)
        r.is_trapped=d.get('is_trapped',0); r.trap_detected=d.get('trap_detected',0)
        r.trap_launch_x=d.get('trap_launch_x',0); r.trap_launch_y=d.get('trap_launch_y',0)
        r.key_item=d.get('key_item',''); r.region_script=d.get('region_script','')
        r.alt_use_point_x=d.get('alt_use_point_x',0); r.alt_use_point_y=d.get('alt_use_point_y',0)
        r.unknown_88=d.get('unknown_88',0)
        unk=d.get('unknown_8c'); r.unknown_8c=bytes.fromhex(unk) if unk else bytes(32)
        r.sound=d.get('sound',''); r.talk_location_x=d.get('talk_location_x',0)
        r.talk_location_y=d.get('talk_location_y',0); r.speaker_name=d.get('speaker_name',0)
        r.dialog_file=d.get('dialog_file',''); r.vertices=d.get('vertices',[])
        return r


# ─────────────────────────────────────────────────────────────────────────────
# Spawn Points
# ─────────────────────────────────────────────────────────────────────────────
class AreSpawnPoint:
    """200 bytes. 10 creature slots. tail_90 (56 bytes) stored verbatim."""
    __slots__=['name','x','y','creature_resrefs','creature_count','base_creature_number',
               'frequency','spawn_method','actor_removal_timer',
               'movement_restriction_distance','movement_restriction_distance_to_object',
               'max_creatures','enabled','appearance_schedule',
               'probability_day','probability_night','tail_90']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= SPAWN_POINT_SIZE
        s=cls.__new__(cls)
        s.name=_str32(data[0x00:0x20]); s.x=struct.unpack_from('<H',data,0x20)[0]; s.y=struct.unpack_from('<H',data,0x22)[0]
        s.creature_resrefs=[_resref(data[0x24+i*8:0x24+i*8+8]) for i in range(10)]
        s.creature_count=struct.unpack_from('<H',data,0x74)[0]; s.base_creature_number=struct.unpack_from('<H',data,0x76)[0]
        s.frequency=struct.unpack_from('<H',data,0x78)[0]; s.spawn_method=struct.unpack_from('<H',data,0x7a)[0]
        s.actor_removal_timer=struct.unpack_from('<I',data,0x7c)[0]
        s.movement_restriction_distance=struct.unpack_from('<H',data,0x80)[0]
        s.movement_restriction_distance_to_object=struct.unpack_from('<H',data,0x82)[0]
        s.max_creatures=struct.unpack_from('<H',data,0x84)[0]; s.enabled=struct.unpack_from('<H',data,0x86)[0]
        s.appearance_schedule=struct.unpack_from('<I',data,0x88)[0]
        s.probability_day=struct.unpack_from('<H',data,0x8c)[0]; s.probability_night=struct.unpack_from('<H',data,0x8e)[0]
        s.tail_90=bytes(data[0x90:0xc8])
        return s

    def to_bytes(self):
        buf=bytearray(SPAWN_POINT_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.x); struct.pack_into('<H',buf,0x22,self.y)
        rr=(list(self.creature_resrefs)+['']*10)[:10]
        for i in range(10): buf[0x24+i*8:0x24+i*8+8]=_resref_encode(rr[i])
        struct.pack_into('<H',buf,0x74,self.creature_count); struct.pack_into('<H',buf,0x76,self.base_creature_number)
        struct.pack_into('<H',buf,0x78,self.frequency); struct.pack_into('<H',buf,0x7a,self.spawn_method)
        struct.pack_into('<I',buf,0x7c,self.actor_removal_timer)
        struct.pack_into('<H',buf,0x80,self.movement_restriction_distance)
        struct.pack_into('<H',buf,0x82,self.movement_restriction_distance_to_object)
        struct.pack_into('<H',buf,0x84,self.max_creatures); struct.pack_into('<H',buf,0x86,self.enabled)
        struct.pack_into('<I',buf,0x88,self.appearance_schedule)
        struct.pack_into('<H',buf,0x8c,self.probability_day); struct.pack_into('<H',buf,0x8e,self.probability_night)
        buf[0x90:0xc8]=self.tail_90[:56]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'x':self.x,'y':self.y,
            'creature_resrefs':[r for r in self.creature_resrefs if r],
            'creature_count':self.creature_count,'base_creature_number':self.base_creature_number,
            'frequency':self.frequency,'spawn_method':self.spawn_method,
            'actor_removal_timer':self.actor_removal_timer,
            'movement_restriction_distance':self.movement_restriction_distance,
            'movement_restriction_distance_to_object':self.movement_restriction_distance_to_object,
            'max_creatures':self.max_creatures,'enabled':self.enabled,
            'appearance_schedule':self.appearance_schedule,
            'probability_day':self.probability_day,'probability_night':self.probability_night,
            'tail_90':self.tail_90.hex() if any(self.tail_90) else None})

    @classmethod
    def from_json(cls, d):
        s=cls.__new__(cls); s.name=d.get('name',''); s.x=d.get('x',0); s.y=d.get('y',0)
        rr=d.get('creature_resrefs',[]); s.creature_resrefs=(rr+['']*10)[:10]
        s.creature_count=d.get('creature_count',0); s.base_creature_number=d.get('base_creature_number',0)
        s.frequency=d.get('frequency',0); s.spawn_method=d.get('spawn_method',0)
        s.actor_removal_timer=d.get('actor_removal_timer',0xFFFFFFFF)
        s.movement_restriction_distance=d.get('movement_restriction_distance',0)
        s.movement_restriction_distance_to_object=d.get('movement_restriction_distance_to_object',0)
        s.max_creatures=d.get('max_creatures',0); s.enabled=d.get('enabled',0)
        s.appearance_schedule=d.get('appearance_schedule',0)
        s.probability_day=d.get('probability_day',0); s.probability_night=d.get('probability_night',0)
        t=d.get('tail_90'); s.tail_90=bytes.fromhex(t) if t else bytes(56)
        return s


# ─────────────────────────────────────────────────────────────────────────────
# Entrances
# ─────────────────────────────────────────────────────────────────────────────
class AreEntrance:
    """104 bytes."""
    __slots__=['name','x','y','orientation','unused_26']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= ENTRANCE_SIZE
        e=cls.__new__(cls)
        e.name=_str32(data[0x00:0x20]); e.x=struct.unpack_from('<H',data,0x20)[0]
        e.y=struct.unpack_from('<H',data,0x22)[0]; e.orientation=struct.unpack_from('<H',data,0x24)[0]
        e.unused_26=bytes(data[0x26:0x68])
        return e

    def to_bytes(self):
        buf=bytearray(ENTRANCE_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.x); struct.pack_into('<H',buf,0x22,self.y)
        struct.pack_into('<H',buf,0x24,self.orientation); buf[0x26:0x68]=self.unused_26[:66]
        return bytes(buf)

    def to_json(self): return _sparse({'name':self.name,'x':self.x,'y':self.y,'orientation':self.orientation})

    @classmethod
    def from_json(cls, d):
        e=cls.__new__(cls); e.name=d.get('name',''); e.x=d.get('x',0); e.y=d.get('y',0)
        e.orientation=d.get('orientation',0); e.unused_26=bytes(66)
        return e


# ─────────────────────────────────────────────────────────────────────────────
# Items
# ─────────────────────────────────────────────────────────────────────────────
class AreItem:
    """20 bytes. Inlined per container."""
    __slots__=['item_resref','expiration_time','charges_1','charges_2','charges_3','flags']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= ITEM_SIZE
        it=cls.__new__(cls)
        it.item_resref=_resref(data[0x00:0x08]); it.expiration_time=struct.unpack_from('<H',data,0x08)[0]
        it.charges_1=struct.unpack_from('<H',data,0x0a)[0]; it.charges_2=struct.unpack_from('<H',data,0x0c)[0]
        it.charges_3=struct.unpack_from('<H',data,0x0e)[0]; it.flags=struct.unpack_from('<I',data,0x10)[0]
        return it

    def to_bytes(self):
        buf=bytearray(ITEM_SIZE); buf[0x00:0x08]=_resref_encode(self.item_resref)
        struct.pack_into('<H',buf,0x08,self.expiration_time); struct.pack_into('<H',buf,0x0a,self.charges_1)
        struct.pack_into('<H',buf,0x0c,self.charges_2); struct.pack_into('<H',buf,0x0e,self.charges_3)
        struct.pack_into('<I',buf,0x10,self.flags)
        return bytes(buf)

    def to_json(self): return _sparse({'item_resref':self.item_resref,'expiration_time':self.expiration_time,
        'charges_1':self.charges_1,'charges_2':self.charges_2,'charges_3':self.charges_3,'flags':self.flags})

    @classmethod
    def from_json(cls, d):
        it=cls.__new__(cls); it.item_resref=d.get('item_resref',''); it.expiration_time=d.get('expiration_time',0)
        it.charges_1=d.get('charges_1',0); it.charges_2=d.get('charges_2',0)
        it.charges_3=d.get('charges_3',0); it.flags=d.get('flags',0)
        return it


# ─────────────────────────────────────────────────────────────────────────────
# Containers
# ─────────────────────────────────────────────────────────────────────────────
class AreContainer:
    """192 bytes. Bounding box = 4 words at 0x0038 (IESDP typo corrected).
    owner (0x0058) is 32-byte script name, not resref. Items+vertices inlined."""
    __slots__=['name','x','y','container_type','lock_difficulty','flags',
               'trap_detection_difficulty','trap_removal_difficulty',
               'is_trapped','trap_detected','trap_launch_x','trap_launch_y',
               'bounding_box','trap_script','trigger_range','owner',
               'key_item','break_difficulty','lockpick_string','unused_88',
               'items','vertices']

    @classmethod
    def from_bytes(cls, data, item_pool, first_item_index, vertex_pool, first_vi):
        assert len(data) >= CONTAINER_SIZE
        c=cls.__new__(cls)
        c.name=_str32(data[0x00:0x20]); c.x=struct.unpack_from('<H',data,0x20)[0]; c.y=struct.unpack_from('<H',data,0x22)[0]
        c.container_type=struct.unpack_from('<H',data,0x24)[0]; c.lock_difficulty=struct.unpack_from('<H',data,0x26)[0]
        c.flags=struct.unpack_from('<I',data,0x28)[0]
        c.trap_detection_difficulty=struct.unpack_from('<H',data,0x2c)[0]
        c.trap_removal_difficulty=struct.unpack_from('<H',data,0x2e)[0]
        c.is_trapped=struct.unpack_from('<H',data,0x30)[0]; c.trap_detected=struct.unpack_from('<H',data,0x32)[0]
        c.trap_launch_x=struct.unpack_from('<H',data,0x34)[0]; c.trap_launch_y=struct.unpack_from('<H',data,0x36)[0]
        c.bounding_box=list(struct.unpack_from('<4H',data,0x38))
        item_count=struct.unpack_from('<I',data,0x44)[0]; c.trap_script=_resref(data[0x48:0x50])
        vertex_count=struct.unpack_from('<H',data,0x54)[0]; c.trigger_range=struct.unpack_from('<H',data,0x56)[0]
        c.owner=_str32(data[0x58:0x78]); c.key_item=_resref(data[0x78:0x80])
        c.break_difficulty=struct.unpack_from('<I',data,0x80)[0]; c.lockpick_string=struct.unpack_from('<I',data,0x84)[0]
        c.unused_88=bytes(data[0x88:0xc0])
        c.items=[AreItem.from_bytes(item_pool[(first_item_index+i)*ITEM_SIZE:(first_item_index+i)*ITEM_SIZE+ITEM_SIZE])
                 for i in range(item_count) if (first_item_index+i)*ITEM_SIZE+ITEM_SIZE<=len(item_pool)]
        c.vertices=_verts_from_pool(vertex_pool,first_vi,vertex_count)
        return c

    def to_bytes(self, first_item_index, first_vi):
        buf=bytearray(CONTAINER_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.x); struct.pack_into('<H',buf,0x22,self.y)
        struct.pack_into('<H',buf,0x24,self.container_type); struct.pack_into('<H',buf,0x26,self.lock_difficulty)
        struct.pack_into('<I',buf,0x28,self.flags)
        struct.pack_into('<H',buf,0x2c,self.trap_detection_difficulty); struct.pack_into('<H',buf,0x2e,self.trap_removal_difficulty)
        struct.pack_into('<H',buf,0x30,self.is_trapped); struct.pack_into('<H',buf,0x32,self.trap_detected)
        struct.pack_into('<H',buf,0x34,self.trap_launch_x); struct.pack_into('<H',buf,0x36,self.trap_launch_y)
        struct.pack_into('<4H',buf,0x38,*self.bounding_box)
        struct.pack_into('<I',buf,0x40,first_item_index); struct.pack_into('<I',buf,0x44,len(self.items))
        buf[0x48:0x50]=_resref_encode(self.trap_script)
        struct.pack_into('<I',buf,0x50,first_vi); struct.pack_into('<H',buf,0x54,len(self.vertices))
        struct.pack_into('<H',buf,0x56,self.trigger_range); buf[0x58:0x78]=_str32_encode(self.owner)
        buf[0x78:0x80]=_resref_encode(self.key_item)
        struct.pack_into('<I',buf,0x80,self.break_difficulty); struct.pack_into('<I',buf,0x84,self.lockpick_string)
        buf[0x88:0xc0]=self.unused_88[:56]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'x':self.x,'y':self.y,
            'container_type':self.container_type,'lock_difficulty':self.lock_difficulty,'flags':self.flags,
            'trap_detection_difficulty':self.trap_detection_difficulty,
            'trap_removal_difficulty':self.trap_removal_difficulty,
            'is_trapped':self.is_trapped,'trap_detected':self.trap_detected,
            'trap_launch_x':self.trap_launch_x,'trap_launch_y':self.trap_launch_y,
            'bounding_box':self.bounding_box,'trap_script':self.trap_script,
            'trigger_range':self.trigger_range,'owner':self.owner,'key_item':self.key_item,
            'break_difficulty':self.break_difficulty,'lockpick_string':self.lockpick_string,
            'items':[it.to_json() for it in self.items],'vertices':self.vertices})

    @classmethod
    def from_json(cls, d):
        c=cls.__new__(cls); c.name=d.get('name',''); c.x=d.get('x',0); c.y=d.get('y',0)
        c.container_type=d.get('container_type',0); c.lock_difficulty=d.get('lock_difficulty',0)
        c.flags=d.get('flags',0); c.trap_detection_difficulty=d.get('trap_detection_difficulty',0)
        c.trap_removal_difficulty=d.get('trap_removal_difficulty',0)
        c.is_trapped=d.get('is_trapped',0); c.trap_detected=d.get('trap_detected',0)
        c.trap_launch_x=d.get('trap_launch_x',0); c.trap_launch_y=d.get('trap_launch_y',0)
        c.bounding_box=d.get('bounding_box',[0,0,0,0]); c.trap_script=d.get('trap_script','')
        c.trigger_range=d.get('trigger_range',0); c.owner=d.get('owner',''); c.key_item=d.get('key_item','')
        c.break_difficulty=d.get('break_difficulty',0); c.lockpick_string=d.get('lockpick_string',0)
        c.unused_88=bytes(56)
        c.items=[AreItem.from_json(it) for it in d.get('items',[])]
        c.vertices=d.get('vertices',[])
        return c


# ─────────────────────────────────────────────────────────────────────────────
# Ambients  (M4)
# ─────────────────────────────────────────────────────────────────────────────
class AreAmbient:
    """
    212 bytes. Up to 10 sound slots; count_of_sounds (0x0080) governs how many
    are active.  JSON stores only occupied slots; unused are zeroed on rebuild.

    Flags (0x0090):
      bit 0 enabled   bit 1 disable-env   bit 2 global
      bit 3 random    bit 4 low-mem-1
    """
    __slots__=['name','x','y','radius','height','pitch_variance','volume_variance',
               'volume','sounds','unused_82','base_time','base_time_deviation',
               'appearance_schedule','flags','unused_94']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= AMBIENT_SIZE
        a=cls.__new__(cls)
        a.name=_str32(data[0x00:0x20]); a.x=struct.unpack_from('<H',data,0x20)[0]; a.y=struct.unpack_from('<H',data,0x22)[0]
        a.radius=struct.unpack_from('<H',data,0x24)[0]; a.height=struct.unpack_from('<H',data,0x26)[0]
        a.pitch_variance=struct.unpack_from('<I',data,0x28)[0]; a.volume_variance=struct.unpack_from('<H',data,0x2c)[0]
        a.volume=struct.unpack_from('<H',data,0x2e)[0]
        count=struct.unpack_from('<H',data,0x80)[0]
        all_snd=[_resref(data[0x30+i*8:0x30+i*8+8]) for i in range(10)]
        a.sounds=all_snd[:count]
        a.unused_82=struct.unpack_from('<H',data,0x82)[0]
        a.base_time=struct.unpack_from('<I',data,0x84)[0]; a.base_time_deviation=struct.unpack_from('<I',data,0x88)[0]
        a.appearance_schedule=struct.unpack_from('<I',data,0x8c)[0]; a.flags=struct.unpack_from('<I',data,0x90)[0]
        a.unused_94=bytes(data[0x94:0xd4])
        return a

    def to_bytes(self):
        buf=bytearray(AMBIENT_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.x); struct.pack_into('<H',buf,0x22,self.y)
        struct.pack_into('<H',buf,0x24,self.radius); struct.pack_into('<H',buf,0x26,self.height)
        struct.pack_into('<I',buf,0x28,self.pitch_variance); struct.pack_into('<H',buf,0x2c,self.volume_variance)
        struct.pack_into('<H',buf,0x2e,self.volume)
        snd=(list(self.sounds)+['']*10)[:10]
        for i in range(10): buf[0x30+i*8:0x30+i*8+8]=_resref_encode(snd[i])
        struct.pack_into('<H',buf,0x80,len(self.sounds)); struct.pack_into('<H',buf,0x82,self.unused_82)
        struct.pack_into('<I',buf,0x84,self.base_time); struct.pack_into('<I',buf,0x88,self.base_time_deviation)
        struct.pack_into('<I',buf,0x8c,self.appearance_schedule); struct.pack_into('<I',buf,0x90,self.flags)
        buf[0x94:0xd4]=self.unused_94[:64]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'x':self.x,'y':self.y,'radius':self.radius,'height':self.height,
            'pitch_variance':self.pitch_variance,'volume_variance':self.volume_variance,'volume':self.volume,
            'sounds':self.sounds,'base_time':self.base_time,'base_time_deviation':self.base_time_deviation,
            'appearance_schedule':self.appearance_schedule,'flags':self.flags})

    @classmethod
    def from_json(cls, d):
        a=cls.__new__(cls); a.name=d.get('name',''); a.x=d.get('x',0); a.y=d.get('y',0)
        a.radius=d.get('radius',0); a.height=d.get('height',0)
        a.pitch_variance=d.get('pitch_variance',0); a.volume_variance=d.get('volume_variance',0)
        a.volume=d.get('volume',0); a.sounds=d.get('sounds',[]); a.unused_82=0
        a.base_time=d.get('base_time',0); a.base_time_deviation=d.get('base_time_deviation',0)
        a.appearance_schedule=d.get('appearance_schedule',0); a.flags=d.get('flags',0)
        a.unused_94=bytes(64)
        return a


# ─────────────────────────────────────────────────────────────────────────────
# Variables  (M4)
# ─────────────────────────────────────────────────────────────────────────────
class AreVariable:
    """
    84 bytes. var_type bitfield: bit0=int bit1=float bit2=scriptname
              bit3=resref bit4=strref bit5=dword.
    Engine only reads/writes INT; all fields stored for round-trip fidelity.
    double_value at 0x002c is IEEE-754 64-bit; script_name at 0x0034 is 32-byte
    char array (not a resref).
    """
    __slots__=['name','var_type','resource_type','dword_value','int_value','double_value','script_name']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= VARIABLE_SIZE
        v=cls.__new__(cls)
        v.name=_str32(data[0x00:0x20]); v.var_type=struct.unpack_from('<H',data,0x20)[0]
        v.resource_type=struct.unpack_from('<H',data,0x22)[0]
        v.dword_value=struct.unpack_from('<I',data,0x24)[0]; v.int_value=struct.unpack_from('<i',data,0x28)[0]
        v.double_value=struct.unpack_from('<d',data,0x2c)[0]; v.script_name=_str32(data[0x34:0x54])
        return v

    def to_bytes(self):
        buf=bytearray(VARIABLE_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.var_type); struct.pack_into('<H',buf,0x22,self.resource_type)
        struct.pack_into('<I',buf,0x24,self.dword_value); struct.pack_into('<i',buf,0x28,self.int_value)
        struct.pack_into('<d',buf,0x2c,self.double_value); buf[0x34:0x54]=_str32_encode(self.script_name)
        return bytes(buf)

    def to_json(self):
        d={'name':self.name,'var_type':self.var_type,'resource_type':self.resource_type,
           'dword_value':self.dword_value,'int_value':self.int_value,
           'double_value':self.double_value,'script_name':self.script_name}
        return _sparse(d)

    @classmethod
    def from_json(cls, d):
        v=cls.__new__(cls); v.name=d.get('name',''); v.var_type=d.get('var_type',1)
        v.resource_type=d.get('resource_type',0); v.dword_value=d.get('dword_value',0)
        v.int_value=d.get('int_value',0); v.double_value=d.get('double_value',0.0)
        v.script_name=d.get('script_name','')
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Doors  (M4)
# ─────────────────────────────────────────────────────────────────────────────
class AreDoor:
    """
    200 bytes. Four vertex sets drawn from the shared global pool:
      vertices_open / vertices_closed — door polygon outline
      impeded_open  / impeded_closed  — search-map cell coords blocked
    All four inlined as [[x,y],...] in JSON; AreFile rebuilds the pool.

    door_id (0x0020): 8-byte char array linking to WED (not a resref).
    approach_points (0x0090): two word-pairs [[x0,y0],[x1,y1]].
    travel_trigger_name (0x009c): 24-byte char array.
    bbox_open / bbox_closed (0x0038 / 0x0040): 4 words each [l,t,r,b].

    IESDP field layout for vertex index/count pairs:
      0x002c first_vertex_open (dword)    0x0030 count_open (word)
      0x0032 count_closed (word)          0x0034 first_vertex_closed (dword)
      0x0048 first_impeded_open (dword)   0x004c count_impeded_open (word)
      0x004e count_impeded_closed (word)  0x0050 first_impeded_closed (dword)
    """
    __slots__=['name','door_id','flags','bbox_open','bbox_closed',
               'hit_points','armor_class','open_sound','close_sound','cursor_index',
               'trap_detection_difficulty','trap_removal_difficulty',
               'is_trapped','trap_detected','trap_launch_x','trap_launch_y',
               'key_item','door_script','detection_difficulty','lock_difficulty',
               'approach_points','lockpick_string','travel_trigger_name',
               'dialog_speaker_name','dialog_resref','unknown_c0',
               'vertices_open','vertices_closed','impeded_open','impeded_closed']

    @classmethod
    def from_bytes(cls, data, vertex_pool,
                   first_vi_open, count_vi_open,
                   first_vi_closed, count_vi_closed,
                   first_imp_open, count_imp_open,
                   first_imp_closed, count_imp_closed):
        assert len(data) >= DOOR_SIZE
        d=cls.__new__(cls)
        d.name=_str32(data[0x00:0x20]); d.door_id=data[0x20:0x28].rstrip(b'\x00').decode('latin-1')
        d.flags=struct.unpack_from('<I',data,0x28)[0]
        d.bbox_open=list(struct.unpack_from('<4H',data,0x38)); d.bbox_closed=list(struct.unpack_from('<4H',data,0x40))
        d.hit_points=struct.unpack_from('<H',data,0x54)[0]; d.armor_class=struct.unpack_from('<H',data,0x56)[0]
        d.open_sound=_resref(data[0x58:0x60]); d.close_sound=_resref(data[0x60:0x68])
        d.cursor_index=struct.unpack_from('<I',data,0x68)[0]
        d.trap_detection_difficulty=struct.unpack_from('<H',data,0x6c)[0]
        d.trap_removal_difficulty=struct.unpack_from('<H',data,0x6e)[0]
        d.is_trapped=struct.unpack_from('<H',data,0x70)[0]; d.trap_detected=struct.unpack_from('<H',data,0x72)[0]
        d.trap_launch_x=struct.unpack_from('<H',data,0x74)[0]; d.trap_launch_y=struct.unpack_from('<H',data,0x76)[0]
        d.key_item=_resref(data[0x78:0x80]); d.door_script=_resref(data[0x80:0x88])
        d.detection_difficulty=struct.unpack_from('<I',data,0x88)[0]
        d.lock_difficulty=struct.unpack_from('<I',data,0x8c)[0]
        pts=struct.unpack_from('<4H',data,0x90)
        d.approach_points=[[pts[0],pts[1]],[pts[2],pts[3]]]
        d.lockpick_string=struct.unpack_from('<I',data,0x98)[0]
        d.travel_trigger_name=data[0x9c:0xb4].rstrip(b'\x00').decode('latin-1')
        d.dialog_speaker_name=struct.unpack_from('<I',data,0xb4)[0]
        d.dialog_resref=_resref(data[0xb8:0xc0]); d.unknown_c0=bytes(data[0xc0:0xc8])
        d.vertices_open  =_verts_from_pool(vertex_pool,first_vi_open,  count_vi_open)
        d.vertices_closed=_verts_from_pool(vertex_pool,first_vi_closed,count_vi_closed)
        d.impeded_open   =_verts_from_pool(vertex_pool,first_imp_open, count_imp_open)
        d.impeded_closed =_verts_from_pool(vertex_pool,first_imp_closed,count_imp_closed)
        return d

    def to_bytes(self, first_vi_open, first_vi_closed, first_imp_open, first_imp_closed):
        buf=bytearray(DOOR_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        buf[0x20:0x28]=self.door_id.encode('latin-1')[:8].ljust(8,b'\x00')
        struct.pack_into('<I',buf,0x28,self.flags)
        struct.pack_into('<I',buf,0x2c,first_vi_open)
        struct.pack_into('<H',buf,0x30,len(self.vertices_open))
        struct.pack_into('<H',buf,0x32,len(self.vertices_closed))
        struct.pack_into('<I',buf,0x34,first_vi_closed)
        struct.pack_into('<4H',buf,0x38,*self.bbox_open)
        struct.pack_into('<4H',buf,0x40,*self.bbox_closed)
        struct.pack_into('<I',buf,0x48,first_imp_open)
        struct.pack_into('<H',buf,0x4c,len(self.impeded_open))
        struct.pack_into('<H',buf,0x4e,len(self.impeded_closed))
        struct.pack_into('<I',buf,0x50,first_imp_closed)
        struct.pack_into('<H',buf,0x54,self.hit_points); struct.pack_into('<H',buf,0x56,self.armor_class)
        buf[0x58:0x60]=_resref_encode(self.open_sound); buf[0x60:0x68]=_resref_encode(self.close_sound)
        struct.pack_into('<I',buf,0x68,self.cursor_index)
        struct.pack_into('<H',buf,0x6c,self.trap_detection_difficulty)
        struct.pack_into('<H',buf,0x6e,self.trap_removal_difficulty)
        struct.pack_into('<H',buf,0x70,self.is_trapped); struct.pack_into('<H',buf,0x72,self.trap_detected)
        struct.pack_into('<H',buf,0x74,self.trap_launch_x); struct.pack_into('<H',buf,0x76,self.trap_launch_y)
        buf[0x78:0x80]=_resref_encode(self.key_item); buf[0x80:0x88]=_resref_encode(self.door_script)
        struct.pack_into('<I',buf,0x88,self.detection_difficulty); struct.pack_into('<I',buf,0x8c,self.lock_difficulty)
        p0=self.approach_points[0] if len(self.approach_points)>0 else [0,0]
        p1=self.approach_points[1] if len(self.approach_points)>1 else [0,0]
        struct.pack_into('<4H',buf,0x90,p0[0],p0[1],p1[0],p1[1])
        struct.pack_into('<I',buf,0x98,self.lockpick_string)
        buf[0x9c:0xb4]=_strn_encode(self.travel_trigger_name,24)
        struct.pack_into('<I',buf,0xb4,self.dialog_speaker_name)
        buf[0xb8:0xc0]=_resref_encode(self.dialog_resref); buf[0xc0:0xc8]=self.unknown_c0[:8]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'door_id':self.door_id,'flags':self.flags,
            'bbox_open':self.bbox_open,'bbox_closed':self.bbox_closed,
            'hit_points':self.hit_points,'armor_class':self.armor_class,
            'open_sound':self.open_sound,'close_sound':self.close_sound,'cursor_index':self.cursor_index,
            'trap_detection_difficulty':self.trap_detection_difficulty,
            'trap_removal_difficulty':self.trap_removal_difficulty,
            'is_trapped':self.is_trapped,'trap_detected':self.trap_detected,
            'trap_launch_x':self.trap_launch_x,'trap_launch_y':self.trap_launch_y,
            'key_item':self.key_item,'door_script':self.door_script,
            'detection_difficulty':self.detection_difficulty,'lock_difficulty':self.lock_difficulty,
            'approach_points':self.approach_points,'lockpick_string':self.lockpick_string,
            'travel_trigger_name':self.travel_trigger_name,'dialog_speaker_name':self.dialog_speaker_name,
            'dialog_resref':self.dialog_resref,
            'unknown_c0':self.unknown_c0.hex() if any(self.unknown_c0) else None,
            'vertices_open':self.vertices_open,'vertices_closed':self.vertices_closed,
            'impeded_open':self.impeded_open,'impeded_closed':self.impeded_closed})

    @classmethod
    def from_json(cls, d):
        door=cls.__new__(cls); door.name=d.get('name',''); door.door_id=d.get('door_id','')
        door.flags=d.get('flags',0); door.bbox_open=d.get('bbox_open',[0,0,0,0]); door.bbox_closed=d.get('bbox_closed',[0,0,0,0])
        door.hit_points=d.get('hit_points',0); door.armor_class=d.get('armor_class',0)
        door.open_sound=d.get('open_sound',''); door.close_sound=d.get('close_sound','')
        door.cursor_index=d.get('cursor_index',0)
        door.trap_detection_difficulty=d.get('trap_detection_difficulty',0)
        door.trap_removal_difficulty=d.get('trap_removal_difficulty',0)
        door.is_trapped=d.get('is_trapped',0); door.trap_detected=d.get('trap_detected',0)
        door.trap_launch_x=d.get('trap_launch_x',0); door.trap_launch_y=d.get('trap_launch_y',0)
        door.key_item=d.get('key_item',''); door.door_script=d.get('door_script','')
        door.detection_difficulty=d.get('detection_difficulty',0)
        door.lock_difficulty=d.get('lock_difficulty',0)
        door.approach_points=d.get('approach_points',[[0,0],[0,0]])
        door.lockpick_string=d.get('lockpick_string',0)
        door.travel_trigger_name=d.get('travel_trigger_name','')
        door.dialog_speaker_name=d.get('dialog_speaker_name',0)
        door.dialog_resref=d.get('dialog_resref','')
        uc=d.get('unknown_c0'); door.unknown_c0=bytes.fromhex(uc) if uc else bytes(8)
        door.vertices_open  =d.get('vertices_open',[])
        door.vertices_closed=d.get('vertices_closed',[])
        door.impeded_open   =d.get('impeded_open',[])
        door.impeded_closed =d.get('impeded_closed',[])
        return door


# ─────────────────────────────────────────────────────────────────────────────
# AreFile
# ─────────────────────────────────────────────────────────────────────────────
class AreFile:
    """
    ARE V1.0 file container.

    Vertex pool layout (rebuilt on every to_bytes):
      region[0..n] vertices | container[0..n] vertices |
      door[0] verts_open | door[0] verts_closed | door[0] impeded_open | door[0] impeded_closed |
      door[1] ... | ...

    Item pool: rebuilt from containers in order.

    Typed sections complete through M4:
      actors, regions, spawn_points, entrances, containers, ambients, variables, doors

    Raw blobs pending M5:
      _raw_animations, _raw_automap_notes, _raw_tiled_objects,
      _raw_projectile_traps, _raw_song_entries, _raw_rest_interruptions
    """

    def __init__(self):
        self.header: Optional[AreHeader] = None
        self.actors:       List[AreActor]      = []
        self.regions:      List[AreRegion]     = []
        self.spawn_points: List[AreSpawnPoint] = []
        self.entrances:    List[AreEntrance]   = []
        self.containers:   List[AreContainer]  = []
        self.ambients:     List[AreAmbient]    = []
        self.variables:    List[AreVariable]   = []
        self.doors:        List[AreDoor]       = []
        self._raw_explored_bitmask:   bytes = b''
        self._raw_animations:         bytes = b''
        self._raw_automap_notes:      bytes = b''
        self._raw_tiled_objects:      bytes = b''
        self._raw_projectile_traps:   bytes = b''
        self._raw_song_entries:       bytes = b''
        self._raw_rest_interruptions: bytes = b''

    # ── pool builders ─────────────────────────────────────────────────────────

    def _build_vertex_pool(self):
        """Returns (pool_bytes, region_vis, container_vis, door_vis_4tuples)."""
        pool = bytearray()

        def _append(verts):
            idx = len(pool) // VERTEX_SIZE
            for vx, vy in verts:
                pool.extend(struct.pack('<HH', vx, vy))
            return idx

        region_vis    = [_append(r.vertices)  for r in self.regions]
        container_vis = [_append(c.vertices)  for c in self.containers]
        # Each door contributes 4 sets: open, closed, imp_open, imp_closed
        door_vis = []
        for door in self.doors:
            vo  = _append(door.vertices_open)
            vc  = _append(door.vertices_closed)
            imo = _append(door.impeded_open)
            imc = _append(door.impeded_closed)
            door_vis.append((vo, vc, imo, imc))

        return bytes(pool), region_vis, container_vis, door_vis

    def _build_item_pool(self):
        """Returns (pool_bytes, first_item_index_per_container)."""
        pool = bytearray()
        indices = []
        for cont in self.containers:
            indices.append(len(pool) // ITEM_SIZE)
            for item in cont.items:
                pool.extend(item.to_bytes())
        return bytes(pool), indices

    # ── from_bytes ────────────────────────────────────────────────────────────

    @classmethod
    def from_bytes(cls, data: bytes) -> 'AreFile':
        af = cls()
        af.header = AreHeader.from_bytes(data)
        h = af.header

        vertex_pool = b''
        if h.vertices_count > 0 and h.vertices_offset > 0:
            vertex_pool = bytes(data[h.vertices_offset : h.vertices_offset + h.vertices_count * VERTEX_SIZE])

        item_pool = b''
        if h.items_count > 0 and h.items_offset > 0:
            item_pool = bytes(data[h.items_offset : h.items_offset + h.items_count * ITEM_SIZE])

        for i in range(h.actors_count):
            s = h.actors_offset + i * ACTOR_SIZE
            af.actors.append(AreActor.from_bytes(data[s:s+ACTOR_SIZE], data))

        for i in range(h.regions_count):
            s = h.regions_offset + i * REGION_SIZE
            rec = data[s:s+REGION_SIZE]
            first_vi = struct.unpack_from('<I', rec, 0x2c)[0]
            af.regions.append(AreRegion.from_bytes(rec, vertex_pool, first_vi))

        for i in range(h.spawn_points_count):
            s = h.spawn_points_offset + i * SPAWN_POINT_SIZE
            af.spawn_points.append(AreSpawnPoint.from_bytes(data[s:s+SPAWN_POINT_SIZE]))

        for i in range(h.entrances_count):
            s = h.entrances_offset + i * ENTRANCE_SIZE
            af.entrances.append(AreEntrance.from_bytes(data[s:s+ENTRANCE_SIZE]))

        for i in range(h.containers_count):
            s = h.containers_offset + i * CONTAINER_SIZE
            rec = data[s:s+CONTAINER_SIZE]
            fii = struct.unpack_from('<I', rec, 0x40)[0]
            fvi = struct.unpack_from('<I', rec, 0x50)[0]
            af.containers.append(AreContainer.from_bytes(rec, item_pool, fii, vertex_pool, fvi))

        for i in range(h.ambients_count):
            s = h.ambients_offset + i * AMBIENT_SIZE
            af.ambients.append(AreAmbient.from_bytes(data[s:s+AMBIENT_SIZE]))

        for i in range(h.variables_count):
            s = h.variables_offset + i * VARIABLE_SIZE
            af.variables.append(AreVariable.from_bytes(data[s:s+VARIABLE_SIZE]))

        for i in range(h.doors_count):
            s = h.doors_offset + i * DOOR_SIZE
            rec = data[s:s+DOOR_SIZE]
            fvo  = struct.unpack_from('<I', rec, 0x2c)[0]
            cvo  = struct.unpack_from('<H', rec, 0x30)[0]
            cvc  = struct.unpack_from('<H', rec, 0x32)[0]
            fvc  = struct.unpack_from('<I', rec, 0x34)[0]
            fimo = struct.unpack_from('<I', rec, 0x48)[0]
            cimo = struct.unpack_from('<H', rec, 0x4c)[0]
            cimc = struct.unpack_from('<H', rec, 0x4e)[0]
            fimc = struct.unpack_from('<I', rec, 0x50)[0]
            af.doors.append(AreDoor.from_bytes(rec, vertex_pool,
                                               fvo, cvo, fvc, cvc, fimo, cimo, fimc, cimc))

        def _raw(off, count, size):
            return bytes(data[off:off+count*size]) if count > 0 and off > 0 else b''

        if h.explored_bitmask_size > 0 and h.explored_bitmask_offset > 0:
            af._raw_explored_bitmask = bytes(data[h.explored_bitmask_offset:
                                                   h.explored_bitmask_offset+h.explored_bitmask_size])
        af._raw_animations    = _raw(h.animations_offset,    h.animations_count,    ANIMATION_SIZE)
        af._raw_tiled_objects = _raw(h.tiled_objects_offset, h.tiled_objects_count, TILED_OBJECT_SIZE)
        if h.song_entries_offset > 0:
            af._raw_song_entries = bytes(data[h.song_entries_offset:h.song_entries_offset+SONG_ENTRIES_SIZE])
        if h.rest_interruptions_offset > 0:
            af._raw_rest_interruptions = bytes(data[h.rest_interruptions_offset:
                                                     h.rest_interruptions_offset+REST_INTERRUPTION_SIZE])
        is_pst = (h.field_c4 == 0xFFFFFFFF)
        automap_off   = h.field_c8 if is_pst else h.field_c4
        automap_count = h.field_cc if is_pst else h.field_c8
        proj_off      = 0 if is_pst else h.field_cc
        note_size = AUTOMAP_NOTE_PST_SIZE if is_pst else AUTOMAP_NOTE_SIZE
        af._raw_automap_notes = _raw(automap_off, automap_count, note_size)
        af._raw_projectile_traps = _raw(proj_off, h.projectile_traps_count, PROJECTILE_TRAP_SIZE)
        return af

    @classmethod
    def from_file(cls, path: str) -> 'AreFile':
        with open(path, 'rb') as f:
            return cls.from_bytes(f.read())

    # ── to_bytes ──────────────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        h = self.header

        vertex_pool, region_vis, container_vis, door_vis = self._build_vertex_pool()
        item_pool,   container_iis                       = self._build_item_pool()

        vert_count  = len(vertex_pool) // VERTEX_SIZE
        items_count = len(item_pool)   // ITEM_SIZE

        # ── layout pass ───────────────────────────────────────────────────────
        pos = HEADER_SIZE

        def _place_blobs(blobs):
            nonlocal pos
            total = sum(len(b) for b in blobs)
            if total == 0: return 0
            off = pos; pos += total; return off

        def _place_raw(raw):
            nonlocal pos
            if not raw: return 0
            off = pos; pos += len(raw); return off

        # Actors: serialise twice (correct CRE offsets unknown until end)
        actor_blobs_tmp = [a.to_bytes(0) for a in self.actors]
        actors_off  = _place_blobs(actor_blobs_tmp)
        regions_off = _place_blobs([r.to_bytes(0) for r in self.regions])
        sp_off      = _place_blobs([s.to_bytes()  for s in self.spawn_points])
        ent_off     = _place_blobs([e.to_bytes()  for e in self.entrances])
        cont_off    = _place_blobs([c.to_bytes(0, 0) for c in self.containers])
        items_off   = _place_raw(item_pool)
        vert_off    = _place_raw(vertex_pool)
        amb_off     = _place_blobs([a.to_bytes() for a in self.ambients])
        var_off     = _place_blobs([v.to_bytes() for v in self.variables])

        expl_off = _place_raw(self._raw_explored_bitmask)

        doors_off = _place_blobs([d.to_bytes(0,0,0,0) for d in self.doors])

        anim_off  = _place_raw(self._raw_animations)
        tiled_off = _place_raw(self._raw_tiled_objects)

        song_off = 0
        if self._raw_song_entries:
            song_off = pos; pos += SONG_ENTRIES_SIZE
        rest_off = 0
        if self._raw_rest_interruptions:
            rest_off = pos; pos += REST_INTERRUPTION_SIZE

        is_pst = (h.field_c4 == 0xFFFFFFFF)
        note_size  = AUTOMAP_NOTE_PST_SIZE if is_pst else AUTOMAP_NOTE_SIZE
        note_count = len(self._raw_automap_notes) // note_size if self._raw_automap_notes else 0
        automap_off = 0
        if note_count > 0:
            automap_off = pos; pos += note_count * note_size
        proj_count = len(self._raw_projectile_traps) // PROJECTILE_TRAP_SIZE if self._raw_projectile_traps else 0
        proj_off2 = 0
        if proj_count > 0:
            proj_off2 = pos; pos += proj_count * PROJECTILE_TRAP_SIZE

        # Embedded CREs at end
        cre_offsets = []
        for actor in self.actors:
            if actor.embedded_cre:
                cre_offsets.append(pos); pos += len(actor.embedded_cre)
            else:
                cre_offsets.append(0)

        # ── assemble ──────────────────────────────────────────────────────────
        buf = bytearray(pos)

        if is_pst:
            fc4, fc8, fcc = 0xFFFFFFFF, automap_off, note_count
        else:
            fc4, fc8, fcc = automap_off, note_count, proj_off2

        offsets = {
            'actors_offset': actors_off,   'actors_count': len(self.actors),
            'regions_offset': regions_off, 'regions_count': len(self.regions),
            'spawn_points_offset': sp_off, 'spawn_points_count': len(self.spawn_points),
            'entrances_offset': ent_off,   'entrances_count': len(self.entrances),
            'containers_offset': cont_off, 'containers_count': len(self.containers),
            'items_offset': items_off,     'items_count': items_count,
            'vertices_offset': vert_off,   'vertices_count': vert_count,
            'ambients_offset': amb_off,    'ambients_count': len(self.ambients),
            'variables_offset': var_off,   'variables_count': len(self.variables),
            'tiled_object_flags_offset': 0,'tiled_object_flags_count': 0,
            'explored_bitmask_offset': expl_off,
            'explored_bitmask_size': len(self._raw_explored_bitmask),
            'doors_offset': doors_off,     'doors_count': len(self.doors),
            'animations_offset': anim_off, 'animations_count': len(self._raw_animations)//ANIMATION_SIZE,
            'tiled_objects_offset': tiled_off,
            'tiled_objects_count': len(self._raw_tiled_objects)//TILED_OBJECT_SIZE,
            'song_entries_offset': song_off,
            'rest_interruptions_offset': rest_off,
            'projectile_traps_count': proj_count,
        }
        new_hdr = AreHeader.from_json(h.to_json(), offsets)
        new_hdr.field_c4  = fc4
        new_hdr.field_c8  = fc8
        new_hdr.field_cc  = fcc
        new_hdr.unused_e4 = h.unused_e4
        buf[0:HEADER_SIZE] = new_hdr.to_bytes()

        def _write(off, raw):
            if off and raw: buf[off:off+len(raw)] = raw

        def _write_blobs(off, blobs):
            if not off: return
            p = off
            for b in blobs:
                buf[p:p+len(b)] = b; p += len(b)

        # Re-serialise actors with correct CRE offsets
        actor_blobs = [self.actors[i].to_bytes(cre_offsets[i]) for i in range(len(self.actors))]
        _write_blobs(actors_off, actor_blobs)

        # Regions with correct vertex indices
        region_blobs = [self.regions[i].to_bytes(region_vis[i]) for i in range(len(self.regions))]
        _write_blobs(regions_off, region_blobs)

        _write_blobs(sp_off,  [s.to_bytes() for s in self.spawn_points])
        _write_blobs(ent_off, [e.to_bytes() for e in self.entrances])

        # Containers with correct item + vertex indices
        cont_blobs = [self.containers[i].to_bytes(container_iis[i], container_vis[i])
                      for i in range(len(self.containers))]
        _write_blobs(cont_off, cont_blobs)

        _write(items_off, item_pool)
        _write(vert_off,  vertex_pool)

        _write_blobs(amb_off, [a.to_bytes() for a in self.ambients])
        _write_blobs(var_off, [v.to_bytes() for v in self.variables])

        # Doors with correct vertex indices
        door_blobs = [self.doors[i].to_bytes(*door_vis[i]) for i in range(len(self.doors))]
        _write_blobs(doors_off, door_blobs)

        _write(expl_off,    self._raw_explored_bitmask)
        _write(anim_off,    self._raw_animations)
        _write(tiled_off,   self._raw_tiled_objects)
        _write(song_off,    self._raw_song_entries)
        _write(rest_off,    self._raw_rest_interruptions)
        _write(automap_off, self._raw_automap_notes)
        _write(proj_off2,   self._raw_projectile_traps)

        for i, actor in enumerate(self.actors):
            if actor.embedded_cre and cre_offsets[i]:
                o = cre_offsets[i]; buf[o:o+len(actor.embedded_cre)] = actor.embedded_cre

        return bytes(buf)

    def to_file(self, path: str) -> None:
        with open(path, 'wb') as f:
            f.write(self.to_bytes())

    # ── JSON ──────────────────────────────────────────────────────────────────

    def to_json(self) -> dict:
        d = {
            'header':       self.header.to_json(),
            'actors':       [a.to_json()  for a in self.actors],
            'regions':      [r.to_json()  for r in self.regions],
            'spawn_points': [s.to_json()  for s in self.spawn_points],
            'entrances':    [e.to_json()  for e in self.entrances],
            'containers':   [c.to_json()  for c in self.containers],
            'ambients':     [a.to_json()  for a in self.ambients],
            'variables':    [v.to_json()  for v in self.variables],
            'doors':        [dr.to_json() for dr in self.doors],
        }
        for key, raw in [
            ('_raw_explored_bitmask',   self._raw_explored_bitmask),
            ('_raw_animations',         self._raw_animations),
            ('_raw_automap_notes',      self._raw_automap_notes),
            ('_raw_tiled_objects',      self._raw_tiled_objects),
            ('_raw_projectile_traps',   self._raw_projectile_traps),
            ('_raw_song_entries',       self._raw_song_entries),
            ('_raw_rest_interruptions', self._raw_rest_interruptions),
        ]:
            if raw: d[key] = raw.hex()
        return d

    @classmethod
    def from_json(cls, d: dict) -> 'AreFile':
        af = cls()
        af.actors       = [AreActor.from_json(a)      for a in d.get('actors', [])]
        af.regions      = [AreRegion.from_json(r)     for r in d.get('regions', [])]
        af.spawn_points = [AreSpawnPoint.from_json(s) for s in d.get('spawn_points', [])]
        af.entrances    = [AreEntrance.from_json(e)   for e in d.get('entrances', [])]
        af.containers   = [AreContainer.from_json(c)  for c in d.get('containers', [])]
        af.ambients     = [AreAmbient.from_json(a)    for a in d.get('ambients', [])]
        af.variables    = [AreVariable.from_json(v)   for v in d.get('variables', [])]
        af.doors        = [AreDoor.from_json(dr)      for dr in d.get('doors', [])]

        def _hex(k): return bytes.fromhex(d[k]) if k in d else b''
        af._raw_explored_bitmask   = _hex('_raw_explored_bitmask')
        af._raw_animations         = _hex('_raw_animations')
        af._raw_automap_notes      = _hex('_raw_automap_notes')
        af._raw_tiled_objects      = _hex('_raw_tiled_objects')
        af._raw_projectile_traps   = _hex('_raw_projectile_traps')
        af._raw_song_entries       = _hex('_raw_song_entries')
        af._raw_rest_interruptions = _hex('_raw_rest_interruptions')

        # Compute layout to fill header offsets
        vertex_pool, _, _, _ = af._build_vertex_pool()
        item_pool,   _       = af._build_item_pool()
        vert_count  = len(vertex_pool) // VERTEX_SIZE
        items_count = len(item_pool)   // ITEM_SIZE

        pos = HEADER_SIZE
        def _lay(count, size):
            nonlocal pos
            if not count: return 0
            off = pos; pos += count * size; return off
        def _lay_raw(raw, size):
            return _lay(len(raw)//size if raw else 0, size)

        actors_off  = _lay(len(af.actors),       ACTOR_SIZE)
        regions_off = _lay(len(af.regions),      REGION_SIZE)
        sp_off      = _lay(len(af.spawn_points), SPAWN_POINT_SIZE)
        ent_off     = _lay(len(af.entrances),    ENTRANCE_SIZE)
        cont_off    = _lay(len(af.containers),   CONTAINER_SIZE)
        items_off   = _lay(items_count,          ITEM_SIZE)
        vert_off    = _lay(vert_count,           VERTEX_SIZE)
        amb_off     = _lay(len(af.ambients),     AMBIENT_SIZE)
        var_off     = _lay(len(af.variables),    VARIABLE_SIZE)
        expl_off    = 0
        if af._raw_explored_bitmask:
            expl_off = pos; pos += len(af._raw_explored_bitmask)
        doors_off   = _lay(len(af.doors),        DOOR_SIZE)
        anim_off    = _lay_raw(af._raw_animations,    ANIMATION_SIZE)
        tiled_off   = _lay_raw(af._raw_tiled_objects, TILED_OBJECT_SIZE)
        song_off = 0
        if af._raw_song_entries:
            song_off = pos; pos += SONG_ENTRIES_SIZE
        rest_off = 0
        if af._raw_rest_interruptions:
            rest_off = pos; pos += REST_INTERRUPTION_SIZE

        hj = d.get('header', {})
        is_pst = (hj.get('field_c4', 0) == 0xFFFFFFFF)
        note_size  = AUTOMAP_NOTE_PST_SIZE if is_pst else AUTOMAP_NOTE_SIZE
        note_count = len(af._raw_automap_notes)//note_size if af._raw_automap_notes else 0
        automap_off = 0
        if note_count > 0:
            automap_off = pos; pos += note_count * note_size
        proj_count = len(af._raw_projectile_traps)//PROJECTILE_TRAP_SIZE if af._raw_projectile_traps else 0
        proj_off = 0
        if proj_count > 0:
            proj_off = pos; pos += proj_count * PROJECTILE_TRAP_SIZE

        fc4 = 0xFFFFFFFF if is_pst else automap_off
        fc8 = automap_off if is_pst else note_count
        fcc = note_count  if is_pst else proj_off

        offsets = {
            'actors_offset': actors_off,   'actors_count': len(af.actors),
            'regions_offset': regions_off, 'regions_count': len(af.regions),
            'spawn_points_offset': sp_off, 'spawn_points_count': len(af.spawn_points),
            'entrances_offset': ent_off,   'entrances_count': len(af.entrances),
            'containers_offset': cont_off, 'containers_count': len(af.containers),
            'items_offset': items_off,     'items_count': items_count,
            'vertices_offset': vert_off,   'vertices_count': vert_count,
            'ambients_offset': amb_off,    'ambients_count': len(af.ambients),
            'variables_offset': var_off,   'variables_count': len(af.variables),
            'tiled_object_flags_offset': 0,'tiled_object_flags_count': 0,
            'explored_bitmask_offset': expl_off,
            'explored_bitmask_size': len(af._raw_explored_bitmask),
            'doors_offset': doors_off,     'doors_count': len(af.doors),
            'animations_offset': anim_off, 'animations_count': len(af._raw_animations)//ANIMATION_SIZE,
            'tiled_objects_offset': tiled_off,
            'tiled_objects_count': len(af._raw_tiled_objects)//TILED_OBJECT_SIZE,
            'song_entries_offset': song_off,
            'rest_interruptions_offset': rest_off,
            'projectile_traps_count': proj_count,
        }
        af.header = AreHeader.from_json(hj, offsets)
        af.header.field_c4 = fc4; af.header.field_c8 = fc8; af.header.field_cc = fcc
        return af

    # ── diagnostics ───────────────────────────────────────────────────────────

    def summary(self) -> str:
        h = self.header
        total_items = sum(len(c.items) for c in self.containers)
        return '\n'.join([
            f"ARE V1.0  WED={h.area_wed!r}  script={h.area_script!r}",
            f"  actors={len(self.actors)}  regions={len(self.regions)}  "
            f"spawn_points={len(self.spawn_points)}  entrances={len(self.entrances)}",
            f"  containers={len(self.containers)}  items={total_items}  "
            f"ambients={len(self.ambients)}  variables={len(self.variables)}",
            f"  doors={len(self.doors)}  animations={h.animations_count}  "
            f"tiled_objects={h.tiled_objects_count}  proj_traps={h.projectile_traps_count}",
            f"  explored_bitmask={h.explored_bitmask_size} bytes  "
            f"vertices(hdr)={h.vertices_count}",
            f"  north={h.north_resref!r}  east={h.east_resref!r}  "
            f"south={h.south_resref!r}  west={h.west_resref!r}",
        ])
