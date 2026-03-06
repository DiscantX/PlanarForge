"""
game/string_manager.py

Manages TLK string table access for a game installation.

Handles the two-file system (dialog.tlk / dialogf.tlk), the difference
in file layout between original IE games and Enhanced Edition games, and
an optional mod override layer that sits on top of the base game strings.

TLK file layouts
----------------
Original games (BG1, BG2, IWD, IWD2, PST):
    <install_root>/dialog.tlk
    <install_root>/dialogf.tlk       (optional — non-English only)

Enhanced Edition games (BGEE, BG2EE, IWDEE, PSTEE):
    <install_root>/lang/<language>/dialog.tlk
    <install_root>/lang/<language>/dialogf.tlk   (optional)

Detection: if <install_root>/lang/ exists, assume EE layout.

Resolution order
----------------
When resolving a StrRef the following priority chain is used:

    Female strref (file_id == 1):
        mod_female → mod_male → base_female → base_male

    Male / default strref (file_id == 0):
        mod_male → base_male

Each step is skipped if that TlkFile is not loaded, or if the tlk_index
is out of range for it.  This mirrors the engine's own fallback behaviour.

Override TLKs
-------------
A mod project supplies its own TLK entries that override or extend the
base game strings.  Load them with set_mod_tlk(); remove with
clear_mod_tlk().  The base game TLKs are never modified.

Usage::

    from game.string_manager import StringManager
    from game.installation import InstallationFinder

    finder  = InstallationFinder()
    manager = StringManager.from_installation(finder.find("BG2EE"))

    # Resolve a StrRef (preferred path — manager picks the right TLK)
    from core.util.strref import StrRef
    ref  = StrRef(12345)
    text = ref.resolve_with(manager.get)     # "Leather Armour"

    # Or call manager.get directly
    text = manager.get(ref.file_id, ref.tlk_index)

    # Load a mod override layer
    from core.formats.tlk import TlkFile
    mod_tlk = TlkFile.from_file("my_mod/dialog.tlk")
    manager.set_mod_tlk(mod_tlk)

    # List available EE languages
    langs = StringManager.available_languages(finder.find("BG2EE"))
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from core.formats.tlk import TlkFile
from core.util.strref import FILE_ID_FEMALE, FILE_ID_MALE

if TYPE_CHECKING:
    from game.installation import GameInstallation


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class StringManagerError(Exception):
    """Raised when a TLK file cannot be located or loaded."""


# ---------------------------------------------------------------------------
# StringManager
# ---------------------------------------------------------------------------

class StringManager:
    """
    Manages TLK string table access with gender fallback and mod override.

    Hold one StringManager per open game installation.  Use
    from_installation() to construct from a GameInstallation, or supply
    TlkFile objects directly for testing.
    """

    def __init__(
        self,
        base_male:   TlkFile,
        base_female: Optional[TlkFile] = None,
        mod_male:    Optional[TlkFile] = None,
        mod_female:  Optional[TlkFile] = None,
    ) -> None:
        """
        Construct from pre-loaded TlkFile objects.

        base_male is required (every IE game has dialog.tlk).
        All others are optional.
        """
        self._base_male   = base_male
        self._base_female = base_female
        self._mod_male    = mod_male
        self._mod_female  = mod_female

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_installation(
        cls,
        inst:     "GameInstallation",
        language: str = "en_US",
    ) -> "StringManager":
        """
        Locate and load TLK files from a game installation.

        For EE games, *language* selects the subdirectory under lang/,
        e.g. ``"en_US"``, ``"es_ES"``.  It is ignored for original games,
        which have a single TLK in the install root regardless of locale.

        Raises StringManagerError if dialog.tlk cannot be found.
        """
        root = Path(inst.install_path)
        male_path, female_path = cls._find_tlk_paths(root, language)

        if not male_path.is_file():
            raise StringManagerError(
                f"dialog.tlk not found for {inst.game_id}. "
                f"Looked in: {male_path}"
            )

        base_male   = TlkFile.from_file(male_path)
        base_female = TlkFile.from_file(female_path) if female_path.is_file() else None

        return cls(base_male=base_male, base_female=base_female)

    @classmethod
    def _find_tlk_paths(
        cls,
        root:     Path,
        language: str,
    ) -> tuple[Path, Path]:
        """
        Return (male_path, female_path) for a game install root.

        Detects EE layout by the presence of a lang/ subdirectory.
        female_path may not exist on disk — callers must check.
        """
        lang_dir = root / "lang"
        if lang_dir.is_dir():
            # Enhanced Edition layout
            tlk_dir = lang_dir / language
        else:
            # Original game layout — single TLK in root
            tlk_dir = root

        return tlk_dir / "dialog.tlk", tlk_dir / "dialogf.tlk"

    # ------------------------------------------------------------------
    # Mod override management
    # ------------------------------------------------------------------

    def set_mod_tlk(
        self,
        male_tlk:   TlkFile,
        female_tlk: Optional[TlkFile] = None,
    ) -> None:
        """
        Load a mod override TLK layer.

        Mod strings take priority over base game strings in resolution.
        Call clear_mod_tlk() to remove the override.
        """
        self._mod_male   = male_tlk
        self._mod_female = female_tlk

    def clear_mod_tlk(self) -> None:
        """Remove the mod override layer; resolution falls back to base game."""
        self._mod_male   = None
        self._mod_female = None

    @property
    def has_mod_tlk(self) -> bool:
        """True if a mod override TLK is currently loaded."""
        return self._mod_male is not None

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def get(self, file_id: int, tlk_index: int) -> str:
        """
        Resolve a (file_id, tlk_index) pair to a string.

        This is the callable interface expected by StrRef.resolve_with():

            text = ref.resolve_with(manager.get)

        Resolution priority:
            Female (file_id == 1): mod_female → mod_male → base_female → base_male
            Male   (file_id == 0): mod_male → base_male

        Returns an empty string if the index is not found in any TLK.
        """
        is_female = (file_id == FILE_ID_FEMALE)

        if is_female:
            chain = [
                self._mod_female,
                self._mod_male,
                self._base_female,
                self._base_male,
            ]
        else:
            chain = [
                self._mod_male,
                self._base_male,
            ]

        for tlk in chain:
            if tlk is not None and tlk_index in tlk:
                text = tlk.get(tlk_index)
                if text:        # skip empty entries and fall through
                    return text

        return ""

    def get_entry(self, file_id: int, tlk_index: int):
        """
        Return the full TlkEntry for a (file_id, tlk_index) pair.

        Uses the same priority chain as get(), but returns the TlkEntry
        rather than just the text.  Useful when the caller also needs the
        sound ResRef or flags.

        Returns None if the index is not found in any TLK.
        """
        is_female = (file_id == FILE_ID_FEMALE)

        chain = (
            [self._mod_female, self._mod_male, self._base_female, self._base_male]
            if is_female else
            [self._mod_male, self._base_male]
        )

        for tlk in chain:
            if tlk is not None and tlk_index in tlk:
                entry = tlk.get_entry(tlk_index)
                if entry is not None and entry.text:
                    return entry

        return None

    def resolve(self, ref: "StrRef") -> str:  # type: ignore[name-defined]
        """
        Resolve a StrRef directly.

        Convenience wrapper around get() for callers that have a StrRef
        object rather than decoded (file_id, tlk_index) components.

            text = manager.resolve(item.identified_name)
        """
        from core.util.strref import StrRef
        if not isinstance(ref, StrRef):
            raise TypeError(f"Expected StrRef, got {type(ref).__name__!r}")
        if ref.is_none:
            return ""
        return self.get(ref.file_id, ref.tlk_index)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @staticmethod
    def available_languages(inst: "GameInstallation") -> List[str]:
        """
        Return a list of language codes available for an EE installation.

        Returns an empty list for original games (which have no lang/ dir).
        Each entry is a directory name under lang/, e.g. ``["en_US", "es_ES"]``.
        """
        lang_dir = Path(inst.install_path) / "lang"
        if not lang_dir.is_dir():
            return []
        return sorted(
            p.name for p in lang_dir.iterdir()
            if p.is_dir() and (p / "dialog.tlk").is_file()
        )

    @property
    def base_language_id(self) -> int:
        """The language ID stored in the base male TLK header."""
        return self._base_male.language_id

    @property
    def base_entry_count(self) -> int:
        """Number of entries in the base male TLK."""
        return len(self._base_male)

    def __repr__(self) -> str:
        parts = [f"base_male={len(self._base_male)} entries"]
        if self._base_female:
            parts.append(f"base_female={len(self._base_female)} entries")
        if self._mod_male:
            parts.append(f"mod_male={len(self._mod_male)} entries")
        if self._mod_female:
            parts.append(f"mod_female={len(self._mod_female)} entries")
        return f"StringManager({', '.join(parts)})"
