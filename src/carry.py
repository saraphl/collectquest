"""
Fractional carry for rewards that have to be paid out in whole numbers.

Modifiers routinely land between whole numbers — a +3% bonus on 8 XP is 8.24, and a review is only
worth 5-12 XP to begin with. Truncating each award on its own would throw the fraction away every
single time, so a bonus below roughly +13% would never pay out at all. Instead the leftover
accumulates in the save and is paid as a whole unit once it reaches 1: two awards of 6.5 give 6 and
then 7.

XP and gold each carry their own remainder. Both are always under 1, so neither is worth showing.
"""
from __future__ import annotations

XP_KEY = "xp_fraction"
GOLD_KEY = "gold_fraction"

# Decimal places kept in the save. Enough that a fraction is never lost, few enough that the stored
# number stays short and free of float noise like 0.2400000000000002.
_PRECISION = 6


def get(data: dict, key: str) -> float:
    """The unpaid fraction currently carried under key, always in [0, 1)."""
    try:
        return float(data.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def restore(data: dict, key: str, value: float) -> None:
    """Put back a carried fraction. Used by undo, which must not let the carry drift."""
    data[key] = round(max(0.0, float(value)), _PRECISION)


def award(data: dict, key: str, exact: float) -> int:
    """
    Turn an exact amount into whole units, carrying the remainder over to the next award.

    Returns the whole amount to grant; the caller adds it to the running total, so undo bookkeeping
    stays in one place. Callers that support undo must save get() from before the call.
    """
    if exact <= 0:
        return 0
    # Rounded before the split so the carry can never itself reach 1.
    carried = round(exact + get(data, key), _PRECISION)
    whole = int(carried)
    data[key] = round(carried - whole, _PRECISION)
    return whole
