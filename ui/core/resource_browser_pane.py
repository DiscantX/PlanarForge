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
        self.table_tag = self._tag("table")
        
        self._row_selectables: list[str] = []
        self._selected_index: int | None = None
        
        # Panel sizing state
        self._total_width: int = 0
        self._total_height: int = 0
        self._panel_width: float = 0.30  # Default 30% of parent width
        self._is_dragging_divider: bool = False
        self._last_mouse_x: int = 0
        self._gap_width: int = 12  # Width of the divider gap between panes

        # Create the UI
        with dpg.child_window(
            tag=self.root_tag,
            parent=parent_tag,
            border=True,
            no_scrollbar=False,
        ):
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
    ) -> None:
        """
        Populate the table with rows.
        
        Args:
            items: List of tuples, where each tuple contains values for the columns
                   (e.g., [(resref1, name1), (resref2, name2), ...])
        """
        # Clear existing rows
        dpg.delete_item(self.table_tag, children_only=True, slot=1)
        self._row_selectables.clear()
        self._selected_index = None

        if not items:
            return

        # Add each row
        for idx, item_data in enumerate(items):
            row_tag = self._tag(f"row_{idx}")
            self._row_selectables.append(row_tag)

            with dpg.table_row(parent=self.table_tag):
                # First column is a selectable (for row selection)
                dpg.add_selectable(
                    tag=row_tag,
                    label=str(item_data[0]) if item_data else "",
                    span_columns=True,
                    callback=self._on_row_clicked,
                    user_data=idx,
                    height=22,
                )

                # Add additional columns as text
                for cell_data in item_data[1:]:
                    dpg.add_text(str(cell_data))

    def select_row(self, index: int) -> None:
        """
        Select a row by index.
        
        Args:
            index: Row index to select
        """
        if index < 0 or index >= len(self._row_selectables):
            return

        # Update selection state for display
        for row_idx, row_tag in enumerate(self._row_selectables):
            if dpg.does_item_exist(row_tag):
                dpg.set_value(row_tag, row_idx == index)

        self._selected_index = index

    def get_selected_index(self) -> int | None:
        """Get the currently selected row index."""
        return self._selected_index

    def clear_rows(self) -> None:
        """Clear all rows from the table."""
        dpg.delete_item(self.table_tag, children_only=True, slot=1)
        self._row_selectables.clear()
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