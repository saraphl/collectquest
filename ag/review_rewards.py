"""
Shared logic for applying one review to AnkiGame state (desktop or synced from revlog).
Used by __init__.py (_on_answer) and revlog_sync.py (process_synced_revlog).
Quest rewards: rolled at creation — either "1 gem" (random color) or gold (reward_gold); always reward_xp.
Level-up: fixed gold; gem has a chance (not guaranteed).
Undo (Ctrl+Z): reverts review XP, quest XP/gold/gems, level-up gold/gems, and quest progress for that review.
"""
from __future__ import annotations

import random

from . import carry, due_baseline, prestige, quests, shop, streak, unlocks, xp

GOLD_PER_LEVEL_UP = 20
# Quest gold/XP come from the rolled quest (reward_gold, reward_xp). Fallback if missing:
GOLD_PER_QUEST_FALLBACK = 10
LEVEL_UP_GEM_BASE_PERCENT = 15  # base chance for 1 gem on level-up; + luck from collectibles (no cap)
LEVEL_UP_GEM_SECOND_ROLL_FRACTION = 0.20  # 20% of effective chance for a second gem (e.g. 15% → 3%, 39% → 7.8%)
QUEST_LUCK_SCALE = 0.5  # quests give half the luck benefit of a level-up (reduces late-game scaling)
# Again pays this share of a Good answer. Not zero: a lapse is a review done, and paying nothing for
# it rewards misgrading a card you actually failed, which corrupts the scheduler the game sits on.
# Kept small so that failing repeatedly is never a faster way to earn than answering correctly.
AGAIN_XP_RATIO = 0.2
# Hard pays this share of a Good answer, on every difficulty. Hard means the card *was* recalled,
# so paying less than Good is reasonable but paying nothing is not — it just pushes the reviewer to
# press Good instead, which is the one grade the scheduler cannot afford to have lied to it.
HARD_XP_RATIO = 0.5
# Bonus for clearing the day's due cards. Flat, unlike quest rewards: it is paid for finishing the
# workload Anki actually set, which is the same achievement whether the day was 20 cards or 200.
# Item and prestige bonuses deliberately do not apply, so the figure shown in the panel is exactly
# the figure paid. The gem roll does take item luck.
CLEARED_BONUS_XP = 20
CLEARED_BONUS_GOLD = 10
CLEARED_BONUS_GEM_PERCENT = 5
# Shared so the panel row and the completion tooltip name it identically. The panel prefixes it with
# "Bonus: "; the tooltip already says "Quest complete:", which would stutter against a second prefix.
CLEARED_BONUS_LABEL = "Review all due cards"
# Undo buffer: max number of review steps (xp/gold/gems excluding quests) to revert with multiple Ctrl+Z
UNDO_BUFFER_MAX = 30


def review_xp_exact(
    data: dict,
    ease: int,
    base_good_xp: float,
    owned_collectibles: list,
) -> float:
    """
    Exact XP one review pays, before rounding. Pure — safe to call for display.

    Algorithm:
    - Start from a base "Good" XP for the current difficulty (9 / 7.2 / 4.5).
    - Add flat XP from collectibles.
    - Apply a ratio per ease (Again/Hard/Good/Easy).
    - Finally apply XP % bonuses (collectibles + prestige).

    Ease 0, or anything above Easy, falls through to a zero ratio and pays nothing: those are not
    answers the reviewer produces, and revlog_sync already drops ease-0 rows before they get here.
    """
    owned = owned_collectibles or []

    # Flat XP applies to every answer, Again included, so that AGAIN_XP_RATIO really is that share
    # of what the same card pays on Good rather than a share of only part of it.
    flat_bonus = shop.xp_flat(owned)

    base = base_good_xp + flat_bonus
    if base <= 0:
        return 0.0

    # Ratios are relative to Good and identical on every difficulty; difficulty enters only through
    # base_good_xp, so it scales the whole ladder rather than reshaping it.
    if ease == 1:  # Again
        ratio = AGAIN_XP_RATIO
    elif ease == 2:  # Hard
        ratio = HARD_XP_RATIO
    elif ease == 3:  # Good
        ratio = 1.0
    elif ease == 4:  # Easy
        ratio = 1.2
    else:
        ratio = 0.0
    if ratio <= 0:
        return 0.0

    bonus_pct = shop.xp_bonus_percent(owned) + prestige.prestige_xp_bonus_percent(data)
    return base * ratio * (1 + bonus_pct / 100)


