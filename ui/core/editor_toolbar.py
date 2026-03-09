"""Reusable toolbar component for editor panels."""

from __future__ import annotations

from typing import Any, Callable, Optional

import dearpygui.dearpygui as dpg


class EditorToolbar:
    """
    Reusable toolbar for editors with common controls.
    
    Includes game selection, refresh/rebuild buttons, and status display.
    Search is handled separately (via app.py global search bar).
    """

    def __init__(
        self,
        parent_tag: str,
        games: list[str],
        on_game_selected: Callable[[str], None],
        on_refresh: Callable[[], None],
        on_rebuild: Callable[[], None],
        *,
        tag_prefix: str = "toolbar",
        extra_controls: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the toolbar.
        
        Args:
            parent_tag: Parent DPG element tag
            games: List of available game IDs
            on_game_selected: Callback when game selection changes (receives game_id)
            on_refresh: Callback for refresh button
            on_rebuild: Callback for rebuild button
            tag_prefix: Prefix for DPG tag generation
            extra_controls: Optional callback to add custom controls to the toolbar.
                           Received parameter is the parent group tag.
        """
        self.parent_tag = parent_tag
        self.games = games
        self.on_game_selected = on_game_selected
        self.on_refresh = on_refresh
        self.on_rebuild = on_rebuild
        self.tag_prefix = tag_prefix

        self.root_tag = self._tag("root")
        self.game_combo_tag = self._tag("game_combo")
        self.refresh_btn_tag = self._tag("refresh_btn")
        self.rebuild_btn_tag = self._tag("rebuild_btn")
        self.status_tag = self._tag("status")

        # Loading state
        self._is_loading = False

        # Create the toolbar UI
        with dpg.group(tag=self.root_tag, parent=parent_tag, horizontal=True):
            dpg.add_text("Game:")
            dpg.add_combo(
                tag=self.game_combo_tag,
                items=games,
                width=160,
                callback=self._on_game_combo_changed,
            )
            dpg.add_button(
                tag=self.refresh_btn_tag,
                label="Refresh",
                callback=lambda: self.on_refresh(),
            )
            dpg.add_button(
                tag=self.rebuild_btn_tag,
                label="Rebuild",
                callback=lambda: self.on_rebuild(),
            )
            dpg.add_spacer(width=16)

            # Allow custom controls to be added in the middle (before status)
            if extra_controls:
                extra_controls(self.root_tag)

            dpg.add_spacer(width=8)
            dpg.add_text("", tag=self.status_tag)

    def _tag(self, suffix: str) -> str:
        """Generate a DPG tag."""
        return f"{self.tag_prefix}_{suffix}"

    def set_games(self, games: list[str]) -> None:
        """Update the available games."""
        self.games = games
        if dpg.does_item_exist(self.game_combo_tag):
            dpg.configure_item(self.game_combo_tag, items=games)

    def set_game(self, game_id: str) -> None:
        """Set the selected game."""
        if dpg.does_item_exist(self.game_combo_tag):
            dpg.set_value(self.game_combo_tag, game_id)

    def get_game(self) -> str:
        """Get the currently selected game."""
        if dpg.does_item_exist(self.game_combo_tag):
            return str(dpg.get_value(self.game_combo_tag) or "")
        return ""

    def set_status(self, message: str) -> None:
        """Update the status message."""
        if dpg.does_item_exist(self.status_tag):
            dpg.set_value(self.status_tag, message)

    def get_status(self) -> str:
        """Get the current status message."""
        if dpg.does_item_exist(self.status_tag):
            return str(dpg.get_value(self.status_tag) or "")
        return ""

    def set_loading(self, is_loading: bool, message: str = "") -> None:
        """
        Set loading state with optional message.

        Args:
            is_loading: True to indicate loading, False to hide it.
            message: Optional message to display in status when done.
        """
        self._is_loading = is_loading
        if not is_loading and message:
            self.set_status(message)

    def update_spinner(self, message: str = "") -> None:
        """No-op stub retained for API compatibility."""
        pass

    def _on_game_combo_changed(self, _sender: Any, app_data: str) -> None:
        """Handle game combo change."""
        if app_data:
            self.on_game_selected(str(app_data))