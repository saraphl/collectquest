"""Dungeons: a track paced by review count alone. An entrance, then 3 to 6 branching pathways, then
the treasure. This module owns the state and every roll but pays nothing; review_rewards pays what
it returns. Design: drafts/dungeons.md."""
from __future__ import annotations

import random
from typing import Any

from . import shop

# Only gates entrance discovery: an open dungeon runs to its treasure even if undo drops the level
# back below this.
UNLOCK_LEVEL = 15

# Rolls are "one in N" per answered card; Again gets a fifth of the chance, as it does of review XP.
ENTRANCE_ONE_IN = 400
BRANCHING_ONE_IN = 200
AGAIN_ROLL_RATIO = 0.2

# Pity: after this many answers with nothing found, PITY_PERCENT_PER_STEP accrues per
# PITY_STEP_REVIEWS (2% on the 110th), on whichever roll is live. A find resets it.
PITY_FLOOR_REVIEWS = 100
PITY_STEP_REVIEWS = 10
PITY_PERCENT_PER_STEP = 2

# Reviews after a branching before the next can roll. Flat, never scaled by gear, so branchings
# can't land back to back; it also floors a dungeon at roughly 4.5 x 50 reviews.
BRANCHING_FLOOR_REVIEWS = 50

# How many pathways a branching offers, drawn 50:50. Named rather than inline because the window
# reserves room for the larger of the two, so a two-path screen is the same width as a three.
PATHS_PER_BRANCHING = (2, 3)

# Branchings to the treasure, rolled when the dungeon starts and never shown.
BRANCHINGS_MIN = 3
BRANCHINGS_MAX = 6

# Flat XP, before the bonus stack review_rewards applies. A whole dungeon pays 550 to 880 base,
# depending on how many branchings it runs to.
XP_BRANCHING = 110
XP_TREASURE = 220

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

# Two or three paths per branching, 50:50, drawn by weight without replacement, so Unique shows on
# about 17% of branchings rather than 6%.
PATH_WEIGHTS = {
    PATH_GOLD: 5,
    PATH_GEMS: 5,
    PATH_GOLD_GEMS: 4,
    PATH_UNMARKED: 3,
    PATH_UNIQUE: 1,
}

# What an Unmarked path holds: about 15% more than a named path while the item slot is open, about
# half after it is spent.
UNMARKED_NOTHING = "nothing"
UNMARKED_WEIGHTS = {
    UNMARKED_NOTHING: 7,
    PATH_GOLD: 4,
    PATH_GEMS: 4,
    PATH_GOLD_GEMS: 3,
    PATH_UNIQUE: 3,
}

# Base payouts before bonus stats: 35, 40.5 and 45 gold-equivalent (1 gem = GEM_COST_RANDOM gold),
# so each currency path is a preference, never the wrong answer.
GOLD_MIN, GOLD_MAX = 25, 45
GEMS_PCT_MIN, GEMS_PCT_MAX = 110, 160
COMBO_GOLD_MIN, COMBO_GOLD_MAX = 15, 30
COMBO_GEMS_PCT_MIN, COMBO_GEMS_PCT_MAX = 50, 100

# --- Auto-pick ---------------------------------------------------------------------------------
# Claimed dungeons before the setting unlocks; survives prestige.
AUTO_PICK_UNLOCK_DUNGEONS = 3

# Default ranking: a guaranteed item first, then Unmarked; the leveled currency paths just express
# which currency the player prefers.
DEFAULT_AUTO_PICK_ORDER = [PATH_UNIQUE, PATH_UNMARKED, PATH_GOLD_GEMS, PATH_GEMS, PATH_GOLD]

# Lifetime count gates auto-pick and survives prestige; the per-run count resets with the run.
KEY_CLAIMED = "dungeons_claimed"
KEY_CLAIMED_RUN = "dungeons_claimed_run"
KEY_AUTO_ENABLED = "dungeon_auto_pick_enabled"
KEY_AUTO_ORDER = "dungeon_auto_pick_order"

# --- Undo --------------------------------------------------------------------------------------
# Reviews the dungeon sits out per undone review, so undo isn't a free reroll of a missed roll.
KEY_UNDO_BLOCK = "dungeon_undo_block"

# Answers spent looking for an entrance: the pity counter outside a dungeon (inside,
# reviews_since_branching serves).
KEY_SEARCH_REVIEWS = "dungeon_search_reviews"