def _apply_xp_bonus(data: dict, ease: int, base_good_xp: float, owned_collectibles: list) -> int:
    """
    Grant review XP through the carry. Mutates data — use review_xp_exact to preview.

    The ratio and the percentage are multiplied out in full and rounded once, by the carry in
    ag/carry.py. Rounding each step separately would drop both fractions: Hard on Steady is
    7.2 * 0.5 = 3.6, and truncating that would pay 3 every time.
    """
    return carry.award(
        data, carry.XP_KEY, review_xp_exact(data, ease, base_good_xp, owned_collectibles)
    )


def quest_xp_exact(data: dict, quest_xp: int, owned_collectibles: list) -> float:
    """
    Exact XP a quest pays: flat XP first, then the XP % bonus (same formula as reviews).

    Pure — safe to call for display. The paired _apply_* function below is the one that grants it
    and moves the carry; calling that one to preview a reward would spend the player's carry.
    """
    owned = owned_collectibles or []
    # Flat bonus (always applies to quests)
    flat_bonus = shop.xp_flat(owned)
    xp_with_flat = quest_xp + flat_bonus
    # Percentage bonus (same as reviews - no separate quest %)
    xp_bonus = shop.xp_bonus_percent(owned) + prestige.prestige_xp_bonus_percent(data)
    return xp_with_flat * (1 + xp_bonus / 100)


def quest_gold_exact(data: dict, base_gold: float, owned_collectibles: list) -> float:
    """
    Exact gold a quest pays. Pure — safe to call for display.

    Quests get half the flat bonus so their gold scales without matching level-up gold, and the
    half is kept exact: rounding it here would lose 0.5 on an odd bonus before the carry saw it.
    """
    owned = owned_collectibles or []
    bonus_pct = shop.gold_bonus_percent(owned) + prestige.prestige_gold_bonus_percent(data)
    return (base_gold + shop.gold_flat(owned) / 2) * (1 + bonus_pct / 100)


def preview_whole(exact: float) -> int:
    """
    Round an exact reward for display. Never touches the carry.

    The amount actually granted varies by one either side as the carry fills, so the nearest whole
    number is the honest single figure to show.
    """
    return int(round(exact))


def _apply_quest_xp_bonus(data: dict, quest_xp: int, owned_collectibles: list) -> int:
    """Grant quest XP through the carry. Mutates data — use quest_xp_exact to preview."""
    return carry.award(data, carry.XP_KEY, quest_xp_exact(data, quest_xp, owned_collectibles))


def _apply_gold_bonus(data: dict, base_gold: float, owned_collectibles: list) -> int:
    """Grant gold through the carry. Mutates data — use quest_gold_exact to preview quest gold."""
    bonus_pct = shop.gold_bonus_percent(owned_collectibles or []) + prestige.prestige_gold_bonus_percent(data)
    return carry.award(data, carry.GOLD_KEY, base_gold * (1 + bonus_pct / 100))


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


def _roll_gem_color(chance_percent: float) -> str | None:
    """Roll a gem at the given percentage chance. Returns a gem color, or None for no gem."""
    if chance_percent <= 0:
        return None
    if random.randint(0, 99) < chance_percent:
        return random.choice([c for c, _ in shop.GEM_COLORS])
    return None


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
    return _roll_gem_color(chance)


def _award_cleared_bonus(data: dict, owned: list, col, earned: dict) -> tuple[int, int]:
    """
    Pay the bonus for finishing the day's due cards. Returns (xp, gold) paid, or (0, 0) if not.

    The amounts are returned rather than left for the caller to re-derive from the constants, so the
    payout and the undo deltas recorded against it cannot drift apart.

    Fires at most once per scheduler day, guarded by cleared_bonus_date. Completion is measured by
    due_baseline.cleared_progress, which counts finished review cards — new cards neither advance it
    nor hold it back. The gem roll is stored under its own date key that undo does not clear, so
    undoing and redoing the last card cannot re-roll it.
    """
    if col is None:
        return (0, 0)
    today = streak.today_str(col)
    if data.get("cleared_bonus_date") == today:
        return (0, 0)
    progress = due_baseline.cleared_progress(data, col)
    if progress is None or progress[0] < progress[1]:
        return (0, 0)

    data["cleared_bonus_date"] = today
    data["total_xp"] = data.get("total_xp", 0) + CLEARED_BONUS_XP
    data["money"] = data.get("money", 0) + CLEARED_BONUS_GOLD
    earned["gold_earned"] += CLEARED_BONUS_GOLD

    if data.get("cleared_bonus_gem_date") != today:
        data["cleared_bonus_gem_date"] = today
        data["cleared_bonus_gem_color"] = _roll_gem_color(
            CLEARED_BONUS_GEM_PERCENT + shop.luck_gem_chance_percent(owned or [])
        )
    gem_color = data.get("cleared_bonus_gem_color")
    if gem_color:
        data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), gem_color)
        earned["gem_earned"] += 1

    # Reported as a completed quest so the caller's one-tooltip-per-answer message picks it up with
    # no special case: its gold and gem are already in earned, so only the XP needs naming here.
    earned["completed_quests"].append((CLEARED_BONUS_LABEL, CLEARED_BONUS_XP))
    return (CLEARED_BONUS_XP, CLEARED_BONUS_GOLD)


