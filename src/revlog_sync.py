"""
Process revlog entries from sync (mobile reviews) so quest rewards, XP, gold, gems update.
Only processes reviews that happened "today" (local date) to keep daily quests and reviews_today correct.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from . import due_baseline, review_rewards, storage, streak


# Debug log file (in add-on folder). Set to None to disable.
_LOG_FILE = os.path.join(os.path.dirname(__file__), "revlog_debug.log")


def _log(msg: str) -> None:
    """Append msg to log file with timestamp."""
    if not _LOG_FILE:
        return
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def _revlog_date_ms(revlog_id_ms: int) -> str:
    """
    Revlog id is epoch ms. Return the *scheduler* day for that timestamp (YYYY-MM-DD, local).
    Shifted by rollover so a mobile review at 00:30 belongs to the day that just ended,
    matching streak.today_str() used as "today" below.
    """
    shifted = datetime.fromtimestamp(revlog_id_ms / 1000.0) - timedelta(hours=streak.rollover_hours())
    return shifted.strftime("%Y-%m-%d")


# Last error from fetch (shown in debug UI).
_last_fetch_error = None

# Columns fetched per revlog row: id, ease, deck id, is-first-review flag, counts-as-due-review flag.
_ROW_COLS = 5

# The deck comes from the card, resolving odid so a card sitting in a filtered deck reports its
# home deck. LEFT JOIN, because revlog rows can reference since-deleted cards and an inner join
# would drop those reviews.
#
# "This row is the card's first-ever answer", shared by the sync fetch and newest_answer_flags so
# the two cannot drift apart. Exact rather than heuristic: the tempting (type = 0 AND lastIvl = 0)
# shortcut missed 22% of first reviews on a real collection. NOT EXISTS uses ix_revlog_cid.
_IS_FIRST_ANSWER = (
    "r.type = 0 AND NOT EXISTS"
    " (SELECT 1 FROM revlog p WHERE p.cid = r.cid AND p.id < r.id)"
)

# "This answer was part of today's due count", owned by due_baseline so the same predicate sizes a
# quest target and credits progress against it. The cutoff is the day floor the fetch already bounds
# itself by, formatted in as _FETCH_SQL states since_id.
_COUNTS_AS_DUE_REVIEW = due_baseline.counts_as_due_review_sql("{since_id}")

_FETCH_SQL = (
    "SELECT r.id, r.ease,"
    " CASE WHEN c.odid != 0 THEN c.odid ELSE c.did END,"
    f" CASE WHEN {_IS_FIRST_ANSWER} THEN 1 ELSE 0 END,"
    f" CASE WHEN {_COUNTS_AS_DUE_REVIEW} THEN 1 ELSE 0 END"
    " FROM revlog r LEFT JOIN cards c ON c.id = r.cid"
    # Both bounds stated: since_id is the day floor, last_id the paging cursor. Relying on the
    # cursor's initial value alone would let a reordered loop widen this to the whole revlog.
    " WHERE r.id >= {since_id} AND r.id > {last_id} ORDER BY r.id LIMIT {chunk}"
)


def _fetch_revlog_rows(col, since_id: int) -> list[tuple[int, int, int, bool, bool]]:
    """
    Fetch every revlog row with id >= since_id. Uses ONLY db.execute() (not db.list()).
    Returns list of (id, ease, deck_id, is_new, counts_as_due_review); deck_id is 0 when the card
    is gone.

    since_id is a floor, not a high-water mark: every row at or above it is returned, including ones
    older than rows already handled. The caller decides which still need crediting.
    Logs to revlog_debug.log.
    """
    global _last_fetch_error
    _last_fetch_error = None
    db = getattr(col, "db", None)
    if db is None:
        _log("_fetch_revlog_rows: db is None")
        _last_fetch_error = "db is None"
        return []
    since_id = int(since_id)
    last_id = since_id - 1  # paging cursor; the floor is stated separately in the SQL
    _log(f"_fetch_revlog_rows: since_id={since_id}")
    out = []
    chunk_size = 1000
    while True:
        sql = _FETCH_SQL.format(since_id=since_id, last_id=last_id, chunk=chunk_size)
        _log(f"  sql: {sql}")
        try:
            res = db.execute(sql)
            _log(f"  execute returned: type={type(res).__name__}")
        except Exception as e:
            _log(f"  execute raised: {type(e).__name__}: {e}")
            _last_fetch_error = f"execute: {type(e).__name__}: {e}"
            break
        # db.execute's result shape varies between Anki versions.
        rows = None
        if hasattr(res, "fetchall"):
            try:
                rows = res.fetchall()
                _log(f"  fetchall: {len(rows) if rows else 0} rows")
            except Exception as e:
                _log(f"  fetchall raised: {type(e).__name__}: {e}")
                _last_fetch_error = f"fetchall: {type(e).__name__}: {e}"
                break
        elif isinstance(res, list):
            rows = res
            _log(f"  res is list: {len(rows)} items")
        else:
            try:
                rows = list(res) if res else []
                _log(f"  list(res): {len(rows)} items")
            except Exception as e:
                _log(f"  list(res) raised: {type(e).__name__}: {e}")
                _last_fetch_error = f"list(res): {type(e).__name__}: {e}"
                break
        if not rows:
            _log("  no rows, done")
            break
        # Normalize: rows of tuples, or one flat list [id,ease,deck,new,due, id,ease,...]
        first = rows[0]
        if isinstance(first, (tuple, list)) and len(first) >= _ROW_COLS:
            tuples = [tuple(r[:_ROW_COLS]) for r in rows]
        else:
            tuples = [
                tuple(rows[i : i + _ROW_COLS])
                for i in range(0, len(rows) - _ROW_COLS + 1, _ROW_COLS)
            ]
        _log(f"  tuples: {len(tuples)}")
        for rid, ease, did, is_new, counts_as_due in tuples:
            try:
                e = int(ease) if ease is not None else 3
            except (TypeError, ValueError):
                e = 3
            if not (0 <= e <= 4):
                continue
            try:
                deck_id = int(did) if did is not None else 0
            except (TypeError, ValueError):
                deck_id = 0
            out.append((int(rid), e, deck_id, bool(is_new), bool(counts_as_due)))
        if tuples:
            last_id = max(int(t[0]) for t in tuples)
        if len(tuples) < chunk_size:
            break
    _log(f"_fetch_revlog_rows: returning {len(out)} rows")
    return out


def _deck_name(col, deck_id: int, cache: dict) -> str | None:
    """Full deck name for a deck id, memoised across a sync batch. None when unknown/deleted."""
    if not deck_id:
        return None
    if deck_id not in cache:
        try:
            cache[deck_id] = col.decks.name(deck_id)
        except Exception:
            cache[deck_id] = None
    return cache[deck_id]


def _ease_from_revlog(ease: int) -> int:
    """
    Revlog ease: 1 = Again, 2 = Hard, 3 = Good, 4 = Easy.

    Ease 0 marks a non-answer (set due date, Forget, FSRS reschedule) and is filtered out before
    this point — it must not be normalized to Again, which would credit it as a review.
    """
    return max(1, min(4, ease))

def process_synced_revlog(col, silent: bool = True) -> dict | None:
    """
    Process new revlog entries from sync (reviews done on phone). Only applies reviews
    from "today" (by revlog timestamp). Uses actual ease from revlog for XP (Again=0, Hard=5, Good=10, Easy=12).
    Advances last_processed_revlog_id so we don't double-count. Call after sync or profile load.
    Returns a summary dict when any today reviews were applied: {"reviews": N, "xp": int, "gold": int, "gems": int}, else None.
    Never raises: on any error returns None so Anki startup is not blocked.
    """
    try:
        return _process_synced_revlog_impl(col, silent)
    except Exception:
        return None


# The card's newest revlog row, i.e. the answer just given. Stated once: two copies of this anchor
# drifted apart and made Good and Easy stop advancing new-card quests.
_NEWEST_ROW = " FROM revlog r WHERE r.cid = ? ORDER BY r.id DESC LIMIT 1"

# Returned when the row cannot be read: no pair is right for both flags, so keep the player's
# review-quest progress and lose only the rarer new-card credit.
_FLAGS_ON_FAILURE = (False, True)


def newest_answer_flags(col, card_id: int) -> tuple[bool, bool]:
    """
    (is_first_answer, counts_as_due_review) for this card's newest revlog row.

    One statement for both, since both describe the same row - and the same tests _FETCH_SQL
    applies, so the desktop and sync paths agree. Not read off the card: this runs after the answer,
    and where the card lands depends on the grade and the deck's learning steps, so any test on
    card.type credits some grades and not others. Two ix_revlog_cid lookups, about 0.02 ms.
    """
    if col is None or not card_id:
        return _FLAGS_ON_FAILURE
    try:
        # The cutoff binds first: it sits in the select list, ahead of the card id in the WHERE.
        row = col.db.first(
            f"SELECT {_IS_FIRST_ANSWER}, {due_baseline.counts_as_due_review_sql()}" + _NEWEST_ROW,
            int(due_baseline.day_start_timestamp_ms(col)),
            int(card_id),
        )
    except Exception:
        return _FLAGS_ON_FAILURE
    if not row:
        return _FLAGS_ON_FAILURE
    return (bool(row[0]), bool(row[1]))


def day_start_id(col) -> int:
    """Lowest revlog id belonging to the current scheduler day (ids are answer timestamps in ms)."""
    from . import due_baseline

    return int(due_baseline.day_start_timestamp_ms(col))


def credited_ids_for_today(data: dict, col, today: str, day_start: int | None = None) -> set[int]:
    """
    Revlog ids already credited today, as a set.

    Rolls over with the scheduler day, so it never holds more than one day of reviews. The first
    call of a day seeds it from last_processed_revlog_id - everything at or below that frontier was
    already paid out - or the day's earlier reviews would be credited again. day_start is accepted
    so a caller that already derived the boundary does not pay for it twice.
    """
    if data.get("credited_revlog_date") == today:
        # Bad entries are dropped one at a time: failing the whole set would report a paid day as
        # uncredited, and the next sync would pay for all of it again.
        out: set[int] = set()
        for i in data.get("credited_revlog_ids") or []:
            try:
                out.add(int(i))
            except (TypeError, ValueError):
                continue
        return out
    mark = int(data.get("last_processed_revlog_id", 0) or 0)
    seeded: set[int] = set()
    if mark:
        try:
            rows = col.db.all(
                "SELECT id FROM revlog WHERE id >= ? AND id <= ?",
                day_start_id(col) if day_start is None else day_start,
                mark,
            )
            for row in rows or []:
                seeded.add(int(row[0] if isinstance(row, (list, tuple)) else row))
        except Exception:
            pass
    _log(f"credited_ids_for_today: new day {today}, seeded {len(seeded)} ids from mark {mark}")
    return seeded


def _store_credited_ids(data: dict, today: str, credited: set[int]) -> None:
    """Persist the day's credited ids. Sorted so the save stays diffable and hashes consistently."""
    data["credited_revlog_date"] = today
    data["credited_revlog_ids"] = sorted(int(i) for i in credited)


