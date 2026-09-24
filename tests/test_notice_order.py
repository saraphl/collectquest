"""
Pin the order and delays of the notices one answer posts.
Run after touching src/notices.py. Exit 1 = a case changed.

    python3 tests/test_notice_order.py
"""
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT.parent))


class _Stub:
    """Any Qt/aqt name: callable, subclassable, and attribute access never fails."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return _Stub()

    def __call__(self, *a, **k):
        return _Stub()


for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.theme", "aqt.gui_hooks", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: _Stub
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = _Stub()
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg
h = importlib.import_module("cq.src.notices")

timers: list[tuple[int, object]] = []
shown: list[str] = []


class _Timer:
    @staticmethod
    def singleShot(ms, fn):
        timers.append((ms, fn))


h.QTimer = _Timer
h.mw = _Stub()
h.ui.stacked_tooltip = lambda msg, *a, **k: shown.append(msg)

BUFF = h.milestones.BUFFS[0]
BUFF_LINE = f"Buff for {h.milestones.BUFF_DAYS} days: {BUFF['label']}"


def run(earned, start_delay=0, unlocks=(), closing=False):
    """One call of show_queued, with its timers fired in order. Returns [(ms, message)]."""
    timers.clear()
    shown.clear()
    h.milestone_queue.clear()
    h.pending_lines.clear()
    h.pending_unlocks[:] = list(unlocks)
    h.pending_streak_reward = None
    h.profile_closing = closing
    h.show_queued(earned, start_delay)
    posted = []
    for ms, fire in sorted(timers, key=lambda t: t[0]):
        before = len(shown)
        fire()
        posted.append((ms, shown[-1] if len(shown) > before else None))
    h.profile_closing = False
    return posted


failures = []


def check(case, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {case:<44} {got!r}" + ("" if ok else f"\n       want {want!r}"))
    if not ok:
        failures.append(case)


print("Buff box")
check(
    "alone, behind the completion",
    run({"buff_started": BUFF}, start_delay=h.STAGGER_MS),
    [(h.BUFF_DELAY_MS, BUFF_LINE)],
)
check(
    "after the track's own box",
    run({"buff_started": BUFF, "dungeon_entrance": True, "magnet_found": True}, start_delay=500),
    [(500, "Dungeon entrance discovered!\nMagnet found!"), (h.BUFF_DELAY_MS, BUFF_LINE)],
)
check(
    "last even behind a long queue",
    run({"buff_started": BUFF}, start_delay=1800, unlocks=("A unlocked!", "B unlocked!")),
    [(2000, BUFF_LINE), (2500, "A unlocked!"), (3000, "B unlocked!")],
)
check("no buff, no second box", run({"magnet_found": True}), [(0, "Magnet found!")])
check("nothing to say", run(None), [])
check(
    "nothing shown once the profile closes",
    run({"buff_started": BUFF}, closing=True),
    [(h.BUFF_DELAY_MS, None)],
)

print("\n" + ("FAILED: " + ", ".join(failures) if failures else "All checks passed."))
sys.exit(1 if failures else 0)
