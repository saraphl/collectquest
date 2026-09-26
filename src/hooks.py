"""Everything the add-on wires into Anki: answer/undo/sync/profile handlers and the status-bar
refresh. The root __init__.py only calls register()."""
from __future__ import annotations

from aqt import gui_hooks, mw
from aqt.qt import QEvent, QObject, QTimer
from . import carry, due_baseline, dungeon, milestones, notices, quests, revlog_sync, review_rewards, storage, streak, ui, xp

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
            # From the revlog, not the card: where the card lands after answering depends on the
            # grade and learning steps, so testing card.type credited Again and dropped the rest.
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
    if len(buf) > review_rewards.UNDO_BUFFER_MAX:
        buf = buf[-review_rewards.UNDO_BUFFER_MAX:]
    mw._collectquest_undo_state = buf
    storage.save(data)
    revlog_sync.update_last_processed_revlog_id(mw.col, getattr(card, "id", 0))
    _announce_earned(earned)


# True while an answer is being announced: the refresh then stashes a finished milestone instead
# of announcing it, so the answer's summary box lands first.
_answer_in_progress = False

# Before the post-sync announcement: one event-loop turn lets Anki's and other add-ons' sync
# messages post first.
_SYNC_NOTICE_DELAY_MS = 100


# The bonus-quest check runs off operation_did_execute, since only card operations shrink the day's
# schedule. Debounced: batch edits and answering fire one operation each.
_VOID_CHECK_DEBOUNCE_MS = 400
_void_check_seq = 0

_VOID_NOTICE = (
    "CollectQuest: Too many reviews are no longer scheduled\n"
    "for today \u2014 the bonus quest can't be completed."
)
_VOID_LIFTED_NOTICE = "CollectQuest: The bonus quest is back in reach."
# Longer than default: two lines, and the only warning the day went out of reach. The lifted notice
# just confirms the player's action, so it keeps the default.
_VOID_NOTICE_MS = 7000


def _on_operation_did_execute(changes, handler) -> None:
    """Re-check the bonus quest after anything that could take cards off today's schedule. Catches
    everything, since Anki drops a hook that raises for the rest of the session."""
    global _void_check_seq
    try:
        if not (getattr(changes, "card", False) or getattr(changes, "study_queues", False)):
            return
        _void_check_seq += 1
        seq = _void_check_seq
        QTimer.singleShot(_VOID_CHECK_DEBOUNCE_MS, lambda: _check_cleared_day(seq))
    except Exception as e:
        print(f"CollectQuest: bonus quest re-check could not be scheduled: {e!r}")


def _check_cleared_day(seq: int = 0, debounced: bool = True) -> None:
    """Settle the bonus quest after today's schedule changed: pay a finished day, or announce it
    going out of or back into reach (once, guarded by a saved date)."""
    if debounced and seq != _void_check_seq:
        return
    if mw is None or not mw.col:
        return
    try:
        data = storage.load()
        today = streak.today_str(mw.col)
        if data.get("cleared_bonus_date") == today:
            return
        # One measurement for both outcomes, and nothing is paid or refreshed on the strength of a
        # day that is merely still in progress.
        status = due_baseline.cleared_status(data, mw.col)
        if status is None:
            return
        done, required, voided = status
        if done >= required:
            # Cards can carry the day over the line by leaving it, which no answer follows - so
            # this is the only thing that would ever pay such a day.
            earned = review_rewards.award_cleared_bonus_out_of_band(
                data, mw.col, measured=(done, required)
            )
            if earned is not None:
                data["cleared_bonus_void_date"] = ""
            # Saved either way: the award refreshes the milestone track first, and dropping that
            # would leave an expired buff live in the save until the next answer.
            storage.save(data)
            if earned is not None:
                _announce_earned(earned)
            return
        announced = data.get("cleared_bonus_void_date") == today
        if voided == announced:
            return
        data["cleared_bonus_void_date"] = today if voided else ""
        storage.save(data)
        if voided:
            ui.stacked_tooltip(_VOID_NOTICE, _VOID_NOTICE_MS, parent=mw)
        else:
            ui.stacked_tooltip(_VOID_LIFTED_NOTICE, parent=mw)
    except Exception as e:
        print(f"CollectQuest: bonus quest check failed: {e!r}")


