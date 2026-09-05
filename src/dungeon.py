"""
Dungeons: a track paced by review count alone, running underneath the day.

An entrance is discovered on a review, branching pathways are discovered on later reviews, and the
treasure is reached after 3 to 6 of them. This module owns the state and every roll; it pays
nothing. review_rewards drives it from apply_one_review and pays what it returns, which is what
keeps the payout rules in one place and this file free of the bonus stack.

Design: drafts/dungeons.md.
"""
from __future__ import annotations

import random
from typing import Any

from . import shop

# The level that opens entrance discovery, and nothing else: a dungeon already open runs to its
# treasure whatever happens to the level afterwards. That matters because undoing a review
# recomputes the level from total_xp, so a player who finds an entrance at exactly 15 can be 14 a
# moment later - and losing a dungeon to Ctrl+Z would be indefensible.
UNLOCK_LEVEL = 15

# Rolls are expressed as "one in N" per answered card. Again pays a fifth of the chance, the share
# it already pays of a review's XP; this is the first place that ratio scales a chance rather than
# a quantity, which is the right player-facing analogue.
ENTRANCE_ONE_IN = 400
BRANCHING_ONE_IN = 200
AGAIN_ROLL_RATIO = 0.2

# Pity: after this many answers with nothing found, a bonus accrues at PITY_PERCENT_PER_STEP per
# PITY_STEP_REVIEWS, so the 110th answer carries 2%. It scales whichever roll is live - discovery
# outside a dungeon, exploration inside - and the discovery it buys resets it.
PITY_FLOOR_REVIEWS = 100
PITY_STEP_REVIEWS = 10
PITY_PERCENT_PER_STEP = 2

# Reviews that must pass after a branching before the next one can roll. Flat, so it never scales
# with the exploration stat: a branching must not land one card after the last, and that reason
# does not weaken because the player has better gear. It is also the structural ceiling on the
# whole feature - no stacking pushes a dungeon below roughly 4.5 x 50 reviews plus the entrance.
BRANCHING_FLOOR_REVIEWS = 50

# Branchings to the treasure, rolled when the dungeon starts and never shown.
BRANCHINGS_MIN = 3
BRANCHINGS_MAX = 6

# Flat XP, before the bonus stack review_rewards applies. A whole dungeon pays about 250 base:
# two thirds of a level at 15, under a quarter of one at 50.
XP_BRANCHING = 40
XP_TREASURE = 70

# --- Paths -------------------------------------------------------------------------------------
PATH_GOLD = "gold"
PATH_GEMS = "gems"
PATH_GOLD_GEMS = "gold_gems"
PATH_UNMARKED = "unmarked"
PATH_UNIQUE = "unique"

# Display order, left to right, whichever subset a branching draws. Relative rather than slotted:
# two paths are two adjacent buttons, not two buttons with a hole between them.
PATH_ORDER = (PATH_GOLD, PATH_GEMS, PATH_GOLD_GEMS, PATH_UNMARKED, PATH_UNIQUE)

PATH_LABELS = {
    PATH_GOLD: "Gold",
    PATH_GEMS: "Gems",
    PATH_GOLD_GEMS: "Gold & gems",
    PATH_UNMARKED: "Unmarked path",
    PATH_UNIQUE: "Unique item",
}

PATH_ICONS = {
    PATH_GOLD: "currency/Coins x3.png",
    PATH_GEMS: "gems/3_unknown_gems.png",
    PATH_GOLD_GEMS: "currency/gold_and_gems.png",
    PATH_UNMARKED: "ui/unmarked_path.png",
    PATH_UNIQUE: "ui/unknown_item.png",
}

# A branching offers two or three paths, 50:50, drawn without replacement by weight. The
# appearance rates are not the weights over 18 - each draw renormalizes over what is left - so
# Unique shows on about 17% of branchings rather than 6%.
PATH_WEIGHTS = {
    PATH_GOLD: 5,
    PATH_GEMS: 5,
    PATH_GOLD_GEMS: 4,
    PATH_UNMARKED: 3,
    PATH_UNIQUE: 1,
}

