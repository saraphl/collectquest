"""
Item quality, refinement and Refinement shards (drafts/item-quality.md), with a stubbed aqt: the
numbers the design settled on, the one gate that hides Shard content, and every place that pays or
spends Shards. Exit 1 = something is off.

    python3 tests/test_item_quality.py
"""
import importlib
import pathlib
import random
import sys
import tempfile
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
dungeon = importlib.import_module("cq.src.dungeon")
prestige = importlib.import_module("cq.src.prestige")
review_rewards = importlib.import_module("cq.src.review_rewards")
milestones = importlib.import_module("cq.src.milestones")
storage = importlib.import_module("cq.src.storage")

FAILS = []


def check(label, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}" + ("" if ok else f" (want {want})"))
    if not ok:
        FAILS.append(label)


def approx(label, got, lo, hi):
    ok = lo <= got <= hi
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got:.4g}" + ("" if ok else f" (want {lo}-{hi})"))
    if not ok:
        FAILS.append(label)


def fresh(bands=0, owned=None, level_xp=10**7):
    d = storage._default_state()
    d["total_xp"] = level_xp
    d["owned_collectibles"] = list(owned or [])
    if bands:
        d["prestige_upgrades"] = {"refinement": bands}
    return d


HIDDEN = {"training_shield", "sickle", "cudgel", "flail", "tankard", "spear"}

print("names, effects and numbers")
c = shop.get_collectible("stone")
check("Fine keeps the name's capitals", shop.display_name(shop.get_collectible("tome_begin"), 1),
      "Fine Tome of Beginnings")
check("Superior Stone", shop.display_name(c, 2), "Superior Stone")
check("Fine Stone effect", shop.effect_text(c, 1), "+1.25% XP")
check("Superior Stone effect", shop.effect_text(c, 2), "+1.6% XP")
check("format drops zeros", [shop.format_amount(x) for x in (1.25, 2.5, 3.0, 0.375)], ["1.25", "2.5", "3", "0.38"])
# 0.625 is exact and 56.974999999999994 is a 56.975 with float noise: plain formatting drops both.
check("format rounds halves up", [shop.format_amount(x) for x in (0.625, 56.974999999999994, 3)],
      ["0.63", "56.98", "3"])
check("a Superior tome adds 2 points", shop.effect_text(shop.get_collectible("tome_ascent"), 2),
      "+3 prestige points per prestige, +8% XP")
check("a Fine tome", shop.effect_text(shop.get_collectible("tome_begin"), 1), "+2 prestige points per prestige")
tomes = [shop.get_collectible(t) for t in ("tome_begin", "tome_ascent")]
check("a base of 2 points stays one plural",
      shop.effect_text({"effect": {"prestige_bonus_points": 2},
                        "effect_description": "+2 prestige points per prestige"}, 1),
      "+3 prestige points per prestige")
check("tome steps cost 5x", [(shop.refine_cost(t), shop.refine_cost(t, 1)) for t in tomes], [(15, 30), (20, 40)])
q = {"tome_begin": 2, "tome_ascent": 1}
check("points from a Superior and a Fine tome", shop.prestige_bonus_points(["tome_begin", "tome_ascent"], q), 5)
check("and from a prestige at level 100", prestige.total_prestige_points_gain(100, ["tome_begin", "tome_ascent"], q), 12)
unchanged = [x["id"] for x in shop.COLLECTIBLES
             if shop.has_quality(x) and shop.effect_text(x, 1) == shop.effect_text(x, 0)]
check("every item with stats reads differently as Fine", unchanged, [])
check("nothing to raise: keys and Prism",
      sorted(x["id"] for x in shop.COLLECTIBLES if not shop.has_quality(x)),
      sorted(["key_bronze", "key_silver", "key_gold", "prism"]))
refinable = [x for x in shop.COLLECTIBLES if shop.is_refinable(x)]
check("refinable items", len(refinable), 91)
check("one step on all of them", sum(shop.refine_cost(x) for x in refinable), 228)
check("both steps on all of them", sum(shop.refine_cost(x) + shop.refine_cost(x, 1) for x in refinable), 684)
check("per band", [sum(1 for x in refinable if shop.craft_price_each(x) == b) for b in range(1, 6)],
      [35, 23, 16, 14, 3])
check("new items: total shard luck",
      shop.luck_shard_chance_percent([x["id"] for x in shop.COLLECTIBLES]), 120.0)

print("\nstats at quality")
d = fresh(owned=["stone", "skull"])
shop.set_item_quality(d, "stone", 2)
check("XP % with Superior Stone", shop.xp_bonus_percent(d["owned_collectibles"], shop.quality_map(d)), 1.6)
check("without the map it's normal", shop.xp_bonus_percent(d["owned_collectibles"]), 1.0)
d = fresh(owned=["hammer"])
shop.set_item_quality(d, "hammer", 1)
check("flat gold is a fraction", shop.gold_flat(d["owned_collectibles"], shop.quality_map(d)), 5.0)
check("Normal is stored as absence", (shop.set_item_quality(d, "hammer", 0), d["item_quality"])[1], {})

