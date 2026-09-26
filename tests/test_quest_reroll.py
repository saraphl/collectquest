"""
Pin the quest reroll: every pair of quests in play, against every deck layout, new-card supply and
amount of the day left. A reroll only swaps to a quest that can still be finished today, capped at
what's left, and the button says why when there is none. Exit 1 = a case changed.

    python3 tests/test_quest_reroll.py
"""
import copy
import importlib
import itertools
import pathlib
import random
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
for name in ("aqt", "aqt.qt", "aqt.utils", "aqt.theme", "anki", "anki.collection"):
    mod = types.ModuleType(name)
    mod.__getattr__ = lambda n: types.SimpleNamespace()
    sys.modules.setdefault(name, mod)
sys.modules["aqt"].mw = None
pkg = types.ModuleType("cq")
pkg.__path__ = [str(ROOT)]
sys.modules["cq"] = pkg

due_baseline = importlib.import_module("cq.src.due_baseline")
quests = importlib.import_module("cq.src.quests")
storage = importlib.import_module("cq.src.storage")
# Kept before the scenarios stub them.
REAL_REMAINING_TODAY = due_baseline.remaining_today
REAL_NEW_CARD_COUNT = due_baseline.new_card_count

FAILS = []
COL = object()  # never touched: remaining_today and new_card_count are stubbed per scenario
ROLLS = 300  # rerolls per scenario, enough to see every allowed kind and deck

TOTAL = quests.QUEST_KIND_TOTAL_REVIEWS
DECK = quests.QUEST_KIND_DECK_REVIEWS
CORRECT = quests.QUEST_KIND_CORRECT_REVIEWS
NEW = quests.QUEST_KIND_NEW_CARDS
NO_OTHER = quests.REROLL_BLOCKED_NO_OTHER
NOT_ENOUGH = quests.REROLL_BLOCKED_NOT_ENOUGH

# A 150-due day. Lowest targets written out by hand, so a change to the bands shows up here:
# reviews 30% of 150 = 45; correct 15% of 150 = 22.5, rounded to even = 22; new cards 3.
BASIS = 150
LOWEST = {TOTAL: 45, CORRECT: 22, NEW: 3}

# Deck layouts: (due per deck, lowest deck-quest target per eligible deck).
LAYOUTS = {
    # Both qualify; 30% of 100 and of 50 are under the 30-card floor.
    "two eligible decks": ({"1": 100, "2": 50}, {"1": 30, "2": 30}),
    # 25 and 15 are under DECK_MIN_DUE; 30% of 110 = 33.
    "one eligible deck": ({"1": 110, "2": 25, "3": 15}, {"1": 33}),
    # 140 is over DECK_MAX_SHARE, 10 under DECK_MIN_DUE.
    "no eligible deck": ({"1": 140, "2": 10}, {}),
}

# How much of the day is left: (total due, deck 1's due, every other deck's due), capped at the
# morning's counts. With 40 left only the correct-answers quest and deck 1 of the two-deck layout
# can still be finished.
LEFT = {
    "all cleared": (0, 0, 0),
    "40 left": (40, 30, 10),
    "untouched": (BASIS, BASIS, BASIS),
}

NEW_SUPPLY = {"no new cards": 0, "2 new cards": 2, "3 new cards": 3}


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got!r}")


def baseline_for(dues):
    return {
        "date": "2026-09-26",
        "total": BASIS,
        "decks": {did: {"name": f"Deck {did}", "due": due, "filtered": False} for did, due in dues.items()},
    }


def remaining_for(dues, left, new):
    left_total, left_first, left_rest = left
    return {
        "total": left_total,
        "decks": {did: min(due, left_first if did == "1" else left_rest) for did, due in dues.items()},
        "new": new,
    }


def quest(kind, deck_id=None, done=False):
    q = {"id": kind, "target": 50, "progress": 50 if done else 0, "label": kind}
    if kind == DECK:
        q.update({"deck_id": deck_id, "deck_name": f"Deck {deck_id}"})
    return q


