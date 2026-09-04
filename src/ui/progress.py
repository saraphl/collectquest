"""Content widget for the CollectQuest progress panel (quests, streak, house)."""
from __future__ import annotations

import html
import os
from typing import Any, Callable
from aqt.qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
    Qt,
)
from .. import due_baseline, dungeon as dungeon_mod, milestones, prestige as prestige_mod, quests, review_rewards, shop as shop_mod, storage, streak as streak_mod, xp
from .options import show_options_dialog
from .assets import _house_pixmap, _icon_pixmap, _label_with_pixmap, equalize_button_widths, house_image_count, house_index_for_level, image_path, next_house_goal_level
from .constants import _COLLECTQUEST_PANEL_WIDTH, _DIALOG_BUTTON_MIN_WIDTH, _MUTED_STAT_STYLE, _POPUP_PROGRESS_DIALOG_WIDTH, _QUEST_BONUS_SEPARATOR_TOP_PAD, _QUEST_BONUS_SEPARATOR_WIDTH
from .items import add_items_stats_row
from .prestige import show_prestige_dialog
from .statusbar import _streak_display_filled, _streak_squares_widget

def _show_dungeon(owner: QWidget | None, on_refresh: Callable[[], None]) -> None:
    """Open the dungeon window. Deferred import, as the other child windows are."""
    from .dungeon import show_dungeon_dialog

    show_dungeon_dialog(owner, on_refresh)


def _show_milestones(owner: QWidget | None, col: Any) -> None:
    """Open the milestones window. Deferred import: ui/__init__ pulls this module in while building
    the package namespace."""
    from .milestones import show_milestones_dialog

    show_milestones_dialog(owner, col)


def _show_items(owner: QWidget | None) -> None:
    """Open the items window. Deferred for the same reason as the milestones one above."""
    from .items import show_items_dialog

    show_items_dialog(owner)


def child_window_button(
    label: str,
    owner: QWidget | None,
    opener: Callable[..., None],
    *args: Any,
    tooltip: str = "",
    for_panel: bool = False,
    **kwargs: Any,
) -> QPushButton:
    """Build a button that opens one of the CollectQuest window's own windows.

    Use it for every one of them: it parents the new window to `owner`, without which Anki can raise
    this window over a modal child that then refuses every click.
    """
    btn = QPushButton(label)
    if tooltip:
        btn.setToolTip(tooltip)
    if for_panel:
        # The dock shrinks to a sliver; without this the button sets a floor it cannot go below.
        btn.setMinimumWidth(1)
    btn.clicked.connect(lambda: opener(owner, *args, **kwargs))
    return btn


def _quest_reward_preview(
    data: dict,
    owned: list,
    base_xp: float,
    base_gold: float,
    gem_count: int,
) -> tuple[int, str]:
    """
    One quest row's rewards as (XP, "+Ng" or "+Ng, +N gems"), scaled by the player's collection.

    Shared by the rolled quests and the clear-the-day one, so no row can drift into promising a
    base constant. Built on the pure *_exact helpers: the award functions beside them move the
    fractional carry, so previewing with those would spend it just by drawing the panel.

    Gold is always named, because a quest carrying a gem now pays both rather than one or the other.
    The gem is named without its color: it is pre-rolled and stored, so the color is known, but an
    inline gem image would make these the only rows in the panel embedding one.
    """
    display_xp = review_rewards.preview_whole(review_rewards.quest_xp_exact(data, base_xp, owned))
    display_gold = review_rewards.preview_whole(
        review_rewards.quest_gold_exact(data, base_gold, owned)
    )
    reward = f"+{display_gold}g"
    if gem_count:
        reward += f", +{gem_count} gem{'s' if gem_count > 1 else ''}"
    return (display_xp, reward)

# The size every section's heading icon is drawn at.
_SECTION_ICON_PX = 24
# Between a heading and the muted line beneath it. The Items block has always used 2; this is that
# figure, lifted out so every section shares it.
_SECTION_LINE_SPACING = 2


def _section_open_button(parent: QWidget | None, opener, *args: Any) -> QPushButton:
    """The [▸] that opens a section's own window, wherever a section has one.

    A QPushButton rather than a clickable label: every interactive element in this panel is one,
    and a label that opens a window would be new vocabulary. Left-aligned beside the section's
    count rather than pushed to the far edge, so it reads as part of that heading rather than as a
    panel-level control the way the "⊞ Dock" button does.
    """
    # No for_panel: setFixedWidth below pins the width anyway.
    btn = child_window_button("▸", parent, opener, *args)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    # Native frame, only narrowed: a bare QPushButton reserves a default minimum width sized for a
    # word, which for a single glyph leaves a button mostly made of padding.
    btn.setStyleSheet("QPushButton { padding: 1px 6px; min-width: 0; }")
    btn.setFixedWidth(btn.fontMetrics().horizontalAdvance("▸") + 18)
    return btn


