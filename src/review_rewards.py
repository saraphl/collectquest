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
# The bonus quest: clearing every card Anki had due. Its target comes from the day rather than from
# a random band, so these are fixed where the rolled quests' rewards are not — but they are still
# only base figures. Item and prestige bonuses scale all three exactly as they scale the two rolled
# quests, so the panel row shows the scaled amount rather than these numbers.
CLEARED_BONUS_XP = 40
CLEARED_BONUS_GOLD = 10
# Chance the reward is a gem *instead of* the gold, decided when the day rolls.
CLEARED_BONUS_GEM_PERCENT = 10
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
    src/carry.py. Rounding each step separately would drop both fractions: Hard on Steady is
    7.2 * 0.5 = 3.6, and truncating that would pay 3 every time.
    """
    return carry.award(
        data, carry.XP_KEY, review_xp_exact(data, ease, base_good_xp, owned_collectibles)
    )


def quest_xp_exact(data: dict, quest_xp: int, owned_collectibles: list) -> float:
    """
    Exact XP a quest pays: the quest's own XP raised by the XP % bonus.

    The flat "+N XP per answer" stat is deliberately not added here. It is sold as a per-answer
    bonus, so paying it once more on quest completion is a surprise the item never advertised.
    Percentages, which are sold as raising what you earn generally, do apply.

    Pure — safe to call for display. The paired _apply_* function below is the one that grants it
    and moves the carry; calling that one to preview a reward would spend the player's carry.
    """
    owned = owned_collectibles or []
    # Percentage bonus (same as reviews - no separate quest %)
    xp_bonus = shop.xp_bonus_percent(owned) + prestige.prestige_xp_bonus_percent(data)
    return quest_xp * (1 + xp_bonus / 100)


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

    Chance = luck from collectibles (scaled down, see QUEST_LUCK_SCALE) + the "quest gem chance"
    bonus from collectibles and prestige. Those bonuses are added, not multiplied, so items like
    Dragon Tooth still do something for a player who owns no luck items. There is no floor: every
    quest, the clear-the-day one included, gets this gem purely from what the player owns.

    Call once per completion, with the collection as it stands at that moment, and store the result
    on the quest so undo doesn't reroll it.
    """
    chance = shop.luck_gem_chance_percent(owned or []) * QUEST_LUCK_SCALE
    chance += shop.quest_gem_bonus_percent(owned or [])
    chance += prestige.prestige_quest_reward_bonus_percent(data)
    return _roll_gem_color(chance)


def cleared_bonus_reward_is_gem(data: dict, today: str) -> bool:
    """
    Whether the clear-the-day quest pays a gem instead of its gold on `today`.

    Reads the stored roll only when it belongs to today, so a caller that runs before the day has
    been settled — the panel drawing while the collection is still loading — shows the gold this
    quest pays by default rather than yesterday's answer.
    """
    if data.get("cleared_bonus_reward_date") != today:
        return False
    return bool(data.get("cleared_bonus_reward_is_gem"))


def ensure_cleared_bonus_reward(data: dict, today: str) -> None:
    """
    Settle whether the clear-the-day quest pays gold or a gem on `today`, once.

    Called when the day rolls, so this quest decides its reward at the same moment the two rolled
    quests decide theirs and the panel can show it from the start of the day rather than only after
    it is claimed. Guarded by cleared_bonus_reward_date, which undo does not clear, so undoing and
    redoing the last card cannot reroll a gold day into a gem one.

    The guard is a key the previous scheme never wrote, so a save updated mid-day rolls afresh
    instead of inheriting a half-migrated reward from it.

    Only the gold-or-gem choice is settled here. The completion luck gem is rolled when the quest is
    claimed, like every other quest's, so items bought during the day still count towards it.
    """
    if data.get("cleared_bonus_reward_date") == today:
        return
    # Gem *instead of* gold, exactly like a rolled quest — not a gem on top of it.
    data["cleared_bonus_reward_is_gem"] = random.random() * 100.0 < CLEARED_BONUS_GEM_PERCENT
    data["cleared_bonus_gem_color"] = random.choice([c for c, _ in shop.GEM_COLORS])
    # Written last: it marks the day settled, so a crash between these lines must not leave the day
    # claiming to be settled with no reward chosen.
    data["cleared_bonus_reward_date"] = today


