import dearpygui.dearpygui as dpg
import ctypes
import sys
from ctypes import wintypes

VIEWPORT_WIDTH = 1100
VIEWPORT_HEIGHT = 700
CONTENT_GAP = 0
WINDOW_TITLE = "PlanarForge"
RESIZE_BORDER = 10
MIN_VIEWPORT_WIDTH = 640
MIN_VIEWPORT_HEIGHT = 420
TITLEBAR_PAD_X = 12
TITLEBAR_PAD_Y = 6
CONTROL_ICON_SIZE = 10
CONTROL_FRAME_PAD = 6
TITLEBAR_HEIGHT = (2 * TITLEBAR_PAD_Y) + CONTROL_ICON_SIZE + (2 * CONTROL_FRAME_PAD)

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    WM_NCHITTEST = 0x0084
    WM_NCLBUTTONDBLCLK = 0x00A3
    GWLP_WNDPROC = -4
    HTCLIENT = 1
    HTCAPTION = 2
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17

app_state = {
    "maximized": False,
    "restore_pos": [100, 0],
    "restore_size": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
}
native_state = {
    "hwnd": None,
    "orig_wndproc": None,
    "new_wndproc": None,
}


def _get_viewport_hwnd() -> int | None:
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)


def _is_maximized() -> bool:
    hwnd = _get_viewport_hwnd()
    if hwnd:
        return bool(ctypes.windll.user32.IsZoomed(hwnd))
    return app_state["maximized"]


def _sync_max_button() -> None:
    icon = "icon_restore_tex" if _is_maximized() else "icon_max_tex"
    dpg.configure_item("max_btn", texture_tag=icon)


def _make_icon_texture(tag: str, kind: str, size: int = 16) -> None:
    pixels = [[0.0, 0.0, 0.0, 0.0] for _ in range(size * size)]

    def set_px(x: int, y: int, rgba: tuple[float, float, float, float]) -> None:
        if 0 <= x < size and 0 <= y < size:
            pixels[y * size + x] = [rgba[0], rgba[1], rgba[2], rgba[3]]

    fg = (0.89, 0.89, 0.89, 1.0)

    if kind == "min":
        y = size - 5
        for x in range(3, size - 3):
            set_px(x, y, fg)
            set_px(x, y + 1, fg)
    elif kind == "max":
        for x in range(3, size - 3):
            set_px(x, 3, fg)
            set_px(x, size - 4, fg)
        for y in range(3, size - 3):
            set_px(3, y, fg)
            set_px(size - 4, y, fg)
    elif kind == "restore":
        for x in range(6, size - 2):
            set_px(x, 2, fg)
            set_px(x, size - 7, fg)
        for y in range(2, size - 6):
            set_px(6, y, fg)
            set_px(size - 3, y, fg)
        for x in range(2, size - 6):
            set_px(x, 6, fg)
            set_px(x, size - 3, fg)
        for y in range(6, size - 2):
            set_px(2, y, fg)
            set_px(size - 7, y, fg)
    elif kind == "close":
        for i in range(3, size - 3):
            set_px(i, i, fg)
            set_px(i, i - 1, fg)
            set_px(size - 1 - i, i, fg)
            set_px(size - 1 - i, i - 1, fg)

    flat = [channel for px in pixels for channel in px]
    dpg.add_static_texture(size, size, flat, tag=tag, parent="window_icon_textures")


def _is_point_over_item_rect(item_tag: str, x_pos: float, y_pos: float) -> bool:
    if not dpg.does_item_exist(item_tag):
        return False

    try:
        min_x, min_y = dpg.get_item_rect_min(item_tag)
        max_x, max_y = dpg.get_item_rect_max(item_tag)
    except Exception:
        return False

    return min_x <= x_pos <= max_x and min_y <= y_pos <= max_y


def _screen_to_viewport_point(x_pos: float, y_pos: float) -> tuple[float, float]:
    view_x, view_y = dpg.get_viewport_pos()
    return x_pos - view_x, y_pos - view_y


def _iter_titlebar_descendants() -> list[int | str]:
    if not dpg.does_item_exist("title_bar"):
        return []

    descendants: list[int | str] = []
    stack = ["title_bar"]
    while stack:
        current = stack.pop()
        children_by_slot = dpg.get_item_children(current)
        for slot_children in children_by_slot.values():
            for child in slot_children:
                descendants.append(child)
                stack.append(child)
    return descendants


def _is_interactive_titlebar_item(item_tag: int | str) -> bool:
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


def _is_point_over_interactive_titlebar_item(x_pos: float, y_pos: float) -> bool:
    for item in _iter_titlebar_descendants():
        if not _is_interactive_titlebar_item(item):
            continue
        if _is_point_over_item_rect(item, x_pos, y_pos):
            return True
    return False


def _get_titlebar_rect() -> tuple[float, float, float, float] | None:
    if not dpg.does_item_exist("title_bar"):
        return None
    try:
        min_x, min_y = dpg.get_item_rect_min("title_bar")
        max_x, max_y = dpg.get_item_rect_max("title_bar")
    except Exception:
        return None
    return min_x, min_y, max_x, max_y


