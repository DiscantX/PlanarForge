from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg

from core.services.itm_catalog import ItmCatalog
from core.util.resref import ResRef


class ItmViewerPanel:
    """Read-only ITM browser panel with list/search and structured/raw details."""

    def __init__(self, parent_tag: str, catalog: ItmCatalog, *, tag_prefix: str = "itm_viewer") -> None:
        self.catalog = catalog
        self.tag_prefix = tag_prefix

        self.root_tag = self._tag("root")
        self.top_bar_tag = self._tag("top")
        self.body_tag = self._tag("body")
        self.left_tag = self._tag("left")
        self.right_tag = self._tag("right")
        self.status_tag = self._tag("status")
        self.game_combo_tag = self._tag("game_combo")
        self.search_tag = self._tag("search")
        self.table_tag = self._tag("table")
        self.structured_tag = self._tag("structured")
        self.structured_table_tag = self._tag("structured_table")
        self.raw_tree_tag = self._tag("raw_tree")
        self.raw_text_tag = self._tag("raw_text")
        self.raw_json_textbox_tag = self._tag("raw_json_textbox")
        self.row_selectable_theme_tag = self._tag("row_selectable_theme")
        self.tooltip_theme_tag = self._tag("tooltip_theme")
        self.icon_texture_tag = self._tag("icon_texture")
        self.default_icon_texture_tag = self._tag("default_icon_texture")
        self.title_text_theme_tag = self._tag("title_text_theme")
        self.title_font_tag = self._tag("title_font")
        self._title_font_ready = False

        self._results: list[Any] = []
        self._game_ids: list[str] = []
        self._selected_game_id: str | None = None
        self._selected_index: int | None = None
        self._row_selectables: list[str] = []
        self._row_selectable_height = 26
        self._dynamic_texture_tags: list[str] = []
        self._texture_counter = 0

        with dpg.theme(tag=self.row_selectable_theme_tag):
            with dpg.theme_component(dpg.mvSelectable):
                dpg.add_theme_style(dpg.mvStyleVar_SelectableTextAlign, 0.0, 0.5)

        with dpg.theme(tag=self.tooltip_theme_tag):
            with dpg.theme_component(dpg.mvTooltip):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 10, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)

        with dpg.theme(tag=self.title_text_theme_tag):
            with dpg.theme_component(dpg.mvText):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 230, 255))

        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            with dpg.group(tag=self.top_bar_tag, horizontal=True):
                dpg.add_text("Game:")
                dpg.add_combo(
                    tag=self.game_combo_tag,
                    width=160,
                    callback=self._on_game_selected
                )
                dpg.add_button(label="Refresh", callback=self._on_refresh_clicked)
                dpg.add_button(label="Rebuild", callback=self._on_rebuild_clicked)
                dpg.add_spacer(width=14)
                dpg.add_text("Search:")
                dpg.add_input_text(
                    tag=self.search_tag,
                    width=380,
                    hint="ResRef, display name, or any ITM field...",
                    callback=self._on_search_changed,
                )
                dpg.add_spacer(width=14)
                dpg.add_text("", tag=self.status_tag)

            with dpg.group(tag=self.body_tag, horizontal=True):
                with dpg.child_window(tag=self.left_tag, border=True):
                    with dpg.table(
                        tag=self.table_tag,
                        header_row=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        resizable=True,
                        sortable=False,
                        borders_innerV=True,
                        borders_outerV=True,
                        borders_innerH=True,
                        borders_outerH=True,
                    ):
                        dpg.add_table_column(label="ResRef")
                        dpg.add_table_column(label="Name")
                        dpg.add_table_column(label="Type")

                with dpg.child_window(tag=self.right_tag, border=True):
                    with dpg.tab_bar():
                        with dpg.tab(label="Structured"):
                            with dpg.child_window(tag=self.structured_tag, border=False):
                                dpg.add_text("Select an ITM entry.")
                        with dpg.tab(label="JSON Tree"):
                            with dpg.child_window(tag=self.raw_tree_tag, border=False):
                                dpg.add_text("Select an ITM entry.")
                        with dpg.tab(label="Raw JSON"):
                            with dpg.child_window(tag=self.raw_text_tag, border=False):
                                dpg.add_text("Select an ITM entry.")

        self._load_games()

    def set_size(self, width: int, height: int) -> None:
        dpg.configure_item(self.root_tag, width=max(0, width), height=max(0, height))
        top_h = 34
        body_h = max(0, height - top_h - 6)
        left_w = max(260, int(width * 0.44))
        right_w = max(260, width - left_w - 12)

        dpg.configure_item(self.top_bar_tag, pos=[0, 0])
        dpg.configure_item(self.body_tag, pos=[0, top_h])
        dpg.configure_item(self.left_tag, width=left_w, height=body_h)
        dpg.configure_item(self.right_tag, width=right_w, height=body_h)

    def refresh_results(self) -> None:
        query = dpg.get_value(self.search_tag) if dpg.does_item_exist(self.search_tag) else ""
        self._search(query)

    def _tag(self, suffix: str) -> str:
        return f"{self.tag_prefix}_{suffix}"

    def _set_status(self, text: str) -> None:
        dpg.set_value(self.status_tag, text)

    def _load_games(self) -> None:
        games = self.catalog.list_games()
        self._game_ids = [g.game_id for g in games]
        dpg.configure_item(self.game_combo_tag, items=self._game_ids)

        if not self._game_ids:
            self._set_status("No game installations detected.")
            return

        self._selected_game_id = self._game_ids[0]
        dpg.set_value(self.game_combo_tag, self._selected_game_id)
        self._activate_selected_game(force_rebuild=False)

    def _activate_selected_game(self, *, force_rebuild: bool) -> None:
        if not self._selected_game_id:
            return
        try:
            self._set_status("Rebuilding index...")
            self.catalog.select_game(self._selected_game_id)
            self.catalog.load_index(force_rebuild=force_rebuild)
            self._set_status(f"Loaded ITM index for {self._selected_game_id}.")
            self._search(dpg.get_value(self.search_tag) if dpg.does_item_exist(self.search_tag) else "")
        except Exception as exc:
            self._set_status(f"Failed to load index: {exc}")
            self._clear_rows()
            self._render_error_details(str(exc))

    def _search(self, query: str) -> None:
        try:
            self._results = self.catalog.search_items(query)
        except Exception as exc:
            self._set_status(f"Search failed: {exc}")
            self._clear_rows()
            self._render_error_details(str(exc))
            return

        self._clear_rows()
        self._row_selectables = []
        self._selected_index = None
        if not self._results:
            self._set_status("No matching ITM resources.")
            self._render_empty_details()
            return

        self._set_status(f"{len(self._results)} item(s) found.")
        for idx, entry in enumerate(self._results):
            row_tag = self._tag(f"row_{idx}")
            self._row_selectables.append(row_tag)

            with dpg.table_row(parent=self.table_tag):
                dpg.add_selectable(
                    tag=row_tag,
                    label=str(entry.resref),
                    callback=self._on_row_selected,
                    user_data=idx,
                    span_columns=True,
                    height=self._row_selectable_height,
                )
                dpg.bind_item_theme(row_tag, self.row_selectable_theme_tag)
                tooltip_text = self._entry_tooltip_text(entry)
                if tooltip_text:
                    with dpg.tooltip(parent=row_tag):
                        dpg.bind_item_theme(dpg.last_item(), self.tooltip_theme_tag)
                        dpg.add_text(tooltip_text, wrap=520)
                dpg.add_text(entry.display_name or "")
                dpg.add_text(entry.res_type.name if hasattr(entry.res_type, "name") else str(entry.res_type))

        self._select_entry(0)

    def _clear_rows(self) -> None:
        dpg.delete_item(self.table_tag, children_only=True, slot=1)

    def _on_row_selected(self, _sender, app_data, user_data) -> None:
        if not bool(app_data):
            return
        try:
            idx = int(user_data)
        except Exception:
            return
        self._select_entry(idx)

    def _select_entry(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._results):
            return
        self._set_selected_index(idx)
        entry = self._results[idx]
        try:
            payload = self.catalog.load_item(entry)
        except Exception as exc:
            self._render_error_details(str(exc))
            return

        icon = self.catalog.load_item_icon(entry)
        title = self._entry_title_text(entry, payload)
        self._render_structured(payload, icon, title)
        self._render_raw(payload)

    def _set_selected_index(self, idx: int) -> None:
        self._selected_index = idx
        for row_idx, tag in enumerate(self._row_selectables):
            selected = row_idx == idx
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, selected)

    def _on_game_selected(self, _sender, app_data) -> None:
        self._selected_game_id = str(app_data) if app_data else None
        self._activate_selected_game(force_rebuild=False)

    def _on_refresh_clicked(self) -> None:
        self._activate_selected_game(force_rebuild=False)

    def _on_rebuild_clicked(self) -> None:
        self._activate_selected_game(force_rebuild=True)

    def _on_search_changed(self, _sender, app_data) -> None:
        self._search(str(app_data or ""))

    def _render_empty_details(self) -> None:
        dpg.delete_item(self.structured_tag, children_only=True)
        dpg.add_text("No item selected.", parent=self.structured_tag)
        dpg.delete_item(self.raw_tree_tag, children_only=True)
        dpg.add_text("No item selected.", parent=self.raw_tree_tag)
        dpg.delete_item(self.raw_text_tag, children_only=True)
        dpg.add_text("No item selected.", parent=self.raw_text_tag)

    def _render_error_details(self, message: str) -> None:
        dpg.delete_item(self.structured_tag, children_only=True)
        dpg.add_text(f"Error: {message}", parent=self.structured_tag, color=(255, 128, 128, 255))
        dpg.delete_item(self.raw_tree_tag, children_only=True)
        dpg.add_text(f"Error: {message}", parent=self.raw_tree_tag, color=(255, 128, 128, 255))
        dpg.delete_item(self.raw_text_tag, children_only=True)
        dpg.add_text(f"Error: {message}", parent=self.raw_text_tag, color=(255, 128, 128, 255))

    def _render_structured(self, payload: dict, icon: tuple[int, int, list[float]] | None, title: str) -> None:
        dpg.delete_item(self.structured_tag, children_only=True)
        self._clear_dynamic_textures()
        if not payload:
            dpg.add_text("No structured data.", parent=self.structured_tag)
            return

        with dpg.group(parent=self.structured_tag, horizontal=True):
            if icon is not None:
                width, height, rgba = icon
                self._set_icon_texture(width, height, rgba)
                self._add_image_with_fullsize_tooltip(
                    texture_tag=self.icon_texture_tag,
                    draw_width=width,
                    draw_height=height,
                    full_width=width,
                    full_height=height,
                )
            else:
                self._ensure_default_icon_texture()
                self._add_image_with_fullsize_tooltip(
                    texture_tag=self.default_icon_texture_tag,
                    draw_width=32,
                    draw_height=32,
                    full_width=16,
                    full_height=16,
                )

            with dpg.group():
                title_tag = self._tag("item_title")
                dpg.add_text(title or "Unknown Item", tag=title_tag)
                dpg.bind_item_theme(title_tag, self.title_text_theme_tag)
                self._ensure_title_font()
                if self._title_font_ready and dpg.does_item_exist(self.title_font_tag):
                    dpg.bind_item_font(title_tag, self.title_font_tag)

        dpg.add_separator(parent=self.structured_tag)

        if "header" in payload:
            with dpg.tree_node(label="Header", parent=self.structured_tag, default_open=True):
                header_node = dpg.last_item()
                rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]] = []
                self._collect_table_rows("header", payload["header"], rows)
                self._render_section_table(
                    header_node,
                    rows,
                    f"{self.structured_table_tag}_header",
                    strip_prefix="header.",
                )

        ext_headers = payload.get("extended_headers", [])
        with dpg.tree_node(label=f"Extended Headers [{len(ext_headers)}]", parent=self.structured_tag, default_open=True):
            ext_root_node = dpg.last_item()
            if isinstance(ext_headers, list) and ext_headers:
                for idx, ext_header in enumerate(ext_headers):
                    with dpg.tree_node(label=f"Extended Header [{idx}]", parent=ext_root_node, default_open=False):
                        ext_node = dpg.last_item()
                        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]] = []
                        self._collect_table_rows(f"extended_headers[{idx}]", ext_header, rows)
                        self._render_section_table(
                            ext_node,
                            rows,
                            f"{self.structured_table_tag}_ext_{idx}",
                            strip_prefix=f"extended_headers[{idx}].",
                        )
            else:
                dpg.add_text("No extended headers.", parent=ext_root_node)

        features = payload.get("feature_blocks", [])
        with dpg.tree_node(label=f"Feature Blocks [{len(features)}]", parent=self.structured_tag, default_open=True):
            features_root_node = dpg.last_item()
            if isinstance(features, list) and features:
                for idx, feature in enumerate(features):
                    with dpg.tree_node(label=f"Feature Block [{idx}]", parent=features_root_node, default_open=False):
                        feature_node = dpg.last_item()
                        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]] = []
                        self._collect_table_rows(f"feature_blocks[{idx}]", feature, rows)
                        self._render_section_table(
                            feature_node,
                            rows,
                            f"{self.structured_table_tag}_fb_{idx}",
                            strip_prefix=f"feature_blocks[{idx}].",
                        )
            else:
                dpg.add_text("No feature blocks.", parent=features_root_node)

        other_keys = [k for k in payload.keys() if k not in {"header", "extended_headers", "feature_blocks"}]
        if other_keys:
            with dpg.tree_node(label="Other", parent=self.structured_tag, default_open=False):
                other_node = dpg.last_item()
                rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]] = []
                for key in other_keys:
                    self._collect_table_rows(key, payload[key], rows)
                self._render_section_table(other_node, rows, f"{self.structured_table_tag}_other")

    def _render_raw(self, payload: dict) -> None:
        dpg.delete_item(self.raw_tree_tag, children_only=True)
        with dpg.tree_node(label="item", parent=self.raw_tree_tag, default_open=True):
            self._render_object(parent=dpg.last_item(), value=payload, default_open=False)

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

    def _render_json_node(self, parent: str | int, key: str, value: Any, *, default_open: bool) -> None:
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

    def _collect_table_rows(
        self,
        field_path: str,
        value: Any,
        out_rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]],
    ) -> None:
        if isinstance(value, dict):
            if not value:
                out_rows.append((field_path, "{}", "", None))
                return
            for key, nested in value.items():
                self._collect_table_rows(f"{field_path}.{key}", nested, out_rows)
            return
        if isinstance(value, list):
            if not value:
                out_rows.append((field_path, "[]", "", None))
                return
            for idx, nested in enumerate(value):
                self._collect_table_rows(f"{field_path}[{idx}]", nested, out_rows)
            return

        value_text = str(value)
        resolved = ""
        bam_icon: tuple[int, int, list[float]] | None = None
        leaf = field_path.split(".")[-1]
        if "[" in leaf:
            leaf = leaf.split("[", 1)[0]
        if self._is_strref_field(leaf) and isinstance(value, int):
            try:
                resolved = self.catalog.resolve_strref(value)
            except Exception:
                resolved = ""
        elif self._is_itm_resref_field(leaf):
            itm_resref = self._normalize_resrefish(value)
            if not itm_resref:
                out_rows.append((field_path, value_text, resolved, bam_icon))
                return
            resolved = itm_resref
            try:
                bam_icon = self.catalog.load_item_icon_by_itm_resref(itm_resref)
            except Exception:
                bam_icon = None
        elif self._is_bam_field(leaf):
            bam_resref = self._normalize_resrefish(value)
            if not bam_resref:
                out_rows.append((field_path, value_text, resolved, bam_icon))
                return
            resolved = bam_resref
            try:
                bam_icon, _status = self.catalog.load_bam_icon_by_resref_with_status(bam_resref)
            except Exception:
                bam_icon = None

        out_rows.append((field_path, value_text, resolved, bam_icon))

    @staticmethod
    def _is_strref_field(field_name: str) -> bool:
        suffixes = (
            "_name",
            "_description",
            "_text",
            "_tooltip",
            "identified_name",
            "unidentified_name",
            "identified_desc",
            "unidentified_desc",
            "identified_description",
            "unidentified_description",
            "journal_text",
            "dialog_text",
            "encounter_text",
            "name",
            "tooltip",
            "description",
        )
        key = field_name.lower()
        return any(key == s or key.endswith(s) for s in suffixes)

    @staticmethod
    def _is_bam_field(field_name: str) -> bool:
        key = field_name.lower()
        explicit = {
            "item_icon",
            "use_icon",
            "ground_icon",
            "description_icon",
            "animation",
        }
        return key in explicit or key.endswith("_icon") or key.endswith("_bam")

    @staticmethod
    def _is_itm_resref_field(field_name: str) -> bool:
        return field_name.lower() in {"replacement_item"}

    def _render_object(self, parent: str | int, value: Any, *, default_open: bool) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                self._render_json_node(parent=parent, key=str(key), value=item, default_open=default_open)
            return
        if isinstance(value, list):
            for idx, item in enumerate(value):
                self._render_json_node(parent=parent, key=f"[{idx}]", value=item, default_open=False)
            return
        dpg.add_text(str(value), parent=parent)

    def _render_section_table(
        self,
        parent: str | int,
        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]],
        table_tag: str,
        *,
        strip_prefix: str = "",
    ) -> None:
        with dpg.table(
            tag=table_tag,
            parent=parent,
            header_row=True,
            policy=dpg.mvTable_SizingFixedFit,
            row_background=True,
            resizable=True,
            sortable=False,
            borders_innerV=True,
            borders_outerV=True,
            borders_innerH=True,
            borders_outerH=True,
        ):
            dpg.add_table_column(label="Field")
            dpg.add_table_column(label="Value")
            dpg.add_table_column(label="Resolved / Preview")
            for field_path, value_text, resolved_strref, bam_icon in rows:
                row_height = 24 if bam_icon is not None else 0
                with dpg.table_row(parent=table_tag, height=row_height):
                    dpg.add_text(ItmViewerPanel._humanize_field_path(field_path, strip_prefix=strip_prefix))
                    dpg.add_text(value_text)
                    with dpg.group(horizontal=True):
                        if bam_icon is not None:
                            tex = self._create_dynamic_texture(*bam_icon)
                            width, height, _ = bam_icon
                            max_preview = 16
                            scale = min(max_preview / max(1, width), max_preview / max(1, height), 1.0)
                            draw_w = max(1, int(width * scale))
                            draw_h = max(1, int(height * scale))
                            self._add_image_with_fullsize_tooltip(
                                texture_tag=tex,
                                draw_width=draw_w,
                                draw_height=draw_h,
                                full_width=width,
                                full_height=height,
                            )
                        if resolved_strref:
                            dpg.add_text(resolved_strref)

    @staticmethod
    def _humanize_field_path(field_path: str, *, strip_prefix: str = "") -> str:
        if strip_prefix and field_path.startswith(strip_prefix):
            field_path = field_path[len(strip_prefix):]

        parts = field_path.split(".")
        pretty_parts: list[str] = []
        for part in parts:
            if "[" in part:
                base = part.split("[", 1)[0]
                index_part = part[len(base):]
            else:
                base = part
                index_part = ""

            base = base.replace("_", " ").strip()
            base = " ".join(token.capitalize() for token in base.split())
            pretty_parts.append(f"{base}{index_part}" if base else part)

        return " > ".join(pretty_parts)

    def _entry_tooltip_text(self, entry: Any) -> str:
        data = getattr(entry, "data", None)
        if not isinstance(data, dict):
            return ""
        header = data.get("header")
        if not isinstance(header, dict):
            return ""

        candidates = (
            header.get("identified_desc"),
            header.get("unidentified_desc"),
        )
        for raw in candidates:
            if not isinstance(raw, int):
                continue
            try:
                text = self.catalog.resolve_strref(raw).strip()
            except Exception:
                text = ""
            if text:
                return text
        return ""

    def _entry_title_text(self, entry: Any, payload: dict) -> str:
        header = payload.get("header", {}) if isinstance(payload, dict) else {}
        if isinstance(header, dict):
            for key in ("identified_name", "unidentified_name"):
                raw = header.get(key)
                if isinstance(raw, int):
                    try:
                        text = self.catalog.resolve_strref(raw).strip()
                    except Exception:
                        text = ""
                    if text:
                        return text

        display_name = getattr(entry, "display_name", "")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
        return str(getattr(entry, "resref", "Unknown Item"))

    @staticmethod
    def _normalize_resrefish(value: Any) -> str:
        if isinstance(value, ResRef):
            return str(value).strip().upper()
        if isinstance(value, str):
            return value.strip().upper()
        if isinstance(value, dict):
            for key in ("resref", "value", "name", "id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip().upper()
        if value is None:
            return ""
        text = str(value).strip().upper()
        return text if text else ""

    def _set_icon_texture(self, width: int, height: int, rgba: list[float]) -> None:
        if dpg.does_item_exist(self.icon_texture_tag):
            dpg.delete_item(self.icon_texture_tag)
        dpg.add_static_texture(
            width=width,
            height=height,
            default_value=rgba,
            tag=self.icon_texture_tag,
            parent="window_icon_textures",
        )

    def _clear_dynamic_textures(self) -> None:
        for tag in self._dynamic_texture_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._dynamic_texture_tags.clear()

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

    def _ensure_default_icon_texture(self) -> None:
        if dpg.does_item_exist(self.default_icon_texture_tag):
            return

        size = 16
        bg = (0.15, 0.15, 0.15, 1.0)
        fg = (0.85, 0.85, 0.85, 1.0)
        pixels = [[*bg] for _ in range(size * size)]

        def set_px(x: int, y: int, color: tuple[float, float, float, float]) -> None:
            if 0 <= x < size and 0 <= y < size:
                pixels[y * size + x] = [color[0], color[1], color[2], color[3]]

        # Question mark glyph
        for x in range(5, 11):
            set_px(x, 3, fg)
        for y in range(4, 7):
            set_px(10, y, fg)
        for x in range(7, 10):
            set_px(x, 7, fg)
        for y in range(8, 10):
            set_px(7, y, fg)
        set_px(7, 12, fg)
        set_px(7, 13, fg)

        flat = [c for px in pixels for c in px]
        dpg.add_static_texture(
            width=size,
            height=size,
            default_value=flat,
            tag=self.default_icon_texture_tag,
            parent="window_icon_textures",
        )

    def _ensure_title_font(self) -> None:
        if self._title_font_ready:
            return

        font_candidates = [
            Path(r"C:\Windows\Fonts\segoeuib.ttf"),  # Segoe UI Bold
            Path(r"C:\Windows\Fonts\arialbd.ttf"),   # Arial Bold fallback
        ]
        for font_path in font_candidates:
            if not font_path.is_file():
                continue
            try:
                with dpg.font_registry():
                    dpg.add_font(str(font_path), 24, tag=self.title_font_tag)
                self._title_font_ready = True
                return
            except Exception:
                continue
