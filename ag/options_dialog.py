from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
import json

from aqt.qt import (
    QApplication,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    QPushButton,
)
from aqt.utils import showInfo, tooltip

from . import due_baseline, quests, review_rewards, shop as shop_mod, storage, streak, xp, revlog_sync


# Selected difficulty chip. Both colours are pinned, and the pair is chosen per theme: setting only
# a background leaves the label at the theme's own text colour, which is white in dark mode and
# unreadable on a pale chip. A pale chip would also look wrong against a dark dialog, so dark mode
# gets a deep blue with light text instead of the light-mode pale blue with dark text.
_DIFF_SELECTED_LIGHT = ("#d0e8ff", "#14304a")
_DIFF_SELECTED_DARK = ("#2f5a86", "#eaf2ff")


def _fmt_xp(value: float) -> str:
    """XP for display: one decimal, but no trailing '.0' on whole numbers (9 XP, not 9.0 XP)."""
    return f"{value:.1f}".removesuffix(".0")


def _selected_difficulty_colors() -> tuple[str, str]:
    """(background, text) for the active difficulty button, matched to the current Anki theme."""
    try:
        from aqt.theme import theme_manager

        if theme_manager.night_mode:
            return _DIFF_SELECTED_DARK
    except Exception:
        pass
    return _DIFF_SELECTED_LIGHT


