"""
Drive the dungeon loop end to end with a stubbed aqt and check the measured rates against the
design. Exit 1 = something is off.

    python3 tests/check_dungeon.py
"""
import concurrent.futures
import contextlib
import importlib
import io
import pathlib
import random
import sys
import traceback
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

dungeon = importlib.import_module("cq.src.dungeon")
shop = importlib.import_module("cq.src.shop")
review_rewards = importlib.import_module("cq.src.review_rewards")
storage = importlib.import_module("cq.src.storage")

FAILS = []
_real_random = random.random
_real_roll = dungeon._roll_one_in


def check(label, got, want, tol=0.0):
    ok = abs(got - want) <= tol if isinstance(want, (int, float)) and tol else got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got}" + (f" (want {want})" if not ok else ""))
    if not ok:
        FAILS.append(label)


def approx(label, got, lo, hi):
    ok = lo <= got <= hi
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got:.4g}" + ("" if ok else f" (want {lo}-{hi})"))
    if not ok:
        FAILS.append(label)


def fresh(level_xp=100000, owned=None):
    d = storage._default_state()
    d["total_xp"] = level_xp
    d["owned_collectibles"] = list(owned or [])
    return d


def _collection_accounting():
    print("collection accounting")
    allc = shop.COLLECTIBLES
    check("total collectibles", len(allc), 78)
    check("purchasable", len(shop.collectibles_for_gold()), 53)
    check("gem-only", len(shop.gem_only_collectibles()), 17)
    check("dungeon loot", len(shop.loot_collectibles()), 8)
    check("three routes partition the table",
          len(shop.collectibles_for_gold()) + len(shop.gem_only_collectibles())
          + len(shop.loot_collectibles()), 78)
    check("loot weight total", sum(int(c["weight"]) for c in shop.loot_collectibles()), 33)
    check("shop-supplied set", len(shop.shop_supplied_collectibles()), 70)
    # The endgame trade must open on the shop's 68, never wait for loot nobody collects in a run.
    d = fresh(owned=[c["id"] for c in shop.shop_supplied_collectibles()])
    check("trade opens without loot", shop.all_collectibles_owned(d), True)
    d = fresh(owned=[c["id"] for c in allc][:60])
    check("trade shut while shop items remain", shop.all_collectibles_owned(d), False)
    # Loot must reach neither shop pool, which is what the two route fields already guarantee.
    loot_ids = {c["id"] for c in shop.loot_collectibles()}
    check("loot out of the gold pool",
          loot_ids & {c["id"] for c in shop.collectibles_for_gold_at_level(999)}, set())
    check("loot out of the craft pool",
          loot_ids & {c["id"] for c in shop.collectibles_for_gems_at_level(999)}, set())
    # Every dungeon stat must unlock at 15 or later, or it is sold as a stat that does nothing yet.
    early = [c["id"] for c in allc
             if (c["effect"].get("dungeon_discover_percent") or c["effect"].get("dungeon_explore_percent"))
             and c["unlock_at_level"] < dungeon.UNLOCK_LEVEL]
    check("no dungeon stat sold before level 15", early, [])
    check("discovery points in the game", shop.dungeon_discover_percent([c["id"] for c in allc]), 100)
    check("exploration points in the game", shop.dungeon_explore_percent([c["id"] for c in allc]), 61)


def _rates_measured_over_400k_reviews():
    print("\nrates, measured over 400k reviews")
    random.seed(4)
    N = 400_000
    d = fresh()
    hits = sum(1 for _ in range(N) if dungeon._roll_one_in(dungeon.ENTRANCE_ONE_IN, 3))
    approx("entrance on Good ~ 1/400", N / max(1, hits), 380, 420)
    hits = sum(1 for _ in range(N) if dungeon._roll_one_in(dungeon.ENTRANCE_ONE_IN, 1))
    approx("entrance on Again ~ 1/2000", N / max(1, hits), 1850, 2200)
    hits = sum(1 for _ in range(N) if dungeon._roll_one_in(dungeon.BRANCHING_ONE_IN, 3, 100.0))
    approx("branching at +100% ~ 1/100", N / max(1, hits), 95, 106)


def _path_assembly_200k_branchings():
    print("\npath assembly, 200k branchings")
    random.seed(5)
    seen = {k: 0 for k in dungeon.PATH_WEIGHTS}
    M = 200_000
    for _ in range(M):
        for k in dungeon._draw_paths(random.choice((2, 3)), allow_unique=True):
            seen[k] += 1
    for k, want in (("gold", 65), ("gems", 65), ("gold_gems", 57), ("unmarked", 46), ("unique", 17)):
        approx(f"{k} appears on ~{want}%", seen[k] / M * 100, want - 1.5, want + 1.5)
    # Display order is fixed however the draw came out, so the row reads the same every time.
    random.seed(6)
    bad = [p for _ in range(2000)
           for p in [dungeon._draw_paths(3, True)]
           if p != [k for k in dungeon.PATH_ORDER if k in p]]
    check("paths always in display order", bad, [])
    check("unique excluded when unavailable",
          any("unique" in dungeon._draw_paths(3, allow_unique=False) for _ in range(3000)), False)


