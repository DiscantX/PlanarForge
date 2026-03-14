"""ITM (item) browser and viewer."""

from __future__ import annotations

import json
import threading
import time
import traceback
from queue import Empty, Full, Queue
from enum import IntEnum, IntFlag
from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg

from core.services.itm_catalog import ItmCatalog
from core.util.enums import (
    AttackType,
    ChargeBehavior,
    EffectTarget,
    EffectTiming,
    ItemAbilityLocation,
    ItemAbilityFlag,
    ItemDamageType,
    ItemDamageTypePST,
    ItemFlag,
    ItemFlagEE,
    ItemFlagPSTEE,
    ItemTargetType,
    ItemTargetTypePST,
    ItemType,
    ItemUsabilityFlag,
    ItemUsabilityFlagEE,
    ItemUsabilityFlagPST,
)
from core.util.resref import ResRef
from ui.core import EditorProgressHandler, EditorToolbar, ResourceBrowserPane


class ItemEditorPanel:
    """Read-only ITM browser panel with list/search and structured/raw details."""

    def __init__(self, parent_tag: str, catalog: ItmCatalog, *, tag_prefix: str = "item_editor") -> None:
        self.catalog = catalog
        self.tag_prefix = tag_prefix

        self.root_tag = self._tag("root")
        self.body_tag = self._tag("body")
        self.right_tag = self._tag("right")
        self.structured_tag = self._tag("structured")
        self.structured_table_tag = self._tag("structured_table")
        self.raw_tree_tag = self._tag("raw_tree")
        self.raw_text_tag = self._tag("raw_text")
        self.raw_json_textbox_tag = self._tag("raw_json_textbox")
        self.row_selectable_theme_tag = self._tag("row_selectable_theme")
        self.tooltip_theme_tag = self._tag("tooltip_theme")
        self.icon_texture_tag = self._tag("icon_texture")
        self.default_icon_texture_tag = self._tag("default_icon_texture")
        self.browser_view_combo_tag = self._tag("browser_view_combo")
        self.title_text_theme_tag = self._tag("title_text_theme")
        self.title_font_tag = self._tag("title_font")
        self.tree_wrap_handler_tag = self._tag("tree_wrap_handler")
        self._title_font_ready = False

        self._results: list[Any] = []
        self._game_ids: list[str] = []
        self._selected_game_id: str | None = None
        self._dynamic_texture_tags: list[str] = []
        self._texture_counter = 0
        self._browser_icon_cache: dict[str, tuple[int, int, list[float]] | None] = {}
        self._browser_icon_attempted: set[str] = set()
        self._browser_indices_set: set[int] = set()
        self._icon_load_queue: Queue[tuple[int, int, str, tuple[int, int, list[float]] | None]] = Queue()
        self._icon_work_queue: Queue[Any] = Queue()
        self._icon_trace_enabled: bool = True
        self._icon_load_token: int = 0
        self._icon_load_threads = [] 
        self._icon_pump_scheduled: bool = False
        self._icon_load_stop: threading.Event | None = None
        self._active_workers: int = 0
        self._worker_lock = threading.Lock()
        
        # Panel sizing state
        self._total_width: int = 0
        self._total_height: int = 0
        self._right_width: int = 0
        self._last_structured_width: int = 0
        self._last_payload: dict | None = None
        self._last_icon: tuple[int, int, list[float]] | None = None
        self._last_title: str = ""
        self._wrap_tables: dict[str, tuple[tuple[str, str, str], list[tuple[str, int]], int, int]] = {}
        
        # Progress tracking
        self._progress_handler = EditorProgressHandler(self._set_status)

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

        with dpg.item_handler_registry(tag=self.tree_wrap_handler_tag):
            dpg.add_item_toggled_open_handler(
                callback=lambda _s, _a, _u: self._refresh_table_wraps_deferred()
            )

        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            # Create toolbar
            self._toolbar = EditorToolbar(
                parent_tag=self.root_tag,
                games=[],
                on_game_selected=self._on_game_selected,
                on_refresh=self._on_refresh_clicked,
                on_rebuild=self._on_rebuild_clicked,
                extra_controls=self._add_toolbar_controls,
                tag_prefix=self._tag("toolbar"),
            )

            with dpg.group(tag=self.body_tag, horizontal=True):
                # Create the browser pane with 3 columns for ITM
                self._browser = ResourceBrowserPane(
                    parent_tag=self.body_tag,
                    columns=["ResRef", "Name", "Type"],
                    on_row_selected=self._on_row_selected,
                    tag_prefix=self._tag("browser"),
                )

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
        self._total_width = width
        self._total_height = height
        dpg.configure_item(self.root_tag, width=max(0, width), height=max(0, height))
        top_h = 34
        body_h = max(0, height - top_h - 6)
        
        # Update browser and right panel sizing
        self._browser.set_size(width, body_h)
        left_w = self._browser.get_panel_width()
        right_w = max(260, width - left_w - 12)
        self._right_width = right_w

        dpg.configure_item(self.body_tag, pos=[0, top_h])
        dpg.configure_item(self.right_tag, width=right_w, height=body_h)
        # Live reflow for structured table wrapping
        structured_w = dpg.get_item_width(self.structured_tag)
        if structured_w <= 0:
            structured_w = right_w
        if (
            self._last_payload
            and abs(structured_w - self._last_structured_width) >= 8
        ):
            self._last_structured_width = structured_w
            try:
                self._render_structured(self._last_payload, self._last_icon, self._last_title)
            except Exception:
                pass

    def refresh_results(self) -> None:
        """Refresh the results list with current search."""
        self._search("")

    def _tag(self, suffix: str) -> str:
        return f"{self.tag_prefix}_{suffix}"

    def _set_status(self, text: str) -> None:
        self._toolbar.set_status(text)

    def _add_toolbar_controls(self, parent_tag: str) -> None:
        dpg.add_text("View:", parent=parent_tag)
        dpg.add_combo(
            tag=self.browser_view_combo_tag,
            items=["List", "Icons"],
            width=90,
            callback=self._on_browser_view_changed,
            parent=parent_tag,
        )
        dpg.set_value(self.browser_view_combo_tag, "List")

    def _on_browser_view_changed(self, _sender: Any, app_data: str) -> None:
        label = str(app_data or "").strip().lower()
        mode = "grid" if label.startswith("icon") else "list"
        self._browser.set_view_mode(mode)
        self.refresh_results()

    def _load_games(self) -> None:
        games = self.catalog.list_games()
        self._game_ids = [g.game_id for g in games]
        self._toolbar.set_games(self._game_ids)

        if not self._game_ids:
            self._set_status("No game installations detected.")
            return

        self._selected_game_id = self._game_ids[0]
        self._toolbar.set_game(self._selected_game_id)
        self._activate_selected_game(force_rebuild=False)

    def _activate_selected_game(self, *, force_rebuild: bool) -> None:
        if not self._selected_game_id:
            return
        try:
            self._set_status("Rebuilding index...")
            self.catalog.select_game(self._selected_game_id)
            self._stop_icon_loader()
            self._browser_icon_cache.clear()
            self._browser_icon_attempted.clear()
            self.catalog.load_index(force_rebuild=force_rebuild)
            self._set_status(f"Loaded ITM index for {self._selected_game_id}.")
            self._search("")
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

        self._populate_browser(include_icons=(self._browser.get_view_mode() == "grid"))

        if not self._results:
            self._set_status("No matching ITM resources.")
            self._render_empty_details()
            return

        self._set_status(f"{len(self._results)} item(s) found.")
        # Auto-select first item
        self._browser.select_row(0)
        self._select_entry(0)

    def _populate_browser(self, *, include_icons: bool) -> None:
        browser_data = [
            (
                str(entry.resref),
                entry.display_name or "",
                entry.res_type.name if hasattr(entry.res_type, "name") else str(entry.res_type),
            )
            for entry in self._results
        ]
        grid_labels = [
            (entry.display_name or str(entry.resref))
            for entry in self._results
        ]
        if include_icons:
            grid_icons: list[tuple[int, int, list[float]] | None] = []
            to_load: list[tuple[int, Any, str]] = []
            for idx, entry in enumerate(self._results):
                resref = str(getattr(entry, "resref", "") or "").strip().upper()
                if not resref:
                    grid_icons.append(None)
                    continue
                if resref in self._browser_icon_attempted:
                    grid_icons.append(self._browser_icon_cache.get(resref))
                else:
                    grid_icons.append(None)
                    to_load.append((idx, entry, resref))
            self._browser.populate_rows(
                browser_data,
                grid_labels=grid_labels,
                grid_icons=grid_icons,
            )
            self._start_icon_loader(to_load)
        else:
            self._browser.populate_rows(
                browser_data,
                grid_labels=grid_labels,
            )
            self._stop_icon_loader()

    def _trace_icon(self, message: str) -> None:
        if self._icon_trace_enabled:
            print(f"[IconLoad] {message}")

    def _start_icon_loader(self, work_items: list[tuple[int, Any, str]]) -> None:
        """Starts background threads to load all icons in work_items."""
        self._stop_icon_loader()
        if not work_items or not self._selected_game_id:
            return

        self._icon_load_token += 1
        token = self._icon_load_token
        self._icon_load_stop = threading.Event()
        stop_event = self._icon_load_stop

        worker_count = 2
        self._icon_work_queue = Queue()
        self._icon_load_queue = Queue(maxsize=worker_count * 10)

        def worker() -> None:
            try:
                while not stop_event.is_set():
                    try:
                        item = self._icon_work_queue.get(timeout=0.1)
                    except Empty:
                        continue
                    if item is None:
                        break
                    try:
                        idx, entry, resref = item
                        if stop_event.is_set():
                            break

                        # Mark as attempted before loading
                        self._browser_icon_attempted.add(resref)
                        icon = self.catalog.load_item_icon(entry)
                        self._browser_icon_cache[resref] = icon

                        if stop_event.is_set():
                            break

                        while not stop_event.is_set():
                            try:
                                self._icon_load_queue.put((token, idx, resref, icon), timeout=0.05)
                                break
                            except Full:
                                pass
                    except Exception:
                        formatted_exc = traceback.format_exc()
                        self._trace_icon(f"worker-outer-exc exc={formatted_exc}")
                        continue
            finally:
                with self._worker_lock:
                    self._active_workers -= 1

        # Populate the work queue with all items at once
        for item in work_items:
            self._icon_work_queue.put(item)

        with self._worker_lock:
            self._active_workers = worker_count

        for _ in range(worker_count):
            thread = threading.Thread(target=worker, daemon=True)
            self._icon_load_threads.append(thread)
            thread.start()

        self._schedule_icon_pump()

    def _stop_icon_loader(self) -> None:
        if getattr(self, "_icon_load_stop", None) is not None:
            self._icon_load_stop.set()
        if hasattr(self, "_icon_work_queue"):
            for _ in range(len(self._icon_load_threads)):
                try:
                    self._icon_work_queue.put(None, block=False)
                except Full:
                    pass
        for thread in self._icon_load_threads:
            thread.join(timeout=0.5)
        self._icon_load_threads.clear()
        self._icon_load_stop = None
        self._icon_pump_scheduled = False
        self._icon_load_queue = Queue()
        self._icon_work_queue = Queue()
        with self._worker_lock:
            self._active_workers = 0

    def _schedule_icon_pump(self) -> None:
        if self._icon_pump_scheduled:
            return
        self._icon_pump_scheduled = True
        frame = dpg.get_frame_count() + 1
        dpg.set_frame_callback(frame, self._pump_icon_queue)

    def _pump_icon_queue(self) -> None:
        self._icon_pump_scheduled = False
        if self._browser.get_view_mode() != "grid":
            return

        processed = 0
        while processed < 8 and not self._icon_load_queue.empty():
            try:
                token, idx, resref, icon = self._icon_load_queue.get_nowait()
            except Empty:
                break

            if token != self._icon_load_token:
                continue

            if resref:
                self._browser_icon_cache[resref] = icon
            try:
                self._browser.set_grid_icon(idx, icon)
                self._browser_indices_set.add(idx)
            except Exception:
                formatted_exc = traceback.format_exc()
                self._trace_icon(f"Failed to set grid icon for idx={idx} resref={resref} exc={formatted_exc}")
            processed += 1

        if (self._icon_load_stop and not self._icon_load_stop.is_set()) or not self._icon_load_queue.empty():
            self._schedule_icon_pump()
        else:
            with self._worker_lock:
                if self._active_workers == 0:
                    self._set_status(f"{len(self._results)} item(s) found.")

    def _clear_rows(self) -> None:
        # self._stop_icon_loader()
        self._browser.clear_rows()

    def _on_row_selected(self, idx: int) -> None:
        self._select_entry(idx)

    def _select_entry(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._results):
            return
        entry = self._results[idx]
        payload = self.catalog.load_item(entry)
        resref = str(getattr(entry, "resref", "") or "").strip().upper()
        icon = self._browser_icon_cache.get(resref)
        
        if icon is None and resref:
            try:
                icon = self.catalog.load_item_icon(entry)
                if icon:
                    self._browser_icon_cache[resref] = icon
            except Exception as e:
                self._trace_icon(f"On-select icon load failed for {resref}: {e}")
                icon = None

        if self._browser.get_view_mode() == "grid":
            try:
                self._browser.set_grid_icon(idx, icon)
            except Exception:
                pass
        title = self._entry_title_text(entry, payload)
        self._render_structured(payload, icon, title)
        self._render_raw(payload)

    def _on_game_selected(self, game_id: str) -> None:
        self._selected_game_id = game_id
        self._activate_selected_game(force_rebuild=False)

    def _on_refresh_clicked(self) -> None:
        self._activate_selected_game(force_rebuild=False)

    def _on_rebuild_clicked(self) -> None:
        self._activate_selected_game(force_rebuild=True)

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
        self._wrap_tables.clear()
        self._last_payload = payload
        self._last_icon = icon
        self._last_title = title
        w = dpg.get_item_width(self.structured_tag)
        if w <= 0:
            w = self._right_width
        if w > 0:
            self._last_structured_width = w

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
                rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None, bool]] = []
                self._collect_table_rows("header", payload["header"], rows)
                rows = self._reorder_header_rows(rows)
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
                    with dpg.tree_node(
                        label=f"Extended Header [{idx}]",
                        parent=ext_root_node,
                        default_open=False,
                    ):
                        node = dpg.last_item()
                        dpg.bind_item_handler_registry(node, self.tree_wrap_handler_tag)
                        ext_node = dpg.last_item()
                        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None, bool]] = []
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
                    with dpg.tree_node(
                        label=f"Feature Block [{idx}]",
                        parent=features_root_node,
                        default_open=False,
                    ):
                        node = dpg.last_item()
                        dpg.bind_item_handler_registry(node, self.tree_wrap_handler_tag)
                        feature_node = dpg.last_item()
                        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None, bool]] = []
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
                rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None, bool]] = []
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
        out_rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None, bool]],
    ) -> None:
        if isinstance(value, dict) and not self._looks_like_idsref(value):
            if not value:
                out_rows.append((field_path, "{}", "", None, False))
                return
            for key, nested in value.items():
                self._collect_table_rows(f"{field_path}.{key}", nested, out_rows)
            return
        if isinstance(value, list):
            if not value:
                out_rows.append((field_path, "[]", "", None, False))
                return
            for idx, nested in enumerate(value):
                self._collect_table_rows(f"{field_path}[{idx}]", nested, out_rows)
            return

        value_text = str(value)
        resolved = ""
        bam_icon: tuple[int, int, list[float]] | None = None
        resolved_is_resref = False
        leaf = field_path.split(".")[-1]
        if "[" in leaf:
            leaf = leaf.split("[", 1)[0]
        if self._looks_like_idsref(value):
            ids_name = str(value.get("ids", "")).strip().upper()
            raw_val = value.get("value", 0)
            try:
                raw_int = int(raw_val)
            except Exception:
                raw_int = 0
            value_text = f"{raw_int} ({ids_name})" if ids_name else str(raw_int)
            if ids_name:
                try:
                    resolved = self.catalog.resolve_ids(ids_name, raw_int)
                except Exception:
                    resolved = ""
        elif (
            self._is_strref_field(leaf)
            or (field_path.startswith("feature_blocks[") and leaf == "parameter1")
        ) and isinstance(value, int):
            try:
                resolved = self.catalog.resolve_strref(value)
            except Exception:
                resolved = ""
        elif self._is_itm_resref_field(leaf):
            itm_resref = self._normalize_resrefish(value)
            if not itm_resref:
                out_rows.append((field_path, value_text, resolved, bam_icon, False))
                return
            resolved = itm_resref
            resolved_is_resref = True
            try:
                bam_icon = self.catalog.load_item_icon_by_itm_resref(itm_resref)
            except Exception:
                bam_icon = None
        elif leaf == "animation" and isinstance(value, str):
            resolved = self._resolve_animation_code(value)
        elif self._is_bam_field(leaf):
            bam_resref = self._normalize_resrefish(value)
            if not bam_resref:
                out_rows.append((field_path, value_text, resolved, bam_icon, False))
                return
            resolved = bam_resref
            resolved_is_resref = True
            try:
                bam_icon, _status = self.catalog.load_bam_icon_by_resref_with_status(bam_resref)
            except Exception:
                bam_icon = None
        elif leaf.startswith("kit_usability_") and isinstance(value, int):
            offset = 0
            if leaf.endswith("_2"):
                offset = 8
            elif leaf.endswith("_3"):
                offset = 16
            elif leaf.endswith("_4"):
                offset = 24
            try:
                resolved = self.catalog.resolve_kit_usability_mask(value, bit_offset=offset)
            except Exception:
                resolved = ""
        elif leaf == "opcode" and field_path.startswith("feature_blocks[") and isinstance(value, int):
            try:
                name, desc = self.catalog.resolve_opcode(value)
                resolved = self._format_opcode_resolved(name, desc)
            except Exception:
                resolved = ""
        else:
            enum_cls = self._enum_for_field(field_path)
            if enum_cls is not None and isinstance(value, int):
                resolved = self._enum_display(enum_cls, value)
                if field_path == "header.usability" and resolved:
                    resolved = self._format_unusable_by(resolved)

        out_rows.append((field_path, value_text, resolved, bam_icon, resolved_is_resref))

    @staticmethod
    def _looks_like_idsref(value: Any) -> bool:
        return isinstance(value, dict) and "value" in value and "ids" in value

    def _enum_for_field(self, field_path: str) -> type[IntEnum] | type[IntFlag] | None:
        normalized = field_path.replace("]", "").replace("[", "")
        # Strip numeric indices from paths like extended_headers0.attack_type
        normalized = "".join(ch for ch in normalized if not ch.isdigit())
        if normalized == "header.item_type":
            return ItemType
        if normalized == "header.flags":
            game_id = (self._selected_game_id or "").upper()
            if game_id == "PSTEE":
                return ItemFlagPSTEE
            if game_id.endswith("EE"):
                return ItemFlagEE
            return ItemFlag
        if normalized == "header.usability":
            game_id = (self._selected_game_id or "").upper()
            if game_id.startswith("PST"):
                return ItemUsabilityFlagPST
            if game_id.endswith("EE"):
                return ItemUsabilityFlagEE
            return ItemUsabilityFlag
        if normalized.startswith("extended_headers.") and normalized.endswith(".attack_type"):
            return AttackType
        if normalized.startswith("extended_headers.") and normalized.endswith(".target_type"):
            if (self._selected_game_id or "").upper().startswith("PST"):
                return ItemTargetTypePST
            return ItemTargetType
        if normalized.startswith("extended_headers.") and normalized.endswith(".location"):
            return ItemAbilityLocation
        if normalized.startswith("extended_headers.") and normalized.endswith(".charge_depletion"):
            return ChargeBehavior
        if normalized.startswith("extended_headers.") and normalized.endswith(".damage_type"):
            if (self._selected_game_id or "").upper().startswith("PST"):
                return ItemDamageTypePST
            return ItemDamageType
        if normalized.startswith("extended_headers.") and normalized.endswith(".flags"):
            return ItemAbilityFlag
        if normalized.startswith("feature_blocks.") and normalized.endswith(".target"):
            return EffectTarget
        if normalized.startswith("feature_blocks.") and normalized.endswith(".timing_mode"):
            return EffectTiming
        return None

    @staticmethod
    def _enum_display(enum_cls: type[IntEnum] | type[IntFlag], value: int) -> str:
        try:
            if issubclass(enum_cls, IntFlag):
                if value == 0:
                    try:
                        return enum_cls(0).name
                    except Exception:
                        return "NONE"
                names = [m.name for m in enum_cls if m.value and (value & int(m.value))]
                return " | ".join(names) if names else f"UNKNOWN({value})"
            return enum_cls(value).name
        except Exception:
            return f"UNKNOWN({value})"

    @staticmethod
    def _format_unusable_by(resolved: str) -> str:
        if not resolved:
            return resolved
        parts = [p.strip() for p in resolved.split("|") if p.strip()]
        cleaned: list[str] = []
        for part in parts:
            if part.startswith("UNUSABLE_BY_"):
                part = part[len("UNUSABLE_BY_") :]
            part = part.replace("_", " ")
            part = " ".join(token.capitalize() for token in part.split())
            cleaned.append(part)
        return " | ".join(cleaned)

    @staticmethod
    def _format_opcode_resolved(name: str, desc: str) -> str:
        if not name:
            return ""
        if not desc:
            return name
        compact = " ".join(desc.split())
        return f"{name}\n{compact}"


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
        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None, bool]],
        table_tag: str,
        *,
        strip_prefix: str = "",
    ) -> None:
        wrap_targets: list[tuple[str, int]] = []
        cell_idx = 0
        col_tags = (
            f"{table_tag}_col_field",
            f"{table_tag}_col_value",
            f"{table_tag}_col_resolved",
        )
        field_labels = [
            ItemEditorPanel._humanize_field_path(field_path, strip_prefix=strip_prefix)
            for field_path, _value_text, _resolved_strref, _bam_icon, _is_resref in rows
        ]
        value_texts = [value_text for _fp, value_text, _rs, _bi, _isr in rows]
        pad = 12
        max_field = 0
        max_value = 0
        for label in field_labels:
            try:
                max_field = max(max_field, int(dpg.get_text_size(label)[0]))
            except Exception:
                continue
        for text in value_texts:
            try:
                max_value = max(max_value, int(dpg.get_text_size(text)[0]))
            except Exception:
                continue
        max_field += pad
        max_value += pad
        with dpg.table(
            tag=table_tag,
            parent=parent,
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
            dpg.add_table_column(
                label="Field",
                width_fixed=True,
                init_width_or_weight=max_field,
                tag=col_tags[0],
            )
            dpg.add_table_column(
                label="Value",
                width_fixed=True,
                init_width_or_weight=max_value,
                tag=col_tags[1],
            )
            dpg.add_table_column(label="Resolved / Preview", width_stretch=True, tag=col_tags[2])
            for idx, (field_path, value_text, resolved_strref, bam_icon, resolved_is_resref) in enumerate(rows):
                row_height = 24 if bam_icon is not None else 0
                with dpg.table_row(parent=table_tag, height=row_height):
                    field_tag = f"{table_tag}_field_{cell_idx}"
                    cell_idx += 1
                    value_tag = f"{table_tag}_value_{cell_idx}"
                    cell_idx += 1
                    dpg.add_text(
                        field_labels[idx] if idx < len(field_labels) else ItemEditorPanel._humanize_field_path(
                            field_path, strip_prefix=strip_prefix
                        ),
                        tag=field_tag,
                    )
                    dpg.add_text(value_text, tag=value_tag)
                    wrap_targets.append((field_tag, 0))
                    wrap_targets.append((value_tag, 1))
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
                            resolved_tag = f"{table_tag}_resolved_{cell_idx}"
                            cell_idx += 1
                            dpg.add_text(resolved_strref, tag=resolved_tag)
                            wrap_targets.append((resolved_tag, 2))
        self._wrap_tables[table_tag] = (col_tags, wrap_targets, max_field, max_value)
        self._apply_wrap_from_known_widths(col_tags, wrap_targets, max_field, max_value)

    def _compute_col_widths(
        self,
        table_tag: str,
        col_tags: tuple[str, str, str],
        max_field: int,
        max_value: int,
    ) -> list[int]:
        """Return [field_w, value_w, resolved_w] using measured columns when available,
        otherwise derive from known fixed-column sizes and right-panel width."""
        measured = self._measure_column_wrap_widths(table_tag, col_tags)
        if any(measured):
            return measured
        # Table hasn't been laid out yet (collapsed or first frame) — compute directly.
        right_w = self._measure_item_width(self.right_tag) or int(self._right_width or 720)
        field_w  = max_field if max_field > 0 else right_w // 4
        value_w  = max_value if max_value > 0 else right_w // 4
        resolved_w = max(80, right_w - field_w - value_w - 16)
        return [field_w, value_w, resolved_w]

    def _apply_wrap_from_known_widths(
        self,
        col_tags: tuple[str, str, str],
        wrap_targets: list[tuple[str, int]],
        max_field: int,
        max_value: int,
    ) -> None:
        """Apply wrap immediately using the known fixed-column sizes — no measurement needed."""
        if not wrap_targets:
            return
        right_w   = self._measure_item_width(self.right_tag) or int(self._right_width or 720)
        field_w   = max_field if max_field > 0 else right_w // 4
        value_w   = max_value if max_value > 0 else right_w // 4
        resolved_w = max(80, right_w - field_w - value_w - 16)
        col_widths = [field_w, value_w, resolved_w]
        for tag, col in wrap_targets:
            if not dpg.does_item_exist(tag):
                continue
            try:
                width = col_widths[col] if col < len(col_widths) else col_widths[-1]
                dpg.configure_item(tag, wrap=max(80, int(width)))
            except Exception:
                continue

    def _schedule_wrap_update(
        self,
        table_tag: str,
        col_tags: tuple[str, str, str],
        wrap_targets: list[tuple[str, int]],
        max_field: int = 0,
        max_value: int = 0,
        attempt: int = 0,
    ) -> None:
        if not wrap_targets:
            return
        frame = dpg.get_frame_count() + 1
        dpg.set_frame_callback(
            frame,
            lambda: self._apply_wrap_update(table_tag, col_tags, wrap_targets, max_field, max_value, attempt),
        )

    def _apply_wrap_update(
        self,
        table_tag: str,
        col_tags: tuple[str, str, str],
        wrap_targets: list[tuple[str, int]],
        max_field: int,
        max_value: int,
        attempt: int,
    ) -> None:
        col_widths = self._compute_col_widths(table_tag, col_tags, max_field, max_value)
        right_w = self._measure_item_width(self.right_tag)
        for tag, col in wrap_targets:
            if not dpg.does_item_exist(tag):
                continue
            try:
                width = col_widths[col] if col < len(col_widths) else col_widths[-1]
                if right_w:
                    width = min(width, right_w)
                dpg.configure_item(tag, wrap=max(80, int(width)))
            except Exception:
                continue

    def _refresh_table_wraps_now(self) -> None:
        if not self._wrap_tables:
            return
        for table_tag, (col_tags, wrap_targets, max_field, max_value) in list(self._wrap_tables.items()):
            if not dpg.does_item_exist(table_tag):
                continue
            self._apply_wrap_update(table_tag, col_tags, wrap_targets, max_field, max_value, attempt=0)

    def _refresh_table_wraps_deferred(self) -> None:
        if not self._wrap_tables:
            return
        for table_tag, (col_tags, wrap_targets, max_field, max_value) in list(self._wrap_tables.items()):
            if not dpg.does_item_exist(table_tag):
                continue
            self._schedule_wrap_update(table_tag, col_tags, wrap_targets, max_field, max_value, attempt=0)


    def _measure_item_width(self, tag: str) -> int:
        try:
            w = dpg.get_item_rect_size(tag)[0]
        except Exception:
            w = 0
        if not w:
            try:
                w = dpg.get_item_width(tag)
            except Exception:
                w = 0
        return int(w) if w else 0

    def _measure_column_wrap_widths(
        self, table_tag: str, col_tags: tuple[str, str, str]
    ) -> list[int]:
        widths = [self._measure_item_width(tag) for tag in col_tags]
        return [max(0, int(w)) for w in widths]

    @staticmethod
    def _humanize_field_path(field_path: str, *, strip_prefix: str = "") -> str:
        if strip_prefix and field_path.startswith(strip_prefix):
            field_path = field_path[len(strip_prefix):]

        if field_path == "usability":
            return "Unusable by"

        if field_path.startswith("melee_anim["):
            idx_text = field_path[len("melee_anim[") :].split("]", 1)[0]
            try:
                idx = int(idx_text)
            except ValueError:
                idx = -1
            labels = {
                0: "Animation: Overhand Swing %",
                1: "Animation: Backhand Swing %",
                2: "Animation: Thrust %",
            }
            if idx in labels:
                return f"Melee Anim [{idx + 1}] ({labels[idx]})"

        kit_labels = {
            "kit_usability_1": "Unusable by kit (1/4)",
            "kit_usability_2": "Unusable by kit (2/4)",
            "kit_usability_3": "Unusable by kit (3/4)",
            "kit_usability_4": "Unusable by kit (4/4)",
        }
        if field_path in kit_labels:
            return kit_labels[field_path]

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

    @staticmethod
    def _reorder_header_rows(
        rows: list[tuple[str, str, str, tuple[int, int, list[float]] | None]]
    ) -> list[tuple[str, str, str, tuple[int, int, list[float]] | None]]:
        if not rows:
            return rows
        kit_keys = {
            "header.kit_usability_1",
            "header.kit_usability_2",
            "header.kit_usability_3",
            "header.kit_usability_4",
        }
        kit_rows = [r for r in rows if r[0] in kit_keys]
        other_rows = [r for r in rows if r[0] not in kit_keys]

        def kit_sort_key(row: tuple[str, str, str, tuple[int, int, list[float]] | None]) -> int:
            name = row[0]
            if name.endswith("_1"):
                return 1
            if name.endswith("_2"):
                return 2
            if name.endswith("_3"):
                return 3
            if name.endswith("_4"):
                return 4
            return 99

        kit_rows.sort(key=kit_sort_key)

        # Insert kit rows right after header.usability if present.
        out: list[tuple[str, str, str, tuple[int, int, list[float]] | None]] = []
        inserted = False
        for row in other_rows:
            out.append(row)
            if row[0] == "header.usability":
                out.extend(kit_rows)
                inserted = True
        if not inserted:
            out.extend(kit_rows)
        return out

    @staticmethod
    def _resolve_animation_code(value: str) -> str:
        code = (value or "").strip().upper()
        if not code:
            return ""
        mapping = {
            "2A": "Leather Armor",
            "3A": "Chainmail",
            "4A": "Plate Mail",
            "2W": "Robe",
            "3W": "Robe",
            "4W": "Robe",
            "AX": "Axe",
            "BW": "Bow",
            "CB": "Crossbow",
            "CL": "Club",
            "D1": "Buckler",
            "D2": "Shield (Small)",
            "D3": "Shield (Medium)",
            "D4": "Shield (Large)",
            "DD": "Dagger",
            "FL": "Flail",
            "FS": "Flame Sword",
            "H0": "Small Vertical Horns",
            "H1": "Large Horizontal Horns",
            "H2": "Feather Wings",
            "H3": "Top Plume",
            "H4": "Dragon Wings",
            "H5": "Feather Sideburns",
            "H6": "Large Curved Horns",
            "HB": "Halberd",
            "MC": "Mace",
            "MS": "Morning Star",
            "QS": "Quarter Staff (Metal)",
            "S1": "Sword 1-Handed",
            "S2": "Sword 2-Handed",
            "SL": "Sling",
            "SP": "Spear",
            "SS": "Short Sword",
            "WH": "War Hammer",
            "S3": "Katana",
            "SC": "Scimitar",
        }
        return mapping.get(code, "")

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

    def handle_mouse_event(self) -> None:
        """Handle mouse events for panel resizing via drag on the divider."""
        if not dpg.does_item_exist(self.root_tag):
            return
        if not dpg.get_item_configuration(self.root_tag).get("show", True):
            self._browser.hide_divider_highlight()
            return
        
        mouse_x, _mouse_y = dpg.get_mouse_pos()
        is_button_down = dpg.is_mouse_button_down(dpg.mvMouseButton_Left)
        
        # Calculate right pane position for robust divider dragging
        gap_width = 12
        right_pane_x = self._browser.get_divider_x() + gap_width
        
        # Let the browser pane handle its divider drag with spacing awareness
        self._browser.handle_divider_drag(
            mouse_x,
            is_button_down,
            right_pane_x=right_pane_x,
            gap_width=gap_width,
        )
        
        # Update right panel sizing based on browser's new width
        if self._total_width > 0 and self._total_height > 0:
            left_w = self._browser.get_panel_width()
            right_w = max(260, self._total_width - left_w - gap_width)
            body_h = max(0, self._total_height - 34 - 6)
            dpg.configure_item(self.right_tag, width=right_w, height=body_h)
            if right_w != self._right_width:
                self._right_width = right_w
                self._refresh_table_wraps_now()