def _award_cleared_bonus(data: dict, owned: list, col, earned: dict) -> tuple[int, int]:
    """
    Pay the bonus for finishing the day's due cards. Returns (xp, gold) paid, or (0, 0) if not.

    The amounts are returned rather than left for the caller to re-derive from the constants, so the
    payout and the undo deltas recorded against it cannot drift apart.

    Fires at most once per scheduler day, guarded by cleared_bonus_date. Completion is measured by
    due_baseline.cleared_progress, which counts finished review cards — new cards neither advance it
    nor hold it back. Both gem rolls — the gold-or-gem choice and the completion luck gem — keep
    their own date keys that undo does not clear, so undoing and redoing the last card cannot
    re-roll either.
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
    # Normally already settled when the day rolled; done here too for a day whose roll was skipped
    # because the collection could not be measured, or that began before this quest existed.
    ensure_cleared_bonus_reward(data, today)

    # XP and gold go through the same helpers as a daily quest, so the collection and prestige
    # upgrades scale this exactly as they scale every other quest reward.
    bonus_xp = _apply_quest_xp_bonus(data, CLEARED_BONUS_XP, owned or [])
    data["total_xp"] = data.get("total_xp", 0) + bonus_xp

    bonus_gold = 0
    if cleared_bonus_reward_is_gem(data, today):
        color = data.get("cleared_bonus_gem_color")
        gems = data.get("gems", shop.default_gems())
        data["gems"] = shop.award_gem_of_color(gems, color) if color else shop.award_random_gem(gems)
        earned["gem_earned"] += 1
    else:
        bonus_gold = carry.award(
            data, carry.GOLD_KEY, quest_gold_exact(data, CLEARED_BONUS_GOLD, owned or [])
        )
        data["money"] = data.get("money", 0) + bonus_gold
        earned["gold_earned"] += bonus_gold

    # Rolled now rather than when the day began, with the collection as it stands at this moment,
    # so a luck item bought today counts — exactly as it does for the two rolled quests. Its own
    # date key is not cleared by undo, so undo/redo cannot reroll it.
    if data.get("cleared_bonus_luck_gem_date") != today:
        data["cleared_bonus_luck_gem_color"] = _roll_quest_luck_gem_color(data, owned or [])
        data["cleared_bonus_luck_gem_date"] = today
    luck_color = data.get("cleared_bonus_luck_gem_color")
    if luck_color:
        data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), luck_color)
        earned["gem_earned"] += 1

    # Reported as a completed quest so the caller's one-tooltip-per-answer message picks it up with
    # no special case: its gold and gem are already in earned, so only the XP needs naming here.
    earned["completed_quests"].append((CLEARED_BONUS_LABEL, bonus_xp))
    return (bonus_xp, bonus_gold)


def grant_level_up(
    data: dict, old_level: int, owned_collectibles: list
) -> tuple[int, int, bool]:
    """
    Bring data["level"] up to date with total_xp and pay for every level crossed since old_level.

    Returns (gold paid, gems awarded, whether any level was gained). Mutates data: level, money,
    gems, unlocked, last_level_up_roll.

    Split out of apply_one_review so the endgame resource trades can pay the same level-up. XP is
    XP: converting leftover gold and gems at the end of the collection should not quietly pay less
    per point than earning it by reviewing would have. The caller records the payout in whatever
    bookkeeping it keeps — the review path folds it into `earned` and its undo deltas; a trade keeps
    neither, since trades never enter the undo buffer.

    Paid per level, not once per call: a review crosses at most one boundary, so that path is
    unchanged, but a single trade can cross many, and the guaranteed gem every fifth level only
    lands if each level is rolled for.

    The unlock sweep runs whether or not a level was gained. It is idempotent, and it reconciles
    `unlocked` with the level on every path that moved total_xp.
    """
    owned = owned_collectibles or []
    new_level = xp.level_from_total_xp(data.get("total_xp", 0))
    data["level"] = new_level

    levels = range(old_level + 1, new_level + 1)

    # Level-up gold: base + flat bonus from items, then apply percentage bonus. Paid per level, and
    # paid again on a repeat call — the undo buffer reverts it, so a redo has to re-pay it.
    gold_paid = 0
    per_level = GOLD_PER_LEVEL_UP + shop.gold_flat(owned)
    for _level in levels:
        gold = _apply_gold_bonus(data, per_level, owned)
        data["money"] = data.get("money", 0) + gold
        gold_paid += gold

    # Gems: reuse the stored roll when this call spans the same levels as the last one (undo then
    # redo of the review that crossed them), else roll each level and store the whole span. Storing
    # only the final level would let a repeat call re-roll the levels below it, which is a free
    # reroll on any jump wider than one level. `from` is absent in saves written before spans were
    # possible; defaulting it to old_level makes those match exactly as they did.
    gem_colors: list[str] = []
    if new_level > old_level:
        stored = data.get("last_level_up_roll") or {}
        if stored.get("level") == new_level and stored.get("from", old_level) == old_level:
            gem_colors = list(stored.get("gems") or [])
        else:
            gem_colors = []
            for level in levels:
                gem_colors.extend(_roll_level_up_gem_colors(owned, level))
            data["last_level_up_roll"] = {"level": new_level, "from": old_level, "gems": gem_colors}
        for color in gem_colors:
            data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), color)

    unlocked_list = data.get("unlocked", [])
    for img_name, _ in unlocks.newly_unlocked(new_level, unlocked_list):
        if img_name not in unlocked_list:
            unlocked_list.append(img_name)
    data["unlocked"] = unlocked_list
    return (gold_paid, len(gem_colors), new_level > old_level)


def apply_one_review(
    data: dict,
    ease: int,
    deck_name: str | None = None,
    is_new: bool = False,
    counts_as_due_review: bool = True,
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
        counts_as_due_review=counts_as_due_review,
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

    level_gold, level_gems, leveled_up = grant_level_up(data, old_level, owned)
    if leveled_up:
        # Reported so the caller can name the cause instead of inferring it from "gold with no
        # quest", which would mislabel any other source of gold that appears later.
        earned["leveled_up"] = True
    gold_delta += level_gold
    undo_gold += level_gold
    earned["gold_earned"] += level_gold
    earned["gem_earned"] += level_gems

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
