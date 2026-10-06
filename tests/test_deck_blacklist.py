"""
Blacklisted decks against a real Anki collection: left out of the day's totals, deck quests and
quest progress, with the deck blacklist fixed for the day once measured. Needs the anki package.

    python3 tests/test_deck_blacklist.py
"""
import datetime, os, sys, tempfile, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _n in ("aqt", "aqt.qt", "aqt.utils", "aqt.gui_hooks", "aqt.operations"):
    sys.modules.setdefault(_n, types.ModuleType(_n))
from anki.collection import Collection  # noqa: E402
from src import deck_blacklist, due_baseline, quests, review_rewards, storage  # noqa: E402

fails = 0


def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}" + ("" if ok else f" (want {want})"))


def add_cards(col, deck_name, n, review=True):
    did = col.decks.id(deck_name)
    for i in range(n):
        note = col.new_note(col.models.by_name("Basic"))
        note["Front"] = f"{deck_name} {i}"
        col.add_note(note, did)
    if review:
        col.db.execute(
            "UPDATE cards SET type = 2, queue = 2, due = ?, ivl = 30, factor = 2500 WHERE did = ?",
            col.sched.today, did)
    return did


def answer_in(col, did, state):
    col.decks.select(did)
    card = col.sched.getCard()
    col.sched.answerCard(card, 3)
    return review_rewards.apply_one_review(
        state, 3, deck_name=col.decks.name(card.did), counts_as_due_review=True, col=col)


with tempfile.TemporaryDirectory() as tmp:
    col = Collection(os.path.join(tmp, "c.anki2"))
    try:
        col.set_config("rollover", (datetime.datetime.now().hour + 12) % 24)
        active = add_cards(col, "Active", 50)
        old = add_cards(col, "Old", 100)
        add_cards(col, "Old::Sub", 30)
        add_cards(col, "Old", 5, review=False)  # new cards
        add_cards(col, "Active::New", 2, review=False)
        add_cards(col, "Lang::A", 40)
        lang_b = add_cards(col, "Lang::B", 60)
        # Lang's own limit binds: it shows 70 of its children's 100.
        conf = col.decks.add_config_returning_id("Lang limit")
        c = col.decks.get_config(conf)
        c["rev"]["perDay"] = 70
        col.decks.update_config(c)
        lang = col.decks.get(col.decks.id("Lang"))
        lang["conf"] = conf
        col.decks.save(lang)

        print("no deck blacklist")
        state = storage._default_state()
        base = due_baseline.ensure_baseline(state, col)
        check("day total", base["total"], 50 + 130 + 70)
        check("new cards", due_baseline.new_card_count(col), 7)

        print("Old and Lang::B blacklisted")
        deck_blacklist.set_configured(col, [old, lang_b])
        check("stored in the collection", deck_blacklist.configured(col), sorted([old, lang_b]))
        check("today's baseline is kept", due_baseline.ensure_baseline(state, col)["total"], 250)
        state = storage._default_state()
        base = due_baseline.ensure_baseline(state, col)
        check("day total", base["total"], 50 + 40)
        decks = {d["name"]: d for d in base["decks"].values()}
        check("Lang keeps only Lang::A under its limit", decks["Lang"]["due"], 40)
        check("subdeck excluded with its parent", decks["Old::Sub"]["excluded"], True)
        check("deck quest candidates", sorted(d["name"] for d in quests.eligible_decks(base)),
              ["Active", "Lang", "Lang::A"])
        check("new cards", due_baseline.new_card_count(col, quests.excluded_today(state, col)), 2)
        check("bonus quest", due_baseline.cleared_progress(state, col), (0, 90))

        quests.ensure_daily_quests(state, col)
        state["daily_quests"] = [quests._build_total_reviews(90)]
        before = (state["correct_today"], state["daily_quests"][0]["progress"])
        earned = answer_in(col, col.decks.id("Old::Sub"), state)
        check("blacklisted answer leaves quests alone",
              (state["correct_today"], state["daily_quests"][0]["progress"]), before)
        check("its undo leaves correct_today alone", earned["undo_deltas"]["was_correct"], False)
        check("bonus quest ignores it", due_baseline.cleared_progress(state, col), (0, 90))
        answer_in(col, active, state)
        check("an Active answer counts",
              (state["correct_today"], state["daily_quests"][0]["progress"]), (before[0] + 1, before[1] + 1))
        check("bonus quest counts it", due_baseline.cleared_progress(state, col), (1, 90))
        left = due_baseline.remaining_today(col, quests.excluded_today(state, col))
        check("what rerolls see as left", (left["total"], left["new"]), (89, 2))

        print("unticked mid-day")
        deck_blacklist.set_configured(col, [])
        check("saving it keeps Anki's undo", col.undo_status().undo, "Answer Card")
        check("today keeps its deck blacklist", quests.counts_for_quests(state, "Old", col), False)
    finally:
        col.close()

print("FAILED" if fails else "all deck blacklist checks passed")
sys.exit(1 if fails else 0)
