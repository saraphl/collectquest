"""
Shared logic for applying one review to AnkiGame state (desktop or synced from revlog).
Used by __init__.py (_on_answer) and revlog_sync.py (process_synced_revlog).
Quest rewards: rolled at creation — either "1 gem" (random color) or gold (reward_gold); always reward_xp.
Level-up: fixed gold; gem has a chance (not guaranteed).
Undo (Ctrl+Z): reverts review XP, quest XP/gold/gems, level-up gold/gems, and quest progress for that review.
"""
from __future__ import annotations

import random

from . import prestige, quests, storage, shop, unlocks, xp

GOLD_PER_LEVEL_UP = 20
# Quest gold/XP come from the rolled quest (reward_gold, reward_xp). Fallback if missing:
GOLD_PER_QUEST_FALLBACK = 10
LEVEL_UP_GEM_BASE_PERCENT = 15  # base chance for 1 gem on level-up; + luck from collectibles (no cap)
LEVEL_UP_GEM_SECOND_ROLL_FRACTION = 0.20  # 20% of effective chance for a second gem (e.g. 15% → 3%, 39% → 7.8%)
QUEST_LUCK_SCALE = 0.5  # quests give half the luck benefit of a level-up (reduces late-game scaling)
# Undo buffer: max number of review steps (xp/gold/gems excluding quests) to revert with multiple Ctrl+Z
UNDO_BUFFER_MAX = 30


def _apply_xp_bonus(
    data: dict,
    ease: int,
    base_good_xp: int,
    owned_collectibles: list,
) -> int:
    """
    Apply XP for one review using difficulty ratios that stay consistent even
    when flat XP and % bonuses grow.

    Algorithm:
    - Start from a base "Good" XP for the current difficulty (e.g. 10/8/5).
    - Add flat XP from collectibles.
    - Apply a ratio per ease (Again/Hard/Good/Easy) that depends on difficulty.
    - Finally apply XP % bonuses (collectibles + prestige).
    """
    owned = owned_collectibles or []

    # Flat XP always applies except to Again.
    flat_bonus = 0
    if ease >= 2:
        flat_bonus = shop.xp_flat(owned)

    base = base_good_xp + flat_bonus
    if base <= 0 or ease <= 1:
        xp_raw = 0
    else:
        diff = xp.get_difficulty()
        # Ratios are relative to Good for each difficulty.
        if ease == 2:  # Hard
            if diff == "easy":       # Casual
                ratio = 0.8
            elif diff == "normal":   # Steady
                ratio = 0.6
            else:                    # hard / Heavy User
                ratio = 0.0
        elif ease == 3:  # Good
            ratio = 1.0
        elif ease == 4:  # Easy
            ratio = 1.2
        else:
            ratio = 0.0
        xp_raw = int(base * ratio)

    if xp_raw <= 0:
        return 0

    bonus_pct = shop.xp_bonus_percent(owned) + prestige.prestige_xp_bonus_percent(data)
    if bonus_pct <= 0:
        return xp_raw
    return int(xp_raw * (1 + bonus_pct / 100))


def _apply_quest_xp_bonus(data: dict, quest_xp: int, owned_collectibles: list) -> int:
    """Apply flat XP first, then XP % bonus (same formula as reviews)."""
    owned = owned_collectibles or []
    # Flat bonus (always applies to quests)
    flat_bonus = shop.xp_flat(owned)
    xp_with_flat = quest_xp + flat_bonus
    # Percentage bonus (same as reviews - no separate quest %)
    xp_bonus = shop.xp_bonus_percent(owned) + prestige.prestige_xp_bonus_percent(data)
    return int(xp_with_flat * (1 + xp_bonus / 100))


def _apply_gold_bonus(data: dict, base_gold: int, owned_collectibles: list) -> int:
    bonus_pct = shop.gold_bonus_percent(owned_collectibles or []) + prestige.prestige_gold_bonus_percent(data)
    if bonus_pct <= 0:
        return base_gold
    return int(base_gold * (1 + bonus_pct / 100))


