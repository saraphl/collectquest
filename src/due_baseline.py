"""
Start-of-day due counts, the basis for quest targets. Reconstructed rather than snapshotted, since
counts shrink as the player reviews and a day started elsewhere arrives drawn down:

    baseline = current capped due + distinct cards already FINISHED today

"Finished", because an Again card is still in today's counts. Which revlog rows count is set by
counts_as_due_review_sql(), which must mirror the deck list; quests.py credits by the same rule.
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from . import streak

if TYPE_CHECKING:
    from anki.collection import Collection

# revlog.type values meaning "a due card was answered": 1 = review, 2 = relearn. Excludes 3-5
# (filtered preview, reschedules); type 0 is admitted conditionally, see _WAS_LEARNING_AT_DAY_START.
_DUE_REVIEW_TYPES = "(1, 2)"

def counts_as_due_review_sql(cutoff_sql: str = "?") -> str:
    """
    SQL predicate over an aliased revlog row `r`: was this answer part of today's due count?
    Shared by the clear-the-day and review quests, so targets and progress agree.

    Type 0 rows count only if the card's last row before the cutoff was type 0 too (in learning
    as the day began). cutoff_sql is "?" or a literal. The lookup uses ix_revlog_cid.
    """
    was_learning_at_day_start = (
        f"(SELECT p.type FROM revlog p WHERE p.cid = r.cid AND p.id < {cutoff_sql}"
        " ORDER BY p.id DESC LIMIT 1) = 0"
    )
    return f"(r.type IN {_DUE_REVIEW_TYPES} OR (r.type = 0 AND {was_learning_at_day_start}))"


_COUNTS_AS_DUE_REVIEW = counts_as_due_review_sql()


# Invisible characters people put in deck names to force sort order. str.strip() does not remove
# them: U+200B and friends are format characters, not whitespace, so .isspace() is False.
_INVISIBLE = "​‌‍⁠﻿"


# Deck names long enough to dominate a quest line are cut to this, with an ellipsis appended. Anki
# puts no limit on deck names, and a quest label is one line among several in a narrow panel.
_DECK_NAME_ELLIPSIS = "..."
_DECK_NAME_MAX = 35
# Derived so the cut plus the ellipsis always lands inside the budget.
_DECK_NAME_TRUNCATED_TO = _DECK_NAME_MAX - len(_DECK_NAME_ELLIPSIS)


def display_deck_name(name: str) -> str:
    """Deck name as shown to the player: invisible sort-order characters removed, quoted, and
    truncated past _DECK_NAME_MAX so a long name can't overflow the panel."""
    cleaned = (name or "").strip().strip(_INVISIBLE).strip()
    if len(cleaned) > _DECK_NAME_MAX:
        cleaned = cleaned[:_DECK_NAME_TRUNCATED_TO] + _DECK_NAME_ELLIPSIS
    return f'"{cleaned}"'


def _node_due(node: Any) -> int:
    """Due count for one deck node (reviews + learning), limit-capped as the deck list shows it. The
    uncapped variants would allow unwinnable targets."""
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
    """Due counts right now: (total, {deck_id: {"name", "due", "filtered"}}). Per-deck counts
    include children, so the total sums top-level decks only. Filtered decks count but are flagged
    so quests decline them as targets."""
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


# "Finished" means no longer in today's counts; an Again card is still counted, so adding it back
# would grow the baseline by one per lapse.
_STILL_DUE_TODAY = (
    "(c.queue = 1 OR (c.queue IN (2, 3) AND c.due <= ?))"
)


def _answered_where(cutoff: int) -> tuple[str, list[int]]:
    """WHERE clause for "answered today" with its bindings, returned together so the order can't
    drift."""
    return (f"r.id >= ? AND {_COUNTS_AS_DUE_REVIEW}", [cutoff, cutoff])


