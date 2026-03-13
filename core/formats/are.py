"""
core/formats/are.py  — ARE V1.0 parser.
Milestones: [M1] Header [M2] Actors+Regions [M3] SpawnPoints+Entrances+Containers+Items
            [M4] Ambients+Variables+Doors
            [M5] Animations+AutomapNotes+TiledObjects+ProjectileTraps+SongEntries+RestInterruption
            [M6] round-trip tests
"""
import struct
from typing import List, Optional

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
            'explored_bitmask_offset': self.explored_bitmask_offset,
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
        struct.pack_into('<I',buf,0x88,embedded_cre_offset)
        struct.pack_into('<I',buf,0x8c,len(self.embedded_cre) if self.embedded_cre else 0)
        buf[0x90:0x110]=self.unused_90[:128]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'current_x':self.current_x,'current_y':self.current_y,
            'destination_x':self.destination_x,'destination_y':self.destination_y,
            'flags':self.flags,'has_been_spawned':self.has_been_spawned,
            'first_letter_cre':self.first_letter_cre,'unused_2f':self.unused_2f,
            'actor_animation':self.actor_animation,'actor_orientation':self.actor_orientation,
            'unused_36':self.unused_36,
            'removal_timer':self.removal_timer,
            'movement_restriction_distance':self.movement_restriction_distance,
            'movement_restriction_distance_to_object':self.movement_restriction_distance_to_object,
            'appearance_schedule':self.appearance_schedule,'num_times_talked_to':self.num_times_talked_to,
            'dialog':self.dialog,'script_override':self.script_override,
            'script_general':self.script_general,'script_class':self.script_class,
            'script_race':self.script_race,'script_default':self.script_default,
            'script_specific':self.script_specific,'cre_file':self.cre_file,
            'embedded_cre':self.embedded_cre.hex() if self.embedded_cre else None})

    @classmethod
    def from_json(cls, d):
        a=cls.__new__(cls); a.name=d.get('name','')
        a.current_x=d.get('current_x',0); a.current_y=d.get('current_y',0)
        a.destination_x=d.get('destination_x',0); a.destination_y=d.get('destination_y',0)
        a.flags=d.get('flags',1); a.has_been_spawned=d.get('has_been_spawned',0)
        a.first_letter_cre=d.get('first_letter_cre',0); a.unused_2f=d.get('unused_2f',0)
        a.actor_animation=d.get('actor_animation',0); a.actor_orientation=d.get('actor_orientation',0)
        a.unused_36=d.get('unused_36',0); a.removal_timer=d.get('removal_timer',0)
        a.movement_restriction_distance=d.get('movement_restriction_distance',0)
        a.movement_restriction_distance_to_object=d.get('movement_restriction_distance_to_object',0)
        a.appearance_schedule=d.get('appearance_schedule',0); a.num_times_talked_to=d.get('num_times_talked_to',0)
        a.dialog=d.get('dialog',''); a.script_override=d.get('script_override','')
        a.script_general=d.get('script_general',''); a.script_class=d.get('script_class','')
        a.script_race=d.get('script_race',''); a.script_default=d.get('script_default','')
        a.script_specific=d.get('script_specific',''); a.cre_file=d.get('cre_file','')
        a.cre_offset=0; a.cre_size=0; a.unused_90=bytes(128)
        ec=d.get('embedded_cre'); a.embedded_cre=bytes.fromhex(ec) if ec else None
        return a


# ─────────────────────────────────────────────────────────────────────────────
# Regions
# ─────────────────────────────────────────────────────────────────────────────
class AreRegion:
    """196 bytes. region_type: 0=proximity 1=info 2=travel."""
    __slots__=['name','region_type','bounding_box','trigger_value','cursor_index',
               'destination_area','destination_entrance','flags','info_string',
               'trap_detection_difficulty','trap_removal_difficulty','is_trapped','trap_detected',
               'trap_launch_x','trap_launch_y','key_item','region_script',
               'use_point_x','use_point_y','unknown_70','unused_78','journal_entry',
               'saved_loc_x','saved_loc_y','saved_loc_orientation',
               'area_point_name','travel_schedule','region_script_2','unknown_b0',
               'vertices']

    @classmethod
    def from_bytes(cls, data, vertex_pool, first_vi):
        assert len(data) >= REGION_SIZE
        r=cls.__new__(cls)
        r.name=_str32(data[0x00:0x20]); r.region_type=struct.unpack_from('<H',data,0x20)[0]
        r.bounding_box=list(struct.unpack_from('<4H',data,0x22))
        vertex_count=struct.unpack_from('<H',data,0x2a)[0]
        r.trigger_value=struct.unpack_from('<I',data,0x30)[0]; r.cursor_index=struct.unpack_from('<I',data,0x34)[0]
        r.destination_area=_resref(data[0x38:0x40]); r.destination_entrance=_resref(data[0x40:0x48])
        r.flags=struct.unpack_from('<I',data,0x48)[0]; r.info_string=struct.unpack_from('<I',data,0x4c)[0]
        r.trap_detection_difficulty=struct.unpack_from('<H',data,0x50)[0]
        r.trap_removal_difficulty=struct.unpack_from('<H',data,0x52)[0]
        r.is_trapped=struct.unpack_from('<H',data,0x54)[0]; r.trap_detected=struct.unpack_from('<H',data,0x56)[0]
        r.trap_launch_x=struct.unpack_from('<H',data,0x58)[0]; r.trap_launch_y=struct.unpack_from('<H',data,0x5a)[0]
        r.key_item=_resref(data[0x5c:0x64]); r.region_script=_resref(data[0x64:0x6c])
        r.use_point_x=struct.unpack_from('<H',data,0x6c)[0]; r.use_point_y=struct.unpack_from('<H',data,0x6e)[0]
        r.unknown_70=bytes(data[0x70:0x78]); r.unused_78=bytes(data[0x78:0x80]); r.journal_entry=struct.unpack_from('<I',data,0x80)[0]
        r.saved_loc_x=struct.unpack_from('<H',data,0x84)[0]; r.saved_loc_y=struct.unpack_from('<H',data,0x86)[0]
        r.saved_loc_orientation=struct.unpack_from('<H',data,0x88)[0]
        r.area_point_name=_resref(data[0x8a:0x92]); r.travel_schedule=struct.unpack_from('<I',data,0x92)[0]
        r.region_script_2=_resref(data[0x96:0x9e]); r.unknown_b0=bytes(data[0x9e:0xc4])
        r.vertices=_verts_from_pool(vertex_pool,first_vi,vertex_count)
        return r

    def to_bytes(self, first_vi):
        buf=bytearray(REGION_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name); struct.pack_into('<H',buf,0x20,self.region_type)
        struct.pack_into('<4H',buf,0x22,*self.bounding_box)
        struct.pack_into('<H',buf,0x2a,len(self.vertices))
        struct.pack_into('<I',buf,0x2c,first_vi)
        struct.pack_into('<I',buf,0x30,self.trigger_value); struct.pack_into('<I',buf,0x34,self.cursor_index)
        buf[0x38:0x40]=_resref_encode(self.destination_area); buf[0x40:0x48]=_resref_encode(self.destination_entrance)
        struct.pack_into('<I',buf,0x48,self.flags); struct.pack_into('<I',buf,0x4c,self.info_string)
        struct.pack_into('<H',buf,0x50,self.trap_detection_difficulty); struct.pack_into('<H',buf,0x52,self.trap_removal_difficulty)
        struct.pack_into('<H',buf,0x54,self.is_trapped); struct.pack_into('<H',buf,0x56,self.trap_detected)
        struct.pack_into('<H',buf,0x58,self.trap_launch_x); struct.pack_into('<H',buf,0x5a,self.trap_launch_y)
        buf[0x5c:0x64]=_resref_encode(self.key_item); buf[0x64:0x6c]=_resref_encode(self.region_script)
        struct.pack_into('<H',buf,0x6c,self.use_point_x); struct.pack_into('<H',buf,0x6e,self.use_point_y)
        buf[0x70:0x78]=self.unknown_70[:8]; buf[0x78:0x80]=self.unused_78[:8]; struct.pack_into('<I',buf,0x80,self.journal_entry)
        struct.pack_into('<H',buf,0x84,self.saved_loc_x); struct.pack_into('<H',buf,0x86,self.saved_loc_y)
        struct.pack_into('<H',buf,0x88,self.saved_loc_orientation)
        buf[0x8a:0x92]=_resref_encode(self.area_point_name); struct.pack_into('<I',buf,0x92,self.travel_schedule)
        buf[0x96:0x9e]=_resref_encode(self.region_script_2); buf[0x9e:0xc4]=self.unknown_b0[:38]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'region_type':self.region_type,'bounding_box':self.bounding_box,
            'trigger_value':self.trigger_value,'cursor_index':self.cursor_index,
            'destination_area':self.destination_area,'destination_entrance':self.destination_entrance,
            'flags':self.flags,'info_string':self.info_string,
            'trap_detection_difficulty':self.trap_detection_difficulty,
            'trap_removal_difficulty':self.trap_removal_difficulty,
            'is_trapped':self.is_trapped,'trap_detected':self.trap_detected,
            'trap_launch_x':self.trap_launch_x,'trap_launch_y':self.trap_launch_y,
            'key_item':self.key_item,'region_script':self.region_script,
            'use_point_x':self.use_point_x,'use_point_y':self.use_point_y,
            'unknown_70':self.unknown_70.hex() if any(self.unknown_70) else None,
            'unused_78':self.unused_78.hex() if any(self.unused_78) else None,
            'journal_entry':self.journal_entry,
            'saved_loc_x':self.saved_loc_x,'saved_loc_y':self.saved_loc_y,
            'saved_loc_orientation':self.saved_loc_orientation,
            'area_point_name':self.area_point_name,'travel_schedule':self.travel_schedule,
            'region_script_2':self.region_script_2,'vertices':self.vertices})

    @classmethod
    def from_json(cls, d):
        r=cls.__new__(cls); r.name=d.get('name',''); r.region_type=d.get('region_type',0)
        r.bounding_box=d.get('bounding_box',[0,0,0,0]); r.trigger_value=d.get('trigger_value',0)
        r.cursor_index=d.get('cursor_index',0); r.destination_area=d.get('destination_area','')
        r.destination_entrance=d.get('destination_entrance',''); r.flags=d.get('flags',0)
        r.info_string=d.get('info_string',0); r.trap_detection_difficulty=d.get('trap_detection_difficulty',0)
        r.trap_removal_difficulty=d.get('trap_removal_difficulty',0)
        r.is_trapped=d.get('is_trapped',0); r.trap_detected=d.get('trap_detected',0)
        r.trap_launch_x=d.get('trap_launch_x',0); r.trap_launch_y=d.get('trap_launch_y',0)
        r.key_item=d.get('key_item',''); r.region_script=d.get('region_script','')
        r.use_point_x=d.get('use_point_x',0); r.use_point_y=d.get('use_point_y',0)
        unk70=d.get('unknown_70'); r.unknown_70=bytes.fromhex(unk70) if unk70 else bytes(8)
        unu78=d.get('unused_78');  r.unused_78 =bytes.fromhex(unu78) if unu78 else bytes(8)
        r.journal_entry=d.get('journal_entry',0)
        r.saved_loc_x=d.get('saved_loc_x',0); r.saved_loc_y=d.get('saved_loc_y',0)
        r.saved_loc_orientation=d.get('saved_loc_orientation',0)
        r.area_point_name=d.get('area_point_name',''); r.travel_schedule=d.get('travel_schedule',0)
        r.region_script_2=d.get('region_script_2',''); r.unknown_b0=bytes(38)
        r.vertices=d.get('vertices',[])
        return r


