"""Applies one review to the game state, for desktop answers (hooks) and synced revlog rows
(revlog_sync). Undo reverts review XP, quest rewards, level-up rewards and quest progress for that
review."""
from __future__ import annotations

import random

from . import carry, due_baseline, dungeon, milestones, prestige, quests, shop, streak, unlocks, xp

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
CLEARED_BONUS_XP = 120
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
    """Exact XP one review pays, before rounding. Pure. Base Good XP plus flat XP, times the ease
    ratio and the XP % bonuses; ease 0 or above Easy pays nothing."""
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

    # Review-scoped, so added here rather than in total_xp_bonus_percent; added, never multiplied,
    # so it cannot compound against a large collection.
    bonus_pct = total_xp_bonus_percent(data, owned)
    if milestones.buff_is_active(data, milestones.BUFF_REVIEWS_XP):
        bonus_pct += milestones.BUFF_REVIEW_XP_PERCENT
    return base * ratio * (1 + bonus_pct / 100)


def total_xp_bonus_percent(data: dict, owned_collectibles: list) -> float:
    """Every percentage that scales XP, summed: collection, prestige and the streak accumulator.
    Shared by review XP, quest XP and the streak reward, so a new bonus cannot skip one."""
    owned = owned_collectibles or []
    return (
        shop.xp_bonus_percent(owned)
        + prestige.prestige_xp_bonus_percent(data)
        + milestones.accumulator_percent(data)
    )


def total_gold_bonus_percent(data: dict, owned_collectibles: list) -> float:
    """Gold counterpart of total_xp_bonus_percent; the accumulator pays in only once the final
    Magnet stage is collected."""
    owned = owned_collectibles or []
    return (
        shop.gold_bonus_percent(owned)
        + prestige.prestige_gold_bonus_percent(data)
        + milestones.accumulator_gold_percent(data)
    )


def _apply_xp_bonus(data: dict, ease: int, base_good_xp: float, owned_collectibles: list) -> int:
    """Grant review XP through the carry (use review_xp_exact to preview). Rounded once by the
    carry, not per step, or Hard on Steady (3.6) would pay 3 every time."""
    return carry.award(
        data, carry.XP_KEY, review_xp_exact(data, ease, base_good_xp, owned_collectibles)
    )


def quest_xp_exact(data: dict, quest_xp: int, owned_collectibles: list) -> float:
    """Exact XP a quest pays: its own XP raised by the XP % bonus. Pure. The flat "+N XP per answer"
    stat is sold per answer, so it does not apply."""
    owned = owned_collectibles or []
    # Percentage bonus (same as reviews - no separate quest %)
    xp_bonus = total_xp_bonus_percent(data, owned)
    # The doubling buff lives here so the panel's preview and both payouts agree.
    return quest_xp * (1 + xp_bonus / 100) * milestones.quest_reward_multiplier(data)


def quest_gold_exact(data: dict, base_gold: float, owned_collectibles: list) -> float:
    """Exact gold a quest pays. Pure. Quests get half the flat bonus, kept exact so an odd bonus
    does not lose 0.5 before the carry sees it."""
    owned = owned_collectibles or []
    bonus_pct = total_gold_bonus_percent(data, owned)
    # Doubled here for the same reason quest_xp_exact is.
    multiplier = milestones.quest_reward_multiplier(data)
    return (base_gold + shop.gold_flat(owned) / 2) * (1 + bonus_pct / 100) * multiplier


def dungeon_xp_exact(data: dict, base_xp: float, owned_collectibles: list) -> float:
    """Exact XP a dungeon pays. Pure. Only the general XP stack: no quest buffs (a dungeon is not a
    quest) and no per-answer flat XP."""
    owned = owned_collectibles or []
    return base_xp * (1 + total_xp_bonus_percent(data, owned) / 100)


def dungeon_gold_exact(data: dict, base_gold: float, owned_collectibles: list) -> float:
    """Exact gold a dungeon pays. Pure, since it is rolled at discovery and shown on the button.
    Mirrors dungeon_xp_exact."""
    owned = owned_collectibles or []
    return base_gold * (1 + total_gold_bonus_percent(data, owned) / 100)


def preview_whole(exact: float) -> int:
    """Round an exact reward for display. Nearest whole number, since what is granted varies by one
    either side as the carry fills."""
    return int(round(exact))


