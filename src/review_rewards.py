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

from . import carry, due_baseline, milestones, prestige, quests, shop, streak, unlocks, xp

GOLD_PER_LEVEL_UP = 20
# Quest gold/XP come from the rolled quest (reward_gold, reward_xp). Fallback if missing:
GOLD_PER_QUEST_FALLBACK = 10
LEVEL_UP_GEM_BASE_PERCENT = 15  # base chance for 1 gem on level-up, before gem luck multiplies it
# Ceiling on one gem roll. Unreachable in play; it exists so a corrupt or hand-edited save cannot
# turn an unclamped chance into an unbounded loop. See roll_gem_count.
MAX_GEMS_PER_ROLL = 50
# Share of a Good answer paid by Again and by Hard. Neither is zero: paying nothing for a grade
# rewards misgrading the card, and the scheduler the game sits on cannot afford to be lied to.
AGAIN_XP_RATIO = 0.2
HARD_XP_RATIO = 0.5
# The bonus quest: clearing every card Anki had due. Base figures - item and prestige bonuses scale
# these like any quest reward, so the panel row shows the scaled amount instead.
CLEARED_BONUS_XP = 40
CLEARED_BONUS_GOLD = 10
# Chance the day also pays a gem, on top of its gold, decided when the day rolls.
CLEARED_BONUS_GEM_PERCENT = 10
# Shared so the panel row and the completion tooltip name it identically. Only the panel prefixes
# it with "Bonus: " - the tooltip already says "Quest complete:".
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

    Ease 0, or anything above Easy, falls through to a zero ratio and pays nothing.
    """
    owned = owned_collectibles or []

    # Applies to every answer, Again included, so the ratios really are a share of what the same
    # card pays on Good.
    flat_bonus = shop.xp_flat(owned)

    base = base_good_xp + flat_bonus
    if base <= 0:
        return 0.0

    # Ratios are relative to Good on every difficulty: difficulty enters through base_good_xp only.
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

    # Added here, not in total_xp_bonus_percent, which is shared with quest XP and the streak
    # reward - this buff is review-scoped. Added to the bucket, never multiplied, so it cannot
    # compound against a large collection.
    bonus_pct = total_xp_bonus_percent(data, owned)
    if milestones.buff_is_active(data, milestones.BUFF_REVIEWS_XP):
        bonus_pct += milestones.BUFF_REVIEW_XP_PERCENT
    return base * ratio * (1 + bonus_pct / 100)


def total_xp_bonus_percent(data: dict, owned_collectibles: list) -> float:
    """
    Every percentage that scales XP, summed: the collection, prestige, and the streak accumulator.

    One function for all three sites (review XP, quest XP, streak reward), so a new bonus cannot
    silently skip one. Additive rather than multiplied on top, so the accumulator is worth most to
    the player who owns least.
    """
    owned = owned_collectibles or []
    return (
        shop.xp_bonus_percent(owned)
        + prestige.prestige_xp_bonus_percent(data)
        + milestones.accumulator_percent(data)
    )


def total_gold_bonus_percent(data: dict, owned_collectibles: list) -> float:
    """
    Every percentage that scales gold, summed: the collection, prestige, and the accumulator - the
    last of which pays in only once the final Magnet stage is collected. The mirror of
    total_xp_bonus_percent, and shared by the three gold payouts for the same reason.
    """
    owned = owned_collectibles or []
    return (
        shop.gold_bonus_percent(owned)
        + prestige.prestige_gold_bonus_percent(data)
        + milestones.accumulator_gold_percent(data)
    )


def _apply_xp_bonus(data: dict, ease: int, base_good_xp: float, owned_collectibles: list) -> int:
    """
    Grant review XP through the carry. Mutates data - use review_xp_exact to preview.

    Rounded once by the carry, never per step: Hard on Steady is 7.2 * 0.5 = 3.6, and truncating
    each step would pay 3 every time.
    """
    return carry.award(
        data, carry.XP_KEY, review_xp_exact(data, ease, base_good_xp, owned_collectibles)
    )


def quest_xp_exact(data: dict, quest_xp: int, owned_collectibles: list) -> float:
    """
    Exact XP a quest pays: the quest's own XP raised by the XP % bonus. Pure - safe to preview with.

    The flat "+N XP per answer" stat deliberately does not apply: it is sold per answer, so paying
    it again on completion is a surprise the item never advertised.
    """
    owned = owned_collectibles or []
    # Percentage bonus (same as reviews - no separate quest %)
    xp_bonus = total_xp_bonus_percent(data, owned)
    # The doubling buff belongs here, not at the call sites: both payouts and the panel's preview
    # go through this helper, so a multiplier applied outside it would make the panel promise a
    # figure the payout does not honor.
    return quest_xp * (1 + xp_bonus / 100) * milestones.quest_reward_multiplier(data)


def quest_gold_exact(data: dict, base_gold: float, owned_collectibles: list) -> float:
    """
    Exact gold a quest pays. Pure — safe to call for display.

    Quests get half the flat bonus so their gold scales without matching level-up gold, and the
    half is kept exact: rounding it here would lose 0.5 on an odd bonus before the carry saw it.
    """
    owned = owned_collectibles or []
    bonus_pct = total_gold_bonus_percent(data, owned)
    # Doubled here for the same reason quest_xp_exact is.
    multiplier = milestones.quest_reward_multiplier(data)
    return (base_gold + shop.gold_flat(owned) / 2) * (1 + bonus_pct / 100) * multiplier


def preview_whole(exact: float) -> int:
    """
    Round an exact reward for display. Never touches the carry, which is why this is the nearest
    whole number: what is granted varies by one either side as the carry fills.
    """
    return int(round(exact))


def _apply_quest_xp_bonus(data: dict, quest_xp: int, owned_collectibles: list) -> int:
    """Grant quest XP through the carry. Mutates data — use quest_xp_exact to preview."""
    return carry.award(data, carry.XP_KEY, quest_xp_exact(data, quest_xp, owned_collectibles))


def _apply_gold_bonus(data: dict, base_gold: float, owned_collectibles: list) -> int:
    """Grant gold through the carry. Mutates data — use quest_gold_exact to preview quest gold."""
    bonus_pct = total_gold_bonus_percent(data, owned_collectibles)
    return carry.award(data, carry.GOLD_KEY, base_gold * (1 + bonus_pct / 100))


def gem_luck_multiplier(data: dict, owned_collectibles: list) -> float:
    """
    What the player's collection and prestige do to any gem chance: `base * multiplier`.

    Multiplies rather than adds: adding would flatten 30% against 10% into 100% against 95%,
    erasing the bands' 3:1 spread exactly when the collection is largest. Collection and prestige
    are summed first and applied once, as the XP and gold percentages already compose.
    """
    pct = shop.luck_gem_chance_percent(owned_collectibles or [])
    pct += prestige.prestige_quest_reward_bonus_percent(data)
    return 1 + pct / 100


def scaled_gem_chance(base_percent: float, data: dict, owned_collectibles: list) -> float:
    """One gem chance, scaled by gem luck. May exceed 100% - `roll_gem_count` resolves that.

    Deliberately unclamped: a clamp at 100 spent the overflow instead of paying it, so gem luck
    stopped buying anything once a band pinned and the 3:1 spread between bands decayed toward 1:1.
    Paying the excess as whole gems keeps the expected count at `base * multiplier` at any size.
    Floored at zero so a hand-edited save cannot produce a negative chance.
    """
    return max(0.0, base_percent * gem_luck_multiplier(data, owned_collectibles))


def award_reward_gems(data: dict, colors: list[str], from_quest: bool = False) -> int:
    """
    Pay the gems a reward rolled, applying the buffs that act on gem rewards. Returns how many.

    Every gem the game awards goes through here - quests, the bonus quest, level-ups, the streak.
    Gems bought in the shop do not: the buffs are worded "every gem reward".

    Both buffs act on the gems already rolled, not on the roll. Most-needed color rewrites which
    gem arrives, never how many. A doubling buff pays quantity rather than chance, which is worth
    the same to every player instead of nothing to those with high gem luck; two doubling buffs
    still double only once (see milestones.gem_reward_multiplier). The extra gems roll their own
    colors, so a doubled reward is not twice as lopsided as an ordinary one.
    """
    if not colors:
        return 0
    gems = data.get("gems", shop.default_gems())
    multiplier = milestones.gem_reward_multiplier(data, from_quest=from_quest)
    # The gems as rolled, then one freshly-rolled color per extra the multiplier buys.
    payout = list(colors) + [
        shop.random_gem_color() for _ in range(len(colors) * (multiplier - 1))
    ]
    if milestones.buff_is_active(data, milestones.BUFF_GEMS_MOST_NEEDED):
        # Resolved per gem, so two gems fill the two largest gaps rather than the same one; after
        # the multiplier, so the extras are aimed at the deficit too.
        payout = [None] * len(payout)
    paid = 0
    for color in payout:
        target = color or shop.most_needed_gem_color(gems)
        gems = shop.award_gem_of_color(gems, target)
        paid += 1
    data["gems"] = gems
    return paid


def roll_gem_count(chance_percent: float) -> int:
    """How many gems a chance pays, with anything above 100% paid as a gem plus a fresh roll.

    120% is one gem outright and a 20% roll for a second; 340% is three gems and a 40% roll for a
    fourth. The expected count is `chance_percent / 100` exactly, at any size - which is the whole
    reason gem luck can stay linear rather than saturating.

    Capped at MAX_GEMS_PER_ROLL: unreachable in play, but the chance is built from save-file
    numbers with no ceiling of their own and the count drives a loop.
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


