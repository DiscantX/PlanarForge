"""
core/project/strref.py

ProjectStrRef — the project-layer string reference type.

This is distinct from core/util/strref.StrRef, which is a binary format
concern wrapping a raw uint32 as stored on disk.  ProjectStrRef is a project
data concern: it carries a string reference through the full lifecycle of a
mod project, from import through editing to WeiDU export.

Three variants
--------------
Discriminated by which fields are populated:

    Live reference      strref=N  strings={}
        An unmodified string from the primary game.  The integer index is
        sufficient — the string is resolved at display time from the active
        TLK.  At WeiDU export this emits the raw integer (the string already
        exists in the game's dialog.tlk; no .tra entry is needed).

    Imported snapshot   strref=N  strings={"en_US": "...", "fr_FR": "..."}
        A string whose text has been captured at import time (either because
        it came from a secondary game, whose StrRef indices are meaningless in
        the primary game's TLK, or because the user has modified the string).
        The original index is preserved for reference.  At export this emits
        a @N WeiDU placeholder and contributes an entry to every .tra file.

    Project-authored    strref=None  strings={"en_US": "...", "fr_FR": "..."}
        A string the user wrote from scratch, with no game original.
        At export this emits a @N WeiDU placeholder.

JSON representation
-------------------
    # Live reference
    {"strref": 15324}

    # Imported snapshot
    {"strref": 15324, "strings": {"en_US": "The Sword of Chaos"}}

    # Project-authored
    {"strings": {"en_US": "My New Item"}}

WeiDU export
------------
Live references: to_weidu_ref() returns the raw integer as a string, e.g.
"15324".  The string already lives in dialog.tlk; WeiDU doesn't need to
ship it.

Snapshots and authored strings: to_weidu_ref(assigned_index) returns
"@15324" where 15324 is the index assigned during the export pass.
The text is written to .tra files (one per language).

Usage::

    from core.project.strref import ProjectStrRef

    # Construct variants
    live      = ProjectStrRef.live(15324)
    snapshot  = ProjectStrRef.snapshot(15324, {"en_US": "Sword", "fr_FR": "Épée"})
    authored  = ProjectStrRef.authored({"en_US": "My Sword"})

    # Display
    text = live.resolve("en_US", string_manager)
    text = snapshot.resolve("fr_FR", string_manager)

    # Modify a live reference (promotes it to a snapshot)
    modified = live.with_text("en_US", "Better Sword")

    # Export
    ref_str = live.to_weidu_ref()           # "15324"
    ref_str = snapshot.to_weidu_ref(42)     # "@42"

    # JSON round-trip
    d    = snapshot.to_json()
    back = ProjectStrRef.from_json(d)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Runtime-free imports — ProjectStrRef carries no live references to
    # game objects.  Resolution is explicit and caller-supplied.
    from core.util.strref import StrRef
    from game.string_manager import StringManager


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ProjectStrRefError(ValueError):
    """Raised when a ProjectStrRef cannot be constructed or resolved."""


# ---------------------------------------------------------------------------
# ProjectStrRef
# ---------------------------------------------------------------------------

@dataclass
class ProjectStrRef:
    """
    A project-layer string reference.

    Carries a TLK string through import, editing, and WeiDU export.
    See module docstring for the three-variant design.

    Do not construct directly for the common cases — use the factory
    classmethods: live(), snapshot(), authored().
    """

    strref:  Optional[int]       # original game StrRef index; None = authored
    strings: dict[str, str]      # language_code → text; {} = live reference

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def live(cls, strref: int) -> "ProjectStrRef":
        """
        Construct a live reference.

        The string is not copied — it will be resolved from the game TLK
        at display time.  Use this for unmodified primary-game strings.
        """
        if not isinstance(strref, int) or strref < 0:
            raise ProjectStrRefError(
                f"live() requires a non-negative int strref, got {strref!r}."
            )
        return cls(strref=strref, strings={})

    @classmethod
    def snapshot(cls, strref: int, strings: dict[str, str]) -> "ProjectStrRef":
        """
        Construct an imported snapshot.

        *strings* must have at least one entry.  Use this for resources
        imported from secondary games, or for any string the user has
        modified.
        """
        if not isinstance(strref, int) or strref < 0:
            raise ProjectStrRefError(
                f"snapshot() requires a non-negative int strref, got {strref!r}."
            )
        if not strings:
            raise ProjectStrRefError(
                "snapshot() requires at least one entry in strings."
            )
        return cls(strref=strref, strings=dict(strings))

    @classmethod
    def authored(cls, strings: dict[str, str]) -> "ProjectStrRef":
        """
        Construct a project-authored string.

        *strings* must have at least one entry.  Use this for strings the
        user has written from scratch with no game original.
        """
        if not strings:
            raise ProjectStrRefError(
                "authored() requires at least one entry in strings."
            )
        return cls(strref=None, strings=dict(strings))

    @classmethod
    def from_util_strref(cls, ref: "StrRef") -> "ProjectStrRef":
        """
        Construct a live reference from a core/util StrRef.

        Convenience for the importer: converts a binary StrRef to the
        project live-reference variant.  The raw uint32 index is used
        directly; file_id bits are ignored since ProjectStrRef works at
        the project layer, not the binary layer.
        """
        return cls.live(ref.tlk_index if hasattr(ref, 'tlk_index') else int(ref))

    # ------------------------------------------------------------------
    # Variant predicates
    # ------------------------------------------------------------------

    @property
    def is_live(self) -> bool:
        """True if this is an unresolved live reference (no inline text)."""
        return self.strref is not None and not self.strings

    @property
    def is_snapshot(self) -> bool:
        """True if this is an imported snapshot (original index + inline text)."""
        return self.strref is not None and bool(self.strings)

    @property
    def is_authored(self) -> bool:
        """True if this is a project-authored string (no original index)."""
        return self.strref is None

    @property
    def needs_tra_entry(self) -> bool:
        """True if this string needs a .tra entry at WeiDU export time."""
        return not self.is_live

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def resolve(
        self,
        language:       str,
        string_manager: "StringManager",
        *,
        fallback_language: str = "en_US",
    ) -> str:
        """
        Return the human-readable text for *language*.

        Resolution order:
        1. Inline strings[language]          — exact language match
        2. Inline strings[fallback_language] — fallback (default en_US)
        3. Any inline string                 — last resort if no match
        4. string_manager.get()              — live reference only

        Returns an empty string if resolution fails entirely.
        """
        if self.strings:
            if language in self.strings:
                return self.strings[language]
            if fallback_language in self.strings:
                return self.strings[fallback_language]
            # Return the first available language as last resort
            return next(iter(self.strings.values()), "")

        # Live reference — delegate to string_manager
        if self.strref is not None:
            try:
                from core.util.strref import StrRef
                ref  = StrRef(self.strref)
                return string_manager.get(ref.file_id, ref.tlk_index)
            except Exception:
                return ""

        return ""

    def get_text(self, language: str) -> Optional[str]:
        """
        Return the inline text for *language*, or None if not present.

        Does not fall back to string_manager — use resolve() for display.
        Useful for checking whether a specific language has been set.
        """
        return self.strings.get(language)

    @property
    def languages(self) -> list[str]:
        """The language codes for which inline text is available."""
        return list(self.strings.keys())

    # ------------------------------------------------------------------
    # Mutation (returns new instance — ProjectStrRef is value-like)
    # ------------------------------------------------------------------

    def with_text(self, language: str, text: str) -> "ProjectStrRef":
        """
        Return a new ProjectStrRef with *text* set for *language*.

        If this is a live reference, promotes it to a snapshot.
        If this is a snapshot or authored string, adds/replaces the language.
        """
        new_strings = dict(self.strings)
        new_strings[language] = text
        return ProjectStrRef(strref=self.strref, strings=new_strings)

    def without_language(self, language: str) -> "ProjectStrRef":
        """
        Return a new ProjectStrRef with *language* removed from strings.

        Raises ProjectStrRefError if removing the language would leave an
        authored or snapshot ref with no strings (which is invalid).
        """
        if language not in self.strings:
            return self
        new_strings = {k: v for k, v in self.strings.items() if k != language}
        if not new_strings and not self.is_live:
            raise ProjectStrRefError(
                f"Cannot remove the last language from a "
                f"{'snapshot' if self.is_snapshot else 'authored'} ProjectStrRef."
            )
        return ProjectStrRef(strref=self.strref, strings=new_strings)

    def as_snapshot(self, strings: dict[str, str]) -> "ProjectStrRef":
        """
        Promote a live reference to a snapshot by attaching resolved strings.

        Raises ProjectStrRefError if called on a non-live reference.
        """
        if not self.is_live:
            raise ProjectStrRefError(
                "as_snapshot() can only be called on a live reference."
            )
        if not strings:
            raise ProjectStrRefError(
                "as_snapshot() requires at least one string entry."
            )
        return ProjectStrRef(strref=self.strref, strings=dict(strings))

    # ------------------------------------------------------------------
    # WeiDU export
    # ------------------------------------------------------------------

    def to_weidu_ref(self, assigned_index: Optional[int] = None) -> str:
        """
        Return the WeiDU string reference for this ProjectStrRef.

        Live references: returns the raw integer as a string, e.g. "15324".
        Snapshots / authored: returns "@N" where N is *assigned_index*.

        *assigned_index* is required (and must be non-negative) for
        non-live references.  It is assigned during the export pass by
        iterating all ProjectStrRefs that need .tra entries and numbering
        them sequentially.

        Raises ProjectStrRefError if assigned_index is missing or invalid
        for a non-live reference.
        """
        if self.is_live:
            assert self.strref is not None
            return str(self.strref)

        if assigned_index is None:
            raise ProjectStrRefError(
                "to_weidu_ref() requires assigned_index for non-live references."
            )
        if not isinstance(assigned_index, int) or assigned_index < 0:
            raise ProjectStrRefError(
                f"assigned_index must be a non-negative int, got {assigned_index!r}."
            )
        return f"@{assigned_index}"

    def to_tra_entry(self, assigned_index: int, language: str) -> str:
        """
        Return a single WeiDU .tra file line for this string.

        Format: ``@N = ~text~``

        Returns an empty string if this language is not available in
        the strings map (the caller should skip or use a fallback).
        """
        text = self.strings.get(language, "")
        if not text:
            return ""
        # Escape ~ in text (WeiDU uses ~ as delimiter; %% escapes to %)
        escaped = text.replace("~", "%%")
        return f"@{assigned_index} = ~{escaped}~"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self) -> dict:
        """
        Serialise to a JSON-compatible dict.

        Three possible forms (see module docstring):
            {"strref": N}
            {"strref": N, "strings": {...}}
            {"strings": {...}}
        """
        if self.is_live:
            return {"strref": self.strref}
        d: dict = {}
        if self.strref is not None:
            d["strref"] = self.strref
        d["strings"] = dict(self.strings)
        return d

    @classmethod
    def from_json(cls, d: int | dict) -> "ProjectStrRef":
        """
        Deserialise from a JSON value.

        Accepts:
        - A plain int — treated as a live reference (backwards compat with
          resource JSON that stores bare StrRef integers)
        - A dict in one of the three canonical forms

        Raises ProjectStrRefError on unrecognised input.
        """
        if isinstance(d, int):
            return cls.live(d)

        if not isinstance(d, dict):
            raise ProjectStrRefError(
                f"ProjectStrRef.from_json() expects int or dict, got {type(d).__name__!r}."
            )

        strref  = d.get("strref", None)
        strings = d.get("strings", {})

        if strref is None and not strings:
            raise ProjectStrRefError(
                "ProjectStrRef.from_json(): dict must have 'strref', 'strings', or both."
            )

        if strref is not None and not isinstance(strref, int):
            raise ProjectStrRefError(
                f"ProjectStrRef.from_json(): 'strref' must be int, got {type(strref).__name__!r}."
            )

        return cls(strref=strref, strings=dict(strings))

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        if self.is_live:
            return f"ProjectStrRef.live({self.strref})"
        if self.is_snapshot:
            langs = ", ".join(self.strings.keys())
            return f"ProjectStrRef.snapshot({self.strref}, [{langs}])"
        langs = ", ".join(self.strings.keys())
        return f"ProjectStrRef.authored([{langs}])"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ProjectStrRef):
            return self.strref == other.strref and self.strings == other.strings
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.strref, tuple(sorted(self.strings.items()))))
