"""
Regression check for GitHub issue #1: suspending due cards left the clear-the-day bonus quest out
of reach. Replays the reporter's 108-card day against a real Anki collection; needs the anki
package. Exit 1 = regressed.

    python3 tests/test_suspend_due_cards.py
"""
import datetime, os, sys, tempfile, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _n in ("aqt", "aqt.qt", "aqt.utils", "aqt.gui_hooks", "aqt.operations"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
from anki.collection import Collection  # noqa: E402
from src import due_baseline, review_rewards, storage  # noqa: E402

DUE = 108
SUSPEND_EVERY = 12  # 9 of the 108, the last card among them
SUSPENDED = DUE // SUSPEND_EVERY
fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}" + ("" if ok else f" (want {want})"))


def settle(state, col):
    """What hooks._check_cleared_day does after the schedule changes. True if it paid."""
    if state.get("cleared_bonus_date") == due_baseline._safe_today(col):
        return False
    status = due_baseline.cleared_status(state, col)
    if status is None:
        return False
    done, required, _voided = status
    return done >= required and review_rewards.award_cleared_bonus_out_of_band(
        state, col, measured=(done, required)) is not None


with tempfile.TemporaryDirectory() as tmp:
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        # Rollover half a day away, so the run cannot straddle two scheduler days.
        col.set_config("rollover", (datetime.datetime.now().hour + 12) % 24)
        deck = col.decks.id("Default")
        for i in range(DUE):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"q{i}"
            col.add_note(note, deck)
        # Mature review cards, all due today and past a year, as the reporter's suspended ones were.
        col.db.execute("UPDATE cards SET type = 2, queue = 2, due = ?, ivl = 400, factor = 2500",
                       col.sched.today)

        state = storage._default_state()
        state["level"] = 1
        due_baseline.ensure_baseline(state, col)
        check("baseline", state["quest_due_baseline"]["total"], DUE)

        # The reporter suspends a card they know instead of grading it. Each suspend must lower the
        # objective by one; before the fix it stayed at 108 while at most 99 could be finished.
        drift, paid = [], []
        answered = suspended = 0
        for n in range(1, DUE + 1):
            card = col.sched.getCard()
            if n % SUSPEND_EVERY:
                col.sched.answerCard(card, 3)
                answered += 1
                if review_rewards.apply_one_review(state, 3, col=col)["undo_deltas"]["cleared_bonus_awarded"]:
                    paid.append(("answer", n))
                if n == DUE // 2:
                    # Suspended after its answer: still finished, so the objective must not move.
                    col.sched.suspend_cards([card.id])
            else:
                col.sched.suspend_cards([card.id])
                suspended += 1
                if settle(state, col):
                    paid.append(("suspend", n))
            progress = review_rewards.cleared_bonus_display(state, col)
            if progress != (answered, DUE - suspended):
                drift.append((n, progress))
            if n == DUE // 2:
                # A baseline rebuilt mid-day (restart, sync) must not count the suspended cards.
                check("baseline rebuilt mid-day", due_baseline.reconstruct(col)["total"], DUE - suspended)
        check("steps where progress was not (answered, 108 - suspended)", drift[:3], [])
        # The last due card left by suspension, so only the out-of-band settle can pay the day.
        check("paid once, by the final suspend", paid, [("suspend", DUE)])
        check("objective frozen at", state.get("cleared_bonus_total"), DUE - SUSPENDED)
        check("not voided", due_baseline.cleared_voided(state, col), False)
    finally:
        col.close()

print("FAILED" if fails else "issue #1 stays fixed")
sys.exit(1 if fails else 0)
