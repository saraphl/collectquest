"""
7-day streak: heatmap-style, revlog-only. No manual counting — we derive from Anki revlog
so streak works across devices (desktop + mobile after sync).

Single streak concept:
- Display streak (current_streak_start_date/current_streak_end_date) is the source of truth.
- 7-day rewards are derived from display streak length and streak_rewards_claimed.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from . import carry, prestige

if TYPE_CHECKING:
    from anki.collection import Collection

STREAK_LENGTH = 7
REWARD_TYPES = ("xp", "gem", "gold")

# How far back to look for activity days (heatmap-style query)
ACTIVITY_DAYS_LOOKBACK_SEC = 400 * 86400


def rollover_hours(col: "Collection | None" = None) -> int:
    """Scheduler's 'Next day starts at' (hours past midnight). Falls back to Anki's default of 4."""
    if col is None:
        try:
            from aqt import mw
            col = mw.col
        except Exception:
            col = None
    if col is None:
        return 4
    try:
        return int(col.conf.get("rollover", 4))
    except Exception:
        return 4


# Backwards-compatible alias (used internally by this module).
_rollover_hours = rollover_hours


def today_str(col: "Collection | None" = None) -> str:
    """
    Local date of the current *scheduler* day (YYYY-MM-DD).
    Reviews done before rollover belong to the previous day, same as Anki's own day accounting.
    Use this for every daily reset/gate (quests, reviews_today, shop) so they follow "Next day starts at".
    """
    return (datetime.now() - timedelta(hours=rollover_hours(col))).strftime("%Y-%m-%d")


def today_epoch(col: "Collection") -> int:
    """Epoch (seconds) of start of 'today' in user's day boundary (rollover). Same logic as heatmap."""
    rollover = _rollover_hours(col)
    try:
        return col.db.scalar(
            "SELECT CAST(STRFTIME('%s', datetime(strftime('%s','now') - ?*3600, 'unixepoch'), 'localtime', 'start of day') AS int)",
            rollover,
        ) or 0
    except Exception:
        return 0


def _day_start_ms(col: "Collection", day_epoch: int) -> int:
    """Epoch ms at which a day-epoch (as produced by today_epoch) begins."""
    return (day_epoch + _rollover_hours(col) * 3600) * 1000


def _activity_window_start_ms(col: "Collection") -> int:
    """
    Oldest revlog id the activity scan considers, anchored to the start of the current day.

    Shared with _activity_signature, so a row cannot enter or leave the scan's range without also
    moving the signature that decides whether to rescan.
    """
    return _day_start_ms(col, today_epoch(col)) - ACTIVITY_DAYS_LOOKBACK_SEC * 1000


def get_activity_days(col: "Collection", state: dict[str, Any]) -> set[int]:
    """
    Set of day epochs (start of day in user timezone) that have at least one review.
    Uses same revlog grouping as heatmap addon; sync-safe (revlog is source of truth).
    """
    rollover = _rollover_hours(col)
    offset_sec = rollover * 3600
    try:
        # Heatmap-style: group revlog by day (id is ms, offset in seconds). Written as
        # `id >= <constant>`, never `id/1000 >= ...`, which would turn a range seek into a full
        # scan. Anchored to the start of the scheduler day rather than "now", so the window cannot
        # drop its oldest day mid-session without _activity_signature noticing.
        rows = col.db.all(
            "SELECT DISTINCT CAST(STRFTIME('%s', datetime(id/1000 - ?, 'unixepoch'), 'localtime', 'start of day') AS int) AS day "
            "FROM revlog WHERE id >= ?",
            offset_sec,
            _activity_window_start_ms(col),
        )
        days = set()
        for row in rows or []:
            if isinstance(row, (list, tuple)) and len(row) >= 1:
                d = row[0]
            else:
                d = row
            if isinstance(d, (int, float)) and d:
                days.add(int(d))
        return days
    except Exception:
        return set()


