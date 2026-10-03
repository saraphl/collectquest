from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from aqt.qt import (
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    QPushButton,
    QStyle,
)
from aqt.utils import showInfo, tooltip

from .. import due_baseline, prestige as prestige_mod, quests, review_rewards, shop as shop_mod, storage, streak as streak_mod, xp
from .assets import equalize_button_widths, exec_dialog
from .hover_tip import set_hover_tip


# Selected difficulty chip: both colors pinned per theme, since dark mode's white text is unreadable
# on the light-mode pale chip.
_DIFF_SELECTED_LIGHT = ("#d0e8ff", "#14304a")
_DIFF_SELECTED_DARK = ("#2f5a86", "#eaf2ff")

# Bottom bar checkboxes: (save key, label, default).
_BOTTOM_BAR_OPTIONS = (
    ("bottom_ui_show_streak", "Show 7-day streak bar", False),
    ("bottom_ui_show_level_xp", "Show Level/XP bar", True),
    ("bottom_ui_show_gold_gems", "Show gold/gems", False),
    ("bottom_ui_show_quests", "Show quests", False),
    ("bottom_ui_invert_buttons", "Invert button order (Shop ↔ CollectQuest)", False),
)

# Category the window last showed, so reopening it lands on the same page this session.
_last_page = 0


def _fmt_xp(value: float) -> str:
    """XP for display: one decimal, but no trailing '.0' on whole numbers (9 XP, not 9.0 XP)."""
    return f"{value:.1f}".removesuffix(".0")


def _selected_difficulty_colors() -> tuple[str, str]:
    """(background, text) for the active difficulty button, matched to the current Anki theme."""
    from .assets import night_mode

    return _DIFF_SELECTED_DARK if night_mode() else _DIFF_SELECTED_LIGHT


