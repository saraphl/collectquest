"""
Everything the add-on wires into Anki: the answer/undo/sync/profile handlers, the status-bar
refresh, and prestige. The root __init__.py stays a thin entry point that only calls register().
"""
from __future__ import annotations

from aqt import gui_hooks, mw
from aqt.qt import QEvent, QHBoxLayout, QObject, QTimer, QWidget
from . import carry, due_baseline, milestones, prestige, quests, revlog_sync, review_rewards, storage, shop as shop_mod, streak, ui, xp

# Rewards (also in src/review_rewards.py for revlog sync)
GOLD_PER_LEVEL_UP = review_rewards.GOLD_PER_LEVEL_UP
GOLD_PER_QUEST = review_rewards.GOLD_PER_QUEST_FALLBACK  # fallback when quest has no reward_gold

# Undo buffer: list of {xp_delta, gold_delta, gems_delta} per review (excluding quests). Multiple Ctrl+Z supported.
UNDO_BUFFER_MAX = review_rewards.UNDO_BUFFER_MAX

# Installed by register(); kept alive as a module global so Qt does not collect it.
_resize_filter: '_CollectQuestResizeFilter | None' = None


def _profile_folder() -> str:
    return mw.pm.profileFolder()


def _ease_from_answer(a1, a2) -> tuple:
    """Return (card, ease_int_1_to_4). Ease may be 0–3 (0-indexed) or 1–4; normalize to 1–4. Handles (card, ease) or (ease, card)."""
    def _as_ease(v):
        if v is None:
            return 3
        if isinstance(v, int) and 1 <= v <= 4:
            return v
        if isinstance(v, int) and 0 <= v <= 3:
            return v + 1  # 0→Again, 1→Hard, 2→Good, 3→Easy
        try:
            n = int(v)
            if 0 <= n <= 4:
                return n if n >= 1 else 1
            return 3
        except (TypeError, ValueError):
            return 3
    # Card has .did (deck id); ease is int 0–4. Avoid using .id (int has no .id but getattr returns None).
    has_did = lambda x: getattr(x, "did", None) is not None
    if has_did(a2) and not has_did(a1):
        card, ease = a2, a1
    elif has_did(a1) and not has_did(a2):
        card, ease = a1, a2
    else:
        card, ease = a1, a2
    return (card, _as_ease(ease))


def _on_answer(reviewer, a1, a2) -> None:
    """Handle reviewer_did_answer_card (notification only, cannot affect card). Anki 24: (reviewer, card, ease). Anki 25: (reviewer, ease, card)."""
    card, ease = _ease_from_answer(a1, a2)
    # Quest targets are sized from the day's due baseline (src/due_baseline.py), so the reviewer's
    # live counts are not consulted here.
    deck_name = None
    is_new = False
    counts_as_due_review = True
    if mw.col:
        try:
            deck_name = mw.col.decks.name(card.did)
            # From the revlog, not the card: this hook runs after the answer, and where the card
            # lands depends on the grade and the deck's learning steps - testing card.type
            # credited Again and dropped the rest.
            is_new, counts_as_due_review = revlog_sync.newest_answer_flags(
                mw.col, getattr(card, "id", 0)
            )
        except Exception:
            pass
    data = storage.load()
    earned = review_rewards.apply_one_review(
        data,
        ease,
        deck_name=deck_name,
        is_new=is_new,
        counts_as_due_review=counts_as_due_review,
        col=mw.col,
    )
    # Pushed for every review, Again included, so the buffer stays in step with Anki's undo stack:
    # otherwise undoing an Again would revert the previous review's XP.
    buf = getattr(mw, "_collectquest_undo_state", None)
    if not isinstance(buf, list):
        buf = []
    buf.append(earned.get("undo_deltas"))
    if len(buf) > UNDO_BUFFER_MAX:
        buf = buf[-UNDO_BUFFER_MAX:]
    mw._collectquest_undo_state = buf
    storage.save(data)
    revlog_sync.update_last_processed_revlog_id(mw.col, getattr(card, "id", 0))
    # The refresh stashes any completion rather than announcing it, so the summary below lands
    # first and the stacked box can sit above it.
    global _answer_in_progress
    _answer_in_progress = True
    try:
        _refresh_xp_bar()
    finally:
        _answer_in_progress = False
    # One tooltip for the whole answer: Anki's tooltip is a singleton, so two calls meant the
    # second replaced the first before it could be read.
    ui.show_review_summary_tooltip(
        earned.get("completed_quests") or [],
        earned.get("gold_earned", 0),
        earned.get("gem_earned", 0),
        leveled_up=bool(earned.get("leveled_up")),
    )
    # After the summary, never before: the stacked box picks its slot from what is already on
    # screen, so going first would leave it overlapped by the summary.
    _show_track_notice(earned)