def _run_length_from_start(activity: set[int], start_epoch: int, max_days: int = 400) -> int:
    """Count consecutive days with activity starting at start_epoch (inclusive)."""
    n = 0
    d = start_epoch
    for _ in range(max_days):
        if d not in activity:
            return n
        n += 1
        d += 86400
    return n


def _longest_run_in_activity(activity: set[int]) -> int:
    """Longest consecutive run in activity (for one-time backfill after upgrade)."""
    if not activity:
        return 0
    sorted_days = sorted(activity)
    best = 1
    cur = 1
    for i in range(1, len(sorted_days)):
        if sorted_days[i] == sorted_days[i - 1] + 86400:
            cur += 1
        else:
            best = max(best, cur)
            cur = 1
    return max(best, cur)


def _reset_run_counters(state: dict[str, Any]) -> None:
    """
    Clear the per-run counters when a streak ends or restarts.

    Both counters describe windows within the current run and are stored absolutely, so surviving a
    break would make a fresh streak need 28 days rather than 7 to pay out again.
    """
    state["streak_rewards_claimed"] = 0
    state["streak_reward_type"] = None
    state["streak_reward_type_block"] = -1


def _ensure_streak_floor(state: dict[str, Any], today: int) -> int:
    """
    First scheduler day this profile ran CollectQuest. The streak never reaches behind it. 0 = none.

    The streak comes from revlog, which knows nothing about when the add-on was installed, so
    without a floor a long-time Anki user arrives at level 1 with a 40-day streak and a reward
    already payable. The displayed run becomes min(days since install, real run), and since
    everything reads the stored run start, that limit reaches the reward windows, the milestone
    objectives and the accumulator alike.

    Stamped on the first refresh of a fresh save; saves that predate the key carry 0, since
    flooring their existing streak now would cut it to a day. Prestige and reset carry it over.
    """
    try:
        floor = int(state.get("streak_floor_epoch") or 0)
    except (TypeError, ValueError):
        # A hand-edited save still loads (a bad hash only sets a flag), so re-stamp rather than
        # let int() take the whole refresh down.
        floor = 0
        state["streak_floor_epoch"] = None
    if not today:
        # today_epoch returns 0 when its query fails, and 0 already means "no floor" in an older
        # save - stamping it would grant that exemption permanently. The next refresh stamps it.
        return floor
    if state.get("streak_floor_epoch") is None:
        state["streak_floor_epoch"] = today
        return today
    if floor > today:
        # Stamped by a clock that was set ahead; left alone it would hide the streak until the
        # calendar caught up. The floor only ever moves backwards.
        state["streak_floor_epoch"] = today
        return today
    return floor


