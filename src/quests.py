"""Daily quests: catalog, rolling and progress. Targets come from today's scheduled reviews (see
due_baseline.py), so a quest is the same relative effort on any size of day."""
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

REWARD_TOTAL_XP = (60, 220)
REWARD_TOTAL_GOLD = (8, 24)
REWARD_TOTAL_GEM_PCT = (14.0, 30.0)

REWARD_CORRECT_XP = (70, 160)
REWARD_CORRECT_GOLD = (8, 18)
REWARD_CORRECT_GEM_PCT = (14.0, 22.0)

# New-card quests ask for 3 to 5 cards (weighted low), since the new-card allowance reads zero for
# Custom Study players. Reward interpolates across the range; the gem chance is flat.
NEW_CARDS_TARGET_WEIGHTS = {3: 3, 4: 2, 5: 1}
NEW_CARDS_TARGET = (min(NEW_CARDS_TARGET_WEIGHTS), max(NEW_CARDS_TARGET_WEIGHTS))
REWARD_NEW_XP = (50, 100)
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
    """Where a quest sits within its band, 0..1, for scaling its reward. From the target actually
    set, since MIN_TARGET can override the roll."""
    lo, hi = band
    if basis <= 0 or hi <= lo:
        return 0.0
    p = min(hi, max(lo, target / basis))
    return (p - lo) / (hi - lo)


def _roll_target(basis: int, band: tuple[float, float], floor: int) -> int:
    return max(floor, int(round(random.uniform(*band) * basis)))


def _lowest_roll(basis: int, band: tuple[float, float], floor: int) -> int:
    """The smallest target _roll_target can return for this basis."""
    return max(floor, int(round(band[0] * basis)))


def _capped(target: int, cap: int | None) -> int:
    """A rolled target no bigger than what the day has left (a reroll's cap; None for none)."""
    return target if cap is None else min(target, cap)


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
    """Build one quest. The gem and its color are rolled now, so undo can't reroll the reward. Gems
    pay on top of gold, never instead."""
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


def _build_total_reviews(
    basis: int, gem_multiplier: float = 1.0, cap: int | None = None
) -> dict[str, Any]:
    if basis < LOW_VOLUME_FLOOR:
        target, t = _capped(LOW_VOLUME_TARGET_REVIEWS, cap), 0.0
    else:
        target = _capped(_roll_target(basis, BAND_REVIEWS, MIN_TARGET_REVIEWS), cap)
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


def _build_correct_reviews(
    basis: int, gem_multiplier: float = 1.0, cap: int | None = None
) -> dict[str, Any]:
    if basis < LOW_VOLUME_FLOOR:
        target, t = _capped(LOW_VOLUME_TARGET_CORRECT, cap), 0.0
    else:
        target = _capped(_roll_target(basis, BAND_CORRECT, MIN_TARGET_CORRECT), cap)
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


def _build_deck_reviews(
    deck: dict[str, Any], gem_multiplier: float = 1.0, cap: int | None = None
) -> dict[str, Any]:
    """Deck quest: the all-decks reward for the same band position, scaled by the deck's share of
    the day. DECK_MAX_SHARE excludes single-deck collections."""
    basis = int(deck["due"])
    share = float(deck["share"])
    target = _capped(_roll_target(basis, BAND_REVIEWS, MIN_TARGET_REVIEWS), cap)
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


def _build_new_cards(gem_multiplier: float = 1.0, cap: int | None = None) -> dict[str, Any]:
    lo, hi = NEW_CARDS_TARGET
    target = random.choices(
        list(NEW_CARDS_TARGET_WEIGHTS), weights=list(NEW_CARDS_TARGET_WEIGHTS.values()), k=1
    )[0]
    target = _capped(target, cap)
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


def _eligible_kinds(decks: list[dict[str, Any]], new_cards: int) -> list[str]:
    kinds = [QUEST_KIND_TOTAL_REVIEWS, QUEST_KIND_CORRECT_REVIEWS]
    if decks:
        kinds.append(QUEST_KIND_DECK_REVIEWS)
    # Enough for the smallest target; the roll is then capped at the count.
    if new_cards >= NEW_CARDS_TARGET[0]:
        kinds.append(QUEST_KIND_NEW_CARDS)
    return kinds