# Milestones finished but not yet shown. _refresh_xp_bar drains the save's queue into this and
# announces straight away, except during an answer - the summary tooltip has to land first.
_track_notices: list[dict] = []
_answer_in_progress = False
_track_notice_scheduled = False

# How long the refresh waits before announcing a completed milestone. stacked_tooltip picks its
# slot by reading what is already on screen, so announcing immediately would take the default slot
# before Anki posts its own "Collection sync complete." and be overlapped by it. Two seconds also
# spaces the message out from the rest of a profile load.
_TRACK_NOTICE_DELAY_MS = 2000

# The same problem for the post-sync announcement, which fires while Anki's "Collection complete."
# and other add-ons' sync messages are still being posted. One turn of the event loop lets them
# speak first; kept short so the message still reads as immediate.
_SYNC_NOTICE_DELAY_MS = 100

# True between profile_will_close and the next profile_did_open. Anki syncs from inside its own
# profile teardown, and the announcement below has to know: a deferred message would be scheduled
# against a collection that is closed a moment later, and would then be dropped unseen.
_profile_closing = False


def _schedule_track_notice() -> None:
    """Announce queued completions shortly, once the noisier startup messages have landed."""
    global _track_notice_scheduled
    if _track_notice_scheduled or not _track_notices:
        return
    _track_notice_scheduled = True

    def _fire() -> None:
        global _track_notice_scheduled
        _track_notice_scheduled = False
        # The stash may have been drained by an answer in the meantime, in which case this is a
        # no-op rather than an empty box.
        _show_track_notice()

    QTimer.singleShot(_TRACK_NOTICE_DELAY_MS, _fire)


def _show_track_notice(earned: dict | None = None) -> None:
    """
    Announce what the milestone track has done, in one stacked notification.

    Completed milestones come from `_track_notices` (the path that notices one often cannot show a
    message); buff and Magnet drops come from `earned`, which only a review has. Never raises - it
    runs from the answer hook - but prints, so a wiring mistake is not a silent no-op.
    """
    try:
        lines: list[str] = []
        while _track_notices:
            entry = _track_notices.pop(0)
            lines.append(f"Milestone complete: {milestones.objective_label(entry)}")
            lines.append(f"Reward: {entry.get('reward', '')}")

        if earned:
            buff = earned.get("buff_started")
            if buff:
                lines.append(f"Buff for {milestones.BUFF_DAYS} days: {buff['label']}")
            if earned.get("magnet_found"):
                lines.append("Magnet found!")
            stage = earned.get("magnet_stage_completed")
            if stage:
                lines.append(milestones.stage_completed_message(stage))
        if not lines:
            return
        ui.stacked_tooltip("\n".join(lines), parent=mw)
    except Exception as e:
        print(f"CollectQuest: milestone notification failed: {e!r}")


