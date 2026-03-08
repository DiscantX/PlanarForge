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

    def handle_divider_drag(self, mouse_x: int, is_button_down: bool) -> bool:
        """
        Handle mouse events for panel resizing via divider drag.
        
        Args:
            mouse_x: Current mouse X position
            is_button_down: Whether left mouse button is pressed
            
        Returns:
            True if currently dragging the divider
        """
        if not dpg.does_item_exist(self.root_tag):
            return False

        divider_x = self.get_divider_x()
        divider_hit_zone = 10  # pixels on each side to detect drag

        # Check if mouse is near the divider
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
                    new_right_w_min = 260
                    
                    # Check if resize is valid
                    if new_w + new_right_w_min + 12 <= self._total_width:
                        new_percentage = new_w / self._total_width
                        self._panel_width = max(0.2, min(0.7, new_percentage))
                        self.set_size(self._total_width, self._total_height)
                    
                    self._last_mouse_x = mouse_x
        else:
            # Mouse button released - stop dragging
            self._is_dragging_divider = False
            self._last_mouse_x = 0

        return self._is_dragging_divider
