"""Dock/panel plumbing: areas, visibility, floating state and the panel toggles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from aqt.qt import (
    QAbstractButton,
    QApplication,
    QDialog,
    QDockWidget,
    QEvent,
    QMainWindow,
    QObject,
    QPushButton,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from .. import shop as shop_mod, storage, streak as streak_mod
from .constants import _COLLECTQUEST_PANEL_EXPAND_WIDTH, _COLLECTQUEST_PANEL_MIN_WIDTH, _COLLECTQUEST_PANEL_WIDTH, _FLOAT_HEIGHT_SAVE_OFFSET, _POPUP_MAX_WIDTH, _POPUP_PROGRESS_DIALOG_WIDTH, _SHOP_PANEL_WIDTH
from .assets import exec_dialog, refit_dialog_height
from .progress import build_progress_content_widget
from .shop import build_shop_content_widget, show_shop_dialog
from .statusbar import update_center_width


@dataclass(frozen=True)
class _Panel:
    """What differs between the two dock panels: where they live on mw and under which save keys."""
    dock_attr: str
    key: str  # save-key prefix
    default_side: str
    default_width: int
    # Set while saved float geometry is being applied, so it isn't overwritten before it lands.
    skip_save_attr: str
    save_timer_attr: str


_PROGRESS = _Panel(
    "_collectquest_dock", "panel", "right", _COLLECTQUEST_PANEL_WIDTH,
    "_collectquest_skip_save_float_geometry", "_collectquest_float_save_timer",
)
_SHOP = _Panel(
    "_collectquest_shop_dock", "shop_panel", "left", _SHOP_PANEL_WIDTH,
    "_collectquest_shop_skip_save_float_geometry", "_collectquest_shop_float_save_timer",
)


def _other(panel: _Panel) -> _Panel:
    return _SHOP if panel is _PROGRESS else _PROGRESS


def _both_sides():
    return Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea

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
    content: QWidget | None = None  # the one live child, replaced wholesale by rebuild()
    closed = False

    def _on_finished(_result: int) -> None:
        nonlocal closed
        closed = True

    d.finished.connect(_on_finished)

    def rebuild() -> None:
        """Redraw the window's contents in place, like the dock panel, so child-window changes show
        without reopening."""
        nonlocal content
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(d.accept)
        # Built before the old copy goes, so a build that raises leaves the window as it was rather
        # than empty and without a Close button.
        new_content = build_progress_content_widget(
            d, refresh, for_panel=False, close_button=close_btn
        )
        old_content, content = content, new_content
        if old_content is not None:
            # Hidden as well as removed: deleteLater only fires once the event loop is reached, and
            # until then the old copy would sit on top of the new one.
            layout.removeWidget(old_content)
            old_content.hide()
            old_content.deleteLater()
        layout.addWidget(new_content)
        # Close keeps focus and Return on every build. setFocus behind a modal child doesn't raise
        # the window.
        close_btn.setDefault(True)
        close_btn.setFocus()
        if old_content is not None:
            QTimer.singleShot(0, lambda: refit_dialog_height(d))

    def refresh() -> None:
        """What the child windows are handed: the caller's refresh, then this window's own."""
        on_refresh()
        # Options schedules its refresh on a timer, which can land after this window is closed.
        if not closed:
            rebuild()

    rebuild()
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
    exec_dialog(d)
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

def _side(mw: QWidget, panel: _Panel) -> str | None:
    """Current dock area of a panel: 'left', 'right', or None if floating/unknown."""
    return _dock_widget_area(mw, getattr(mw, panel.dock_attr, None))


def _dock_area_for_panel(mw: QWidget, preferred_side: str, other: _Panel) -> Qt.DockWidgetArea:
    """Preferred side 'left' or 'right'. If the other panel is docked on that side, the other side."""
    other_dock = getattr(mw, other.dock_attr, None)
    is_other_docked = other_dock and not (getattr(other_dock, "isFloating", lambda: True)())
    other_side = _side(mw, other) if is_other_docked else None
    if other_side == preferred_side:
        return Qt.DockWidgetArea.LeftDockWidgetArea if preferred_side == "right" else Qt.DockWidgetArea.RightDockWidgetArea
    return Qt.DockWidgetArea.LeftDockWidgetArea if preferred_side == "left" else Qt.DockWidgetArea.RightDockWidgetArea

def _redock(dock: QWidget, panel: _Panel) -> None:
    """Re-dock a floating panel on its last saved side, or the other side if the other panel is there."""
    try:
        mw = dock.parent()
        if not mw or not getattr(mw, "addDockWidget", None):
            dock.setFloating(False)
            return
        preferred = panel.default_side
        try:
            preferred = storage.load().get(f"{panel.key}_area") or panel.default_side
        except Exception:
            pass
        area_enum = _dock_area_for_panel(mw, preferred, _other(panel))
        mw.addDockWidget(area_enum, dock)
        dock.setFloating(False)
        _update_center(mw)
    except Exception:
        try:
            dock.setFloating(False)
        except Exception:
            pass


def _dock_progress_panel(dock: QWidget) -> None:
    _redock(dock, _PROGRESS)


def _dock_shop_panel(dock: QWidget) -> None:
    _redock(dock, _SHOP)


def _update_center(mw: QWidget) -> None:
    """Re-center the bottom bar through whichever centering the current bar mode installed."""
    upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
    if callable(upd):
        upd()


def _write_panel_state(mw: QWidget, panel: _Panel, data: dict, respect_skip: bool = True) -> None:
    """Record a panel's visibility and placement into data. Untouched when the dock was never built."""
    dock = getattr(mw, panel.dock_attr, None)
    if dock is None:
        return
    k = panel.key
    data[f"{k}_visible"] = dock.isVisible()
    if not dock.isVisible():
        return
    data[f"{k}_area"] = _side(mw, panel) or panel.default_side
    data[f"{k}_width"] = max(_COLLECTQUEST_PANEL_MIN_WIDTH, dock.width())
    data[f"{k}_floating"] = dock.isFloating()
    # Only while visible, as a hidden dock can report a wrong frameGeometry(); relative to Anki's
    # window, so it survives moving between screens.
    if dock.isFloating() and not (respect_skip and getattr(mw, panel.skip_save_attr, False)):
        rect = dock.frameGeometry()
        mw_win = mw.window().frameGeometry()
        data[f"{k}_float_rel_x"] = rect.x() - mw_win.x()
        data[f"{k}_float_rel_y"] = rect.y() - mw_win.y()
        data[f"{k}_float_width"] = max(200, rect.width())
        data[f"{k}_float_height"] = max(300, rect.height() - _FLOAT_HEIGHT_SAVE_OFFSET)


