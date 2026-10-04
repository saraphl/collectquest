"""XP and level logic."""
from __future__ import annotations

# Linear level scaling: XP from L to L+1 = XP_LEVEL_BASE + (L - 1) * XP_LEVEL_INCREMENT (100, 120,
# 140, ...).
XP_LEVEL_BASE = 100       # XP for first level (1→2)
XP_LEVEL_INCREMENT = 20  # extra XP per level (100, 120, 140, 160, ...)

# Good XP before items and difficulty; review_rewards derives the other answers from it.
BASE_GOOD_XP = 7

# Ids "easy"/"normal"/"hard" show as Casual, Steady and Heavy User. Applied after every item bonus,
# so the gap holds at any level. Dungeon chances move half as far.
DIFFICULTY_MULTIPLIER = {"easy": 1.3, "normal": 1.0, "hard": 0.7}
DIFFICULTY_DEFAULT = "normal"


def difficulty_multiplier(data: dict) -> float:
    """Reward multiplier for the save's difficulty."""
    default = DIFFICULTY_MULTIPLIER[DIFFICULTY_DEFAULT]
    return DIFFICULTY_MULTIPLIER.get(data.get("difficulty", DIFFICULTY_DEFAULT), default)


def dungeon_difficulty_multiplier(data: dict) -> float:
    """Half the difficulty's increase or decrease, for dungeon discovery and exploration rolls."""
    return 1 + (difficulty_multiplier(data) - 1) / 2


def xp_for_this_level(level: int) -> int:
    """XP needed to go from this level to the next (e.g. level 1 → 2 needs 100)."""
    if level < 1:
        return 0
    return XP_LEVEL_BASE + (level - 1) * XP_LEVEL_INCREMENT


def xp_required_for_level(level: int) -> int:
    """Total XP needed to reach this level (cumulative)."""
    if level <= 1:
        return 0
    # Sum of xp_for_this_level(i) for i in 1..level-1
    # = (level-1)*BASE + INCREMENT * (0+1+...+(level-2)) = (level-1)*BASE + INCREMENT*(level-2)*(level-1)//2
    n = level - 1
    return n * XP_LEVEL_BASE + XP_LEVEL_INCREMENT * (n - 1) * n // 2


def level_from_total_xp(total_xp: int) -> int:
    """Largest level achievable with given total XP."""
    level = 1
    while total_xp >= xp_required_for_level(level + 1):
        level += 1
    return level


def xp_needed_for_next_level(total_xp: int) -> int:
    """Approximate XP needed from current state to reach the next level."""
    level = level_from_total_xp(total_xp)
    return xp_for_this_level(level)


def xp_progress_in_level(total_xp: int) -> tuple[int, int, int]:
    """Returns (current_level, xp_in_current_level, xp_needed_for_next)."""
    lev = level_from_total_xp(total_xp)
    xp_at_lev = xp_required_for_level(lev)
    xp_next = xp_required_for_level(lev + 1)
    xp_in_level = total_xp - xp_at_lev
    xp_needed = xp_next - xp_at_lev
    return lev, xp_in_level, xp_needed
