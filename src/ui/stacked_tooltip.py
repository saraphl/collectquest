"""
A notification that stacks above existing ones instead of replacing them.

Anki's aqt.utils.tooltip is a singleton: it calls closeTooltip() first, so whichever add-on speaks
last is the only one heard. After a sync that is three messages competing for one slot — Anki's own
"Collection complete.", plus anything each add-on wants to report.

This builds the same widget Anki builds (same frame, palette and window flags, so it is
indistinguishable from the stock notification) but never touches Anki's _tooltipLabel/_tooltipTimer
globals. Nothing else can close it, and it closes nothing else.

--- THE CONTRACT -------------------------------------------------------------------------------
This file is self-contained and imports nothing from its host add-on, so it can be copied verbatim
into any add-on. Two add-ons that both use it stack correctly without importing each other and
without agreeing on any shared variable, because occupancy is read off the screen rather than
tracked. Both sides must agree on:

  1. RECOGNITION - a notification is any *visible top-level widget* whose window type is exactly
     Qt.WindowType.ToolTip, tested as `flags & WindowType_Mask == ToolTip` (a plain bit test
     also matches SplashScreen). This is what lets one add-on see another's label.
  2. PLACEMENT   - a new label goes above the topmost one already on screen, using that label's
     real geometry. Heights vary with text wrapping, so never assume a fixed slot pitch.
  3. GEOMETRY    - BASE_Y_OFFSET below the parent's bottom edge when alone, GAP_PX between boxes.
     A mismatch here is only cosmetic; a mismatch in 1 or 2 breaks stacking.

Known limitation: Qt's own hover tooltips also carry the ToolTip flag, so hovering a widget while a
notification appears can push the new one one slot higher. Harmless and transient.
------------------------------------------------------------------------------------------------
"""
from __future__ import annotations

import html

import aqt
from aqt.qt import (
    QColor,
    QFrame,
    QLabel,
    QPalette,
    QPoint,
    Qt,
    QWidget,
)

# Anki's own default y_offset, so a lone notification sits exactly where the stock one would.
BASE_Y_OFFSET = 100
GAP_PX = 6
DEFAULT_PERIOD_MS = 3000


class _StackedLabel(QLabel):
    """Mirrors Anki's CustomLabel: click to dismiss, and closes without fuss."""

    silentlyClose = True

    def mousePressEvent(self, evt) -> None:
        if evt is not None:
            evt.accept()
        self.hide()


def _visible_tooltips() -> list[QWidget]:
    """Every tooltip-like widget currently on screen, whoever created it."""
    found = []
    for w in aqt.mw.app.topLevelWidgets():
        try:
            if not w.isVisible():
                continue
            # Compared against WindowType_Mask, not bit-tested: SplashScreen (0x000f) contains
            # every bit of ToolTip (0x000d) and would otherwise register as a notification.
            if (w.windowFlags() & Qt.WindowType.WindowType_Mask) == Qt.WindowType.ToolTip:
                found.append(w)
        except RuntimeError:
            continue  # C++ side already deleted
    return found


def _position_for(label: QWidget, anchor: QWidget) -> QPoint:
    """
    Top-left corner for `label`: the stock position when nothing else is showing, otherwise just
    above whatever is lowest on screen.

    Computed in global coordinates because the labels being avoided may belong to other add-ons
    and other parent widgets.
    """
    default = anchor.mapToGlobal(QPoint(0, anchor.height() - BASE_Y_OFFSET))
    tops = []
    for w in _visible_tooltips():
        try:
            tops.append(w.mapToGlobal(QPoint(0, 0)).y())
        except RuntimeError:
            continue
    if not tops:
        return default
    return QPoint(default.x(), min(tops) - GAP_PX - label.height())


def stacked_tooltip(
    msg: str,
    period: int = DEFAULT_PERIOD_MS,
    parent: QWidget | None = None,
) -> QLabel | None:
    """
    Show `msg` for `period` ms, above any notification already visible. Returns the label.

    parent should be the main window: right after a sync the active window can still be the
    centered progress dialog, which would put the message in the middle of the screen.

    msg is escaped, so a deck name containing < or & displays rather than being parsed as
    markup. Callers wanting markup should not use this function.

    A newline in msg starts a new line. The cell holds rich text, where a newline character
    collapses to a space and silently produces one long line instead of two, so the split is done
    here and each line escaped on its own -- line breaks stay a structural request rather than
    markup a caller has to smuggle past the escape.
    """
    try:
        anchor = parent or aqt.mw.app.activeWindow() or aqt.mw
        body = "<br>".join(html.escape(line) for line in msg.split("\n"))
        lab = _StackedLabel(
            f"""<table cellpadding=10>
<tr>
<td>{body}</td>
</tr>
</table>""",
            anchor,
        )
        lab.setFrameStyle(QFrame.Shape.Panel)
        lab.setLineWidth(2)
        lab.setWindowFlags(Qt.WindowType.ToolTip)
        try:
            from aqt.theme import theme_manager

            night = theme_manager.night_mode
        except Exception:
            night = False
        if not night:
            p = QPalette()
            p.setColor(QPalette.ColorRole.Window, QColor("#feffc4"))
            p.setColor(QPalette.ColorRole.WindowText, QColor("#000000"))
            lab.setPalette(p)
        # Sized before positioning: the offset is measured from this label's own height.
        lab.adjustSize()
        lab.move(_position_for(lab, anchor))

        holder: dict[str, object] = {}

        def _close() -> None:
            for obj in (lab, holder.get("timer")):
                try:
                    if obj is not None:
                        obj.deleteLater()
                except RuntimeError:
                    pass  # parent window closed first, taking the object with it

        # Scheduled before the label is shown: if this raises, the fallback below reports the
        # message and no orphan is left on screen with nothing to close it. The timer is parented
        # to a long-lived window, so it is deleted explicitly once it has fired -- see the warning
        # in aqt/progress.py about closures kept alive for the parent's lifetime.
        holder["timer"] = aqt.mw.progress.timer(
            period, _close, False, requiresCollection=False, parent=anchor
        )
        lab.show()
        return lab
    except Exception as e:
        # Never let a notification break the caller. The fallback is Anki's singleton, i.e. the
        # overwriting behavior this module exists to avoid, so it is reported rather than silent:
        # otherwise a placement bug is indistinguishable from the module not being wired up.
        print(f"CollectQuest: stacked notification failed, using Anki's tooltip: {e!r}")
        try:
            from aqt.utils import tooltip as _anki_tooltip

            _anki_tooltip(msg, period=period, parent=parent)
        except Exception:
            pass
        return None