def _update_display_streak(state: dict[str, Any], activity: set[int], today: int, floor: int) -> None:
    """
    Update current_streak_start_date and longest_streak_days from revlog activity.
    Current streak = consecutive days with activity ending on the *most recent* day with activity (<= today).
    So you see your streak on load even before studying today; it extends when you study today.
    On upgrade, longest_streak_days is 0; we backfill once from longest run in revlog (so it's preserved).
    Days before `floor` (see _ensure_streak_floor) are not this profile's to count: the run is
    clamped to start there, and the one-time longest backfill ignores anything older.
    """
    # Most recent day with activity (<= today) so streak shows on load before you study today
    recent = max((d for d in activity if d <= today), default=0)
    if floor and recent < floor:
        # Everything in the revlog predates the install: nothing here is this profile's streak yet.
        recent = 0
    if not recent:
        run_len = 0
        run_start = 0
    else:
        # Run ending at recent (walk backwards from recent)
        run_len = 0
        day = recent
        for _ in range(400):
            if day not in activity:
                break
            run_len += 1
            day -= 86400
        run_start = recent - (run_len - 1) * 86400 if run_len else 0
        if floor and run_start and run_start < floor:
            # The run began before the add-on did. Clamped at the write, not per reader, so every
            # reader of the stored start describes the same run.
            run_start = floor
            run_len = (recent - run_start) // 86400 + 1

    stored_start = state.get("current_streak_start_date") or 0
    longest = state.get("longest_streak_days") or 0
    # One-time backfill after upgrade: longest was never stored; use longest run that ended before today
    if longest == 0 and activity:
        past_only = activity - {today}
        if floor:
            past_only = {d for d in past_only if d >= floor}
        if past_only:
            backfill = _longest_run_in_activity(past_only)
            if backfill > 0:
                state["longest_streak_days"] = backfill
                longest = backfill

    if run_len == 0:
        # No activity in window: streak broken (if we had one)
        if stored_start:
            old_len = _run_length_from_start(activity, stored_start)
            if old_len > longest:
                state["longest_streak_days"] = old_len
            state["current_streak_start_date"] = 0
            state["current_streak_end_date"] = 0
            _reset_run_counters(state)
    else:
        # Have a run ending at recent
        if stored_start != run_start:
            if stored_start:
                old_len = _run_length_from_start(activity, stored_start)
                if old_len > longest:
                    state["longest_streak_days"] = old_len
                # A later start means the old run ended and a new one began: reset its counters.
                # An *earlier* start is the same run growing backwards (e.g. a sync filled in a
                # missing day), so the already-claimed windows must stand.
                if run_start > stored_start:
                    _reset_run_counters(state)
            state["current_streak_start_date"] = run_start
        state["current_streak_end_date"] = recent


def get_display_streak_days(state: dict[str, Any], today_epoch_val: int) -> tuple[int, int]:
    """
    Return (current_streak_days, longest_streak_days) for UI.
    current = run length (start to end inclusive); end stored so we show correct length before you study today.
    Backward compat: if no end stored, use (today - start)/86400 + 1.
    """
    start = state.get("current_streak_start_date") or 0
    end = state.get("current_streak_end_date") or 0
    if not start:
        return (0, state.get("longest_streak_days") or 0)
    if end:
        current = (end - start) // 86400 + 1
    else:
        current = (today_epoch_val - start) // 86400 + 1
    return (max(0, current), state.get("longest_streak_days") or 0)


def _activity_signature(col: "Collection", today: int) -> tuple[int, int] | None:
    """
    (rows in the lookback window before today, rows today), or None if it could not be read.

    Counts, not MAX(id): a synced review backfills below the current maximum and would leave it
    untouched, as would deleting any row but the newest. Anchored to today's start rather than
    "now", so the figure holds still for the whole day.
    """
    today_start_ms = _day_start_ms(col, today)
    window_start_ms = _activity_window_start_ms(col)
    # Two scalars rather than one two-column row: db.all's row shape varies between Anki versions,
    # and a surprise here would read as "cannot read" and force the full scan forever.
    try:
        before_today = int(
            col.db.scalar(
                "SELECT COUNT(*) FROM revlog WHERE id >= ? AND id < ?",
                window_start_ms,
                today_start_ms,
            )
            or 0
        )
        today_rows = int(
            col.db.scalar("SELECT COUNT(*) FROM revlog WHERE id >= ?", today_start_ms) or 0
        )
    except Exception:
        return None
    return (before_today, today_rows)


