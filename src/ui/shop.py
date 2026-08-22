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
from .constants import _POPUP_MAX_WIDTH, _POPUP_SHOP_DIALOG_OPEN_WIDTH, _POPUP_SHOP_DIALOG_WIDTH

def build_shop_content_widget(
    parent: QWidget,
    on_refresh: Callable[[], None] | None,
    on_close: Callable[[], None],
    for_panel: bool = False,
) -> QWidget:
    """Build the shop UI (gold, daily items, buy/craft, refresh). When for_panel=False (dialog), adds Close button and focuses it; when for_panel=True (dock), no Close and no focus."""
    root = QWidget(parent)
    if for_panel:
        # Dock only: lets it be dragged down to the dock's own minimum, same as the progress panel.
        # Not applied to the dialog, where it let the window open narrower than its own fixed text
        # and clip the "You own all collectibles!" header at larger UI fonts. Without it the layout
        # reports an honest minimum and Qt widens the dialog to fit. Item text still cannot drive
        # that minimum: effect lines are word-wrapped, so they shrink instead of pushing outwards.
        root.setMinimumWidth(1)
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

    def _item_row_widgets(c: dict) -> tuple[QLabel | None, QWidget]:
        """
        Icon and name/effect cell for one collectible, exactly as the "Today's items" rows draw it.

        Shared so the crafted-item row below the Craft button stays identical to the shop rows
        instead of being a copy that drifts the next time either is restyled.
        """
        effect = (c.get("effect_description") or "").strip()
        tip = f"{c.get('name', '')}: {effect}" if effect else c.get("name", "")
        pm = _pixmap(c["image"], 36)
        icon = None
        if pm:
            icon = QLabel()
            icon.setPixmap(pm)
            icon.setToolTip(tip)
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
        return (icon, name_cell)

    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

    def _add_gold_row(layout: QVBoxLayout, money: int) -> None:
        """The player's gold, with the coin icon."""
        gold_row = QHBoxLayout()
        coin_pm = _pixmap("currency/Coin x1.png", 28)
        if coin_pm:
            gold_row.addWidget(_label_with_pixmap(coin_pm, QLabel(f"Your gold: {money}")))
        else:
            gold_row.addWidget(QLabel(f"Your gold: {money}"))
        gold_row.addStretch()
        layout.addLayout(gold_row)

    def _add_gem_counts_row(layout: QVBoxLayout, gems: dict) -> None:
        """One icon and count per gem color."""
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

    def _add_refresh_controls(
        layout: QVBoxLayout, data: dict, money: int, on_click: Callable[[], None]
    ) -> None:
        """Auto-refresh countdown and the manual refresh button, when the player has one.

        Split out so the caller can leave the whole group off: with every collectible owned there is
        no items section for a refresh to change, and the two are only ever shown together.
        """
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
            if shop_mod.has_free_refresh_available(data):
                refresh_btn = QPushButton("Refresh shop")
                refresh_btn.setEnabled(True)
            else:
                refresh_btn = QPushButton(f"Refresh shop ({refresh_cost}g)")
                refresh_btn.setEnabled(money >= refresh_cost)
            refresh_btn.clicked.connect(on_click)
            layout.addWidget(refresh_btn)

    def _trade_message(what: str, xp_added: int, before_level: int, data: dict) -> str:
        """One line for the whole trade: the XP, and the level it reached if it gained any.

        A trade can cross several levels at once, and each pays its level-up gold, so the purse is
        not empty afterwards. Naming the level explains where that came from without a second
        notification.
        """
        msg = f"Traded {what} for +{xp_added} XP!"
        new_level = data.get("level", before_level)
        if new_level > before_level:
            msg += f" Reached level {new_level}!"
        return msg

    def on_trade_gold_for_xp():
        data = storage.load()
        if not shop_mod.all_collectibles_owned(data):
            return
        before_level = data.get("level", 1)
        xp_added = shop_mod.trade_gold_for_xp(data)
        if xp_added <= 0:
            tooltip("No gold to trade.")
            return
        storage.save(data)
        tooltip(_trade_message("gold", xp_added, before_level, data))
        refresh()
        if on_refresh:
            on_refresh()

    def on_trade_gems_for_xp():
        data = storage.load()
        if not shop_mod.all_collectibles_owned(data):
            return
        before_level = data.get("level", 1)
        xp_added = shop_mod.trade_gems_for_xp(data)
        if xp_added <= 0:
            tooltip("No gems to trade.")
            return
        storage.save(data)
        tooltip(_trade_message("gems", xp_added, before_level, data))
        refresh()
        if on_refresh:
            on_refresh()

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

    def on_buy_magnet(slot_index: int):
        data = storage.load()
        slots = data.get("shop_daily_slots", [])
        if slot_index < 0 or slot_index >= len(slots):
            return
        result = shop_mod.buy_magnet(data, slots[slot_index])
        if isinstance(result, str):
            # Names the actual reason: three of the four failures have nothing to do with gold, and
            # the stage can finish between the restock and the click if a bonus quest dropped the
            # Magnet that filled it.
            tooltip(shop_mod.MAGNET_BUY_MESSAGES.get(result, "Could not buy that."))
            return
        storage.save(data)
        # The only case worth a message: the last Magnet of a stage arrived and the accumulator got
        # faster. A Magnet that merely counts is reported by the row going Sold and the milestones
        # window's count moving, the same way a gem purchase reports itself.
        if isinstance(result, dict):
            tooltip(shop_mod.milestones_stage_message(result))
        refresh()
        if on_refresh:
            on_refresh()

    def on_buy(cid: str):
        data = storage.load()
        c = shop_mod.get_collectible(cid)
        if not c or cid in data.get("owned_collectibles", []):
            return
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        cost = shop_mod.effective_cost_gold(c, level, data)
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
            if not shop_mod.can_craft(data.get("gems", shop_mod.default_gems()), data):
                tooltip("Need 1 of each gem color (5 total) to get a random item.")
            else:
                tooltip("You already own every collectible available at your level!")
            return
        # Shown as a row under the Craft button by the rebuild below, rather than as a tooltip: the
        # item's icon and effect say more than a line of text, and the tooltip was competing with
        # every other notification for the same slot.
        data["shop_last_crafted_id"] = cid
        storage.save(data)
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
        level = xp.level_from_total_xp(data.get("total_xp", 0))
        all_owned = shop_mod.all_collectibles_owned(data)
        # Only when the grid will be drawn: get_daily_slots rolls the day's slots and mutates data,
        # which the save below then persists, and the trading layout renders no items at all.
        owned: set[str] = set()
        daily_slots: list = []
        if not all_owned:
            owned = set(data.get("owned_collectibles", []))
            daily_slots = shop_mod.get_daily_slots(data, level)
        storage.save(data)

        # --- TOP section (aligned to top): the trade header, or gold and the day's items ---
        if all_owned:
            layout.addWidget(QLabel("You own all collectibles! Convert resources to XP:"))
            layout.addSpacing(8)
            total_xp = data.get("total_xp", 0)
            current_level = xp.level_from_total_xp(total_xp)
            layout.addWidget(QLabel(f"Level {current_level} — {total_xp} XP total"))
        else:
            # Gold heads the shop while it still buys something. On the trading layout it moves
            # down instead, to sit directly above the button that spends it.
            _add_gold_row(layout, money)
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
                    icon, name_cell = _item_row_widgets(c)
                    if icon is not None:
                        daily_grid.addWidget(icon, r, 0)
                    daily_grid.addWidget(name_cell, r, 1)
                    if cid in owned:
                        daily_grid.addWidget(QLabel("(owned)"), r, 2)
                        daily_grid.addWidget(QLabel(""), r, 3)
                    else:
                        cost = shop_mod.effective_cost_gold(c, level, data)
                        daily_grid.addWidget(QLabel(f"{cost}g"), r, 2)
                        buy_btn = QPushButton("Buy")
                        buy_btn.setStyleSheet("padding: 0 5px;")
                        buy_btn.setEnabled(money >= cost)
                        buy_btn.clicked.connect(lambda checked=False, cid=cid: on_buy(cid))
                        daily_grid.addWidget(buy_btn, r, 3)
                elif slot.get("type") == "magnet":
                    # The same icon the milestones window counts them with, so the thing found in
                    # the shop and the thing counted in the window are visibly one object.
                    sold = slot.get("sold", False)
                    cost = shop_mod.slot_cost(data, slot, shop_mod.MAGNET_COST_GOLD)
                    pm = _pixmap("ui/magnet.png", 28)
                    if pm:
                        icon = QLabel()
                        icon.setPixmap(pm)
                        daily_grid.addWidget(icon, r, 0)
                    daily_grid.addWidget(QLabel("Magnet"), r, 1)
                    buy_btn = QPushButton("Buy")
                    buy_btn.setStyleSheet("padding: 0 5px;")
                    if sold:
                        daily_grid.addWidget(QLabel("Sold"), r, 2)
                        buy_btn.setEnabled(False)
                    else:
                        daily_grid.addWidget(QLabel(f"{cost}g"), r, 2)
                        buy_btn.setEnabled(money >= cost)
                        buy_btn.clicked.connect(lambda checked=False, idx=r: on_buy_magnet(idx))
                    daily_grid.addWidget(buy_btn, r, 3)
                else:
                    sold = slot.get("sold", False)
                    cost = shop_mod.slot_cost(data, slot)
                    if slot.get("random"):
                        pm = _pixmap("gems/Gem - Blue.png", 28)
                        label = "1 random gem"
                    else:
                        color = slot.get("color", "")
                        img_name = next((img for col, img in shop_mod.GEM_COLORS if col == color), "gems/Gem - Blue.png")
                        pm = _pixmap(img_name, 28)
                        # A most-needed slot names what it is for rather than the color it holds —
                        # the icon beside it already says which color, and the player is buying it
                        # for the gap it fills.
                        label = "Most needed gem" if slot.get("most_needed") else f"{color.capitalize()} gem"
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
        # No heading while trading: the "You own all collectibles" line above already says what this
        # section is, and each currency is labeled by the row and button it sits between. A heading
        # would only name a section that no longer has an alternative.
        if not all_owned:
            # Unstyled, like "Today's items": both are section headings and should read the same.
            layout.addWidget(QLabel("Gem crafting"))
            # Only while crafting is still possible: with every item owned there is no button to
            # follow this, and an instruction to craft would be telling the player to do something
            # the shop no longer offers.
            # Says which pool the craft draws from, because targeted craft changes it and a label
            # still promising "some are gem-only" would be describing the pool it replaced.
            gem_info_lbl = QLabel(
                "Craft a random gem-only item — the ones the shop never sells."
                if shop_mod.craft_pool_is_targeted(data, level)
                else "Craft a random item with gems. Some are gem-only!"
            )
            gem_info_lbl.setStyleSheet("font-size: 10px; color: #666;")
            layout.addWidget(gem_info_lbl)

        if all_owned:
            # Each currency directly above the button that spends it, gold first, so the two trades
            # read as a pair rather than as two buttons after a shared pile of resources.
            _add_gold_row(layout, money)

            # Rates read from the constants rather than written out, so the label cannot promise one
            # exchange while trade_gold_for_xp/trade_gems_for_xp perform another. "all" is load-
            # bearing: both trades empty the purse or the gem pile outright, and saying so in the
            # label is what the removed tooltips were really for. The rest of what they said — the
            # rate, and a condition the player had plainly met to be seeing the button — was already
            # on screen.
            gold_rate = shop_mod.TRADE_GOLD_TO_XP_RATE
            gem_rate = shop_mod.TRADE_GEM_TO_XP_RATE
            trade_gold_btn = QPushButton(f"Trade all gold for XP (1g = {gold_rate} XP)")
            # Disabled with nothing to trade, like the craft button whose place this took. The
            # zero guard inside trade_gold_for_xp stays as the authority; this only stops the
            # button from offering an exchange that would do nothing.
            trade_gold_btn.setEnabled(money > 0)
            trade_gold_btn.clicked.connect(on_trade_gold_for_xp)
            layout.addWidget(trade_gold_btn)

            layout.addSpacing(8)
            _add_gem_counts_row(layout, gems)

            trade_gems_btn = QPushButton(f"Trade all gems for XP (1 gem = {gem_rate} XP)")
            trade_gems_btn.setEnabled(sum(gems.values()) > 0)
            trade_gems_btn.clicked.connect(on_trade_gems_for_xp)
            layout.addWidget(trade_gems_btn)
        else:
            _add_gem_counts_row(layout, gems)
            can_craft = shop_mod.can_craft(gems, data)
            # The label states what the craft will actually charge. While the discount buff runs
            # that is four colors rather than five, and a button still promising "1 gem of each"
            # would be the one place in the shop that disagreed with the spend.
            craft_colors = shop_mod.craft_required_colors(gems, data)
            all_colors = [c for c, _ in shop_mod.GEM_COLORS]
            waived = [c for c in all_colors if c not in craft_colors]
            spend_gems_btn = QPushButton(
                "Craft (1 gem of each)"
                if not waived
                else f"Craft ({len(craft_colors)} gems, no {waived[0]})"
            )
            spend_gems_btn.setEnabled(can_craft)
            spend_gems_btn.clicked.connect(on_spend_gems)
            layout.addWidget(spend_gems_btn)

        # Outside the guard above: a completed collection still has a last craft worth naming, and
        # the row is a record of what happened rather than an invitation to craft again.
        last_crafted_id = data.get("shop_last_crafted_id")
        crafted = shop_mod.get_collectible(last_crafted_id) if last_crafted_id else None
        if crafted:
            layout.addWidget(QLabel("Last crafted item"))
            crafted_row = QHBoxLayout()
            crafted_row.setContentsMargins(0, 0, 0, 0)
            icon, name_cell = _item_row_widgets(crafted)
            if icon is not None:
                crafted_row.addWidget(icon)
            crafted_row.addWidget(name_cell, 1)
            layout.addLayout(crafted_row)
            if crafted.get("cost_gold") is None:
                gem_only_lbl = QLabel("This is a gem-only item!")
                gem_only_lbl.setStyleSheet("color: #666; font-size: 11px;")
                layout.addWidget(gem_only_lbl)

        # Only while there is something to refresh. With every item owned the items section is
        # gone, so a reroll changes nothing the player can see — and the paid button would charge
        # gold that is now worth only the XP it trades for.
        if not all_owned:
            _add_refresh_controls(layout, data, money, on_refresh_shop)

        if add_close:
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(close_callback)
            layout.addWidget(close_btn)
            QTimer.singleShot(0, close_btn.setFocus)

    def _refit_dialog_height() -> None:
        """Shrink the dialog back to the height its content now needs.

        Qt grows a window when the rebuilt content asks for more room, but never shrinks it again.
        A rebuild that ends up shorter — crafting a normal item after a gem-only one drops the
        "This is a gem-only item!" line, and a reroll can rewrap an effect onto one line — therefore
        left the window at its old height, and the leftover went to the stretch above "Gem crafting"
        as a band of empty space. Width is kept as it is: only the height is chosen by the content.

        Deferred by a timer so the new widgets have been laid out and sizeHint() is the rebuilt
        content's, not the one that just went away. The dock panel is excluded: its size belongs to
        the dock (and to whatever the player dragged it to), not to the content.
        """
        try:
            win = root.window()
            if win is None:
                return
            wanted = win.sizeHint().height()
            if win.height() > wanted:
                win.resize(win.width(), wanted)
        except RuntimeError:
            pass  # dialog closed before the timer fired

    def refresh() -> None:
        _clear_layout(content_layout)
        _build_shop_content(content_layout, on_close, add_close=not for_panel)
        if not for_panel:
            QTimer.singleShot(0, _refit_dialog_height)

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
    layout = QVBoxLayout(d)
    layout.addWidget(build_shop_content_widget(d, on_refresh, d.accept, for_panel=False))

    # Every width bound starts from what the content actually needs, then the constants widen it —
    # not the other way round. An explicit setMinimumWidth overrides minimumSizeHint entirely, so
    # pinning the minimum to the constant let the dialog sit narrower than its own fixed text and
    # clip the "You own all collectibles!" header, which outgrows the constants at larger UI fonts.
    # A maximum below that minimum would clip it just the same, so the cap is raised to match.
    #
    # This does not reopen what the fixed width was guarding against: item effect lines are
    # word-wrapped, so they shrink rather than push outwards, and editing an item's text still
    # cannot resize the dialog. Only the fixed interface strings set this floor.
    needed_width = d.minimumSizeHint().width()
    d.setMinimumWidth(max(_POPUP_SHOP_DIALOG_WIDTH, needed_width))
    d.setMaximumWidth(max(_POPUP_MAX_WIDTH, needed_width))

    # Opens at the constant unless the content needs more, so the ordinary shop is unchanged and
    # only the completed-collection layout widens. Qt clamps the height to whatever the reflow asks.
    def _set_initial_width() -> None:
        d.resize(max(_POPUP_SHOP_DIALOG_OPEN_WIDTH, needed_width), d.sizeHint().height())

    QTimer.singleShot(0, _set_initial_width)
    d.exec()
