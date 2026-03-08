from __future__ import annotations

import dearpygui.dearpygui as dpg

from ui.skin.infinity.assets import InfinitySkinAssets


def draw_inventory_slot_card(
    *,
    parent: str | int,
    assets: InfinitySkinAssets,
    slot_name: str,
    item_name: str,
    item_resref: str,
    item_icon: tuple[int, int, list[float]] | None,
) -> None:
    frame_tag, fw, fh = assets.get_slot_frame_texture()
    slot_w = max(36, fw)
    slot_h = max(36, fh)

    row_group = dpg.add_group(parent=parent, horizontal=True)
    draw_tag = dpg.add_drawlist(parent=row_group, width=slot_w, height=slot_h)
    dpg.draw_image(frame_tag, pmin=(0, 0), pmax=(slot_w, slot_h), parent=draw_tag)

    if item_icon is not None:
        icon_tag, iw, ih = assets.texture_for_icon(item_icon)
        max_inner_w = max(8, int(slot_w * 0.70))
        max_inner_h = max(8, int(slot_h * 0.70))
        scale = min(max_inner_w / max(1, iw), max_inner_h / max(1, ih))
        # Allow small icons to scale up for readability.
        scale = max(scale, 1.0)
        draw_w = max(1, int(iw * scale))
        draw_h = max(1, int(ih * scale))
        x = (slot_w - draw_w) // 2
        y = (slot_h - draw_h) // 2
        dpg.draw_image(icon_tag, pmin=(x, y), pmax=(x + draw_w, y + draw_h), parent=draw_tag)

    text_group = dpg.add_group(parent=row_group)
    dpg.add_text(slot_name, parent=text_group)
    dpg.add_text(f"{item_name} ({item_resref})", parent=text_group)
