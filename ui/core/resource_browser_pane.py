"""Reusable left-panel browser component for browsing resources (characters, items, etc.)."""

from __future__ import annotations

from typing import Any, Callable

import dearpygui.dearpygui as dpg


class ResourceBrowserPane:
    """
    Generic left-panel browser with a configurable table.
    
    Can be reused for different resource types (characters, items, spells, etc.).
    Handles table layout, row selection, and panel resizing.
    """

    def __init__(
        self,
        parent_tag: str,
        columns: list[str],
        on_row_selected: Callable[[int], None],
        *,
        tag_prefix: str = "browser",
    ) -> None:
        """
        Initialize the browser pane.
        
        Args:
            parent_tag: Parent DPG element tag
            columns: List of column labels for the table
            on_row_selected: Callback when a row is selected (receives row index)
            tag_prefix: Prefix for DPG tag generation
        """
        self.parent_tag = parent_tag
        self.columns = columns
        self.on_row_selected = on_row_selected
        self.tag_prefix = tag_prefix

        self.root_tag = self._tag("root")
        self.list_tag = self._tag("list")
        self.grid_tag = self._tag("grid")
        self.table_tag = self._tag("table")
        self.grid_table_tag = self._tag("grid_table")
        self.grid_normal_theme_tag = self._tag("grid_normal_theme")
        self.grid_selected_theme_tag = self._tag("grid_selected_theme")
        self.grid_default_icon_tag = self._tag("grid_default_icon")
        self.grid_click_handler_tag = self._tag("grid_click_handler")
        
        self._row_selectables: list[str] = []
        self._selected_index: int | None = None
        self._rows: list[tuple[str, ...]] = []

        # Grid view state
        self._view_mode: str = "list"
        self._grid_labels: list[str] = []
        self._grid_icons: list[tuple[int, int, list[float]] | None] = []
        self._grid_icon_textures: list[tuple[str, int, int] | None] = []
        self._grid_texture_tags: list[str] = []
        self._grid_tile_tags: list[str] = []
        self._grid_image_tags: list[int | str] = []
        self._grid_icon_pad_tags: list[str] = []
        self._grid_texture_counter = 0
        self._grid_columns: int = 1
        self._grid_tile_width = 110
        self._grid_tile_height = 110
        self._grid_icon_size = 48
        self._grid_tile_padding = 8
        
        # Panel sizing state
        self._total_width: int = 0
        self._total_height: int = 0
        self._panel_width: float = 0.30  # Default 30% of parent width
        self._is_dragging_divider: bool = False
        self._last_mouse_x: int = 0
        self._gap_width: int = 12  # Width of the divider gap between panes

        with dpg.theme(tag=self.grid_normal_theme_tag):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (37, 37, 38, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (54, 54, 59, 255))
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 4, 4)

        with dpg.theme(tag=self.grid_selected_theme_tag):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (45, 45, 55, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (0, 120, 212, 255))
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 4, 4)

        with dpg.handler_registry(tag=self.grid_click_handler_tag):
            dpg.add_mouse_click_handler(callback=self._on_grid_mouse_click)

        # Create the UI
        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=True,
            no_scrollbar=False,
        ):
            with dpg.group(tag=self.list_tag, show=True):
                # Create table with dynamic columns
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
                    for column_label in columns:
                        dpg.add_table_column(label=column_label)

            with dpg.group(tag=self.grid_tag, show=False):
                pass

    def _tag(self, suffix: str) -> str:
        """Generate a DPG tag."""
        return f"{self.tag_prefix}_{suffix}"

    def set_size(self, total_width: int, total_height: int) -> None:
        """
        Update the browser pane dimensions.
        
        Args:
            total_width: Total available width
            total_height: Total available height
        """
        self._total_width = total_width
        self._total_height = total_height
        
        pane_width = max(180, int(total_width * self._panel_width))
        pane_height = max(100, total_height)
        
        dpg.configure_item(self.root_tag, width=pane_width, height=pane_height)

        if self._view_mode == "grid" and self._rows:
            self._update_grid_layout(pane_width)

    def set_view_mode(self, mode: str) -> None:
        """Set the browser view mode ('list' or 'grid')."""
        normalized = str(mode or "").strip().lower()
        if normalized in {"grid", "icons", "icon"}:
            normalized = "grid"
        else:
            normalized = "list"

        if normalized == self._view_mode:
            return

        self._view_mode = normalized
        if dpg.does_item_exist(self.list_tag):
            dpg.configure_item(self.list_tag, show=self._view_mode == "list")
        if dpg.does_item_exist(self.grid_tag):
            dpg.configure_item(self.grid_tag, show=self._view_mode == "grid")

        if self._view_mode == "grid":
            self._render_grid()
        else:
            self._render_list()

        if self._selected_index is not None:
            self.select_row(self._selected_index)

    def get_view_mode(self) -> str:
        """Return the current browser view mode."""
        return self._view_mode

    def get_panel_width(self) -> int:
        """Get the current pixel width of the browser pane."""
        return max(180, int(self._total_width * self._panel_width))

    def get_divider_x(self) -> int:
        """Get the absolute X position of the right divider (for cursor change detection)."""
        if not dpg.does_item_exist(self.root_tag):
            return 0
        root_pos = dpg.get_item_pos(self.root_tag)
        return root_pos[0] + self.get_panel_width()

    def check_divider_hover(self, screen_x: int, screen_y: int) -> bool:
        """Return True if the given screen coordinates are over the divider gap.

        Called from titlebar.py's WM_NCHITTEST handler (screen coordinates).
        Converts to viewport-local coordinates via Win32 ClientToScreen.
        Must be fast and allocation-free.
        """
        try:
            import ctypes
            import ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, dpg.get_viewport_title())
            if not hwnd:
                return False
            pt = wt.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            client_x = screen_x - pt.x
            client_y = screen_y - pt.y
        except Exception:
            return False

        if client_y < 0 or client_y > dpg.get_viewport_height():
            return False

        divider_x = self.get_divider_x()
        right_pane_x = divider_x + self._gap_width
        return divider_x <= client_x <= right_pane_x

    def populate_rows(
        self,
        items: list[tuple[str, ...]],
        *,
        grid_labels: list[str] | None = None,
        grid_icons: list[tuple[int, int, list[float]] | None] | None = None,
    ) -> None:
        """
        Populate the table with rows.
        
        Args:
            items: List of tuples, where each tuple contains values for the columns
                   (e.g., [(resref1, name1), (resref2, name2), ...])
        """
        self._rows = list(items or [])
        self._grid_labels = self._derive_grid_labels(self._rows, grid_labels)
        self._grid_icons = self._normalize_grid_icons(self._rows, grid_icons)
        self._selected_index = None

        dpg.delete_item(self.grid_tag, children_only=True)
        self._clear_grid_textures()
        self._grid_icon_textures.clear()
        self._grid_tile_tags.clear()
        self._grid_image_tags.clear()
        self._grid_icon_pad_tags.clear()

        if self._view_mode == "grid":
            self._render_grid()
        else:
            self._render_list()

    def select_row(self, index: int) -> None:
        """
        Select a row by index.
        
        Args:
            index: Row index to select
        """
        if index < 0 or index >= max(len(self._row_selectables), len(self._grid_tile_tags)):
            return

        # Update selection state for display (list)
        for row_idx, row_tag in enumerate(self._row_selectables):
            if dpg.does_item_exist(row_tag):
                dpg.set_value(row_tag, row_idx == index)

        # Update selection state for display (grid)
        for row_idx, tile_tag in enumerate(self._grid_tile_tags):
            if not dpg.does_item_exist(tile_tag):
                continue
            theme = self.grid_selected_theme_tag if row_idx == index else self.grid_normal_theme_tag
            dpg.bind_item_theme(tile_tag, theme)

        self._selected_index = index

    def get_selected_index(self) -> int | None:
        """Get the currently selected row index."""
        return self._selected_index

    def clear_rows(self) -> None:
        """Clear all rows from the table."""
        dpg.delete_item(self.table_tag, children_only=True, slot=1)
        dpg.delete_item(self.grid_tag, children_only=True)
        self._row_selectables.clear()
        self._grid_tile_tags.clear()
        self._rows.clear()
        self._grid_labels.clear()
        self._grid_icons.clear()
        self._grid_icon_textures.clear()
        self._clear_grid_textures()
        self._grid_image_tags.clear()
        self._grid_icon_pad_tags.clear()
        self._selected_index = None

    def _on_row_clicked(self, _sender: Any, app_data: bool, user_data: int) -> None:
        """Handle row selection click."""
        if not bool(app_data):
            return
        try:
            self.select_row(user_data)
            self.on_row_selected(user_data)
        except Exception:
            pass

    def _on_grid_mouse_click(self, _sender: Any, app_data: Any) -> None:
        if self._view_mode != "grid":
            return
        if app_data != dpg.mvMouseButton_Left:
            return
        for idx, tile_tag in enumerate(self._grid_tile_tags):
            if not dpg.does_item_exist(tile_tag):
                continue
            try:
                if dpg.is_item_hovered(tile_tag):
                    self.select_row(idx)
                    self.on_row_selected(idx)
                    break
            except Exception:
                continue

    def _render_list(self) -> None:
        dpg.delete_item(self.table_tag, children_only=True, slot=1)
        self._row_selectables.clear()
        if not self._rows:
            return

        for idx, item_data in enumerate(self._rows):
            row_tag = self._tag(f"row_{idx}")
            self._row_selectables.append(row_tag)

            with dpg.table_row(parent=self.table_tag):
                dpg.add_selectable(
                    tag=row_tag,
                    label=str(item_data[0]) if item_data else "",
                    span_columns=True,
                    callback=self._on_row_clicked,
                    user_data=idx,
                    height=22,
                )

                for cell_data in item_data[1:]:
                    dpg.add_text(str(cell_data))

    def _render_grid(self) -> None:
        dpg.delete_item(self.grid_tag, children_only=True)
        self._grid_tile_tags.clear()
        self._grid_image_tags.clear()
        self._grid_icon_pad_tags.clear()

        if not self._rows:
            return

        pane_width = self._measure_root_width() or self.get_panel_width()
        self._grid_columns = self._compute_grid_columns(pane_width)
        self._ensure_grid_textures()

        with dpg.table(
            tag=self.grid_table_tag,
            parent=self.grid_tag,
            header_row=False,
            policy=dpg.mvTable_SizingFixedFit,
            row_background=False,
            resizable=False,
            sortable=False,
            borders_innerV=False,
            borders_outerV=False,
            borders_innerH=False,
            borders_outerH=False,
        ):
            for _ in range(self._grid_columns):
                dpg.add_table_column(
                    width_fixed=True,
                    init_width_or_weight=self._grid_tile_width,
                )

            idx = 0
            total = len(self._rows)
            while idx < total:
                with dpg.table_row():
                    for _col in range(self._grid_columns):
                        if idx >= total:
                            dpg.add_spacer(width=self._grid_tile_width, height=self._grid_tile_height)
                            continue
                        self._add_grid_tile(idx)
                        idx += 1

    def _add_grid_tile(self, idx: int) -> None:
        label = self._grid_labels[idx] if idx < len(self._grid_labels) else ""
        icon_tex = self._grid_icon_textures[idx] if idx < len(self._grid_icon_textures) else None
        if icon_tex is None:
            icon_tag, iw, ih = self._ensure_default_grid_icon()
        else:
            icon_tag, iw, ih = icon_tex

        draw_w, draw_h = self._scale_icon(iw, ih, self._grid_icon_size)
        tile_tag = self._tag(f"grid_tile_{idx}")
        self._grid_tile_tags.append(tile_tag)

        with dpg.child_window(
            tag=tile_tag,
            width=self._grid_tile_width,
            height=self._grid_tile_height,
            border=True,
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                pad = max(0, int((self._grid_tile_width - draw_w) / 2))
                pad_tag = self._tag(f"grid_icon_pad_{idx}")
                dpg.add_spacer(width=pad, tag=pad_tag)
                image_tag = self._tag(f"grid_image_{idx}")
                dpg.add_image(icon_tag, width=draw_w, height=draw_h, tag=image_tag)
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_spacer(width=4)
                dpg.add_text(label, wrap=max(1, self._grid_tile_width - 8))

        dpg.bind_item_theme(tile_tag, self.grid_normal_theme_tag)

        if idx >= len(self._grid_image_tags):
            self._grid_image_tags.append(image_tag)
        else:
            self._grid_image_tags[idx] = image_tag

        if idx >= len(self._grid_icon_pad_tags):
            self._grid_icon_pad_tags.append(pad_tag)
        else:
            self._grid_icon_pad_tags[idx] = pad_tag

    def _update_grid_layout(self, pane_width: int) -> None:
        new_cols = self._compute_grid_columns(pane_width)
        if new_cols != self._grid_columns:
            self._grid_columns = new_cols
            self._render_grid()

    def _compute_grid_columns(self, pane_width: int) -> int:
        usable = max(1, int(pane_width) - self._grid_tile_padding)
        return max(1, usable // self._grid_tile_width)

    def _scale_icon(self, width: int, height: int, target: int) -> tuple[int, int]:
        if width <= 0 or height <= 0:
            return target, target
        scale = min(target / max(1, width), target / max(1, height))
        return max(1, int(width * scale)), max(1, int(height * scale))

    def _ensure_grid_textures(self) -> None:
        if not self._grid_icons:
            return
        if self._grid_icon_textures and len(self._grid_icon_textures) == len(self._grid_icons):
            return

        self._clear_grid_textures()
        self._grid_icon_textures.clear()

        for icon in self._grid_icons:
            if icon is None:
                self._grid_icon_textures.append(None)
                continue
            width, height, rgba = icon
            self._grid_texture_counter += 1
            tag = self._tag(f"grid_tex_{self._grid_texture_counter}")
            dpg.add_static_texture(
                width=max(1, int(width)),
                height=max(1, int(height)),
                default_value=rgba,
                tag=tag,
                parent="window_icon_textures",
            )
            self._grid_texture_tags.append(tag)
            self._grid_icon_textures.append((tag, int(width), int(height)))

    def set_grid_icon(self, index: int, icon: tuple[int, int, list[float]] | None) -> bool:
        """Update a grid tile's icon texture and refresh its image widget."""
        if index < 0 or index >= len(self._rows):
            return False

        if index >= len(self._grid_icons):
            self._grid_icons.extend([None] * (index + 1 - len(self._grid_icons)))
        if index >= len(self._grid_icon_textures):
            self._grid_icon_textures.extend([None] * (index + 1 - len(self._grid_icon_textures)))

        self._grid_icons[index] = icon

        icon_tex: tuple[str, int, int] | None = None
        if icon is not None:
            width, height, rgba = icon
            self._grid_texture_counter += 1
            tag = self._tag(f"grid_tex_{self._grid_texture_counter}")
            dpg.add_static_texture(
                width=max(1, int(width)),
                height=max(1, int(height)),
                default_value=rgba,
                tag=tag,
                parent="window_icon_textures",
            )
            self._grid_texture_tags.append(tag)
            icon_tex = (tag, int(width), int(height))

        self._grid_icon_textures[index] = icon_tex

        if index >= len(self._grid_image_tags):
            return False
        image_tag = self._grid_image_tags[index]
        if not dpg.does_item_exist(image_tag):
            return False

        if icon_tex is None:
            icon_tag, iw, ih = self._ensure_default_grid_icon()
        else:
            icon_tag, iw, ih = icon_tex

        draw_w, draw_h = self._scale_icon(iw, ih, self._grid_icon_size)
        dpg.configure_item(image_tag, texture_tag=icon_tag, width=draw_w, height=draw_h)

        if index < len(self._grid_icon_pad_tags):
            pad_tag = self._grid_icon_pad_tags[index]
            if dpg.does_item_exist(pad_tag):
                pad = max(0, int((self._grid_tile_width - draw_w) / 2))
                dpg.configure_item(pad_tag, width=pad)
        return True

    def _clear_grid_textures(self) -> None:
        for tag in self._grid_texture_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._grid_texture_tags.clear()

    def _ensure_default_grid_icon(self) -> tuple[str, int, int]:
        if dpg.does_item_exist(self.grid_default_icon_tag):
            return self.grid_default_icon_tag, 32, 32

        size = 32
        bg = (0.15, 0.15, 0.15, 1.0)
        fg = (0.85, 0.85, 0.85, 1.0)
        pixels = [[*bg] for _ in range(size * size)]

        def set_px(x: int, y: int) -> None:
            if 0 <= x < size and 0 <= y < size:
                pixels[y * size + x] = [fg[0], fg[1], fg[2], fg[3]]

        # Question mark glyph
        for x in range(10, 22):
            set_px(x, 6)
        for y in range(7, 12):
            set_px(21, y)
        for x in range(14, 21):
            set_px(x, 12)
        for y in range(13, 18):
            set_px(14, y)
        for y in range(22, 26):
            set_px(14, y)

        flat = [c for px in pixels for c in px]
        dpg.add_static_texture(
            width=size,
            height=size,
            default_value=flat,
            tag=self.grid_default_icon_tag,
            parent="window_icon_textures",
        )
        return self.grid_default_icon_tag, size, size

    def _derive_grid_labels(
        self,
        items: list[tuple[str, ...]],
        grid_labels: list[str] | None,
    ) -> list[str]:
        if grid_labels is not None and len(grid_labels) == len(items):
            return [str(label) for label in grid_labels]
        labels: list[str] = []
        for item in items:
            if len(item) > 1 and str(item[1]).strip():
                labels.append(str(item[1]))
            elif item:
                labels.append(str(item[0]))
            else:
                labels.append("")
        return labels

    def _normalize_grid_icons(
        self,
        items: list[tuple[str, ...]],
        grid_icons: list[tuple[int, int, list[float]] | None] | None,
    ) -> list[tuple[int, int, list[float]] | None]:
        if grid_icons is None:
            return [None for _ in items]
        if len(grid_icons) != len(items):
            return [None for _ in items]
        return list(grid_icons)

    def _measure_root_width(self) -> int:
        if not dpg.does_item_exist(self.root_tag):
            return 0
        try:
            w = dpg.get_item_rect_size(self.root_tag)[0]
        except Exception:
            w = 0
        if not w:
            try:
                w = dpg.get_item_width(self.root_tag)
            except Exception:
                w = 0
        return int(w) if w else 0

    def handle_divider_drag(
        self,
        mouse_x: int,
        is_button_down: bool,
        *,
        right_pane_x: int | None = None,
        right_pane_min_width: int = 260,
        gap_width: int = 12,
    ) -> bool:
        """
        Handle mouse events for panel resizing via divider drag.
        
        Allows dragging anywhere in the space between the left and right panes.
        For robust, spacing-independent behavior, pass right_pane_x.
        If not provided, uses a small fixed hit zone as fallback.
        
        Args:
            mouse_x: Current mouse X position
            is_button_down: Whether left mouse button is pressed
            right_pane_x: Optional X position where the right pane starts.
                         If provided, allows dragging anywhere from left pane edge to this position.
                         Makes the behavior robust to spacing changes.
            right_pane_min_width: Minimum width to maintain for the right pane (default: 260).
            gap_width: Width of the gap between panes (default: 12).
            
        Returns:
            True if currently dragging the divider
        """
        if not dpg.does_item_exist(self.root_tag):
            return False

        self._gap_width = gap_width  # Keep in sync for cursor/highlight use

        divider_x = self.get_divider_x()

        # Calculate valid drag zone
        if right_pane_x is not None:
            # Robust mode: allow dragging anywhere from left pane edge to right pane start
            drag_zone_left = divider_x
            drag_zone_right = right_pane_x
            on_divider = drag_zone_left <= mouse_x <= drag_zone_right
        else:
            # Fallback mode: small fixed hit zone
            divider_hit_zone = 4  # pixels on each side
            on_divider = abs(mouse_x - divider_x) < divider_hit_zone

        if is_button_down:
            if on_divider and not self._is_dragging_divider:
                # Start dragging
                self._is_dragging_divider = True
                self._last_mouse_x = mouse_x
            elif self._is_dragging_divider and self._last_mouse_x != 0:
                # Continue dragging - calculate delta
                delta = mouse_x - self._last_mouse_x
                if delta != 0:
                    current_w = self.get_panel_width()
                    new_w = max(180, current_w + delta)
                    
                    # Validate: new left width + gap + min right width must fit in total width
                    available_right_w = self._total_width - gap_width - new_w
                    if new_w >= 180 and available_right_w >= right_pane_min_width:
                        new_percentage = new_w / self._total_width
                        self._panel_width = max(0.2, min(0.7, new_percentage))
                        self.set_size(self._total_width, self._total_height)
                    
                    self._last_mouse_x = mouse_x
        else:
            # Mouse button released - stop dragging
            self._is_dragging_divider = False
            self._last_mouse_x = 0

        # ── Divider highlight (VS Code style blue tint) ───────────────────────
        is_hovering = on_divider and not is_button_down
        is_active   = self._is_dragging_divider
        self._update_divider_highlight(is_hovering or is_active, gap_width)

        return self._is_dragging_divider

    def hide_divider_highlight(self) -> None:
        """Unconditionally hide the divider highlight."""
        self._update_divider_highlight(False, self._gap_width)

    def _update_divider_highlight(self, show: bool, gap_width: int) -> None:
        """Draw or erase the blue highlight rectangle over the divider gap.

        Uses a viewport drawlist (renders above all windows). To hide, we
        delete the rectangle child — configure_item(show=False) is not
        honoured by front-layer viewport drawlists in DPG.
        """
        drawlist_tag = self._tag("divider_highlight")
        rect_tag     = self._tag("divider_rect")

        # Ensure the drawlist container exists.
        if not dpg.does_item_exist(drawlist_tag):
            if not show:
                return
            dpg.add_viewport_drawlist(tag=drawlist_tag, front=True)

        # Always delete the old rectangle first.
        if dpg.does_item_exist(rect_tag):
            dpg.delete_item(rect_tag)

        if not show:
            return

        # root_tag y is relative to its immediate parent (body group).
        # The body group's y is a duplicate of the same editor-toolbar offset,
        # so we skip it and use the grandparent's y (the app-level container
        # whose pos=[0, app_toolbar_height]) instead.
        try:
            _, ry = dpg.get_item_pos(self.root_tag)
            parent = dpg.get_item_parent(self.root_tag)
            grandparent = dpg.get_item_parent(parent) if parent else None
            _, gy = dpg.get_item_pos(grandparent) if grandparent else (0, 0)
            x0 = self.get_panel_width()
            y0 = ry + gy
        except Exception:
            return

        # TODO: Use correct gap width and rename it to something more fitting such as 
        x1 = x0 + gap_width - 7 # A small offset to cover the divider area without being too wide (adjust as needed).
        y1 = y0 + max(1, self._total_height)

        dpg.draw_rectangle(
            (x0, y0), (x1, y1),
            color=(0, 0, 0, 0),
            fill=(0, 120, 212, 255),
            tag=rect_tag,
            parent=drawlist_tag,
        )
