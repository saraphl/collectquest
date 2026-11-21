"""
Pin what a prestige does to the day's quests: they carry on with their progress, a finished quest or
clear-the-day bonus can't pay twice, unfinished quests re-roll their gems with the new gem luck, and a
finished row shows what it paid. Exit 1 = a check failed.

    python3 tests/prestige/test_prestige_quests.py
"""
import importlib
import os
import pathlib
import pickle
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))

import PyQt6.QtCore as QtCore
import PyQt6.QtGui as QtGui
import PyQt6.QtWidgets as QtWidgets

# Same flat aqt.qt stand-in as test_prestige_ui.py, so the progress view can be imported.
qt = types.ModuleType("aqt.qt")
for src in (QtCore, QtGui, QtWidgets):
    for name in dir(src):
        if name.startswith("Q") or name == "Qt":
            setattr(qt, name, getattr(src, name))
sys.modules["aqt.qt"] = qt
aqt = types.ModuleType("aqt")
aqt.mw = None
aqt.qt = qt
aqt.gui_hooks = types.SimpleNamespace()
sys.modules["aqt"] = aqt
sys.modules["aqt.gui_hooks"] = types.ModuleType("aqt.gui_hooks")
for name, attrs in (
    ("aqt.utils", {"tooltip": lambda *a, **k: None, "showInfo": lambda *a, **k: None,
                   "openLink": lambda *a, **k: None, "askUser": lambda *a, **k: True}),
    ("aqt.theme", {"theme_manager": types.SimpleNamespace(night_mode=False)}),
    ("anki", {}), ("anki.collection", {}),
):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

due_baseline = importlib.import_module("cq.src.due_baseline")
prestige = importlib.import_module("cq.src.prestige")
quests = importlib.import_module("cq.src.quests")
review_rewards = importlib.import_module("cq.src.review_rewards")
storage = importlib.import_module("cq.src.storage")
streak = importlib.import_module("cq.src.streak")
progress = importlib.import_module("cq.src.ui.progress")

TODAY = "2026-11-09"
COL = object()  # never touched: everything that would read it is stubbed below
BASELINE = {"date": TODAY, "total": 150, "decks": {}}
streak.today_str = lambda col=None: TODAY
due_baseline.ensure_baseline = lambda state, col: state.get("quest_due_baseline") or None
due_baseline.new_card_count = lambda col, excluded: 0

FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(label)
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def quest(kind, target, progress_, colors, gem_pct=100.0):
    q = {
        "id": kind, "target": target, "progress": progress_, "reward_xp": 100, "reward_gold": 10,
        "reward_gem_colors": list(colors), "reward_gem": bool(colors),
        "reward_gem_color": colors[0] if colors else None, "label": f"{kind} {target}",
    }
    if gem_pct is not None:
        q["gem_pct"] = gem_pct
    if kind == quests.QUEST_KIND_CORRECT_REVIEWS:
        q["correct_start"] = 0
    return q


def run_state():
    """A level-80 run mid-day: one quest finished and paid, one not, the day cleared and paid."""
    s = storage._default_state()
    s.update({
        "total_xp": 10**7, "level": 80, "last_date": TODAY, "reviews_today": 60, "correct_today": 40,
        "quest_due_baseline": BASELINE,
        "daily_quests": [
            quest(quests.QUEST_KIND_CORRECT_REVIEWS, 40, 40, ["blue"]),
            quest(quests.QUEST_KIND_TOTAL_REVIEWS, 90, 60, ["pink", "green", "yellow"]),
        ],
        "cleared_bonus_date": TODAY, "cleared_bonus_total": 150,
        "cleared_bonus_paid": {"xp": 300, "gold": 40, "gems": 1},
        "last_processed_revlog_id": 1794238633385,
        "credited_revlog_date": TODAY, "credited_revlog_ids": [1, 2, 3],
        # No gem luck upgrades, so 100% is exactly one gem after the prestige.
        "prestige_upgrades": {}, "prestige_points_total": 0,
    })
    s["daily_quests"][0]["paid"] = {"xp": 500, "gold": 55, "gems": 2}
    return s


def do_prestige(state):
    saved = {}
    storage.load = lambda: pickle.loads(pickle.dumps(state))
    storage.save = lambda s: saved.update(s=s)
    prestige.perform_prestige(COL, force=True)
    return saved["s"]


print("prestige keeps today's quests")
before = run_state()
after = do_prestige(before)
check("level reset", after["level"], 1)
for i, (b, a) in enumerate(zip(before["daily_quests"], after["daily_quests"])):
    for key in ("id", "target", "progress", "reward_xp", "reward_gold", "label"):
        check(f"quest {i} {key}", a.get(key), b.get(key))
check("finished quest keeps its gems", after["daily_quests"][0]["reward_gem_colors"], ["blue"])
check("finished quest keeps its payout", after["daily_quests"][0].get("paid"), {"xp": 500, "gold": 55, "gems": 2})
check("unfinished quest re-rolled at 100% x1", len(after["daily_quests"][1]["reward_gem_colors"]), 1)
for key in ("correct_today", "reviews_today", "cleared_bonus_date", "cleared_bonus_total",
            "cleared_bonus_paid", "last_processed_revlog_id", "credited_revlog_date",
            "credited_revlog_ids", "quest_due_baseline"):
    check(f"kept {key}", after.get(key), before[key])

