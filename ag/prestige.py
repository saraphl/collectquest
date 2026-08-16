"""Prestige math and helpers (points, upgrades, bonuses)."""
from __future__ import annotations

from typing import Any, Dict

PRESTIGE_MIN_LEVEL = 50
START_GOLD_PER_LEVEL = 100
# Each level of Global XP / Global gold adds this much percent.
UPGRADE_STEP_PERCENT = 30
# Each level of Quest reward adds this much percent.
QUEST_REWARD_STEP_PERCENT = 40


def prestige_points_gain(level: int) -> int:
    """Points gained when prestiging at this level (0 if below threshold).

    Rule:
    - 2 points at level 50
    - +1 extra point for every full 10 levels above 50 (60→3, 70→4, …).
    """
    if level < PRESTIGE_MIN_LEVEL:
        return 0
    return 2 + max(0, (level - PRESTIGE_MIN_LEVEL) // 10)


def levels_to_next_point(level: int) -> int:
    """
    Levels still to climb before the payout goes up by one, or 0 when there is nothing to announce.

    Below the threshold the first points arrive at level 50, not at the next multiple of ten:
    reaching level 20 grants nothing, so counting towards it would promise a reward that is not
    there. At or above the threshold the payout steps on each multiple of ten, and a level that is
    already a multiple returns 0 so the caller can omit the line rather than print "in 0 levels".
    """
    if level < PRESTIGE_MIN_LEVEL:
        return PRESTIGE_MIN_LEVEL - level
    return (10 - level % 10) % 10


def can_prestige(level: int) -> bool:
    """True if player can prestige in normal flow (non-admin)."""
    return prestige_points_gain(level) > 0


def _upgrades_from_state(state: Dict[str, Any]) -> Dict[str, int]:
    ups = state.get("prestige_upgrades") or {}
    if not isinstance(ups, dict):
        return {
            "xp_percent": 0,
            "gold_percent": 0,
            "start_gold": 0,
            "streak_bonus": 0,
            "quest_reward": 0,
        }
    # Ensure keys exist
    return {
        "xp_percent": int(ups.get("xp_percent", 0) or 0),
        "gold_percent": int(ups.get("gold_percent", 0) or 0),
        "start_gold": int(ups.get("start_gold", 0) or 0),
        "streak_bonus": int(ups.get("streak_bonus", 0) or 0),
        "quest_reward": int(ups.get("quest_reward", 0) or 0),
    }


def prestige_xp_bonus_percent(state: Dict[str, Any]) -> int:
    """Total XP bonus % from prestige upgrades."""
    ups = _upgrades_from_state(state)
    return UPGRADE_STEP_PERCENT * ups["xp_percent"]


def prestige_gold_bonus_percent(state: Dict[str, Any]) -> int:
    """Total gold bonus % from prestige upgrades."""
    ups = _upgrades_from_state(state)
    return UPGRADE_STEP_PERCENT * ups["gold_percent"]


def prestige_start_gold_bonus(state: Dict[str, Any]) -> int:
    """Extra starting gold from prestige upgrades."""
    ups = _upgrades_from_state(state)
    return START_GOLD_PER_LEVEL * ups["start_gold"]


def prestige_streak_multiplier(state: Dict[str, Any]) -> float:
    """Multiplier for 7-day streak rewards (XP, gold, and gems).

    Each level of the streak_bonus upgrade adds +100% to the reward:
    level 0 → x1, level 1 → x2, level 2 → x3, etc.
    """
    ups = _upgrades_from_state(state)
    lvl = max(0, ups.get("streak_bonus", 0))
    return 1.0 + float(lvl)


def prestige_quest_reward_bonus_percent(state: Dict[str, Any]) -> int:
    """Total quest reward bonus % from prestige upgrades."""
    ups = _upgrades_from_state(state)
    return QUEST_REWARD_STEP_PERCENT * ups["quest_reward"]


def available_prestige_points(state: Dict[str, Any]) -> int:
    """Points available to spend in the prestige shop."""
    total = int(state.get("prestige_points_total", 0) or 0)
    spent = int(state.get("prestige_points_spent", 0) or 0)
    avail = total - spent
    return max(0, avail)


def upgrade_cost(current_level: int) -> int:
    """Cost in prestige points for the next level of an upgrade."""
    base_cost = 1
    return base_cost + max(0, int(current_level))


def spend_prestige_points(state: Dict[str, Any], cost: int) -> bool:
    """Spend prestige points if available. Returns True on success."""
    if cost <= 0:
        return True
    total = int(state.get("prestige_points_total", 0) or 0)
    spent = int(state.get("prestige_points_spent", 0) or 0)
    if spent + cost > total:
        return False
    state["prestige_points_spent"] = spent + cost
    return True

