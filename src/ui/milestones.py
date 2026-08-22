"""The milestones window: the full track at full size, opened from the panel's [▸] button."""
from __future__ import annotations

from aqt.qt import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .. import milestones as milestones_mod, storage, xp
from .assets import _pixmap

# Markers for the three states an entry can be in. Blank for locked rather than a third glyph: the
# list reads as a progression, and the eye needs to find the frontier, not label every row.
_MARK_DONE = "✓"
_MARK_ACTIVE = "⏳"
_MARK_LOCKED = " "  # figure space, so locked rows align with marked ones

_HEADER_ICON_PX = 96
_STATUS_ICON_PX = 24
# Beyond this the table scrolls rather than growing the window off the screen.
_MAX_TABLE_HEIGHT = 620
# Breathing room to the right of the rewards column. Measured from the font rather than set in
# pixels, so it stays the same visual gap at any size. The reward column is the one that stretches,
# so the width lands there as blank space after the text rather than as a layout margin.
_RIGHT_GUTTER = "MMM"
# Between the table and the Close button, matching the gap the CollectQuest window leaves between
# its scroll box and its button row.
_BUTTON_ROW_GAP = 8
_MUTED = "color: #888;"

# Grid columns: marker, objective, progress, reward. One grid for the header and every entry, so
# the "Rewards" label sits over the column it names by construction. Matching widths by hand does
# not work here — a header built from spacers and one built from labels distribute the leftover
# width differently, because stretch is shared out on top of each item's own size hint.
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

    mark_lbl = QLabel(mark)
    mark_lbl.setFixedWidth(_MARK_W)
    grid.addWidget(mark_lbl, row, _COL_MARK)

    # Never wrapped. An objective is one short phrase, and wrapping one turns a fourteen-row table
    # into a ragged block where the eye can no longer scan the markers down the left edge. The
    # dialog is sized from the widest row instead, below.
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

    # A pixmap in the dialog's own layout, the way the shop puts its sign above its heading. No
    # setWindowIcon: no other dialog in the add-on sets one, and KDE under Wayland generally takes
    # the title-bar icon from the application rather than the window anyway.
    badge = _pixmap("ui/Icon_Badge2.png", _HEADER_ICON_PX)
    if badge:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(badge)
        layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    header = QHBoxLayout()
    header.setSpacing(8)
    title_lbl = QLabel("Milestones")
    title_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")
    header.addWidget(title_lbl)
    count_lbl = QLabel(f"{done_n}/{total}")
    count_lbl.setStyleSheet(_MUTED)
    header.addWidget(count_lbl)
    header.addStretch()
    layout.addLayout(header)
    layout.addSpacing(8)

    # Fourteen single-line entries fit without scrolling at the sizes below, but the scroll area is
    # here so a longer track, or a wrapped objective on a narrow screen, does not clip the last row.
    inner = QWidget()
    grid = QGridLayout(inner)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(4)
    # Only the reward column stretches. Left to share the extra width, the objective column would
    # grow past its longest label and strand the progress figure halfway to the rewards, reading as
    # if it belonged to them rather than to the objective it counts.
    grid.setColumnStretch(_COL_OBJECTIVE, 0)
    grid.setColumnStretch(_COL_REWARD, 1)
    # The progress column holds one figure on one row, so it is sized to that figure and no wider.
    # Left-aligned in it, which puts the count against the objective it belongs to rather than
    # against the rewards, where a right-aligned figure in a roomy column ends up reading.
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
    # A QScrollArea reports a small fixed size hint in *both* directions regardless of what it
    # holds — setWidgetResizable makes the table follow the viewport, not the other way round — so a
    # dialog sized from the layout got a squeezed table and had to be padded back out with hardcoded
    # floors. Handing it the table's own measurements instead lets the dialog size itself to its
    # content, and the whole track then fits without scrolling, which is what makes the scroll area
    # a safety net rather than the normal case.
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

    _add_status_block(layout, data, col)


def _add_status_block(layout: QVBoxLayout, data: dict, col) -> None:
    """
    Standing state below the track, behind a rule: read after the chain, not before it.

    The accumulator is not an entry in a sequence — it is what the chain produced, and it changes
    daily without ever needing action. That is also why it is not in the panel: the panel carries
    the active milestone and, later, a running buff.
    """
    cap = milestones_mod.accumulator_cap_percent(data)
    if cap <= 0:
        return  # Nothing has been granted yet, so there is no standing state to report.

    rule = QFrame()
    rule.setFrameShape(QFrame.Shape.HLine)
    rule.setFrameShadow(QFrame.Shadow.Plain)
    layout.addSpacing(4)
    layout.addWidget(rule)
    layout.addSpacing(4)

    row = QHBoxLayout()
    row.setSpacing(8)
    icon = _pixmap("ui/accumulator.png", _STATUS_ICON_PX)
    if icon:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon)
        row.addWidget(icon_lbl)
    row.addWidget(QLabel("Streak accumulator"))

    charge = milestones_mod.accumulator_percent(data)
    value_lbl = QLabel(f"+{charge:g}% of +{cap}%")
    row.addWidget(value_lbl)

    # What is charging it, so a player wondering why their XP dipped can see that a broken streak
    # reset it rather than being left to guess.
    days = 0
    try:
        from .. import streak as streak_mod

        if col is not None:
            days, _ = streak_mod.get_display_streak_days(data, streak_mod.today_epoch(col))
    except Exception:
        days = 0
    source_lbl = QLabel(f"({days}-day streak)" if days else "(no streak)")
    source_lbl.setStyleSheet(_MUTED)
    row.addWidget(source_lbl)
    row.addStretch()
    layout.addLayout(row)

    # The Magnet line, present only while a stage is in progress — which under the supply rule is
    # exactly when a Magnet can be found at all. So the line is there whenever finding one is
    # possible, and absent whenever it is not.
    stage = milestones_mod.magnet_upgrade_in_progress(data)
    if stage is None:
        return
    mag_row = QHBoxLayout()
    mag_row.setSpacing(8)
    mag_icon = _pixmap("ui/magnet.png", _STATUS_ICON_PX)
    if mag_icon:
        lbl = QLabel()
        lbl.setPixmap(mag_icon)
        mag_row.addWidget(lbl)
    # Named, not counted: a count toward a specific upgrade, never a growing pile. It names no
    # target rate — the reward column above already states what each cap grants, and the count is
    # the only part that changes day to day.
    mag_row.addWidget(QLabel("Upgrade: find magnets"))
    count_lbl = QLabel(f"{milestones_mod.magnets_held(data)}/{stage['magnets']}")
    mag_row.addWidget(count_lbl)
    mag_row.addStretch()
    layout.addLayout(mag_row)


def show_milestones_dialog(parent: QWidget | None = None, col=None) -> None:
    """Open the track in its own window."""
    d = QDialog(parent)
    d.setWindowTitle("Milestones")
    layout = QVBoxLayout(d)
    layout.setSpacing(6)
    build_milestones_content(layout, col)

    layout.addSpacing(_BUTTON_ROW_GAP)
    close_row = QHBoxLayout()
    close_row.addStretch()
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.accept)
    # Twice the width its text asks for. Measured from the button's own hint rather than set to a
    # pixel count, so it stays proportionate at any font size.
    close_btn.setMinimumWidth(close_btn.sizeHint().width() * 2)
    close_row.addWidget(close_btn)
    layout.addLayout(close_row)

    # Sized from the content, with no floor. Nothing in the table wraps, so the layout's own hint is
    # the width the widest row needs and no more - a floor above it would only add empty margin to
    # the right of the rewards column.
    d.adjustSize()
    d.exec()