def _finished_where(cutoff: int, today_no: int) -> tuple[str, list[int]]:
    """WHERE clause for "answered today and done for today", with its bindings. See _answered_where."""
    clause, params = _answered_where(cutoff)
    return (f"{clause} AND NOT {_STILL_DUE_TODAY}", [*params, today_no])


def answered_today(col: "Collection") -> int:
    """Distinct cards answered in the current scheduler day (diagnostics only). Unlike
    finished_today, includes cards still due and deleted cards."""
    cutoff = streak.day_start_ms(col)
    where, params = _answered_where(cutoff)
    try:
        return int(
            col.db.scalar(f"SELECT count(DISTINCT r.cid) FROM revlog r WHERE {where}", *params)
            or 0
        )
    except Exception:
        return 0


def finished_today_total(
    col: "Collection", cutoff: int | None = None, today_no: int | None = None
) -> int:
    """Distinct cards answered today that are done for today, without the per-deck GROUP BY (the
    clear-the-day check runs on every answer). Kept separate so a breakdown failure can't sink
    it."""
    if today_no is None:
        try:
            today_no = int(col.sched.today)
        except Exception as e:
            raise BaselineUnavailable(f"col.sched.today unavailable: {e}") from e
    if cutoff is None:
        cutoff = streak.day_start_ms(col)
    where, params = _finished_where(cutoff, today_no)
    try:
        return int(
            col.db.scalar(
                "SELECT count(DISTINCT r.cid) FROM revlog r JOIN cards c ON c.id = r.cid "
                f"WHERE {where}",
                *params,
            )
            or 0
        )
    except Exception:
        return 0


