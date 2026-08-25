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
from .assets import _icon_pixmap, _ink_pixmap

# Markers for the three states an entry can be in. Blank for locked rather than a third glyph: the
# list reads as a progression, and the eye needs to find the frontier, not label every row.
_MARK_DONE = "✓"
# Drawn from images/ui/ rather than as the ⏳ emoji, which came from the color emoji font and
# carried its metrics into the row - sitting high and right of the checkmarks above it. The emoji
# stays as the fallback for a missing image.
_MARK_ACTIVE = "⏳"
_MARK_ACTIVE_IMAGE = "ui/Hourglass.png"
# Height and downward nudge, as fractions of the row's line height rather than pixels: a fixed 2px
# nudge measured right at 9-13pt but drifted 3.5px off at 26pt. As fractions the mark tracks the
# checkmark at any font size and stays shorter than the objective beside it, so no row grows.
_MARK_ACTIVE_HEIGHT = 0.8
_MARK_ACTIVE_DROP = 0.1
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

    mark_lbl = QLabel()
    mark_lbl.setFixedWidth(_MARK_W)
    # Added to the grid before it is measured, not after: an unparented label reports the
    # application font, while the row is drawn in the font of the grid's own widget. The sizes
    # below are fractions of that font's line height, so measuring the wrong one silently
    # mis-sizes the mark.
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

    # A pixmap in the layout, as the shop puts its sign above its heading - not setWindowIcon, which
    # no dialog here sets. content = the full canvas, unlike the shop grids: nothing shares a column
    # with this badge, so there is no inset to reserve.
    badge = _icon_pixmap("ui/Icon_Badge2.png", _HEADER_ICON_PX, content=_HEADER_ICON_PX)
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
    # A QScrollArea reports a small fixed size hint whatever it holds, so a dialog sized from the
    # layout squeezed the table. Sizing from the table's own measurements makes the whole track fit
    # without scrolling, leaving the scroll area a safety net.
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
    icon = _icon_pixmap("ui/accumulator.png", _STATUS_ICON_PX, content=_STATUS_ICON_PX)
    if icon:
        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon)
        row.addWidget(icon_lbl)
    row.addWidget(QLabel("Streak accumulator"))

    # "+7 of +10% XP", not "+7% of +10%": the bare figure reads as progress toward the cap rather
    # than as a second, unrelated percentage, and naming the stat says what the number actually
    # does. No "bonus" - the leading "+" already says it is one. The last Magnet stage widens it to
    # gold, and the label says so rather than leaving the player to notice their gold moved.
    charge = milestones_mod.accumulator_percent(data)
    stats = "XP & gold" if milestones_mod.accumulator_boosts_gold(data) else "XP"
    value_lbl = QLabel(f"+{charge:g} of +{cap}% {stats}")
    row.addWidget(value_lbl)

    # What is charging it, so a player wondering why their XP dipped can see that a broken streak
    # reset it rather than being left to guess. The accumulator's own day count, not the player's
    # streak length: the two differ while the ramp is still shorter than the run it sits inside,
    # and a bracket reading "11-day streak" beside a "+1" would be explaining nothing.
    days = milestones_mod.accumulator_days(data, col)
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
    mag_icon = _icon_pixmap("ui/magnet.png", _STATUS_ICON_PX, content=_STATUS_ICON_PX)
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
