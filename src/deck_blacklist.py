"""Decks left out of quests (Options > Deck blacklist). Kept in the collection's config, where deck
ids belong; each day's baseline snapshots it, so a change applies from the next day."""
from __future__ import annotations

from typing import Any

CONFIG_KEY = "collectquest_blacklisted_decks"

def _ids(raw: Any) -> list[int]:
    out: list[int] = []
    for v in raw or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            pass
    return out


def configured(col: Any) -> list[int]:
    """Deck ids crossed out in Options right now. Empty when unreadable."""
    if col is None:
        return []
    try:
        return _ids(col.get_config(CONFIG_KEY, []))
    except Exception:
        return []


def set_configured(col: Any, ids: Any) -> None:
    col.set_config(CONFIG_KEY, sorted(set(_ids(ids))))


def baseline_ids(baseline: dict[str, Any] | None) -> list[int]:
    """The deck blacklist a day's baseline was measured with."""
    return _ids((baseline or {}).get("deck_blacklist"))


def expand(col: Any, ids: list[int]) -> frozenset[int]:
    """The given decks plus their subdecks, for SQL filters. Deleted decks drop out."""
    out: set[int] = set()
    if col is None:
        return frozenset()
    for did in ids:
        try:
            out.update(int(d) for d in col.decks.deck_and_child_ids(did))
        except Exception:
            pass
    return frozenset(out)


def excluded(col: Any, baseline: dict[str, Any] | None) -> frozenset[int]:
    """Deck ids the day's quests ignore."""
    return expand(col, baseline_ids(baseline))


def sql_filter(deck_expr: str, excluded_ids: frozenset[int]) -> str:
    """' AND <deck_expr> NOT IN (...)', or '' with nothing excluded. Ids are ints, so inlined."""
    if not excluded_ids:
        return ""
    return f" AND {deck_expr} NOT IN ({','.join(str(int(d)) for d in sorted(excluded_ids))})"


def covers(col: Any, ids: list[int], deck_name: str | None) -> bool:
    """Whether a deck is blacklisted or under a blacklisted deck, by the "::" rule deck quests use."""
    if not ids or not deck_name or col is None:
        return False
    from .quests import _MISSING_DECK_NAME, deck_matches

    for did in ids:
        try:
            name = col.decks.name(did)
        except Exception:
            continue
        if name != _MISSING_DECK_NAME and deck_matches(deck_name, name):
            return True
    return False