def _revert_last_review_rewards() -> bool:
    """Revert last review: pop one step from buffer and subtract its XP/gold/gems. Returns True if reverted."""
    buf = getattr(mw, "_collectquest_undo_state", None)
    if not isinstance(buf, list) or not buf:
        return False
    deltas = buf.pop()
    mw._collectquest_undo_state = buf
    try:
        data = storage.load()
        data["total_xp"] = max(0, data.get("total_xp", 0) - deltas.get("xp_delta", 0))
        data["money"] = max(0, data.get("money", 0) - deltas.get("gold_delta", 0))
        # The sub-1 carries are restored to their pre-review values too, or repeated undo/redo
        # would slowly invent or lose a point.
        for key, delta_key in ((carry.XP_KEY, "xp_fraction_before"), (carry.GOLD_KEY, "gold_fraction_before")):
            if delta_key in deltas:
                carry.restore(data, key, deltas[delta_key])
        if deltas.get("cleared_bonus_awarded"):
            # XP/gold/gems already come back via the deltas above; this frees the once-a-day claim.
            data.pop("cleared_bonus_date", None)
        gems = data.get("gems", {})
        for color, add in (deltas.get("gems_delta") or {}).items():
            gems[color] = max(0, gems.get(color, 0) - add)
        data["gems"] = gems
        if deltas.get("was_correct"):
            data["correct_today"] = max(0, data.get("correct_today", 0) - 1)
        if deltas.get("counted_as_review"):
            # reviews_today gates shop unlock (10 reviews); reverting keeps it in sync with undo
            data["reviews_today"] = max(0, data.get("reviews_today", 0) - 1)
        # Correct-quests track the day's total, not a per-review +1, so they are recomputed.
        correct_today = data.get("correct_today", 0)
        for q in data.get("daily_quests") or []:
            if q.get("id") == quests.QUEST_KIND_CORRECT_REVIEWS:
                q["progress"] = min(correct_today, q.get("target", 0))
        # Revert quest progress for review/deck/new-card quests so Ctrl+Z is consistent
        progress_revert = deltas.get("quest_progress_revert") or []
        for idx, progress_before in progress_revert:
            dq = data.get("daily_quests") or []
            if 0 <= idx < len(dq):
                dq[idx]["progress"] = progress_before
        data["level"] = xp.level_from_total_xp(data["total_xp"])
        # Point the high-water mark at the newest surviving revlog row: still naming the deleted
        # one would make _a_review_was_undone read every later undo as a reverted review.
        try:
            newest = mw.col.db.scalar("SELECT MAX(id) FROM revlog") if mw.col else None
            data["last_processed_revlog_id"] = int(newest or 0)
        except Exception:
            pass
        storage.save(data)
        _refresh_xp_bar()
        return True
    except Exception:
        return False


def _a_review_was_undone() -> bool:
    """
    True when the operation Anki just undid was a card answer.

    state_did_undo fires for anything on the undo stack, and the operation name is localised and so
    unusable as a test. Undoing an answer deletes its revlog row, so a missing high-water row means
    a review was undone.
    """
    col = getattr(mw, "col", None)
    if col is None:
        return False
    try:
        mark = int(storage.load().get("last_processed_revlog_id", 0) or 0)
    except Exception:
        return False
    if mark <= 0:
        return False
    try:
        # Primary-key lookup, so this costs nothing even though it runs on every undo.
        return not col.db.scalar("SELECT 1 FROM revlog WHERE id = ?", mark)
    except Exception:
        return False


def _on_undo_after_state_change(changes=None) -> None:
    """Called when user undoes (e.g. Ctrl+Z). Hook: state_did_undo(changes). Revert our rewards."""
    if not _a_review_was_undone():
        return
    _revert_last_review_rewards()
    _refresh_xp_bar()


def _open_progress() -> None:
    data = storage.load()
    if data.get("use_dock_panels"):
        ui.toggle_progress_panel(mw, _refresh_xp_bar, _update_statusbar_center_width)
    else:
        ui.show_progress_dialog(mw, on_refresh=_refresh_xp_bar)


def _open_options() -> None:
    ui.show_options_dialog(mw, on_refresh=_refresh_xp_bar)


def _open_prestige() -> None:
    ui.show_prestige_dialog(mw, _refresh_xp_bar)