def _unmarked_outcomes_200k_draws():
    print("\nunmarked outcomes, 200k draws")
    random.seed(7)
    M = 200_000
    out = {}
    for _ in range(M):
        k = dungeon._weighted_choice(dungeon.UNMARKED_WEIGHTS)
        out[k] = out.get(k, 0) + 1
    for k, want in (("nothing", 33.3), ("gold", 19.0), ("gems", 19.0), ("gold_gems", 14.3), ("unique", 14.3)):
        approx(f"unmarked {k} ~{want}%", out[k] / M * 100, want - 1.0, want + 1.0)


def _a_full_dungeon_driven_through_apply_one_review():
    print("\na full dungeon, driven through apply_one_review")
    random.seed(11)
    d = fresh()
    d["level"] = 30
    events = {"entrance": 0, "branching": 0, "treasure": 0}
    for i in range(30_000):
        earned = review_rewards.apply_one_review(d, ease=3)
        for k in events:
            if earned.get(f"dungeon_{k}"):
                events[k] += 1
        p = dungeon.pending(d)
        if p:
            dungeon.choose_path(d, 0)          # a manual player always taking the leftmost path
        if dungeon.treasure_ready(d):
            review_rewards.claim_dungeon_treasure(d)
    check("entrances found", events["entrance"] > 8, True)
    check("branchings found", events["branching"] > 30, True)
    # The loop stops at a fixed review count, so the last dungeon is usually still open.
    open_at_end = 1 if dungeon.is_active(d) else 0
    check("every finished dungeon was claimed",
          dungeon.dungeons_claimed(d), events["entrance"] - open_at_end)
    check("auto-pick unlocked after 3", dungeon.has_auto_pick(d), True)
    check("at most one dungeon open", open_at_end <= 1, True)
    check("last_dungeon recorded", isinstance(d.get("last_dungeon"), dict), True)
    approx("reviews per dungeon near the designed 1772",
           30_000 / max(1, events["entrance"]), 1300, 2400)


def _the_treasure_has_to_be_found_not_handed_over_with_the_last_pathway():
    print("\nthe treasure has to be found, not handed over with the last pathway")
    # The whole point of the change: taking the final pathway must not open the treasure. It is found
    # by a later review's roll, behind the same floor every branching sits behind.
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["branchings_total"] = 1
    d["dungeon"]["branchings_done"] = 1
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 10}]}
    dungeon.choose_path(d, 0)
    check("the last pathway leaves the treasure closed", dungeon.treasure_ready(d), False)
    check("and the dungeon still open", dungeon.is_active(d), True)

    # The floor applies to it as it does to a branching.
    for i in range(dungeon.BRANCHING_FLOOR_REVIEWS - 1):
        dungeon.on_review(d, 3, 30)
    check("nothing found inside the floor", dungeon.treasure_ready(d), False)
    check("the counter ran", d["dungeon"]["reviews_since_branching"],
          dungeon.BRANCHING_FLOOR_REVIEWS - 1)

    random.seed(37)
    guard = 0
    while not dungeon.treasure_ready(d) and guard < 40_000:
        guard += 1
        dungeon.on_review(d, 3, 30)
    check("the treasure is reached by a later roll", dungeon.treasure_ready(d), True)
    approx("and takes about a branching's worth of reviews to find",
           guard + dungeon.BRANCHING_FLOOR_REVIEWS - 1, 60, 1600)

    # The last stretch costs roughly what a branching does. The wait is geometric, so 1200 samples
    # are needed to keep the standard error under six reviews and the band below meaningful.
    random.seed(41)
    lengths = []
    for _ in range(1200):
        d = fresh()
        d["dungeon"] = dungeon._new_dungeon()
        d["dungeon"]["branchings_total"] = 1
        d["dungeon"]["branchings_done"] = 1
        n = 0
        while not dungeon.treasure_ready(d) and n < 40_000:
            n += 1
            dungeon.on_review(d, 3, 30)
        lengths.append(n)
    # 49 reviews of floor, then a 1-in-200 roll that pity steepens from the 110th answer on:
    # an analytic mean of 217 (250 without pity).
    approx("mean reviews from the last pathway to the treasure",
           sum(lengths) / len(lengths), 195, 245)

    # The XP is paid by the review that finds it, through the same bonus stack as everything else.
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["branchings_total"] = 1
    d["dungeon"]["branchings_done"] = 1
    d["dungeon"]["reviews_since_branching"] = dungeon.BRANCHING_FLOOR_REVIEWS
    random.seed(43)
    before = d["total_xp"]
    paid = 0
    for _ in range(40_000):
        earned = review_rewards.apply_one_review(d, ease=3)
        if earned.get("dungeon_treasure"):
            paid = earned.get("dungeon_xp", 0)
            break
    check("the finding review reports the treasure", dungeon.treasure_ready(d), True)
    check("and pays its XP", paid >= dungeon.XP_TREASURE, True)


