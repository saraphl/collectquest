"""Shop content widget and its dialog entry point."""
from __future__ import annotations

from typing import Callable
from aqt.qt import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import tooltip
from .. import shop as shop_mod, storage, streak as streak_mod, xp
from .assets import _label_with_pixmap, _pixmap
from .constants import _POPUP_MAX_WIDTH, _POPUP_SHOP_DIALOG_WIDTH

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
        # Imported here rather than at module scope: docks imports this module to build its panel
        # content, so a top-level import would close the loop. Deferring to click time breaks it.
        from .docks import _dock_shop_panel

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
        # No confirmation tooltip: the refresh below shows the gold drop, the slot marked sold, and
        # the gem counter going up.
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
        # No confirmation tooltip: the refresh below already shows the gold drop, the slot going,
        # and the item appearing in Items.
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
        # No confirmation tooltip: the slots visibly change.
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
            # Rounded up to the next whole minute: the label is drawn once when the panel opens and
            # never ticks, so a seconds figure was stale the moment it appeared. Rounding up also
            # keeps the last minute from reading "0m".
            total_mins = -(-remaining_sec // 60)
            hours, mins = divmod(total_mins, 60)
            remaining_str = f"{hours}h {mins}m" if hours else f"{mins}m"
            timer_lbl = QLabel(f"Auto-refresh in {remaining_str}")
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