# ─────────────────────────────────────────────────────────────────────────────
# Spawn Points
# ─────────────────────────────────────────────────────────────────────────────
class AreSpawnPoint:
    """200 bytes."""
    __slots__=['name','x','y','creature_resrefs','creature_count',
               'base_count','frequency','spawn_method','actor_removal_timer',
               'movement_restriction_distance','movement_restriction_to_object',
               'enabled','spawn_schedule','probability_day','probability_night',
               'unused_b4']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= SPAWN_POINT_SIZE
        s=cls.__new__(cls)
        s.name=_str32(data[0x00:0x20]); s.x=struct.unpack_from('<H',data,0x20)[0]; s.y=struct.unpack_from('<H',data,0x22)[0]
        s.creature_resrefs=[_resref(data[0x24+i*8:0x24+i*8+8]) for i in range(10)]
        s.creature_count=struct.unpack_from('<H',data,0x74)[0]; s.base_count=struct.unpack_from('<H',data,0x76)[0]
        s.frequency=struct.unpack_from('<H',data,0x78)[0]; s.spawn_method=struct.unpack_from('<H',data,0x7a)[0]
        s.actor_removal_timer=struct.unpack_from('<I',data,0x7c)[0]
        s.movement_restriction_distance=struct.unpack_from('<H',data,0x80)[0]
        s.movement_restriction_to_object=struct.unpack_from('<H',data,0x82)[0]
        s.enabled=struct.unpack_from('<H',data,0x84)[0]; s.unused_b4=bytes(data[0x86:0xb4]) # includes spawn_schedule area
        s.spawn_schedule=struct.unpack_from('<I',data,0x88)[0]
        s.probability_day=struct.unpack_from('<H',data,0x8c)[0]; s.probability_night=struct.unpack_from('<H',data,0x8e)[0]
        return s

    def to_bytes(self):
        buf=bytearray(SPAWN_POINT_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.x); struct.pack_into('<H',buf,0x22,self.y)
        refs=(list(self.creature_resrefs)+['']*10)[:10]
        for i in range(10): buf[0x24+i*8:0x24+i*8+8]=_resref_encode(refs[i])
        struct.pack_into('<H',buf,0x74,self.creature_count); struct.pack_into('<H',buf,0x76,self.base_count)
        struct.pack_into('<H',buf,0x78,self.frequency); struct.pack_into('<H',buf,0x7a,self.spawn_method)
        struct.pack_into('<I',buf,0x7c,self.actor_removal_timer)
        struct.pack_into('<H',buf,0x80,self.movement_restriction_distance)
        struct.pack_into('<H',buf,0x82,self.movement_restriction_to_object)
        struct.pack_into('<H',buf,0x84,self.enabled)
        buf[0x86:0xb4]=self.unused_b4[:46]
        struct.pack_into('<I',buf,0x88,self.spawn_schedule)
        struct.pack_into('<H',buf,0x8c,self.probability_day); struct.pack_into('<H',buf,0x8e,self.probability_night)
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'x':self.x,'y':self.y,
            'creature_resrefs':self.creature_resrefs,
            'creature_count':self.creature_count,'base_count':self.base_count,
            'frequency':self.frequency,'spawn_method':self.spawn_method,
            'actor_removal_timer':self.actor_removal_timer,
            'movement_restriction_distance':self.movement_restriction_distance,
            'movement_restriction_to_object':self.movement_restriction_to_object,
            'enabled':self.enabled,'spawn_schedule':self.spawn_schedule,
            'probability_day':self.probability_day,'probability_night':self.probability_night,
            'unused_b4':self.unused_b4.hex() if any(self.unused_b4) else None})

    @classmethod
    def from_json(cls, d):
        s=cls.__new__(cls); s.name=d.get('name',''); s.x=d.get('x',0); s.y=d.get('y',0)
        refs=d.get('creature_resrefs',[])
        s.creature_count=d.get('creature_count',0)
        s.creature_resrefs=(refs+['']*10)[:10]
        s.base_count=d.get('base_count',0); s.frequency=d.get('frequency',0)
        s.spawn_method=d.get('spawn_method',0); s.actor_removal_timer=d.get('actor_removal_timer',0)
        s.movement_restriction_distance=d.get('movement_restriction_distance',0)
        s.movement_restriction_to_object=d.get('movement_restriction_to_object',0)
        s.enabled=d.get('enabled',0); s.unused_b4=bytes(46)
        ub = d.get('unused_b4')
        s.unused_b4 = bytes.fromhex(ub) if ub else bytes(46)
        s.spawn_schedule=d.get('spawn_schedule',0)
        s.probability_day=d.get('probability_day',0); s.probability_night=d.get('probability_night',0)
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
        e.name=_str32(data[0x00:0x20]); e.x=struct.unpack_from('<H',data,0x20)[0]; e.y=struct.unpack_from('<H',data,0x22)[0]
        e.orientation=struct.unpack_from('<H',data,0x24)[0]; e.unused_26=bytes(data[0x26:0x68])
        return e

    def to_bytes(self):
        buf=bytearray(ENTRANCE_SIZE)
        buf[0x00:0x20]=_str32_encode(self.name)
        struct.pack_into('<H',buf,0x20,self.x); struct.pack_into('<H',buf,0x22,self.y)
        struct.pack_into('<H',buf,0x24,self.orientation); buf[0x26:0x68]=self.unused_26[:66]
        return bytes(buf)

    def to_json(self):
        return _sparse({'name':self.name,'x':self.x,'y':self.y,'orientation':self.orientation,
            'unused_26':self.unused_26.hex() if any(self.unused_26) else None})

    @classmethod
    def from_json(cls, d):
        e=cls.__new__(cls); e.name=d.get('name',''); e.x=d.get('x',0); e.y=d.get('y',0)
        e.orientation=d.get('orientation',0)
        uu=d.get('unused_26'); e.unused_26=bytes.fromhex(uu) if uu else bytes(66)
        return e