def cleared_bonus_xp_base(data: dict) -> float:
    """
    The bonus quest's base XP after the track's boost, before items and prestige scale it.

    Kept exact: the caller hands the whole product to the carry, so a fractional boost is not lost.
    The panel's preview reads this too, so the row cannot promise what the payout will not honor.
    """
    pct = milestones.granted_value(data, "bonus_quest_xp_percent", 0)
    return CLEARED_BONUS_XP * (1 + float(pct) / 100)


def cleared_bonus_gold_base(data: dict) -> float:
    """The bonus quest's base gold after the track's boost. See cleared_bonus_xp_base."""
    pct = milestones.granted_value(data, "bonus_quest_gold_percent", 0)
    return CLEARED_BONUS_GOLD * (1 + float(pct) / 100)


def cleared_bonus_gem_colors(data: dict, today: str) -> list[str]:
    """
    Gem colors the clear-the-day quest pays on `today`, alongside its gold.

    Reads the stored roll only when it belongs to today, so a panel drawn before the day is settled
    shows the default rather than yesterday's answer.

    Days settled before gem chances could exceed 100% stored a bool and one color, and keep paying
    what they promised. That legacy pair is consulted whenever the new list is empty rather than
    when the key is absent - `storage._migrate` backfills every key, so a presence check would make
    this unreachable, and `ensure_cleared_bonus_reward` writes both.
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

    Called when the day rolls, so the panel can show the reward from the start of the day. Guarded
    by cleared_bonus_reward_date, which undo does not clear, so redoing the last card cannot reroll
    a gold day into a gem one.

    Only the gold-or-gem choice is settled here; the completion luck gem is rolled on claim like
    every other quest's, so items bought during the day still count towards it.
    """
    if data.get("cleared_bonus_reward_date") == today:
        return
    # A gem on top of the gold, exactly like a rolled quest — never instead of it.
    chance = scaled_gem_chance(CLEARED_BONUS_GEM_PERCENT, data, data.get("owned_collectibles", []))
    gem_choices = [c for c, _ in shop.GEM_COLORS]
    colors = [random.choice(gem_choices) for _ in range(roll_gem_count(chance))]
    data["cleared_bonus_gem_colors"] = colors
    # Written so a save opened by an older build still sees a reward it can understand.
    data["cleared_bonus_reward_is_gem"] = bool(colors)
    data["cleared_bonus_gem_color"] = colors[0] if colors else None
    # Written last: it marks the day settled, so a crash between these lines must not leave the day
    # claiming to be settled with no reward chosen.
    data["cleared_bonus_reward_date"] = today