def _save_panel_state(mw: QWidget, panel: _Panel) -> None:
    """Only while visible: the hide at profile close must not record the panel as closed."""
    dock = getattr(mw, panel.dock_attr, None)
    if dock is None or not dock.isVisible():
        return
    try:
        data = storage.load()
        _write_panel_state(mw, panel, data)
        storage.save(data)
    except Exception:
        pass


def _stop_float_save_timer(mw: QWidget, panel: _Panel) -> None:
    t = getattr(mw, panel.save_timer_attr, None)
    if t is not None:
        try:
            t.stop()
            t.deleteLater()  # parented to mw, so it would otherwise live all session
        except Exception:
            pass
        setattr(mw, panel.save_timer_attr, None)


def _start_float_save_timer(mw: QWidget, panel: _Panel) -> None:
    """Save a floating panel's position every 2s, so it is kept even if the panel is never closed."""
    t = QTimer(mw)
    t.setSingleShot(False)
    t.timeout.connect(lambda: _save_panel_state(mw, panel))
    t.start(2000)
    setattr(mw, panel.save_timer_attr, t)


def _float_other_if_same_side(mw: QWidget, panel: _Panel) -> None:
    """After a panel docks, float the other one if it is docked on the same side. Deferred, so Qt has
    updated dockWidgetArea() first."""
    other = _other(panel)

    def _enforce() -> None:
        side = _side(mw, panel)
        other_dock = getattr(mw, other.dock_attr, None)
        if side and other_dock and not other_dock.isFloating() and _side(mw, other) == side:
            other_dock.setFloating(True)

    QTimer.singleShot(0, _enforce)