# ─────────────────────────────────────────────────────────────────────────────
# Items
# ─────────────────────────────────────────────────────────────────────────────
class AreItem:
    """20 bytes."""
    # IESDP layout: resref(8) expiry(2) qty1(2) qty2(2) qty3(2) flags(4) = 20 bytes
    __slots__=['item_resref','expiry_time','quantity1','quantity2','quantity3','flags']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= ITEM_SIZE
        it=cls.__new__(cls)
        it.item_resref=_resref(data[0x00:0x08])
        it.expiry_time=struct.unpack_from('<H',data,0x08)[0]
        it.quantity1  =struct.unpack_from('<H',data,0x0a)[0]
        it.quantity2  =struct.unpack_from('<H',data,0x0c)[0]
        it.quantity3  =struct.unpack_from('<H',data,0x0e)[0]
        it.flags      =struct.unpack_from('<I',data,0x10)[0]
        return it

    def to_bytes(self):
        buf=bytearray(ITEM_SIZE)
        buf[0x00:0x08]=_resref_encode(self.item_resref)
        struct.pack_into('<H',buf,0x08,self.expiry_time)
        struct.pack_into('<H',buf,0x0a,self.quantity1)
        struct.pack_into('<H',buf,0x0c,self.quantity2)
        struct.pack_into('<H',buf,0x0e,self.quantity3)
        struct.pack_into('<I',buf,0x10,self.flags)
        return bytes(buf)

    def to_json(self):
        return _sparse({'item_resref':self.item_resref,'expiry_time':self.expiry_time,
            'quantity1':self.quantity1,'quantity2':self.quantity2,
            'quantity3':self.quantity3,'flags':self.flags})

    @classmethod
    def from_json(cls, d):
        it=cls.__new__(cls); it.item_resref=d.get('item_resref',''); it.expiry_time=d.get('expiry_time',0)
        it.quantity1=d.get('quantity1',0); it.quantity2=d.get('quantity2',0)
        it.quantity3=d.get('quantity3',0); it.flags=d.get('flags',0)
        return it


# ─────────────────────────────────────────────────────────────────────────────
# Containers
# ─────────────────────────────────────────────────────────────────────────────
class AreContainer:
    """192 bytes."""
    __slots__=['name','x','y','container_type','lock_difficulty','flags',
               'trap_detection_difficulty','trap_removal_difficulty','is_trapped','trap_detected',
               'trap_launch_x','trap_launch_y','bounding_box','trap_script',
               'trigger_range','owner','key_item','break_difficulty','lockpick_string',
               'unused_88','items','vertices']

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
# Ambients
# ─────────────────────────────────────────────────────────────────────────────
class AreAmbient:
    """212 bytes. Up to 10 sound slots."""
    __slots__=['name','x','y','radius','height','pitch_variance','volume_variance',
               'volume','sounds','_raw_sound_slots','unused_82','base_time','base_time_deviation',
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
        a._raw_sound_slots=bytes(data[0x30:0x80])
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
        if self._raw_sound_slots:
            buf[0x30:0x80]=self._raw_sound_slots[:80]
        else:
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
            'sounds':self.sounds,
            '_raw_sound_slots':self._raw_sound_slots.hex() if self._raw_sound_slots else None,
            'base_time':self.base_time,'base_time_deviation':self.base_time_deviation,
            'appearance_schedule':self.appearance_schedule,'flags':self.flags})

    @classmethod
    def from_json(cls, d):
        a=cls.__new__(cls); a.name=d.get('name',''); a.x=d.get('x',0); a.y=d.get('y',0)
        a.radius=d.get('radius',0); a.height=d.get('height',0)
        a.pitch_variance=d.get('pitch_variance',0); a.volume_variance=d.get('volume_variance',0)
        a.volume=d.get('volume',0); a.sounds=d.get('sounds',[])
        rss = d.get('_raw_sound_slots')
        a._raw_sound_slots = bytes.fromhex(rss) if rss else None
        a.unused_82=0
        a.base_time=d.get('base_time',0); a.base_time_deviation=d.get('base_time_deviation',0)
        a.appearance_schedule=d.get('appearance_schedule',0); a.flags=d.get('flags',0)
        a.unused_94=bytes(64)
        return a


