"""Fractional carry for rewards paid in whole numbers: the remainder accumulates in the save and
pays out once it reaches 1 (6.5 twice pays 6, then 7), so small bonuses aren't truncated away. XP
and gold each have their own."""
from __future__ import annotations

XP_KEY = "xp_fraction"
GOLD_KEY = "gold_fraction"

# Decimal places kept in the save: enough not to lose a fraction, few enough to avoid float noise.
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
    """Turn an exact amount into whole units, carrying the remainder to the next award. Returns the
    whole amount; callers supporting undo must save get() first."""
    if exact <= 0:
        return 0
    # Rounded before the split so the carry can never itself reach 1.
    carried = round(exact + get(data, key), _PRECISION)
    whole = int(carried)
    data[key] = round(carried - whole, _PRECISION)
    return whole
