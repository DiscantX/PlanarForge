"""
ui/skin/infinity/screen_panel.py

DearPyGui widget that renders an Infinity Engine game screen emulation:
  - MOS background composited onto a drawlist
  - Item icons drawn at slot positions derived from ChuLayout
  - Hover tooltip showing slot name + item name
  - Optional highlight rect on hover

This is the "Game Screen" mode for CharacterEditorPanel.  It replaces the
card-list draw_inventory_slot_card approach with a spatially accurate
reproduction of the in-game inventory/record screen.

Usage (inside a DearPyGui layout)::

    panel = InfinityScreenPanel(
        parent_tag="some_child_window",
        assets=skin_assets,
        tag_prefix="inv_screen",
    )

    # When a character is loaded:
    panel.render(layout, slot_items)

    # slot_items maps slot_name -> InventorySlotVM
    # layout is a ChuLayout (from ChuLayout.from_chu or .make_fallback)

Architecture notes:
    - One dpg.add_drawlist per render; the old one is deleted and recreated.
    - All textures go through InfinitySkinAssets for lifetime management.
    - Hover detection uses dpg item handlers on invisible selectables
      overlaid on each slot rect.
"""

from __future__ import annotations

from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from core.viewmodels.character_vm import InventorySlotVM
from ui.skin.infinity.assets import InfinitySkinAssets
from ui.skin.infinity.chu_layout import ChuLayout, SlotRect


# Pixel inset applied when drawing an item icon inside a slot rect.
_ICON_INSET = 4

# RGBA colour for the slot hover highlight (gold tint, semi-transparent).
_HOVER_COLOUR = (220, 190, 80, 120)

# RGBA colour for an empty slot indicator border.
_EMPTY_COLOUR = (80, 80, 80, 100)


