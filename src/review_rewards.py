"""
Shared logic for applying one review to AnkiGame state (desktop or synced from revlog).
Used by __init__.py (_on_answer) and revlog_sync.py (process_synced_revlog).
Quest rewards: rolled at creation — reward_gold and reward_xp always, plus any gems in
reward_gem_colors (a chance over 100% pays more than one; see roll_gem_count).
Level-up: fixed gold; gem has a chance (not guaranteed).
Undo (Ctrl+Z): reverts review XP, quest XP/gold/gems, level-up gold/gems, and quest progress for that review.
"""
from __future__ import annotations

import random

from . import carry, due_baseline, prestige, quests, shop, streak, unlocks, xp

GOLD_PER_LEVEL_UP = 20
# Quest gold/XP come from the rolled quest (reward_gold, reward_xp). Fallback if missing:
GOLD_PER_QUEST_FALLBACK = 10
LEVEL_UP_GEM_BASE_PERCENT = 15  # base chance for 1 gem on level-up, before gem luck multiplies it
# Ceiling on one gem roll. Unreachable in play; it exists so a corrupt or hand-edited save cannot
# turn an unclamped chance into an unbounded loop. See roll_gem_count.
MAX_GEMS_PER_ROLL = 50
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
# Chance the day also pays a gem, on top of its gold, decided when the day rolls.
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


def gem_luck_multiplier(data: dict, owned_collectibles: list) -> float:
    """
    What the player's collection and prestige do to any gem chance: `base * multiplier`.

    Gem luck multiplies rather than adds, because adding flattens the base rates it is applied to. A
    quest carrying a 30% chance and the clear-the-day quest carrying 10% are a deliberate 3:1
    statement about which is worth more; a +200 bonus turns them into 100% and 95% and the
    distinction disappears exactly when the player has the biggest collection. Multiplying keeps
    30:10 at 90:30.

    Collection and prestige are summed before being applied once, which is how `xp_bonus_percent`
    and `gold_bonus_percent` already compose. The prestige quest-reward upgrade lives here because
    this is now the only gem roll a quest has.
    """
    pct = shop.luck_gem_chance_percent(owned_collectibles or [])
    pct += prestige.prestige_quest_reward_bonus_percent(data)
    return 1 + pct / 100


def scaled_gem_chance(base_percent: float, data: dict, owned_collectibles: list) -> float:
    """One gem chance, scaled by gem luck. May exceed 100% - `roll_gem_count` resolves that.

    This used to clamp at 100. Clamping kept a chance a chance, but it spent the overflow instead of
    paying it: a complete collection already puts the 30% review band at 90%, and two levels of the
    prestige Gem luck upgrade take it past 100, where every further point bought nothing. It also
    eroded the spread the bands exist to state - 30:10 held at 3:1 only until the top band pinned,
    then decayed toward 1:1 for exactly the players who had invested most, which is the failure the
    additive model was replaced to avoid in the first place.

    Letting the chance run past 100 and paying the excess as whole gems keeps the expected count at
    `base * multiplier` at any size, so the 3:1 spread holds at every multiplier and no point of gem
    luck is ever wasted.

    Still floored at zero: only the ceiling was ever the problem. A hand-edited save with a negative
    prestige upgrade level would otherwise drive the multiplier below zero, and callers that compare
    against a chance read better with a number they can trust the sign of.
    """
    return max(0.0, base_percent * gem_luck_multiplier(data, owned_collectibles))


