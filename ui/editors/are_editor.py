"""ui/editors/are_editor.py

ARE (Area) browser and viewer panel.

Three tabs mirror the ITM editor:
  • Structured  — tree of named sections with flat field tables
  • JSON Tree   — collapsible tree of the raw JSON dict
  • Raw JSON    — read-only text box with full JSON

The browser columns are: ResRef | Name | Version.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

import dearpygui.dearpygui as dpg

from core.services.are_catalog import AreCatalog
from core.index import IndexEntry
from ui.core import EditorProgressHandler, EditorToolbar, ResourceBrowserPane


# ---------------------------------------------------------------------------
# Section display metadata
# ---------------------------------------------------------------------------

# For each top-level key in AreFile.to_json(), a friendly section label.
_SECTION_LABELS: dict[str, str] = {
    "header":           "Header",
    "actors":           "Actors",
    "regions":          "Regions",
    "spawn_points":     "Spawn Points",
    "entrances":        "Entrances",
    "containers":       "Containers",
    "ambients":         "Ambients",
    "variables":        "Variables",
    "doors":            "Doors",
    "animations":       "Animations",
    "automap_notes":    "Automap Notes",
    "tiled_objects":    "Tiled Objects",
    "projectile_traps": "Projectile Traps",
    "song_entries":     "Song Entries",
    "rest_interruption":"Rest Interruption",
}

# Keys rendered in order; raw blobs shown last under "Other"
_SECTION_ORDER = list(_SECTION_LABELS.keys())


class AreEditorPanel:
    """Read-only ARE browser with list/search and structured/JSON detail tabs."""

    def __init__(
        self,
        parent_tag: str,
        catalog: AreCatalog,
        *,
        tag_prefix: str = "are_editor",
    ) -> None:
        self.catalog = catalog
        self.tag_prefix = tag_prefix

        self.root_tag               = self._tag("root")
        self.body_tag               = self._tag("body")
        self.right_tag              = self._tag("right")
        self.structured_tag         = self._tag("structured")
        self.raw_tree_tag           = self._tag("raw_tree")
        self.raw_text_tag           = self._tag("raw_text")
        self.raw_json_textbox_tag   = self._tag("raw_json_textbox")

        self._results:               list[IndexEntry] = []
        self._selected_resref:       str | None = None
        self._last_payload:          dict | None = None
        self._total_width:           int = 800
        self._total_height:          int = 600
        self._right_width:           int = 540

        self._build_ui(parent_tag)
        self._load_games()

    # ------------------------------------------------------------------
    # Tag helper
    # ------------------------------------------------------------------

    def _tag(self, name: str) -> str:
        return f"{self.tag_prefix}_{name}"

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, parent_tag: str) -> None:
        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=False,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            self._toolbar = EditorToolbar(
                parent_tag=self.root_tag,
                games=[],
                on_game_selected=self._on_game_selected,
                on_refresh=self._on_refresh_clicked,
                on_rebuild=self._on_rebuild_clicked,
                extra_controls=self._add_toolbar_controls,
                tag_prefix=self._tag("toolbar"),
            )
            self._progress_handler = EditorProgressHandler(self._toolbar.set_status)
            self.catalog.set_progress_callback(self._progress_handler.on_progress)

            with dpg.group(tag=self.body_tag, horizontal=True):
                self._browser = ResourceBrowserPane(
                    parent_tag=self.body_tag,
                    columns=["ResRef", "Name", "Version"],
                    on_row_selected=self._on_row_selected,
                    tag_prefix=self._tag("browser"),
                )

                with dpg.child_window(tag=self.right_tag, border=True):
                    with dpg.tab_bar():
                        with dpg.tab(label="Structured"):
                            with dpg.child_window(tag=self.structured_tag, border=False):
                                dpg.add_text("Select an ARE entry.")
                        with dpg.tab(label="JSON Tree"):
                            with dpg.child_window(tag=self.raw_tree_tag, border=False):
                                dpg.add_text("Select an ARE entry.")
                        with dpg.tab(label="Raw JSON"):
                            with dpg.child_window(tag=self.raw_text_tag, border=False):
                                dpg.add_text("Select an ARE entry.")

    def _add_toolbar_controls(self, parent_tag: str) -> None:
        """Extra toolbar widgets (search box)."""
        dpg.add_input_text(
            tag=self._tag("search"),
            hint="Search…",
            width=200,
            parent=parent_tag,
            callback=lambda _s, _a, _u: self.refresh_results(),
        )

    # ------------------------------------------------------------------
    # Size management
    # ------------------------------------------------------------------

    def set_size(self, width: int, height: int) -> None:
        self._total_width  = width
        self._total_height = height
        dpg.configure_item(self.root_tag, width=max(0, width), height=max(0, height))
        top_h  = 34
        body_h = max(0, height - top_h - 6)

        self._browser.set_size(width, body_h)
        left_w = self._browser.get_panel_width()
        right_w = max(260, width - left_w - 12)
        self._right_width = right_w

        dpg.configure_item(self.body_tag, pos=[0, top_h])
        dpg.configure_item(self.right_tag, width=right_w, height=body_h)

    # ------------------------------------------------------------------
    # Game / index lifecycle
    # ------------------------------------------------------------------

    def _load_games(self) -> None:
        try:
            games = self.catalog.list_games()
            game_ids = [g.game_id for g in games]
            self._toolbar.set_games(game_ids)
            if not game_ids:
                self._toolbar.set_status("No game installations detected.")
                return
            self._toolbar.set_game(game_ids[0])
            self._on_game_selected(game_ids[0])
        except Exception as exc:
            self._toolbar.set_status(f"No games found: {exc}")

    def _on_game_selected(self, game_id: str) -> None:
        try:
            self._toolbar.set_status(f"Loading {game_id}…")
            self.catalog.select_game(game_id)
            self.catalog.load_index(force_rebuild=False)
            self.refresh_results()
            self._toolbar.set_status(f"{game_id} ready.")
        except Exception as exc:
            self._toolbar.set_status(f"Error: {exc}")

    def _on_refresh_clicked(self) -> None:
        self.refresh_results()

    def _on_rebuild_clicked(self) -> None:
        try:
            self._toolbar.set_status("Rebuilding index…")
            self.catalog.load_index(force_rebuild=True)
            self.refresh_results()
            self._toolbar.set_status("Index rebuilt.")
        except Exception as exc:
            self._toolbar.set_status(f"Rebuild failed: {exc}")

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------

    def refresh_results(self) -> None:
        query = ""
        try:
            query = dpg.get_value(self._tag("search")) or ""
        except Exception:
            pass
        self._results = self.catalog.search(query)
        rows = []
        for entry in self._results:
            resref  = str(entry.resref)
            wed     = entry.display_name or ""
            version = (entry.data or {}).get("header", {}).get("version", "")
            rows.append([resref, wed, version])
        self._browser.populate_rows(rows)

    def _on_row_selected(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self._results):
            return
        entry = self._results[row_index]
        resref = str(entry.resref)
        self._selected_resref = resref
        try:
            payload = self.catalog.load_entry_data(entry)
            self._last_payload = payload
            self._render_structured(payload)
            self._render_raw(payload)
            self._toolbar.set_status(f"Loaded {resref}.")
        except Exception as exc:
            self._toolbar.set_status(f"Error loading {resref}: {exc}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Structured renderer
    # ------------------------------------------------------------------

    def _render_structured(self, payload: dict) -> None:
        dpg.delete_item(self.structured_tag, children_only=True)

        if not payload:
            dpg.add_text("(empty)", parent=self.structured_tag)
            return

        for key in _SECTION_ORDER:
            if key not in payload:
                continue
            value = payload[key]
            label = _SECTION_LABELS.get(key, key)

            if isinstance(value, list):
                section_label = f"{label}  [{len(value)}]"
                default_open  = key == "header" or len(value) <= 5
                with dpg.tree_node(
                    label=section_label,
                    parent=self.structured_tag,
                    default_open=default_open,
                ):
                    node_tag = dpg.last_item()
                    if not value:
                        dpg.add_text("(none)", parent=node_tag)
                    else:
                        for idx, item in enumerate(value):
                            item_label = self._item_summary(key, item, idx)
                            with dpg.tree_node(
                                label=item_label,
                                parent=node_tag,
                                default_open=False,
                            ):
                                item_node = dpg.last_item()
                                self._render_flat_table(item_node, item, f"{self._tag('tbl')}_{key}_{idx}")

            elif isinstance(value, dict):
                with dpg.tree_node(
                    label=label,
                    parent=self.structured_tag,
                    default_open=(key == "header"),
                ):
                    tbl_node = dpg.last_item()
                    self._render_flat_table(tbl_node, value, f"{self._tag('tbl')}_{key}")
            else:
                with dpg.tree_node(
                    label=label,
                    parent=self.structured_tag,
                    default_open=False,
                ):
                    dpg.add_text(str(value), parent=dpg.last_item())

        # Any keys not in the known order (raw blobs, etc.)
        extra_keys = [k for k in payload if k not in _SECTION_ORDER]
        if extra_keys:
            with dpg.tree_node(
                label="Other",
                parent=self.structured_tag,
                default_open=False,
            ):
                other_node = dpg.last_item()
                for k in extra_keys:
                    dpg.add_text(f"{k}: {payload[k]}", parent=other_node)

    @staticmethod
    def _item_summary(section_key: str, item: dict, idx: int) -> str:
        """Generate a one-line summary label for a list item."""
        if not isinstance(item, dict):
            return f"[{idx}]"
        # Try common name fields
        for name_field in ("name", "script_name", "resref"):
            v = item.get(name_field, "")
            if v and isinstance(v, str) and v.strip():
                return f"[{idx}]  {v.strip()}"
        # For actors, show the CRE resref
        if section_key == "actors":
            cre = item.get("cre_resref", "")
            if cre:
                return f"[{idx}]  {cre}"
        # For entrances, show name
        if section_key == "entrances":
            n = item.get("name", "")
            if n:
                return f"[{idx}]  {n}"
        return f"[{idx}]"

    def _render_flat_table(
        self,
        parent: str | int,
        data: dict,
        table_tag: str,
    ) -> None:
        """Render a two-column (Field / Value) table for a flat dict."""
        if not data:
            dpg.add_text("(empty)", parent=parent)
            return

        rows = self._flatten_dict(data)
        if not rows:
            dpg.add_text("(empty)", parent=parent)
            return

        # Measure column widths
        field_w = 8
        value_w = 8
        for field_path, value_text in rows:
            try:
                if field_path:
                    fw = dpg.get_text_size(field_path)
                    if fw and fw[0]:
                        field_w = max(field_w, int(fw[0]) + 8)
            except Exception:
                pass
            try:
                vt = str(value_text)
                if vt:
                    vw = dpg.get_text_size(vt)
                    if vw and vw[0]:
                        value_w = max(value_w, int(vw[0]) + 8)
            except Exception:
                pass

        field_w = min(field_w, 260)
        value_w = min(value_w, 400)

        with dpg.table(
            tag=table_tag,
            parent=parent,
            header_row=False,
            borders_innerH=False,
            borders_outerH=False,
            borders_innerV=True,
            borders_outerV=False,
            resizable=True,
        ):
            dpg.add_table_column(width_fixed=True, init_width_or_weight=field_w)
            dpg.add_table_column(width_fixed=True, init_width_or_weight=value_w)

            for field_path, value_text in rows:
                with dpg.table_row():
                    label = self._humanize(field_path)
                    dpg.add_text(label)
                    dpg.add_text(str(value_text))

    @staticmethod
    def _flatten_dict(
        d: dict,
        prefix: str = "",
        depth: int = 0,
        max_depth: int = 3,
    ) -> list[tuple[str, str]]:
        """Flatten a nested dict into (dotted.path, value_text) pairs."""
        rows: list[tuple[str, str]] = []
        if depth > max_depth or not isinstance(d, dict):
            return rows
        for key, value in d.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and depth < max_depth:
                rows.extend(AreEditorPanel._flatten_dict(value, path, depth + 1, max_depth))
            elif isinstance(value, list):
                rows.append((path, f"[{len(value)} items]"))
            else:
                rows.append((path, str(value) if value is not None else ""))
        return rows

    @staticmethod
    def _humanize(field_path: str) -> str:
        """Convert a dotted field path to a readable label."""
        parts = field_path.split(".")
        name = parts[-1]
        return name.replace("_", " ").title()

    # ------------------------------------------------------------------
    # Raw renderers
    # ------------------------------------------------------------------

    def _render_raw(self, payload: dict) -> None:
        # JSON Tree tab
        dpg.delete_item(self.raw_tree_tag, children_only=True)
        with dpg.tree_node(label="area", parent=self.raw_tree_tag, default_open=True):
            node = dpg.last_item()
            for k, v in payload.items():
                self._render_json_node(node, v, default_open=False, key=str(k))

        # Raw JSON tab
        try:
            raw_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            raw_text = f"(serialization error: {exc})"
        dpg.delete_item(self.raw_text_tag, children_only=True)
        dpg.add_input_text(
            tag=self.raw_json_textbox_tag,
            multiline=True,
            readonly=True,
            width=-1,
            height=-1,
            default_value=raw_text,
            parent=self.raw_text_tag,
        )

    def _render_json_node(
        self,
        parent: str | int,
        value: Any,
        *,
        default_open: bool,
        key: str = "",
    ) -> None:
        if isinstance(value, dict):
            label = key if key else "{ }"
            with dpg.tree_node(label=label, parent=parent, default_open=default_open):
                node = dpg.last_item()
                for k, v in value.items():
                    self._render_json_node(node, v, default_open=False, key=str(k))
        elif isinstance(value, list):
            label = f"{key} [{len(value)}]" if key else f"[{len(value)}]"
            with dpg.tree_node(label=label, parent=parent, default_open=False):
                node = dpg.last_item()
                for idx, item in enumerate(value):
                    self._render_json_node(node, item, default_open=False, key=f"[{idx}]")
        else:
            text = f"{key}: {value}" if key else str(value)
            dpg.add_text(text, parent=parent)