def _open_shop() -> None:
    data = storage.load()
    if data.get("use_dock_panels"):
        ui.toggle_shop_panel(mw, _refresh_xp_bar)
    else:
        ui.show_shop_dialog(mw, on_refresh=_refresh_xp_bar)


# True only while the welcome dialog is up: its exec() runs an event loop, so a hook that refreshes
# the bar meanwhile would stack a streak reward dialog on top of the welcome. Only that reward is
# held back - a nested refresh still rebuilds the bar, so options changed from the welcome popup's
# "Open Options" button take effect while the player watches.
_onboarding_dialog_open = False


def _update_statusbar_center_width() -> None:
    """Update block width and right 2/3-panel block so bottom UI stays centered when right panel opens (stretch, block, stretch, 2/3block)."""
    block_w = getattr(mw, "_collectquest_statusbar_center_block", None)
    right_block_w = getattr(mw, "_collectquest_statusbar_right_panel_block", None)
    if block_w is None:
        return
    content_px = ui.get_collectquest_statusbar_center_content_width(mw)
    block_w.setFixedWidth(content_px)
    if right_block_w is not None:
        right_block_w.setFixedWidth(ui.get_collectquest_statusbar_right_panel_block_width(mw))


def _refresh_xp_bar() -> None:
    global _onboarding_dialog_open
    try:
        sb = mw.statusBar()
    except Exception:
        return
    # The welcome popup goes first: every startup path leads here, and a new player should be
    # greeted before the streak reward dialog below. It also writes difficulty and its own flag, so
    # it has to run before `data` is loaded or the save at the end would undo both. The flag is
    # saved and restored, not cleared, so a nested refresh cannot report the dialog as closed.
    if mw.col:
        was_open = _onboarding_dialog_open
        _onboarding_dialog_open = True
        try:
            ui.maybe_show_onboarding(mw, _refresh_xp_bar)
        except Exception:
            pass
        finally:
            _onboarding_dialog_open = was_open
    data = storage.load()
    use_dock_panels = data.get("use_dock_panels", False)

    streak_count = 0
    if mw.col:
        streak.refresh_streak(data, mw.col)
        # Not while the welcome dialog is up: the refresh that opened it is still on the stack and
        # grants the reward once the player clicks OK.
        streak_reward = None if _onboarding_dialog_open else streak.maybe_grant_streak_reward(data, mw.col)
        # Capture start-of-day due counts once per scheduler day. Here because this is the one path
        # that fires on profile load, after every answer and after sync.
        try:
            due_baseline.ensure_baseline(data, mw.col)
        except Exception:
            pass
        # Streak milestones are finished by the day turning, so without this nothing would notice
        # one until the next answered card. Idempotent, and the queue is drained once. Wrapped like
        # ensure_baseline: bookkeeping must not cost the player their status bar.
        try:
            milestones.advance_if_complete(data, mw.col)
            _track_notices.extend(milestones.take_pending_announcements(data))
        except Exception:
            pass
        storage.save(data)
        # Announced from here rather than from chosen callers, so a completion spotted by the
        # shop's refresh or the launch retry loop is not left in the queue with nobody to report it.
        if not _answer_in_progress:
            _schedule_track_notice()
        if streak_reward:
            ui.show_streak_reward_dialog(mw, streak_reward)

    # One snapshot for everything the bar draws, taken after the dialogs above: any of them runs a
    # nested event loop where a refresh can save, and building half the bar from the older `data`
    # put a stale square count beside a fresh reward icon.
    bar_data = storage.load()
    if mw.col:
        today_ep = streak.today_epoch(mw.col)
        current_days, _ = streak.get_display_streak_days(bar_data, today_ep)
        streak_count = ((current_days - 1) % streak.STREAK_LENGTH) + 1 if current_days > 0 else 0

    if not use_dock_panels:
        # Simple mode: popup dialogs, centered bar in status bar (no dock panels)
        for dock_attr in ("_collectquest_dock", "_collectquest_shop_dock"):
            dock = getattr(mw, dock_attr, None)
            if dock is not None and getattr(dock, "isVisible", None):
                try:
                    dock.setVisible(False)
                except Exception:
                    pass
        # Tear down dock-mode container if present
        container = getattr(mw, "_collectquest_statusbar_container", None)
        if container is not None and container.parent() is not None:
            sb.removeWidget(container)
            container.deleteLater()
            mw._collectquest_statusbar_container = None
            mw._collectquest_statusbar_center_block = None
            mw._collectquest_statusbar_right_panel_block = None
            mw._collectquest_xp_widget = None
        # Tear down previous simple widgets
        if getattr(mw, "_collectquest_streak_widget", None) is not None:
            try:
                sb.removeWidget(mw._collectquest_streak_widget)
                mw._collectquest_streak_widget.deleteLater()
            except Exception:
                pass
            mw._collectquest_streak_widget = None
        if getattr(mw, "_collectquest_xp_widget", None) is not None:
            try:
                sb.removeWidget(mw._collectquest_xp_widget)
                mw._collectquest_xp_widget.deleteLater()
            except Exception:
                pass
            mw._collectquest_xp_widget = None
        # One status bar item holding the optional streak plus the bar. The streak lives inside it
        # so its width can be mirrored on the right and the bar stays centered rather than pushed.
        streak_w = (
            ui.build_streak_widget(streak_count=streak_count, data=bar_data)
            if bar_data.get("bottom_ui_show_streak", False)
            else None
        )
        center_w = ui.build_simple_centered_xp_bar_widget(
            _open_progress, _open_shop, _open_prestige, streak_widget=streak_w, data=bar_data
        )
        mw._collectquest_xp_widget = center_w
        mw._collectquest_streak_widget = None  # owned by center_w now; teardown removes it with the parent
        sb.addWidget(center_w, 1)
        # Re-balance against the status bar's size-grip reserve, now and on every window resize.
        def _recenter_simple_bar() -> None:
            ui.update_simple_bar_centering(sb, center_w)
        mw._collectquest_update_statusbar_center_width = _recenter_simple_bar
        QTimer.singleShot(0, _recenter_simple_bar)
        ui.maybe_show_prestige_prompt(mw, _refresh_xp_bar)
        ui.maybe_show_game_finished_prompt(mw, _refresh_xp_bar)
        return

    # Dock panels mode: build container with block and right-panel compensation
    if getattr(mw, "_collectquest_streak_widget", None) is not None:
        try:
            sb.removeWidget(mw._collectquest_streak_widget)
            mw._collectquest_streak_widget.deleteLater()
        except Exception:
            pass
        mw._collectquest_streak_widget = None
    if getattr(mw, "_collectquest_xp_widget", None) is not None and getattr(mw, "_collectquest_statusbar_container", None) is None:
        try:
            sb.removeWidget(mw._collectquest_xp_widget)
            mw._collectquest_xp_widget.deleteLater()
        except Exception:
            pass
        mw._collectquest_xp_widget = None

    streak_w = (
        ui.build_streak_widget(streak_count=streak_count, data=bar_data)
        if bar_data.get("bottom_ui_show_streak", False)
        else None
    )
    block = ui.build_bottom_ui_block(
        _open_progress, _open_shop, _open_prestige, streak_w, mw, data=bar_data
    )

    container = getattr(mw, "_collectquest_statusbar_container", None)
    if container is not None and container.parent() is not None:
        old_block = mw._collectquest_statusbar_center_block
        if old_block is not None:
            layout = container.layout()
            if layout is not None and layout.count() >= 3:
                layout.removeWidget(old_block)
                layout.insertWidget(1, block, 0)
                old_block.deleteLater()
                mw._collectquest_statusbar_center_block = block
                mw._collectquest_xp_widget = block
                _update_statusbar_center_width()
                ui.refresh_progress_panel(mw)
                ui.maybe_show_prestige_prompt(mw, _refresh_xp_bar)
                ui.maybe_show_game_finished_prompt(mw, _refresh_xp_bar)
                return
        sb.removeWidget(container)
        container.deleteLater()
        mw._collectquest_statusbar_container = None
        mw._collectquest_statusbar_center_block = None
        mw._collectquest_statusbar_right_panel_block = None
        mw._collectquest_xp_widget = None

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
    mw._collectquest_update_statusbar_center_width = _update_statusbar_center_width
    _update_statusbar_center_width()
    sb.addWidget(container, 1)
    ui.refresh_progress_panel(mw)
    ui.maybe_show_prestige_prompt(mw, _refresh_xp_bar)
    ui.maybe_show_game_finished_prompt(mw, _refresh_xp_bar)
    if data.get("panel_visible") and (not getattr(mw, "_collectquest_dock", None) or not mw._collectquest_dock.isVisible()):
        want_floating = data.get("panel_floating")
        def _restore_panel():
            if want_floating:
                mw._collectquest_restore_floating = True
            ui.toggle_progress_panel(mw, _refresh_xp_bar, _update_statusbar_center_width)
            if want_floating:
                mw._collectquest_restore_floating = False
        QTimer.singleShot(80, _restore_panel)
    if data.get("shop_panel_visible") and (not getattr(mw, "_collectquest_shop_dock", None) or not mw._collectquest_shop_dock.isVisible()):
        today = streak.today_str(mw.col)
        gate_date = data.get("shop_gate_date", "")
        reviews_today = data.get("reviews_today", 0)
        if gate_date == today or reviews_today >= shop_mod.SHOP_MIN_REVIEWS:
            QTimer.singleShot(120, lambda: ui.toggle_shop_panel(mw, _refresh_xp_bar))


