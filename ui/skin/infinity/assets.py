from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import dearpygui.dearpygui as dpg


class InfinitySkinAssets:
    """Texture cache/loader for game-skin UI primitives."""

    def __init__(
        self,
        *,
        icon_loader: Callable[[str], tuple[int, int, list[float]] | None],
        mos_loader: Callable[[str], tuple[int, int, list[float]] | None],
        texture_parent: str = "window_icon_textures",
    ) -> None:
        self._icon_loader = icon_loader
        self._mos_loader = mos_loader
        self._texture_parent = texture_parent

        self._manifest: dict[str, str] = {
            "slot_frame_icon_resref": "",
            "slot_frame_mos_resref": "",
        }
        self._persistent_tags: dict[str, tuple[str, int, int]] = {}
        self._transient_tags: list[str] = []
        self._counter = 0

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

    def begin_frame(self) -> None:
        self.clear_transient()

    def clear_transient(self) -> None:
        for tag in self._transient_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._transient_tags.clear()

    def get_slot_frame_texture(self) -> tuple[str, int, int]:
        cached = self._persistent_tags.get("slot_frame")
        if cached is not None and dpg.does_item_exist(cached[0]):
            return cached

        icon_resref = self._manifest.get("slot_frame_icon_resref", "").strip().upper()
        mos_resref = self._manifest.get("slot_frame_mos_resref", "").strip().upper()

        icon = self._icon_loader(icon_resref) if icon_resref else None
        if icon is None and mos_resref:
            icon = self._mos_loader(mos_resref)
        if icon is None:
            icon = self._generate_fallback_frame()

        tag, width, height = self._add_texture(icon[0], icon[1], icon[2], persistent_key="slot_frame")
        return tag, width, height

    def texture_for_icon(self, icon: tuple[int, int, list[float]]) -> tuple[str, int, int]:
        width, height, rgba = icon
        tag, w, h = self._add_texture(width, height, rgba, persistent_key=None)
        return tag, w, h

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
            self._persistent_tags[persistent_key] = (tag, max(1, int(width)), max(1, int(height)))
        else:
            self._transient_tags.append(tag)
        return tag, max(1, int(width)), max(1, int(height))

    @staticmethod
    def _generate_fallback_frame() -> tuple[int, int, list[float]]:
        size = 36
        border = (0.78, 0.72, 0.48, 1.0)
        fill = (0.17, 0.14, 0.10, 1.0)
        rgba: list[float] = []
        for y in range(size):
            for x in range(size):
                if x in (0, 1, size - 2, size - 1) or y in (0, 1, size - 2, size - 1):
                    rgba.extend(border)
                else:
                    rgba.extend(fill)
        return size, size, rgba
