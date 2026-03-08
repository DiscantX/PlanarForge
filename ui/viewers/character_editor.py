from __future__ import annotations

from pathlib import Path

import dearpygui.dearpygui as dpg

from core.services.character_service import CharacterService
from core.viewmodels.character_vm import CharacterVM
from ui.skin.infinity import InfinitySkinAssets, draw_inventory_slot_card


class CharacterEditorPanel:
    """Read-only character screen scaffold backed by CharacterService."""

    def __init__(self, parent_tag: str, service: CharacterService, *, tag_prefix: str = "char_editor") -> None:
        self.service = service
        self.tag_prefix = tag_prefix

        self.root_tag = self._tag("root")
        self.top_tag = self._tag("top")
        self.body_tag = self._tag("body")
        self.left_tag = self._tag("left")
        self.right_tag = self._tag("right")
        self.status_tag = self._tag("status")
        self.game_combo_tag = self._tag("game_combo")
        self.search_tag = self._tag("search")
        self.layout_combo_tag = self._tag("layout_combo")
        self.character_table_tag = self._tag("character_table")
        self.summary_tag = self._tag("summary")
        self.stats_table_tag = self._tag("stats_table")
        self.inventory_tag = self._tag("inventory")
        self.overview_tag = self._tag("overview")
        self.raw_tree_tag = self._tag("raw_tree")
        self.raw_text_tag = self._tag("raw_text")
        self.raw_json_textbox_tag = self._tag("raw_json_textbox")

        self._game_ids: list[str] = []
        self._character_rows: list[tuple[str, str]] = []
        self._row_selectables: list[str] = []
        self._dynamic_texture_tags: list[str] = []
        self._texture_counter = 0
        self._current_vm: CharacterVM | None = None
        self._current_payload: dict | None = None

        self._skin_assets = InfinitySkinAssets(
            icon_loader=self.service.load_icon_by_resref,
            mos_loader=self.service.load_mos_by_resref,
        )
        manifest_path = Path("ui/skin/infinity/manifest_default.json")
        self._skin_assets.load_manifest_file(manifest_path)

        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            with dpg.group(tag=self.top_tag, horizontal=True):
                dpg.add_text("Game:")
                dpg.add_combo(tag=self.game_combo_tag, width=160, callback=self._on_game_selected)
                dpg.add_spacer(width=10)
                dpg.add_text("Find:")
                dpg.add_input_text(
                    tag=self.search_tag,
                    width=260,
                    hint="Search character by resref or name...",
                    callback=self._on_search_changed,
                )
                dpg.add_spacer(width=8)
                dpg.add_text("Layout:")
                dpg.add_combo(
                    tag=self.layout_combo_tag,
                    items=["Table", "Game Skin"],
                    default_value="Game Skin",
                    width=120,
                    callback=self._on_layout_changed,
                )
                dpg.add_button(label="Refresh", callback=self._on_refresh_clicked)
                dpg.add_button(label="Rebuild", callback=self._on_rebuild_clicked)
                dpg.add_spacer(width=16)
                dpg.add_text("", tag=self.status_tag)

            with dpg.group(tag=self.body_tag, horizontal=True):
                with dpg.child_window(tag=self.left_tag, border=True):
                    dpg.add_text("Character Browser")
                    with dpg.table(
                        tag=self.character_table_tag,
                        header_row=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        resizable=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        height=220,
                    ):
                        dpg.add_table_column(label="ResRef")
                        dpg.add_table_column(label="Name")

                with dpg.child_window(tag=self.right_tag, border=True):
                    with dpg.tab_bar():
                        with dpg.tab(label="Overview"):
                            with dpg.child_window(tag=self.overview_tag, border=False):
                                with dpg.group(tag=self.summary_tag):
                                    dpg.add_text("No character loaded.")
                                dpg.add_separator()
                                with dpg.table(
                                    tag=self.stats_table_tag,
                                    header_row=True,
                                    policy=dpg.mvTable_SizingStretchProp,
                                    row_background=True,
                                    borders_innerV=True,
                                    borders_outerV=True,
                                    borders_innerH=True,
                                    borders_outerH=True,
                                ):
                                    dpg.add_table_column(label="Stat")
                                    dpg.add_table_column(label="Value")
                                dpg.add_separator()
                                dpg.add_text("Inventory / Equipped")
                                dpg.add_separator()
                                with dpg.child_window(tag=self.inventory_tag, border=False):
                                    dpg.add_text("No items.")
                        with dpg.tab(label="JSON Tree"):
                            with dpg.child_window(tag=self.raw_tree_tag, border=False):
                                dpg.add_text("No character loaded.")
                        with dpg.tab(label="Raw JSON"):
                            with dpg.child_window(tag=self.raw_text_tag, border=False):
                                dpg.add_text("No character loaded.")

        self._load_games()

    def _tag(self, suffix: str) -> str:
        return f"{self.tag_prefix}_{suffix}"

    def set_size(self, width: int, height: int) -> None:
        dpg.configure_item(self.root_tag, width=max(0, width), height=max(0, height))
        top_h = 34
        body_h = max(0, height - top_h - 6)
        left_w = max(260, int(width * 0.42))
        right_w = max(260, width - left_w - 12)
        dpg.configure_item(self.left_tag, width=left_w, height=body_h)
        dpg.configure_item(self.right_tag, width=right_w, height=body_h)

    def _set_status(self, text: str) -> None:
        dpg.set_value(self.status_tag, text)

    def _load_games(self) -> None:
        games = self.service.list_games()
        self._game_ids = [g.game_id for g in games]
        dpg.configure_item(self.game_combo_tag, items=self._game_ids)
        if not self._game_ids:
            self._set_status("No game installations detected.")
            return
        dpg.set_value(self.game_combo_tag, self._game_ids[0])
        self._activate_game(self._game_ids[0])

    def _activate_game(self, game_id: str) -> None:
        try:
            self.service.select_game(game_id)
            self._set_status("Loading CRE index...")
            self.service.load_index(force_rebuild=False)
            self._set_status(f"Loaded CRE index for {game_id}")
            self._refresh_character_list("")
        except Exception as exc:
            self._set_status(f"Failed to select game: {exc}")

    def _on_game_selected(self, _sender, app_data) -> None:
        game_id = str(app_data or "")
        if game_id:
            self._activate_game(game_id)

    def _on_search_changed(self, _sender, app_data) -> None:
        self._refresh_character_list(str(app_data or ""))

    def _on_refresh_clicked(self) -> None:
        query = str(dpg.get_value(self.search_tag) or "")
        try:
            self.service.load_index(force_rebuild=False)
        except Exception as exc:
            self._set_status(f"Refresh failed: {exc}")
            return
        self._refresh_character_list(query)

    def _on_rebuild_clicked(self) -> None:
        query = str(dpg.get_value(self.search_tag) or "")
        try:
            self._set_status("Rebuilding CRE index...")
            self.service.load_index(force_rebuild=True)
        except Exception as exc:
            self._set_status(f"Rebuild failed: {exc}")
            return
        self._refresh_character_list(query)

    def _on_layout_changed(self, _sender, app_data) -> None:
        _layout = str(app_data or "Table")
        if self._current_vm is not None and self._current_payload is not None:
            try:
                self._render_character(self._current_vm, self._current_payload)
            except Exception as exc:
                self._set_status(f"Layout render failed: {exc}")

    def _refresh_character_list(self, query: str) -> None:
        try:
            self._character_rows = self.service.search_characters(query)
        except Exception as exc:
            self._set_status(f"Character list failed: {exc}")
            self._character_rows = []

        dpg.delete_item(self.character_table_tag, children_only=True, slot=1)
        self._row_selectables = []
        if not self._character_rows:
            self._set_status("No matching characters.")
            return
        for idx, (resref, name) in enumerate(self._character_rows):
            row_tag = self._tag(f"character_row_{idx}")
            self._row_selectables.append(row_tag)
            with dpg.table_row(parent=self.character_table_tag):
                dpg.add_selectable(
                    tag=row_tag,
                    label=resref,
                    span_columns=True,
                    callback=self._on_character_selected,
                    user_data=idx,
                    height=22,
                )
                dpg.add_text(name)

    def _on_character_selected(self, _sender, app_data, user_data) -> None:
        if not bool(app_data):
            return
        try:
            idx = int(user_data)
        except Exception:
            return
        if idx < 0 or idx >= len(self._character_rows):
            return
        for i, tag in enumerate(self._row_selectables):
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, i == idx)
        resref, _name = self._character_rows[idx]
        self.load_character(resref)

    def load_character(self, cre_resref: str) -> None:
        try:
            vm, payload = self.service.load_character_with_payload(cre_resref)
            self._render_character(vm, payload)
            self._set_status(f"Loaded {vm.display_name} ({vm.resref})")
        except Exception as exc:
            self._set_status(f"Load failed: {exc}")
            self._render_empty()

    def _render_empty(self) -> None:
        self._current_vm = None
        self._current_payload = None
        dpg.delete_item(self.summary_tag, children_only=True)
        dpg.add_text("No character loaded.", parent=self.summary_tag)
        dpg.delete_item(self.stats_table_tag, children_only=True, slot=1)
        dpg.delete_item(self.inventory_tag, children_only=True)
        dpg.add_text("No items.", parent=self.inventory_tag)
        dpg.delete_item(self.raw_tree_tag, children_only=True)
        dpg.add_text("No character loaded.", parent=self.raw_tree_tag)
        dpg.delete_item(self.raw_text_tag, children_only=True)
        dpg.add_text("No character loaded.", parent=self.raw_text_tag)

    def _render_character(self, vm: CharacterVM, payload: dict) -> None:
        self._current_vm = vm
        self._current_payload = payload
        dpg.delete_item(self.summary_tag, children_only=True)
        dpg.add_text(vm.display_name, parent=self.summary_tag)
        dpg.add_text(f"ResRef: {vm.resref}", parent=self.summary_tag)
        dpg.add_text(
            f"{vm.race}  |  {vm.klass}  |  {vm.gender}  |  {vm.alignment}",
            parent=self.summary_tag,
        )
        dpg.add_text(f"Level {vm.level}  |  HP {vm.hp_current}/{vm.hp_max}", parent=self.summary_tag)

        dpg.delete_item(self.stats_table_tag, children_only=True, slot=1)
        for stat in vm.stats:
            with dpg.table_row(parent=self.stats_table_tag):
                dpg.add_text(stat.label)
                dpg.add_text(stat.value)

        self._clear_dynamic_textures()
        self._skin_assets.begin_frame()
        dpg.delete_item(self.inventory_tag, children_only=True)
        if not vm.inventory:
            dpg.add_text("No equipped/inventory items.", parent=self.inventory_tag)
            return
        layout = str(dpg.get_value(self.layout_combo_tag) or "Table") if dpg.does_item_exist(self.layout_combo_tag) else "Table"
        if layout == "Game Skin":
            for slot in vm.inventory:
                draw_inventory_slot_card(
                    parent=self.inventory_tag,
                    assets=self._skin_assets,
                    slot_name=slot.slot_name,
                    item_name=slot.item_name,
                    item_resref=slot.item_resref,
                    item_icon=slot.icon,
                )
        else:
            for slot in vm.inventory:
                with dpg.group(parent=self.inventory_tag, horizontal=True):
                    if slot.icon is not None:
                        tex = self._create_dynamic_texture(*slot.icon)
                        width, height, _ = slot.icon
                        draw_w = max(16, width)
                        draw_h = max(16, height)
                        self._add_image_with_fullsize_tooltip(
                            texture_tag=tex,
                            draw_width=draw_w,
                            draw_height=draw_h,
                            full_width=width,
                            full_height=height,
                        )
                    else:
                        dpg.add_spacer(width=16)
                    dpg.add_text(f"{slot.slot_name}: {slot.item_name} ({slot.item_resref})")

        self._render_raw(payload)

    def _render_raw(self, payload: dict) -> None:
        dpg.delete_item(self.raw_tree_tag, children_only=True)
        with dpg.tree_node(label="character", parent=self.raw_tree_tag, default_open=True):
            self._render_object(parent=dpg.last_item(), value=payload, default_open=False)

        import json
        raw_json = json.dumps(payload, ensure_ascii=False, indent=2)
        dpg.delete_item(self.raw_text_tag, children_only=True)
        dpg.add_input_text(
            tag=self.raw_json_textbox_tag,
            multiline=True,
            readonly=True,
            width=-1,
            height=-1,
            default_value=raw_json,
            parent=self.raw_text_tag,
        )

    def _render_json_node(self, parent: str | int, key: str, value, *, default_open: bool) -> None:
        if isinstance(value, dict):
            with dpg.tree_node(label=key, parent=parent, default_open=default_open):
                node_tag = dpg.last_item()
                self._render_object(parent=node_tag, value=value, default_open=default_open)
            return
        if isinstance(value, list):
            with dpg.tree_node(label=f"{key} [{len(value)}]", parent=parent, default_open=default_open):
                node_tag = dpg.last_item()
                for idx, item in enumerate(value):
                    self._render_json_node(parent=node_tag, key=f"[{idx}]", value=item, default_open=False)
            return
        dpg.add_text(f"{key}: {value}", parent=parent)

    def _render_object(self, parent: str | int, value, *, default_open: bool) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                self._render_json_node(parent=parent, key=str(key), value=item, default_open=default_open)
            return
        if isinstance(value, list):
            for idx, item in enumerate(value):
                self._render_json_node(parent=parent, key=f"[{idx}]", value=item, default_open=False)
            return
        dpg.add_text(str(value), parent=parent)

    def _create_dynamic_texture(self, width: int, height: int, rgba: list[float]) -> str:
        self._texture_counter += 1
        tag = self._tag(f"dyn_tex_{self._texture_counter}")
        dpg.add_static_texture(
            width=width,
            height=height,
            default_value=rgba,
            tag=tag,
            parent="window_icon_textures",
        )
        self._dynamic_texture_tags.append(tag)
        return tag

    def _clear_dynamic_textures(self) -> None:
        for tag in self._dynamic_texture_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._dynamic_texture_tags.clear()

    def _add_image_with_fullsize_tooltip(
        self,
        *,
        texture_tag: str,
        draw_width: int,
        draw_height: int,
        full_width: int,
        full_height: int,
    ) -> None:
        dpg.add_image(texture_tag, width=draw_width, height=draw_height)
        image_tag = dpg.last_item()
        with dpg.tooltip(parent=image_tag):
            min_tooltip_size = 48
            fw = max(1, int(full_width))
            fh = max(1, int(full_height))
            scale = max(1.0, min_tooltip_size / fw, min_tooltip_size / fh)
            tip_w = max(1, int(fw * scale))
            tip_h = max(1, int(fh * scale))
            dpg.add_image(texture_tag, width=tip_w, height=tip_h)
