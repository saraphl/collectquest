"""
Pin milestone #16: buffs last 3 days until it's done, 4 after, and the ones running when it
completes gain the extra day. Run after touching buff_days, roll_buff or advance_if_complete.
Exit 1 = a case changed.

    python3 tests/test_buff_length.py
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

TODAY = 1000 * DAY
COL = object()
streak = [0]
m._today_epoch = lambda col=None: TODAY if col is not None else 0
m.streak.get_display_streak_days = lambda data, t: streak[0]
m.streak.today_str = lambda col=None: "2026-01-01"
m.random.randint = lambda a, b: a  # every roll lands

M16 = 16
IDS = [b["id"] for b in m.BUFFS]

failures = []


def check(case, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {case:<46} {got!r}" + ("" if ok else f"  want {want!r}"))
    if not ok:
        failures.append(case)


def save(active, buffs=()):
    """A save on milestone `active`, opened 20 days ago, with `buffs` as (id, days ago, length)."""
    data = {}
    ms = m.get_state(data)
    ms.update({"started": "y", "active": active, "active_since_epoch": TODAY - 20 * DAY})
    ms["active_buffs"] = [{"id": i, "started_epoch": TODAY - ago * DAY, "days": n} for i, ago, n in buffs]
    return data


print("the reward")
check("#16 is a 16-day streak", (m.LADDER[M16 - 1]["objective"], m.LADDER[M16 - 1]["target"]),
      (m.OBJ_STREAK, 16))
check("3 days while #16 is active", m.buff_days(save(M16)), 3)
check("4 days once it's done", m.buff_days(save(M16 + 1)), 4)
d = save(M16 + 1)
b = m.roll_buff(d, COL)
check("a drop after #16 is stored as 4 days", m.get_state(d)["active_buffs"][-1]["days"], 4)
check("and reported as 4 days", b["days"], 4)
check("the catalog entry stays untouched", "days" in m.buff_by_id(b["id"]), False)

print("\ncompleting #16")
d = save(M16, [(IDS[0], 2, 3), (IDS[1], 0, 3), (IDS[2], 3, 3)])
streak[0] = 15
check("a 15-day streak doesn't complete it", m.advance_if_complete(d, COL), None)
check("and leaves running buffs alone", [e["days"] for e in m.get_state(d)["active_buffs"]], [3, 3, 3])
streak[0] = 16
check("a 16-day streak completes it", (m.advance_if_complete(d, COL) or {}).get("reward"),
      m.LADDER[M16 - 1]["reward"])
left = [(e["id"], m.buff_days_left(e, COL)) for e in m.get_state(d)["active_buffs"]]
check("running buffs gain a day, expired stay gone", left, [(IDS[0], 2), (IDS[1], 4)])

print("\nother milestones")
d = save(13, [(IDS[0], 0, 3)])
m.get_state(d)["active_progress"] = 10
m.advance_if_complete(d, COL)
check("#13 leaves buff length alone", m.get_state(d)["active_buffs"][0]["days"], 3)

print(f"\n{len(failures)} FAILED: {', '.join(failures)}" if failures else "\nall buff length checks passed")
sys.exit(1 if failures else 0)
