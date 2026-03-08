from __future__ import annotations

from pathlib import Path

import dearpygui.dearpygui as dpg

from core.services.character_service import CharacterService
from core.viewmodels.character_vm import CharacterVM
from ui.skin.infinity import InfinitySkinAssets, draw_inventory_slot_card
from ui.skin.infinity.screen_panel import InfinityScreenPanel
from ui.core import EditorToolbar, ResourceBrowserPane


class CharacterEditorPanel:
    """Read-only character screen scaffold backed by CharacterService."""

    def __init__(self, parent_tag: str, service: CharacterService, *, tag_prefix: str = "char_editor") -> None:
        self.service = service
        self.tag_prefix = tag_prefix

        self.root_tag = self._tag("root")
        self.top_tag = self._tag("top")
        self.body_tag = self._tag("body")
        self.right_tag = self._tag("right")
        self.layout_combo_tag = self._tag("layout_combo")
        self.summary_tag = self._tag("summary")
        self.stats_table_tag = self._tag("stats_table")
        self.inventory_tag = self._tag("inventory")
        self.overview_tag = self._tag("overview")
        self.raw_tree_tag = self._tag("raw_tree")
        self.raw_text_tag = self._tag("raw_text")
        self.raw_json_textbox_tag = self._tag("raw_json_textbox")
        self.screen_tab_tag = self._tag("screen_tab")

        self._game_ids: list[str] = []
        self._character_rows: list[tuple[str, str]] = []
        self._dynamic_texture_tags: list[str] = []
        self._texture_counter = 0
        self._current_vm: CharacterVM | None = None
        self._current_payload: dict | None = None
        
        # Panel sizing state
        self._total_width: int = 0
        self._total_height: int = 0

        self._skin_assets = InfinitySkinAssets(
            icon_loader=self.service.load_icon_by_resref,
            mos_loader=self.service.load_mos_by_resref,
            bam_loader=self.service.load_bam_by_resref,
            chu_loader=self.service.load_chu_by_resref,
        )
        manifest_path = Path("ui/skin/infinity/data/manifest_default.json")
        self._skin_assets.load_manifest_file(manifest_path)

        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            # Create toolbar with layout combo as extra control
            def _add_layout_control(parent):
                dpg.add_spacer(width=8, parent=parent)
                dpg.add_text("Layout:", parent=parent)
                dpg.add_combo(
                    tag=self.layout_combo_tag,
                    items=["Table", "Game Skin"],
                    default_value="Game Skin",
                    width=120,
                    callback=self._on_layout_changed,
                    parent=parent,
                )

            self._toolbar = EditorToolbar(
                parent_tag=self.root_tag,
                games=[],
                on_game_selected=self._on_game_selected,
                on_refresh=self._on_refresh_clicked,
                on_rebuild=self._on_rebuild_clicked,
                tag_prefix=self._tag("toolbar"),
                extra_controls=_add_layout_control,
            )

            with dpg.group(tag=self.body_tag, horizontal=True):
                # Create the browser pane
                self._browser = ResourceBrowserPane(
                    parent_tag=self.body_tag,
                    columns=["ResRef", "Name"],
                    on_row_selected=self._on_character_selected,
                    tag_prefix=self._tag("browser"),
                )

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
                        with dpg.tab(label="Game Screen"):
                            with dpg.child_window(tag=self.screen_tab_tag, border=False, no_scrollbar=True):
                                pass

        self._screen_panel = InfinityScreenPanel(
            parent_tag=self.screen_tab_tag,
            assets=self._skin_assets,
            tag_prefix=self._tag("ie_screen"),
            on_slot_clicked=self._on_slot_clicked,
        )

        self._load_games()

    def _tag(self, suffix: str) -> str:
        return f"{self.tag_prefix}_{suffix}"

    def set_size(self, width: int, height: int) -> None:
        self._total_width = width
        self._total_height = height
        dpg.configure_item(self.root_tag, width=max(0, width), height=max(0, height))
        top_h = 34
        body_h = max(0, height - top_h - 6)
        
        # Update browser and right panel sizing
        self._browser.set_size(width, body_h)
        left_w = self._browser.get_panel_width()
        right_w = max(260, width - left_w - 12)
        
        dpg.configure_item(self.right_tag, width=right_w, height=body_h)
        # The screen tab child_window and its panel need explicit sizing too
        if dpg.does_item_exist(self.screen_tab_tag):
            dpg.configure_item(self.screen_tab_tag, width=right_w - 8, height=body_h - 28)
        self._screen_panel.set_size(right_w - 8, body_h - 28)

    def _set_status(self, text: str) -> None:
        self._toolbar.set_status(text)

    def _load_games(self) -> None:
        games = self.service.list_games()
        self._game_ids = [g.game_id for g in games]
        self._toolbar.set_games(self._game_ids)
        if not self._game_ids:
            self._set_status("No game installations detected.")
            return
        self._toolbar.set_game(self._game_ids[0])
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

    def _on_game_selected(self, game_id: str) -> None:
        if game_id:
            self._skin_assets.invalidate_chu_cache()
            self._screen_panel.clear()
            self._activate_game(game_id)

    def _on_refresh_clicked(self) -> None:
        try:
            self.service.load_index(force_rebuild=False)
        except Exception as exc:
            self._set_status(f"Refresh failed: {exc}")
            return
        self._refresh_character_list("")

    def _on_rebuild_clicked(self) -> None:
        try:
            self._set_status("Rebuilding CRE index...")
            self.service.load_index(force_rebuild=True)
        except Exception as exc:
            self._set_status(f"Rebuild failed: {exc}")
            return
        self._refresh_character_list("")

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

        self._browser.populate_rows(self._character_rows)
        if not self._character_rows:
            self._set_status("No matching characters.")
            return
        self._set_status(f"{len(self._character_rows)} character(s) found.")
        # Auto-select first row
        self._browser.select_row(0)
        self._on_character_selected(0)

    def _on_character_selected(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._character_rows):
            return
        self._browser.select_row(idx)
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
        self._render_game_screen(vm)

    def _render_game_screen(self, vm: CharacterVM) -> None:
        game_id = self._toolbar.get_game()
        layout = self._skin_assets.get_chu_layout(game_id)
        slot_items = {slot.slot_name: slot for slot in vm.inventory}
        self._screen_panel.render(layout, slot_items)

    def _on_slot_clicked(self, slot_name: str, vm) -> None:
        self._set_status(f"Clicked: {slot_name}" + (
            f" → {vm.item_name} ({vm.item_resref})" if vm else " (empty)"
        ))

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

    def handle_mouse_event(self) -> None:
        """Handle mouse events for panel resizing via drag on the divider."""
        if not dpg.does_item_exist(self.root_tag):
            return
        
        mouse_x, _mouse_y = dpg.get_mouse_pos()
        is_button_down = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        
        # Let the browser pane handle its divider drag
        self._browser.handle_divider_drag(mouse_x, is_button_down)
        
        # Update right panel sizing based on browser's new width
        if self._total_width > 0 and self._total_height > 0:
            left_w = self._browser.get_panel_width()
            right_w = max(260, self._total_width - left_w - 12)
            body_h = max(0, self._total_height - 34 - 6)
            dpg.configure_item(self.right_tag, width=right_w, height=body_h)
            if dpg.does_item_exist(self.screen_tab_tag):
                dpg.configure_item(self.screen_tab_tag, width=right_w - 8, height=body_h - 28)
            self._screen_panel.set_size(right_w - 8, body_h - 28)
