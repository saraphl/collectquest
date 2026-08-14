"""Daily quests: definitions and rolling. At creation we roll reward (1 gem or gold) per quest and display it."""
from __future__ import annotations

import random
from datetime import datetime
from typing import Any

# Difficulty multipliers for quest targets
# Easy: 20% less, Normal: unchanged, Hard: 20% more
DIFFICULTY_TARGET_MULT = {
    "easy": 0.8,
    "normal": 1.0,
    "hard": 1.2,
}

# Quest type id -> (target_min, target_max, xp_min, xp_max, gold_min, gold_max, gem_chance_percent, label_template)
# gem_chance_percent nerfed by ~6 points across the board to reduce base quest gem rate.
QUEST_DEFS: dict[str, tuple[int, int, int, int, int, int, int, str]] = {
    # More cards (review counts) - gem chance 14–30%
    "reviews_10": (10, 14, 20, 35, 8, 14, 14, "Complete {target} reviews"),
    "reviews_20": (18, 25, 45, 70, 10, 16, 18, "Complete {target} reviews"),
    "reviews_30": (28, 38, 70, 100, 12, 20, 24, "Complete {target} reviews"),
    "reviews_big": (40, 55, 95, 140, 14, 24, 30, "Complete {target} reviews"),
    # Correct today (total correct this day; persists across sessions)
    "correct_today_12": (10, 14, 30, 50, 8, 14, 14, "Get {target} correct today"),
    "correct_today_25": (20, 28, 55, 85, 10, 18, 22, "Get {target} correct today"),
    # Session / "clear a deck" style: finish a batch
    "session_15": (15, 18, 35, 55, 9, 15, 18, "Session: {target} reviews"),
    "session_25": (22, 28, 60, 95, 12, 20, 24, "Session: {target} reviews"),
    # Contextual: offered when deck has due cards / new cards available (filled at roll time)
    "deck_reviews": (5, 12, 30, 55, 8, 14, 18, "Complete {target} reviews in {deck_name}"),
    "new_cards": (3, 8, 25, 50, 6, 12, 14, "Review {target} new cards"),
}


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


BASE_QUEST_KEYS = [k for k in QUEST_DEFS if k not in ("deck_reviews", "new_cards")]


def _adjust_target(target: int, difficulty: str) -> int:
    """Apply difficulty multiplier to quest target (easy=80%, normal=100%, hard=120%)."""
    mult = DIFFICULTY_TARGET_MULT.get(difficulty, 1.0)
    adjusted = int(round(target * mult))
    return max(1, adjusted)  # at least 1


def _make_quest(k: str, target: int, deck_name: str | None = None) -> dict[str, Any]:
    from . import shop
    t_lo, t_hi, xp_lo, xp_hi, g_lo, g_hi, gem_chance, label_tpl = QUEST_DEFS[k]
    reward_xp = random.randint(xp_lo, xp_hi)
    # Roll at creation: gem chance → reward is "1 gem" (no gold); else rolled gold. Pre-roll color so undo doesn't reroll.
    reward_gem = random.randint(0, 99) < gem_chance
    reward_gold = 0 if reward_gem else random.randint(g_lo, g_hi)
    reward_gem_color = random.choice([c for c, _ in shop.GEM_COLORS]) if reward_gem else None
    label = label_tpl.format(target=target, deck_name=deck_name or "")
    out = {
        "id": k,
        "target": target,
        "progress": 0,
        "reward_xp": reward_xp,
        "reward_gold": reward_gold,
        "reward_gem": reward_gem,
        "label": label,
        **({"deck_name": deck_name} if deck_name else {}),
    }
    if reward_gem_color is not None:
        out["reward_gem_color"] = reward_gem_color
    return out


def roll_one_correct_today_quest(difficulty: str = "normal") -> dict[str, Any]:
    """Roll a single brand-new 'correct today' quest. Used when replacing old in-a-row quests."""
    k = random.choice(["correct_today_12", "correct_today_25"])
    t_lo, t_hi, xp_lo, xp_hi, g_lo, g_hi, gem_chance, label_tpl = QUEST_DEFS[k]
    target = random.randint(t_lo, t_hi)
    target = _adjust_target(target, difficulty)
    return _make_quest(k, target)