# What an Unmarked path turns out to hold. Averages about 15% more than a named path while the
# item slot is open and about half of one after it is spent, which makes it the only path whose
# value depends on where in the dungeon you are.
UNMARKED_NOTHING = "nothing"
UNMARKED_WEIGHTS = {
    UNMARKED_NOTHING: 7,
    PATH_GOLD: 4,
    PATH_GEMS: 4,
    PATH_GOLD_GEMS: 3,
    PATH_UNIQUE: 3,
}

# Base payouts, before the player's bonus stats. Priced against each other at the game's own rate
# of 1 gem = GEM_COST_RANDOM gold, the three currency paths form a short ladder rather than sitting
# level: 35, 40.5 and 45 gold-equivalent. Gold is the plainest and pays least, the mixed path asks
# the player to want both currencies and pays most, and the spread from end to end is under 1.3:1 -
# wide enough to be a preference, narrow enough that no path is ever simply the wrong answer.
#
# The distributions differ as much as the means do, which is what keeps a fixed priority order
# worth less than choosing by hand: the best of three rolls beats any single kind by about a sixth.
GOLD_MIN, GOLD_MAX = 25, 45
GEMS_PCT_MIN, GEMS_PCT_MAX = 110, 160
COMBO_GOLD_MIN, COMBO_GOLD_MAX = 15, 30
COMBO_GEMS_PCT_MIN, COMBO_GEMS_PCT_MAX = 50, 100

# --- Auto-pick ---------------------------------------------------------------------------------
# Claimed dungeons before the setting unlocks. The counter survives a prestige (storage's
# preserved keys): a run holds fewer than three dungeons, so a counter reset by prestige would push
# the gate away every time the player did the thing the game most rewards.
AUTO_PICK_UNLOCK_DUNGEONS = 3

# The order an informed player would set: a guaranteed item is worth several currency paths, and
# Unmarked is the best of the rest while the slot is open. The three currency paths are levelled at
# parity, so their ranking carries no strategy - it is only which currency the player would rather
# bank, which is what the setting is for.
DEFAULT_AUTO_PICK_ORDER = [PATH_UNIQUE, PATH_UNMARKED, PATH_GOLD_GEMS, PATH_GEMS, PATH_GOLD]

# Two counters, because they answer different questions and have different lifetimes. The lifetime
# one gates auto-pick and so is carried through a prestige; the per-run one is not carried, so it
# resets with everything else and says what this run has managed.
KEY_CLAIMED = "dungeons_claimed"
KEY_CLAIMED_RUN = "dungeons_claimed_run"
KEY_AUTO_ENABLED = "dungeon_auto_pick_enabled"
KEY_AUTO_ORDER = "dungeon_auto_pick_order"

# --- Undo --------------------------------------------------------------------------------------
# Reviews the dungeon must sit out, one for every undone review. Nothing found is ever taken back
# by Ctrl+Z (see hooks._revert_last_review_rewards), which on its own would make undo a free reroll
# of a roll that missed: answer, undo, answer again, forever. Charging a review of frozen progress
# per undo makes the retry cost exactly what it was trying to save, without the dungeon needing to
# know which review it is looking at or that an undo ever happened.
KEY_UNDO_BLOCK = "dungeon_undo_block"

# Answers spent looking for an entrance: the pity counter for the half of the cycle spent outside a
# dungeon, and the figure the idle window reports. Inside one, reviews_since_branching already
# counts answers since the last thing found, so the pity there needs no state of its own.
KEY_SEARCH_REVIEWS = "dungeon_search_reviews"


# --- State -------------------------------------------------------------------------------------

def get_state(data: dict[str, Any]) -> dict[str, Any] | None:
    """The open dungeon, or None. Absence means no dungeon, which is also a fresh save's state."""
    state = data.get("dungeon")
    return state if isinstance(state, dict) and state.get("active") else None


def is_active(data: dict[str, Any]) -> bool:
    return get_state(data) is not None