def _apply_quest_xp_bonus(data: dict, quest_xp: int, owned_collectibles: list) -> int:
    """Grant quest XP through the carry. Mutates data — use quest_xp_exact to preview."""
    return carry.award(data, carry.XP_KEY, quest_xp_exact(data, quest_xp, owned_collectibles))


def _apply_gold_bonus(data: dict, base_gold: float, owned_collectibles: list) -> int:
    """Grant gold through the carry. Mutates data — use quest_gold_exact to preview quest gold."""
    bonus_pct = total_gold_bonus_percent(data, owned_collectibles)
    return carry.award(data, carry.GOLD_KEY, base_gold * (1 + bonus_pct / 100))


def gem_luck_multiplier(data: dict, owned_collectibles: list) -> float:
    """What the collection and prestige do to any gem chance: `base * multiplier`. Multiplied, not
    added, so the bands' 3:1 spread survives a large collection."""
    pct = shop.luck_gem_chance_percent(owned_collectibles or [])
    pct += prestige.prestige_quest_reward_bonus_percent(data)
    return 1 + pct / 100


def scaled_gem_chance(base_percent: float, data: dict, owned_collectibles: list) -> float:
    """One gem chance scaled by gem luck, floored at zero. Unclamped, so the expected count stays
    `base * multiplier`; `roll_gem_count` pays the excess as whole gems."""
    return max(0.0, base_percent * gem_luck_multiplier(data, owned_collectibles))


