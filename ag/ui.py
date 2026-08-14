"""CollectQuest UI: status bar (level, gold, gems, shop), progress dialog, shop dialog. All custom Qt UI (no card hack)."""
from __future__ import annotations

import json
import os
import random
from typing import Callable

from aqt.qt import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QDesktopServices,
    QDialog,
    QDockWidget,
    QEvent,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QObject,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSize,
    QSizePolicy,
    QTimer,
    QUrl,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import showInfo, tooltip

from . import prestige as prestige_mod, quests, review_rewards, revlog_sync, storage, shop as shop_mod, streak as streak_mod, xp
from .options_dialog import show_options_dialog


def addon_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _admin_enabled() -> bool:
    """True if an empty txt named 'admin' exists at add-on root (admin.txt)."""
    path = os.path.join(addon_dir(), "admin.txt")
    return os.path.isfile(path)


def image_path(filename: str) -> str:
    return os.path.join(addon_dir(), "images", filename)


def _pixmap(filename: str, size: int = 32):
    """Load image as QPixmap scaled to size, or None if missing."""
    path = image_path(filename)
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        return QPixmap(path).scaled(size, size)
    except Exception:
        return None


def _pixmap_ui(filename: str, height: int = 36):
    """Load image from images/ui/ scaled to height (width auto), for UI buttons."""
    path = image_path(os.path.join("ui", filename))
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        px = QPixmap(path)
        if px.isNull():
            return None
        return px.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


def _house_level_threshold(image_index: int) -> int:
    """Level at which this house image unlocks. Image 1 at level 1, 2 at 3, 3 at 6, 4 at 10, 5 at 15, ... (n(n+1)/2)."""
    return image_index * (image_index + 1) // 2


def house_index_for_level(level: int) -> int:
    """Largest house image index unlocked at this level (1-based)."""
    # n(n+1)/2 <= level  =>  n^2 + n - 2*level <= 0  =>  n <= (-1 + sqrt(1+8*level))/2
    if level < 1:
        return 0
    n = int(((-1 + (1 + 8 * level) ** 0.5) / 2))
    return max(0, n)


def next_house_goal_level(level: int) -> int | None:
    """Level required for the next house image, or None if at max."""
    idx = house_index_for_level(level)
    next_level = _house_level_threshold(idx + 1)
    return next_level  # same as current threshold means we're at max; caller can hide "next" then


def _house_pixmap(image_index: int, width: int = 360) -> "QPixmap | None":
    """Load house/N.png scaled by width, preserving the image's aspect ratio.

    The image is uniformly rescaled to the requested width; height is derived from
    the original aspect ratio (no squashing or stretching)."""
    path = image_path(os.path.join("house", f"{image_index}.png"))
    if not os.path.isfile(path):
        return None
    try:
        from aqt.qt import QPixmap
        pm = QPixmap(path)
        if pm.isNull():
            return None
        # Uniformly scale to the requested width while keeping the original aspect ratio.
        return pm.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


def _label_with_pixmap(pixmap, text_label: QLabel) -> QWidget:
    """Row: icon + text label, vertically centered."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(2)
    icon = QLabel()
    icon.setPixmap(pixmap)
    row.addWidget(icon)
    row.addWidget(text_label)
    row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return w


# Streak square colors: filled = blue (validated day); unfilled = dark gray, no light outline
_STREAK_FILLED_COLOR = "#2563eb"
_STREAK_EMPTY_COLOR = "#5c5c5c"


def _streak_gift_image_for_type(reward_type: str) -> str:
    """Gift image path for streak reward type (xp=blue, gem=pink, gold=yellow). Call only when type is set."""
    return _STREAK_GIFT_IMAGES.get(reward_type, _STREAK_GIFT_IMAGES["xp"])


def _streak_squares_widget(streak_days: int, size: int = 12, reward_type: str | None = None) -> QWidget:
    """7 squares + optional gift icon. When reward_type is None (e.g. after claim until next week), show no icon."""
    from . import streak as streak_mod
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(2)
    for i in range(streak_mod.STREAK_LENGTH):
        box = QFrame()
        box.setFixedSize(size, size)
        bg = _STREAK_FILLED_COLOR if i < streak_days else _STREAK_EMPTY_COLOR
        box.setStyleSheet(
            "QFrame { background-color: %s; border: none; border-radius: 1px; }" % bg
        )
        row.addWidget(box)
    if reward_type is not None:
        gift_img = _streak_gift_image_for_type(reward_type)
        gift_pm = _pixmap(gift_img, size)
        if gift_pm:
            gift_lbl = QLabel()
            gift_lbl.setPixmap(gift_pm)
            gift_lbl.setToolTip("7-day streak reward")
            row.addWidget(gift_lbl)
    w.setToolTip(f"Streak: {streak_days}/7 days. Study every day for a reward!")
    return w


def _streak_display_filled(data: dict) -> int:
    """Fallback from stored display streak state only (never reviews_today)."""
    start = int(data.get("current_streak_start_date") or 0)
    end = int(data.get("current_streak_end_date") or 0)
    if start <= 0:
        return 0
    if end < start:
        return 0
    current_days = ((end - start) // 86400) + 1
    return ((current_days - 1) % 7) + 1 if current_days > 0 else 0


def build_streak_widget(streak_count: int | None = None) -> QWidget:
    """Build status bar widget: 7-day streak only. streak_count from streak.refresh_streak (revlog-based)."""
    data = storage.load()
    filled = streak_count if streak_count is not None else _streak_display_filled(data)
    reward_type = data.get("streak_reward_type")  # None until next week starts → show no icon
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(8, 0, 4, 0)
    row.setSpacing(0)
    row.addWidget(_streak_squares_widget(filled, size=10, reward_type=reward_type))
    return w


def build_xp_bar_widget(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    include_streak: bool = False,
) -> QWidget:
    """Build status bar widget: level, XP bar, gold, gems, [optional streak], Shop button, CollectQuest button.
    Visibility of streak/level-xp/gold-gems/quests and button order follow storage bottom_ui_* options."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(6, 0, 6, 0)  # equal margins so the row centres; right one also keeps
    # the last button (CollectQuest) from being truncated
    layout.setSpacing(4)

    data = storage.load()
    show_level_xp = data.get("bottom_ui_show_level_xp", True)
    show_gold_gems = data.get("bottom_ui_show_gold_gems", True)
    show_quests = data.get("bottom_ui_show_quests", True)
    invert_buttons = data.get("bottom_ui_invert_buttons", False)

    total_xp = data.get("total_xp", 0)
    lev, xp_in, xp_needed = xp.xp_progress_in_level(total_xp)
    money = data.get("money", 0)
    gems = data.get("gems", shop_mod.default_gems())
    reviews_today = data.get("reviews_today", 0)
    shop_enabled = reviews_today >= shop_mod.SHOP_MIN_REVIEWS

    layout.addStretch(1)
    if include_streak:
        layout.addWidget(_streak_squares_widget(
            _streak_display_filled(data), size=10,
            reward_type=data.get("streak_reward_type")
        ))
        layout.addSpacing(6)

    if show_level_xp:
        level_label = QLabel(f"Lv {lev}")
        level_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(level_label)
        bar = QProgressBar()
        bar.setFixedHeight(16)
        bar.setMaximumWidth(100)
        bar.setMinimum(0)
        bar.setMaximum(max(1, xp_needed))
        bar.setValue(xp_in)
        bar.setTextVisible(True)
        bar.setFormat(f"{xp_in}/{xp_needed}")
        bar.setStyleSheet(
            "QProgressBar { border: none; background: #3d3d3d; border-radius: 2px; text-align: center; color: #eee; }"
            " QProgressBar::chunk { background: #4a90d9; border-radius: 2px; }"
        )
        layout.addWidget(bar)
        layout.addSpacing(6)

    align_v = Qt.AlignmentFlag.AlignVCenter
    if show_gold_gems:
        coin_pm = _pixmap("currency/Coin x1.png", 18)
        if coin_pm:
            gold_icon = QLabel()
            gold_icon.setPixmap(coin_pm)
            layout.addWidget(gold_icon, 0, align_v)
        layout.addWidget(QLabel(f"{money}"), 0, align_v)
        layout.addSpacing(2)
        gems_row = QWidget()
        # gems_row.setMinimumWidth(30)  # 5 gem cols: icon + count each
        gems_layout = QHBoxLayout(gems_row)
        gems_layout.setContentsMargins(0, 0, 0, 0)
        gems_layout.setSpacing(1)
        gems_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        for _color, img_name in shop_mod.GEM_COLORS:
            cnt = gems.get(_color, 0)
            pm = _pixmap(img_name, 12)
            if pm:
                gicon = QLabel()
                gicon.setPixmap(pm)
                gems_layout.addWidget(gicon, 0, align_v)
            gems_layout.addWidget(QLabel(str(cnt)), 0, align_v)
        layout.addWidget(gems_row, 0, align_v)
        layout.addSpacing(8)
        # if show_quests:
            # # Small gap so "Q: …" never overlaps gems when layout is tight
            # _gap = QWidget()
            # _gap.setFixedWidth(8)
            # layout.addWidget(_gap, 0, align_v)

    if show_quests:
        daily_quests = data.get("daily_quests", [])
        if daily_quests:
            parts = [f"{q.get('progress', 0)}/{q.get('target', 0)}" for q in daily_quests]
            quest_text = " • ".join(parts)
            quest_tooltip = "Daily quests:\n" + "\n".join(
                f"  {q.get('label', '?')}: {q.get('progress', 0)}/{q.get('target', 0)}"
                for q in daily_quests
            )
            quest_lbl = QLabel(f"Q: {quest_text}")
            quest_lbl.setStyleSheet("color: #555; font-size: 11px;")
            quest_lbl.setToolTip(quest_tooltip)
            quest_lbl.setMinimumWidth(60)
            layout.addWidget(quest_lbl)
            layout.addSpacing(6)

    # Shop: small padding; CollectQuest: no inner padding (stylesheet + no icon area so text isn't truncated).
    _shop_style = "QPushButton { padding: 1px 4px; margin: 0; font-size: 11px; min-width: 44px; max-width: 50px }"
    _cq_style = "QPushButton { padding: 1px 2px; margin: 0; font-size: 11px; min-width: 80px; max-width: 110px; border: none; }"
    shop_btn = QPushButton("Shop")
    shop_btn.setFlat(True)
    shop_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    shop_btn.setEnabled(True)
    # No explicit colour when unlocked: the button then inherits the theme's default text colour,
    # matching the "Lv N" label beside it in both light and dark mode. Locked stays dimmed, because
    # that greying is what signals the shop is not open yet.
    _shop_enabled_style = _shop_style + " QPushButton { font-weight: bold; } QPushButton:hover { text-decoration: underline; }"
    _shop_locked_style = _shop_style + " QPushButton { color: #666; } QPushButton:hover { text-decoration: underline; }"
    shop_btn.setStyleSheet(_shop_enabled_style if shop_enabled else _shop_locked_style)
    shop_btn.setToolTip("Open shop (unlocked after 10 reviews today)" if shop_enabled else f"Click to see when shop unlocks — {reviews_today}/{shop_mod.SHOP_MIN_REVIEWS} reviews today")
    shop_btn.clicked.connect(on_shop_click)
    cq_btn = QPushButton("CollectQuest")
    cq_btn.setFlat(True)
    cq_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    cq_btn.setStyleSheet(_cq_style + " QPushButton { font-weight: bold; } QPushButton:hover { text-decoration: underline; }")
    cq_btn.clicked.connect(on_progress_click)
    if invert_buttons:
        layout.addWidget(cq_btn)
        layout.addWidget(shop_btn)
    else:
        layout.addWidget(shop_btn)
        layout.addWidget(cq_btn)

    layout.addStretch(1)
    widget.setMinimumWidth(_bottom_ui_block_min_width())
    return widget


def build_centered_xp_bar_widget(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    main_window: QWidget | None = None,
) -> QWidget:
    """Build the bottomUI block (level, XP, gold, gems, buttons). If main_window is given, set a minimum width
    so it doesn't squish. Used by build_bottom_ui_block or when no streak is needed."""
    bar_widget = build_xp_bar_widget(on_progress_click, on_shop_click, include_streak=False)
    return bar_widget


