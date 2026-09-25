"""
Pin the 7-day streak payouts: the wiki's table, gold earned on both gold-paying weeks, prestige and
item bonuses multiplying, and the item-only bonus gem roll. Exit 1 = a payout changed.

    python3 tests/test_streak_rewards.py
"""
import importlib
import pathlib
import random
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

review_rewards = importlib.import_module("cq.src.review_rewards")
storage = importlib.import_module("cq.src.storage")
streak = importlib.import_module("cq.src.streak")

FAILS = []
ALL_STREAK_ITEMS = ["island", "gem_red", "flag_snow"]  # +30, +45, +60 = +135%


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got!r}")


def pay(level, kind, owned=(), streak_bonus=0, roll=None):
    """One payout from a fresh save. `roll` fixes random.random() for the bonus gem roll."""
    data = storage._default_state()
    data["level"] = level
    data["owned_collectibles"] = list(owned)
    data["prestige_upgrades"] = {"streak_bonus": streak_bonus}
    saved = random.random
    if roll is not None:
        random.random = lambda: roll
    try:
        return streak.grant_streak_reward(data, kind)
    finally:
        random.random = saved


def pay_roll(roll):
    """A 35% gem roll under a fixed random.random()."""
    saved = random.random
    random.random = lambda: roll
    try:
        return review_rewards.roll_gem_count(35.0)
    finally:
        random.random = saved


print("base payouts (the wiki's streak table)")
for level, xp_week, gem_week, gold_week in (
    (20, 600, (2, 18), (60, 42)),
    (50, 975, (3, 45), (120, 97)),
):
    check(f"XP week, level {level}", pay(level, "xp")["amount"], xp_week)
    r = pay(level, "gem")
    check(f"gem week, level {level}", (r["amount"], r["gold"]), gem_week)
    r = pay(level, "gold")
    check(f"gold week, level {level}", (r["amount"], r["xp"]), gold_week)

print("base gems by level")
for level, gems in ((19, 1), (20, 2), (29, 2), (30, 3), (59, 3), (60, 4), (90, 5)):
    check(f"level {level}", pay(level, "gem")["amount"], gems)

print("gold earned (Hammer, +4g)")
check("gold week", pay(50, "gold", ["hammer"])["amount"], 124)
check("gem week gold", pay(50, "gem", ["hammer"])["gold"], 49)

print("prestige and items multiply")
check("XP week, x2", pay(50, "xp", streak_bonus=1)["amount"], 1950)
check("XP week, x2 and Island", pay(50, "xp", ["island"], streak_bonus=1)["amount"], 2535)
check("gold week, x2 and Island", pay(50, "gold", ["island"], streak_bonus=1)["amount"], 312)
check("base gems, x2", pay(60, "gem", streak_bonus=1)["amount"], 8)

print("bonus gem roll (items only, scaled by gem luck)")
# The cases below fix random.random(); make sure that is still what decides a roll.
check("fixed roll reaches roll_gem_count", (pay_roll(0.0), pay_roll(0.99)), (1, 0))
# Blue Shield is +40% gem luck: with no streak item there is still nothing to roll.
check("no streak item, lucky roll", pay(50, "gem", ["shield_blue"], roll=0.0)["amount"], 3)
# 135%: one guaranteed bonus gem, then a 35% roll for a second.
check("135%, roll fails", pay(50, "gem", ALL_STREAK_ITEMS, roll=0.99)["amount"], 4)
check("135%, roll succeeds", pay(50, "gem", ALL_STREAK_ITEMS, roll=0.0)["amount"], 5)
# x1.4 luck: 189%, still one guaranteed; the prestige multiplier leaves the bonus alone.
check("189%, x2 prestige, roll fails",
      pay(50, "gem", ALL_STREAK_ITEMS + ["shield_blue"], streak_bonus=1, roll=0.99)["amount"], 7)

print()
if FAILS:
    print(f"{len(FAILS)} failing case(s)")
    sys.exit(1)
print("all streak reward checks passed")