def award_reward_gems(
    data: dict,
    colors: list[str],
    from_quest: bool = False,
    multiplier: int | None = None,
    most_needed: bool | None = None,
) -> int:
    """Pay the gems a reward rolled, applying the gem buffs (most-needed recolors, doubling pays
    once). Returns how many. Dungeons pass `multiplier=1` and their recorded `most_needed`, fixed at
    discovery."""
    if not colors:
        return 0
    gems = data.get("gems", shop.default_gems())
    if multiplier is None:
        multiplier = milestones.gem_reward_multiplier(data, from_quest=from_quest)
    # The gems as rolled, then one freshly-rolled color per extra the multiplier buys.
    payout = list(colors) + [
        shop.random_gem_color() for _ in range(len(colors) * (multiplier - 1))
    ]
    if most_needed is None:
        most_needed = milestones.buff_is_active(data, milestones.BUFF_GEMS_MOST_NEEDED)
    if most_needed:
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
    """How many gems a chance pays: each full 100% is a gem, the remainder a roll, so the expected
    count is `chance_percent / 100`. Capped at MAX_GEMS_PER_ROLL against hand-edited saves."""
    if chance_percent <= 0:
        return 0
    whole = min(MAX_GEMS_PER_ROLL, int(chance_percent // 100))
    if whole >= MAX_GEMS_PER_ROLL:
        return MAX_GEMS_PER_ROLL
    return whole + (1 if random.random() * 100.0 < chance_percent - whole * 100.0 else 0)


def _roll_level_up_gem_colors(level: int, effective_chance: float) -> list[str]:
    """Roll level-up gems (guaranteed every 5 levels + luck). Returns the colors to award. Takes the
    already-scaled chance, since the collection can't change across grant_level_up's loop."""
    colors: list[str] = []
    gem_choices = [c for c, _ in shop.GEM_COLORS]
    if level % 5 == 0:
        colors.append(random.choice(gem_choices))
    colors.extend(
        random.choice(gem_choices) for _ in range(roll_gem_count(effective_chance))
    )
    return colors


def cleared_bonus_xp_base(data: dict) -> float:
    """The bonus quest's base XP after the track's boost, kept exact for the carry. The panel's
    preview reads it too, so the two cannot disagree."""
    pct = milestones.granted_value(data, "bonus_quest_xp_percent", 0)
    return CLEARED_BONUS_XP * (1 + float(pct) / 100)


def cleared_bonus_gold_base(data: dict) -> float:
    """The bonus quest's base gold after the track's boost. See cleared_bonus_xp_base."""
    pct = milestones.granted_value(data, "bonus_quest_gold_percent", 0)
    return CLEARED_BONUS_GOLD * (1 + float(pct) / 100)


def cleared_bonus_gem_colors(data: dict, today: str) -> list[str]:
    """Gem colors the clear-the-day quest pays on `today`. Falls back to the legacy bool+color pair
    when the list is empty (not absent, since _migrate backfills keys)."""
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
    """Settle once whether the clear-the-day quest pays gold or a gem on `today`, when the day
    rolls. Guarded by cleared_bonus_reward_date, which undo does not clear, so redo cannot reroll
    it. The luck gem is rolled on claim like any quest's."""
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


def _award_cleared_bonus(
    data: dict, owned: list, col, earned: dict, measured: tuple[int, int] | None = None
) -> tuple[int, int]:
    """Pay the bonus for finishing the day's due cards, at most once per scheduler day. Returns (xp,
    gold) paid or (0, 0), so the undo deltas cannot drift from the payout. `measured` reuses a
    caller's reading of due_baseline.cleared_progress."""
    if col is None:
        return (0, 0)
    today = streak.today_str(col)
    if data.get("cleared_bonus_date") == today:
        return (0, 0)
    progress = measured if measured is not None else due_baseline.cleared_progress(data, col)
    if progress is None or progress[0] < progress[1]:
        return (0, 0)

    data["cleared_bonus_date"] = today
    # Frozen for the rest of the day, so cards coming back onto the schedule can't put a completed
    # quest back in progress.
    data["cleared_bonus_total"] = progress[1]
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

    # Guarded on the track's own day key, since undo pops cleared_bonus_date and re-answering would
    # roll a second buff and Magnet that undo can't take back.
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


def cleared_bonus_display(data: dict, col) -> tuple[int, int] | None:
    """What the bonus quest's row shows: (finished, objective), or None. A paid day reports the
    objective it was paid at, so cards returning to the schedule can't untick it, and costs no
    measurement."""
    try:
        paid_today = data.get("cleared_bonus_date") == streak.today_str(col)
        if paid_today:
            objective = data.get("cleared_bonus_total")
            # Checked rather than trusted: a save paid by a build predating this key has nothing
            # stored, and is handled below instead.
            if isinstance(objective, int) and objective > 0:
                return (objective, objective)
        live = due_baseline.cleared_progress(data, col)
        if live and paid_today:
            # Paid by a build that did not record the objective: read as complete at what it
            # finished.
            return (live[0], live[0])
        return live
    except Exception:
        return None


def award_cleared_bonus_out_of_band(
    data: dict, col, measured: tuple[int, int] | None = None
) -> dict | None:
    """Pay the clear-the-day bonus for a day finished without answering a card (suspending, burying,
    deleting, lowering a limit), or None if not due. Mutates data; caller saves. No undo deltas: it
    pays once a day whatever happens to the cards afterwards."""
    earned: dict = {
        "gold_earned": 0,
        "gem_earned": 0,
        "completed_quests": [],
        "leveled_up": False,
    }
    # As apply_one_review does before paying anything: the XP figures below read the accumulator
    # and the review buff, and an expired buff must not be honored.
    milestones.refresh(data, col)
    owned = data.get("owned_collectibles", [])
    old_level = data.get("level", 1)
    bonus_xp, bonus_gold = _award_cleared_bonus(data, owned, col, earned, measured)
    if not (bonus_xp or bonus_gold):
        return None
    level_gold, level_gems, leveled_up = grant_level_up(data, old_level, owned)
    if leveled_up:
        earned["leveled_up"] = True
        earned["level_gold"] = level_gold
        earned["level_gems"] = level_gems
    earned["gold_earned"] += level_gold
    earned["gem_earned"] += level_gems
    return earned


def grant_level_up(
    data: dict, old_level: int, owned_collectibles: list
) -> tuple[int, int, bool]:
    """Bring data["level"] up to date with total_xp and pay for every level crossed since old_level.
    Returns (gold, gems, whether a level was gained). Paid per level, so the fifth-level gem lands
    on multi-level trades. The unlock sweep always runs; it is idempotent."""
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

    # Reuse the stored roll when this call spans the same levels (undo then redo), else roll and
    # store the whole span. `from` defaults to old_level for older saves.
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


def _apply_dungeon_review(data: dict, ease: int, owned: list, earned: dict) -> None:
    """Roll the dungeon for this answer and pay the XP it found. Mutates data and earned. dungeon.py
    returns base XP; scaling happens here so all XP goes through one bonus stack."""
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    found = dungeon.on_review(data, ease, level)
    if found["xp"]:
        gained = carry.award(data, carry.XP_KEY, dungeon_xp_exact(data, found["xp"], owned))
        data["total_xp"] = data.get("total_xp", 0) + gained
        earned["dungeon_xp"] = gained
    for key in ("entrance", "branching", "treasure"):
        if found[key]:
            earned[f"dungeon_{key}"] = True
    if found["auto_took"]:
        earned["dungeon_auto_took"] = found["auto_took"]


def apply_dungeon_catch_up(data: dict) -> dict:
    """Replay the reviews banked while the dungeon was blocked, once a pathway is taken or a
    treasure claimed. Returns {"xp", "entrance", "branching", "treasure"}."""
    owned = data.get("owned_collectibles", [])
    level = xp.level_from_total_xp(data.get("total_xp", 0))
    out = {"xp": 0, "entrance": False, "branching": 0, "treasure": False}
    for found in dungeon.catch_up(data, level):
        if found["xp"]:
            gained = carry.award(data, carry.XP_KEY, dungeon_xp_exact(data, found["xp"], owned))
            data["total_xp"] = data.get("total_xp", 0) + gained
            out["xp"] += gained
        for key in ("entrance", "treasure"):
            if found[key]:
                out[key] = True
        if found["branching"]:
            out["branching"] += 1
    return out


def resolve_dungeon_backlog(data: dict) -> dict:
    """Take the catch-up prompt's offer: auto-pick every branching this backlog produces. Treasures
    still stop the replay, since claiming stays the player's."""
    data[dungeon.KEY_CATCH_UP_AUTO] = True
    out = {"xp": 0, "entrance": False, "branching": 0, "treasure": False}
    while dungeon.pending(data):
        dungeon.choose_path(data, dungeon.auto_pick_index(data))
        got = apply_dungeon_catch_up(data)
        out["xp"] += got["xp"]
        out["branching"] += got["branching"]
        for key in ("entrance", "treasure"):
            out[key] = out[key] or got[key]
        if dungeon.treasure_ready(data):
            break
    return out


def claim_dungeon_treasure(data: dict) -> dict:
    """Pay out a reached treasure and close the dungeon. Returns what was paid. Amounts were fixed
    at discovery; only gem colors are rolled now, with multiplier=1 so a live buff can't double them
    again."""
    paid = {"gold": 0, "gems": 0, "item": None}
    # Guarded here too, since catch_up also calls this; closing early would pay the picks and end
    # the run.
    if not dungeon.treasure_ready(data):
        return paid
    totals = dungeon.treasure_totals(data)
    picked = [e.get("took") for e in dungeon.picks(data)]

    if totals["gold"]:
        gold = carry.award(data, carry.GOLD_KEY, float(totals["gold"]))
        data["money"] = data.get("money", 0) + gold
        paid["gold"] = gold
    for count, most_needed in totals["gem_entries"]:
        paid["gems"] += award_reward_gems(
            data,
            [shop.random_gem_color() for _ in range(count)],
            multiplier=1,
            most_needed=most_needed,
        )
    if totals["item"]:
        owned_list = data.setdefault("owned_collectibles", [])
        if totals["item"] not in owned_list:
            owned_list.append(totals["item"])
        paid["item"] = totals["item"]
        milestones.note_event(data, milestones.OBJ_LOOT)
        milestones.advance_if_complete(data)

    # The idle window's only record of the run just finished. Run state, so a prestige drops it.
    data["last_dungeon"] = {
        "branchings": len(picked),
        "picked": picked,
        "gold": paid["gold"],
        "gems": paid["gems"],
        "item": paid["item"],
    }
    dungeon.close(data)
    return paid


def apply_one_review(
    data: dict,
    ease: int,
    deck_name: str | None = None,
    is_new: bool = False,
    counts_as_due_review: bool = True,
    col=None,
) -> dict:
    """Apply one review to state: quest progress, XP, gold, gems, level, unlocks. Mutates data;
    caller saves. `col` enables the streak rollover check. Returns gold/gem earned, completed quests
    and undo deltas."""
    earned = {
        "gold_earned": 0,
        "gem_earned": 0,
        "completed_quests": [],
        "leveled_up": False,
    }
    # Refreshed before anything pays, or a new day's first review would pay yesterday's charge and
    # an expired buff.
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

    # Left out of the undo deltas: undo keeps a discovery and what it paid (the retry is charged
    # instead).
    _apply_dungeon_review(data, ease, owned, earned)

    level_gold, level_gems, leveled_up = grant_level_up(data, old_level, owned)
    if leveled_up:
        # Reported so the caller can name the cause; kept apart from the totals, since the level-up
        # has its own notification.
        earned["leveled_up"] = True
        earned["level_gold"] = level_gold
        earned["level_gems"] = level_gems
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