def _the_one_item_slot():
    print("\nthe one-item slot")
    random.seed(13)
    for trial in range(400):
        d = fresh()
        while not dungeon.is_active(d):
            dungeon.on_review(d, 3, 30)
        guard = 0
        while dungeon.is_active(d) and guard < 60_000:
            guard += 1
            dungeon.on_review(d, 3, 30)
            if dungeon.pending(d):
                # Take an item wherever one is offered, which is the way to stress the slot.
                paths = dungeon.pending(d)["paths"]
                idx = next((i for i, o in enumerate(paths) if o.get("item")), 0)
                dungeon.choose_path(d, idx)
            if dungeon.treasure_ready(d):
                items = [e["took"] for e in dungeon.picks(d) if e["took"].get("item")]
                if len(items) > 1:
                    FAILS.append("two items in one dungeon")
                review_rewards.claim_dungeon_treasure(d)
                break
    check("never more than one item per dungeon", "two items in one dungeon" in FAILS, False)


def _only_a_taken_unique_path_closes_the_offer():
    print("\nonly a taken Unique path closes the offer")
    random.seed(29)
    after_unmarked = after_unique = empty_unique = 0
    for trial in range(3000):
        d = fresh()
        d["dungeon"] = dungeon._new_dungeon()
        st = dungeon.get_state(d)
        st["branchings_total"] = 10
        for b in range(10):
            st["branchings_done"] = b + 1
            kinds = dungeon._draw_paths(
                random.choice(dungeon.PATHS_PER_BRANCHING),
                allow_unique=dungeon.unique_offer_available(d),
            )
            offers = [dungeon._build_offer(k, d, []) for k in kinds]
            st["pending"] = {"paths": offers}
            uq = [i for i, o in enumerate(offers) if o["kind"] == dungeon.PATH_UNIQUE]
            if uq and dungeon.unique_path_taken(d):
                FAILS.append("unique offered after a unique path was taken")
            if uq and dungeon.item_taken(d):
                after_unmarked += 1
            um = [i for i, o in enumerate(offers) if o["kind"] == dungeon.PATH_UNMARKED]
            idx = (um or uq or [0])[0]
            took = dungeon.choose_path(d, idx)
            if took["kind"] == dungeon.PATH_UNIQUE and not took.get("item"):
                empty_unique += 1
    check("unique never re-offered after a unique pick",
          "unique offered after a unique path was taken" in FAILS, False)
    check("but still offered after an unmarked pick spent the slot", after_unmarked > 0, True)
    check("and pays nothing when taken then", empty_unique > 0, True)
    check("the empty offer looks identical on the button",
          dungeon.offer_summary({"kind": dungeon.PATH_UNIQUE}),
          dungeon.offer_summary({"kind": dungeon.PATH_UNIQUE, "item": "mushroom"}))


def _the_pool_empties_cleanly():
    print("\nthe pool empties cleanly")
    d = fresh(owned=[c["id"] for c in shop.loot_collectibles()])
    check("item unavailable with every loot item owned", dungeon.item_available(d), False)
    check("and no unique offer either", dungeon.unique_offer_available(d), False)
    d["dungeon"] = dungeon._new_dungeon()
    random.seed(17)
    offered = any(
        o.get("kind") == "unique"
        for _ in range(4000)
        for o in [dungeon._build_offer(k, d, d["owned_collectibles"])
                  for k in dungeon._draw_paths(3, allow_unique=dungeon.unique_offer_available(d))]
    )
    check("unique never offered when the pool is empty", offered, False)
    random.seed(19)
    unmarked_items = sum(
        1 for _ in range(4000)
        if dungeon._build_offer("unmarked", d, d["owned_collectibles"]).get("item")
    )
    check("unmarked pays no item when the pool is empty", unmarked_items, 0)


