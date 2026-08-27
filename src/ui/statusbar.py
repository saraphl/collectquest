"""The bottom status-bar block: streak squares, XP bar and its centering."""
from __future__ import annotations

from typing import Callable
from aqt.qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QWidget,
    Qt,
)
from .. import prestige as prestige_mod, shop as shop_mod, storage, streak as streak_mod, xp
from .assets import _pixmap
from .constants import _STATUSBAR_BLOCK_MIN, _STREAK_EMPTY_COLOR, _STREAK_FILLED_COLOR, _STREAK_GAP, _STREAK_GIFT_IMAGES

def _streak_gift_image_for_type(reward_type: str) -> str:
    """Gift image path for streak reward type (xp=blue, gem=pink, gold=yellow). Call only when type is set."""
    return _STREAK_GIFT_IMAGES.get(reward_type, _STREAK_GIFT_IMAGES["xp"])

def _streak_squares_widget(streak_days: int, size: int = 12, reward_type: str | None = None) -> QWidget:
    """7 squares + optional gift icon. When reward_type is None (e.g. after claim until next week), show no icon."""
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

def build_streak_widget(streak_count: int | None = None, data: dict | None = None) -> QWidget:
    """Build status bar widget: 7-day streak only. streak_count from streak.refresh_streak (revlog-based).

    `data` is an already-loaded save. Every builder here takes one: storage.load() re-reads and
    re-hashes the file, and a whole bar rebuild used to cost three or four of those.
    """
    data = storage.load() if data is None else data
    filled = streak_count if streak_count is not None else _streak_display_filled(data)
    reward_type = data.get("streak_reward_type")  # None until next week starts → show no icon
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(8, 0, 4, 0)
    row.setSpacing(0)
    row.addWidget(_streak_squares_widget(filled, size=10, reward_type=reward_type))
    return w

def _prestige_unlocked(data: dict, level: int | None = None) -> bool:
    """Whether the Prestige button belongs in the bar: reachable now, or prestiged at least once.

    The same gate the CollectQuest window used before the button moved here. `level` is the caller's
    already-computed level - deriving it walks one loop iteration per level.
    """
    if level is None:
        level, _, _ = xp.xp_progress_in_level(data.get("total_xp", 0))
    return prestige_mod.can_prestige(level) or int(data.get("prestige_points_total", 0) or 0) > 0

def build_xp_bar_widget(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    on_prestige_click: Callable[[], None],
    include_streak: bool = False,
    data: dict | None = None,
) -> QWidget:
    """Build status bar widget: level, XP bar, gold, gems, [optional streak], Shop, Prestige, CollectQuest.
    Visibility of streak/level-xp/gold-gems/quests and button order follow storage bottom_ui_* options."""
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(6, 0, 6, 0)  # equal margins so the row centers; right one also keeps
    # the last button (CollectQuest) from being truncated
    layout.setSpacing(4)

    data = storage.load() if data is None else data
    show_level_xp = data.get("bottom_ui_show_level_xp", True)
    show_gold_gems = data.get("bottom_ui_show_gold_gems", False)
    show_quests = data.get("bottom_ui_show_quests", False)
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
    _prestige_style = "QPushButton { padding: 1px 4px; margin: 0; font-size: 11px; min-width: 56px; max-width: 62px }"
    shop_btn = QPushButton("Shop")
    shop_btn.setFlat(True)
    shop_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    shop_btn.setEnabled(True)
    # No explicit color when unlocked: the button then inherits the theme's default text color,
    # matching the "Lv N" label beside it in both light and dark mode. Locked stays dimmed, because
    # that graying is what signals the shop is not open yet.
    _shop_enabled_style = _shop_style + " QPushButton { font-weight: bold; }"
    _shop_locked_style = _shop_style + " QPushButton { color: #666; }"
    shop_btn.setStyleSheet(_shop_enabled_style if shop_enabled else _shop_locked_style)
    shop_btn.setToolTip("Open shop (unlocked after 10 reviews today)" if shop_enabled else f"Click to see when shop unlocks — {reviews_today}/{shop_mod.SHOP_MIN_REVIEWS} reviews today")
    shop_btn.clicked.connect(on_shop_click)
    cq_btn = QPushButton("CollectQuest")
    cq_btn.setFlat(True)
    cq_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    cq_btn.setStyleSheet(_cq_style + " QPushButton { font-weight: bold; }")
    cq_btn.clicked.connect(on_progress_click)
    prestige_btn = None
    if _prestige_unlocked(data, lev):
        prestige_btn = QPushButton("Prestige")
        prestige_btn.setFlat(True)
        prestige_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        prestige_btn.setStyleSheet(_prestige_style + " QPushButton { font-weight: bold; }")
        prestige_btn.setToolTip("Open prestige")
        prestige_btn.clicked.connect(on_prestige_click)
    # Prestige holds the middle seat, so inverting swaps only the two around it. Skipping it while
    # locked leaves the row exactly as it was before prestige existed; the outer stretches keep the
    # content centered either way.
    order = [cq_btn, prestige_btn, shop_btn] if invert_buttons else [shop_btn, prestige_btn, cq_btn]
    for btn in order:
        if btn is not None:
            layout.addWidget(btn)

    layout.addStretch(1)
    widget.setMinimumWidth(_bottom_ui_block_min_width(data, lev))
    return widget