def _apply_prestige_starting_gold(data: dict) -> None:
    """Apply starting gold bonus from prestige upgrades to a freshly created state."""
    bonus = prestige.prestige_start_gold_bonus(data)
    if bonus > 0:
        data["money"] = data.get("money", 0) + bonus


def perform_prestige(force: bool = False) -> bool:
    """
    Award prestige points based on current level, then reset state to defaults
    while preserving prestige meta (points and upgrades). Returns True if a
    prestige was performed.
    """
    data = storage.load()
    # Recompute level from total_xp so preview and actual gain use the same value.
    level = xp.level_from_total_xp(int(data.get("total_xp", 0) or 0))
    gain = prestige.total_prestige_points_gain(level, data.get("owned_collectibles") or [])
    if not force and gain <= 0:
        return False
    total = int(data.get("prestige_points_total", 0) or 0)
    pending_from_gems = int(data.get("pending_prestige_points_from_gems", 0) or 0)
    data["prestige_points_total"] = total + max(0, gain) + pending_from_gems
    # Preserve prestige meta fields before resetting (pending_from_gems is consumed, not copied)
    prestige_points_total = data["prestige_points_total"]
    prestige_points_spent = int(data.get("prestige_points_spent", 0) or 0)
    prestige_upgrades = data.get("prestige_upgrades") or {}
    # Create fresh state and reattach prestige (XP reset to 0, not level-based)
    new_state = storage._default_state()
    new_state["total_xp"] = 0
    new_state["level"] = 1
    new_state["prestige_count"] = (data.get("prestige_count", 0) or 0) + 1
    new_state["prestige_points_total"] = prestige_points_total
    new_state["prestige_points_spent"] = prestige_points_spent
    new_state["prestige_upgrades"] = prestige_upgrades
    # The track persists across a prestige - two of its objectives ask for prestiges. Carried over
    # before the prestige is counted, so the count lands on the state that is kept.
    if isinstance(data.get("milestones"), dict):
        new_state["milestones"] = data["milestones"]
    milestones.note_event(new_state, milestones.OBJ_PRESTIGE)
    milestones.advance_if_complete(new_state)
    # Settings a wipe must not touch, plus what a prestige keeps on top of them: difficulty and the
    # streak's per-run counters. The key list lives in storage next to the defaults, so a reset and
    # a prestige cannot drift apart. Nothing here re-arms a popup - a prestige is not a new player,
    # so the welcome dialog stays shown and the streak pays no reward that was already claimed.
    storage.carry_prestige_keys(data, new_state)
    _apply_prestige_starting_gold(new_state)
    # Roll fresh daily quests immediately so the player sees them after prestiging.
    try:
        quests.ensure_daily_quests(new_state, col=mw.col if mw.col else None)
    except Exception:
        pass
    storage.save(new_state)
    _refresh_xp_bar()
    return True