def roll_daily_quests(
    count: int = QUESTS_PER_DAY,
    baseline: dict[str, Any] | None = None,
    col: Any = None,
    gem_multiplier: float = 1.0,
    correct_today: int = 0,
) -> list[dict[str, Any]]:
    """Roll `count` quests of distinct kinds, sized from today's due counts. gem_multiplier applies
    gem luck at creation, so later purchases don't change a rolled quest."""
    baseline = baseline or {}
    total = int(baseline.get("total", 0) or 0)
    decks = eligible_decks(baseline)
    new_cards = due_baseline.new_card_count(col)
    kinds = _eligible_kinds(decks, new_cards)

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
            out.append(_build_new_cards(gem_multiplier, cap=new_cards))
    _stamp_correct_start(out, correct_today)
    return out


def quest_gem_colors(q: dict[str, Any]) -> list[str]:
    """Gem colors one quest pays. Falls back to the legacy `reward_gem`/`reward_gem_color` pair when
    the list is empty, like review_rewards.cleared_bonus_gem_colors."""
    colors = [c for c in (q.get("reward_gem_colors") or []) if c]
    if colors:
        return colors
    if q.get("reward_gem"):
        from . import shop

        color = q.get("reward_gem_color")
        return [color] if color else [random.choice([c for c, _ in shop.GEM_COLORS])]
    return []


# --- Rerolling -----------------------------------------------------------------------------------

REROLL_BLOCKED_NO_OTHER = "No other quest available to swap to today."
REROLL_BLOCKED_NOT_ENOUGH = "Not enough reviews remain to reroll this quest."

# One quest the day could hold: its kind, plus the deck for a deck quest.
QuestOption = tuple[str, "dict[str, Any] | None"]


def _quest_options(baseline: dict[str, Any], new_cards: int) -> list[QuestOption]:
    """Every quest the day could roll, one per deck for deck quests."""
    decks = eligible_decks(baseline)
    out: list[QuestOption] = []
    for kind in _eligible_kinds(decks, new_cards):
        if kind == QUEST_KIND_DECK_REVIEWS:
            out.extend((kind, d) for d in decks)
        else:
            out.append((kind, None))
    return out


def _lowest_target(option: QuestOption, baseline: dict[str, Any]) -> int:
    """The smallest target this option's builder can roll. Mirrors the builders above."""
    kind, deck = option
    total = int(baseline.get("total", 0) or 0)
    if kind == QUEST_KIND_NEW_CARDS:
        return NEW_CARDS_TARGET[0]
    if kind == QUEST_KIND_DECK_REVIEWS:
        return _lowest_roll(int(deck["due"]), BAND_REVIEWS, MIN_TARGET_REVIEWS)
    if kind == QUEST_KIND_CORRECT_REVIEWS:
        if total < LOW_VOLUME_FLOOR:
            return LOW_VOLUME_TARGET_CORRECT
        return _lowest_roll(total, BAND_CORRECT, MIN_TARGET_CORRECT)
    if total < LOW_VOLUME_FLOOR:
        return LOW_VOLUME_TARGET_REVIEWS
    return _lowest_roll(total, BAND_REVIEWS, MIN_TARGET_REVIEWS)


def _available_today(option: QuestOption, remaining: dict[str, Any]) -> int:
    """How much of what this option counts is still left today (see due_baseline.remaining_today)."""
    kind, deck = option
    if kind == QUEST_KIND_NEW_CARDS:
        return int(remaining.get("new", 0) or 0)
    if kind == QUEST_KIND_DECK_REVIEWS:
        return int((remaining.get("decks") or {}).get(str(deck["id"]), 0) or 0)
    return int(remaining.get("total", 0) or 0)


