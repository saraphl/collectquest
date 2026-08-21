"""Content widget for the CollectQuest progress panel (quests, streak, house)."""
from __future__ import annotations

import os
from typing import Callable
from aqt.qt import (
    QEvent,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QObject,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from .. import due_baseline, prestige as prestige_mod, quests, review_rewards, shop as shop_mod, storage, streak as streak_mod, xp
from .options import show_options_dialog
from .assets import _house_pixmap, _label_with_pixmap, _pixmap, _pixmap_ui, house_index_for_level, image_path, next_house_goal_level
from .constants import _COLLECTQUEST_PANEL_WIDTH, _POPUP_PROGRESS_DIALOG_WIDTH, _QUEST_BONUS_SEPARATOR_TOP_PAD, _QUEST_BONUS_SEPARATOR_WIDTH, _VISIBLE_ITEM_ROWS
from .prestige import show_prestige_dialog
from .statusbar import _streak_display_filled, _streak_squares_widget

def _quest_reward_preview(
    data: dict,
    owned: list,
    base_xp: int,
    base_gold: int,
    gem_count: int,
) -> tuple[int, str]:
    """
    One quest row's rewards as (XP, "+Ng" or "+Ng, +N gems"), scaled by the player's collection.

    Shared by the rolled quests and the clear-the-day one so all three rows read the same and none
    can drift into promising a base constant. The *_exact helpers are pure; the award functions
    beside them move the fractional carry, so previewing with those would spend it just by drawing
    the panel.

    Gold is always named, because a quest carrying a gem now pays both rather than one or the other.
    The gem is named without its color: it is pre-rolled and stored, so the color is known, but these
    rows are plain-text labels and an inline image would make them the only rich text in the panel to
    embed one.
    """
    display_xp = review_rewards.preview_whole(review_rewards.quest_xp_exact(data, base_xp, owned))
    display_gold = review_rewards.preview_whole(
        review_rewards.quest_gold_exact(data, base_gold, owned)
    )
    reward = f"+{display_gold}g"
    if gem_count:
        reward += f", +{gem_count} gem{'s' if gem_count > 1 else ''}"
    return (display_xp, reward)

def build_progress_content_widget(
    parent: QWidget | None,
    on_refresh: Callable[[], None],
    parent_for_dialogs: QWidget | None,
    *,
    for_panel: bool = False,
    close_button: QPushButton | None = None,
) -> QWidget:
    """Build the progress view (level, XP, streak, house, quests, collectibles, Options).
    for_panel: slightly tighter spacing and smaller collectibles scroll height for side panel.
    close_button: placed in the bottom button row, right of Options (dialog only; the dock has none)."""
    data = storage.load()
    total_xp = data.get("total_xp", 0)
    lev, xp_in, xp_needed = xp.xp_progress_in_level(total_xp)
    daily_quests = data.get("daily_quests", [])
    spacer = 4 if for_panel else 8
    # Panel keeps a flat cap (the dock is resized by dragging); the dialog replaces this with a
    # height measured from _VISIBLE_ITEM_ROWS actual rows once they exist.
    scroll_max = 160 if for_panel else 220

    root = QWidget(parent)
    if for_panel:
        root.setMinimumWidth(1)  # allow dock to shrink to its minimum
    layout = QVBoxLayout(root)
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

    # --- Prestige (meta progression) ---
    prestige_count = int(data.get("prestige_count", 0) or 0)
    prestige_points_total = int(data.get("prestige_points_total", 0) or 0)
    if prestige_count == 0 and prestige_points_total > 0:
        prestige_count = 1
    prestige_avail = prestige_mod.available_prestige_points(data)
    if prestige_count > 0 or prestige_avail > 0:
        prestige_row = QHBoxLayout()
        star_pm = _pixmap_ui("Icon_Star_Grade_On.png", height=18)
        if not star_pm or star_pm.isNull():
            star_pm = _pixmap_ui("Star.png", height=18)
        if star_pm:
            star_lbl = QLabel()
            star_lbl.setPixmap(star_pm)
            prestige_row.addWidget(star_lbl)
        txt = f"Prestiged {prestige_count} time(s)"
        if prestige_avail > 0:
            txt += f"  •  {prestige_avail} pts"
        prestige_lbl = QLabel(txt)
        prestige_lbl.setStyleSheet("font-size: 11px; color: #888;")
        prestige_row.addWidget(prestige_lbl)
        prestige_row.addStretch()
        layout.addLayout(prestige_row)
        layout.addSpacing(spacer // 2)

    # --- 7-day streak (revlog-based; compute only, reward is centralized elsewhere) ---
    streak_filled = 0
    current_streak_days = 0
    try:
        from aqt import mw as _mw
        if getattr(_mw, "col", None):
            streak_mod.refresh_streak(data, _mw.col)
            storage.save(data)
            today_ep = streak_mod.today_epoch(_mw.col)
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
            has_next_image = next_goal is not None and os.path.isfile(image_path(os.path.join("house", f"{house_idx + 1}.png")))
            if has_next_image and next_goal > lev:
                goal_lbl = QLabel(f"Next unlock at level {next_goal}")
                goal_lbl.setStyleSheet("color: #666; font-size: 11px;")
                goal_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
                if for_panel:
                    goal_lbl.setMinimumWidth(1)
                layout.addWidget(goal_lbl)
            else:
                goal_lbl = QLabel("Best House obtained ! Thank you for playing")
                goal_lbl.setStyleSheet("color: #666; font-size: 11px;")
                goal_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
                if for_panel:
                    goal_lbl.setMinimumWidth(1)
                layout.addWidget(goal_lbl)
    layout.addSpacing(spacer if for_panel else 12)

    # --- Daily quests ---
    daily_header = QHBoxLayout()
    daily_header.setSpacing(4)
    cal_pm = _pixmap("ui/Calendar.png", 24)
    daily_quests_lbl = QLabel("Daily quests")
    if cal_pm:
        daily_header_w = _label_with_pixmap(cal_pm, daily_quests_lbl)
        daily_header.addWidget(daily_header_w)
        if for_panel:
            daily_header_w.setMinimumWidth(1)
    else:
        daily_header.addWidget(daily_quests_lbl)
        if for_panel:
            daily_quests_lbl.setMinimumWidth(1)
    daily_header.addStretch()
    layout.addLayout(daily_header)
    owned = data.get("owned_collectibles", [])
    quests_container = QWidget()
    quests_container_layout = QVBoxLayout(quests_container)
    quests_container_layout.setContentsMargins(0, 0, 0, 0)
    quests_container_layout.setSpacing(2 if for_panel else 4)
    try:
        from aqt import mw as _quest_mw
        _quest_col = getattr(_quest_mw, "col", None)
    except Exception:
        _quest_col = None
    for q in daily_quests:
        # A quest whose deck was deleted can never be completed, so its row is dropped rather than
        # left sitting at stuck progress. Filtered per quest, not by position, so it works whichever
        # slot it occupies; the quest stays in state, because quest_progress_revert indexes into it.
        if quests.deck_quest_is_orphaned(q, _quest_col):
            continue
        prog = q.get("progress", 0)
        tgt = q.get("target", 0)
        # Rebuilt from the deck's current name, so a rename is reflected here immediately.
        label = quests.quest_display_label(q, _quest_col)
        done = prog >= tgt
        display_xp, reward_str = _quest_reward_preview(
            data,
            owned,
            q.get("reward_xp", 0),
            q.get("reward_gold", 10),
            len(quests.quest_gem_colors(q)),
        )
        qtext = f"  {'✓ ' if done else ''}{label}: {prog}/{tgt}  (+{display_xp} XP, {reward_str})"
        ql = QLabel(qtext)
        # Wrapped rather than clipped: a deck name is truncated above, but a long deck plus a big
        # target and reward can still outrun the panel, and the dialog is capped at its max width.
        ql.setWordWrap(True)
        if for_panel:
            ql.setMinimumWidth(1)
        quests_container_layout.addWidget(ql)

    # Clear-the-day bonus. Progress counts cards finished today that the day's baseline counted, so
    # a card failed with Again holds the count back until it graduates and cards new today do not
    # move it at all. Hidden when the day could not be measured or nothing was due, not shown as 0/0.
    _cleared_col = None
    try:
        from aqt import mw as _cleared_mw
        _cleared_col = getattr(_cleared_mw, "col", None)
        cleared = due_baseline.cleared_progress(data, _cleared_col)
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
            review_rewards.CLEARED_BONUS_XP,
            review_rewards.CLEARED_BONUS_GOLD,
            len(
                review_rewards.cleared_bonus_gem_colors(
                    data, streak_mod.today_str(_cleared_col)
                )
            ),
        )
        # Rich text, so "Bonus:" can be bold. HTML collapses leading spaces, which would lose the
        # two-space indent the quest rows above use, so the indent is two non-breaking spaces.
        bonus_text = (
            f"&nbsp;&nbsp;{'✓ ' if done_n >= total_n else ''}<b>Bonus:</b> "
            f"{review_rewards.CLEARED_BONUS_LABEL}: {done_n}/{total_n}&nbsp;&nbsp;"
            f"(+{display_bonus_xp} XP, {bonus_reward_str})"
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

    # --- Items (collectibles) ---
    owned_collectibles = data.get("owned_collectibles", [])
    owned_list = list(reversed(owned_collectibles))
    total_items = len(shop_mod.COLLECTIBLES)
    stats_style = "color: #888; font-size: 10px;"
    items_block = QWidget()
    items_block_layout = QVBoxLayout(items_block)
    items_block_layout.setContentsMargins(0, 0, 0, 0)
    items_block_layout.setSpacing(2)
    bag_row = QHBoxLayout()
    bag_row.setSpacing(8)
    bag_pm = _pixmap("collectibles/Bag.png", 24)
    items_title_lbl = QLabel("Items")
    items_count_lbl = QLabel(f" {len(owned_collectibles)}/{total_items}")
    items_count_lbl.setStyleSheet(stats_style)
    if bag_pm:
        bag_icon = QLabel()
        bag_icon.setPixmap(bag_pm)
        bag_row.addWidget(bag_icon)
    bag_row.addWidget(items_title_lbl)
    bag_row.addWidget(items_count_lbl)
    if for_panel:
        items_title_lbl.setMinimumWidth(1)
        items_count_lbl.setMinimumWidth(1)
    bag_row.addStretch()
    items_block_layout.addLayout(bag_row)
    xp_pct = shop_mod.xp_bonus_percent(owned_collectibles)
    gold_pct = shop_mod.gold_bonus_percent(owned_collectibles)
    gold_flat = shop_mod.gold_flat(owned_collectibles)
    xp_flat = shop_mod.xp_flat(owned_collectibles)
    luck_pct = shop_mod.luck_gem_chance_percent(owned_collectibles)
    bonus_parts = []
    if xp_pct: bonus_parts.append(f"+{int(xp_pct)}% XP")
    if xp_flat: bonus_parts.append(f"+{xp_flat} XP")
    if gold_pct: bonus_parts.append(f"+{int(gold_pct)}% gold")
    if gold_flat: bonus_parts.append(f"+{gold_flat}g")
    if bonus_parts or luck_pct:
        stats_row = QHBoxLayout()
        if bonus_parts:
            other_lbl = QLabel("  ·  ".join(bonus_parts))
            other_lbl.setStyleSheet(stats_style)
            if for_panel:
                other_lbl.setMinimumWidth(1)
            stats_row.addWidget(other_lbl)
        if luck_pct:
            if bonus_parts:
                sep = QLabel("  ·  ")
                sep.setStyleSheet(stats_style)
                if for_panel:
                    sep.setMinimumWidth(1)
                stats_row.addWidget(sep)
            luck_lbl = QLabel(f"+{int(luck_pct)}% gem luck")
            luck_lbl.setStyleSheet(stats_style)
            luck_lbl.setToolTip("Gem luck improves your chances of finding gems")
            if for_panel:
                luck_lbl.setMinimumWidth(1)
            stats_row.addWidget(luck_lbl)
        stats_row.addStretch()
        items_block_layout.addLayout(stats_row)
    if for_panel:
        items_block.setMinimumWidth(1)
    layout.addWidget(items_block)

    # Single scrollable area: icon grid on top, then item list below. Keeps panel height under control.
    collectibles_scroll_content = QWidget()
    collectibles_scroll_content.setMinimumWidth(1)  # allow dock to shrink narrow
    collectibles_scroll_layout = QVBoxLayout(collectibles_scroll_content)
    collectibles_scroll_layout.setContentsMargins(0, 0, 0, 0)
    collectibles_scroll_layout.setSpacing(spacer)

    icon_sz = 28 if len(owned_list) > 20 else 32
    grid_spacing = 6
    icons_widget = QWidget()
    icons_widget.setMinimumWidth(1)
    icons_widget.setMaximumWidth(800)
    icons_layout = QGridLayout(icons_widget)
    icons_layout.setContentsMargins(0, 0, 0, 0)
    icons_layout.setSpacing(grid_spacing)
    icon_labels: list[QLabel] = []
    for cid in owned_list:
        c = shop_mod.get_collectible(cid)
        if not c:
            continue
        pm = _pixmap(c["image"], icon_sz)
        if not pm:
            continue
        effect = c.get("effect_description", "")
        tip = f"{c.get('name', cid)}: {effect}" if effect else c.get("name", cid)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(pm)
        icon_lbl.setToolTip(tip)
        icon_labels.append(icon_lbl)
    min_cols = 6
    cell_w = icon_sz + grid_spacing

    def _relayout_icons_grid():
        w = icons_widget.width()
        cols = max(min_cols, w // cell_w) if w > 0 else min_cols
        for lbl in icon_labels:
            icons_layout.removeWidget(lbl)
        for i, lbl in enumerate(icon_labels):
            r, c = divmod(i, cols)
            icons_layout.addWidget(lbl, r, c)
        # When only one row, align grid content left so it doesn't sit centered
        if len(icon_labels) <= cols:
            icons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        else:
            icons_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

    icons_widget._grid_relayout = _relayout_icons_grid
    _relayout_icons_grid()

    class _IconsGridResizeFilter(QObject):
        def __init__(self, w):
            super().__init__(w)
            self._w = w
        def eventFilter(self, obj, event):
            if obj is self._w and event.type() == QEvent.Type.Resize:
                relayout = getattr(self._w, "_grid_relayout", None)
                if callable(relayout):
                    QTimer.singleShot(0, relayout)
            return False
    icons_widget.installEventFilter(_IconsGridResizeFilter(icons_widget))
    collectibles_scroll_layout.addWidget(icons_widget)

    collectibles_list = QWidget()
    if for_panel:
        collectibles_list.setMinimumWidth(1)  # allow dock to shrink; list may clip
    collectibles_list_layout = QVBoxLayout(collectibles_list)
    collectibles_list_layout.setContentsMargins(0, 0, 0, 0)
    for cid in owned_list:
        c = shop_mod.get_collectible(cid)
        if not c:
            continue
        row = QHBoxLayout()
        pm = _pixmap(c["image"], 36)
        if pm:
            icon = QLabel()
            icon.setPixmap(pm)
            row.addWidget(icon)
        desc = c.get("name", cid)
        if c.get("effect_description"):
            desc += f"  — {c['effect_description']}"
        lbl = QLabel(desc)
        lbl.setToolTip(c.get("effect_description") or c.get("name", cid))
        row.addWidget(lbl)
        row.addStretch()
        collectibles_list_layout.addLayout(row)
    collectibles_scroll_layout.addWidget(collectibles_list)

    scroll = QScrollArea()
    scroll.setWidget(collectibles_scroll_content)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    if not for_panel:
        # Dialog: size the viewport to the icon row plus exactly _VISIBLE_ITEM_ROWS item rows, so it
        # opens showing whole items instead of clipping one mid-row. Measured from the real rows
        # rather than a fixed pixel count, so it stays right if icon or font sizes change.
        shown = min(_VISIBLE_ITEM_ROWS, collectibles_list_layout.count())
        if shown > 0:
            rows_h = sum(
                collectibles_list_layout.itemAt(i).sizeHint().height() for i in range(shown)
            ) + collectibles_list_layout.spacing() * (shown - 1)
            icons_h = icons_widget.sizeHint().height()
            if rows_h > 0 and icons_h > 0:
                scroll_max = icons_h + spacer + rows_h + 2 * scroll.frameWidth()
    scroll.setMaximumHeight(scroll_max)
    if for_panel:
        scroll.setMinimumWidth(1)  # allow dock to shrink
        scroll.setStyleSheet(
            "QScrollBar:vertical { width: 8px; border: none; border-radius: 4px; background: #2a2a2a; }"
            " QScrollBar::handle:vertical { min-height: 24px; border-radius: 4px; background: #555; }"
            " QScrollBar::handle:vertical:hover { background: #666; }"
            " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
    layout.addWidget(scroll)
    layout.addSpacing(spacer)

    options_row = QHBoxLayout()
    options_btn = QPushButton("Options")
    options_btn.setToolTip("Reset progress, difficulty, cheat (if admin.txt present)")
    if for_panel:
        options_btn.setMinimumWidth(1)
    options_btn.clicked.connect(lambda: show_options_dialog(parent_for_dialogs or parent, on_refresh))
    # Equal stretch so every button in this row ends up the same width, and no color override so
    # they all use the theme's default button text.
    options_row.addWidget(options_btn, 1)

    # Prestige button: only visible if we can prestige now (level >= 50)
    # or if we've prestiged at least once (have any prestige points).
    level_for_prestige, _, _ = xp.xp_progress_in_level(total_xp)
    can_prestige_now = prestige_mod.can_prestige(level_for_prestige)
    has_prestige = prestige_points_total > 0
    if can_prestige_now or has_prestige:
        prestige_btn = QPushButton("Prestige")
        if for_panel:
            prestige_btn.setMinimumWidth(1)
        prestige_btn.clicked.connect(lambda: show_prestige_dialog(parent_for_dialogs or parent, on_refresh))
        options_row.addWidget(prestige_btn, 1)

    # The dialog puts its Close button here so it sits beside Options rather than on its own row.
    # The dock panel passes nothing and keeps the row as-is.
    if close_button is not None:
        options_row.addWidget(close_button, 1)

    layout.addLayout(options_row)

    return root
