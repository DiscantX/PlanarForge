"""
core/formats/dlg.py

Parser and writer for the Infinity Engine DLG (Dialogue) format.

A DLG file encodes a conversation as a directed graph of States and
Transitions.  Every NPC dialogue file in the game is a DLG resource.

Graph structure
---------------
Each **State** is one NPC speech node.  It carries:
  - A StrRef for the spoken text
  - An optional state-trigger (BCS condition) that gates entry
  - A slice of the **Transitions** array

Each **Transition** is one player-response branch.  It carries:
  - An optional StrRef for the player response text
  - An optional transition trigger (BCS condition)
  - An optional action (BCS action list) to execute when taken
  - A pointer to the next State (same DLG or a foreign DLG), OR a
    termination flag

Triggers and actions are stored as raw compiled script strings
(the same text that appears in BCS files).  Helper methods are provided
for pretty-printing and simple parsing.

Traversal
---------
Raw indices are always available on each struct.  The :class:`DlgFile`
also provides resolved-object traversal via
``state.get_transitions(dlg)`` and ``transition.get_next_state(dlg)``.

Versions
--------
    V1.0  — all IE games (the only version; the format never changed)

IESDP reference:
    https://gibberlings3.github.io/iesdp/file_formats/ie_formats/dlg_v1.htm

Usage::

    from core.formats.dlg import DlgFile

    dlg = DlgFile.from_file("GORION.dlg")
    print(len(dlg.states), "states")

    # Walk the graph from state 0
    state = dlg.states[0]
    print(dlg.tlk_text(state.text_strref))      # NPC line (StrRef only)
    for trans in state.get_transitions(dlg):
        print("  ->", trans.text_strref,
              "to", trans.next_dlg or "<self>",
              "state", trans.next_state_index)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.util.binary import BinaryReader, BinaryWriter, SignatureMismatch
from core.util.strref import StrRef, StrRefError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE    = b"DLG "
VERSION      = b"V1.0"
HEADER_SIZE  = 52        # bytes

STATE_SIZE       = 16
TRANSITION_SIZE  = 32

NO_INDEX     = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Transition flags
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Script string helpers
# ---------------------------------------------------------------------------

# Minimal pretty-printer for compiled BCS trigger/action strings.
# The compiled format looks like:
#   "CO()CR()OR(2)" — for triggers
#   "AC()" — for actions
# Each token is a 2-char opcode followed by bracketed arguments.

_BCS_TOKEN = re.compile(r'([A-Z]{2})\(([^)]*)\)')

def _parse_script_string(raw: str) -> List[Tuple[str, str]]:
    """
    Split a raw compiled BCS string into (opcode, args) pairs.

    Returns a list of (opcode, args_string) tuples.
    Example::

        _parse_script_string("CO()CR()OR(2)")
        # -> [("CO", ""), ("CR", ""), ("OR", "2")]
    """
    return [(m.group(1), m.group(2)) for m in _BCS_TOKEN.finditer(raw)]


def _format_trigger(raw: str) -> str:
    """
    Return a human-readable multiline representation of a trigger string.

    Example::

        _format_trigger('CO(0 "Player1" 0 0 "" "")CR()')
        # ->
        # CO(0 "Player1" 0 0 "" "")
        # CR()
    """
    tokens = _parse_script_string(raw)
    if not tokens:
        return raw.strip()
    return "\n".join(f"{op}({args})" for op, args in tokens)


def _format_action(raw: str) -> str:
    """Return a human-readable multiline representation of an action string."""
    # Action strings use the same token format but are prefixed with
    # CR() (character reference) before each action opcode.
    return _format_trigger(raw)


# ---------------------------------------------------------------------------
# State  (16 bytes in binary)
# ---------------------------------------------------------------------------

@dataclass
class State:
    """
    One NPC speech node in the dialogue graph.

    Raw index fields
    ~~~~~~~~~~~~~~~~
    ``first_transition_index``  — index of the first Transition in this
                                   state's response list (into DlgFile.transitions)
    ``transition_count``        — number of responses
    ``trigger_index``           — index into DlgFile.state_triggers (-1 = none)

    Convenience
    ~~~~~~~~~~~
    ``get_transitions(dlg)``    — resolved list of :class:`Transition` objects
    ``get_trigger(dlg)``        — raw trigger string or ``None``
    """
    text_strref:            StrRef = StrRef(0xFFFFFFFF)   # uint32 — NPC spoken text
    first_transition_index: int = 0             # uint32
    transition_count:       int = 0             # uint32
    trigger_index:          int = NO_INDEX      # uint32 — 0xFFFFFFFF = none

    @classmethod
    def _read(cls, r: BinaryReader) -> "State":
        text_strref  = StrRef(r.read_uint32())
        first_ti     = r.read_uint32()
        trans_count  = r.read_uint32()
        trig_idx     = r.read_uint32()
        return cls(
            text_strref=text_strref,
            first_transition_index=first_ti,
            transition_count=trans_count,
            trigger_index=trig_idx,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint32(int(self.text_strref))
        w.write_uint32(self.first_transition_index)
        w.write_uint32(self.transition_count)
        w.write_uint32(self.trigger_index)

    # ------------------------------------------------------------------
    # Resolved traversal
    # ------------------------------------------------------------------

    def get_transitions(self, dlg: "DlgFile") -> List["Transition"]:
        """Return the :class:`Transition` objects for this state."""
        start = self.first_transition_index
        count = self.transition_count
        return dlg.transitions[start : start + count]

    def get_trigger(self, dlg: "DlgFile") -> Optional[str]:
        """Return the raw state-trigger string, or ``None`` if absent."""
        if self.trigger_index >= len(dlg.state_triggers):
            return None
        return dlg.state_triggers[self.trigger_index]

    def get_trigger_pretty(self, dlg: "DlgFile") -> Optional[str]:
        """Return a pretty-printed state-trigger string, or ``None``."""
        raw = self.get_trigger(dlg)
        return _format_trigger(raw) if raw is not None else None

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        d: dict = {"text_strref": self.text_strref.to_json(),
                   "first_transition_index": self.first_transition_index,
                   "transition_count": self.transition_count}
        if self.trigger_index != NO_INDEX:
            d["trigger_index"] = self.trigger_index
        return d

    @classmethod
    def from_json(cls, d: dict) -> "State":
        return cls(
            text_strref=StrRef.from_json(hd.get("text_strref", 0xFFFFFFFF)),
            first_transition_index = d.get("first_transition_index", 0),
            transition_count       = d.get("transition_count", 0),
            trigger_index          = d.get("trigger_index", NO_INDEX),
        )


# ---------------------------------------------------------------------------
# Transition  (32 bytes in binary)
# ---------------------------------------------------------------------------

@dataclass
class Transition:
    """
    One player-response branch (edge) in the dialogue graph.

    Destination
    ~~~~~~~~~~~
    If ``flags & TERMINATES``, the conversation ends after this transition.
    Otherwise ``next_dlg`` names the DLG file containing the next state
    (empty string = same DLG file), and ``next_state_index`` is the state
    index within that file.

    Raw index fields
    ~~~~~~~~~~~~~~~~
    ``trigger_index``       — index into DlgFile.transition_triggers
    ``action_index``        — index into DlgFile.actions
    ``journal_strref``      — StrRef for journal entry text (if any)

    Convenience
    ~~~~~~~~~~~
    ``get_next_state(dlg)``  — resolved :class:`State` (same-DLG only)
    ``get_trigger(dlg)``     — raw trigger string or ``None``
    ``get_action(dlg)``      — raw action string or ``None``
    """
    flags:            int = TransitionFlag.NONE   # uint32
    text_strref:      StrRef = StrRef(0xFFFFFFFF)           # uint32 — player response text
    journal_strref:   StrRef = StrRef(0xFFFFFFFF)           # uint32 — journal text
    trigger_index:    int = NO_INDEX              # uint32 — into transition_triggers
    action_index:     int = NO_INDEX              # uint32 — into actions
    next_dlg:         str = ""                    # ResRef — foreign DLG (empty = self)
    next_state_index: int = 0                     # uint32 — state in next_dlg

    @classmethod
    def _read(cls, r: BinaryReader) -> "Transition":
        flags        = r.read_uint32()
        text_strref  = StrRef(r.read_uint32())
        journal_str  = r.read_uint32()
        trig_idx     = r.read_uint32()
        action_idx   = r.read_uint32()
        next_dlg     = r.read_resref()
        next_state   = r.read_uint32()
        return cls(
            flags=flags, text_strref=text_strref,
            journal_strref=journal_str,
            trigger_index=trig_idx, action_index=action_idx,
            next_dlg=next_dlg, next_state_index=next_state,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint32(self.flags)
        w.write_uint32(int(self.text_strref))
        w.write_uint32(int(self.journal_strref))
        w.write_uint32(self.trigger_index)
        w.write_uint32(self.action_index)
        w.write_resref(self.next_dlg)
        w.write_uint32(self.next_state_index)

    # ------------------------------------------------------------------
    # Properties derived from flags
    # ------------------------------------------------------------------

    @property
    def has_text(self) -> bool:
        return bool(self.flags & TransitionFlag.HAS_TEXT)

    @property
    def has_trigger(self) -> bool:
        return bool(self.flags & TransitionFlag.HAS_TRIGGER)

    @property
    def has_action(self) -> bool:
        return bool(self.flags & TransitionFlag.HAS_ACTION)

    @property
    def terminates(self) -> bool:
        return bool(self.flags & TransitionFlag.TERMINATES)

    # ------------------------------------------------------------------
    # Resolved traversal
    # ------------------------------------------------------------------

    def get_next_state(self, dlg: "DlgFile") -> Optional["State"]:
        """
        Return the destination :class:`State`, or ``None`` if the
        transition terminates or points to a foreign DLG file.
        """
        if self.terminates or self.next_dlg:
            return None
        idx = self.next_state_index
        if idx < len(dlg.states):
            return dlg.states[idx]
        return None

    def get_trigger(self, dlg: "DlgFile") -> Optional[str]:
        """Return the raw transition-trigger string, or ``None`` if absent."""
        if not self.has_trigger:
            return None
        if self.trigger_index >= len(dlg.transition_triggers):
            return None
        return dlg.transition_triggers[self.trigger_index]

    def get_trigger_pretty(self, dlg: "DlgFile") -> Optional[str]:
        raw = self.get_trigger(dlg)
        return _format_trigger(raw) if raw is not None else None

    def get_action(self, dlg: "DlgFile") -> Optional[str]:
        """Return the raw action string, or ``None`` if absent."""
        if not self.has_action:
            return None
        if self.action_index >= len(dlg.actions):
            return None
        return dlg.actions[self.action_index]

    def get_action_pretty(self, dlg: "DlgFile") -> Optional[str]:
        raw = self.get_action(dlg)
        return _format_action(raw) if raw is not None else None

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        d: dict = {"flags": self.flags}
        if self.has_text:
            d["text_strref"] = self.text_strref
        if not self.journal_strref.is_none:
            d["journal_strref"] = self.journal_strref
        if self.has_trigger:
            d["trigger_index"] = self.trigger_index
        if self.has_action:
            d["action_index"] = self.action_index
        if not self.terminates:
            if self.next_dlg:
                d["next_dlg"] = self.next_dlg
            d["next_state_index"] = self.next_state_index
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Transition":
        return cls(
            flags            = d.get("flags", TransitionFlag.NONE),
            text_strref=StrRef.from_json(hd.get("text_strref", 0xFFFFFFFF)),
            journal_strref=StrRef.from_json(hd.get("journal_strref", 0xFFFFFFFF)),
            trigger_index    = d.get("trigger_index", NO_INDEX),
            action_index     = d.get("action_index", NO_INDEX),
            next_dlg         = d.get("next_dlg", ""),
            next_state_index = d.get("next_state_index", 0),
        )


# ---------------------------------------------------------------------------
# DLG header  (52 bytes)
# ---------------------------------------------------------------------------

@dataclass
class DlgHeader:
    state_count:                int = 0
    state_offset:               int = 0
    transition_count:           int = 0
    transition_offset:          int = 0
    state_trigger_offset:       int = 0
    state_trigger_count:        int = 0
    transition_trigger_offset:  int = 0
    transition_trigger_count:   int = 0
    action_offset:              int = 0
    action_count:               int = 0
    flags:                      int = 0   # uint32 — threat / non-pausing flags

    @classmethod
    def _read(cls, r: BinaryReader) -> "DlgHeader":
        s_cnt   = r.read_uint32()
        s_off   = r.read_uint32()
        t_cnt   = r.read_uint32()
        t_off   = r.read_uint32()
        st_off  = r.read_uint32()
        st_cnt  = r.read_uint32()
        tt_off  = r.read_uint32()
        tt_cnt  = r.read_uint32()
        a_off   = r.read_uint32()
        a_cnt   = r.read_uint32()
        flags   = r.read_uint32()
        return cls(
            state_count=s_cnt, state_offset=s_off,
            transition_count=t_cnt, transition_offset=t_off,
            state_trigger_offset=st_off, state_trigger_count=st_cnt,
            transition_trigger_offset=tt_off, transition_trigger_count=tt_cnt,
            action_offset=a_off, action_count=a_cnt,
            flags=flags,
        )

    def _write(self, w: BinaryWriter) -> None:
        w.write_uint32(self.state_count)
        w.write_uint32(self.state_offset)
        w.write_uint32(self.transition_count)
        w.write_uint32(self.transition_offset)
        w.write_uint32(self.state_trigger_offset)
        w.write_uint32(self.state_trigger_count)
        w.write_uint32(self.transition_trigger_offset)
        w.write_uint32(self.transition_trigger_count)
        w.write_uint32(self.action_offset)
        w.write_uint32(self.action_count)
        w.write_uint32(self.flags)


# ---------------------------------------------------------------------------
# Script string table helpers
# ---------------------------------------------------------------------------

# Triggers and actions are stored as a table of (offset, length) pairs
# followed by the raw string data.  Each entry is 8 bytes:
#   uint32 offset — byte offset of the string within the string block
#   uint32 length — byte length of the string (including null terminator)

_SCRIPT_ENTRY_SIZE = 8


def _read_script_table(r: BinaryReader, count: int,
                       table_offset: int) -> List[str]:
    """
    Read *count* script strings from the table at *table_offset*.

    Returns a list of decoded strings (latin-1, null terminator stripped).
    """
    if count == 0:
        return []

    r.seek(table_offset)
    entries: List[Tuple[int, int]] = []
    for _ in range(count):
        off = r.read_uint32()
        length = r.read_uint32()
        entries.append((off, length))

    # String data starts immediately after the entry table
    string_block_base = table_offset + count * _SCRIPT_ENTRY_SIZE

    strings: List[str] = []
    for off, length in entries:
        if length == 0:
            strings.append("")
            continue
        raw = r.read_bytes_at(string_block_base + off, length)
        # Strip null terminator if present
        text = raw.rstrip(b"\x00").decode("latin-1", errors="replace")
        strings.append(text)

    return strings


def _write_script_table(w: BinaryWriter, strings: List[str]) -> None:
    """
    Write a script string table (entry array + string block) into *w*.

    The caller is responsible for recording the offset before this call.
    """
    if not strings:
        return

    # Build string block first to know offsets
    encoded: List[bytes] = []
    for s in strings:
        enc = s.encode("latin-1", errors="replace") + b"\x00"
        encoded.append(enc)

    offsets = []
    cursor = 0
    for enc in encoded:
        offsets.append(cursor)
        cursor += len(enc)

    # Entry table
    for i, enc in enumerate(encoded):
        w.write_uint32(offsets[i])
        w.write_uint32(len(enc))

    # String block
    for enc in encoded:
        w.write_bytes(enc)


# ---------------------------------------------------------------------------
# DlgFile — top-level container
# ---------------------------------------------------------------------------

class DlgFile:
    """
    A complete DLG dialogue resource.

    Attributes::

        header               — :class:`DlgHeader`
        states               — List[:class:`State`]
        transitions          — List[:class:`Transition`]
        state_triggers       — List[str]   (compiled BCS trigger strings)
        transition_triggers  — List[str]
        actions              — List[str]   (compiled BCS action strings)

    Traversal::

        # Object-graph style (same-DLG links only)
        state = dlg.states[0]
        for trans in state.get_transitions(dlg):
            next_state = trans.get_next_state(dlg)

        # Raw index style
        for i, state in enumerate(dlg.states):
            for j in range(state.transition_count):
                t = dlg.transitions[state.first_transition_index + j]

    Graph export::

        # All reachable (state_index, transition_index, next_state_index)
        edges = dlg.edges()

        # Adjacency dict: state_index -> list of state_indices
        adj = dlg.adjacency()

    Script strings::

        # Raw
        raw = dlg.transitions[0].get_trigger(dlg)

        # Pretty-printed tokens
        pretty = dlg.transitions[0].get_trigger_pretty(dlg)

        # Parse into (opcode, args) pairs
        from core.formats.dlg import parse_script_string
        tokens = parse_script_string(raw)
    """

    def __init__(
        self,
        header:              DlgHeader,
        states:              List[State],
        transitions:         List[Transition],
        state_triggers:      List[str],
        transition_triggers: List[str],
        actions:             List[str],
        source_path:         Optional[Path] = None,
    ) -> None:
        self.header              = header
        self.states              = states
        self.transitions         = transitions
        self.state_triggers      = state_triggers
        self.transition_triggers = transition_triggers
        self.actions             = actions
        self.source_path         = source_path

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes) -> "DlgFile":
        r = BinaryReader(data)
        try:
            r.expect_signature(SIGNATURE)
            r.expect_signature(VERSION)
        except SignatureMismatch as exc:
            raise ValueError(str(exc)) from exc

        header = DlgHeader._read(r)

        # States
        states: List[State] = []
        if header.state_count:
            r.seek(header.state_offset)
            for _ in range(header.state_count):
                states.append(State._read(r))

        # Transitions
        transitions: List[Transition] = []
        if header.transition_count:
            r.seek(header.transition_offset)
            for _ in range(header.transition_count):
                transitions.append(Transition._read(r))

        # Script string tables
        state_triggers = _read_script_table(
            r, header.state_trigger_count, header.state_trigger_offset)
        transition_triggers = _read_script_table(
            r, header.transition_trigger_count, header.transition_trigger_offset)
        actions = _read_script_table(
            r, header.action_count, header.action_offset)

        return cls(
            header=header,
            states=states,
            transitions=transitions,
            state_triggers=state_triggers,
            transition_triggers=transition_triggers,
            actions=actions,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "DlgFile":
        path = Path(path)
        instance = cls.from_bytes(path.read_bytes())
        instance.source_path = path
        return instance

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        # Layout order (IESDP convention):
        #   Header (52)
        #   States (N × 16)
        #   Transitions (M × 32)
        #   State trigger table + strings
        #   Transition trigger table + strings
        #   Action table + strings

        # Measure section sizes
        states_size      = len(self.states)      * STATE_SIZE
        transitions_size = len(self.transitions) * TRANSITION_SIZE

        def _script_table_size(strings: List[str]) -> int:
            if not strings: return 0
            entry_bytes  = len(strings) * _SCRIPT_ENTRY_SIZE
            string_bytes = sum(len(s.encode("latin-1", errors="replace")) + 1
                               for s in strings)
            return entry_bytes + string_bytes

        states_off      = HEADER_SIZE
        transitions_off = states_off      + states_size
        st_off          = transitions_off + transitions_size
        tt_off          = st_off + _script_table_size(self.state_triggers)
        a_off           = tt_off + _script_table_size(self.transition_triggers)

        # Patch header
        h = self.header
        h.state_count                = len(self.states)
        h.state_offset               = states_off
        h.transition_count           = len(self.transitions)
        h.transition_offset          = transitions_off
        h.state_trigger_count        = len(self.state_triggers)
        h.state_trigger_offset       = st_off
        h.transition_trigger_count   = len(self.transition_triggers)
        h.transition_trigger_offset  = tt_off
        h.action_count               = len(self.actions)
        h.action_offset              = a_off

        w = BinaryWriter()
        w.write_bytes(SIGNATURE)
        w.write_bytes(VERSION)
        h._write(w)

        for state in self.states:
            state._write(w)
        for trans in self.transitions:
            trans._write(w)

        _write_script_table(w, self.state_triggers)
        _write_script_table(w, self.transition_triggers)
        _write_script_table(w, self.actions)

        return w.to_bytes()

    def to_file(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        return {
            "format":              "dlg",
            "version":             "V1.0",
            "flags":               self.header.flags,
            "states":              [s.to_json()  for s in self.states],
            "transitions":         [t.to_json()  for t in self.transitions],
            "state_triggers":      self.state_triggers,
            "transition_triggers": self.transition_triggers,
            "actions":             self.actions,
        }

    @classmethod
    def from_json(cls, d: dict) -> "DlgFile":
        header = DlgHeader(flags=d.get("flags", 0))
        return cls(
            header              = header,
            states              = [State.from_json(s)      for s in d.get("states", [])],
            transitions         = [Transition.from_json(t) for t in d.get("transitions", [])],
            state_triggers      = d.get("state_triggers",      []),
            transition_triggers = d.get("transition_triggers", []),
            actions             = d.get("actions",             []),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "DlgFile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Graph traversal helpers
    # ------------------------------------------------------------------

    def edges(self) -> List[Tuple[int, int, Optional[int], Optional[str]]]:
        """
        Return all graph edges as a list of tuples::

            (state_index, transition_index, next_state_index, next_dlg)

        ``next_state_index`` is ``None`` for terminating transitions.
        ``next_dlg`` is ``None`` for same-DLG links, or a ResRef string
        for foreign-DLG jumps.
        """
        result = []
        for si, state in enumerate(self.states):
            for j in range(state.transition_count):
                ti   = state.first_transition_index + j
                trans = self.transitions[ti]
                if trans.terminates:
                    result.append((si, ti, None, None))
                elif trans.next_dlg:
                    result.append((si, ti, trans.next_state_index, trans.next_dlg))
                else:
                    result.append((si, ti, trans.next_state_index, None))
        return result

    def adjacency(self) -> Dict[int, List[int]]:
        """
        Return a same-DLG adjacency dict mapping each state index to the
        list of state indices reachable directly from it (foreign-DLG and
        terminating transitions are excluded).

        Useful for cycle detection, reachability analysis, and visualisation.
        """
        adj: Dict[int, List[int]] = {i: [] for i in range(len(self.states))}
        for si, state in enumerate(self.states):
            for j in range(state.transition_count):
                ti    = state.first_transition_index + j
                trans = self.transitions[ti]
                if not trans.terminates and not trans.next_dlg:
                    adj[si].append(trans.next_state_index)
        return adj

    def reachable_states(self, start: int = 0) -> List[int]:
        """
        Return the list of state indices reachable from *start* via
        same-DLG links (BFS order).
        """
        visited: List[int] = []
        queue   = [start]
        seen    = {start}
        adj     = self.adjacency()
        while queue:
            current = queue.pop(0)
            visited.append(current)
            for nxt in adj.get(current, []):
                if nxt not in seen and nxt < len(self.states):
                    seen.add(nxt)
                    queue.append(nxt)
        return visited

    def external_links(self) -> List[Tuple[int, int, str, int]]:
        """
        Return all transitions that jump to a foreign DLG file::

            (state_index, transition_index, foreign_dlg_resref, foreign_state_index)
        """
        result = []
        for si, state in enumerate(self.states):
            for j in range(state.transition_count):
                ti    = state.first_transition_index + j
                trans = self.transitions[ti]
                if trans.next_dlg:
                    result.append((si, ti, trans.next_dlg, trans.next_state_index))
        return result

    def cycles(self) -> List[List[int]]:
        """
        Return a list of simple cycles in the same-DLG state graph.

        Uses DFS with path tracking.  Each returned cycle is a list of
        state indices forming a loop.

        Note: IE dialogue trees frequently have intentional loops (e.g.
        "I don't know what you mean" looping back to the opening).
        """
        adj     = self.adjacency()
        cycles_found: List[List[int]] = []
        visited = set()
        path: List[int] = []
        path_set: set = set()

        def _dfs(node: int) -> None:
            visited.add(node)
            path.append(node)
            path_set.add(node)
            for nxt in adj.get(node, []):
                if nxt in path_set:
                    cycle_start = path.index(nxt)
                    cycles_found.append(list(path[cycle_start:]))
                elif nxt not in visited:
                    _dfs(nxt)
            path.pop()
            path_set.discard(node)

        for i in range(len(self.states)):
            if i not in visited:
                _dfs(i)

        return cycles_found

    # ------------------------------------------------------------------
    # Script string access
    # ------------------------------------------------------------------

    def all_triggers(self) -> List[Tuple[str, List[Tuple[str, str]]]]:
        """
        Return a list of (raw_string, parsed_tokens) for every unique
        state trigger and transition trigger in the file.

        Useful for a quick overview of what conditions the dialogue tests.
        """
        result = []
        seen   = set()
        for raw in (*self.state_triggers, *self.transition_triggers):
            if raw and raw not in seen:
                seen.add(raw)
                result.append((raw, _parse_script_string(raw)))
        return result

    def all_actions(self) -> List[Tuple[str, List[Tuple[str, str]]]]:
        """
        Return a list of (raw_string, parsed_tokens) for every unique
        action string in the file.
        """
        result = []
        seen   = set()
        for raw in self.actions:
            if raw and raw not in seen:
                seen.add(raw)
                result.append((raw, _parse_script_string(raw)))
        return result

    # ------------------------------------------------------------------
    # Human-readable dump
    # ------------------------------------------------------------------

    def dump(self, tlk=None) -> str:
        """
        Return a human-readable text dump of the entire dialogue tree.

        If *tlk* is a :class:`~core.formats.tlk.TlkFile` instance, StrRefs
        are resolved to their text; otherwise StrRef numbers are printed.

        Useful for quick inspection without a GUI::

            print(dlg.dump())
            print(dlg.dump(tlk=my_tlk))
        """
        def _str(strref: StrRef) -> str:
            if strref.is_none:
                return "<none>"
            if tlk is not None:
                try:
                    return repr(tlk.get(int(strref)).text[:60])
                except Exception:
                    pass
            return f"#{strref}"

        lines: List[str] = []
        lines.append(f"DLG  {self.source_path.name if self.source_path else '?'}")
        lines.append(f"  {len(self.states)} states  "
                     f"{len(self.transitions)} transitions  "
                     f"{len(self.state_triggers)} state-triggers  "
                     f"{len(self.transition_triggers)} trans-triggers  "
                     f"{len(self.actions)} actions")
        lines.append("")

        for si, state in enumerate(self.states):
            trig_str = ""
            trigger  = state.get_trigger(self)
            if trigger:
                trig_str = f"  [IF: {trigger.strip()[:40]}]"
            lines.append(f"STATE {si}{trig_str}")
            lines.append(f"  NPC: {_str(state.text_strref)}")
            for j in range(state.transition_count):
                ti    = state.first_transition_index + j
                trans = self.transitions[ti]

                parts = [f"  -> T{ti}"]
                if trans.has_text:
                    parts.append(f"PC: {_str(trans.text_strref)}")
                if trans.terminates:
                    parts.append("[END]")
                elif trans.next_dlg:
                    parts.append(f"=> {trans.next_dlg}#{trans.next_state_index}")
                else:
                    parts.append(f"=> STATE {trans.next_state_index}")
                if trans.has_trigger:
                    traw = trans.get_trigger(self) or ""
                    parts.append(f"[IF: {traw.strip()[:30]}]")
                if trans.has_action:
                    araw = trans.get_action(self) or ""
                    parts.append(f"[DO: {araw.strip()[:30]}]")
                lines.append("  " + "  ".join(parts))
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    def add_state(self, text_strref: int,
                  trigger: Optional[str] = None) -> int:
        """
        Append a new state and return its index.

        If *trigger* is given it is added to the state-trigger table and
        the state's trigger_index is set accordingly.
        """
        trig_idx = NO_INDEX
        if trigger is not None:
            trig_idx = len(self.state_triggers)
            self.state_triggers.append(trigger)
        state = State(
            text_strref=text_strref,
            first_transition_index=len(self.transitions),
            transition_count=0,
            trigger_index=trig_idx,
        )
        self.states.append(state)
        return len(self.states) - 1

    def add_transition(
        self,
        from_state_index: int,
        text_strref:      StrRef = StrRef(0xFFFFFFFF),
        next_state_index: int = 0,
        next_dlg:         str = "",
        terminates:       bool = False,
        trigger:          Optional[str] = None,
        action:           Optional[str] = None,
        journal_strref:   StrRef = StrRef(0xFFFFFFFF),
    ) -> int:
        """
        Append a transition to *from_state_index* and return the
        transition index.

        The owning state's ``transition_count`` is incremented.  States are
        expected to have been built in order so that
        ``first_transition_index + transition_count`` always points to the
        end of the transition list — i.e. add all transitions for a state
        before moving to the next.
        """
        flags = TransitionFlag.NONE
        if not text_strref.is_none:
            flags |= TransitionFlag.HAS_TEXT

        trig_idx = NO_INDEX
        if trigger is not None:
            flags |= TransitionFlag.HAS_TRIGGER
            trig_idx = len(self.transition_triggers)
            self.transition_triggers.append(trigger)

        action_idx = NO_INDEX
        if action is not None:
            flags |= TransitionFlag.HAS_ACTION
            action_idx = len(self.actions)
            self.actions.append(action)

        if terminates:
            flags |= TransitionFlag.TERMINATES

        trans = Transition(
            flags=flags,
            text_strref=text_strref,
            journal_strref=journal_strref,
            trigger_index=trig_idx,
            action_index=action_idx,
            next_dlg=next_dlg,
            next_state_index=next_state_index,
        )
        self.transitions.append(trans)
        self.states[from_state_index].transition_count += 1
        return len(self.transitions) - 1

    @classmethod
    def new(cls, flags: int = 0) -> "DlgFile":
        """Create a new empty DLG file ready for states and transitions."""
        return cls(
            header=DlgHeader(flags=flags),
            states=[], transitions=[],
            state_triggers=[], transition_triggers=[], actions=[],
        )

    # ------------------------------------------------------------------
    # Informational
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        src = self.source_path.name if self.source_path else "?"
        return (
            f"<DlgFile {src!r} "
            f"states={len(self.states)} "
            f"transitions={len(self.transitions)}>"
        )


# ---------------------------------------------------------------------------
# Public re-exports for convenience
# ---------------------------------------------------------------------------

parse_script_string = _parse_script_string
format_trigger      = _format_trigger
format_action       = _format_action
