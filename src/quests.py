"""
Daily quests: catalog, rolling and progress.

Targets are derived from the reviews Anki actually scheduled for the player today (see
src/due_baseline.py) rather than from fixed constants, so a quest is the same relative effort on a
20-card day and a 500-card day.
"""
from __future__ import annotations

import random
from typing import Any

from . import due_baseline, milestones, streak

# --- Quest kinds ---------------------------------------------------------------------------------

QUEST_KIND_TOTAL_REVIEWS = "quest_kind_total_reviews"
QUEST_KIND_DECK_REVIEWS = "quest_kind_deck_reviews"
QUEST_KIND_CORRECT_REVIEWS = "quest_kind_correct_reviews"
QUEST_KIND_NEW_CARDS = "quest_kind_new_cards"

QUEST_KINDS = (
    QUEST_KIND_TOTAL_REVIEWS,
    QUEST_KIND_DECK_REVIEWS,
    QUEST_KIND_CORRECT_REVIEWS,
    QUEST_KIND_NEW_CARDS,
)

QUESTS_PER_DAY = 2

# --- Targets -------------------------------------------------------------------------------------

# Fraction of the basis a target is rolled from.
BAND_REVIEWS = (0.30, 0.70)
BAND_CORRECT = (0.15, 0.30)

# Smallest target a quest may ask for: without it a 5-due day rolling 70% would pay a full reward
# for 4 reviews. Correct answers are scarcer, so their floor is half.
MIN_TARGET_REVIEWS = 30
MIN_TARGET_CORRECT = 15

# Below this many due cards percentages produce nothing meaningful; fall back to fixed targets so
# the player still has quests to look at.
LOW_VOLUME_FLOOR = 10
LOW_VOLUME_TARGET_REVIEWS = 10
LOW_VOLUME_TARGET_CORRECT = 5

# --- Rewards -------------------------------------------------------------------------------------
# (value at the bottom of the band, value at the top).

REWARD_TOTAL_XP = (20, 140)
REWARD_TOTAL_GOLD = (8, 24)
REWARD_TOTAL_GEM_PCT = (14.0, 30.0)

REWARD_CORRECT_XP = (30, 85)
REWARD_CORRECT_GOLD = (8, 18)
REWARD_CORRECT_GEM_PCT = (14.0, 22.0)

# New-card quests ask for 3 to 6 cards, rolled flat: the day's new-card allowance reads zero for
# players who use Custom Study, so there is no usable percentage basis. The reward is interpolated
# across that range; the gem chance is a single flat value.
NEW_CARDS_TARGET = (3, 6)
REWARD_NEW_XP = (25, 50)
REWARD_NEW_GOLD = (6, 12)
REWARD_NEW_GEM_PCT = 14.0

# --- Deck-quest eligibility ----------------------------------------------------------------------

DECK_MIN_SHARE = 0.15              # below this the quest is trivial and pays almost nothing
DECK_MAX_SHARE = 0.90              # above this it merely duplicates the all-decks quest
DECK_MIN_DUE = MIN_TARGET_REVIEWS  # so the floor can never ask for more cards than the deck holds


def _today_str() -> str:
    """Scheduler day (honors 'Next day starts at'), not civil midnight."""
    return streak.today_str()


# --- Target and reward math ----------------------------------------------------------------------


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * t


def _band_position(target: int, basis: int, band: tuple[float, float]) -> float:
    """
    Where a quest sits within its band, 0..1, used to scale its reward.

    Derived from the target actually set, not the raw roll: once MIN_TARGET overrides a low roll,
    paying by the invisible roll would give identical quests wildly different rewards.
    """
    lo, hi = band
    if basis <= 0 or hi <= lo:
        return 0.0
    p = min(hi, max(lo, target / basis))
    return (p - lo) / (hi - lo)


def _roll_target(basis: int, band: tuple[float, float], floor: int) -> int:
    return max(floor, int(round(random.uniform(*band) * basis)))