_STREAK_GAP = 8  # space between the streak squares and the centred group


def build_simple_centered_xp_bar_widget(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    streak_widget: QWidget | None = None,
) -> QWidget:
    """
    Centered bar for simple (non-dock) mode:

        [grip pad][streak][gap][stretch][bar][stretch][mirror pad]

    The streak sits at the far left but must not drag the bar off-centre with it, so an equal-width
    mirror pad is reserved on the right. Both pads are sized by update_simple_bar_centering() once
    real geometry exists.
    """
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    # QStatusBar keeps its size grip outside the area addWidget() lays out in, so stretches alone
    # centre the bar within that shortened area — about half a grip-width left of the window centre
    # (measured at -12px). This pad restores the balance; the reserve is style-dependent, so it is
    # measured rather than hardcoded.
    grip_pad = QWidget()
    grip_pad.setFixedWidth(0)
    row.addWidget(grip_pad)
    if streak_widget is not None:
        row.addWidget(streak_widget)
        row.addSpacing(_STREAK_GAP)
    row.addStretch()
    bar = build_xp_bar_widget(on_progress_click, on_shop_click, include_streak=False)
    row.addWidget(bar)
    row.addStretch()
    mirror_pad = QWidget()
    mirror_pad.setFixedWidth(0)
    row.addWidget(mirror_pad)
    wrapper._collectquest_center_pad = grip_pad
    wrapper._collectquest_mirror_pad = mirror_pad
    wrapper._collectquest_streak = streak_widget
    wrapper._collectquest_bar = bar
    return wrapper


def update_simple_bar_centering(status_bar: QWidget, wrapper: QWidget) -> None:
    """
    Keep the bar centred on the window: compensate for the status bar's right-hand size-grip
    reserve, and mirror the streak block so it does not push the bar right.

    The mirror is dropped when the window is too narrow to afford it, so a cramped window spends its
    width on content rather than on balance — the bar shifts right, which is the sensible fallback.

    Idempotent: it reads the wrapper's geometry, which the pads do not change, so repeated calls
    (on every window resize) settle on the same widths instead of drifting.
    """
    grip_pad = getattr(wrapper, "_collectquest_center_pad", None)
    mirror_pad = getattr(wrapper, "_collectquest_mirror_pad", None)
    if grip_pad is None or mirror_pad is None:
        return
    try:
        left_gap = wrapper.x()
        right_gap = status_bar.width() - (wrapper.x() + wrapper.width())
        grip_pad.setFixedWidth(max(0, right_gap - left_gap))

        streak = getattr(wrapper, "_collectquest_streak", None)
        bar = getattr(wrapper, "_collectquest_bar", None)
        streak_block = (streak.width() + _STREAK_GAP) if streak is not None else 0
        if streak_block:
            bar_w = bar.minimumWidth() if bar is not None else 0
            room = wrapper.width() - grip_pad.width() - streak_block - bar_w
            streak_block = streak_block if room >= streak_block else 0
        mirror_pad.setFixedWidth(streak_block)
    except Exception:
        pass


def build_bottom_ui_block(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    streak_widget: QWidget | None,
    main_window: QWidget | None = None,
) -> QWidget:
    """Build the single bottom UI block: one centered group = [7day (optional)] + margin + [level | XP | gold | gems | quests | buttons].
    Outer stretches center the whole group; margin moves the 7-day streak away from the main content."""
    content_group = QWidget()
    group_row = QHBoxLayout(content_group)
    group_row.setContentsMargins(0, 0, 0, 0)
    group_row.setSpacing(0)
    if streak_widget is not None:
        group_row.addWidget(streak_widget)
        group_row.addSpacing(24)
    bar = build_xp_bar_widget(on_progress_click, on_shop_click, include_streak=False)
    group_row.addWidget(bar)

    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addStretch(1)
    row.addWidget(content_group, 0)
    row.addStretch(1)
    if main_window is not None:
        container.setMinimumWidth(_bottom_ui_block_min_width())
    return container


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
    from . import prestige as prestige_mod
    prestige_count = int(data.get("prestige_count", 0) or 0)
    prestige_points_total = int(data.get("prestige_points_total", 0) or 0)
    if prestige_count == 0 and prestige_points_total > 0:
        prestige_count = 1
    prestige_points_spent = int(data.get("prestige_points_spent", 0) or 0)
    prestige_avail = max(0, prestige_points_total - prestige_points_spent)
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
            from . import streak as streak_mod
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
    for q in daily_quests:
        prog = q.get("progress", 0)
        tgt = q.get("target", 0)
        label = q.get("label", "?")
        done = prog >= tgt
        base_xp = q.get("reward_xp", 0)
        display_xp = review_rewards._apply_quest_xp_bonus(data, base_xp, owned)
        if q.get("reward_gem"):
            reward_str = "1 gem"
        else:
            base_gold = q.get("reward_gold", 10)
            flat_for_quest = shop_mod.gold_flat(owned) // 2
            pct = shop_mod.gold_bonus_percent(owned)
            display_gold = int((base_gold + flat_for_quest) * (1 + pct / 100)) if pct else (base_gold + flat_for_quest)
            reward_str = f"+{display_gold}g"
        qtext = f"  {'✓ ' if done else ''}{label}: {prog}/{tgt}  (+{display_xp} XP, {reward_str})"
        ql = QLabel(qtext)
        if for_panel:
            ql.setMinimumWidth(1)
        quests_container_layout.addWidget(ql)
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
            luck_lbl = QLabel(f"Luck {int(luck_pct)}%")
            luck_lbl.setStyleSheet(stats_style)
            luck_lbl.setToolTip("Luck improves chances to get gems") 
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
    # Equal stretch so every button in this row ends up the same width, and no colour override so
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
    from .. import perform_prestige as _perform_prestige

    data = storage.load()
    prestige_count = int(data.get("prestige_count", 0) or 0)
    total_points = int(data.get("prestige_points_total", 0) or 0)
    if prestige_count == 0 and total_points > 0:
        prestige_count = 1
    spent_points = int(data.get("prestige_points_spent", 0) or 0)
    available = max(0, total_points - spent_points)
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
        "Quest reward",
        f"+{prestige_mod.QUEST_REWARD_STEP_PERCENT}% daily quest rewards globally",
        quest_reward_level,
        f"{quest_reward_level * prestige_mod.QUEST_REWARD_STEP_PERCENT}%",
    )

    layout.addSpacing(8)
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
        preview_lbl.setText(
            f"Current level: {current_level}. Prestiging now will grant {gain_preview + p} prestige point(s)."
            + (f" ({gain_preview} from level, {p} from gem trade(s))" if p > 0 else "")
        )

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
    current_level, _, _ = xp.xp_progress_in_level(data.get("total_xp", 0))
    gain_preview = prestige_mod.prestige_points_gain(current_level)
    total_preview = gain_preview + pending_gem_pts
    preview_text = f"Current level: {current_level}. Prestiging now will grant {total_preview} prestige point(s)."
    if pending_gem_pts > 0:
        preview_text += f" ({gain_preview} from level, {pending_gem_pts} from gem trade(s))"
    preview_lbl = QLabel(preview_text)
    preview_lbl.setStyleSheet("color: #888; font-size: 12px; font-weight: bold;")
    layout.addWidget(preview_lbl)

    # How prestige points are gained
    explain = QLabel(
        "You gain 2 prestige points at level 50,\n"
        "plus 1 extra point for every full 10 levels above 50."
    )
    explain.setWordWrap(True)
    explain.setStyleSheet("color: #888; font-size: 12px;")
    layout.addWidget(explain)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    prestige_btn = QPushButton("Prestige now")
    prestige_btn.setEnabled(prestige_mod.can_prestige(current_level))

    def on_prestige_now() -> None:
        if gain_preview <= 0:
            tooltip("Reach level 50 to prestige.")
            return
        reply = QMessageBox.question(
            parent or d,
            "Prestige",
            f"Prestige will reset ALL progress (XP, level, gold, gems, collectibles, quests, streak) "
            f"and grant {total_preview} prestige point(s).\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if not _perform_prestige(force=False):
            tooltip("Prestige cancelled or failed.")
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
    from .prestige import PRESTIGE_MIN_LEVEL

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


# Last house (image 17) unlocks at level 153. Show "game finished" panel when reached.
LAST_HOUSE_LEVEL = 153
KOFI_URL = "https://ko-fi.com/barisflo"


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

    review_msg = QLabel(
        'Feel free to <a href="' + ANKIWEB_REVIEW_URL + '">leave a review</a> if you haven\'t done already, '
        "or leave me a message / tip on my Ko-fi page to show your interest for another better version of this game !"
    )
    review_msg.setOpenExternalLinks(True)
    review_msg.setWordWrap(True)
    review_msg.setStyleSheet("font-size: 12px;")
    layout.addWidget(review_msg)

    kofi_pix = _pixmap_ui("kofi.png", height=36)
    if kofi_pix and not kofi_pix.isNull():
        kofi_btn = QPushButton()
        kofi_btn.setIcon(QIcon(kofi_pix))
        kofi_btn.setIconSize(kofi_pix.size())
        kofi_btn.setFlat(True)
        kofi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        kofi_btn.setToolTip("Support on Ko-fi")
        pw, ph = kofi_pix.width(), kofi_pix.height()
        kofi_btn.setFixedSize(pw, ph)
        kofi_btn.setStyleSheet("QPushButton { padding: 0; margin: 0; border: none; }")
        kofi_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(KOFI_URL)))
        kofi_row = QHBoxLayout()
        kofi_row.addStretch()
        kofi_row.addWidget(kofi_btn)
        kofi_row.addStretch()
        layout.addLayout(kofi_row)

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