def _safe_item_width(item_tag: str, fallback: float = 0.0) -> float:
    if not dpg.does_item_exist(item_tag):
        return fallback
    try:
        width, _ = dpg.get_item_rect_size(item_tag)
        return width if width > 0 else fallback
    except Exception:
        return fallback


def close_app() -> None:
    dpg.stop_dearpygui()


def minimize_app() -> None:
    dpg.minimize_viewport()


def toggle_maximize() -> None:
    hwnd = _get_viewport_hwnd()
    if hwnd:
        SW_MAXIMIZE = 3
        SW_RESTORE = 9
        if ctypes.windll.user32.IsZoomed(hwnd):
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        app_state["maximized"] = bool(ctypes.windll.user32.IsZoomed(hwnd))
        _sync_max_button()
        return

    if _is_maximized():
        restore_width, restore_height = app_state["restore_size"]
        restore_x, restore_y = app_state["restore_pos"]
        dpg.set_viewport_width(restore_width)
        dpg.set_viewport_height(restore_height)
        dpg.set_viewport_pos([restore_x, restore_y])
        app_state["maximized"] = False
    else:
        config = dpg.get_viewport_configuration(0)
        app_state["restore_pos"] = list(dpg.get_viewport_pos())
        app_state["restore_size"] = [config["width"], config["height"]]
        dpg.maximize_viewport()
        app_state["maximized"] = True

    _sync_max_button()


def handle_titlebar_double_click(_sender, _app_data) -> None:
    mouse_x, mouse_y = dpg.get_mouse_pos(local=False)
    mouse_x, mouse_y = _screen_to_viewport_point(mouse_x, mouse_y)
    title_rect = _get_titlebar_rect()
    if not title_rect:
        return
    min_x, min_y, max_x, max_y = title_rect
    if not (min_x <= mouse_x <= max_x and min_y <= mouse_y <= max_y):
        return

    if _is_point_over_interactive_titlebar_item(mouse_x, mouse_y):
        return

    toggle_maximize()


def apply_vscode_style() -> None:
    with dpg.theme(tag="vscode_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (31, 31, 31, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (37, 37, 38, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (31, 31, 31, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (220, 220, 220, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (62, 62, 66, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 80, 85, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (95, 95, 99, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (58, 58, 61, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (69, 69, 72, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (84, 84, 87, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 5)

    with dpg.theme(tag="title_control_theme"):
        with dpg.theme_component(dpg.mvImageButton):
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, CONTROL_FRAME_PAD, CONTROL_FRAME_PAD)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_color(dpg.mvThemeCol_Button, (62, 62, 66, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 80, 85, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (95, 95, 99, 255))


def on_viewport_resize(_sender, _app_data) -> None:
    width = dpg.get_viewport_client_width()
    height = dpg.get_viewport_client_height()
    title_rect = _get_titlebar_rect()
    title_height = TITLEBAR_HEIGHT if not title_rect else int(title_rect[3] - title_rect[1])
    dpg.configure_item("root", width=width, height=height)
    dpg.configure_item("content", pos=[0, title_height + CONTENT_GAP], width=width, height=max(0, height - title_height - CONTENT_GAP))

    controls_w = _safe_item_width("title_controls_group", fallback=120.0)
    controls_x = max(TITLEBAR_PAD_X, width - TITLEBAR_PAD_X - controls_w)
    dpg.configure_item("title_controls_group", pos=[int(controls_x), TITLEBAR_PAD_Y])

    search_x = _safe_item_width("title_left_before_search", fallback=260.0) + TITLEBAR_PAD_X
    available_search_w = max(80.0, controls_x - search_x - 12.0)
    dpg.configure_item("title_search", width=int(available_search_w))


def _install_native_resize_hit_test() -> None:
    if sys.platform != "win32":
        return

    hwnd = _get_viewport_hwnd()
    if not hwnd or native_state["hwnd"] == hwnd:
        return

    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    orig_wndproc = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
    if not orig_wndproc:
        return

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    def _signed_word(value: int) -> int:
        value &= 0xFFFF
        return value - 0x10000 if value & 0x8000 else value

    @WNDPROC
    def custom_wndproc(h_wnd, msg, w_param, l_param):
        if msg == WM_NCLBUTTONDBLCLK and w_param == HTCAPTION:
            toggle_maximize()
            return 0

        if msg == WM_NCHITTEST:
            is_maximized = _is_maximized()
            default_hit = user32.CallWindowProcW(orig_wndproc, h_wnd, msg, w_param, l_param)
            if default_hit != HTCLIENT:
                return default_hit

            x_pos = _signed_word(l_param)
            y_pos = _signed_word(l_param >> 16)
            rect = wintypes.RECT()
            user32.GetWindowRect(h_wnd, ctypes.byref(rect))
            width = rect.right - rect.left
            rel_x = x_pos - rect.left
            rel_y = y_pos - rect.top

            near_left = x_pos <= rect.left + RESIZE_BORDER
            near_right = x_pos >= rect.right - RESIZE_BORDER
            near_top = y_pos <= rect.top + RESIZE_BORDER
            near_bottom = y_pos >= rect.bottom - RESIZE_BORDER

            if not is_maximized:
                if near_top and near_left:
                    return HTTOPLEFT
                if near_top and near_right:
                    return HTTOPRIGHT
                if near_bottom and near_left:
                    return HTBOTTOMLEFT
                if near_bottom and near_right:
                    return HTBOTTOMRIGHT
                if near_left:
                    return HTLEFT
                if near_right:
                    return HTRIGHT
                if near_top:
                    return HTTOP
                if near_bottom:
                    return HTBOTTOM

            title_rect = _get_titlebar_rect()
            if title_rect:
                _min_x, title_top, _max_x, title_bottom = title_rect
                in_title_drag_band = title_top <= rel_y <= title_bottom
            else:
                in_title_drag_band = RESIZE_BORDER < rel_y < TITLEBAR_HEIGHT
            away_from_resize_edges = True if is_maximized else (RESIZE_BORDER < rel_x < (width - RESIZE_BORDER))
            if in_title_drag_band and away_from_resize_edges:
                if not _is_point_over_interactive_titlebar_item(rel_x, rel_y):
                    return HTCAPTION

        return user32.CallWindowProcW(orig_wndproc, h_wnd, msg, w_param, l_param)

    if not user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, custom_wndproc):
        return

    native_state["hwnd"] = hwnd
    native_state["orig_wndproc"] = orig_wndproc
    native_state["new_wndproc"] = custom_wndproc