def _reroll_choices(
    state: dict[str, Any], index: int, col: Any, remaining: dict[str, Any] | None
) -> tuple[list[QuestOption], list[QuestOption]] | None:
    """(every quest the reroll could swap to, those still completable today), or None when this
    quest can't be rerolled at all. An unmeasurable `remaining` filters nothing."""
    quests = state.get("daily_quests") or []
    if index < 0 or index >= len(quests):
        return None
    # A finished quest already paid; replacing it would let it pay again. Enforced here, not just in
    # the UI.
    target = int(quests[index].get("target", 0) or 0)
    if int(quests[index].get("progress", 0) or 0) >= target:
        return None
    baseline = state.get("quest_due_baseline") or {}
    if not baseline:
        return None
    # Every kind currently in play is off the table, not just the one being replaced: the two
    # quests are always of distinct kinds, and a reroll must not break that.
    taken = {q.get("id") for q in quests}
    new_cards = due_baseline.new_card_count(col) if remaining is None else int(remaining.get("new", 0) or 0)
    options = [o for o in _quest_options(baseline, new_cards) if o[0] not in taken]
    if remaining is None:
        return (options, options)
    completable = [o for o in options if _available_today(o, remaining) >= _lowest_target(o, baseline)]
    return (options, completable)


def reroll_block_reason(
    state: dict[str, Any], index: int, col: Any, remaining: dict[str, Any] | None
) -> str | None:
    """Why this quest can't be rerolled right now, or None if it can. `remaining` is
    due_baseline.remaining_today(), measured once by the caller for all rows."""
    choices = _reroll_choices(state, index, col, remaining)
    if choices is None or not choices[0]:
        return REROLL_BLOCKED_NO_OTHER
    if not choices[1]:
        return REROLL_BLOCKED_NOT_ENOUGH
    return None


def reroll_quest(state: dict[str, Any], index: int, col: Any = None) -> dict[str, Any] | None:
    """Replace one of today's quests with a fresh one of a different kind, sized from the same
    baseline, completable today and capped at what's left. Returns the new quest, or None (see
    reroll_block_reason)."""
    remaining = due_baseline.remaining_today(col)
    choices = _reroll_choices(state, index, col, remaining)
    if choices is None or not choices[1]:
        return None
    completable = choices[1]
    # Kind first, then deck, so a collection with many decks doesn't crowd out the other kinds.
    kind = random.choice(list(dict.fromkeys(k for k, _ in completable)))
    options = [o for o in completable if o[0] == kind]
    option = random.choices(options, weights=[int((d or {}).get("due", 1)) for _, d in options], k=1)[0]
    from . import review_rewards

    gem_mult = review_rewards.gem_luck_multiplier(state, state.get("owned_collectibles", []))
    total = int((state.get("quest_due_baseline") or {}).get("total", 0) or 0)
    # Never asks for more than the day has left; the reward follows the smaller target.
    cap = None if remaining is None else _available_today(option, remaining)
    if kind == QUEST_KIND_TOTAL_REVIEWS:
        new_quest = _build_total_reviews(total, gem_mult, cap)
    elif kind == QUEST_KIND_CORRECT_REVIEWS:
        new_quest = _build_correct_reviews(total, gem_mult, cap)
    elif kind == QUEST_KIND_DECK_REVIEWS:
        new_quest = _build_deck_reviews(option[1], gem_mult, cap)
    elif kind == QUEST_KIND_NEW_CARDS:
        new_quest = _build_new_cards(gem_mult, cap)
    else:
        return None
    _stamp_correct_start([new_quest], state.get("correct_today", 0))
    state["daily_quests"][index] = new_quest
    return new_quest


def _has_unknown_quests(state: dict[str, Any]) -> bool:
    """True if any stored quest predates the current catalog (upstream ids, session quests, …)."""
    return any(q.get("id") not in QUEST_KINDS for q in (state.get("daily_quests") or []))


def ensure_daily_quests(state: dict[str, Any], col: Any = None) -> None:
    """Roll a new day's quests when the scheduler day turns and capture their due baseline. Also
    swaps out quests from the old fixed-target catalog."""
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
        state["daily_quests"] = roll_daily_quests(
            QUESTS_PER_DAY, baseline, col, gem_mult, state.get("correct_today", 0)
        )
    return None