def show_progress_dialog(
    parent: QWidget | None = None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Open CollectQuest in a modal dialog (e.g. from menu). Main entry is the side panel via toggle_progress_panel."""
    on_refresh = on_refresh or (lambda: None)
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Progress")
    d.setMinimumWidth(_POPUP_PROGRESS_DIALOG_WIDTH)
    d.setMaximumWidth(_POPUP_MAX_WIDTH)
    layout = QVBoxLayout(d)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.accept)
    layout.addWidget(
        build_progress_content_widget(d, on_refresh, parent or d, for_panel=False, close_button=close_btn)
    )
    close_btn.setFocus()
    # Open at the maximum width the dialog allows, so quest lines are readable without the user
    # having to drag it wider every time. Height follows content; the dialog stays resizable.
    def _set_initial_size() -> None:
        h = d.sizeHint().height() or 520
        # Clamp to the screen rather than a fixed 600px: the items list asks for enough height to
        # show three whole rows, and a flat cap clipped the third one on a normal display.
        screen = d.screen() or QApplication.primaryScreen()
        max_h = int(screen.availableGeometry().height() * 0.9) if screen else 900
        d.resize(_POPUP_MAX_WIDTH, min(h, max_h))
    QTimer.singleShot(0, _set_initial_size)
    d.exec()


# Panel default width; house image uses this in panel. 2/3 is added to window when panel opens.
_COLLECTQUEST_PANEL_WIDTH = 280
_COLLECTQUEST_PANEL_MIN_WIDTH = 200  # minimum dock width; content uses setMinimumWidth(1) so dock can shrink to this

# Popup (old-style) dialog: minimum width and max so they don't open super wide; user can resize between.
_POPUP_PROGRESS_DIALOG_WIDTH = 260
_POPUP_SHOP_DIALOG_WIDTH = 280
_POPUP_MAX_WIDTH = 420

# Item rows visible in the progress dialog's collectibles list when it opens, below the icon row.
# The list scrolls past this; the point is to open on whole rows rather than a clipped one.
_VISIBLE_ITEM_ROWS = 3

# Shop panel default width (slightly narrower than the main CollectQuest panel so it feels lighter).
_SHOP_PANEL_WIDTH = 220


def _dock_widget_features_default():
    """Closable | Movable | Floatable, compatible with PyQt5 and PyQt6."""
    try:
        F = QDockWidget.DockWidgetFeature
        return F.DockWidgetClosable | F.DockWidgetMovable | F.DockWidgetFloatable
    except AttributeError:
        return (
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
_COLLECTQUEST_PANEL_EXPAND_WIDTH = (_COLLECTQUEST_PANEL_WIDTH * 2) // 3  # 2/3 expansion, 1/3 from center
# frameGeometry().height() reports ~25px more than the visible height; subtract when saving so restore matches.
_FLOAT_HEIGHT_SAVE_OFFSET = 30
# Width reserved on the left for 7dayUI only (no reserve on the right).
_STATUSBAR_STREAK_AREA_WIDTH = 120

# Block width: preferred when all elements visible; minimum is computed from visible elements.
_STATUSBAR_BLOCK_PREFERRED = 380
_STATUSBAR_BLOCK_MIN = 260  # fallback when sizeHint not available

# Set to True (e.g. via env COLLECTQUEST_DEBUG_BOTTOM_UI=1) to log bottom UI layout values.
def _bottom_ui_debug_enabled() -> bool:
    return os.environ.get("COLLECTQUEST_DEBUG_BOTTOM_UI", "").strip().lower() in ("1", "true", "yes")


def _log_bottom_ui_debug(line: str) -> None:
    """Append one debug line to a file so users can share traces."""
    if not _bottom_ui_debug_enabled():
                return
    try:
        log_path = os.path.join(addon_dir(), "ag", "bottom_ui_debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _bottom_ui_block_min_width() -> int:
    """Minimum width for the bottom UI block based on which elements are visible (from storage)."""
    data = storage.load()
    show_level_xp = data.get("bottom_ui_show_level_xp", True)
    show_gold_gems = data.get("bottom_ui_show_gold_gems", True)
    show_quests = data.get("bottom_ui_show_quests", True)
    w = 24  # margins + internal spacing
    if show_level_xp:
        w += 28 + 100 + 6  # "Lv N" + bar + spacing
    if show_gold_gems:
        w += 18 + 36 + 2 + 100 + 8  # coin + gold + spacing + gems + spacing
        if show_quests:
            w += 12 + 72  # gap + "Q: 0/1"
    elif show_quests:
        w += 72  # quest label only
    w += 6  # before buttons
    w += 54 + 4 + 150  # Shop + spacing + CollectQuest
    return max(_STATUSBAR_BLOCK_MIN, min(520, w))


def get_collectquest_central_width(mw: QWidget) -> int:
    """Width of the base Anki window (central area). Qt already excludes docked panels."""
    cw = getattr(mw, "centralWidget", None) and mw.centralWidget()
    if cw is not None:
        return max(0, cw.width())
    return max(0, mw.width())


def get_collectquest_statusbar_center_content_width(mw: QWidget) -> int:
    """Width to use for the center block. Block contains [streak?] + 24px + bar; must be bar_min + 24 + streak so bar isn't squeezed (CollectQuest visible)."""
    bar_min = _bottom_ui_block_min_width()
    data = storage.load()
    show_streak = data.get("bottom_ui_show_streak", True)
    # Block min = bar min + spacing + streak area so the bar gets at least bar_min and buttons aren't clipped
    block_min = bar_min + 24 + (_STATUSBAR_STREAK_AREA_WIDTH if show_streak else 0) + 8  # +8 so right edge (Shop/CQ) isn't truncated
    center_w = getattr(mw, "_collectquest_xp_widget", None)
    if center_w is not None:
        sh = center_w.sizeHint().width()
        if sh > 0:
            return max(block_min, min(600, sh))
    return max(block_min, _STATUSBAR_BLOCK_PREFERRED)


def _statusbar_effective_width(mw: QWidget) -> int:
    """Width for centering when using fixed left/right spacers. When right panel docked, use stored reference so block doesn't move. No artificial minimum so left margin disappears when resizing down."""
    current = max(200, mw.width())
    cq_right = _collectquest_dock_area(mw) == "right"
    shop_right = _shop_dock_area(mw) == "right"
    any_right = cq_right or shop_right
    ref = getattr(mw, "_collectquest_statusbar_reference_width", None)
    if any_right:
        return max(200, ref if ref is not None else current)
    if ref is None or current <= ref:
        mw._collectquest_statusbar_reference_width = current
    return current


def get_collectquest_statusbar_right_panel_block_width(mw: QWidget) -> int:
    """Width of the right-side block (2/3 of right panel) when a panel is DOCKED on the right. No compensation when panel is floating."""
    panel_w = 0
    for dock_attr, area_fn in (
        ("_collectquest_dock", _collectquest_dock_area),
        ("_collectquest_shop_dock", _shop_dock_area),
    ):
        dock = getattr(mw, dock_attr, None)
        if dock is None or not dock.isVisible() or dock.isFloating():
            continue
        if area_fn(mw) == "right":
            panel_w = max(panel_w, dock.width())
    return int(panel_w * 2 / 3) if panel_w > 0 else 0


def get_collectquest_statusbar_left_spacer_width(mw: QWidget) -> int:
    """Left spacer so block center is at effective width/2. Uses reference width when right panel docked (no movement)."""
    total = _statusbar_effective_width(mw)
    content_w = get_collectquest_statusbar_center_content_width(mw)
    left_spacer = (total - content_w) // 2
    _log_bottom_ui_debug(
        "[CollectQuest bottom UI] total=%s content=%s left=%s"
        % (total, content_w, left_spacer)
    )
    return max(0, left_spacer)


def get_collectquest_statusbar_right_spacer_width(mw: QWidget) -> int:
    """Right spacer so block is centered (symmetric with left). Uses same effective width as left."""
    total = _statusbar_effective_width(mw)
    content_w = get_collectquest_statusbar_center_content_width(mw)
    left_spacer = (total - content_w) // 2
    return max(0, total - left_spacer - content_w)


def _dock_widget_area(mw: QWidget, dock: QWidget | None) -> str | None:
    """Dock area for the given dock: 'left', 'right', or None if floating/unknown."""
    if not dock:
        return None
    area_fn = getattr(mw, "dockWidgetArea", None)
    if not area_fn:
        return None
    try:
        a = area_fn(dock)
        if a == Qt.DockWidgetArea.LeftDockWidgetArea:
            return "left"
        if a == Qt.DockWidgetArea.RightDockWidgetArea:
            return "right"
    except Exception:
        pass
    return None


def _collectquest_dock_area(mw: QWidget) -> str | None:
    """Current dock area for progress panel: 'left', 'right', or None if floating/unknown."""
    return _dock_widget_area(mw, getattr(mw, "_collectquest_dock", None))


def _shop_dock_area(mw: QWidget) -> str | None:
    """Current dock area for shop panel: 'left', 'right', or None if floating/unknown."""
    return _dock_widget_area(mw, getattr(mw, "_collectquest_shop_dock", None))


def _dock_area_for_panel(
    mw: QWidget,
    preferred_side: str,
    other_dock: QWidget | None,
    other_area_fn: Callable[[QWidget], str | None],
) -> Qt.DockWidgetArea:
    """Preferred side 'left' or 'right'. If other panel is docked on that side, return the other side."""
    is_other_docked = other_dock and not (getattr(other_dock, "isFloating", lambda: True)())
    other_side = other_area_fn(mw) if is_other_docked else None
    if other_side == preferred_side:
        return Qt.DockWidgetArea.LeftDockWidgetArea if preferred_side == "right" else Qt.DockWidgetArea.RightDockWidgetArea
    return Qt.DockWidgetArea.LeftDockWidgetArea if preferred_side == "left" else Qt.DockWidgetArea.RightDockWidgetArea


def _dock_progress_panel(dock: QWidget) -> None:
    """Re-dock the Progress panel. Uses last saved area or right; docks to other side if that side is occupied by Shop."""
    try:
        mw = dock.parent()
        if not mw or not getattr(mw, "addDockWidget", None):
            dock.setFloating(False)
            return
        preferred = "right"
        try:
            data = storage.load()
            preferred = data.get("panel_area") or "right"
        except Exception:
            pass
        area_enum = _dock_area_for_panel(mw, preferred, getattr(mw, "_collectquest_shop_dock", None), _shop_dock_area)
        mw.addDockWidget(area_enum, dock)
        dock.setFloating(False)
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
    except Exception:
        try:
            dock.setFloating(False)
        except Exception:
            pass


def _dock_shop_panel(dock: QWidget) -> None:
    """Re-dock the Shop panel. Uses last saved area or left; docks to other side if that side is occupied by Progress."""
    try:
        mw = dock.parent()
        if not mw or not getattr(mw, "addDockWidget", None):
            dock.setFloating(False)
            return
        preferred = "left"
        try:
            data = storage.load()
            preferred = data.get("shop_panel_area") or "left"
        except Exception:
            pass
        area_enum = _dock_area_for_panel(mw, preferred, getattr(mw, "_collectquest_dock", None), _collectquest_dock_area)
        mw.addDockWidget(area_enum, dock)
        dock.setFloating(False)
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
    except Exception:
        try:
            dock.setFloating(False)
        except Exception:
            pass


def _save_shop_panel_state(mw: QWidget) -> None:
    """Persist shop panel visibility and placement (same pattern as progress panel)."""
    try:
        data = storage.load()
        dock = getattr(mw, "_collectquest_shop_dock", None)
        data["shop_panel_visible"] = dock.isVisible() if dock else False
        if dock and dock.isVisible():
            data["shop_panel_area"] = _shop_dock_area(mw) or "left"
            data["shop_panel_width"] = max(_COLLECTQUEST_PANEL_MIN_WIDTH, dock.width())
            data["shop_panel_floating"] = dock.isFloating()
            if dock.isFloating() and not getattr(mw, "_collectquest_shop_skip_save_float_geometry", False):
                rect = dock.frameGeometry()
                mw_win = mw.window().frameGeometry()
                data["shop_panel_float_rel_x"] = rect.x() - mw_win.x()
                data["shop_panel_float_rel_y"] = rect.y() - mw_win.y()
                data["shop_panel_float_width"] = max(200, rect.width())
                data["shop_panel_float_height"] = max(300, rect.height() - _FLOAT_HEIGHT_SAVE_OFFSET)
            storage.save(data)
    except Exception:
        pass


def _save_collectquest_panel_state(mw: QWidget) -> None:
    """Persist panel visibility and placement so it can be restored on next load."""
    try:
        data = storage.load()
        dock = getattr(mw, "_collectquest_dock", None)
        data["panel_visible"] = dock.isVisible() if dock else False
        if dock and dock.isVisible():
            area = _collectquest_dock_area(mw)
            data["panel_area"] = area or "right"
            data["panel_width"] = max(80, dock.width())
            data["panel_floating"] = dock.isFloating()
            # Only save floating geometry while visible; hidden dock can report wrong frameGeometry()
            # Position relative to Anki window so multi-monitor / different screen positions work
            if dock.isFloating() and not getattr(mw, "_collectquest_skip_save_float_geometry", False):
                rect = dock.frameGeometry()
                mw_win = mw.window().frameGeometry()
                data["panel_float_rel_x"] = rect.x() - mw_win.x()
                data["panel_float_rel_y"] = rect.y() - mw_win.y()
                data["panel_float_width"] = max(200, rect.width())
                data["panel_float_height"] = max(300, rect.height() - _FLOAT_HEIGHT_SAVE_OFFSET)
            storage.save(data)
    except Exception:
        pass


def _on_collectquest_dock_visibility_changed(mw: QWidget, visible: bool) -> None:
    """On close/hide: shrink window only if dock was docked. On show: expand only if docked (not floating)."""
    dock = getattr(mw, "_collectquest_dock", None)
    # Stop periodic float-save timer when panel is hidden (so we don't save bad geometry)
    save_timer = getattr(mw, "_collectquest_float_save_timer", None)
    if save_timer is not None:
        try:
            save_timer.stop()
        except Exception:
            pass
        mw._collectquest_float_save_timer = None
    _save_collectquest_panel_state(mw)
    # Floating panel: no effect on main window size; start periodic save so we persist position/size before user closes panel
    if dock and dock.isFloating():
        if visible:
            t = QTimer(mw)
            t.setSingleShot(False)
            t.timeout.connect(lambda: _save_collectquest_panel_state(mw))
            t.start(2000)
            mw._collectquest_float_save_timer = t
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return
    # Restore path: opening then immediately floating — don't expand
    if visible and getattr(mw, "_collectquest_restore_floating", False):
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return
    # Dock-in from float: skip expand here; topLevelChanged(False) will expand (avoids double expand)
    if visible and getattr(mw, "_collectquest_was_floating", False):
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
        return
    _y_before = mw.y()
    _h_before = mw.height()
    expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
    if not visible:
        # Shrink based on which side the dock was on (still known while closing)
        side = _collectquest_dock_area(mw)
        if side == "right":
            mw.resize(max(mw.minimumWidth(), mw.width() - expand), mw.height())
        elif side == "left":
            close_y = getattr(mw, "_collectquest_last_good_y", None) or _y_before
            close_h = getattr(mw, "_collectquest_last_good_height", None) or _h_before
            mw.setGeometry(mw.x() + expand, close_y, max(mw.minimumWidth(), mw.width() - expand), close_h)
            mw._collectquest_saved_y = close_y
            mw._collectquest_saved_height = close_h
            # Qt/Windows: re-apply position after shrink so window doesn't jump up
            def _reapply_after_shrink():
                try:
                    y, h = getattr(mw, "_collectquest_saved_y", None), getattr(mw, "_collectquest_saved_height", None)
                    if y is not None and h is not None:
                        mw.setGeometry(mw.x(), y, mw.width(), h)
                except Exception:
                    pass
            for delay in (50, 150, 300, 450, 600):
                QTimer.singleShot(delay, _reapply_after_shrink)
        else:
            mw.resize(max(mw.minimumWidth(), mw.width() - expand), mw.height())
        if side != "left":
            mw._collectquest_saved_y = mw.y()
            mw._collectquest_saved_height = mw.height()
        mw._collectquest_window_expanded = False
        upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
        if callable(upd):
            upd()
    else:
        # Expand when panel is shown or docked back in; defer so dock area is updated after dock-in
        def _expand():
            if getattr(mw, "_collectquest_window_expanded", False):
                upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
                if callable(upd):
                    upd()
                return
            side = _collectquest_dock_area(mw)
            mw._collectquest_last_dock_side = side
            if side == "right":
                mw.resize(mw.width() + expand, mw.height())
                mw._collectquest_last_good_y = mw.y()
                mw._collectquest_last_good_height = mw.height()
            elif side == "left":
                # Use saved y/height so the window doesn't jump up (Qt on Windows often repositions after left-dock)
                y = getattr(mw, "_collectquest_saved_y", None)
                h = getattr(mw, "_collectquest_saved_height", None)
                if y is None:
                    y = _y_before
                if h is None:
                    h = _h_before
                mw.setGeometry(mw.x() - expand, y, mw.width() + expand, h)
                mw._collectquest_saved_y = y
                mw._collectquest_saved_height = h
                # Workaround Qt/Windows bug: re-apply y/height after layout runs so the window doesn't move up
                def _reapply_left_position():
                    try:
                        want_y = getattr(mw, "_collectquest_saved_y", None)
                        want_h = getattr(mw, "_collectquest_saved_height", None)
                        if want_y is not None and want_h is not None:
                            mw.setGeometry(mw.x(), want_y, mw.width(), want_h)
                            # Remember for when we close (so close doesn't move window up)
                            mw._collectquest_last_good_y = want_y
                            mw._collectquest_last_good_height = want_h
                    except Exception:
                        pass
                for delay in (50, 150, 300, 450):
                    QTimer.singleShot(delay, _reapply_left_position)
            else:
                mw.resize(mw.width() + expand, mw.height())
            mw._collectquest_window_expanded = True
            upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
            if callable(upd):
                upd()
        QTimer.singleShot(0, _expand)


def _position_floating_dock_next_to_main(mw: QWidget, dock: QWidget | None, side: str) -> None:
    """Place a floating dock window left or right of the main window at about the same height."""
    if dock is None or not getattr(dock, "isFloating", lambda: False)():
        return
    try:
        mw_win = mw.window()
        mw_rect = mw_win.frameGeometry()
        gap = 8
        dock_w = dock.width()
        y = mw_rect.y()
        if side == "right":
            x = mw_rect.x() + mw_rect.width() + gap
        else:
            x = mw_rect.x() - dock_w - gap
        dock.move(x, y)
    except Exception:
        pass


def _on_collectquest_dock_top_level_changed(mw: QWidget, floating: bool) -> None:
    """When user floats the panel: shrink main window. When they dock it again: expand."""
    if not floating:
        save_timer = getattr(mw, "_collectquest_float_save_timer", None)
        if save_timer is not None:
            try:
                save_timer.stop()
            except Exception:
                pass
            mw._collectquest_float_save_timer = None
    if floating:
        if not getattr(mw, "_collectquest_window_expanded", False):
            return
        expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
        side = getattr(mw, "_collectquest_last_dock_side", None) or "right"
        if side == "right":
            new_w = max(mw.minimumWidth(), mw.width() - expand)
            mw.resize(new_w, mw.height())
            _g = (mw.x(), mw.y(), new_w, mw.height())
        elif side == "left":
            close_y = getattr(mw, "_collectquest_last_good_y", None) or mw.y()
            close_h = getattr(mw, "_collectquest_last_good_height", None) or mw.height()
            new_x = mw.x() + expand
            new_w = max(mw.minimumWidth(), mw.width() - expand)
            mw.setGeometry(new_x, close_y, new_w, close_h)
            mw._collectquest_saved_y = close_y
            mw._collectquest_saved_height = close_h
            _g = (new_x, close_y, new_w, close_h)
            def _reapply():
                y, h = getattr(mw, "_collectquest_saved_y", None), getattr(mw, "_collectquest_saved_height", None)
                if y is not None and h is not None:
                    mw.setGeometry(mw.x(), y, mw.width(), h)
            for delay in (50, 150, 300):
                QTimer.singleShot(delay, _reapply)
        else:
            new_w = max(mw.minimumWidth(), mw.width() - expand)
            mw.resize(new_w, mw.height())
            _g = (mw.x(), mw.y(), new_w, mw.height())
        mw._collectquest_window_expanded = False
        mw._collectquest_was_floating = True
        mw._collectquest_reference_window_width = mw.width()
        # Re-apply geometry and force a resize so QMainWindow re-layouts (fixes drag-to-float leaving "preview" layout)
        def _refresh_after_float():
            try:
                g = getattr(mw, "_collectquest_float_target_geometry", None)
                if g is not None and len(g) == 4:
                    mw.setGeometry(g[0], g[1], g[2], g[3])
                # Trigger same path as user resize: resize by 1 then back so central/dock layout updates
                w, h = mw.width(), mw.height()
                mw.resize(w + 1, h)
                mw.resize(w, h)
            except Exception:
                pass
        mw._collectquest_float_target_geometry = _g
        QTimer.singleShot(0, _refresh_after_float)
        QTimer.singleShot(150, _refresh_after_float)
        # Position floating window left or right of main window at same height (skip when restoring saved position)
        if not getattr(mw, "_collectquest_skip_save_float_geometry", False):
            def _place_progress_float() -> None:
                _position_floating_dock_next_to_main(mw, getattr(mw, "_collectquest_dock", None), side)
            QTimer.singleShot(50, _place_progress_float)
    else:
        # Progress just docked: don't allow both panels on same side — float shop even if hidden.
        # Defer so Qt has updated dockWidgetArea() before we read it.
        def _enforce_same_side_after_progress_docked() -> None:
            progress_side = _collectquest_dock_area(mw)
            shop_dock = getattr(mw, "_collectquest_shop_dock", None)
            if progress_side and shop_dock and not shop_dock.isFloating():
                if _shop_dock_area(mw) == progress_side:
                    shop_dock.setFloating(True)
        QTimer.singleShot(0, _enforce_same_side_after_progress_docked)
        if getattr(mw, "_collectquest_window_expanded", False):
            upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
            if callable(upd):
                upd()
            return
        _y_before, _h_before = mw.y(), mw.height()
        expand = _COLLECTQUEST_PANEL_EXPAND_WIDTH
        def _expand():
            if getattr(mw, "_collectquest_window_expanded", False):
                upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
                if callable(upd):
                    upd()
                return
            side = _collectquest_dock_area(mw)
            mw._collectquest_last_dock_side = side
            if side == "right":
                mw.resize(mw.width() + expand, mw.height())
                mw._collectquest_last_good_y = mw.y()
                mw._collectquest_last_good_height = mw.height()
            elif side == "left":
                y = getattr(mw, "_collectquest_saved_y", None) or _y_before
                h = getattr(mw, "_collectquest_saved_height", None) or _h_before
                mw.setGeometry(mw.x() - expand, y, mw.width() + expand, h)
                mw._collectquest_saved_y = y
                mw._collectquest_saved_height = h
                def _reapply_left():
                    want_y = getattr(mw, "_collectquest_saved_y", None)
                    want_h = getattr(mw, "_collectquest_saved_height", None)
                    if want_y is not None and want_h is not None:
                        mw.setGeometry(mw.x(), want_y, mw.width(), want_h)
                        mw._collectquest_last_good_y = want_y
                        mw._collectquest_last_good_height = want_h
                for delay in (50, 150, 300):
                    QTimer.singleShot(delay, _reapply_left)
            else:
                mw.resize(mw.width() + expand, mw.height())
            mw._collectquest_window_expanded = True
            mw._collectquest_was_floating = False
            upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
            if callable(upd):
                upd()
        QTimer.singleShot(0, _expand)
        return
    upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
    if callable(upd):
        upd()


def toggle_progress_panel(
    mw: QWidget,
    on_refresh: Callable[[], None],
    on_statusbar_center_update: Callable[[], None] | None = None,
) -> None:
    """Show or hide the CollectQuest side panel (right dock). Creates dock on first use.
    When showing, the window expands by 2/3 of the panel width; 1/3 is taken from the main area.
    on_statusbar_center_update is called after show/hide so the bottom bar can re-center over the main area."""
    if not hasattr(mw, "_collectquest_dock") or mw._collectquest_dock is None:
        dock = QDockWidget("CollectQuest", mw)
        dock.setObjectName("CollectQuestProgressDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        dock.setMinimumWidth(_COLLECTQUEST_PANEL_MIN_WIDTH)
        # Cursor on hover: title bar = open hand (movable), close/float buttons = pointing hand (clickable)
        _COLLECTQUEST_TITLE_BAR_HEIGHT = 28  # approximate; used to detect title bar vs content

        class _DockTitleBarCursorFilter(QObject):
            def __init__(self, dock_widget):
                super().__init__(dock_widget)
                self._dock = dock_widget

            def eventFilter(self, obj, event):
                if obj is not self._dock:
                    return False
                t = event.type()
                if t == QEvent.Type.MouseMove:
                    try:
                        p = event.position() if hasattr(event, "position") else event.pos()
                        y = p.y() if hasattr(p, "y") else 0
                        if y < _COLLECTQUEST_TITLE_BAR_HEIGHT and not getattr(self._dock, "isFloating", lambda: False)():
                            self._dock.setCursor(Qt.CursorShape.OpenHandCursor)
                        else:
                            self._dock.setCursor(Qt.CursorShape.ArrowCursor)
                    except Exception:
                        pass
                elif t == QEvent.Type.Leave:
                    self._dock.unsetCursor()
                return False

        dock.setMouseTracking(True)  # needed so we get MouseMove over title vs content
        dock.installEventFilter(_DockTitleBarCursorFilter(dock))
        # When mouse enters content (not title), clear the open-hand cursor so it doesn't stick
        class _DockContentCursorFilter(QObject):
            def __init__(self, dock_widget):
                super().__init__(dock_widget)
                self._dock = dock_widget

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.Enter:
                    self._dock.setCursor(Qt.CursorShape.ArrowCursor)
                return False

        def _install_content_cursor_filter(dock_widget, content_widget):
            if content_widget is not None:
                f = _DockContentCursorFilter(dock_widget)
                content_widget.installEventFilter(f)
                content_widget.setMouseTracking(True)

        mw._collectquest_content_cursor_filter_install = _install_content_cursor_filter
        # Pointing-hand cursor on the close/float buttons (they are children of the dock)
        def _set_dock_button_cursors():
            for child in dock.findChildren(QAbstractButton):
                try:
                    child.setCursor(Qt.CursorShape.PointingHandCursor)
                except Exception:
                    pass
        QTimer.singleShot(50, _set_dock_button_cursors)
        area = Qt.DockWidgetArea.RightDockWidgetArea
        try:
            saved = storage.load()
            if saved.get("panel_area") == "left":
                area = Qt.DockWidgetArea.LeftDockWidgetArea
        except Exception:
            pass
        mw.addDockWidget(area, dock)
        mw._collectquest_dock = dock
        mw._collectquest_on_refresh = on_refresh
        # One-time: ensure main window dock options include AnimatedDocks so drag-to-dock overlay shows
        if not getattr(mw, "_collectquest_dock_options_ensured", False):
            try:
                if hasattr(mw, "dockOptions") and hasattr(mw, "setDockOptions"):
                    opts = mw.dockOptions()
                    from aqt.qt import QMainWindow
                    animated = getattr(QMainWindow.DockOption, "AnimatedDocks", None) or getattr(QMainWindow, "AnimatedDocks", None)
                    if animated is not None and (opts & animated) == 0:
                        mw.setDockOptions(opts | animated)
            except Exception:
                pass
            mw._collectquest_dock_options_ensured = True
        dock.visibilityChanged.connect(lambda v: _on_collectquest_dock_visibility_changed(mw, v))
        if getattr(dock, "topLevelChanged", None):
            dock.topLevelChanged.connect(lambda floating: _on_collectquest_dock_top_level_changed(mw, floating))
    if on_statusbar_center_update is not None:
        mw._collectquest_update_statusbar_center_width = on_statusbar_center_update
    dock = mw._collectquest_dock
    if dock.isVisible():
        dock.hide()
        # Resize and status bar update are done by visibilityChanged
    else:
        # Re-apply so drag-to-dock overlay and drop zones work (can be reset by Qt/Anki)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        old = dock.widget()
        if old:
            old.deleteLater()
        content = build_progress_content_widget(dock, mw._collectquest_on_refresh, mw, for_panel=True)
        dock.setWidget(content)
        install = getattr(mw, "_collectquest_content_cursor_filter_install", None)
        if callable(install):
            install(dock, content)
        # Open floating before first show if saved state was floating (so it appears floating, no dock-then-float)
        try:
            if storage.load().get("panel_floating"):
                dock.setFloating(True)
                mw._collectquest_skip_save_float_geometry = True  # don't overwrite stored geometry before we apply it
        except Exception:
            pass
        dock.show()
        # Apply saved floating position/size after show (floating window exists then)
        def _apply_float_geometry():
            try:
                if not getattr(dock, "isFloating", lambda: False)():
                    setattr(mw, "_collectquest_skip_save_float_geometry", False)
                    return
                data = storage.load()
                rel_x = data.get("panel_float_rel_x")
                rel_y = data.get("panel_float_rel_y")
                w = data.get("panel_float_width")
                h = data.get("panel_float_height")
                mw_win = mw.window().frameGeometry()
                if isinstance(w, (int, float)) and isinstance(h, (int, float)) and 200 <= w <= 1200 and 300 <= h <= 900:
                    dock.resize(int(w), int(h))
                else:
                    dock.resize(_COLLECTQUEST_PANEL_WIDTH, 480)
                if isinstance(rel_x, (int, float)) and isinstance(rel_y, (int, float)):
                    dock.move(mw_win.x() + int(rel_x), mw_win.y() + int(rel_y))
                else:
                    dock.move(mw_win.x() + mw_win.width() - dock.width() - 20, mw_win.y() + 50)
            except Exception:
                pass
            finally:
                setattr(mw, "_collectquest_skip_save_float_geometry", False)
        # Apply once, next tick; no extra delayed re-apply (that was causing the window to extend vertically)
        QTimer.singleShot(0, _apply_float_geometry)
        # Expansion is done by visibilityChanged(True) only when docked; floating is handled above
        # Set panel width when docked: saved value or default; apply twice so Qt doesn't leave it oversized after dock-in
        def _apply_dock_width():
            try:
                if not getattr(mw, "resizeDocks", None):
                    return
                if getattr(dock, "isFloating", lambda: False)():
                    return
                data = storage.load()
                w = data.get("panel_width")
                if not isinstance(w, (int, float)) or w < 80 or w > 800:
                    w = _COLLECTQUEST_PANEL_WIDTH
                w = int(w)
                mw.resizeDocks([dock], [w], Qt.Orientation.Horizontal)
            except Exception:
                pass
        QTimer.singleShot(50, _apply_dock_width)
        QTimer.singleShot(250, _apply_dock_width)
    if on_statusbar_center_update:
        QTimer.singleShot(0, on_statusbar_center_update)


def toggle_shop_panel(mw: QWidget, on_refresh: Callable[[], None]) -> None:
    """Show or hide the Shop panel (left dock by default). Both Shop and CollectQuest can be docked or floating at the same time."""
    data = storage.load()
    today = streak_mod.today_str()
    reviews_today = data.get("reviews_today", 0)
    gate_date = data.get("shop_gate_date", "")
    shop_unlocked = (gate_date == today) or (reviews_today >= shop_mod.SHOP_MIN_REVIEWS)
    if not shop_unlocked:
        show_shop_dialog(mw, on_refresh)
        return

    if not hasattr(mw, "_collectquest_shop_dock") or mw._collectquest_shop_dock is None:
        dock = QDockWidget("Shop", mw)
        dock.setObjectName("CollectQuestShopDock")
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        dock.setMinimumWidth(_COLLECTQUEST_PANEL_MIN_WIDTH)
        area = Qt.DockWidgetArea.LeftDockWidgetArea
        try:
            saved = storage.load()
            if saved.get("shop_panel_area") == "right":
                area = Qt.DockWidgetArea.RightDockWidgetArea
        except Exception:
            pass
        mw.addDockWidget(area, dock)
        mw._collectquest_shop_dock = dock
        def _on_shop_visibility_changed(visible: bool) -> None:
            t = getattr(mw, "_collectquest_shop_float_save_timer", None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
                mw._collectquest_shop_float_save_timer = None
            _save_shop_panel_state(mw)
            if visible and dock.isFloating():
                t = QTimer(mw)
                t.setSingleShot(False)
                t.timeout.connect(lambda: _save_shop_panel_state(mw))
                t.start(2000)
                mw._collectquest_shop_float_save_timer = t
        dock.visibilityChanged.connect(_on_shop_visibility_changed)
        if getattr(dock, "topLevelChanged", None):
            def _on_shop_top_level(mw_ref: QWidget, floating: bool) -> None:
                if not floating:
                    # Shop just docked: don't allow both panels on same side. Defer so Qt has updated dockWidgetArea().
                    def _enforce_same_side_after_shop_docked() -> None:
                        shop_side = _shop_dock_area(mw_ref)
                        progress_dock = getattr(mw_ref, "_collectquest_dock", None)
                        if shop_side and progress_dock and not progress_dock.isFloating():
                            if _collectquest_dock_area(mw_ref) == shop_side:
                                progress_dock.setFloating(True)
                    QTimer.singleShot(0, _enforce_same_side_after_shop_docked)
                else:
                    # Position floating shop window left or right of main at same height (skip when restoring saved position)
                    if not getattr(mw_ref, "_collectquest_shop_skip_save_float_geometry", False):
                        try:
                            side = storage.load().get("shop_panel_area") or "left"
                        except Exception:
                            side = "left"
                        def _place_shop_float() -> None:
                            _position_floating_dock_next_to_main(mw_ref, getattr(mw_ref, "_collectquest_shop_dock", None), side)
                        QTimer.singleShot(50, _place_shop_float)
            dock.topLevelChanged.connect(lambda f: _on_shop_top_level(mw, f))
    dock = mw._collectquest_shop_dock
    if dock.isVisible():
        dock.hide()
    else:
        # Re-apply so drag-to-dock overlay and drop zones work (can be reset by Qt/Anki)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setFeatures(_dock_widget_features_default())
        old = dock.widget()
        if old:
            old.deleteLater()
        content = build_shop_content_widget(dock, on_refresh, dock.hide, for_panel=True)
        dock.setWidget(content)
        try:
            saved = storage.load()
            if saved.get("shop_panel_floating"):
                dock.setFloating(True)
                mw._collectquest_shop_skip_save_float_geometry = True
        except Exception:
            pass
        dock.show()

        def _apply_shop_float_geometry() -> None:
            try:
                if not getattr(dock, "isFloating", lambda: False)():
                    setattr(mw, "_collectquest_shop_skip_save_float_geometry", False)
                    return
                data = storage.load()
                rel_x = data.get("shop_panel_float_rel_x")
                rel_y = data.get("shop_panel_float_rel_y")
                w = data.get("shop_panel_float_width")
                h = data.get("shop_panel_float_height")
                mw_win = mw.window().frameGeometry()
                if isinstance(w, (int, float)) and isinstance(h, (int, float)) and 200 <= w <= 1200 and 300 <= h <= 900:
                    dock.resize(int(w), int(h))
                else:
                    dock.resize(_SHOP_PANEL_WIDTH, 480)
                if isinstance(rel_x, (int, float)) and isinstance(rel_y, (int, float)):
                    dock.move(mw_win.x() + int(rel_x), mw_win.y() + int(rel_y))
                else:
                    dock.move(mw_win.x() + mw_win.width() - dock.width() - 20, mw_win.y() + 50)
            except Exception:
                pass
            finally:
                setattr(mw, "_collectquest_shop_skip_save_float_geometry", False)
        QTimer.singleShot(0, _apply_shop_float_geometry)

        def _apply_shop_dock_width() -> None:
            try:
                if not getattr(mw, "resizeDocks", None):
                    return
                if getattr(dock, "isFloating", lambda: False)():
                    return
                data = storage.load()
                w = data.get("shop_panel_width")
                if not isinstance(w, (int, float)) or w < _COLLECTQUEST_PANEL_MIN_WIDTH or w > 800:
                    w = _SHOP_PANEL_WIDTH
                w = int(w)
                mw.resizeDocks([dock], [w], Qt.Orientation.Horizontal)
            except Exception:
                pass
        QTimer.singleShot(50, _apply_shop_dock_width)
        QTimer.singleShot(250, _apply_shop_dock_width)


def refresh_progress_panel(mw: QWidget) -> None:
    """Refresh the side panel content if it exists and is visible."""
    if not getattr(mw, "_collectquest_dock", None) or not mw._collectquest_dock.isVisible():
        return
    on_refresh = getattr(mw, "_collectquest_on_refresh", None)
    if not callable(on_refresh):
        return
    dock = mw._collectquest_dock
    old = dock.widget()
    if old:
        old.deleteLater()
    content = build_progress_content_widget(dock, on_refresh, mw, for_panel=True)
    dock.setWidget(content)
    install = getattr(mw, "_collectquest_content_cursor_filter_install", None)
    if callable(install):
        install(dock, content)


def show_review_summary_tooltip(
    completed_quests: list[tuple[str, int]],
    gold_earned: int,
    gem_earned: int,
    leveled_up: bool = False,
) -> None:
    """
    One tooltip for everything a single answer earned:

        Quest complete: Review 82 cards (+61 XP, +12g)
        Quests complete: Review 82 cards, Get 45 correct (+118 XP, +25g, +1 gem)
        Level up (+24g, +2 gems)

    Anki's tooltip is a singleton — every call closes the previous one — so firing "quest complete"
    and "+gold" as two calls meant the second silently ate the first and the quest message was never
    readable. Composing one line is the only way both survive.
    """
    rewards: list[str] = []
    quest_xp = sum(x for _, x in completed_quests) if completed_quests else 0
    if quest_xp > 0:
        rewards.append(f"+{quest_xp} XP")
    if gold_earned > 0:
        rewards.append(f"+{gold_earned}g")
    if gem_earned > 0:
        rewards.append(f"+{gem_earned} gem" + ("s" if gem_earned > 1 else ""))

    if completed_quests:
        labels = ", ".join(label for label, _ in completed_quests)
        head = ("Quest complete: " if len(completed_quests) == 1 else "Quests complete: ") + labels
    elif leveled_up:
        head = "Level up"
    else:
        # Rewards with no quest and no level-up shouldn't happen, but report the amounts plainly
        # rather than captioning them with a cause that didn't occur.
        head = ""

    if head:
        tooltip(head + (f" ({', '.join(rewards)})" if rewards else ""), period=2500)
    elif rewards:
        tooltip(", ".join(rewards), period=2500)


# 7-day streak reward: type -> gift image. The toast that used to carry per-type background and
# text colours now goes through Anki's own tooltip, so only the icon distinction remains.
_STREAK_GIFT_IMAGES = {
    "xp": "rewards/Gift - Blue (Border).png",
    "gem": "rewards/Gift - Pink (Border).png",
    "gold": "rewards/Gift - Yellow (Border).png",
}


def _streak_reward_message(reward: dict) -> str:
    """Build reward text for toast or dialog."""
    kind = reward.get("type", "xp")
    amount = reward.get("amount", 0)
    if kind == "xp":
        return f"+{amount} XP"
    if kind == "gem":
        msg = f"+{amount} gem" + ("s" if amount != 1 else "")
        if reward.get("gold"):
            msg += f"  and  +{reward['gold']}g"
        return msg
    msg = f"+{amount}g"
    if reward.get("xp"):
        msg += f"  and  +{reward['xp']} XP"
    return msg


# Review prompt: shown once at level 20 (or level+2 for existing 20+ players)
REVIEW_PROMPT_LEVEL = 20
REDDIT_FEEDBACK_URL = "https://www.reddit.com/r/Anki/comments/1qx86w1/made_a_gamification_addon_looking_for_feedback/"
ANKIWEB_INFO_URL = "https://ankiweb.net/shared/info/627746544"
ANKIWEB_REVIEW_URL = "https://ankiweb.net/shared/review/627746544"


def _ensure_review_prompt_trigger(data: dict) -> None:
    """Set review_prompt_trigger_level once: 20 if level < 20, else level+2 for existing 20+ players."""
    if data.get("review_prompt_trigger_level") is not None:
        return
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    data["review_prompt_trigger_level"] = REVIEW_PROMPT_LEVEL if level < REVIEW_PROMPT_LEVEL else level + 2


def should_show_review_prompt(data: dict) -> bool:
    """True if we should show the enjoyment prompt once (level reached trigger, not shown yet)."""
    if data.get("review_prompt_shown_at_level") is not None:
        return False
    _ensure_review_prompt_trigger(data)
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    trigger = data.get("review_prompt_trigger_level")
    return trigger is not None and level >= trigger


def _review_dialog_icon() -> QLabel | None:
    """Icon for the 3 review sub-windows (images/ui icon_scroll_letter_1)."""
    pm = None
    for name in ("icon_scroll_letter_1.png", "Icon_Scroll_Letter_1.png"):
        pm = _pixmap_ui(name, height=64)
        if pm is not None and not pm.isNull():
            break
    if pm is None or pm.isNull():
        return None
    lbl = QLabel()
    lbl.setPixmap(pm)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def show_review_prompt_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
    force: bool = False,
) -> None:
    """
    Three separate popups: (1) "Do you enjoy CollectQuest?" No / Yes (Yes focused). (2) No → sorry + Reddit + Close. (3) Yes → thanks + reward + AnkiWeb + CTA + Close.
    """
    # --- Dialog 1: Question ---
    d1 = QDialog(parent)
    d1.setWindowTitle("CollectQuest")
    layout1 = QVBoxLayout(d1)
    layout1.setSpacing(12)
    icon1 = _review_dialog_icon()
    if icon1:
        layout1.addWidget(icon1)
    q_lbl = QLabel("Do you enjoy CollectQuest?")
    q_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
    layout1.addWidget(q_lbl, 0, Qt.AlignmentFlag.AlignCenter)
    btn_row = QHBoxLayout()
    no_btn = QPushButton("No")
    yes_btn = QPushButton("Yes")
    clicked_yes: list[bool] = [False]

    def on_no() -> None:
        clicked_yes[0] = False
        d1.accept()

    def on_yes() -> None:
        clicked_yes[0] = True
        d1.accept()

    no_btn.clicked.connect(on_no)
    yes_btn.clicked.connect(on_yes)
    btn_row.addWidget(no_btn)
    btn_row.addWidget(yes_btn)
    layout1.addLayout(btn_row)
    d1.setMinimumWidth(280)
    yes_btn.setFocus()
    d1.exec()
    is_yes = clicked_yes[0]

    if not is_yes:
        # --- Dialog 2: No → sorry + Reddit + Close ---
        d2 = QDialog(parent)
        d2.setWindowTitle("CollectQuest")
        layout2 = QVBoxLayout(d2)
        layout2.setSpacing(12)
        icon2 = _review_dialog_icon()
        if icon2:
            layout2.addWidget(icon2)
        sorry_title = QLabel("Sorry to hear that !")
        sorry_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        sorry_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout2.addWidget(sorry_title)
        msg = QLabel(
            'Feel free to leave some feedback on <a href="'
            + REDDIT_FEEDBACK_URL
            + '">reddit</a>.'
        )
        msg.setOpenExternalLinks(True)
        msg.setWordWrap(True)
        msg.setStyleSheet("font-size: 12px;")
        layout2.addWidget(msg)
        close2 = QPushButton("Close")
        close2.clicked.connect(d2.accept)
        layout2.addWidget(close2)
        d2.setMinimumWidth(320)
        d2.exec()
        return
    # --- Yes: grant reward then Dialog 3 ---
    if not force:
        data = storage.load()
        data["money"] = data.get("money", 0) + 50
        data["gems"] = shop_mod.award_random_gem(data.get("gems", shop_mod.default_gems()))
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        data["review_prompt_shown_at_level"] = level
        if data.get("review_prompt_trigger_level") is None:
            _ensure_review_prompt_trigger(data)
        storage.save(data)
        if on_refresh:
            on_refresh()
    # --- Dialog 3: Yes → thanks + AnkiWeb + CTA + Close (bottom right), slightly larger ---
    d3 = QDialog(parent)
    d3.setWindowTitle("CollectQuest")
    layout3 = QVBoxLayout(d3)
    layout3.setSpacing(12)
    icon3 = _review_dialog_icon()
    if icon3:
        layout3.addWidget(icon3)
    thanks_title = QLabel("Thanks a lot !")
    thanks_title.setStyleSheet("font-size: 16px; font-weight: bold;")
    thanks_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout3.addWidget(thanks_title)
    token_lbl = QLabel("As a token of appreciation:")
    token_lbl.setStyleSheet("font-size: 12px;")
    token_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout3.addWidget(token_lbl)
    reward_row = QHBoxLayout()
    reward_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
    reward_row.setSpacing(16)
    coin_pm = _pixmap("currency/Coin x1.png", 22)
    if coin_pm:
        reward_row.addWidget(_label_with_pixmap(coin_pm, QLabel("+50 gold")))
    else:
        reward_row.addWidget(QLabel("+50 gold"))
    gem_pm = _pixmap("gems/Gem - Pink.png", 22)
    if gem_pm:
        reward_row.addWidget(_label_with_pixmap(gem_pm, QLabel("+1 random gem")))
    else:
        reward_row.addWidget(QLabel("+1 random gem"))
    layout3.addLayout(reward_row)
    prompt = QLabel(
        'Please consider giving a thumbs up on the <a href="'
        + ANKIWEB_INFO_URL
        + '">add-on page</a> !'
    )
    prompt.setOpenExternalLinks(True)
    prompt.setWordWrap(True)
    prompt.setStyleSheet("font-size: 12px;")
    layout3.addWidget(prompt)
    cta_btn = QPushButton("Leave a review on AnkiWeb")
    cta_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ANKIWEB_REVIEW_URL)))
    layout3.addWidget(cta_btn)
    bottom_row = QHBoxLayout()
    bottom_row.addStretch()
    close3 = QPushButton("Close")
    close3.clicked.connect(d3.accept)
    bottom_row.addWidget(close3)
    layout3.addLayout(bottom_row)
    d3.setMinimumWidth(360)
    d3.exec()


