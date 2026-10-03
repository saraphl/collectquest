"""
Switch each Options > Notifications kind off in turn and check only its notification disappears,
then back on. Covers the answer, post-sync and queued paths. Exit 1 = a case changed.

    python3 tests/test_notification_toggles.py
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
sys.modules["aqt"].gui_hooks = _Stub()
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

hooks = importlib.import_module("cq.src.hooks")
notices = importlib.import_module("cq.src.notices")
storage = importlib.import_module("cq.src.storage")
ui_notifications = importlib.import_module("cq.src.ui.notifications")

STATE: dict = {}
storage.load = lambda: STATE
storage.save = lambda data: None

timers: list[tuple[int, object]] = []
shown: list[str] = []


class _Timer:
    @staticmethod
    def singleShot(ms, fn):
        timers.append((ms, fn))


def fire_timers() -> None:
    """Run queued timers in delay order, including any they queue themselves."""
    while timers:
        timers.sort(key=lambda t: t[0])
        _, fn = timers.pop(0)
        fn()


notices.QTimer = hooks.QTimer = _Timer
notices.mw = _Stub()
hooks.mw = types.SimpleNamespace(col=object())
# Both notification styles: Anki's singleton tooltip and the stacked box.
ui_notifications.tooltip = lambda msg, *a, **k: shown.append(msg)
ui_notifications.stacked_tooltip = lambda msg, *a, **k: shown.append(msg)
hooks.ui.stacked_tooltip = notices.ui.stacked_tooltip = lambda msg, *a, **k: shown.append(msg)
ui_notifications._current_streak_days = lambda: 21
hooks._refresh_xp_bar = lambda: None
hooks._maybe_prompt_dungeon_catch_up = lambda: None
# Kept for its own case at the end; the sync path would otherwise measure the day.
check_cleared_day = hooks._check_cleared_day
hooks._check_cleared_day = lambda *a, **k: None

# What each kind's notification contains. Dungeon is checked on both paths it has.
MARKERS = {
    "level_up": ["Level up"],
    "quests": ["Quest complete:"],
    "dungeon": ["Dungeon entrance discovered!", "Dungeon: treasure room discovered!"],
    "sync": ["Synced 12 reviews"],
    "buffs": ["Magnet found!", "Buff for"],
    "streak_reward": ["Streak reward:"],
    "milestones": ["Milestone complete:"],
    "unlocks": ["Dungeons unlocked!"],
}
assert set(MARKERS) == {k for k, _ in storage.NOTIFICATION_KINDS}, "a kind has no marker here"


def run_everything(toggles: dict) -> str:
    """One answer that earns every kind, then a sync with reviews and a dungeon find. Returns all
    that was shown, joined."""
    STATE.clear()
    STATE["notifications"] = dict(toggles)
    shown.clear()
    timers.clear()
    notices.clear()
    notices.profile_closing = False

    # The answer path, with the queue a refresh would have filled first.
    notices.pending_streak_reward = {"type": "gold", "amount": 21}
    notices.milestone_queue.append(hooks.milestones.LADDER[0])
    notices.pending_unlocks.append("Dungeons unlocked!\nSee the CollectQuest window.")
    hooks._announce_earned({
        "completed_quests": [("Review 10 cards", 20)],
        "gold_earned": 30,
        "leveled_up": True,
        "level_gold": 10,
        "dungeon_entrance": True,
        "magnet_found": True,
        "buff_started": hooks.milestones.BUFFS[0],
    })
    fire_timers()

    # The sync path: the batch credits reviews and reaches a dungeon's treasure room.
    stages = iter([(True, 0, False, 0), (True, 0, True, 0)])
    hooks._dungeon_stage = lambda: next(stages)
    hooks.revlog_sync.process_synced_revlog = lambda col, silent=True: {"reviews": 12, "xp": 40}
    hooks._on_sync_did_finish()
    fire_timers()
    notices.show_queued()  # what the stubbed refresh would announce
    fire_timers()
    return "\n".join(shown)


failures = []


def check(case, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {case}" + ("" if ok else f"\n       {detail}"))
    if not ok:
        failures.append(case)


def missing(text: str, kinds) -> list[str]:
    return [m for k in kinds for m in MARKERS[k] if m not in text]


def present(text: str, kinds) -> list[str]:
    return [m for k in kinds for m in MARKERS[k] if m in text]


print("Everything on")
for label, toggles in (("fresh save", {}), ("every kind ticked", {k: True for k in MARKERS})):
    text = run_everything(toggles)
    gone = missing(text, MARKERS)
    check(f"{label}: all shown", not gone, f"missing {gone}")

print("\nOne kind off at a time")
for kind in MARKERS:
    text = run_everything({kind: False})
    leaked = present(text, [kind])
    gone = missing(text, [k for k in MARKERS if k != kind])
    check(f"{kind} off: hidden", not leaked, f"still shown {leaked}")
    check(f"{kind} off: the rest still shown", not gone, f"missing {gone}")
    text = run_everything({kind: True})
    gone = missing(text, MARKERS)
    check(f"{kind} back on: all shown", not gone, f"missing {gone}")

print("\nEverything off")
text = run_everything({k: False for k in MARKERS})
leaked = present(text, MARKERS)
check("nothing shown", not leaked, f"still shown {leaked}")
check("queues drained, not deferred",
      not (notices.milestone_queue or notices.pending_unlocks or notices.pending_lines
           or notices.pending_streak_reward),
      "something is still queued")

print("\nBonus quest notice (not switchable)")
hooks.due_baseline.cleared_status = lambda data, col: (10, 100, True)
hooks.streak.today_str = lambda col=None: "2026-10-03"
STATE.clear()
STATE["notifications"] = {k: False for k in MARKERS}
shown.clear()
check_cleared_day(debounced=False)
check("shown with every kind off", any("bonus quest can't be completed" in m for m in shown),
      f"shown {shown}")

print("\n" + ("FAILED: " + ", ".join(failures) if failures else "All checks passed."))
sys.exit(1 if failures else 0)