# Reviews answered while the dungeon was blocked, kept as two counts; catch_up spreads the Agains
# evenly, which matches a shuffled order (drafts/dungeons.md §6).
KEY_BANKED_REVIEWS = "dungeon_banked_reviews"
KEY_BANKED_AGAINS = "dungeon_banked_agains"

# A sync this far behind owes about eighteen manual choices (drafts/dungeons.md §6), worth offering
# to auto-pick.
CATCH_UP_PROMPT_MIN_BANK = 5000
# Auto-pick granted for one backlog only; catch_up drops it once the bank runs dry.
KEY_CATCH_UP_AUTO = "dungeon_catch_up_auto"
# Asked once per backlog: without this every later sync would put the same question up again while
# the player is still working through the answer they already gave.
KEY_CATCH_UP_ASKED = "dungeon_catch_up_asked"


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


def banked_reviews(data: dict[str, Any]) -> int:
    """Reviews answered while the dungeon was blocked and not yet replayed."""
    return max(0, int(data.get(KEY_BANKED_REVIEWS, 0) or 0))


def banked_agains(data: dict[str, Any]) -> int:
    """How many of those were Again, which rolls at AGAIN_ROLL_RATIO."""
    return max(0, min(banked_reviews(data), int(data.get(KEY_BANKED_AGAINS, 0) or 0)))


def _bank_review(data: dict[str, Any], ease: int) -> None:
    """Set one blocked review aside. Mutates data; the caller saves."""
    data[KEY_BANKED_REVIEWS] = banked_reviews(data) + 1
    if ease == 1:
        data[KEY_BANKED_AGAINS] = banked_agains(data) + 1


def _replay_eases(count: int, agains: int):
    """`count` grades with `agains` of them Again, spread evenly, which sits where a shuffled order
    does. step is never below 1, so the count of Agains is exact."""
    agains = max(0, min(agains, count))
    marks = set()
    if agains:
        step = count / agains
        marks = {min(count - 1, int(i * step)) for i in range(agains)}
    for i in range(count):
        yield 1 if i in marks else 3


def _shift_counters(data: dict[str, Any], delta: int) -> None:
    """Move the open dungeon's counters by `delta` reviews, floored at zero. The counters always
    include the bank; catch_up shifts it off before replaying (or each roll would see too much pity)
    and shifts back what it doesn't replay."""
    state = get_state(data)
    if not state:
        return  # a claimed treasure took the dungeon with it; nothing left to shift
    for key in ("reviews_since_entrance", "reviews_since_branching"):
        state[key] = max(0, int(state.get(key, 0)) + delta)


def catch_up(data: dict[str, Any], level: int) -> list[dict[str, Any]]:
    """Roll the banked reviews now the dungeon is unblocked. Returns what each found. Stops and
    re-banks as soon as it blocks again, so the bank pays out one decision at a time."""
    count = banked_reviews(data)
    # Still blocked: leave the bank and the counters alone.
    if count <= 0 or pending(data) or treasure_ready(data):
        return []
    agains = banked_agains(data)
    _shift_counters(data, -count)
    data[KEY_BANKED_REVIEWS] = 0
    data[KEY_BANKED_AGAINS] = 0

    out: list[dict[str, Any]] = []
    spent_agains = 0
    # Consumed lazily: a chained catch-up takes a few hundred of a bank that can hold a year, and
    # the remainder is two numbers rather than a slice.
    for i, ease in enumerate(_replay_eases(count, agains)):
        if pending(data) or treasure_ready(data):
            rest = count - i
            data[KEY_BANKED_REVIEWS] = rest
            data[KEY_BANKED_AGAINS] = agains - spent_agains
            # Back onto the counters: they are still waiting to be replayed, and the next catch_up
            # shifts off exactly this many again.
            _shift_counters(data, rest)
            break
        if ease == 1:
            spent_agains += 1
        found = on_review(data, ease, level)
        if found["xp"] or any(found[k] for k in ("entrance", "branching", "treasure")):
            out.append(found)
    if banked_reviews(data) <= 0:
        # The backlog is spent: the temporary grant and the one-shot question both expire with it.
        data.pop(KEY_CATCH_UP_AUTO, None)
        data.pop(KEY_CATCH_UP_ASKED, None)
    return out


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
    """The setting, or the one-backlog grant the catch-up prompt hands out (KEY_CATCH_UP_AUTO)."""
    if bool(data.get(KEY_CATCH_UP_AUTO, False)):
        return True
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
    """Whether this dungeon has already paid its one item, derived from the picks so it can't
    disagree with them."""
    for entry in picks(data):
        if (entry.get("took") or {}).get("item"):
            return True
    return False