def _activity_scan_needed(state: dict[str, Any], col: "Collection", today: int) -> bool:
    """
    Whether the activity-day set has to be rebuilt, or the last result still stands.

    get_activity_days walks the whole 400-day window, too expensive to repeat per answered card.
    Decided from the revlog itself rather than from invalidation hooks, so a sync backfilling an
    older day or an undo emptying today is detected rather than having to be announced.

    Unchanged means: no row added or removed before today, today still has a row, and today was
    already counted - more rows on a day that already counts cannot change a set of days.
    """
    scan = state.get("streak_scan") or {}
    if scan.get("day") != today or "before_today" not in scan:
        return True  # never scanned, or the scheduler day turned over
    sig = _activity_signature(col, today)
    if sig is None:
        return True
    before_today, today_rows = sig
    try:
        recorded = int(scan.get("before_today") or 0)
    except (TypeError, ValueError):
        return True  # unreadable record: scan rather than trust it
    if before_today != recorded:
        return True  # a past day gained or lost rows
    if today_rows <= 0:
        return True  # today emptied, so it may have dropped out of the streak
    # Today has rows: a scan is needed only if it is not already counted, i.e. this is its first.
    return state.get("current_streak_end_date") != today


def refresh_streak(state: dict[str, Any], col: "Collection") -> None:
    """
    Recompute streak from revlog (heatmap-style) and update the display streak fields.

    Skips the revlog scan when nothing can have changed since the last one; see
    _activity_scan_needed. Returns nothing: callers read the displayed count from
    get_display_streak_days(state, today), which needs only state.

    Reward granting is intentionally not done here; use maybe_grant_streak_reward()
    from one centralized call path.
    """
    from . import milestones

    today = today_epoch(col)
    floor = _ensure_streak_floor(state, today)
    if not today:
        # The clock query failed. Carrying on would find no activity at or before epoch 0, take the
        # streak-broken branch and clear streak_rewards_claimed - after which the next healthy
        # refresh would pay the same rewards again. Skipping costs one refresh.
        return
    if _activity_scan_needed(state, col, today):
        activity = get_activity_days(col, state)
        _update_display_streak(state, activity, today, floor)
        # Recorded after the scan, so the next call compares against the revlog as it stood when
        # the set was last built. Dropped if unreadable, which just means scanning again.
        sig = _activity_signature(col, today)
        if sig is None:
            state.pop("streak_scan", None)
        else:
            state["streak_scan"] = {"day": today, "before_today": sig[0]}

    # Which 7-day window today falls in (block 0 = days 0-6 from run_start). From the run start
    # alone, so it stays correct on the path that skipped the scan.
    run_start = state.get("current_streak_start_date") or 0
    block_index = -1
    if run_start > 0 and today >= run_start:
        block_index = (today - run_start) // 86400 // STREAK_LENGTH

    # Rolled only on entering a new window (block_index >= 1), so the icon does not switch to the
    # next reward right after claiming, and block 0 does not re-roll on every open.
    last_block = int(state.get("streak_reward_type_block", -1) or -1)
    if run_start > 0 and block_index >= 1 and block_index > last_block:
        state["streak_reward_type"] = random.choice(REWARD_TYPES)
        state["streak_reward_type_block"] = block_index

    # The accumulator charges off the run just recomputed, and this is the one place that knows the
    # streak changed - so the track's housekeeping runs here rather than in its readers.
    milestones.refresh(state, col)


def maybe_grant_streak_reward(state: dict[str, Any], col: "Collection") -> dict[str, Any] | None:
    """
    Grant at most one pending 7-day streak reward, based on current display streak.
    Returns reward dict when granted, else None.
    """
    today = today_epoch(col)
    current_days, _ = get_display_streak_days(state, today)
    windows = current_days // STREAK_LENGTH
    claimed = int(state.get("streak_rewards_claimed", 0) or 0)
    if current_days < STREAK_LENGTH or windows <= claimed:
        return None
    reward_type = state.get("streak_reward_type") or random.choice(REWARD_TYPES)
    reward = grant_streak_reward(state, reward_type=reward_type)
    state["streak_rewards_claimed"] = windows
    state["streak_reward_type"] = None
    return reward


def _xp_with_bonus(data: dict[str, Any], base_xp: float, owned: list) -> float:
    """Exact XP after % bonuses. Left unrounded so the caller can apply its own multipliers first."""
    from . import review_rewards
    return base_xp * (1 + review_rewards.total_xp_bonus_percent(data, owned or []) / 100)