def _section_header(icon: str, title: str, for_panel: bool) -> QHBoxLayout:
    """A section's heading row: its icon and name, laid out the way every section here does it.

    Falls back to the bare title when the image is missing, so a half-installed images/ folder
    costs the icon rather than the heading.
    """
    row = QHBoxLayout()
    row.setSpacing(4)
    # _icon_pixmap, not _pixmap: fitting the frame lines the files up but not the art in them, and
    # each icon carries its own transparent margin - enough that the bag's title started six pixels
    # right of the badge's. Fitting the alpha bounding box puts every title at the same x.
    pm = _icon_pixmap(icon, _SECTION_ICON_PX)
    title_lbl = QLabel(title)
    if pm:
        header_w = _label_with_pixmap(pm, title_lbl)
        row.addWidget(header_w)
        if for_panel:
            header_w.setMinimumWidth(1)
    else:
        row.addWidget(title_lbl)
        if for_panel:
            title_lbl.setMinimumWidth(1)
    return row


def _add_prestige_section(
    layout, data: dict, parent, on_refresh, level: int, for_panel: bool, spacer: int
) -> None:
    """The Prestige section: star, heading with its points, the [>], and the run total below."""
    prestige_points_total = int(data.get("prestige_points_total", 0) or 0)
    # The same gate the Prestige button carried: reachable now, or reached before. Nothing is
    # gained by naming a screen to a player who cannot open anything on it yet.
    if not (prestige_mod.can_prestige(level) or prestige_points_total > 0):
        return
    # The star this section used to wear on a row of its own beside the XP bar. _section_header
    # falls back to a bare title if the file is missing, which is what the old row's own fallback
    # was reaching for - it named Star.png, which the add-on does not ship.
    header = _section_header("ui/Icon_Star_Grade_On.png", "Prestige", for_panel)
    # Beside the heading, where Milestones and Items carry their own counts: the points waiting to
    # be spent are this section's version of the same figure, and they read as one line with it.
    avail = prestige_mod.available_prestige_points(data)
    pts_lbl = QLabel(f" {avail} pts")
    pts_lbl.setStyleSheet(_MUTED_STAT_STYLE)
    header.addWidget(pts_lbl)
    if for_panel:
        pts_lbl.setMinimumWidth(1)
    header.addWidget(_section_open_button(parent, show_prestige_dialog, on_refresh))
    header.addStretch()
    layout.addLayout(header)

    # Indented two spaces like every other line that sits under a section heading here.
    prestige_count = int(data.get("prestige_count", 0) or 0)
    if prestige_count == 0 and prestige_points_total > 0:
        # Points with no recorded prestige means a save from before the count was kept.
        prestige_count = 1
    if prestige_count > 0:
        count_lbl = QLabel(
            f"  Prestiged {prestige_count} time{'s' if prestige_count != 1 else ''}."
        )
        count_lbl.setStyleSheet(_MUTED_STAT_STYLE)
        if for_panel:
            count_lbl.setMinimumWidth(1)
        layout.addWidget(count_lbl)
    layout.addSpacing(spacer)


def _add_dungeon_section(
    layout, data: dict, parent, on_refresh, level: int, for_panel: bool, spacer: int
) -> None:
    """The Dungeon section: heading and [>], with no status line - the window carries the state."""
    # Drawn from level 15, and also whenever there is a dungeon to show: undoing a review
    # recomputes the level, so a player can be back at 14 with one open, and the window must not
    # become unreachable while it still has something in it.
    if not (level >= dungeon_mod.UNLOCK_LEVEL or dungeon_mod.is_active(data)
            or isinstance(data.get("last_dungeon"), dict)):
        return
    # The small dungeon icon, which is the right size for a 24px section heading even though it was
    # too small for the window's own 96px header.
    header = _section_header("ui/Icon_Dungeon.png", "Dungeon", for_panel)
    header.addWidget(_section_open_button(parent, _show_dungeon, on_refresh))
    header.addStretch()
    layout.addLayout(header)

    # Only once there is something to count: "Completed 0 dungeons" is a line that says nothing and
    # would sit under the heading for the several hundred reviews before the first one is found.
    # Indented two spaces like every other line under a heading here.
    total = dungeon_mod.dungeons_claimed(data)
    if total > 0:
        this_run = dungeon_mod.dungeons_claimed_run(data)
        count_lbl = QLabel(
            f"  Completed {this_run} dungeon{'s' if this_run != 1 else ''} this run,"
            f" {total} total."
        )
        count_lbl.setStyleSheet(_MUTED_STAT_STYLE)
        if for_panel:
            count_lbl.setMinimumWidth(1)
        layout.addWidget(count_lbl)
    layout.addSpacing(spacer)


