"""
Start-of-day due counts, the basis for quest targets (see docs/quest-revamp.md).

Anki's due counts shrink as the player reviews, so the number a quest target is derived from has to
be captured once per scheduler day and persisted. When the day was started on another device the
desktop opens with the counts already drawn down, so the baseline is reconstructed rather than
snapshotted:

    baseline = current capped due + distinct cards already FINISHED today

Every card due at start-of-day is either still due or has been finished today. "Finished" is the
load-bearing word: a card failed with Again drops back into relearning and is still counted in
today's numbers, so counting every card *answered* would double-count each lapse. This composes
correctly with deck limits: a 100/day limit with 40 done on the phone shows 60 remaining, and
60 + 40 = 100.

Phase 1: nothing reads the baseline yet. It is captured so the reconstruction can be checked against
a real collection (Options → "Quest baseline (debug)") before quest targets depend on it.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from . import streak

if TYPE_CHECKING:
    from anki.collection import Collection

# revlog.type values meaning "a due card was answered": 1 = review, 2 = relearn.
# Excludes 0 (new/learning), 3 (filtered/cram) and 4 (manual reschedule), none of which represent a
# card that was counted as due at the start of the day.
_DUE_REVIEW_TYPES = "(1, 2)"


def day_start_timestamp_ms(col: "Collection | None" = None) -> int:
    """
    Epoch ms at which the current scheduler day began (honours 'Next day starts at').

    Built from an aware local timestamp: a naive datetime resolves .timestamp() against whatever UTC
    offset applies to the replaced wall-clock time, so on a DST changeover the cutoff would land an
    hour out and misfile revlog rows near the boundary.
    """
    rollover = streak.rollover_hours(col)
    now = datetime.now().astimezone()
    shifted = now - timedelta(hours=rollover)
    day_start = shifted.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=rollover)
    # Re-resolve the offset for the computed instant rather than reusing `now`'s.
    return int(day_start.replace(tzinfo=None).astimezone().timestamp() * 1000)


# Invisible characters people put in deck names to force sort order. str.strip() does not remove
# them: U+200B and friends are format characters, not whitespace, so .isspace() is False.
_INVISIBLE = "​‌‍⁠﻿"


def display_deck_name(name: str) -> str:
    """Deck name as shown to the player: invisible sort-order characters removed, quoted.

    Anki lets a deck be called "​Kanji writing" to control where it sorts; rendered raw in a
    quest label that shows as a stray leading gap. Quoting also keeps the deck name legible when it
    contains spaces or "::".
    """
    cleaned = (name or "").strip().strip(_INVISIBLE).strip()
    return f'"{cleaned}"'


def _node_due(node: Any) -> int:
    """Due count for one deck node: reviews + interday/intraday learning, as the deck list shows it.

    These are the limit-capped counts, i.e. already min(cards due, deck preset daily limit). The
    *_uncapped variants are deliberately not used: a target above what Anki will serve is unwinnable.
    """
    return int(getattr(node, "review_count", 0) or 0) + int(getattr(node, "learn_count", 0) or 0)


def _iter_nodes(tree: Any) -> list[Any]:
    """Flatten the due tree into a list of deck nodes (the synthetic root is not included)."""
    out: list[Any] = []
    stack = list(getattr(tree, "children", []) or [])
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(getattr(node, "children", []) or [])
    return out


class BaselineUnavailable(Exception):
    """The collection could not be measured. Raised rather than reporting zero due cards, which
    would be stored as a real baseline and shrink every quest target for the rest of the day."""


def live_counts(col: "Collection") -> tuple[int, dict[str, dict[str, Any]]]:
    """
    Due counts as they stand right now: (total, {deck_id: {"name", "due", "filtered"}}).

    Per-deck counts are subtree-aggregated, exactly what the deck list shows, so a parent's figure
    includes its children's. The total therefore sums only the top-level decks.

    Filtered decks are counted in the total — Custom Study moves genuinely due cards into them, and
    while a card sits in one it is counted there rather than in its home deck, so skipping them would
    undercount the day. They are flagged instead, so quest rolling can decline them as targets.
    """
    try:
        tree = col.sched.deck_due_tree()
    except Exception as e:
        raise BaselineUnavailable(f"deck_due_tree failed: {e}") from e
    if tree is None:
        raise BaselineUnavailable("deck_due_tree returned None")

    total = sum(_node_due(child) for child in (getattr(tree, "children", []) or []))

    decks: dict[str, dict[str, Any]] = {}
    for node in _iter_nodes(tree):
        did = int(getattr(node, "deck_id", 0) or 0)
        try:
            # Node names are single components ("Kanji"); ask the deck manager for the full path.
            name = col.decks.name(did)
        except Exception:
            name = getattr(node, "name", "") or ""
        decks[str(did)] = {
            "name": name,
            "due": _node_due(node),
            "filtered": bool(getattr(node, "filtered", False)),
        }
    return (total, decks)


# A card answered today is only "finished" if it no longer contributes to today's counts. A card
# failed with Again goes into relearning and is STILL counted today, so adding it back would
# double-count it — the baseline would grow by one per lapse over the course of a day.
_STILL_DUE_TODAY = (
    "(c.queue = 1 OR (c.queue IN (2, 3) AND c.due <= ?))"
)


def answered_today(col: "Collection") -> int:
    """Distinct cards answered in the current scheduler day (diagnostics only)."""
    try:
        return int(
            col.db.scalar(
                f"SELECT count(DISTINCT cid) FROM revlog WHERE id >= ? AND type IN {_DUE_REVIEW_TYPES}",
                day_start_timestamp_ms(col),
            )
            or 0
        )
    except Exception:
        return 0


def finished_today_total(col: "Collection") -> int:
    """
    How many distinct cards answered today are done for today.

    Split out from finished_today so callers that only need the total — the clear-the-day bonus,
    which runs on every answer — do not also pay for the per-deck GROUP BY and its deck-name lookups.
    """
    try:
        today_no = int(col.sched.today)
    except Exception as e:
        raise BaselineUnavailable(f"col.sched.today unavailable: {e}") from e
    try:
        return int(
            col.db.scalar(
                "SELECT count(DISTINCT r.cid) FROM revlog r JOIN cards c ON c.id = r.cid "
                f"WHERE r.id >= ? AND r.type IN {_DUE_REVIEW_TYPES} AND NOT {_STILL_DUE_TODAY}",
                day_start_timestamp_ms(col),
                today_no,
            )
            or 0
        )
    except Exception:
        return 0


def finished_today(col: "Collection") -> tuple[int, dict[str, int]]:
    """
    Cards answered today that are done for today: (distinct total, {deck_name: distinct}).

    Counts distinct card ids so learning-step repeats don't inflate the figure; only review and
    relearn rows, so new cards and manual reschedules are excluded; and excludes cards still sitting
    in today's queues, which are already represented in the live due count.
    """
    cutoff = day_start_timestamp_ms(col)
    try:
        today_no = int(col.sched.today)
    except Exception as e:
        # Falling back to 0 would silently disable the "still due today" half of the filter — review
        # due values are days-since-creation and always positive, so every answered card would count
        # as finished and the baseline would be inflated by the whole remaining queue.
        raise BaselineUnavailable(f"col.sched.today unavailable: {e}") from e
    where = (
        f"r.id >= ? AND r.type IN {_DUE_REVIEW_TYPES} AND NOT {_STILL_DUE_TODAY}"
    )
    total = finished_today_total(col)
    by_deck: dict[str, int] = {}
    try:
        rows = (
            col.db.all(
                "SELECT CASE WHEN c.odid != 0 THEN c.odid ELSE c.did END AS deck, count(DISTINCT r.cid) "
                f"FROM revlog r JOIN cards c ON c.id = r.cid WHERE {where} GROUP BY deck",
                cutoff,
                today_no,
            )
            or []
        )
        for row in rows:
            try:
                did, n = int(row[0]), int(row[1])
            except (TypeError, ValueError, IndexError):
                continue
            try:
                name = col.decks.name(did)
            except Exception:
                continue
            by_deck[name] = by_deck.get(name, 0) + n
    except Exception:
        pass
    return (total, by_deck)


def has_new_cards(col: "Collection | None") -> bool:
    """
    True when the collection holds any new card, scheduled today or not.

    Deliberately not the scheduler's new_count, which respects the deck preset's new-cards-per-day
    limit and reads zero for players who keep new cards disabled and introduce them through Custom
    Study. queue = 0 is new; suspended (-1) and buried (-2, -3) are excluded as unstudiable.
    """
    if col is None:
        return False
    try:
        return bool(col.db.scalar("SELECT 1 FROM cards WHERE queue = 0 LIMIT 1"))
    except Exception:
        return False


def _done_for_deck(deck_name: str, done_by_deck: dict[str, int]) -> int:
    """Cards done today in this deck or any of its subdecks (same prefix rule quests use)."""
    return sum(
        n
        for name, n in done_by_deck.items()
        if name == deck_name or name.startswith(deck_name + "::")
    )


def reconstruct(col: "Collection") -> dict[str, Any]:
    """Start-of-day due counts, adding back whatever has already been finished today."""
    total_now, decks_now = live_counts(col)
    return reconstruct_from(col, total_now, decks_now)


def reconstruct_from(
    col: "Collection", total_now: int, decks_now: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """reconstruct() against counts the caller has already measured, so they need not be re-read."""
    done_total, done_by_deck = finished_today(col)
    decks: dict[str, dict[str, Any]] = {}
    for did, info in decks_now.items():
        decks[did] = {
            "name": info["name"],
            "due": info["due"] + _done_for_deck(info["name"], done_by_deck),
            "filtered": info["filtered"],
        }
    return {
        "date": streak.today_str(col),
        "total": total_now + done_total,
        "decks": decks,
    }


def cleared_progress(
    state: dict[str, Any], col: "Collection | None"
) -> tuple[int, int] | None:
    """
    Progress toward clearing the day's due cards: (finished, total), or None when not measurable.

    total is the start-of-day baseline; finished is how many of those cards are done for today.

    Counted with finished_today rather than as (baseline - still due), which looks equivalent but is
    not. Answering an unseen new card moves it from the new queue, which is not counted as due, into
    the learning queue, which is — so subtracting the live count made progress run *backwards* by
    one every time a new card was introduced. finished_today only looks at review and relearn rows,
    so new cards never touch this figure at all.

    Again still does not advance it: a review card failed with Again sits in the relearning queue
    and stays "still due today", which finished_today excludes until it graduates.
    """
    baseline = state.get("quest_due_baseline") or {}
    total = int(baseline.get("total", 0) or 0)
    if total <= 0 or col is None:
        return None
    if baseline.get("date") != _safe_today(col):
        return None
    try:
        done = finished_today_total(col)
    except Exception:
        return None
    # Clamped: cards finished today that were never in the baseline (unburied, or made due by an
    # edit) would otherwise read as more than 100%.
    return (max(0, min(total, done)), total)


def ensure_baseline(state: dict[str, Any], col: "Collection | None") -> dict[str, Any] | None:
    """
    Capture the baseline once per scheduler day, into state["quest_due_baseline"].
    Returns today's baseline, or None when it could not be measured. Never raises.

    None is meaningful: it says "unknown", not "nothing due". Callers must not roll quests from it,
    or a transient failure would fix low-volume targets in place for the whole day.
    """
    if col is None:
        current = state.get("quest_due_baseline") or {}
        return current if current.get("date") == _safe_today(col) else None
    today = _safe_today(col)
    if today is None:
        return None
    current = state.get("quest_due_baseline") or {}
    if current.get("date") == today:
        return current
    try:
        baseline = reconstruct(col)
    except Exception:
        return None
    state["quest_due_baseline"] = baseline
    return baseline


def _safe_today(col: "Collection | None") -> str | None:
    try:
        return streak.today_str(col)
    except Exception:
        return None