def pity_percent(reviews: int) -> int:
    """The pity bonus earned by `reviews` answers with nothing found. Zero below the floor."""
    if reviews < PITY_FLOOR_REVIEWS:
        return 0
    return PITY_PERCENT_PER_STEP * ((reviews - PITY_FLOOR_REVIEWS) // PITY_STEP_REVIEWS)


def search_reviews(data: dict[str, Any]) -> int:
    """Answers spent looking for an entrance. Only counted while the roll is live: see on_review."""
    return max(0, int(data.get(KEY_SEARCH_REVIEWS, 0) or 0))


def discover_pity_percent(data: dict[str, Any]) -> int:
    """The pity bonus currently added to the entrance roll."""
    return pity_percent(search_reviews(data))


def explore_pity_percent(data: dict[str, Any]) -> int:
    """The pity bonus currently added to the branching roll. Zero outside a dungeon."""
    state = get_state(data)
    return pity_percent(int(state.get("reviews_since_branching", 0))) if state else 0


def undo_block(data: dict[str, Any]) -> int:
    """Reviews still owed before the dungeon rolls again."""
    return max(0, int(data.get(KEY_UNDO_BLOCK, 0) or 0))


def note_undone_review(data: dict[str, Any]) -> None:
    """Charge one review of frozen progress. Mutates data; caller saves."""
    data[KEY_UNDO_BLOCK] = undo_block(data) + 1


def dungeons_claimed(data: dict[str, Any]) -> int:
    """Treasures claimed across every run on this profile. Survives a prestige."""
    return int(data.get(KEY_CLAIMED, 0) or 0)


def dungeons_claimed_run(data: dict[str, Any]) -> int:
    """Treasures claimed in the current run. Reset by a prestige, like the rest of the run."""
    return int(data.get(KEY_CLAIMED_RUN, 0) or 0)


def has_auto_pick(data: dict[str, Any]) -> bool:
    """Whether the setting is unlocked. Derived, never stored - one field, one truth."""
    return dungeons_claimed(data) >= AUTO_PICK_UNLOCK_DUNGEONS


def auto_pick_enabled(data: dict[str, Any]) -> bool:
    return has_auto_pick(data) and bool(data.get(KEY_AUTO_ENABLED, False))


def auto_pick_order(data: dict[str, Any]) -> list[str]:
    """The player's ranking, repaired against the known paths so a stale save cannot drop one."""
    stored = data.get(KEY_AUTO_ORDER)
    order = [p for p in stored if p in PATH_WEIGHTS] if isinstance(stored, list) else []
    order += [p for p in DEFAULT_AUTO_PICK_ORDER if p not in order]
    return order


def pending(data: dict[str, Any]) -> dict[str, Any] | None:
    """The unanswered branching, or None. While one is pending nothing else rolls."""
    state = get_state(data)
    if not state:
        return None
    p = state.get("pending")
    return p if isinstance(p, dict) and p.get("paths") else None


def treasure_ready(data: dict[str, Any]) -> bool:
    """True when the treasure has been reached and not yet claimed."""
    state = get_state(data)
    return bool(state and isinstance(state.get("treasure"), dict))


def picks(data: dict[str, Any]) -> list[dict[str, Any]]:
    state = get_state(data)
    return list(state.get("picked") or []) if state else []


def item_taken(data: dict[str, Any]) -> bool:
    """
    Whether this dungeon has already paid its one item. Derived from the picks rather than stored:
    a separate flag is a thing that can disagree with the picks beside it.
    """
    for entry in picks(data):
        if (entry.get("took") or {}).get("item"):
            return True
    return False


def _loot_pool(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Loot items the player does not already own."""
    owned = set(data.get("owned_collectibles", []))
    return [c for c in shop.loot_collectibles() if c["id"] not in owned]


def item_available(data: dict[str, Any]) -> bool:
    """
    Whether an item can still be paid: the slot is unspent and something is left to pay from.

    One condition, two ways to reach it. The empty pool is a corner in normal play - nobody
    collects eight loot items inside a run - but the admin "unlock all collectibles" action reaches
    it on the first click, so it is the branch a tester hits first.
    """
    return not item_taken(data) and bool(_loot_pool(data))


# --- Rolls -------------------------------------------------------------------------------------

def _roll_one_in(one_in: int, ease: int, bonus_percent: float = 0.0) -> bool:
    """
    One chance in `one_in`, scaled by a collection bonus and cut to a fifth for Again.

    Both factors are multiplicative, so their order does not matter. The bonus is applied the way
    gem luck already is - summed across owned items, then base * (1 + pct/100) once.
    """
    if one_in <= 0:
        return False
    chance = (1.0 / one_in) * (1.0 + max(0.0, bonus_percent) / 100.0)
    if ease == 1:
        chance *= AGAIN_ROLL_RATIO
    return random.random() < chance


def _weighted_choice(weights: dict[str, int]) -> str:
    """One key, drawn by weight. Returns the last key if the weights are somehow all zero."""
    total = sum(max(0, w) for w in weights.values())
    if total <= 0:
        return list(weights)[-1]
    roll = random.random() * total
    running = 0.0
    for key, weight in weights.items():
        running += max(0, weight)
        if roll < running:
            return key
    return list(weights)[-1]


def _draw_paths(count: int, allow_unique: bool) -> list[str]:
    """`count` distinct paths, weighted, without replacement, returned in display order."""
    remaining = {
        k: v for k, v in PATH_WEIGHTS.items()
        if allow_unique or k != PATH_UNIQUE
    }
    chosen: list[str] = []
    for _ in range(min(count, len(remaining))):
        pick = _weighted_choice(remaining)
        chosen.append(pick)
        del remaining[pick]
    return [p for p in PATH_ORDER if p in chosen]


# --- Building an offer -------------------------------------------------------------------------

def _roll_gold(low: int, high: int, data: dict[str, Any], owned: list) -> int:
    """A gold amount, scaled by the same bonus stack quest gold uses. Whole gold, floored at 1."""
    from . import review_rewards

    base = random.uniform(low, high)
    return max(1, int(round(review_rewards.dungeon_gold_exact(data, base, owned))))


def _roll_gems(low_pct: int, high_pct: int, data: dict[str, Any], owned: list) -> int:
    """
    A gem count, from a chance scaled by gem luck.

    The percentage is the design-time figure and the player only ever sees the count: a chance is
    the only form gem luck can scale, and roll_gem_count pays anything above 100% as whole gems
    rather than clamping it, so the expected count stays base * multiplier at any collection size.
    """
    from . import review_rewards

    base = random.uniform(low_pct, high_pct)
    return review_rewards.roll_gem_count(
        review_rewards.scaled_gem_chance(base, data, owned)
    )


def _most_needed_active(data: dict[str, Any]) -> bool:
    from . import milestones

    return milestones.buff_is_active(data, milestones.BUFF_GEMS_MOST_NEEDED)


def _gem_multiplier(data: dict[str, Any]) -> int:
    from . import milestones

    return milestones.gem_reward_multiplier(data)


def _build_offer(kind: str, data: dict[str, Any], owned: list) -> dict[str, Any]:
    """
    One path resolved into the numbers its button will show.

    Everything is fixed here, at discovery, including the temporary buffs: the previewed quantity
    has to be the paid quantity, and a dungeon outlives a three-day buff. Gem colors are the one
    exception - they are never previewed, so only the flag is kept and the colors are resolved when
    the treasure pays, filling the gap the player has then rather than the one they had days ago.
    """
    offer: dict[str, Any] = {"kind": kind}
    if kind == PATH_UNIQUE:
        pool = _loot_pool(data)
        if pool:
            offer["item"] = _weighted_choice({c["id"]: int(c.get("weight", 1)) for c in pool})
        return offer
    if kind == PATH_UNMARKED:
        outcome = _weighted_choice(
            {k: v for k, v in UNMARKED_WEIGHTS.items()
             if k != PATH_UNIQUE or item_available(data)}
        )
        offer["outcome"] = outcome
        if outcome != UNMARKED_NOTHING:
            offer.update(_build_offer(outcome, data, owned))
            offer["kind"] = PATH_UNMARKED
        return offer

    if kind in (PATH_GOLD, PATH_GOLD_GEMS):
        low, high = (GOLD_MIN, GOLD_MAX) if kind == PATH_GOLD else (COMBO_GOLD_MIN, COMBO_GOLD_MAX)
        offer["gold"] = _roll_gold(low, high, data, owned)
    if kind in (PATH_GEMS, PATH_GOLD_GEMS):
        low, high = (
            (GEMS_PCT_MIN, GEMS_PCT_MAX) if kind == PATH_GEMS
            else (COMBO_GEMS_PCT_MIN, COMBO_GEMS_PCT_MAX)
        )
        # The doubling buff changes the count, and the count is on the button, so it lands here.
        offer["gems"] = _roll_gems(low, high, data, owned) * _gem_multiplier(data)
        offer["most_needed"] = _most_needed_active(data)
    return offer


def offer_summary(offer: dict[str, Any]) -> str:
    """
    What a path button says under its icon.

    The three currency paths name their amount, because it is settled the moment the branching is
    discovered and the button is what promises it. The other two name themselves instead: one is an
    item whose identity waits for the treasure, and the other is the passage with nothing written
    on its walls, which is the whole of what the player knows about it.
    """
    kind = offer.get("kind")
    if kind == PATH_UNIQUE:
        return "Unknown item"
    if kind == PATH_UNMARKED:
        return PATH_LABELS[PATH_UNMARKED]
    parts = []
    if offer.get("gold"):
        parts.append(f"{offer['gold']}g")
    gems = offer.get("gems") or 0
    if gems:
        parts.append(f"{gems} gem" + ("s" if gems != 1 else ""))
    return " + ".join(parts) if parts else "nothing"


# --- The loop ----------------------------------------------------------------------------------

def _new_dungeon() -> dict[str, Any]:
    return {
        "active": True,
        "reviews_since_entrance": 0,
        "reviews_since_branching": 0,
        "branchings_total": random.randint(BRANCHINGS_MIN, BRANCHINGS_MAX),
        "branchings_done": 0,
        "picked": [],
    }


def on_review(data: dict[str, Any], ease: int, level: int) -> dict[str, Any]:
    """
    Advance the dungeon by one answered card and roll for what it finds.

    Returns {"entrance": bool, "branching": bool, "treasure": bool, "xp": int, "auto_took": offer}
    where xp is *base* XP - the caller scales and pays it, so the bonus stack lives in one place.

    Every answer advances the counters, Again included: the fifth applies to the roll, not to the
    count, and both counters measure elapsed reviewing rather than earning.
    """
    found = {"entrance": False, "branching": False, "treasure": False, "xp": 0, "auto_took": None}

    # A review owed to an undo does nothing here at all - no roll, and no counter advanced either,
    # since the floor a branching waits on is progress towards discovering one like any other.
    if undo_block(data):
        data[KEY_UNDO_BLOCK] = undo_block(data) - 1
        return found

    owned = data.get("owned_collectibles", [])
    state = get_state(data)

    if state is None:
        # Counted only above the gate, so the pity measures answers that could have found
        # something: climbing to 15 must not arrive with a bonus already banked.
        if level < UNLOCK_LEVEL:
            return found
        # Counted first, then read back through the same accessor the window quotes, so the bonus
        # shown and the bonus rolled cannot be two expressions that drift apart.
        data[KEY_SEARCH_REVIEWS] = search_reviews(data) + 1
        if _roll_one_in(
            ENTRANCE_ONE_IN, ease,
            shop.dungeon_discover_percent(owned) + discover_pity_percent(data),
        ):
            data["dungeon"] = _new_dungeon()
            data[KEY_SEARCH_REVIEWS] = 0
            found["entrance"] = True
        return found

    state["reviews_since_entrance"] = int(state.get("reviews_since_entrance", 0)) + 1
    state["reviews_since_branching"] = int(state.get("reviews_since_branching", 0)) + 1

    # A pending choice blocks everything: without it, a week away would return five stacked
    # decisions, and a sync batch would roll a whole dungeon before the player saw the first one.
    if pending(data) or treasure_ready(data):
        return found
    if state["reviews_since_branching"] < BRANCHING_FLOOR_REVIEWS:
        return found
    if not _roll_one_in(
        BRANCHING_ONE_IN, ease,
        shop.dungeon_explore_percent(owned) + explore_pity_percent(data),
    ):
        return found

    state["reviews_since_branching"] = 0  # and with it the exploration pity

    # The treasure is found the same way a branching is - the floor, then the same roll - rather
    # than appearing the moment the last pathway is chosen. Walking the final stretch is part of
    # the dungeon, and a treasure that materialised on a button press would make the branching
    # count feel like the whole of it.
    if int(state.get("branchings_done", 0)) >= int(state.get("branchings_total", BRANCHINGS_MAX)):
        state["treasure"] = {"claimed": False}
        found["treasure"] = True
        found["xp"] = XP_TREASURE
        return found

    state["branchings_done"] = int(state.get("branchings_done", 0)) + 1
    found["branching"] = True
    found["xp"] = XP_BRANCHING

    count = random.choice((2, 3))
    kinds = _draw_paths(count, allow_unique=item_available(data))
    state["pending"] = {"paths": [_build_offer(k, data, owned) for k in kinds]}

    if auto_pick_enabled(data):
        found["auto_took"] = choose_path(data, _auto_pick_index(data))
    return found


def _auto_pick_index(data: dict[str, Any]) -> int:
    """
    Which of the offered paths a ranking takes: the highest-ranked kind present.

    By kind and never by value, deliberately. An auto-pick that compared the amounts on the buttons
    would be optimal, which would make the branching a formality with a switch attached - the
    setting is meant to cost a little against playing by hand.
    """
    p = pending(data) or {"paths": []}
    kinds = [o.get("kind") for o in p["paths"]]
    for want in auto_pick_order(data):
        if want in kinds:
            return kinds.index(want)
    return 0


def choose_path(data: dict[str, Any], index: int, auto: bool | None = None) -> dict[str, Any] | None:
    """
    Take one of the offered paths. Returns the offer taken, or None if there was nothing pending.

    Nothing is rolled here: the offer was resolved at discovery and this only records which one was
    taken. Taking the last pathway does not open the treasure - that is its own roll, made on a
    later review (see on_review).
    """
    p = pending(data)
    state = get_state(data)
    if not p or state is None:
        return None
    paths = p["paths"]
    if not 0 <= index < len(paths):
        index = 0
    took = paths[index]
    state.setdefault("picked", []).append({
        "took": took,
        "auto": auto_pick_enabled(data) if auto is None else auto,
    })
    state.pop("pending", None)
    return took


def treasure_totals(data: dict[str, Any]) -> dict[str, Any]:
    """What the picks add up to. Derived from `picked`, never stored - it is their sum."""
    gold = 0
    gem_entries: list[tuple[int, bool]] = []
    item: str | None = None
    for entry in picks(data):
        took = entry.get("took") or {}
        gold += int(took.get("gold") or 0)
        gems = int(took.get("gems") or 0)
        if gems:
            gem_entries.append((gems, bool(took.get("most_needed"))))
        if took.get("item"):
            item = took["item"]
    return {
        "gold": gold,
        "gems": sum(n for n, _ in gem_entries),
        "gem_entries": gem_entries,
        "item": item,
    }


def close(data: dict[str, Any]) -> None:
    """Drop the dungeon and count the claim. The next entrance roll is live again immediately."""
    data.pop("dungeon", None)
    data[KEY_CLAIMED] = dungeons_claimed(data) + 1
    data[KEY_CLAIMED_RUN] = dungeons_claimed_run(data) + 1
