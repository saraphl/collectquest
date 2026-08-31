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
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import tooltip
from .. import prestige as prestige_mod, shop as shop_mod, storage, xp
from .assets import (
    _pixmap_ui,
    clear_layout,
    _review_dialog_icon,
    equalize_button_widths,
    gem_counts_row_widget,
    image_path,
    refit_dialog_height,
)
from .assets import last_house_level
from .constants import _DIALOG_BUTTON_MIN_WIDTH

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

    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Prestige")
    outer = QVBoxLayout(d)
    outer.setContentsMargins(0, 0, 0, 0)
    content = QWidget(d)
    layout = QVBoxLayout(content)
    outer.addWidget(content)

    # Repopulated in place by rebuild(), never rebound, so the closures below keep reading the
    # current save rather than a copy taken when the window opened.
    data = storage.load()

    def rebuild() -> None:
        """Re-read the save and redraw the contents in place.

        Buying an upgrade used to accept() the dialog and open a fresh one, which read as the
        window collapsing and reappearing. This is the shop's mechanism instead: the same window
        stays put and only its contents are replaced.
        """
        data.clear()
        data.update(storage.load())
        clear_layout(layout)
        _build_content()
        QTimer.singleShot(0, lambda: refit_dialog_height(d))

    def _build_content() -> None:
        prestige_count = int(data.get("prestige_count", 0) or 0)
        total_points = int(data.get("prestige_points_total", 0) or 0)
        if prestige_count == 0 and total_points > 0:
            prestige_count = 1
        available = prestige_mod.available_prestige_points(data)
        ups = data.get("prestige_upgrades") or {}
        xp_level = int(ups.get("xp_percent", 0) or 0)
        gold_level = int(ups.get("gold_percent", 0) or 0)
        start_gold_level = int(ups.get("start_gold", 0) or 0)

        # Top: character scene + star grid (one star per time prestiged) + summary
        layout.addWidget(_build_prestige_scene(content))
        layout.addSpacing(4)
        layout.addWidget(_build_prestige_star_grid(content, prestige_count))
        summary = QLabel(
            f"Prestiged {prestige_count} time{'s' if prestige_count != 1 else ''}"
            f"  •  Available points: {available}"
        )
        summary.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(summary)

        def save_and_rebuild() -> None:
            storage.save(data)
            on_refresh()
            rebuild()

        def add_upgrade_row(
            key: str,
            title: str,
            desc: str,
            level: int,
            current_value: str,
        ) -> None:
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
                if not prestige_mod.spend_prestige_points(data, cost):
                    tooltip("Not enough prestige points.")
                    return
                ups = data.get("prestige_upgrades") or {}
                ups[key] = int(ups.get(key, 0) or 0) + 1
                data["prestige_upgrades"] = ups
                if key == "start_gold":
                    data["money"] = data.get("money", 0) + prestige_mod.START_GOLD_PER_LEVEL
                save_and_rebuild()

            btn.clicked.connect(on_buy)
            row.addWidget(btn)
            layout.addLayout(row)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Prestige upgrades"))

        add_upgrade_row(
            "xp_percent",
            "XP bonus",
            f"+{prestige_mod.UPGRADE_STEP_PERCENT}% XP",
            xp_level,
            f"{xp_level * prestige_mod.UPGRADE_STEP_PERCENT}%",
        )
        add_upgrade_row(
            "gold_percent",
            "Gold bonus",
            f"+{prestige_mod.UPGRADE_STEP_PERCENT}% gold",
            gold_level,
            f"{gold_level * prestige_mod.UPGRADE_STEP_PERCENT}%",
        )
        quest_reward_level = int(ups.get("quest_reward", 0) or 0)
        add_upgrade_row(
            "quest_reward",
            "Gem luck",
            f"+{prestige_mod.QUEST_REWARD_STEP_PERCENT}% gem luck",
            quest_reward_level,
            f"{quest_reward_level * prestige_mod.QUEST_REWARD_STEP_PERCENT}%",
        )
        add_upgrade_row(
            "start_gold",
            "Starting gold",
            f"+{prestige_mod.START_GOLD_PER_LEVEL} gold at start of each run",
            start_gold_level,
            f"{start_gold_level * prestige_mod.START_GOLD_PER_LEVEL}g",
        )

        streak_level = int(ups.get("streak_bonus", 0) or 0)
        add_upgrade_row(
            "streak_bonus",
            "Streak reward",
            "+100% 7-day streak rewards",
            streak_level,
            f"{streak_level * 100}%",
        )

        layout.addSpacing(8)

        current_level, _, _ = xp.xp_progress_in_level(data.get("total_xp", 0))

        def points_preview() -> tuple[int, str, list[str]]:
            """Current total, its headline, and the lines the total breaks down into."""
            level_pts = prestige_mod.prestige_points_gain(current_level)
            item_pts = prestige_mod.prestige_item_points(
                current_level, data.get("owned_collectibles") or []
            )
            gem_pts = int(data.get("pending_prestige_points_from_gems", 0) or 0)
            total = level_pts + item_pts + gem_pts
            plural = "" if total == 1 else "s"
            text = f"Prestiging now (level {current_level}) will grant {total} prestige point{plural}."
            parts = [f"{level_pts} from level"]
            if item_pts > 0:
                parts.append(f"{item_pts} from items")
            if gem_pts > 0:
                # Unlike the level payout this really can be 1, so it pluralizes rather than hedging.
                parts.append(f"{gem_pts} from gem trade" + ("" if gem_pts == 1 else "s"))
            return total, text, parts

        def breakdown_text(parts: list[str]) -> str:
            """The parts as bullets, or "" when there is nothing to break down.

            Kept off the headline: as one parenthetical it set the dialog's width on its own, and a
            lone "2 from level" would only restate the number in front of it.
            """
            return "" if len(parts) < 2 else "\n".join(f"•  {p}" for p in parts)

        gems = data.get("gems", shop_mod.default_gems())
        gem_colors = [c for c, _ in shop_mod.GEM_COLORS]
        has_three_each = all((gems.get(c, 0) or 0) >= 3 for c in gem_colors)
        pending_gem_pts = int(data.get("pending_prestige_points_from_gems", 0) or 0)
        gem_row = QHBoxLayout()
        gem_row.addWidget(QLabel("3 of each gem → +1 extra prestige point (one-time only)"))
        if pending_gem_pts > 0:
            pending_gem_lbl = QLabel(f"  (+{pending_gem_pts} pending)")
            gem_row.addWidget(pending_gem_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        gem_row.addStretch()
        gem_convert_btn = QPushButton("Trade (3 each)")
        gem_convert_btn.setEnabled(has_three_each)
        gem_convert_btn.setToolTip("Spend 3 blue, 3 green, 3 pink, 3 purple, 3 yellow.")

        def on_gem_convert() -> None:
            g = data.get("gems", shop_mod.default_gems())
            if not all((g.get(c, 0) or 0) >= 3 for c in gem_colors):
                tooltip("Need 3 of each gem color.")
                return
            for c in gem_colors:
                g[c] = max(0, (g.get(c, 0) or 0) - 3)
            data["gems"] = g
            data["pending_prestige_points_from_gems"] = (data.get("pending_prestige_points_from_gems", 0) or 0) + 1
            save_and_rebuild()

        gem_convert_btn.clicked.connect(on_gem_convert)
        layout.addLayout(gem_row)
        # The shop's own row, not a copy of it, so both windows count gems the same way. Trade sits
        # beside it rather than beside the line above, which is now too long to share a row.
        gem_counts_row = QHBoxLayout()
        gem_counts_row.addWidget(gem_counts_row_widget(gems))
        gem_counts_row.addStretch()
        gem_counts_row.addWidget(gem_convert_btn)
        layout.addLayout(gem_counts_row)

        layout.addSpacing(12)

        # Bottom: Prestige again. The preview is gated on the same test as the button below, so
        # "Prestiging now..." is never claimed while prestiging is not actually on offer.
        _, headline, parts = points_preview()
        if prestige_mod.can_prestige(current_level):
            preview_lbl = QLabel(headline)
            preview_lbl.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
            layout.addWidget(preview_lbl)
            breakdown = breakdown_text(parts)
            if breakdown:
                breakdown_lbl = QLabel(breakdown)
                breakdown_lbl.setStyleSheet("color: #888; font-size: 12px;")
                layout.addWidget(breakdown_lbl)

        # Omitted when the answer is 0, i.e. standing exactly on a step, where "in 0 levels" would
        # say nothing.
        to_next_point = prestige_mod.levels_to_next_point(current_level)
        if to_next_point > 0:
            next_point_lbl = QLabel(
                f"Next prestige point in {to_next_point} "
                + ("level" if to_next_point == 1 else "levels")
            )
            next_point_lbl.setStyleSheet("color: #888; font-size: 12px;")
            layout.addWidget(next_point_lbl)

        # How prestige points are gained
        _base_pts = prestige_mod.PRESTIGE_POINTS_AT_UNLOCK
        explain = QLabel(
            f"You gain {_base_pts} prestige point{'' if _base_pts == 1 else 's'} at level "
            f"{prestige_mod.PRESTIGE_MIN_LEVEL}, +1 per {prestige_mod.LEVELS_PER_EXTRA_POINT} "
            "levels above it.\nSome collectibles grant extra points on top."
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
                tooltip(f"Reach level {prestige_mod.PRESTIGE_MIN_LEVEL} to prestige.")
                return
            reply = QMessageBox.question(
                parent or d,
                "Prestige",
                f"Prestige will reset ALL progress (XP, level, gold, gems, collectibles, quests) "
                f"and grant {points_preview()[0]} prestige points.\n\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if not _perform_prestige(force=False):
                # A guard, not a message the player should ever see: the button is only enabled when
                # can_prestige() holds, so this fires only if that gate and perform_prestige's own
                # test drift apart.
                tooltip("Prestige is not available right now.")
                return
            tooltip("Prestiged! Progress reset and prestige points granted.")
            on_refresh()
            # The window stays open: the points just granted are almost always spent right away, and
            # closing it only to be reopened put a needless step in front of that.
            rebuild()

        prestige_btn.clicked.connect(on_prestige_now)
        btn_row.addWidget(prestige_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(d.reject)
        equalize_button_widths(prestige_btn, close_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Close takes the focus and the Enter key: prestige wipes the run, so the button that does
        # nothing is the safe one to arrive pre-selected. autoDefault off on the other one stops Qt
        # handing the default ring back to the first button in the dialog.
        prestige_btn.setAutoDefault(False)
        close_btn.setDefault(True)
        def _focus_close() -> None:
            try:
                close_btn.setFocus()
            except RuntimeError:
                pass  # rebuilt or closed before the timer fired

        QTimer.singleShot(0, _focus_close)

    rebuild()
    d.exec()

def maybe_show_prestige_prompt(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Show a one-time popup the first time the player reaches the prestige unlock level."""
    data = storage.load()
    if data.get("prestige_unlock_prompt_shown"):
        return
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    # Only trigger when we newly reach the prestige threshold.
    if level < prestige_mod.PRESTIGE_MIN_LEVEL:
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
        f"Prestige unlocks at level {prestige_mod.PRESTIGE_MIN_LEVEL}, and you're there.\n"
        "A prestige resets your run and pays prestige points,\n"
        "which buy permanent upgrades: XP, gold, gem luck,\n"
        "starting gold and streak rewards.\n"
        "\n"
        "Open it from the Prestige button\n"
        "in the CollectQuest window."
    )
    msg.setWordWrap(True)
    msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
    msg.setStyleSheet("font-size: 12px;")
    layout.addWidget(msg)

    # Right-aligned and sized to its text, like every other window's button row.
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    close_btn = QPushButton("Got it")
    close_btn.clicked.connect(d.accept)
    close_btn.setFixedWidth(max(close_btn.sizeHint().width(), _DIALOG_BUTTON_MIN_WIDTH))
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    d.adjustSize()
    d.exec()

    data = storage.load()
    data["prestige_unlock_prompt_shown"] = True
    storage.save(data)
    if on_refresh:
        on_refresh()

def show_game_finished_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
    force: bool = False,
) -> None:
    """Panel shown when reaching the last house's level. force=True for admin debug (no flag set)."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Game finished")
    layout = QVBoxLayout(d)
    layout.setSpacing(12)

    layout.addWidget(_build_prestige_scene(d))

    title = QLabel("Congratulations! Your house is now fully expanded!")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    layout.addWidget(title)

    thanks = QLabel("Thank you for playing CollectQuest!")
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

    # Right-aligned and sized to its text, like every other window's button row.
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(d.accept)
    ok_btn.setFixedWidth(max(ok_btn.sizeHint().width(), _DIALOG_BUTTON_MIN_WIDTH))
    btn_row.addWidget(ok_btn)
    layout.addLayout(btn_row)

    d.adjustSize()
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
    """Show the game-finished panel once when the player reaches the last house's level."""
    data = storage.load()
    if data.get("game_finished_prompt_shown"):
        return
    last_level = last_house_level()
    if last_level is None:
        return  # no house art installed, so no last house to congratulate anyone for
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    if level < last_level:
        return
    show_game_finished_dialog(parent, on_refresh, force=False)
