"""The milestones window: the full track at full size, opened from the panel's [▸] button."""
from __future__ import annotations

from aqt.qt import (
    QDialog,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .. import milestones as milestones_mod, storage, xp
from .assets import _ink_pixmap, add_detail_window_close_row, add_detail_window_header, exec_dialog
from .constants import _DETAIL_MUTED

# Markers for the three states an entry can be in. Blank for locked rather than a third glyph: the
# list reads as a progression, and the eye needs to find the frontier, not label every row.
_MARK_DONE = "✓"
# An image rather than the ⏳ emoji, whose font metrics sat it off the checkmarks; the emoji is the
# fallback.
_MARK_ACTIVE = "⏳"
_MARK_ACTIVE_IMAGE = "ui/Hourglass.png"
# Height and downward nudge as fractions of line height, so the mark tracks the checkmark at any
# font size.
_MARK_ACTIVE_HEIGHT = 0.8
_MARK_ACTIVE_DROP = 0.1
_MARK_LOCKED = " "  # figure space, so locked rows align with marked ones

# Beyond this the table scrolls rather than growing the window off the screen.
_MAX_TABLE_HEIGHT = 620
# Font-relative gap right of the rewards column, which is the one that stretches.
_RIGHT_GUTTER = "MMM"
# Between the table and the Close button, matching the gap the CollectQuest window leaves between
# its scroll box and its button row.
_MUTED = _DETAIL_MUTED

# Grid columns: marker, objective, progress, reward. One grid for header and entries, so "Rewards"
# sits over its column by construction.
_COL_MARK, _COL_OBJECTIVE, _COL_PROGRESS, _COL_REWARD = range(4)
_MARK_W = 18
# Widest figure any row can show, used to size the progress column from the running font rather
# than from a pixel count that only held at the font this was written against.
_WIDEST_PROGRESS = "15/15"


def _add_entry_row(
    grid: QGridLayout,
    row: int,
    index: int,
    active: int,
    entry: dict,
    progress: int,
    target: int,
    blocked: bool = False,
) -> None:
    """One line of the track: marker, objective, progress when it is running, and the reward."""
    done = index < active
    is_active = index == active
    mark = _MARK_DONE if done else (_MARK_ACTIVE if is_active else _MARK_LOCKED)
    muted = not done and not is_active

    mark_lbl = QLabel()
    mark_lbl.setFixedWidth(_MARK_W)
    # Added to the grid before measuring, so it reports the grid's font rather than the app's.
    grid.addWidget(mark_lbl, row, _COL_MARK)
    line_h = mark_lbl.fontMetrics().height()
    mark_pm = (
        _ink_pixmap(_MARK_ACTIVE_IMAGE, max(1, round(line_h * _MARK_ACTIVE_HEIGHT)))
        if is_active
        else None
    )
    if mark_pm:
        mark_lbl.setPixmap(mark_pm)
        # Only the vertical needs help: a pixmap centers in the row where text sits on a baseline,
        # leaving it half a line-gap high. Small enough that the label stays shorter than the row.
        mark_lbl.setContentsMargins(0, max(1, round(line_h * _MARK_ACTIVE_DROP)), 0, 0)
    else:
        mark_lbl.setText(mark)

    # Never wrapped, so the markers stay scannable; the dialog is sized from the widest row instead.
    text = milestones_mod.objective_label(entry)
    if is_active and blocked:
        text += "  " + milestones_mod.CRAFT_BLOCKED_NOTE
    obj_lbl = QLabel(text)
    if muted:
        obj_lbl.setStyleSheet(_MUTED)
    grid.addWidget(obj_lbl, row, _COL_OBJECTIVE)

    # Only the active milestone shows a figure. The others have no counter running, so a number
    # there would imply one.
    prog_lbl = QLabel(f"{progress}/{target}" if is_active else "")
    prog_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(prog_lbl, row, _COL_PROGRESS)

    # Every entry names its reward, completed ones included: this is the only place a granted
    # reward is ever stated, so the window doubles as the answer to "where is this bonus from?".
    reward_lbl = QLabel(entry.get("reward", ""))
    if muted:
        reward_lbl.setStyleSheet(_MUTED)
    grid.addWidget(reward_lbl, row, _COL_REWARD)


def build_milestones_content(layout: QVBoxLayout, col=None) -> None:
    """Fill `layout` with the badge, the count and the full ladder. Shared by dialog and tests."""
    data = storage.load()
    active = milestones_mod.get_state(data)["active"]
    done_n = milestones_mod.completed_count(data)
    total = milestones_mod.TRACK_LENGTH
    progress, target = milestones_mod.active_progress(data, col)

    add_detail_window_header(layout, "ui/Icon_Badge2.png", "Milestones", f"{done_n}/{total}")
    layout.addSpacing(8)

    # Fourteen single-line entries fit without scrolling at the sizes below, but the scroll area is
    # here so a longer track, or a wrapped objective on a narrow screen, does not clip the last row.
    inner = QWidget()
    grid = QGridLayout(inner)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(4)
    # Only the reward column stretches, keeping the progress figure beside its objective.
    grid.setColumnStretch(_COL_OBJECTIVE, 0)
    grid.setColumnStretch(_COL_REWARD, 1)
    # The progress column is sized to its figure and left-aligned, against its objective.
    grid.setColumnMinimumWidth(
        _COL_PROGRESS, inner.fontMetrics().horizontalAdvance(_WIDEST_PROGRESS)
    )

    for text, column in (("Objectives", _COL_OBJECTIVE), ("Rewards", _COL_REWARD)):
        head_lbl = QLabel(text)
        head_lbl.setStyleSheet(_MUTED + " font-weight: bold;")
        grid.addWidget(head_lbl, 0, column)

    level = xp.level_from_total_xp(data.get("total_xp", 0))
    blocked = milestones_mod.craft_objective_blocked(data, level)
    for i, entry in enumerate(milestones_mod.LADDER, start=1):
        _add_entry_row(grid, i, i, active, entry, progress, target, blocked)
    grid.setRowStretch(len(milestones_mod.LADDER) + 1, 1)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(inner)
    # Sized from the table's own measurements, since a QScrollArea's hint is tiny; scrolling is only
    # a safety net.
    hint = inner.sizeHint()
    capped = min(hint.height(), _MAX_TABLE_HEIGHT)
    extra = 0
    if capped < hint.height():
        # Capped, so a vertical scrollbar will appear and eat width the table needs.
        extra = scroll.verticalScrollBar().sizeHint().width()
    scroll.setMinimumWidth(
        hint.width() + extra + inner.fontMetrics().horizontalAdvance(_RIGHT_GUTTER)
    )
    scroll.setMinimumHeight(capped)
    layout.addWidget(scroll, 1)

    if milestones_mod.is_finished(data):
        done_lbl = QLabel(milestones_mod.ALL_COMPLETE_LABEL)
        done_lbl.setStyleSheet(_MUTED)
        layout.addWidget(done_lbl)


def show_milestones_dialog(parent: QWidget | None = None, col=None) -> None:
    """Open the track in its own window."""
    d = QDialog(parent)
    d.setWindowTitle("Milestones")
    layout = QVBoxLayout(d)
    layout.setSpacing(6)
    build_milestones_content(layout, col)

    add_detail_window_close_row(layout, d)

    # Sized from the content with no floor; nothing wraps, so the hint is exact.
    d.adjustSize()
    exec_dialog(d)