def _on_profile_loaded() -> None:
    global _profile_closing
    _profile_closing = False
    # Clear CollectQuest and Shop docks so this profile gets fresh panels (avoids stale content)
    if hasattr(mw, "_collectquest_dock") and mw._collectquest_dock is not None:
        mw._collectquest_dock.deleteLater()
        mw._collectquest_dock = None
        mw._collectquest_on_refresh = None
    if hasattr(mw, "_collectquest_shop_dock") and mw._collectquest_shop_dock is not None:
        mw._collectquest_shop_dock.deleteLater()
        mw._collectquest_shop_dock = None
    storage.set_profile_folder(_profile_folder())
    data = storage.load()
    xp.set_difficulty(data.get("difficulty", "normal"))
    # On first load (last_processed_revlog_id == 0), set it to current max to avoid replaying old reviews
    if data.get("last_processed_revlog_id", 0) == 0 and mw.col:
        try:
            result = mw.col.db.execute("SELECT MAX(id) FROM revlog")
            if hasattr(result, 'fetchone'):
                row = result.fetchone()
            elif isinstance(result, list) and len(result) > 0:
                row = result[0] if isinstance(result[0], (list, tuple)) else (result[0],)
            else:
                row = None
            if row and row[0]:
                data["last_processed_revlog_id"] = row[0]
                storage.save(data)
        except Exception:
            pass
    # Process any new revlog from sync (mobile reviews); must not crash Anki if revlog fails
    try:
        if mw.col:
            revlog_sync.process_synced_revlog(mw.col, silent=True)
    except Exception:
        pass
    # Ensure daily quests are rolled for today (fixes empty quest UI on first load or after reset)
    data = storage.load()
    quests.ensure_daily_quests(data, col=mw.col if mw.col else None)
    storage.save(data)
    # Run same refresh as after a review; defer until col is set (profile_did_open can run before collection is loaded)
    def _refresh_when_ready(retries: int = 25) -> None:
        if mw.col:
            # Onboarding is not called here: _refresh_xp_bar shows it itself, early enough to beat
            # the streak reward dialog whichever hook refreshes the bar first.
            _refresh_xp_bar()
            ui.maybe_show_update_popup(mw)
            return
        if retries > 0:
            QTimer.singleShot(200, lambda: _refresh_when_ready(retries - 1))
    QTimer.singleShot(0, lambda: _refresh_when_ready())