def roll_daily_quests(
    count: int = 2,
    deck_name: str | None = None,
    deck_due: int = 0,
    new_count: int = 0,
    difficulty: str = "normal",
) -> list[dict[str, Any]]:
    """Roll `count` random daily quests. Difficulty adjusts targets (easy=80%, normal=100%, hard=120%)."""
    out: list[dict[str, Any]] = []
    base = list(BASE_QUEST_KEYS)
    # Decide second quest: prefer one contextual (deck or new cards) when available.
    # Only offer deck_reviews when deck has enough due cards to complete the quest (min 10).
    can_deck = deck_name and deck_due >= 10
    can_new = new_count >= 3
    if can_deck or can_new:
        if can_deck and (not can_new or random.random() < 0.5):
            t_lo, t_hi, _, _, _, _, _, _ = QUEST_DEFS["deck_reviews"]
            target = min(random.randint(t_lo, t_hi), deck_due)
            target = _adjust_target(target, difficulty)
            target = min(target, deck_due)  # never exceed due count (e.g. after hard multiplier)
            out.append(_make_quest("deck_reviews", target, deck_name))
        else:
            t_lo, t_hi, _, _, _, _, _, _ = QUEST_DEFS["new_cards"]
            target = min(random.randint(t_lo, t_hi), new_count)
            target = _adjust_target(target, difficulty)
            target = min(target, new_count)  # never exceed available new cards
            out.append(_make_quest("new_cards", target))
    # Fill remaining with random base quests (no duplicates)
    need = count - len(out)
    chosen = random.sample(base, min(need, len(base)))
    for k in chosen:
        t_lo, t_hi, xp_lo, xp_hi, g_lo, g_hi, gem_chance, label_tpl = QUEST_DEFS[k]
        target = random.randint(t_lo, t_hi)
        target = _adjust_target(target, difficulty)
        out.append(_make_quest(k, target))
    return out


def ensure_daily_quests(
    state: dict[str, Any],
    deck_name: str | None = None,
    deck_due: int = 0,
    new_count: int = 0,
    difficulty: str | None = None,
    col: Any = None,
) -> dict[str, Any] | None:
    """
    If last_date is not today, reset daily state and roll new quests.
    Streak rewards are centrally granted in the UI refresh flow.
    """
    today = _today_str()
    if state.get("last_date") != today:
        state["last_date"] = today
        state["daily_xp"] = 0
        state["reviews_today"] = 0
        diff = difficulty or state.get("difficulty", "normal")
        state["daily_quests"] = roll_daily_quests(
            2, deck_name=deck_name, deck_due=deck_due, new_count=new_count, difficulty=diff
        )
        state["correct_today"] = 0
    return None


def on_review(
    state: dict[str, Any],
    ease: int,
    deck_name: str | None = None,
    is_new: bool = False,
    deck_due: int = 0,
    new_count: int = 0,
    fixed_xp: int | None = None,
    col: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[tuple[int, int]]]:
    """
    Update state for one review. Ease 1=Again, 2=Hard, 3=Good, 4=Easy.
    deck_name/is_new/deck_due/new_count are from desktop reviewer (for contextual quest progress and roll).
    Returns (list of quests that were just completed, streak_reward or None, quest_progress_revert).
    quest_progress_revert: (index, progress_before) for every quest that had progress advanced (for undo).
    """
    # Normalize ease (Anki 25 may pass card as ease in some builds)
    ease_val = ease if isinstance(ease, int) else 3
    is_again = ease_val <= 1
    streak_reward = ensure_daily_quests(
        state, deck_name=deck_name, deck_due=deck_due, new_count=new_count, col=col
    )
    completed = []
    quest_progress_revert: list[tuple[int, int]] = []  # (index, progress_before) for undo
    # Again does not count as 1 review done (shop, quests)
    if not is_again:
        state["reviews_today"] = state.get("reviews_today", 0) + 1

    # Daily XP (Again = 0). Synced reviews use fixed_xp (e.g. 8) when provided.
    from .xp import xp_for_review
    xp_this = fixed_xp if fixed_xp is not None else xp_for_review(ease_val)
    state["daily_xp"] = state.get("daily_xp", 0) + xp_this

    # Correct today (only Good and Easy count; Again and Hard do not)
    if ease_val >= 3:
        state["correct_today"] = state.get("correct_today", 0) + 1

    # Quest progress: Again does not advance review-type quests
    daily_quests = state.get("daily_quests", [])
    for i, q in enumerate(daily_quests):
        was_done = q.get("progress", 0) >= q.get("target", 0)
        qid = q.get("id", "")
        if not is_again:
            if qid.startswith("reviews") or qid.startswith("session"):
                progress_before = q.get("progress", 0)
                quest_progress_revert.append((i, progress_before))
                q["progress"] = progress_before + 1
            elif qid == "deck_reviews" and deck_name and q.get("deck_name") == deck_name:
                progress_before = q.get("progress", 0)
                quest_progress_revert.append((i, progress_before))
                q["progress"] = progress_before + 1
            elif qid == "new_cards" and is_new:
                progress_before = q.get("progress", 0)
                quest_progress_revert.append((i, progress_before))
                q["progress"] = progress_before + 1
        if qid.startswith("correct_today"):
            correct_today = state.get("correct_today", 0)
            target = q.get("target", 0)
            q["progress"] = min(correct_today, target)
        if not was_done and q.get("progress", 0) >= q.get("target", 0):
            completed.append(q)
    return (completed, streak_reward, quest_progress_revert)
