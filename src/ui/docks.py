"""Dock/panel plumbing: areas, visibility, floating state and the panel toggles."""
from __future__ import annotations

from typing import Callable
from aqt.qt import (
    QAbstractButton,
    QApplication,
    QDialog,
    QDockWidget,
    QEvent,
    QObject,
    QPushButton,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from .. import shop as shop_mod, storage, streak as streak_mod
from .constants import _COLLECTQUEST_PANEL_EXPAND_WIDTH, _COLLECTQUEST_PANEL_MIN_WIDTH, _COLLECTQUEST_PANEL_WIDTH, _FLOAT_HEIGHT_SAVE_OFFSET, _POPUP_MAX_WIDTH, _POPUP_PROGRESS_DIALOG_WIDTH, _SHOP_PANEL_WIDTH, _STATUSBAR_BLOCK_PREFERRED, _STATUSBAR_STREAK_AREA_WIDTH
from .progress import build_progress_content_widget
from .shop import build_shop_content_widget, show_shop_dialog
from .statusbar import _bottom_ui_block_min_width

def show_progress_dialog(
    parent: QWidget | None = None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Open CollectQuest in a modal dialog (e.g. from menu). Main entry is the side panel via toggle_progress_panel."""
    on_refresh = on_refresh or (lambda: None)
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Progress")
    d.setMinimumWidth(_POPUP_PROGRESS_DIALOG_WIDTH)
    d.setMaximumWidth(_POPUP_MAX_WIDTH)
    layout = QVBoxLayout(d)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.accept)
    layout.addWidget(
        build_progress_content_widget(d, on_refresh, parent or d, for_panel=False, close_button=close_btn)
    )
    close_btn.setFocus()
    # Open at the maximum width the dialog allows, so quest lines are readable without the user
    # having to drag it wider every time. Height follows content; the dialog stays resizable.
    def _set_initial_size() -> None:
        h = d.sizeHint().height() or 520
        # Clamp to the screen rather than a fixed 600px: the items list asks for enough height to
        # show three whole rows, and a flat cap clipped the third one on a normal display.
        screen = d.screen() or QApplication.primaryScreen()
        max_h = int(screen.availableGeometry().height() * 0.9) if screen else 900
        d.resize(_POPUP_MAX_WIDTH, min(h, max_h))
    QTimer.singleShot(0, _set_initial_size)
    d.exec()

def _dock_widget_features_default():
    """Closable | Movable | Floatable, compatible with PyQt5 and PyQt6."""
    try:
        F = QDockWidget.DockWidgetFeature
        return F.DockWidgetClosable | F.DockWidgetMovable | F.DockWidgetFloatable
    except AttributeError:
        return (
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )

def get_collectquest_statusbar_center_content_width(mw: QWidget) -> int:
    """Width to use for the center block. Block contains [streak?] + 24px + bar; must be bar_min + 24 + streak so bar isn't squeezed (CollectQuest visible)."""
    bar_min = _bottom_ui_block_min_width()
    data = storage.load()
    show_streak = data.get("bottom_ui_show_streak", False)
    # Block min = bar min + spacing + streak area so the bar gets at least bar_min and buttons aren't clipped
    block_min = bar_min + 24 + (_STATUSBAR_STREAK_AREA_WIDTH if show_streak else 0) + 8  # +8 so right edge (Shop/CQ) isn't truncated
    center_w = getattr(mw, "_collectquest_xp_widget", None)
    if center_w is not None:
        sh = center_w.sizeHint().width()
        if sh > 0:
            return max(block_min, min(600, sh))
    return max(block_min, _STATUSBAR_BLOCK_PREFERRED)

def get_collectquest_statusbar_right_panel_block_width(mw: QWidget) -> int:
    """Width of the right-side block (2/3 of right panel) when a panel is DOCKED on the right. No compensation when panel is floating."""
    panel_w = 0
    for dock_attr, area_fn in (
        ("_collectquest_dock", _collectquest_dock_area),
        ("_collectquest_shop_dock", _shop_dock_area),
    ):
        dock = getattr(mw, dock_attr, None)
        if dock is None or not dock.isVisible() or dock.isFloating():
            continue
        if area_fn(mw) == "right":
            panel_w = max(panel_w, dock.width())
    return int(panel_w * 2 / 3) if panel_w > 0 else 0

def _dock_widget_area(mw: QWidget, dock: QWidget | None) -> str | None:
    """Dock area for the given dock: 'left', 'right', or None if floating/unknown."""
    if not dock:
        return None
    area_fn = getattr(mw, "dockWidgetArea", None)
    if not area_fn:
        return None
    try:
        a = area_fn(dock)
        if a == Qt.DockWidgetArea.LeftDockWidgetArea:
            return "left"
        if a == Qt.DockWidgetArea.RightDockWidgetArea:
            return "right"
    except Exception:
        pass
    return None

def _collectquest_dock_area(mw: QWidget) -> str | None:
    """Current dock area for progress panel: 'left', 'right', or None if floating/unknown."""
    return _dock_widget_area(mw, getattr(mw, "_collectquest_dock", None))

def _shop_dock_area(mw: QWidget) -> str | None:
    """Current dock area for shop panel: 'left', 'right', or None if floating/unknown."""
    return _dock_widget_area(mw, getattr(mw, "_collectquest_shop_dock", None))

def _dock_area_for_panel(
    mw: QWidget,
    preferred_side: str,
    other_dock: QWidget | None,
    other_area_fn: Callable[[QWidget], str | None],
) -> Qt.DockWidgetArea:
    """Preferred side 'left' or 'right'. If other panel is docked on that side, return the other side."""
    is_other_docked = other_dock and not (getattr(other_dock, "isFloating", lambda: True)())
    other_side = other_area_fn(mw) if is_other_docked else None
    if other_side == preferred_side:
        return Qt.DockWidgetArea.LeftDockWidgetArea if preferred_side == "right" else Qt.DockWidgetArea.RightDockWidgetArea
    return Qt.DockWidgetArea.LeftDockWidgetArea if preferred_side == "left" else Qt.DockWidgetArea.RightDockWidgetArea

def _dock_progress_panel(dock: QWidget) -> None:
    """Re-dock the Progress panel. Uses last saved area or right; docks to other side if that side is occupied by Shop."""
    try:
        mw = dock.parent()
        if not mw or not getattr(mw, "addDockWidget", None):
            dock.setFloating(False)
            return
        preferred = "right"
        try:
            data = storage.load()
            preferred = data.get("panel_area") or "right"
        except Exception:
            pass
        area_enum = _dock_area_for_panel(mw, preferred, getattr(mw, "_collectquest_shop_dock", None), _shop_dock_area)
        mw.addDockWidget(area_enum, dock)
        dock.setFloating(False)
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
    except Exception:
        try:
            dock.setFloating(False)
        except Exception:
            pass

def _dock_shop_panel(dock: QWidget) -> None:
    """Re-dock the Shop panel. Uses last saved area or left; docks to other side if that side is occupied by Progress."""
    try:
        mw = dock.parent()
        if not mw or not getattr(mw, "addDockWidget", None):
            dock.setFloating(False)
            return
        preferred = "left"
        try:
            data = storage.load()
            preferred = data.get("shop_panel_area") or "left"
        except Exception:
            pass
        area_enum = _dock_area_for_panel(mw, preferred, getattr(mw, "_collectquest_dock", None), _collectquest_dock_area)
        mw.addDockWidget(area_enum, dock)
        dock.setFloating(False)
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
    except Exception:
        try:
            dock.setFloating(False)
        except Exception:
            pass

def _save_shop_panel_state(mw: QWidget) -> None:
    """Persist shop panel visibility and placement (same pattern as progress panel)."""
    try:
        data = storage.load()
        dock = getattr(mw, "_collectquest_shop_dock", None)
        data["shop_panel_visible"] = dock.isVisible() if dock else False
        if dock and dock.isVisible():
            data["shop_panel_area"] = _shop_dock_area(mw) or "left"
            data["shop_panel_width"] = max(_COLLECTQUEST_PANEL_MIN_WIDTH, dock.width())
            data["shop_panel_floating"] = dock.isFloating()
            if dock.isFloating() and not getattr(mw, "_collectquest_shop_skip_save_float_geometry", False):
                rect = dock.frameGeometry()
                mw_win = mw.window().frameGeometry()
                data["shop_panel_float_rel_x"] = rect.x() - mw_win.x()
                data["shop_panel_float_rel_y"] = rect.y() - mw_win.y()
                data["shop_panel_float_width"] = max(200, rect.width())
                data["shop_panel_float_height"] = max(300, rect.height() - _FLOAT_HEIGHT_SAVE_OFFSET)
            storage.save(data)
    except Exception:
        pass

def _save_collectquest_panel_state(mw: QWidget) -> None:
    """Persist panel visibility and placement so it can be restored on next load."""
    try:
        data = storage.load()
        dock = getattr(mw, "_collectquest_dock", None)
        data["panel_visible"] = dock.isVisible() if dock else False
        if dock and dock.isVisible():
            area = _collectquest_dock_area(mw)
            data["panel_area"] = area or "right"
            data["panel_width"] = max(80, dock.width())
            data["panel_floating"] = dock.isFloating()
            # Only save floating geometry while visible; hidden dock can report wrong frameGeometry()
            # Position relative to Anki window so multi-monitor / different screen positions work
            if dock.isFloating() and not getattr(mw, "_collectquest_skip_save_float_geometry", False):
                rect = dock.frameGeometry()
                mw_win = mw.window().frameGeometry()
                data["panel_float_rel_x"] = rect.x() - mw_win.x()
                data["panel_float_rel_y"] = rect.y() - mw_win.y()
                data["panel_float_width"] = max(200, rect.width())
                data["panel_float_height"] = max(300, rect.height() - _FLOAT_HEIGHT_SAVE_OFFSET)
            storage.save(data)
    except Exception:
        pass

def _expand_main_window_for_dock(mw: QWidget, expand: int, y_before: int, h_before: int) -> bool:
    """
    Widen the main window to make room for a dock that has just appeared. Returns True if it did.

    Both dock handlers — the one for the panel becoming visible and the one for it docking back in
    from floating — need this, and each used to carry its own copy. The copies had drifted: one
    fell back to the pre-dock position with `or`, which discards a saved y of 0 and so jumped the
    window whenever it sat flush against the top of the screen; one retried the reposition three
    times rather than four; and only one guarded the retry, which runs inside a timer callback
    where nothing else can catch it. This keeps the safe form of all three.

    Returns False when the window was already expanded, so a caller can tell a real expansion from
    a no-op and only then clear its own state.
    """
    if getattr(mw, "_collectquest_window_expanded", False):
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return False
    side = _collectquest_dock_area(mw)
    mw._collectquest_last_dock_side = side
    if side == "right":
        mw.resize(mw.width() + expand, mw.height())
        mw._collectquest_last_good_y = mw.y()
        mw._collectquest_last_good_height = mw.height()
    elif side == "left":
        # Use saved y/height so the window doesn't jump up (Qt on Windows often repositions after
        # left-dock). Tested with `is None`, not truthiness: a window flush to the top of the
        # screen has a saved y of 0, which `or` would throw away.
        y = getattr(mw, "_collectquest_saved_y", None)
        h = getattr(mw, "_collectquest_saved_height", None)
        if y is None:
            y = y_before
        if h is None:
            h = h_before
        mw.setGeometry(mw.x() - expand, y, mw.width() + expand, h)
        mw._collectquest_saved_y = y
        mw._collectquest_saved_height = h

        # Workaround Qt/Windows bug: re-apply y/height after layout runs so the window doesn't move up
        def _reapply_left_position():
            try:
                want_y = getattr(mw, "_collectquest_saved_y", None)
                want_h = getattr(mw, "_collectquest_saved_height", None)
                if want_y is not None and want_h is not None:
                    mw.setGeometry(mw.x(), want_y, mw.width(), want_h)
                    # Remember for when we close (so close doesn't move window up)
                    mw._collectquest_last_good_y = want_y
                    mw._collectquest_last_good_height = want_h
            except Exception:
                pass

        for delay in (50, 150, 300, 450):
            QTimer.singleShot(delay, _reapply_left_position)
    else:
        mw.resize(mw.width() + expand, mw.height())
    mw._collectquest_window_expanded = True
    upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
    if callable(upd):
        upd()
    return True


def _on_collectquest_dock_visibility_changed(mw: QWidget, visible: bool) -> None:
    """On close/hide: shrink window only if dock was docked. On show: expand only if docked (not floating)."""
    dock = getattr(mw, "_collectquest_dock", None)
    # Stop periodic float-save timer when panel is hidden (so we don't save bad geometry)
    save_timer = getattr(mw, "_collectquest_float_save_timer", None)
    if save_timer is not None:
        try:
            save_timer.stop()
        except Exception:
            pass
        mw._collectquest_float_save_timer = None
    _save_collectquest_panel_state(mw)
    # Floating panel: no effect on main window size; start periodic save so we persist position/size before user closes panel
    if dock and dock.isFloating():
        if visible:
            t = QTimer(mw)
            t.setSingleShot(False)
            t.timeout.connect(lambda: _save_collectquest_panel_state(mw))
            t.start(2000)
            mw._collectquest_float_save_timer = t
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return
    # Restore path: opening then immediately floating — don't expand
    if visible and getattr(mw, "_collectquest_restore_floating", False):
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return
    # Dock-in from float: skip expand here; topLevelChanged(False) will expand (avoids double expand)
    if visible and getattr(mw, "_collectquest_was_floating", False):
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return
    _y_before = mw.y()
    _h_before = mw.height()
    expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
    if not visible:
        # Shrink based on which side the dock was on (still known while closing)
        side = _collectquest_dock_area(mw)
        if side == "right":
            mw.resize(max(mw.minimumWidth(), mw.width() - expand), mw.height())
        elif side == "left":
            close_y = getattr(mw, "_collectquest_last_good_y", None) or _y_before
            close_h = getattr(mw, "_collectquest_last_good_height", None) or _h_before
            mw.setGeometry(mw.x() + expand, close_y, max(mw.minimumWidth(), mw.width() - expand), close_h)
            mw._collectquest_saved_y = close_y
            mw._collectquest_saved_height = close_h
            # Qt/Windows: re-apply position after shrink so window doesn't jump up
            def _reapply_after_shrink():
                try:
                    y, h = getattr(mw, "_collectquest_saved_y", None), getattr(mw, "_collectquest_saved_height", None)
                    if y is not None and h is not None:
                        mw.setGeometry(mw.x(), y, mw.width(), h)
                except Exception:
                    pass
            for delay in (50, 150, 300, 450, 600):
                QTimer.singleShot(delay, _reapply_after_shrink)
        else:
            mw.resize(max(mw.minimumWidth(), mw.width() - expand), mw.height())
        if side != "left":
            mw._collectquest_saved_y = mw.y()
            mw._collectquest_saved_height = mw.height()
        mw._collectquest_window_expanded = False
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
    else:
        # Expand when panel is shown or docked back in; defer so dock area is updated after dock-in
        QTimer.singleShot(
            0, lambda: _expand_main_window_for_dock(mw, expand, _y_before, _h_before)
        )

def _position_floating_dock_next_to_main(mw: QWidget, dock: QWidget | None, side: str) -> None:
    """Place a floating dock window left or right of the main window at about the same height."""
    if dock is None or not getattr(dock, "isFloating", lambda: False)():
        return
    try:
        mw_win = mw.window()
        mw_rect = mw_win.frameGeometry()
        gap = 8
        dock_w = dock.width()
        y = mw_rect.y()
        if side == "right":
            x = mw_rect.x() + mw_rect.width() + gap
        else:
            x = mw_rect.x() - dock_w - gap
        dock.move(x, y)
    except Exception:
        pass

def _on_collectquest_dock_top_level_changed(mw: QWidget, floating: bool) -> None:
    """When user floats the panel: shrink main window. When they dock it again: expand."""
    if not floating:
        save_timer = getattr(mw, "_collectquest_float_save_timer", None)
        if save_timer is not None:
            try:
                save_timer.stop()
            except Exception:
                pass
            mw._collectquest_float_save_timer = None
    if floating:
        if not getattr(mw, "_collectquest_window_expanded", False):
            return
        expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
        side = getattr(mw, "_collectquest_last_dock_side", None) or "right"
        if side == "right":
            new_w = max(mw.minimumWidth(), mw.width() - expand)
            mw.resize(new_w, mw.height())
            _g = (mw.x(), mw.y(), new_w, mw.height())
        elif side == "left":
            close_y = getattr(mw, "_collectquest_last_good_y", None) or mw.y()
            close_h = getattr(mw, "_collectquest_last_good_height", None) or mw.height()
            new_x = mw.x() + expand
            new_w = max(mw.minimumWidth(), mw.width() - expand)
            mw.setGeometry(new_x, close_y, new_w, close_h)
            mw._collectquest_saved_y = close_y
            mw._collectquest_saved_height = close_h
            _g = (new_x, close_y, new_w, close_h)
            def _reapply():
                y, h = getattr(mw, "_collectquest_saved_y", None), getattr(mw, "_collectquest_saved_height", None)
                if y is not None and h is not None:
                    mw.setGeometry(mw.x(), y, mw.width(), h)
            for delay in (50, 150, 300):
                QTimer.singleShot(delay, _reapply)
        else:
            new_w = max(mw.minimumWidth(), mw.width() - expand)
            mw.resize(new_w, mw.height())
            _g = (mw.x(), mw.y(), new_w, mw.height())
        mw._collectquest_window_expanded = False
        mw._collectquest_was_floating = True
        mw._collectquest_reference_window_width = mw.width()
        # Re-apply geometry and force a resize so QMainWindow re-layouts (fixes drag-to-float leaving "preview" layout)
        def _refresh_after_float():
            try:
                g = getattr(mw, "_collectquest_float_target_geometry", None)
                if g is not None and len(g) == 4:
                    mw.setGeometry(g[0], g[1], g[2], g[3])
                # Trigger same path as user resize: resize by 1 then back so central/dock layout updates
                w, h = mw.width(), mw.height()
                mw.resize(w + 1, h)
                mw.resize(w, h)
            except Exception:
                pass
        mw._collectquest_float_target_geometry = _g
        QTimer.singleShot(0, _refresh_after_float)
        QTimer.singleShot(150, _refresh_after_float)
        # Position floating window left or right of main window at same height (skip when restoring saved position)
        if not getattr(mw, "_collectquest_skip_save_float_geometry", False):
            def _place_progress_float() -> None:
                _position_floating_dock_next_to_main(mw, getattr(mw, "_collectquest_dock", None), side)
            QTimer.singleShot(50, _place_progress_float)
    else:
        # Progress just docked: don't allow both panels on same side — float shop even if hidden.
        # Defer so Qt has updated dockWidgetArea() before we read it.
        def _enforce_same_side_after_progress_docked() -> None:
            progress_side = _collectquest_dock_area(mw)
            shop_dock = getattr(mw, "_collectquest_shop_dock", None)
            if progress_side and shop_dock and not shop_dock.isFloating():
                if _shop_dock_area(mw) == progress_side:
                    shop_dock.setFloating(True)
        QTimer.singleShot(0, _enforce_same_side_after_progress_docked)
        if getattr(mw, "_collectquest_window_expanded", False):
            upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
            if callable(upd):
                upd()
            return
        _y_before, _h_before = mw.y(), mw.height()
        expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
        def _expand_and_settle() -> None:
            # The flag is cleared only on a real expansion: the early-return path (already
            # expanded) used to leave it untouched, and that difference is deliberate.
            if _expand_main_window_for_dock(mw, expand, _y_before, _h_before):
                mw._collectquest_was_floating = False

        QTimer.singleShot(0, _expand_and_settle)
        return
    upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
    if callable(upd):
        upd()

def toggle_progress_panel(
    mw: QWidget,
    on_refresh: Callable[[], None],
    on_statusbar_center_update: Callable[[], None] | None = None,
) -> None:
    """Show or hide the CollectQuest side panel (right dock). Creates dock on first use.
    When showing, the window expands by 2/3 of the panel width; 1/3 is taken from the main area.
    on_statusbar_center_update is called after show/hide so the bottom bar can re-center over the main area."""
    if not hasattr(mw, "_collectquest_dock") or mw._collectquest_dock is None:
        dock = QDockWidget("CollectQuest", mw)
        dock.setObjectName("CollectQuestProgressDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        dock.setMinimumWidth(_COLLECTQUEST_PANEL_MIN_WIDTH)
        # Cursor on hover: title bar = open hand (movable), close/float buttons = pointing hand (clickable)
        _COLLECTQUEST_TITLE_BAR_HEIGHT = 28  # approximate; used to detect title bar vs content

        class _DockTitleBarCursorFilter(QObject):
            def __init__(self, dock_widget):
                super().__init__(dock_widget)
                self._dock = dock_widget

            def eventFilter(self, obj, event):
                if obj is not self._dock:
                    return False
                t = event.type()
                if t == QEvent.Type.MouseMove:
                    try:
                        p = event.position() if hasattr(event, "position") else event.pos()
                        y = p.y() if hasattr(p, "y") else 0
                        if y < _COLLECTQUEST_TITLE_BAR_HEIGHT and not getattr(self._dock, "isFloating", lambda: False)():
                            self._dock.setCursor(Qt.CursorShape.OpenHandCursor)
                        else:
                            self._dock.setCursor(Qt.CursorShape.ArrowCursor)
                    except Exception:
                        pass
                elif t == QEvent.Type.Leave:
                    self._dock.unsetCursor()
                return False

        dock.setMouseTracking(True)  # needed so we get MouseMove over title vs content
        dock.installEventFilter(_DockTitleBarCursorFilter(dock))
        # When mouse enters content (not title), clear the open-hand cursor so it doesn't stick
        class _DockContentCursorFilter(QObject):
            def __init__(self, dock_widget):
                super().__init__(dock_widget)
                self._dock = dock_widget

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.Enter:
                    self._dock.setCursor(Qt.CursorShape.ArrowCursor)
                return False

        def _install_content_cursor_filter(dock_widget, content_widget):
            if content_widget is not None:
                f = _DockContentCursorFilter(dock_widget)
                content_widget.installEventFilter(f)
                content_widget.setMouseTracking(True)

        mw._collectquest_content_cursor_filter_install = _install_content_cursor_filter
        # Pointing-hand cursor on the close/float buttons (they are children of the dock)
        def _set_dock_button_cursors():
            for child in dock.findChildren(QAbstractButton):
                try:
                    child.setCursor(Qt.CursorShape.PointingHandCursor)
                except Exception:
                    pass
        QTimer.singleShot(50, _set_dock_button_cursors)
        area = Qt.DockWidgetArea.RightDockWidgetArea
        try:
            saved = storage.load()
            if saved.get("panel_area") == "left":
                area = Qt.DockWidgetArea.LeftDockWidgetArea
        except Exception:
            pass
        mw.addDockWidget(area, dock)
        mw._collectquest_dock = dock
        mw._collectquest_on_refresh = on_refresh
        # One-time: ensure main window dock options include AnimatedDocks so drag-to-dock overlay shows
        if not getattr(mw, "_collectquest_dock_options_ensured", False):
            try:
                if hasattr(mw, "dockOptions") and hasattr(mw, "setDockOptions"):
                    opts = mw.dockOptions()
                    from aqt.qt import QMainWindow
                    animated = getattr(QMainWindow.DockOption, "AnimatedDocks", None) or getattr(QMainWindow, "AnimatedDocks", None)
                    if animated is not None and (opts & animated) == 0:
                        mw.setDockOptions(opts | animated)
            except Exception:
                pass
            mw._collectquest_dock_options_ensured = True
        dock.visibilityChanged.connect(lambda v: _on_collectquest_dock_visibility_changed(mw, v))
        if getattr(dock, "topLevelChanged", None):
            dock.topLevelChanged.connect(lambda floating: _on_collectquest_dock_top_level_changed(mw, floating))
    if on_statusbar_center_update is not None:
        mw._collectquest_update_statusbar_center_width = on_statusbar_center_update
    dock = mw._collectquest_dock
    if dock.isVisible():
        dock.hide()
        # Resize and status bar update are done by visibilityChanged
    else:
        # Re-apply so drag-to-dock overlay and drop zones work (can be reset by Qt/Anki)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        old = dock.widget()
        if old:
            old.deleteLater()
        content = build_progress_content_widget(dock, mw._collectquest_on_refresh, mw, for_panel=True)
        dock.setWidget(content)
        install = getattr(mw, "_collectquest_content_cursor_filter_install", None)
        if callable(install):
            install(dock, content)
        # Open floating before first show if saved state was floating (so it appears floating, no dock-then-float)
        try:
            if storage.load().get("panel_floating"):
                dock.setFloating(True)
                mw._collectquest_skip_save_float_geometry = True  # don't overwrite stored geometry before we apply it
        except Exception:
            pass
        dock.show()
        # Apply saved floating position/size after show (floating window exists then)
        def _apply_float_geometry():
            try:
                if not getattr(dock, "isFloating", lambda: False)():
                    setattr(mw, "_collectquest_skip_save_float_geometry", False)
                    return
                data = storage.load()
                rel_x = data.get("panel_float_rel_x")
                rel_y = data.get("panel_float_rel_y")
                w = data.get("panel_float_width")
                h = data.get("panel_float_height")
                mw_win = mw.window().frameGeometry()
                if isinstance(w, (int, float)) and isinstance(h, (int, float)) and 200 <= w <= 1200 and 300 <= h <= 900:
                    dock.resize(int(w), int(h))
                else:
                    dock.resize(_COLLECTQUEST_PANEL_WIDTH, 480)
                if isinstance(rel_x, (int, float)) and isinstance(rel_y, (int, float)):
                    dock.move(mw_win.x() + int(rel_x), mw_win.y() + int(rel_y))
                else:
                    dock.move(mw_win.x() + mw_win.width() - dock.width() - 20, mw_win.y() + 50)
            except Exception:
                pass
            finally:
                setattr(mw, "_collectquest_skip_save_float_geometry", False)
        # Apply once, next tick; no extra delayed re-apply (that was causing the window to extend vertically)
        QTimer.singleShot(0, _apply_float_geometry)
        # Expansion is done by visibilityChanged(True) only when docked; floating is handled above
        # Set panel width when docked: saved value or default; apply twice so Qt doesn't leave it oversized after dock-in
        def _apply_dock_width():
            try:
                if not getattr(mw, "resizeDocks", None):
                    return
                if getattr(dock, "isFloating", lambda: False)():
                    return
                data = storage.load()
                w = data.get("panel_width")
                if not isinstance(w, (int, float)) or w < 80 or w > 800:
                    w = _COLLECTQUEST_PANEL_WIDTH
                w = int(w)
                mw.resizeDocks([dock], [w], Qt.Orientation.Horizontal)
            except Exception:
                pass
        QTimer.singleShot(50, _apply_dock_width)
        QTimer.singleShot(250, _apply_dock_width)
    if on_statusbar_center_update:
        QTimer.singleShot(0, on_statusbar_center_update)

def toggle_shop_panel(mw: QWidget, on_refresh: Callable[[], None]) -> None:
    """Show or hide the Shop panel (left dock by default). Both Shop and CollectQuest can be docked or floating at the same time."""
    data = storage.load()
    today = streak_mod.today_str()
    reviews_today = data.get("reviews_today", 0)
    gate_date = data.get("shop_gate_date", "")
    shop_unlocked = (gate_date == today) or (reviews_today >= shop_mod.SHOP_MIN_REVIEWS)
    if not shop_unlocked:
        show_shop_dialog(mw, on_refresh)
        return

    if not hasattr(mw, "_collectquest_shop_dock") or mw._collectquest_shop_dock is None:
        dock = QDockWidget("Shop", mw)
        dock.setObjectName("CollectQuestShopDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        dock.setMinimumWidth(_COLLECTQUEST_PANEL_MIN_WIDTH)
        area = Qt.DockWidgetArea.LeftDockWidgetArea
        try:
            saved = storage.load()
            if saved.get("shop_panel_area") == "right":
                area = Qt.DockWidgetArea.RightDockWidgetArea
        except Exception:
            pass
        mw.addDockWidget(area, dock)
        mw._collectquest_shop_dock = dock
        def _on_shop_visibility_changed(visible: bool) -> None:
            t = getattr(mw, "_collectquest_shop_float_save_timer", None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
                mw._collectquest_shop_float_save_timer = None
            _save_shop_panel_state(mw)
            if visible and dock.isFloating():
                t = QTimer(mw)
                t.setSingleShot(False)
                t.timeout.connect(lambda: _save_shop_panel_state(mw))
                t.start(2000)
                mw._collectquest_shop_float_save_timer = t
        dock.visibilityChanged.connect(_on_shop_visibility_changed)
        if getattr(dock, "topLevelChanged", None):
            def _on_shop_top_level(mw_ref: QWidget, floating: bool) -> None:
                if not floating:
                    # Shop just docked: don't allow both panels on same side. Defer so Qt has updated dockWidgetArea().
                    def _enforce_same_side_after_shop_docked() -> None:
                        shop_side = _shop_dock_area(mw_ref)
                        progress_dock = getattr(mw_ref, "_collectquest_dock", None)
                        if shop_side and progress_dock and not progress_dock.isFloating():
                            if _collectquest_dock_area(mw_ref) == shop_side:
                                progress_dock.setFloating(True)
                    QTimer.singleShot(0, _enforce_same_side_after_shop_docked)
                else:
                    # Position floating shop window left or right of main at same height (skip when restoring saved position)
                    if not getattr(mw_ref, "_collectquest_shop_skip_save_float_geometry", False):
                        try:
                            side = storage.load().get("shop_panel_area") or "left"
                        except Exception:
                            side = "left"
                        def _place_shop_float() -> None:
                            _position_floating_dock_next_to_main(mw_ref, getattr(mw_ref, "_collectquest_shop_dock", None), side)
                        QTimer.singleShot(50, _place_shop_float)
            dock.topLevelChanged.connect(lambda f: _on_shop_top_level(mw, f))
    dock = mw._collectquest_shop_dock
    if dock.isVisible():
        dock.hide()
    else:
        # Re-apply so drag-to-dock overlay and drop zones work (can be reset by Qt/Anki)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        old = dock.widget()
        if old:
            old.deleteLater()
        content = build_shop_content_widget(dock, on_refresh, dock.hide, for_panel=True)
        dock.setWidget(content)
        try:
            saved = storage.load()
            if saved.get("shop_panel_floating"):
                dock.setFloating(True)
                mw._collectquest_shop_skip_save_float_geometry = True
        except Exception:
            pass
        dock.show()

        def _apply_shop_float_geometry() -> None:
            try:
                if not getattr(dock, "isFloating", lambda: False)():
                    setattr(mw, "_collectquest_shop_skip_save_float_geometry", False)
                    return
                data = storage.load()
                rel_x = data.get("shop_panel_float_rel_x")
                rel_y = data.get("shop_panel_float_rel_y")
                w = data.get("shop_panel_float_width")
                h = data.get("shop_panel_float_height")
                mw_win = mw.window().frameGeometry()
                if isinstance(w, (int, float)) and isinstance(h, (int, float)) and 200 <= w <= 1200 and 300 <= h <= 900:
                    dock.resize(int(w), int(h))
                else:
                    dock.resize(_SHOP_PANEL_WIDTH, 480)
                if isinstance(rel_x, (int, float)) and isinstance(rel_y, (int, float)):
                    dock.move(mw_win.x() + int(rel_x), mw_win.y() + int(rel_y))
                else:
                    dock.move(mw_win.x() + mw_win.width() - dock.width() - 20, mw_win.y() + 50)
            except Exception:
                pass
            finally:
                setattr(mw, "_collectquest_shop_skip_save_float_geometry", False)
        QTimer.singleShot(0, _apply_shop_float_geometry)

        def _apply_shop_dock_width() -> None:
            try:
                if not getattr(mw, "resizeDocks", None):
                    return
                if getattr(dock, "isFloating", lambda: False)():
                    return
                data = storage.load()
                w = data.get("shop_panel_width")
                if not isinstance(w, (int, float)) or w < _COLLECTQUEST_PANEL_MIN_WIDTH or w > 800:
                    w = _SHOP_PANEL_WIDTH
                w = int(w)
                mw.resizeDocks([dock], [w], Qt.Orientation.Horizontal)
            except Exception:
                pass
        QTimer.singleShot(50, _apply_shop_dock_width)
        QTimer.singleShot(250, _apply_shop_dock_width)

def refresh_progress_panel(mw: QWidget) -> None:
    """Refresh the side panel content if it exists and is visible."""
    if not getattr(mw, "_collectquest_dock", None) or not mw._collectquest_dock.isVisible():
        return
    on_refresh = getattr(mw, "_collectquest_on_refresh", None)
    if not callable(on_refresh):
        return
    dock = mw._collectquest_dock
    old = dock.widget()
    if old:
        old.deleteLater()
    content = build_progress_content_widget(dock, on_refresh, mw, for_panel=True)
    dock.setWidget(content)
    install = getattr(mw, "_collectquest_content_cursor_filter_install", None)
    if callable(install):
        install(dock, content)
