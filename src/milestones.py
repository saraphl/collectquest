"""
Milestones: a sequential track of fourteen objectives, one active at a time.

See drafts/milestones.md for the design. Two rules from it shape everything here:

  * Every counter starts when its milestone becomes active. Nothing is read from lifetime history,
    so opening the track never hands out completions the player did not earn under it.
  * Exactly one milestone is active. Its progress restarts at zero, so "reach a new 8-day streak"
    following "reach a new 4-day streak" is a fresh eight days rather than four more.

This module owns the ladder, the counters, the advance and what each milestone grants. Rewards are
not written into the save when they are earned: `granted_value` derives them from how far the chain
has come, so nothing has to be replayed and nothing can be granted twice.
"""
from __future__ import annotations

import random
import time
import weakref
from typing import Any

from . import streak, xp

# --- Objective kinds -----------------------------------------------------------------------------

OBJ_STREAK = "streak"          # reach a new N-day streak
OBJ_BONUS_QUEST = "bonus_quest"  # complete the bonus quest N times
OBJ_BOTH_QUESTS = "both_quests"  # complete both daily quests N times
OBJ_CRAFT = "craft"            # craft N items
OBJ_PRESTIGE = "prestige"      # prestige N times

# Objectives whose progress is derived from state the game already keeps, rather than tallied here.
_DERIVED = (OBJ_STREAK,)

# --- The ladder ----------------------------------------------------------------------------------
# (objective, target, reward label). Order is the chain; index 0 is milestone #1.
#
# Labels are derived from the objective and target rather than written out, so a target that is
# rebalanced cannot leave a label behind claiming the old figure.

LADDER: tuple[dict[str, Any], ...] = (
    {"objective": OBJ_STREAK, "target": 4, "reward": "Streak accumulator, +5% cap",
     "grants": {"accumulator_cap_percent": 5}},
    {"objective": OBJ_BONUS_QUEST, "target": 3, "reward": "Bonus quest XP +15%",
     "grants": {"bonus_quest_xp_percent": 15}},
    {"objective": OBJ_BOTH_QUESTS, "target": 5, "reward": "Targeted craft",
     "grants": {"targeted_craft": True}},
    {"objective": OBJ_STREAK, "target": 8, "reward": "Bonus quest can award buffs (15%)",
     "grants": {"buff_drop_percent": 15}},
    {"objective": OBJ_CRAFT, "target": 3, "reward": "Accumulator → +10% cap",
     "grants": {"accumulator_cap_percent": 10}},
    {"objective": OBJ_BONUS_QUEST, "target": 5, "reward": "Quest reroll, once a week",
     "grants": {"quest_reroll": True}},
    {"objective": OBJ_BOTH_QUESTS, "target": 10, "reward": "Shop offers 4 items",
     "grants": {"shop_slots": 4}},
    {"objective": OBJ_PRESTIGE, "target": 2, "reward": "Magnets appear in the shop",
     "grants": {"magnets_in_shop": True}},
    {"objective": OBJ_STREAK, "target": 12, "reward": "Accumulator → +15% cap",
     "grants": {"accumulator_cap_percent": 15}},
    {"objective": OBJ_CRAFT, "target": 6, "reward": "Bonus quest gold +20%",
     "grants": {"bonus_quest_gold_percent": 20}},
    {"objective": OBJ_BONUS_QUEST, "target": 7, "reward": "Buff drop chance → 20%",
     "grants": {"buff_drop_percent": 20}},
    {"objective": OBJ_BOTH_QUESTS, "target": 15, "reward": "Accumulator → +20% cap",
     "grants": {"accumulator_cap_percent": 20}},
    {"objective": OBJ_BONUS_QUEST, "target": 10, "reward": "Buff drop chance → 25%",
     "grants": {"buff_drop_percent": 25}},
    {"objective": OBJ_PRESTIGE, "target": 4, "reward": "Accumulator also boosts gold",
     "grants": {"accumulator_gold_stage": True}},
)

TRACK_LENGTH = len(LADDER)

# The track stays out of sight until here. A new player already has XP, levels, quests, a streak,
# gold, gems and a shop to take in; a fourteen-rung chain on top of that on day one is one system
# too many. Level 10 is a few days in — early enough that the track still has the whole game ahead
# of it, late enough that nothing else is still being explained.
UNLOCK_LEVEL = 10

# --- The streak accumulator ----------------------------------------------------------------------

# Percent added per day of the current streak. Magnets raise this later; until then every player
# charges at the base rate.
ACCUMULATOR_RATE_PERCENT_PER_DAY = 1.0

# --- Magnets -------------------------------------------------------------------------------------

# The first three stages are opened by the accumulator caps the track grants, and raise the charge
# rate. The track raises the ceiling; Magnets raise how fast it is reached. Neither does the other's
# job, and pairing them keeps the time to fill roughly constant as the ceiling rises — without that,
# a player who unlocks a higher cap is worse off after a broken streak than one still on the lower.
#
# The fourth is a different kind of reward, which is why it is the closing one. It raises neither
# the ceiling nor the rate: it widens what the charge applies to, paying the same percentage into
# Gold % as it already pays into XP %. A fourth cap-and-rate step would have been the third one
# again with bigger numbers; this is the only stage that changes the shape of the bonus rather than
# its size, and it is the only one not gated on a cap — #14 grants it directly.
MAGNET_STAGES: tuple[dict[str, Any], ...] = (
    {"cap": 10, "magnets": 3, "rate": 1.5},
    {"cap": 15, "magnets": 5, "rate": 2.0},
    {"cap": 20, "magnets": 10, "rate": 2.5},
    {"grant": "accumulator_gold_stage", "magnets": 15, "gold": True},
)