def _add_milestones_section(
    layout, data: dict, parent, col, for_panel: bool, spacer: int
) -> None:
    """The panel's Milestones section: header, count, the [▸] button, and the active row."""
    ms_header = _section_header("ui/Icon_Badge2.png", "Milestones", for_panel)
    ms_count_lbl = QLabel(f" {milestones.completed_count(data)}/{milestones.TRACK_LENGTH}")
    ms_count_lbl.setStyleSheet(_MUTED_STAT_STYLE)
    ms_header.addWidget(ms_count_lbl)
    if for_panel:
        ms_count_lbl.setMinimumWidth(1)
    ms_header.addWidget(_section_open_button(parent, _show_milestones, col))
    ms_header.addStretch()
    layout.addLayout(ms_header)

    ms_entry = milestones.active_entry(data)
    if ms_entry is None:
        ms_text = f"  {milestones.ALL_COMPLETE_LABEL}"
    else:
        ms_progress, ms_target = milestones.active_progress(data, col)
        # No "Next:" prefix — without it the row is structurally identical to a quest row,
        # "label: progress/target", which is the point of putting it in the same panel.
        ms_text = f"  {milestones.objective_label(ms_entry)}: {ms_progress}/{ms_target}"
        # Says the objective cannot currently be met rather than rescaling it or quietly finishing
        # it. Derived here, so a level-up that unlocks new items takes the note straight back off.
        if milestones.craft_objective_blocked(data, xp.level_from_total_xp(data.get("total_xp", 0))):
            ms_text += f"  {milestones.CRAFT_BLOCKED_NOTE}"
    ms_lbl = QLabel(ms_text)
    ms_lbl.setWordWrap(True)
    if for_panel:
        ms_lbl.setMinimumWidth(1)
    layout.addWidget(ms_lbl)

    layout.addSpacing(spacer)


def _add_accumulator_section(layout, data: dict, for_panel: bool, spacer: int) -> None:
    """The panel's Streak accumulator section: the charge, and the Magnet count while one is due.

    Lives here rather than in the milestones window because it is standing state that changes daily
    without ever needing action - the same reason the running buffs below it are in the panel.
    """
    cap = milestones.accumulator_cap_percent(data)
    if cap <= 0:
        return  # Nothing has been granted yet, so there is no standing state to report.

    header = _section_header("ui/accumulator.png", "Streak accumulator", for_panel)
    header.addStretch()
    layout.addLayout(header)

    # "+7 of +10% XP", not "+7% of +10%": the bare figure reads as progress toward the cap rather
    # than as a second, unrelated percentage, and naming the stat says what the number actually
    # does. At the cap there is no progress left to show, so it drops to the one figure that is
    # true. The last Magnet stage widens it to gold, and the label says so.
    charge = milestones.accumulator_percent(data)
    stats = "XP & gold" if milestones.accumulator_boosts_gold(data) else "XP"
    full = charge >= cap
    value = f"+{cap}% {stats}" if full else f"+{charge:g} of +{cap}% {stats}"
    # Which of the two states it is in, so a player wondering why their XP dipped can see it is
    # rebuilding rather than being left to guess. Muted and parenthesized like a quest's reward.
    note = (
        "fully charged" if full
        else f"charging +{milestones.accumulator_rate_percent_per_day(data):g}%/day"
    )
    charge_lbl = QLabel(
        f"&nbsp;&nbsp;{html.escape(value)}&nbsp;&nbsp;"
        f'<span style="{_MUTED_STAT_STYLE}">({html.escape(note)})</span>'
    )
    charge_lbl.setTextFormat(Qt.TextFormat.RichText)
    charge_lbl.setWordWrap(True)
    if for_panel:
        charge_lbl.setMinimumWidth(1)
    layout.addWidget(charge_lbl)

    # The Magnet line, present only while a stage is in progress - which under the supply rule is
    # exactly when a Magnet can be found at all. So the line is there whenever finding one is
    # possible, and absent whenever it is not.
    stage = milestones.magnet_upgrade_in_progress(data)
    if stage is not None:
        # "label: progress/target", the same shape as the quest and milestone rows above.
        mag_lbl = QLabel(f"  Find magnets: {milestones.magnets_held(data)}/{stage['magnets']}")
        mag_lbl.setWordWrap(True)
        if for_panel:
            mag_lbl.setMinimumWidth(1)
        layout.addWidget(mag_lbl)

    layout.addSpacing(spacer)


