"""
Milestone #17 with a stubbed aqt: only refines that land on Superior count toward it, a save that
had finished the 16-milestone track picks it up from zero, and its reward (a Normal item refined
straight to Superior at the Fine price) rolls at 10% and only once it's done. Run after touching
refine_item, LADDER or lucky_refine_percent. Exit 1 = a case changed.

    python3 tests/milestones/test_lucky_refine.py
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
m = importlib.import_module("cq.src.milestones")
storage = importlib.import_module("cq.src.storage")

M17 = 17
# Level 1-30 items: 1 shard to Fine, 2 more to Superior.
CHEAP = [c["id"] for c in shop.COLLECTIBLES if shop.is_refinable(c) and shop.craft_price_each(c) == 1]
FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got!r}" + ("" if ok else f" (want {want!r})"))
    if not ok:
        FAILS.append(label)


def save(active, owned=CHEAP, shards=999):
    """A save on milestone `active` with refinement's first band and `owned`, all Normal."""
    d = storage._default_state()
    d["total_xp"] = 10**7
    d["owned_collectibles"] = list(owned)
    d["prestige_upgrades"] = {"refinement": 1}
    d["shards"] = shards
    m.get_state(d).update({"started": "y", "active": active})
    return d


print("the milestone")
entry = m.LADDER[M17 - 1]
check("#17 is the last one", m.TRACK_LENGTH, M17)
check("objective", m.objective_label(entry), "Refine 5 items to Superior")
check("reward", entry["reward"], "Refining can skip to Superior (10%)")

print("\na save that had finished the old track")
d = save(M17)
check("is on #17, not finished", (m.is_finished(d), m.active_progress(d)), (False, (0, 5)))
check("with no lucky refine yet", m.lucky_refine_percent(d), 0)

print("\nwhat counts")
shop.refine_item(d, CHEAP[0])
check("a Fine step doesn't", (shop.item_quality(d, CHEAP[0]), m.active_progress(d)), (1, (0, 5)))
shop.refine_item(d, CHEAP[0])
check("the Superior step does", (shop.item_quality(d, CHEAP[0]), m.active_progress(d)), (2, (1, 5)))
for cid in CHEAP[1:4]:
    shop.refine_item(d, cid)
    shop.refine_item(d, cid)
check("four Superior items, still active", (m.active_progress(d), m.is_finished(d)), ((4, 5), False))
shop.set_item_quality(d, CHEAP[4], shop.QUALITY_FINE)
shop.refine_item(d, CHEAP[4])
check("the fifth completes it, even bought Fine", m.is_finished(d), True)
check("and is announced", [e["reward"] for e in m.take_pending_announcements(d)], [entry["reward"]])
check("the reward is granted", m.lucky_refine_percent(d), 10)

d = save(M17 - 1)
shop.refine_item(d, CHEAP[0])
shop.refine_item(d, CHEAP[0])
check("nothing counts while #16 is active", (m.get_state(d)["active"], m.get_state(d)["active_progress"]), (16, 0))

print("\nlucky refine")
real_random = shop.random.random
shop.random.random = lambda: 0.0  # every roll lands
d = save(M17, shards=1)
shop.refine_item(d, CHEAP[0])
check("never before #17 is done", shop.item_quality(d, CHEAP[0]), 1)
d = save(M17 + 1, shards=1)
check("a lucky refine pays the Fine price", (shop.refine_item(d, CHEAP[0]), d["shards"]), (True, 0))
check("and lands on Superior", shop.item_quality(d, CHEAP[0]), 2)
tome = shop.get_collectible("tome_begin")
d = save(M17 + 1, owned=["tome_begin"])
d["prestige_upgrades"]["refinement"] = shop.REFINEMENT_BANDS_MAX
shop.refine_item(d, "tome_begin")
check("a tome too, at its own Fine price",
      (shop.item_quality(d, "tome_begin"), 999 - d["shards"]), (2, shop.refine_cost(tome)))
shop.random.random = lambda: 0.999  # no roll lands
d = save(M17 + 1)
shop.refine_item(d, CHEAP[0])
check("an unlucky one is the usual Fine step", (shop.item_quality(d, CHEAP[0]), d["shards"]), (1, 998))
shop.random.random = real_random

random.seed(17)
TRIES = 20000
hits = 0
for _ in range(TRIES):
    d = save(M17 + 1, owned=CHEAP[:1], shards=1)
    shop.refine_item(d, CHEAP[0])
    hits += shop.item_quality(d, CHEAP[0]) == shop.QUALITY_SUPERIOR
rate = hits / TRIES * 100
ok = 9 <= rate <= 11
print(f"  {'ok  ' if ok else 'FAIL'} about 1 in 10: {rate:.2f}%")
if not ok:
    FAILS.append("lucky rate")

print(f"\n{len(FAILS)} FAILED: {', '.join(FAILS)}" if FAILS else "\nall lucky refine checks passed")
sys.exit(1 if FAILS else 0)
