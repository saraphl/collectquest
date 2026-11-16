"""
Pin the shop slot draw: each offer type's weight, the lighter ones still filling what items can't,
and the Magnet drawn from the pool like any other, one purchase a day.
Exit 1 = a check failed.

    python3 tests/shop/test_shop_slots.py
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

shop = importlib.import_module("cq.src.shop")
storage = importlib.import_module("cq.src.storage")
milestones = importlib.import_module("cq.src.milestones")

FAILS = []
RUNS = 20000


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def state(unowned=0, refinement=False, active=1, magnet_stage=0):
    """A save that owns every gold item but `unowned` of them (ones with no tier prerequisite), on
    milestone `active`."""
    d = storage._default_state()
    if refinement:
        d["prestige_upgrades"] = {"refinement": 1}
    milestones.get_state(d).update(active=active, magnet_stage=magnet_stage)
    gold = [c["id"] for c in shop.collectibles_for_gold(d)]
    keep = [cid for cid in gold if cid not in shop.TIER_PREREQUISITE][:unowned]
    d["owned_collectibles"] = [cid for cid in gold if cid not in keep]
    return d


def tally(d):
    """Average gem slots per restock, and how often any gem / the Shard slot shows."""
    gems = any_gem = shard = 0
    for _ in range(RUNS):
        types_ = [s["type"] for s in shop._restock(d, 999)]
        gems += types_.count("gem")
        any_gem += "gem" in types_
        shard += "shards" in types_
    return gems / RUNS, any_gem / RUNS, shard / RUNS


print("the weights")
check("an item weighs 10", shop.SLOT_WEIGHT_ITEM == 10)
check("gems weigh 5, 4 and 4",
      shop.SLOT_WEIGHT_GEM == {"random": 5, "specific": 4, "most_needed": 4}, str(shop.SLOT_WEIGHT_GEM))
check("one pool entry per weighted gem offer",
      [g["kind"] for g in shop._GEM_PLACEHOLDERS] == list(shop.SLOT_WEIGHT_GEM))
check("the Shard weighs 13", shop.SLOT_WEIGHT_SHARDS == 13)
check("the gem offers together weigh what the Shard does",
      sum(shop.SLOT_WEIGHT_GEM.values()) == shop.SLOT_WEIGHT_SHARDS)
check("the Magnet weighs 2", shop.SLOT_WEIGHT_MAGNET == 2)

print("\nfilling the shop")
random.seed(5)
d = state()
kinds = set()
full = True
for _ in range(200):
    slots = shop._restock(d, 999)
    full = full and len(slots) == 3 and all(s["type"] == "gem" for s in slots)
    kinds.add(tuple(sorted((bool(s.get("random")), bool(s.get("most_needed"))) for s in slots)))
check("nothing left to sell: three gems", full)
check("one of each kind", kinds == {((False, False), (False, True), (True, False))}, str(kinds))

d = state(unowned=1)
sizes = {len(shop._restock(d, 999)) for _ in range(200)}
check("one item left: still three slots", sizes == {3}, str(sizes))

gems_only = [dict(g) for g in shop._GEM_PLACEHOLDERS]
check("more slots than the pool holds: the whole pool", len(shop._draw_slots(gems_only, 4)) == 3)
check("no slots: nothing drawn", shop._draw_slots(gems_only, 0) == [])

print("\na weight of 0")
real_weights = shop.SLOT_WEIGHT_GEM
shop.SLOT_WEIGHT_GEM = dict.fromkeys(real_weights, 0)
random.seed(6)
d = state(unowned=3)
check("no gem while items can fill the shop",
      all(s["type"] == "collectible" for _ in range(200) for s in shop._restock(d, 999)))
d = state(unowned=1)
mixes = {tuple(sorted(s["type"] for s in shop._restock(d, 999))) for _ in range(200)}
check("gems still fill the rest", mixes == {("collectible", "gem", "gem")}, str(mixes))
shop.SLOT_WEIGHT_GEM = real_weights

print("\nhow often gems show")
random.seed(7)
d = state(unowned=20)
pool = shop._build_daily_slot_pool(999, set(d["owned_collectibles"]), d)
check("20 items in the pool", sum(s["type"] == "collectible" for s in pool) == 20)
gems, any_gem, _ = tally(d)
# The gems' 13 against the items' 200, over three slots.
check("about 0.19 gem slots a restock", 0.17 < gems < 0.21, f"{gems:.3f}")
check("a gem in about one restock in six", 0.16 < any_gem < 0.20, f"{any_gem:.3f}")

d = state(unowned=20, refinement=True)
pool = shop._build_daily_slot_pool(999, set(d["owned_collectibles"]), d)
items = sum(s["type"] == "collectible" for s in pool)
_, any_gem, shard = tally(d)
check("gems as a group show about as often as the Shard slot", abs(any_gem - shard) < 0.02,
      f"{items} items: gem {any_gem:.3f}, shard {shard:.3f}")

print("\nmagnets")
SOLD = 9  # milestone #8 done: Magnets in the shop, four slots, the first upgrade waiting


def has_magnet(d):
    pool = shop._build_daily_slot_pool(999, set(d["owned_collectibles"]), d)
    return sum(s["type"] == "magnet_placeholder" for s in pool) == 1


check("none before milestone #8", not has_magnet(state(unowned=20, active=SOLD - 1)))
check("none with no upgrade waiting", not has_magnet(state(unowned=20, active=SOLD, magnet_stage=1)))
d = state(unowned=20, active=SOLD)
check("one in the pool once the shop stocks them", has_magnet(d))
random.seed(8)
sizes, most, shown, magnet_slots = set(), 0, 0, []
for _ in range(RUNS):
    slots = shop._restock(d, 999)
    found = [s for s in slots if s["type"] == "magnet"]
    sizes.add(len(slots))
    most = max(most, len(found))
    shown += bool(found)
    magnet_slots += found
check("still four slots", sizes == {4}, str(sizes))
check("never more than one", most == 1, str(most))
check("the slot is a Magnet at its price",
      all(s == {"type": "magnet", "cost": shop.MAGNET_COST_GOLD} for s in magnet_slots))
# 2 against the items' 200 and the gems' 13, over four slots.
check("in about one restock in twenty-five", 0.033 < shown / RUNS < 0.045, f"{shown / RUNS:.3f}")

d = state(active=SOLD)
random.seed(8)
mixes = {tuple(sorted(s["type"] for s in shop._restock(d, 999))) for _ in range(200)}
check("nothing else to sell: it fills the fourth slot", mixes == {("gem", "gem", "gem", "magnet")}, str(mixes))

print("\none a day")
day = ["2026-11-16"]
real_today_str = shop._today_str
shop._today_str = lambda: day[0]


def magnet_slot():
    return {"type": "magnet", "cost": shop.MAGNET_COST_GOLD}


d = state(active=SOLD)
check("too poor: no sale", shop.buy_magnet(d, magnet_slot()) == shop.MAGNET_BUY_POOR)
check("and the day isn't used up", has_magnet(d))
milestones.award_magnet(d)
check("a bonus quest's Magnet doesn't use it up either", has_magnet(d))
d["money"] = 1000
bought = magnet_slot()
check("the first of the day sells", shop.buy_magnet(d, bought) is True)
check("it counted", milestones.magnets_held(d) == 2, str(milestones.magnets_held(d)))
check("none in the pool for the rest of the day", not has_magnet(d))
random.seed(8)
mixes = {tuple(sorted(s["type"] for s in shop._restock(d, 999))) for _ in range(200)}
check("no restock offers another", mixes == {("gem", "gem", "gem")}, str(mixes))
check("a second one is refused", shop.buy_magnet(d, magnet_slot()) == shop.MAGNET_BUY_DAILY)
check("and costs nothing", d["money"] == 1000 - shop.MAGNET_COST_GOLD, str(d["money"]))
day[0] = "2026-11-17"
check("back in the pool the next day", has_magnet(d))
check("and it sells again", not isinstance(shop.buy_magnet(d, magnet_slot()), str))
shop._today_str = real_today_str

print("\nwhere they land")
random.seed(9)
d = state(unowned=3)
first = last = 0
for _ in range(RUNS):
    slots = shop._restock(d, 999)
    first += slots[0]["type"] == "gem"
    last += slots[-1]["type"] == "gem"
check("no more often in the last slot than the first", abs(first - last) / RUNS < 0.02,
      f"{first / RUNS:.3f} vs {last / RUNS:.3f}")

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
    sys.exit(1)
print("all shop slot checks passed")
