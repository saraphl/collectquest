"""XP and level logic."""
from __future__ import annotations

# Level-up XP scaling: linear, not exponential.
# XP to go from level L to L+1 = XP_LEVEL_BASE + (L - 1) * XP_LEVEL_INCREMENT
# So level 1→2: 100, 2→3: 120, 3→4: 140, 4→5: 160, ... (keeps leveling frequent and reachable)
XP_LEVEL_BASE = 100       # XP for first level (1→2)
XP_LEVEL_INCREMENT = 20  # extra XP per level (100, 120, 140, 160, ...)

# Difficulty settings: XP per ease (1=Again, 2=Hard, 3=Good, 4=Easy)
# Internal ids are "easy"/"normal"/"hard", but UI names can be
# "Casual", "Steady", "Heavy User".
DIFFICULTY_XP = {
    # "easy" → Casual: Again=0, Hard≈-20%, Good=10, Easy≈+20%
    "easy":   {1: 0, 2: 8, 3: 10, 4: 12},  # 0, 8, 10, 12
    # "normal" → Steady: Again=0, Hard≈-40%, Good=8, Easy≈+20%
    "normal": {1: 0, 2: 5, 3: 8,  4: 10},  # 0, 5, 8, 10
    # "hard" → Heavy User: Again=0, Hard=0, Good=5, Easy≈+20%
    "hard":   {1: 0, 2: 0, 3: 5,  4: 6},   # 0, 0, 5, 6
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


def get_difficulty() -> str:
    """Get current difficulty."""
    return _current_difficulty


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


def xp_for_review(ease: int) -> int:
    """XP for a review based on ease (1-4) and current difficulty."""
    if not isinstance(ease, int):
        ease = 3  # fallback Good if hook passed wrong type (e.g. card)
    if ease < 1:
        ease = 1
    if ease > 4:
        ease = 4
    xp_table = DIFFICULTY_XP.get(_current_difficulty, DIFFICULTY_XP[DIFFICULTY_DEFAULT])
    return xp_table.get(ease, 0)
