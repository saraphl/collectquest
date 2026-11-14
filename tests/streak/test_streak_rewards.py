"""
Pin the 7-day streak payouts: a fixed base of the week's resource at every level, the resource's
own stat applying to it, and items and the prestige upgrade adding into one streak reward stat. Gold
per level is pinned here too: paid on level-ups, and on nothing else.
Exit 1 = a payout changed.

    python3 tests/streak/test_streak_rewards.py
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
shop = importlib.import_module("cq.src.shop")
storage = importlib.import_module("cq.src.storage")
streak = importlib.import_module("cq.src.streak")

FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got!r}")


def pay(kind, owned=(), streak_bonus=0, roll=None, level=50, extra=None, **upgrades):
    """One payout from a fresh save. `roll` fixes random.random() for the fraction of a gem; `extra`
    is merged into the save."""
    data = storage._default_state()
    data["level"] = level
    data["owned_collectibles"] = list(owned)
    data["prestige_upgrades"] = {"streak_bonus": streak_bonus, **upgrades}
    data.update(extra or {})
    saved = random.random
    if roll is not None:
        random.random = lambda: roll
    try:
        return streak.grant_streak_reward(data, kind)
    finally:
        random.random = saved


print("base payouts, the same at every level")
for level in (1, 20, 130):
    check(f"XP week, level {level}", pay("xp", level=level), {"type": "xp", "amount": 600})
    check(f"gold week, level {level}", pay("gold", level=level), {"type": "gold", "amount": 60})
    check(f"gem week, level {level}", pay("gem", level=level), {"type": "gem", "amount": 2})

print("each week's own stat")
check("XP % (Crystal, +3%)", pay("xp", ["crystal"])["amount"], 618)
check("XP % from prestige", pay("xp", xp_percent=1)["amount"], 780)
check("gold per level stays out of the gold week (Hammer)", pay("gold", ["hammer"])["amount"], 60)
check("gold % from prestige", pay("gold", gold_percent=1)["amount"], 78)
# Blue shield is +40% gem luck: 2.8 gems, so two and an 80% roll for a third.
check("gem luck, roll fails", pay("gem", ["shield_blue"], roll=0.99)["amount"], 2)
check("gem luck, roll succeeds", pay("gem", ["shield_blue"], roll=0.0)["amount"], 3)
check("gem luck leaves the other weeks alone",
      (pay("xp", ["shield_blue"])["amount"], pay("gold", ["shield_blue"])["amount"]), (600, 60))

print("the streak reward stat: items and prestige add")
check("upgrade level 1, +30%", pay("xp", streak_bonus=1)["amount"], 780)
check("upgrade level 10, +300%", pay("gold", streak_bonus=10)["amount"], 240)
# Snow banner is +20% streak rewards and +8% gold: 60 x 1.08 x 1.2 = 77.76, the rest carried.
check("Snow banner, gold week", pay("gold", ["flag_snow"])["amount"], 77)
check("Snow banner, XP week", pay("xp", ["flag_snow"])["amount"], 720)
# +20% and +60% add to +80%, where multiplying them would give +92%.
check("Snow banner and upgrade level 2", pay("xp", ["flag_snow"], streak_bonus=2)["amount"], 1080)
# 2 x 1.3 = 2.6 gems.
check("gem week, upgrade level 1, roll fails", pay("gem", streak_bonus=1, roll=0.99)["amount"], 2)
check("gem week, upgrade level 1, roll succeeds", pay("gem", streak_bonus=1, roll=0.0)["amount"], 3)
# Gem luck and the streak stat multiply: 2 x 1.4 x 1.6 = 4.48 gems.
check("gem week, Blue shield and upgrade level 2",
      (pay("gem", ["shield_blue"], streak_bonus=2, roll=0.99)["amount"],
       pay("gem", ["shield_blue"], streak_bonus=2, roll=0.0)["amount"]), (4, 5))

print("item quality and the gem buffs reach the payout")
# A Fine Island is +12.5% streak rewards and +2.5% XP: 600 x 1.025 x 1.125 = 691.875.
fine_island = {shop.QUALITY_KEY: {"island": shop.QUALITY_FINE}}
check("Fine Island, XP week", pay("xp", ["island"], extra=fine_island)["amount"], 691)
doubled = {"milestones": {"active_buffs": [{"id": milestones.BUFF_GEMS_DOUBLE, "started_epoch": 1}]}}
check("Double gem rewards, gem week", pay("gem", extra=doubled)["amount"], 4)
no_list = {"owned_collectibles": None}
check("a null item list pays the base", pay("gold", extra=no_list)["amount"], 60)

print("gold per level (Hammer, +4g) pays on level-ups only")
data = storage._default_state()
data.update(owned_collectibles=["hammer"], total_xp=100)  # exactly level 2
check("a level-up: 20 + 4", review_rewards.grant_level_up(data, 1, ["hammer"])[0], 24)
check("a quest keeps its own gold", review_rewards.quest_gold_exact(data, 20, ["hammer"]), 20.0)

print("the stat the Stats section shows is the one paid")
data = storage._default_state()
data.update(owned_collectibles=["island", "flag_snow"], prestige_upgrades={"streak_bonus": 3})
check("Island, Snow banner and upgrade level 3", streak.reward_bonus_percent(data), 120)

print()
if FAILS:
    print(f"{len(FAILS)} failing case(s)")
    sys.exit(1)
print("all streak reward checks passed")