# ─────────────────────────────────────────────────────────────────────────────
# Variables
# ─────────────────────────────────────────────────────────────────────────────
class AreVariable:
    """84 bytes."""
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
        return _sparse({'name':self.name,'var_type':self.var_type,'resource_type':self.resource_type,
           'dword_value':self.dword_value,'int_value':self.int_value,
           'double_value':self.double_value,'script_name':self.script_name})

    @classmethod
    def from_json(cls, d):
        v=cls.__new__(cls); v.name=d.get('name',''); v.var_type=d.get('var_type',1)
        v.resource_type=d.get('resource_type',0); v.dword_value=d.get('dword_value',0)
        v.int_value=d.get('int_value',0); v.double_value=d.get('double_value',0.0)
        v.script_name=d.get('script_name','')
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Doors
# ─────────────────────────────────────────────────────────────────────────────
class AreDoor:
    """200 bytes. Four vertex sets from the shared pool."""
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
# Animations  (M5)
# ─────────────────────────────────────────────────────────────────────────────
class AreAnimation:
    """76 bytes.
    flags (0x38): bit0 enabled, bit1 blended, bit2 not_light_source,
                  bit3 partial_anim, bit4 synchronized, bit5 random_start,
                  bit6 not_covered, bit7 background, bit8 allcycles,
                  bit9 once, bit10 paused.
    animation_bam2 is BG2-specific (twin / mirror-image BAM slot).
    """
    __slots__ = [
        'name', 'x', 'y', 'appearance_schedule',
        'animation_bam', 'animation_bam2',
        'flags', 'height', 'transparency', 'starting_frame',
        'looping_chance', 'skip_cycles', 'palette', 'unknown_4a',
    ]

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= ANIMATION_SIZE
        a = cls.__new__(cls)
        a.name                = _str32(data[0x00:0x20])
        a.x                   = struct.unpack_from('<H', data, 0x20)[0]
        a.y                   = struct.unpack_from('<H', data, 0x22)[0]
        a.appearance_schedule = struct.unpack_from('<I', data, 0x24)[0]
        a.animation_bam       = _resref(data[0x28:0x30])
        a.animation_bam2      = _resref(data[0x30:0x38])
        a.flags               = struct.unpack_from('<H', data, 0x38)[0]
        a.height              = struct.unpack_from('<H', data, 0x3a)[0]
        a.transparency        = struct.unpack_from('<H', data, 0x3c)[0]
        a.starting_frame      = struct.unpack_from('<H', data, 0x3e)[0]
        a.looping_chance      = data[0x40]
        a.skip_cycles         = data[0x41]
        a.palette             = _resref(data[0x42:0x4a])
        a.unknown_4a          = struct.unpack_from('<H', data, 0x4a)[0]
        return a

    def to_bytes(self):
        buf = bytearray(ANIMATION_SIZE)
        buf[0x00:0x20] = _str32_encode(self.name)
        struct.pack_into('<H', buf, 0x20, self.x)
        struct.pack_into('<H', buf, 0x22, self.y)
        struct.pack_into('<I', buf, 0x24, self.appearance_schedule)
        buf[0x28:0x30] = _resref_encode(self.animation_bam)
        buf[0x30:0x38] = _resref_encode(self.animation_bam2)
        struct.pack_into('<H', buf, 0x38, self.flags)
        struct.pack_into('<H', buf, 0x3a, self.height)
        struct.pack_into('<H', buf, 0x3c, self.transparency)
        struct.pack_into('<H', buf, 0x3e, self.starting_frame)
        buf[0x40] = self.looping_chance
        buf[0x41] = self.skip_cycles
        buf[0x42:0x4a] = _resref_encode(self.palette)
        struct.pack_into('<H', buf, 0x4a, self.unknown_4a)
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'name': self.name, 'x': self.x, 'y': self.y,
            'appearance_schedule': self.appearance_schedule,
            'animation_bam': self.animation_bam,
            'animation_bam2': self.animation_bam2,
            'flags': self.flags, 'height': self.height,
            'transparency': self.transparency,
            'starting_frame': self.starting_frame,
            'looping_chance': self.looping_chance,
            'skip_cycles': self.skip_cycles,
            'palette': self.palette,
            'unknown_4a': self.unknown_4a,
        })

    @classmethod
    def from_json(cls, d):
        a = cls.__new__(cls)
        a.name                = d.get('name', '')
        a.x                   = d.get('x', 0)
        a.y                   = d.get('y', 0)
        a.appearance_schedule = d.get('appearance_schedule', 0)
        a.animation_bam       = d.get('animation_bam', '')
        a.animation_bam2      = d.get('animation_bam2', '')
        a.flags               = d.get('flags', 0)
        a.height              = d.get('height', 0)
        a.transparency        = d.get('transparency', 0)
        a.starting_frame      = d.get('starting_frame', 0)
        a.looping_chance      = d.get('looping_chance', 0)
        a.skip_cycles         = d.get('skip_cycles', 0)
        a.palette             = d.get('palette', '')
        a.unknown_4a          = d.get('unknown_4a', 0)
        return a


# ─────────────────────────────────────────────────────────────────────────────
# Automap Notes  (M5)
# Non-PST only.  PST notes (0x214 bytes) are kept as _raw_pst_automap_notes.
# ─────────────────────────────────────────────────────────────────────────────
class AreAutomapNote:
    """52 bytes.
    colour: 0=grey 1=violet 2=green 3=orange 4=red 5=blue 6=darkblue 7=darkgreen.
    note_type: 0=user, 1=external.
    """
    __slots__ = ['x', 'y', 'text', 'colour', 'note_type', 'unknown_0c']

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= AUTOMAP_NOTE_SIZE
        n = cls.__new__(cls)
        n.x         = struct.unpack_from('<H', data, 0x00)[0]
        n.y         = struct.unpack_from('<H', data, 0x02)[0]
        n.text      = struct.unpack_from('<I', data, 0x04)[0]
        n.colour    = struct.unpack_from('<H', data, 0x08)[0]
        n.note_type = struct.unpack_from('<H', data, 0x0a)[0]
        n.unknown_0c = bytes(data[0x0c:0x34])
        return n

    def to_bytes(self):
        buf = bytearray(AUTOMAP_NOTE_SIZE)
        struct.pack_into('<H', buf, 0x00, self.x)
        struct.pack_into('<H', buf, 0x02, self.y)
        struct.pack_into('<I', buf, 0x04, self.text)
        struct.pack_into('<H', buf, 0x08, self.colour)
        struct.pack_into('<H', buf, 0x0a, self.note_type)
        buf[0x0c:0x34] = self.unknown_0c[:40]
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'x': self.x, 'y': self.y, 'text': self.text,
            'colour': self.colour, 'note_type': self.note_type,
        })

    @classmethod
    def from_json(cls, d):
        n = cls.__new__(cls)
        n.x         = d.get('x', 0)
        n.y         = d.get('y', 0)
        n.text      = d.get('text', 0)
        n.colour    = d.get('colour', 0)
        n.note_type = d.get('note_type', 0)
        n.unknown_0c = bytes(40)
        return n


# ─────────────────────────────────────────────────────────────────────────────
# Tiled Objects  (M5)
# ─────────────────────────────────────────────────────────────────────────────
class AreTiledObject:
    """108 bytes.
    tiled_object_id: 8-byte char array linking to WED tiled-cell entry.
    first_vertex_open / first_vertex_closed index into the tiled_object_flags
    pool (header 0x90/0x92), NOT the main vertex pool.  The pool itself is
    preserved verbatim as AreFile._raw_tiled_object_flags.
    """
    __slots__ = [
        'name', 'tiled_object_id', 'flags',
        'first_vertex_open', 'count_open',
        'count_closed', 'first_vertex_closed',
        'unknown_38',
    ]

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= TILED_OBJECT_SIZE
        t = cls.__new__(cls)
        t.name                = _str32(data[0x00:0x20])
        t.tiled_object_id     = data[0x20:0x28].rstrip(b'\x00').decode('latin-1')
        t.flags               = struct.unpack_from('<I', data, 0x28)[0]
        t.first_vertex_open   = struct.unpack_from('<I', data, 0x2c)[0]
        t.count_open          = struct.unpack_from('<H', data, 0x30)[0]
        t.count_closed        = struct.unpack_from('<H', data, 0x32)[0]
        t.first_vertex_closed = struct.unpack_from('<I', data, 0x34)[0]
        t.unknown_38          = bytes(data[0x38:0x6c])
        return t

    def to_bytes(self):
        buf = bytearray(TILED_OBJECT_SIZE)
        buf[0x00:0x20] = _str32_encode(self.name)
        buf[0x20:0x28] = self.tiled_object_id.encode('latin-1')[:8].ljust(8, b'\x00')
        struct.pack_into('<I', buf, 0x28, self.flags)
        struct.pack_into('<I', buf, 0x2c, self.first_vertex_open)
        struct.pack_into('<H', buf, 0x30, self.count_open)
        struct.pack_into('<H', buf, 0x32, self.count_closed)
        struct.pack_into('<I', buf, 0x34, self.first_vertex_closed)
        buf[0x38:0x6c] = self.unknown_38[:52]
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'name': self.name,
            'tiled_object_id': self.tiled_object_id,
            'flags': self.flags,
            'first_vertex_open': self.first_vertex_open,
            'count_open': self.count_open,
            'count_closed': self.count_closed,
            'first_vertex_closed': self.first_vertex_closed,
            'unknown_38': self.unknown_38.hex() if any(self.unknown_38) else None,
        })

    @classmethod
    def from_json(cls, d):
        t = cls.__new__(cls)
        t.name                = d.get('name', '')
        t.tiled_object_id     = d.get('tiled_object_id', '')
        t.flags               = d.get('flags', 0)
        t.first_vertex_open   = d.get('first_vertex_open', 0)
        t.count_open          = d.get('count_open', 0)
        t.count_closed        = d.get('count_closed', 0)
        t.first_vertex_closed = d.get('first_vertex_closed', 0)
        unk = d.get('unknown_38')
        t.unknown_38 = bytes.fromhex(unk) if unk else bytes(52)
        return t


