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

Which revlog rows count is set by counts_as_due_review_sql(), and it has to mirror what the deck
list puts in the counts, or the two halves disagree and the day can never be cleared. quests.py
credits the rolled review quests by the same rule, for the same reason.

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
# Excludes 3 (filtered preview), 4 (manual reschedule) and 5 (bulk reschedule, e.g. FSRS
# optimization), none of which represent a card that was counted as due at the start of the day.
# Type 0 (learning) is admitted conditionally — see _WAS_LEARNING_AT_DAY_START.
_DUE_REVIEW_TYPES = "(1, 2)"

def counts_as_due_review_sql(cutoff_sql: str = "?") -> str:
    """
    SQL predicate over an aliased revlog row `r`: was this answer part of today's due count?

    This is the one rule two separate mechanisms have to agree on. Quest targets are a fraction of
    the day's due count, and quest progress is the answers credited against them; if the two sides
    disagree about a card, it sits in a target that its own answers cannot advance. So the same
    predicate sizes the clear-the-day quest, credits it, and (via revlog_sync) credits the rolled
    review quests.

    Type 0 is written for every answer to a card in the learning queue, the graduating answer
    included, so a card part-way through its learning steps produces nothing but type 0 rows. The
    deck list counts such a card in its learning column, which means _node_due puts it in the
    baseline — so refusing every type 0 row leaves it in the target with no way to be credited.
    That happens whenever learning outlives a rollover, from a learning step of a day or more or
    from introducing a card shortly before one: measured against this collection, 145 of 6495 cards
    ever learned had their steps span a rollover.

    The test is what the card's last row before the cutoff was, which is precisely "the card sat in
    the learning queue as the day began". Deliberately narrower than "its first answer predates
    today", which would also readmit a card reset with Forget and studied fresh today: that card
    carries learning rows from its original introduction, but today it is a new card and no more
    part of the day's due count than any other. Its last row before today is the manual reset
    (type 4), so this test excludes it and the first-answer test would not.

    A card introduced today has no row before the cutoff at all, so cards new today still cannot
    advance a due-derived target — the property the clear-the-day quest is built on.

    cutoff_sql says where the start-of-day timestamp comes from: "?" to bind it as a parameter (the
    default), or a literal for callers that format it into the statement. The correlated lookup runs
    only for type 0 rows, since SQLite evaluates the AND left to right, and uses ix_revlog_cid.
    """
    was_learning_at_day_start = (
        f"(SELECT p.type FROM revlog p WHERE p.cid = r.cid AND p.id < {cutoff_sql}"
        " ORDER BY p.id DESC LIMIT 1) = 0"
    )
    return f"(r.type IN {_DUE_REVIEW_TYPES} OR (r.type = 0 AND {was_learning_at_day_start}))"


_COUNTS_AS_DUE_REVIEW = counts_as_due_review_sql()


def day_start_timestamp_ms(col: "Collection | None" = None) -> int:
    """
    Epoch ms at which the current scheduler day began (honors 'Next day starts at').

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


# Deck names long enough to dominate a quest line are cut to this, with an ellipsis appended. Anki
# puts no limit on deck names, and a quest label is one line among several in a narrow panel.
_DECK_NAME_ELLIPSIS = "..."
_DECK_NAME_MAX = 35
# Derived, not written out: the cut plus the ellipsis has to land inside the budget, and two
# independent literals let a change to one silently shorten the result.
_DECK_NAME_TRUNCATED_TO = _DECK_NAME_MAX - len(_DECK_NAME_ELLIPSIS)


def display_deck_name(name: str) -> str:
    """Deck name as shown to the player: invisible sort-order characters removed, truncated, quoted.

    Anki lets a deck be called "​Kanji writing" to control where it sorts; rendered raw in a
    quest label that shows as a stray leading gap. Quoting also keeps the deck name legible when it
    contains spaces or "::".

    Over _DECK_NAME_MAX characters the name is cut to _DECK_NAME_TRUNCATED_TO and given an ellipsis,
    so one very long deck name cannot push the quest line past the panel it lives in.
    """
    cleaned = (name or "").strip().strip(_INVISIBLE).strip()
    if len(cleaned) > _DECK_NAME_MAX:
        cleaned = cleaned[:_DECK_NAME_TRUNCATED_TO] + _DECK_NAME_ELLIPSIS
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


def _answered_where(cutoff: int) -> tuple[str, list[int]]:
    """WHERE clause for "answered today", with its bindings.

    Clause and parameters are returned together because the clause is assembled from fragments that
    each contribute their own positional placeholder, and every binding is an integer — so an order
    that drifts from the fragments raises nothing and silently answers a different question.
    """
    return (f"r.id >= ? AND {_COUNTS_AS_DUE_REVIEW}", [cutoff, cutoff])


def _finished_where(cutoff: int, today_no: int) -> tuple[str, list[int]]:
    """WHERE clause for "answered today and done for today", with its bindings. See _answered_where."""
    clause, params = _answered_where(cutoff)
    return (f"{clause} AND NOT {_STILL_DUE_TODAY}", [*params, today_no])


def answered_today(col: "Collection") -> int:
    """Distinct cards answered in the current scheduler day (diagnostics only).

    Admits the rows finished_today admits, minus its two narrowing conditions: this counts a card
    that is still due today, and it does not join cards, so a card answered and then deleted counts
    here and not there. Both gaps are expected in the readout — it exists to be compared against
    finished_today, so what separates them has to be stated rather than discovered.
    """
    cutoff = day_start_timestamp_ms(col)
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
    """
    How many distinct cards answered today are done for today.

    Split out from finished_today so callers that only need the total — the clear-the-day bonus,
    which runs on every answer — do not also pay for the per-deck GROUP BY and its deck-name lookups.

    cutoff and today_no are accepted so finished_today, which has already derived both, does not pay
    for them twice. The query itself is deliberately still its own: it is the authoritative figure,
    and the per-deck breakdown is allowed to fail without taking the total down with it.
    """
    if today_no is None:
        try:
            today_no = int(col.sched.today)
        except Exception as e:
            raise BaselineUnavailable(f"col.sched.today unavailable: {e}") from e
    if cutoff is None:
        cutoff = day_start_timestamp_ms(col)
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
    """
    Cards answered today that are done for today: (distinct total, {deck_name: distinct}).

    Counts distinct card ids so learning-step repeats don't inflate the figure; only rows that
    _COUNTS_AS_DUE_REVIEW admits, so manual reschedules and cards new today are excluded; and
    excludes cards still sitting in today's queues, which the live due count already represents.
    """
    cutoff = day_start_timestamp_ms(col)
    try:
        today_no = int(col.sched.today)
    except Exception as e:
        # Falling back to 0 would silently disable the "still due today" half of the filter — review
        # due values are days-since-creation and always positive, so every answered card would count
        # as finished and the baseline would be inflated by the whole remaining queue.
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
    one every time a new card was introduced. finished_today never admits a card new today, so it
    cannot move this figure in either direction. A card that was already learning when the day began
    does count: the baseline counted it too.

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