def _auto_pick():
    print("\nauto-pick")
    d = fresh()
    d["dungeons_claimed"] = 3
    d["dungeon_auto_pick_enabled"] = True
    check("enabled once unlocked", dungeon.auto_pick_enabled(d), True)
    d["dungeons_claimed"] = 2
    check("locked below the gate", dungeon.auto_pick_enabled(d), False)
    d["dungeon_auto_pick_order"] = ["gems", "nonsense"]
    check("a damaged order is repaired", sorted(dungeon.auto_pick_order(d)),
          sorted(dungeon.DEFAULT_AUTO_PICK_ORDER))
    check("and keeps what it could read", dungeon.auto_pick_order(d)[0], "gems")
    # The ranking must pick by kind and never by amount: that gap is what keeps manual play worth it.
    d = fresh()
    d["dungeons_claimed"] = 5
    d["dungeon_auto_pick_enabled"] = True
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["pending"] = {"paths": [
        {"kind": "gold", "gold": 5000},
        {"kind": "gems", "gems": 1},
    ]}
    check("takes the ranked kind, not the bigger number",
          dungeon.choose_path(d, dungeon.auto_pick_index(d))["kind"], "gems")


def _auto_pick_runs_a_dungeon_with_nothing_pending():
    print("\nauto-pick runs a dungeon with nothing pending")
    random.seed(23)
    d = fresh()
    d["dungeons_claimed"] = 3
    d["dungeon_auto_pick_enabled"] = True
    claimed = 0
    for _ in range(20_000):
        review_rewards.apply_one_review(d, ease=3)
        if dungeon.pending(d):
            FAILS.append("auto-pick left a branching pending")
            break
        if dungeon.treasure_ready(d):
            review_rewards.claim_dungeon_treasure(d)
            claimed += 1
    check("nothing ever pends under auto-pick", "auto-pick left a branching pending" in FAILS, False)
    check("dungeons still complete", claimed > 3, True)


def _treasure_payout():
    print("\ntreasure payout")
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["picked"] = [
        {"took": {"kind": "gold", "gold": 40}, "auto": False},
        {"took": {"kind": "gems", "gems": 3, "most_needed": False}, "auto": False},
        {"took": {"kind": "unique", "item": "mushroom"}, "auto": False},
    ]
    # Reached, not just picked: claim_dungeon_treasure pays nothing without this, which is the point
    # of the guard - catch_up made it a second caller and an unreached treasure must not close a run.
    d["dungeon"]["treasure"] = {"claimed": False}
    before_gold, before_gems = d["money"], sum(d["gems"].values())
    paid = review_rewards.claim_dungeon_treasure(d)
    check("gold paid", d["money"] - before_gold, 40)
    check("gems paid", sum(d["gems"].values()) - before_gems, 3)
    check("item granted", "mushroom" in d["owned_collectibles"], True)
    check("dungeon closed", d.get("dungeon"), None)
    check("claim counted", d["dungeons_claimed"], 1)
    check("payout reported", (paid["gold"], paid["gems"], paid["item"]), (40, 3, "mushroom"))


def _the_doubling_buff_is_not_applied_twice():
    print("\nthe doubling buff is not applied twice")
    d = fresh()
    # A count already doubled at discovery, claimed while a doubling buff happens to be running.
    d["milestones"]["active_buffs"] = [
        {"id": "gems_double", "started": "2026-01-01", "started_epoch": 0, "days": 3}
    ]
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["picked"] = [{"took": {"kind": "gems", "gems": 4, "most_needed": False}, "auto": False}]
    d["dungeon"]["treasure"] = {"claimed": False}
    before = sum(d["gems"].values())
    review_rewards.claim_dungeon_treasure(d)
    check("gems paid once, not doubled again", sum(d["gems"].values()) - before, 4)


