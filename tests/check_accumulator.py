"""
Pin the streak accumulator's day arithmetic: the ramp, the cap-raise carry, and old saves.
Run after touching _charge_for_cap, _carry_cap_raise or the Magnet rates. Exit 1 = a case changed.

    python3 tests/check_accumulator.py
"""
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
DAY = 86400

sys.path.insert(0, str(ROOT.parent))
for name in ("aqt", "aqt.qt", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = None
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg
m = importlib.import_module("cq.src.milestones")

today = [1000 * DAY]
streak = [1]
m._today_epoch = lambda col=None: today[0] if col is not None else 0
m.streak.get_display_streak_days = lambda data, t: (streak[0], 0)
m.streak.today_str = lambda col=None: "2026-01-01"

# Milestone #1 grants the +5% cap, #5 raises it to +10%. `active` is 1-based, so the track is one
# past the milestone that has been earned.
CAP_5, CAP_10 = 2, 6

failures = []


def check(case, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {case:<46} {got!r}" + ("" if ok else f"  want {want!r}"))
    if not ok:
        failures.append(case)


def new_game(streak_days, active=CAP_5):
    """A fresh save on its first refresh, mid-streak."""
    today[0] += 500 * DAY
    streak[0] = streak_days
    data = {}
    ms = m.get_state(data)
    ms["started"] = "y"
    ms["active"] = active
    m.refresh_accumulator(data, object())
    return data


def next_day(data, streak_days=None):
    today[0] += DAY
    streak[0] = streak[0] + 1 if streak_days is None else streak_days
    m.refresh_accumulator(data, object())
    return m.accumulator_percent(data)


def raise_cap(data, active=CAP_10):
    m.get_state(data)["active"] = active
    m.refresh_accumulator(data, object())
    return m.accumulator_percent(data)


print("the ramp")
d = new_game(60)
check("days 1-7 at cap 5, unlocked mid-streak",
      [m.accumulator_percent(d)] + [next_day(d) for _ in range(6)], [1, 2, 3, 4, 5, 5, 5])
d = new_game(3)
check("streak shorter than the ramp bounds it", [m.accumulator_percent(d), next_day(d)], [1, 2])
d = new_game(60)
for _ in range(6):
    next_day(d)
check("a break drops it to one day's worth", next_day(d, streak_days=1), 1)

print("\nthe carry")
d = new_game(60)
for _ in range(4):
    next_day(d)                       # the 5th charge lands today
check("raised the day the charge filled up", [m.accumulator_percent(d), raise_cap(d), next_day(d)],
      [5, 5, 6])
d = new_game(60)
for _ in range(5):
    next_day(d)                       # filled yesterday, so today was spent earning nothing
check("raised a day after it filled up", [m.accumulator_percent(d), raise_cap(d), next_day(d)],
      [5, 6, 7])
d = new_game(60)
for _ in range(2):
    next_day(d)
check("raised while still climbing", [m.accumulator_percent(d), raise_cap(d), next_day(d)],
      [3, 3, 4])
d = new_game(3)
check("raised while the streak is short", [m.accumulator_percent(d), raise_cap(d), next_day(d)],
      [1, 1, 2])
d = new_game(60)
for _ in range(4):
    next_day(d)
raise_cap(d)
check("a break after a raise still empties it", next_day(d, streak_days=1), 1)
d = new_game(60)
for _ in range(5):
    next_day(d)
raise_cap(d)
check("repeated refreshes on the raise day",
      [m.refresh_accumulator(d, object()) for _ in range(3)], [6, 6, 6])

print("\na save from before the carry existed")
today[0] += 500 * DAY
streak[0] = 40
d = {}
ms = m.get_state(d)
ms["started"] = "y"
ms["active"] = CAP_5
ms["accumulator_since_epoch"] = today[0] - 3 * DAY     # mid-ramp under the old formula
for key in ("accumulator_base_percent", "accumulator_cap_seen"):
    ms.pop(key, None)
m.refresh_accumulator(d, object())
check("mid-ramp save keeps the old build's figure", m.accumulator_percent(d), 4)
ms["accumulator_since_epoch"] = today[0] - 60 * DAY    # long full
ms["accumulator_cap_seen"] = 0
m.refresh_accumulator(d, object())
check("full save arrives full, not re-ramping", m.accumulator_percent(d), 5)
check("and the first later raise carries it", [raise_cap(d), next_day(d)], [6, 7])

print("\nhand-edited and clock-skewed saves")
d = new_game(60)
m.get_state(d)["accumulator_base_percent"] = "not a number"
check("a bad stored value does not raise", m.refresh_accumulator(d, object()), 1)
d = new_game(60)
for _ in range(4):
    next_day(d)
m.get_state(d)["accumulator_since_epoch"] = today[0] + 30 * DAY   # clock ran ahead, then corrected
check("a stamp left in the future recovers", m.refresh_accumulator(d, object()), 1)

print(f"\n{len(failures)} failing case(s)")
sys.exit(1 if failures else 0)
