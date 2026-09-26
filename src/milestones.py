"""Milestones: a sequential track of fifteen objectives, one active at a time
(drafts/milestones.md). Counters start from zero when a milestone activates; rewards are derived
from progress by `granted_value`, never stored, so nothing is granted twice."""
from __future__ import annotations

import random
from typing import Any

from . import streak, xp

# --- Objective kinds -----------------------------------------------------------------------------

OBJ_STREAK = "streak"          # reach a new N-day streak
OBJ_BONUS_QUEST = "bonus_quest"  # complete the bonus quest N times
OBJ_BOTH_QUESTS = "both_quests"  # complete both daily quests N times
OBJ_CRAFT = "craft"            # craft N items
OBJ_PRESTIGE = "prestige"      # prestige N times
OBJ_LOOT = "loot"              # loot N items from dungeon treasure

# Objectives whose progress is derived from state the game already keeps, rather than tallied here.
_DERIVED = (OBJ_STREAK,)

# --- The ladder ----------------------------------------------------------------------------------
# (objective, target, reward label), in chain order. Labels are derived, so they can't go stale.

LADDER: tuple[dict[str, Any], ...] = (
    {"objective": OBJ_STREAK, "target": 4, "reward": "Streak accumulator, +5% cap",
     "grants": {"accumulator_cap_percent": 5}},
    {"objective": OBJ_BONUS_QUEST, "target": 3, "reward": "Bonus quest XP +15%",
     "grants": {"bonus_quest_xp_percent": 15}},
    {"objective": OBJ_BOTH_QUESTS, "target": 5, "reward": "Craft gem-only items first",
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
    {"objective": OBJ_LOOT, "target": 3, "reward": "Dungeons bigger by 1 branching",
     "grants": {"dungeon_extra_branchings": 1}},
)

TRACK_LENGTH = len(LADDER)

# Hidden until here: a new player has enough systems to take in on day one.
UNLOCK_LEVEL = 10

# --- The streak accumulator ----------------------------------------------------------------------

# Percent added per day of the current streak. Magnets raise this later; until then every player
# charges at the base rate.
ACCUMULATOR_RATE_PERCENT_PER_DAY = 1.0

# --- Magnets -------------------------------------------------------------------------------------

# The track raises the accumulator's ceiling and the first three stages its rate, keeping
# time-to-fill roughly constant. The fourth (granted by #14) widens the charge into Gold %.
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
    """The stage currently being collected for, or None. Also the supply rule: no stage waiting, no
    Magnets anywhere."""
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
    """How fast the accumulator charges: the base rate, or the last completed stage that sets one
    (the fourth sets none)."""
    done = magnet_stage_index(data)
    rate = ACCUMULATOR_RATE_PERCENT_PER_DAY
    for stage in MAGNET_STAGES[:done]:
        if stage.get("rate"):
            rate = float(stage["rate"])
    return rate


def stage_completed_message(stage: dict[str, Any]) -> str:
    """What to announce when a Magnet stage completes. Shared by both notification sites; the fourth
    stage has no "rate" key."""
    rate = stage.get("rate")
    if rate:
        return f"Accumulator now charges {float(rate):g}%/day!"
    if stage.get("gold"):
        return "Accumulator now boosts gold as well as XP!"
    return "Accumulator upgraded!"


def stage_payoff_label(stage: dict[str, Any]) -> str:
    """What a Magnet stage pays, named in front of the objective asking for its magnets."""
    if stage.get("rate"):
        return "Faster charging"
    if stage.get("gold"):
        return "Gold bonus"
    return "Accumulator upgrade"


def accumulator_boosts_gold(data: dict[str, Any]) -> bool:
    """Whether the accumulator pays into Gold % as well as XP %. The last Magnet stage grants it."""
    done = magnet_stage_index(data)
    return any(stage.get("gold") for stage in MAGNET_STAGES[:done])


def accumulator_gold_percent(data: dict[str, Any]) -> float:
    """The accumulator's contribution to Gold %: the same charge as XP, or nothing until stage 4."""
    return accumulator_percent(data) if accumulator_boosts_gold(data) else 0.0


def award_magnet(data: dict[str, Any], col: Any = None) -> dict[str, Any] | None:
    """Add one Magnet. Returns the stage it completed, or None (merely counted, or no stage to count
    toward). A stage completes on its last Magnet."""
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
    """Whether the active craft milestone has fewer items left to craft than it still needs. Derived
    per draw, since the pool shrinks and grows; the row says so rather than rescaling."""
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
        # No collection to date it against: allow rather than gray the button out on a path that
        # simply cannot tell.
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


def dungeon_extra_branchings(data: dict[str, Any]) -> int:
    """Branchings added to both ends of a new dungeon's range. Granted by #15."""
    return int(granted_value(data, "dungeon_extra_branchings", 0))


def magnets_sold_in_shop(data: dict[str, Any]) -> bool:
    """Whether the shop stocks Magnets. #8 grants this; the bonus quest drops them from #5 either way."""
    return bool(granted_value(data, "magnets_in_shop", False))


def roll_magnet(data: dict[str, Any], col: Any = None) -> bool:
    """Roll the bonus quest's Magnet drop. Independent of the buff roll on the same completion."""
    if magnet_upgrade_in_progress(data) is None:
        return False
    return random.randint(0, 99) < MAGNET_DROP_PERCENT


# --- Temporary buffs -----------------------------------------------------------------------------

# The system each buff accelerates. At most one buff per system runs at a time, which makes two
# buffs on the same system - and the compounding that follows - structurally impossible.
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

# Reviews pay this much more while the multiplier runs. Review-scoped on purpose: xp_bonus_percent
# also covers quests and streak rewards, so it cannot express this.
BUFF_REVIEW_XP_PERCENT = 20

# How much the shop knocks off every gold price while the discount runs.
BUFF_SHOP_DISCOUNT_PERCENT = 20

# What the two doubling buffs multiply by. Buffs multiply quantities, never chances.
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

# "Available" rather than "all", so adding more later does not make this a lie.
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
    if kind == OBJ_LOOT:
        return f"Loot {n} items from dungeons"
    return ""


# --- State ---------------------------------------------------------------------------------------


def default_state() -> dict[str, Any]:
    """Fresh track state. `active` is 1-based; TRACK_LENGTH + 1 means finished. `active_since_epoch`
    lets streak objectives compare against a scheduler-day boundary."""
    return {
        "started": "",
        "active": 1,
        "active_since": "",
        "active_since_epoch": 0,
        "active_progress": 0,
        # Scheduler days these counters are done with (fired, or sealed by `_seal_activation_day`).
        # Separate from `cleared_bonus_date`, which undo pops, or one completion counted twice.
        "both_quests_date": "",
        "bonus_quest_date": "",
        # Current accumulator charge. Stored rather than derived: the XP math runs on paths with
        # no collection, and refresh_accumulator keeps this current on the paths that have one.
        "accumulator_percent": 0.0,
        # Scheduler day the current ramp began: the unlock, or the last cap raise. It charges from
        # that day, not from the streak's start, so unlocking it mid-streak still ramps up from 1%.
        "accumulator_since_epoch": 0,
        # The charge standing the day before that: 0 at the unlock, the carry at a cap raise. A save
        # from before this key ramped from 0 too, so it needs no migration.
        "accumulator_base_percent": 0.0,
        # The cap the last refresh saw, which is how a raise is noticed. 0 = not looked yet, so a
        # save from before this key keeps the charge it arrives with.
        "accumulator_cap_seen": 0,
        # Running buffs: {"id", "started", "started_epoch", "days"}. Never two for one system.
        "active_buffs": [],
        # Magnets toward the stage in progress, and how many stages are done.
        "magnets": 0,
        "magnet_stage": 0,
        # Scheduler-day epoch of the last quest reroll. 0 means never used.
        "quest_reroll_epoch": 0,
        # Milestones finished but not yet announced, as 1-based ladder indexes. A queue, because
        # not every path that can finish one can show a notification; the next UI path drains it.
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
    """Whether the track is available: level UNLOCK_LEVEL, or any prestige ever (so a prestige never
    re-hides it)."""
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


def _today_epoch(col: Any) -> int:
    """Day epoch of the current scheduler day, or 0 without a readable collection."""
    if col is None:
        return 0
    try:
        return int(streak.today_epoch(col))
    except Exception:
        return 0


def _ensure_active_epoch(data: dict[str, Any], col: Any) -> int:
    """The day the active milestone opened, back-filled once a collection is available. An epoch of
    zero means "no boundary yet", so an existing long streak can't complete milestone #1 the moment
    the track opens."""
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
    """The value `key` has been granted up to across completed milestones, derived from `active`.
    Numbers take the highest granted; anything else takes the last."""
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
    """The accumulator's current contribution, in percent. Clamped on read too, so a charge stored
    under a higher cap can't pay out."""
    cap = accumulator_cap_percent(data)
    if cap <= 0:
        return 0.0
    return max(0.0, min(float(cap), float(get_state(data).get("accumulator_percent", 0.0) or 0.0)))


def refresh(data: dict[str, Any], col: Any = None) -> None:
    """Daily housekeeping: expire finished buffs and recharge the accumulator. Call wherever a
    collection is at hand, since collection-less readers only see what's stored."""
    active_buffs(data, col)
    refresh_accumulator(data, col)


def _stored_number(ms: dict[str, Any], key: str) -> float:
    """A number the save holds, or 0 when a hand-edited one holds something else. Guarded because
    the refresh runs from paths that do not catch, so a bad value would cost the status bar."""
    try:
        return float(ms.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _charge_for_cap(
    ms: dict[str, Any], cap: int, rate: float, streak_days: int, today_ep: int
) -> float:
    """The charge a ceiling produces: min(ceiling, ramp since the start day, streak). Day and streak
    are arguments so a cap raise can ask what yesterday's charge was."""
    since = int(_stored_number(ms, "accumulator_since_epoch"))
    if cap <= 0 or not since or not today_ep:
        return 0.0
    base = _stored_number(ms, "accumulator_base_percent")
    days_since_start = (today_ep - since) // 86400 + 1
    return max(0.0, min(float(cap), base + rate * days_since_start, rate * float(streak_days)))


def _carry_cap_raise(
    ms: dict[str, Any], cap: int, rate: float, streak_days: int, today_ep: int
) -> None:
    """Restart the ramp when the cap rises, carrying what was earned as of yesterday under the old
    cap (wiki: Streak accumulator)."""
    last_cap = int(_stored_number(ms, "accumulator_cap_seen"))
    if cap <= last_cap:
        return
    if last_cap > 0:
        ms["accumulator_base_percent"] = _charge_for_cap(
            ms, last_cap, rate, max(0, streak_days - 1), today_ep - 86400
        )
        ms["accumulator_since_epoch"] = today_ep
    ms["accumulator_cap_seen"] = cap


def refresh_accumulator(data: dict[str, Any], col: Any = None) -> float:
    """Recompute and store the charge from the current streak; returns it. Ramps from the unlock day
    and drops to nothing on a break. Left alone without a collection, or it would write a 0 over
    it."""
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
    # Stamped on the first refresh that sees a cap, so old saves don't arrive pre-charged. Moves
    # back, never forward, so a fast clock can't count negative days.
    since = int(_stored_number(ms, "accumulator_since_epoch"))
    if not since or since > today_ep:
        ms["accumulator_since_epoch"] = today_ep
    rate = accumulator_rate_percent_per_day(data)
    _carry_cap_raise(ms, cap, rate, streak_days, today_ep)
    charge = _charge_for_cap(ms, cap, rate, streak_days, today_ep)
    ms["accumulator_percent"] = charge
    return charge


def buff_drop_percent(data: dict[str, Any]) -> int:
    """Chance the bonus quest also drops a buff. 0 until #4 opens the faucet."""
    return int(granted_value(data, "buff_drop_percent", 0))


def active_buffs(data: dict[str, Any], col: Any = None) -> list[dict[str, Any]]:
    """The buffs running now, pruning expired ones in place. Expiry is in scheduler days, so a buff
    dropping at 23:00 still lasts three studying days."""
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
            # Dropped on a path that could not date it. Back-filled rather than read as "started
            # at the epoch", which would delete a buff the player was just told they had.
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
    """What a gem reward is multiplied by: 1, or 2 while a doubling buff applies. Never 4, so the
    two doubling buffs don't compound."""
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
    """Roll the bonus quest's buff drop; returns the buff started, or None. Picks a free system
    first, then a buff within it, so adding buffs adds variety rather than frequency."""
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
    """Days of the current streak at or after the milestone became active, so a mid-streak player
    need not break it to begin."""
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
    """Record one `kind` event against the active milestone; other objectives' events are dropped,
    which is what starts each counter at zero."""
    ensure_started(data, col)
    if not has_started(data):
        return  # Locked: nothing counts toward a track the player cannot see.
    entry = active_entry(data)
    if entry is None or entry["objective"] != kind or kind in _DERIVED:
        return
    ms = get_state(data)
    ms["active_progress"] = int(ms.get("active_progress", 0) or 0) + int(amount)


def note_both_quests_complete(data: dict[str, Any], col: Any = None) -> None:
    """Count a day on which every daily quest was finished, once per scheduler day. Re-reads the
    pair via `_quests_today`, since an unrolled day still holds yesterday's finished pair."""
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
    """Count today's bonus quest once; True if this call counted it. Keyed separately from
    `cleared_bonus_date` (which undo pops), so undo-and-redo re-pays XP and gold but no buff or
    Magnet."""
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
    """Today's daily quests, or [] when the stored ones are from a day that has already turned
    (possible when `ensure_daily_quests` could not roll)."""
    if data.get("last_date") != today:
        return []
    return data.get("daily_quests") or []


def _seal_activation_day(data: dict[str, Any], col: Any = None) -> None:
    """Seal today out of a newly active milestone's counter when today's quest work is already part
    done, so a day half earned under the previous milestone isn't banked. Stamps the counter's day
    key."""
    entry = active_entry(data)
    if entry is None or entry["objective"] not in (OBJ_BOTH_QUESTS, OBJ_BONUS_QUEST):
        return  # Nothing else counts whole days, so nothing else has a part-spent one to shut out.
    ms = get_state(data)
    today = streak.today_str(col)
    if entry["objective"] == OBJ_BOTH_QUESTS:
        if any(q.get("progress", 0) >= q.get("target", 0) for q in _quests_today(data, today)):
            ms["both_quests_date"] = today
    # `bonus_quest_date` is stamped whenever the bonus quest is counted, so the only day this adds
    # is one cleared while the track was locked.
    elif data.get("cleared_bonus_date") == today:
        ms["bonus_quest_date"] = today


def advance_if_complete(data: dict[str, Any], col: Any = None) -> dict[str, Any] | None:
    """Move to the next milestone if the active one is done; returns the completed entry or None.
    Safe anytime, since streak objectives complete without an event."""
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
    # Queued before the seal: a seal that raised on a malformed save would otherwise consume the
    # milestone without announcing the reward it just paid.
    ms.setdefault("pending_announcements", []).append(index)
    _seal_activation_day(data, col)
    # Recharge now, since the completed milestone may have raised the cap.
    refresh_accumulator(data, col)
    return entry


def take_pending_announcements(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The ladder entries finished since the last announcement, draining the queue so a redraw can't
    announce one twice."""
    ms = get_state(data)
    pending = [i for i in (ms.get("pending_announcements") or []) if 1 <= i <= TRACK_LENGTH]
    if ms.get("pending_announcements"):
        ms["pending_announcements"] = []
    return [LADDER[i - 1] for i in pending]
