"""
Process revlog entries from sync (mobile reviews) so quest rewards, XP, gold, gems update.
Only processes reviews that happened "today" (local date) to keep daily quests and reviews_today correct.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from . import review_rewards, storage, streak


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

# Columns fetched per revlog row: id, ease, deck id, is-first-review flag.
_ROW_COLS = 4

# The deck comes from the card, resolving odid so cards temporarily sitting in a filtered deck
# (including Custom Study) report their home deck. The join is LEFT because thousands of revlog rows
# can reference since-deleted cards — an inner join would silently drop those reviews, costing the
# player XP for work they actually did.
#
# is_new is exact rather than heuristic: a row is a card's first exposure when it is a learning row
# with no earlier row for the same card. The tempting shortcut (type = 0 AND lastIvl = 0) was
# measured against a real collection and missed 22% of first reviews while adding false positives.
# NOT EXISTS uses ix_revlog_cid and costs well under a millisecond per 1000-row chunk.
_FETCH_SQL = (
    "SELECT r.id, r.ease,"
    " CASE WHEN c.odid != 0 THEN c.odid ELSE c.did END,"
    " CASE WHEN r.type = 0 AND NOT EXISTS"
    " (SELECT 1 FROM revlog p WHERE p.cid = r.cid AND p.id < r.id) THEN 1 ELSE 0 END"
    " FROM revlog r LEFT JOIN cards c ON c.id = r.cid"
    " WHERE r.id > {last_id} ORDER BY r.id LIMIT {chunk}"
)


def _fetch_revlog_rows(col, last_id: int) -> list[tuple[int, int, int, bool]]:
    """
    Fetch revlog rows with id > last_id. Uses ONLY db.execute() (not db.list()).
    Returns list of (id, ease, deck_id, is_new); deck_id is 0 when the card is gone.
    Logs to revlog_debug.log.
    """
    global _last_fetch_error
    _last_fetch_error = None
    db = getattr(col, "db", None)
    if db is None:
        _log("_fetch_revlog_rows: db is None")
        _last_fetch_error = "db is None"
        return []
    last_id = int(last_id)
    _log(f"_fetch_revlog_rows: last_id={last_id}")
    out = []
    chunk_size = 1000
    while True:
        sql = _FETCH_SQL.format(last_id=last_id, chunk=chunk_size)
        _log(f"  sql: {sql}")
        try:
            res = db.execute(sql)
            _log(f"  execute returned: type={type(res).__name__}")
        except Exception as e:
            _log(f"  execute raised: {type(e).__name__}: {e}")
            _last_fetch_error = f"execute: {type(e).__name__}: {e}"
            break
        # Get rows from result
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
        # Normalize: rows of tuples, or one flat list [id,ease,deck,new, id,ease,deck,new, ...]
        first = rows[0]
        if isinstance(first, (tuple, list)) and len(first) >= _ROW_COLS:
            tuples = [tuple(r[:_ROW_COLS]) for r in rows]
        else:
            tuples = [
                tuple(rows[i : i + _ROW_COLS])
                for i in range(0, len(rows) - _ROW_COLS + 1, _ROW_COLS)
            ]
        _log(f"  tuples: {len(tuples)}")
        for rid, ease, did, is_new in tuples:
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
            out.append((int(rid), e, deck_id, bool(is_new)))
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
    this point — it must not be normalised to Again, which would credit it as a review.
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


def _process_synced_revlog_impl(col, silent: bool) -> dict | None:
    _log("_process_synced_revlog_impl: start")
    data = storage.load()
    last_id = data.get("last_processed_revlog_id", 0)
    rows = _fetch_revlog_rows(col, last_id)
    _log(f"_process_synced_revlog_impl: got {len(rows)} rows")
    if not rows:
        return None
    today = streak.today_str(col)
    max_id = last_id
    total_xp = 0
    total_gold = 0
    total_gems = 0
    applied = 0
    deck_cache: dict = {}
    for revlog_id, revlog_ease, deck_id, is_new in rows:
        # Advance the pointer past every row, including the ones skipped below, so they are not
        # rescanned on each sync.
        max_id = max(max_id, revlog_id)
        if revlog_ease == 0:
            # Not an answer. "Set due date", Forget, and FSRS's reschedule-on-change all write
            # revlog rows with ease 0 (types 4 and 5). They used to be harmless because Again did
            # not advance quests; now that it does, a single FSRS optimisation — 6666 rows in one
            # day on the collection this was tested against — would complete every review quest at
            # the next sync.
            continue
        if _revlog_date_ms(revlog_id) != today:
            continue
        ease = _ease_from_revlog(revlog_ease)
        # deck_name/is_new let synced reviews advance deck and new-card quests, which they could not
        # before: the fetch returned only (id, ease), so those quest types stalled at 0 on any day
        # the reviews were done on a phone.
        earned = review_rewards.apply_one_review(
            data,
            ease=ease,
            deck_name=_deck_name(col, deck_id, deck_cache),
            is_new=is_new,
            col=col,
        )
        applied += 1
        total_xp += earned.get("undo_deltas", {}).get("xp_delta", 0)
        total_gold += earned.get("gold_earned", 0)
        total_gems += earned.get("gem_earned", 0)
        # Append to undo buffer so multiple Ctrl+Z can revert synced reviews too. Every review is
        # pushed, Again included: Again now advances review quests, so it carries progress to roll
        # back — and skipping it would make an undo pop the *previous* review's deltas instead.
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
    # Fetch rows using execute() only.
    rows = _fetch_revlog_rows(col, last_id)
    fetch_error = _last_fetch_error
    today = streak.today_str(col)
    # Mirror the processing filter: ease 0 rows (set due date, Forget, FSRS reschedule) are counted
    # by the fetch but never credited, so reporting them here would overstate what a sync will apply.
    today_rows = [r for r in rows if r[1] != 0 and _revlog_date_ms(r[0]) == today]
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
        "new_revlog_rows": len(rows),
        "new_rows_from_today": today_count,
        "today_rows_with_deck": today_with_deck,
        "today_rows_new_cards": today_new,
        "today_date": today,
        "max_revlog_id_in_db": max_id_in_db,
        "revlog_total_rows": revlog_total_rows,
        "revlog_error": revlog_error,
        "fetch_error": fetch_error,
    }


def update_last_processed_revlog_id(col) -> None:
    """Set last_processed_revlog_id to current max revlog id (call after desktop review so we don't double-count on next sync process)."""
    db = getattr(col, "db", None)
    if db is None:
        return
    try:
        res = db.execute("SELECT MAX(id) FROM revlog")
        if hasattr(res, "fetchone"):
            row = res.fetchone()
        elif isinstance(res, list) and res:
            row = res[0] if isinstance(res[0], (tuple, list)) else (res[0],)
        else:
            row = None
        if row and row[0] is not None:
            data = storage.load()
            data["last_processed_revlog_id"] = row[0]
            storage.save(data)
    except Exception:
        pass