def _process_synced_revlog_impl(col, silent: bool) -> dict | None:
    _log("_process_synced_revlog_impl: start")
    data = storage.load()
    today = streak.today_str(col)
    day_start = day_start_id(col)
    credited = credited_ids_for_today(data, col, today, day_start)
    rows = _fetch_revlog_rows(col, day_start)
    _log(f"_process_synced_revlog_impl: got {len(rows)} rows, {len(credited)} already credited")
    if not rows:
        # Persist the seed even with nothing to apply, or the seeding query is repeated on every
        # sync until the day's first row shows up.
        _store_credited_ids(data, today, credited)
        storage.save(data)
        return None
    max_id = int(data.get("last_processed_revlog_id", 0) or 0)
    total_xp = 0
    total_gold = 0
    total_gems = 0
    applied = 0
    deck_cache: dict = {}
    for revlog_id, revlog_ease, deck_id, is_new, counts_as_due_review in rows:
        max_id = max(max_id, revlog_id)
        # Which rows are already done is tracked per id, not by a high-water mark. A review answered
        # on a phone carries the timestamp of when it was answered, so one done at 09:50 and synced
        # at 10:05 arrives *below* a desktop review from 10:00 — under a "greater than the newest
        # seen" rule it would never be credited at all.
        if revlog_id in credited:
            continue
        # Recorded whatever happens next, so a row examined once is not examined again.
        credited.add(revlog_id)
        if revlog_ease == 0:
            # Not an answer: "Set due date", Forget and FSRS reschedules write ease 0. Now that
            # Again advances quests, one FSRS optimization (6666 rows in a day, measured) would
            # otherwise complete every review quest at the next sync.
            continue
        if _revlog_date_ms(revlog_id) != today:
            continue
        ease = _ease_from_revlog(revlog_ease)
        # deck_name/is_new let synced reviews advance deck and new-card quests, which stalled at 0
        # on phone-only days while the fetch returned just (id, ease).
        earned = review_rewards.apply_one_review(
            data,
            ease=ease,
            deck_name=_deck_name(col, deck_id, deck_cache),
            is_new=is_new,
            counts_as_due_review=counts_as_due_review,
            col=col,
        )
        applied += 1
        total_xp += earned.get("undo_deltas", {}).get("xp_delta", 0)
        total_gold += earned.get("gold_earned", 0)
        total_gems += earned.get("gem_earned", 0)
        # Pushed so Ctrl+Z reverts synced reviews too, Again included: it advances quests now, and
        # skipping it would make an undo pop the previous review's deltas.
        try:
            from aqt import mw
            buf = getattr(mw, "_collectquest_undo_state", None)
            if not isinstance(buf, list):
                buf = []
            buf.append(earned.get("undo_deltas"))
            if len(buf) > review_rewards.UNDO_BUFFER_MAX:
                buf = buf[-review_rewards.UNDO_BUFFER_MAX:]
            mw._collectquest_undo_state = buf
        except Exception:
            pass
    data["last_processed_revlog_id"] = max_id
    _store_credited_ids(data, today, credited)
    storage.save(data)
    if applied == 0:
        return None
    return {"reviews": applied, "xp": total_xp, "gold": total_gold, "gems": total_gems}