def finished_today(col: "Collection") -> tuple[int, dict[str, int]]:
    """Cards answered today that are done for today: (distinct total, {deck_name: distinct}). Only
    rows _COUNTS_AS_DUE_REVIEW admits, excluding cards still in today's queues."""
    cutoff = streak.day_start_ms(col)
    try:
        today_no = int(col.sched.today)
    except Exception as e:
        # No fallback to 0: review due values are always positive, so every answered card would
        # count as finished.
        raise BaselineUnavailable(f"col.sched.today unavailable: {e}") from e
    where, params = _finished_where(cutoff, today_no)
    total = finished_today_total(col, cutoff, today_no)
    by_deck: dict[str, int] = {}
    try:
        rows = (
            col.db.all(
                "SELECT CASE WHEN c.odid != 0 THEN c.odid ELSE c.did END AS deck, count(DISTINCT r.cid) "
                f"FROM revlog r JOIN cards c ON c.id = r.cid WHERE {where} GROUP BY deck",
                *params,
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


def new_card_count(col: "Collection | None") -> int:
    """New cards in the collection (queue = 0, not suspended or buried); 0 when unmeasurable. Not
    the scheduler's new_count, which reads zero for Custom Study players."""
    if col is None:
        return 0
    try:
        return int(col.db.scalar("SELECT count() FROM cards WHERE queue = 0") or 0)
    except Exception:
        return 0


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


# How much of the morning's baseline may leave today's schedule (suspended, buried, deleted) before
# the day is voided instead of forgiven.
CLEARED_MAX_FORGIVEN_FRACTION = 0.70
_CLEARED_MIN_REQUIRED_FRACTION = 1.0 - CLEARED_MAX_FORGIVEN_FRACTION


def _cleared_min_required(total: int) -> int:
    """Fewest cards the day may still ask for before it is voided, as a whole card count. Rounded
    before the ceiling, since 1.0 - 0.70 isn't exactly 0.3 in floating point."""
    return math.ceil(round(total * _CLEARED_MIN_REQUIRED_FRACTION, 6))


def _cleared_measured(
    state: dict[str, Any], col: "Collection | None"
) -> tuple[int, int] | None:
    """(finished today, morning baseline), or None when unmeasurable. One revlog query, no live deck
    counts."""
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


def _new_today_in_learning_where(col: "Collection") -> tuple[str, list[int]]:
    """WHERE clause, with its bindings, for cards introduced today whose learning step is in the live
    counts: as the deck list counts them, intraday within the learn-ahead limit, interday due today."""
    learn_cutoff = int(time.time()) + int(col.conf.get("collapseTime", 1200))
    return (
        "((c.queue = 1 AND c.due < ?) OR (c.queue = 3 AND c.due <= ?)) AND NOT EXISTS "
        "(SELECT 1 FROM revlog p WHERE p.cid = c.id AND p.id < ?)",
        [learn_cutoff, int(col.sched.today), streak.day_start_ms(col)],
    )


def _new_today_in_learning(col: "Collection") -> int:
    """Cards introduced today and still in a learning step. In the live counts but never `done`, so
    leaving them in would cancel the forgiveness."""
    try:
        where, params = _new_today_in_learning_where(col)
        return int(col.db.scalar(f"SELECT count() FROM cards c WHERE {where}", *params) or 0)
    except Exception:
        return 0


def _new_today_in_learning_by_deck(col: "Collection") -> dict[str, int]:
    """_new_today_in_learning split by full deck name."""
    where, params = _new_today_in_learning_where(col)
    rows = col.db.all(f"SELECT c.did, count() FROM cards c WHERE {where} GROUP BY c.did", *params)
    out: dict[str, int] = {}
    for did, n in rows or []:
        name = col.decks.name(int(did))
        out[name] = out.get(name, 0) + int(n or 0)
    return out


def remaining_today(col: "Collection | None") -> dict[str, Any] | None:
    """What today still offers a freshly rolled quest: {"total", "decks": {deck_id: due}, "new"}.
    Due counts leave out cards first seen today, as cleared_status does. None when unmeasurable."""
    if col is None:
        return None
    try:
        total, decks = live_counts(col)
        learning = _new_today_in_learning_by_deck(col)
    except Exception:
        return None
    return {
        "total": max(0, total - sum(learning.values())),
        "decks": {
            did: max(0, info["due"] - _done_for_deck(info["name"], learning))
            for did, info in decks.items()
        },
        "new": new_card_count(col),
    }


def cleared_status(
    state: dict[str, Any], col: "Collection | None"
) -> tuple[int, int, bool] | None:
    """
    Clear-the-day standing: (finished, required, voided), or None when not measurable.

        required = min(baseline, live due now + finished today)

    Never above the baseline nor below done work. Below _CLEARED_MIN_REQUIRED_FRACTION the day is
    voided and reports that floor as its objective.
    """
    measured = _cleared_measured(state, col)
    if measured is None:
        return None
    done, total = measured
    try:
        live_total, _ = live_counts(col)
    except BaselineUnavailable:
        # Unknown, not zero: reporting the baseline leaves the day neither complete nor voided.
        return (done, total, False)
    live_due = max(0, live_total - _new_today_in_learning(col))
    required = min(total, live_due + done)
    # Integer comparison, same boundary: `required` is a whole number of cards, so falling short of
    # the ceiling and falling short of the fractional floor are the same test.
    min_required = _cleared_min_required(total)
    if required < min_required:
        return (done, min_required, True)
    return (done, required, False)


def cleared_progress(
    state: dict[str, Any], col: "Collection | None"
) -> tuple[int, int] | None:
    """Progress toward clearing the day: (finished, required), or None when not measurable. Counted
    from finished_today, not (baseline - still due), which new cards entering learning ran
    backwards. A voided day reports finished short of required."""
    status = cleared_status(state, col)
    if status is None:
        return None
    done, required, _voided = status
    return (done, required)


def cleared_voided(state: dict[str, Any], col: "Collection | None") -> bool:
    """Whether so much has left today's schedule that the day can no longer be cleared."""
    status = cleared_status(state, col)
    return bool(status and status[2])


def ensure_baseline(state: dict[str, Any], col: "Collection | None") -> dict[str, Any] | None:
    """Capture the baseline once per scheduler day into state["quest_due_baseline"]. Returns it, or
    None when unmeasurable ("unknown", not "nothing due": don't roll quests from it). Never
    raises."""
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