def make_state(dues, in_play, correct_today=0):
    state = storage._default_state()
    state["quest_due_baseline"] = baseline_for(dues)
    state["daily_quests"] = in_play
    state["correct_today"] = correct_today
    return state


def stub(remaining):
    due_baseline.remaining_today = lambda col: remaining
    due_baseline.new_card_count = lambda col: remaining["new"] if remaining else 0


def expected(in_play_kinds, lowest_decks, remaining):
    """Hand-written spec: (candidate kinds, completable kinds, completable deck ids)."""
    candidates, completable, decks_ok = set(), set(), set()
    for kind in (TOTAL, CORRECT, DECK, NEW):
        if kind in in_play_kinds:
            continue
        if kind == DECK:
            if not lowest_decks:
                continue
            candidates.add(kind)
            decks_ok = {d for d, low in lowest_decks.items() if remaining["decks"][d] >= low}
            if decks_ok:
                completable.add(kind)
        elif kind == NEW:
            # Offered at all only with enough new cards for the smallest target.
            if remaining["new"] >= LOWEST[NEW]:
                candidates.add(kind)
                completable.add(kind)
        else:
            candidates.add(kind)
            if remaining["total"] >= LOWEST[kind]:
                completable.add(kind)
    return candidates, completable, decks_ok


def bounds(q, lowest_decks, remaining):
    """(lowest roll, what's left) for a rolled quest, from the hand-written numbers above."""
    if q["id"] == DECK:
        return lowest_decks[q["deck_id"]], remaining["decks"][q["deck_id"]]
    if q["id"] == NEW:
        return LOWEST[NEW], remaining["new"]
    return LOWEST[q["id"]], remaining["total"]


def answer(state, ease):
    """One answer through on_review, with the day already set up. Returns the quests it finished."""
    saved = (quests.ensure_daily_quests, quests.milestones.note_both_quests_complete, quests.milestones.advance_if_complete)
    quests.ensure_daily_quests = lambda state, col=None: None
    quests.milestones.note_both_quests_complete = lambda state, col=None: None
    quests.milestones.advance_if_complete = lambda state, col=None: None
    try:
        return quests.on_review(state, ease, counts_as_due_review=False)[0]
    finally:
        quests.ensure_daily_quests, quests.milestones.note_both_quests_complete, quests.milestones.advance_if_complete = saved


def run_matrix():
    """Every (rerolled kind, other kind) pair against every layout, day and new-card supply."""
    random.seed(1)
    scenarios = 0
    for layout, (dues, lowest_decks) in LAYOUTS.items():
        # A deck quest can only be in play if a deck qualifies; take the first eligible one.
        deck_in_play = next(iter(lowest_decks), None)
        for this_kind, other_kind in itertools.permutations((TOTAL, CORRECT, DECK, NEW), 2):
            if DECK in (this_kind, other_kind) and deck_in_play is None:
                continue
            for (left_name, left), (supply, new) in itertools.product(
                LEFT.items(), NEW_SUPPLY.items()
            ):
                scenarios += 1
                remaining = remaining_for(dues, left, new)
                stub(remaining)
                in_play = [quest(this_kind, deck_in_play), quest(other_kind, deck_in_play)]
                state = make_state(dues, in_play)
                candidates, completable, decks_ok = expected({this_kind, other_kind}, lowest_decks, remaining)
                name = f"{layout}, {left_name}, {supply}: reroll {this_kind} beside {other_kind}"

                want_reason = None if completable else (NOT_ENOUGH if candidates else NO_OTHER)
                got_reason = quests.reroll_block_reason(state, 0, COL, remaining)
                if got_reason != want_reason:
                    check(f"{name} - block reason", got_reason, want_reason)

                seen_kinds, seen_decks = set(), set()
                for _ in range(ROLLS):
                    trial = copy.deepcopy(state)
                    new_quest = quests.reroll_quest(trial, 0, COL)
                    if new_quest is None:
                        if trial != state:
                            check(f"{name} - refused reroll leaves state alone", "changed", "unchanged")
                        break
                    seen_kinds.add(new_quest["id"])
                    if new_quest["id"] == DECK:
                        seen_decks.add(new_quest["deck_id"])
                    low, left_for_it = bounds(new_quest, lowest_decks, remaining)
                    if not low <= new_quest["target"] <= left_for_it:
                        check(f"{name} - target within [{low}, {left_for_it}]", new_quest["target"], "inside")
                        break
                    if trial["daily_quests"][1] != state["daily_quests"][1]:
                        check(f"{name} - other quest kept", "changed", "unchanged")
                        break
                if seen_kinds != completable:
                    check(f"{name} - kinds rolled", sorted(seen_kinds), sorted(completable))
                if DECK in completable and seen_decks != decks_ok:
                    check(f"{name} - decks rolled", sorted(seen_decks), sorted(decks_ok))
    # 12 ordered pairs for each layout with a deck quest, 6 without, each over 3 days x 3 supplies.
    check("scenarios run (failures listed above)", scenarios, (12 + 12 + 6) * 9)