def show_options_dialog(
    parent: QWidget | None,
    on_refresh: Callable[[], None],
) -> None:
    """
    CollectQuest options panel: Difficulty, Reset progress, Cheat (enabled only if admin.txt at add-on root).
    on_refresh is called after any action so the status bar updates.
    """
    d = QDialog(parent)
    d.setWindowTitle("CollectQuest — Options")
    layout = QVBoxLayout(d)

    # Late import to avoid circular import at module load time
    from . import ui as ui_mod

    # --- Difficulty selector ---
    layout.addSpacing(4)
    layout.addWidget(QLabel("Difficulty (XP per review):"))
    diff_row = QHBoxLayout()
    data = storage.load()
    current_diff = data.get("difficulty", "normal")

    def make_diff_btn(diff_id: str, label: str):
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(current_diff == diff_id)
        if current_diff == diff_id:
            bg, fg = _selected_difficulty_colors()
            btn.setStyleSheet(
                f"QPushButton {{ font-weight: bold; background-color: {bg}; color: {fg}; }}"
            )

        def on_click():
            data = storage.load()
            data["difficulty"] = diff_id
            storage.save(data)
            xp.set_difficulty(diff_id)
            on_refresh()
            d.accept()
            show_options_dialog(parent, on_refresh)

        btn.clicked.connect(on_click)
        return btn

    diff_row.addWidget(make_diff_btn("easy", "Casual"))
    diff_row.addWidget(make_diff_btn("normal", "Steady"))
    diff_row.addWidget(make_diff_btn("hard", "Heavy User"))
    diff_row.addStretch()
    layout.addLayout(diff_row)

    # What a Good answer pays right now, with this profile's flat and % bonuses folded in. Computed
    # with the pure helper: the awarding one would spend the fractional XP carry just to draw a
    # label. The dialog is rebuilt when a difficulty is picked, so this re-reads on every change.
    good_xp = review_rewards.review_xp_exact(
        data, 3, xp.xp_for_review(3), data.get("owned_collectibles", [])
    )
    diff_desc = QLabel(
        f"Receiving {_fmt_xp(good_xp)} XP per review.\n"
        "Quest targets follow your real due count, not difficulty."
    )
    diff_desc.setStyleSheet("color: #666; font-size: 11px;")
    layout.addWidget(diff_desc)
    layout.addSpacing(6)

    longest = (storage.load()).get("longest_streak_days") or 0
    longest_lbl = QLabel(
        f"Longest previous streak: {longest} day{'s' if longest != 1 else ''}"
        if longest > 0
        else "Longest previous streak: —"
    )
    longest_lbl.setStyleSheet("color: #666; font-size: 11px;")
    layout.addWidget(longest_lbl)
    layout.addSpacing(4)

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
                result = _mw.col.db.execute("SELECT MAX(id) FROM revlog")
                if hasattr(result, "fetchone"):
                    row = result.fetchone()
                elif isinstance(result, list) and len(result) > 0:
                    row = result[0] if isinstance(result[0], (list, tuple)) else (result[0],)
                else:
                    row = None
                if row and row[0]:
                    max_revlog_id = row[0]
                    data["last_processed_revlog_id"] = max_revlog_id
            except Exception as e:
                print(f"CollectQuest reset error: {e}")
        storage.save(data)
        on_refresh()
        tooltip(f"Progress reset. (revlog_id={max_revlog_id})")
        d.accept()

    # --- Bottom UI (status bar) checkboxes — above Save ---
    layout.addSpacing(6)
    layout.addWidget(QLabel("Bottom UI"))

    def _save_bottom_ui_opt(key: str, value: bool) -> None:
        data = storage.load()
        data[key] = value
        storage.save(data)
        on_refresh()
        QApplication.processEvents()

    opts = storage.load()
    _checked = Qt.CheckState.Checked.value
    cb_streak = QCheckBox("Show 7-day streak bar")
    cb_streak.setStyleSheet("font-size: 11px;")
    cb_streak.setChecked(opts.get("bottom_ui_show_streak", True))
    cb_streak.stateChanged.connect(lambda s: _save_bottom_ui_opt("bottom_ui_show_streak", s == _checked))
    layout.addWidget(cb_streak)
    cb_level_xp = QCheckBox("Show Level/XP bar")
    cb_level_xp.setStyleSheet("font-size: 11px;")
    cb_level_xp.setChecked(opts.get("bottom_ui_show_level_xp", True))
    cb_level_xp.stateChanged.connect(lambda s: _save_bottom_ui_opt("bottom_ui_show_level_xp", s == _checked))
    layout.addWidget(cb_level_xp)
    cb_gold_gems = QCheckBox("Show gold/gems")
    cb_gold_gems.setStyleSheet("font-size: 11px;")
    cb_gold_gems.setChecked(opts.get("bottom_ui_show_gold_gems", True))
    cb_gold_gems.stateChanged.connect(lambda s: _save_bottom_ui_opt("bottom_ui_show_gold_gems", s == _checked))
    layout.addWidget(cb_gold_gems)
    cb_quests = QCheckBox("Show quests")
    cb_quests.setStyleSheet("font-size: 11px;")
    cb_quests.setChecked(opts.get("bottom_ui_show_quests", True))
    cb_quests.stateChanged.connect(lambda s: _save_bottom_ui_opt("bottom_ui_show_quests", s == _checked))
    layout.addWidget(cb_quests)
    cb_invert = QCheckBox("Invert button (Shop ↔ CollectQuest order)")
    cb_invert.setStyleSheet("font-size: 11px;")
    cb_invert.setChecked(opts.get("bottom_ui_invert_buttons", False))
    cb_invert.stateChanged.connect(lambda s: _save_bottom_ui_opt("bottom_ui_invert_buttons", s == _checked))
    layout.addWidget(cb_invert)

    cb_dock = QCheckBox("Experimental: Enable drag-and-drop side panels")
    cb_dock.setStyleSheet("font-size: 11px;")
    cb_dock.setChecked(opts.get("use_dock_panels", False))
    cb_dock.setToolTip("Use dockable Progress/Shop panels instead of popup dialogs. Disable for the classic popup behavior.")
    def _save_dock(s):
        data = storage.load()
        data["use_dock_panels"] = s == _checked
        storage.save(data)
        on_refresh()
        QApplication.processEvents()
    cb_dock.stateChanged.connect(_save_dock)
    layout.addWidget(cb_dock)

    # --- Save: one input shows current save; replace with another and click Load to load ---
    layout.addSpacing(6)
    data_for_hash = storage.load()
    last_saved = data_for_hash.get("last_saved_at", "") or "(never saved)"
    layout.addWidget(QLabel(f"Last saved: {last_saved}"))
    try:
        data_for_blob = storage.load()
        data_for_blob.pop("_hash_invalid", None)
        if not data_for_blob.get("_hash"):
            data_for_blob["last_saved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            data_for_blob["saved_with_version"] = storage.get_version()
            data_for_blob["_hash"] = storage.compute_hash(data_for_blob)
        current_blob = storage.encode_to_hashsave(data_for_blob)
    except Exception as e:
        current_blob = ""
        showInfo(f"Could not load save for box: {e}")
    save_edit = QPlainTextEdit()
    save_edit.setPlainText(current_blob or "")
    save_edit.setMaximumHeight(60)
    save_edit.setStyleSheet("font-family: monospace; font-size: 10px;")
    layout.addWidget(save_edit)

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
        cur_date = data_for_hash.get("last_saved_at", "") or "(never)"
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
    copy_save_btn = QPushButton("Copy save")
    copy_save_btn.clicked.connect(do_copy_save)
    load_save_btn = QPushButton("Load save")
    load_save_btn.clicked.connect(do_load_save)
    save_btn_row.addWidget(copy_save_btn)
    save_btn_row.addWidget(load_save_btn)
    layout.addLayout(save_btn_row)

    def do_cheat():
        data = storage.load()
        owned = data.get("owned_collectibles", [])
        if "key_bronze" not in owned:
            data.setdefault("owned_collectibles", []).append("key_bronze")
        data["money"] = data.get("money", 0) + 1000
        if data.get("reviews_today", 0) < shop_mod.SHOP_MIN_REVIEWS:
            data["reviews_today"] = shop_mod.SHOP_MIN_REVIEWS
        storage.save(data)
        on_refresh()
        tooltip("Done! Key (unlocks refresh) + 1000 gold. Shop unlocked for today.")
        d.accept()

    if ui_mod._admin_enabled():
        from aqt import mw as _mw
        from .. import perform_prestige as _perform_prestige

        def do_refresh_quests():
            data = storage.load()
            col = getattr(_mw, "col", None)
            baseline = due_baseline.ensure_baseline(data, col) or {}
            data["daily_quests"] = quests.roll_daily_quests(quests.QUESTS_PER_DAY, baseline, col)
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
            w = ui_mod._COLLECTQUEST_PANEL_WIDTH
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
            _perform_prestige(_mw, force=True)
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
        cheat_btn.setToolTip(
            "Add Bronze Key (unlocks shop refresh), 1000 gold, and unlock shop for today (10 reviews)"
        )
        cheat_btn.clicked.connect(do_cheat)
        add_admin_btn(cheat_btn)

        refresh_quests_btn = QPushButton("Admin: Refresh quests")
        refresh_quests_btn.setToolTip("Roll 2 new random daily quests (admin only)")
        refresh_quests_btn.clicked.connect(do_refresh_quests)
        add_admin_btn(refresh_quests_btn)

        unlock_btn = QPushButton("Admin: Unlock all items")
        unlock_btn.setToolTip("Instantly own every collectible (admin only)")
        unlock_btn.clicked.connect(do_unlock_all)
        add_admin_btn(unlock_btn)


        game_finished_btn = QPushButton("Admin: Game finished panel")
        game_finished_btn.setToolTip("Show the 'last house reached' congratulations panel (admin only).")
        game_finished_btn.clicked.connect(
            lambda: ui_mod.show_game_finished_dialog(parent or d, on_refresh, force=True)
        )
        add_admin_btn(game_finished_btn)

        reset_panel_btn = QPushButton("Admin: Reset panel size")
        reset_panel_btn.setToolTip(f"Set CollectQuest panel width to {ui_mod._COLLECTQUEST_PANEL_WIDTH} px (default).")
        reset_panel_btn.clicked.connect(do_reset_panel_size)
        add_admin_btn(reset_panel_btn)

        add_levels_btn = QPushButton("Admin: +10 levels")
        add_levels_btn.clicked.connect(do_add_10_levels)
        add_admin_btn(add_levels_btn)

        prestige_now_btn = QPushButton("Admin: Prestige now")
        prestige_now_btn.clicked.connect(do_prestige_now)
        add_admin_btn(prestige_now_btn)

        onboarding_btn = QPushButton("Admin: Onboarding popup")
        onboarding_btn.setToolTip("Show the welcome/difficulty popup again (admin only)")
        onboarding_btn.clicked.connect(lambda: ui_mod.maybe_show_onboarding(parent or d, on_refresh, force=True))
        add_admin_btn(onboarding_btn)

        update_popup_btn = QPushButton("Admin: Update popup")
        update_popup_btn.setToolTip("Show the 'Updated to X' popup (admin only)")
        update_popup_btn.clicked.connect(lambda: ui_mod.maybe_show_update_popup(parent or d, force=True))
        add_admin_btn(update_popup_btn)

        gems_btn = QPushButton("Admin: +3 gems each")
        gems_btn.setToolTip("Add 3 gems of each color (blue, green, pink, purple, yellow) for testing prestige trade.")
        gems_btn.clicked.connect(do_give_3_gems_each)
        add_admin_btn(gems_btn)

        admin_widget = QWidget()
        admin_widget.setLayout(admin_grid)
        layout.addWidget(admin_widget)

    # --- Sync (mobile revlog): button first; debug text only after click ---
    layout.addSpacing(12)
    from aqt import gui_hooks, mw as _mw

    debug_lbl = QLabel("")
    debug_lbl.setStyleSheet("color: #666; font-size: 11px; font-family: monospace;")
    debug_lbl.setWordWrap(True)

    def do_run_sync_now():
        if not getattr(_mw, "col", None):
            showInfo("No collection open.")
            return
        sync_hook_exists = hasattr(gui_hooks, "sync_did_finish")
        debug_lines = [
            f"Sync hook (sync_did_finish): {'present' if sync_hook_exists else 'NOT FOUND'}",
        ]
        try:
            info = revlog_sync.get_sync_debug_info(_mw.col)
            debug_lines.extend(
                [
                    f"last_processed_revlog_id: {info.get('last_processed_revlog_id', 0)}",
                    f"new revlog rows (id > last): {info.get('new_revlog_rows', 0)}",
                    f"of those from today ({info.get('today_date', '?')}): {info.get('new_rows_from_today', 0)}",
                    f"  with a deck: {info.get('today_rows_with_deck', 0)}"
                    f", new cards: {info.get('today_rows_new_cards', 0)}",
                    f"max revlog id in DB: {info.get('max_revlog_id_in_db', 0)}",
                    f"revlog total rows in DB: {info.get('revlog_total_rows', '?')}",
                ]
            )
            if info.get("fetch_error"):
                debug_lines.append(f"fetch error: {info.get('fetch_error')}")
            if info.get("revlog_error"):
                debug_lines.append(f"revlog error: {info.get('revlog_error')}")
            debug_lines.append("Log file: ag/revlog_debug.log")
        except Exception as e:
            debug_lines.append(f"Debug error: {type(e).__name__}: {e}")
        debug_lbl.setText("\n".join(debug_lines))
        summary = revlog_sync.process_synced_revlog(_mw.col, silent=True)
        on_refresh()
        if summary:
            showInfo(
                f"Sync applied: {summary.get('reviews', 0)} reviews from today.\n"
                f"+{summary.get('xp', 0)} XP, +{summary.get('gold', 0)}g, +{summary.get('gems', 0)} gems."
            )
        else:
            showInfo(
                "No new revlog rows from today were applied.\n"
                "See debug info above; if 'new rows from today' is 0, do some reviews on mobile then sync again."
            )

    run_sync_btn = QPushButton("Run sync now (process revlog)")
    run_sync_btn.clicked.connect(do_run_sync_now)
    layout.addWidget(run_sync_btn)

    def do_show_due_baseline():
        """Show the start-of-day due counts and how they were reconstructed (see ag/due_baseline.py).

        Read-only: compare 'reconstructed' against the total Anki showed you this morning.
        """
        from aqt import mw as _mw

        if not getattr(_mw, "col", None):
            showInfo("No collection loaded.")
            return
        col = _mw.col
        try:
            # reconstruct() already runs live_counts() and finished_today() internally; calling them
            # again here would build the deck tree and scan the revlog twice per button press.
            live_total, live_decks = due_baseline.live_counts(col)
            done_total, _ = due_baseline.finished_today(col)
            answered = due_baseline.answered_today(col)
            recon = due_baseline.reconstruct_from(col, live_total, live_decks)
            cutoff = due_baseline.day_start_timestamp_ms(col)
        except Exception as e:
            showInfo(f"Baseline error: {type(e).__name__}: {e}")
            return
        stored = (storage.load().get("quest_due_baseline") or {})
        started = datetime.fromtimestamp(cutoff / 1000).strftime("%Y-%m-%d %H:%M")
        recon_total = recon.get("total", 0)
        stored_total = stored.get("total")
        # The invariant: reconstruction must stay flat all day. If it drifts, the "finished" rule is
        # wrong for some card state and quest targets built on it would drift too.
        if stored.get("date") == recon.get("date") and isinstance(stored_total, int):
            drift = recon_total - stored_total
            verdict = "stable" if drift == 0 else f"DRIFT {drift:+d}"
        else:
            verdict = "no stored baseline for today yet"
        lines = [
            f"Scheduler day:  {streak.today_str(col)}  (rollover {streak.rollover_hours(col)}h)",
            f"Day started:    {started}",
            "",
            f"Due now (capped):        {live_total}",
            f"Cards answered today:    {answered}",
            f"  of those, finished:    {done_total}   (the rest are back in relearning)",
            f"Reconstructed baseline:  {recon_total}   = {live_total} + {done_total}",
            "",
            f"Stored baseline: {stored_total if stored_total is not None else '(none)'}"
            f"   (captured for {stored.get('date', '-')})",
            f"Check: {verdict}",
            "",
            "Per deck — due now + finished today = baseline:",
        ]
        by_size = sorted(recon.get("decks", {}).items(), key=lambda kv: -kv[1].get("due", 0))
        for did, info in by_size[:15]:
            now = live_decks.get(did, {}).get("due", 0)
            base = info.get("due", 0)
            flag = "  [filtered]" if info.get("filtered") else ""
            name = due_baseline.display_deck_name(info.get("name", "?"))
            lines.append(f"   {name}: {now} + {base - now} = {base}{flag}")
        if len(by_size) > 15:
            lines.append(f"   … and {len(by_size) - 15} more")
        showInfo("\n".join(lines))

    baseline_btn = QPushButton("Quest baseline (debug)")
    baseline_btn.setToolTip(
        "Show start-of-day due counts used for quest targets, and how they were reconstructed. Read-only."
    )
    baseline_btn.clicked.connect(do_show_due_baseline)
    layout.addWidget(baseline_btn)
    reset_btn = QPushButton("Reset progress")
    reset_btn.setToolTip("Delete all game data (with confirmation)")
    reset_btn.clicked.connect(do_reset)
    layout.addWidget(reset_btn)
    layout.addWidget(debug_lbl)

    layout.addSpacing(12)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(d.accept)
    layout.addWidget(close_btn)

    # Version display
    layout.addSpacing(8)
    version_str = "?"
    try:
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            version_str = manifest.get("version", "?")
    except Exception:
        pass
    version_lbl = QLabel(f"CollectQuest v{version_str}")
    version_lbl.setStyleSheet("color: #999; font-size: 10px;")
    version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(version_lbl)
    QTimer.singleShot(0, close_btn.setFocus)

    d.exec()