def _undo_keeps_what_was_found_and_charges_reviews_for_it():
    print("\nundo keeps what was found, and charges reviews for it")
    random.seed(29)
    d = fresh()
    d["level"] = 30
    # Nothing about the dungeon may ride in the undo entry any more: the revert must have nothing to
    # put back. A stray key here is how the wholesale snapshot would creep back in.
    carried = False
    for _ in range(4000):
        earned = review_rewards.apply_one_review(d, ease=1)   # Again: still advances the counters
        if any("dungeon" in k for k in earned["undo_deltas"]):
            carried = True
            break
        if dungeon.pending(d):
            dungeon.choose_path(d, 0)
    check("no dungeon state in the undo entry", carried, False)

    # The XP a discovery paid must not be in xp_delta either, or the revert would take back the XP for
    # a dungeon the player still has.
    random.seed(31)
    d = fresh()
    d["level"] = 30
    xp_leaked = False
    for _ in range(30_000):
        before_xp = d["total_xp"]
        earned = review_rewards.apply_one_review(d, ease=3)
        if not (earned.get("dungeon_branching") or earned.get("dungeon_treasure")):
            if dungeon.pending(d):
                dungeon.choose_path(d, 0)
            continue
        paid = earned.get("dungeon_xp", 0)
        # What undo would subtract, against what the answer actually added.
        if paid and d["total_xp"] - earned["undo_deltas"]["xp_delta"] < before_xp:
            xp_leaked = True
        break
    check("dungeon XP is not in the undo delta", xp_leaked, False)

    # The debt: one review owed per undo, and while it is owed nothing rolls and nothing advances.
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["reviews_since_branching"] = 60          # already past the floor
    d["dungeon"]["branchings_total"] = 5
    for _ in range(3):
        dungeon.note_undone_review(d)
    check("three undos owe three reviews", dungeon.undo_block(d), 3)
    frozen = True
    for _ in range(3):
        found = dungeon.on_review(d, 3, 30)
        if any(found[k] for k in ("entrance", "branching", "treasure")) or found["xp"]:
            frozen = False
    check("a blocked review finds nothing", frozen, True)
    check("a blocked review advances no counter", d["dungeon"]["reviews_since_branching"], 60)
    check("the debt is paid off", dungeon.undo_block(d), 0)
    # An entrance cannot be found while the debt stands either.
    d = fresh()
    dungeon.note_undone_review(d)
    dungeon.on_review(d, 3, 30)
    check("no entrance while blocked", dungeon.is_active(d), False)

    # Again must advance the counters even though it does not count toward reviews_today.
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    dungeon.on_review(d, 1, 30)
    check("Again advances the dungeon counter", d["dungeon"]["reviews_since_entrance"], 1)


def _the_pity_bonus():
    print("\nthe pity bonus")
    check("nothing below the floor", dungeon.pity_percent(99), 0)
    check("nothing at the floor itself", dungeon.pity_percent(100), 0)
    check("2% on the 110th answer", dungeon.pity_percent(110), 2)
    check("still 2% on the 119th", dungeon.pity_percent(119), 2)
    check("4% on the 120th", dungeon.pity_percent(120), 4)

    # Only above the gate: climbing to 15 must not arrive with a bonus already banked.
    d = fresh()
    random.random = lambda: 1.0
    for _ in range(60):
        dungeon.on_review(d, 3, dungeon.UNLOCK_LEVEL - 1)
    check("no search counted below level 15", dungeon.search_reviews(d), 0)
    for _ in range(115):
        dungeon.on_review(d, 3, dungeon.UNLOCK_LEVEL)
    check("115 answers counted at the gate", dungeon.search_reviews(d), 115)
    check("and worth 2%", dungeon.discover_pity_percent(d), 2)

    # The bonus has to reach the roll, added to whatever the collection already gives.
    seen = {}
    real_roll = dungeon._roll_one_in
    dungeon._roll_one_in = lambda one_in, ease, bonus_percent=0.0: seen.update(b=bonus_percent) or False
    d = fresh()
    d["owned_collectibles"] = ["winged_shoes"]          # +38% discovery
    d[dungeon.KEY_SEARCH_REVIEWS] = 199
    dungeon.on_review(d, 3, 30)
    check("items and pity both reach the entrance roll", seen["b"], 58.0)   # 38 + 20

    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["reviews_since_branching"] = 129
    dungeon.on_review(d, 3, 30)
    check("and the branching roll", seen["b"], 6.0)
    dungeon._roll_one_in = real_roll

    # A discovery clears it, on both sides.
    random.random = lambda: 0.0
    d = fresh()
    d[dungeon.KEY_SEARCH_REVIEWS] = 500
    dungeon.on_review(d, 3, 30)
    check("an entrance resets the search count", dungeon.search_reviews(d), 0)
    d["dungeon"]["reviews_since_branching"] = 300
    dungeon.on_review(d, 3, 30)
    check("a branching resets the exploration pity", dungeon.explore_pity_percent(d), 0)

    # Frozen while a dungeon is open, which is what makes the idle window's "since completing the last
    # dungeon" figure true: the search counter must measure searching, not the dungeon it found.
    random.random = lambda: 1.0
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d[dungeon.KEY_SEARCH_REVIEWS] = 7
    for _ in range(200):
        dungeon.on_review(d, 3, 30)
    check("the search count is frozen inside a dungeon", dungeon.search_reviews(d), 7)
    random.random = _real_random

    # The number on the item and the number in its sentence, which are edited by hand and separately.
    mismatched = []
    for c in shop.COLLECTIBLES:
        for key, phrase in (("dungeon_discover_percent", "chance to find a dungeon"),
                            ("dungeon_explore_percent", "faster dungeon exploration")):
            if key in c["effect"] and f"+{c['effect'][key]}% {phrase}" not in c["effect_description"]:
                mismatched.append(c["id"])
    check("every dungeon stat is described by its own number", mismatched, [])