def maybe_show_review_prompt(parent: QWidget | None, on_refresh: Callable[[], None] | None = None) -> None:
    """If level >= trigger and not shown yet, show the review prompt once and mark shown."""
    data = storage.load()
    if not should_show_review_prompt(data):
        storage.save(data)  # persist trigger if we just set it
        return
    storage.save(data)
    show_review_prompt_dialog(parent, on_refresh=on_refresh, force=False)
    # shown_at_level is set inside dialog on Yes; if they close without Yes we don't mark shown (they can see it again)
    # Actually we should mark shown when we show the dialog so we only show once regardless of Yes/No
    data = storage.load()
    if data.get("review_prompt_shown_at_level") is None:
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        data["review_prompt_shown_at_level"] = level
        storage.save(data)
    if on_refresh:
        on_refresh()


def show_streak_reward_dialog(parent: QWidget | None, reward: dict) -> None:
    """Show a modal dialog for 7-day streak reward with title, correct gift icon, current streak, and reward icons."""
    kind = reward.get("type", "xp")
    gift_img = _STREAK_GIFT_IMAGES.get(kind, _STREAK_GIFT_IMAGES["xp"])
    msg = _streak_reward_message(reward)

    d = QDialog(parent)
    d.setWindowTitle("Streak reward!")
    layout = QVBoxLayout(d)
    layout.setSpacing(12)

    # Title (always visible)
    title_lbl = QLabel("Streak reward!")
    title_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")
    layout.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    # Current total streak
    current_streak_days = 0
    try:
        from aqt import mw as _mw
        if getattr(_mw, "col", None):
            from . import streak as _streak_mod
            data = storage.load()
            today_ep = _streak_mod.today_epoch(_mw.col)
            current_streak_days, _ = _streak_mod.get_display_streak_days(data, today_ep)
    except Exception:
        pass
    if current_streak_days > 0:
        streak_txt = f"Current total streak: {current_streak_days} day{'s' if current_streak_days != 1 else ''}"
        streak_lbl = QLabel(streak_txt)
        streak_lbl.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(streak_lbl, 0, Qt.AlignmentFlag.AlignCenter)

    # Reward row: gift icon + small gem/coin icon (before message) + message
    row = QHBoxLayout()
    row.setSpacing(10)
    gift_pm = _pixmap(gift_img, 56)
    if not gift_pm or gift_pm.isNull():
        gift_pm = _pixmap("ui/icon_message.png", 56)
    if gift_pm and not gift_pm.isNull():
        icon_lbl = QLabel()
        icon_lbl.setPixmap(gift_pm)
        row.addWidget(icon_lbl)
    # Small icon for gem or gold before the amount (fallback to ui icon if asset missing)
    if kind == "gem":
        small_pm = _pixmap("gems/Gem - Pink.png", 24) or _pixmap("ui/icon_message.png", 24)
        if small_pm and not small_pm.isNull():
            gem_lbl = QLabel()
            gem_lbl.setPixmap(small_pm)
            row.addWidget(gem_lbl)
    elif kind == "gold":
        small_pm = _pixmap("currency/Coin x1.png", 24) or _pixmap("ui/icon_message.png", 24)
        if small_pm and not small_pm.isNull():
            coin_lbl = QLabel()
            coin_lbl.setPixmap(small_pm)
            row.addWidget(coin_lbl)
    msg_lbl = QLabel(msg)
    msg_lbl.setStyleSheet("font-size: 13px;")
    row.addWidget(msg_lbl)
    row.addStretch()
    layout.addLayout(row)

    ok_btn = QPushButton("OK")
    ok_btn.setDefault(True)
    ok_btn.setFocus(Qt.FocusReason.PopupFocusReason)
    ok_btn.clicked.connect(d.accept)
    layout.addWidget(ok_btn, 0, Qt.AlignmentFlag.AlignCenter)
    d.exec()


