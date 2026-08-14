"""
7-day streak: heatmap-style, revlog-only. No manual counting — we derive from Anki revlog
so streak works across devices (desktop + mobile after sync).

Single streak concept:
- Display streak (current_streak_start_date/current_streak_end_date) is the source of truth.
- 7-day rewards are derived from display streak length and streak_rewards_claimed.
- streak_start_date is kept only for backward compatibility and is no longer used operationally.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from . import prestige

if TYPE_CHECKING:
    from anki.collection import Collection

STREAK_LENGTH = 7
REWARD_TYPES = ("xp", "gem", "gold")

# How far back to look for activity days (heatmap-style query)
ACTIVITY_DAYS_LOOKBACK_SEC = 400 * 86400


def _rollover_hours(col: "Collection") -> int:
    try:
        return int(col.conf.get("rollover", 4))
    except Exception:
        return 4


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


def get_activity_days(col: "Collection", state: dict[str, Any]) -> set[int]:
    """
    Set of day epochs (start of day in user timezone) that have at least one review.
    Uses same revlog grouping as heatmap addon; sync-safe (revlog is source of truth).
    """
    rollover = _rollover_hours(col)
    offset_sec = rollover * 3600
    try:
        # Heatmap-style: group revlog by day (id is ms, offset in seconds)
        rows = col.db.all(
            "SELECT DISTINCT CAST(STRFTIME('%s', datetime(id/1000 - ?, 'unixepoch'), 'localtime', 'start of day') AS int) AS day "
            "FROM revlog WHERE id/1000 >= strftime('%s','now') - ?",
            offset_sec,
            ACTIVITY_DAYS_LOOKBACK_SEC,
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
    else:
        # Have a run ending at recent
        if stored_start != run_start:
            if stored_start:
                old_len = _run_length_from_start(activity, stored_start)
                if old_len > longest:
                    state["longest_streak_days"] = old_len
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


def refresh_streak(state: dict[str, Any], col: "Collection") -> tuple[int, dict[str, Any] | None]:
    """
    Recompute streak from revlog (heatmap-style), update display streak fields,
    and return 7-square progress for UI.

    Reward granting is intentionally not done here; use maybe_grant_streak_reward()
    from one centralized call path.
    """
    activity = get_activity_days(col, state)
    today = today_epoch(col)
    _update_display_streak(state, activity, today)

    # Display streak used for UI (squares + text)
    current_days, _ = get_display_streak_days(state, today)

    # Squares = how many days in the *current 7-day window* (the one containing today) have activity.
    # So on day 8 before any review, that window has 0 days → 0/7; after one review → 1/7.
    run_start = state.get("current_streak_start_date") or 0
    block_index = -1
    if run_start <= 0 or today < run_start:
        streak_squares = 0
    else:
        # 7-day window that contains today (block 0 = days 0–6 from run_start, block 1 = days 7–13, …)
        block_index = (today - run_start) // 86400 // STREAK_LENGTH
        window_start = run_start + block_index * STREAK_LENGTH * 86400
        streak_squares = 0
        for i in range(STREAK_LENGTH):
            day_epoch = window_start + i * 86400
            if day_epoch <= today and day_epoch in activity:
                streak_squares += 1

    # Choose the next reward type only when we've entered the new 7-day window (e.g. 8th day),
    # so the UI doesn’t switch to the next reward icon right after claiming.
    # Only roll when we've entered the next week (block_index >= 1). Never roll in block 0 so we
    # don't re-roll every open when last_block was -1, and after claim type stays None until day 8.
    last_block = int(state.get("streak_reward_type_block", -1) or -1)
    if run_start > 0 and block_index >= 1 and block_index > last_block:
        state["streak_reward_type"] = random.choice(REWARD_TYPES)
        state["streak_reward_type_block"] = block_index

    return (streak_squares, None)


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
    # Keep streak_start_date untouched (legacy key; not used for current streak logic).
    state["streak_reward_type"] = None
    return reward


def update_streak_on_rollover(state: dict[str, Any], col: "Collection") -> dict[str, Any] | None:
    """
    Backward-compat helper for day-change call sites. Recomputes streak state only.
    """
    refresh_streak(state, col)
    return None


def _apply_xp_bonus(data: dict[str, Any], base_xp: float, owned: list) -> int:
    from . import shop
    pct = shop.xp_bonus_percent(owned or []) + prestige.prestige_xp_bonus_percent(data)
    return int(base_xp * (1 + pct / 100))


def _apply_gold_bonus(data: dict[str, Any], base_gold: float, owned: list) -> int:
    from . import shop
    pct = shop.gold_bonus_percent(owned or []) + prestige.prestige_gold_bonus_percent(data)
    return int(base_gold * (1 + pct / 100))


def grant_streak_reward(data: dict[str, Any], reward_type: str | None = None) -> dict[str, Any]:
    """Grant the streak reward. Modifies data in place. Returns dict for UI/toast."""
    from . import shop

    level = data.get("level", 1)
    owned = data.get("owned_collectibles", [])
    level_bonus = 1 + (level // 10) * 0.1

    kind = reward_type if reward_type in REWARD_TYPES else random.choice(REWARD_TYPES)

    multiplier = prestige.prestige_streak_multiplier(data)

    if kind == "xp":
        base_xp = (150 + level * 3) * level_bonus
        amount = _apply_xp_bonus(data, base_xp, owned)
        # Apply prestige streak multiplier (x2, x3, ...) to XP-only reward
        amount = int(amount * multiplier)
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
        chance = shop.luck_gem_chance_percent(owned)
        if chance > 0 and random.randint(0, 99) < chance:
            gems = shop.award_random_gem(gems)
            amount += 1
        data["gems"] = gems
        base_gold = (5 + level // 2) * level_bonus + shop.gold_flat(owned)
        gold_added = _apply_gold_bonus(data, base_gold, owned)
        gold_added = int(gold_added * multiplier)
        data["money"] = data.get("money", 0) + gold_added
        return {"type": "gem", "amount": amount, "gold": gold_added}

    base_gold = (30 + level) * level_bonus
    gold_amount = _apply_gold_bonus(data, base_gold, owned)
    gold_amount = int(gold_amount * multiplier)
    data["money"] = data.get("money", 0) + gold_amount
    base_xp = (15 + level) * level_bonus
    xp_added = _apply_xp_bonus(data, base_xp, owned)
    xp_added = int(xp_added * multiplier)
    data["total_xp"] = data.get("total_xp", 0) + xp_added
    return {"type": "gold", "amount": gold_amount, "xp": xp_added}