dpg.create_context()
with dpg.texture_registry(tag="window_icon_textures"):
    _make_icon_texture("icon_min_tex", "min")
    _make_icon_texture("icon_max_tex", "max")
    _make_icon_texture("icon_restore_tex", "restore")
    _make_icon_texture("icon_close_tex", "close")

dpg.create_viewport(
    title=WINDOW_TITLE,
    width=VIEWPORT_WIDTH,
    height=VIEWPORT_HEIGHT,
    decorated=False,
    resizable=True,
    x_pos=app_state["restore_pos"][0],
    y_pos=app_state["restore_pos"][1],
)
dpg.setup_dearpygui()
dpg.set_viewport_min_width(MIN_VIEWPORT_WIDTH)
dpg.set_viewport_min_height(MIN_VIEWPORT_HEIGHT)
apply_vscode_style()

with dpg.window(
    tag="root",
    no_title_bar=True,
    no_move=True,
    no_resize=True,
    no_collapse=True,
    no_scrollbar=True,
    no_background=False,
    pos=[0, 0],
    width=VIEWPORT_WIDTH,
    height=VIEWPORT_HEIGHT,
):
    with dpg.child_window(
        tag="title_bar",
        autosize_x=True,
        height=TITLEBAR_HEIGHT,
        border=False,
        no_scrollbar=True,
    ):
        with dpg.group(tag="title_left_group", horizontal=True, pos=[TITLEBAR_PAD_X, TITLEBAR_PAD_Y]):
            with dpg.group(tag="title_left_before_search", horizontal=True):
                dpg.add_text("PlanarForge", tag="title_text")
                dpg.add_spacer(width=10)
                dpg.add_button(tag="menu_file_btn", label="File")
                dpg.add_button(tag="menu_edit_btn", label="Edit")
                dpg.add_button(tag="menu_view_btn", label="View")
                dpg.add_spacer(width=16)
            dpg.add_input_text(
                tag="title_search",
                hint="Search files, resources, commands...",
                width=420,
            )

        with dpg.group(tag="title_controls_group", horizontal=True, pos=[TITLEBAR_PAD_X, TITLEBAR_PAD_Y]):
            dpg.add_image_button("icon_min_tex", tag="min_btn", callback=minimize_app, width=CONTROL_ICON_SIZE, height=CONTROL_ICON_SIZE)
            dpg.add_image_button("icon_max_tex", tag="max_btn", callback=toggle_maximize, width=CONTROL_ICON_SIZE, height=CONTROL_ICON_SIZE)
            dpg.add_image_button("icon_close_tex", tag="close_btn", callback=close_app, width=CONTROL_ICON_SIZE, height=CONTROL_ICON_SIZE)

    with dpg.child_window(
        tag="content",
        border=False,
        no_scrollbar=True,
        pos=[0, TITLEBAR_HEIGHT + CONTENT_GAP],
    ):
        dpg.add_spacer(height=12)
        dpg.add_text("Main content area")
        dpg.add_text("Replace this with your editor panes, data grids, and tools.")

dpg.bind_item_theme("root", "vscode_theme")
dpg.bind_item_theme("min_btn", "title_control_theme")
dpg.bind_item_theme("max_btn", "title_control_theme")
dpg.bind_item_theme("close_btn", "title_control_theme")
dpg.set_primary_window("root", True)
dpg.set_viewport_resize_callback(on_viewport_resize)
on_viewport_resize(None, None)
_sync_max_button()

with dpg.handler_registry():
    dpg.add_mouse_double_click_handler(
        button=dpg.mvMouseButton_Left,
        callback=handle_titlebar_double_click,
    )

dpg.show_viewport()
_install_native_resize_hit_test()
dpg.start_dearpygui()
dpg.destroy_context()