def show_streak_reward_toast(parent: QWidget | None, reward: dict) -> None:
    """Report a 7-day streak reward, via Anki's own bottom-left tooltip."""
    tooltip("7-day streak! " + _streak_reward_message(reward))


def _estimate_reviews_per_day_last_30(col) -> float:
    """Rough average reviews/day over the last 30 days, from revlog."""
    try:
        days = 30
        rows = col.db.scalar(
            "SELECT COUNT() FROM revlog WHERE id/1000 >= strftime('%s','now') - ?",
            days * 86400,
        )
        count = rows or 0
        return float(count) / float(days)
    except Exception:
        return 0.0


def _recommend_difficulty(avg_reviews_per_day: float) -> str:
    """Map average reviews/day to difficulty id. Heavy user = 200+ reviews/day."""
    if avg_reviews_per_day < 60:
        return "easy"
    if avg_reviews_per_day >= 200:
        return "hard"
    return "normal"


def _show_onboarding_dialog(
    parent: QWidget | None,
    avg_per_day: float,
    diff_id: str,
    on_refresh: Callable[[], None] | None,
) -> None:
    """Welcome popup explaining basics and chosen difficulty."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Welcome")
    layout = QVBoxLayout(d)
    layout.setSpacing(10)

    icon = _review_dialog_icon()
    if icon:
        layout.addWidget(icon)

    title = QLabel("Welcome to CollectQuest!")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setStyleSheet("font-size: 16px; font-weight: bold;")
    layout.addWidget(title)

    intro = QLabel(
        "CollectQuest adds a light progression layer on top of your reviews:\n"
        "- Earn XP and gold from your daily studying and quests.\n"
        "- Buy collectibles in the shop and upgrade your house over time."
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("font-size: 12px;")
    layout.addWidget(intro)

    avg_txt = f"~{avg_per_day:.0f}" if avg_per_day > 0 else "unknown"
    diff_label = {
        "easy": "Casual",
        "normal": "Steady",
        "hard": "Heavy User",
    }.get(diff_id, "Steady")

    diff_msg = QLabel(
        f"Based on your last 30 days (~{avg_txt} reviews/day),\n"
        f"we started you in **{diff_label}** difficulty.\n\n"
        "You can always change this later in the Options."
    )
    diff_msg.setWordWrap(True)
    diff_msg.setStyleSheet("font-size: 12px;")
    layout.addWidget(diff_msg)

    btn_row = QHBoxLayout()
    btn_row.addStretch()

    def _open_options() -> None:
        d.accept()
        show_options_dialog(parent, on_refresh or (lambda: None))

    options_btn = QPushButton("Open Options")
    options_btn.clicked.connect(_open_options)
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(d.accept)
    btn_row.addWidget(options_btn)
    btn_row.addWidget(ok_btn)
    layout.addLayout(btn_row)

    # Highlight the OK button by default (not Open Options)
    ok_btn.setDefault(True)
    ok_btn.setAutoDefault(True)
    ok_btn.setFocus()

    d.setMinimumWidth(380)
    d.exec()


# Reddit feedback link for update popup
_UPDATE_POPUP_REDDIT_URL = "https://www.reddit.com/r/Anki/comments/1riq88z/comment/o8am3dr/"


def show_update_popup(
    parent: QWidget | None = None,
    version: str | None = None,
    on_open_options: Callable[[], None] | None = None,
) -> None:
    """Show the 'Updated to X' dialog. version defaults to current add-on version. on_open_options called when user clicks the options link."""
    ver = version or storage.get_version() or "1.1.1"
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Update")
    layout = QVBoxLayout(d)
    layout.setSpacing(10)
    scroll_pm = _pixmap_ui("icon_scroll_letter_1.png", height=56)
    if scroll_pm and not scroll_pm.isNull():
        scroll_lbl = QLabel()
        scroll_lbl.setPixmap(scroll_pm)
        scroll_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(scroll_lbl)
    title = QLabel(f"Updated to {ver} !")
    title.setStyleSheet("font-weight: bold; font-size: 14px;")
    layout.addWidget(title)
    options_lbl = QLabel(
        'Thank you for playing CollectQuest! You can tune everything in <a href="options">options</a>.'
    )
    options_lbl.setTextFormat(Qt.TextFormat.RichText)
    options_lbl.setOpenExternalLinks(False)
    def _on_link(url: str) -> None:
        if url == "options":
            d.accept()
            if on_open_options:
                on_open_options()
    options_lbl.linkActivated.connect(_on_link)
    layout.addWidget(options_lbl)
    changes_lbl = QLabel(
        "- Streak logic was simplified and stabilized (maybe for good this time)\n"
        "- Craft gem clarification and fixes\n"
        "- Shop shows item effects directly in daily offers.\n"
        "- Options panel is cleaner and uses less vertical space."
    )
    changes_lbl.setWordWrap(True)
    changes_lbl.setStyleSheet("font-size: 12px;")
    layout.addWidget(changes_lbl)
    feedback = QLabel(
        'Feel free to give me feedback on <a href="'
        + _UPDATE_POPUP_REDDIT_URL
        + '">reddit</a> !'
    )
    feedback.setOpenExternalLinks(True)
    feedback.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(feedback)
    ok_btn = QPushButton("OK")
    ok_btn.clicked.connect(d.accept)
    layout.addWidget(ok_btn)
    ok_btn.setFocus()
    d.setMinimumWidth(340)
    d.exec()


def maybe_show_update_popup(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
    force: bool = False,
) -> None:
    """Show update popup once per version: if shown_update_popup_for != current, show it. The flag is set *after* the user closes the popup (so we don't mark as shown while it's open). force=True (admin) just shows the dialog."""
    data = storage.load()
    current = (storage.get_version() or "").strip()
    if not current:
        current = "1.1.1"
    shown_for = (data.get("shown_update_popup_for") or "0").strip()
    def _open_options() -> None:
        show_options_dialog(parent, on_refresh=on_refresh)
    if not force and shown_for == current:
        return
    show_update_popup(parent, version=current, on_open_options=_open_options)
    # Set flag only after popup was closed (user clicked OK)
    if not force:
        data = storage.load()
        data["shown_update_popup_for"] = current
        storage.save(data)


def maybe_show_onboarding(
    parent: QWidget | None,
    on_refresh: Callable[[], None] | None = None,
    force: bool = False,
) -> None:
    """Show onboarding popup once, and auto-set difficulty from last 30 days. force=True (admin) skips guards and shows dialog."""
    from aqt import mw as _mw

    data = storage.load()
    if not force:
        if data.get("onboarding_shown") or (data.get("total_xp", 0) or 0) > 0:
            return
    col = getattr(_mw, "col", None)
    avg = _estimate_reviews_per_day_last_30(col) if col else 0.0
    diff_id = _recommend_difficulty(avg) if col else "normal"
    if not force:
        data["difficulty"] = diff_id
        data["onboarding_shown"] = True
        storage.save(data)
    xp.set_difficulty(diff_id)
    _show_onboarding_dialog(parent, avg, diff_id, on_refresh)


def show_sync_summary_panel(parent: QWidget | None, summary: dict) -> None:
    """Report what a sync credited (Sync · N reviews · +X XP · …), via Anki's own bottom-left tooltip."""
    reviews = summary.get("reviews", 0)
    if reviews <= 0:
        return
    xp_val = summary.get("xp", 0)
    gold_val = summary.get("gold", 0)
    gems_val = summary.get("gems", 0)
    parts = ["Sync", f"{reviews} review" + ("s" if reviews != 1 else "")]
    if xp_val > 0:
        parts.append(f"+{xp_val} XP")
    if gold_val > 0:
        parts.append(f"+{gold_val}g")
    if gems_val > 0:
        parts.append(f"+{gems_val} gem" + ("s" if gems_val != 1 else ""))
    tooltip("  ·  ".join(parts), period=2500)