def _expand_main_window_for_dock(mw: QWidget, expand: int, y_before: int, h_before: int) -> bool:
    """Widen the main window to make room for a newly shown dock, shared by both dock handlers.
    Returns False when already expanded, so callers only clear state after a real expansion."""
    if getattr(mw, "_collectquest_window_expanded", False):
        _update_center(mw)
        return False
    side = _side(mw, _PROGRESS)
    mw._collectquest_last_dock_side = side
    if side == "right":
        mw.resize(mw.width() + expand, mw.height())
        mw._collectquest_last_good_y = mw.y()
        mw._collectquest_last_good_height = mw.height()
    elif side == "left":
        # Saved y/height, so the window doesn't jump (Qt on Windows repositions after left-dock).
        # `is None`, since a saved y of 0 is valid.
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
    _update_center(mw)
    return True


def _on_collectquest_dock_visibility_changed(mw: QWidget, visible: bool) -> None:
    """On close/hide: shrink window only if dock was docked. On show: expand only if docked (not floating)."""
    dock = getattr(mw, "_collectquest_dock", None)
    # Stopped while hidden, so it can't save bad geometry.
    _stop_float_save_timer(mw, _PROGRESS)
    _save_panel_state(mw, _PROGRESS)
    # Floating panel: no effect on main window size.
    if dock and dock.isFloating():
        if visible:
            _start_float_save_timer(mw, _PROGRESS)
        _update_center(mw)
        return
    # Restore path: opening then immediately floating — don't expand
    if visible and getattr(mw, "_collectquest_restore_floating", False):
        _update_center(mw)
        return
    # Dock-in from float: skip expand here; topLevelChanged(False) will expand (avoids double expand)
    if visible and getattr(mw, "_collectquest_was_floating", False):
        _update_center(mw)
        return
    _y_before = mw.y()
    _h_before = mw.height()
    expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
    if not visible:
        # Shrink based on which side the dock was on (still known while closing)
        side = _side(mw, _PROGRESS)
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
        _update_center(mw)
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
        _stop_float_save_timer(mw, _PROGRESS)
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
        # Floats the shop even if hidden.
        _float_other_if_same_side(mw, _PROGRESS)
        if getattr(mw, "_collectquest_window_expanded", False):
            _update_center(mw)
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
    _update_center(mw)

# Rough title bar height, to tell the title bar (open hand: movable) from the content.
_TITLE_BAR_HEIGHT = 28


class _DockTitleBarCursorFilter(QObject):
    """Open-hand cursor over a docked panel's title bar, arrow elsewhere."""

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
                if y < _TITLE_BAR_HEIGHT and not getattr(self._dock, "isFloating", lambda: False)():
                    self._dock.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self._dock.setCursor(Qt.CursorShape.ArrowCursor)
            except Exception:
                pass
        elif t == QEvent.Type.Leave:
            self._dock.unsetCursor()
        return False


class _DockContentCursorFilter(QObject):
    """Clears the open-hand cursor when the mouse enters the content, so it doesn't stick. Owned by
    the content, so it goes when a refresh replaces it."""

    def __init__(self, dock_widget, content):
        super().__init__(content)
        self._dock = dock_widget

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            self._dock.setCursor(Qt.CursorShape.ArrowCursor)
        return False


def _install_content_cursor_filter(dock: QWidget, content: QWidget | None) -> None:
    if content is not None:
        content.installEventFilter(_DockContentCursorFilter(dock, content))
        content.setMouseTracking(True)


def _create_dock(mw: QWidget, panel: _Panel, title: str, object_name: str) -> QDockWidget:
    """Build a panel's dock on its saved side and remember it on mw."""
    dock = QDockWidget(title, mw)
    dock.setObjectName(object_name)
    dock.setAllowedAreas(_both_sides())
    dock.setFeatures(_dock_widget_features_default())
    dock.setMinimumWidth(_COLLECTQUEST_PANEL_MIN_WIDTH)
    side = panel.default_side
    try:
        side = storage.load().get(f"{panel.key}_area") or panel.default_side
    except Exception:
        pass
    area = Qt.DockWidgetArea.LeftDockWidgetArea if side == "left" else Qt.DockWidgetArea.RightDockWidgetArea
    mw.addDockWidget(area, dock)
    setattr(mw, panel.dock_attr, dock)
    return dock