def _banked_reviews_while_the_dungeon_is_blocked():
    print("\nbanked reviews while the dungeon is blocked")
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["reviews_since_branching"] = 60
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 10}]}
    random.random = lambda: 1.0
    for i in range(100):
        dungeon.on_review(d, 1 if i % 5 == 0 else 3, 60)      # every fifth answer an Again
    random.random = _real_random
    check("100 blocked reviews banked", dungeon.banked_reviews(d), 100)
    check("and the Agains counted", dungeon.banked_agains(d), 20)
    check("the counter kept climbing too", d["dungeon"]["reviews_since_branching"], 160)

    # Nothing is banked while the dungeon is unblocked - those reviews roll for themselves.
    d2 = fresh()
    d2["dungeon"] = dungeon._new_dungeon()
    random.random = lambda: 1.0
    for _ in range(30):
        dungeon.on_review(d2, 3, 60)
    random.random = _real_random
    check("an unblocked review is not banked", dungeon.banked_reviews(d2), 0)

    # Nor while an undo is owed: that review makes no progress at all, banked or otherwise.
    d3 = fresh()
    d3["dungeon"] = dungeon._new_dungeon()
    d3["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 10}]}
    dungeon.note_undone_review(d3)
    dungeon.on_review(d3, 3, 60)
    check("a review owed to an undo is not banked", dungeon.banked_reviews(d3), 0)


def _the_agains_are_spread_rather_than_bunched():
    print("\nthe Agains are spread rather than bunched")
    for count, agains in ((100, 20), (10, 8), (10, 10), (7, 0), (5, 5)):
        seq = list(dungeon._replay_eases(count, agains))
        ok = len(seq) == count and sum(1 for e in seq if e == 1) == agains
        print(f"  {'ok  ' if ok else 'FAIL'} {count} reviews, {agains} Again -> {len(seq)} grades,"
              f" {sum(1 for e in seq if e == 1)} of them Again")
        if not ok:
            FAILS.append(f"replay eases wrong for {count}/{agains}")
    seq = list(dungeon._replay_eases(100, 20))
    gaps = [j - i for i, j in zip([k for k, e in enumerate(seq) if e == 1],
                                  [k for k, e in enumerate(seq) if e == 1][1:])]
    check("evenly, so every gap is the same", len(set(gaps)), 1)


def _catch_up_replays_the_bank_and_stops_at_the_next_block():
    print("\ncatch-up replays the bank and stops at the next block")
    random.seed(5)
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["branchings_total"] = 6
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 10}]}
    for _ in range(600):
        dungeon.on_review(d, 3, 60)
    banked_before = dungeon.banked_reviews(d)
    counter_before = d["dungeon"]["reviews_since_branching"]
    dungeon.choose_path(d, 0)
    found = dungeon.catch_up(d, 60)
    check("the bank was 600", banked_before, 600)
    # The rewind is what keeps the replay honest: the counter went back by the bank and then forward
    # again as the replay advanced it, so it never counts a review twice.
    spent = banked_before - dungeon.banked_reviews(d)
    check("it found something", len(found) > 0, True)
    check("and stopped on a new block", bool(dungeon.pending(d) or dungeon.treasure_ready(d)), True)
    check("with the rest still banked", dungeon.banked_reviews(d) == banked_before - spent, True)
    check("no review counted twice",
          d["dungeon"]["reviews_since_branching"] <= counter_before, True)

    # An empty bank is a no-op, and catch-up on an unblocked dungeon changes nothing.
    d4 = fresh()
    d4["dungeon"] = dungeon._new_dungeon()
    check("an empty bank finds nothing", dungeon.catch_up(d4, 60), [])


def _spreading_the_agains_matches_answering_them_in_a_random_order():
    print("\nspreading the Agains matches answering them in a random order")
    def _replay_hits(seq, trials=4000):
        hits = 0
        for _ in range(trials):
            n = 0
            for e in seq:
                n += 1
                if n < dungeon.BRANCHING_FLOOR_REVIEWS:
                    continue
                c = (1.0 / dungeon.BRANCHING_ONE_IN) * (1 + dungeon.pity_percent(n) / 100.0)
                if e == 1:
                    c *= dungeon.AGAIN_ROLL_RATIO
                if _real_random() < c:
                    hits += 1
                    n = 0
        return hits / trials

    random.seed(17)
    shuffled = [1] * 100 + [3] * 400
    random.shuffle(shuffled)
    even = list(dungeon._replay_eases(500, 100))
    a, b = _replay_hits(shuffled), _replay_hits(even)
    ok = abs(a - b) < 0.12                      # ~4000 trials of a mean near 1.8: noise is ~0.02
    print(f"  {'ok  ' if ok else 'FAIL'} discoveries per bank: shuffled {a:.3f} vs spread {b:.3f}")
    if not ok:
        FAILS.append(f"spreading the Agains diverges: {a:.3f} vs {b:.3f}")