def _announce_earned(earned: dict) -> None:
    """Report one payout: summary box, then a level-up, then the track. Shared by the answer path
    and the out-of-band bonus; one tooltip, since Anki's tooltip is a singleton."""
    # The refresh must stash a finished milestone rather than announce it, or its box and the
    # summary below race for the same slot.
    global _answer_in_progress
    _answer_in_progress = True
    try:
        _refresh_xp_bar()
    finally:
        _answer_in_progress = False
    # Quest rewards only: the level-up's own gold and gems are announced by its own box below, and
    # counting them here would have the quest take credit for them.
    level_gold = earned.get("level_gold", 0)
    level_gems = earned.get("level_gems", 0)
    spoke = ui.show_review_summary_tooltip(
        earned.get("completed_quests") or [],
        earned.get("gold_earned", 0) - level_gold,
        earned.get("gem_earned", 0) - level_gems,
    )
    # A level-up with nothing before it lands at once; behind a quest it waits its turn, so the two
    # are read as two things rather than one box replacing another.
    delay = notices.STAGGER_MS if spoke else 0
    if earned.get("leveled_up"):
        delay = notices.post([ui.level_up_message(level_gold, level_gems)], delay)
    # After the summary, never before: the stacked box picks its slot from what is already on
    # screen, so going first would leave it overlapped by the summary.
    notices.show_queued(earned, delay)


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
        # The dungeon is not unwound: a discovery stays found (so its XP isn't in xp_delta either).
        # Undo costs a review of frozen progress instead, so retrying a missed roll isn't free.
        dungeon.note_undone_review(data)
        if deltas.get("was_correct"):
            data["correct_today"] = max(0, data.get("correct_today", 0) - 1)
        if deltas.get("counted_as_review"):
            # reviews_today gates shop unlock (10 reviews); reverting keeps it in sync with undo
            data["reviews_today"] = max(0, data.get("reviews_today", 0) - 1)
        # Correct-quests read the day's total, not a per-review +1, so they are recomputed.
        correct_today = data.get("correct_today", 0)
        for q in data.get("daily_quests") or []:
            if q.get("id") == quests.QUEST_KIND_CORRECT_REVIEWS:
                # Undoing an answer from before the quest appeared moves its start back with it, so
                # answering that card again counts.
                q["correct_start"] = min(int(q.get("correct_start", 0) or 0), correct_today)
                q["progress"] = quests.correct_quest_progress(q, correct_today)
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
    """True when the operation Anki just undid was a card answer. The operation name is localized,
    so this checks for a missing high-water revlog row instead."""
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
        ui.toggle_progress_panel(mw, _refresh_xp_bar)
    else:
        ui.show_progress_dialog(mw, on_refresh=_refresh_xp_bar)


def _open_options() -> None:
    ui.show_options_dialog(mw, on_refresh=_refresh_xp_bar)


def _open_dungeon() -> None:
    """Open the dungeon window from the bottom bar."""
    ui.show_dungeon_dialog(mw, _refresh_xp_bar)


def _open_shop() -> None:
    data = storage.load()
    if data.get("use_dock_panels"):
        ui.toggle_shop_panel(mw, _refresh_xp_bar)
    else:
        ui.show_shop_dialog(mw, on_refresh=_refresh_xp_bar)


# True while the welcome dialog's exec() runs, so a nested refresh holds back the streak reward (but
# still rebuilds the bar, so "Open Options" changes show up).
_onboarding_dialog_open = False


def _show_onboarding() -> None:
    """The welcome popup. The flag is restored, not cleared, for nested refreshes."""
    global _onboarding_dialog_open
    was_open = _onboarding_dialog_open
    _onboarding_dialog_open = True
    try:
        ui.maybe_show_onboarding(mw, _refresh_xp_bar)
    except Exception:
        pass
    finally:
        _onboarding_dialog_open = was_open


def _daily_bookkeeping(data: dict) -> None:
    """Upkeep every refresh does while a collection is open: streak, day baseline, milestones and
    unlock notices. Saves, and queues what there is to announce."""
    streak.refresh_streak(data, mw.col)
    # Not while the welcome dialog is up: the refresh that opened it is still on the stack and
    # grants the reward once the player clicks OK.
    streak_reward = None if _onboarding_dialog_open else streak.maybe_grant_streak_reward(data, mw.col)
    # Start-of-day due counts, captured here as the one path that fires on profile load, after every
    # answer and after sync.
    try:
        due_baseline.ensure_baseline(data, mw.col)
    except Exception:
        pass
    # Streak milestones finish when the day turns, which no answer would notice. Wrapped like
    # ensure_baseline so bookkeeping can't cost the status bar.
    try:
        milestones.advance_if_complete(data, mw.col)
        notices.milestone_queue.extend(milestones.take_pending_announcements(data))
    except Exception:
        pass
    try:
        notices.queue_unlocks(data)
    except Exception:
        pass
    storage.save(data)
    # Stashed rather than shown, like a completed milestone: the answer's summary has not landed yet.
    if streak_reward:
        notices.pending_streak_reward = streak_reward
    # From here rather than chosen callers, so a completion spotted by any refresh gets reported.
    if not _answer_in_progress:
        notices.schedule()


def _refresh_xp_bar() -> None:
    try:
        mw.statusBar()
    except Exception:
        return
    # The welcome popup goes first, before any streak reward and before the save loads, since it
    # writes the save.
    if mw.col:
        _show_onboarding()
        _daily_bookkeeping(storage.load())
    # One snapshot for the whole bar, taken after the welcome dialog, whose nested event loop can
    # save.
    data = storage.load()
    streak_count = 0
    if mw.col:
        current_days, _ = streak.get_display_streak_days(data, streak.today_epoch(mw.col))
        streak_count = ((current_days - 1) % streak.STREAK_LENGTH) + 1 if current_days > 0 else 0
    fresh_container = ui.mount_status_bar(
        mw, data, streak_count, _open_progress, _open_shop, _open_dungeon
    )
    if data.get("use_dock_panels", False):
        ui.refresh_progress_panel(mw)
    ui.maybe_show_prestige_prompt(mw, _refresh_xp_bar)
    ui.maybe_show_game_finished_prompt(mw, _refresh_xp_bar)
    if fresh_container:
        ui.restore_saved_panels(mw, data, _refresh_xp_bar)


