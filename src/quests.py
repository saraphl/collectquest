"""
Daily quests: catalog, rolling and progress.

Targets are derived from the reviews Anki actually scheduled for the player today (see
src/due_baseline.py) rather than from fixed constants, so a quest is the same relative effort on a
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
    """Scheduler day (honors 'Next day starts at'), not civil midnight."""
    return streak.today_str()


# --- Target and reward math ----------------------------------------------------------------------


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
    Build one quest. The gold-or-gem choice is rolled here, at creation, and the color pre-rolled,
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
        f"Review {target} cards",
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
        f"Get {target} answers correct",
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
        f"Review {target} cards from {name}",
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
        f"Study {target} new cards",
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
    """True if any stored quest predates the current catalog (upstream ids, session quests, …)."""
    return any(q.get("id") not in QUEST_KINDS for q in (state.get("daily_quests") or []))


def ensure_daily_quests(state: dict[str, Any], col: Any = None) -> None:
    """
    Roll a new day's quests when the scheduler day has turned, and capture the due baseline they are
    sized from. Also swaps out quests left over from the old fixed-target catalog, without
    resetting the day's counters.
    """
    today = _today_str()
    # The clear-the-day quest settles its reward here too, so all three quests decide what they pay
    # at the same moment. Above the baseline guard on purpose: the gold-or-gem choice does not
    # depend on the day's due counts, so there is no reason for an unmeasurable collection to leave
    # it unsettled and the panel showing a previous day's answer. No-op once done for the day.
    from . import review_rewards

    review_rewards.ensure_cleared_bonus_reward(state, streak.today_str(col))
    baseline = due_baseline.ensure_baseline(state, col)
    if baseline is None:
        # The collection could not be measured — profile_did_open can fire before it is loaded, and
        # deck_due_tree can fail transiently. Rolling now would size the whole day from a zero
        # baseline and stamp last_date, so nothing could correct it later. Leave the day untouched;
        # the next call (profile load retry, refresh, or first review) rolls with real numbers.
        return None
    if state.get("last_date") != today:
        state["last_date"] = today
        state["reviews_today"] = 0
        state["correct_today"] = 0
        state["daily_quests"] = roll_daily_quests(QUESTS_PER_DAY, baseline, col)
    elif _has_unknown_quests(state) or not state.get("daily_quests"):
        # Stale kinds from the old catalog, or an empty list left by an interrupted roll.
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


# What col.decks.name() returns for an id that no longer exists. It does not raise and does not
# return empty, so a deleted deck has to be recognized by this placeholder or it would be treated
# as an ordinary deck name that no review can ever match.
_MISSING_DECK_NAME = "[no deck]"


def _resolve_quest_deck(q: dict[str, Any], col: Any) -> str | None:
    """
    Current name of a deck quest's target deck, or None when that deck no longer exists.

    Prefers the stored deck id so renaming a deck mid-day does not strand the quest. Falls back to
    the name captured at roll time only when the quest has no deck id at all — for a deck that has
    been deleted the old name is no help, because deleting a deck deletes its cards too.
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

    The quest is left in state rather than dropped: quest_progress_revert stores positions within
    daily_quests, so removing an entry would shift the indexes a pending undo still refers to. The
    UI hides the row instead.
    """
    if q.get("id") != QUEST_KIND_DECK_REVIEWS:
        return False
    return _resolve_quest_deck(q, col) is None


def quest_display_label(q: dict[str, Any], col: Any = None) -> str:
    """
    Label to show for a quest, rebuilt from the deck's current name.

    The label stored at roll time freezes the deck name, so a deck renamed mid-day would keep being
    announced under its old name even though the quest correctly follows the rename by deck id.
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

    # Counted for every answer, learning ones included: this quest asks for correct answers rather
    # than for reviews, which is why its label names answers and the review quests name cards.
    if ease_val >= 3:
        state["correct_today"] = state.get("correct_today", 0) + 1

    daily_quests = state.get("daily_quests", [])
    for i, q in enumerate(daily_quests):
        was_done = q.get("progress", 0) >= q.get("target", 0)
        kind = q.get("id", "")
        advance = False
        if kind == QUEST_KIND_TOTAL_REVIEWS:
            # Every answer counts, Again included: the quest asks for effort, not accuracy. Studying
            # a card new today does not. The target is a fraction of the day's due count, so it is
            # exactly the answers that count belongs to that may advance it — a card the count never
            # included would finish the quest with work it was never sized from, and a card it did
            # include (one already learning as the day began) has to be creditable or the target
            # holds cards its own answers cannot reach. due_baseline.counts_as_due_review_sql()
            # decides which, for this and for the clear-the-day bonus alike.
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
    return (completed, None, quest_progress_revert)
