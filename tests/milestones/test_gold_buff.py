"""
Pin Double gold rewards: every gold payout doubles while it runs, quest XP doesn't, with Double
quest rewards also running quest gold is still doubled only once, and it drops but never beside the
shop discount.
Exit 1 = a payout changed.

    python3 tests/milestones/test_gold_buff.py
"""
import importlib
import pathlib
import random
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
streak = importlib.import_module("cq.src.streak")

FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got!r}")


def save(*buff_ids):
    data = storage._default_state()
    data["milestones"] = {"active_buffs": [{"id": b, "started_epoch": 1} for b in buff_ids]}
    return data


GOLD, QUESTS = milestones.BUFF_GOLD_DOUBLE, milestones.BUFF_QUESTS_DOUBLE

print("the buff exists and shares the Shop group")
check("in the Shop group", milestones.buff_by_id(GOLD)["system"], milestones.SYS_SHOP)

print("quest gold doubles once, whichever doublers run")
for label, buffs, want in (("no buff", (), 20.0), ("gold", (GOLD,), 40.0),
                           ("quests", (QUESTS,), 40.0), ("both", (GOLD, QUESTS), 40.0)):
    check(f"quest gold, {label}", review_rewards.quest_gold_exact(save(*buffs), 20, []), want)

print("quest XP ignores the gold buff")
check("quest XP, gold", review_rewards.quest_xp_exact(save(GOLD), 10, []), 10.0)
check("quest XP, both", review_rewards.quest_xp_exact(save(GOLD, QUESTS), 10, []), 20.0)

print("every other gold payout doubles under the gold buff only")
check("dungeon gold, gold", review_rewards.dungeon_gold_exact(save(GOLD), 30, []), 60.0)
check("dungeon gold, quests", review_rewards.dungeon_gold_exact(save(QUESTS), 30, []), 30.0)
data = save(GOLD)
data["total_xp"] = 100  # exactly level 2
check("level-up gold, gold", review_rewards.grant_level_up(data, 1, [])[0], 40)
data = save(QUESTS)
data["total_xp"] = 100
check("level-up gold, quests", review_rewards.grant_level_up(data, 1, [])[0], 20)
check("streak gold week, gold", streak.grant_streak_reward(save(GOLD), "gold")["amount"], 120)
check("streak XP week, gold", streak.grant_streak_reward(save(GOLD), "xp")["amount"], 600)

print("it drops, but never beside the shop discount")
milestones.buff_drop_percent = lambda data: 100  # every roll drops a buff
random.seed(3)
dropped = {(milestones.roll_buff(save()) or {}).get("id") for _ in range(2000)}
check("can drop", GOLD in dropped, True)
beside = {(milestones.roll_buff(save(milestones.BUFF_SHOP_DISCOUNT)) or {}).get("id")
          for _ in range(500)}
check("never beside the shop discount", GOLD in beside, False)

print()
if FAILS:
    print(f"{len(FAILS)} failed")
    sys.exit(1)
print("all passed")