def get_sync_debug_info(col) -> dict:
    """
    Return diagnostic info for debugging sync rewards: last_id, new revlog count,
    how many of those are from today, today date, max revlog id in DB, total revlog rows.
    """
    from . import storage
    _log("get_sync_debug_info: start")
    data = storage.load()
    last_id = data.get("last_processed_revlog_id", 0)
    max_id_in_db = last_id
    revlog_total_rows = None
    revlog_error = None
    fetch_error = None
    # Fetch rows using execute() only, from the same floor the real pass uses — the argument is a
    # day floor, not a high-water mark, so passing last_id here would report from the mark to the
    # end of the revlog rather than today.
    today = streak.today_str(col)
    day_start = day_start_id(col)
    rows = _fetch_revlog_rows(col, day_start)
    fetch_error = _last_fetch_error
    # Mirror the processing filter: ease 0 rows (set due date, Forget, FSRS reschedule) are counted
    # by the fetch but never credited, and rows already paid for are skipped, so counting either
    # here would overstate what a sync will apply. day_start is passed through rather than derived
    # again, and nothing is written back — this is a read-only diagnostic.
    credited = credited_ids_for_today(data, col, today, day_start)
    today_rows = [
        r for r in rows
        if r[1] != 0 and r[0] not in credited and _revlog_date_ms(r[0]) == today
    ]
    today_count = len(today_rows)
    today_with_deck = sum(1 for r in today_rows if r[2])
    today_new = sum(1 for r in today_rows if r[3])
    _log(f"get_sync_debug_info: {len(rows)} rows, {today_count} from today")
    # Get scalars for display.
    try:
        db = getattr(col, "db", None)
        if db:
            try:
                res = db.execute("SELECT MAX(id) FROM revlog")
                if hasattr(res, "fetchone"):
                    row = res.fetchone()
                elif isinstance(res, list) and res:
                    row = res[0] if isinstance(res[0], (tuple, list)) else (res[0],)
                else:
                    row = None
                if row and row[0] is not None:
                    max_id_in_db = row[0]
            except Exception as e:
                _log(f"get_sync_debug_info: MAX(id) error: {e}")
            try:
                res = db.execute("SELECT COUNT(*) FROM revlog")
                if hasattr(res, "fetchone"):
                    row = res.fetchone()
                elif isinstance(res, list) and res:
                    row = res[0] if isinstance(res[0], (tuple, list)) else (res[0],)
                else:
                    row = None
                if row is not None:
                    revlog_total_rows = row[0] if isinstance(row, (tuple, list)) else row
            except Exception as e:
                _log(f"get_sync_debug_info: COUNT(*) error: {e}")
    except Exception as e:
        revlog_error = str(e)
    return {
        "last_processed_revlog_id": last_id,
        # Rows fetched for today, credited ones included. Not "rows past the mark": the fetch is
        # bounded by the day, and what has already been paid is tracked per id, not by a frontier.
        "today_revlog_rows": len(rows),
        "new_rows_from_today": today_count,
        "today_rows_with_deck": today_with_deck,
        "today_rows_new_cards": today_new,
        "today_date": today,
        "max_revlog_id_in_db": max_id_in_db,
        "revlog_total_rows": revlog_total_rows,
        "revlog_error": revlog_error,
        "fetch_error": fetch_error,
    }


def update_last_processed_revlog_id(col, card_id: int = 0) -> None:
    """
    Record the review just answered on this device as already credited.

    Called from the answer hook, which pays the reward directly; without this the next sync pass
    would pay for the same row again. Also advances last_processed_revlog_id, still used to detect
    an undone review.

    card_id pins this to the row the answer wrote: revlog ids are the answering device's local
    timestamps, so a phone whose clock runs ahead can hold a higher id than the row just added.
    """
    db = getattr(col, "db", None)
    if db is None:
        return
    try:
        if card_id:
            newest = db.scalar("SELECT MAX(id) FROM revlog WHERE cid = ?", int(card_id))
        else:
            newest = db.scalar("SELECT MAX(id) FROM revlog")
        if newest is None:
            return
        newest = int(newest)
        data = storage.load()
        today = streak.today_str(col)
        credited = credited_ids_for_today(data, col, today)
        credited.add(newest)
        _store_credited_ids(data, today, credited)
        # The undo check asks whether the row it names still exists, so it has to name the newest
        # row overall, not this card's.
        overall = db.scalar("SELECT MAX(id) FROM revlog")
        data["last_processed_revlog_id"] = int(overall or newest)
        storage.save(data)
    except Exception:
        pass
