"""
Pin the shop slot draw: gem offers weigh a third of an item, and still fill what items can't.
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

FAILS = []
RUNS = 20000


def check(label, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {label}{': ' + detail if detail else ''}")
    if not ok:
        FAILS.append(label)


def state(unowned=0, refinement=False):
    """A save that owns every gold item but `unowned` of them (ones with no tier prerequisite)."""
    d = storage._default_state()
    if refinement:
        d["prestige_upgrades"] = {"refinement": 1}
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


print("the weight")
# Counted, not 3: adding or dropping a gem offer has to revisit the weight.
check("the gem offers together weigh one item",
      abs(len(shop._GEM_PLACEHOLDERS) * shop.GEM_SLOT_WEIGHT - 1) < 1e-9)

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
real_weight = shop.GEM_SLOT_WEIGHT
shop.GEM_SLOT_WEIGHT = 0
random.seed(6)
d = state(unowned=3)
check("no gem while items can fill the shop",
      all(s["type"] == "collectible" for _ in range(200) for s in shop._restock(d, 999)))
d = state(unowned=1)
mixes = {tuple(sorted(s["type"] for s in shop._restock(d, 999))) for _ in range(200)}
check("gems still fill the rest", mixes == {("collectible", "gem", "gem")}, str(mixes))
shop.GEM_SLOT_WEIGHT = real_weight

print("\nhow often gems show")
random.seed(7)
d = state(unowned=20)
pool = shop._build_daily_slot_pool(999, set(d["owned_collectibles"]), d)
check("20 items in the pool", sum(s["type"] == "collectible" for s in pool) == 20)
gems, any_gem, _ = tally(d)
# Equal weights gave 9 / 23 = 0.39 gem slots a restock.
check("about 0.15 gem slots a restock", 0.13 < gems < 0.17, f"{gems:.3f}")
check("a gem in about one restock in seven", 0.12 < any_gem < 0.16, f"{any_gem:.3f}")

d = state(unowned=20, refinement=True)
pool = shop._build_daily_slot_pool(999, set(d["owned_collectibles"]), d)
items = sum(s["type"] == "collectible" for s in pool)
_, any_gem, shard = tally(d)
check("gems as a group show about as often as the Shard slot", abs(any_gem - shard) < 0.02,
      f"{items} items: gem {any_gem:.3f}, shard {shard:.3f}")

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
