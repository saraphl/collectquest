"""Prestige dialogs: the star grid, the scene, and the prompts around them."""
from __future__ import annotations

import os
from typing import Callable
from aqt.qt import (
    QDialog,
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
from .. import dungeon as dungeon_mod, prestige as prestige_mod, shop as shop_mod, storage, xp
from .assets import (
    _pixmap_ui,
    exec_dialog,
    clear_layout,
    _review_dialog_icon,
    equalize_button_widths,
    gem_counts_row_widget,
    image_path,
    refit_dialog,
)
from .assets import last_house_level
from .constants import _DIALOG_BUTTON_MIN_WIDTH, _PRESTIGE_DIALOG_WIDTH

# Matches the star the CollectQuest panel puts in front of its own prestige line.
_PRESTIGE_STAR_PX = 18

def _add_prestige_summary_row(layout, prestige_count: int, available: int) -> None:
    """One star and the summary beside it, like the CollectQuest panel's row."""
    row = QHBoxLayout()
    if prestige_count > 0:
        star_pm = _pixmap_ui("Icon_Star_Grade_On.png", height=_PRESTIGE_STAR_PX)
        if not star_pm or star_pm.isNull():
            star_pm = _pixmap_ui("Star.png", height=_PRESTIGE_STAR_PX)
        if star_pm:
            star_lbl = QLabel()
            star_lbl.setPixmap(star_pm)
            row.addWidget(star_lbl)
    # Before the first prestige the count and the points are both necessarily zero, and a line of
    # zeroes is what every player meets on opening this window. It says so in words instead.
    if prestige_count <= 0:
        text = "No prestige yet"
    else:
        text = (
            f"Prestiged {prestige_count} time{'s' if prestige_count != 1 else ''}"
            f"  •  Available points: {available}"
        )
    summary = QLabel(text)
    summary.setStyleSheet("color: #888; font-size: 12px;")
    row.addWidget(summary)
    row.addStretch()
    layout.addLayout(row)


def _build_prestige_scene(parent: QWidget | None) -> QWidget:
    """Character scene for the prestige UI: BackGlow, Platform and the hero from images/characters/,
    stacked as overlapping child labels."""
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

# (key, title, effect per level, value per level, unit), in display order.
_UPGRADES = (
    ("xp_percent", "XP bonus", f"+{prestige_mod.UPGRADE_STEP_PERCENT}% XP",
     prestige_mod.UPGRADE_STEP_PERCENT, "%"),
    ("gold_percent", "Gold bonus", f"+{prestige_mod.UPGRADE_STEP_PERCENT}% gold",
     prestige_mod.UPGRADE_STEP_PERCENT, "%"),
    ("quest_reward", "Gem luck", f"+{prestige_mod.QUEST_REWARD_STEP_PERCENT}% gem luck",
     prestige_mod.QUEST_REWARD_STEP_PERCENT, "%"),
    ("start_gold", "Starting gold", f"+{prestige_mod.START_GOLD_PER_LEVEL} gold at start of each run",
     prestige_mod.START_GOLD_PER_LEVEL, "g"),
    ("streak_bonus", "Streak reward", "+100% 7-day streak rewards", 100, "%"),
)


def _add_upgrade_rows(layout, data: dict, on_change: Callable[[], None]) -> None:
    """The upgrade shop: one row per upgrade with its level, effect and Buy button."""
    available = prestige_mod.available_prestige_points(data)
    ups = data.get("prestige_upgrades") or {}

    def on_buy(key: str) -> None:
        if not prestige_mod.buy_upgrade(data, key):
            tooltip("Not enough prestige points.")
            return
        on_change()

    layout.addSpacing(8)
    layout.addWidget(QLabel("Prestige upgrades"))
    for key, title, desc, step, unit in _UPGRADES:
        level = int(ups.get(key, 0) or 0)
        row = QHBoxLayout()
        # Indented and unbolded, so the heading is the only thing above them that reads as one.
        row.addWidget(QLabel(f"  {title} — Lvl {level} · {level * step}{unit}"))
        row.addStretch()
        effect_lbl = QLabel(desc)
        effect_lbl.setStyleSheet("color: #888; font-size: 11px;")
        row.addWidget(effect_lbl)
        cost = prestige_mod.upgrade_cost(level)
        btn = QPushButton(f"Buy ({cost} pt)")
        btn.setEnabled(available >= cost)
        btn.clicked.connect(lambda _checked=False, k=key: on_buy(k))
        row.addWidget(btn)
        layout.addLayout(row)
    layout.addSpacing(8)


def _add_gem_trade_rows(layout, data: dict, on_change: Callable[[], None]) -> None:
    """The one-time gem trade for an extra point, above the shop's own gem counts row."""
    each = prestige_mod.GEM_TRADE_EACH
    pending_gem_pts = int(data.get("pending_prestige_points_from_gems", 0) or 0)
    gem_row = QHBoxLayout()
    gem_row.addWidget(QLabel(f"{each} of each gem → +1 extra prestige point (one-time only)"))
    if pending_gem_pts > 0:
        gem_row.addWidget(QLabel(f"  (+{pending_gem_pts} pending)"), 0, Qt.AlignmentFlag.AlignVCenter)
    gem_row.addStretch()
    layout.addLayout(gem_row)

    trade_btn = QPushButton(f"Trade ({each} each)")
    trade_btn.setEnabled(prestige_mod.can_trade_gems(data))

    def on_trade() -> None:
        if not prestige_mod.trade_gems_for_point(data):
            tooltip(f"Need {each} of each gem color.")
            return
        on_change()

    trade_btn.clicked.connect(on_trade)
    # Trade sits beside the gem counts rather than the line above, which is too long to share a row.
    gem_counts_row = QHBoxLayout()
    gem_counts_row.addWidget(gem_counts_row_widget(data.get("gems", shop_mod.default_gems())))
    gem_counts_row.addStretch()
    gem_counts_row.addWidget(trade_btn)
    layout.addLayout(gem_counts_row)
    layout.addSpacing(12)


def _points_preview(data: dict, level: int) -> tuple[int, str, list[str]]:
    """Current total, its headline, and the lines the total breaks down into."""
    level_pts = prestige_mod.prestige_points_gain(level)
    item_pts = prestige_mod.prestige_item_points(level, data.get("owned_collectibles") or [])
    gem_pts = int(data.get("pending_prestige_points_from_gems", 0) or 0)
    total = level_pts + item_pts + gem_pts
    plural = "" if total == 1 else "s"
    text = f"Prestiging now (level {level}) will grant {total} prestige point{plural}."
    parts = [f"{level_pts} from level"]
    if item_pts > 0:
        parts.append(f"{item_pts} from items")
    if gem_pts > 0:
        parts.append(f"{gem_pts} from gem trade" + ("" if gem_pts == 1 else "s"))
    return total, text, parts


def _add_points_info(layout, data: dict, level: int) -> None:
    """What prestiging now pays and how points are earned."""
    # Gated like the Prestige button, so "Prestiging now..." is never claimed while it isn't on offer.
    if prestige_mod.can_prestige(level):
        _, headline, parts = _points_preview(data, level)
        preview_lbl = QLabel(headline)
        preview_lbl.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
        layout.addWidget(preview_lbl)
        # Bullets off the headline, which they made too wide; nothing to break down with one part.
        if len(parts) >= 2:
            breakdown_lbl = QLabel("\n".join(f"•  {p}" for p in parts))
            breakdown_lbl.setStyleSheet("color: #888; font-size: 12px;")
            layout.addWidget(breakdown_lbl)

    # Omitted when standing exactly on a step, where "in 0 levels" would say nothing.
    to_next_point = prestige_mod.levels_to_next_point(level)
    if to_next_point > 0:
        next_point_lbl = QLabel(
            f"Next prestige point in {to_next_point} "
            + ("level" if to_next_point == 1 else "levels")
        )
        next_point_lbl.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(next_point_lbl)

    base_pts = prestige_mod.PRESTIGE_POINTS_AT_UNLOCK
    explain = QLabel(
        f"You gain {base_pts} prestige point{'' if base_pts == 1 else 's'} at level "
        f"{prestige_mod.PRESTIGE_MIN_LEVEL}, +1 per {prestige_mod.LEVELS_PER_EXTRA_POINT} "
        "levels above it.\nSome collectibles grant extra points on top."
    )
    explain.setWordWrap(True)
    explain.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(explain)


def _dungeon_warning() -> str:
    """A second line, only while there is a dungeon to lose. Informs rather than blocks."""
    data = storage.load()
    if not dungeon_mod.is_active(data):
        return ""
    if dungeon_mod.treasure_ready(data):
        return "\n\nA dungeon treasure is waiting to be claimed. Prestiging loses it."
    state = dungeon_mod.get_state(data) or {}
    done = int(state.get("branchings_done", 0))
    found = " and one unique item found" if dungeon_mod.item_taken(data) else ""
    return (
        f"\n\nA dungeon is in progress ({done} branching pathway"
        f"{'s' if done != 1 else ''} taken{found}). Prestiging abandons it."
    )


def _add_prestige_buttons(
    layout, d: QDialog, data: dict, level: int, on_prestiged: Callable[[], None]
) -> None:
    """Prestige now and Close, with Close holding focus and Enter since prestige wipes the run."""
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    prestige_btn = QPushButton("Prestige now")
    prestige_btn.setEnabled(prestige_mod.can_prestige(level))

    def on_prestige_now() -> None:
        if not prestige_mod.can_prestige(level):
            tooltip(f"Reach level {prestige_mod.PRESTIGE_MIN_LEVEL} to prestige.")
            return
        reply = QMessageBox.question(
            d.parentWidget() or d,
            "Prestige",
            f"Prestige will reset ALL progress (XP, level, gold, gems, collectibles, quests, "
            f"dungeons) and grant {_points_preview(data, level)[0]} prestige points."
            f"{_dungeon_warning()}\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from aqt import mw

        if not prestige_mod.perform_prestige(getattr(mw, "col", None), force=False):
            # A guard only: the button is enabled only when can_prestige() holds.
            tooltip("Prestige is not available right now.")
            return
        tooltip("Prestiged! Progress reset and prestige points granted.")
        on_prestiged()

    prestige_btn.clicked.connect(on_prestige_now)
    btn_row.addWidget(prestige_btn)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.reject)
    equalize_button_widths(prestige_btn, close_btn)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    # autoDefault off stops Qt moving the default back to Prestige.
    prestige_btn.setAutoDefault(False)
    close_btn.setDefault(True)

    def _focus_close() -> None:
        try:
            close_btn.setFocus()
        except RuntimeError:
            pass  # rebuilt or closed before the timer fired

    QTimer.singleShot(0, _focus_close)


def show_prestige_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None],
) -> None:
    """Prestige popup: star grid, upgrades, and 'Prestige again' button."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Prestige")
    outer = QVBoxLayout(d)
    outer.setContentsMargins(0, 0, 0, 0)
    content = QWidget(d)
    layout = QVBoxLayout(content)
    outer.addWidget(content)

    # Repopulated in place by rebuild(), never rebound, so the closures keep reading the current save.
    data = storage.load()

    def rebuild() -> None:
        """Re-read the save and redraw the contents in place, as the shop does."""
        data.clear()
        data.update(storage.load())
        clear_layout(layout)
        _build_content()
        QTimer.singleShot(0, lambda: refit_dialog(d))

    def save_and_rebuild() -> None:
        storage.save(data)
        on_refresh()
        rebuild()

    def on_prestiged() -> None:
        on_refresh()
        # Stays open: the points just granted are almost always spent right away.
        rebuild()

    def _build_content() -> None:
        prestige_count = int(data.get("prestige_count", 0) or 0)
        if prestige_count == 0 and int(data.get("prestige_points_total", 0) or 0) > 0:
            prestige_count = 1
        layout.addWidget(_build_prestige_scene(content))
        layout.addSpacing(4)
        _add_prestige_summary_row(layout, prestige_count, prestige_mod.available_prestige_points(data))
        _add_upgrade_rows(layout, data, save_and_rebuild)
        _add_gem_trade_rows(layout, data, save_and_rebuild)
        level, _, _ = xp.xp_progress_in_level(data.get("total_xp", 0))
        _add_points_info(layout, data, level)
        _add_prestige_buttons(layout, d, data, level, on_prestiged)

    rebuild()
    # Widened, not pinned: at its natural width the effect column presses against the upgrade titles.
    d.adjustSize()
    d.resize(max(_PRESTIGE_DIALOG_WIDTH, d.width()), d.height())
    exec_dialog(d)


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
    exec_dialog(d)
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
    exec_dialog(d)
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