def _on_sync_did_finish() -> None:
    """After sync: process new revlog entries (e.g. from mobile) so quest rewards, XP, gold, gems update."""
    if not mw.col:
        return
    # Credited straight away, so the save is correct even if what follows never runs.
    summary = revlog_sync.process_synced_revlog(mw.col, silent=True)

    def _announce() -> None:
        # The profile can be closed in the meantime - an auto-sync on close finishes into this hook.
        if not mw.col:
            return
        if summary:
            ui.show_sync_summary_panel(mw, summary)
        # After the notification, not before: the refresh can open a streak reward or prestige
        # dialog, whose exec() would otherwise hold the message back until the player closes it.
        _refresh_xp_bar()

    if _profile_closing:
        # A sync on profile close: Anki closes the collection as soon as this hook returns, so a
        # deferred message would find mw.col gone and say nothing at all. Nothing is competing for
        # the slot on the way out either - the delay buys nothing here and costs the message.
        _announce()
        return
    # Everything the player sees is deferred together: the refresh announces finished milestones
    # and can pop a reward dialog. Anki refreshes the same bar right after this hook anyway
    # (mw.reset() -> state_did_reset), so nothing looks stale in the meantime.
    QTimer.singleShot(_SYNC_NOTICE_DELAY_MS, _announce)


