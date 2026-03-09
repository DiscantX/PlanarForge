from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

import dearpygui.dearpygui as dpg


class CustomTitleBarController:
    """Reusable native window-chrome controller for frameless Dear PyGui viewports.

    This controller handles Windows hit-testing so a custom title bar can still
    support normal OS behaviors: resize edges/corners, caption drag, restore-down
    drag from maximized, and caption double-click maximize/restore.
    """

    def __init__(
        self,
        window_title: str,
        title_bar_tag: str,
        is_maximized: Callable[[], bool],
        on_caption_double_click: Callable[[], None],
        resize_border: int = 10,
        divider_hit_test_callback: Callable[[int, int], bool] | None = None,
    ) -> None:
        """Initialize a controller for one viewport/title-bar pair.

        Args:
            window_title: Native viewport title used to resolve HWND.
            title_bar_tag: Dear PyGui item tag for the custom title bar container.
            is_maximized: Callback that returns current maximized state.
            on_caption_double_click: Callback invoked on native caption double-click.
            resize_border: Edge thickness (pixels) for resize hit zones.
            divider_hit_test_callback: Optional callable (screen_x, screen_y) -> bool.
                Called from WM_NCHITTEST when the hit would be HTCLIENT. If it returns
                True, the horizontal-resize cursor (IDC_SIZEWE ↔) is set immediately
                inside the message handler before Windows can reset it, and HTCLIENT is
                still returned so normal DPG mouse events continue to fire. Must be fast
                and allocation-free (runs in WndProc).
        """
        self.window_title = window_title
        self.title_bar_tag = title_bar_tag
        self.is_maximized = is_maximized
        self.on_caption_double_click = on_caption_double_click
        self.resize_border = resize_border
        self._divider_hit_test_callback = divider_hit_test_callback

        self._hwnd: int | None = None
        self._orig_wndproc = None
        self._new_wndproc = None

        self._supported = sys.platform == "win32"
        if self._supported:
            self._user32 = ctypes.windll.user32
            self._WM_NCHITTEST = 0x0084
            self._WM_NCLBUTTONDBLCLK = 0x00A3
            self._GWLP_WNDPROC = -4
            self._HTCLIENT = 1
            self._HTCAPTION = 2
            self._HTLEFT = 10
            self._HTRIGHT = 11
            self._HTTOP = 12
            self._HTTOPLEFT = 13
            self._HTTOPRIGHT = 14
            self._HTBOTTOM = 15
            self._HTBOTTOMLEFT = 16
            self._HTBOTTOMRIGHT = 17
            # Pre-load cursors once so the WndProc has zero-latency access.
            self._cursor_arrow  = self._user32.LoadCursorW(None, 32512)   # IDC_ARROW
            self._cursor_sizewe = self._user32.LoadCursorW(None, 32644)   # IDC_SIZEWE ↔

    def set_divider_hit_test_callback(
        self, callback: Callable[[int, int], bool] | None
    ) -> None:
        """Replace (or clear) the divider hit-test callback at runtime.

        The callback receives screen coordinates (x, y) and must return True
        when the cursor is over a resizable pane divider. It is called from
        the Windows message handler so it must be fast and must not call any
        DPG APIs. Typically it does nothing more than compare two integers.
        """
        self._divider_hit_test_callback = callback

    def install(self) -> None:
        """Install the native window-proc hook if running on Windows."""
        if not self._supported:
            return

        hwnd = self._get_viewport_hwnd()
        if not hwnd or self._hwnd == hwnd:
            return

        self._user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        self._user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        self._user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self._user32.CallWindowProcW.restype = ctypes.c_ssize_t
        self._user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]

        orig_wndproc = self._user32.GetWindowLongPtrW(hwnd, self._GWLP_WNDPROC)
        if not orig_wndproc:
            return

        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        @wndproc_type
        def custom_wndproc(h_wnd, msg, w_param, l_param):
            if msg == self._WM_NCLBUTTONDBLCLK and w_param == self._HTCAPTION:
                self.on_caption_double_click()
                return 0

            if msg == self._WM_NCHITTEST:
                maximized = self.is_maximized()
                default_hit = self._user32.CallWindowProcW(orig_wndproc, h_wnd, msg, w_param, l_param)
                if default_hit != self._HTCLIENT:
                    return default_hit

                x_pos = self._signed_word(l_param)
                y_pos = self._signed_word(l_param >> 16)
                rect = wintypes.RECT()
                self._user32.GetWindowRect(h_wnd, ctypes.byref(rect))

                width = rect.right - rect.left
                rel_x = x_pos - rect.left
                rel_y = y_pos - rect.top

                near_left = x_pos <= rect.left + self.resize_border
                near_right = x_pos >= rect.right - self.resize_border
                near_top = y_pos <= rect.top + self.resize_border
                near_bottom = y_pos >= rect.bottom - self.resize_border

                if not maximized:
                    if near_top and near_left:
                        return self._HTTOPLEFT
                    if near_top and near_right:
                        return self._HTTOPRIGHT
                    if near_bottom and near_left:
                        return self._HTBOTTOMLEFT
                    if near_bottom and near_right:
                        return self._HTBOTTOMRIGHT
                    if near_left:
                        return self._HTLEFT
                    if near_right:
                        return self._HTRIGHT
                    if near_top:
                        return self._HTTOP
                    if near_bottom:
                        return self._HTBOTTOM

                title_rect = self._get_titlebar_rect()
                if title_rect:
                    _x0, title_top, _x1, title_bottom = title_rect
                    in_title_band = title_top <= rel_y <= title_bottom
                else:
                    in_title_band = self.resize_border < rel_y < (self.resize_border + 32)

                away_from_edges = True if maximized else (self.resize_border < rel_x < (width - self.resize_border))
                if in_title_band and away_from_edges and not self._is_point_over_interactive_titlebar_item(rel_x, rel_y):
                    return self._HTCAPTION

                # Client area — check for pane divider before returning HTCLIENT.
                # Setting the cursor here (inside WM_NCHITTEST) runs at a higher
                # priority than DPG's event loop, so Windows cannot reset it.
                cb = self._divider_hit_test_callback
                if cb is not None:
                    try:
                        if cb(x_pos, y_pos):
                            self._user32.SetCursor(self._cursor_sizewe)
                            return self._HTCLIENT
                    except Exception:
                        pass  # never propagate out of a WndProc

            return self._user32.CallWindowProcW(orig_wndproc, h_wnd, msg, w_param, l_param)

        if not self._user32.SetWindowLongPtrW(hwnd, self._GWLP_WNDPROC, custom_wndproc):
            return

        self._hwnd = hwnd
        self._orig_wndproc = orig_wndproc
        self._new_wndproc = custom_wndproc

    def _get_viewport_hwnd(self) -> int | None:
        """Resolve the current viewport HWND from its title."""
        if not self._supported:
            return None
        return self._user32.FindWindowW(None, self.window_title)

    @staticmethod
    def _signed_word(value: int) -> int:
        """Convert low/high 16-bit word to signed screen coordinate component."""
        value &= 0xFFFF
        return value - 0x10000 if value & 0x8000 else value

    def _iter_titlebar_descendants(self) -> list[int | str]:
        """Return all descendant Dear PyGui items under the title bar."""
        if not dpg.does_item_exist(self.title_bar_tag):
            return []

        descendants: list[int | str] = []
        stack: list[int | str] = [self.title_bar_tag]
        while stack:
            current = stack.pop()
            children_by_slot = dpg.get_item_children(current)
            for slot_children in children_by_slot.values():
                for child in slot_children:
                    descendants.append(child)
                    stack.append(child)
        return descendants

    @staticmethod
    def _is_interactive_titlebar_item(item_tag: int | str) -> bool:
        """Heuristic: treat non-layout/title primitives as interactive controls."""
        try:
            item_type = dpg.get_item_info(item_tag).get("type", "")
        except Exception:
            return False

        non_interactive = (
            "mvGroup",
            "mvText",
            "mvSpacer",
            "mvSeparator",
            "mvChildWindow",
            "mvDrawlist",
        )
        return not any(kind in item_type for kind in non_interactive)

    @staticmethod
    def _is_point_over_item_rect(item_tag: int | str, x_pos: float, y_pos: float) -> bool:
        """Check whether a local viewport point lies inside an item's rect."""
        if not dpg.does_item_exist(item_tag):
            return False
        try:
            min_x, min_y = dpg.get_item_rect_min(item_tag)
            max_x, max_y = dpg.get_item_rect_max(item_tag)
        except Exception:
            return False
        return min_x <= x_pos <= max_x and min_y <= y_pos <= max_y

    def _is_point_over_interactive_titlebar_item(self, x_pos: float, y_pos: float) -> bool:
        """Check whether point is over any interactive control in the title bar."""
        for item in self._iter_titlebar_descendants():
            if not self._is_interactive_titlebar_item(item):
                continue
            if self._is_point_over_item_rect(item, x_pos, y_pos):
                return True
        return False

    def _get_titlebar_rect(self) -> tuple[float, float, float, float] | None:
        """Get title-bar rect in viewport-local coordinates."""
        if not dpg.does_item_exist(self.title_bar_tag):
            return None
        try:
            min_x, min_y = dpg.get_item_rect_min(self.title_bar_tag)
            max_x, max_y = dpg.get_item_rect_max(self.title_bar_tag)
        except Exception:
            return None
        return min_x, min_y, max_x, max_y