"""Prestige math and helpers (points, upgrades, bonuses)."""
from __future__ import annotations

from typing import Any, Dict

from . import milestones, quests, shop, storage, xp

PRESTIGE_MIN_LEVEL = 50
# What a prestige pays at the unlock level, and how many levels above it buy each extra point. Every
# payout quote derives from these.
PRESTIGE_POINTS_AT_UNLOCK = 2
LEVELS_PER_EXTRA_POINT = 10
START_GOLD_PER_LEVEL = 100
# Each level of the XP bonus / gold bonus upgrade adds this much percent.
UPGRADE_STEP_PERCENT = 30
# Percent of Gem luck per upgrade level (the `quest_reward` key predates the gem merge). Matches the
# step above, but kept separate as it prices a different stat.
QUEST_REWARD_STEP_PERCENT = 30
# Percent of 7-day streak rewards per Streak reward level.
STREAK_STEP_PERCENT = 40
# Percent of dungeon discovery / exploration per level of either dungeon upgrade.
DUNGEON_STEP_PERCENT = 20
# Gems of every color the first trade for an extra prestige point takes; each later one in the run
# takes one more.
GEM_TRADE_EACH = 3


def prestige_points_gain(level: int) -> int:
    """Points gained when prestiging at this level (0 below the threshold):
    PRESTIGE_POINTS_AT_UNLOCK, plus one per LEVELS_PER_EXTRA_POINT above it (50 → 2, 60 → 3)."""
    if level < PRESTIGE_MIN_LEVEL:
        return 0
    return PRESTIGE_POINTS_AT_UNLOCK + (level - PRESTIGE_MIN_LEVEL) // LEVELS_PER_EXTRA_POINT


def levels_to_next_point(level: int) -> int:
    """Levels still to climb before the payout rises by one, or 0 when there's nothing to announce
    (including exactly on a step). Below the threshold it counts to the unlock level; above, steps
    count from the unlock level."""
    if level < PRESTIGE_MIN_LEVEL:
        return PRESTIGE_MIN_LEVEL - level
    past_step = (level - PRESTIGE_MIN_LEVEL) % LEVELS_PER_EXTRA_POINT
    return (LEVELS_PER_EXTRA_POINT - past_step) % LEVELS_PER_EXTRA_POINT


def prestige_item_points(level: int, owned_ids: list[str]) -> int:
    """Extra points the collection grants for a prestige at this level; zero below the threshold.
    Kept out of prestige_points_gain so a tome can never make a player eligible. owned_ids is
    required, so forgetting it fails loudly."""
    if prestige_points_gain(level) <= 0:
        return 0
    return shop.prestige_bonus_points(owned_ids)


def total_prestige_points_gain(level: int, owned_ids: list[str]) -> int:
    """Points actually paid out for a prestige at this level: level payout plus item bonuses."""
    return prestige_points_gain(level) + prestige_item_points(level, owned_ids)


def can_prestige(level: int) -> bool:
    """True if player can prestige in normal flow (non-admin)."""
    return prestige_points_gain(level) > 0


# Every upgrade, in the prestige window's order. A new upgrade is a row here plus the function that
# applies it; saves store only the levels bought, so a missing key reads as level 0.
UPGRADES: tuple[dict[str, Any], ...] = (
    {"key": "xp_percent", "title": "XP bonus", "effect": f"+{UPGRADE_STEP_PERCENT}% XP",
     "step": UPGRADE_STEP_PERCENT, "unit": "%"},
    {"key": "gold_percent", "title": "Gold bonus", "effect": f"+{UPGRADE_STEP_PERCENT}% gold",
     "step": UPGRADE_STEP_PERCENT, "unit": "%"},
    {"key": "quest_reward", "title": "Gem luck",
     "effect": f"+{QUEST_REWARD_STEP_PERCENT}% gem luck", "step": QUEST_REWARD_STEP_PERCENT, "unit": "%"},
    {"key": "start_gold", "title": "Starting gold",
     "effect": f"+{START_GOLD_PER_LEVEL} gold from the start",
     "step": START_GOLD_PER_LEVEL, "unit": "g", "starting": True},  # under Starting boosts
    {"key": "streak_bonus", "title": "Streak reward",
     "effect": f"+{STREAK_STEP_PERCENT}% 7-day streak rewards",
     "step": STREAK_STEP_PERCENT, "unit": "%"},
    {"key": "dungeon_discover", "title": "Dungeon discovery",
     "effect": f"+{DUNGEON_STEP_PERCENT}% chance to find a dungeon",
     "step": DUNGEON_STEP_PERCENT, "unit": "%"},
    {"key": "dungeon_explore", "title": "Dungeon exploration",
     "effect": f"+{DUNGEON_STEP_PERCENT}% faster dungeon exploration",
     "step": DUNGEON_STEP_PERCENT, "unit": "%"},
)


