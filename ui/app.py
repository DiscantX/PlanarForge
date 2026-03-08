import ctypes

import dearpygui.dearpygui as dpg

from core.services.character_service import CharacterService
from core.services.itm_catalog import ItmCatalog
from ui.custom_chrome import CustomTitleBarController
from ui.viewers.character_editor import CharacterEditorPanel
from ui.viewers.itm_viewer import ItmViewerPanel

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

app_state = {
    "maximized": False,
    "restore_pos": [100, 0],
    "restore_size": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
}
ui_state: dict[str, object] = {
    "active_view": "home",
}


def _get_viewport_hwnd() -> int | None:
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
    dpg.configure_item("root", width=width, height=height)
    dpg.configure_item("title_bar", height=TITLEBAR_HEIGHT)
    dpg.configure_item("content", pos=[0, TITLEBAR_HEIGHT + CONTENT_GAP])

    controls_w = _safe_item_width("title_controls_group", fallback=120.0)
    controls_x = max(TITLEBAR_PAD_X, width - TITLEBAR_PAD_X - controls_w)
    dpg.configure_item("title_controls_group", pos=[int(controls_x), TITLEBAR_PAD_Y])

    search_x = _safe_item_width("title_left_before_search", fallback=260.0) + TITLEBAR_PAD_X
    available_search_w = max(80.0, controls_x - search_x - 12.0)
    dpg.configure_item("title_search", width=int(available_search_w))

    viewer = ui_state.get("itm_viewer")
    if isinstance(viewer, ItmViewerPanel):
        viewer.set_size(width=width, height=max(0, height - TITLEBAR_HEIGHT - CONTENT_GAP))
    character = ui_state.get("character_editor")
    if isinstance(character, CharacterEditorPanel):
        character.set_size(width=width, height=max(0, height - TITLEBAR_HEIGHT - CONTENT_GAP))


def show_home_view() -> None:
    ui_state["active_view"] = "home"
    if dpg.does_item_exist("home_view"):
        dpg.show_item("home_view")
    viewer = ui_state.get("itm_viewer")
    if isinstance(viewer, ItmViewerPanel):
        dpg.hide_item(viewer.root_tag)
    character = ui_state.get("character_editor")
    if isinstance(character, CharacterEditorPanel):
        dpg.hide_item(character.root_tag)


def show_itm_viewer() -> None:
    ui_state["active_view"] = "itm"
    if dpg.does_item_exist("home_view"):
        dpg.hide_item("home_view")
    character = ui_state.get("character_editor")
    if isinstance(character, CharacterEditorPanel):
        dpg.hide_item(character.root_tag)

    viewer = ui_state.get("itm_viewer")
    if isinstance(viewer, ItmViewerPanel):
        dpg.show_item(viewer.root_tag)
        viewer.refresh_results()


def show_character_editor() -> None:
    ui_state["active_view"] = "character"
    if dpg.does_item_exist("home_view"):
        dpg.hide_item("home_view")
    viewer = ui_state.get("itm_viewer")
    if isinstance(viewer, ItmViewerPanel):
        dpg.hide_item(viewer.root_tag)
    character = ui_state.get("character_editor")
    if isinstance(character, CharacterEditorPanel):
        dpg.show_item(character.root_tag)


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
    clear_color=(31, 31, 31, 255),
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
    no_scroll_with_mouse=True,
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
        no_scroll_with_mouse=True,
    ):
        with dpg.group(tag="title_left_group", horizontal=True, pos=[TITLEBAR_PAD_X, TITLEBAR_PAD_Y]):
            with dpg.group(tag="title_left_before_search", horizontal=True):
                dpg.add_text("PlanarForge", tag="title_text")
                dpg.add_spacer(width=10)
                dpg.add_button(tag="menu_file_btn", label="File")
                dpg.add_button(tag="menu_edit_btn", label="Edit")
                dpg.add_button(tag="menu_view_btn", label="Item", callback=show_itm_viewer)
                dpg.add_button(tag="menu_character_btn", label="Character", callback=show_character_editor)
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

    with dpg.group(
        tag="content",
        pos=[0, TITLEBAR_HEIGHT + CONTENT_GAP],
    ):
        with dpg.group(tag="home_view"):
            dpg.add_spacer(height=12)
            dpg.add_text("Main content area")
            dpg.add_text("Use View to open the ITM viewer or Character to open the CRE viewer.")

dpg.bind_item_theme("root", "vscode_theme")
dpg.bind_item_theme("min_btn", "title_control_theme")
dpg.bind_item_theme("max_btn", "title_control_theme")
dpg.bind_item_theme("close_btn", "title_control_theme")
dpg.set_primary_window("root", True)
dpg.set_viewport_resize_callback(on_viewport_resize)
on_viewport_resize(None, None)
_sync_max_button()

itm_catalog = ItmCatalog()
itm_viewer = ItmViewerPanel(parent_tag="content", catalog=itm_catalog, tag_prefix="itm")
ui_state["itm_viewer"] = itm_viewer
dpg.hide_item(itm_viewer.root_tag)

character_service = CharacterService(itm_catalog=itm_catalog)
character_editor = CharacterEditorPanel(parent_tag="content", service=character_service, tag_prefix="character")
ui_state["character_editor"] = character_editor
dpg.hide_item(character_editor.root_tag)
show_home_view()
on_viewport_resize(None, None)

chrome = CustomTitleBarController(
    window_title=WINDOW_TITLE,
    title_bar_tag="title_bar",
    is_maximized=_is_maximized,
    on_caption_double_click=toggle_maximize,
    resize_border=RESIZE_BORDER,
)

dpg.show_viewport()
dpg.maximize_viewport()
app_state["maximized"] = True
_sync_max_button()
chrome.install()
dpg.start_dearpygui()
dpg.destroy_context()