def _on_profile_loaded() -> None:
    notices.profile_closing = False
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


def _dungeon_stage() -> tuple:
    """A small snapshot of the dungeon, compared before and after a sync batch, since synced reviews
    lose the per-answer `earned` the desktop path reports."""
    data = storage.load()
    state = dungeon.get_state(data) or {}
    return (
        dungeon.is_active(data),
        int(state.get("branchings_done", 0)),
        dungeon.treasure_ready(data),
        dungeon.dungeons_claimed(data),
    )


def _dungeon_sync_lines(before: tuple) -> list[str]:
    """What to announce after a sync, from what changed while the batch was credited."""
    was_active, branchings, had_treasure, claimed = before
    now_active, now_branchings, now_treasure, now_claimed = _dungeon_stage()
    earned: dict = {}
    if now_active and not was_active:
        earned["dungeon_entrance"] = True
    # "At least one", not a count: a batch can run several branchings when auto-pick is on. A
    # dungeon that started inside the batch is covered too - branchings is 0 when none was open.
    if now_branchings > branchings:
        earned["dungeon_branching"] = True
    if (now_treasure and not had_treasure) or now_claimed > claimed:
        earned["dungeon_treasure"] = True
    return notices.dungeon_lines(earned)


def _maybe_prompt_dungeon_catch_up() -> None:
    """After a sync that owes a lot of choices, offer to auto-pick them (once). Auto-pick pays less
    (§2), so it trades reward for clicking; treasures are still claimed one at a time."""
    try:
        data = storage.load()
        if dungeon.banked_reviews(data) < dungeon.CATCH_UP_PROMPT_MIN_BANK:
            # Below the line the question is not worth asking, and the one-shot resets with it.
            if data.pop(dungeon.KEY_CATCH_UP_ASKED, None) is not None:
                storage.save(data)
            return
        if dungeon.auto_pick_enabled(data) or data.get(dungeon.KEY_CATCH_UP_ASKED):
            return
        locked = not dungeon.has_auto_pick(data)
        data[dungeon.KEY_CATCH_UP_ASKED] = True
        storage.save(data)
        if not ui.show_catch_up_prompt(mw, locked):
            return
        # Re-read: the prompt was modal and the save is the only thing that carries the answer.
        data = storage.load()
        review_rewards.resolve_dungeon_backlog(data)
        storage.save(data)
        _refresh_xp_bar()
    except Exception as e:
        print(f"CollectQuest: dungeon catch-up prompt failed: {e!r}")


def _on_sync_did_finish() -> None:
    """After sync: process new revlog entries (e.g. from mobile) so quest rewards, XP, gold, gems update."""
    if not mw.col:
        return
    # Credited straight away, so the save is correct even if what follows never runs.
    before = _dungeon_stage()
    summary = revlog_sync.process_synced_revlog(mw.col, silent=True)
    notices.pending_lines.extend(_dungeon_sync_lines(before))

    def _announce() -> None:
        # The profile can be closed in the meantime - an auto-sync on close finishes into this hook.
        if not mw.col:
            return
        if summary:
            ui.show_sync_summary_panel(mw, summary)
        # Dungeon events join the refresh's stacked box, not this reviews/XP panel. Queued after the
        # panel, since the refresh can open a dialog whose exec() would hold it back.
        _refresh_xp_bar()
        # A sync can finish the day with no reviews (cards suspended or deleted elsewhere). Not
        # debounced: the sync is a single event.
        _check_cleared_day(debounced=False)
        # Last of all: it is a modal question, and everything above should be readable first.
        _maybe_prompt_dungeon_catch_up()

    if notices.profile_closing:
        # Sync on profile close: the collection closes as soon as this returns, so announce
        # immediately.
        _announce()
        return
    # Deferred together, since the refresh can pop a dialog. Anki redraws the bar right after this
    # hook anyway (mw.reset() -> state_did_reset).
    QTimer.singleShot(_SYNC_NOTICE_DELAY_MS, _announce)


def _on_state_did_reset(state: str | None = None, _old_state: str | None = None) -> None:
    if state == "review":
        return
    _refresh_xp_bar()


def _on_profile_will_close() -> None:
    notices.profile_closing = True
    # Anything still queued belongs to the closing profile and would otherwise fire against the next
    # one - including dungeon lines a sync finishing into the closing profile queued.
    notices.clear()
    ui.close_panels(mw)


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
    # Suspend, bury and delete all reach the bonus quest the same way: fewer cards on today's
    # schedule. This is the only hook that sees them.
    if hasattr(gui_hooks, "operation_did_execute"):
        gui_hooks.operation_did_execute.append(_on_operation_did_execute)
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