def _add_buffs_section(layout, data: dict, col, for_panel: bool, spacer: int) -> None:
    """The panel's Buffs section: header, then one row per running buff.

    Drawn only while something is running. A heading over an empty list is a system the player has
    to read and dismiss, the same reason the Milestones section stays hidden below its unlock level.
    """
    running = [
        (entry, buff)
        for entry in milestones.active_buffs(data, col)
        if (buff := milestones.buff_by_id(entry.get("id")))
    ]
    if not running:
        return

    # The image rather than the ⏳ emoji, which comes from the color emoji font and carries its
    # metrics into the row - see ui/milestones._MARK_ACTIVE_IMAGE, the marker this one echoes.
    header = _section_header("ui/Hourglass.png", "Temporary buffs", for_panel)
    header.addStretch()
    layout.addLayout(header)

    for entry, buff in running:
        left = milestones.buff_days_left(entry, col)
        # Built like a quest row, down to the two-space indent and the muted figure in
        # parentheses: both say "this is running, here is where it stands". HTML collapses leading
        # spaces, so the indent is two non-breaking ones.
        buff_text = (
            f"&nbsp;&nbsp;{html.escape(buff['label'])}&nbsp;&nbsp;"
            f'<span style="{_MUTED_STAT_STYLE}">'
            f"({left} day{'s' if left != 1 else ''} left)</span>"
        )
        buff_lbl = QLabel(buff_text)
        buff_lbl.setTextFormat(Qt.TextFormat.RichText)
        buff_lbl.setWordWrap(True)
        if for_panel:
            buff_lbl.setMinimumWidth(1)
        layout.addWidget(buff_lbl)

    layout.addSpacing(spacer)


def _reroll_quest_clicked(index: int, on_refresh) -> None:
    """Spend the week's reroll on one quest. Nothing is charged if the swap cannot be made."""
    from aqt import mw as _mw
    from aqt.utils import tooltip

    col = getattr(_mw, "col", None)
    data = storage.load()
    if not milestones.quest_reroll_available(data, col):
        return
    # The swap is attempted before the allowance is spent, so a day with nothing to swap to leaves
    # the reroll unused rather than consuming a week's worth of it for no change.
    new_quest = quests.reroll_quest(data, index, col)
    if new_quest is None:
        tooltip("No other quest available to swap to today.")
        return
    milestones.spend_quest_reroll(data, col)
    storage.save(data)
    tooltip(f"New quest: {quests.quest_display_label(new_quest, col)}")
    if on_refresh:
        on_refresh()


