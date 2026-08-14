"""
Daily quests: catalogue, rolling and progress.

Targets are derived from the reviews Anki actually scheduled for the player today (see
ag/due_baseline.py) rather than from fixed constants, so a quest is the same relative effort on a
20-card day and a 500-card day. See docs/quest-revamp.md for the design and its rationale.
"""
from __future__ import annotations

import random
from typing import Any

from . import due_baseline, streak

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

# Smallest target a quest may ask for. Without it a 5-due day rolling 70% would pay a full reward
# for 4 reviews. Correct answers are scarcer than reviews (Again never counts toward them), so the
# correct-quest floor is half the review floor.
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

# New-card quests ask for 3 to 6 cards. There is no percentage basis here — the day's new-card
# allowance is unusable, since it reads zero for players who introduce new cards through Custom
# Study — so the target is rolled from a flat range and the reward is interpolated across it:
# 3 cards pays the bottom of each range, 6 pays the top. Gem chance stays at upstream's flat value,
# which is a single number with no range to scale across.
NEW_CARDS_TARGET = (3, 6)
REWARD_NEW_XP = (25, 50)
REWARD_NEW_GOLD = (6, 12)
REWARD_NEW_GEM_PCT = 14.0

# --- Deck-quest eligibility ----------------------------------------------------------------------

DECK_MIN_SHARE = 0.15              # below this the quest is trivial and pays almost nothing
DECK_MAX_SHARE = 0.90              # above this it merely duplicates the all-decks quest
DECK_MIN_DUE = MIN_TARGET_REVIEWS  # so the floor can never ask for more cards than the deck holds


def _today_str() -> str:
    """Scheduler day (honours 'Next day starts at'), not civil midnight."""
    return streak.today_str()


# --- Target and reward maths ---------------------------------------------------------------------


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * t


def _band_position(target: int, basis: int, band: tuple[float, float]) -> float:
    """
    Where a quest sits within its band, 0..1, used to scale its reward.

    Derived from the target actually set, not from the raw roll. When MIN_TARGET overrides a low roll
    the target stops varying with the percentage, and paying by the (invisible) roll would hand
    identical quests wildly different rewards — 20 XP one day and 140 the next for the same work.
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
) -> dict[str, Any]:
    """
    Build one quest. The gold-or-gem choice is rolled here, at creation, and the colour pre-rolled,
    so that undoing a completion cannot reroll the reward into something better.
    """
    from . import shop

    reward_gem = random.random() * 100.0 < gem_pct
    out: dict[str, Any] = {
        "id": kind,
        "target": max(1, int(target)),
        "progress": 0,
        "reward_xp": max(0, int(round(reward_xp))),
        "reward_gold": 0 if reward_gem else max(0, int(round(reward_gold))),
        "reward_gem": reward_gem,
        "label": label,
    }
    if reward_gem:
        out["reward_gem_color"] = random.choice([c for c, _ in shop.GEM_COLORS])
    if extra:
        out.update(extra)
    return out


# --- Builders ------------------------------------------------------------------------------------


def _build_total_reviews(basis: int) -> dict[str, Any]:
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
        f"Complete {target} reviews",
    )


def _build_correct_reviews(basis: int) -> dict[str, Any]:
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
        f"Get {target} correct",
    )


def _build_deck_reviews(deck: dict[str, Any]) -> dict[str, Any]:
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
        f"Complete {target} reviews from {name}",
        {"deck_name": deck.get("name", ""), "deck_id": deck.get("id", "")},
    )


def _build_new_cards() -> dict[str, Any]:
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
        f"Review {target} new cards",
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
) -> list[dict[str, Any]]:
    """Roll `count` quests of distinct kinds, sized from today's due counts."""
    baseline = baseline or {}
    total = int(baseline.get("total", 0) or 0)
    decks = eligible_decks(baseline)
    kinds = _eligible_kinds(baseline, decks, col)

    out: list[dict[str, Any]] = []
    for kind in random.sample(kinds, min(count, len(kinds))):
        if kind == QUEST_KIND_TOTAL_REVIEWS:
            out.append(_build_total_reviews(total))
        elif kind == QUEST_KIND_CORRECT_REVIEWS:
            out.append(_build_correct_reviews(total))
        elif kind == QUEST_KIND_DECK_REVIEWS and decks:
            deck = random.choices(decks, weights=[d["due"] for d in decks], k=1)[0]
            out.append(_build_deck_reviews(deck))
        elif kind == QUEST_KIND_NEW_CARDS:
            out.append(_build_new_cards())
    return out