def _stamp_correct_start(quest_list: list[dict[str, Any]], correct_today: int) -> None:
    """Start correct-answers quests from today's count now, so answers given before they appeared
    don't count. A quest without the stamp (an older save's) counts from 0."""
    for q in quest_list:
        if q.get("id") == QUEST_KIND_CORRECT_REVIEWS:
            q["correct_start"] = int(correct_today or 0)
            q["progress"] = 0


def correct_quest_progress(q: dict[str, Any], correct_today: int) -> int:
    """A correct-answers quest's progress: answers since it appeared, at most its target."""
    since = int(correct_today or 0) - int(q.get("correct_start", 0) or 0)
    return min(max(0, since), int(q.get("target", 0) or 0))


# --- Progress ------------------------------------------------------------------------------------


def deck_matches(review_deck: str | None, quest_deck: str | None) -> bool:
    """A review counts toward a quest naming its deck or any ancestor ("::" required, so "Japanese"
    doesn't match "JapaneseOther")."""
    if not review_deck or not quest_deck:
        return False
    return review_deck == quest_deck or review_deck.startswith(quest_deck + "::")


# What col.decks.name() returns for an id that no longer exists - it neither raises nor returns
# empty, so a deleted deck has to be recognized by this placeholder.
_MISSING_DECK_NAME = "[no deck]"


def _resolve_quest_deck(q: dict[str, Any], col: Any) -> str | None:
    """Current name of a deck quest's deck, or None if it's gone. Prefers the stored deck id, so a
    rename doesn't strand the quest."""
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
    """True when a deck quest names a deleted deck. Left in state, since quest_progress_revert
    stores indexes into daily_quests; the UI hides the row."""
    if q.get("id") != QUEST_KIND_DECK_REVIEWS:
        return False
    return _resolve_quest_deck(q, col) is None


def quest_display_order(q: dict[str, Any]) -> int:
    """A quest kind's place in the fixed display order (as in the wiki's table), so kinds keep their
    rows. Unknown kinds sort last."""
    try:
        return QUEST_KINDS.index(q.get("id"))
    except ValueError:
        return len(QUEST_KINDS)


def quest_display_label(q: dict[str, Any], col: Any = None) -> str:
    """Label to show for a quest, rebuilt from the deck's current name. Shared with the completion
    tooltip so the two agree."""
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
    """Update state for one review (ease 1=Again .. 4=Easy). Returns (completed quests,
    streak_reward or None, quest_progress_revert), the last being (index, progress_before) per
    advanced quest."""
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
            # Again counts (effort, not accuracy); cards new today don't. See
            # due_baseline.counts_as_due_review_sql().
            advance = counts_as_due_review
        elif kind == QUEST_KIND_DECK_REVIEWS:
            advance = counts_as_due_review and deck_matches(deck_name, _resolve_quest_deck(q, col))
        elif kind == QUEST_KIND_NEW_CARDS:
            advance = bool(is_new)
        elif kind == QUEST_KIND_CORRECT_REVIEWS:
            # Read off the day's running total rather than a per-review increment, so it stays
            # correct across sessions and undo.
            q["progress"] = correct_quest_progress(q, state.get("correct_today", 0))
        if advance:
            progress_before = q.get("progress", 0)
            # A finished quest stops counting, so it reads 46/46 rather than 51/46.
            if progress_before < q.get("target", 0):
                quest_progress_revert.append((i, progress_before))
                q["progress"] = progress_before + 1
        if not was_done and q.get("progress", 0) >= q.get("target", 0):
            completed.append(q)

    # Fast path so the scheduler-day lookup isn't on every answer; note_both_quests_complete
    # re-reads the pair. Streak milestones need no event, hence the bare advance.
    if daily_quests and all(q.get("progress", 0) >= q.get("target", 0) for q in daily_quests):
        milestones.note_both_quests_complete(state, col)
    milestones.advance_if_complete(state, col)

    return (completed, None, quest_progress_revert)
