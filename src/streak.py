"""7-day streak, derived from the revlog so it works across devices. The display streak
(current_streak_start_date/end_date) is the source of truth; rewards derive from its length and
streak_rewards_claimed."""
from __future__ import annotations

import calendar
import random
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from . import carry, prestige

if TYPE_CHECKING:
    from anki.collection import Collection

STREAK_LENGTH = 7
REWARD_TYPES = ("xp", "gem", "gold")

DAY_SEC = 86400
# How far SQLite's local-to-UTC conversion may land from a day's true start: the size of a DST
# shift. It misplaces the boundary when the rollover hour falls inside the shift itself.
_BOUNDARY_SLACK_MS = 3600 * 1000


def rollover_hours(col: "Collection | None" = None) -> int:
    """Scheduler's 'Next day starts at' (hours past midnight), capped to 0-23 as Anki caps it. Falls
    back to Anki's default of 4."""
    if col is None:
        try:
            from aqt import mw
            col = mw.col
        except Exception:
            col = None
    if col is None:
        return 4
    try:
        return max(0, min(23, int(col.conf.get("rollover", 4))))
    except Exception:
        return 4


# Backwards-compatible alias (used internally by this module).
_rollover_hours = rollover_hours


def _scheduler_date(ts: float | None, rollover: int) -> date:
    moment = datetime.now() if ts is None else datetime.fromtimestamp(ts)
    return (moment - timedelta(hours=rollover)).date()


def scheduler_date(col: "Collection | None" = None, ts: float | None = None) -> date:
    """Scheduler day holding `ts` (default: now): local time less the rollover, as Anki splits days.
    Used by every daily gate and the streak."""
    return _scheduler_date(ts, rollover_hours(col))


def today_str(col: "Collection | None" = None) -> str:
    """Current scheduler day as YYYY-MM-DD, the key every daily reset (quests, shop) is stamped with."""
    return scheduler_date(col).isoformat()


def _date_epoch(d: date) -> int:
    """Day epoch of a date: its midnight read as UTC, the form streak state stores days in."""
    return calendar.timegm(d.timetuple())


def today_epoch(col: "Collection | None" = None) -> int:
    """Day epoch of the current scheduler day."""
    return _date_epoch(scheduler_date(col))