print("nothing pays twice after a prestige")
state = pickle.loads(pickle.dumps(after))
completed, _, _ = quests.on_review(state, 3, col=COL)
check("finished correct quest not completed again", [q["id"] for q in completed], [])
check("correct quest progress", state["daily_quests"][0]["progress"], 40)
earned = {"gold_earned": 0, "gem_earned": 0, "completed_quests": []}
check("bonus already paid today", review_rewards._award_cleared_bonus(state, [], COL, earned, (150, 150)), (0, 0))

print("undo can't reach back past a prestige")
aqt.mw = types.SimpleNamespace(_collectquest_undo_state=[{"xp_delta": 50, "quest_progress_revert": [(1, 59)]}])
do_prestige(run_state())
check("undo buffer emptied", aqt.mw._collectquest_undo_state, [])
aqt.mw = None

print("gem luck applies to the re-roll")
lucky = run_state()
# 10 levels at 30% a level is +300% gem luck, so a 100% chance pays exactly four gems.
lucky["prestige_upgrades"] = {"quest_reward": 10}
check("luck step", prestige.QUEST_REWARD_STEP_PERCENT, 30)
check("four gems at x4 luck", len(do_prestige(lucky)["daily_quests"][1]["reward_gem_colors"]), 4)

print("a quest rolled before gem_pct was stored keeps its gems")
legacy = run_state()
legacy["daily_quests"][1] = quest(quests.QUEST_KIND_TOTAL_REVIEWS, 90, 60, ["pink", "green"], gem_pct=None)
check("legacy gems kept", do_prestige(legacy)["daily_quests"][1]["reward_gem_colors"], ["pink", "green"])

print("a new quest stores its base gem chance")
q = quests._build_new_cards()
check("new-card gem_pct", q.get("gem_pct"), quests.REWARD_NEW_GEM_PCT)

print("completing a quest records what it paid")
state = storage._default_state()
state.update({"last_date": TODAY, "quest_due_baseline": BASELINE,
              "daily_quests": [quest(quests.QUEST_KIND_TOTAL_REVIEWS, 5, 4, [])]})
earned = review_rewards.apply_one_review(state, 3, counts_as_due_review=True, col=None)
paid = state["daily_quests"][0].get("paid")
check("paid recorded", isinstance(paid, dict), True)
if isinstance(paid, dict):
    check("paid xp matches tooltip", paid["xp"], earned["completed_quests"][0][1])
    # Not earned["gold_earned"], which includes the level-up's gold.
    check("paid gold", paid["gold"], 10)
    check("paid gems", paid["gems"], 0)

print("paying the bonus records the day")
state = storage._default_state()
state.update({"last_date": TODAY, "quest_due_baseline": BASELINE})
earned = {"gold_earned": 0, "gem_earned": 0, "completed_quests": []}
xp_paid, gold_paid = review_rewards._award_cleared_bonus(state, [], COL, earned, (150, 150))
check("bonus record", state.get("cleared_bonus_paid"),
      {"date": TODAY, "xp": xp_paid, "gold": gold_paid, "gems": earned["gem_earned"]})


def bonus_row_text(data):
    """The bonus row's label, drawn with the day's progress stubbed to cleared."""
    review_rewards.cleared_bonus_display = lambda d, c: (150, 150)
    box = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(box)
    progress._add_cleared_bonus_row(lay, box, data, [], COL, True)
    labels = box.findChildren(QtWidgets.QLabel)
    return labels[-1].text() if labels else ""


print("the bonus row shows the payout only for its own day")
check("today's record shown", "+777&nbsp;XP" in bonus_row_text(state | {
    "cleared_bonus_paid": {"date": TODAY, "xp": 777, "gold": 1, "gems": 0}}), True)
check("an earlier day's record ignored", "+777&nbsp;XP" in bonus_row_text(state | {
    "cleared_bonus_paid": {"date": "2026-11-08", "xp": 777, "gold": 1, "gems": 0}}), False)
check("undone claim ignored", "+777&nbsp;XP" in bonus_row_text(state | {"cleared_bonus_date": "",
    "cleared_bonus_paid": {"date": TODAY, "xp": 777, "gold": 1, "gems": 0}}), False)

print("the finished row shows the payout")
check("paid row", progress._paid_reward({"xp": 849, "gold": 91, "gems": 2}), (849, "+91g, +2 gems"))
check("one gem", progress._paid_reward({"xp": 5, "gold": 1, "gems": 1}), (5, "+1g, +1 gem"))
check("unrecorded", progress._paid_reward({}), None)
check("missing", progress._paid_reward(None), None)

if FAILS:
    print(f"\n{len(FAILS)} check(s) failed")
    sys.exit(1)
print("\nall checks passed")