def _catch_up_pays_its_xp_through_the_bonus_stack():
    print("\ncatch-up pays its XP through the bonus stack")
    random.seed(5)
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["branchings_total"] = 6
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 10}]}
    for _ in range(600):
        dungeon.on_review(d, 3, 60)
    dungeon.choose_path(d, 0)
    xp_before = d["total_xp"]
    out = review_rewards.apply_dungeon_catch_up(d)
    check("XP was paid for what it found", out["xp"] > 0 and d["total_xp"] > xp_before, True)
    check("and the bank is drained or re-banked",
          dungeon.banked_reviews(d) < 600, True)

    # A treasure that was never reached must not be claimable.
    d5 = fresh()
    d5["dungeon"] = dungeon._new_dungeon()
    d5["dungeon"]["picked"] = [{"took": {"kind": "gold", "gold": 40}, "auto": False}]
    money_before = d5["money"]
    paid = review_rewards.claim_dungeon_treasure(d5)
    check("claiming an unreached treasure pays nothing", (paid["gold"], d5["money"]), (0, money_before))
    check("and leaves the dungeon open", dungeon.is_active(d5), True)


def _the_counters_survive_a_catch_up_that_only_drains_part_of_the_bank():
    print("\nthe counters survive a catch-up that only drains part of the bank")
    random.seed(4)
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["branchings_total"] = 6
    d["dungeon"]["reviews_since_branching"] = 60
    d["dungeon"]["reviews_since_entrance"] = 60
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 44}]}
    for _ in range(500):
        dungeon.on_review(d, 3, 60)
    check("banking advanced the entrance counter", d["dungeon"]["reviews_since_entrance"], 560)
    rounds = 0
    while (dungeon.banked_reviews(d) or dungeon.pending(d)) and rounds < 25:
        if dungeon.pending(d):
            dungeon.choose_path(d, 0)
        elif dungeon.treasure_ready(d):
            break
        dungeon.catch_up(d, 60)
        rounds += 1
    # Every one of the 500 elapsed, however many chained catch-ups it took to replay them: the shift
    # off the counters has to be put back for whatever a catch-up re-banks.
    check("and every replayed review is still counted",
          d["dungeon"]["reviews_since_entrance"] + dungeon.banked_reviews(d), 560)

    # Called while still blocked it must change nothing at all - the shift would otherwise come off
    # the counters with nothing replayed to put it back.
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["reviews_since_branching"] = 300
    d["dungeon"]["reviews_since_entrance"] = 300
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 44}]}
    d[dungeon.KEY_BANKED_REVIEWS] = 200
    check("a blocked catch-up finds nothing", dungeon.catch_up(d, 60), [])
    check("keeps the bank", dungeon.banked_reviews(d), 200)
    check("and leaves the counters alone",
          (d["dungeon"]["reviews_since_entrance"], d["dungeon"]["reviews_since_branching"]), (300, 300))


def _the_catch_up_grant_is_temporary_and_never_leaks():
    print("\nthe catch-up grant is temporary and never leaks")
    d = fresh()                                   # auto-pick locked: 0 dungeons claimed
    check("locked, so the setting is off", dungeon.auto_pick_enabled(d), False)
    d[dungeon.KEY_CATCH_UP_AUTO] = True
    check("the grant turns it on anyway", dungeon.auto_pick_enabled(d), True)

    # It expires with the backlog it was given for, and takes the one-shot question with it.
    d["dungeon"] = dungeon._new_dungeon()
    d[dungeon.KEY_BANKED_REVIEWS] = 3
    d[dungeon.KEY_BANKED_AGAINS] = 0
    d[dungeon.KEY_CATCH_UP_ASKED] = True
    dungeon.catch_up(d, 60)
    check("bank drained", dungeon.banked_reviews(d), 0)
    check("grant expired with it", dungeon.KEY_CATCH_UP_AUTO in d, False)
    check("and so did the one-shot", dungeon.KEY_CATCH_UP_ASKED in d, False)
    check("back to the real setting", dungeon.auto_pick_enabled(d), False)

    # A bank that stops on a treasure keeps the grant, or the branchings after the claim would ask.
    d = fresh()
    d[dungeon.KEY_CATCH_UP_AUTO] = True
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["treasure"] = {"claimed": False}
    d[dungeon.KEY_BANKED_REVIEWS] = 200
    dungeon.catch_up(d, 60)
    check("a blocked catch-up keeps the grant", d.get(dungeon.KEY_CATCH_UP_AUTO), True)