# One-time unlocks, bought once at a flat cost and kept for good. "item" is a collectible granted at
# the start of every run; "requires" is an unlock that must be bought first.
UNLOCKS: tuple[dict[str, Any], ...] = (
    {"key": "bronze_key", "title": "Bronze key", "effect": "Manual shop restock from the start",
     "cost": 5, "item": shop.KEY_BRONZE_ID},
    {"key": "silver_key", "title": "Silver key", "effect": "4 → 2h restock from the start",
     "cost": 10, "item": shop.KEY_SILVER_ID, "requires": "bronze_key"},
)


def owned_unlocks(state: Dict[str, Any]) -> set[str]:
    """Keys of the one-time unlocks bought."""
    unlocks = state.get("prestige_unlocks") or []
    return set(unlocks) if isinstance(unlocks, list) else set()


def unlock_available(state: Dict[str, Any], unlock: dict[str, Any]) -> bool:
    """True once the unlock it requires, if any, is bought."""
    required = unlock.get("requires")
    return required is None or required in owned_unlocks(state)


def grant_unlock_items(state: Dict[str, Any]) -> None:
    """Add every bought unlock's item the run doesn't hold yet. An unlock whose requirement wasn't
    granted is skipped, so a key never arrives without the one below it."""
    owned_items = state.get("owned_collectibles") or []
    state["owned_collectibles"] = owned_items
    bought = owned_unlocks(state)
    granted: set[str] = set()
    for unlock in UNLOCKS:  # requirements come first
        required = unlock.get("requires")
        if unlock["key"] not in bought or (required is not None and required not in granted):
            continue
        granted.add(unlock["key"])
        item = unlock.get("item")
        if item and item not in owned_items:
            owned_items.append(item)


def buy_unlock(state: Dict[str, Any], key: str) -> bool:
    """Buy a one-time unlock; its item is granted at once. False if unknown, owned, locked or
    unaffordable."""
    unlock = next((u for u in UNLOCKS if u["key"] == key), None)
    if unlock is None or key in owned_unlocks(state) or not unlock_available(state, unlock):
        return False
    if not spend_prestige_points(state, unlock["cost"]):
        return False
    state["prestige_unlocks"] = sorted(owned_unlocks(state) | {key})
    grant_unlock_items(state)
    return True


def upgrade_levels(state: Dict[str, Any]) -> Dict[str, int]:
    """Level bought of every upgrade, by key; 0 for any the save doesn't hold."""
    ups = state.get("prestige_upgrades") or {}
    if not isinstance(ups, dict):
        ups = {}
    # Ensure keys exist
    return {u["key"]: int(ups.get(u["key"], 0) or 0) for u in UPGRADES}


def prestige_xp_bonus_percent(state: Dict[str, Any]) -> int:
    """Total XP bonus % from prestige upgrades."""
    ups = upgrade_levels(state)
    return UPGRADE_STEP_PERCENT * ups["xp_percent"]


def prestige_gold_bonus_percent(state: Dict[str, Any]) -> int:
    """Total gold bonus % from prestige upgrades."""
    ups = upgrade_levels(state)
    return UPGRADE_STEP_PERCENT * ups["gold_percent"]


def prestige_start_gold_bonus(state: Dict[str, Any]) -> int:
    """Extra starting gold from prestige upgrades."""
    ups = upgrade_levels(state)
    return START_GOLD_PER_LEVEL * ups["start_gold"]


def prestige_streak_multiplier(state: Dict[str, Any]) -> float:
    """Multiplier for 7-day streak rewards (XP, gold, gems): +STREAK_STEP_PERCENT per streak_bonus
    level (x1, x1.4, x1.8, …)."""
    ups = upgrade_levels(state)
    lvl = max(0, ups.get("streak_bonus", 0))
    return 1.0 + STREAK_STEP_PERCENT * lvl / 100


def prestige_quest_reward_bonus_percent(state: Dict[str, Any]) -> int:
    """Total quest reward bonus % from prestige upgrades."""
    ups = upgrade_levels(state)
    return QUEST_REWARD_STEP_PERCENT * ups["quest_reward"]


def prestige_dungeon_discover_percent(state: Dict[str, Any]) -> int:
    """Chance to find a dungeon % from prestige upgrades."""
    return DUNGEON_STEP_PERCENT * upgrade_levels(state)["dungeon_discover"]


