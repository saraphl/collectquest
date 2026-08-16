"""XP and level logic."""
from __future__ import annotations

# Level-up XP scaling: linear, not exponential.
# XP to go from level L to L+1 = XP_LEVEL_BASE + (L - 1) * XP_LEVEL_INCREMENT
# So level 1→2: 100, 2→3: 120, 3→4: 140, 4→5: 160, ... (keeps leveling frequent and reachable)
XP_LEVEL_BASE = 100       # XP for first level (1→2)
XP_LEVEL_INCREMENT = 20  # extra XP per level (100, 120, 140, 160, ...)

# Difficulty settings: XP per ease (1=Again, 2=Hard, 3=Good, 4=Easy).
# Internal ids are "easy"/"normal"/"hard", but UI names can be
# "Casual", "Steady", "Heavy User".
#
# Only the Good entry is read. Again, Hard and Easy are derived from it as ratios in
# review_rewards._apply_xp_bonus, so the other entries here are historical and unused.
#
# Good is 90% of the original add-on's value, offsetting the XP that Again now pays out. Every
# other ease is a ratio of Good, so they all moved by the same 10%. Fractions are fine: the carry
# in ag/carry.py pays them out rather than dropping them.
DIFFICULTY_XP = {
    "easy":   {1: 0, 2: 8, 3: 9,   4: 12},   # Casual
    "normal": {1: 0, 2: 5, 3: 7.2, 4: 10},   # Steady
    "hard":   {1: 0, 2: 0, 3: 4.5, 4: 6},    # Heavy User
}
DIFFICULTY_DEFAULT = "normal"

# Current difficulty (set by main module from storage)
_current_difficulty: str = DIFFICULTY_DEFAULT


def set_difficulty(difficulty: str) -> None:
    """Set current difficulty (easy/normal/hard)."""
    global _current_difficulty
    if difficulty in DIFFICULTY_XP:
        _current_difficulty = difficulty
    else:
        _current_difficulty = DIFFICULTY_DEFAULT


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


def xp_for_review(ease: int) -> float:
    """XP for a review based on ease (1-4) and current difficulty. Good may be fractional."""
    if not isinstance(ease, int):
        ease = 3  # fallback Good if hook passed wrong type (e.g. card)
    if ease < 1:
        ease = 1
    if ease > 4:
        ease = 4
    xp_table = DIFFICULTY_XP.get(_current_difficulty, DIFFICULTY_XP[DIFFICULTY_DEFAULT])
    return xp_table.get(ease, 0)