def _award_cleared_bonus(data: dict, owned: list, col, earned: dict) -> tuple[int, int]:
    """
    Pay the bonus for finishing the day's due cards. Returns (xp, gold) paid, or (0, 0) if not, so
    the payout and the undo deltas recorded against it cannot drift apart.

    Fires at most once per scheduler day. Completion is measured by due_baseline.cleared_progress,
    which counts finished review cards - new cards neither advance it nor hold it back.
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

    # Through the same helpers as a daily quest, so every bonus scales this the same way.
    bonus_xp = _apply_quest_xp_bonus(data, cleared_bonus_xp_base(data), owned or [])
    data["total_xp"] = data.get("total_xp", 0) + bonus_xp

    # Gold always, then the gem if the day rolled one — the same rule the rolled quests follow.
    bonus_gold = carry.award(
        data, carry.GOLD_KEY, quest_gold_exact(data, cleared_bonus_gold_base(data), owned or [])
    )
    data["money"] = data.get("money", 0) + bonus_gold
    earned["gold_earned"] += bonus_gold
    earned["gem_earned"] += award_reward_gems(
        data, cleared_bonus_gem_colors(data, today), from_quest=True
    )

    # Guarded on the track's own scheduler-day key, not cleared_bonus_date above, which undo pops:
    # otherwise re-answering the last due card counted the completion twice and rolled a second
    # buff and Magnet, neither of which undo takes back. The rolls sit inside that guard.
    if milestones.note_bonus_quest_complete(data, col):
        milestones.advance_if_complete(data, col)

        # After the advance, so a completion that opens the faucet at #4 can drop the same day.
        # Reported through `earned`, not the return value: undo does not take a buff back.
        buff = milestones.roll_buff(data, col)
        if buff:
            earned["buff_started"] = buff

        # A separate draw from the buff: either, both or neither can land.
        if milestones.roll_magnet(data, col):
            earned["magnet_found"] = True
            completed_stage = milestones.award_magnet(data, col)
            if completed_stage:
                earned["magnet_stage_completed"] = completed_stage

    # Reported as a completed quest so the caller's tooltip picks it up with no special case; its
    # gold and gem are already in `earned`.
    earned["completed_quests"].append((CLEARED_BONUS_LABEL, bonus_xp))
    return (bonus_xp, bonus_gold)


def grant_level_up(
    data: dict, old_level: int, owned_collectibles: list
) -> tuple[int, int, bool]:
    """
    Bring data["level"] up to date with total_xp and pay for every level crossed since old_level.

    Returns (gold paid, gems awarded, whether any level was gained). Mutates data: level, money,
    gems, unlocked, last_level_up_roll.

    Split out of apply_one_review so the endgame resource trades pay the same level-up. Paid per
    level, not per call: a trade can cross many at once, and the guaranteed gem every fifth level
    only lands if each is rolled for.

    The unlock sweep runs whether or not a level was gained - it is idempotent, and reconciles
    `unlocked` with the level on every path that moved total_xp.
    """
    owned = owned_collectibles or []
    new_level = xp.level_from_total_xp(data.get("total_xp", 0))
    data["level"] = new_level

    levels = range(old_level + 1, new_level + 1)

    # Base + flat bonus from items, then the percentage. Re-paid on a repeat call, because undo
    # reverted it.
    gold_paid = 0
    per_level = GOLD_PER_LEVEL_UP + shop.gold_flat(owned)
    for _level in levels:
        gold = _apply_gold_bonus(data, per_level, owned)
        data["money"] = data.get("money", 0) + gold
        gold_paid += gold

    # Reuse the stored roll when this call spans the same levels as the last one (undo then redo),
    # else roll each level and store the whole span - storing only the final level would let a
    # repeat call re-roll the ones below it. `from` is absent in older saves; defaulting it to
    # old_level makes those match as they did.
    gem_colors: list[str] = []
    gems_paid = 0
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
        # The count paid, not rolled: a doubling buff pays two gems per rolled color.
        gems_paid = award_reward_gems(data, gem_colors)

    unlocked_list = data.get("unlocked", [])
    for img_name, _ in unlocks.newly_unlocked(new_level, unlocked_list):
        if img_name not in unlocked_list:
            unlocked_list.append(img_name)
    data["unlocked"] = unlocked_list
    return (gold_paid, gems_paid, new_level > old_level)


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
    # Before anything is paid: every XP figure below reads the accumulator and the review buff, and
    # the only other refresh runs after the answer - which would pay the first review of a new day
    # at yesterday's charge and honor a buff that expired overnight.
    milestones.refresh(data, col)

    gems_before = dict(data.get("gems", shop.default_gems()))
    # Undo restores these exactly: subtracting whole XP and gold alone would let the carries drift.
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
        earned["gem_earned"] += award_reward_gems(
            data, quests.quest_gem_colors(q), from_quest=True
        )
        # Reported rather than drawn here: the caller composes one tooltip for the whole answer.
        # The label is resolved so a deck renamed mid-day is named as the panel names it.
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
        # Reported so the caller names the cause instead of inferring it from "gold with no quest".
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
