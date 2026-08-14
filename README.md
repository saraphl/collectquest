# CollectQuest (fork)

A personal fork of [CollectQuest](https://ankiweb.net/shared/info/627746544) by Florent Baris — an RPG-style progression layer for Anki (XP, levels, daily quests, gold, gems, collectibles, streaks, prestige).

All credit for the original add-on goes to the upstream author. This fork exists only to carry a few local changes.

## Changes in this fork

### Daily resets follow the scheduler's day, not civil midnight

Daily quests previously reset at midnight local time, ignoring Anki's **Preferences → Scheduler → Next day starts at** setting. With the default 4 a.m. rollover, a review at 00:30 belonged to *yesterday* as far as Anki was concerned, but already started a *new* day of daily quests.

The day boundary is now taken from that setting, which is what the streak code already did. The same boundary applies to the shop's daily unlock and free refresh, and to which synced phone reviews count as today's — without that last one, reviews done between midnight and rollover were dropped rather than credited.

### Reward bonuses that silently did nothing

Several items promised bonuses the game never applied — a better chance of gems from daily quests, and bigger 7-day streak payouts — as did the prestige *Quest reward* upgrade, which cost points and did nothing. They now work.

Separately, the count of claimed 7-day rewards carried over when a streak broke, so after three payouts a fresh streak needed 28 consecutive days rather than 7 to pay out again. It now resets when a streak ends or restarts — but not when a sync backfills a missing day, which extends the same streak.

### Daily quests scale to your workload

Quest targets used to be fixed numbers — complete 25 reviews, get 12 correct — regardless of how much you actually had due. Targets are now a share of the reviews Anki has genuinely scheduled for you today, counted before you start and capped by your deck limits, so a quest can never ask for more than Anki will hand you. The reward scales with how much the quest asks for.

There are four kinds: all decks, a single deck, correct answers, and new cards. "Session" quests are gone — they were the ordinary review quest under a different name, with nothing session-like about them. New-card quests now appear whenever your collection holds new cards at all, rather than only when new cards are scheduled, so they still turn up if you introduce new cards through **Custom Study**. Reviews done on your phone count towards every kind once you sync, deck-specific quests included.

Two smaller changes came along with it. Every answer now counts towards review quests, including *Again* — correct-answer quests still need *Good* or *Easy*. Difficulty no longer changes quest targets, since those already follow your real workload; it only sets how much XP a review is worth.