def build_progress_content_widget(
    parent: QWidget | None,
    on_refresh: Callable[[], None],
    *,
    for_panel: bool = False,
    close_button: QPushButton | None = None,
) -> QWidget:
    """Build the progress view (level, XP, streak, house, quests, collectibles, Options).
    for_panel: slightly tighter spacing and smaller collectibles scroll height for side panel.
    close_button: placed in the bottom button row, right of Options (dialog only; the dock has none).

    Every dialog opened from here is parented to `parent`, i.e. to this window: a dialog parented to
    the main window instead let Anki raise this one over a modal child that then refused clicks."""
    data = storage.load()
    # One lookup for the whole build: the streak, quest, bonus, milestone and buff blocks below all
    # need the collection, and separate reads of it could only drift apart.
    col = None
    try:
        from aqt import mw as _mw
        col = getattr(_mw, "col", None)
    except Exception:
        col = None
    total_xp = data.get("total_xp", 0)
    lev, xp_in, xp_needed = xp.xp_progress_in_level(total_xp)
    daily_quests = data.get("daily_quests", [])
    spacer = 4 if for_panel else 8

    root = QWidget(parent)
    if for_panel:
        root.setMinimumWidth(1)  # allow dock to shrink to its minimum
    layout = QVBoxLayout(root)
    # Every section's heading and the muted line under it sit at this distance, so the panel has
    # one vertical rhythm rather than one per section. It matches the Items block, which set its
    # own spacing and was the only section that looked right: the rest inherited Qt's default of
    # roughly six pixels, which read as a gap between two things rather than as one heading with
    # its subtitle. Separation between sections is drawn by the explicit addSpacing(spacer) calls,
    # not by this - which is why tightening it does not run the sections together.
    layout.setSpacing(_SECTION_LINE_SPACING)
    if for_panel:
        layout.setContentsMargins(6, 5, 6, 5)
    else:
        layout.setContentsMargins(8, 6, 8, 6)

    # When floating: small re-dock button top-right, discreet
    if for_panel and parent is not None and getattr(parent, "isFloating", None) is not None:
        dock_row = QHBoxLayout()
        dock_row.addStretch()
        dock_btn = QPushButton("⊞ Dock")
        dock_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        dock_btn.setStyleSheet(
            "QPushButton { font-size: 10px; color: #888; padding: 1px 6px; border: 1px solid palette(window); border-radius: 2px; "
            "background: transparent; min-width: 0; outline: none; } "
            "QPushButton:hover, QPushButton:focus, QPushButton:pressed { background: transparent; border: 1px solid palette(window); outline: none; }"
        )
        dock_btn.setToolTip("Attach panel to main window (left or right). Uses other side if current is occupied.")
        dock_btn.setVisible(parent.isFloating())
        # Imported here rather than at module scope: docks imports this module to build its panel
        # content, so a top-level import would close the loop. Deferring to click time breaks it.
        from .docks import _dock_progress_panel

        dock_btn.clicked.connect(lambda: _dock_progress_panel(parent))
        if getattr(parent, "topLevelChanged", None) is not None:
            def _on_progress_float_changed(floating: bool) -> None:
                try:
                    dock_btn.setVisible(floating)
                except RuntimeError:
                    pass  # content may have been replaced (e.g. on re-dock)
            parent.topLevelChanged.connect(_on_progress_float_changed)
        dock_row.addWidget(dock_btn)
        layout.addLayout(dock_row)

    # --- Level & XP (progression) ---
    level_row = QHBoxLayout()
    lv_lbl = QLabel(f"Level {lev}")
    xp_lbl = QLabel(f"{total_xp} total XP")
    if for_panel:
        lv_lbl.setMinimumWidth(1)
        xp_lbl.setMinimumWidth(1)
    level_row.addWidget(lv_lbl)
    level_row.addStretch()
    level_row.addWidget(xp_lbl)
    layout.addLayout(level_row)

    xp_bar = QProgressBar()
    xp_bar.setMinimum(0)
    xp_bar.setMaximum(max(1, xp_needed))
    xp_bar.setValue(xp_in)
    xp_bar.setFormat(f"{xp_in} / {xp_needed} XP to next level")
    if for_panel:
        xp_bar.setMinimumWidth(1)
    layout.addWidget(xp_bar)
    layout.addSpacing(spacer)

    # --- 7-day streak (revlog-based; compute only, reward is centralized elsewhere) ---
    streak_filled = 0
    current_streak_days = 0
    try:
        if col:
            streak_mod.refresh_streak(data, col)
            storage.save(data)
            today_ep = streak_mod.today_epoch(col)
            current_streak_days, _ = streak_mod.get_display_streak_days(data, today_ep)
            streak_filled = ((current_streak_days - 1) % streak_mod.STREAK_LENGTH) + 1 if current_streak_days > 0 else 0
        else:
            streak_filled = _streak_display_filled(data)
            start = int(data.get("current_streak_start_date") or 0)
            end = int(data.get("current_streak_end_date") or 0)
            if start > 0 and end >= start:
                current_streak_days = ((end - start) // 86400) + 1
    except Exception:
        streak_filled = _streak_display_filled(data)
        start = int(data.get("current_streak_start_date") or 0)
        end = int(data.get("current_streak_end_date") or 0)
        if start > 0 and end >= start:
            current_streak_days = ((end - start) // 86400) + 1
    streak_reward_type = data.get("streak_reward_type")  # None until next week → no icon
    streak_row = QHBoxLayout()
    streak_lbl = QLabel("7 day:")
    streak_lbl.setStyleSheet("font-size: 11px;")
    if for_panel:
        streak_lbl.setMinimumWidth(1)
    streak_row.addWidget(streak_lbl)
    streak_sq = _streak_squares_widget(streak_filled, size=12, reward_type=streak_reward_type)
    if for_panel and streak_sq:
        streak_sq.setMinimumWidth(1)
    streak_row.addWidget(streak_sq)
    streak_row.addSpacing(12)
    streak_row.addStretch()
    if current_streak_days > 0:
        current_lbl = QLabel(f"Streak {current_streak_days} day{'s' if current_streak_days != 1 else ''}")
        current_lbl.setStyleSheet("font-size: 11px;")
        if for_panel:
            current_lbl.setMinimumWidth(1)
        streak_row.addWidget(current_lbl)
    layout.addLayout(streak_row)
    layout.addSpacing(spacer)

    # --- House (long-term goal) ---
    house_idx = house_index_for_level(lev)
    # Popup (old-style) uses shorter width; dock panel uses panel width.
    house_width = int(_COLLECTQUEST_PANEL_WIDTH) if for_panel else _POPUP_PROGRESS_DIALOG_WIDTH
    if house_idx >= 1:
        house_pm = _house_pixmap(house_idx, width=house_width)
        if house_pm and not house_pm.isNull():
            house_lbl = QLabel()
            house_lbl.setPixmap(house_pm)
            # Fix the house to its scaled size so it does not stretch/shrink.
            house_lbl.setMinimumSize(house_pm.width(), house_pm.height())
            house_lbl.setMaximumSize(house_pm.width(), house_pm.height())
            # Wrap in an HBox with stretches so it is truly centered horizontally.
            house_row = QHBoxLayout()
            house_row.addStretch()
            house_row.addWidget(house_lbl)
            house_row.addStretch()
            layout.addLayout(house_row)
            next_goal = next_house_goal_level(lev)
            has_next_image = next_goal is not None and house_idx < house_image_count()
            if has_next_image and next_goal > lev:
                goal_lbl = QLabel(f"Next house expansion at level {next_goal}")
                goal_lbl.setStyleSheet("color: #666; font-size: 11px;")
                goal_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if for_panel:
                    goal_lbl.setMinimumWidth(1)
                layout.addWidget(goal_lbl)
            else:
                goal_lbl = QLabel("Your house is fully expanded!")
                goal_lbl.setStyleSheet("color: #666; font-size: 11px;")
                goal_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if for_panel:
                    goal_lbl.setMinimumWidth(1)
                layout.addWidget(goal_lbl)
    layout.addSpacing(spacer if for_panel else 12)

    # --- Daily quests ---
    daily_header = _section_header("ui/Calendar.png", "Daily quests", for_panel)
    daily_header.addStretch()
    layout.addLayout(daily_header)
    owned = data.get("owned_collectibles", [])
    quests_container = QWidget()
    quests_container_layout = QVBoxLayout(quests_container)
    quests_container_layout.setContentsMargins(0, 0, 0, 0)
    quests_container_layout.setSpacing(2 if for_panel else 4)
    # Enumerated because the reroll button below needs the quest's index in state["daily_quests"],
    # which is what quests.reroll_quest replaces into. Skipped rows keep their index, so the button
    # cannot be pointed at the wrong quest by an orphaned deck row above it.
    #
    # Sorted by kind rather than left in rolled order, so a given kind always occupies the same row
    # and the pair reads the same way every day. Indexes are taken before the sort, so the reroll
    # button still points at the quest's real slot in state.
    for quest_index, q in sorted(
        enumerate(daily_quests), key=lambda pair: quests.quest_display_order(pair[1])
    ):
        # A quest whose deck was deleted can never be completed, so its row is dropped rather than
        # left sitting at stuck progress. Filtered per quest, not by position, so it works whichever
        # slot it occupies; the quest stays in state, because quest_progress_revert indexes into it.
        if quests.deck_quest_is_orphaned(q, col):
            continue
        prog = q.get("progress", 0)
        tgt = q.get("target", 0)
        # Rebuilt from the deck's current name, so a rename is reflected here immediately.
        label = quests.quest_display_label(q, col)
        done = prog >= tgt
        display_xp, reward_str = _quest_reward_preview(
            data,
            owned,
            q.get("reward_xp", 0),
            q.get("reward_gold", 10),
            len(quests.quest_gem_colors(q)) * milestones.gem_reward_multiplier(data, from_quest=True),
        )
        # Rich text, so the reward can be smaller and gray like the items count. HTML collapses
        # leading spaces, so the row's two-space indent is two non-breaking ones; the label carries
        # a deck name, so it is escaped rather than trusted as markup.
        qtext = (
            f"&nbsp;&nbsp;{'✓ ' if done else ''}{html.escape(label)}: {prog}/{tgt}"
            f'&nbsp;&nbsp;<span style="{_MUTED_STAT_STYLE}">(+{display_xp} XP, {reward_str})</span>'
        )
        ql = QLabel(qtext)
        ql.setTextFormat(Qt.TextFormat.RichText)
        # Wrapped rather than clipped: a deck name is truncated above, but a long deck plus a big
        # target and reward can still outrun the panel, and the dialog is capped at its max width.
        ql.setWordWrap(True)
        if for_panel:
            ql.setMinimumWidth(1)
        # The weekly reroll (milestone #6), offered only on a quest that can still use it: a
        # finished quest has already paid, and rerolling it would take the reward back. The button
        # is per row because the whole point of the reward is swapping the *particular* quest the
        # player cannot do, most often the new-cards one on a day with no new cards.
        if not done and milestones.quest_reroll_available(data, col):
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            row_l.addWidget(ql, 1)
            reroll_btn = QPushButton("⟳")
            reroll_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            reroll_btn.setStyleSheet("QPushButton { padding: 1px 6px; min-width: 0; }")
            reroll_btn.setFixedWidth(reroll_btn.fontMetrics().horizontalAdvance("⟳") + 18)
            reroll_btn.setToolTip("Swap this quest for a different one. Once a week.")
            reroll_btn.clicked.connect(
                lambda checked=False, idx=quest_index: _reroll_quest_clicked(idx, on_refresh)
            )
            row_l.addWidget(reroll_btn, 0, Qt.AlignmentFlag.AlignTop)
            if for_panel:
                row_w.setMinimumWidth(1)
            quests_container_layout.addWidget(row_w)
        else:
            quests_container_layout.addWidget(ql)

    # Clear-the-day bonus. Progress counts cards finished today that the day's baseline counted, so
    # a card failed with Again holds the count back until it graduates and cards new today do not
    # move it at all. Hidden when the day could not be measured or nothing was due, not shown as 0/0.
    try:
        cleared = due_baseline.cleared_progress(data, col)
    except Exception:
        cleared = None
    if cleared:
        done_n, total_n = cleared
        # The rule sits closer to the row above it than below, because the label above carries
        # descender space the 1px line does not. A few pixels on top even the two gaps out.
        quests_container_layout.addSpacing(_QUEST_BONUS_SEPARATOR_TOP_PAD)
        bonus_sep = QFrame()
        bonus_sep.setFrameShape(QFrame.Shape.HLine)
        bonus_sep.setFixedHeight(1)
        # Color is pinned rather than left to the frame's default 3D shading, which renders as a
        # hard dark line in dark mode; a translucent gray sits correctly on either theme. The left
        # margin lines the rule up with the rows, which begin two spaces in — measured from the font
        # rather than hardcoded, so it stays aligned at any font size or DPI.
        bonus_sep.setStyleSheet(
            "QFrame { border: none; background-color: rgba(128,128,128,0.35); margin-left: %dpx; }"
            % quests_container.fontMetrics().horizontalAdvance("  ")
        )
        # Maximum, not fixed: a fixed width would also raise the minimum and stop the dock being
        # dragged narrower than the rule, which every other widget here is careful to allow. No
        # alignment flag either — that would make the layout hand it only its 1px size hint.
        bonus_sep.setMaximumWidth(_QUEST_BONUS_SEPARATOR_WIDTH)
        if for_panel:
            bonus_sep.setMinimumWidth(1)
        quests_container_layout.addWidget(bonus_sep)

        # Formatted by the same helper as the quest rows above, so this row reads identically and
        # promises what the quest will actually pay rather than its base constants.
        display_bonus_xp, bonus_reward_str = _quest_reward_preview(
            data,
            owned,
            review_rewards.cleared_bonus_xp_base(data),
            review_rewards.cleared_bonus_gold_base(data),
            len(
                review_rewards.cleared_bonus_gem_colors(
                    data, streak_mod.today_str(col)
                )
            )
            * milestones.gem_reward_multiplier(data, from_quest=True),
        )
        # Rich text, so "Bonus:" can be bold. HTML collapses leading spaces, which would lose the
        # two-space indent the quest rows above use, so the indent is two non-breaking spaces.
        bonus_text = (
            f"&nbsp;&nbsp;{'✓ ' if done_n >= total_n else ''}<b>Bonus:</b> "
            f"{review_rewards.CLEARED_BONUS_LABEL}: {done_n}/{total_n}&nbsp;&nbsp;"
            f'<span style="{_MUTED_STAT_STYLE}">(+{display_bonus_xp} XP, {bonus_reward_str})</span>'
        )
        bl = QLabel(bonus_text)
        bl.setTextFormat(Qt.TextFormat.RichText)
        # Wrapped for the same reason the quest rows above are: this row is longer than they are,
        # carrying a bold prefix as well as the progress and reward figures.
        bl.setWordWrap(True)
        if for_panel:
            bl.setMinimumWidth(1)
        quests_container_layout.addWidget(bl)

    if for_panel:
        quests_container.setMinimumWidth(1)
    layout.addWidget(quests_container)
    layout.addSpacing(spacer)

    # --- Milestones ---
    # One entry: exactly one milestone runs at a time, and the window behind [▸] holds the rest.
    # Hidden entirely below the unlock level rather than shown empty - the counters are not running
    # either, and an empty heading is still a system the player has to read and dismiss.
    if milestones.is_unlocked(data):
        _add_milestones_section(layout, data, parent, col, for_panel, spacer)

    # --- Items (collectibles) ---
    # The heading, the count and the standing bonuses; the collection itself lives behind the [▸],
    # which keeps the panel a summary rather than a list that grows with every purchase.
    owned_collectibles = data.get("owned_collectibles", [])
    items_block = QWidget()
    items_block_layout = QVBoxLayout(items_block)
    items_block_layout.setContentsMargins(0, 0, 0, 0)
    items_block_layout.setSpacing(_SECTION_LINE_SPACING)
    # Added before it is filled: the stats row measures its indent from this widget's font, and an
    # unparented widget reports the application default rather than the font it will inherit here.
    if for_panel:
        items_block.setMinimumWidth(1)
    layout.addWidget(items_block)
    # Count and [▸] beside the heading, exactly as the milestones section carries its own.
    bag_row = _section_header("collectibles/Bag.png", "Items", for_panel)
    items_count_lbl = QLabel(
        f" {len(owned_collectibles)}/{len(shop_mod.COLLECTIBLES)}"
    )
    items_count_lbl.setStyleSheet(_MUTED_STAT_STYLE)
    bag_row.addWidget(items_count_lbl)
    if for_panel:
        items_count_lbl.setMinimumWidth(1)
    bag_row.addWidget(_section_open_button(parent, _show_items))
    bag_row.addStretch()
    items_block_layout.addLayout(bag_row)
    add_items_stats_row(items_block_layout, owned_collectibles, for_panel, indent=True)
    layout.addSpacing(spacer)

    # --- Prestige and Dungeon ---
    # Sections rather than buttons in the row below. Four windows hang off this panel and only two
    # of them had a heading; as buttons the other two crowded Options and Close into slivers, and
    # the row got narrower again every time a window was added. A section costs a line and scales.
    _add_prestige_section(layout, data, parent, on_refresh, lev, for_panel, spacer)
    _add_dungeon_section(layout, data, parent, on_refresh, lev, for_panel, spacer)

    # --- Streak accumulator ---
    _add_accumulator_section(layout, data, for_panel, spacer)

    # --- Buffs ---
    # Below the items because both read as "what is currently working for you", and a buff is the
    # temporary half of that pair. Self-hiding, so the section costs nothing on the usual day.
    _add_buffs_section(layout, data, col, for_panel, spacer)

    # Two buttons only: Prestige and Dungeon are sections above, where they have room for a
    # heading and a status line instead of competing for width down here.
    options_row = QHBoxLayout()
    options_btn = child_window_button(
        "Options",
        parent,
        show_options_dialog,
        on_refresh,
        tooltip="Reset progress, difficulty, cheat (if admin.txt present)",
        for_panel=for_panel,
    )
    # The dialog puts its Close button here so it sits beside Options rather than on its own row.
    # The dock panel passes nothing and keeps the row as-is.
    if for_panel:
        # The dock shrinks to a sliver, so its buttons keep the full width rather than a fixed one
        # they could not shrink below.
        options_row.addWidget(options_btn, 1)
    else:
        # Right-aligned row of equal width, Close last - the same shape as the prestige window.
        options_row.addStretch()
        options_row.addWidget(options_btn)
        if close_button is not None:
            options_row.addWidget(close_button)
        equalize_button_widths(options_btn, close_button, minimum=_DIALOG_BUTTON_MIN_WIDTH)

    layout.addLayout(options_row)

    return root
