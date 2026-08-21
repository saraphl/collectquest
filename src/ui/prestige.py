"""Prestige dialogs: the star grid, the scene, and the prompts around them."""
from __future__ import annotations

import os
from typing import Callable
from aqt.qt import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import tooltip
from .. import prestige as prestige_mod, shop as shop_mod, storage, xp
from .assets import _pixmap, _pixmap_ui, _review_dialog_icon, image_path

def _build_prestige_star_grid(parent: QWidget, prestige_count: int) -> QWidget:
    """Star grid: one gold star (Icon_Star_Grade_On.png) per time prestiged. Left-aligned, spreads in rows of 6."""
    grid_inner = QWidget(parent)
    grid = QGridLayout(grid_inner)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(4)
    if prestige_count <= 0:
        lbl = QLabel("No prestige yet.")
        lbl.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(lbl, 0, 0)
        out = QWidget(parent)
        row = QHBoxLayout(out)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(grid_inner, 0, Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        return out
    star_pm = _pixmap_ui("Icon_Star_Grade_On.png", height=20)
    if not star_pm or star_pm.isNull():
        star_pm = _pixmap_ui("Star.png", height=20)
    max_icons = min(prestige_count, 30)
    cols = 6
    row_i = 0
    col = 0
    for i in range(max_icons):
        lbl = QLabel()
        if star_pm:
            lbl.setPixmap(star_pm)
        grid.addWidget(lbl, row_i, col)
        col += 1
        if col >= cols:
            col = 0
            row_i += 1
    if prestige_count > max_icons:
        more_lbl = QLabel(f"+{prestige_count - max_icons}")
        more_lbl.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(more_lbl, row_i, min(col, cols - 1))
    out = QWidget(parent)
    row = QHBoxLayout(out)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(grid_inner, 0, Qt.AlignmentFlag.AlignLeft)
    row.addStretch(1)
    return out

def _build_prestige_scene(parent: QWidget | None) -> QWidget:
    """Composite character/platform/background scene for prestige UI.

    We stack three PNGs from images/characters/ using child labels so they
    visually overlap:
    - Character_BackGlow (back)
    - Character_Platform (middle/back)
    - hero (front)
    """
    from aqt.qt import QPixmap

    bg_path = image_path(os.path.join("characters", "Character_BackGlow.png"))
    platform_path = image_path(os.path.join("characters", "Character_Platform.png"))
    char_path = image_path(os.path.join("characters", "hero.png"))

    has_any = any(os.path.isfile(p) for p in (bg_path, platform_path, char_path))
    if not has_any:
        # Fallback: reuse the scroll/letter icon from the review prompt if available.
        w = QWidget(parent)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        icon = _review_dialog_icon()
        if icon:
            layout.addWidget(icon)
        else:
            layout.addWidget(QLabel("Prestige"))
        return w

    # Base widget with fixed size; children are absolutely positioned.
    base = QWidget(parent)
    base.setFixedSize(260, 180)

    # Background glow
    if os.path.isfile(bg_path):
        bg_pm = QPixmap(bg_path)
        if not bg_pm.isNull():
            bg_pm = bg_pm.scaled(
                base.width(),
                base.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            bg_lbl = QLabel(base)
            bg_lbl.setPixmap(bg_pm)
            bg_lbl.resize(base.size())
            bg_lbl.move(0, 0)

    # Platform (back relative to character)
    if os.path.isfile(platform_path):
        plat_pm = QPixmap(platform_path)
        if not plat_pm.isNull():
            plat_pm = plat_pm.scaledToWidth(
                int(base.width() * 0.7),
                Qt.TransformationMode.SmoothTransformation,
            )
            plat_lbl = QLabel(base)
            plat_lbl.setPixmap(plat_pm)
            pw = plat_pm.width()
            ph = plat_pm.height()
            plat_lbl.resize(pw, ph)
            plat_lbl.move((base.width() - pw) // 2, base.height() - ph - 4)

    # Character (front)
    if os.path.isfile(char_path):
        char_pm = QPixmap(char_path)
        if not char_pm.isNull():
            char_pm = char_pm.scaled(
                int(base.width() * 0.55),
                int(base.height() * 0.9),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            char_lbl = QLabel(base)
            char_lbl.setPixmap(char_pm)
            cw = char_pm.width()
            ch = char_pm.height()
            char_lbl.resize(cw, ch)
            # Center horizontally, slightly above platform with a small extra upward offset.
            char_lbl.move((base.width() - cw) // 2, max(0, base.height() - ch - 24))

    # Wrap base into a container so layouts can center it easily.
    container = QWidget(parent)
    outer = QHBoxLayout(container)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addStretch()
    outer.addWidget(base)
    outer.addStretch()
    return container

def show_prestige_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None],
) -> None:
    """Prestige popup: star grid, upgrades, and 'Prestige again' button."""
    from ..hooks import perform_prestige as _perform_prestige

    data = storage.load()
    prestige_count = int(data.get("prestige_count", 0) or 0)
    total_points = int(data.get("prestige_points_total", 0) or 0)
    if prestige_count == 0 and total_points > 0:
        prestige_count = 1
    available = prestige_mod.available_prestige_points(data)
    ups = data.get("prestige_upgrades") or {}
    xp_level = int(ups.get("xp_percent", 0) or 0)
    gold_level = int(ups.get("gold_percent", 0) or 0)
    start_gold_level = int(ups.get("start_gold", 0) or 0)

    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Prestige")
    layout = QVBoxLayout(d)

    # Top: character scene + star grid (one star per time prestiged) + summary
    layout.addWidget(_build_prestige_scene(d))
    layout.addSpacing(4)
    layout.addWidget(_build_prestige_star_grid(d, prestige_count))
    summary = QLabel(
        f"Prestiged {prestige_count} time(s)  •  Available points: {available}"
    )
    summary.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(summary)

    def save_and_refresh_dialog() -> None:
        storage.save(data)
        on_refresh()
        d.accept()
        show_prestige_dialog(parent, on_refresh)

    def add_upgrade_row(
        key: str,
        title: str,
        desc: str,
        level: int,
        current_value: str,
    ) -> None:
        nonlocal available
        row = QHBoxLayout()
        left_lbl = QLabel(f"{title} — Lvl {level} · {current_value}")
        left_lbl.setStyleSheet("font-weight: bold;")
        row.addWidget(left_lbl)
        row.addStretch()
        effect_lbl = QLabel(desc)
        effect_lbl.setStyleSheet("color: #888; font-size: 11px;")
        row.addWidget(effect_lbl)
        cost = prestige_mod.upgrade_cost(level)
        btn = QPushButton(f"Buy ({cost} pt)")
        btn.setEnabled(available >= cost)

        def on_buy() -> None:
            nonlocal available
            if not prestige_mod.spend_prestige_points(data, cost):
                tooltip("Not enough prestige points.")
                return
            ups = data.get("prestige_upgrades") or {}
            ups[key] = int(ups.get(key, 0) or 0) + 1
            data["prestige_upgrades"] = ups
            if key == "start_gold":
                data["money"] = data.get("money", 0) + prestige_mod.START_GOLD_PER_LEVEL
            available = max(
                0,
                int(data.get("prestige_points_total", 0) or 0)
                - int(data.get("prestige_points_spent", 0) or 0),
            )
            save_and_refresh_dialog()

        btn.clicked.connect(on_buy)
        row.addWidget(btn)
        layout.addLayout(row)

    layout.addSpacing(8)
    layout.addWidget(QLabel("Prestige upgrades"))

    add_upgrade_row(
        "xp_percent",
        "Global XP",
        f"+{prestige_mod.UPGRADE_STEP_PERCENT}% XP globally",
        xp_level,
        f"{xp_level * prestige_mod.UPGRADE_STEP_PERCENT}%",
    )
    add_upgrade_row(
        "gold_percent",
        "Global gold",
        f"+{prestige_mod.UPGRADE_STEP_PERCENT}% gold globally",
        gold_level,
        f"{gold_level * prestige_mod.UPGRADE_STEP_PERCENT}%",
    )
    add_upgrade_row(
        "start_gold",
        "Starting gold",
        f"+{prestige_mod.START_GOLD_PER_LEVEL} gold at start of each run",
        start_gold_level,
        f"{start_gold_level * prestige_mod.START_GOLD_PER_LEVEL}g",
    )

    streak_level = int((data.get("prestige_upgrades") or {}).get("streak_bonus", 0) or 0)
    add_upgrade_row(
        "streak_bonus",
        "Streak reward",
        "Increase 7-day streak rewards by +100%",
        streak_level,
        f"{streak_level * 100}%",
    )
    quest_reward_level = int((data.get("prestige_upgrades") or {}).get("quest_reward", 0) or 0)
    add_upgrade_row(
        "quest_reward",
        "Gem luck",
        f"+{prestige_mod.QUEST_REWARD_STEP_PERCENT}% gem luck, on every gem roll",
        quest_reward_level,
        f"{quest_reward_level * prestige_mod.QUEST_REWARD_STEP_PERCENT}%",
    )

    layout.addSpacing(8)

    current_level, _, _ = xp.xp_progress_in_level(data.get("total_xp", 0))

    def points_preview() -> tuple[int, str]:
        """
        Current point breakdown and its label, read from `data` every call.

        Trading gems inside this dialog reloads `data`, so anything that quotes a total has to ask
        again rather than reuse a value captured when the window was built.
        """
        level_pts = prestige_mod.prestige_points_gain(current_level)
        item_pts = prestige_mod.prestige_item_points(
            current_level, data.get("owned_collectibles") or []
        )
        gem_pts = int(data.get("pending_prestige_points_from_gems", 0) or 0)
        total = level_pts + item_pts + gem_pts
        # Never "point(s)": the level payout starts at 2 and only climbs, so this is always plural.
        text = f"Prestiging now (level {current_level}) will grant {total} prestige points."
        # Only worth breaking down once something beyond the level payout contributes; a lone
        # "(2 from level)" would just restate the number in front of it.
        parts = [f"{level_pts} from level"]
        if item_pts > 0:
            parts.append(f"{item_pts} from items")
        if gem_pts > 0:
            # Unlike the level payout this really can be 1, so it pluralises rather than hedging.
            parts.append(f"{gem_pts} from gem trade" + ("" if gem_pts == 1 else "s"))
        if len(parts) > 1:
            text += " (" + ", ".join(parts) + ")"
        return total, text

    gems = data.get("gems", shop_mod.default_gems())
    gem_colors = [c for c, _ in shop_mod.GEM_COLORS]
    has_three_each = all((gems.get(c, 0) or 0) >= 3 for c in gem_colors)
    pending_gem_pts = int(data.get("pending_prestige_points_from_gems", 0) or 0)
    gem_row = QHBoxLayout()
    gem_row.addWidget(QLabel("3 of each gem → +1 prestige point at next prestige"))
    pending_gem_lbl = QLabel(f"  (+{pending_gem_pts} pending)" if pending_gem_pts > 0 else "")
    pending_gem_lbl.setVisible(pending_gem_pts > 0)
    gem_row.addWidget(pending_gem_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
    gem_row.addStretch()
    gem_convert_btn = QPushButton("Trade (3 each)")
    gem_convert_btn.setEnabled(has_three_each)
    gem_convert_btn.setToolTip("Spend 3 blue, 3 green, 3 pink, 3 purple, 3 yellow. You get +1 prestige point when you next prestige, not now.")
    gem_row.addWidget(gem_convert_btn)

    def on_gem_convert() -> None:
        g = data.get("gems", shop_mod.default_gems())
        if not all((g.get(c, 0) or 0) >= 3 for c in gem_colors):
            tooltip("Need 3 of each gem color.")
            return
        for c in gem_colors:
            g[c] = max(0, (g.get(c, 0) or 0) - 3)
        data["gems"] = g
        data["pending_prestige_points_from_gems"] = (data.get("pending_prestige_points_from_gems", 0) or 0) + 1
        storage.save(data)
        on_refresh()
        data.clear()
        data.update(storage.load())
        p = int(data.get("pending_prestige_points_from_gems", 0) or 0)
        pending_gem_lbl.setText(f"  (+{p} pending)" if p > 0 else "")
        pending_gem_lbl.setVisible(p > 0)
        has_three = all((data.get("gems", shop_mod.default_gems()).get(c, 0) or 0) >= 3 for c in gem_colors)
        gem_convert_btn.setEnabled(has_three)
        preview_lbl.setText(points_preview()[1])

    gem_convert_btn.clicked.connect(on_gem_convert)
    layout.addLayout(gem_row)
    # Gem icons + numbers (no duplicate text list), left-aligned
    gem_icons_row = QWidget()
    gem_icons_layout = QHBoxLayout(gem_icons_row)
    gem_icons_layout.setContentsMargins(0, 2, 0, 0)
    gem_icons_layout.setSpacing(2)
    for color, img_name in shop_mod.GEM_COLORS:
        cnt = gems.get(color, 0) or 0
        pm = _pixmap(img_name, 12)
        if pm:
            ico = QLabel()
            ico.setPixmap(pm)
            ico.setToolTip(f"{color.capitalize()}: {cnt}")
            gem_icons_layout.addWidget(ico, 0, Qt.AlignmentFlag.AlignVCenter)
        num_lbl = QLabel(str(cnt))
        num_lbl.setStyleSheet("color: #888; font-size: 10px; min-width: 10px;")
        num_lbl.setToolTip(f"{color.capitalize()}: {cnt}")
        gem_icons_layout.addWidget(num_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
    gem_icons_wrap = QWidget()
    gem_icons_wrap_row = QHBoxLayout(gem_icons_wrap)
    gem_icons_wrap_row.setContentsMargins(0, 0, 0, 0)
    gem_icons_wrap_row.addWidget(gem_icons_row, 0, Qt.AlignmentFlag.AlignLeft)
    gem_icons_wrap_row.addStretch(1)
    layout.addWidget(gem_icons_wrap)

    layout.addSpacing(12)

    # Bottom: Prestige again
    preview_lbl = QLabel(points_preview()[1])
    preview_lbl.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
    layout.addWidget(preview_lbl)

    # Omitted when the answer is 0, i.e. standing exactly on a step, where "in 0 levels" would say
    # nothing. Depends only on level, so unlike the line above it never needs refreshing.
    to_next_point = prestige_mod.levels_to_next_point(current_level)
    if to_next_point > 0:
        next_point_lbl = QLabel(
            f"Next prestige point in {to_next_point} "
            + ("level" if to_next_point == 1 else "levels")
        )
        next_point_lbl.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(next_point_lbl)

    # How prestige points are gained
    explain = QLabel(
        "You gain 2 prestige points at level 50,\n"
        "plus 1 extra point for every full 10 levels above 50.\n"
        "Some collectibles grant extra points on top."
    )
    explain.setWordWrap(True)
    explain.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(explain)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    prestige_btn = QPushButton("Prestige now")
    prestige_btn.setEnabled(prestige_mod.can_prestige(current_level))

    def on_prestige_now() -> None:
        if not prestige_mod.can_prestige(current_level):
            tooltip("Reach level 50 to prestige.")
            return
        reply = QMessageBox.question(
            parent or d,
            "Prestige",
            f"Prestige will reset ALL progress (XP, level, gold, gems, collectibles, quests, streak) "
            f"and grant {points_preview()[0]} prestige points.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if not _perform_prestige(force=False):
            # Not reachable as things stand, and kept as a guard rather than a message the player is
            # expected to see. False means perform_prestige recomputed the level and found no points
            # to award, but this button is only enabled when can_prestige() holds, both read the
            # same total_xp, and the dialog is modal so nothing can move it in between. It cannot
            # mean cancelled — declining the confirmation above returns silently — nor failed, since
            # an error would raise rather than return. It fires only if the button's gate and
            # perform_prestige's own test ever drift apart, so it says what happened, not why.
            tooltip("Prestige is not available right now.")
            return
        tooltip("Prestiged! Progress reset and prestige points granted.")
        on_refresh()
        d.accept()

    prestige_btn.clicked.connect(on_prestige_now)
    btn_row.addWidget(prestige_btn)
    layout.addLayout(btn_row)

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.reject)
    layout.addWidget(close_btn)

    d.exec()

def maybe_show_prestige_prompt(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Show a one-time popup when prestige unlocks (first time reaching level 50+)."""
    data = storage.load()
    if data.get("prestige_unlock_prompt_shown"):
        return
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    # Only trigger when we newly reach the prestige threshold.
    from ..prestige import PRESTIGE_MIN_LEVEL

    if level < PRESTIGE_MIN_LEVEL:
        return

    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Prestige unlocked")
    layout = QVBoxLayout(d)
    layout.setSpacing(10)

    layout.addWidget(_build_prestige_scene(d))

    title = QLabel("Prestige unlocked!")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    layout.addWidget(title)

    msg = QLabel(
        "You reached a high level run.\n"
        "You can now Prestige: reset all progress to earn prestige points\n"
        "and buy permanent XP and gold bonuses for future runs."
    )
    msg.setWordWrap(True)
    msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
    msg.setStyleSheet("font-size: 12px;")
    layout.addWidget(msg)

    close_btn = QPushButton("Got it")
    close_btn.clicked.connect(d.accept)
    layout.addWidget(close_btn)

    d.setMinimumWidth(380)
    d.exec()

    data = storage.load()
    data["prestige_unlock_prompt_shown"] = True
    storage.save(data)
    if on_refresh:
        on_refresh()

LAST_HOUSE_LEVEL = 153

def show_game_finished_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
    force: bool = False,
) -> None:
    """Panel shown when reaching last house level (153). Hero + scroll style; review link and Ko-fi button. force=True for admin debug (no flag set)."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Game finished")
    layout = QVBoxLayout(d)
    layout.setSpacing(12)

    layout.addWidget(_build_prestige_scene(d))

    title = QLabel("Congratulations ! You reached the last house")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    layout.addWidget(title)

    thanks = QLabel("Thank you for playing CollectQuest")
    thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
    thanks.setStyleSheet("font-size: 13px;")
    layout.addWidget(thanks)

    msg = QLabel(
        "You can keep prestiging and grinding more levels if you like, "
        "but you've seen about all of the content by now."
    )
    msg.setWordWrap(True)
    msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
    msg.setStyleSheet("font-size: 12px;")
    layout.addWidget(msg)

    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(d.accept)
    layout.addWidget(ok_btn)

    d.setMinimumWidth(400)
    d.exec()

    if not force:
        data = storage.load()
        data["game_finished_prompt_shown"] = True
        storage.save(data)
        if on_refresh:
            on_refresh()

def maybe_show_game_finished_prompt(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Show the game-finished panel once when the player reaches the last house level (153)."""
    data = storage.load()
    if data.get("game_finished_prompt_shown"):
        return
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    if level < LAST_HOUSE_LEVEL:
        return
    show_game_finished_dialog(parent, on_refresh, force=False)