def unique_path_taken(data: dict[str, Any]) -> bool:
    """Whether a Unique pathway has been taken (not item_taken, so Unique keeps being offered and
    can't give away what an Unmarked path held)."""
    return any((entry.get("took") or {}).get("kind") == PATH_UNIQUE for entry in picks(data))


def _loot_pool(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Loot items the player does not already own."""
    owned = set(data.get("owned_collectibles", []))
    return [c for c in shop.loot_collectibles() if c["id"] not in owned]


def item_available(data: dict[str, Any]) -> bool:
    """Whether an item can still be paid: the slot is unspent and the pool isn't empty (reachable in
    play only via the admin "unlock all collectibles")."""
    return not item_taken(data) and bool(_loot_pool(data))


def unique_offer_available(data: dict[str, Any]) -> bool:
    """Whether a Unique pathway may still be offered: yes even after the item is spent (it then pays
    nothing), no only when the pool is empty."""
    return not unique_path_taken(data) and bool(_loot_pool(data))


# --- Rolls -------------------------------------------------------------------------------------

def _roll_one_in(one_in: int, ease: int, bonus_percent: float = 0.0) -> bool:
    """One chance in `one_in`, scaled like gem luck by a collection bonus and cut to a fifth for
    Again."""
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
    """A gem count from a chance scaled by gem luck; roll_gem_count pays anything above 100% as
    whole gems."""
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
    """One path resolved into the numbers its button shows. Fixed at discovery, buffs included,
    since the preview must be what's paid. Gem colors are the exception: resolved when the treasure
    pays."""
    offer: dict[str, Any] = {"kind": kind}
    if kind == PATH_UNIQUE:
        # No item when the dungeon has already paid its one - an unmarked path may have taken it
        # without the player knowing. The offer still stands; the treasure reveals it as empty.
        pool = [] if item_taken(data) else _loot_pool(data)
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
    """What a path button says under its icon: currency paths name their settled amount; the item
    and Unmarked paths name only themselves."""
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
    """Advance the dungeon by one answered card and roll for what it finds. Returns {"entrance",
    "branching", "treasure", "xp", "auto_took"}, with base XP for the caller to scale and pay. Again
    advances the counters too; the fifth applies only to the roll."""
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

    # A pending choice blocks everything, so a week away can't stack decisions. Banked rather than
    # dropped; catch_up replays the rolls once the player picks or claims.
    if pending(data) or treasure_ready(data):
        _bank_review(data, ease)
        return found
    if state["reviews_since_branching"] < BRANCHING_FLOOR_REVIEWS:
        return found
    if not _roll_one_in(
        BRANCHING_ONE_IN, ease,
        shop.dungeon_explore_percent(owned) + explore_pity_percent(data),
    ):
        return found

    state["reviews_since_branching"] = 0  # and with it the exploration pity

    # The treasure is found like a branching (floor, then roll), not the moment the last pathway is
    # taken.
    if int(state.get("branchings_done", 0)) >= int(state.get("branchings_total", BRANCHINGS_MAX)):
        state["treasure"] = {"claimed": False}
        found["treasure"] = True
        found["xp"] = XP_TREASURE
        return found

    state["branchings_done"] = int(state.get("branchings_done", 0)) + 1
    found["branching"] = True
    found["xp"] = XP_BRANCHING

    count = random.choice(PATHS_PER_BRANCHING)
    kinds = _draw_paths(count, allow_unique=unique_offer_available(data))
    state["pending"] = {"paths": [_build_offer(k, data, owned) for k in kinds]}

    if auto_pick_enabled(data):
        found["auto_took"] = choose_path(data, auto_pick_index(data))
    return found


def auto_pick_index(data: dict[str, Any]) -> int:
    """Which offered path a ranking takes: the highest-ranked kind present. By kind, never value, so
    auto-pick costs a little against choosing by hand."""
    p = pending(data) or {"paths": []}
    kinds = [o.get("kind") for o in p["paths"]]
    for want in auto_pick_order(data):
        if want in kinds:
            return kinds.index(want)
    return 0


def choose_path(data: dict[str, Any], index: int, auto: bool | None = None) -> dict[str, Any] | None:
    """Take one of the offered paths (already resolved at discovery). Returns the offer, or None if
    nothing was pending. The treasure is a later roll, not opened here."""
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