def _has_unknown_quests(state: dict[str, Any]) -> bool:
    """True if any stored quest predates the current catalogue (upstream ids, session quests, …)."""
    return any(q.get("id") not in QUEST_KINDS for q in (state.get("daily_quests") or []))


def ensure_daily_quests(state: dict[str, Any], col: Any = None) -> None:
    """
    Roll a new day's quests when the scheduler day has turned, and capture the due baseline they are
    sized from. Also swaps out quests left over from the old fixed-target catalogue, without
    resetting the day's counters.
    """
    today = _today_str()
    baseline = due_baseline.ensure_baseline(state, col)
    if baseline is None:
        # The collection could not be measured — profile_did_open can fire before it is loaded, and
        # deck_due_tree can fail transiently. Rolling now would size the whole day from a zero
        # baseline and stamp last_date, so nothing could correct it later. Leave the day untouched;
        # the next call (profile load retry, refresh, or first review) rolls with real numbers.
        return None
    if state.get("last_date") != today:
        state["last_date"] = today
        state["daily_xp"] = 0
        state["reviews_today"] = 0
        state["correct_today"] = 0
        state["daily_quests"] = roll_daily_quests(QUESTS_PER_DAY, baseline, col)
    elif _has_unknown_quests(state) or not state.get("daily_quests"):
        # Stale kinds from the old catalogue, or an empty list left by an interrupted roll.
        state["daily_quests"] = roll_daily_quests(QUESTS_PER_DAY, baseline, col)
    return None


# --- Progress ------------------------------------------------------------------------------------


def deck_matches(review_deck: str | None, quest_deck: str | None) -> bool:
    """
    A review counts toward a quest naming its deck or any ancestor of it.

    The "::" is required: without it a quest for "Japanese" would also collect reviews from an
    unrelated top-level deck called "JapaneseOther".
    """
    if not review_deck or not quest_deck:
        return False
    return review_deck == quest_deck or review_deck.startswith(quest_deck + "::")


def _resolve_quest_deck(q: dict[str, Any], col: Any) -> str | None:
    """
    Current name of a deck quest's target deck.

    Prefers the stored deck id so renaming a deck mid-day does not strand the quest; falls back to
    the name captured at roll time when the id is missing or the deck is gone.
    """
    did = q.get("deck_id")
    if did and col is not None:
        try:
            name = col.decks.name(int(did))
            if name:
                return name
        except Exception:
            pass
    return q.get("deck_name")


def on_review(
    state: dict[str, Any],
    ease: int,
    deck_name: str | None = None,
    is_new: bool = False,
    fixed_xp: int | None = None,
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

    from .xp import xp_for_review

    xp_this = fixed_xp if fixed_xp is not None else xp_for_review(ease_val)
    state["daily_xp"] = state.get("daily_xp", 0) + xp_this

    if ease_val >= 3:
        state["correct_today"] = state.get("correct_today", 0) + 1

    daily_quests = state.get("daily_quests", [])
    for i, q in enumerate(daily_quests):
        was_done = q.get("progress", 0) >= q.get("target", 0)
        kind = q.get("id", "")
        advance = False
        if kind == QUEST_KIND_TOTAL_REVIEWS:
            # Every answer counts, Again included: the quest asks for effort, not accuracy.
            advance = True
        elif kind == QUEST_KIND_DECK_REVIEWS:
            advance = deck_matches(deck_name, _resolve_quest_deck(q, col))
        elif kind == QUEST_KIND_NEW_CARDS:
            advance = bool(is_new)
        elif kind == QUEST_KIND_CORRECT_REVIEWS:
            # Tracks the day's running total rather than a per-review increment, so it stays correct
            # across sessions and undo.
            q["progress"] = min(state.get("correct_today", 0), q.get("target", 0))
        if advance:
            progress_before = q.get("progress", 0)
            quest_progress_revert.append((i, progress_before))
            q["progress"] = progress_before + 1
        if not was_done and q.get("progress", 0) >= q.get("target", 0):
            completed.append(q)
    return (completed, None, quest_progress_revert)