print("\nthe one gate")
locked, unlocked = fresh(), fresh(bands=1)
check("catalog before refinement", len(shop.catalog(locked)), 97)
check("catalog after", len(shop.catalog(unlocked)), 103)
check("no hidden item in a locked craft pool",
      HIDDEN & {x["id"] for x in shop.craft_pool(999, set(), locked)}, set())
check("no hidden item in a locked shop pool",
      HIDDEN & {s.get("id") for s in shop._build_daily_slot_pool(999, set(), locked)}, set())
check("no Shard slot before refinement",
      any(s["type"] == "shards_placeholder" for s in shop._build_daily_slot_pool(999, set(), locked)), False)
check("a Shard slot after",
      any(s["type"] == "shards_placeholder" for s in shop._build_daily_slot_pool(999, set(), unlocked)), True)
everything = [x["id"] for x in shop.shop_supplied_collectibles(locked)]
check("first-run trades open without the hidden items",
      shop.owns_all_gold_items(fresh(owned=everything)) and shop.owns_all_craftable(fresh(owned=everything)), True)
check("and close again once they appear", shop.owns_all_gold_items(fresh(bands=1, owned=everything)), False)

print("\nrefining")
d = fresh(bands=1, owned=["stone", "crown", "loot_bag", "key_bronze"])
check("level 60 item, one band", shop.refine_status(d, "crown"), shop.REFINE_LOCKED)
check("no Shards", shop.refine_status(d, "stone"), shop.REFINE_POOR)
check("dungeon items never", shop.refine_status(d, "loot_bag"), shop.REFINE_NEVER)
check("keys never", shop.refine_status(d, "key_bronze"), shop.REFINE_NEVER)
check("unowned never", shop.refine_status(d, "fish"), shop.REFINE_NEVER)
d["shards"] = 3
check("refine Stone", shop.refine_item(d, "stone"), True)
check("now Fine, 2 Shards left", (shop.item_quality(d, "stone"), d["shards"]), (1, 2))
check("the Superior step costs double", (shop.refine_item(d, "stone"), d["shards"]), (True, 0))
check("Superior is the last step", shop.refine_status(d, "stone"), shop.REFINE_MAXED)
check("and can't be refined again", shop.refine_item(d, "stone"), False)
d["prestige_upgrades"]["refinement"] = 2
d["shards"] = 2
check("level 60 costs 2", (shop.refine_item(d, "crown"), d["shards"]), (True, 0))

print("\nprestige upgrades")
d = fresh()
d["prestige_points_total"] = 100
check("Shard luck hidden before refinement", prestige.buy_upgrade(d, "shard_luck"), False)
costs = []
for _ in range(6):
    before = prestige.available_prestige_points(d)
    if prestige.buy_upgrade(d, "refinement"):
        costs.append(before - prestige.available_prestige_points(d))
check("refinement costs 3, 4, 5, 6, 7 and stops", costs, [3, 4, 5, 6, 7])
check("five bands", prestige.refinement_bands(d), 5)
check("Shard luck after", prestige.buy_upgrade(d, "shard_luck"), True)
check("+30% per level", prestige.prestige_shard_luck_percent(d), 30)

print("\nthe shop")
random.seed(3)
d = fresh(bands=1)
fine = total = 0
for _ in range(20000):
    for s in shop._restock(d, 999):
        if s.get("type") == "collectible":
            total += 1
            fine += s.get("quality") == 1
approx("Fine offers ~5%", fine / total * 100, 4.5, 5.5)
d = fresh(bands=1)
d["money"] = 1000
d["shop_daily_slots"] = [{"type": "collectible", "id": "fish", "quality": 1}, {"type": "shards", "cost": 50}]
check("buy the Fine offer", shop.buy_collectible(d, "fish", 50), True)
check("owned as Fine", shop.item_quality(d, "fish"), 1)
check("buy a Shard", (shop.buy_shards(d, d["shop_daily_slots"][1]), d["shards"], d["money"]), (True, 1, 1000 - 42 - 50))
check("sold once", shop.buy_shards(d, d["shop_daily_slots"][1]), False)
random.seed(9)
fine = 0
for _ in range(4000):
    d = fresh(bands=1)
    d["gems"] = {k: 99 for k in d["gems"]}
    cid, _c = shop.craft_next(d, 999)
    fine += shop.item_quality(d, cid) == 1
approx("Fine crafts ~5%", fine / 4000 * 100, 4.0, 6.0)