def run_edges():
    dues, _ = LAYOUTS["two eligible decks"]
    plenty = remaining_for(dues, LEFT["untouched"], 10)

    print("the reported scenario: 150 due over two decks, all cleared, rerolling Learn new cards")
    cleared = remaining_for(dues, LEFT["all cleared"], 10)
    stub(cleared)
    for other in (TOTAL, CORRECT, ("deck", "1")):
        other_q = quest(DECK, "1") if isinstance(other, tuple) else quest(other)
        state = make_state(dues, [quest(NEW), other_q], correct_today=140)
        check(f"new cards beside {other_q['id']} - blocked", quests.reroll_block_reason(state, 0, COL, cleared), NOT_ENOUGH)
        check(f"new cards beside {other_q['id']} - reroll refused", quests.reroll_quest(state, 0, COL), None)
        # Nor the other one: Learn new cards is already in play.
        rolled = quests.reroll_quest(copy.deepcopy(state), 1, COL)
        check(f"{other_q['id']} beside new cards - still blocked", rolled, None)
    state = make_state(dues, [quest(TOTAL), quest(CORRECT)], correct_today=140)
    check("total beside correct, all cleared - swaps to new cards", quests.reroll_quest(state, 0, COL)["id"], NEW)

    print("quests that can't be rerolled at all")
    stub(plenty)
    state = make_state(dues, [quest(NEW, done=True), quest(TOTAL)])
    check("finished quest - blocked", quests.reroll_block_reason(state, 0, COL, plenty), NO_OTHER)
    check("finished quest - refused", quests.reroll_quest(state, 0, COL), None)
    state = make_state(dues, [quest(NEW), quest(TOTAL)])
    check("bad index - refused", quests.reroll_quest(state, 5, COL), None)
    check("negative index - refused", quests.reroll_quest(state, -1, COL), None)
    state["quest_due_baseline"] = {}
    check("no baseline - blocked", quests.reroll_block_reason(state, 0, COL, plenty), NO_OTHER)
    check("no baseline - refused", quests.reroll_quest(state, 0, COL), None)

    print("unmeasurable day filters nothing")
    stub(None)
    due_baseline.new_card_count = lambda col: 10
    state = make_state(dues, [quest(NEW), quest(TOTAL)])
    check("unmeasured - not blocked", quests.reroll_block_reason(state, 0, COL, None), None)
    random.seed(2)
    kinds = {quests.reroll_quest(copy.deepcopy(state), 0, COL)["id"] for _ in range(ROLLS)}
    check("unmeasured - rolls every other kind", sorted(kinds), sorted({CORRECT, DECK}))

    print("correct-answers quest counts only answers given after it appeared")
    stub(remaining_for(dues, (40, 0, 0), 0))  # only the correct-answers quest is left to roll
    random.seed(3)
    state = make_state(dues, [quest(TOTAL), quest(NEW)], correct_today=140)
    q = quests.reroll_quest(state, 0, COL)
    check("rerolled after 140 correct - progress", q["progress"], 0)
    check("rerolled after 140 correct - start", q["correct_start"], 140)
    answer(state, 3)
    answer(state, 1)  # Again doesn't count
    answer(state, 4)
    check("two correct answers later", q["progress"], 2)
    completed = []
    for _ in range(q["target"] - 2):
        completed += answer(state, 3)
    check("pays when its own target is reached", [c["id"] for c in completed], [CORRECT])
    check("finished quest stops counting", (answer(state, 3), q["progress"]), ([], q["target"]))
    # Undo's recompute: answers from before the reroll never go negative.
    check("undone below its start", quests.correct_quest_progress(q, 100), 0)
    check("undone to its start + 5", quests.correct_quest_progress(q, 145), 5)
    check("older save without a start counts the whole day", quests.correct_quest_progress(quest(CORRECT), 12), 12)

    print("quests rolled mid-day start from the day's count too")
    due_baseline.new_card_count = lambda col: 0  # total and correct only, so both roll every time
    rolled = quests.roll_daily_quests(baseline=baseline_for({"1": 150}), col=COL, correct_today=30)
    check("any roll path - start", [q.get("correct_start") for q in rolled if q["id"] == CORRECT], [30])
    saved = (due_baseline.ensure_baseline, quests._today_str)
    due_baseline.ensure_baseline = lambda state, col: state["quest_due_baseline"]
    quests._today_str = lambda: "2026-09-26"
    try:
        state = make_state(dues, [], correct_today=30)
        state["last_date"] = "2026-09-26"
        rolled = []
        for seed in range(40):
            random.seed(seed)
            trial = copy.deepcopy(state)
            quests.ensure_daily_quests(trial, None)
            rolled += trial["daily_quests"]
        starts = {q["correct_start"] for q in rolled if q["id"] == CORRECT}
        check("empty list rolled mid-day - start", starts, {30})
        trial = copy.deepcopy(state)
        trial["last_date"] = "2026-09-25"
        random.seed(1)
        quests.ensure_daily_quests(trial, None)
        starts = {q["correct_start"] for q in trial["daily_quests"] if q["id"] == CORRECT}
        check("new day - count reset, starts from 0", (trial["correct_today"], starts <= {0}), (0, True))
    finally:
        due_baseline.ensure_baseline, quests._today_str = saved

    print("targets are capped at what's left, and pay for the capped target")
    random.seed(5)
    for kind, left, low, cap in (
        (TOTAL, (50, 0, 0), 45, 50),
        (CORRECT, (25, 0, 0), 22, 25),
        (DECK, (0, 35, 0), 30, 35),
    ):
        stub(remaining_for(dues, left, 0))
        # The other kinds are in play, or have nothing left, so only `kind` can roll.
        other = CORRECT if kind == TOTAL else TOTAL
        state = make_state(dues, [quest(NEW), quest(other)])
        rolled = [quests.reroll_quest(copy.deepcopy(state), 0, COL) for _ in range(ROLLS)]
        targets = {q["target"] for q in rolled}
        check(f"{kind} - targets within [{low}, {cap}]", all(low <= t <= cap for t in targets), True)
        check(f"{kind} - rolls over what's left land on it", cap in targets, True)
    stub(remaining_for(dues, (0, 0, 0), 4))
    state = make_state(dues, [quest(TOTAL), quest(CORRECT)])
    rolled = [quests.reroll_quest(copy.deepcopy(state), 0, COL) for _ in range(ROLLS)]
    check("new cards - 5 capped to the 4 left", {q["target"] for q in rolled}, {3, 4})
    # 50 of 150 is 33.3%, 8.3% into the 30-70% band: 60 + 160 * 0.083 XP, 8 + 16 * 0.083 gold.
    stub(remaining_for(dues, (50, 0, 0), 0))
    state = make_state(dues, [quest(NEW), quest(CORRECT)])
    capped = next(q for q in (quests.reroll_quest(copy.deepcopy(state), 0, COL) for _ in range(ROLLS)) if q["target"] == 50)
    check("capped at 50 - XP", capped["reward_xp"], 73)
    check("capped at 50 - gold", capped["reward_gold"], 9)
    check("capped at 50 - label", capped["label"], "Review 50 cards")

    print("daily roll offers new cards only with 3 or more, capped at the count")
    for new, want in ((0, set()), (2, set()), (3, {3}), (4, {3, 4}), (10, {3, 4, 5})):
        due_baseline.new_card_count = lambda col, n=new: n
        random.seed(6)
        targets = set()
        for _ in range(ROLLS):
            rolled = quests.roll_daily_quests(baseline=baseline_for(dues), col=COL)
            targets |= {q["target"] for q in rolled if q["id"] == NEW}
        check(f"{new} new cards - targets", targets, want)

    print("lowest target matches what the builders roll at the bottom of the band")
    saved = random.uniform
    random.uniform = lambda a, b: a
    try:
        for basis in (0, 5, 9, 10, 60, 75, 150, 151, 1000):
            baseline = {"total": basis}
            got = quests._build_total_reviews(basis)["target"]
            check(f"total, basis {basis}", quests._lowest_target((TOTAL, None), baseline), got)
            got = quests._build_correct_reviews(basis)["target"]
            check(f"correct, basis {basis}", quests._lowest_target((CORRECT, None), baseline), got)
        for due in (30, 50, 99, 100, 101, 500):
            deck = {"id": "1", "name": "Deck", "due": due, "share": 0.5}
            got = quests._build_deck_reviews(deck)["target"]
            check(f"deck, due {due}", quests._lowest_target((DECK, deck), {"total": 1000}), got)
    finally:
        random.uniform = saved
    random.seed(4)
    news = {quests._build_new_cards()["target"] for _ in range(ROLLS)}
    check("new cards, lowest roll", quests._lowest_target((NEW, None), {}), min(news))