def roll_gem_count(chance_percent: float) -> int:
    """How many gems a chance pays, with anything above 100% paid as a gem plus a fresh roll.

    120% is one gem outright and a 20% roll for a second; 340% is three gems and a 40% roll for a
    fourth. The expected count is `chance_percent / 100` exactly, at any size - which is the whole
    reason gem luck can stay linear rather than saturating.

    Capped at MAX_GEMS_PER_ROLL. Nothing reachable by play comes near it - a complete collection at
    the top band pays one or two - but the chance is built from save-file numbers with no ceiling of
    their own, and the count drives loops and a stored color list. The old 100% clamp bounded this
    implicitly; removing it means saying the bound out loud.
    """
    if chance_percent <= 0:
        return 0
    whole = min(MAX_GEMS_PER_ROLL, int(chance_percent // 100))
    if whole >= MAX_GEMS_PER_ROLL:
        return MAX_GEMS_PER_ROLL
    return whole + (1 if random.random() * 100.0 < chance_percent - whole * 100.0 else 0)


def _roll_level_up_gem_colors(level: int, effective_chance: float) -> list[str]:
    """Roll level-up gems (guaranteed every 5 levels + luck). Returns list of gem colors to award. Used so we can store roll for undo/re-level.

    Takes the already-scaled chance rather than computing it: grant_level_up calls this once per
    level crossed, and the collection cannot change inside that loop.
    """
    colors: list[str] = []
    gem_choices = [c for c, _ in shop.GEM_COLORS]
    if level % 5 == 0:
        colors.append(random.choice(gem_choices))
    colors.extend(
        random.choice(gem_choices) for _ in range(roll_gem_count(effective_chance))
    )
    return colors


def cleared_bonus_gem_colors(data: dict, today: str) -> list[str]:
    """
    Gem colors the clear-the-day quest pays on `today`, alongside its gold.

    Reads the stored roll only when it belongs to today, so a caller that runs before the day has
    been settled — the panel drawing while the collection is still loading — shows the gold this
    quest pays by default rather than yesterday's answer.

    Days settled before gem chances could exceed 100% stored a bool and one color; they keep paying
    what they promised rather than being re-rolled under the new rule.

    The legacy pair is consulted whenever the new list is empty rather than whenever the new key is
    absent: `storage._migrate` backfills every missing default into a loaded save, so the key is
    always present and a presence check would make this fallback unreachable. A day already settled
    by the previous build reaches here with the list defaulted to empty and the bool still true, and
    the gem the panel promised would be dropped. `ensure_cleared_bonus_reward` writes both, so an
    empty list on a day settled by this build always has the bool false beside it.
    """
    if data.get("cleared_bonus_reward_date") != today:
        return []
    colors = [c for c in (data.get("cleared_bonus_gem_colors") or []) if c]
    if colors:
        return colors
    if data.get("cleared_bonus_reward_is_gem"):
        color = data.get("cleared_bonus_gem_color")
        return [color] if color else [random.choice([c for c, _ in shop.GEM_COLORS])]
    return []


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
    # A gem on top of the gold, exactly like a rolled quest — never instead of it.
    chance = scaled_gem_chance(CLEARED_BONUS_GEM_PERCENT, data, data.get("owned_collectibles", []))
    gem_choices = [c for c, _ in shop.GEM_COLORS]
    colors = [random.choice(gem_choices) for _ in range(roll_gem_count(chance))]
    data["cleared_bonus_gem_colors"] = colors
    # Written so a save opened by an older build still sees a reward it can understand.
    data["cleared_bonus_reward_is_gem"] = count > 0
    data["cleared_bonus_gem_color"] = colors[0] if colors else None
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

    # Gold always, then the gem if the day rolled one — the same rule the rolled quests follow.
    bonus_gold = carry.award(
        data, carry.GOLD_KEY, quest_gold_exact(data, CLEARED_BONUS_GOLD, owned or [])
    )
    data["money"] = data.get("money", 0) + bonus_gold
    earned["gold_earned"] += bonus_gold
    for color in cleared_bonus_gem_colors(data, today):
        data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), color)
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
            level_up_chance = scaled_gem_chance(LEVEL_UP_GEM_BASE_PERCENT, data, owned)
            for level in levels:
                gem_colors.extend(_roll_level_up_gem_colors(level, level_up_chance))
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
        # Gold always, then the gem if this quest rolled one. Not either-or: see _make_quest.
        base_gold = q.get("reward_gold", GOLD_PER_QUEST_FALLBACK)
        gold = carry.award(data, carry.GOLD_KEY, quest_gold_exact(data, base_gold, owned))
        data["money"] = data.get("money", 0) + gold
        gold_delta += gold
        undo_gold += gold
        earned["gold_earned"] += gold
        for color in quests.quest_gem_colors(q):
            data["gems"] = shop.award_gem_of_color(data.get("gems", shop.default_gems()), color)
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