def _on_state_did_reset(state: str | None = None, _old_state: str | None = None) -> None:
    if state == "review":
        return
    _refresh_xp_bar()


def _on_profile_will_close() -> None:
    global _profile_closing
    _profile_closing = True
    data = storage.load()
    dock = getattr(mw, "_collectquest_dock", None)
    if dock is not None:
        data["panel_visible"] = dock.isVisible()
        if dock.isVisible():
            area = ui._collectquest_dock_area(mw)
            data["panel_area"] = area or "right"
            data["panel_width"] = max(80, dock.width())
            data["panel_floating"] = dock.isFloating()
            if dock.isFloating():
                rect = dock.frameGeometry()
                mw_win = mw.window().frameGeometry()
                data["panel_float_rel_x"] = rect.x() - mw_win.x()
                data["panel_float_rel_y"] = rect.y() - mw_win.y()
                data["panel_float_width"] = max(200, rect.width())
                data["panel_float_height"] = max(300, rect.height() - ui._FLOAT_HEIGHT_SAVE_OFFSET)
    shop_dock = getattr(mw, "_collectquest_shop_dock", None)
    if shop_dock is not None:
        data["shop_panel_visible"] = shop_dock.isVisible()
        if shop_dock.isVisible():
            data["shop_panel_area"] = ui._shop_dock_area(mw) or "left"
            data["shop_panel_width"] = max(ui._COLLECTQUEST_PANEL_MIN_WIDTH, shop_dock.width())
            data["shop_panel_floating"] = shop_dock.isFloating()
            if shop_dock.isFloating():
                rect = shop_dock.frameGeometry()
                mw_win = mw.window().frameGeometry()
                data["shop_panel_float_rel_x"] = rect.x() - mw_win.x()
                data["shop_panel_float_rel_y"] = rect.y() - mw_win.y()
                data["shop_panel_float_width"] = max(200, rect.width())
                data["shop_panel_float_height"] = max(300, rect.height() - ui._FLOAT_HEIGHT_SAVE_OFFSET)
    storage.save(data)
    if dock is not None and dock.isVisible():
        dock.hide()
    if shop_dock is not None and shop_dock.isVisible():
        shop_dock.hide()


# Resize filter: keep status bar (XP bar) centered over the main area when the CollectQuest panel is open
class _CollectQuestResizeFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

    def eventFilter(self, obj, event):
        if obj is mw and event.type() == QEvent.Type.Resize:
            upd = getattr(mw, "_collectquest_update_statusbar_center_width", None)
            if callable(upd):
                upd()
        return False


def register() -> None:
    """Install every Qt event filter and gui_hook. Called once, from the add-on entry point."""
    global _resize_filter
    _resize_filter = _CollectQuestResizeFilter(mw)
    mw.installEventFilter(_resize_filter)

    # Only use reviewer_did_answer_card (notification hook) - NEVER use reviewer_will_answer_card (filter hook that can break card answering)
    gui_hooks.reviewer_did_answer_card.append(_on_answer)
    # Undo (Ctrl+Z): state_did_undo is called after backend undoes a change (e.g. review).
    if hasattr(gui_hooks, "state_did_undo"):
        gui_hooks.state_did_undo.append(_on_undo_after_state_change)
    gui_hooks.profile_did_open.append(_on_profile_loaded)
    gui_hooks.state_did_reset.append(_on_state_did_reset)
    # Save state when the profile closes; the handler hides the panel first so Anki
    # stores the shrunk window geometry.
    if hasattr(gui_hooks, "profile_will_close"):
        gui_hooks.profile_will_close.append(_on_profile_will_close)
    # Sync: only register if this hook exists (Anki version may not have it).
    if hasattr(gui_hooks, "sync_did_finish"):
        gui_hooks.sync_did_finish.append(_on_sync_did_finish)

    # Run profile load if already open (e.g. add-on just loaded)
    if mw.col:
        _on_profile_loaded()
