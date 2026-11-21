"""
Pin Double quest rewards: a quest's XP and gold double, the bonus quest's too, while dungeon and
level-up gold stay as they are.
Exit 1 = a payout changed.

    python3 tests/quests/test_quest_buff.py
"""
import importlib
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.theme", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = None
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

milestones = importlib.import_module("cq.src.milestones")
review_rewards = importlib.import_module("cq.src.review_rewards")
storage = importlib.import_module("cq.src.storage")

FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got!r}")


def save(buffed):
    data = storage._default_state()
    if buffed:
        milestones.get_state(data)["active_buffs"] = [
            {"id": milestones.BUFF_QUESTS_DOUBLE, "started_epoch": 1}
        ]
    return data


print("quest rewards double")
for buffed, mult in ((False, 1), (True, 2)):
    label = "buff" if buffed else "no buff"
    check(f"quest XP, {label}", review_rewards.quest_xp_exact(save(buffed), 10, []), 10.0 * mult)
    check(f"quest gold, {label}", review_rewards.quest_gold_exact(save(buffed), 20, []), 20.0 * mult)

print("other gold doesn't")
check("dungeon gold", review_rewards.dungeon_gold_exact(save(True), 30, []), 30.0)
data = save(True)
data["total_xp"] = 100  # exactly level 2
check("level-up gold", review_rewards.grant_level_up(data, 1, [])[0], 20)

print()
if FAILS:
    print(f"{len(FAILS)} failed")
    sys.exit(1)
print("all passed")