print("\ndungeons")
random.seed(5)
for label, bands, want in (("before refinement", 0, (0, 2, 3)), ("after", 1, (50, 2, 4))):
    shards = 0
    sizes = set()
    for _ in range(40000):
        kinds = dungeon._draw_paths(random.choice(dungeon.PATHS_PER_BRANCHING), True,
                                    allow_shards=bool(bands))
        shards += "shards" in kinds
        sizes.add(len(kinds))
    approx(f"Shards path {label} ~{want[0]}%", shards / 400, want[0] - 1.5, want[0] + 1.5)
    check(f"pathways {label}", (min(sizes), max(sizes)), want[1:])
check("most paths before / after", (dungeon.most_paths(fresh()), dungeon.most_paths(fresh(bands=1))), (3, 4))
random.seed(6)
d = fresh()
check("no Shards in a locked Unmarked path",
      any(dungeon._build_offer("unmarked", d, []).get("outcome") == "shards" for _ in range(5000)), False)
d = fresh(bands=1)
counts = [dungeon._build_offer("shards", d, [])["shards"] for _ in range(20000)]
check("at least one Shard", min(counts), 1)
approx("1.25 Shards a pick on average", sum(counts) / len(counts), 1.2, 1.3)
d["owned_collectibles"] = [x["id"] for x in shop.COLLECTIBLES]
d["prestige_upgrades"]["shard_luck"] = 2
counts = [dungeon._build_offer("shards", d, d["owned_collectibles"])["shards"] for _ in range(20000)]
approx("x2.8 with +120% items and +60% prestige", sum(counts) / len(counts), 3.4, 3.6)
d = fresh(bands=1)
d["milestones"]["active_buffs"] = [{"id": milestones.BUFF_SHARDS_DOUBLE, "started_epoch": 0, "days": 3}]
real_active_buffs, real_drop_percent = milestones.active_buffs, milestones.buff_drop_percent
# Stubbed only around the checks that need a buff running or a sure drop, then put back.
milestones.active_buffs = lambda data, col=None: data["milestones"]["active_buffs"]
check("the buff doubles a pick", all(dungeon._build_offer("shards", d, [])["shards"] % 2 == 0
                                     for _ in range(200)), True)
milestones.active_buffs = real_active_buffs
check("old ranking gets Shards second",
      dungeon.auto_pick_order({"dungeon_auto_pick_order": ["gold", "gems", "gold_gems", "unmarked", "unique"]}),
      ["gold", "shards", "gems", "gold_gems", "unmarked", "unique"])

print("\nthe treasure")
random.seed(8)
tally = {0: 0, 1: 0, 2: 0}
for _ in range(20000):
    tally[shop.roll_loot_quality(shop.get_collectible("loot_bag"))] += 1
approx("dungeon items Fine ~25%", tally[1] / 200, 24, 26)
approx("dungeon items Superior ~12.5%", tally[2] / 200, 11.5, 13.5)
d = fresh(bands=1)
d["dungeon"] = dungeon._new_dungeon()
d["dungeon"]["picked"] = [{"took": {"kind": "shards", "shards": 3}},
                          {"took": {"kind": "unique", "item": "loot_bag"}}]
d["dungeon"]["treasure"] = {"claimed": False, "item_quality": 2}
paid = review_rewards.claim_dungeon_treasure(d)
check("Shards paid", (paid["shards"], d["shards"]), (3, 3))
check("item kept at its revealed quality", shop.item_quality(d, "loot_bag"), 2)
check("and recorded for the idle window", (d["last_dungeon"]["shards"], d["last_dungeon"]["item_quality"]), (3, 2))

print("\nthe Shard buff")
milestones.active_buffs = lambda data, col=None: []
random.seed(10)
milestones.buff_drop_percent = lambda data: 100
for label, bands in (("never before refinement", 0), ("rolled after", 1)):
    got = set()
    for _ in range(3000):
        d = fresh(bands=bands)
        b = milestones.roll_buff(d)
        if b:
            got.add(b["id"])
    check(f"Double shard rewards {label}", milestones.BUFF_SHARDS_DOUBLE in got, bool(bands))
milestones.active_buffs, milestones.buff_drop_percent = real_active_buffs, real_drop_percent

print("\nprestige empties it")
tmp = tempfile.mkdtemp()
storage.set_profile_folder(tmp)
d = fresh(bands=1, owned=["stone"])
d["shards"] = 9
shop.set_item_quality(d, "stone", 2)
d["total_xp"] = 10**7
storage.save(d)
prestige.perform_prestige(None, force=True)
after = storage.load()
check("Shards and quality reset, refinement kept",
      (after["shards"], after["item_quality"], prestige.refinement_bands(after)), (0, {}, 1))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(FAILS))
    sys.exit(1)
print("all item quality checks passed")