# One constant for both sources: the bonus quest rolls it on completion, the shop rolls it per
# restock. Deliberately the same figure — a Magnet is one thing to find, however it is found.
MAGNET_DROP_PERCENT = 10


def magnet_stage_index(data: dict[str, Any]) -> int:
    """How many Magnet stages are finished. Also the index of the one in progress, if any."""
    return int(get_state(data).get("magnet_stage", 0) or 0)


def magnet_upgrade_in_progress(data: dict[str, Any]) -> dict[str, Any] | None:
    """
    The stage currently being collected for, or None.

    This is the whole supply rule: no stage waiting to be filled, no Magnets anywhere. It is what
    settles what happens past the last stage — they stop arriving rather than piling up against a
    purchase that does not exist — and it creates deliberate gaps mid-track, between a stage being
    filled and the next cap unlocking the one after it.
    """
    idx = magnet_stage_index(data)
    if idx >= len(MAGNET_STAGES):
        return None
    stage = MAGNET_STAGES[idx]
    return stage if _stage_unlocked(data, stage) else None


def _stage_unlocked(data: dict[str, Any], stage: dict[str, Any]) -> bool:
    """Whether the track has opened this Magnet stage: by reaching its cap, or by granting it."""
    if "cap" in stage:
        return accumulator_cap_percent(data) >= stage["cap"]
    return bool(granted_value(data, stage["grant"], False))


def magnets_held(data: dict[str, Any]) -> int:
    """Magnets collected toward the stage in progress."""
    return int(get_state(data).get("magnets", 0) or 0)


def accumulator_rate_percent_per_day(data: dict[str, Any]) -> float:
    """
    How fast the accumulator charges: the base rate, or the fastest completed stage that sets one.

    Read as "the last stage carrying a rate" rather than "the last stage", because the fourth sets
    none — it widens the bonus instead of speeding it up, and indexing blindly would have raised a
    KeyError the moment a player finished it.
    """
    done = magnet_stage_index(data)
    rate = ACCUMULATOR_RATE_PERCENT_PER_DAY
    for stage in MAGNET_STAGES[:done]:
        if stage.get("rate"):
            rate = float(stage["rate"])
    return rate


def stage_completed_message(stage: dict[str, Any]) -> str:
    """
    What to announce when a Magnet stage completes.

    Lives here rather than at the two notification sites, which both read stage["rate"] directly and
    raised KeyError on the fourth stage — it carries no rate, because it widens the bonus into gold
    instead of speeding it up. A shared reader also means a fifth stage cannot be added without
    deciding what it says.
    """
    rate = stage.get("rate")
    if rate:
        return f"Accumulator now charges {float(rate):g}%/day!"
    if stage.get("gold"):
        return "Accumulator now boosts gold as well as XP!"
    return "Accumulator upgraded!"


def accumulator_boosts_gold(data: dict[str, Any]) -> bool:
    """Whether the accumulator pays into Gold % as well as XP %. The last Magnet stage grants it."""
    done = magnet_stage_index(data)
    return any(stage.get("gold") for stage in MAGNET_STAGES[:done])


def accumulator_gold_percent(data: dict[str, Any]) -> float:
    """The accumulator's contribution to Gold %: the same charge as XP, or nothing until stage 4."""
    return accumulator_percent(data) if accumulator_boosts_gold(data) else 0.0


def award_magnet(data: dict[str, Any], col: Any = None) -> dict[str, Any] | None:
    """
    Add one Magnet. Returns the stage it completed, or None (both when it merely counts and when
    there was no stage to count toward).

    The stage completes itself the moment its last Magnet arrives — no inventory, no combine button,
    no decision, which is the same passivity rule the buffs follow.
    """
    stage = magnet_upgrade_in_progress(data)
    if stage is None:
        return None
    ms = get_state(data)
    held = magnets_held(data) + 1
    if held < int(stage["magnets"]):
        ms["magnets"] = held
        return None
    ms["magnets"] = 0
    ms["magnet_stage"] = magnet_stage_index(data) + 1
    # The new rate applies from this moment rather than from the next streak refresh.
    refresh_accumulator(data, col)
    return stage


CRAFT_BLOCKED_NOTE = "(will require prestiging)"


def craft_objective_blocked(data: dict[str, Any], level: int) -> bool:
    """
    Whether the active craft milestone has fewer items left to craft than it still needs.

    Derived when the row is drawn, never stored. Four things change the answer — an item bought with
    gold and a craft both shrink the pool, a prestige refills it, and a level-up *grows* it as new
    items unlock. That last one flips the answer back, and it is the one a stored flag would get
    wrong: items unlock as high as level 110, so an objective dead at level 29 can be live at 30.

    The objective is neither rescaled nor auto-completed when this is true; the row says so instead.
    Rescaling would quietly turn "craft 6" into "acquire the last items by any means", since some of
    them are also purchasable, and auto-completing hands over a reward for work not done.
    """
    entry = active_entry(data)
    if entry is None or entry["objective"] != OBJ_CRAFT or not has_started(data):
        return False
    progress, target = active_progress(data)
    remaining = target - progress
    if remaining <= 0:
        return False
    # Imported last, and only once the cheap checks have passed: this walks the whole catalog, and
    # the panel that calls it is rebuilt after every answered card.
    from . import shop

    owned = set(data.get("owned_collectibles", []))
    return len(shop.craft_pool(level, owned, data)) < remaining


