"""
Pin the clear-the-day quest's forgiveness rule after suspends, buries and deletions, and when
the day is voided instead. Exit 1 = a case changed.

    python3 tests/check_cleared_day.py
"""
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.theme", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = None
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

due_baseline = importlib.import_module("cq.src.due_baseline")

FAILS = []
TODAY = "2026-09-20"
COL = object()  # never touched: both measurements are stubbed below


def scene(baseline, done, live, new_learning=0):
    """State and stubs for a day that opened with `baseline`, has `done` finished and `live` left."""
    due_baseline.finished_today_total = lambda col, *a, **k: done
    due_baseline.live_counts = lambda col: (live + new_learning, {})
    due_baseline._new_today_in_learning = lambda col: new_learning
    due_baseline._safe_today = lambda col: TODAY
    return {"quest_due_baseline": {"date": TODAY, "total": baseline}}


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got!r}")


def case(label, baseline, done, live, want_progress, want_voided, want_complete, new_learning=0):
    state = scene(baseline, done, live, new_learning)
    progress = due_baseline.cleared_progress(state, COL)
    voided = due_baseline.cleared_voided(state, COL)
    check(f"{label} - progress", progress, want_progress)
    check(f"{label} - voided", voided, want_voided)
    # How review_rewards._award_cleared_bonus reads it.
    complete = progress is not None and progress[0] >= progress[1]
    check(f"{label} - completes", complete, want_complete)


print("clear-the-day forgiveness (baseline 328, floor 98.4)")
# Nothing taken off the schedule: the day is the day.
case("untouched, nothing done", 328, 0, 328, (0, 328), False, False)
case("untouched, part done", 328, 143, 185, (143, 328), False, False)
case("untouched, all done", 328, 328, 0, (328, 328), False, True)

# Cards leave the schedule before any reviewing: forgiven down to the floor, voided past it,
# and reported straight away so the panel never shows an objective the rule already lowered.
case("suspend 100 first thing", 328, 0, 228, (0, 228), False, False)
# A voided day reports the floor it has to climb back to, not the morning's objective.
case("suspend 230 (70%) first thing", 328, 0, 98, (0, 99), True, False)
case("suspend 300 first thing", 328, 0, 28, (0, 99), True, False)

# The same day once the floor is passed: forgiveness applies and voiding cannot happen.
case("suspend 100, then clear the rest", 328, 228, 0, (228, 228), False, True)
case("do 143, suspend the rest", 328, 143, 0, (143, 143), False, True)
case("do 143, suspend 100 of the rest", 328, 143, 85, (143, 228), False, False)
case("do 100, suspend everything left", 328, 100, 0, (100, 100), False, True)

# Unsuspending puts the work back, but never more than the day opened with.
case("suspended then unsuspended", 328, 143, 185, (143, 328), False, False)
case("unsuspended older cards too", 328, 143, 400, (143, 328), False, False)

# Deleting a card already answered drops it from both figures at once.
case("did 143, deleted 3 of them", 328, 140, 185, (140, 325), False, False)

print("new cards being learned today (in the live queue, never in `done`)")
# They must not raise the objective: the forgiveness they would cancel is the whole point.
case("suspend 100, 6 new cards mid-step", 328, 100, 128, (100, 228), False, False, new_learning=6)
case("suspend 100, cleared, 1 new mid-step", 328, 228, 0, (228, 228), False, True, new_learning=1)
case("untouched day, 20 new mid-step", 328, 143, 185, (143, 328), False, False, new_learning=20)

# The shortfall is readable off the row: 28 cards on the schedule against a floor of 99 means 71
# have to come back before the day counts again.
case("one card short of the floor", 328, 0, 99, (0, 99), False, False)
case("exactly on the floor", 330, 0, 99, (0, 99), False, False)
case("one under it", 330, 0, 98, (0, 99), True, False)

print("edge cases")
case("no baseline", 0, 0, 0, None, False, False)
state = scene(328, 143, 185)
state["quest_due_baseline"]["date"] = "2026-09-19"
check("stale baseline - progress", due_baseline.cleared_progress(state, COL), None)
check("stale baseline - voided", due_baseline.cleared_voided(state, COL), False)