# ─────────────────────────────────────────────────────────────────────────────
# Projectile Traps  (M5)
# ─────────────────────────────────────────────────────────────────────────────
class AreProjectileTrap:
    """28 bytes.
    effects_offset is an absolute file offset pointing to the trap's effect
    records; stored verbatim for round-trip fidelity (effects data not parsed).
    """
    __slots__ = [
        'projectile_resref', 'effects_count',
        'x', 'y', 'effects_offset',
        'projectile_type', 'effect_expiry',
        'orientation', 'unknown_1a',
    ]

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= PROJECTILE_TRAP_SIZE
        p = cls.__new__(cls)
        p.projectile_resref = _resref(data[0x00:0x08])
        p.effects_count     = struct.unpack_from('<I', data, 0x08)[0]
        p.x                 = struct.unpack_from('<H', data, 0x0c)[0]
        p.y                 = struct.unpack_from('<H', data, 0x0e)[0]
        p.effects_offset    = struct.unpack_from('<I', data, 0x10)[0]
        p.projectile_type   = struct.unpack_from('<H', data, 0x14)[0]
        p.effect_expiry     = struct.unpack_from('<H', data, 0x16)[0]
        p.orientation       = struct.unpack_from('<H', data, 0x18)[0]
        p.unknown_1a        = struct.unpack_from('<H', data, 0x1a)[0]
        return p

    def to_bytes(self):
        buf = bytearray(PROJECTILE_TRAP_SIZE)
        buf[0x00:0x08] = _resref_encode(self.projectile_resref)
        struct.pack_into('<I', buf, 0x08, self.effects_count)
        struct.pack_into('<H', buf, 0x0c, self.x)
        struct.pack_into('<H', buf, 0x0e, self.y)
        struct.pack_into('<I', buf, 0x10, self.effects_offset)
        struct.pack_into('<H', buf, 0x14, self.projectile_type)
        struct.pack_into('<H', buf, 0x16, self.effect_expiry)
        struct.pack_into('<H', buf, 0x18, self.orientation)
        struct.pack_into('<H', buf, 0x1a, self.unknown_1a)
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'projectile_resref': self.projectile_resref,
            'effects_count': self.effects_count,
            'x': self.x, 'y': self.y,
            'effects_offset': self.effects_offset,
            'projectile_type': self.projectile_type,
            'effect_expiry': self.effect_expiry,
            'orientation': self.orientation,
            'unknown_1a': self.unknown_1a,
        })

    @classmethod
    def from_json(cls, d):
        p = cls.__new__(cls)
        p.projectile_resref = d.get('projectile_resref', '')
        p.effects_count     = d.get('effects_count', 0)
        p.x                 = d.get('x', 0)
        p.y                 = d.get('y', 0)
        p.effects_offset    = d.get('effects_offset', 0)
        p.projectile_type   = d.get('projectile_type', 0)
        p.effect_expiry     = d.get('effect_expiry', 0)
        p.orientation       = d.get('orientation', 0)
        p.unknown_1a        = d.get('unknown_1a', 0)
        return p


# ─────────────────────────────────────────────────────────────────────────────
# Song Entries  (M5 — singleton, 0x90 bytes)
# ─────────────────────────────────────────────────────────────────────────────
class AreSongEntries:
    """144 bytes, single record per file.
    Music/ambient indices for day, night, win, battle, lose, and five alternates.
    main_ambients: resref for the daytime ambient sound set.
    unknown_34: 92 bytes of unknown data preserved verbatim.
    """
    __slots__ = [
        'day_song', 'night_song', 'win_song', 'battle_song', 'lose_song',
        'alt_music',        # list of 5 dwords
        'main_ambients', 'reverb',
        'unknown_34',
    ]

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= SONG_ENTRIES_SIZE
        s = cls.__new__(cls)
        s.day_song    = struct.unpack_from('<I', data, 0x00)[0]
        s.night_song  = struct.unpack_from('<I', data, 0x04)[0]
        s.win_song    = struct.unpack_from('<I', data, 0x08)[0]
        s.battle_song = struct.unpack_from('<I', data, 0x0c)[0]
        s.lose_song   = struct.unpack_from('<I', data, 0x10)[0]
        s.alt_music   = list(struct.unpack_from('<5I', data, 0x14))
        s.main_ambients = _resref(data[0x28:0x30])
        s.reverb      = struct.unpack_from('<I', data, 0x30)[0]
        s.unknown_34  = bytes(data[0x34:0x90])
        return s

    def to_bytes(self):
        buf = bytearray(SONG_ENTRIES_SIZE)
        struct.pack_into('<I',  buf, 0x00, self.day_song)
        struct.pack_into('<I',  buf, 0x04, self.night_song)
        struct.pack_into('<I',  buf, 0x08, self.win_song)
        struct.pack_into('<I',  buf, 0x0c, self.battle_song)
        struct.pack_into('<I',  buf, 0x10, self.lose_song)
        alts = (list(self.alt_music) + [0] * 5)[:5]
        struct.pack_into('<5I', buf, 0x14, *alts)
        buf[0x28:0x30] = _resref_encode(self.main_ambients)
        struct.pack_into('<I',  buf, 0x30, self.reverb)
        buf[0x34:0x90] = self.unknown_34[:92]
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'day_song': self.day_song, 'night_song': self.night_song,
            'win_song': self.win_song, 'battle_song': self.battle_song,
            'lose_song': self.lose_song, 'alt_music': self.alt_music,
            'main_ambients': self.main_ambients, 'reverb': self.reverb,
            'unknown_34': self.unknown_34.hex() if any(self.unknown_34) else None,
        })

    @classmethod
    def from_json(cls, d):
        s = cls.__new__(cls)
        s.day_song      = d.get('day_song', 0)
        s.night_song    = d.get('night_song', 0)
        s.win_song      = d.get('win_song', 0)
        s.battle_song   = d.get('battle_song', 0)
        s.lose_song     = d.get('lose_song', 0)
        s.alt_music     = (d.get('alt_music', []) + [0] * 5)[:5]
        s.main_ambients = d.get('main_ambients', '')
        s.reverb        = d.get('reverb', 0)
        unk34 = d.get('unknown_34')
        s.unknown_34 = bytes.fromhex(unk34) if unk34 else bytes(92)
        return s