# A rolling seven days from the last use rather than a calendar week: a fixed week boundary would
# hand a player two rerolls in two days by straddling it, and then make them wait thirteen.
QUEST_REROLL_DAYS = 7


def has_quest_reroll(data: dict[str, Any]) -> bool:
    """Whether the reroll has been granted at all. #6 grants it."""
    return bool(granted_value(data, "quest_reroll", False))


def quest_reroll_available(data: dict[str, Any], col: Any = None) -> bool:
    """Whether a reroll can be spent right now."""
    if not has_quest_reroll(data):
        return False
    last = int(get_state(data).get("quest_reroll_epoch", 0) or 0)
    if not last:
        return True
    today = _today_epoch(col)
    if not today:
        # No collection to date it against. Refusing would be the safer-looking answer and the wrong
        # one: it would gray the button out on a path that simply cannot tell, rather than on a
        # player who has already used it.
        return True
    return today >= last + QUEST_REROLL_DAYS * 86400


def quest_reroll_days_left(data: dict[str, Any], col: Any = None) -> int:
    """Whole days until the next reroll. 0 when one is available."""
    if quest_reroll_available(data, col):
        return 0
    last = int(get_state(data).get("quest_reroll_epoch", 0) or 0)
    today = _today_epoch(col)
    if not today or not last:
        return 0
    return max(0, QUEST_REROLL_DAYS - int((today - last) // 86400))


def spend_quest_reroll(data: dict[str, Any], col: Any = None) -> bool:
    """Consume this week's reroll. False if there was none to spend."""
    if not quest_reroll_available(data, col):
        return False
    get_state(data)["quest_reroll_epoch"] = _today_epoch(col) or 1
    return True


def has_targeted_craft(data: dict[str, Any]) -> bool:
    """Whether crafting draws from the gem-only items alone. Granted by #3."""
    return bool(granted_value(data, "targeted_craft", False))


def magnets_sold_in_shop(data: dict[str, Any]) -> bool:
    """Whether the shop stocks Magnets. #8 grants this; the bonus quest drops them from #5 either way."""
    return bool(granted_value(data, "magnets_in_shop", False))


def roll_magnet(data: dict[str, Any], col: Any = None) -> bool:
    """Roll the bonus quest's Magnet drop. Independent of the buff roll on the same completion."""
    if magnet_upgrade_in_progress(data) is None:
        return False
    return random.randint(0, 99) < MAGNET_DROP_PERCENT


# --- Temporary buffs -----------------------------------------------------------------------------

# The system each buff accelerates. At most one buff per system may run at a time: two buffs that
# speed up the same system multiply rather than add, and rather than re-checking every pair by hand
# as the pool grows, the occupancy rule makes compounding structurally impossible.
SYS_REVIEWS = "reviews"
SYS_QUESTS = "quests"
SYS_SHOP = "shop"
SYS_CRAFTING = "crafting"

BUFF_DAYS = 3

BUFF_REVIEWS_XP = "reviews_xp_20"
BUFF_CRAFT_CHEAPER = "craft_costs_four"
BUFF_GEMS_MOST_NEEDED = "gems_most_needed"
BUFF_GEMS_DOUBLE = "gems_double"
BUFF_SHOP_DISCOUNT = "shop_discount"
BUFF_QUESTS_DOUBLE = "quests_double"

# Reviews pay this much more while the multiplier runs. Review-scoped on purpose: the game's
# xp_bonus_percent also covers quests and streak rewards, and a percentage that applies to reviews
# alone is a shape it has no stat for, which is what makes it worth a buff slot.
BUFF_REVIEW_XP_PERCENT = 20

# How much the shop knocks off every gold price while the discount runs.
BUFF_SHOP_DISCOUNT_PERCENT = 20

# What the two doubling buffs multiply by. Named rather than written as a bare 2, because the rule
# they follow is "buffs multiply quantities, never chances" and the constant is where that lives.
BUFF_DOUBLE = 2

BUFFS: tuple[dict[str, Any], ...] = (
    {"id": BUFF_REVIEWS_XP, "system": SYS_REVIEWS, "label": "Reviews pay 20% more XP"},
    {"id": BUFF_QUESTS_DOUBLE, "system": SYS_QUESTS,
     "label": "Double quest rewards, bonus quest included"},
    {"id": BUFF_SHOP_DISCOUNT, "system": SYS_SHOP,
     "label": "Everything in the shop costs 20% less gold"},
    {"id": BUFF_CRAFT_CHEAPER, "system": SYS_CRAFTING,
     "label": "Crafting costs 4 gems instead of 5"},
    {"id": BUFF_GEMS_MOST_NEEDED, "system": SYS_CRAFTING,
     "label": "Every gem reward is the most-needed color"},
    {"id": BUFF_GEMS_DOUBLE, "system": SYS_CRAFTING, "label": "Double gem rewards"},
)


def buff_by_id(buff_id: str) -> dict[str, Any] | None:
    return next((b for b in BUFFS if b["id"] == buff_id), None)

# Shown in the panel and the window once every milestone is done. "Available" rather than "all",
# so a later version adding a fifteenth has not told the player they were finished with it.
ALL_COMPLETE_LABEL = "All available milestones complete!"


def objective_label(entry: dict[str, Any]) -> str:
    """The player-facing objective text for one ladder entry."""
    kind = entry["objective"]
    n = entry["target"]
    if kind == OBJ_STREAK:
        return f"Reach a new {n}-day streak"
    if kind == OBJ_BONUS_QUEST:
        return f"Complete the bonus quest {n} times"
    if kind == OBJ_BOTH_QUESTS:
        return f"Complete both daily quests {n} times"
    if kind == OBJ_CRAFT:
        return f"Craft {n} items"
    if kind == OBJ_PRESTIGE:
        return f"Prestige {n} times"
    return ""


# --- State ---------------------------------------------------------------------------------------


def default_state() -> dict[str, Any]:
    """
    Fresh track state. `active` is 1-based; TRACK_LENGTH + 1 means the chain is finished.

    `active_since_epoch` is stored alongside the date string because the streak objectives compare
    against a scheduler-day boundary, and reconstructing that boundary from a date string would mean
    re-deriving the rollover hour this module has no other reason to know.
    """
    return {
        "started": "",
        "active": 1,
        "active_since": "",
        "active_since_epoch": 0,
        "active_progress": 0,
        # Scheduler days the two quest counters are done with: the day each last fired, or a day
        # `_seal_activation_day` shut out because the milestone opened onto it half spent. One key
        # for both meanings on purpose - a day that cannot count again is the whole of what either
        # needs - so anything clearing one of these reopens a day the seal closed, not merely a
        # count that "did not really happen".
        # Both live here rather than in the save's root, and undo never touches them - which is the
        # whole point. `cleared_bonus_date` in the root looks like it would serve for the bonus
        # quest, but undo deliberately pops it so the day's XP and gold can be re-earned, and
        # hanging the track's counter on it let one completion count twice.
        "both_quests_date": "",
        "bonus_quest_date": "",
        # Current accumulator charge. Stored rather than derived because the XP math runs on paths
        # that hold no collection, and the streak length it comes from needs one. Kept current by
        # refresh_accumulator, which every path that touches the streak already calls.
        "accumulator_percent": 0.0,
        # The scheduler day the accumulator was unlocked, stamped the first time its cap is above
        # zero. It charges from that day rather than from the streak's start, so a player who
        # unlocks it mid-streak ramps up from 1% like everyone else.
        "accumulator_since_epoch": 0,
        # Running buffs: {"id", "started", "started_epoch", "days"}. A list because buffs from
        # different systems coexist; never two entries for one effect, since the occupancy rule
        # below refuses a roll that lands on a system already running one.
        "active_buffs": [],
        # Magnets toward the stage in progress, and how many stages are done. Two numbers rather
        # than one running total: a Magnet is collected toward a named upgrade, not banked.
        "magnets": 0,
        "magnet_stage": 0,
        # Scheduler-day epoch of the last quest reroll. 0 means never used.
        "quest_reroll_epoch": 0,
        # Milestones finished but not yet announced, as 1-based ladder indexes. A queue rather than
        # a return value, because the four paths that can finish one - a review, a craft, a
        # prestige, and the refresh that notices a streak milestone at launch - are not all places
        # a notification can be shown from. Whichever UI path runs next drains it.
        "pending_announcements": [],
    }


def get_state(data: dict[str, Any]) -> dict[str, Any]:
    """The track state, creating it in `data` on first read."""
    ms = data.get("milestones")
    if not isinstance(ms, dict):
        ms = default_state()
        data["milestones"] = ms
    else:
        for k, v in default_state().items():
            ms.setdefault(k, v)
    return ms


def is_unlocked(data: dict[str, Any]) -> bool:
    """
    Whether the track is available at all: level UNLOCK_LEVEL, or any prestige ever.

    A prestige sends the player back to level 1 with everything else intact, and the track is one
    of the things it keeps. Re-hiding it for the first ten levels of every run would take a system
    away from the player who has most reason to have it, so a single prestige unlocks it for good.

    The level is derived from total XP rather than read from `level`, which is the same rule the
    prestige payout follows: total XP is the number the game actually stores forward.
    """
    if int(data.get("prestige_count", 0) or 0) > 0:
        return True
    return xp.level_from_total_xp(int(data.get("total_xp", 0) or 0)) >= UNLOCK_LEVEL


def has_started(data: dict[str, Any]) -> bool:
    """Whether the track has opened. False before the unlock, and the gate every counter checks."""
    return bool(get_state(data).get("started"))


def ensure_started(data: dict[str, Any], col: Any = None) -> None:
    """Open the track once it is unlocked, stamping today as the first milestone's start."""
    ms = get_state(data)
    if ms["started"] or not is_unlocked(data):
        return
    today = streak.today_str(col)
    ms["started"] = today
    ms["active_since"] = today
    ms["active_since_epoch"] = _today_epoch(col)
    ms["active_progress"] = 0
    _seal_activation_day(data, col)


# The scheduler day, memoized for the collection it was read from. streak.today_epoch runs a DB
# query, and an answered card reaches this module from half a dozen places - the refresh, the
# both-quests counter, the advance, the bonus quest's own counter - each of which asked again for a
# value that cannot change within one answer.
#
# The collection is identified by a weak reference rather than by id(). An id is only unique among
# *live* objects: a collection that is closed and replaced can land at the same address, and the
# cache would then hand the new one the old one's day. A weak reference goes dead when that happens,
# so a swapped collection is a guaranteed miss. Weak rather than strong so a closed profile is not
# held open by a cache entry.
_today_cache: tuple[Any, float, int] | None = None
_TODAY_CACHE_TTL_SECONDS = 5.0


def _today_epoch(col: Any) -> int:
    """Scheduler day start as a Unix timestamp, or 0 when the collection cannot be read."""
    global _today_cache
    if col is None:
        return 0
    now = time.monotonic()
    if _today_cache is not None:
        ref, stamp, value = _today_cache
        if ref() is col and now - stamp < _TODAY_CACHE_TTL_SECONDS:
            return value
    try:
        value = int(streak.today_epoch(col))
    except Exception:
        return 0
    try:
        _today_cache = (weakref.ref(col), now, value)
    except TypeError:
        _today_cache = None  # Not weak-referenceable; correct but uncached.
    return value


def _ensure_active_epoch(data: dict[str, Any], col: Any) -> int:
    """
    The day the active milestone opened, back-filling it the first time a collection is available.

    Some events reach this module without one — a gem craft is bought from the shop dialog, which
    has no reason to hold a collection — so a track opened by one of those stamps a date string and
    a zero epoch. Streak progress is measured against that epoch, and treating zero as "no boundary"
    rather than "the epoch" is what stops a player's pre-existing 200-day streak from completing the
    first milestone the instant the track opens.
    """
    ms = get_state(data)
    since = int(ms.get("active_since_epoch") or 0)
    if since:
        return since
    today = _today_epoch(col)
    if today:
        ms["active_since_epoch"] = today
    return today


def is_finished(data: dict[str, Any]) -> bool:
    return get_state(data)["active"] > TRACK_LENGTH


def active_entry(data: dict[str, Any]) -> dict[str, Any] | None:
    """The ladder entry currently being worked on, or None once the track is finished."""
    ms = get_state(data)
    idx = ms["active"]
    if 1 <= idx <= TRACK_LENGTH:
        return LADDER[idx - 1]
    return None


def completed_count(data: dict[str, Any]) -> int:
    """Milestones finished. Everything below `active` is done, by construction."""
    return min(TRACK_LENGTH, get_state(data)["active"] - 1)


def granted_value(data: dict[str, Any], key: str, default: Any = 0) -> Any:
    """
    The value `key` has been granted up to, across every milestone already completed.

    Derived from `active` rather than written into the save when a milestone completes. Nothing has
    to be replayed for a save whose track advanced under a build that did not yet grant the reward,
    a reward can never be applied twice, and the ladder stays the single statement of what each
    milestone pays. Numbers take the highest granted; anything else takes the last.
    """
    active = get_state(data)["active"]
    out = default
    for i, entry in enumerate(LADDER, start=1):
        if i >= active:
            break
        if key in entry.get("grants", {}):
            value = entry["grants"][key]
            out = max(out, value) if isinstance(value, (int, float)) and isinstance(out, (int, float)) else value
    return out


def accumulator_cap_percent(data: dict[str, Any]) -> int:
    """The ceiling the track has raised the accumulator to. 0 until milestone #1 is done."""
    return int(granted_value(data, "accumulator_cap_percent", 0))


def accumulator_percent(data: dict[str, Any]) -> float:
    """
    The accumulator's current contribution, in percent. Read by the XP math; never recomputed there.

    Clamped to the cap on read as well as on refresh, so a save carrying a charge from a higher cap
    - the track is kept across a prestige, and a future rebalance could lower one - cannot pay out
    above what the player has actually unlocked.
    """
    cap = accumulator_cap_percent(data)
    if cap <= 0:
        return 0.0
    return max(0.0, min(float(cap), float(get_state(data).get("accumulator_percent", 0.0) or 0.0)))


def refresh(data: dict[str, Any], col: Any = None) -> None:
    """
    Daily housekeeping for the track: expire finished buffs and recharge the accumulator.

    Both need the collection, and both are read from paths that have none — `review_xp_exact` asks
    whether the review buff is running, and gets no collection to date it against. Without a prune
    on a path that *does* hold one, a buff would apply forever: active_buffs falls back to reporting
    what is stored rather than expiring everything, which is the safe answer for a reader but the
    wrong one to leave standing. Calling this wherever the collection is in hand keeps the stored
    list itself current, so the col-less readers are reading an already-pruned list.
    """
    active_buffs(data, col)
    refresh_accumulator(data, col)


def refresh_accumulator(data: dict[str, Any], col: Any = None) -> float:
    """
    Recompute the charge from the current streak, and store it. Returns the new value.

    Charges one percent per day, capped, and lost with the streak: a broken run reads zero days and
    so pays zero, which is the whole point of the reward. Called from streak.refresh_streak, which
    every path that could have moved the streak already runs.

    **Counted from the unlock, not from the streak's start.** A player who finishes milestone #1 on
    day 11 of a streak would otherwise see the bar jump straight to its cap, which is the one thing
    the track never does - every objective on it starts its count at zero the moment it opens, and
    the reward it grants should read the same way. Bounded by the streak as well, so the charge is
    the number of days that are both since the unlock and inside the current run: a break still
    drops it to nothing and rebuilds from 1%. Once the ramp is longer than the cap needs, the streak
    is the only term that binds and this reduces to what it always was.

    **Without a collection it leaves the stored charge alone**, clamped to the cap but not
    recomputed. Zero days and "cannot count the days" are not the same answer, and several callers
    arrive with no collection: buying the last Magnet of a stage, crafting the item that completes a
    craft milestone, and prestiging all advance the track from a path that holds none. Recomputing
    there wrote a 0 over a charge the player had earned, and the craft case did it while granting
    the very cap the charge fills.
    """
    ms = get_state(data)
    cap = accumulator_cap_percent(data)
    if cap <= 0:
        ms["accumulator_percent"] = 0.0
        return 0.0
    today_ep = _today_epoch(col)
    if not today_ep:
        return accumulator_percent(data)
    try:
        streak_days, _ = streak.get_display_streak_days(data, today_ep)
    except Exception:
        return accumulator_percent(data)
    # Stamped on the first refresh that sees a cap, which is the refresh right after milestone #1
    # completes. Lazy rather than written by the grant, so a save whose cap was granted by an
    # earlier build starts its ramp now instead of arriving pre-charged.
    if not int(ms.get("accumulator_since_epoch") or 0):
        ms["accumulator_since_epoch"] = today_ep
    days = accumulator_days(data, col)
    charge = min(float(cap), days * accumulator_rate_percent_per_day(data))
    ms["accumulator_percent"] = charge
    return charge


def accumulator_days(data: dict[str, Any], col: Any = None) -> int:
    """
    The days currently charging the accumulator: since the unlock, and inside the current run.

    The number the charge is actually computed from, which is not the player's streak length once
    the two differ - unlocking on day 11 of a streak charges from day 1. Shared with the label in
    the milestones window so the figure in brackets explains the figure beside it; deriving it
    twice is how the two would come to disagree.
    """
    if accumulator_cap_percent(data) <= 0:
        return 0
    today_ep = _today_epoch(col)
    if not today_ep:
        return 0
    since = int(get_state(data).get("accumulator_since_epoch") or 0)
    if not since:
        return 0
    try:
        streak_days, _ = streak.get_display_streak_days(data, today_ep)
    except Exception:
        return 0
    days_since_unlock = (today_ep - since) // 86400 + 1
    return max(0, min(int(streak_days), int(days_since_unlock)))


def buff_drop_percent(data: dict[str, Any]) -> int:
    """Chance the bonus quest also drops a buff. 0 until #4 opens the faucet."""
    return int(granted_value(data, "buff_drop_percent", 0))


def active_buffs(data: dict[str, Any], col: Any = None) -> list[dict[str, Any]]:
    """
    The buffs running right now, dropping any that have expired.

    Expiry is measured against the scheduler day the buff started, so a buff bought at 23:00 lasts
    three studying days rather than two days and an hour. Prunes in place, which is what keeps the
    save from accumulating an entry per drop forever.
    """
    ms = get_state(data)
    entries = ms.get("active_buffs") or []
    today = _today_epoch(col)
    if not today:
        # No collection to date it against; report what is stored rather than expiring everything.
        return [e for e in entries if buff_by_id(e.get("id"))]
    live = []
    for e in entries:
        if not buff_by_id(e.get("id")):
            continue  # An effect from a build that defined buffs this one does not.
        started = int(e.get("started_epoch") or 0)
        if not started:
            # Dropped on a path that could not date it. Back-filled to today rather than treated as
            # expired: an unstamped entry read as "started at the epoch" would delete a buff the
            # player was just told they had, on the first prune that saw it.
            started = today
            e["started_epoch"] = today
        days = int(e.get("days") or BUFF_DAYS)
        if today < started + days * 86400:
            live.append(e)
    if len(live) != len(entries):
        ms["active_buffs"] = live
    return live


def buff_is_active(data: dict[str, Any], buff_id: str, col: Any = None) -> bool:
    """Whether one particular effect is running. The readers of a buff all go through this."""
    return any(e.get("id") == buff_id for e in active_buffs(data, col))


def gem_reward_multiplier(data: dict[str, Any], from_quest: bool = False) -> int:
    """
    What a gem reward is multiplied by: 1, or 2 while a doubling buff applies.

    **Never 4.** "Double gem rewards" is tagged crafting and "Double quest rewards" is tagged
    quests, so the one-buff-per-system rule does not keep them apart — both can run at once, and
    both claim a quest's gem. Multiplying them would quadruple it, which is exactly the compounding
    the occupancy rule exists to prevent, reappearing across systems instead of within one. Doubling
    at most once closes it: two doubling buffs are redundant on a quest gem rather than explosive,
    and each is still worth its full value everywhere the other does not reach.
    """
    doubled = buff_is_active(data, BUFF_GEMS_DOUBLE)
    if from_quest and buff_is_active(data, BUFF_QUESTS_DOUBLE):
        doubled = True
    return BUFF_DOUBLE if doubled else 1


def quest_reward_multiplier(data: dict[str, Any]) -> int:
    """What a quest's XP and gold are multiplied by. Covers the bonus quest, which shares helpers."""
    return BUFF_DOUBLE if buff_is_active(data, BUFF_QUESTS_DOUBLE) else 1


def buff_days_left(entry: dict[str, Any], col: Any = None) -> int:
    """Whole scheduler days a running buff has left, counting today as one."""
    today = _today_epoch(col)
    started = int(entry.get("started_epoch") or 0)
    days = int(entry.get("days") or BUFF_DAYS)
    if not today or not started:
        return days
    return max(0, days - int((today - started) // 86400))


def roll_buff(data: dict[str, Any], col: Any = None) -> dict[str, Any] | None:
    """
    Roll the bonus quest's buff drop. Returns the buff that started, or None.

    The system is rolled first and a buff chosen within it, rather than one buff drawn from the
    whole pool. Drawn flat, a system holding three of the six buffs would take half of every drop,
    so adding a buff to a system would raise its *frequency* instead of its variety. Systems already
    running a buff are excluded, which is both the occupancy rule and the re-roll it calls for: an
    even draw among the free systems is exactly "re-roll among the ones that are free".

    Systems with no buff defined yet are excluded too, so a partial pool drops something rather than
    rolling a system it has nothing to offer from.
    """
    chance = buff_drop_percent(data)
    if chance <= 0 or random.randint(0, 99) >= chance:
        return None
    busy = {b["system"] for e in active_buffs(data, col) if (b := buff_by_id(e.get("id")))}
    free = sorted({b["system"] for b in BUFFS} - busy)
    if not free:
        return None
    system = random.choice(free)
    buff = random.choice([b for b in BUFFS if b["system"] == system])
    get_state(data).setdefault("active_buffs", []).append(
        {
            "id": buff["id"],
            "started": streak.today_str(col),
            "started_epoch": _today_epoch(col),
            "days": BUFF_DAYS,
        }
    )
    return buff


# --- Progress ------------------------------------------------------------------------------------


def _streak_progress(data: dict[str, Any], col: Any) -> int:
    """
    Days of the current streak that fall at or after the milestone became active.

    Not "the run started after active_since": a player who is mid-streak when the milestone opens
    would then have to break the streak before they could begin, which is the opposite of what the
    track is for. Counting only the days since activation gives the fresh N days the design asks for
    without ever making a broken streak the way forward.
    """
    if col is None:
        return 0
    today_ep = _today_epoch(col)
    if not today_ep:
        return 0
    since = _ensure_active_epoch(data, col)
    if not since:
        return 0
    current, _ = streak.get_display_streak_days(data, today_ep)
    if current <= 0:
        return 0
    days_since_active = (today_ep - since) // 86400 + 1
    return max(0, min(current, int(days_since_active)))


def active_progress(data: dict[str, Any], col: Any = None) -> tuple[int, int]:
    """(progress, target) for the active milestone, or (0, 0) once the track is finished."""
    entry = active_entry(data)
    if entry is None or not has_started(data):
        return (0, 0)
    target = int(entry["target"])
    if entry["objective"] == OBJ_STREAK:
        return (min(_streak_progress(data, col), target), target)
    ms = get_state(data)
    return (min(int(ms.get("active_progress", 0) or 0), target), target)


# --- Events --------------------------------------------------------------------------------------


def note_event(data: dict[str, Any], kind: str, col: Any = None, amount: int = 1) -> None:
    """
    Record one occurrence of `kind` against the active milestone.

    Only the active milestone's own objective advances: this is what makes each counter start at
    zero when its milestone opens, without storing a counter per objective and subtracting a
    baseline. An event for any other objective is dropped on the floor by design.
    """
    ensure_started(data, col)
    if not has_started(data):
        return  # Locked: nothing counts toward a track the player cannot see.
    entry = active_entry(data)
    if entry is None or entry["objective"] != kind or kind in _DERIVED:
        return
    ms = get_state(data)
    ms["active_progress"] = int(ms.get("active_progress", 0) or 0) + int(amount)


def note_both_quests_complete(data: dict[str, Any], col: Any = None) -> None:
    """
    Count a day on which every daily quest was finished, at most once per scheduler day.

    The guard is stored rather than inferred from the quests themselves, because the quests are
    replaced when the day turns and a caller running just after the roll would see an unfinished
    pair on a day that had already been counted.

    The pair is re-read here rather than taken on the caller's word. `quests.on_review` decides the
    day is complete from `daily_quests` alone, which on a day `ensure_daily_quests` could not roll -
    an unmeasurable due count - is still yesterday's finished pair beside yesterday's un-reset
    counters. Every quest reads as done on the first answer of the new day, and the day would be
    counted for work nobody did. `_quests_today` is the same freshness check the seal runs, so both
    the counting and the shutting-out judge the day by one rule.
    """
    ensure_started(data, col)
    if not has_started(data):
        return
    ms = get_state(data)
    today = streak.today_str(col)
    if ms.get("both_quests_date") == today:
        return
    quests_today = _quests_today(data, today)
    if not quests_today:
        return
    if not all(q.get("progress", 0) >= q.get("target", 0) for q in quests_today):
        return
    ms["both_quests_date"] = today
    note_event(data, OBJ_BOTH_QUESTS, col)


def note_bonus_quest_complete(data: dict[str, Any], col: Any = None) -> bool:
    """
    Count today's bonus quest once. True if this call was the one that counted it.

    Guarded on its own scheduler-day key rather than on the payout's `cleared_bonus_date`, because
    undo pops that one: hooks._revert_last_review_rewards clears it so the day's XP and gold can be
    claimed again, which is correct for the payout and wrong for a counter. Without a guard of its
    own, undoing and re-answering the day's last due card counted one completion twice - and handed
    out a second buff roll and a second Magnet roll with it, neither of which undo takes back.

    The caller uses the return value to gate those rolls, so a redo re-pays the XP and gold and
    nothing else.
    """
    ensure_started(data, col)
    if not has_started(data):
        return False
    ms = get_state(data)
    today = streak.today_str(col)
    if ms.get("bonus_quest_date") == today:
        return False
    ms["bonus_quest_date"] = today
    note_event(data, OBJ_BONUS_QUEST, col)
    return True


def _quests_today(data: dict[str, Any], today: str) -> list[dict[str, Any]]:
    """
    Today's daily quests, or [] when the stored ones belong to a day that has already turned.

    The date check is what keeps yesterday's finished pair from being read as today's. The quests
    are replaced by `quests.ensure_daily_quests`, which gives up without rolling on a day whose due
    counts cannot be measured - so a day can be well under way with the previous day's finished
    pair, and its stale `reviews_today` and `correct_today`, still sitting in the save. Both readers
    below would take that pair for today's.

    Takes the day rather than deriving it, so a caller that has already asked for it - both of them
    have - does not pay for a second `rollover` lookup.
    """
    if data.get("last_date") != today:
        return []
    return data.get("daily_quests") or []


def _seal_activation_day(data: dict[str, Any], col: Any = None) -> None:
    """
    Shut today out of a newly active milestone's counter when today's work is already part done.

    "Progress restarts" has to mean the objective is met by work done under it, and the two quest
    objectives count whole days. A day is only half spent when a milestone opens mid-session: a
    player holding one finished daily quest when "complete both daily quests 5 times" arrives would
    finish the other and bank a day whose first half was earned under the milestone before it.

    Stamping the counter's scheduler-day key is the entire mechanism - both counters are already
    guarded to once per day, so a day marked as counted is a day that cannot count. A day with
    nothing finished yet is deliberately left alone: it is still a day the player can complete from
    scratch under the new objective.

    The unit is a finished quest, not the progress inside one. A quest sitting at 19/20 when the
    milestone opens still counts when it is completed - the objective is written in completions, and
    reaching for part-finished progress would also have to explain what a half-reviewed collection
    means for the bonus quest.
    """
    entry = active_entry(data)
    if entry is None or entry["objective"] not in (OBJ_BOTH_QUESTS, OBJ_BONUS_QUEST):
        return  # Nothing else counts whole days, so nothing else has a part-spent one to shut out.
    ms = get_state(data)
    today = streak.today_str(col)
    if entry["objective"] == OBJ_BOTH_QUESTS:
        if any(q.get("progress", 0) >= q.get("target", 0) for q in _quests_today(data, today)):
            ms["both_quests_date"] = today
    # `bonus_quest_date` is already stamped whenever the bonus quest is counted, whichever milestone
    # was active at the time, so the only day this adds is one cleared while the track was locked.
    elif data.get("cleared_bonus_date") == today:
        ms["bonus_quest_date"] = today


def advance_if_complete(data: dict[str, Any], col: Any = None) -> dict[str, Any] | None:
    """
    Move to the next milestone if the active one is done. Returns the entry just completed, or None.

    Called after any event that could have finished one, and safe to call at any other time: a
    streak objective can complete without an event of its own, since its progress is derived from
    the streak rather than tallied.
    """
    ensure_started(data, col)
    if not has_started(data):
        return None
    entry = active_entry(data)
    if entry is None:
        return None
    progress, target = active_progress(data, col)
    if progress < target:
        return None
    ms = get_state(data)
    index = int(ms["active"])
    ms["active"] = index + 1
    ms["active_since"] = streak.today_str(col)
    ms["active_since_epoch"] = _today_epoch(col)
    ms["active_progress"] = 0
    # Queued before the seal: the advance is already written, and a seal that raised - a foreign
    # save with a malformed quest entry - would otherwise consume the milestone without announcing
    # the reward it just paid.
    ms.setdefault("pending_announcements", []).append(index)
    _seal_activation_day(data, col)
    # The completed milestone may have raised the cap, and granted_value reads the new `active`
    # straight away. Recharging here means the reward is worth something on the day it lands rather
    # than at the next streak refresh.
    refresh_accumulator(data, col)
    return entry


def take_pending_announcements(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    The ladder entries finished since anything last announced, clearing the queue.

    Draining is what keeps a completion from being announced twice: the refresh that advances the
    track runs from eight call sites including panel redraws, so anything that announced from the
    state itself would repeat on every redraw until the day changed.
    """
    ms = get_state(data)
    pending = [i for i in (ms.get("pending_announcements") or []) if 1 <= i <= TRACK_LENGTH]
    if ms.get("pending_announcements"):
        ms["pending_announcements"] = []
    return [LADDER[i - 1] for i in pending]