def prestige_dungeon_explore_percent(state: Dict[str, Any]) -> int:
    """Faster dungeon exploration % from prestige upgrades."""
    return DUNGEON_STEP_PERCENT * upgrade_levels(state)["dungeon_explore"]


def available_prestige_points(state: Dict[str, Any]) -> int:
    """Points available to spend in the prestige shop."""
    total = int(state.get("prestige_points_total", 0) or 0)
    spent = int(state.get("prestige_points_spent", 0) or 0)
    avail = total - spent
    return max(0, avail)


def upgrade_cost(current_level: int) -> int:
    """Cost in prestige points for the next level of an upgrade."""
    base_cost = 1
    return base_cost + max(0, int(current_level))


def spend_prestige_points(state: Dict[str, Any], cost: int) -> bool:
    """Spend prestige points if available. Returns True on success."""
    if cost <= 0:
        return True
    total = int(state.get("prestige_points_total", 0) or 0)
    spent = int(state.get("prestige_points_spent", 0) or 0)
    if spent + cost > total:
        return False
    state["prestige_points_spent"] = spent + cost
    return True


def buy_upgrade(state: Dict[str, Any], key: str) -> bool:
    """Buy the next level of one upgrade; starting gold also pays out at once. False if unaffordable."""
    ups = state.get("prestige_upgrades") or {}
    level = int(ups.get(key, 0) or 0)
    if not spend_prestige_points(state, upgrade_cost(level)):
        return False
    ups[key] = level + 1
    state["prestige_upgrades"] = ups
    if key == "start_gold":
        state["money"] = state.get("money", 0) + START_GOLD_PER_LEVEL
    return True


def gem_trade_each(state: Dict[str, Any]) -> int:
    """Gems of every color the next trade takes. Pending points reset on prestige, and so does this."""
    return GEM_TRADE_EACH + int(state.get("pending_prestige_points_from_gems", 0) or 0)


def can_trade_gems(state: Dict[str, Any]) -> bool:
    gems = state.get("gems", shop.default_gems())
    each = gem_trade_each(state)
    return all((gems.get(c, 0) or 0) >= each for c, _ in shop.GEM_COLORS)


def trade_gems_for_point(state: Dict[str, Any]) -> bool:
    """Spend gem_trade_each of every color for a point paid out at the next prestige."""
    if not can_trade_gems(state):
        return False
    each = gem_trade_each(state)
    gems = state.get("gems", shop.default_gems())
    for c, _ in shop.GEM_COLORS:
        gems[c] = max(0, (gems.get(c, 0) or 0) - each)
    state["gems"] = gems
    state["pending_prestige_points_from_gems"] = (
        int(state.get("pending_prestige_points_from_gems", 0) or 0) + 1
    )
    return True


def perform_prestige(col: Any = None, force: bool = False) -> bool:
    """Bank this run's points and save a fresh run that keeps prestige meta and the milestone track.
    Returns False, saving nothing, when there is nothing to gain and not forced."""
    data = storage.load()
    # From total_xp, so preview and actual gain use the same level.
    level = xp.level_from_total_xp(int(data.get("total_xp", 0) or 0))
    gain = total_prestige_points_gain(level, data.get("owned_collectibles") or [])
    if not force and gain <= 0:
        return False
    pending_from_gems = int(data.get("pending_prestige_points_from_gems", 0) or 0)
    new_state = storage._default_state()
    new_state["total_xp"] = 0
    new_state["level"] = 1
    new_state["prestige_count"] = (data.get("prestige_count", 0) or 0) + 1
    new_state["prestige_points_total"] = (
        int(data.get("prestige_points_total", 0) or 0) + max(0, gain) + pending_from_gems
    )
    new_state["prestige_points_spent"] = int(data.get("prestige_points_spent", 0) or 0)
    new_state["prestige_upgrades"] = data.get("prestige_upgrades") or {}
    new_state["prestige_unlocks"] = sorted(owned_unlocks(data))
    grant_unlock_items(new_state)
    # The track persists (two objectives ask for prestiges), so the prestige is counted on the kept
    # state. No collection: streak fields are still defaults, and a recharge would write a 0-day charge.
    if isinstance(data.get("milestones"), dict):
        new_state["milestones"] = data["milestones"]
    milestones.note_event(new_state, milestones.OBJ_PRESTIGE)
    milestones.advance_if_complete(new_state)
    # Settings a wipe keeps plus what a prestige keeps on top; see storage.
    storage.carry_prestige_keys(data, new_state)
    new_state["money"] = new_state.get("money", 0) + prestige_start_gold_bonus(new_state)
    try:
        quests.ensure_daily_quests(new_state, col=col)
    except Exception:
        pass
    storage.save(new_state)
    return True