def grant_single_quest_reward(data: dict, q: dict) -> None:
    """
    Grant the reward for a single quest (XP + gold or gem). Updates data in place.
    Used by admin 'Validate one quest'. Caller must set q["progress"] = q["target"] and storage.save(data).
    """
    owned = data.get("owned_collectibles", [])
    base_quest_xp = q.get("reward_xp", 0)
    quest_xp = _apply_quest_xp_bonus(data, base_quest_xp, owned)
    data["total_xp"] = data.get("total_xp", 0) + quest_xp
    if q.get("reward_gem"):
        color = q.get("reward_gem_color")
        gems = data.get("gems", shop.default_gems())
        data["gems"] = shop.award_gem_of_color(gems, color) if color else shop.award_random_gem(gems)
    else:
        base_gold = q.get("reward_gold", GOLD_PER_QUEST_FALLBACK)
        flat_for_quest = shop.gold_flat(owned) // 2  # half flat so quest gold scales with items
        gold = _apply_gold_bonus(base_gold + flat_for_quest, owned)
        data["money"] = data.get("money", 0) + gold
    # Luck gem: same as apply_one_review — roll once per completion, store on quest
    if not q.get("reward_luck_gem_rolled"):
        q["reward_luck_gem_rolled"] = True
        q["reward_luck_gem_color"] = _roll_quest_luck_gem_color(data, owned)
    if q.get("reward_luck_gem_color"):
        data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), q["reward_luck_gem_color"])
    data["level"] = xp.level_from_total_xp(data["total_xp"])
    unlocked_list = data.get("unlocked", [])
    for img_name, _ in unlocks.newly_unlocked(data["level"], unlocked_list):
        if img_name not in unlocked_list:
            unlocked_list.append(img_name)
    data["unlocked"] = unlocked_list


def _roll_level_up_gem_colors(owned: list, level: int) -> list[str]:
    """Roll level-up gems (guaranteed every 5 levels + luck). Returns list of gem colors to award. Used so we can store roll for undo/re-level."""
    colors: list[str] = []
    gem_choices = [c for c, _ in shop.GEM_COLORS]
    if level % 5 == 0:
        colors.append(random.choice(gem_choices))
    effective_chance = LEVEL_UP_GEM_BASE_PERCENT + shop.luck_gem_chance_percent(owned)
    if random.randint(0, 99) < effective_chance:
        colors.append(random.choice(gem_choices))
        if random.random() < (effective_chance * LEVEL_UP_GEM_SECOND_ROLL_FRACTION / 100.0):
            colors.append(random.choice(gem_choices))
    return colors


def _roll_quest_luck_gem_color(data: dict, owned: list) -> str | None:
    """
    Roll the bonus gem for one quest completion. Returns a gem color, or None for no gem.
    Chance = luck from collectibles (scaled down, see QUEST_LUCK_SCALE) + the "daily quest rewards"
    bonus from collectibles and prestige. That bonus is added, not multiplied, so items like
    Dragon Tooth still do something for a player who owns no luck items.
    Call once per completion and store the result on the quest so undo doesn't reroll it.
    """
    chance = shop.luck_gem_chance_percent(owned or []) * QUEST_LUCK_SCALE
    chance += shop.quest_reward_bonus_percent(owned or [])
    chance += prestige.prestige_quest_reward_bonus_percent(data)
    if chance <= 0:
        return None
    if random.randint(0, 99) < chance:
        return random.choice([c for c, _ in shop.GEM_COLORS])
    return None