# ─────────────────────────────────────────────────────────────────────────────
# Rest Interruption  (M5 — singleton, 0xE4 bytes)
# ─────────────────────────────────────────────────────────────────────────────
class AreRestInterruption:
    """228 bytes, single record per file.
    Up to 10 creature resrefs that may spawn to interrupt a rest.
    creature_count marks how many slots are active.
    difficulty: spawn probability (1-100).
    unknown_5c: 136 bytes preserved verbatim.
    """
    __slots__ = [
        'creature_resrefs',     # list of up to 10 resrefs
        'difficulty', 'removal_time',
        'movement_restriction', 'unknown_56',
        'creature_count', 'unknown_5a',
        'unknown_5c',
    ]

    @classmethod
    def from_bytes(cls, data):
        assert len(data) >= REST_INTERRUPTION_SIZE
        r = cls.__new__(cls)
        r.creature_resrefs    = [_resref(data[i*8:(i+1)*8]) for i in range(10)]
        r.difficulty          = struct.unpack_from('<H', data, 0x50)[0]
        r.removal_time        = struct.unpack_from('<H', data, 0x52)[0]
        r.movement_restriction = struct.unpack_from('<H', data, 0x54)[0]
        r.unknown_56          = struct.unpack_from('<H', data, 0x56)[0]
        r.creature_count      = struct.unpack_from('<H', data, 0x58)[0]
        r.unknown_5a          = struct.unpack_from('<H', data, 0x5a)[0]
        r.unknown_5c          = bytes(data[0x5c:0xe4])
        return r

    def to_bytes(self):
        buf = bytearray(REST_INTERRUPTION_SIZE)
        refs = (list(self.creature_resrefs) + [''] * 10)[:10]
        for i in range(10):
            buf[i*8:(i+1)*8] = _resref_encode(refs[i])
        struct.pack_into('<H', buf, 0x50, self.difficulty)
        struct.pack_into('<H', buf, 0x52, self.removal_time)
        struct.pack_into('<H', buf, 0x54, self.movement_restriction)
        struct.pack_into('<H', buf, 0x56, self.unknown_56)
        struct.pack_into('<H', buf, 0x58, self.creature_count)
        struct.pack_into('<H', buf, 0x5a, self.unknown_5a)
        buf[0x5c:0xe4] = self.unknown_5c[:136]
        return bytes(buf)

    def to_json(self):
        return _sparse({
            'creature_resrefs': self.creature_resrefs,
            'difficulty': self.difficulty,
            'removal_time': self.removal_time,
            'movement_restriction': self.movement_restriction,
            'creature_count': self.creature_count,
            'unknown_5c': self.unknown_5c.hex() if any(self.unknown_5c) else None,
        })

    @classmethod
    def from_json(cls, d):
        r = cls.__new__(cls)
        refs = d.get('creature_resrefs', [])
        r.creature_count       = d.get('creature_count', 0)
        r.creature_resrefs     = (refs + [''] * 10)[:10]
        r.difficulty           = d.get('difficulty', 0)
        r.removal_time         = d.get('removal_time', 0)
        r.movement_restriction = d.get('movement_restriction', 0)
        r.unknown_56           = 0
        r.unknown_5a           = 0
        unk = d.get('unknown_5c')
        r.unknown_5c = bytes.fromhex(unk) if unk else bytes(136)
        return r