# A tiny day still obeys the same fractions.
case("3-card day, 1 done 0 left", 3, 1, 0, (1, 1), False, True)
case("3-card day, nothing done 0 left", 3, 0, 0, (0, 1), True, False)

print("out-of-band payout (a day finished by losing cards, with no answer behind it)")
review_rewards = importlib.import_module("cq.src.review_rewards")
storage = importlib.import_module("cq.src.storage")
# Pinned like due_baseline's own clock above: the payout stamps streak.today_str, so leaving it
# real made every expectation here expire at the next rollover.
review_rewards.streak.today_str = lambda c=None: TODAY


def payout(label, baseline, done, live, want_paid, want_frozen=None):
    """Drive the real award the way hooks._check_cleared_day does."""
    state = storage._default_state()
    state.update(scene(baseline, done, live))
    state["level"] = 1
    before_xp = state.get("total_xp", 0)
    earned = review_rewards.award_cleared_bonus_out_of_band(state, COL)
    paid = earned is not None
    check(f"{label} - pays", paid, want_paid)
    if paid:
        check(f"{label} - xp moved", state["total_xp"] > before_xp, True)
        check(f"{label} - stamped for today", state.get("cleared_bonus_date"), TODAY)
        check(f"{label} - names the quest",
              bool(earned.get("completed_quests")), True)
        # Frozen at payout: what the panel row shows for the rest of the day.
        check(f"{label} - objective frozen at", state.get("cleared_bonus_total"), want_frozen)
        # A second settle must not pay twice, however the day is poked afterwards.
        check(f"{label} - pays once", review_rewards.award_cleared_bonus_out_of_band(state, COL), None)


payout("suspend the rest after 143 of 328", 328, 143, 0, True, want_frozen=143)
payout("suspend the rest after 100 of 328", 328, 100, 0, True, want_frozen=100)
payout("still 85 left to review", 328, 143, 85, False)
payout("voided day pays nothing", 328, 0, 28, False)
payout("untouched day, all done", 328, 328, 0, True, want_frozen=328)

print("a paid day stops moving (the unbury case)")
state = storage._default_state()
# A 218-card day, 2 of them buried: the objective drops to 216 and is cleared there.
state.update(scene(218, 216, 0))
check("cleared at", due_baseline.cleared_progress(state, COL), (216, 216))
review_rewards.award_cleared_bonus_out_of_band(state, COL)
check("paid at", state.get("cleared_bonus_total"), 216)
# The 2 are unburied afterwards: the live objective climbs back to the baseline, frozen holds.
state.update(scene(218, 216, 2))
check("live objective rises", due_baseline.cleared_progress(state, COL), (216, 218))
check("frozen objective holds", state.get("cleared_bonus_total"), 216)
check("still stamped paid", state.get("cleared_bonus_date"), TODAY)

print("the row itself (review_rewards.cleared_bonus_display)")
state = storage._default_state()
state.update(scene(218, 216, 2))
check("unpaid day reads live", review_rewards.cleared_bonus_display(state, COL), (216, 218))
state["cleared_bonus_date"], state["cleared_bonus_total"] = TODAY, 216
check("paid day reads frozen", review_rewards.cleared_bonus_display(state, COL), (216, 216))
# A save that was paid before this key existed: nothing to freeze at, so the live figures stand.
state.pop("cleared_bonus_total")
check("pre-update save reads complete", review_rewards.cleared_bonus_display(state, COL), (216, 216))
state["cleared_bonus_total"] = 0
check("zero total reads complete", review_rewards.cleared_bonus_display(state, COL), (216, 216))
state["cleared_bonus_total"] = "216"
check("junk total reads complete", review_rewards.cleared_bonus_display(state, COL), (216, 216))
state["cleared_bonus_date"] = "2026-09-19"
state["cleared_bonus_total"] = 216
check("yesterday's payment ignored", review_rewards.cleared_bonus_display(state, COL), (216, 218))
# A voided day reaches the panel as the floor it has to climb back to, not the morning's objective:
# 28 cards left on a 328-card day means 99 have to be scheduled again.
state = storage._default_state()
state.update(scene(328, 0, 28))
check("voided day reads as the floor", review_rewards.cleared_bonus_display(state, COL), (0, 99))

print()
if FAILS:
    print(f"{len(FAILS)} case(s) off")
    sys.exit(1)
print("all clear")