_last_center_pad_width = 0

def build_simple_centered_xp_bar_widget(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    on_prestige_click: Callable[[], None],
    streak_widget: QWidget | None = None,
    data: dict | None = None,
) -> QWidget:
    """
    Centered bar for simple (non-dock) mode:

        [grip pad][streak][gap][stretch][bar][stretch][mirror pad]

    The streak sits at the far left but must not drag the bar off-center with it, so an equal-width
    mirror pad is reserved on the right. Both pads are sized by update_simple_bar_centering() once
    real geometry exists.
    """
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    # QStatusBar keeps its size grip outside the area addWidget() lays out in, so stretches alone
    # center the bar within that shortened area — about half a grip-width left of the window center
    # (measured at -12px). This pad restores the balance; the reserve is style-dependent, so it is
    # measured rather than hardcoded.
    grip_pad = QWidget()
    # Seeded from the last measured value rather than left at 0. This widget is rebuilt after every
    # single review, and sizing the pad only from the deferred callback meant each rebuild was shown
    # off-center for one frame and then shifted — a visible twitch on every answer. The reserve does
    # not change between rebuilds, so the remembered value is already correct.
    grip_pad.setFixedWidth(_last_center_pad_width)
    row.addWidget(grip_pad)
    if streak_widget is not None:
        row.addWidget(streak_widget)
        row.addSpacing(_STREAK_GAP)
    row.addStretch()
    bar = build_xp_bar_widget(
        on_progress_click, on_shop_click, on_prestige_click, include_streak=False, data=data
    )
    row.addWidget(bar)
    row.addStretch()
    mirror_pad = QWidget()
    # The streak block's width is known from its size hint before it is ever shown, so the mirror
    # needs no measurement pass at all.
    mirror_pad.setFixedWidth(
        streak_widget.sizeHint().width() + _STREAK_GAP if streak_widget is not None else 0
    )
    row.addWidget(mirror_pad)
    wrapper._collectquest_center_pad = grip_pad
    wrapper._collectquest_mirror_pad = mirror_pad
    wrapper._collectquest_streak = streak_widget
    wrapper._collectquest_bar = bar
    return wrapper

def update_simple_bar_centering(status_bar: QWidget, wrapper: QWidget) -> None:
    """
    Keep the bar centered on the window: compensate for the status bar's right-hand size-grip
    reserve, and mirror the streak block so it does not push the bar right.

    The mirror is dropped when the window is too narrow to afford it, so a cramped window spends its
    width on content and the bar shifts right. Idempotent: it reads the wrapper's geometry, which
    the pads do not change, so repeated calls settle on the same widths.
    """
    global _last_center_pad_width
    grip_pad = getattr(wrapper, "_collectquest_center_pad", None)
    mirror_pad = getattr(wrapper, "_collectquest_mirror_pad", None)
    if grip_pad is None or mirror_pad is None:
        return
    try:
        left_gap = wrapper.x()
        right_gap = status_bar.width() - (wrapper.x() + wrapper.width())
        pad_w = max(0, right_gap - left_gap)
        grip_pad.setFixedWidth(pad_w)
        _last_center_pad_width = pad_w  # so the next rebuild starts already centered

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
    on_prestige_click: Callable[[], None],
    streak_widget: QWidget | None,
    main_window: QWidget | None = None,
    data: dict | None = None,
) -> QWidget:
    """Build the single bottom UI block: one centered group = [7day (optional)] + margin + [level | XP | gold | gems | quests | buttons].
    Outer stretches center the whole group; margin moves the 7-day streak away from the main content."""
    data = storage.load() if data is None else data
    content_group = QWidget()
    group_row = QHBoxLayout(content_group)
    group_row.setContentsMargins(0, 0, 0, 0)
    group_row.setSpacing(0)
    if streak_widget is not None:
        group_row.addWidget(streak_widget)
        group_row.addSpacing(24)
    bar = build_xp_bar_widget(
        on_progress_click, on_shop_click, on_prestige_click, include_streak=False, data=data
    )
    group_row.addWidget(bar)

    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addStretch(1)
    row.addWidget(content_group, 0)
    row.addStretch(1)
    if main_window is not None:
        container.setMinimumWidth(_bottom_ui_block_min_width(data))
    return container

def _bottom_ui_block_min_width(data: dict | None = None, level: int | None = None) -> int:
    """Minimum width for the bottom UI block based on which elements are visible (from storage)."""
    data = storage.load() if data is None else data
    show_level_xp = data.get("bottom_ui_show_level_xp", True)
    show_gold_gems = data.get("bottom_ui_show_gold_gems", False)
    show_quests = data.get("bottom_ui_show_quests", False)
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
    if _prestige_unlocked(data, level):
        # 66, not the stylesheet's max-width of 62: that caps the contents rect, and the padding
        # sits outside it.
        w += 4 + 66  # spacing + Prestige
    return max(_STATUSBAR_BLOCK_MIN, min(520, w))