# ─────────────────────────────────────────────────────────────────────────────
# AreFile
# ─────────────────────────────────────────────────────────────────────────────
class AreFile:
    """
    ARE V1.0 file container.  All sections are fully typed through M5.

    Vertex pool layout (rebuilt on every to_bytes):
      region[0..n] vertices | container[0..n] vertices |
      door[0] verts_open | door[0] verts_closed | door[0] impeded_open | door[0] impeded_closed |
      door[1] ... | ...

    Item pool: rebuilt from containers in order.

    Tiled object flags pool: stored verbatim as _raw_tiled_object_flags.
    Its stride (per-entry bytes) is undocumented and potentially game-specific,
    so the pool is treated as an opaque blob referenced by AreTiledObject
    first_vertex_open / first_vertex_closed indices.

    PST automap notes (0x214 bytes each) differ structurally from non-PST notes
    (0x34 bytes each); the PST variant is stored as _raw_pst_automap_notes.
    """

    def __init__(self):
        self.header: Optional[AreHeader] = None
        # M1-M4 typed sections
        self.actors:       List[AreActor]       = []
        self.regions:      List[AreRegion]      = []
        self.spawn_points: List[AreSpawnPoint]  = []
        self.entrances:    List[AreEntrance]    = []
        self.containers:   List[AreContainer]   = []
        self.ambients:     List[AreAmbient]     = []
        self.variables:    List[AreVariable]    = []
        self.doors:        List[AreDoor]        = []
        # M5 typed sections
        self.animations:        List[AreAnimation]          = []
        self.automap_notes:     List[AreAutomapNote]        = []   # non-PST only
        self.tiled_objects:     List[AreTiledObject]        = []
        self.projectile_traps:  List[AreProjectileTrap]     = []
        self.song_entries:      Optional[AreSongEntries]    = None
        self.rest_interruption: Optional[AreRestInterruption] = None
        # opaque blobs
        self._raw_explored_bitmask:   bytes = b''
        self._raw_pst_automap_notes:  bytes = b''   # PST only (field_c4 == 0xFFFFFFFF)
        self._raw_tiled_object_flags: bytes = b''   # tiled_object_flags pool; stride opaque

    # ── pool builders ─────────────────────────────────────────────────────────

    def _build_vertex_pool(self):
        """Returns (pool_bytes, region_vis, container_vis, door_vis_4tuples)."""
        pool = bytearray()

        def _append(verts):
            idx = len(pool) // VERTEX_SIZE
            for vx, vy in verts:
                pool.extend(struct.pack('<HH', vx, vy))
            return idx

        region_vis    = [_append(r.vertices) for r in self.regions]
        container_vis = [_append(c.vertices) for c in self.containers]
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
            vertex_pool = bytes(data[h.vertices_offset: h.vertices_offset + h.vertices_count * VERTEX_SIZE])

        item_pool = b''
        if h.items_count > 0 and h.items_offset > 0:
            item_pool = bytes(data[h.items_offset: h.items_offset + h.items_count * ITEM_SIZE])

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

        # M5: Animations
        for i in range(h.animations_count):
            s = h.animations_offset + i * ANIMATION_SIZE
            if s + ANIMATION_SIZE <= len(data):
                af.animations.append(AreAnimation.from_bytes(data[s:s+ANIMATION_SIZE]))

        # M5: Tiled Objects
        for i in range(h.tiled_objects_count):
            s = h.tiled_objects_offset + i * TILED_OBJECT_SIZE
            if s + TILED_OBJECT_SIZE <= len(data):
                af.tiled_objects.append(AreTiledObject.from_bytes(data[s:s+TILED_OBJECT_SIZE]))

        # M5: Tiled object flags pool (opaque — preserve verbatim)
        tofp_off = h.tiled_object_flags_offset
        tofp_cnt = h.tiled_object_flags_count
        if tofp_off > 0 and tofp_cnt > 0:
            # Each entry is a dword per IESDP; store the raw pool bytes.
            af._raw_tiled_object_flags = bytes(data[tofp_off: tofp_off + tofp_cnt * 4])

        # M5: Song Entries (singleton)
        if h.song_entries_offset > 0:
            se_end = h.song_entries_offset + SONG_ENTRIES_SIZE
            if se_end <= len(data):
                af.song_entries = AreSongEntries.from_bytes(data[h.song_entries_offset:se_end])

        # M5: Rest Interruption (singleton)
        if h.rest_interruptions_offset > 0:
            ri_end = h.rest_interruptions_offset + REST_INTERRUPTION_SIZE
            if ri_end <= len(data):
                af.rest_interruption = AreRestInterruption.from_bytes(
                    data[h.rest_interruptions_offset:ri_end])

        # Explored bitmask
        if h.explored_bitmask_size > 0 and h.explored_bitmask_offset > 0:
            af._raw_explored_bitmask = bytes(
                data[h.explored_bitmask_offset: h.explored_bitmask_offset + h.explored_bitmask_size])

        # M5: Automap Notes + Projectile Traps
        # field_c4/c8/cc encode these differently for PST vs non-PST.
        is_pst        = (h.field_c4 == 0xFFFFFFFF)
        automap_off   = h.field_c8 if is_pst else h.field_c4
        automap_count = h.field_cc if is_pst else h.field_c8
        proj_off      = 0           if is_pst else h.field_cc
        note_size     = AUTOMAP_NOTE_PST_SIZE if is_pst else AUTOMAP_NOTE_SIZE

        if is_pst:
            # Keep PST notes verbatim; structure differs (0x214 bytes, string-embedded text)
            if automap_off > 0 and automap_count > 0:
                end = automap_off + automap_count * note_size
                if end <= len(data):
                    af._raw_pst_automap_notes = bytes(data[automap_off:end])
        else:
            for i in range(automap_count):
                s = automap_off + i * AUTOMAP_NOTE_SIZE
                if s + AUTOMAP_NOTE_SIZE <= len(data):
                    af.automap_notes.append(AreAutomapNote.from_bytes(data[s:s+AUTOMAP_NOTE_SIZE]))

        for i in range(h.projectile_traps_count):
            s = proj_off + i * PROJECTILE_TRAP_SIZE
            if proj_off > 0 and s + PROJECTILE_TRAP_SIZE <= len(data):
                af.projectile_traps.append(AreProjectileTrap.from_bytes(data[s:s+PROJECTILE_TRAP_SIZE]))

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

        is_pst = (h.field_c4 == 0xFFFFFFFF)

        # ── layout pass ───────────────────────────────────────────────────────
        pos = HEADER_SIZE

        def _place_blobs(blobs):
            nonlocal pos
            total = sum(len(b) for b in blobs)
            off = pos; pos += total; return off

        def _place_raw(raw):
            nonlocal pos
            off = pos
            if raw: pos += len(raw)
            return off

        # Actors: serialise twice (CRE offsets unknown until end)
        actor_blobs_tmp = [a.to_bytes(0) for a in self.actors]
        actors_off  = _place_blobs(actor_blobs_tmp)
        regions_off = _place_blobs([r.to_bytes(0)      for r in self.regions])
        sp_off      = _place_blobs([s.to_bytes()        for s in self.spawn_points])
        ent_off     = _place_blobs([e.to_bytes()        for e in self.entrances])
        cont_off    = _place_blobs([c.to_bytes(0, 0)   for c in self.containers])
        items_off   = _place_raw(item_pool)
        amb_off     = _place_blobs([a.to_bytes()        for a in self.ambients])
        var_off     = _place_blobs([v.to_bytes()        for v in self.variables])
        doors_off   = _place_blobs([d.to_bytes(0,0,0,0) for d in self.doors])
        tiled_off   = _place_blobs([t.to_bytes()        for t in self.tiled_objects])
        vert_off    = _place_raw(vertex_pool)
        expl_off    = _place_raw(self._raw_explored_bitmask)

        # M5 layout
        anim_off    = _place_blobs([a.to_bytes() for a in self.animations])
        tofp_off    = _place_raw(self._raw_tiled_object_flags)
        tofp_count  = len(self._raw_tiled_object_flags) // 4 if self._raw_tiled_object_flags else 0

        song_off = 0
        if self.song_entries:
            song_off = pos; pos += SONG_ENTRIES_SIZE
        rest_off = 0
        if self.rest_interruption:
            rest_off = pos; pos += REST_INTERRUPTION_SIZE

        # Automap notes + projectile traps
        automap_off   = 0
        automap_count = 0
        if is_pst:
            automap_off   = _place_raw(self._raw_pst_automap_notes)
            automap_count = (len(self._raw_pst_automap_notes) // AUTOMAP_NOTE_PST_SIZE
                             if self._raw_pst_automap_notes else 0)
        else:
            note_blobs  = [n.to_bytes() for n in self.automap_notes]
            automap_off   = _place_blobs(note_blobs)
            automap_count = len(self.automap_notes)

        proj_off2 = _place_blobs([p.to_bytes() for p in self.projectile_traps])

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
            fc4 = 0xFFFFFFFF
            fc8 = automap_off if automap_count > 0 else h.field_c8
            fcc = automap_count
        else:
            fc4 = automap_off if automap_count > 0 else h.field_c4
            fc8 = automap_count
            fcc = proj_off2 if self.projectile_traps else h.field_cc

        # For zero-size explored_bitmask, preserve the original placeholder offset
        if not self._raw_explored_bitmask:
            expl_off = h.explored_bitmask_offset

        offsets = {
            'actors_offset': actors_off,    'actors_count': len(self.actors),
            'regions_offset': regions_off,  'regions_count': len(self.regions),
            'spawn_points_offset': sp_off,  'spawn_points_count': len(self.spawn_points),
            'entrances_offset': ent_off,    'entrances_count': len(self.entrances),
            'containers_offset': cont_off,  'containers_count': len(self.containers),
            'items_offset': items_off,      'items_count': items_count,
            'vertices_offset': vert_off,    'vertices_count': vert_count,
            'ambients_offset': amb_off,     'ambients_count': len(self.ambients),
            'variables_offset': var_off,    'variables_count': len(self.variables),
            'tiled_object_flags_offset': tofp_off if tofp_count else 0,
            'tiled_object_flags_count': tofp_count,
            'explored_bitmask_offset': expl_off,
            'explored_bitmask_size': len(self._raw_explored_bitmask),
            'doors_offset': doors_off,      'doors_count': len(self.doors),
            'animations_offset': anim_off,  'animations_count': len(self.animations),
            'tiled_objects_offset': tiled_off, 'tiled_objects_count': len(self.tiled_objects),
            'song_entries_offset': song_off,
            'rest_interruptions_offset': rest_off,
            'projectile_traps_count': len(self.projectile_traps),
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

        _write_blobs(amb_off, [a.to_bytes() for a in self.ambients])
        _write_blobs(var_off, [v.to_bytes() for v in self.variables])

        # Doors with correct vertex indices
        door_blobs = [self.doors[i].to_bytes(*door_vis[i]) for i in range(len(self.doors))]
        _write_blobs(doors_off, door_blobs)

        # M5 sections
        _write_blobs(tiled_off,   [t.to_bytes() for t in self.tiled_objects])
        _write(vert_off,          vertex_pool)
        _write(expl_off,          self._raw_explored_bitmask)
        _write_blobs(anim_off,    [a.to_bytes() for a in self.animations])
        _write(tofp_off,          self._raw_tiled_object_flags)

        if self.song_entries and song_off:
            buf[song_off:song_off+SONG_ENTRIES_SIZE] = self.song_entries.to_bytes()
        if self.rest_interruption and rest_off:
            buf[rest_off:rest_off+REST_INTERRUPTION_SIZE] = self.rest_interruption.to_bytes()

        if is_pst:
            _write(automap_off, self._raw_pst_automap_notes)
        else:
            _write_blobs(automap_off, [n.to_bytes() for n in self.automap_notes])

        _write_blobs(proj_off2, [p.to_bytes() for p in self.projectile_traps])

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
            'header':           self.header.to_json(),
            'actors':           [a.to_json()  for a in self.actors],
            'regions':          [r.to_json()  for r in self.regions],
            'spawn_points':     [s.to_json()  for s in self.spawn_points],
            'entrances':        [e.to_json()  for e in self.entrances],
            'containers':       [c.to_json()  for c in self.containers],
            'ambients':         [a.to_json()  for a in self.ambients],
            'variables':        [v.to_json()  for v in self.variables],
            'doors':            [dr.to_json() for dr in self.doors],
            'animations':       [a.to_json()  for a in self.animations],
            'automap_notes':    [n.to_json()  for n in self.automap_notes],
            'tiled_objects':    [t.to_json()  for t in self.tiled_objects],
            'projectile_traps': [p.to_json()  for p in self.projectile_traps],
        }
        if self.song_entries:
            d['song_entries'] = self.song_entries.to_json()
        if self.rest_interruption:
            d['rest_interruption'] = self.rest_interruption.to_json()
        for key, raw in [
            ('_raw_explored_bitmask',    self._raw_explored_bitmask),
            ('_raw_pst_automap_notes',   self._raw_pst_automap_notes),
            ('_raw_tiled_object_flags',  self._raw_tiled_object_flags),
        ]:
            if raw:
                d[key] = raw.hex()
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
        af.animations       = [AreAnimation.from_json(a)     for a in d.get('animations', [])]
        af.automap_notes    = [AreAutomapNote.from_json(n)    for n in d.get('automap_notes', [])]
        af.tiled_objects    = [AreTiledObject.from_json(t)    for t in d.get('tiled_objects', [])]
        af.projectile_traps = [AreProjectileTrap.from_json(p) for p in d.get('projectile_traps', [])]
        se = d.get('song_entries')
        af.song_entries = AreSongEntries.from_json(se) if se is not None else None
        ri = d.get('rest_interruption')
        af.rest_interruption = AreRestInterruption.from_json(ri) if ri is not None else None

        def _hex(k): return bytes.fromhex(d[k]) if k in d else b''
        af._raw_explored_bitmask   = _hex('_raw_explored_bitmask')
        af._raw_pst_automap_notes  = _hex('_raw_pst_automap_notes')
        af._raw_tiled_object_flags = _hex('_raw_tiled_object_flags')

        # Compute layout to fill header offsets
        vertex_pool, _, _, _ = af._build_vertex_pool()
        item_pool,   _       = af._build_item_pool()
        vert_count  = len(vertex_pool) // VERTEX_SIZE
        items_count = len(item_pool)   // ITEM_SIZE

        hj     = d.get('header', {})
        is_pst = (hj.get('field_c4', 0) == 0xFFFFFFFF)

        pos = HEADER_SIZE
        def _lay(count, size):
            nonlocal pos
            off = pos; pos += count * size; return off
        def _lay_raw(raw):
            nonlocal pos
            off = pos
            if raw: pos += len(raw)
            return off

        actors_off  = _lay(len(af.actors),       ACTOR_SIZE)
        regions_off = _lay(len(af.regions),      REGION_SIZE)
        sp_off      = _lay(len(af.spawn_points), SPAWN_POINT_SIZE)
        ent_off     = _lay(len(af.entrances),    ENTRANCE_SIZE)
        cont_off    = _lay(len(af.containers),   CONTAINER_SIZE)
        items_off   = _lay(items_count,          ITEM_SIZE)
        amb_off     = _lay(len(af.ambients),     AMBIENT_SIZE)
        var_off     = _lay(len(af.variables),    VARIABLE_SIZE)
        doors_off   = _lay(len(af.doors),        DOOR_SIZE)
        tiled_off   = _lay(len(af.tiled_objects), TILED_OBJECT_SIZE)
        vert_off    = _lay(vert_count,           VERTEX_SIZE)
        expl_off    = _lay_raw(af._raw_explored_bitmask)
        anim_off    = _lay(len(af.animations),   ANIMATION_SIZE)
        tofp_off    = _lay_raw(af._raw_tiled_object_flags)
        tofp_count  = len(af._raw_tiled_object_flags) // 4 if af._raw_tiled_object_flags else 0

        song_off = 0
        if af.song_entries:
            song_off = pos; pos += SONG_ENTRIES_SIZE
        rest_off = 0
        if af.rest_interruption:
            rest_off = pos; pos += REST_INTERRUPTION_SIZE

        if is_pst:
            automap_off   = _lay_raw(af._raw_pst_automap_notes)
            automap_count = (len(af._raw_pst_automap_notes) // AUTOMAP_NOTE_PST_SIZE
                             if af._raw_pst_automap_notes else 0)
        else:
            automap_off   = _lay(len(af.automap_notes), AUTOMAP_NOTE_SIZE)
            automap_count = len(af.automap_notes)

        proj_off = _lay(len(af.projectile_traps), PROJECTILE_TRAP_SIZE)

        if is_pst:
            fc4 = 0xFFFFFFFF
            fc8 = automap_off if automap_count > 0 else hj.get('field_c8', 0)
            fcc = automap_count
        else:
            fc4 = automap_off if automap_count > 0 else hj.get('field_c4', 0)
            fc8 = automap_count
            fcc = proj_off if af.projectile_traps else hj.get('field_cc', 0)

        # For zero-size explored_bitmask, preserve original placeholder offset
        if not af._raw_explored_bitmask:
            expl_off = hj.get('explored_bitmask_offset', expl_off)

        offsets = {
            'actors_offset': actors_off,    'actors_count': len(af.actors),
            'regions_offset': regions_off,  'regions_count': len(af.regions),
            'spawn_points_offset': sp_off,  'spawn_points_count': len(af.spawn_points),
            'entrances_offset': ent_off,    'entrances_count': len(af.entrances),
            'containers_offset': cont_off,  'containers_count': len(af.containers),
            'items_offset': items_off,      'items_count': items_count,
            'vertices_offset': vert_off,    'vertices_count': vert_count,
            'ambients_offset': amb_off,     'ambients_count': len(af.ambients),
            'variables_offset': var_off,    'variables_count': len(af.variables),
            'tiled_object_flags_offset': tofp_off if tofp_count else 0,
            'tiled_object_flags_count': tofp_count,
            'explored_bitmask_offset': expl_off,
            'explored_bitmask_size': len(af._raw_explored_bitmask),
            'doors_offset': doors_off,      'doors_count': len(af.doors),
            'animations_offset': anim_off,  'animations_count': len(af.animations),
            'tiled_objects_offset': tiled_off, 'tiled_objects_count': len(af.tiled_objects),
            'song_entries_offset': song_off,
            'rest_interruptions_offset': rest_off,
            'projectile_traps_count': len(af.projectile_traps),
        }
        af.header = AreHeader.from_json(hj, offsets)
        af.header.field_c4 = fc4
        af.header.field_c8 = fc8
        af.header.field_cc = fcc
        return af

    # ── diagnostics ───────────────────────────────────────────────────────────

    def summary(self) -> str:
        h = self.header
        total_items = sum(len(c.items) for c in self.containers)
        ri = self.rest_interruption
        return '\n'.join([
            f"ARE V1.0  WED={h.area_wed!r}  script={h.area_script!r}",
            f"  actors={len(self.actors)}  regions={len(self.regions)}  "
            f"spawn_points={len(self.spawn_points)}  entrances={len(self.entrances)}",
            f"  containers={len(self.containers)}  items={total_items}  "
            f"ambients={len(self.ambients)}  variables={len(self.variables)}",
            f"  doors={len(self.doors)}  animations={len(self.animations)}  "
            f"tiled_objects={len(self.tiled_objects)}",
            f"  automap_notes={len(self.automap_notes)}  "
            f"projectile_traps={len(self.projectile_traps)}  "
            f"song_entries={'yes' if self.song_entries else 'no'}  "
            f"rest_interruption={'yes' if ri else 'no'}"
            + (f" ({ri.creature_count} creatures)" if ri else ''),
            f"  explored_bitmask={h.explored_bitmask_size} bytes  "
            f"vertices(hdr)={h.vertices_count}",
            f"  north={h.north_resref!r}  east={h.east_resref!r}  "
            f"south={h.south_resref!r}  west={h.west_resref!r}",
        ])
