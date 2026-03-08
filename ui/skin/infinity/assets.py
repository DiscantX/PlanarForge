"""
ui/skin/infinity/assets.py  (updated)

Adds:
  - get_mos_texture(resref) — persistent MOS background texture
  - get_chu_layout(game_id, chu_loader) — load + cache a ChuLayout for
    the current game's inventory screen
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from ui.skin.infinity.chu_layout import ChuLayout, ScreenControlMap


class InfinitySkinAssets:
    """Texture cache/loader for game-skin UI primitives."""

    def __init__(
        self,
        *,
        icon_loader: Callable[[str], tuple[int, int, list[float]] | None],
        mos_loader: Callable[[str], tuple[int, int, list[float]] | None],
        chu_loader: Callable[[str], bytes | None] | None = None,
        texture_parent: str = "window_icon_textures",
    ) -> None:
        self._icon_loader = icon_loader
        self._mos_loader  = mos_loader
        self._chu_loader  = chu_loader
        self._texture_parent = texture_parent

        self._manifest: dict[str, str] = {
            "slot_frame_icon_resref": "",
            "slot_frame_mos_resref":  "",
        }
        self._persistent_tags: dict[str, tuple[str, int, int]] = {}
        self._transient_tags:  list[str] = []
        self._counter = 0

        # Cache: resref → ChuLayout (one per game, reset on game change)
        self._chu_layout_cache: dict[str, ChuLayout] = {}

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def load_manifest_file(self, path: str | Path) -> None:
        p = Path(path)
        if not p.is_file():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._manifest.update({k: str(v) for k, v in data.items()})
        except Exception:
            return

    def invalidate_chu_cache(self) -> None:
        """Call when the selected game changes so CHU layouts are reloaded."""
        self._chu_layout_cache.clear()

    # ------------------------------------------------------------------
    # Frame lifecycle
    # ------------------------------------------------------------------

    def begin_frame(self) -> None:
        self.clear_transient()

    def clear_transient(self) -> None:
        for tag in self._transient_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._transient_tags.clear()

    # ------------------------------------------------------------------
    # Slot frame texture (persistent)
    # ------------------------------------------------------------------

    def get_slot_frame_texture(self) -> tuple[str, int, int] | None:
        cached = self._persistent_tags.get("slot_frame")
        if cached is not None and dpg.does_item_exist(cached[0]):
            return cached

        icon_resref = self._manifest.get("slot_frame_icon_resref", "").strip().upper()
        mos_resref  = self._manifest.get("slot_frame_mos_resref",  "").strip().upper()

        icon = self._icon_loader(icon_resref) if icon_resref else None
        if icon is None and mos_resref:
            icon = self._mos_loader(mos_resref)
        if icon is None:
            icon = self._generate_fallback_frame()

        tag, width, height = self._add_texture(
            icon[0], icon[1], icon[2], persistent_key="slot_frame"
        )
        return tag, width, height

    # ------------------------------------------------------------------
    # MOS background texture (persistent, keyed by resref)
    # ------------------------------------------------------------------

    def get_mos_texture(self, resref: str) -> tuple[str, int, int] | None:
        """
        Load and cache a MOS texture.  Returns (tag, w, h) or None.

        Supports both palette-based (V1/MOSC) and PVRZ-based (V2) MOS files.
        For PVRZ MOS files, attempts to decode using available decoders.  If
        PVRTC decoding is unavailable, uses a fallback placeholder pattern.
        """
        key = f"mos_{resref.upper()}"
        cached = self._persistent_tags.get(key)
        if cached is not None and dpg.does_item_exist(cached[0]):
            return cached

        img = self._mos_loader(resref)
        if img is None:
            return None

        tag, w, h = self._add_texture(img[0], img[1], img[2], persistent_key=key)
        return tag, w, h

    # ------------------------------------------------------------------
    # Item icon texture (transient)
    # ------------------------------------------------------------------

    def texture_for_icon(self, icon: tuple[int, int, list[float]]) -> tuple[str, int, int]:
        width, height, rgba = icon
        tag, w, h = self._add_texture(width, height, rgba, persistent_key=None)
        return tag, w, h

    # ------------------------------------------------------------------
    # CHU layout (cached per CHU resref)
    # ------------------------------------------------------------------

    def get_chu_layout(self, game_id: str) -> ChuLayout:
        """
        Return a ChuLayout for the given game's inventory screen.

        Tries to load the CHU via chu_loader; falls back to a synthesised
        grid layout if the CHU is unavailable or unparseable.
        """
        from core.formats.chu import ChuFile

        screen_def = ScreenControlMap.for_game(game_id)
        cache_key  = f"{game_id.upper()}:{screen_def.chu_resref}"

        if cache_key in self._chu_layout_cache:
            return self._chu_layout_cache[cache_key]

        layout: Optional[ChuLayout] = None
        chu_source = "none"

        if self._chu_loader is not None:
            try:
                raw = self._chu_loader(screen_def.chu_resref)
                if raw is None:
                    print(f"[ChuLayout] CHU not found in KEY: {screen_def.chu_resref!r}")
                else:
                    chu    = ChuFile.from_bytes(raw)
                    layout = ChuLayout.from_chu(chu, screen_def)
                    slot_count = len(layout.slots)
                    chu_source = f"CHU ({slot_count} slots resolved)"
                    if slot_count == 0:
                        # CHU parsed but none of the expected control IDs matched —
                        # dump what window IDs and control IDs actually exist so we
                        # can correct the ScreenControlMap.
                        window = chu.find_window(screen_def.window_id)
                        if window is None:
                            print(f"[ChuLayout]   window_id={screen_def.window_id} not found; "
                                  f"available: {[w.window_id for w in chu.windows]}")
                        else:
                            actual_ids = [c.control_id for c in window.controls]
                            expected_ids = list(screen_def.slot_control_ids.values())
                            print(f"[ChuLayout]   window {screen_def.window_id} has "
                                  f"{len(window.controls)} controls: {actual_ids[:20]}")
                            print(f"[ChuLayout]   expected control IDs: {expected_ids[:20]}")
            except Exception as exc:
                print(f"[ChuLayout] Error loading {screen_def.chu_resref!r}: {exc}")

        if layout is None or not layout.slots:
            print(f"[ChuLayout] Using fallback grid for {game_id!r} (source={chu_source})")
            layout = ChuLayout.make_fallback(screen_def)

        self._chu_layout_cache[cache_key] = layout
        return layout

    # ------------------------------------------------------------------
    # Internal texture helpers
    # ------------------------------------------------------------------

    def _add_texture(
        self,
        width: int,
        height: int,
        rgba: list[float],
        *,
        persistent_key: str | None,
    ) -> tuple[str, int, int]:
        self._counter += 1
        tag = f"infinity_skin_tex_{self._counter}"
        dpg.add_static_texture(
            width=max(1, int(width)),
            height=max(1, int(height)),
            default_value=rgba,
            tag=tag,
            parent=self._texture_parent,
        )
        if persistent_key is not None:
            old = self._persistent_tags.get(persistent_key)
            if old and dpg.does_item_exist(old[0]):
                dpg.delete_item(old[0])
            self._persistent_tags[persistent_key] = (
                tag, max(1, int(width)), max(1, int(height))
            )
        else:
            self._transient_tags.append(tag)
        return tag, max(1, int(width)), max(1, int(height))

    @staticmethod
    def _generate_fallback_frame() -> tuple[int, int, list[float]]:
        size   = 36
        border = (0.78, 0.72, 0.48, 1.0)
        fill   = (0.17, 0.14, 0.10, 1.0)
        rgba: list[float] = []
        for y in range(size):
            for x in range(size):
                if x in (0, 1, size - 2, size - 1) or y in (0, 1, size - 2, size - 1):
                    rgba.extend(border)
                else:
                    rgba.extend(fill)
        return size, size, rgba