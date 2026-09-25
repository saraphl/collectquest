"""Hover tips drawn inside the window instead of as Qt tooltip popups, which Wayland closes almost
as soon as they appear. A tip stays up for as long as the cursor is on its widget."""
from __future__ import annotations

import time

from aqt.qt import QApplication, QCursor, QEvent, QLabel, QObject, QPoint, QStyle, QTimer, QToolTip, QWidget, Qt

from .assets import night_mode
from .constants import _HOVER_TIP_COLORS_DARK, _HOVER_TIP_COLORS_LIGHT

_TEXT_PROP = "cq_hover_tip"
_MAX_WIDTH = 420
_GAP = 4


def set_hover_tip(widget: QWidget, text: str) -> None:
    """Give `widget` a hover tip."""
    widget.setProperty(_TEXT_PROP, text)
    widget.installEventFilter(_filter())


class _HoverTip(QLabel):
    """The tip itself: one per window, a child of it, so nothing but the cursor leaving can close it."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def _restyle(self) -> None:
        """Colors and font for the current theme; per show, since the main window's tip outlives a
        theme switch."""
        bg, fg, border = _HOVER_TIP_COLORS_DARK if night_mode() else _HOVER_TIP_COLORS_LIGHT
        font = QToolTip.font()
        # In the style sheet, since a window's own QLabel rules would otherwise override setFont.
        size = f"{font.pointSizeF()}pt" if font.pointSizeF() > 0 else f"{font.pixelSize()}px"
        sheet = (
            f"QLabel {{ background: {bg}; color: {fg}; border: 1px solid {border}; border-radius: 4px;"
            f" padding: 3px 6px; font-size: {size}; font-weight: normal; }}"
        )
        if sheet != self.styleSheet():
            self.setStyleSheet(sheet)

    def show_for(self, anchor: QWidget, text: str) -> None:
        """Show `text` under `anchor` (above it if there's no room), kept inside the window."""
        win = self.parentWidget()
        self._restyle()
        self.setText(text)
        # One line if it fits, else wrapped.
        self.setWordWrap(False)
        w = min(self.sizeHint().width(), _MAX_WIDTH, win.width() - 2 * _GAP)
        self.setWordWrap(True)
        h = self.heightForWidth(w)
        top_left = anchor.mapTo(win, QPoint(0, 0))
        x = max(_GAP, min(top_left.x(), win.width() - w - _GAP))
        y = top_left.y() + anchor.height() + _GAP
        if y + h > win.height() - _GAP:
            y = max(_GAP, top_left.y() - h - _GAP)
        self.setGeometry(x, y, w, h)
        self.raise_()
        self.show()


class _HoverTipFilter(QObject):
    """Shows tips after Qt's usual tooltip delay, and at once while another tip was just showing."""

    def __init__(self) -> None:
        super().__init__(QApplication.instance())
        style = QApplication.style()
        self._wake_ms = style.styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay)
        self._asleep_s = style.styleHint(QStyle.StyleHint.SH_ToolTip_FallAsleepDelay) / 1000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_pending)
        self._pending: QWidget | None = None
        self._anchor: QWidget | None = None
        self._tip: _HoverTip | None = None
        self._hidden_at = 0.0

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        # No tips mid-drag, as with Qt's own.
        if kind == QEvent.Type.Enter and obj.property(_TEXT_PROP) and not QApplication.mouseButtons():
            self._pending = obj
            awake = self._anchor is not None or time.monotonic() - self._hidden_at < self._asleep_s
            if awake:
                self._show_pending()
            else:
                self._timer.start(self._wake_ms)
        elif kind in (QEvent.Type.Leave, QEvent.Type.Hide, QEvent.Type.MouseButtonPress):
            if obj is self._pending:
                self._timer.stop()
                self._pending = None
            if obj is self._anchor:
                self._hide()
                if kind == QEvent.Type.Leave:
                    self._resume_ancestor(obj)
        return False

    def _show_pending(self) -> None:
        self._timer.stop()
        anchor, self._pending = self._pending, None
        self._hide()
        if anchor is None or not _alive(anchor) or not anchor.isVisible():
            return
        win = anchor.window()
        tip = win.findChild(_HoverTip, options=Qt.FindChildOption.FindDirectChildrenOnly) or _HoverTip(win)
        self._anchor, self._tip = anchor, tip
        # The anchor may be rebuilt away (the status bar is, every review) without a Leave.
        anchor.destroyed.connect(self._on_anchor_destroyed)
        tip.show_for(anchor, anchor.property(_TEXT_PROP))

    def _hide(self) -> None:
        anchor, tip = self._anchor, self._tip
        self._anchor = self._tip = None
        if anchor is not None and _alive(anchor):
            anchor.destroyed.disconnect(self._on_anchor_destroyed)
        # Its window may have closed and deleted it.
        if tip is not None and _alive(tip) and tip.isVisible():
            tip.hide()
            self._hidden_at = time.monotonic()

    def _on_anchor_destroyed(self, *_args) -> None:
        # Mid-destruction: leave the anchor alone, just drop it and hide the tip.
        self._anchor = None
        self._hide()

    def _resume_ancestor(self, left: QWidget) -> None:
        """Back on a tipped parent (e.g. the streak row around its gift icon): show its tip again."""
        w = left.parentWidget()
        while w is not None:
            if w.property(_TEXT_PROP) and w.rect().contains(w.mapFromGlobal(QCursor.pos())):
                self._pending = w
                self._show_pending()
                return
            w = w.parentWidget()


def _alive(obj: QObject) -> bool:
    """False once Qt has deleted the object under its Python wrapper."""
    try:
        obj.objectName()
        return True
    except RuntimeError:
        return False


_instance: _HoverTipFilter | None = None


def _filter() -> _HoverTipFilter:
    global _instance
    if _instance is None:
        _instance = _HoverTipFilter()
    return _instance