# --- Shop: reusable content widget (dialog or dock), then dialog entry point ---

def build_shop_content_widget(
    parent: QWidget,
    on_refresh: Callable[[], None] | None,
    on_close: Callable[[], None],
    for_panel: bool = False,
) -> QWidget:
    """Build the shop UI (gold, daily items, buy/craft, refresh). When for_panel=False (dialog), adds Close button and focuses it; when for_panel=True (dock), no Close and no focus."""
    root = QWidget(parent)
    root.setMinimumWidth(1)  # allow dock to shrink to its minimum (same treatment as progress panel)
    main_layout = QVBoxLayout(root)
    # Match progress panel: small, even margins; avoid extra left gutter in the dock.
    main_layout.setContentsMargins(6, 5, 6, 5)

    # Header: Shop icon + two-line title on its right
    header_row = QHBoxLayout()
    header_row.setSpacing(8)
    shop_pm = _pixmap("ui/Shop (Border).png", 56)
    if shop_pm:
        shop_lbl = QLabel()
        shop_lbl.setPixmap(shop_pm)
        shop_lbl.setMinimumSize(56, 56)
        shop_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_row.addWidget(shop_lbl)
    title_col = QVBoxLayout()
    title_col.setSpacing(0)
    title_line1 = QLabel("Shop")
    title_line1.setStyleSheet("font-weight: bold; font-size: 14px;")
    title_col.addWidget(title_line1)
    title_line2 = QLabel("CollectQuest")
    title_line2.setStyleSheet("font-size: 11px; color: #888;")
    title_col.addWidget(title_line2)
    header_row.addLayout(title_col)
    header_row.addStretch()
    if for_panel and parent is not None and getattr(parent, "isFloating", None) is not None:
        shop_dock_btn = QPushButton("⊞ Dock")
        shop_dock_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        shop_dock_btn.setStyleSheet(
            "QPushButton { font-size: 10px; color: #888; padding: 1px 6px; border: 1px solid palette(window); border-radius: 2px; "
            "background: transparent; min-width: 0; outline: none; } "
            "QPushButton:hover, QPushButton:focus, QPushButton:pressed { background: transparent; border: 1px solid palette(window); outline: none; }"
        )
        shop_dock_btn.setToolTip("Attach panel to main window (left or right). Uses other side if current is occupied.")
        shop_dock_btn.setVisible(parent.isFloating())
        shop_dock_btn.clicked.connect(lambda: _dock_shop_panel(parent))
        if getattr(parent, "topLevelChanged", None) is not None:
            def _on_shop_float_changed(floating: bool) -> None:
                try:
                    shop_dock_btn.setVisible(floating)
                except RuntimeError:
                    pass  # content may have been replaced (e.g. on re-dock)
            parent.topLevelChanged.connect(_on_shop_float_changed)
        header_row.addWidget(shop_dock_btn)
    main_layout.addLayout(header_row)

    content = QWidget()
    content_layout = QVBoxLayout(content)
    # Remove extra indent inside the scrollable content so the shop body lines up with the header text
    content_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.addWidget(content, 1)  # content takes all available space; stretch is inside

    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

    def on_buy_gem_slot(slot_index: int):
        data = storage.load()
        slots = data.get("shop_daily_slots", [])
        if slot_index < 0 or slot_index >= len(slots):
            return
        slot = slots[slot_index]
        if not shop_mod.buy_gem_option(data, slot):
            tooltip("Not enough gold.")
            return
        storage.save(data)
        if slot.get("random"):
            tooltip("Bought 1 random gem!")
        else:
            color = slot.get("color", "")
            name = color.capitalize() if color else "Gem"
            tooltip(f"Bought 1 {name} gem!")
        refresh()
        if on_refresh:
            on_refresh()

    def on_buy(cid: str):
        data = storage.load()
        c = shop_mod.get_collectible(cid)
        if not c or cid in data.get("owned_collectibles", []):
            return
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        cost = shop_mod.effective_cost_gold(c, level)
        if cost <= 0 or data.get("money", 0) < cost:
            return
        data["money"] = data["money"] - cost
        data.setdefault("owned_collectibles", []).append(cid)
        storage.save(data)
        tooltip(f"Purchased {c.get('name', cid)}!")
        refresh()
        if on_refresh:
            on_refresh()

    def on_spend_gems():
        data = storage.load()
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        cid, c = shop_mod.spend_gems_get_random(data, level)
        if c is None:
            if not shop_mod.can_craft(data.get("gems", shop_mod.default_gems())):
                tooltip("Need 1 of each gem color (5 total) to get a random item.")
            else:
                tooltip("You already own every collectible available at your level!")
            return
        storage.save(data)
        name = c.get("name", cid)
        if c.get("cost_gold") is None:
            tooltip(f"Got {name}! (GEM-ONLY ITEM !)")
        else:
            tooltip(f"Got {name}!")
        refresh()
        if on_refresh:
            on_refresh()

    def on_refresh_shop():
        data = storage.load()
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        if not shop_mod.refresh_shop(data, level):
            if not shop_mod.has_refresh_unlocked(data):
                tooltip("Own a key (Bronze, Silver, or Golden) to unlock shop refresh.")
            else:
                cost = shop_mod.get_refresh_cost(data)
                tooltip(f"Need {cost}g to refresh (15g first, +15g per use).")
            return
        storage.save(data)
        tooltip("Shop refreshed!")
        refresh()
        if on_refresh:
            on_refresh()

    def _build_shop_content(layout: QVBoxLayout, close_callback: Callable[[], None], add_close: bool) -> None:
        data = storage.load()
        money = data.get("money", 0)
        gems = data.get("gems", shop_mod.default_gems())
        owned = set(data.get("owned_collectibles", []))
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        daily_slots = shop_mod.get_daily_slots(data, level)
        storage.save(data)

        gold_row = QHBoxLayout()
        coin_pm = _pixmap("currency/Coin x1.png", 28)
        if coin_pm:
            gold_row.addWidget(_label_with_pixmap(coin_pm, QLabel(f"Your gold: {money}")))
        else:
            gold_row.addWidget(QLabel(f"Your gold: {money}"))
        gold_row.addStretch()
        layout.addLayout(gold_row)

        all_owned = shop_mod.all_collectibles_owned(data)

        # --- TOP section: gold + items (aligned to top) ---
        if all_owned:
            layout.addWidget(QLabel("You own all collectibles! Convert resources to XP:"))
            layout.addSpacing(8)
            total_xp = data.get("total_xp", 0)
            current_level = xp.level_from_total_xp(total_xp)
            layout.addWidget(QLabel(f"Level {current_level} — {total_xp} XP total"))
        else:
            layout.addWidget(QLabel("Today's items"))
            daily_grid = QGridLayout()
            daily_grid.setContentsMargins(0, 0, 0, 0)
            daily_grid.setColumnStretch(1, 1)
            for r, slot in enumerate(daily_slots):
                if slot.get("type") == "collectible":
                    cid = slot.get("id", "")
                    c = shop_mod.get_collectible(cid)
                    if not c:
                        continue
                    effect = (c.get("effect_description") or "").strip()
                    tip = f"{c.get('name', '')}: {effect}" if effect else c.get("name", "")
                    pm = _pixmap(c["image"], 36)
                    if pm:
                        icon = QLabel()
                        icon.setPixmap(pm)
                        icon.setToolTip(tip)
                        daily_grid.addWidget(icon, r, 0)
                    name_cell = QWidget()
                    name_col = QVBoxLayout(name_cell)
                    name_col.setContentsMargins(0, 0, 0, 0)
                    name_col.setSpacing(2)
                    name_lbl = QLabel(c["name"])
                    name_lbl.setToolTip(tip)
                    name_col.addWidget(name_lbl)
                    if effect:
                        eff_lbl = QLabel(effect)
                        eff_lbl.setStyleSheet("font-size: 10px; color: #888;")
                        eff_lbl.setWordWrap(True)
                        eff_lbl.setToolTip(tip)
                        name_col.addWidget(eff_lbl)
                    daily_grid.addWidget(name_cell, r, 1)
                    if cid in owned:
                        daily_grid.addWidget(QLabel("(owned)"), r, 2)
                        daily_grid.addWidget(QLabel(""), r, 3)
                    else:
                        cost = shop_mod.effective_cost_gold(c, level)
                        daily_grid.addWidget(QLabel(f"{cost}g"), r, 2)
                        buy_btn = QPushButton("Buy")
                        buy_btn.setStyleSheet("padding: 0 5px;")
                        buy_btn.setEnabled(money >= cost)
                        buy_btn.clicked.connect(lambda checked=False, cid=cid: on_buy(cid))
                        daily_grid.addWidget(buy_btn, r, 3)
                else:
                    sold = slot.get("sold", False)
                    cost = slot.get("cost", 0)
                    if slot.get("random"):
                        pm = _pixmap("gems/Gem - Blue.png", 28)
                        label = "1 random gem"
                    else:
                        color = slot.get("color", "")
                        img_name = next((img for col, img in shop_mod.GEM_COLORS if col == color), "gems/Gem - Blue.png")
                        pm = _pixmap(img_name, 28)
                        label = f"{color.capitalize()} gem"
                    if pm:
                        icon = QLabel()
                        icon.setPixmap(pm)
                        daily_grid.addWidget(icon, r, 0)
                    daily_grid.addWidget(QLabel(label), r, 1)
                    if sold:
                        daily_grid.addWidget(QLabel("Sold"), r, 2)
                        buy_btn = QPushButton("Buy")
                        buy_btn.setStyleSheet("padding: 0 5px;")
                        buy_btn.setEnabled(False)
                    else:
                        daily_grid.addWidget(QLabel(f"{cost}g"), r, 2)
                        buy_btn = QPushButton("Buy")
                        buy_btn.setStyleSheet("padding: 0 5px;")
                        buy_btn.setEnabled(money >= cost)
                        buy_btn.clicked.connect(lambda checked=False, idx=r: on_buy_gem_slot(idx))
                    daily_grid.addWidget(buy_btn, r, 3)
            layout.addLayout(daily_grid)

        # --- Stretch: pushes top section up, bottom section down ---
        layout.addStretch()

        # --- BOTTOM section: gems, craft, trade, refresh, close (aligned to bottom) ---
        gem_info_lbl = QLabel(
            "Craft a random item with Gems.\n"
            "Some rares items are gem-only !"
        )
        # Slightly smaller helper label so the updated gem A/B copy feels subtle.
        gem_info_lbl.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(gem_info_lbl)

        gem_counts_row = QHBoxLayout()
        gem_counts_row.setSpacing(3)  # 1px less than default
        for color, img_name in shop_mod.GEM_COLORS:
            cnt = gems.get(color, 0)
            pm = _pixmap(img_name, 24)
            if pm:
                gem_counts_row.addWidget(_label_with_pixmap(pm, QLabel(f"×{cnt}")))
            else:
                gem_counts_row.addWidget(QLabel(f"{color}:{cnt}"))
        gem_counts_row.addStretch()
        layout.addLayout(gem_counts_row)
        if not all_owned:
            can_craft = shop_mod.can_craft(gems)
            spend_gems_btn = QPushButton("Craft (1 gem of each)")
            spend_gems_btn.setEnabled(can_craft)
            spend_gems_btn.clicked.connect(on_spend_gems)
            spend_gems_btn.setToolTip(
                "Spend one of each gem color (5 total) to get a random item at your level.\n"
                "(Can get unique gem items, but some are gold-only in the late game)"
            )
            layout.addWidget(spend_gems_btn)

        if all_owned:
            def on_trade_gold_for_xp():
                data = storage.load()
                if not shop_mod.all_collectibles_owned(data):
                    return
                xp_added = shop_mod.trade_gold_for_xp(data)
                if xp_added <= 0:
                    tooltip("No gold to trade.")
                    return
                storage.save(data)
                tooltip(f"Traded gold for +{xp_added} XP!")
                refresh()
                if on_refresh:
                    on_refresh()

            trade_gold_btn = QPushButton("Trade gold for XP (1g = 3 XP)")
            trade_gold_btn.setToolTip("Convert all your gold to XP at 1g = 3 XP. Only when you own every collectible.")
            trade_gold_btn.clicked.connect(on_trade_gold_for_xp)
            layout.addWidget(trade_gold_btn)

            def on_trade_gems_for_xp():
                data = storage.load()
                if not shop_mod.all_collectibles_owned(data):
                    return
                xp_added = shop_mod.trade_gems_for_xp(data)
                if xp_added <= 0:
                    tooltip("No gems to trade.")
                    return
                storage.save(data)
                tooltip(f"Traded gems for +{xp_added} XP!")
                refresh()
                if on_refresh:
                    on_refresh()

            trade_gems_btn = QPushButton("Trade gems for XP (1 gem = 100 XP)")
            trade_gems_btn.setToolTip("Convert all your gems to XP at 1 gem = 100 XP. Only when you own every collectible.")
            trade_gems_btn.clicked.connect(on_trade_gems_for_xp)
            layout.addWidget(trade_gems_btn)

        remaining_sec = shop_mod.get_shop_refresh_remaining(data)
        if remaining_sec > 0:
            mins = remaining_sec // 60
            secs = remaining_sec % 60
            timer_lbl = QLabel(f"Auto-refresh in {mins}m {secs}s")
            timer_lbl.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(timer_lbl)

        if shop_mod.has_refresh_unlocked(data):
            refresh_cost = shop_mod.get_refresh_cost(data)
            is_free = shop_mod.has_free_refresh_available(data)
            if is_free:
                refresh_btn = QPushButton("Refresh shop")
                refresh_btn.setEnabled(True)
            else:
                refresh_btn = QPushButton(f"Refresh shop ({refresh_cost}g)")
                refresh_btn.setEnabled(money >= refresh_cost)
            refresh_btn.clicked.connect(on_refresh_shop)
            layout.addWidget(refresh_btn)

        if add_close:
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(close_callback)
            layout.addWidget(close_btn)
            QTimer.singleShot(0, close_btn.setFocus)

    def refresh() -> None:
        _clear_layout(content_layout)
        _build_shop_content(content_layout, on_close, add_close=not for_panel)

    refresh()
    return root


