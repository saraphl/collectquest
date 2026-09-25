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
    QTimer,
    QWidget,
    Qt,
)
from .. import dungeon as dungeon_mod, quests, shop as shop_mod, storage, streak as streak_mod, xp
from .assets import _pixmap, attention_color
from .constants import _STATUSBAR_BLOCK_MIN, _STATUSBAR_BLOCK_PREFERRED, _STATUSBAR_STREAK_AREA_WIDTH, _STREAK_EMPTY_COLOR, _STREAK_FILLED_COLOR, _STREAK_GAP, _STREAK_GIFT_IMAGES
from .hover_tip import set_hover_tip

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
            set_hover_tip(gift_lbl, "7-day streak reward")
            row.addWidget(gift_lbl)
    set_hover_tip(w, f"Streak: {streak_days}/7 days. Study every day for a reward!")
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
    """Build the status bar's 7-day streak widget. `data` is an already-loaded save, as for every
    builder here, so a rebuild doesn't re-read the file."""
    data = storage.load() if data is None else data
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
    data: dict | None = None,
    on_dungeon_click: Callable[[], None] | None = None,
) -> QWidget:
    """Build status bar widget: level, XP bar, gold, gems, [optional streak], Shop, CollectQuest.
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
    today = streak_mod.today_str()
    reviews_today = shop_mod.reviews_counted_today(data, today)
    shop_enabled = shop_mod.is_open_today(data, today)

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
        # Same fixed order the CollectQuest panel renders, so the bare pairs here can be read
        # against its rows: without it the two views list the day's quests differently.
        try:
            from aqt import mw as _mw
            _quest_col = getattr(_mw, "col", None)
        except Exception:
            _quest_col = None
        daily_quests = sorted(data.get("daily_quests", []), key=quests.quest_display_order)
        if daily_quests:
            parts = [f"{q.get('progress', 0)}/{q.get('target', 0)}" for q in daily_quests]
            quest_text = " • ".join(parts)
            # Label rebuilt rather than read from the save, so a renamed deck reads correctly
            # here as well as in the panel.
            quest_tooltip = "Daily quests:\n" + "\n".join(
                f"  {quests.quest_display_label(q, _quest_col)}: "
                f"{q.get('progress', 0)}/{q.get('target', 0)}"
                for q in daily_quests
            )
            quest_lbl = QLabel(f"Q: {quest_text}")
            quest_lbl.setStyleSheet("color: #555; font-size: 11px;")
            set_hover_tip(quest_lbl, quest_tooltip)
            quest_lbl.setMinimumWidth(60)
            layout.addWidget(quest_lbl)
            layout.addSpacing(6)

    # Shop: small padding; CollectQuest: no inner padding (stylesheet + no icon area so text isn't truncated).
    _shop_style = "QPushButton { padding: 1px 4px; margin: 0; font-size: 11px; min-width: 44px; max-width: 50px }"
    _cq_style = "QPushButton { padding: 1px 2px; margin: 0; font-size: 11px; min-width: 80px; max-width: 110px; border: none; }"
    _dungeon_style = "QPushButton { padding: 1px 4px; margin: 0; font-size: 11px; min-width: 58px; max-width: 64px }"
    shop_btn = QPushButton("Shop")
    shop_btn.setFlat(True)
    shop_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    shop_btn.setEnabled(True)
    # No explicit color when unlocked, so it inherits the theme's text color; locked stays dimmed.
    _shop_enabled_style = _shop_style + " QPushButton { font-weight: bold; }"
    _shop_locked_style = _shop_style + " QPushButton { color: #666; }"
    shop_btn.setStyleSheet(_shop_enabled_style if shop_enabled else _shop_locked_style)
    if not shop_enabled:
        set_hover_tip(shop_btn, f"Click to see when shop unlocks — {reviews_today}/{shop_mod.SHOP_MIN_REVIEWS} reviews today")
    shop_btn.clicked.connect(on_shop_click)
    cq_btn = QPushButton("CollectQuest")
    cq_btn.setFlat(True)
    cq_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    cq_btn.setStyleSheet(_cq_style + " QPushButton { font-weight: bold; }")
    cq_btn.clicked.connect(on_progress_click)

    dungeon_btn = None
    # Only while a dungeon is open; otherwise it's reachable from the CollectQuest window.
    if on_dungeon_click is not None and dungeon_mod.is_active(data):
        dungeon_btn = QPushButton("Dungeon")
        dungeon_btn.setFlat(True)
        dungeon_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        style = _dungeon_style + " QPushButton { font-weight: bold; }"
        if dungeon_mod.pending(data) or dungeon_mod.treasure_ready(data):
            # Needs the player (a branching or a treasure): outline and colored text, no fill, so
            # the button keeps its shape.
            accent = attention_color()
            style += (
                " QPushButton { border: 1px solid %s; border-radius: 3px; color: %s; }"
                % (accent, accent)
            )
            set_hover_tip(dungeon_btn, "Your dungeon is waiting for you")
        dungeon_btn.setStyleSheet(style)
        dungeon_btn.clicked.connect(on_dungeon_click)

    # Shop and CollectQuest keep the outside edges (the invert option swaps them); the transient
    # Dungeon button sits between.
    first, last = (cq_btn, shop_btn) if invert_buttons else (shop_btn, cq_btn)
    for btn in (first, dungeon_btn, last):
        if btn is not None:
            layout.addWidget(btn)

    layout.addStretch(1)
    widget.setMinimumWidth(_bottom_ui_block_min_width(data))
    return widget

_last_center_pad_width = 0

def build_simple_centered_xp_bar_widget(
    on_progress_click: Callable[[], None],
    on_shop_click: Callable[[], None],
    streak_widget: QWidget | None = None,
    data: dict | None = None,
    on_dungeon_click: Callable[[], None] | None = None,
) -> QWidget:
    """
    Centered bar for simple (non-dock) mode:

        [grip pad][streak][gap][stretch][bar][stretch][mirror pad]

    The mirror pad offsets the streak so the bar stays centered; update_simple_bar_centering() sizes
    both pads.
    """
    wrapper = QWidget()
    row = QHBoxLayout(wrapper)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    # QStatusBar's size grip sits outside the addWidget() area, pulling the bar about half a grip
    # left; this pad, measured per style, restores the balance.
    grip_pad = QWidget()
    # Seeded from the last measured value, or every per-review rebuild twitches for a frame.
    grip_pad.setFixedWidth(_last_center_pad_width)
    row.addWidget(grip_pad)
    if streak_widget is not None:
        row.addWidget(streak_widget)
        row.addSpacing(_STREAK_GAP)
    row.addStretch()
    bar = build_xp_bar_widget(on_progress_click, on_shop_click, include_streak=False, data=data,
                              on_dungeon_click=on_dungeon_click)
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
    """Keep the bar centered: offset the size-grip reserve and mirror the streak block, dropping the
    mirror when the window is too narrow. Idempotent."""
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
    streak_widget: QWidget | None,
    main_window: QWidget | None = None,
    data: dict | None = None,
    on_dungeon_click: Callable[[], None] | None = None,
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
    bar = build_xp_bar_widget(on_progress_click, on_shop_click, include_streak=False, data=data,
                              on_dungeon_click=on_dungeon_click)
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

def _bottom_ui_block_min_width(data: dict | None = None) -> int:
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
    # Conditional, because the Dungeon button comes and goes: reserving its width the rest of the
    # time would leave a gap in the bar for a button that is not there.
    if dungeon_mod.is_active(data):
        w += 4 + 68  # spacing + Dungeon
    return max(_STATUSBAR_BLOCK_MIN, min(520, w))


def _center_block_min(data: dict) -> int:
    """The dock-mode center block's minimum: the bar's plus the streak, so neither is squeezed."""
    show_streak = data.get("bottom_ui_show_streak", False)
    # +8 so the right edge (Shop/CQ) isn't truncated.
    return _bottom_ui_block_min_width(data) + 24 + (_STATUSBAR_STREAK_AREA_WIDTH if show_streak else 0) + 8


def _center_content_width(mw: QWidget) -> int:
    """Width of the dock-mode center block. Its minimum is stored at mount, since this also runs on
    every window resize."""
    center_w = getattr(mw, "_collectquest_xp_widget", None)
    block_min = getattr(center_w, "_collectquest_block_min", None)
    if block_min is None:
        block_min = _center_block_min(storage.load())
    if center_w is not None:
        sh = center_w.sizeHint().width()
        if sh > 0:
            return max(block_min, min(600, sh))
    return max(block_min, _STATUSBAR_BLOCK_PREFERRED)


def _right_panel_block_width(mw: QWidget) -> int:
    """2/3 of the widest panel docked on the right, the share it takes from the main area; 0 when
    none is (floating panels take nothing)."""
    panel_w = 0
    for dock_attr in ("_collectquest_dock", "_collectquest_shop_dock"):
        dock = getattr(mw, dock_attr, None)
        if dock is None or not dock.isVisible() or dock.isFloating():
            continue
        try:
            if mw.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea:
                panel_w = max(panel_w, dock.width())
        except Exception:
            pass
    return int(panel_w * 2 / 3) if panel_w > 0 else 0


def update_center_width(mw: QWidget) -> None:
    """Resize the dock-mode center block and the right-panel compensation, so the bar stays centered
    over the main area."""
    block_w = getattr(mw, "_collectquest_statusbar_center_block", None)
    if block_w is None:
        return
    block_w.setFixedWidth(_center_content_width(mw))
    right_block_w = getattr(mw, "_collectquest_statusbar_right_panel_block", None)
    if right_block_w is not None:
        right_block_w.setFixedWidth(_right_panel_block_width(mw))


def _remove_bar_widget(sb: QWidget, mw: QWidget, attr: str) -> None:
    widget = getattr(mw, attr, None)
    if widget is not None:
        try:
            sb.removeWidget(widget)
            widget.deleteLater()
        except Exception:
            pass
    setattr(mw, attr, None)


def _remove_dock_container(sb: QWidget, mw: QWidget) -> None:
    container = getattr(mw, "_collectquest_statusbar_container", None)
    if container is None or container.parent() is None:
        return
    sb.removeWidget(container)
    container.deleteLater()
    mw._collectquest_statusbar_container = None
    mw._collectquest_statusbar_center_block = None
    mw._collectquest_statusbar_right_panel_block = None
    mw._collectquest_xp_widget = None


def _mount_simple(sb: QWidget, mw: QWidget, streak_w: QWidget | None, data: dict, on_progress, on_shop, on_dungeon) -> None:
    """Simple mode: one status bar item holding the optional streak plus the bar, the streak inside it
    so its width can be mirrored and the bar stays centered."""
    for dock_attr in ("_collectquest_dock", "_collectquest_shop_dock"):
        dock = getattr(mw, dock_attr, None)
        if dock is not None and getattr(dock, "isVisible", None):
            try:
                dock.setVisible(False)
            except Exception:
                pass
    _remove_dock_container(sb, mw)
    _remove_bar_widget(sb, mw, "_collectquest_xp_widget")
    center_w = build_simple_centered_xp_bar_widget(
        on_progress, on_shop, streak_widget=streak_w, data=data, on_dungeon_click=on_dungeon,
    )
    mw._collectquest_xp_widget = center_w
    sb.addWidget(center_w, 1)

    # Re-balance against the status bar's size-grip reserve, now and on every window resize.
    def _recenter() -> None:
        update_simple_bar_centering(sb, center_w)

    mw._collectquest_update_statusbar_center_width = _recenter
    QTimer.singleShot(0, _recenter)


def _mount_dock_mode(sb: QWidget, mw: QWidget, block: QWidget) -> bool:
    """Dock mode: stretch, block, stretch, right-panel compensation. Swaps the block into an existing
    container when there is one; returns True when a new container was built."""
    if getattr(mw, "_collectquest_statusbar_container", None) is None:
        _remove_bar_widget(sb, mw, "_collectquest_xp_widget")

    container = getattr(mw, "_collectquest_statusbar_container", None)
    if container is not None and container.parent() is not None:
        old_block = mw._collectquest_statusbar_center_block
        layout = container.layout()
        if old_block is not None and layout is not None and layout.count() >= 3:
            layout.removeWidget(old_block)
            layout.insertWidget(1, block, 0)
            old_block.deleteLater()
            mw._collectquest_statusbar_center_block = block
            mw._collectquest_xp_widget = block
            update_center_width(mw)
            return False
        _remove_dock_container(sb, mw)

    right_panel_block = QWidget()
    right_panel_block.setFixedWidth(0)
    mw._collectquest_statusbar_center_block = block
    mw._collectquest_statusbar_right_panel_block = right_panel_block
    mw._collectquest_xp_widget = block
    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addStretch(1)
    row.addWidget(block, 0)
    row.addStretch(1)
    row.addWidget(right_panel_block, 0)
    mw._collectquest_statusbar_container = container
    mw._collectquest_update_statusbar_center_width = lambda: update_center_width(mw)
    update_center_width(mw)
    sb.addWidget(container, 1)
    return True


def mount_status_bar(
    mw: QWidget,
    data: dict,
    streak_count: int,
    on_progress: Callable[[], None],
    on_shop: Callable[[], None],
    on_dungeon: Callable[[], None],
) -> bool:
    """(Re)build the bottom bar in Anki's status bar for the current mode. Returns True when dock mode
    built a fresh container, i.e. when saved panels should be restored."""
    sb = mw.statusBar()
    streak_w = (
        build_streak_widget(streak_count=streak_count, data=data)
        if data.get("bottom_ui_show_streak", False)
        else None
    )
    if not data.get("use_dock_panels", False):
        _mount_simple(sb, mw, streak_w, data, on_progress, on_shop, on_dungeon)
        return False
    block = build_bottom_ui_block(on_progress, on_shop, streak_w, mw, data=data, on_dungeon_click=on_dungeon)
    block._collectquest_block_min = _center_block_min(data)
    return _mount_dock_mode(sb, mw, block)