def apply_one_review(
    data: dict,
    ease: int,
    deck_name: str | None = None,
    is_new: bool = False,
    col=None,
) -> dict:
    """
    Apply one review to state: quest progress, XP, gold, gems, level, unlocks.
    Modifies data in place. Caller must storage.save(data) after.
    col: optional collection for 7-day streak rollover (revlog check).
    Returns {"gold_earned": int, "gem_earned": int, "completed_quests": [...], "undo_deltas": ...}.
    """
    earned = {
        "gold_earned": 0,
        "gem_earned": 0,
        "completed_quests": [],
        "leveled_up": False,
    }
    gems_before = dict(data.get("gems", shop.default_gems()))
    # The fractional carries move with every award, so undo has to put back the exact values from
    # before this answer; subtracting whole XP and gold alone would let them drift.
    xp_fraction_before = carry.get(data, carry.XP_KEY)
    gold_fraction_before = carry.get(data, carry.GOLD_KEY)
    xp_delta = 0
    gold_delta = 0

    # Undo reverts review XP + level-up gold/gems + quest rewards (XP, gold or gem) and quest progress.
    undo_xp = 0
    undo_gold = 0

    old_level = data.get("level", 1)
    # Streak rewards are granted centrally in the UI refresh flow (streak.maybe_grant_streak_reward),
    # not here; on_review's middle return value is always None.
    completed_quests, _, quest_progress_revert = quests.on_review(
        data,
        ease,
        deck_name=deck_name,
        is_new=is_new,
        col=col,
    )
    # Base "Good" XP for the current difficulty; _apply_xp_bonus scales it by ease.
    base_good = xp.xp_for_review(3)
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
    for q in completed_quests:
        base_quest_xp = q.get("reward_xp", 0)
        quest_xp = _apply_quest_xp_bonus(data, base_quest_xp, owned)
        data["total_xp"] = data.get("total_xp", 0) + quest_xp
        xp_delta += quest_xp
        undo_xp += quest_xp
        if q.get("reward_gem"):
            color = q.get("reward_gem_color")
            gems = data.get("gems", shop.default_gems())
            data["gems"] = shop.award_gem_of_color(gems, color) if color else shop.award_random_gem(gems)
            earned["gem_earned"] += 1
        else:
            base_gold = q.get("reward_gold", GOLD_PER_QUEST_FALLBACK)
            gold = carry.award(data, carry.GOLD_KEY, quest_gold_exact(data, base_gold, owned))
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
        # Reported back to the caller rather than drawn here: the caller composes one tooltip for
        # the whole answer, and this module stays free of UI. The label is resolved rather than read
        # straight off the quest so a deck renamed mid-day is named the same way the panel names it.
        earned["completed_quests"].append((quests.quest_display_label(q, col), quest_xp))

    # Cleared-all-due bonus. Checked after quests so the level recomputed below covers it too.
    bonus_xp, bonus_gold = _award_cleared_bonus(data, owned, col, earned)
    cleared_bonus_awarded = bool(bonus_xp or bonus_gold)
    xp_delta += bonus_xp
    undo_xp += bonus_xp
    gold_delta += bonus_gold
    undo_gold += bonus_gold

    new_level = xp.level_from_total_xp(data["total_xp"])
    data["level"] = new_level
    gems_before_level_up = dict(data.get("gems", shop.default_gems()))
    if new_level > old_level:
        # Reported so the caller can name the cause instead of inferring it from "gold with no
        # quest", which would mislabel any other source of gold that appears later.
        earned["leveled_up"] = True
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
        "xp_fraction_before": xp_fraction_before,
        "gold_delta": undo_gold,
        "gold_fraction_before": gold_fraction_before,
        # Undoing the answer that emptied the queue un-empties it, so the day's bonus is released to
        # be earned again. The gem roll is kept, so a redo cannot reroll it.
        "cleared_bonus_awarded": cleared_bonus_awarded,
        "gems_delta": undo_gems_delta,
        "quest_progress_revert": quest_progress_revert,  # every quest this answer advanced
        "was_correct": ease >= 3,  # only Good/Easy count as correct for correct_today
        "counted_as_review": ease > 1,  # not Again: revert reviews_today on undo
    }
    return earned