def run_remaining_today():
    print("remaining_today: live counts net of cards first seen today")
    live = (
        90,
        {
            "1": {"name": "Lang", "due": 60, "filtered": False},
            "2": {"name": "Lang::Kanji", "due": 25, "filtered": False},
            "3": {"name": "Other", "due": 30, "filtered": False},
        },
    )
    learning = {"Lang::Kanji": 20, "Other": 40}
    db = types.SimpleNamespace(scalar=lambda sql, *a: 7)
    col = types.SimpleNamespace(db=db)
    saved = (due_baseline.live_counts, due_baseline._new_today_in_learning_by_deck)
    remaining_today = REAL_REMAINING_TODAY
    due_baseline.new_card_count = REAL_NEW_CARD_COUNT
    due_baseline.live_counts = lambda c: live
    due_baseline._new_today_in_learning_by_deck = lambda c: learning
    got = remaining_today(col)
    check("total", got["total"], 30)
    check("parent deck counts its subdeck's learning", got["decks"]["1"], 40)
    check("subdeck", got["decks"]["2"], 5)
    check("clamped at zero", got["decks"]["3"], 0)
    check("new cards", got["new"], 7)
    check("no collection", remaining_today(None), None)

    def boom(c):
        raise due_baseline.BaselineUnavailable("test")

    due_baseline.live_counts = boom
    check("unmeasurable", remaining_today(col), None)
    due_baseline.live_counts, due_baseline._new_today_in_learning_by_deck = saved


print("reroll matrix")
run_matrix()
run_edges()
run_remaining_today()

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    sys.exit(1)
print("all passed")