def _apply_float_geometry(mw: QWidget, dock: QDockWidget, panel: _Panel) -> None:
    """Restore a floating panel's saved position and size, relative to Anki's window."""
    k = panel.key
    try:
        if not getattr(dock, "isFloating", lambda: False)():
            return
        data = storage.load()
        rel_x = data.get(f"{k}_float_rel_x")
        rel_y = data.get(f"{k}_float_rel_y")
        w = data.get(f"{k}_float_width")
        h = data.get(f"{k}_float_height")
        mw_win = mw.window().frameGeometry()
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and 200 <= w <= 1200 and 300 <= h <= 900:
            dock.resize(int(w), int(h))
        else:
            dock.resize(panel.default_width, 480)
        if isinstance(rel_x, (int, float)) and isinstance(rel_y, (int, float)):
            dock.move(mw_win.x() + int(rel_x), mw_win.y() + int(rel_y))
        else:
            dock.move(mw_win.x() + mw_win.width() - dock.width() - 20, mw_win.y() + 50)
    except Exception:
        pass
    finally:
        setattr(mw, panel.skip_save_attr, False)


def _apply_dock_width(mw: QWidget, dock: QDockWidget, panel: _Panel) -> None:
    """Set a docked panel to its saved width, or the default."""
    try:
        if not getattr(mw, "resizeDocks", None) or getattr(dock, "isFloating", lambda: False)():
            return
        w = storage.load().get(f"{panel.key}_width")
        if not isinstance(w, (int, float)) or w < _COLLECTQUEST_PANEL_MIN_WIDTH or w > 800:
            w = panel.default_width
        mw.resizeDocks([dock], [int(w)], Qt.Orientation.Horizontal)
    except Exception:
        pass


def _show_panel(mw: QWidget, dock: QDockWidget, panel: _Panel, content: QWidget) -> None:
    """Fill and show a panel, floating first if it was saved floating (so it never docks, then floats)."""
    # Re-applied, since Qt/Anki can reset them and break the drag-to-dock drop zones.
    dock.setAllowedAreas(_both_sides())
    dock.setFeatures(_dock_widget_features_default())
    old = dock.widget()
    if old:
        old.deleteLater()
    dock.setWidget(content)
    try:
        if storage.load().get(f"{panel.key}_floating"):
            dock.setFloating(True)
            setattr(mw, panel.skip_save_attr, True)
    except Exception:
        pass
    dock.show()
    # Once, next tick: a delayed re-apply made the window extend vertically.
    QTimer.singleShot(0, lambda: _apply_float_geometry(mw, dock, panel))
    # Twice, so Qt doesn't leave it oversized after dock-in.
    QTimer.singleShot(50, lambda: _apply_dock_width(mw, dock, panel))
    QTimer.singleShot(250, lambda: _apply_dock_width(mw, dock, panel))


def _create_progress_dock(mw: QWidget, on_refresh: Callable[[], None]) -> QDockWidget:
    dock = _create_dock(mw, _PROGRESS, "CollectQuest", "CollectQuestProgressDock")
    dock.setMouseTracking(True)  # for MouseMove over title vs content
    dock.installEventFilter(_DockTitleBarCursorFilter(dock))

    def _set_dock_button_cursors():
        for child in dock.findChildren(QAbstractButton):
            try:
                child.setCursor(Qt.CursorShape.PointingHandCursor)
            except Exception:
                pass

    QTimer.singleShot(50, _set_dock_button_cursors)
    mw._collectquest_on_refresh = on_refresh
    # Once: AnimatedDocks, so the drag-to-dock overlay shows.
    if not getattr(mw, "_collectquest_dock_options_ensured", False):
        try:
            if hasattr(mw, "dockOptions") and hasattr(mw, "setDockOptions"):
                opts = mw.dockOptions()
                animated = getattr(QMainWindow.DockOption, "AnimatedDocks", None) or getattr(QMainWindow, "AnimatedDocks", None)
                if animated is not None and (opts & animated) == 0:
                    mw.setDockOptions(opts | animated)
        except Exception:
            pass
        mw._collectquest_dock_options_ensured = True
    dock.visibilityChanged.connect(lambda v: _on_collectquest_dock_visibility_changed(mw, v))
    if getattr(dock, "topLevelChanged", None):
        dock.topLevelChanged.connect(lambda floating: _on_collectquest_dock_top_level_changed(mw, floating))
    return dock


