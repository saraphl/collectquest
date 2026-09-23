"""
Regression check for GitHub issue #2: a 1867-day streak showed as 400 days.
Replays it against a real Anki collection; needs the anki package. Exit 1 = regressed.

    python3 tests/check_long_streak.py
"""
import os, sys, tempfile, time, types

os.environ["TZ"] = "Asia/Tokyo"  # the reporter's, going by their mail client
time.tzset()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _n in ("aqt", "aqt.qt", "aqt.utils", "aqt.gui_hooks", "aqt.operations"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
from anki.collection import Collection  # noqa: E402
from src import storage, streak  # noqa: E402

DAY = streak.DAY_SEC
STREAK = 1868  # 1867 when reported, plus the day they confirmed the fix
fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}" + ("" if ok else f" (want {want})"))


def bar(state, col):
    """The 7-day bar's filled squares, computed as hooks.py does."""
    days, _ = streak.get_display_streak_days(state, streak.today_epoch(col))
    return ((days - 1) % streak.STREAK_LENGTH) + 1 if days > 0 else 0


def add_reviews(col, day_offsets):
    today = streak.today_epoch(col)
    rows = []
    for k in day_offsets:
        start = streak.day_start_ms(col, today - k * DAY)
        rows += [(start + h * 3600_000 + n, 1, -1, 3, 10, 5, 2500, 8000, 1)
                 for h in (1, 9, 17) for n in range(3)]
    for r in rows:
        col.db.execute("INSERT INTO revlog VALUES (?,?,?,?,?,?,?,?,?)", *r)


with tempfile.TemporaryDirectory() as tmp:
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        # Studied every day up to yesterday; today not yet, as when the bar was first looked at.
        add_reviews(col, range(1, STREAK + 1))
        today = streak.today_epoch(col)
        yesterday = today - DAY

        # A save from before the fix: no install floor, the run cut to 400 days, 57 windows paid.
        state = storage._migrate({"streak_floor_epoch": 0})
        state.update({
            "current_streak_start_date": yesterday - 399 * DAY,
            "current_streak_end_date": yesterday,
            "streak_rewards_claimed": 400 // 7,
            "longest_streak_days": 400,
            "level": 30,
        })

        streak.refresh_streak(state, col)
        check("streak before today's reviews", streak.get_display_streak_days(state, today)[0], STREAK)
        check("bar before today's reviews", bar(state, col), STREAK % 7 or 7)
        check("run kept its claimed windows", state["streak_rewards_claimed"], 400 // 7)
        reward = streak.maybe_grant_streak_reward(state, col)
        check("catch-up reward paid once", (reward is not None, state["streak_rewards_claimed"]),
              (True, STREAK // 7))
        check("no second payout", streak.maybe_grant_streak_reward(state, col), None)

        # Today's reviews: the run grows by one and the bar moves with it.
        add_reviews(col, [0])
        streak.refresh_streak(state, col)
        check("streak after today's reviews", streak.get_display_streak_days(state, today)[0], STREAK + 1)
        check("bar after today's reviews", bar(state, col), (STREAK + 1) % 7 or 7)
        paid = streak.maybe_grant_streak_reward(state, col)
        check("reward when the bar fills", paid is not None, (STREAK + 1) % 7 == 0)

        # The bug's own shape: exactly 400 days must no longer be where the count stops.
        check("not pinned at 400", streak.get_display_streak_days(state, today)[0] != 400, True)

        # The refresh runs after every answer, and Anki reads SQL not starting with SELECT as a
        # write, which clears the undo queue.
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"] = "q"
        col.add_note(note, col.decks.id("Default"))
        col.sched.answerCard(col.sched.getCard(), 3)
        streak.refresh_streak(state, col)
        check("the answer is still undoable after a refresh", col.undo_status().undo, "Answer Card")
    finally:
        col.close()

print("FAILED" if fails else "issue #2 stays fixed")
sys.exit(1 if fails else 0)