def _add_page(nav: QListWidget, stack: QStackedWidget, title: str) -> QVBoxLayout:
    """Add a category to the list and return its page's (top-aligned) layout."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    nav.addItem(title)
    stack.addWidget(page)
    return layout


def show_options_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None],
) -> None:
    """CollectQuest options: categories on the left, their settings on the right. Admin appears only
    with admin.txt at the add-on root. on_refresh runs after any action to update the status bar."""
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Options")
    outer = QVBoxLayout(d)

    # Late import to avoid circular import at module load time: docks imports this module for the
    # Options button, and these siblings sit on the far side of that edge.
    from .assets import _admin_enabled
    from .constants import _COLLECTQUEST_PANEL_WIDTH, _DIALOG_BUTTON_MIN_WIDTH
    from .notifications import maybe_show_onboarding, maybe_show_update_popup
    from .prestige import show_game_finished_dialog

    body = QHBoxLayout()
    body.setSpacing(12)
    nav = QListWidget()
    stack = QStackedWidget()
    body.addWidget(nav)
    body.addWidget(stack, 1)
    outer.addLayout(body)
    _checked = Qt.CheckState.Checked.value

    # ===== Gameplay =====
    layout = _add_page(nav, stack, "Gameplay")
    layout.addWidget(QLabel("Difficulty (XP per review):"))
    diff_row = QHBoxLayout()
    # Stated rather than inherited: an inherited spacing() can report the vertical metric, and
    # fit_save_box sizes the save row from this gap.
    diff_row.setSpacing(max(d.style().pixelMetric(QStyle.PixelMetric.PM_LayoutHorizontalSpacing), 6))
    diff_btns: dict[str, QPushButton] = {}
    diff_desc = QLabel()
    diff_desc.setStyleSheet("color: #666; font-size: 11px;")

    def show_difficulty() -> None:
        """Style the active chip and say what a Good answer pays now. Re-read on each change."""
        data = storage.load()
        current = data.get("difficulty", "normal")
        bg, fg = _selected_difficulty_colors()
        for diff_id, btn in diff_btns.items():
            btn.setChecked(diff_id == current)
            btn.setStyleSheet(
                f"QPushButton {{ font-weight: bold; background-color: {bg}; color: {fg}; }}"
                if diff_id == current
                else ""
            )
        # The pure helper, since the awarding one would spend the carry.
        good_xp = review_rewards.review_xp_exact(
            data, 3, xp.xp_for_review(3), data.get("owned_collectibles", [])
        )
        diff_desc.setText(
            f"Receiving {_fmt_xp(good_xp)} XP per review.\n"
            "Quest targets follow your real due count, not difficulty."
        )

    def make_diff_btn(diff_id: str, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setCheckable(True)

        def on_click():
            data = storage.load()
            data["difficulty"] = diff_id
            storage.save(data)
            xp.set_difficulty(diff_id)
            on_refresh()
            show_difficulty()
            fit_save_box()
            refresh_save_box()

        btn.clicked.connect(on_click)
        diff_btns[diff_id] = btn
        return btn

    diff_row.addWidget(make_diff_btn("easy", "Casual"))
    diff_row.addWidget(make_diff_btn("normal", "Steady"))
    diff_row.addWidget(make_diff_btn("hard", "Heavy User"))
    diff_row.addStretch()
    layout.addLayout(diff_row)
    show_difficulty()
    layout.addWidget(diff_desc)

    # --- Save: one input shows current save; replace with another and click Load to load ---
    layout.addSpacing(12)
    last_saved_lbl = QLabel()
    layout.addWidget(last_saved_lbl)
    save_edit = QPlainTextEdit()
    save_edit.setMaximumHeight(60)
    save_edit.setStyleSheet("font-family: monospace; font-size: 10px;")
    layout.addWidget(save_edit)
    shown_blob = [""]  # what the box was last filled with, to tell a pasted save apart

    def refresh_save_box() -> None:
        """Show the save as it is now, after anything in this window wrote it. A save pasted into
        the box for Load is left alone."""
        data = storage.load()
        last_saved_lbl.setText(f"Last saved: {data.get('last_saved_at', '') or '(never saved)'}")
        if save_edit.toPlainText().strip() != shown_blob[0]:
            return
        try:
            data.pop("_hash_invalid", None)
            if not data.get("_hash"):
                data["last_saved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                data["saved_with_version"] = storage.get_version()
                data["_hash"] = storage.compute_hash(data)
            blob = storage.encode_to_hashsave(data)
        except Exception as e:
            blob = ""
            showInfo(f"Could not load save for box: {e}")
        shown_blob[0] = blob
        save_edit.setPlainText(blob)

    refresh_save_box()

    def fit_save_box() -> None:
        """End the save box and its buttons where the difficulty row ends (Reset matches Copy); the
        bold active chip shifts that edge."""
        widths = [b.sizeHint().width() for b in diff_btns.values()]
        gap = diff_row.spacing()
        total = sum(widths) + gap * (len(widths) - 1)
        save_edit.setFixedWidth(total)
        copy_save_btn.setFixedWidth((total - gap) // 2)
        reset_btn.setFixedWidth((total - gap) // 2)
        load_save_btn.setFixedWidth(total - gap - (total - gap) // 2)

    def do_copy_save():
        blob = save_edit.toPlainText().strip()
        if blob:
            QApplication.clipboard().setText(blob)
            tooltip("Save copied to clipboard.")
        else:
            showInfo(
                "Nothing to copy. Paste a save into the box first, or the box should show current save when you open Options."
            )

    def do_load_save():
        blob = save_edit.toPlainText().strip()
        if not blob:
            showInfo("Paste a save into the box above, then click Load save.")
            return
        try:
            imported = storage.decode_from_hashsave(blob)
        except Exception as e:
            showInfo(f"Invalid save data: {e}")
            return
        if "_hash" not in imported:
            showInfo("This save has no hash; it may be from an older add-on.")
            return
        expected = imported["_hash"]
        actual = storage.compute_hash(imported)
        if expected != actual:
            showInfo("Hash mismatch: save may be corrupted or modified. Load aborted.")
            return
        imported = storage._migrate(imported)
        imp_date = imported.get("last_saved_at", "") or "(unknown)"
        cur_date = storage.load().get("last_saved_at", "") or "(never)"
        older = ""
        if imp_date != "(unknown)" and cur_date != "(never)" and imp_date < cur_date:
            older = "\n\nWarning: this save is older than your current save."
        imp_ver = imported.get("saved_with_version", "") or "?"
        cur_ver = storage.get_version() or "?"
        ver_warn = ""
        if imp_ver != cur_ver:
            ver_warn = f"\n\nWarning: save was made with version {imp_ver}; current is {cur_ver}."
        reply = QMessageBox.question(
            parent or d,
            "Load save",
            f"Overwrite current save?{older}{ver_warn}\n\nSave from: {imp_date}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        storage.save(imported)
        tooltip("Save loaded. Progress updated.")
        d.accept()
        QTimer.singleShot(0, on_refresh)

    save_btn_row = QHBoxLayout()
    save_btn_row.setSpacing(diff_row.spacing())
    copy_save_btn = QPushButton("Copy save")
    copy_save_btn.clicked.connect(do_copy_save)
    save_btn_row.addWidget(copy_save_btn)
    load_save_btn = QPushButton("Load save")
    load_save_btn.clicked.connect(do_load_save)
    save_btn_row.addWidget(load_save_btn)
    save_btn_row.addStretch()
    layout.addLayout(save_btn_row)

    def do_reset():
        reply = QMessageBox.question(
            parent or d,
            "Reset progress",
            "This will delete all progress (XP, level, gold, gems, collectibles, quests).\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        storage.reset()
        data = storage.load()
        from aqt import mw as _mw

        # storage.reset() already left last_date empty, so ensure_daily_quests treats this as a new
        # day: it captures a fresh due baseline, rolls quests sized from it and zeroes the counters.
        quests.ensure_daily_quests(data, col=getattr(_mw, "col", None))

        max_revlog_id = 0
        if getattr(_mw, "col", None):
            try:
                max_revlog_id = int(_mw.col.db.scalar("SELECT MAX(id) FROM revlog") or 0)
                if max_revlog_id:
                    data["last_processed_revlog_id"] = max_revlog_id
            except Exception as e:
                print(f"CollectQuest reset error: {e}")
        storage.save(data)
        on_refresh()
        tooltip(f"Progress reset. (revlog_id={max_revlog_id})")
        d.accept()

    layout.addSpacing(12)
    reset_btn = QPushButton("Reset progress")
    set_hover_tip(reset_btn, "Delete all game data (with confirmation)")
    reset_btn.clicked.connect(do_reset)
    layout.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    fit_save_box()
    QTimer.singleShot(0, fit_save_box)  # again once shown: some styles change button hints on polish

    # ===== Bottom bar =====
    layout = _add_page(nav, stack, "Bottom bar")

    def _save_bottom_bar_opt(key: str, value: bool) -> None:
        data = storage.load()
        data[key] = value
        storage.save(data)
        on_refresh()
        QApplication.processEvents()
        refresh_save_box()

    opts = storage.load()
    for key, label, default in _BOTTOM_BAR_OPTIONS:
        cb = QCheckBox(label)
        cb.setChecked(opts.get(key, default))
        cb.stateChanged.connect(lambda s, k=key: _save_bottom_bar_opt(k, s == _checked))
        layout.addWidget(cb)

    layout.addSpacing(12)
    cb_dock = QCheckBox("Experimental: Enable drag-and-drop side panels")
    cb_dock.setChecked(opts.get("use_dock_panels", False))
    set_hover_tip(cb_dock, "Use dockable Progress/Shop panels instead of popup dialogs. Disable for the classic popup behavior.")
    cb_dock.stateChanged.connect(lambda s: _save_bottom_bar_opt("use_dock_panels", s == _checked))
    layout.addWidget(cb_dock)

    # ===== Notifications =====
    layout = _add_page(nav, stack, "Notifications")
    layout.addWidget(QLabel("Show a notification for:"))

    def _save_notification_opt(kind: str, value: bool) -> None:
        data = storage.load()
        data.setdefault("notifications", {})[kind] = value
        storage.save(data)
        refresh_save_box()

    for kind, label in storage.NOTIFICATION_KINDS:
        cb = QCheckBox(label)
        cb.setChecked(storage.notification_enabled(kind, opts))
        cb.stateChanged.connect(lambda s, k=kind: _save_notification_opt(k, s == _checked))
        layout.addWidget(cb)

    # ===== Admin (admin.txt only) =====
    if _admin_enabled():
        layout = _add_page(nav, stack, "Admin")
        from aqt import mw as _mw

        def do_cheat():
            data = storage.load()
            owned = data.get("owned_collectibles", [])
            if "key_bronze" not in owned:
                data.setdefault("owned_collectibles", []).append("key_bronze")
            data["money"] = data.get("money", 0) + 1000
            if data.get("reviews_today", 0) < shop_mod.SHOP_MIN_REVIEWS:
                data["reviews_today"] = shop_mod.SHOP_MIN_REVIEWS
            # The count alone is ignored before the day's first answer resets it.
            data["shop_gate_date"] = streak_mod.today_str()
            storage.save(data)
            on_refresh()
            tooltip("Done! Key (unlocks restocking) + 1000 gold. Shop unlocked for today.")
            d.accept()

        def do_refresh_quests():
            data = storage.load()
            col = getattr(_mw, "col", None)
            baseline = due_baseline.ensure_baseline(data, col) or {}
            gem_mult = review_rewards.gem_luck_multiplier(data, data.get("owned_collectibles", []))
            data["daily_quests"] = quests.roll_daily_quests(
                quests.QUESTS_PER_DAY, baseline, col, gem_mult, data.get("correct_today", 0)
            )
            storage.save(data)
            on_refresh()
            tooltip("Quests refreshed (2 new random quests).")

        def do_unlock_all():
            data = storage.load()
            all_ids = [c["id"] for c in shop_mod.COLLECTIBLES]
            data["owned_collectibles"] = all_ids
            storage.save(data)
            on_refresh()
            tooltip(f"Unlocked all {len(all_ids)} collectibles!")
            d.accept()

        def do_reset_panel_size():
            data = storage.load()
            w = _COLLECTQUEST_PANEL_WIDTH
            data["panel_width"] = w
            storage.save(data)
            dock = getattr(_mw, "_collectquest_dock", None)
            if dock is not None and dock.isVisible() and getattr(_mw, "resizeDocks", None):
                _mw.resizeDocks([dock], [w], Qt.Orientation.Horizontal)
            tooltip(f"Panel width set to {w} (default).")

        def do_add_10_levels():
            data = storage.load()
            data["total_xp"] = data.get("total_xp", 0) + 10 * xp.xp_needed_for_next_level(data.get("total_xp", 0))
            storage.save(data)
            on_refresh()
            tooltip("+10 levels for testing.")

        def do_prestige_now():
            prestige_mod.perform_prestige(getattr(_mw, "col", None), force=True)  # at any level
            on_refresh()
            tooltip("Prestige performed (admin).")

        def do_give_3_gems_each():
            data = storage.load()
            gems = data.get("gems", shop_mod.default_gems())
            for color, _ in shop_mod.GEM_COLORS:
                gems[color] = gems.get(color, 0) + 3
            data["gems"] = gems
            storage.save(data)
            on_refresh()
            tooltip("Added 3 gems of each color (admin).")

        admin_grid = QGridLayout()
        # Fill the two columns in creation order rather than hardcoding (row, col) per button, so
        # adding or removing one never leaves a hole in the grid.
        _admin_slot = 0

        def add_admin_btn(btn: QPushButton) -> None:
            nonlocal _admin_slot
            admin_grid.addWidget(btn, _admin_slot // 2, _admin_slot % 2)
            _admin_slot += 1

        cheat_btn = QPushButton("Cheat: Key + 1000g")
        set_hover_tip(
            cheat_btn,
            "Add Bronze Key (unlocks shop restocking), 1000 gold, and unlock shop for today (10 reviews)"
        )
        cheat_btn.clicked.connect(do_cheat)
        add_admin_btn(cheat_btn)

        refresh_quests_btn = QPushButton("Admin: Refresh quests")
        set_hover_tip(refresh_quests_btn, "Roll 2 new random daily quests (admin only)")
        refresh_quests_btn.clicked.connect(do_refresh_quests)
        add_admin_btn(refresh_quests_btn)

        unlock_btn = QPushButton("Admin: Unlock all items")
        set_hover_tip(unlock_btn, "Instantly own every collectible (admin only)")
        unlock_btn.clicked.connect(do_unlock_all)
        add_admin_btn(unlock_btn)

        game_finished_btn = QPushButton("Admin: Game finished panel")
        set_hover_tip(game_finished_btn, "Show the 'last house reached' congratulations panel (admin only).")
        game_finished_btn.clicked.connect(
            lambda: show_game_finished_dialog(parent or d, on_refresh, force=True)
        )
        add_admin_btn(game_finished_btn)

        reset_panel_btn = QPushButton("Admin: Reset panel size")
        set_hover_tip(reset_panel_btn, f"Set CollectQuest panel width to {_COLLECTQUEST_PANEL_WIDTH} px (default).")
        reset_panel_btn.clicked.connect(do_reset_panel_size)
        add_admin_btn(reset_panel_btn)

        add_levels_btn = QPushButton("Admin: +10 levels")
        add_levels_btn.clicked.connect(do_add_10_levels)
        add_admin_btn(add_levels_btn)

        prestige_now_btn = QPushButton("Admin: Prestige now")
        prestige_now_btn.clicked.connect(do_prestige_now)
        add_admin_btn(prestige_now_btn)

        onboarding_btn = QPushButton("Admin: Onboarding popup")
        set_hover_tip(onboarding_btn, "Show the welcome/difficulty popup again (admin only)")
        onboarding_btn.clicked.connect(lambda: maybe_show_onboarding(parent or d, on_refresh, force=True))
        add_admin_btn(onboarding_btn)

        update_popup_btn = QPushButton("Admin: Update popup")
        set_hover_tip(update_popup_btn, "Show the 'Updated to X' popup (admin only)")
        update_popup_btn.clicked.connect(lambda: maybe_show_update_popup(parent or d, force=True))
        add_admin_btn(update_popup_btn)

        gems_btn = QPushButton("Admin: +3 gems each")
        set_hover_tip(gems_btn, "Add 3 gems of each color (blue, green, pink, purple, yellow) for testing prestige trade.")
        gems_btn.clicked.connect(do_give_3_gems_each)
        add_admin_btn(gems_btn)

        layout.addLayout(admin_grid)

    # Narrow enough to leave the width to the settings, wide enough for the longest category.
    nav.setFixedWidth(nav.sizeHintForColumn(0) + 2 * nav.frameWidth() + 24)

    def on_page_changed(row: int) -> None:
        global _last_page
        stack.setCurrentIndex(row)
        _last_page = row

    nav.currentRowChanged.connect(on_page_changed)
    nav.setCurrentRow(min(_last_page, nav.count() - 1))

    # --- Footer: version on the left, Close on the right ---
    outer.addSpacing(8)
    footer = QHBoxLayout()
    # Via storage.get_version(), which finds the manifest correctly from src/ui/.
    version_str = storage.get_version() or "?"
    version_lbl = QLabel(f"CollectQuest v{version_str}")
    version_lbl.setStyleSheet("color: #999; font-size: 10px;")
    footer.addWidget(version_lbl)
    footer.addStretch()
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.accept)
    footer.addWidget(close_btn)
    equalize_button_widths(close_btn, minimum=_DIALOG_BUTTON_MIN_WIDTH)  # as in the CollectQuest window
    outer.addLayout(footer)

    # Close alone wears the default ring; otherwise Qt gives it to Casual, and Return sets the
    # difficulty.
    for btn in d.findChildren(QPushButton):
        btn.setAutoDefault(False)
    close_btn.setAutoDefault(True)
    close_btn.setDefault(True)
    QTimer.singleShot(0, close_btn.setFocus)

    exec_dialog(d)