class InfinityScreenPanel:
    """
    A composited game-screen panel backed by ChuLayout + InfinitySkinAssets.

    The panel owns one DearPyGui child_window containing a single drawlist.
    Calling render() tears down the previous drawlist and builds a new one
    — this is intentional: slot positions change between games and CHU files,
    so a full rebuild is simpler and cheaper than incremental diffing.
    """

    def __init__(
        self,
        parent_tag: str | int,
        assets: InfinitySkinAssets,
        *,
        tag_prefix: str = "ie_screen",
        on_slot_clicked: Optional[Callable[[str, Optional[InventorySlotVM]], None]] = None,
    ) -> None:
        """
        Args:
            parent_tag:       DearPyGui tag of the parent container.
            assets:           InfinitySkinAssets instance for texture management.
            tag_prefix:       Unique prefix for all DearPyGui tags created here.
            on_slot_clicked:  Optional callback(slot_name, slot_vm_or_None).
        """
        self._assets          = assets
        self._tag_prefix      = tag_prefix
        self._on_slot_clicked = on_slot_clicked

        self._root_tag        = f"{tag_prefix}__root"
        self._drawlist_tag    = f"{tag_prefix}__dl"
        self._overlay_tag     = f"{tag_prefix}__overlay"

        self._current_layout: Optional[ChuLayout] = None
        self._slot_items:     dict[str, InventorySlotVM] = {}
        self._hover_slot:     Optional[str] = None
        self._counter         = 0
        self._panel_width     = 640
        self._panel_height    = 480

        # Build the container — a borderless child window that we size to
        # match the MOS background each time render() is called.
        with dpg.child_window(
            tag=self._root_tag,
            parent=parent_tag,
            border=False,
            no_scrollbar=False,
        ):
            pass  # content added by render()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_size(self, width: int, height: int) -> None:
        """Resize the root window; re-renders if a layout is loaded."""
        self._panel_width  = max(64, width)
        self._panel_height = max(64, height)
        if dpg.does_item_exist(self._root_tag):
            dpg.configure_item(self._root_tag, width=self._panel_width, height=self._panel_height)
        if self._current_layout is not None:
            self._rebuild(self._current_layout, self._slot_items)

    def render(
        self,
        layout: ChuLayout,
        slot_items: dict[str, InventorySlotVM],
    ) -> None:
        """
        (Re)build the drawlist for the given layout and slot contents.

        Args:
            layout:     ChuLayout with window geometry and slot rects.
            slot_items: Maps slot_name → InventorySlotVM (may be partial).
        """
        self._current_layout = layout
        self._slot_items      = slot_items
        self._assets.begin_frame()
        self._rebuild(layout, slot_items)

    def clear(self) -> None:
        """Remove all content and reset to an empty state."""
        self._teardown()
        self._current_layout = None
        self._slot_items     = {}

    # ------------------------------------------------------------------
    # Internal build / teardown
    # ------------------------------------------------------------------

    def _teardown(self) -> None:
        """Delete any previously created drawlist and overlay."""
        for tag in (self._drawlist_tag, self._overlay_tag):
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

    def _rebuild(
        self,
        layout: ChuLayout,
        slot_items: dict[str, InventorySlotVM],
    ) -> None:
        self._teardown()

        w = self._panel_width
        h = self._panel_height

        # Scale CHU slot coordinates to fit the available panel.
        # CHU positions are in the native game window space (e.g. 864x710);
        # we need to map them into our panel without clipping any slots.
        lw = max(1, layout.window_width)
        lh = max(1, layout.window_height)
        scale = min(w / lw, h / lh, 1)   # never upscale past 1:1

        # Build scaled layout if needed
        if scale < 0.999:
            from ui.skin.infinity.chu_layout import SlotRect, ChuLayout as _CL
            scaled_slots = {
                name: SlotRect(
                    x=int(rect.x * scale),
                    y=int(rect.y * scale),
                    width=max(8, int(rect.width * scale)),
                    height=max(8, int(rect.height * scale)),
                )
                for name, rect in layout.slots.items()
            }
            # for item in layout.slots:
            #     print(item, layout.slots[item])

            layout = _CL(
                background_mos=layout.background_mos,
                window_x=layout.window_x,
                window_y=layout.window_y,
                window_width=int(lw * scale),
                window_height=int(lh * scale),
                slots=scaled_slots,
            )

        # Resize the root child_window to match the panel
        dpg.configure_item(self._root_tag, width=w, height=h)

        # --- Drawlist: background + slot contents ---
        dl = dpg.add_drawlist(
            tag=self._drawlist_tag,
            parent=self._root_tag,
            width=w,
            height=h,
        )

        # 1. MOS background
        if layout.background_mos:
            bg = self._assets.get_mos_texture(layout.background_mos)
            if bg is not None:
                bg_tag, bw, bh = bg
                dpg.draw_image(bg_tag, pmin=(0, 0), pmax=(w, h), parent=dl)
            else:
                self._draw_fallback_background(dl, w, h)
        else:
            self._draw_fallback_background(dl, w, h)

        # 2. Slot frames + item icons
        for slot_name, rect in layout.slots.items():
            vm = slot_items.get(slot_name)
            self._draw_slot(dl, slot_name, rect, vm)

        # --- Overlay: invisible selectables for hover/click ---
        self._build_overlay(layout, slot_items, w, h)

    def _draw_fallback_background(self, dl: int | str, w: int, h: int) -> None:
        """Draw a dark parchment-coloured fill when no MOS is available."""
        dpg.draw_rectangle(
            pmin=(0, 0), pmax=(w, h),
            fill=(28, 22, 14, 255),
            color=(60, 50, 30, 255),
            thickness=2,
            parent=dl,
        )
        # Subtle inner border
        dpg.draw_rectangle(
            pmin=(4, 4), pmax=(w - 4, h - 4),
            color=(90, 75, 45, 160),
            fill=(0, 0, 0, 0),
            thickness=1,
            parent=dl,
        )

    def _draw_slot(
        self,
        dl: int | str,
        slot_name: str,
        rect: SlotRect,
        vm: Optional[InventorySlotVM],
    ) -> None:
        x, y, sw, sh = rect.x, rect.y, rect.width, rect.height

        # Slot background frame
        frame = self._assets.get_slot_frame_texture()
        if frame is not None:
            frame_tag, fw, fh = frame
            dpg.draw_image(
                frame_tag,
                pmin=(x, y), pmax=(x + sw, y + sh),
                parent=dl,
            )
        else:
            # Fallback: plain dark rect with gold border
            dpg.draw_rectangle(
                pmin=(x, y), pmax=(x + sw, y + sh),
                fill=(20, 16, 10, 200),
                color=(130, 110, 60, 200),
                thickness=1,
                parent=dl,
            )

        if vm is None or vm.item_resref == "":
            # Empty slot — draw a subtle dot to indicate it's interactive
            cx, cy = rect.centre
            dpg.draw_circle(
                center=(cx, cy), radius=3,
                color=_EMPTY_COLOUR, fill=_EMPTY_COLOUR,
                parent=dl,
            )
            return

        # Item icon
        if vm.icon is not None:
            icon_tag, iw, ih = self._assets.texture_for_icon(vm.icon)
            inset = _ICON_INSET
            # Scale to fit inside the slot with inset, preserving aspect ratio
            avail_w = max(1, sw - inset * 2)
            avail_h = max(1, sh - inset * 2)
            scale = min(avail_w / max(1, iw), avail_h / max(1, ih))
            scale = max(scale, 0.5)
            draw_w = max(1, int(iw * scale))
            draw_h = max(1, int(ih * scale))
            ox = x + inset + (avail_w - draw_w) // 2
            oy = y + inset + (avail_h - draw_h) // 2
            dpg.draw_image(
                icon_tag,
                pmin=(ox, oy),
                pmax=(ox + draw_w, oy + draw_h),
                parent=dl,
            )

    def _build_overlay(
        self,
        layout: ChuLayout,
        slot_items: dict[str, InventorySlotVM],
        panel_w: int,
        panel_h: int,
    ) -> None:
        """
        Create invisible DearPyGui buttons overlaid on each slot for
        hover tooltips and click handling.

        DearPyGui drawlists don't natively support per-region mouse events,
        so we place zero-alpha buttons at the exact slot coordinates inside
        a group that's absolutely positioned over the drawlist.
        """
        overlay_group = dpg.add_group(
            tag=self._overlay_tag,
            parent=self._root_tag,
        )
        # Shift the overlay back up to overlap the drawlist.
        # DearPyGui stacks items vertically by default; we use
        # set_item_pos to anchor the overlay at (0, 0) within the window.
        dpg.set_item_pos(self._overlay_tag, [0, 0])

        for slot_name, rect in layout.slots.items():
            self._counter += 1
            btn_tag = f"{self._tag_prefix}__slot_btn_{self._counter}"
            vm = slot_items.get(slot_name)

            btn = dpg.add_button(
                tag=btn_tag,
                parent=overlay_group,
                width=rect.width,
                height=rect.height,
                label="",
            )
            # Position precisely over the slot
            dpg.set_item_pos(btn_tag, [rect.x, rect.y])

            # Apply invisible style (alpha=0)
            with dpg.theme() as slot_theme:
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(
                        dpg.mvThemeCol_Button,
                        (0, 0, 0, 0),
                        category=dpg.mvThemeCat_Core,
                    )
                    dpg.add_theme_color(
                        dpg.mvThemeCol_ButtonHovered,
                        (220, 190, 80, 60),
                        category=dpg.mvThemeCat_Core,
                    )
                    dpg.add_theme_color(
                        dpg.mvThemeCol_ButtonActive,
                        (220, 190, 80, 100),
                        category=dpg.mvThemeCat_Core,
                    )
                    dpg.add_theme_color(
                        dpg.mvThemeCol_Border,
                        (0, 0, 0, 0),
                        category=dpg.mvThemeCat_Core,
                    )
            dpg.bind_item_theme(btn_tag, slot_theme)

            # Tooltip
            tooltip_lines = [slot_name.replace("_", " ").title()]
            if vm is not None:
                tooltip_lines.append(vm.item_name or vm.item_resref)
                if vm.item_resref:
                    tooltip_lines.append(f"({vm.item_resref})")
            with dpg.tooltip(btn_tag):
                for line in tooltip_lines:
                    dpg.add_text(line)

            # Click callback
            if self._on_slot_clicked is not None:
                _slot = slot_name
                _vm   = vm
                dpg.configure_item(
                    btn_tag,
                    callback=lambda s, a, u: self._on_slot_clicked(*u),
                    user_data=(_slot, _vm),
                )