def _make_quest(
    kind: str,
    target: int,
    reward_xp: float,
    reward_gold: float,
    gem_pct: float,
    label: str,
    extra: dict[str, Any] | None = None,
    gem_multiplier: float = 1.0,
) -> dict[str, Any]:
    """
    Build one quest. The gem roll happens here, at creation, and the color with it, so that undoing a
    completion cannot reroll the reward into something better.

    The gem is paid in addition to the gold, never instead of it: substituting made every gem bonus
    a gold debuff, since raising the gem chance lowered gold income by the same stroke.
    """
    from . import review_rewards, shop

    gem_choices = [c for c, _ in shop.GEM_COLORS]
    gem_count = review_rewards.roll_gem_count(gem_pct * gem_multiplier)
    colors = [random.choice(gem_choices) for _ in range(gem_count)]
    out: dict[str, Any] = {
        "id": kind,
        "target": max(1, int(target)),
        "progress": 0,
        "reward_xp": max(0, int(round(reward_xp))),
        "reward_gold": max(0, int(round(reward_gold))),
        "reward_gem_colors": colors,
        # Written so an older build pays the same color rather than a random one (only the first).
        "reward_gem": bool(colors),
        "reward_gem_color": colors[0] if colors else None,
        "label": label,
    }
    if extra:
        out.update(extra)
    return out


# --- Builders ------------------------------------------------------------------------------------


def _build_total_reviews(basis: int, gem_multiplier: float = 1.0) -> dict[str, Any]:
    if basis < LOW_VOLUME_FLOOR:
        target, t = LOW_VOLUME_TARGET_REVIEWS, 0.0
    else:
        target = _roll_target(basis, BAND_REVIEWS, MIN_TARGET_REVIEWS)
        t = _band_position(target, basis, BAND_REVIEWS)
    return _make_quest(
        QUEST_KIND_TOTAL_REVIEWS,
        target,
        _lerp(REWARD_TOTAL_XP[0], REWARD_TOTAL_XP[1], t),
        _lerp(REWARD_TOTAL_GOLD[0], REWARD_TOTAL_GOLD[1], t),
        _lerp(REWARD_TOTAL_GEM_PCT[0], REWARD_TOTAL_GEM_PCT[1], t),
        f"Review {target} cards",
        gem_multiplier=gem_multiplier,
    )


def _build_correct_reviews(basis: int, gem_multiplier: float = 1.0) -> dict[str, Any]:
    if basis < LOW_VOLUME_FLOOR:
        target, t = LOW_VOLUME_TARGET_CORRECT, 0.0
    else:
        target = _roll_target(basis, BAND_CORRECT, MIN_TARGET_CORRECT)
        t = _band_position(target, basis, BAND_CORRECT)
    return _make_quest(
        QUEST_KIND_CORRECT_REVIEWS,
        target,
        _lerp(REWARD_CORRECT_XP[0], REWARD_CORRECT_XP[1], t),
        _lerp(REWARD_CORRECT_GOLD[0], REWARD_CORRECT_GOLD[1], t),
        _lerp(REWARD_CORRECT_GEM_PCT[0], REWARD_CORRECT_GEM_PCT[1], t),
        f"Get {target} answers correct",
        gem_multiplier=gem_multiplier,
    )


def _build_deck_reviews(deck: dict[str, Any], gem_multiplier: float = 1.0) -> dict[str, Any]:
    """
    Deck quest. Reward is the all-decks reward for the same band position, scaled by the deck's
    share of the day: half the reviews, half the reward. A single-deck collection would give
    share 1.0 and an identical quest, which is why DECK_MAX_SHARE excludes that case.
    """
    basis = int(deck["due"])
    share = float(deck["share"])
    target = _roll_target(basis, BAND_REVIEWS, MIN_TARGET_REVIEWS)
    t = _band_position(target, basis, BAND_REVIEWS)
    name = due_baseline.display_deck_name(deck.get("name", ""))
    return _make_quest(
        QUEST_KIND_DECK_REVIEWS,
        target,
        _lerp(REWARD_TOTAL_XP[0], REWARD_TOTAL_XP[1], t) * share,
        _lerp(REWARD_TOTAL_GOLD[0], REWARD_TOTAL_GOLD[1], t) * share,
        _lerp(REWARD_TOTAL_GEM_PCT[0], REWARD_TOTAL_GEM_PCT[1], t) * share,
        f"Review {target} cards from {name}",
        {"deck_name": deck.get("name", ""), "deck_id": deck.get("id", "")},
        gem_multiplier,
    )


def _build_new_cards(gem_multiplier: float = 1.0) -> dict[str, Any]:
    lo, hi = NEW_CARDS_TARGET
    target = random.randint(lo, hi)
    # Position within the target range, the same role _band_position plays for the other kinds:
    # it keeps pay tied to effort instead of rolling the two independently.
    t = (target - lo) / (hi - lo) if hi > lo else 0.0
    return _make_quest(
        QUEST_KIND_NEW_CARDS,
        target,
        _lerp(REWARD_NEW_XP[0], REWARD_NEW_XP[1], t),
        _lerp(REWARD_NEW_GOLD[0], REWARD_NEW_GOLD[1], t),
        REWARD_NEW_GEM_PCT,
        f"Study {target} new cards",
        gem_multiplier=gem_multiplier,
    )