def toggle_progress_panel(mw: QWidget, on_refresh: Callable[[], None]) -> None:
    """Show or hide the CollectQuest side panel, creating it on first use. Docked, the window grows by
    2/3 of the panel width and the main area gives up the rest."""
    if getattr(mw, "_collectquest_dock", None) is None:
        _create_progress_dock(mw, on_refresh)
    mw._collectquest_update_statusbar_center_width = lambda: update_center_width(mw)
    dock = mw._collectquest_dock
    if dock.isVisible():
        dock.hide()  # resize and status bar update follow from visibilityChanged
    else:
        content = build_progress_content_widget(dock, mw._collectquest_on_refresh, for_panel=True)
        _show_panel(mw, dock, _PROGRESS, content)
        _install_content_cursor_filter(dock, content)
    QTimer.singleShot(0, lambda: update_center_width(mw))


def _create_shop_dock(mw: QWidget) -> QDockWidget:
    dock = _create_dock(mw, _SHOP, "Shop", "CollectQuestShopDock")

    def _on_visibility_changed(visible: bool) -> None:
        _stop_float_save_timer(mw, _SHOP)
        _save_panel_state(mw, _SHOP)
        if visible and dock.isFloating():
            _start_float_save_timer(mw, _SHOP)

    def _on_top_level_changed(floating: bool) -> None:
        if not floating:
            _float_other_if_same_side(mw, _SHOP)
            return
        # Beside the main window, unless a saved position is being restored.
        if not getattr(mw, _SHOP.skip_save_attr, False):
            try:
                side = storage.load().get("shop_panel_area") or "left"
            except Exception:
                side = "left"
            QTimer.singleShot(
                50, lambda: _position_floating_dock_next_to_main(mw, getattr(mw, _SHOP.dock_attr, None), side)
            )

    dock.visibilityChanged.connect(_on_visibility_changed)
    if getattr(dock, "topLevelChanged", None):
        dock.topLevelChanged.connect(_on_top_level_changed)
    return dock


def toggle_shop_panel(mw: QWidget, on_refresh: Callable[[], None]) -> None:
    """Show or hide the Shop panel (left by default); the shop's locked dialog while it isn't open yet."""
    data = storage.load()
    today = streak_mod.today_str()
    gate_before = data.get("shop_gate_date", "")
    if not shop_mod.open_for_today(data, today):
        show_shop_dialog(mw, on_refresh)
        return
    # Stamped like the popup's, so undo can't lock the panel again today.
    if gate_before != today:
        storage.save(data)
    if getattr(mw, "_collectquest_shop_dock", None) is None:
        _create_shop_dock(mw)
    dock = mw._collectquest_shop_dock
    if dock.isVisible():
        dock.hide()
    else:
        _show_panel(mw, dock, _SHOP, build_shop_content_widget(dock, on_refresh, dock.hide, for_panel=True))


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
    content = build_progress_content_widget(dock, on_refresh, for_panel=True)
    dock.setWidget(content)
    _install_content_cursor_filter(dock, content)


def restore_saved_panels(mw: QWidget, data: dict, on_refresh: Callable[[], None]) -> None:
    """Reopen the panels the last session left open, once the bar has been built."""
    progress_dock = getattr(mw, "_collectquest_dock", None)
    if data.get("panel_visible") and (progress_dock is None or not progress_dock.isVisible()):
        want_floating = data.get("panel_floating")

        def _restore_panel():
            # Tells the visibility handler not to widen the window for a panel about to float.
            mw._collectquest_restore_floating = bool(want_floating)
            toggle_progress_panel(mw, on_refresh)
            mw._collectquest_restore_floating = False

        QTimer.singleShot(80, _restore_panel)
    shop_dock = getattr(mw, "_collectquest_shop_dock", None)
    if data.get("shop_panel_visible") and (shop_dock is None or not shop_dock.isVisible()):
        if shop_mod.is_open_today(data, streak_mod.today_str(getattr(mw, "col", None))):
            QTimer.singleShot(120, lambda: toggle_shop_panel(mw, on_refresh))


def close_panels(mw: QWidget) -> None:
    """Save both panels' placement for next time, then hide them so Anki stores the shrunk window."""
    data = storage.load()
    for panel in (_PROGRESS, _SHOP):
        _write_panel_state(mw, panel, data, respect_skip=False)
    storage.save(data)
    for panel in (_PROGRESS, _SHOP):
        dock = getattr(mw, panel.dock_attr, None)
        if dock is not None and dock.isVisible():
            dock.hide()