def _the_prompt_s_offer_resolves_the_branchings_but_never_the_treasures():
    print("\nthe prompt's offer resolves the branchings but never the treasures")
    random.seed(3)
    d = fresh()                                   # still locked
    d["dungeon"] = dungeon._new_dungeon()
    d["dungeon"]["pending"] = {"paths": [{"kind": "gold", "gold": 44}]}
    for i in range(4500):
        dungeon.on_review(d, 1 if i % 5 == 0 else 3, 60)
    banked = dungeon.banked_reviews(d)
    setting_before = d.get(dungeon.KEY_AUTO_ENABLED)
    out = review_rewards.resolve_dungeon_backlog(d)
    check("the waiting branching was taken", dungeon.pending(d), None)
    check("it stopped on a treasure for the player to claim", dungeon.treasure_ready(d), True)
    check("and spent part of the backlog", dungeon.banked_reviews(d) < banked, True)
    check("recorded as auto-picked", all(e.get("auto") for e in dungeon.picks(d)), True)
    # The prompt promises "One-time action only - your auto-pick setting will stay untouched", so the
    # grant must never write the setting. Compared by value: the key is in _default_state either way.
    check("and the setting itself is untouched", d.get(dungeon.KEY_AUTO_ENABLED), setting_before)


def _the_threshold():
    print("\nthe threshold")
    check("5000, about eighteen manual clicks", dungeon.CATCH_UP_PROMPT_MIN_BANK, 5000)


def _prestige():
    print("\nprestige")
    d = fresh()
    d["dungeon"] = dungeon._new_dungeon()
    d["last_dungeon"] = {"branchings": 3}
    d["dungeons_claimed"] = 7
    d["dungeon_auto_pick_enabled"] = True
    new = storage.carry_prestige_keys(d, storage._default_state())
    check("an open dungeon is abandoned", new.get("dungeon"), None)
    check("the last dungeon is forgotten", new.get("last_dungeon"), None)
    check("the claim counter survives", new["dungeons_claimed"], 7)
    check("the auto-pick setting survives", new["dungeon_auto_pick_enabled"], True)


SECTIONS = [
    _collection_accounting,
    _rates_measured_over_400k_reviews,
    _path_assembly_200k_branchings,
    _unmarked_outcomes_200k_draws,
    _a_full_dungeon_driven_through_apply_one_review,
    _the_treasure_has_to_be_found_not_handed_over_with_the_last_pathway,
    _the_one_item_slot,
    _only_a_taken_unique_path_closes_the_offer,
    _the_pool_empties_cleanly,
    _auto_pick,
    _auto_pick_runs_a_dungeon_with_nothing_pending,
    _treasure_payout,
    _the_doubling_buff_is_not_applied_twice,
    _undo_keeps_what_was_found_and_charges_reviews_for_it,
    _the_pity_bonus,
    _banked_reviews_while_the_dungeon_is_blocked,
    _the_agains_are_spread_rather_than_bunched,
    _catch_up_replays_the_bank_and_stops_at_the_next_block,
    _spreading_the_agains_matches_answering_them_in_a_random_order,
    _catch_up_pays_its_xp_through_the_bonus_stack,
    _the_counters_survive_a_catch_up_that_only_drains_part_of_the_bank,
    _the_catch_up_grant_is_temporary_and_never_leaks,
    _the_prompt_s_offer_resolves_the_branchings_but_never_the_treasures,
    _the_threshold,
    _prestige,
]


def _run(section):
    """One section in a worker: its output and failures. Seeded first, so a section that rolls
    without seeding is still deterministic now it no longer inherits the previous one's state."""
    random.seed(0)
    FAILS.clear()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            section()
        except Exception:
            # Reported as a failure, so the other sections still print their results.
            print(traceback.format_exc(), end="")
            FAILS.append(f"{section.__name__} raised")
        finally:
            # A section that raised mid-patch must not leave the patch to the next one in this worker.
            random.random, dungeon._roll_one_in = _real_random, _real_roll
    return out.getvalue(), list(FAILS)


if __name__ == "__main__":
    # Sections are independent, so they run in parallel and print in order.
    with concurrent.futures.ProcessPoolExecutor() as pool:
        results = list(pool.map(_run, SECTIONS))
    for out, fails in results:
        print(out, end="")
        FAILS += fails
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: " + ", ".join(dict.fromkeys(FAILS)))
        sys.exit(1)
    print("all dungeon checks passed")