def _gold_with_bonus(data: dict[str, Any], base_gold: float, owned: list) -> float:
    """Exact gold after % bonuses. Left unrounded so the caller can apply its own multipliers first."""
    from . import review_rewards
    return base_gold * (1 + review_rewards.total_gold_bonus_percent(data, owned or []) / 100)


def grant_streak_reward(data: dict[str, Any], reward_type: str | None = None) -> dict[str, Any]:
    """Grant the streak reward. Modifies data in place. Returns dict for UI/toast."""
    from . import shop

    level = data.get("level", 1)
    owned = data.get("owned_collectibles", [])
    level_bonus = 1 + (level // 10) * 0.1

    kind = reward_type if reward_type in REWARD_TYPES else random.choice(REWARD_TYPES)

    multiplier = prestige.prestige_streak_multiplier(data)
    # "+% 7-day streak rewards" from collectibles (Island, Red Gem, Snow Banner). The effect is
    # primarily about gems, so it is added to the bonus-gem roll; it also scales the XP and gold
    # payouts, otherwise the item would do nothing in the two weeks out of three that roll xp/gold.
    streak_pct = shop.streak_reward_bonus_percent(owned)
    streak_scale = 1 + streak_pct / 100

    if kind == "xp":
        base_xp = (150 + level * 3) * level_bonus
        # Prestige streak multiplier (x2, x3, ...) applies to the XP-only reward, and is folded in
        # before rounding so it and the % bonus share a single carry.
        exact_xp = _xp_with_bonus(data, base_xp, owned) * multiplier * streak_scale
        amount = carry.award(data, carry.XP_KEY, exact_xp)
        data["total_xp"] = data.get("total_xp", 0) + amount
        return {"type": "xp", "amount": amount}

    if kind == "gem":
        base_gems = 2 if level >= 20 else 1
        gems = data.get("gems", shop.default_gems())
        # Apply multiplier to base gems (so 1→2→3 etc.)
        base_gems_multi = max(1, int(base_gems * multiplier))
        from . import review_rewards

        # Routed through the reward path rather than awarded directly, so the gem buffs reach the
        # streak the same way they reach every other reward.
        data["gems"] = gems
        amount = review_rewards.award_reward_gems(
            data, [shop.random_gem_color() for _ in range(base_gems_multi)]
        )
        gems = data.get("gems", gems)
        # Gem luck multiplies rather than adds: with the collection worth +200 the old additive
        # form guaranteed this gem outright. What it scales is the streak's own reward stat, so a
        # player with neither still rolls nothing here - the same floor the additive form had.
        chance = review_rewards.scaled_gem_chance(streak_pct, data, owned)
        data["gems"] = gems
        amount += review_rewards.award_reward_gems(
            data, [shop.random_gem_color() for _ in range(review_rewards.roll_gem_count(chance))]
        )
        gems = data.get("gems", gems)
        base_gold = (5 + level // 2) * level_bonus + shop.gold_flat(owned)
        exact_gold = _gold_with_bonus(data, base_gold, owned) * multiplier * streak_scale
        gold_added = carry.award(data, carry.GOLD_KEY, exact_gold)
        data["money"] = data.get("money", 0) + gold_added
        return {"type": "gem", "amount": amount, "gold": gold_added}

    base_gold = (30 + level) * level_bonus
    gold_amount = carry.award(
        data, carry.GOLD_KEY, _gold_with_bonus(data, base_gold, owned) * multiplier * streak_scale
    )
    data["money"] = data.get("money", 0) + gold_amount
    base_xp = (15 + level) * level_bonus
    xp_added = carry.award(
        data, carry.XP_KEY, _xp_with_bonus(data, base_xp, owned) * multiplier * streak_scale
    )
    data["total_xp"] = data.get("total_xp", 0) + xp_added
    return {"type": "gold", "amount": gold_amount, "xp": xp_added}
