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

    Shared with _activity_signature so the scan and the change-detection probe describe exactly the
    same range; if they disagreed, a row entering or leaving the difference between them would move
    the activity set without moving the signature.
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
        # Heatmap-style: group revlog by day (id is ms, offset in seconds).
        # The window is expressed as `id >= <constant>` rather than `id/1000 >= <constant>`: dividing
        # the primary key forces the planner to compute it for every row, turning what should be a
        # range seek into a full scan of the whole revlog.
        # Anchored to the start of the current scheduler day, not to "now", so the window holds
        # still for the whole day. A window sliding with the clock would quietly drop its oldest day
        # mid-session, and _activity_signature — which measures the same window to decide whether a
        # rescan is needed — would not see that happen.
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

    streak_rewards_claimed and streak_reward_type_block count windows *within the current run*
    (see storage._default_state). Both are stored absolutely, so if they survive a break the next
    run has to out-grow the old counts before it behaves: after claiming 3 windows, a fresh streak
    would need 28 consecutive days rather than 7 to pay out again, and the reward icon would stay
    blank until block 4.
    """
    state["streak_rewards_claimed"] = 0
    state["streak_reward_type"] = None
    state["streak_reward_type_block"] = -1


def _update_display_streak(state: dict[str, Any], activity: set[int], today: int) -> None:
    """
    Update current_streak_start_date and longest_streak_days from revlog activity.
    Current streak = consecutive days with activity ending on the *most recent* day with activity (<= today).
    So you see your streak on load even before studying today; it extends when you study today.
    On upgrade, longest_streak_days is 0; we backfill once from longest run in revlog (so it's preserved).
    """
    # Most recent day with activity (<= today) so streak shows on load before you study today
    recent = max((d for d in activity if d <= today), default=0)
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

    stored_start = state.get("current_streak_start_date") or 0
    longest = state.get("longest_streak_days") or 0
    # One-time backfill after upgrade: longest was never stored; use longest run that ended before today
    if longest == 0 and activity:
        past_only = activity - {today}
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

    Deliberately not MAX(id): a review synced from another device carries the timestamp of when it
    was answered, so backfilling yesterday inserts *below* the current maximum and leaves it
    untouched — as does deleting any row that is not the newest. Counts see both.

    Anchored to today's start rather than to "now", so the figure is stable for the whole day
    instead of drifting as rows age out of the window.
    """
    today_start_ms = _day_start_ms(col, today)
    window_start_ms = _activity_window_start_ms(col)
    # Two scalars rather than one row of two columns: db.all's row shape varies between Anki
    # versions (see the flattened-result handling in revlog_sync), and a shape surprise here would
    # be swallowed as "cannot read", permanently forcing the full scan this exists to avoid.
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

    get_activity_days walks the whole 400-day revlog window, far too expensive to repeat after every
    answered card. The set can only differ if the revlog changed, so this decides from the revlog
    itself rather than from invalidation hooks — a sync that backfills an older day, or an undo that
    empties today, is *detected* instead of having to be announced, which is what makes it safe.

    The set is unchanged only when no row was added or removed on any day before today, today still
    has at least one row, and today was already counted. More rows on a day that already counts
    cannot change a set of days.
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
    today = today_epoch(col)
    if _activity_scan_needed(state, col, today):
        activity = get_activity_days(col, state)
        _update_display_streak(state, activity, today)
        # Recorded after the scan, so the next call compares against the revlog as it stood when
        # the set was last built. Dropped if unreadable, which just means scanning again.
        sig = _activity_signature(col, today)
        if sig is None:
            state.pop("streak_scan", None)
        else:
            state["streak_scan"] = {"day": today, "before_today": sig[0]}

    # Which 7-day window today falls in (block 0 = days 0-6 from run_start, block 1 = 7-13, …).
    # Derived from the run start alone, so it needs no activity set and stays correct on the path
    # that skipped the scan.
    run_start = state.get("current_streak_start_date") or 0
    block_index = -1
    if run_start > 0 and today >= run_start:
        block_index = (today - run_start) // 86400 // STREAK_LENGTH

    # Choose the next reward type only when we've entered the new 7-day window (e.g. 8th day),
    # so the UI doesn’t switch to the next reward icon right after claiming.
    # Only roll when we've entered the next week (block_index >= 1). Never roll in block 0 so we
    # don't re-roll every open when last_block was -1, and after claim type stays None until day 8.
    last_block = int(state.get("streak_reward_type_block", -1) or -1)
    if run_start > 0 and block_index >= 1 and block_index > last_block:
        state["streak_reward_type"] = random.choice(REWARD_TYPES)
        state["streak_reward_type_block"] = block_index


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
    from . import shop
    pct = shop.xp_bonus_percent(owned or []) + prestige.prestige_xp_bonus_percent(data)
    return base_xp * (1 + pct / 100)


def _gold_with_bonus(data: dict[str, Any], base_gold: float, owned: list) -> float:
    """Exact gold after % bonuses. Left unrounded so the caller can apply its own multipliers first."""
    from . import shop
    pct = shop.gold_bonus_percent(owned or []) + prestige.prestige_gold_bonus_percent(data)
    return base_gold * (1 + pct / 100)


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
        for _ in range(base_gems_multi):
            gems = shop.award_random_gem(gems)
        amount = base_gems_multi
        # Gem luck multiplies rather than adds: with the collection worth +200 the old additive
        # form guaranteed this gem outright. What it scales is the streak's own reward stat, so a
        # player with neither still rolls nothing here - the same floor the additive form had.
        from . import review_rewards
        chance = review_rewards.scaled_gem_chance(streak_pct, data, owned)
        for _ in range(review_rewards.roll_gem_count(chance)):
            gems = shop.award_random_gem(gems)
            amount += 1
        data["gems"] = gems
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
