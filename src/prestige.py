"""Prestige math and helpers (points, upgrades, bonuses)."""
from __future__ import annotations

from typing import Any, Dict

from . import shop

PRESTIGE_MIN_LEVEL = 50
# What a prestige pays at the unlock level, and how many levels above it buy each extra point. Every
# payout quote derives from these.
PRESTIGE_POINTS_AT_UNLOCK = 2
LEVELS_PER_EXTRA_POINT = 10
START_GOLD_PER_LEVEL = 100
# Each level of the XP bonus / gold bonus upgrade adds this much percent.
UPGRADE_STEP_PERCENT = 30
# Percent of Gem luck per upgrade level (the `quest_reward` key predates the gem merge). Matches the
# step above, but kept separate as it prices a different stat.
QUEST_REWARD_STEP_PERCENT = 30


def prestige_points_gain(level: int) -> int:
    """Points gained when prestiging at this level (0 below the threshold):
    PRESTIGE_POINTS_AT_UNLOCK, plus one per LEVELS_PER_EXTRA_POINT above it (50 → 2, 60 → 3)."""
    if level < PRESTIGE_MIN_LEVEL:
        return 0
    return PRESTIGE_POINTS_AT_UNLOCK + (level - PRESTIGE_MIN_LEVEL) // LEVELS_PER_EXTRA_POINT


def levels_to_next_point(level: int) -> int:
    """Levels still to climb before the payout rises by one, or 0 when there's nothing to announce
    (including exactly on a step). Below the threshold it counts to the unlock level; above, steps
    count from the unlock level."""
    if level < PRESTIGE_MIN_LEVEL:
        return PRESTIGE_MIN_LEVEL - level
    past_step = (level - PRESTIGE_MIN_LEVEL) % LEVELS_PER_EXTRA_POINT
    return (LEVELS_PER_EXTRA_POINT - past_step) % LEVELS_PER_EXTRA_POINT


def prestige_item_points(level: int, owned_ids: list[str]) -> int:
    """Extra points the collection grants for a prestige at this level; zero below the threshold.
    Kept out of prestige_points_gain so a tome can never make a player eligible. owned_ids is
    required, so forgetting it fails loudly."""
    if prestige_points_gain(level) <= 0:
        return 0
    return shop.prestige_bonus_points(owned_ids)


def total_prestige_points_gain(level: int, owned_ids: list[str]) -> int:
    """Points actually paid out for a prestige at this level: level payout plus item bonuses."""
    return prestige_points_gain(level) + prestige_item_points(level, owned_ids)


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
    """Multiplier for 7-day streak rewards (XP, gold, gems): +100% per streak_bonus level (x1, x2,
    x3, …)."""
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