# --- Rolling -------------------------------------------------------------------------------------


def eligible_decks(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    """Decks that can carry a deck quest, each with its share of the day's due count."""
    total = int(baseline.get("total", 0) or 0)
    if total <= 0:
        return []
    out: list[dict[str, Any]] = []
    for did, info in (baseline.get("decks") or {}).items():
        if info.get("filtered"):
            continue
        due = int(info.get("due", 0) or 0)
        if due < DECK_MIN_DUE:
            continue
        share = due / total
        # A lone deck has share 1.0 and fails the upper bound, so "player has at least two decks"
        # needs no separate check.
        if share < DECK_MIN_SHARE or share > DECK_MAX_SHARE:
            continue
        out.append({"id": did, "name": info.get("name", ""), "due": due, "share": share})
    return out


def _eligible_kinds(baseline: dict[str, Any], decks: list[dict[str, Any]], col: Any) -> list[str]:
    kinds = [QUEST_KIND_TOTAL_REVIEWS, QUEST_KIND_CORRECT_REVIEWS]
    if decks:
        kinds.append(QUEST_KIND_DECK_REVIEWS)
    if due_baseline.has_new_cards(col):
        kinds.append(QUEST_KIND_NEW_CARDS)
    return kinds


def roll_daily_quests(
    count: int = QUESTS_PER_DAY,
    baseline: dict[str, Any] | None = None,
    col: Any = None,
    gem_multiplier: float = 1.0,
) -> list[dict[str, Any]]:
    """Roll `count` quests of distinct kinds, sized from today's due counts.

    gem_multiplier scales each quest's gem chance by the player's gem luck, applied here because the
    reward is decided once at creation. A luck item bought later the same day therefore does not
    improve a quest already rolled, which is the same rule the gold-or-gem choice always followed.
    """
    baseline = baseline or {}
    total = int(baseline.get("total", 0) or 0)
    decks = eligible_decks(baseline)
    kinds = _eligible_kinds(baseline, decks, col)

    out: list[dict[str, Any]] = []
    for kind in random.sample(kinds, min(count, len(kinds))):
        if kind == QUEST_KIND_TOTAL_REVIEWS:
            out.append(_build_total_reviews(total, gem_multiplier))
        elif kind == QUEST_KIND_CORRECT_REVIEWS:
            out.append(_build_correct_reviews(total, gem_multiplier))
        elif kind == QUEST_KIND_DECK_REVIEWS and decks:
            deck = random.choices(decks, weights=[d["due"] for d in decks], k=1)[0]
            out.append(_build_deck_reviews(deck, gem_multiplier))
        elif kind == QUEST_KIND_NEW_CARDS:
            out.append(_build_new_cards(gem_multiplier))
    return out


def quest_gem_colors(q: dict[str, Any]) -> list[str]:
    """Gem colors one quest pays, newest storage first.

    Quests rolled before gem chances could exceed 100% stored a `reward_gem` bool and a single
    `reward_gem_color`; those saves keep paying exactly what they promised rather than being
    re-rolled under the new rule, which would change a reward the panel has already shown.

    The twin of `review_rewards.cleared_bonus_gem_colors`, falling back on the same rule - an empty
    list, not a missing key - so the two accessors read alike.
    """
    colors = [c for c in (q.get("reward_gem_colors") or []) if c]
    if colors:
        return colors
    if q.get("reward_gem"):
        from . import shop

        color = q.get("reward_gem_color")
        return [color] if color else [random.choice([c for c, _ in shop.GEM_COLORS])]
    return []


def reroll_quest(state: dict[str, Any], index: int, col: Any = None) -> dict[str, Any] | None:
    """
    Replace one of today's quests with a fresh one of a different kind. Returns the new quest.

    Returns None when it cannot help: a bad index, an unmeasurable day, or no other eligible kind
    to swap to - rerolling into the same kind would spend the week's allowance on a new target for
    the same job. The other quest is untouched, and the day's baseline is reused, so the
    replacement is sized from the same day.
    """
    quests = state.get("daily_quests") or []
    if index < 0 or index >= len(quests):
        return None
    baseline = state.get("quest_due_baseline") or {}
    if not baseline:
        return None
    decks = eligible_decks(baseline)
    kinds = _eligible_kinds(baseline, decks, col)
    # Every kind currently in play is off the table, not just the one being replaced: the two
    # quests are always of distinct kinds, and a reroll must not break that.
    in_play = {q.get("id") for i, q in enumerate(quests) if i != index}
    choices = [k for k in kinds if k not in in_play and k != quests[index].get("id")]
    if not choices:
        return None
    from . import review_rewards

    gem_mult = review_rewards.gem_luck_multiplier(state, state.get("owned_collectibles", []))
    total = int(baseline.get("total", 0) or 0)
    kind = random.choice(choices)
    if kind == QUEST_KIND_TOTAL_REVIEWS:
        new_quest = _build_total_reviews(total, gem_mult)
    elif kind == QUEST_KIND_CORRECT_REVIEWS:
        new_quest = _build_correct_reviews(total, gem_mult)
    elif kind == QUEST_KIND_DECK_REVIEWS and decks:
        deck = random.choices(decks, weights=[d["due"] for d in decks], k=1)[0]
        new_quest = _build_deck_reviews(deck, gem_mult)
    elif kind == QUEST_KIND_NEW_CARDS:
        new_quest = _build_new_cards(gem_mult)
    else:
        return None
    # The correct-answers quest tracks the day's running total, so a fresh one starts from what is
    # already answered rather than showing 0/N beside a day's work. Capped one short of the target:
    # on_review only pays a quest that crosses into finished, so one handed over already at its
    # target would sit at N/N forever having paid nothing.
    if kind == QUEST_KIND_CORRECT_REVIEWS:
        target = int(new_quest.get("target", 0))
        new_quest["progress"] = min(state.get("correct_today", 0), max(0, target - 1))
    quests[index] = new_quest
    state["daily_quests"] = quests
    return new_quest


def _has_unknown_quests(state: dict[str, Any]) -> bool:
    """True if any stored quest predates the current catalog (upstream ids, session quests, …)."""
    return any(q.get("id") not in QUEST_KINDS for q in (state.get("daily_quests") or []))


def ensure_daily_quests(state: dict[str, Any], col: Any = None) -> None:
    """
    Roll a new day's quests when the scheduler day has turned, and capture the due baseline they are
    sized from. Also swaps out quests left over from the old fixed-target catalog, without
    resetting the day's counters.
    """
    today = _today_str()
    # The clear-the-day quest settles its reward here too, so all three decide what they pay at the
    # same moment. Above the baseline guard: that choice does not depend on the day's due counts.
    from . import review_rewards

    gem_mult = review_rewards.gem_luck_multiplier(state, state.get("owned_collectibles", []))
    review_rewards.ensure_cleared_bonus_reward(state, streak.today_str(col))
    baseline = due_baseline.ensure_baseline(state, col)
    if baseline is None:
        # The collection could not be measured. Rolling now would size the whole day from a zero
        # baseline and stamp last_date, past correcting; the next call rolls with real numbers.
        return None
    if state.get("last_date") != today:
        state["last_date"] = today
        state["reviews_today"] = 0
        state["correct_today"] = 0
        state["daily_quests"] = roll_daily_quests(QUESTS_PER_DAY, baseline, col, gem_mult)
    elif _has_unknown_quests(state) or not state.get("daily_quests"):
        # Stale kinds from the old catalog, or an empty list left by an interrupted roll.
        state["daily_quests"] = roll_daily_quests(QUESTS_PER_DAY, baseline, col, gem_mult)
    return None


# --- Progress ------------------------------------------------------------------------------------


def deck_matches(review_deck: str | None, quest_deck: str | None) -> bool:
    """
    A review counts toward a quest naming its deck or any ancestor of it.

    The "::" is required, or a quest for "Japanese" would also collect "JapaneseOther".
    """
    if not review_deck or not quest_deck:
        return False
    return review_deck == quest_deck or review_deck.startswith(quest_deck + "::")


# What col.decks.name() returns for an id that no longer exists - it neither raises nor returns
# empty, so a deleted deck has to be recognized by this placeholder.
_MISSING_DECK_NAME = "[no deck]"


def _resolve_quest_deck(q: dict[str, Any], col: Any) -> str | None:
    """
    Current name of a deck quest's target deck, or None when that deck no longer exists.

    Prefers the stored deck id, so renaming a deck mid-day does not strand the quest. The name
    captured at roll time is only a fallback for a quest with no deck id.
    """
    did = q.get("deck_id")
    if did and col is not None:
        try:
            name = col.decks.name(int(did))
        except Exception:
            name = None
        if name == _MISSING_DECK_NAME:
            return None
        if name:
            return name
    return q.get("deck_name")


def deck_quest_is_orphaned(q: dict[str, Any], col: Any) -> bool:
    """
    True when a deck quest names a deck that no longer exists, so it can never be completed.

    Left in state rather than dropped - quest_progress_revert stores positions within daily_quests,
    so removing an entry would shift the indexes a pending undo refers to. The UI hides the row.
    """
    if q.get("id") != QUEST_KIND_DECK_REVIEWS:
        return False
    return _resolve_quest_deck(q, col) is None


def quest_display_label(q: dict[str, Any], col: Any = None) -> str:
    """
    Label to show for a quest, rebuilt from the deck's current name.

    The label stored at roll time freezes the deck name, which a rename would then contradict.
    Shared with the completion tooltip so the panel and the notification never disagree.
    """
    stored = q.get("label", "?")
    if q.get("id") != QUEST_KIND_DECK_REVIEWS:
        return stored
    name = _resolve_quest_deck(q, col)
    if not name:
        return stored
    return f"Review {q.get('target', 0)} cards from {due_baseline.display_deck_name(name)}"


def on_review(
    state: dict[str, Any],
    ease: int,
    deck_name: str | None = None,
    is_new: bool = False,
    counts_as_due_review: bool = True,
    col: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[tuple[int, int]]]:
    """
    Update state for one review. Ease 1=Again, 2=Hard, 3=Good, 4=Easy.
    Returns (quests just completed, streak_reward or None, quest_progress_revert).
    quest_progress_revert is (index, progress_before) per advanced quest, for undo.
    """
    ease_val = ease if isinstance(ease, int) else 3
    is_again = ease_val <= 1
    ensure_daily_quests(state, col=col)

    completed: list[dict[str, Any]] = []
    quest_progress_revert: list[tuple[int, int]] = []

    # The shop gate counts passed reviews only, so Again is excluded here even though quests count
    # every answer.
    if not is_again:
        state["reviews_today"] = state.get("reviews_today", 0) + 1

    # Every answer, learning ones included: this quest asks for correct answers, not reviews, which
    # is why its label names answers where the review quests name cards.
    if ease_val >= 3:
        state["correct_today"] = state.get("correct_today", 0) + 1

    daily_quests = state.get("daily_quests", [])
    for i, q in enumerate(daily_quests):
        was_done = q.get("progress", 0) >= q.get("target", 0)
        kind = q.get("id", "")
        advance = False
        if kind == QUEST_KIND_TOTAL_REVIEWS:
            # Again counts (the quest asks for effort, not accuracy); a card studied new today
            # does not. The target is a fraction of the day's due count, so exactly the answers
            # that count belongs to may advance it - see due_baseline.counts_as_due_review_sql().
            advance = counts_as_due_review
        elif kind == QUEST_KIND_DECK_REVIEWS:
            advance = counts_as_due_review and deck_matches(deck_name, _resolve_quest_deck(q, col))
        elif kind == QUEST_KIND_NEW_CARDS:
            advance = bool(is_new)
        elif kind == QUEST_KIND_CORRECT_REVIEWS:
            # Tracks the day's running total rather than a per-review increment, so it stays correct
            # across sessions and undo.
            q["progress"] = min(state.get("correct_today", 0), q.get("target", 0))
        if advance:
            progress_before = q.get("progress", 0)
            # A finished quest stops counting, so it reads 46/46 rather than 51/46.
            if progress_before < q.get("target", 0):
                quest_progress_revert.append((i, progress_before))
                q["progress"] = progress_before + 1
        if not was_done and q.get("progress", 0) >= q.get("target", 0):
            completed.append(q)

    # The both-quests objective is judged from the quests themselves, not from `completed`, which
    # holds only what this answer finished. The check here is a fast path that keeps a scheduler-day
    # lookup off every answer; note_both_quests_complete re-reads the pair, since this one cannot
    # tell a finished pair from a stale one. Streak milestones need no event, hence the bare advance.
    if daily_quests and all(q.get("progress", 0) >= q.get("target", 0) for q in daily_quests):
        milestones.note_both_quests_complete(state, col)
    milestones.advance_if_complete(state, col)

    return (completed, None, quest_progress_revert)
