"""
Pin the craft price bands, the pre-rolled next craft and the escalating prestige gem trade.
Exit 1 = a check failed.

    python3 tests/test_craft_price.py
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

shop = importlib.import_module("cq.src.shop")
milestones = importlib.import_module("cq.src.milestones")
prestige = importlib.import_module("cq.src.prestige")
storage = importlib.import_module("cq.src.storage")

FAILS = []


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def state(level_owned_upto=0, gems=9):
    d = storage._default_state()
    d["owned_collectibles"] = [c["id"] for c in shop.COLLECTIBLES if c["unlock_at_level"] <= level_owned_upto]
    d["gems"] = {c: gems for c, _ in shop.GEM_COLORS}
    return d


print("price bands")
for level, each, band in ((1, 1, "1–30"), (30, 1, "1–30"), (31, 2, "31–60"), (60, 2, "31–60"),
                          (61, 3, "61–90"), (90, 3, "61–90"), (91, 4, "91–120"), (110, 4, "91–120")):
    c = {"unlock_at_level": level}
    check(f"level {level} costs {each} of each, band {band}",
          shop.craft_price_each(c) == each and shop.craft_band_label(c) == band,
          f"{shop.craft_price_each(c)}, {shop.craft_band_label(c)}")
for cid, each in (("leaf", 1), ("lantern", 1), ("skull", 2), ("shield_blue", 2), ("gemstone", 3), ("tome_begin", 3)):
    check(f"{cid} costs {each} of each", shop.craft_price_each(shop.get_collectible(cid)) == each)

print("\nthe next craft")
random.seed(1)
d = state()
first = shop.next_craft(d, 70)
check("is rolled and stored", first is not None and d["next_craft_id"] == first["id"])
check("holds across calls", all(shop.next_craft(d, 70)["id"] == first["id"] for _ in range(20)))
check("holds across a level-up", shop.next_craft(d, 95)["id"] == first["id"])
d["next_craft_id"] = "hourglass"  # unlocks at 60
check("holds when undo drops the level below it", shop.next_craft(d, 59)["id"] == "hourglass")
d["owned_collectibles"].append("hourglass")  # bought for gold, say
again = shop.next_craft(d, 70)
check("is redrawn once it leaves the pool", again is not None and again["id"] != "hourglass"
      and d["next_craft_id"] == again["id"])

d = state()
d["next_craft_id"] = "crown"  # craftable, but sold for gold too
real_targeted = milestones.has_targeted_craft
milestones.has_targeted_craft = lambda data: True
narrowed = shop.next_craft(d, 70)
check("gem-only items first redraws a gold item", narrowed is not None and narrowed.get("cost_gold") is None,
      narrowed["id"] if narrowed else "none")
milestones.has_targeted_craft = real_targeted

d = state(level_owned_upto=200)
check("nothing left to craft", shop.next_craft(d, 200) is None and d["next_craft_id"] is None)

print("\ncrafting")
d = state(gems=3)
d["next_craft_id"] = "gemstone"
cid, _ = shop.craft_next(d, 70)
check("pays the band's price", cid == "gemstone" and all(n == 0 for n in d["gems"].values()), str(d["gems"]))
check("owns the item", "gemstone" in d["owned_collectibles"])
check("and rolls the next", d["next_craft_id"] not in (None, "gemstone"))

d = state(gems=2)
d["next_craft_id"] = "gemstone"
check("can't pay 3 of each with 2", shop.craft_next(d, 70) == (None, None)
      and all(n == 2 for n in d["gems"].values()) and d["next_craft_id"] == "gemstone")

d = state(gems=3)
d["gems"]["pink"] = 0
d["next_craft_id"] = "gemstone"
real_buff = milestones.buff_is_active
milestones.buff_is_active = lambda data, buff_id, col=None: buff_id == milestones.BUFF_CRAFT_CHEAPER
cid, _ = shop.craft_next(d, 70)
milestones.buff_is_active = real_buff
check("the discount buff waives the scarcest color", cid == "gemstone"
      and d["gems"] == {c: 0 for c, _ in shop.GEM_COLORS}, str(d["gems"]))

d = state(level_owned_upto=59)
d["milestones"] = milestones.default_state()
d["milestones"].update(started="2026-10-01", active=5, active_progress=2)  # #5: craft 3 items
check("craft milestone short with nothing left at 59", milestones.craft_objective_blocked(d, 59))
d["next_craft_id"] = "hourglass"
check("the kept roll still counts after an undone level-up", not milestones.craft_objective_blocked(d, 59))

check("prestige clears the roll", "next_craft_id" not in storage.PRESERVED_ON_PRESTIGE_KEYS
      and storage._default_state()["next_craft_id"] is None)

print("\nprestige gem trade")
d = state(gems=12)
prices = []
while prestige.can_trade_gems(d):
    prices.append(prestige.gem_trade_each(d))
    prestige.trade_gems_for_point(d)
check("costs 3, then 4, then 5", prices == [3, 4, 5], str(prices))
check("takes exactly that", all(n == 0 for n in d["gems"].values()), str(d["gems"]))
check("banks a point each", d["pending_prestige_points_from_gems"] == 3)
# What perform_prestige does to the save: a fresh state plus the keys a prestige carries over.
fresh = storage.carry_prestige_keys(d, storage._default_state())
check("a prestige resets it to 3", prestige.gem_trade_each(fresh) == 3)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all craft price checks passed")