def show_shop_dialog(parent: QWidget | None = None, on_refresh: Callable[[], None] | None = None) -> None:
    """
    Open shop: only if either:
      - shop_gate_date == today (already unlocked today), OR
      - reviews_today >= SHOP_MIN_REVIEWS (10 reviews done today).
    Once unlocked, set shop_gate_date = today so it stays open all day.
    """
    data = storage.load()
    today = streak_mod.today_str()
    reviews_today = data.get("reviews_today", 0)
    gate_date = data.get("shop_gate_date", "")
    shop_unlocked = (gate_date == today) or (reviews_today >= shop_mod.SHOP_MIN_REVIEWS)
    if shop_unlocked and gate_date != today:
        data["shop_gate_date"] = today
        storage.save(data)
    if not shop_unlocked:
        d = QDialog(parent)
        d.setWindowTitle("CollectQuest — Shop")
        layout = QVBoxLayout(d)
        layout.addSpacing(12)
        shop_pm = _pixmap("ui/Shop (Border).png", 96)
        if shop_pm:
            shop_lbl = QLabel()
            shop_lbl.setPixmap(shop_pm)
            layout.addWidget(shop_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        msg = QLabel("Shop available after 10 reviews!")
        msg.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(msg, 0, Qt.AlignmentFlag.AlignCenter)
        counter = QLabel(f"Reviews today: {reviews_today} / {shop_mod.SHOP_MIN_REVIEWS}")
        layout.addWidget(counter, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(12)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(d.accept)
        layout.addWidget(close_btn)
        d.exec()
        return

    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Shop")
    d.setMinimumWidth(_POPUP_SHOP_DIALOG_WIDTH)
    d.setMaximumWidth(_POPUP_MAX_WIDTH)
    layout = QVBoxLayout(d)
    layout.addWidget(build_shop_content_widget(d, on_refresh, d.accept, for_panel=False))
    d.exec()