def day_start_ms(col: "Collection | None" = None, day_epoch: int | None = None) -> int:
    """Epoch ms at which a scheduler day (default: today) begins, i.e. its lowest revlog id."""
    rollover = rollover_hours(col)
    d = _scheduler_date(None, rollover) if day_epoch is None else (
        date(1970, 1, 1) + timedelta(days=int(day_epoch) // DAY_SEC)
    )
    start = int(datetime(d.year, d.month, d.day, rollover).timestamp())
    if _scheduler_date(start - 1, rollover) == d:
        # The rollover hour fell into a DST gap, so the day began at the shift: somewhere in the hour
        # before. Found by bisection, as the shift need not sit on the hour.
        lo = start - 3600
        while start - lo > 1:
            mid = (lo + start) // 2
            if _scheduler_date(mid, rollover) == d:
                start = mid
            else:
                lo = mid
    return start * 1000


def _day_of_sql(id_expr: str, rollover: int) -> str:
    """scheduler_date of a revlog id as a day epoch, in SQL. Both go through the C library's
    localtime, so the two agree exactly."""
    return (
        "CAST(STRFTIME('%s', (" + id_expr + ") / 1000, 'unixepoch', 'localtime', '-" + str(rollover)
        + " hours', 'start of day') AS int)"
    )


def _approx_start_ms_sql(day_expr: str, rollover: int) -> str:
    """day_start_ms in SQL, give or take _BOUNDARY_SLACK_MS."""
    return (
        "STRFTIME('%s', " + day_expr + ", 'unixepoch', '+" + str(rollover) + " hours', 'utc') * 1000"
    )


def _run_ending(col: "Collection", before_ms: int, floor: int) -> tuple[int, int] | None:
    """(first, last) day of the consecutive-day run ending before `before_ms`, not behind `floor`.
    (0, 0) for none, None if unreadable. Rows are classified per day, since edges drift on DST
    days."""
    rollover = rollover_hours(col)
    try:
        latest = col.db.scalar(
            "SELECT MAX(id) FROM revlog WHERE id >= ? AND id < ?",
            day_start_ms(col, floor) if floor else 0,
            int(before_ms),
        )
        if latest is None:
            return (0, 0)
        last = _date_epoch(scheduler_date(col, int(latest) / 1000))
        # Each step goes one day further back, so the walk ends: at the floor, or at the first
        # empty day, which the start of the revlog is at the latest. Wrapped in SELECT: Anki treats
        # SQL that doesn't start with it as a write, and a write clears the undo queue.
        first = col.db.scalar(
            "SELECT (WITH RECURSIVE w(day) AS (SELECT ? UNION ALL"
            " SELECT day - 86400 FROM w WHERE day - 86400 >= ? AND EXISTS ("
            "  SELECT 1 FROM revlog"
            "   WHERE id >= " + _approx_start_ms_sql("day - 86400", rollover) + " - " + str(_BOUNDARY_SLACK_MS) +
            "   AND id < " + _approx_start_ms_sql("day", rollover) + " + " + str(_BOUNDARY_SLACK_MS) +
            "   AND " + _day_of_sql("id", rollover) + " = day - 86400))"
            " SELECT MIN(day) FROM w)",
            last,
            floor,
        )
    except Exception:
        return None
    return (int(first), last)


def _run_days(run: tuple[int, int]) -> int:
    """Length in days of a (first day, last day) run; 0 for no run."""
    return (run[1] - run[0]) // DAY_SEC + 1 if run[0] else 0


def _ended_run_length(
    col: "Collection", state: dict[str, Any], stored_start: int, before_ms: int, floor: int
) -> int:
    """Length of the displayed run that has now ended, for longest_streak_days. Re-measured, since a
    sync may have extended it."""
    stored_end = state.get("current_streak_end_date") or 0
    length = (stored_end - stored_start) // DAY_SEC + 1 if stored_end >= stored_start else 0
    prior = _run_ending(col, before_ms, floor)
    if prior and prior[0] == stored_start:
        length = max(length, _run_days(prior))
    return length


def _longest_run_before(col: "Collection", before_ms: int, floor: int) -> int:
    """Longest run below `before_ms`, run by run from the newest; for the one-time backfill."""
    best = 0
    while True:
        run = _run_ending(col, before_ms, floor)
        if not run or not run[0]:
            return best
        best = max(best, _run_days(run))
        before_ms = day_start_ms(col, run[0])


def _reset_run_counters(state: dict[str, Any]) -> None:
    """Clear the per-run counters when a streak ends or restarts, or a fresh streak would need 28
    days to pay out rather than 7."""
    state["streak_rewards_claimed"] = 0
    state["streak_reward_type"] = None
    state["streak_reward_type_block"] = -1


def _ensure_streak_floor(state: dict[str, Any], today: int) -> int:
    """First scheduler day this profile ran CollectQuest (0 = none), which the streak never reaches
    behind, so long-time Anki users don't arrive with a payable streak. Stamped on a fresh save's
    first refresh; older saves carry 0. Prestige and reset keep it."""
    try:
        floor = int(state.get("streak_floor_epoch") or 0)
    except (TypeError, ValueError):
        # A hand-edited save still loads (a bad hash only sets a flag), so re-stamp rather than
        # let int() take the whole refresh down.
        floor = 0
        state["streak_floor_epoch"] = None
    if state.get("streak_floor_epoch") is None:
        state["streak_floor_epoch"] = today
        return today
    if floor > today:
        # Stamped by a clock that was set ahead; left alone it would hide the streak until the
        # calendar caught up. The floor only ever moves backwards.
        state["streak_floor_epoch"] = today
        return today
    return floor


def _update_display_streak(
    state: dict[str, Any], col: "Collection", run: tuple[int, int], today: int, floor: int
) -> None:
    """Store `run` (see _run_ending) as the displayed streak, clamped to `floor`, and update
    longest_streak_days. Ends on the latest study day, so it shows before today's first review."""
    run_start, recent = run
    stored_start = state.get("current_streak_start_date") or 0
    longest = state.get("longest_streak_days") or 0
    if longest == 0:
        # Backfilled from the revlog for old saves and after a prestige or wipe resets it. Cheap to
        # repeat while it finds nothing, as that means no review since the floor before today.
        longest = _longest_run_before(col, day_start_ms(col, today), floor)
        if longest:
            state["longest_streak_days"] = longest

    if stored_start and stored_start != run_start and (not run_start or run_start > stored_start):
        # The displayed run ended. An *earlier* start is instead the same run growing backwards
        # (a sync filled in a missing day), so its claimed windows stand.
        ended = _ended_run_length(
            col, state, stored_start, day_start_ms(col, run_start or today + DAY_SEC), floor
        )
        if ended > longest:
            state["longest_streak_days"] = ended
        _reset_run_counters(state)
    state["current_streak_start_date"] = run_start
    state["current_streak_end_date"] = recent


def get_display_streak_days(state: dict[str, Any], today_epoch_val: int) -> tuple[int, int]:
    """(current_streak_days, longest_streak_days) for the UI, from the stored start and end. Without
    a stored end, uses (today - start)/86400 + 1."""
    start = state.get("current_streak_start_date") or 0
    end = state.get("current_streak_end_date") or 0
    if not start:
        return (0, state.get("longest_streak_days") or 0)
    if end:
        current = (end - start) // 86400 + 1
    else:
        current = (today_epoch_val - start) // 86400 + 1
    return (max(0, current), state.get("longest_streak_days") or 0)


def refresh_streak(state: dict[str, Any], col: "Collection") -> None:
    """Recompute the display streak from revlog (uncached; about 3.5 us per day). Read the count
    with get_display_streak_days(); rewards come only from maybe_grant_streak_reward()."""
    from . import milestones

    today = today_epoch(col)
    floor = _ensure_streak_floor(state, today)
    run = _run_ending(col, day_start_ms(col, today + DAY_SEC), floor)
    if run is None:
        # Unreadable revlog. Carrying on would read as a broken streak and clear
        # streak_rewards_claimed - after which the next healthy refresh would pay them again.
        return
    _update_display_streak(state, col, run, today, floor)

    # Which 7-day window today falls in (block 0 = days 0-6 from run_start).
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
    """Grant at most one pending 7-day streak reward from the display streak. Returns it, or
    None."""
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
    # "+% 7-day streak rewards" (Island, Red Gem, Snow Banner): mainly the bonus-gem roll, but also
    # scales XP and gold so it works on non-gem weeks.
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
        # Gem luck multiplies the streak's own reward stat, so without that stat nothing rolls here.
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