def apply_one_review(
    data: dict,
    ease: int,
    show_quest_tooltip: bool = False,
    deck_name: str | None = None,
    is_new: bool = False,
    fixed_xp: int | None = None,
    col=None,
) -> dict:
    """
    Apply one review to state: quest progress, XP, gold, gems, level, unlocks.
    Modifies data in place. Caller must storage.save(data) after.
    fixed_xp: when set, use this instead of xp_for_review(ease). Optional; sync uses actual revlog ease.
    col: optional collection for 7-day streak rollover (revlog check).
    Returns {"gold_earned": int, "gem_earned": int, "streak_reward": {...}|None, "undo_deltas": ...}.
    """
    earned = {"gold_earned": 0, "gem_earned": 0, "streak_reward": None}
    gems_before = dict(data.get("gems", shop.default_gems()))
    xp_delta = 0
    gold_delta = 0

    # Undo reverts review XP + level-up gold/gems + quest rewards (XP, gold or gem) and quest progress.
    undo_xp = 0
    undo_gold = 0
    prev_quest_progress = [q.get("progress", 0) for q in data.get("daily_quests", [])]

    old_level = data.get("level", 1)
    completed_quests, streak_reward, quest_progress_revert = quests.on_review(
        data,
        ease,
        deck_name=deck_name,
        is_new=is_new,
        fixed_xp=fixed_xp,
        col=col,
    )
    if streak_reward:
        earned["streak_reward"] = streak_reward
        if streak_reward.get("type") == "gem":
            earned["gem_earned"] = earned.get("gem_earned", 0) + streak_reward.get("amount", 1)
            extra_gold = streak_reward.get("gold", 0)
            if extra_gold:
                gold_delta += extra_gold
                earned["gold_earned"] = earned.get("gold_earned", 0) + extra_gold
        elif streak_reward.get("type") == "gold":
            gold_delta += streak_reward.get("amount", 0)
            earned["gold_earned"] = earned.get("gold_earned", 0) + streak_reward.get("amount", 0)
        # Undo must revert streak XP/gold (gems already in gems_delta)
        if streak_reward.get("type") == "xp":
            undo_xp += streak_reward.get("amount", 0)
        elif streak_reward.get("type") == "gold":
            undo_xp += streak_reward.get("xp", 0)
    # Base "Good" XP for the current difficulty (fixed_xp for sync, else xp_for_review on Good).
    base_good = fixed_xp if fixed_xp is not None else xp.xp_for_review(3)
    gained = _apply_xp_bonus(
        data,
        ease,
        base_good,
        data.get("owned_collectibles", []),
    )
    data["total_xp"] = data.get("total_xp", 0) + gained
    xp_delta += gained
    undo_xp += gained
    owned = data.get("owned_collectibles", [])
    daily_quests = data.get("daily_quests", [])
    completed_quest_progress: list[tuple[int, int]] = []  # (index, progress_before) for undo
    for q in completed_quests:
        base_quest_xp = q.get("reward_xp", 0)
        quest_xp = _apply_quest_xp_bonus(data, base_quest_xp, owned)
        data["total_xp"] = data.get("total_xp", 0) + quest_xp
        xp_delta += quest_xp
        undo_xp += quest_xp
        # Index for undo (revert progress)
        try:
            qidx = next(i for i, dq in enumerate(daily_quests) if dq is q)
            completed_quest_progress.append((qidx, prev_quest_progress[qidx]))
        except StopIteration:
            pass
        if q.get("reward_gem"):
            color = q.get("reward_gem_color")
            gems = data.get("gems", shop.default_gems())
            data["gems"] = shop.award_gem_of_color(gems, color) if color else shop.award_random_gem(gems)
            earned["gem_earned"] += 1
        else:
            base_gold = q.get("reward_gold", GOLD_PER_QUEST_FALLBACK)
            flat_for_quest = shop.gold_flat(owned) // 2  # half flat so quest gold scales
            gold = _apply_gold_bonus(data, base_gold + flat_for_quest, owned)
            data["money"] = data.get("money", 0) + gold
            gold_delta += gold
            undo_gold += gold
            earned["gold_earned"] += gold
        # Luck gem: roll once per completion and store on quest so undo doesn't reroll (same "get a gem or not" + color)
        if not q.get("reward_luck_gem_rolled"):
            q["reward_luck_gem_rolled"] = True
            q["reward_luck_gem_color"] = _roll_quest_luck_gem_color(data, owned)
        luck_color = q.get("reward_luck_gem_color")
        if luck_color:
            data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), luck_color)
            earned["gem_earned"] += 1
        if show_quest_tooltip:
            from . import ui
            ui.show_quest_completed_tooltip(q.get("label", "Quest"), quest_xp)
    new_level = xp.level_from_total_xp(data["total_xp"])
    data["level"] = new_level
    gems_before_level_up = dict(data.get("gems", shop.default_gems()))
    if new_level > old_level:
        # Level-up gold: base + flat bonus from items, then apply percentage bonus
        flat_bonus = shop.gold_flat(owned)
        gold = _apply_gold_bonus(data, GOLD_PER_LEVEL_UP + flat_bonus, owned)
        data["money"] = data.get("money", 0) + gold
        gold_delta += gold
        undo_gold += gold
        earned["gold_earned"] += gold
        # Gems: use stored roll if re-reaching same level (e.g. after Ctrl+Z), else roll and store
        stored = data.get("last_level_up_roll") or {}
        if stored.get("level") == new_level:
            gem_colors = stored.get("gems") or []
        else:
            gem_colors = _roll_level_up_gem_colors(owned, new_level)
            data["last_level_up_roll"] = {"level": new_level, "gems": gem_colors}
        for color in gem_colors:
            data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), color)
            earned["gem_earned"] += 1
    unlocked_list = data.get("unlocked", [])
    for img_name, _ in unlocks.newly_unlocked(new_level, unlocked_list):
        if img_name not in unlocked_list:
            unlocked_list.append(img_name)
    data["unlocked"] = unlocked_list

    # Undo deltas: review XP + quest XP, level-up + quest gold, level-up + quest gems; plus quest progress revert.
    gems_after = data.get("gems", shop.default_gems())
    colors = list(shop.default_gems().keys())
    undo_gems_delta = {
        c: gems_after.get(c, 0) - gems_before.get(c, 0)
        for c in colors
    }
    earned["undo_deltas"] = {
        "xp_delta": undo_xp,
        "gold_delta": undo_gold,
        "gems_delta": undo_gems_delta,
        "completed_quest_progress": completed_quest_progress,
        "quest_progress_revert": quest_progress_revert,  # all review/session/deck/new progress for undo
        "was_correct": ease >= 3,  # only Good/Easy count as correct for correct_today
        "counted_as_review": ease > 1,  # not Again: revert reviews_today on undo
    }
    return earned
